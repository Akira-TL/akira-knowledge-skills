from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[1]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class StructuredAuthorityFailureBlackBoxTests(unittest.TestCase):
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
        self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Existing.md",
            "--default-write-root", "Knowledge",
        )

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

    def vault_snapshot(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in sorted(self.vault.rglob("*")):
            if path.is_file():
                snapshot[path.relative_to(self.vault).as_posix()] = path.read_bytes()
        return snapshot

    def test_missing_structured_authority_store_blocks_capture_and_registration(self) -> None:
        self.database.unlink()
        before_seed = self.seed.read_bytes()
        before_materials = list(self.knowledge.glob("材料-*.md"))

        capture = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--confirmed-intent",
            "--note", "must not be partially captured",
            expect=2,
        )
        capture_error = json.loads(capture.stderr)
        self.assertFalse(capture_error["ok"])
        self.assertIn("structured Authority store is missing", capture_error["error"])
        self.assertFalse(self.database.exists())
        self.assertEqual(before_materials, list(self.knowledge.glob("材料-*.md")))
        self.assertEqual(before_seed, self.seed.read_bytes())

        additional = self.knowledge / "Additional.md"
        additional.write_text("ordinary existing note\n", encoding="utf-8")
        before_additional = additional.read_bytes()
        registration = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Additional.md",
            "--default-write-root", "Knowledge",
            expect=2,
        )
        registration_error = json.loads(registration.stderr)
        self.assertIn("structured Authority store is missing", registration_error["error"])
        self.assertFalse(self.database.exists())
        self.assertEqual(before_additional, additional.read_bytes())
        self.assertNotIn("akira_knowledge_id", additional.read_text(encoding="utf-8"))

    def test_corrupt_structured_authority_store_fails_closed_without_partial_markdown(self) -> None:
        corrupt = b"not-a-sqlite-database\x00preserve-corrupt-evidence"
        self.database.write_bytes(corrupt)
        before = self.vault_snapshot()

        result = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--confirmed-intent",
            "--note", "must not survive a corrupt store",
            expect=2,
        )

        payload = json.loads(result.stderr)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(corrupt, self.database.read_bytes())
        self.assertEqual(before, self.vault_snapshot())
        self.assertEqual([], list(self.knowledge.glob("材料-*.md")))


if __name__ == "__main__":
    unittest.main()
