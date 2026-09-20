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


class RetireLifecycleBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.note = self.knowledge / "Existing.md"
        self.note.write_text(
            "---\n"
            "topic: lifecycle\n"
            "custom: preserve-me\n"
            "---\n"
            "# Existing\n\n"
            "RetireLifecycleToken.\n",
            encoding="utf-8",
        )
        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/Existing.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )
        self.identity = registered["registered"][0]["identity"]

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

    def current_revision(self) -> int:
        with sqlite3.connect(self.database) as conn:
            return int(
                conn.execute(
                    "SELECT revision FROM objects WHERE identity = ?",
                    (self.identity,),
                ).fetchone()[0]
            )

    def lifecycle(self) -> str:
        with sqlite3.connect(self.database) as conn:
            return str(
                conn.execute(
                    "SELECT status FROM knowledge_asset_lifecycle WHERE identity = ?",
                    (self.identity,),
                ).fetchone()[0]
            )

    def propose_retire(self, *, base_revision: int | None = None) -> dict[str, object]:
        if base_revision is None:
            base_revision = self.current_revision()
        return json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", self.identity,
                "--base-revision", str(base_revision),
                "--reason", "Source evidence is obsolete.",
            ).stdout
        )

    def test_lifecycle_markdown_mirror_drift_fails_closed(self) -> None:
        proposal = self.propose_retire()
        self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
        )
        drifted = self.note.read_text(encoding="utf-8").replace(
            "akira_knowledge_lifecycle: retired",
            "akira_knowledge_lifecycle: current",
        )
        self.note.write_text(drifted, encoding="utf-8")

        failed = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--scope", "retired",
            "--identity", self.identity,
            expect=2,
        )

        self.assertIn(
            "lifecycle Property disagrees with structured Authority",
            failed.stderr,
        )
        self.assertEqual("retired", self.lifecycle())

    def test_v1_database_migrates_current_lifecycle_without_rewriting_markdown(self) -> None:
        before = self.note.read_bytes()
        with sqlite3.connect(self.database) as conn:
            conn.execute("DROP TABLE lifecycle_proposals")
            conn.execute("DROP TABLE knowledge_asset_lifecycle_events")
            conn.execute("DROP TABLE knowledge_asset_lifecycle")
            conn.execute(
                "UPDATE schema_meta SET value = '1' WHERE key = 'schema_version'"
            )
            conn.commit()

        exact = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--identity", self.identity,
            ).stdout
        )

        self.assertEqual(self.identity, exact["result"]["stable_identity"])
        self.assertEqual(before, self.note.read_bytes())
        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            lifecycle = conn.execute(
                "SELECT status FROM knowledge_asset_lifecycle WHERE identity = ?",
                (self.identity,),
            ).fetchone()[0]
        self.assertEqual("2", schema_version)
        self.assertEqual("current", lifecycle)

    def test_v2_missing_lifecycle_authority_fails_closed_instead_of_guessing_current(self) -> None:
        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            self.assertEqual("2", schema_version)
            conn.execute(
                "DELETE FROM knowledge_asset_lifecycle WHERE identity = ?",
                (self.identity,),
            )
            conn.commit()

        failed = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.identity,
            expect=2,
        )

        self.assertIn(
            "lifecycle is missing from structured Authority",
            failed.stderr,
        )
        with sqlite3.connect(self.database) as conn:
            row = conn.execute(
                "SELECT status FROM knowledge_asset_lifecycle WHERE identity = ?",
                (self.identity,),
            ).fetchone()
        self.assertIsNone(row)

    def test_retire_preserves_existing_material_provenance(self) -> None:
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Provenance evidence for a curated asset.",
            ).stdout
        )
        proposal = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(material["identity"]),
                "--body", "# Curated\n\nCurated asset with provenance.\n",
            ).stdout
        )
        created = json.loads(
            self.run_cli(
                "curate-approve",
                "--vault", str(self.vault),
                "--proposal-id", str(proposal["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        asset_identity = str(created["asset_identity"])

        with sqlite3.connect(self.database) as conn:
            before = conn.execute(
                "SELECT material_identity, proposal_id, material_basis_revision "
                "FROM knowledge_asset_materials WHERE asset_identity = ?",
                (asset_identity,),
            ).fetchall()
            base_revision = conn.execute(
                "SELECT revision FROM objects WHERE identity = ?",
                (asset_identity,),
            ).fetchone()[0]

        retired = json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", asset_identity,
                "--base-revision", str(base_revision),
                "--reason", "Curated asset is no longer current.",
            ).stdout
        )
        self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(retired["proposal_id"]),
            "--confirmed-approval",
        )

        with sqlite3.connect(self.database) as conn:
            after = conn.execute(
                "SELECT material_identity, proposal_id, material_basis_revision "
                "FROM knowledge_asset_materials WHERE asset_identity = ?",
                (asset_identity,),
            ).fetchall()
        self.assertTrue(before)
        self.assertEqual(before, after)

    def test_retire_proposal_fails_closed_when_target_authority_changes(self) -> None:
        proposal = self.propose_retire()
        edited = self.note.read_text(encoding="utf-8").replace(
            "RetireLifecycleToken.",
            "Newer user edit must win.",
        )
        self.note.write_text(edited, encoding="utf-8")

        failed = self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
            expect=2,
        )

        self.assertIn("retire proposal is stale", failed.stderr.lower())
        self.assertEqual(edited, self.note.read_text(encoding="utf-8"))
        self.assertEqual(2, self.current_revision())
        self.assertEqual("current", self.lifecycle())
        with sqlite3.connect(self.database) as conn:
            proposal_status = conn.execute(
                "SELECT status FROM lifecycle_proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual("pending", proposal_status)

    def test_views_show_current_and_retired_without_advancing_revisions(self) -> None:
        proposal = self.propose_retire()
        self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
        )
        before_revision = self.current_revision()

        payload = json.loads(
            self.run_cli(
                "views-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(
            ["Current Knowledge", "Retired Knowledge", "Materials"],
            payload["views"],
        )
        text = (
            self.vault / "Akira Knowledge Views" / "Akira Knowledge.base"
        ).read_text(encoding="utf-8")
        self.assertIn("Retired Knowledge", text)
        self.assertIn('note.akira_knowledge_lifecycle == "retired"', text)
        self.assertIn(
            '!file.hasProperty("akira_knowledge_lifecycle") || '
            'note.akira_knowledge_lifecycle != "retired"',
            text,
        )
        self.assertEqual(before_revision, self.current_revision())

    def test_retire_requires_explicit_approval_and_moves_asset_out_of_current_scope(self) -> None:
        original = self.note.read_text(encoding="utf-8")
        self.assertEqual("current", self.lifecycle())
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Material must keep its own workflow status.",
            ).stdout
        )
        proposal = self.propose_retire()

        self.assertEqual("retire", proposal["proposal_kind"])
        self.assertEqual("pending", proposal["status"])
        self.assertEqual(self.identity, proposal["target_identity"])
        self.assertEqual(1, proposal["base_revision"])
        self.assertEqual("current", proposal["current_lifecycle"])
        self.assertEqual("retired", proposal["proposed_lifecycle"])
        self.assertEqual("Source evidence is obsolete.", proposal["reason"])
        self.assertEqual(original, self.note.read_text(encoding="utf-8"))
        self.assertEqual(1, self.current_revision())
        self.assertEqual("current", self.lifecycle())

        denied = self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            expect=2,
        )
        self.assertIn("explicit user approval", denied.stderr)
        self.assertEqual(original, self.note.read_text(encoding="utf-8"))
        self.assertEqual(1, self.current_revision())
        self.assertEqual("current", self.lifecycle())

        applied = json.loads(
            self.run_cli(
                "maintain-apply-retire",
                "--vault", str(self.vault),
                "--proposal-id", str(proposal["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(self.identity, applied["stable_identity"])
        self.assertEqual("retired", applied["lifecycle"])
        self.assertEqual(2, applied["revision"])

        retired_text = self.note.read_text(encoding="utf-8")
        self.assertIn("akira_knowledge_lifecycle: retired\n", retired_text)
        self.assertIn("custom: preserve-me\n", retired_text)
        self.assertTrue(retired_text.endswith("# Existing\n\nRetireLifecycleToken.\n"))
        self.assertEqual("retired", self.lifecycle())

        current_exact = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.identity,
            expect=2,
        )
        self.assertIn("outside requested retrieval scope", current_exact.stderr)

        retired_exact = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--scope", "retired",
                "--identity", self.identity,
            ).stdout
        )
        self.assertEqual(["retired"], retired_exact["scope"])
        self.assertEqual(self.identity, retired_exact["result"]["stable_identity"])

        lifecycle_property = self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--scope", "retired",
            "--property", "akira_knowledge_lifecycle=retired",
            expect=2,
        )
        self.assertIn(
            "Use dedicated identity/kind/status filters for Akira Knowledge-owned properties",
            lifecycle_property.stderr,
        )

        retired_filter = json.loads(
            self.run_cli(
                "retrieve-filter",
                "--vault", str(self.vault),
                "--scope", "retired",
                "--kind", "knowledge_asset",
            ).stdout
        )
        self.assertEqual(
            [self.identity],
            [item["stable_identity"] for item in retired_filter["results"]],
        )

        retired_task = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "Read retired lifecycle knowledge",
                "--scope", "retired",
                "--exact", self.identity,
            ).stdout
        )
        self.assertEqual(self.identity, retired_task["results"][0]["stable_identity"])

        with sqlite3.connect(self.database) as conn:
            material_status, material_revision = conn.execute(
                "SELECT m.status, o.revision "
                "FROM material_records m JOIN objects o ON o.identity = m.identity "
                "WHERE m.identity = ?",
                (material["identity"],),
            ).fetchone()
            revision_events = [
                row[0]
                for row in conn.execute(
                    "SELECT event FROM revisions WHERE identity = ? ORDER BY revision",
                    (self.identity,),
                )
            ]
            lifecycle_events = conn.execute(
                "SELECT revision, status, event, reason "
                "FROM knowledge_asset_lifecycle_events WHERE identity = ? ORDER BY revision",
                (self.identity,),
            ).fetchall()

        self.assertEqual("待处理", material_status)
        self.assertEqual(1, material_revision)
        self.assertEqual(["registered", "retired"], revision_events)
        self.assertEqual(
            [(2, "retired", "retired", "Source evidence is obsolete.")],
            lifecycle_events,
        )

if __name__ == "__main__":
    unittest.main()
