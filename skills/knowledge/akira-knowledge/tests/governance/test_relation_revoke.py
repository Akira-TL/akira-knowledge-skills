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


class RelationRevokeBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        (self.knowledge / "A.md").write_text("# A\n\nSource.\n", encoding="utf-8")
        (self.knowledge / "B.md").write_text("# B\n\nTarget.\n", encoding="utf-8")
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

    def propose_and_approve(self, provenance: str = "basis-one") -> dict[str, object]:
        candidate = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.identities["A.md"],
                "--type", "supports",
                "--target-id", self.identities["B.md"],
                "--provenance", provenance,
            ).stdout
        )
        return json.loads(
            self.run_cli(
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", candidate["candidate_id"],
                "--confirmed-approval",
            ).stdout
        )

    def revoke(
        self,
        relation_id: str,
        revision: int,
        *,
        confirmed: bool = True,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "relation-revoke",
            "--vault", str(self.vault),
            "--relation-id", relation_id,
            "--expected-revision", str(revision),
        ]
        if confirmed:
            args.append("--confirmed-revoke")
        return self.run_cli(*args, expect=expect)

    def relation_row(self, relation_id: str) -> tuple[object, ...]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
                "FROM relation_records WHERE identity = ?",
                (relation_id,),
            ).fetchone()

    def relation_events(self, relation_id: str) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT revision, event, provenance FROM relation_events "
                "WHERE relation_identity = ? ORDER BY revision",
                (relation_id,),
            ).fetchall()

    def test_explicit_revoke_preserves_identity_triple_provenance_and_history(self) -> None:
        approved = self.propose_and_approve()
        relation_id = approved["relation_identity"]

        denied = self.revoke(relation_id, 1, confirmed=False, expect=2)
        self.assertIn("explicit user confirmation", denied.stderr)
        self.assertEqual("active", self.relation_row(relation_id)[6])

        revoked = json.loads(self.revoke(relation_id, 1).stdout)

        self.assertEqual(relation_id, revoked["relation_identity"])
        self.assertEqual(self.identities["A.md"], revoked["source"])
        self.assertEqual("supports", revoked["type"])
        self.assertEqual(self.identities["B.md"], revoked["target"])
        self.assertEqual(["basis-one"], revoked["provenance"])
        self.assertEqual("revoked", revoked["status"])
        self.assertEqual(2, revoked["revision"])
        self.assertTrue(revoked["changed"])
        self.assertEqual(
            (
                relation_id,
                self.identities["A.md"],
                "supports",
                self.identities["B.md"],
                "basis-one",
                2,
                "revoked",
            ),
            self.relation_row(relation_id),
        )
        self.assertEqual(
            [
                (1, "created_from_candidate", "basis-one"),
                (2, "revoked", None),
            ],
            self.relation_events(relation_id),
        )

    def test_revision_change_after_read_fails_closed(self) -> None:
        first = self.propose_and_approve("basis-one")
        relation_id = first["relation_identity"]
        self.assertEqual(1, first["relation_revision"])

        second = self.propose_and_approve("basis-two")
        self.assertEqual(relation_id, second["relation_identity"])
        self.assertEqual(2, second["relation_revision"])

        failed = self.revoke(relation_id, 1, expect=2)

        self.assertIn("revision changed", failed.stderr.lower())
        row = self.relation_row(relation_id)
        self.assertEqual(2, row[5])
        self.assertEqual("active", row[6])
        self.assertEqual(
            [
                (1, "created_from_candidate", "basis-one"),
                (2, "provenance_added", "basis-two"),
            ],
            self.relation_events(relation_id),
        )

    def test_repeated_revoke_with_current_revision_is_idempotent(self) -> None:
        approved = self.propose_and_approve()
        relation_id = approved["relation_identity"]
        first = json.loads(self.revoke(relation_id, 1).stdout)
        self.assertEqual(2, first["revision"])

        second = json.loads(self.revoke(relation_id, 2).stdout)

        self.assertEqual("revoked", second["status"])
        self.assertEqual(2, second["revision"])
        self.assertFalse(second["changed"])
        self.assertEqual(2, len(self.relation_events(relation_id)))

        stale_repeat = self.revoke(relation_id, 1, expect=2)
        self.assertIn("revision changed", stale_repeat.stderr.lower())
        self.assertEqual(2, self.relation_row(relation_id)[5])

    def test_default_relation_traversal_excludes_revoked_relation(self) -> None:
        approved = self.propose_and_approve()
        relation_id = approved["relation_identity"]

        before = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "before revoke",
                "--relation-seed", self.identities["A.md"],
                "--relation-direction", "outgoing",
            ).stdout
        )
        self.assertEqual(
            [self.identities["B.md"]],
            [item["stable_identity"] for item in before["results"]],
        )

        self.revoke(relation_id, 1)

        after = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "after revoke",
                "--relation-seed", self.identities["A.md"],
                "--relation-direction", "outgoing",
            ).stdout
        )
        self.assertEqual([], after["results"])
        self.assertEqual([], after["results"])
        self.assertEqual("revoked", self.relation_row(relation_id)[6])


if __name__ == "__main__":
    unittest.main()
