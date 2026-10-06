from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[2]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class HumanReadableWritingTests(unittest.TestCase):
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

    def test_normal_human_readable_note_passes_strict_review(self) -> None:
        body = (
            "# FastQC 报告解读\n\n"
            "FastQC 用于快速检查测序数据的质量特征。它的 warning 和 fail "
            "表示指标偏离经验阈值，不等价于数据不可用。\n\n"
            "## 判断原则\n\n"
            "先结合文库类型判断异常是否符合预期，再决定是否需要处理。"
            "质量下降、接头残留和重复率需要分别解释，不能只看红色标记。\n"
        )
        payload = json.loads(
            self.run_cli("writing-check", "--body", body, "--strict").stdout
        )
        self.assertTrue(payload["ok"])
        self.assertEqual("FastQC 报告解读", payload["title"])
        self.assertEqual([], payload["errors"])
        self.assertEqual([], payload["warnings"])

    def test_missing_h1_fails_closed(self) -> None:
        result = self.run_cli(
            "writing-check",
            "--body", "只有正文，没有一级标题。",
            expect=2,
        )
        self.assertIn("missing_h1", result.stderr)

    def test_heading_level_jump_fails_closed(self) -> None:
        result = self.run_cli(
            "writing-check",
            "--body", "# 标题\n\n正文。\n\n### 跳级标题\n\n内容。\n",
            expect=2,
        )
        self.assertIn("heading_level_jump", result.stderr)

    def test_generation_style_opening_fails_closed(self) -> None:
        result = self.run_cli(
            "writing-check",
            "--body", "# 方法说明\n\n本文将介绍这个方法的使用方式。\n",
            expect=2,
        )
        self.assertIn("meta_opening", result.stderr)

    def test_wall_paragraph_fails_closed(self) -> None:
        paragraph = "这个句子持续堆叠大量解释而没有合理分段。" * 40
        result = self.run_cli(
            "writing-check",
            "--body", f"# 墙状段落示例\n\n{paragraph}\n",
            expect=2,
        )
        self.assertIn("wall_paragraph", result.stderr)

    def test_many_short_single_sentence_paragraphs_fail_closed(self) -> None:
        body = (
            "# 碎片段落示例\n\n"
            "第一点。\n\n"
            "第二点。\n\n"
            "第三点。\n\n"
            "第四点。\n\n"
            "第五点。\n"
        )
        result = self.run_cli("writing-check", "--body", body, expect=2)
        self.assertIn("fragmented_paragraphs", result.stderr)

    def test_generic_heading_is_warning_and_strict_mode_rejects_it(self) -> None:
        body = (
            "# 参数选择\n\n"
            "参数应根据输入数据和验证目标选择。\n\n"
            "## 总结\n\n"
            "不要机械复制固定参数。\n"
        )
        payload = json.loads(self.run_cli("writing-check", "--body", body).stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(any(x["code"] == "generic_heading" for x in payload["warnings"]))

        result = self.run_cli(
            "writing-check",
            "--body", body,
            "--strict",
            expect=2,
        )
        self.assertIn("generic_heading", result.stderr)

    def test_update_baseline_allows_existing_style_debt_but_blocks_regression(self) -> None:
        baseline = (
            "# 现有知识\n\n"
            "这是一个已经存在的知识资产。\n\n"
            "## 总结\n\n"
            "这个泛化标题属于既有写作债务。\n"
        )
        candidate = baseline.replace(
            "这是一个已经存在的知识资产。",
            "这是一个已经存在的知识资产。本次只补充一个与旧标题无关的事实。",
        )
        payload = json.loads(
            self.run_cli(
                "writing-check",
                "--baseline", baseline,
                "--body", candidate,
                "--strict",
            ).stdout
        )
        self.assertTrue(payload["strict_ok"])
        self.assertEqual([], payload["regressions"]["warnings"])

        worsened = candidate + "\n## 分析\n\n新增的泛化标题属于新的写作问题。\n"
        result = self.run_cli(
            "writing-check",
            "--baseline", baseline,
            "--body", worsened,
            "--strict",
            expect=2,
        )
        self.assertIn("generic_heading", result.stderr)

    def test_code_fence_does_not_trigger_prose_findings(self) -> None:
        code_lines = "\n".join(f"- generated-code-{i}-" + ("x" * 220) for i in range(25))
        fence = chr(96) * 3
        body = (
            "# 代码示例\n\n"
            "代码块是原始示例，写作检查不把代码内容当作正文。\n\n"
            + fence + "text\n" + code_lines + "\n" + fence + "\n"
        )
        payload = json.loads(
            self.run_cli("writing-check", "--body", body, "--strict").stdout
        )
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["warnings"])


if __name__ == "__main__":
    unittest.main()
