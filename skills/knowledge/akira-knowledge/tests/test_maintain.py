from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[1]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class MaintainBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.target = self.knowledge / "Existing.md"
        self.target.write_text(
            "---\n"
            "topic: stable-user-property\n"
            "---\n"
            "# Existing\n\n"
            "Original body.\n",
            encoding="utf-8",
        )
        registered = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Existing.md",
            "--default-write-root", "Knowledge",
        )
        self.identity = json.loads(registered.stdout)["registered"][0]["identity"]

    def tearDown(self) -> None:
        self.tempdir.cleanup()

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

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    def capture(self, note: str) -> dict[str, object]:
        result = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--confirmed-intent",
            "--note", note,
        )
        return json.loads(result.stdout)

    def propose_update(
        self,
        material_id: str,
        body: str,
        *,
        base_revision: int | None = None,
    ) -> dict[str, object]:
        if base_revision is None:
            synced = self.run_cli(
                "maintain-sync",
                "--vault", str(self.vault),
                "--identity", self.identity,
            )
            base_revision = json.loads(synced.stdout)["revision"]
        result = self.run_cli(
            "curate-propose",
            "--vault", str(self.vault),
            "--material-id", material_id,
            "--target-id", self.identity,
            "--base-revision", str(base_revision),
            "--body", body,
        )
        return json.loads(result.stdout)

    def apply_update(
        self,
        proposal_id: str,
        *,
        confirmed: bool = True,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "maintain-apply-update",
            "--vault", str(self.vault),
            "--proposal-id", proposal_id,
        ]
        if confirmed:
            args.append("--confirmed-approval")
        return self.run_cli(*args, expect=expect)

    def object_state(self) -> tuple[str, int, str]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT locator, revision, authority_fingerprint FROM objects WHERE identity = ?",
                (self.identity,),
            ).fetchone()

    def revision_events(self) -> list[str]:
        with sqlite3.connect(self.database) as conn:
            rows = conn.execute(
                "SELECT event FROM revisions WHERE identity = ? ORDER BY revision",
                (self.identity,),
            ).fetchall()
        return [row[0] for row in rows]

    def test_material_resolution_is_explicit_revision_safe_and_stable_after_sync(self) -> None:
        material = self.capture("reference material that does not warrant a Knowledge Asset")
        material_path = self.vault / material["locator"]

        denied = self.run_cli(
            "maintain-resolve-material",
            "--vault", str(self.vault),
            "--identity", material["identity"],
            "--expected-revision", "1",
            "--reason", "Useful source, but no durable knowledge needs to be extracted.",
            expect=2,
        )
        self.assertIn("explicit user confirmation", denied.stderr)
        self.assertIn("akira_knowledge_status: 待处理\n", material_path.read_text(encoding="utf-8"))

        resolved = json.loads(
            self.run_cli(
                "maintain-resolve-material",
                "--vault", str(self.vault),
                "--identity", material["identity"],
                "--expected-revision", "1",
                "--reason", "Useful source, but no durable knowledge needs to be extracted.",
                "--confirmed-resolution",
            ).stdout
        )
        self.assertEqual("已处理", resolved["status"])
        self.assertEqual(2, resolved["revision"])
        self.assertEqual("material_resolved", resolved["event"])
        self.assertIn("akira_knowledge_status: 已处理\n", material_path.read_text(encoding="utf-8"))

        synced = json.loads(
            self.run_cli(
                "maintain-sync",
                "--vault", str(self.vault),
                "--identity", material["identity"],
            ).stdout
        )
        self.assertFalse(synced["changed"])
        self.assertEqual(2, synced["revision"])

        with sqlite3.connect(self.database) as conn:
            material_state = conn.execute(
                "SELECT status FROM material_records WHERE identity = ?",
                (material["identity"],),
            ).fetchone()[0]
            revision_event = conn.execute(
                "SELECT event FROM revisions WHERE identity = ? AND revision = 2",
                (material["identity"],),
            ).fetchone()[0]
            resolution = conn.execute(
                "SELECT reason FROM material_resolution_events "
                "WHERE identity = ? AND revision = 2",
                (material["identity"],),
            ).fetchone()[0]
        self.assertEqual("已处理", material_state)
        self.assertEqual("material_resolved", revision_event)
        self.assertEqual(
            "Useful source, but no durable knowledge needs to be extracted.",
            resolution,
        )

    def test_current_schema_missing_material_resolution_authority_fails_closed(self) -> None:
        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            self.assertEqual("8", schema_version)
            conn.execute("DROP TABLE material_resolution_events")
            conn.commit()

        failed = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.identity,
            expect=2,
        )
        self.assertIn("Material resolution governance table is missing", failed.stderr)
        with sqlite3.connect(self.database) as conn:
            recreated = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'material_resolution_events'"
            ).fetchone()
        self.assertIsNone(recreated)

    def test_material_resolution_rejects_stale_revision(self) -> None:
        material = self.capture("material whose current revision changes before resolution")
        material_path = self.vault / material["locator"]
        material_path.write_text(
            material_path.read_text(encoding="utf-8") + "\nUser annotation.\n",
            encoding="utf-8",
        )
        synced = json.loads(
            self.run_cli(
                "maintain-sync",
                "--vault", str(self.vault),
                "--identity", material["identity"],
            ).stdout
        )
        self.assertEqual(2, synced["revision"])

        stale = self.run_cli(
            "maintain-resolve-material",
            "--vault", str(self.vault),
            "--identity", material["identity"],
            "--expected-revision", "1",
            "--reason", "No extraction required.",
            "--confirmed-resolution",
            expect=2,
        )
        self.assertIn("revision changed", stale.stderr)
        self.assertIn("akira_knowledge_status: 待处理\n", material_path.read_text(encoding="utf-8"))

    def test_move_sync_updates_locator_and_revision_without_changing_identity(self) -> None:
        moved_dir = self.knowledge / "Moved"
        moved_dir.mkdir()
        moved = moved_dir / "Renamed.md"
        original = self.target.read_text(encoding="utf-8")
        self.target.rename(moved)

        result = self.run_cli(
            "maintain-sync",
            "--vault", str(self.vault),
            "--identity", self.identity,
        )
        payload = json.loads(result.stdout)

        self.assertTrue(payload["changed"])
        self.assertEqual("external_move", payload["event"])
        self.assertEqual(self.identity, payload["stable_identity"])
        self.assertEqual("Knowledge/Moved/Renamed.md", payload["canonical_locator"])
        self.assertEqual(2, payload["revision"])
        self.assertEqual(original, moved.read_text(encoding="utf-8"))
        self.assertEqual("Knowledge/Moved/Renamed.md", self.object_state()[0])
        self.assertEqual(["registered", "external_move"], self.revision_events())

    def test_update_proposal_requires_the_revision_that_was_actually_read(self) -> None:
        material = self.capture("evidence without an explicit base")
        result = self.run_cli(
            "curate-propose",
            "--vault", str(self.vault),
            "--material-id", material["identity"],
            "--target-id", self.identity,
            "--body", "Candidate without a bound base revision.\n",
            expect=2,
        )
        self.assertIn("requires the base revision", result.stderr)
        with sqlite3.connect(self.database) as conn:
            count = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
        self.assertEqual(0, count)
        self.assertEqual(1, self.object_state()[1])

    def test_update_proposal_creation_rejects_a_revision_that_changed_after_read(self) -> None:
        material = self.capture("new evidence")
        original = self.target.read_text(encoding="utf-8")
        edited = original.replace("Original body.", "User edited body directly in Obsidian.")
        self.target.write_text(edited, encoding="utf-8")

        stale = self.run_cli(
            "curate-propose",
            "--vault", str(self.vault),
            "--material-id", material["identity"],
            "--target-id", self.identity,
            "--base-revision", "1",
            "--body", "Proposal generated from revision 1.\n",
            expect=2,
        )
        self.assertIn("Target revision changed during proposal preparation", stale.stderr)
        self.assertEqual(edited, self.target.read_text(encoding="utf-8"))
        self.assertEqual(2, self.object_state()[1])
        self.assertEqual(["registered", "external_edit"], self.revision_events())

        proposal = self.propose_update(material["identity"], "# Existing\n\nProposal from revision 2.\n")
        self.assertEqual(2, proposal["base_revision"])

    def test_unapproved_update_is_unchanged_then_approved_update_advances_revision(self) -> None:
        material = self.capture("evidence for approved update")
        proposal = self.propose_update(material["identity"], "# Updated\n\nApproved body.\n")
        before = self.target.read_text(encoding="utf-8")

        denied = self.apply_update(proposal["proposal_id"], confirmed=False, expect=2)
        self.assertIn("explicit user approval", denied.stderr)
        self.assertEqual(before, self.target.read_text(encoding="utf-8"))
        self.assertEqual(1, self.object_state()[1])

        applied = json.loads(self.apply_update(proposal["proposal_id"]).stdout)
        updated = self.target.read_text(encoding="utf-8")
        self.assertEqual(self.identity, applied["stable_identity"])
        self.assertEqual(2, applied["revision"])
        self.assertEqual("Knowledge/Existing.md", applied["canonical_locator"])
        self.assertIn("topic: stable-user-property\n", updated)
        self.assertIn(f"akira_knowledge_id: {self.identity}\n", updated)
        self.assertTrue(updated.endswith("# Updated\n\nApproved body.\n"))
        self.assertEqual(
            ["registered", "updated_from_proposal"],
            self.revision_events(),
        )

        material_path = self.vault / material["locator"]
        self.assertIn("akira_knowledge_status: 已处理\n", material_path.read_text(encoding="utf-8"))
        with sqlite3.connect(self.database) as conn:
            proposal_status = conn.execute(
                "SELECT status, result_identity FROM proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()
        self.assertEqual(("applied", self.identity), proposal_status)

    def test_direct_edit_after_proposal_makes_update_stale_and_preserves_newer_authority(self) -> None:
        material = self.capture("evidence for stale proposal")
        proposal = self.propose_update(material["identity"], "# Existing\n\nStale proposed body.\n")
        self.assertEqual(1, proposal["base_revision"])

        current = self.target.read_text(encoding="utf-8")
        user_edit = current.replace("Original body.", "Newer user edit must win.")
        self.target.write_text(user_edit, encoding="utf-8")

        failed = self.apply_update(proposal["proposal_id"], expect=2)
        self.assertIn("proposal is stale", failed.stderr.lower())
        self.assertEqual(user_edit, self.target.read_text(encoding="utf-8"))
        self.assertEqual(2, self.object_state()[1])
        self.assertEqual(["registered", "external_edit"], self.revision_events())

        with sqlite3.connect(self.database) as conn:
            status = conn.execute(
                "SELECT status FROM proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual("pending", status)

    def test_move_after_proposal_is_disjoint_and_update_applies_at_new_locator(self) -> None:
        material = self.capture("evidence for move-safe update")
        proposal = self.propose_update(material["identity"], "# Existing\n\nUpdated after move.\n")
        moved = self.knowledge / "MovedAfterProposal.md"
        self.target.rename(moved)

        applied = json.loads(self.apply_update(proposal["proposal_id"]).stdout)

        self.assertEqual(self.identity, applied["stable_identity"])
        self.assertEqual("Knowledge/MovedAfterProposal.md", applied["canonical_locator"])
        self.assertEqual(3, applied["revision"])
        moved_text = moved.read_text(encoding="utf-8")
        self.assertIn("topic: stable-user-property\n", moved_text)
        self.assertTrue(moved_text.endswith("# Existing\n\nUpdated after move.\n"))
        self.assertEqual(
            ["registered", "external_move", "updated_from_proposal"],
            self.revision_events(),
        )
        locator, revision, _fingerprint = self.object_state()
        self.assertEqual("Knowledge/MovedAfterProposal.md", locator)
        self.assertEqual(3, revision)


if __name__ == "__main__":
    unittest.main()
