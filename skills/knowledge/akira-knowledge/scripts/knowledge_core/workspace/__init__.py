from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterator

from knowledge_core.common import BootstrapError, _write_atomic


KNOWLEDGE_ROUTER_NAME = "KNOWLEDGE.md"
AGENTS_NAME = "AGENTS.md"
GITIGNORE_NAME = ".gitignore"

DEFAULT_CONTENT_DIRS = ("收件箱", "项目", "知识", "记录", "成果", "归档", "系统", ".assets")

PROJECTION_DIR_NAMES = frozenset(
    {
        "AK Views",
        "AK Graph",
        "Akira Knowledge Views",
        "Akira Knowledge Graph",
    }
)

ENGINEERING_NOISE_DIR_NAMES = frozenset(
    {
        ".git",
        ".obsidian",
        ".akira-knowledge",
        ".agents",
        ".skiloom",
        ".skiloom-state",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        ".next",
        ".nuxt",
        "dist",
        "build",
        "coverage",
        "htmlcov",
        "target",
    }
)

SCAN_EXCLUDED_DIR_NAMES = ENGINEERING_NOISE_DIR_NAMES | PROJECTION_DIR_NAMES

AGENTS_BLOCK_START = "<!-- akira-knowledge:begin -->"
AGENTS_BLOCK_END = "<!-- akira-knowledge:end -->"
AGENTS_BLOCK = f"""{AGENTS_BLOCK_START}
## Akira Knowledge

这是一个 Akira Knowledge 单 Vault 工作区。进入本工作区后，先读取根目录 KNOWLEDGE.md；它是人类与 Agent 共用的顶层知识路由。先按其中的 Knowledge Map 判断主题、项目、代码/原型与持久化产物所在区域，再使用 Akira Knowledge 的检索入口定位具体 Knowledge Asset；不得用全目录盲扫替代正式检索。

.akira-knowledge/ 是结构化 Authority，AK Views/ 与 AK Graph/ 是可重建 Projection。依赖目录、虚拟环境、缓存和构建产物不是 Knowledge，不得纳入知识盘点或 registration。
{AGENTS_BLOCK_END}
"""

GITIGNORE_BLOCK_START = "# >>> akira-knowledge managed"
GITIGNORE_BLOCK_END = "# <<< akira-knowledge managed"
GITIGNORE_BLOCK = f"""{GITIGNORE_BLOCK_START}
# Rebuildable Akira Knowledge projections
AK Views/
AK Graph/
Akira Knowledge Views/
Akira Knowledge Graph/

# SQLite transient files; knowledge.sqlite itself remains durable Authority
.akira-knowledge/*.sqlite-wal
.akira-knowledge/*.sqlite-shm
.akira-knowledge/*.sqlite-journal

# Agent / package-manager runtime projections
.agents/
.skiloom/
.skiloom-state/

# Dependency trees, virtual environments, caches, and build products
node_modules/
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.cache/
.next/
.nuxt/
dist/
build/
coverage/
htmlcov/
target/
*.egg-info/
*.log
.DS_Store
{GITIGNORE_BLOCK_END}
"""

KNOWLEDGE_ROUTER_TEMPLATE = """# Knowledge

本文件是这个单一 Akira Knowledge Vault 的人类与 Agent 顶层路由。它负责说明知识空间如何组织、去哪里继续阅读，以及代码、原型、来源和持久化产物放在哪里；它不复制 SQLite registry、全文索引或 Relation Authority。

## Knowledge Map

| 路由 | 用途 | 入口 |
| --- | --- | --- |
| 收件箱 | 尚未判断归属的新内容，只用于暂存和后续整理 | 收件箱/ |
| 项目 | 有明确目标、持续推进的工作；项目知识、代码、框架、原型和项目记录跟项目放在一起 | 项目/ |
| 知识 | 可跨任务复用、长期维护和继续验证的知识 | 知识/ |
| 记录 | 按时间发生的事实、会议、日志、任务、样品和数据记录 | 记录/ |
| 成果 | 面向他人的课程、文章、报告、演示、网站和其他完成品 | 成果/ |
| 归档 | 已结束、被替代或仅保留作历史追溯的内容 | 归档/ |
| 系统 | 知识库自身的规范、模板、自动化、审计和维护记录 | 系统/ |

新增稳定主题或长期项目时，在这里增加一条路由；不要把每篇笔记都列成目录索引。精确知识查找继续使用 Akira Knowledge Retrieval。

## Workspace Rules

- 这是一个总 Vault：主题、项目和知识类型是逻辑分类，不各自建立 .akira-knowledge/ 或独立数据库。
- 代码、框架和原型是允许存在的一等工作内容，应放在对应 项目/<project>/ 内并正常进入 Git；不要为了代码再建立独立的根级工程仓。
- 值得长期保留的展示、报告和导出进入 成果/，或跟随其 owning 项目放在项目目录内；不要把临时导出散落在 Vault 根目录。
- node_modules/、.venv/、依赖缓存、测试缓存、构建目录和其他可再生产物不是 Knowledge，也不参与 Knowledge 扫描。
- .akira-knowledge/ 保存结构化 Authority；AK Views/ 与 AK Graph/ 只是可重建 Projection。
- KNOWLEDGE.md 自身是顶层导航 Authority，不注册成普通 Knowledge Asset，也不由 Projection 自动覆盖。

## Agent Routing

1. 进入 Vault 后先读本文件。
2. 先根据 Knowledge Map 选择相关主题或项目区域。
3. 需要精确事实、历史对象、关系或跨目录召回时，使用 Akira Knowledge Retrieval，而不是递归扫描整个 Vault。
4. 新增主题、长期项目或改变顶层路由时，先更新本文件的语义导航；普通依赖、缓存和构建输出不得进入路由。
"""


def is_scan_excluded(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return True
    parts = relative.parts
    if not parts:
        return False
    if any(part in SCAN_EXCLUDED_DIR_NAMES for part in parts):
        return True
    if path.name == AGENTS_NAME:
        return True
    if len(parts) == 1 and parts[0] == KNOWLEDGE_ROUTER_NAME:
        return True
    return False


def iter_markdown_files(root: Path, scan_root: Path | None = None) -> Iterator[Path]:
    scan_root = root if scan_root is None else scan_root
    if is_scan_excluded(root, scan_root):
        return
    for dirpath, dirnames, filenames in os.walk(scan_root, topdown=True, followlinks=False):
        current = Path(dirpath)
        kept_dirs: list[str] = []
        for name in dirnames:
            candidate = current / name
            if candidate.is_symlink() or is_scan_excluded(root, candidate):
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in filenames:
            if not name.lower().endswith(".md"):
                continue
            candidate = current / name
            if candidate.is_symlink() or is_scan_excluded(root, candidate):
                continue
            yield candidate


def replace_or_append_managed_block(
    path: Path,
    *,
    start: str,
    end: str,
    block: str,
) -> str:
    if path.exists() and not path.is_file():
        raise BootstrapError(f"Workspace control path is not a file: {path.name}")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    has_start = start in existing
    has_end = end in existing
    if has_start != has_end:
        raise BootstrapError(f"Malformed Akira Knowledge managed block in {path.name}")
    if has_start:
        before, remainder = existing.split(start, 1)
        _owned, after = remainder.split(end, 1)
        new_text = before + block.rstrip("\n") + after
        action = "updated"
    else:
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix:
            prefix += "\n"
        new_text = prefix + block.rstrip("\n") + "\n"
        action = "created" if not existing else "appended"
    _write_atomic(path, new_text)
    return action


def git_status(root: Path) -> tuple[bool, str | None]:
    if shutil.which("git") is None:
        raise BootstrapError("Git is required to initialize an Akira Knowledge workspace")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False, None
    top = result.stdout.strip()
    return True, top or None


def ensure_git_repository(root: Path) -> str:
    in_repo, top = git_status(root)
    if in_repo:
        top_path = Path(top).resolve() if top else None
        if top_path != root.resolve():
            raise BootstrapError(
                "Knowledge Vault is nested inside another Git repository; "
                "use an independent repository root instead"
            )
        return "existing"
    result = subprocess.run(
        ["git", "init", "-b", "main", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise BootstrapError(f"Cannot initialize Git repository: {result.stderr.strip()}")
    return "initialized"
