from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Mapping, Sequence

from knowledge_core import storage
from knowledge_core.projections import search as search_projection
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.markdown import AK_ID, AK_KIND, AK_LIFECYCLE, AK_STATUS, searchable_text
from knowledge_core.resolution import ResolvedObject, resolve_object, resolve_objects

SCOPE_CURRENT = "current"
SCOPE_MATERIAL = "material"
SCOPE_RETIRED = "retired"
_SUPPORTED_SCOPES = (SCOPE_CURRENT, SCOPE_MATERIAL, SCOPE_RETIRED)


def _normalize_scopes(scopes: Sequence[str] | None) -> tuple[str, ...]:
    requested = tuple(dict.fromkeys(scopes or (SCOPE_CURRENT,)))
    unsupported = [scope for scope in requested if scope not in _SUPPORTED_SCOPES]
    if unsupported:
        raise BootstrapError(
            "Unsupported retrieval scope: "
            + ", ".join(unsupported)
            + "; supported scopes are current, material, and retired"
        )
    if not requested:
        raise BootstrapError("Retrieval scope must not be empty")
    return requested


def _scope_allows(
    conn: sqlite3.Connection,
    obj: ResolvedObject,
    scopes: Sequence[str],
) -> bool:
    if obj.kind == "knowledge_asset":
        lifecycle = storage.get_knowledge_asset_lifecycle(conn, obj.identity)
        if lifecycle is None:
            raise BootstrapError(
                f"Knowledge asset lifecycle does not exist: {obj.identity}"
            )
        if SCOPE_CURRENT in scopes and lifecycle == "current":
            return True
        if SCOPE_RETIRED in scopes and lifecycle == "retired":
            return True
        return False
    if SCOPE_MATERIAL in scopes and obj.kind == "material_record":
        return True
    return False


def _scope_payload(scopes: Sequence[str]) -> list[str]:
    return list(scopes)


def _result(
    obj: ResolvedObject,
    *,
    evidence: str,
    reason: str,
) -> dict[str, object]:
    return {
        "stable_identity": obj.identity,
        "object_kind": obj.kind,
        "canonical_locator": obj.locator,
        "matched_evidence": evidence,
        "retrieval_reason": reason,
        "authority_text": obj.text,
    }


def retrieve_exact(
    vault: Path,
    *,
    identity: str,
    scopes: Sequence[str] | None = None,
) -> dict[str, object]:
    root = _vault_root(vault)
    normalized_scopes = _normalize_scopes(scopes)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")
    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        obj = resolve_object(root, conn, identity)
        if not _scope_allows(conn, obj, normalized_scopes):
            raise BootstrapError(
                f"Knowledge object is outside requested retrieval scope: {identity}"
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "scope": _scope_payload(normalized_scopes),
        "result": _result(
            obj,
            evidence=f"stable identity {identity}",
            reason="exact stable-identity match",
        ),
    }


def retrieve_filter(
    vault: Path,
    *,
    kind: str | None,
    status: str | None,
    properties: Mapping[str, str],
    scopes: Sequence[str] | None = None,
) -> dict[str, object]:
    root = _vault_root(vault)
    normalized_scopes = _normalize_scopes(scopes)
    reserved = {AK_ID, AK_KIND, AK_STATUS, AK_LIFECYCLE}
    conflicting = sorted(reserved.intersection(properties))
    if conflicting:
        raise BootstrapError(
            "Use dedicated identity/kind/status filters for Akira Knowledge-owned properties: "
            + ", ".join(conflicting)
        )
    if status is not None and status not in {"待处理", "已处理"}:
        raise BootstrapError("Material status filter must be 待处理 or 已处理")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    results: list[dict[str, object]] = []
    try:
        storage.initialize_schema(conn)
        conn.commit()
        objects = resolve_objects(root, conn)
        for identity in sorted(objects):
            obj = objects[identity]
            if not _scope_allows(conn, obj, normalized_scopes):
                continue
            if kind is not None and obj.kind != kind:
                continue
            evidence: list[str] = []
            if kind is not None:
                evidence.append(f"object kind={kind}")

            if status is not None:
                if obj.kind != "material_record":
                    continue
                current_status = storage.get_material_status(conn, identity)
                if current_status != status:
                    continue
                evidence.append(f"material status={status}")

            matched = True
            for key, expected in properties.items():
                if obj.properties.get(key) != expected:
                    matched = False
                    break
                evidence.append(f"{key}={expected}")
            if not matched:
                continue
            if not evidence:
                evidence.append("all Knowledge-managed objects")
            results.append(
                _result(
                    obj,
                    evidence="; ".join(evidence),
                    reason="authoritative property filter",
                )
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "scope": _scope_payload(normalized_scopes),
        "results": results,
    }


def _direct_full_text_matches(
    objects: Mapping[str, ResolvedObject],
    query: str,
) -> list[tuple[str, str]]:
    needle = query.casefold()
    matches: list[tuple[str, str]] = []
    for identity, obj in objects.items():
        content = searchable_text(obj.text)
        lowered = content.casefold()
        index = lowered.find(needle)
        if index < 0:
            continue
        start = max(0, index - 60)
        end = min(len(content), index + len(query) + 60)
        evidence = content[start:end].replace("\n", " ").strip()
        matches.append((identity, evidence))
    return matches


def retrieve_full_text(
    vault: Path,
    *,
    query: str,
    scopes: Sequence[str] | None = None,
) -> dict[str, object]:
    root = _vault_root(vault)
    normalized_scopes = _normalize_scopes(scopes)
    if not query.strip():
        raise BootstrapError("Full-text query must not be empty")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    projection_mode = "sqlite-fts5"
    try:
        storage.initialize_schema(conn)
        conn.commit()
        objects = resolve_objects(root, conn)
        documents = [
            (identity, obj.fingerprint, searchable_text(obj.text))
            for identity, obj in sorted(objects.items())
        ]
        desired_state = {identity: fingerprint for identity, fingerprint, _ in documents}
        try:
            search_projection.initialize(conn)
            conn.commit()
            current_state = search_projection.state(conn)
            current_count = search_projection.count(conn)
            if current_state != desired_state or current_count != len(documents):
                with storage.transaction(conn):
                    search_projection.rebuild(conn, documents)
            raw_matches = search_projection.query(conn, query)
        except sqlite3.DatabaseError:
            conn.rollback()
            projection_mode = "authority-scan-fallback"
            raw_matches = _direct_full_text_matches(objects, query)

        results: list[dict[str, object]] = []
        for identity, evidence in raw_matches:
            obj = objects.get(identity)
            if obj is None or not _scope_allows(conn, obj, normalized_scopes):
                continue
            results.append(
                _result(
                    obj,
                    evidence=evidence,
                    reason=(
                        "full-text via rebuildable SQLite FTS5 Projection"
                        if projection_mode == "sqlite-fts5"
                        else "full-text via direct Authority scan fallback"
                    ),
                )
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "query": query,
        "scope": _scope_payload(normalized_scopes),
        "projection_mode": projection_mode,
        "results": results,
    }


def rebuild_full_text_projection(vault: Path) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")
    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        objects = resolve_objects(root, conn)
        documents = [
            (identity, obj.fingerprint, searchable_text(obj.text))
            for identity, obj in sorted(objects.items())
        ]
        try:
            with storage.transaction(conn):
                search_projection.reset(conn)
                search_projection.rebuild(conn, documents)
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            raise BootstrapError(f"SQLite FTS5 Projection cannot be rebuilt: {exc}") from exc
    finally:
        conn.close()
    return {"vault": str(root), "indexed_objects": len(documents)}
