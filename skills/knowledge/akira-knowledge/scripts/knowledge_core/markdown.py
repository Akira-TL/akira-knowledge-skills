from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

AK_ID = "akira_knowledge_id"
AK_KIND = "akira_knowledge_kind"
AK_STATUS = "akira_knowledge_status"
AK_KEYS = (AK_ID, AK_KIND, AK_STATUS)
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:")


class MarkdownConflict(ValueError):
    pass


@dataclass(frozen=True)
class FrontmatterView:
    prefix: str
    lines: tuple[str, ...]
    closing: str
    body: str

    @property
    def exists(self) -> bool:
        return bool(self.prefix)


def split_frontmatter(text: str) -> FrontmatterView:
    if not text.startswith("---\n") and text != "---":
        return FrontmatterView("", (), "", text)

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return FrontmatterView("", (), "", text)

    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") in {"---", "..."}:
            return FrontmatterView(
                prefix=lines[0],
                lines=tuple(lines[1:index]),
                closing=lines[index],
                body="".join(lines[index + 1 :]),
            )
    raise MarkdownConflict("Markdown starts with YAML frontmatter but has no closing delimiter")


def top_level_keys(view: FrontmatterView) -> set[str]:
    keys: set[str] = set()
    for line in view.lines:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def has_knowledge_keys(text: str) -> bool:
    view = split_frontmatter(text)
    keys = top_level_keys(view)
    return any(key in keys for key in AK_KEYS)


def inject_registration(text: str, *, identity: str, kind: str) -> str:
    view = split_frontmatter(text)
    keys = top_level_keys(view)
    conflicts = [key for key in AK_KEYS if key in keys]
    if conflicts:
        raise MarkdownConflict(
            "unregistered Markdown already contains reserved Akira Knowledge properties: "
            + ", ".join(conflicts)
        )

    injected = (f"{AK_ID}: {identity}\n", f"{AK_KIND}: {kind}\n")
    if view.exists:
        return view.prefix + "".join(view.lines + injected) + view.closing + view.body
    return "---\n" + "".join(injected) + "---\n" + text


def create_material_markdown(*, identity: str, status: str, capture_note: str) -> str:
    return (
        "---\n"
        f"{AK_ID}: {identity}\n"
        "akira_knowledge_kind: material_record\n"
        f"{AK_STATUS}: {status}\n"
        "---\n"
        f"{capture_note}"
    )


def registration_values(text: str) -> dict[str, str]:
    view = split_frontmatter(text)
    values: dict[str, str] = {}
    for line in view.lines:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if not match or match.group(1) not in AK_KEYS:
            continue
        key = match.group(1)
        _, raw = line.split(":", 1)
        values[key] = raw.strip()
    return values


def human_authority_bytes(text: str) -> bytes:
    """Return human-owned Markdown bytes with Knowledge-owned registration fields removed."""
    view = split_frontmatter(text)
    if not view.exists:
        return text.encode("utf-8")

    kept: list[str] = []
    for line in view.lines:
        if line and not line[0].isspace():
            match = _KEY_RE.match(line)
            if match and match.group(1) in AK_KEYS:
                continue
        kept.append(line)

    if not kept:
        return view.body.encode("utf-8")
    return (view.prefix + "".join(kept) + view.closing + view.body).encode("utf-8")


def authority_fingerprint(text: str) -> str:
    return hashlib.sha256(human_authority_bytes(text)).hexdigest()
