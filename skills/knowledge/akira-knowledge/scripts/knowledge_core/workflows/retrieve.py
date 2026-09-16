from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Mapping

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.markdown import AK_ID, AK_KIND, AK_STATUS, searchable_text
from knowledge_core.resolution import ResolvedObject, resolve_object, resolve_objects


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


def retrieve_exact(vault: Path, *, identity: str) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")
    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        obj = resolve_object(root, conn, identity)
    finally:
        conn.close()

    return {
        "vault": str(root),
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
) -> dict[str, object]:
    root = _vault_root(vault)
    reserved = {AK_ID, AK_KIND, AK_STATUS}
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

    return {"vault": str(root), "results": results}


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


def retrieve_full_text(vault: Path, *, query: str) -> dict[str, object]:
    root = _vault_root(vault)
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
            storage.initialize_search_projection(conn)
            conn.commit()
            current_state = storage.search_projection_state(conn)
            current_count = storage.search_projection_count(conn)
            if current_state != desired_state or current_count != len(documents):
                with storage.transaction(conn):
                    storage.rebuild_search_projection(conn, documents)
            raw_matches = storage.query_search_projection(conn, query)
        except sqlite3.DatabaseError:
            conn.rollback()
            projection_mode = "authority-scan-fallback"
            raw_matches = _direct_full_text_matches(objects, query)

        results: list[dict[str, object]] = []
        for identity, evidence in raw_matches:
            obj = objects.get(identity)
            if obj is None:
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
                storage.reset_search_projection(conn)
                storage.rebuild_search_projection(conn, documents)
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            raise BootstrapError(f"SQLite FTS5 Projection cannot be rebuilt: {exc}") from exc
    finally:
        conn.close()
    return {"vault": str(root), "indexed_objects": len(documents)}
