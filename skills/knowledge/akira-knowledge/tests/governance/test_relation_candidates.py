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


class RelationCandidateBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)

        self.a_path = self.knowledge / "A.md"
        self.b_path = self.knowledge / "B.md"
        self.a_path.write_text(
            "---\n"
            "topic: network\n"
            "---\n"
            "# A\n\n"
            "A has an ordinary [[B]] navigation link.\n",
            encoding="utf-8",
        )
        self.b_path.write_text(
            "---\n"
            "topic: network\n"
            "---\n"
            "# B\n\n"
            "B current Authority.\n",
            encoding="utf-8",
        )

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

    def relation_count(self) -> int:
        with sqlite3.connect(self.database) as conn:
            return conn.execute("SELECT COUNT(*) FROM relation_records").fetchone()[0]

    def candidate_count(self) -> int:
        with sqlite3.connect(self.database) as conn:
            return conn.execute("SELECT COUNT(*) FROM relation_candidates").fetchone()[0]

    def object_rows(self) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, kind, locator, revision, authority_fingerprint "
                "FROM objects ORDER BY identity"
            ).fetchall()

    def revision_rows(self) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, revision, event, locator, authority_fingerprint "
                "FROM revisions ORDER BY identity, revision"
            ).fetchall()

    def propose_local(
        self,
        *,
        source: str | None = None,
        target: str | None = None,
        relation_type: str = "supports",
        provenance: str = "user-reviewed evidence",
    ) -> dict[str, object]:
        source = source or self.identities["A.md"]
        target = target or self.identities["B.md"]
        return json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", source,
                "--type", relation_type,
                "--target-id", target,
                "--provenance", provenance,
            ).stdout
        )

    def test_candidate_is_governance_state_not_relation_authority(self) -> None:
        before_objects = self.object_rows()
        before_revisions = self.revision_rows()

        candidate = self.propose_local()

        self.assertEqual("pending", candidate["status"])
        self.assertEqual("knowledge", candidate["source"]["kind"])
        self.assertEqual(self.identities["A.md"], candidate["source"]["ref"])
        self.assertEqual(1, candidate["source"]["revision"])
        self.assertIsNotNone(candidate["source"]["authority_fingerprint"])
        self.assertEqual("knowledge", candidate["target"]["kind"])
        self.assertEqual("supports", candidate["type"])
        self.assertEqual("user-reviewed evidence", candidate["provenance"])

        with sqlite3.connect(self.database) as conn:
            candidate_row = conn.execute(
                "SELECT candidate_id, status, source_ref, relation_type, target_ref, provenance "
                "FROM relation_candidates WHERE candidate_id = ?",
                (candidate["candidate_id"],),
            ).fetchone()
            object_candidate = conn.execute(
                "SELECT COUNT(*) FROM objects WHERE identity = ?",
                (candidate["candidate_id"],),
            ).fetchone()[0]
        self.assertEqual(
            (
                candidate["candidate_id"],
                "pending",
                self.identities["A.md"],
                "supports",
                self.identities["B.md"],
                "user-reviewed evidence",
            ),
            candidate_row,
        )
        self.assertEqual(0, object_candidate)
        self.assertEqual(0, self.relation_count())
        self.assertEqual(before_objects, self.object_rows())
        self.assertEqual(before_revisions, self.revision_rows())

        traversal = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "pending candidate must not affect retrieval",
                "--relation-seed", self.identities["A.md"],
                "--relation-direction", "outgoing",
            ).stdout
        )
        self.assertEqual([], traversal["results"])
        self.assertFalse((self.vault / "AK Graph").exists())

    def test_reject_preserves_candidate_record_without_relation_authority(self) -> None:
        candidate = self.propose_local()

        denied = self.run_cli(
            "relation-reject",
            "--vault", str(self.vault),
            "--candidate-id", candidate["candidate_id"],
            expect=2,
        )
        self.assertIn("explicit user rejection", denied.stderr)

        rejected = json.loads(
            self.run_cli(
                "relation-reject",
                "--vault", str(self.vault),
                "--candidate-id", candidate["candidate_id"],
                "--confirmed-rejection",
            ).stdout
        )
        self.assertEqual("rejected", rejected["status"])
        with sqlite3.connect(self.database) as conn:
            status = conn.execute(
                "SELECT status FROM relation_candidates WHERE candidate_id = ?",
                (candidate["candidate_id"],),
            ).fetchone()[0]
        self.assertEqual("rejected", status)
        self.assertEqual(0, self.relation_count())

    def test_authority_edit_after_candidate_marks_it_stale(self) -> None:
        candidate = self.propose_local()
        original = self.b_path.read_text(encoding="utf-8")
        self.b_path.write_text(
            original.replace("B current Authority.", "B changed after candidate creation."),
            encoding="utf-8",
        )

        inspected = json.loads(
            self.run_cli(
                "relation-inspect",
                "--vault", str(self.vault),
                "--candidate-id", candidate["candidate_id"],
            ).stdout
        )

        self.assertEqual("stale", inspected["status"])
        self.assertEqual(1, inspected["target"]["revision"])
        self.assertEqual(2, inspected["current_target"]["revision"])
        self.assertNotEqual(
            inspected["target"]["authority_fingerprint"],
            inspected["current_target"]["authority_fingerprint"],
        )
        self.assertEqual(0, self.relation_count())

    def test_pure_rename_keeps_candidate_pending(self) -> None:
        candidate = self.propose_local()
        moved = self.knowledge / "Renamed-B.md"
        self.b_path.rename(moved)

        inspected = json.loads(
            self.run_cli(
                "relation-inspect",
                "--vault", str(self.vault),
                "--candidate-id", candidate["candidate_id"],
            ).stdout
        )

        self.assertEqual("pending", inspected["status"])
        self.assertEqual(1, inspected["target"]["revision"])
        self.assertEqual(2, inspected["current_target"]["revision"])
        self.assertEqual(
            inspected["target"]["authority_fingerprint"],
            inspected["current_target"]["authority_fingerprint"],
        )
        self.assertEqual("Knowledge/Renamed-B.md", inspected["current_target"]["canonical_locator"])
        self.assertEqual(0, self.relation_count())

    def test_external_reference_endpoint_is_explicit_and_not_local_object(self) -> None:
        candidate = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.identities["A.md"],
                "--type", "references",
                "--target-external", "doi:10.1000/example",
                "--provenance", "explicit external citation",
            ).stdout
        )

        self.assertEqual("external", candidate["target"]["kind"])
        self.assertEqual("doi:10.1000/example", candidate["target"]["ref"])
        self.assertIsNone(candidate["target"]["revision"])
        self.assertIsNone(candidate["target"]["authority_fingerprint"])
        self.assertEqual(0, self.relation_count())

    def test_navigation_and_retrieval_do_not_auto_create_candidate(self) -> None:
        self.assertEqual(0, self.candidate_count())

        self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "navigation link",
        )
        self.run_cli(
            "retrieve-task",
            "--vault", str(self.vault),
            "--task", "find network knowledge",
            "--query", "network",
        )

        self.assertEqual(0, self.candidate_count())
        self.assertEqual(0, self.relation_count())

    def test_02_schema_upgrade_is_additive(self) -> None:
        before_objects = self.object_rows()
        before_revisions = self.revision_rows()
        with sqlite3.connect(self.database) as conn:
            conn.execute("DROP TABLE relation_candidates")
            conn.commit()

        candidate = self.propose_local(provenance="schema upgrade check")
        self.assertEqual("pending", candidate["status"])
        self.assertEqual(before_objects, self.object_rows())
        self.assertEqual(before_revisions, self.revision_rows())
        self.assertEqual(0, self.relation_count())


if __name__ == "__main__":
    unittest.main()
