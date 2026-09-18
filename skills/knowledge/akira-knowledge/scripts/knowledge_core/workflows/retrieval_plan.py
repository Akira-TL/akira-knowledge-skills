from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from knowledge_core.common import BootstrapError
from knowledge_core.workflows.relation_retrieve import retrieve_relation_expansion
from knowledge_core.workflows.retrieve import (
    _normalize_scopes,
    retrieve_exact,
    retrieve_filter,
    retrieve_full_text,
)


@dataclass(frozen=True)
class RetrievalMatch:
    path: str
    matched_evidence: str
    retrieval_reason: str
    relation: Mapping[str, object] | None = None


@dataclass
class AggregatedResult:
    stable_identity: str
    object_kind: str
    canonical_locator: str
    authority_text: str
    matches: list[RetrievalMatch]


def _append_results(
    aggregated: dict[str, AggregatedResult],
    *,
    path: str,
    results: Sequence[Mapping[str, object]],
) -> None:
    for item in results:
        identity = str(item["stable_identity"])
        kind = str(item["object_kind"])
        locator = str(item["canonical_locator"])
        authority_text = str(item["authority_text"])
        evidence = str(item["matched_evidence"])
        reason = str(item["retrieval_reason"])

        existing = aggregated.get(identity)
        if existing is None:
            existing = AggregatedResult(
                stable_identity=identity,
                object_kind=kind,
                canonical_locator=locator,
                authority_text=authority_text,
                matches=[],
            )
            aggregated[identity] = existing
        elif (
            existing.object_kind != kind
            or existing.canonical_locator != locator
            or existing.authority_text != authority_text
        ):
            raise BootstrapError(
                f"Retrieval paths disagree about current Authority for stable identity: {identity}"
            )

        relation = item.get("relation")
        if relation is not None and not isinstance(relation, Mapping):
            raise BootstrapError("Relation retrieval result has invalid relation metadata")
        match = RetrievalMatch(
            path=path,
            matched_evidence=evidence,
            retrieval_reason=reason,
            relation=relation,
        )
        if match not in existing.matches:
            existing.matches.append(match)


def retrieve_task_package(
    vault: Path,
    *,
    task: str,
    scopes: Sequence[str] | None,
    exact_identities: Sequence[str],
    full_text_queries: Sequence[str],
    filter_kind: str | None,
    filter_status: str | None,
    filter_properties: Mapping[str, str],
    relation_seeds: Sequence[str],
    relation_direction: str | None,
    relation_type: str | None,
) -> dict[str, object]:
    if not task.strip():
        raise BootstrapError("Task-related retrieval requires a non-empty task description")

    normalized_scopes = _normalize_scopes(scopes)
    exact_identities = tuple(dict.fromkeys(exact_identities))
    full_text_queries = tuple(dict.fromkeys(full_text_queries))
    use_filter = (
        filter_kind is not None
        or filter_status is not None
        or bool(filter_properties)
    )
    relation_seeds = tuple(dict.fromkeys(relation_seeds))
    if relation_seeds and relation_direction is None:
        raise BootstrapError("Relation retrieval path requires an explicit direction")
    if relation_direction is not None and not relation_seeds:
        raise BootstrapError("Relation direction requires at least one relation seed")

    paths: list[dict[str, object]] = []
    aggregated: dict[str, AggregatedResult] = {}

    for identity in exact_identities:
        payload = retrieve_exact(
            vault,
            identity=identity,
            scopes=normalized_scopes,
        )
        paths.append({"type": "exact", "identity": identity})
        _append_results(
            aggregated,
            path="exact",
            results=[payload["result"]],
        )

    if use_filter:
        payload = retrieve_filter(
            vault,
            kind=filter_kind,
            status=filter_status,
            properties=filter_properties,
            scopes=normalized_scopes,
        )
        paths.append(
            {
                "type": "filter",
                "kind": filter_kind,
                "status": filter_status,
                "properties": dict(filter_properties),
            }
        )
        _append_results(
            aggregated,
            path="filter",
            results=payload["results"],
        )

    for query in full_text_queries:
        if not query.strip():
            raise BootstrapError("Task-related full-text query must not be empty")
        payload = retrieve_full_text(
            vault,
            query=query,
            scopes=normalized_scopes,
        )
        paths.append({"type": "full_text", "query": query})
        _append_results(
            aggregated,
            path="full_text",
            results=payload["results"],
        )

    for seed_identity in relation_seeds:
        payload = retrieve_relation_expansion(
            vault,
            seed_identity=seed_identity,
            direction=str(relation_direction),
            relation_type=relation_type,
            scopes=normalized_scopes,
        )
        paths.append(
            {
                "type": "relation",
                "seed_identity": seed_identity,
                "direction": relation_direction,
                "relation_type": relation_type,
            }
        )
        _append_results(
            aggregated,
            path="relation",
            results=payload["results"],
        )

    if not paths:
        raise BootstrapError(
            "Retrieval plan must contain at least one exact, filter, or full-text path"
        )

    results: list[dict[str, object]] = []
    for identity in sorted(aggregated):
        item = aggregated[identity]
        results.append(
            {
                "stable_identity": item.stable_identity,
                "object_kind": item.object_kind,
                "canonical_locator": item.canonical_locator,
                "matched_evidence": [
                    match.matched_evidence for match in item.matches
                ],
                "retrieval_reason": [
                    match.retrieval_reason for match in item.matches
                ],
                "retrieval_paths": [match.path for match in item.matches],
                "matches": [
                    {
                        "path": match.path,
                        "matched_evidence": match.matched_evidence,
                        "retrieval_reason": match.retrieval_reason,
                        **({"relation": dict(match.relation)} if match.relation is not None else {}),
                    }
                    for match in item.matches
                ],
                "authority_text": item.authority_text,
            }
        )

    return {
        "vault": str(vault.expanduser().resolve()),
        "task": task,
        "scope": list(normalized_scopes),
        "retrieval_plan": {
            "scope": list(normalized_scopes),
            "paths": paths,
        },
        "results": results,
    }
