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


class CaptureBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        root = self.vault / "Knowledge"
        root.mkdir(parents=True)
        seed = root / "Existing.md"
        seed.write_text("existing\n", encoding="utf-8")
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

    def capture(self, note: str, source: str) -> dict[str, object]:
        result = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--confirmed-intent",
            "--note", note,
            "--source", source,
        )
        return json.loads(result.stdout)

    def material_count(self) -> int:
        with sqlite3.connect(self.vault / ".akira-knowledge" / "knowledge.sqlite") as conn:
            return conn.execute("SELECT COUNT(*) FROM material_records").fetchone()[0]

    def test_explicit_capture_creates_readable_material_with_provenance(self) -> None:
        note = "这是用户原始的 capture note。\n第二行保持原样。"
        source = "https://example.org/article?id=42"
        payload = self.capture(note, source)

        self.assertTrue(payload["ok"])
        self.assertEqual("material_record", payload["kind"])
        self.assertEqual("待处理", payload["status"])
        self.assertEqual(1, payload["revision"])
        self.assertEqual([source], payload["sources"])

        material = self.vault / payload["locator"]
        text = material.read_text(encoding="utf-8")
        self.assertIn(f"akira_knowledge_id: {payload['identity']}\n", text)
        self.assertIn("akira_knowledge_kind: material_record\n", text)
        self.assertIn("akira_knowledge_status: 待处理\n", text)
        self.assertTrue(text.endswith(note))
        self.assertNotIn("summary:", text)
        self.assertNotIn("tags:", text)

        with sqlite3.connect(self.vault / ".akira-knowledge" / "knowledge.sqlite") as conn:
            record = conn.execute(
                "SELECT status FROM material_records WHERE identity = ?",
                (payload["identity"],),
            ).fetchone()
            source_row = conn.execute(
                "SELECT locator FROM material_sources WHERE material_identity = ?",
                (payload["identity"],),
            ).fetchone()
            event = conn.execute(
                "SELECT intent_mode FROM capture_events WHERE material_identity = ?",
                (payload["identity"],),
            ).fetchone()
        self.assertEqual(("待处理",), record)
        self.assertEqual((source,), source_row)
        self.assertEqual(("explicit",), event)
        self.assertNotEqual(source, payload["identity"])

    def test_capture_without_confirmed_persistent_intent_does_not_write(self) -> None:
        before_files = sorted(path.name for path in (self.vault / "Knowledge").glob("材料-*.md"))
        before_count = self.material_count()

        result = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--note", "普通任务里偶然出现的信息",
            expect=2,
        )

        self.assertIn("explicit persistent intent", result.stderr)
        self.assertEqual(before_count, self.material_count())
        self.assertEqual(
            before_files,
            sorted(path.name for path in (self.vault / "Knowledge").glob("材料-*.md")),
        )

    def test_same_source_creates_distinct_materials_and_only_reports_candidate(self) -> None:
        source = "doi:10.1234/example"
        first = self.capture("第一次捕获", source)
        second = self.capture("第二次捕获", source)

        self.assertNotEqual(first["identity"], second["identity"])
        self.assertNotEqual(first["locator"], second["locator"])
        self.assertEqual(2, self.material_count())
        self.assertIn(source, second["duplicate_candidates"])
        self.assertIn(first["identity"], second["duplicate_candidates"][source])
        self.assertTrue((self.vault / first["locator"]).exists())
        self.assertTrue((self.vault / second["locator"]).exists())


if __name__ == "__main__":
    unittest.main()
