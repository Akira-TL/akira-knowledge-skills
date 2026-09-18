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


class TaskRetrievalBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)

        primary = self.knowledge / "Primary.md"
        primary.write_text(
            "---\n"
            "topic: statistics\n"
            "audience: advanced\n"
            "---\n"
            "# Primary\n\n"
            "BayesianEvidence appears in the current Authority.\n",
            encoding="utf-8",
        )
        secondary = self.knowledge / "Secondary.md"
        secondary.write_text(
            "---\n"
            "topic: biology\n"
            "---\n"
            "# Secondary\n\n"
            "Unrelated knowledge.\n",
            encoding="utf-8",
        )

        registered = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Primary.md",
            "--note", "Knowledge/Secondary.md",
            "--default-write-root", "Knowledge",
        )
        records = json.loads(registered.stdout)["registered"]
        self.primary_identity = next(
            item["identity"] for item in records if item["locator"] == "Knowledge/Primary.md"
        )

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

    def authority_snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }

    def object_state(self) -> list[tuple[str, str, str, int]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, kind, locator, revision FROM objects ORDER BY identity"
            ).fetchall()

    def test_task_plan_deduplicates_identity_and_preserves_all_real_matches(self) -> None:
        before_authority = self.authority_snapshot()
        before_objects = self.object_state()
        before_system_entries = {
            path.name for path in (self.vault / ".akira-knowledge").iterdir()
        }

        result = self.run_cli(
            "retrieve-task",
            "--vault", str(self.vault),
            "--task", "为当前贝叶斯统计任务取得已有长期知识",
            "--scope", "current",
            "--exact", self.primary_identity,
            "--kind", "knowledge_asset",
            "--property", "topic=statistics",
            "--query", "BayesianEvidence",
        )
        payload = json.loads(result.stdout)

        self.assertEqual("为当前贝叶斯统计任务取得已有长期知识", payload["task"])
        self.assertEqual(["current"], payload["scope"])
        self.assertEqual(["current"], payload["retrieval_plan"]["scope"])
        self.assertEqual(
            ["exact", "filter", "full_text"],
            [path["type"] for path in payload["retrieval_plan"]["paths"]],
        )

        self.assertEqual(1, len(payload["results"]))
        item = payload["results"][0]
        self.assertEqual(self.primary_identity, item["stable_identity"])
        self.assertEqual("knowledge_asset", item["object_kind"])
        self.assertEqual("Knowledge/Primary.md", item["canonical_locator"])
        self.assertIn("BayesianEvidence", item["authority_text"])
        self.assertEqual(
            ["exact", "filter", "full_text"],
            item["retrieval_paths"],
        )
        self.assertEqual(3, len(item["matches"]))
        self.assertEqual(3, len(item["matched_evidence"]))
        self.assertEqual(3, len(item["retrieval_reason"]))
        self.assertTrue(any("stable identity" in value for value in item["matched_evidence"]))
        self.assertTrue(any("topic=statistics" in value for value in item["matched_evidence"]))
        self.assertTrue(any("BayesianEvidence" in value for value in item["matched_evidence"]))
        self.assertTrue(any("stable-identity" in value for value in item["retrieval_reason"]))
        self.assertTrue(any("authoritative property filter" in value for value in item["retrieval_reason"]))
        self.assertTrue(any("full-text" in value for value in item["retrieval_reason"]))

        self.assertEqual(before_authority, self.authority_snapshot())
        self.assertEqual(before_objects, self.object_state())
        self.assertEqual(
            before_system_entries,
            {path.name for path in (self.vault / ".akira-knowledge").iterdir()},
        )
        self.assertEqual(
            {"Primary.md", "Secondary.md"},
            {path.name for path in self.knowledge.glob("*.md")},
        )

    def test_task_plan_requires_explicit_retrieval_paths_and_does_not_create_state(self) -> None:
        before_authority = self.authority_snapshot()
        before_objects = self.object_state()
        before_system_entries = {
            path.name for path in (self.vault / ".akira-knowledge").iterdir()
        }

        result = self.run_cli(
            "retrieve-task",
            "--vault", str(self.vault),
            "--task", "只有任务描述但没有显式检索路径",
            expect=2,
        )

        self.assertIn("Retrieval plan must contain at least one", result.stderr)
        self.assertEqual(before_authority, self.authority_snapshot())
        self.assertEqual(before_objects, self.object_state())
        self.assertEqual(
            before_system_entries,
            {path.name for path in (self.vault / ".akira-knowledge").iterdir()},
        )


if __name__ == "__main__":
    unittest.main()
