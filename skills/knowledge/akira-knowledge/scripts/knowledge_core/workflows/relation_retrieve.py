from __future__ import annotations

from pathlib import Path
from typing import Sequence

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.resolution import resolve_object, resolve_objects
from knowledge_core.workflows.retrieve import _normalize_scopes, _result, _scope_allows


def retrieve_relation_expansion(
    vault: Path,
    *,
    seed_identity: str,
    direction: str,
    relation_type: str | None,
    scopes: Sequence[str] | None,
) -> dict[str, object]:
    root = _vault_root(vault)
    normalized_scopes = _normalize_scopes(scopes)
    if direction not in {"outgoing", "incoming"}:
        raise BootstrapError("Relation direction must be outgoing or incoming")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        seed = resolve_object(root, conn, seed_identity)
        if not _scope_allows(seed, normalized_scopes):
            raise BootstrapError(
                f"Relation seed is outside requested retrieval scope: {seed_identity}"
            )

        objects = resolve_objects(root, conn)
        relations = storage.list_relation_neighbors(
            conn,
            seed_ref=seed_identity,
            direction=direction,
            relation_type=relation_type,
        )

        results: list[dict[str, object]] = []
        traversed_relations: list[dict[str, object]] = []
        for relation in relations:
            neighbor_identity = (
                relation.target_ref if direction == "outgoing" else relation.source_ref
            )
            neighbor = objects.get(neighbor_identity)
            if neighbor is None or not _scope_allows(neighbor, normalized_scopes):
                continue

            evidence = (
                f"relation {relation.identity}: "
                f"{relation.source_ref} -[{relation.relation_type}]-> {relation.target_ref}; "
                f"provenance={relation.provenance}"
            )
            reason = (
                f"accepted typed relation {direction} expansion "
                f"via {relation.relation_type}"
            )
            item = _result(
                neighbor,
                evidence=evidence,
                reason=reason,
            )
            item["relation"] = {
                "identity": relation.identity,
                "source": relation.source_ref,
                "type": relation.relation_type,
                "target": relation.target_ref,
                "provenance": relation.provenance,
                "revision": relation.revision,
                "direction": direction,
            }
            results.append(item)
            traversed_relations.append(item["relation"])

    finally:
        conn.close()

    return {
        "vault": str(root),
        "scope": list(normalized_scopes),
        "seed_identity": seed_identity,
        "direction": direction,
        "relation_type": relation_type,
        "relations": traversed_relations,
        "results": results,
    }
