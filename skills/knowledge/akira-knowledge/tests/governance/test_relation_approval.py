from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[2]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class RelationApprovalBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.a_path = self.knowledge / "A.md"
        self.b_path = self.knowledge / "B.md"
        self.a_path.write_text("# A\n\nSource Authority.\n", encoding="utf-8")
        self.b_path.write_text("# B\n\nTarget Authority.\n", encoding="utf-8")

        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/A.md",
                "--note", "Knowledge/B.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )["registered"]
        self.identities = {
            Path(item["locator"]).name: item["identity"]
            for item in registered
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    def run_cli(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            expect,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def propose(
        self,
        *,
        relation_type: str = "supports",
        provenance: str = "basis-one",
    ) -> dict[str, object]:
        return json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.identities["A.md"],
                "--type", relation_type,
                "--target-id", self.identities["B.md"],
                "--provenance", provenance,
            ).stdout
        )

    def approve(
        self,
        candidate_id: str,
        *,
        confirmed: bool = True,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "relation-approve",
            "--vault", str(self.vault),
            "--candidate-id", candidate_id,
        ]
        if confirmed:
            args.append("--confirmed-approval")
        return self.run_cli(*args, expect=expect)

    def relation_rows(self) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, revision "
                "FROM relation_records ORDER BY identity"
            ).fetchall()

    def provenance(self, relation_identity: str) -> list[str]:
        with sqlite3.connect(self.database) as conn:
            initial = conn.execute(
                "SELECT provenance FROM relation_records WHERE identity = ?",
                (relation_identity,),
            ).fetchone()[0]
            additions = conn.execute(
                "SELECT provenance FROM relation_provenance_additions "
                "WHERE relation_identity = ? ORDER BY recorded_at, provenance",
                (relation_identity,),
            ).fetchall()
        return [initial] + [row[0] for row in additions]

    def test_explicit_approval_creates_relation_and_existing_traversal_reads_it(self) -> None:
        candidate = self.propose()

        denied = self.approve(candidate["candidate_id"], confirmed=False, expect=2)
        self.assertIn("explicit user approval", denied.stderr)
        self.assertEqual([], self.relation_rows())

        approved = json.loads(self.approve(candidate["candidate_id"]).stdout)
        self.assertEqual("accepted", approved["status"])
        self.assertTrue(approved["relation_created"])
        self.assertTrue(approved["provenance_added"])
        self.assertEqual(1, approved["relation_revision"])
        self.assertEqual(["basis-one"], approved["provenance"])
        relation_identity = approved["relation_identity"]
        self.assertNotEqual(candidate["candidate_id"], relation_identity)

        rows = self.relation_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(
            (
                relation_identity,
                self.identities["A.md"],
                "supports",
                self.identities["B.md"],
                "basis-one",
                1,
            ),
            rows[0],
        )
        with sqlite3.connect(self.database) as conn:
            candidate_state = conn.execute(
                "SELECT status, result_relation_identity FROM relation_candidates "
                "WHERE candidate_id = ?",
                (candidate["candidate_id"],),
            ).fetchone()
            events = conn.execute(
                "SELECT revision, event, provenance FROM relation_events "
                "WHERE relation_identity = ? ORDER BY revision",
                (relation_identity,),
            ).fetchall()
        self.assertEqual(("accepted", relation_identity), candidate_state)
        self.assertEqual([(1, "created_from_candidate", "basis-one")], events)

        traversal = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "use accepted relation",
                "--relation-seed", self.identities["A.md"],
                "--relation-direction", "outgoing",
                "--relation-type", "supports",
            ).stdout
        )
        self.assertEqual(
            [self.identities["B.md"]],
            [item["stable_identity"] for item in traversal["results"]],
        )
        relation = traversal["results"][0]["matches"][0]["relation"]
        self.assertEqual(relation_identity, relation["identity"])
        self.assertEqual(["basis-one"], relation["provenance_entries"])

    def test_stale_candidate_cannot_be_approved(self) -> None:
        candidate = self.propose()
        current = self.b_path.read_text(encoding="utf-8")
        self.b_path.write_text(
            current.replace("Target Authority.", "Changed after candidate."),
            encoding="utf-8",
        )

        failed = self.approve(candidate["candidate_id"], expect=2)

        self.assertIn("stale", failed.stderr.lower())
        self.assertEqual([], self.relation_rows())
        with sqlite3.connect(self.database) as conn:
            status = conn.execute(
                "SELECT status FROM relation_candidates WHERE candidate_id = ?",
                (candidate["candidate_id"],),
            ).fetchone()[0]
        self.assertEqual("stale", status)

    def test_new_provenance_reuses_identity_and_advances_revision(self) -> None:
        first_candidate = self.propose(provenance="basis-one")
        first = json.loads(self.approve(first_candidate["candidate_id"]).stdout)
        identity = first["relation_identity"]

        second_candidate = self.propose(provenance="basis-two")
        second = json.loads(self.approve(second_candidate["candidate_id"]).stdout)

        self.assertEqual(identity, second["relation_identity"])
        self.assertFalse(second["relation_created"])
        self.assertTrue(second["provenance_added"])
        self.assertEqual(2, second["relation_revision"])
        self.assertEqual(["basis-one", "basis-two"], second["provenance"])
        self.assertEqual(1, len(self.relation_rows()))
        self.assertEqual(["basis-one", "basis-two"], self.provenance(identity))

        traversal = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "read all relation provenance",
                "--relation-seed", self.identities["A.md"],
                "--relation-direction", "outgoing",
            ).stdout
        )
        relation = traversal["results"][0]["matches"][0]["relation"]
        self.assertEqual(2, relation["revision"])
        self.assertEqual(["basis-one", "basis-two"], relation["provenance_entries"])

    def test_duplicate_provenance_is_idempotent(self) -> None:
        first_candidate = self.propose(provenance="same-basis")
        first = json.loads(self.approve(first_candidate["candidate_id"]).stdout)

        duplicate_candidate = self.propose(provenance="same-basis")
        duplicate = json.loads(self.approve(duplicate_candidate["candidate_id"]).stdout)

        self.assertEqual(first["relation_identity"], duplicate["relation_identity"])
        self.assertFalse(duplicate["relation_created"])
        self.assertFalse(duplicate["provenance_added"])
        self.assertEqual(1, duplicate["relation_revision"])
        self.assertEqual(["same-basis"], duplicate["provenance"])
        with sqlite3.connect(self.database) as conn:
            event_count = conn.execute(
                "SELECT COUNT(*) FROM relation_events WHERE relation_identity = ?",
                (first["relation_identity"],),
            ).fetchone()[0]
        self.assertEqual(1, event_count)

    def test_different_type_creates_new_relation_identity_without_mutating_original(self) -> None:
        first_candidate = self.propose(relation_type="supports", provenance="support-basis")
        first = json.loads(self.approve(first_candidate["candidate_id"]).stdout)

        second_candidate = self.propose(relation_type="contrasts", provenance="contrast-basis")
        second = json.loads(self.approve(second_candidate["candidate_id"]).stdout)

        self.assertNotEqual(first["relation_identity"], second["relation_identity"])
        self.assertEqual(2, len(self.relation_rows()))
        triples = {
            (row[1], row[2], row[3], row[4], row[5])
            for row in self.relation_rows()
        }
        self.assertIn(
            (
                self.identities["A.md"],
                "supports",
                self.identities["B.md"],
                "support-basis",
                1,
            ),
            triples,
        )
        self.assertIn(
            (
                self.identities["A.md"],
                "contrasts",
                self.identities["B.md"],
                "contrast-basis",
                1,
            ),
            triples,
        )

    def test_legacy_02_relation_is_preserved_and_extended_in_place(self) -> None:
        legacy_identity = "01991f4a-7abc-7def-8123-456789abc099"
        with sqlite3.connect(self.database) as conn:
            conn.execute(
                "INSERT INTO relation_records(identity, source_ref, relation_type, target_ref, provenance, revision) "
                "VALUES (?, ?, 'supports', ?, 'legacy-basis', 1)",
                (
                    legacy_identity,
                    self.identities["A.md"],
                    self.identities["B.md"],
                ),
            )
            conn.execute("DROP TABLE relation_candidates")
            conn.execute("DROP TABLE relation_events")
            conn.execute("DROP TABLE relation_provenance_additions")
            conn.commit()

        candidate = self.propose(provenance="new-0.3-basis")
        approved = json.loads(self.approve(candidate["candidate_id"]).stdout)

        self.assertEqual(legacy_identity, approved["relation_identity"])
        self.assertFalse(approved["relation_created"])
        self.assertEqual(2, approved["relation_revision"])
        self.assertEqual(
            ["legacy-basis", "new-0.3-basis"],
            approved["provenance"],
        )
        rows = self.relation_rows()
        self.assertEqual(
            (
                legacy_identity,
                self.identities["A.md"],
                "supports",
                self.identities["B.md"],
                "legacy-basis",
                2,
            ),
            rows[0],
        )
        with sqlite3.connect(self.database) as conn:
            events = conn.execute(
                "SELECT revision, event, provenance FROM relation_events "
                "WHERE relation_identity = ? ORDER BY revision",
                (legacy_identity,),
            ).fetchall()
        self.assertEqual(
            [
                (1, "existing_relation", "legacy-basis"),
                (2, "provenance_added", "new-0.3-basis"),
            ],
            events,
        )


if __name__ == "__main__":
    unittest.main()
