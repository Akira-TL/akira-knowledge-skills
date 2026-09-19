from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Mapping

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _safe_relative
from knowledge_core.markdown import (
    AK_ID,
    AK_KIND,
    AK_LIFECYCLE,
    MarkdownConflict,
    authority_fingerprint,
    top_level_properties,
)


@dataclass(frozen=True)
class ResolvedObject:
    identity: str
    kind: str
    locator: str
    text: str
    properties: Mapping[str, str]
    fingerprint: str


def managed_markdown_paths(root: Path) -> list[Path]:
    config = storage.read_config(root)
    if config is None:
        raise BootstrapError("Vault is not bootstrapped")
    scopes = config.get("managed_scopes")
    if not isinstance(scopes, list) or not scopes or not all(isinstance(item, str) for item in scopes):
        raise BootstrapError("Akira Knowledge config has invalid management scopes")

    paths: set[Path] = set()
    for scope in scopes:
        _relative, resolved = _safe_relative(root, scope, must_exist=True)
        if resolved.is_file():
            if resolved.suffix.lower() == ".md" and not resolved.is_symlink():
                paths.add(resolved)
            continue
        if not resolved.is_dir():
            continue
        for candidate in resolved.rglob("*.md"):
            if storage.SYSTEM_DIR in candidate.parts or candidate.is_symlink():
                continue
            paths.add(candidate.resolve())
    return sorted(paths)


def resolve_objects(root: Path, conn: sqlite3.Connection) -> dict[str, ResolvedObject]:
    registry = {record.identity: record for record in storage.list_objects(conn)}
    resolved: dict[str, ResolvedObject] = {}

    for path in managed_markdown_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
            properties = top_level_properties(text)
        except (OSError, UnicodeError, MarkdownConflict) as exc:
            raise BootstrapError(f"Cannot safely read managed Markdown {path}: {exc}") from exc

        identity = properties.get(AK_ID)
        if identity is None or identity not in registry:
            continue
        record = registry[identity]
        kind = properties.get(AK_KIND)
        if kind != record.kind:
            raise BootstrapError(
                f"Managed Markdown object kind disagrees with registry: {path.relative_to(root)}"
            )
        if record.kind == "knowledge_asset":
            lifecycle = storage.get_knowledge_asset_lifecycle(conn, identity)
            if lifecycle is None:
                raise BootstrapError(
                    f"Knowledge asset lifecycle is missing from structured Authority: {identity}"
                )
            lifecycle_mirror = properties.get(AK_LIFECYCLE)
            if lifecycle == "current":
                if lifecycle_mirror not in {None, "current"}:
                    raise BootstrapError(
                        "Knowledge lifecycle Property disagrees with structured Authority: "
                        f"{path.relative_to(root)}"
                    )
            elif lifecycle_mirror != lifecycle:
                raise BootstrapError(
                    "Knowledge lifecycle Property disagrees with structured Authority: "
                    f"{path.relative_to(root)}"
                )
        if identity in resolved:
            raise BootstrapError(f"Duplicate stable identity found in managed Vault: {identity}")
        locator = path.relative_to(root).as_posix()
        resolved[identity] = ResolvedObject(
            identity=identity,
            kind=record.kind,
            locator=locator,
            text=text,
            properties=properties,
            fingerprint=authority_fingerprint(text),
        )
    return resolved


def resolve_object(
    root: Path,
    conn: sqlite3.Connection,
    identity: str,
) -> ResolvedObject:
    record = storage.get_by_identity(conn, identity)
    if record is None:
        raise BootstrapError(f"Knowledge object does not exist: {identity}")
    obj = resolve_objects(root, conn).get(identity)
    if obj is None:
        raise BootstrapError(
            f"Current canonical Markdown cannot be resolved inside managed scopes: {identity}"
        )
    return obj
