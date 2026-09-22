from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

AK_ID = "akira_knowledge_id"
AK_KIND = "akira_knowledge_kind"
AK_STATUS = "akira_knowledge_status"
AK_LIFECYCLE = "akira_knowledge_lifecycle"
AK_KEYS = (AK_ID, AK_KIND, AK_STATUS, AK_LIFECYCLE)
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


def create_knowledge_asset_markdown(*, identity: str, body: str) -> str:
    return (
        "---\n"
        f"{AK_ID}: {identity}\n"
        "akira_knowledge_kind: knowledge_asset\n"
        "---\n"
        f"{body}"
    )


def set_knowledge_property(text: str, *, key: str, value: str) -> str:
    if key not in AK_KEYS:
        raise MarkdownConflict(f"Property is not owned by Akira Knowledge: {key}")
    view = split_frontmatter(text)
    if not view.exists:
        raise MarkdownConflict("Registered Markdown is missing YAML frontmatter")

    matches: list[int] = []
    for index, line in enumerate(view.lines):
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if match and match.group(1) == key:
            matches.append(index)
    if len(matches) > 1:
        raise MarkdownConflict(
            f"Expected at most one Akira Knowledge property {key}, found {len(matches)}"
        )

    lines = list(view.lines)
    if matches:
        old_line = lines[matches[0]]
        newline = "\r\n" if old_line.endswith("\r\n") else "\n" if old_line.endswith("\n") else ""
        lines[matches[0]] = f"{key}: {value}{newline}"
    else:
        newline = "\r\n" if view.prefix.endswith("\r\n") else "\n"
        lines.append(f"{key}: {value}{newline}")
    return view.prefix + "".join(lines) + view.closing + view.body


def replace_knowledge_property(text: str, *, key: str, value: str) -> str:
    view = split_frontmatter(text)
    if not view.exists:
        raise MarkdownConflict("Registered Markdown is missing YAML frontmatter")
    if key not in top_level_keys(view):
        raise MarkdownConflict(f"Expected exactly one Akira Knowledge property {key}, found 0")
    return set_knowledge_property(text, key=key, value=value)


def replace_human_body(text: str, *, body: str) -> str:
    view = split_frontmatter(text)
    if not view.exists:
        return body
    return view.prefix + "".join(view.lines) + view.closing + body


def set_user_property(text: str, *, key: str, value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise MarkdownConflict(f"Unsupported user Property key: {key}")
    if key in AK_KEYS:
        raise MarkdownConflict(
            f"Akira Knowledge-owned Property must not use human Authority edit: {key}"
        )
    if "\n" in value or "\r" in value:
        raise MarkdownConflict("User Property value must be a single line")

    view = split_frontmatter(text)
    if not view.exists:
        raise MarkdownConflict("Registered Markdown is missing YAML frontmatter")

    matches: list[int] = []
    for index, line in enumerate(view.lines):
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if match and match.group(1) == key:
            matches.append(index)
    if len(matches) > 1:
        raise MarkdownConflict(
            f"Expected at most one user Property {key}, found {len(matches)}"
        )

    lines = list(view.lines)
    if matches:
        old_line = lines[matches[0]]
        newline = (
            "\r\n"
            if old_line.endswith("\r\n")
            else "\n"
            if old_line.endswith("\n")
            else ""
        )
        lines[matches[0]] = f"{key}: {value}{newline}"
    else:
        newline = "\r\n" if view.prefix.endswith("\r\n") else "\n"
        lines.append(f"{key}: {value}{newline}")
    return view.prefix + "".join(lines) + view.closing + view.body


def replace_wikilink_target(
    text: str,
    *,
    old_target: str,
    new_target: str,
) -> tuple[str, int]:
    old_target = old_target.strip()
    new_target = new_target.strip()
    if not old_target or not new_target:
        raise MarkdownConflict("Wikilink replacement targets must not be empty")
    for value in (old_target, new_target):
        if any(token in value for token in ("[[", "]]", "\n", "\r")):
            raise MarkdownConflict("Unsupported wikilink replacement target")

    view = split_frontmatter(text)
    pattern = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")
    replacements = 0

    def replace_match(match: re.Match[str]) -> str:
        nonlocal replacements
        inside = match.group(1)
        target, separator, alias = inside.partition("|")
        normalized_target = target.strip()

        replacement_target: str | None = None
        if normalized_target == old_target:
            replacement_target = new_target
        else:
            marker_positions = [
                position
                for token in ("#", "^")
                if (position := normalized_target.find(token)) > 0
            ]
            if marker_positions:
                marker_index = min(marker_positions)
                base_target = normalized_target[:marker_index].strip()
                target_suffix = normalized_target[marker_index:]
                if base_target == old_target:
                    replacement_target = (
                        new_target
                        if any(token in new_target for token in ("#", "^"))
                        else new_target + target_suffix
                    )

        if replacement_target is None:
            return match.group(0)

        replacements += 1
        alias_suffix = f"|{alias}" if separator else ""
        return f"[[{replacement_target}{alias_suffix}]]"

    body = pattern.sub(replace_match, view.body)
    if replacements == 0:
        raise MarkdownConflict(
            f"Wikilink target was not found in human Authority: {old_target}"
        )
    if not view.exists:
        return body, replacements
    return view.prefix + "".join(view.lines) + view.closing + body, replacements


def top_level_properties(text: str) -> dict[str, str]:
    view = split_frontmatter(text)
    values: dict[str, str] = {}
    for line in view.lines:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in values:
            raise MarkdownConflict(f"Duplicate top-level YAML property: {key}")
        _, raw = line.split(":", 1)
        values[key] = raw.strip()
    return values


def searchable_text(text: str) -> str:
    return human_authority_bytes(text).decode("utf-8")


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
