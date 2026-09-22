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


class NetworkHealthBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        notes = {
            "A.md": "# A\n\nNavigate to [[B]].\n",
            "B.md": "# B\n\nNo outward navigation.\n",
            "C.md": "# C\n\nRelation-only connectivity.\n",
            "D.md": (
                "---\n"
                "owner: old\n"
                "custom: preserve-me\n"
                "# preserve frontmatter comment\n"
                "---\n"
                "# D\n\nBroken navigation to [[Missing Target#Section|Broken target]].\n"
                "<!-- preserve body comment -->\n"
            ),
            "E.md": "# E\n\nCompletely isolated.\n",
        }
        for name, body in notes.items():
            (self.knowledge / name).write_text(body, encoding="utf-8")

        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/A.md",
                "--note", "Knowledge/B.md",
                "--note", "Knowledge/C.md",
                "--note", "Knowledge/D.md",
                "--note", "Knowledge/E.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )
        self.ids = {
            Path(item["locator"]).name: str(item["identity"])
            for item in registered["registered"]
        }

        relation = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.ids["C.md"],
                "--type", "supports",
                "--target-id", self.ids["A.md"],
                "--provenance", "Connectivity evidence for health diagnostics.",
            ).stdout
        )
        approved = json.loads(
            self.run_cli(
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", str(relation["candidate_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.relation_id = str(approved["relation_identity"])

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

    def revision_snapshot(self) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        with sqlite3.connect(self.database) as conn:
            objects = conn.execute(
                "SELECT identity, revision FROM objects ORDER BY identity"
            ).fetchall()
            relations = conn.execute(
                "SELECT identity, revision FROM relation_records ORDER BY identity"
            ).fetchall()
        return objects, relations

    def test_health_scan_reports_orphan_unresolved_and_dead_end_without_mutation(self) -> None:
        before = self.revision_snapshot()

        payload = json.loads(
            self.run_cli(
                "maintain-health-scan",
                "--vault", str(self.vault),
            ).stdout
        )

        self.assertEqual("knowledge_network_health", payload["diagnostic_kind"])
        self.assertEqual(5, payload["current_knowledge_count"])
        self.assertEqual(1, payload["active_relation_count"])

        orphan_ids = {item["identity"] for item in payload["orphan"]}
        self.assertEqual(
            {self.ids["D.md"], self.ids["E.md"]},
            orphan_ids,
        )

        unresolved = payload["unresolved"]
        self.assertEqual(1, len(unresolved))
        self.assertEqual(self.ids["D.md"], unresolved[0]["source_identity"])
        self.assertEqual("Knowledge/D.md", unresolved[0]["source_locator"])
        self.assertEqual("Missing Target", unresolved[0]["reference"])
        self.assertEqual(
            "[[Missing Target#Section|Broken target]]",
            unresolved[0]["evidence"],
        )

        dead_end_ids = {item["identity"] for item in payload["dead_end"]}
        self.assertEqual({self.ids["B.md"]}, dead_end_ids)

        self.assertNotIn(self.ids["C.md"], orphan_ids)
        self.assertNotIn(self.ids["A.md"], orphan_ids)
        self.assertEqual(before, self.revision_snapshot())

        rescanned = json.loads(
            self.run_cli(
                "maintain-health-scan",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(payload["orphan"], rescanned["orphan"])
        self.assertEqual(payload["unresolved"], rescanned["unresolved"])
        self.assertEqual(payload["dead_end"], rescanned["dead_end"])
        self.assertEqual(before, self.revision_snapshot())

    def test_wikilink_maintenance_requires_proposal_and_approval_with_round_trip_safety(self) -> None:
        identity = self.ids["D.md"]
        path = self.knowledge / "D.md"
        original = path.read_text(encoding="utf-8")

        proposal = json.loads(
            self.run_cli(
                "maintain-propose-authority-edit",
                "--vault", str(self.vault),
                "--identity", identity,
                "--base-revision", "1",
                "--replace-wikilink", "Missing Target", "B",
                "--reason", "Repair the unresolved local Knowledge navigation.",
            ).stdout
        )

        self.assertEqual("authority_edit", proposal["proposal_kind"])
        self.assertEqual("wikilink", proposal["edit_kind"])
        self.assertEqual("pending", proposal["status"])
        self.assertEqual(identity, proposal["target_identity"])
        self.assertEqual(1, proposal["base_revision"])
        self.assertIn(
            "[[B#Section|Broken target]]",
            proposal["proposed_authority_text"],
        )
        self.assertIn("owner: old\n", proposal["proposed_authority_text"])
        self.assertIn("custom: preserve-me\n", proposal["proposed_authority_text"])
        self.assertIn("# preserve frontmatter comment\n", proposal["proposed_authority_text"])
        self.assertIn("<!-- preserve body comment -->\n", proposal["proposed_authority_text"])
        self.assertEqual(original, path.read_text(encoding="utf-8"))

        denied = self.run_cli(
            "maintain-apply-authority-edit",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            expect=2,
        )
        self.assertIn("explicit user approval", denied.stderr)
        self.assertEqual(original, path.read_text(encoding="utf-8"))

        applied = json.loads(
            self.run_cli(
                "maintain-apply-authority-edit",
                "--vault", str(self.vault),
                "--proposal-id", str(proposal["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(2, applied["revision"])
        updated = path.read_text(encoding="utf-8")
        self.assertIn("[[B#Section|Broken target]]", updated)
        self.assertNotIn("[[Missing Target#Section|Broken target]]", updated)
        self.assertIn("owner: old\n", updated)
        self.assertIn("custom: preserve-me\n", updated)
        self.assertIn("# preserve frontmatter comment\n", updated)
        self.assertIn("<!-- preserve body comment -->\n", updated)

        with sqlite3.connect(self.database) as conn:
            relation_count = conn.execute(
                "SELECT COUNT(*) FROM relation_records"
            ).fetchone()[0]
        self.assertEqual(1, relation_count)

        health = json.loads(
            self.run_cli(
                "maintain-health-scan",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertNotIn(
            identity,
            {item["source_identity"] for item in health["unresolved"]},
        )
        self.assertNotIn(
            identity,
            {item["identity"] for item in health["orphan"]},
        )

    def test_user_property_maintenance_preserves_unrelated_authority_and_is_revision_safe(self) -> None:
        identity = self.ids["D.md"]
        path = self.knowledge / "D.md"
        proposal = json.loads(
            self.run_cli(
                "maintain-propose-authority-edit",
                "--vault", str(self.vault),
                "--identity", identity,
                "--base-revision", "1",
                "--set-property", "owner", "new-owner",
                "--reason", "Correct the human-owned owner property.",
            ).stdout
        )

        self.assertEqual("property", proposal["edit_kind"])
        self.assertIn("owner: new-owner\n", proposal["proposed_authority_text"])
        self.assertIn(
            "[[Missing Target#Section|Broken target]]",
            proposal["proposed_authority_text"],
        )
        self.assertIn("custom: preserve-me\n", proposal["proposed_authority_text"])
        self.assertIn("# preserve frontmatter comment\n", proposal["proposed_authority_text"])

        current = path.read_text(encoding="utf-8")
        path.write_text(
            current.replace(
                "Broken navigation",
                "Newer direct edit before approval. Broken navigation",
            ),
            encoding="utf-8",
        )
        stale = self.run_cli(
            "maintain-apply-authority-edit",
            "--vault", str(self.vault),
            "--proposal-id", str(proposal["proposal_id"]),
            "--confirmed-approval",
            expect=2,
        )
        self.assertIn("proposal is stale", stale.stderr.lower())
        self.assertIn(
            "Newer direct edit before approval",
            path.read_text(encoding="utf-8"),
        )
        self.assertIn("owner: old\n", path.read_text(encoding="utf-8"))

    def test_authority_edit_rejects_knowledge_owned_property_without_mutation(self) -> None:
        identity = self.ids["D.md"]
        path = self.knowledge / "D.md"
        before = path.read_bytes()
        before_revisions = self.revision_snapshot()

        failed = self.run_cli(
            "maintain-propose-authority-edit",
            "--vault", str(self.vault),
            "--identity", identity,
            "--base-revision", "1",
            "--set-property", "akira_knowledge_id", "forbidden",
            "--reason", "Must not edit Knowledge-owned metadata through human Authority.",
            expect=2,
        )

        self.assertIn("knowledge-owned property", failed.stderr.lower())
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(before_revisions, self.revision_snapshot())

    def test_health_scan_missing_structured_authority_fails_closed_without_recreation(self) -> None:
        before_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.database.unlink()

        failed = self.run_cli(
            "maintain-health-scan",
            "--vault", str(self.vault),
            expect=2,
        )

        self.assertIn("structured authority store is missing", failed.stderr.lower())
        self.assertFalse(self.database.exists())
        after_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.assertEqual(before_markdown, after_markdown)

    def test_v5_schema_migrates_authority_edit_governance_without_revision_or_markdown_changes(self) -> None:
        before_revisions = self.revision_snapshot()
        before_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            self.assertEqual("6", schema_version)
            conn.execute("DROP TABLE authority_edit_proposals")
            conn.execute(
                "UPDATE schema_meta SET value = '5' WHERE key = 'schema_version'"
            )
            conn.commit()

        payload = json.loads(
            self.run_cli(
                "maintain-health-scan",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual("knowledge_network_health", payload["diagnostic_kind"])

        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            table = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='authority_edit_proposals'"
            ).fetchone()
            proposal_count = conn.execute(
                "SELECT COUNT(*) FROM authority_edit_proposals"
            ).fetchone()[0]
        self.assertEqual("6", schema_version)
        self.assertEqual(("authority_edit_proposals",), table)
        self.assertEqual(0, proposal_count)
        self.assertEqual(before_revisions, self.revision_snapshot())
        after_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.assertEqual(before_markdown, after_markdown)

    def test_v6_missing_authority_edit_governance_fails_closed(self) -> None:
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(
                "6",
                conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0],
            )
            conn.execute("DROP TABLE authority_edit_proposals")
            conn.commit()

        failed = self.run_cli(
            "maintain-health-scan",
            "--vault", str(self.vault),
            expect=2,
        )
        self.assertIn(
            "authority edit structured governance is missing",
            failed.stderr.lower(),
        )
        with sqlite3.connect(self.database) as conn:
            missing = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='authority_edit_proposals'"
            ).fetchall()
        self.assertEqual([], missing)

    def test_duplicate_stable_identity_fails_closed_without_mutation(self) -> None:
        source = self.knowledge / "A.md"
        duplicate = self.knowledge / "A-copy.md"
        original = source.read_bytes()
        duplicate.write_bytes(original)
        before_revisions = self.revision_snapshot()

        failed = self.run_cli(
            "maintain-health-scan",
            "--vault", str(self.vault),
            expect=2,
        )

        self.assertIn("duplicate stable identity", failed.stderr.lower())
        self.assertEqual(before_revisions, self.revision_snapshot())
        self.assertEqual(original, source.read_bytes())
        self.assertEqual(original, duplicate.read_bytes())

    def test_ambiguous_wikilink_target_fails_closed_instead_of_reporting_unresolved(self) -> None:
        (self.knowledge / "X").mkdir()
        (self.knowledge / "Y").mkdir()
        (self.knowledge / "X" / "Shared.md").write_text("# Shared X\n", encoding="utf-8")
        (self.knowledge / "Y" / "Shared.md").write_text("# Shared Y\n", encoding="utf-8")
        ambiguous = self.knowledge / "Ambiguous.md"
        ambiguous.write_text("# Ambiguous\n\n[[Shared]]\n", encoding="utf-8")

        self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/X/Shared.md",
            "--note", "Knowledge/Y/Shared.md",
            "--note", "Knowledge/Ambiguous.md",
            "--default-write-root", "Knowledge",
        )

        failed = self.run_cli(
            "maintain-health-scan",
            "--vault", str(self.vault),
            expect=2,
        )
        self.assertIn(
            "ambiguous local knowledge reference",
            failed.stderr.lower(),
        )


if __name__ == "__main__":
    unittest.main()
