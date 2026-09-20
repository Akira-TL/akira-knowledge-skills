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


class SupersedeLifecycleBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.old_note = self.knowledge / "Old.md"
        self.new_note = self.knowledge / "New.md"
        self.old_note.write_text(
            "---\n"
            "topic: lifecycle\n"
            "custom: preserve-old\n"
            "---\n"
            "# Old\n\n"
            "OldKnowledgeToken.\n",
            encoding="utf-8",
        )
        self.new_note.write_text(
            "---\n"
            "topic: lifecycle\n"
            "custom: preserve-new\n"
            "---\n"
            "# New\n\n"
            "NewKnowledgeToken.\n",
            encoding="utf-8",
        )
        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/Old.md",
                "--note", "Knowledge/New.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )
        identities = {
            item["locator"]: item["identity"]
            for item in registered["registered"]
        }
        self.old_identity = identities["Knowledge/Old.md"]
        self.new_identity = identities["Knowledge/New.md"]

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

    def object_revision(self, identity: str) -> int:
        with sqlite3.connect(self.database) as conn:
            return int(
                conn.execute(
                    "SELECT revision FROM objects WHERE identity = ?",
                    (identity,),
                ).fetchone()[0]
            )

    def lifecycle(self, identity: str) -> tuple[str, str | None]:
        with sqlite3.connect(self.database) as conn:
            row = conn.execute(
                "SELECT status, superseded_by "
                "FROM knowledge_asset_lifecycle WHERE identity = ?",
                (identity,),
            ).fetchone()
        return str(row[0]), None if row[1] is None else str(row[1])

    def propose_supersede(self) -> dict[str, object]:
        return json.loads(
            self.run_cli(
                "maintain-propose-supersede",
                "--vault", str(self.vault),
                "--identity", self.old_identity,
                "--base-revision", str(self.object_revision(self.old_identity)),
                "--replacement-id", self.new_identity,
                "--replacement-revision", str(self.object_revision(self.new_identity)),
                "--reason", "The new asset replaces the old interpretation.",
            ).stdout
        )

    def test_v2_lifecycle_schema_migrates_to_current_schema_without_losing_retired_state(self) -> None:
        retire = json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", self.old_identity,
                "--base-revision", "1",
                "--reason", "Retired before v3 migration.",
            ).stdout
        )
        self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(retire["proposal_id"]),
            "--confirmed-approval",
        )
        old_markdown = self.old_note.read_bytes()
        new_markdown = self.new_note.read_bytes()

        with sqlite3.connect(self.database) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            lifecycle_rows = conn.execute(
                "SELECT identity, status, updated_at FROM knowledge_asset_lifecycle "
                "ORDER BY identity"
            ).fetchall()
            event_rows = conn.execute(
                "SELECT identity, revision, status, event, reason, recorded_at "
                "FROM knowledge_asset_lifecycle_events ORDER BY identity, revision"
            ).fetchall()
            proposal_rows = conn.execute(
                "SELECT proposal_id, proposal_kind, status, target_identity, "
                "base_revision, reason, created_at, decided_at "
                "FROM lifecycle_proposals ORDER BY proposal_id"
            ).fetchall()

            conn.execute("DROP TABLE relation_maintenance_candidates")
            conn.execute("DROP TABLE conflict_candidate_members")
            conn.execute("DROP TABLE conflict_candidates")
            conn.execute("DROP TABLE maintenance_candidates")
            conn.execute("DROP TABLE review_findings")
            conn.execute("DROP TABLE lifecycle_proposals")
            conn.execute("DROP TABLE knowledge_asset_lifecycle_events")
            conn.execute("DROP TABLE knowledge_asset_lifecycle")
            conn.executescript(
                """
                CREATE TABLE knowledge_asset_lifecycle (
                    identity TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('current', 'retired')),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE knowledge_asset_lifecycle_events (
                    identity TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('current', 'retired')),
                    event TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY (identity, revision)
                );
                CREATE TABLE lifecycle_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    proposal_kind TEXT NOT NULL CHECK (proposal_kind = 'retire'),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'rejected', 'applied')),
                    target_identity TEXT NOT NULL,
                    base_revision INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX lifecycle_proposals_status_idx
                    ON lifecycle_proposals(status);
                """
            )
            conn.executemany(
                "INSERT INTO knowledge_asset_lifecycle(identity, status, updated_at) "
                "VALUES (?, ?, ?)",
                lifecycle_rows,
            )
            conn.executemany(
                "INSERT INTO knowledge_asset_lifecycle_events("
                "identity, revision, status, event, reason, recorded_at"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                event_rows,
            )
            conn.executemany(
                "INSERT INTO lifecycle_proposals("
                "proposal_id, proposal_kind, status, target_identity, base_revision, "
                "reason, created_at, decided_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                proposal_rows,
            )
            conn.execute(
                "UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'"
            )
            conn.commit()

        migrated = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--scope", "retired",
                "--identity", self.old_identity,
            ).stdout
        )
        self.assertEqual(self.old_identity, migrated["result"]["stable_identity"])
        self.assertEqual(old_markdown, self.old_note.read_bytes())
        self.assertEqual(new_markdown, self.new_note.read_bytes())

        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            lifecycle = conn.execute(
                "SELECT status, superseded_by FROM knowledge_asset_lifecycle "
                "WHERE identity = ?",
                (self.old_identity,),
            ).fetchone()
            events = conn.execute(
                "SELECT revision, status, event, reason, superseded_by "
                "FROM knowledge_asset_lifecycle_events WHERE identity = ? "
                "ORDER BY revision",
                (self.old_identity,),
            ).fetchall()
            proposal_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(lifecycle_proposals)").fetchall()
            }

        self.assertEqual("5", schema_version)
        self.assertEqual(("retired", None), lifecycle)
        self.assertEqual(
            [(2, "retired", "retired", "Retired before v3 migration.", None)],
            events,
        )
        self.assertIn("replacement_identity", proposal_columns)
        self.assertIn("replacement_revision", proposal_columns)

    def test_supersede_preserves_existing_material_provenance(self) -> None:
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Provenance evidence for supersede.",
            ).stdout
        )
        curate = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(material["identity"]),
                "--body", "# Curated Old\n\nCuratedSupersedeToken.\n",
            ).stdout
        )
        created = json.loads(
            self.run_cli(
                "curate-approve",
                "--vault", str(self.vault),
                "--proposal-id", str(curate["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        curated_identity = str(created["asset_identity"])

        with sqlite3.connect(self.database) as conn:
            before = conn.execute(
                "SELECT material_identity, proposal_id, material_basis_revision "
                "FROM knowledge_asset_materials WHERE asset_identity = ?",
                (curated_identity,),
            ).fetchall()
            curated_revision = conn.execute(
                "SELECT revision FROM objects WHERE identity = ?",
                (curated_identity,),
            ).fetchone()[0]
            replacement_revision = conn.execute(
                "SELECT revision FROM objects WHERE identity = ?",
                (self.new_identity,),
            ).fetchone()[0]

        proposal = json.loads(
            self.run_cli(
                "maintain-propose-supersede",
                "--vault", str(self.vault),
                "--identity", curated_identity,
                "--base-revision", str(curated_revision),
                "--replacement-id", self.new_identity,
                "--replacement-revision", str(replacement_revision),
                "--reason", "Curated knowledge was replaced.",
            ).stdout
        )
        self.run_cli(
            "maintain-apply-supersede",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
        )

        with sqlite3.connect(self.database) as conn:
            after = conn.execute(
                "SELECT material_identity, proposal_id, material_basis_revision "
                "FROM knowledge_asset_materials WHERE asset_identity = ?",
                (curated_identity,),
            ).fetchall()
        self.assertTrue(before)
        self.assertEqual(before, after)

    def test_supersede_replacement_must_be_a_current_registered_knowledge_asset(self) -> None:
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Material is not a replacement Knowledge Asset.",
            ).stdout
        )
        wrong_kind = self.run_cli(
            "maintain-propose-supersede",
            "--vault", str(self.vault),
            "--identity", self.old_identity,
            "--base-revision", "1",
            "--replacement-id", str(material["identity"]),
            "--replacement-revision", "1",
            "--reason", "Invalid replacement kind.",
            expect=2,
        )
        self.assertIn("Replacement Knowledge asset does not exist", wrong_kind.stderr)

        retire = json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", self.new_identity,
                "--base-revision", "1",
                "--reason", "Replacement is no longer current.",
            ).stdout
        )
        self.run_cli(
            "maintain-apply-retire",
            "--vault", str(self.vault),
            "--proposal-id", str(retire["proposal_id"]),
            "--confirmed-approval",
        )
        noncurrent = self.run_cli(
            "maintain-propose-supersede",
            "--vault", str(self.vault),
            "--identity", self.old_identity,
            "--base-revision", "1",
            "--replacement-id", self.new_identity,
            "--replacement-revision", "2",
            "--reason", "Retired replacement must be rejected.",
            expect=2,
        )
        self.assertIn("Replacement Knowledge asset is not current", noncurrent.stderr)

    def test_superseded_asset_cannot_be_silently_retired_or_superseded_again(self) -> None:
        proposal = self.propose_supersede()
        applied = json.loads(
            self.run_cli(
                "maintain-apply-supersede",
                "--vault", str(self.vault),
                "--proposal-id", str(proposal["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(2, applied["revision"])

        retire = self.run_cli(
            "maintain-propose-retire",
            "--vault", str(self.vault),
            "--identity", self.old_identity,
            "--base-revision", "2",
            "--reason", "Do not silently convert superseded to retired.",
            expect=2,
        )
        self.assertIn("Knowledge asset is not current", retire.stderr)

        supersede_again = self.run_cli(
            "maintain-propose-supersede",
            "--vault", str(self.vault),
            "--identity", self.old_identity,
            "--base-revision", "2",
            "--replacement-id", self.new_identity,
            "--replacement-revision", "1",
            "--reason", "Do not silently supersede twice.",
            expect=2,
        )
        self.assertIn("Knowledge asset is not current", supersede_again.stderr)
        self.assertEqual(("superseded", self.new_identity), self.lifecycle(self.old_identity))

    def test_supersede_fails_closed_when_old_authority_changes_after_proposal(self) -> None:
        proposal = self.propose_supersede()
        edited = self.old_note.read_text(encoding="utf-8").replace(
            "OldKnowledgeToken.",
            "Newer old-asset edit must win.",
        )
        self.old_note.write_text(edited, encoding="utf-8")

        failed = self.run_cli(
            "maintain-apply-supersede",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
            expect=2,
        )

        self.assertIn("supersede proposal is stale", failed.stderr.lower())
        self.assertEqual(edited, self.old_note.read_text(encoding="utf-8"))
        self.assertEqual(("current", None), self.lifecycle(self.old_identity))
        self.assertEqual(("current", None), self.lifecycle(self.new_identity))
        with sqlite3.connect(self.database) as conn:
            proposal_status = conn.execute(
                "SELECT status FROM lifecycle_proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual("pending", proposal_status)

    def test_supersede_fails_closed_when_replacement_authority_changes_after_proposal(self) -> None:
        proposal = self.propose_supersede()
        edited = self.new_note.read_text(encoding="utf-8").replace(
            "NewKnowledgeToken.",
            "Newer replacement edit must win.",
        )
        self.new_note.write_text(edited, encoding="utf-8")

        failed = self.run_cli(
            "maintain-apply-supersede",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
            expect=2,
        )

        self.assertIn("supersede proposal is stale", failed.stderr.lower())
        self.assertEqual(edited, self.new_note.read_text(encoding="utf-8"))
        self.assertEqual(("current", None), self.lifecycle(self.old_identity))
        self.assertEqual(("current", None), self.lifecycle(self.new_identity))
        with sqlite3.connect(self.database) as conn:
            proposal_status = conn.execute(
                "SELECT status FROM lifecycle_proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual("pending", proposal_status)

    def test_views_separate_current_retired_and_superseded_without_revision_changes(self) -> None:
        proposal = self.propose_supersede()
        self.run_cli(
            "maintain-apply-supersede",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
        )
        old_revision = self.object_revision(self.old_identity)
        new_revision = self.object_revision(self.new_identity)

        payload = json.loads(
            self.run_cli(
                "views-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )

        self.assertEqual(
            [
                "Current Knowledge",
                "Retired Knowledge",
                "Superseded Knowledge",
                "Materials",
            ],
            payload["views"],
        )
        text = (
            self.vault / "Akira Knowledge Views" / "Akira Knowledge.base"
        ).read_text(encoding="utf-8")
        self.assertIn("Superseded Knowledge", text)
        self.assertIn(
            'note.akira_knowledge_lifecycle == "superseded"',
            text,
        )
        self.assertIn(
            'note.akira_knowledge_lifecycle != "retired" && '
            'note.akira_knowledge_lifecycle != "superseded"',
            text,
        )
        self.assertEqual(old_revision, self.object_revision(self.old_identity))
        self.assertEqual(new_revision, self.object_revision(self.new_identity))

    def test_supersede_requires_explicit_approval_and_preserves_both_identities(self) -> None:
        old_original = self.old_note.read_text(encoding="utf-8")
        new_original = self.new_note.read_text(encoding="utf-8")

        proposal = self.propose_supersede()

        self.assertEqual("supersede", proposal["proposal_kind"])
        self.assertEqual("pending", proposal["status"])
        self.assertEqual(self.old_identity, proposal["target_identity"])
        self.assertEqual(self.new_identity, proposal["replacement_identity"])
        self.assertEqual(1, proposal["base_revision"])
        self.assertEqual(1, proposal["replacement_revision"])
        self.assertEqual("current", proposal["current_lifecycle"])
        self.assertEqual("superseded", proposal["proposed_lifecycle"])
        self.assertEqual(old_original, self.old_note.read_text(encoding="utf-8"))
        self.assertEqual(new_original, self.new_note.read_text(encoding="utf-8"))
        self.assertEqual(1, self.object_revision(self.old_identity))
        self.assertEqual(1, self.object_revision(self.new_identity))
        self.assertEqual(("current", None), self.lifecycle(self.old_identity))
        self.assertEqual(("current", None), self.lifecycle(self.new_identity))

        denied = self.run_cli(
            "maintain-apply-supersede",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            expect=2,
        )
        self.assertIn("explicit user approval", denied.stderr)

        applied = json.loads(
            self.run_cli(
                "maintain-apply-supersede",
                "--vault", str(self.vault),
                "--proposal-id", str(proposal["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(self.old_identity, applied["stable_identity"])
        self.assertEqual(self.new_identity, applied["replacement_identity"])
        self.assertEqual("superseded", applied["lifecycle"])
        self.assertEqual(2, applied["revision"])
        self.assertEqual(1, applied["replacement_revision"])

        self.assertEqual(2, self.object_revision(self.old_identity))
        self.assertEqual(1, self.object_revision(self.new_identity))
        self.assertEqual(("superseded", self.new_identity), self.lifecycle(self.old_identity))
        self.assertEqual(("current", None), self.lifecycle(self.new_identity))

        old_text = self.old_note.read_text(encoding="utf-8")
        self.assertIn("akira_knowledge_lifecycle: superseded\n", old_text)
        self.assertIn("custom: preserve-old\n", old_text)
        self.assertTrue(old_text.endswith("# Old\n\nOldKnowledgeToken.\n"))
        self.assertEqual(new_original, self.new_note.read_text(encoding="utf-8"))

        current_old = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.old_identity,
            expect=2,
        )
        self.assertIn("outside requested retrieval scope", current_old.stderr)

        superseded_old = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--scope", "superseded",
                "--identity", self.old_identity,
            ).stdout
        )
        self.assertEqual(["superseded"], superseded_old["scope"])
        self.assertEqual(
            self.old_identity,
            superseded_old["result"]["stable_identity"],
        )
        superseded_filter = json.loads(
            self.run_cli(
                "retrieve-filter",
                "--vault", str(self.vault),
                "--scope", "superseded",
                "--kind", "knowledge_asset",
            ).stdout
        )
        self.assertEqual(
            [self.old_identity],
            [item["stable_identity"] for item in superseded_filter["results"]],
        )
        superseded_task = json.loads(
            self.run_cli(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "Read superseded knowledge",
                "--scope", "superseded",
                "--exact", self.old_identity,
            ).stdout
        )
        self.assertEqual(
            self.old_identity,
            superseded_task["results"][0]["stable_identity"],
        )

        current_new = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--identity", self.new_identity,
            ).stdout
        )
        self.assertEqual(self.new_identity, current_new["result"]["stable_identity"])

        with sqlite3.connect(self.database) as conn:
            event = conn.execute(
                "SELECT revision, status, event, reason, superseded_by "
                "FROM knowledge_asset_lifecycle_events "
                "WHERE identity = ? ORDER BY revision",
                (self.old_identity,),
            ).fetchall()
            proposal_row = conn.execute(
                "SELECT status, replacement_identity, replacement_revision "
                "FROM lifecycle_proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()
        self.assertEqual(
            [
                (
                    2,
                    "superseded",
                    "superseded",
                    "The new asset replaces the old interpretation.",
                    self.new_identity,
                )
            ],
            event,
        )
        self.assertEqual(
            ("applied", self.new_identity, 1),
            proposal_row,
        )


if __name__ == "__main__":
    unittest.main()
