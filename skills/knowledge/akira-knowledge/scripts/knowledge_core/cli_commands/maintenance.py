from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_core.cli_commands.authority_edits import (
    AUTHORITY_EDIT_COMMANDS,
    dispatch_authority_edit_command,
    register_authority_edit_commands,
)
from knowledge_core.service import (
    apply_retire_proposal,
    apply_supersede_proposal,
    apply_update_proposal,
    approve_batch,
    create_batch,
    create_retire_proposal,
    create_supersede_proposal,
    execute_batch,
    inspect_conflict_candidate,
    inspect_relation_maintenance_candidate,
    inspect_review_candidate,
    plan_source_review,
    propose_conflict,
    propose_relation_maintenance,
    reject_conflict_candidate,
    reject_relation_maintenance_candidate,
    reject_review_candidate,
    resolve_material,
    review_source,
    scan_network_health,
    synchronize_object,
)


MAINTENANCE_COMMANDS = frozenset(
    {
        "maintain-health-scan",
        "maintain-batch-create",
        "maintain-batch-approve",
        "maintain-batch-execute",
        "maintain-sync",
        "maintain-resolve-material",
        "maintain-apply-update",
        "maintain-propose-retire",
        "maintain-apply-retire",
        "maintain-propose-supersede",
        "maintain-apply-supersede",
        "maintain-propose-conflict",
        "maintain-inspect-conflict",
        "maintain-reject-conflict",
        "maintain-propose-relation-maintenance",
        "maintain-inspect-relation-maintenance",
        "maintain-reject-relation-maintenance",
        "maintain-review-plan",
        "maintain-review-source",
        "maintain-inspect-review-candidate",
        "maintain-reject-review-candidate",
        *AUTHORITY_EDIT_COMMANDS,
    }
)


def register_maintenance_commands(
    subparsers: argparse._SubParsersAction,
) -> None:
    health_parser = subparsers.add_parser(
        "maintain-health-scan",
        help="Read-only diagnostics for orphan, unresolved, and dead-end Knowledge network states",
    )
    health_parser.add_argument("--vault", required=True, type=Path)

    register_authority_edit_commands(subparsers)
    _register_batch_commands(subparsers)
    _register_core_commands(subparsers)
    _register_conflict_commands(subparsers)
    _register_review_commands(subparsers)


def _register_batch_commands(subparsers: argparse._SubParsersAction) -> None:
    create_parser = subparsers.add_parser(
        "maintain-batch-create",
        help="Create a maintenance batch from existing governed proposals/candidates",
    )
    create_parser.add_argument("--vault", required=True, type=Path)
    create_parser.add_argument("--update-proposal", action="append", default=[])
    create_parser.add_argument("--retire-proposal", action="append", default=[])
    create_parser.add_argument("--supersede-proposal", action="append", default=[])
    create_parser.add_argument("--authority-edit-proposal", action="append", default=[])
    create_parser.add_argument("--relation-candidate", action="append", default=[])
    create_parser.add_argument("--relation-revoke-candidate", action="append", default=[])

    approve_parser = subparsers.add_parser(
        "maintain-batch-approve",
        help="Approve an explicit subset of maintenance batch items",
    )
    approve_parser.add_argument("--vault", required=True, type=Path)
    approve_parser.add_argument("--batch-id", required=True)
    approve_parser.add_argument("--item-id", action="append", default=[])
    approve_parser.add_argument("--confirmed-approval", action="store_true")

    execute_parser = subparsers.add_parser(
        "maintain-batch-execute",
        help="Execute approved maintenance items through their existing governance paths",
    )
    execute_parser.add_argument("--vault", required=True, type=Path)
    execute_parser.add_argument("--batch-id", required=True)


def _register_core_commands(subparsers: argparse._SubParsersAction) -> None:
    sync_parser = subparsers.add_parser(
        "maintain-sync",
        help="Synchronize current locator/fingerprint into the revision ledger",
    )
    sync_parser.add_argument("--vault", required=True, type=Path)
    sync_parser.add_argument("--identity", required=True)

    resolve_parser = subparsers.add_parser(
        "maintain-resolve-material",
        help="Explicitly mark one pending Material Record processed without creating Knowledge",
    )
    resolve_parser.add_argument("--vault", required=True, type=Path)
    resolve_parser.add_argument("--identity", required=True)
    resolve_parser.add_argument("--expected-revision", required=True, type=int)
    resolve_parser.add_argument("--reason", required=True)
    resolve_parser.add_argument("--confirmed-resolution", action="store_true")

    update_parser = subparsers.add_parser(
        "maintain-apply-update",
        help="Apply an approved update proposal with revision protection",
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


def _register_conflict_commands(subparsers: argparse._SubParsersAction) -> None:
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

    relation_parser = subparsers.add_parser(
        "maintain-propose-relation-maintenance",
        help="Create a basis-bound stale/conflict candidate for one active Relation Record",
    )
    relation_parser.add_argument("--vault", required=True, type=Path)
    relation_parser.add_argument("--relation-id", required=True)
    relation_parser.add_argument(
        "--kind",
        required=True,
        choices=("relation_stale", "relation_conflict"),
    )
    relation_parser.add_argument("--source-finding-id")
    relation_parser.add_argument("--evidence", required=True)

    relation_inspect_parser = subparsers.add_parser(
        "maintain-inspect-relation-maintenance",
        help="Revalidate one Relation maintenance candidate",
    )
    relation_inspect_parser.add_argument("--vault", required=True, type=Path)
    relation_inspect_parser.add_argument("--candidate-id", required=True)

    relation_reject_parser = subparsers.add_parser(
        "maintain-reject-relation-maintenance",
        help="Reject a pending or stale Relation maintenance candidate",
    )
    relation_reject_parser.add_argument("--vault", required=True, type=Path)
    relation_reject_parser.add_argument("--candidate-id", required=True)
    relation_reject_parser.add_argument("--confirmed-rejection", action="store_true")


def _register_review_commands(subparsers: argparse._SubParsersAction) -> None:
    plan_parser = subparsers.add_parser(
        "maintain-review-plan",
        help="List provenance Sources that should be verified for one current Knowledge Asset",
    )
    plan_parser.add_argument("--vault", required=True, type=Path)
    plan_parser.add_argument("--identity", required=True)

    source_parser = subparsers.add_parser(
        "maintain-review-source",
        help="Record one verified Source review and create a stale maintenance candidate when changed",
    )
    source_parser.add_argument("--vault", required=True, type=Path)
    source_parser.add_argument("--identity", required=True)
    source_parser.add_argument("--source", required=True)
    source_parser.add_argument("--basis-source-id")
    source_parser.add_argument("--basis-revision")
    source_parser.add_argument("--basis-fingerprint")
    source_parser.add_argument("--unknown", action="store_true")
    source_parser.add_argument("--observed-source-id")
    source_parser.add_argument("--observed-revision")
    source_parser.add_argument("--observed-fingerprint")
    source_parser.add_argument("--evidence", required=True)

    inspect_parser = subparsers.add_parser(
        "maintain-inspect-review-candidate",
        help="Revalidate and inspect one maintenance candidate",
    )
    inspect_parser.add_argument("--vault", required=True, type=Path)
    inspect_parser.add_argument("--candidate-id", required=True)

    reject_parser = subparsers.add_parser(
        "maintain-reject-review-candidate",
        help="Reject a pending or stale maintenance candidate",
    )
    reject_parser.add_argument("--vault", required=True, type=Path)
    reject_parser.add_argument("--candidate-id", required=True)
    reject_parser.add_argument("--confirmed-rejection", action="store_true")


def dispatch_maintenance_command(args: argparse.Namespace) -> dict[str, object]:
    if args.command in AUTHORITY_EDIT_COMMANDS:
        return dispatch_authority_edit_command(args)
    if args.command == "maintain-health-scan":
        return scan_network_health(args.vault)
    if args.command == "maintain-batch-create":
        return create_batch(
            args.vault,
            update_proposals=args.update_proposal,
            retire_proposals=args.retire_proposal,
            supersede_proposals=args.supersede_proposal,
            authority_edit_proposals=args.authority_edit_proposal,
            relation_candidates=args.relation_candidate,
            relation_revoke_candidates=args.relation_revoke_candidate,
        )
    if args.command == "maintain-batch-approve":
        return approve_batch(
            args.vault,
            batch_id=args.batch_id,
            item_ids=args.item_id,
            confirmed_approval=args.confirmed_approval,
        )
    if args.command == "maintain-batch-execute":
        return execute_batch(args.vault, batch_id=args.batch_id)
    if args.command == "maintain-sync":
        return synchronize_object(args.vault, identity=args.identity)
    if args.command == "maintain-resolve-material":
        return resolve_material(
            args.vault,
            identity=args.identity,
            expected_revision=args.expected_revision,
            reason=args.reason,
            confirmed_resolution=args.confirmed_resolution,
        )
    if args.command == "maintain-apply-update":
        return apply_update_proposal(
            args.vault,
            proposal_id=args.proposal_id,
            confirmed_approval=args.confirmed_approval,
        )
    if args.command == "maintain-propose-retire":
        return create_retire_proposal(
            args.vault,
            identity=args.identity,
            expected_base_revision=args.base_revision,
            reason=args.reason,
        )
    if args.command == "maintain-apply-retire":
        return apply_retire_proposal(
            args.vault,
            proposal_id=args.proposal_id,
            confirmed_approval=args.confirmed_approval,
        )
    if args.command == "maintain-propose-supersede":
        return create_supersede_proposal(
            args.vault,
            identity=args.identity,
            expected_base_revision=args.base_revision,
            replacement_identity=args.replacement_id,
            expected_replacement_revision=args.replacement_revision,
            reason=args.reason,
        )
    if args.command == "maintain-apply-supersede":
        return apply_supersede_proposal(
            args.vault,
            proposal_id=args.proposal_id,
            confirmed_approval=args.confirmed_approval,
        )
    if args.command == "maintain-propose-conflict":
        return propose_conflict(
            args.vault,
            knowledge_ids=args.knowledge_id,
            source_finding_ids=args.source_finding_id,
            relation_ids=args.relation_id,
            conflict=args.conflict,
            evidence=args.evidence,
        )
    if args.command == "maintain-inspect-conflict":
        return inspect_conflict_candidate(args.vault, candidate_id=args.candidate_id)
    if args.command == "maintain-reject-conflict":
        return reject_conflict_candidate(
            args.vault,
            candidate_id=args.candidate_id,
            confirmed_rejection=args.confirmed_rejection,
        )
    if args.command == "maintain-propose-relation-maintenance":
        return propose_relation_maintenance(
            args.vault,
            relation_identity=args.relation_id,
            candidate_kind=args.kind,
            source_finding_id=args.source_finding_id,
            evidence=args.evidence,
        )
    if args.command == "maintain-inspect-relation-maintenance":
        return inspect_relation_maintenance_candidate(
            args.vault,
            candidate_id=args.candidate_id,
        )
    if args.command == "maintain-reject-relation-maintenance":
        return reject_relation_maintenance_candidate(
            args.vault,
            candidate_id=args.candidate_id,
            confirmed_rejection=args.confirmed_rejection,
        )
    if args.command == "maintain-review-plan":
        return plan_source_review(args.vault, identity=args.identity)
    if args.command == "maintain-review-source":
        return review_source(
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
    if args.command == "maintain-inspect-review-candidate":
        return inspect_review_candidate(args.vault, candidate_id=args.candidate_id)
    if args.command == "maintain-reject-review-candidate":
        return reject_review_candidate(
            args.vault,
            candidate_id=args.candidate_id,
            confirmed_rejection=args.confirmed_rejection,
        )
    raise ValueError(f"unsupported maintenance command: {args.command}")
