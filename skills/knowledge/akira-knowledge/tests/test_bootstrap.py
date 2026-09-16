from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid

SKILL_ROOT = Path(__file__).resolve().parents[1]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class BootstrapBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.vault.mkdir()

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

    def test_empty_vault_inspect_is_read_only(self) -> None:
        result = self.run_cli("inspect", "--vault", str(self.vault))
        payload = json.loads(result.stdout)

        self.assertTrue(payload["ok"])
        self.assertEqual(0, payload["markdown_count"])
        self.assertFalse(payload["system_exists"])
        self.assertEqual([], list(self.vault.iterdir()))

    def test_inspect_is_read_only(self) -> None:
        notes = self.vault / "Notes"
        notes.mkdir()
        note = notes / "Existing.md"
        original = "---\ntags: [old]\n---\n# Existing\n[[Other]]\n"
        note.write_text(original, encoding="utf-8")
        before = sorted(path.relative_to(self.vault).as_posix() for path in self.vault.rglob("*"))

        result = self.run_cli("inspect", "--vault", str(self.vault))
        payload = json.loads(result.stdout)

        self.assertTrue(payload["ok"])
        self.assertEqual(1, payload["markdown_count"])
        self.assertFalse(payload["system_exists"])
        self.assertEqual(before, sorted(path.relative_to(self.vault).as_posix() for path in self.vault.rglob("*")))
        self.assertEqual(original, note.read_text(encoding="utf-8"))

    def test_registration_is_in_place_and_preserves_user_content(self) -> None:
        knowledge = self.vault / "Knowledge"
        knowledge.mkdir()
        note = knowledge / "Bayes.md"
        original = (
            "---\n"
            "title: Bayes\n"
            "tags: [stats, important]\n"
            "custom: keep-me # inline comment\n"
            "---\n"
            "# 贝叶斯统计\n\n"
            "See [[Likelihood]].\n"
        )
        note.write_text(original, encoding="utf-8")

        result = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Bayes.md",
            "--default-write-root", "Knowledge",
        )
        payload = json.loads(result.stdout)
        record = payload["registered"][0]

        identity = uuid.UUID(record["identity"])
        self.assertEqual(7, identity.version)
        self.assertEqual("Knowledge/Bayes.md", record["locator"])
        self.assertEqual(1, record["revision"])

        registered = note.read_text(encoding="utf-8")
        self.assertIn("akira_knowledge_id: ", registered)
        self.assertIn("akira_knowledge_kind: knowledge_asset\n", registered)
        self.assertIn("title: Bayes\n", registered)
        self.assertIn("tags: [stats, important]\n", registered)
        self.assertIn("custom: keep-me # inline comment\n", registered)
        self.assertIn("# 贝叶斯统计\n\nSee [[Likelihood]].\n", registered)
        self.assertEqual(self.vault / "Knowledge" / "Bayes.md", note)

        config = json.loads((self.vault / ".akira-knowledge" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(1, config["schema_version"])
        self.assertEqual(["Knowledge"], config["managed_scopes"])
        self.assertEqual("Knowledge", config["default_write_root"])

        with sqlite3.connect(self.vault / ".akira-knowledge" / "knowledge.sqlite") as conn:
            row = conn.execute(
                "SELECT identity, kind, locator, revision FROM objects"
            ).fetchone()
            history = conn.execute(
                "SELECT revision, event FROM revisions"
            ).fetchone()
        self.assertEqual(record["identity"], row[0])
        self.assertEqual("knowledge_asset", row[1])
        self.assertEqual("Knowledge/Bayes.md", row[2])
        self.assertEqual(1, row[3])
        self.assertEqual((1, "registered"), history)

    def test_note_without_frontmatter_gets_only_reserved_properties(self) -> None:
        note = self.vault / "Plain.md"
        original = "# Plain\nbody\n"
        note.write_text(original, encoding="utf-8")

        self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", ".",
            "--note", "Plain.md",
            "--default-write-root", ".",
        )

        text = note.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nakira_knowledge_id: "))
        self.assertIn("akira_knowledge_kind: knowledge_asset\n---\n# Plain\nbody\n", text)

    def test_reserved_property_collision_fails_closed_before_mutation(self) -> None:
        note = self.vault / "Collision.md"
        original = "---\nakira_knowledge_id: user-value\ntags: keep\n---\nbody\n"
        note.write_text(original, encoding="utf-8")

        result = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", ".",
            "--note", "Collision.md",
            "--default-write-root", ".",
            expect=2,
        )

        self.assertIn("reserved Akira Knowledge properties", result.stderr)
        self.assertEqual(original, note.read_text(encoding="utf-8"))
        self.assertFalse((self.vault / ".akira-knowledge").exists())

    def test_unregistered_markdown_coexists_and_scope_is_enforced(self) -> None:
        approved = self.vault / "Approved"
        other = self.vault / "Other"
        approved.mkdir()
        other.mkdir()
        selected = approved / "Selected.md"
        untouched = other / "Untouched.md"
        selected.write_text("selected\n", encoding="utf-8")
        untouched.write_text("untouched\n", encoding="utf-8")

        self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Approved",
            "--note", "Approved/Selected.md",
            "--default-write-root", "Approved",
        )
        self.assertEqual("untouched\n", untouched.read_text(encoding="utf-8"))

        result = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Approved",
            "--note", "Other/Untouched.md",
            "--default-write-root", "Approved",
            expect=2,
        )
        self.assertIn("outside approved management scopes", result.stderr)
        self.assertEqual("untouched\n", untouched.read_text(encoding="utf-8"))

    def test_changing_default_write_root_does_not_move_registered_note(self) -> None:
        old_root = self.vault / "Old"
        new_root = self.vault / "New"
        old_root.mkdir()
        new_root.mkdir()
        note = old_root / "Stable.md"
        note.write_text("stable\n", encoding="utf-8")

        first = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", ".",
            "--note", "Old/Stable.md",
            "--default-write-root", "Old",
        )
        identity = json.loads(first.stdout)["registered"][0]["identity"]

        second = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", ".",
            "--note", "Old/Stable.md",
            "--default-write-root", "New",
        )
        second_record = json.loads(second.stdout)["registered"][0]
        self.assertTrue(second_record["already_registered"])
        self.assertEqual(identity, second_record["identity"])
        self.assertTrue(note.exists())
        self.assertFalse((new_root / "Stable.md").exists())

        config = json.loads((self.vault / ".akira-knowledge" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual("New", config["default_write_root"])


if __name__ == "__main__":
    unittest.main()
