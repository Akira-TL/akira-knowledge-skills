from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[2]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class ReleaseSurfaceBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.seed = self.knowledge / "Existing.md"
        self.seed.write_text(
            "---\ncustom: preserve-me\n---\n# Existing\n[[Linked Note]]\n<!-- preserve comment -->\n",
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

    def vault_snapshot(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in sorted(self.vault.rglob("*")):
            if path.is_file():
                snapshot[path.relative_to(self.vault).as_posix()] = path.read_bytes()
        return snapshot

    def test_approved_update_preserves_unrelated_existing_frontmatter(self) -> None:
        captured = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "支持更新的材料",
            ).stdout
        )
        proposed_body = "# Revised\n[[Approved Link]]\n<!-- approved comment -->\n"
        proposal = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", captured["identity"],
                "--target-id", self.identity,
                "--base-revision", "1",
                "--body", proposed_body,
            ).stdout
        )
        self.run_cli(
            "maintain-apply-update",
            "--vault", str(self.vault),
            "--proposal-id", proposal["proposal_id"],
            "--confirmed-approval",
        )

        updated = self.seed.read_text(encoding="utf-8")
        self.assertIn("custom: preserve-me\n", updated)
        self.assertIn(f"akira_knowledge_id: {self.identity}\n", updated)
        self.assertTrue(updated.endswith(proposed_body))

    def test_unimplemented_semantic_write_surfaces_fail_closed_without_mutation(self) -> None:
        before = self.vault_snapshot()
        unsupported_commands = (
            ("move", "--identity", "not-used", "--to", "Knowledge/Moved.md"),
            ("relate", "--source", "a", "--target", "b"),
            ("tag", "--identity", "not-used", "--value", "candidate"),
            ("accept-conflict", "--identity", "not-used"),
        )

        for command in unsupported_commands:
            with self.subTest(command=command[0]):
                result = self.run_cli(
                    command[0],
                    "--vault", str(self.vault),
                    *command[1:],
                    expect=2,
                )
                self.assertIn("invalid choice", result.stderr)
                self.assertEqual(before, self.vault_snapshot())

        self.assertTrue(self.seed.exists())
        self.assertFalse((self.knowledge / "Moved.md").exists())


if __name__ == "__main__":
    unittest.main()
