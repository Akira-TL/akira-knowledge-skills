from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

TEST_FILE = Path(__file__).resolve()
SKILL_ROOT = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[5]
CURRENT_CLI = SKILL_ROOT / "scripts" / "knowledge.py"
OLD_HEAD = "32682cc8526b01cf1d0b35dd366993259ca2a2c9"


class Upgrade03To04BlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.old_source = self.root / "old-source"
        self.old_source.mkdir()
        self._extract_old_source()
        self.old_cli = (
            self.old_source
            / "skills"
            / "knowledge"
            / "akira-knowledge"
            / "scripts"
            / "knowledge.py"
        )
        self.vault = self.root / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.a_path = self.knowledge / "A.md"
        self.b_path = self.knowledge / "B.md"
        self.a_path.write_text(
            "---\ncustom: preserve-a\n---\n"
            "# A\n\nLegacy 0.3 A. [[B]]\n<!-- preserve-a -->\n",
            encoding="utf-8",
        )
        self.b_path.write_text(
            "---\ncustom: preserve-b\n---\n"
            "# B\n\nLegacy 0.3 B.\n<!-- preserve-b -->\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    def _extract_old_source(self) -> None:
        archived = subprocess.run(
            [
                "git",
                "archive",
                OLD_HEAD,
                "skills/knowledge/akira-knowledge",
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            0,
            archived.returncode,
            msg=archived.stderr.decode("utf-8", errors="replace"),
        )
        with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
            archive.extractall(self.old_source, filter="data")

    def run_cli(
        self,
        cli: Path,
        *args: str,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(cli), *args],
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

    def markdown_snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
            if ".akira-knowledge" not in path.parts
            and "AK Graph" not in path.parts
            and "AK Views" not in path.parts
        }

    def snapshot_core(self) -> dict[str, list[tuple[object, ...]]]:
        with sqlite3.connect(self.database) as conn:
            return {
                "objects": conn.execute(
                    "SELECT identity, kind, locator, revision, authority_fingerprint "
                    "FROM objects ORDER BY identity"
                ).fetchall(),
                "revisions": conn.execute(
                    "SELECT identity, revision, event, locator, authority_fingerprint "
                    "FROM revisions ORDER BY identity, revision"
                ).fetchall(),
                "proposals": conn.execute(
                    "SELECT proposal_id, proposal_kind, status, target_identity, "
                    "base_revision, proposed_body, result_identity "
                    "FROM proposals ORDER BY proposal_id"
                ).fetchall(),
                "relation_records": conn.execute(
                    "SELECT identity, source_ref, relation_type, target_ref, "
                    "provenance, revision, status "
                    "FROM relation_records ORDER BY identity"
                ).fetchall(),
                "relation_candidates": conn.execute(
                    "SELECT candidate_id, status, source_kind, source_ref, "
                    "source_revision, source_fingerprint, relation_type, "
                    "target_kind, target_ref, target_revision, target_fingerprint, "
                    "provenance, result_relation_identity "
                    "FROM relation_candidates ORDER BY candidate_id"
                ).fetchall(),
            }

    def test_real_03_vault_upgrades_in_place_to_04_without_identity_or_authority_rewrite(self) -> None:
        registered = json.loads(
            self.run_cli(
                self.old_cli,
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/A.md",
                "--note", "Knowledge/B.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )["registered"]
        ids = {
            Path(item["locator"]).name: str(item["identity"])
            for item in registered
        }
        a = ids["A.md"]
        b = ids["B.md"]

        material = json.loads(
            self.run_cli(
                self.old_cli,
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Legacy 0.3 material.",
                "--source", "https://example.org/legacy-03",
            ).stdout
        )
        pending_proposal = json.loads(
            self.run_cli(
                self.old_cli,
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(material["identity"]),
                "--body", "# Pending 0.3\n\nMust survive 0.4 upgrade.\n",
            ).stdout
        )
        self.assertEqual("pending", pending_proposal["status"])

        accepted_candidate = json.loads(
            self.run_cli(
                self.old_cli,
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", a,
                "--type", "supports",
                "--target-id", b,
                "--provenance", "accepted-0.3-relation",
            ).stdout
        )
        relation = json.loads(
            self.run_cli(
                self.old_cli,
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", str(accepted_candidate["candidate_id"]),
                "--confirmed-approval",
            ).stdout
        )
        relation_id = str(relation["relation_identity"])

        pending_candidate = json.loads(
            self.run_cli(
                self.old_cli,
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", b,
                "--type", "contrasts-with",
                "--target-id", a,
                "--provenance", "pending-0.3-candidate",
            ).stdout
        )
        self.assertEqual("pending", pending_candidate["status"])

        before_core = self.snapshot_core()
        before_markdown = self.markdown_snapshot()
        with sqlite3.connect(self.database) as conn:
            before_schema = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
        self.assertEqual("1", str(before_schema))

        # First current-version read must perform only additive migrations.
        exact = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "retrieve-exact",
                "--vault", str(self.vault),
                "--identity", a,
            ).stdout
        )
        self.assertEqual(a, exact["result"]["stable_identity"])

        after_core = self.snapshot_core()
        self.assertEqual(before_core, after_core)
        self.assertEqual(before_markdown, self.markdown_snapshot())

        with sqlite3.connect(self.database) as conn:
            after_schema = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
            lifecycle_rows = conn.execute(
                "SELECT identity, status, superseded_by "
                "FROM knowledge_asset_lifecycle ORDER BY identity"
            ).fetchall()
            new_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ("
                    "'review_findings', 'maintenance_candidates', "
                    "'conflict_candidates', 'conflict_candidate_members', "
                    "'relation_maintenance_candidates', "
                    "'authority_edit_proposals', "
                    "'maintenance_batches', 'maintenance_batch_items', "
                    "'maintenance_batch_item_bases'"
                    ")"
                ).fetchall()
            }
            foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        self.assertEqual("7", str(after_schema))
        self.assertEqual(
            {(a, "current", None), (b, "current", None)},
            set(lifecycle_rows),
        )
        self.assertEqual(
            {
                "review_findings",
                "maintenance_candidates",
                "conflict_candidates",
                "conflict_candidate_members",
                "relation_maintenance_candidates",
                "authority_edit_proposals",
                "maintenance_batches",
                "maintenance_batch_items",
                "maintenance_batch_item_bases",
            },
            new_tables,
        )
        self.assertEqual([], foreign_key_errors)
        self.assertEqual("ok", integrity)

        # Existing 0.3 pending governance remains usable after upgrade.
        approved_pending = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", str(pending_candidate["candidate_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual("accepted", approved_pending["status"])
        self.assertEqual(1, approved_pending["relation_revision"])

        # Existing Relation Record remains same identity/triple/provenance/revision.
        with sqlite3.connect(self.database) as conn:
            accepted_relation = conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, "
                "provenance, revision, status "
                "FROM relation_records WHERE identity = ?",
                (relation_id,),
            ).fetchone()
        self.assertEqual(
            (
                relation_id,
                a,
                "supports",
                b,
                "accepted-0.3-relation",
                1,
                "active",
            ),
            accepted_relation,
        )

        # 0.4 projections and diagnostics remain read/rebuild-only.
        with sqlite3.connect(self.database) as conn:
            before_projection_objects = conn.execute(
                "SELECT identity, revision FROM objects ORDER BY identity"
            ).fetchall()
            before_projection_relations = conn.execute(
                "SELECT identity, revision FROM relation_records ORDER BY identity"
            ).fetchall()
        self.run_cli(CURRENT_CLI, "maintain-health-scan", "--vault", str(self.vault))
        self.run_cli(CURRENT_CLI, "views-rebuild", "--vault", str(self.vault))
        self.run_cli(CURRENT_CLI, "relation-graph-rebuild", "--vault", str(self.vault))
        with sqlite3.connect(self.database) as conn:
            after_projection_objects = conn.execute(
                "SELECT identity, revision FROM objects ORDER BY identity"
            ).fetchall()
            after_projection_relations = conn.execute(
                "SELECT identity, revision FROM relation_records ORDER BY identity"
            ).fetchall()
        self.assertEqual(before_projection_objects, after_projection_objects)
        self.assertEqual(before_projection_relations, after_projection_relations)
        self.assertEqual(before_markdown, self.markdown_snapshot())


if __name__ == "__main__":
    unittest.main()
