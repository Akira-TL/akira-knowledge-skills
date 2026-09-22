from __future__ import annotations

from pathlib import PurePosixPath
import re
from pathlib import Path

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.markdown import split_frontmatter
from knowledge_core.persistence import lifecycle as lifecycle_store
from knowledge_core.persistence import relations as relation_store
from knowledge_core.resolution import ResolvedObject, resolve_objects

_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")


def _wikilink_targets(text: str) -> list[tuple[str, str]]:
    body = split_frontmatter(text).body
    links: list[tuple[str, str]] = []
    for match in _WIKILINK_RE.finditer(body):
        raw = match.group(0)
        target = match.group(1)
        target = target.split("|", 1)[0]
        target = target.split("#", 1)[0]
        target = target.split("^", 1)[0]
        target = target.strip()
        if target:
            links.append((raw, target))
    return links


def _locator_key(locator: str) -> str:
    path = PurePosixPath(locator)
    if path.suffix.lower() == ".md":
        path = path.with_suffix("")
    return path.as_posix()


def _reference_candidates(
    reference: str,
    *,
    by_locator: dict[str, str],
    by_suffix: dict[str, set[str]],
    by_stem: dict[str, set[str]],
) -> set[str]:
    normalized = reference.replace("\\", "/").strip("/")
    if normalized.lower().endswith(".md"):
        normalized = normalized[:-3]
    candidates: set[str] = set()

    exact = by_locator.get(normalized)
    if exact is not None:
        candidates.add(exact)

    for identity in by_suffix.get(normalized, set()):
        candidates.add(identity)

    if "/" not in normalized:
        for identity in by_stem.get(normalized, set()):
            candidates.add(identity)

    return candidates


def scan_network_health(vault: Path) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        objects = resolve_objects(root, conn)
        current: dict[str, ResolvedObject] = {}
        for identity, obj in objects.items():
            if obj.kind != "knowledge_asset":
                continue
            lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(conn, identity)
            if lifecycle == "current":
                current[identity] = obj

        by_locator: dict[str, str] = {}
        by_suffix: dict[str, set[str]] = {}
        by_stem: dict[str, set[str]] = {}
        for identity, obj in current.items():
            key = _locator_key(obj.locator)
            by_locator[key] = identity
            parts = PurePosixPath(key).parts
            for index in range(len(parts)):
                suffix = PurePosixPath(*parts[index:]).as_posix()
                by_suffix.setdefault(suffix, set()).add(identity)
            by_stem.setdefault(PurePosixPath(key).name, set()).add(identity)

        outgoing: dict[str, set[str]] = {identity: set() for identity in current}
        incoming: dict[str, set[str]] = {identity: set() for identity in current}
        unresolved: list[dict[str, object]] = []

        for source_identity, obj in current.items():
            for raw, reference in _wikilink_targets(obj.text):
                candidates = _reference_candidates(
                    reference,
                    by_locator=by_locator,
                    by_suffix=by_suffix,
                    by_stem=by_stem,
                )
                if len(candidates) > 1:
                    raise BootstrapError(
                        "Ambiguous local Knowledge reference "
                        f"{raw} from {obj.locator}: "
                        + ", ".join(
                            sorted(current[item].locator for item in candidates)
                        )
                    )
                if not candidates:
                    unresolved.append(
                        {
                            "source_identity": source_identity,
                            "source_locator": obj.locator,
                            "reference": reference,
                            "evidence": raw,
                        }
                    )
                    continue
                target_identity = next(iter(candidates))
                if target_identity == source_identity:
                    continue
                outgoing[source_identity].add(target_identity)
                incoming[target_identity].add(source_identity)

        relations = relation_store.list_active_relation_records(conn)
        active_relation_count = len(relations)
        for relation in relations:
            if relation.source_ref not in current or relation.target_ref not in current:
                continue
            if relation.source_ref == relation.target_ref:
                continue
            outgoing[relation.source_ref].add(relation.target_ref)
            incoming[relation.target_ref].add(relation.source_ref)

        orphan = [
            {
                "identity": identity,
                "canonical_locator": current[identity].locator,
                "incoming_count": 0,
                "outgoing_count": 0,
            }
            for identity in sorted(current)
            if not incoming[identity] and not outgoing[identity]
        ]
        dead_end = [
            {
                "identity": identity,
                "canonical_locator": current[identity].locator,
                "incoming_from": sorted(incoming[identity]),
                "outgoing_count": 0,
            }
            for identity in sorted(current)
            if incoming[identity] and not outgoing[identity]
        ]

        unresolved.sort(
            key=lambda item: (
                str(item["source_locator"]),
                str(item["reference"]),
                str(item["evidence"]),
            )
        )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "diagnostic_kind": "knowledge_network_health",
        "current_knowledge_count": len(current),
        "active_relation_count": active_relation_count,
        "orphan": orphan,
        "unresolved": unresolved,
        "dead_end": dead_end,
    }
