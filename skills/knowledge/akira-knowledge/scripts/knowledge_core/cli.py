from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from knowledge_core.service import (
    BootstrapError,
    apply_retire_proposal,
    apply_supersede_proposal,
    apply_update_proposal,
    approve_curate_proposal,
    approve_relation_candidate,
    capture_material,
    create_curate_proposal,
    create_retire_proposal,
    create_supersede_proposal,
    create_relation_candidate,
    inspect_conflict_candidate,
    inspect_relation_candidate,
    inspect_relation_maintenance_candidate,
    inspect_review_candidate,
    inspect_vault,
    plan_source_review,
    propose_conflict,
    propose_relation_maintenance,
    rebuild_dynamic_views,
    rebuild_relation_graph,
    rebuild_full_text_projection,
    register_notes,
    reject_curate_proposal,
    reject_conflict_candidate,
    reject_relation_candidate,
    reject_relation_maintenance_candidate,
    reject_review_candidate,
    retrieve_exact,
    retrieve_filter,
    retrieve_full_text,
    retrieve_task_package,
    review_source,
    revoke_relation,
    synchronize_object,
)
from knowledge_core.storage import StorageError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="akira-knowledge-store")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Read-only Vault inventory")
    inspect_parser.add_argument("--vault", required=True, type=Path)

    register_parser = subparsers.add_parser(
        "register", help="Register explicitly approved existing Markdown in-place"
    )
    register_parser.add_argument("--vault", required=True, type=Path)
    register_parser.add_argument("--scope", action="append", required=True)
    register_parser.add_argument("--note", action="append", required=True)
    register_parser.add_argument("--default-write-root", required=True)
    register_parser.add_argument("--kind", default="knowledge_asset")

    capture_parser = subparsers.add_parser(
        "capture", help="Create one Material Record after explicit persistent intent"
    )
    capture_parser.add_argument("--vault", required=True, type=Path)
    capture_parser.add_argument("--note")
    capture_parser.add_argument("--note-file", type=Path)
    capture_parser.add_argument("--source", action="append", default=[])
    capture_parser.add_argument("--confirmed-intent", action="store_true")

    propose_parser = subparsers.add_parser(
        "curate-propose", help="Persist a candidate knowledge change without modifying Authority"
    )
    propose_parser.add_argument("--vault", required=True, type=Path)
    propose_parser.add_argument("--material-id", action="append", required=True)
    propose_parser.add_argument("--body")
    propose_parser.add_argument("--body-file", type=Path)
    propose_parser.add_argument("--target-id")
    propose_parser.add_argument("--base-revision", type=int)

    approve_parser = subparsers.add_parser(
        "curate-approve", help="Apply an explicitly approved create proposal"
    )
    approve_parser.add_argument("--vault", required=True, type=Path)
    approve_parser.add_argument("--proposal-id", required=True)
    approve_parser.add_argument("--confirmed-approval", action="store_true")

    reject_parser = subparsers.add_parser(
        "curate-reject", help="Reject a pending proposal without modifying Authority"
    )
    reject_parser.add_argument("--vault", required=True, type=Path)
    reject_parser.add_argument("--proposal-id", required=True)
    reject_parser.add_argument("--confirmed-rejection", action="store_true")

    relation_propose_parser = subparsers.add_parser(
        "relation-propose", help="Persist a Relation Candidate without creating Relation Authority"
    )
    relation_propose_parser.add_argument("--vault", required=True, type=Path)
    source_group = relation_propose_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-id")
    source_group.add_argument("--source-external")
    relation_propose_parser.add_argument("--type", required=True)
    target_group = relation_propose_parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--target-id")
    target_group.add_argument("--target-external")
    relation_propose_parser.add_argument("--provenance", required=True)

    relation_inspect_parser = subparsers.add_parser(
        "relation-inspect", help="Revalidate and inspect one Relation Candidate"
    )
    relation_inspect_parser.add_argument("--vault", required=True, type=Path)
    relation_inspect_parser.add_argument("--candidate-id", required=True)

    relation_approve_parser = subparsers.add_parser(
        "relation-approve", help="Approve a pending Relation Candidate into Relation Authority"
    )
    relation_approve_parser.add_argument("--vault", required=True, type=Path)
    relation_approve_parser.add_argument("--candidate-id", required=True)
    relation_approve_parser.add_argument("--confirmed-approval", action="store_true")

    relation_reject_parser = subparsers.add_parser(
        "relation-reject", help="Reject a pending Relation Candidate"
    )
    relation_reject_parser.add_argument("--vault", required=True, type=Path)
    relation_reject_parser.add_argument("--candidate-id", required=True)
    relation_reject_parser.add_argument("--confirmed-rejection", action="store_true")

    exact_parser = subparsers.add_parser(
        "retrieve-exact", help="Read one current Knowledge object by stable identity"
    )
    exact_parser.add_argument("--vault", required=True, type=Path)
    exact_parser.add_argument("--identity", required=True)
    exact_parser.add_argument(
        "--scope",
        action="append",
        help="Retrieval scope; repeat to combine current, material, retired, and superseded. Defaults to current.",
    )

    filter_parser = subparsers.add_parser(
        "retrieve-filter", help="Filter current Knowledge objects by authoritative properties"
    )
    filter_parser.add_argument("--vault", required=True, type=Path)
    filter_parser.add_argument("--kind")
    filter_parser.add_argument("--status")
    filter_parser.add_argument(
        "--scope",
        action="append",
        help="Retrieval scope; repeat to combine current, material, retired, and superseded. Defaults to current.",
    )
    filter_parser.add_argument(
        "--property",
        action="append",
        default=[],
        help="Top-level Authority property filter as key=value",
    )

    full_text_parser = subparsers.add_parser(
        "retrieve-full-text", help="Search current Knowledge Markdown with a rebuildable FTS Projection"
    )
    full_text_parser.add_argument("--vault", required=True, type=Path)
    full_text_parser.add_argument("--query", required=True)
    full_text_parser.add_argument(
        "--scope",
        action="append",
        help="Retrieval scope; repeat to combine current, material, retired, and superseded. Defaults to current.",
    )

    task_parser = subparsers.add_parser(
        "retrieve-task", help="Execute an explicit task-related Retrieval Plan"
    )
    task_parser.add_argument("--vault", required=True, type=Path)
    task_parser.add_argument("--task", required=True)
    task_parser.add_argument(
        "--scope",
        action="append",
        help="Retrieval scope; repeat to combine current, material, retired, and superseded. Defaults to current.",
    )
    task_parser.add_argument("--exact", action="append", default=[])
    task_parser.add_argument("--query", action="append", default=[])
    task_parser.add_argument("--kind")
    task_parser.add_argument("--status")
    task_parser.add_argument("--relation-seed", action="append", default=[])
    task_parser.add_argument("--relation-direction", choices=("outgoing", "incoming"))
    task_parser.add_argument("--relation-type")
    task_parser.add_argument(
        "--property",
        action="append",
        default=[],
        help="Filter-path top-level Authority property as key=value",
    )

    rebuild_parser = subparsers.add_parser(
        "retrieve-rebuild-index", help="Explicitly rebuild the full-text search Projection"
    )
    rebuild_parser.add_argument("--vault", required=True, type=Path)

    views_parser = subparsers.add_parser(
        "views-rebuild", help="Rebuild Akira Knowledge Obsidian Bases Projection"
    )
    views_parser.add_argument("--vault", required=True, type=Path)

    graph_parser = subparsers.add_parser(
        "relation-graph-rebuild", help="Rebuild active Relation Record Graph Projection"
    )
    graph_parser.add_argument("--vault", required=True, type=Path)

    sync_parser = subparsers.add_parser(
        "maintain-sync", help="Synchronize current locator/fingerprint into the revision ledger"
    )
    sync_parser.add_argument("--vault", required=True, type=Path)
    sync_parser.add_argument("--identity", required=True)

    update_parser = subparsers.add_parser(
        "maintain-apply-update", help="Apply an approved update proposal with revision protection"
    )
    update_parser.add_argument("--vault", required=True, type=Path)
    update_parser.add_argument("--proposal-id", required=True)
    update_parser.add_argument("--confirmed-approval", action="store_true")

    retire_propose_parser = subparsers.add_parser(
        "maintain-propose-retire",
        help="Create a revision-bound proposal to retire one current Knowledge Asset",
    )
    retire_propose_parser.add_argument("--vault", required=True, type=Path)
    retire_propose_parser.add_argument("--identity", required=True)
    retire_propose_parser.add_argument("--base-revision", required=True, type=int)
    retire_propose_parser.add_argument("--reason", required=True)

    retire_apply_parser = subparsers.add_parser(
        "maintain-apply-retire",
        help="Apply an explicitly approved Knowledge Asset retire proposal",
    )
    retire_apply_parser.add_argument("--vault", required=True, type=Path)
    retire_apply_parser.add_argument("--proposal-id", required=True)
    retire_apply_parser.add_argument("--confirmed-approval", action="store_true")

    supersede_propose_parser = subparsers.add_parser(
        "maintain-propose-supersede",
        help="Create a revision-bound proposal to supersede one current Knowledge Asset",
    )
    supersede_propose_parser.add_argument("--vault", required=True, type=Path)
    supersede_propose_parser.add_argument("--identity", required=True)
    supersede_propose_parser.add_argument("--base-revision", required=True, type=int)
    supersede_propose_parser.add_argument("--replacement-id", required=True)
    supersede_propose_parser.add_argument("--replacement-revision", required=True, type=int)
    supersede_propose_parser.add_argument("--reason", required=True)

    supersede_apply_parser = subparsers.add_parser(
        "maintain-apply-supersede",
        help="Apply an explicitly approved Knowledge Asset supersede proposal",
    )
    supersede_apply_parser.add_argument("--vault", required=True, type=Path)
    supersede_apply_parser.add_argument("--proposal-id", required=True)
    supersede_apply_parser.add_argument("--confirmed-approval", action="store_true")

    conflict_parser = subparsers.add_parser(
        "maintain-propose-conflict",
        help="Create a basis-bound semantic conflict candidate without modifying Authority",
    )
    conflict_parser.add_argument("--vault", required=True, type=Path)
    conflict_parser.add_argument("--knowledge-id", action="append", default=[])
    conflict_parser.add_argument("--source-finding-id", action="append", default=[])
    conflict_parser.add_argument("--relation-id", action="append", default=[])
    conflict_parser.add_argument("--conflict", required=True)
    conflict_parser.add_argument("--evidence", required=True)

    conflict_inspect_parser = subparsers.add_parser(
        "maintain-inspect-conflict",
        help="Revalidate and inspect one semantic conflict candidate",
    )
    conflict_inspect_parser.add_argument("--vault", required=True, type=Path)
    conflict_inspect_parser.add_argument("--candidate-id", required=True)

    conflict_reject_parser = subparsers.add_parser(
        "maintain-reject-conflict",
        help="Reject a pending or stale semantic conflict candidate",
    )
    conflict_reject_parser.add_argument("--vault", required=True, type=Path)
    conflict_reject_parser.add_argument("--candidate-id", required=True)
    conflict_reject_parser.add_argument("--confirmed-rejection", action="store_true")

    relation_maintenance_parser = subparsers.add_parser(
        "maintain-propose-relation-maintenance",
        help="Create a basis-bound stale/conflict candidate for one active Relation Record",
    )
    relation_maintenance_parser.add_argument("--vault", required=True, type=Path)
    relation_maintenance_parser.add_argument("--relation-id", required=True)
    relation_maintenance_parser.add_argument(
        "--kind",
        required=True,
        choices=("relation_stale", "relation_conflict"),
    )
    relation_maintenance_parser.add_argument("--source-finding-id")
    relation_maintenance_parser.add_argument("--evidence", required=True)

    relation_maintenance_inspect_parser = subparsers.add_parser(
        "maintain-inspect-relation-maintenance",
        help="Revalidate one Relation maintenance candidate",
    )
    relation_maintenance_inspect_parser.add_argument("--vault", required=True, type=Path)
    relation_maintenance_inspect_parser.add_argument("--candidate-id", required=True)

    relation_maintenance_reject_parser = subparsers.add_parser(
        "maintain-reject-relation-maintenance",
        help="Reject a pending or stale Relation maintenance candidate",
    )
    relation_maintenance_reject_parser.add_argument("--vault", required=True, type=Path)
    relation_maintenance_reject_parser.add_argument("--candidate-id", required=True)
    relation_maintenance_reject_parser.add_argument(
        "--confirmed-rejection", action="store_true"
    )

    review_plan_parser = subparsers.add_parser(
        "maintain-review-plan",
        help="List provenance Sources that should be verified for one current Knowledge Asset",
    )
    review_plan_parser.add_argument("--vault", required=True, type=Path)
    review_plan_parser.add_argument("--identity", required=True)

    review_source_parser = subparsers.add_parser(
        "maintain-review-source",
        help="Record one verified Source review and create a stale maintenance candidate when changed",
    )
    review_source_parser.add_argument("--vault", required=True, type=Path)
    review_source_parser.add_argument("--identity", required=True)
    review_source_parser.add_argument("--source", required=True)
    review_source_parser.add_argument("--basis-source-id")
    review_source_parser.add_argument("--basis-revision")
    review_source_parser.add_argument("--basis-fingerprint")
    review_source_parser.add_argument("--unknown", action="store_true")
    review_source_parser.add_argument("--observed-source-id")
    review_source_parser.add_argument("--observed-revision")
    review_source_parser.add_argument("--observed-fingerprint")
    review_source_parser.add_argument("--evidence", required=True)

    review_inspect_parser = subparsers.add_parser(
        "maintain-inspect-review-candidate",
        help="Revalidate and inspect one maintenance candidate",
    )
    review_inspect_parser.add_argument("--vault", required=True, type=Path)
    review_inspect_parser.add_argument("--candidate-id", required=True)

    review_reject_parser = subparsers.add_parser(
        "maintain-reject-review-candidate",
        help="Reject a pending or stale maintenance candidate",
    )
    review_reject_parser.add_argument("--vault", required=True, type=Path)
    review_reject_parser.add_argument("--candidate-id", required=True)
    review_reject_parser.add_argument("--confirmed-rejection", action="store_true")

    revoke_parser = subparsers.add_parser(
        "relation-revoke", help="Explicitly revoke an active Relation Record"
    )
    revoke_parser.add_argument("--vault", required=True, type=Path)
    revoke_parser.add_argument("--relation-id", required=True)
    revoke_parser.add_argument("--expected-revision", required=True, type=int)
    revoke_parser.add_argument("--confirmed-revoke", action="store_true")
    return parser


def _parse_property_filters(items: list[str]) -> dict[str, str]:
    property_filters: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise BootstrapError("Property filter must use key=value syntax")
        key, value = item.split("=", 1)
        if not key:
            raise BootstrapError("Property filter key must not be empty")
        if key in property_filters:
            raise BootstrapError(f"Duplicate property filter: {key}")
        property_filters[key] = value
    return property_filters


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            payload = inspect_vault(args.vault)
        elif args.command == "register":
            payload = register_notes(
                args.vault,
                scopes=args.scope,
                notes=args.note,
                default_write_root=args.default_write_root,
                kind=args.kind,
            )
        elif args.command == "capture":
            if bool(args.note) == bool(args.note_file):
                raise BootstrapError("Capture requires exactly one of --note or --note-file")
            capture_note = (
                args.note_file.read_text(encoding="utf-8") if args.note_file else args.note
            )
            payload = capture_material(
                args.vault,
                capture_note=capture_note,
                sources=args.source,
                confirmed_intent=args.confirmed_intent,
            )
        elif args.command == "curate-propose":
            if bool(args.body) == bool(args.body_file):
                raise BootstrapError(
                    "Curate proposal requires exactly one of --body or --body-file"
                )
            proposed_body = (
                args.body_file.read_text(encoding="utf-8") if args.body_file else args.body
            )
            payload = create_curate_proposal(
                args.vault,
                proposed_body=proposed_body,
                material_ids=args.material_id,
                target_identity=args.target_id,
                expected_base_revision=args.base_revision,
            )
        elif args.command == "curate-approve":
            payload = approve_curate_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_approval=args.confirmed_approval,
            )
        elif args.command == "curate-reject":
            payload = reject_curate_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_rejection=args.confirmed_rejection,
            )
        elif args.command == "relation-propose":
            payload = create_relation_candidate(
                args.vault,
                source_identity=args.source_id,
                source_external=args.source_external,
                relation_type=args.type,
                target_identity=args.target_id,
                target_external=args.target_external,
                provenance=args.provenance,
            )
        elif args.command == "relation-inspect":
            payload = inspect_relation_candidate(
                args.vault,
                candidate_id=args.candidate_id,
            )
        elif args.command == "relation-approve":
            payload = approve_relation_candidate(
                args.vault,
                candidate_id=args.candidate_id,
                confirmed_approval=args.confirmed_approval,
            )
        elif args.command == "relation-reject":
            payload = reject_relation_candidate(
                args.vault,
                candidate_id=args.candidate_id,
                confirmed_rejection=args.confirmed_rejection,
            )
        elif args.command == "retrieve-exact":
            payload = retrieve_exact(
                args.vault,
                identity=args.identity,
                scopes=args.scope,
            )
        elif args.command == "retrieve-filter":
            property_filters = _parse_property_filters(args.property)
            payload = retrieve_filter(
                args.vault,
                kind=args.kind,
                status=args.status,
                properties=property_filters,
                scopes=args.scope,
            )
        elif args.command == "retrieve-full-text":
            payload = retrieve_full_text(
                args.vault,
                query=args.query,
                scopes=args.scope,
            )
        elif args.command == "retrieve-task":
            payload = retrieve_task_package(
                args.vault,
                task=args.task,
                scopes=args.scope,
                exact_identities=args.exact,
                full_text_queries=args.query,
                filter_kind=args.kind,
                filter_status=args.status,
                filter_properties=_parse_property_filters(args.property),
                relation_seeds=args.relation_seed,
                relation_direction=args.relation_direction,
                relation_type=args.relation_type,
            )
        elif args.command == "retrieve-rebuild-index":
            payload = rebuild_full_text_projection(args.vault)
        elif args.command == "views-rebuild":
            payload = rebuild_dynamic_views(args.vault)
        elif args.command == "relation-graph-rebuild":
            payload = rebuild_relation_graph(args.vault)
        elif args.command == "maintain-sync":
            payload = synchronize_object(args.vault, identity=args.identity)
        elif args.command == "maintain-apply-update":
            payload = apply_update_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_approval=args.confirmed_approval,
            )
        elif args.command == "maintain-propose-retire":
            payload = create_retire_proposal(
                args.vault,
                identity=args.identity,
                expected_base_revision=args.base_revision,
                reason=args.reason,
            )
        elif args.command == "maintain-apply-retire":
            payload = apply_retire_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_approval=args.confirmed_approval,
            )
        elif args.command == "maintain-propose-supersede":
            payload = create_supersede_proposal(
                args.vault,
                identity=args.identity,
                expected_base_revision=args.base_revision,
                replacement_identity=args.replacement_id,
                expected_replacement_revision=args.replacement_revision,
                reason=args.reason,
            )
        elif args.command == "maintain-apply-supersede":
            payload = apply_supersede_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_approval=args.confirmed_approval,
            )
        elif args.command == "maintain-propose-conflict":
            payload = propose_conflict(
                args.vault,
                knowledge_ids=args.knowledge_id,
                source_finding_ids=args.source_finding_id,
                relation_ids=args.relation_id,
                conflict=args.conflict,
                evidence=args.evidence,
            )
        elif args.command == "maintain-inspect-conflict":
            payload = inspect_conflict_candidate(
                args.vault,
                candidate_id=args.candidate_id,
            )
        elif args.command == "maintain-reject-conflict":
            payload = reject_conflict_candidate(
                args.vault,
                candidate_id=args.candidate_id,
                confirmed_rejection=args.confirmed_rejection,
            )
        elif args.command == "maintain-propose-relation-maintenance":
            payload = propose_relation_maintenance(
                args.vault,
                relation_identity=args.relation_id,
                candidate_kind=args.kind,
                source_finding_id=args.source_finding_id,
                evidence=args.evidence,
            )
        elif args.command == "maintain-inspect-relation-maintenance":
            payload = inspect_relation_maintenance_candidate(
                args.vault,
                candidate_id=args.candidate_id,
            )
        elif args.command == "maintain-reject-relation-maintenance":
            payload = reject_relation_maintenance_candidate(
                args.vault,
                candidate_id=args.candidate_id,
                confirmed_rejection=args.confirmed_rejection,
            )
        elif args.command == "maintain-review-plan":
            payload = plan_source_review(
                args.vault,
                identity=args.identity,
            )
        elif args.command == "maintain-review-source":
            payload = review_source(
                args.vault,
                identity=args.identity,
                source_locator=args.source,
                basis_source_id=args.basis_source_id,
                basis_revision=args.basis_revision,
                basis_fingerprint=args.basis_fingerprint,
                unknown=args.unknown,
                observed_source_id=args.observed_source_id,
                observed_revision=args.observed_revision,
                observed_fingerprint=args.observed_fingerprint,
                evidence=args.evidence,
            )
        elif args.command == "maintain-inspect-review-candidate":
            payload = inspect_review_candidate(
                args.vault,
                candidate_id=args.candidate_id,
            )
        elif args.command == "maintain-reject-review-candidate":
            payload = reject_review_candidate(
                args.vault,
                candidate_id=args.candidate_id,
                confirmed_rejection=args.confirmed_rejection,
            )
        else:
            payload = revoke_relation(
                args.vault,
                relation_identity=args.relation_id,
                expected_revision=args.expected_revision,
                confirmed_revoke=args.confirmed_revoke,
            )
    except (BootstrapError, StorageError, sqlite3.DatabaseError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0
