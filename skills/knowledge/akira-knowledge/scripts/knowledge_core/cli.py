from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from knowledge_core.service import (
    BootstrapError,
    apply_update_proposal,
    approve_curate_proposal,
    capture_material,
    create_curate_proposal,
    inspect_vault,
    rebuild_full_text_projection,
    register_notes,
    reject_curate_proposal,
    retrieve_exact,
    retrieve_filter,
    retrieve_full_text,
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

    exact_parser = subparsers.add_parser(
        "retrieve-exact", help="Read one current Knowledge object by stable identity"
    )
    exact_parser.add_argument("--vault", required=True, type=Path)
    exact_parser.add_argument("--identity", required=True)
    exact_parser.add_argument(
        "--scope",
        action="append",
        help="Retrieval scope; repeat to combine current and material. Defaults to current.",
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
        help="Retrieval scope; repeat to combine current and material. Defaults to current.",
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
        help="Retrieval scope; repeat to combine current and material. Defaults to current.",
    )

    rebuild_parser = subparsers.add_parser(
        "retrieve-rebuild-index", help="Explicitly rebuild the full-text search Projection"
    )
    rebuild_parser.add_argument("--vault", required=True, type=Path)

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
    return parser


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
        elif args.command == "retrieve-exact":
            payload = retrieve_exact(
                args.vault,
                identity=args.identity,
                scopes=args.scope,
            )
        elif args.command == "retrieve-filter":
            property_filters: dict[str, str] = {}
            for item in args.property:
                if "=" not in item:
                    raise BootstrapError("Property filter must use key=value syntax")
                key, value = item.split("=", 1)
                if not key:
                    raise BootstrapError("Property filter key must not be empty")
                if key in property_filters:
                    raise BootstrapError(f"Duplicate property filter: {key}")
                property_filters[key] = value
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
        elif args.command == "retrieve-rebuild-index":
            payload = rebuild_full_text_projection(args.vault)
        elif args.command == "maintain-sync":
            payload = synchronize_object(args.vault, identity=args.identity)
        else:
            payload = apply_update_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_approval=args.confirmed_approval,
            )
    except (BootstrapError, StorageError, sqlite3.DatabaseError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0
