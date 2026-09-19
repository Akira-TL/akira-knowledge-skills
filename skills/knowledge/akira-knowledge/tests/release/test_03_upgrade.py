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
OLD_HEAD = "66c67c9d0bb59f8e46eb18081446dd7c78ee0552"


class Upgrade02To03BlackBoxTests(unittest.TestCase):
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
            "---\n"
            "custom: preserve-a\n"
            "---\n"
            "# A\n\n"
            "Legacy 0.2 source. [[B]]\n"
            "<!-- preserve-a-comment -->\n",
            encoding="utf-8",
        )
        self.b_path.write_text(
            "---\n"
            "custom: preserve-b\n"
            "---\n"
            "# B\n\n"
            "Legacy 0.2 target.\n"
            "<!-- preserve-b-comment -->\n",
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

    def snapshot_sql(self) -> dict[str, list[tuple[object, ...]]]:
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
            }

    def snapshot_markdown(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
            if ".akira-knowledge" not in path.parts
            and "Akira Knowledge Graph" not in path.parts
            and "Akira Knowledge Views" not in path.parts
        }

    def test_real_02_vault_upgrades_in_place_and_preserves_legacy_relation(self) -> None:
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
        identities = {
            Path(item["locator"]).name: item["identity"]
            for item in registered
        }
        a = identities["A.md"]
        b = identities["B.md"]

        material = json.loads(
            self.run_cli(
                self.old_cli,
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Legacy 0.2 material for pending proposal.",
                "--source", "https://example.org/legacy-02",
            ).stdout
        )
        proposal = json.loads(
            self.run_cli(
                self.old_cli,
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", material["identity"],
                "--body", "# Legacy pending proposal\n\nMust survive upgrade.\n",
            ).stdout
        )
        self.assertEqual("pending", proposal["status"])

        legacy_relation_id = "0199a000-0000-7000-8000-000000000003"
        with sqlite3.connect(self.database) as conn:
            relation_columns = [
                row[1]
                for row in conn.execute("PRAGMA table_info(relation_records)").fetchall()
            ]
            self.assertNotIn("status", relation_columns)
            conn.execute(
                "INSERT INTO relation_records("
                "identity, source_ref, relation_type, target_ref, provenance, revision"
                ") VALUES (?, ?, 'supports', ?, 'legacy-0.2-basis', 1)",
                (legacy_relation_id, a, b),
            )
            conn.commit()

        before_sql = self.snapshot_sql()
        before_markdown = self.snapshot_markdown()
        with sqlite3.connect(self.database) as conn:
            before_relation = conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, revision "
                "FROM relation_records WHERE identity = ?",
                (legacy_relation_id,),
            ).fetchone()

        # First current-version read initializes only additive 0.3 schema and must
        # immediately consume the legacy 0.2 relation.
        traversal = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "read legacy relation after in-place upgrade",
                "--relation-seed", a,
                "--relation-direction", "outgoing",
                "--relation-type", "supports",
            ).stdout
        )
        self.assertEqual([b], [item["stable_identity"] for item in traversal["results"]])
        relation_meta = traversal["results"][0]["matches"][0]["relation"]
        self.assertEqual(legacy_relation_id, relation_meta["identity"])
        self.assertEqual(["legacy-0.2-basis"], relation_meta["provenance_entries"])

        self.assertEqual(before_sql, self.snapshot_sql())
        self.assertEqual(before_markdown, self.snapshot_markdown())
        with sqlite3.connect(self.database) as conn:
            upgraded_relation = conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, "
                "revision, status FROM relation_records WHERE identity = ?",
                (legacy_relation_id,),
            ).fetchone()
            relation_events = conn.execute(
                "SELECT revision, event, provenance FROM relation_events "
                "WHERE relation_identity = ? ORDER BY revision",
                (legacy_relation_id,),
            ).fetchall()
            candidate_table = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='relation_candidates'"
            ).fetchone()
        self.assertEqual((*before_relation, "active"), upgraded_relation)
        self.assertEqual(
            [(1, "existing_relation", "legacy-0.2-basis")],
            relation_events,
        )
        self.assertIsNotNone(candidate_table)

        # A 0.3 Candidate for the same triple augments the legacy relation in place.
        candidate = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", a,
                "--type", "supports",
                "--target-id", b,
                "--provenance", "new-0.3-basis",
            ).stdout
        )
        approved = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", candidate["candidate_id"],
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(legacy_relation_id, approved["relation_identity"])
        self.assertFalse(approved["relation_created"])
        self.assertTrue(approved["provenance_added"])
        self.assertEqual(2, approved["relation_revision"])
        self.assertEqual(
            ["legacy-0.2-basis", "new-0.3-basis"],
            approved["provenance"],
        )

        graph = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "relation-graph-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(1, graph["relation_count"])
        graph_node = (
            self.vault
            / "Akira Knowledge Graph"
            / f"relation-{legacy_relation_id}.md"
        )
        graph_text = graph_node.read_text(encoding="utf-8")
        self.assertIn("[[Knowledge/A]]", graph_text)
        self.assertIn("[[Knowledge/B]]", graph_text)
        self.assertIn("legacy-0.2-basis", graph_text)
        self.assertIn("new-0.3-basis", graph_text)

        revoked = json.loads(
            self.run_cli(
                CURRENT_CLI,
                "relation-revoke",
                "--vault", str(self.vault),
                "--relation-id", legacy_relation_id,
                "--expected-revision", "2",
                "--confirmed-revoke",
            ).stdout
        )
        self.assertEqual(legacy_relation_id, revoked["relation_identity"])
        self.assertEqual("revoked", revoked["status"])
        self.assertEqual(3, revoked["revision"])

        # Legacy Knowledge state and pending proposal remain continuous even after
        # exercising the new relation lifecycle.
        after_sql = self.snapshot_sql()
        self.assertEqual(before_sql["objects"], after_sql["objects"])
        self.assertEqual(before_sql["revisions"], after_sql["revisions"])
        self.assertEqual(before_sql["proposals"], after_sql["proposals"])
        self.assertEqual(before_markdown, self.snapshot_markdown())

        with sqlite3.connect(self.database) as conn:
            final_relation = conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, "
                "revision, status FROM relation_records WHERE identity = ?",
                (legacy_relation_id,),
            ).fetchone()
            final_events = conn.execute(
                "SELECT revision, event, provenance FROM relation_events "
                "WHERE relation_identity = ? ORDER BY revision",
                (legacy_relation_id,),
            ).fetchall()
        self.assertEqual(
            (
                legacy_relation_id,
                a,
                "supports",
                b,
                "legacy-0.2-basis",
                3,
                "revoked",
            ),
            final_relation,
        )
        self.assertEqual(
            [
                (1, "existing_relation", "legacy-0.2-basis"),
                (2, "provenance_added", "new-0.3-basis"),
                (3, "revoked", None),
            ],
            final_events,
        )


if __name__ == "__main__":
    unittest.main()
