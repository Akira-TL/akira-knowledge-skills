from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
from typing import Iterable


_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_FENCE_RE = re.compile(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$")
_BRACKET_MATH_RE = re.compile(r"(?ms)^\s*\\\[\s*$.*?^\s*\\\]\s*$")
_DOLLAR_MATH_RE = re.compile(r"(?ms)^\s*\$\$\s*$.*?^\s*\$\$\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])(?:[”’\"']?)(?=\s*|$)")

_STRONG_OPENING_META = (
    "本文将",
    "本文主要",
    "在本文中",
    "下面将",
    "接下来将",
    "以下内容将",
    "我们将",
    "首先我们",
)
_AI_META_PHRASES = (
    "值得注意的是",
    "需要明确的是",
    "从上述分析可以看出",
    "综上所述",
    "不难发现",
    "总的来说",
    "从整体上来看",
    "在这一部分中",
    "接下来我们",
)
_GENERIC_HEADINGS = {
    "背景",
    "概述",
    "分析",
    "说明",
    "总结",
    "其他",
    "相关内容",
    "进一步说明",
    "补充说明",
    "一些说明",
}
_GENERIC_TITLES = {
    "笔记",
    "总结",
    "资料",
    "相关内容",
    "一些问题",
    "一些想法",
    "其他",
    "未命名",
}


@dataclass(frozen=True)
class WritingFinding:
    code: str
    severity: str
    message: str
    line: int | None = None


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def _strip_non_prose_blocks(text: str) -> str:
    def preserve_lines(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    text = _FENCE_RE.sub(preserve_lines, text)
    text = _BRACKET_MATH_RE.sub(preserve_lines, text)
    return _DOLLAR_MATH_RE.sub(preserve_lines, text)


def _sentence_count(paragraph: str) -> int:
    compact = re.sub(r"\s+", " ", paragraph).strip()
    if not compact:
        return 0
    chunks = [chunk for chunk in _SENTENCE_SPLIT_RE.split(compact) if chunk.strip()]
    return max(1, len(chunks))


def _max_sentence_length(paragraph: str) -> int:
    compact = re.sub(r"\s+", " ", paragraph).strip()
    if not compact:
        return 0
    chunks = [chunk.strip() for chunk in _SENTENCE_SPLIT_RE.split(compact) if chunk.strip()]
    return max((len(chunk) for chunk in chunks), default=0)


def _paragraphs(lines: list[str]) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    buf: list[str] = []
    start_line = 0
    end_line = 0

    def flush() -> None:
        nonlocal buf, start_line, end_line
        if buf:
            result.append((start_line, end_line, " ".join(line.strip() for line in buf)))
            buf = []
            start_line = 0
            end_line = 0

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if (
            not stripped
            or _HEADING_RE.match(stripped)
            or _LIST_RE.match(stripped)
            or _TABLE_RE.match(stripped)
            or stripped.startswith(">")
            or stripped.startswith("![")
        ):
            flush()
            continue
        if not buf:
            start_line = lineno
        end_line = lineno
        buf.append(line)
    flush()
    return result


def inspect_human_readable_knowledge(text: str) -> dict[str, object]:
    body = _strip_non_prose_blocks(_strip_frontmatter(text))
    lines = body.splitlines()
    findings: list[WritingFinding] = []

    headings: list[tuple[int, int, str]] = []
    for lineno, line in enumerate(lines, 1):
        match = _HEADING_RE.match(line.strip())
        if match:
            headings.append((lineno, len(match.group(1)), match.group(2).strip()))

    h1s = [heading for heading in headings if heading[1] == 1]
    if not h1s:
        findings.append(
            WritingFinding(
                "missing_h1",
                "error",
                "Knowledge Asset 必须有且只有一个一级标题，作为主要人类检索句柄。",
            )
        )
        title = None
    else:
        title = h1s[0][2]
        if len(h1s) > 1:
            findings.append(
                WritingFinding(
                    "multiple_h1",
                    "error",
                    "Knowledge Asset 只能有一个一级标题；其余结构使用二级或三级标题。",
                    h1s[1][0],
                )
            )
        if title in _GENERIC_TITLES or len(title.strip()) < 2:
            findings.append(
                WritingFinding(
                    "generic_title",
                    "warning",
                    f"一级标题“{title}”过于泛化，未来难以搜索和区分。",
                    h1s[0][0],
                )
            )

    previous_level = 0
    for lineno, level, heading in headings:
        if previous_level and level > previous_level + 1:
            findings.append(
                WritingFinding(
                    "heading_level_jump",
                    "error",
                    f"标题层级从 H{previous_level} 跳到 H{level}；请保持连续层级。",
                    lineno,
                )
            )
        previous_level = level
        if level > 1 and heading in _GENERIC_HEADINGS:
            findings.append(
                WritingFinding(
                    "generic_heading",
                    "warning",
                    f"小节标题“{heading}”检索信息不足；优先改成能说明本节内容的描述性标题。",
                    lineno,
                )
            )

    prose_paragraphs = _paragraphs(lines)
    opening = prose_paragraphs[0][2] if prose_paragraphs else ""
    for phrase in _STRONG_OPENING_META:
        if phrase in opening[:300]:
            findings.append(
                WritingFinding(
                    "meta_opening",
                    "error",
                    f"开头包含生成式铺垫“{phrase}”；请直接给定义、结论、用途或适用范围。",
                    prose_paragraphs[0][0] if prose_paragraphs else None,
                )
            )
            break

    single_streak = 0
    single_streak_start: int | None = None
    previous_paragraph_end: int | None = None
    for lineno, paragraph_end, paragraph in prose_paragraphs:
        if previous_paragraph_end is not None and lineno > previous_paragraph_end + 2:
            if single_streak >= 5:
                findings.append(
                    WritingFinding(
                        "fragmented_paragraphs",
                        "error",
                        "连续出现至少 5 个短单句段落，阅读节奏过碎；请合并为连贯段落。",
                        single_streak_start,
                    )
                )
            elif single_streak >= 4:
                findings.append(
                    WritingFinding(
                        "fragmented_paragraphs",
                        "warning",
                        "连续出现多个短单句段落；检查是否为了排版而把一个完整意思拆碎。",
                        single_streak_start,
                    )
                )
            single_streak = 0
            single_streak_start = None

        sentence_count = _sentence_count(paragraph)
        char_count = len(re.sub(r"\s+", "", paragraph))
        max_sentence = _max_sentence_length(paragraph)

        if char_count >= 500 or sentence_count >= 9:
            findings.append(
                WritingFinding(
                    "wall_paragraph",
                    "error",
                    "段落明显过长，可能同时承载多个意思；请拆分或改为真正的结构化列表 / 表格。",
                    lineno,
                )
            )
        elif char_count >= 300 or sentence_count >= 6:
            findings.append(
                WritingFinding(
                    "long_paragraph",
                    "warning",
                    "段落较长；检查是否可以按完整意思拆分，并把重点移到段首。",
                    lineno,
                )
            )

        if max_sentence >= 180:
            findings.append(
                WritingFinding(
                    "very_long_sentence",
                    "error",
                    "存在异常长句；请拆分多层条件、因果或并列关系。",
                    lineno,
                )
            )
        elif max_sentence >= 100:
            findings.append(
                WritingFinding(
                    "long_sentence",
                    "warning",
                    "存在较长句；检查是否可以在不破坏逻辑的前提下拆成更直接的完整句。",
                    lineno,
                )
            )

        if sentence_count == 1 and char_count <= 120:
            if single_streak == 0:
                single_streak_start = lineno
            single_streak += 1
        else:
            if single_streak >= 5:
                findings.append(
                    WritingFinding(
                        "fragmented_paragraphs",
                        "error",
                        "连续出现至少 5 个短单句段落，阅读节奏过碎；请合并为连贯段落。",
                        single_streak_start,
                    )
                )
            elif single_streak >= 4:
                findings.append(
                    WritingFinding(
                        "fragmented_paragraphs",
                        "warning",
                        "连续出现多个短单句段落；检查是否为了排版而把一个完整意思拆碎。",
                        single_streak_start,
                    )
                )
            single_streak = 0
            single_streak_start = None
        previous_paragraph_end = paragraph_end
    if single_streak >= 5:
        findings.append(
            WritingFinding(
                "fragmented_paragraphs",
                "error",
                "连续出现至少 5 个短单句段落，阅读节奏过碎；请合并为连贯段落。",
                single_streak_start,
            )
        )
    elif single_streak >= 4:
        findings.append(
            WritingFinding(
                "fragmented_paragraphs",
                "warning",
                "连续出现多个短单句段落；检查是否为了排版而把一个完整意思拆碎。",
                single_streak_start,
            )
        )

    list_lines = sum(1 for line in lines if _LIST_RE.match(line))
    content_lines = sum(
        1
        for line in lines
        if line.strip()
        and not _HEADING_RE.match(line.strip())
        and not _TABLE_RE.match(line.strip())
    )
    if (
        list_lines >= 24
        and content_lines
        and list_lines / content_lines >= 0.8
        and len(prose_paragraphs) <= 2
    ):
        findings.append(
            WritingFinding(
                "list_dominant",
                "warning",
                "正文几乎完全由列表组成且缺少必要解释；确认这确实是速查 / 检查清单，而不是把连续论述误拆成 bullet。",
            )
        )

    body_without_code = _strip_non_prose_blocks(body)
    for phrase in _AI_META_PHRASES:
        count = body_without_code.count(phrase)
        if count:
            findings.append(
                WritingFinding(
                    "ai_meta_language",
                    "warning",
                    f"检测到 {count} 处“{phrase}”；如果删掉不损失语义，应直接删除元话语。",
                )
            )

    if all(token in body_without_code for token in ("首先", "其次", "再次", "最后")):
        findings.append(
            WritingFinding(
                "formulaic_sequence",
                "warning",
                "同时出现“首先 / 其次 / 再次 / 最后”；检查是否只是形式化 AI 排比而非真实顺序。",
            )
        )

    errors = [asdict(item) for item in findings if item.severity == "error"]
    warnings = [asdict(item) for item in findings if item.severity == "warning"]
    return {
        "ok": not errors,
        "title": title,
        "errors": errors,
        "warnings": warnings,
        "finding_count": len(findings),
    }


def compare_human_readable_knowledge(
    baseline_text: str,
    candidate_text: str,
) -> dict[str, object]:
    baseline = inspect_human_readable_knowledge(baseline_text)
    candidate = inspect_human_readable_knowledge(candidate_text)

    def regressions(severity: str) -> list[dict[str, object]]:
        baseline_findings = baseline["errors"] if severity == "error" else baseline["warnings"]
        candidate_findings = candidate["errors"] if severity == "error" else candidate["warnings"]
        baseline_counts = Counter(str(item["code"]) for item in baseline_findings)
        seen = Counter()
        result: list[dict[str, object]] = []
        for item in candidate_findings:
            code = str(item["code"])
            seen[code] += 1
            if seen[code] > baseline_counts[code]:
                result.append(item)
        return result

    error_regressions = regressions("error")
    warning_regressions = regressions("warning")
    return {
        "ok": not error_regressions,
        "strict_ok": not error_regressions and not warning_regressions,
        "title": candidate["title"],
        "baseline": baseline,
        "candidate": candidate,
        "regressions": {
            "errors": error_regressions,
            "warnings": warning_regressions,
        },
    }


def format_writing_findings(findings: Iterable[dict[str, object]]) -> str:
    parts: list[str] = []
    for finding in findings:
        code = str(finding.get("code", "writing"))
        message = str(finding.get("message", ""))
        line = finding.get("line")
        location = f" line {line}" if line else ""
        parts.append(f"{code}{location}: {message}")
    return "; ".join(parts)
