from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from knowledge_core.service import (
    BootstrapError,
    approve_curate_proposal,
    capture_material,
    create_curate_proposal,
    inspect_vault,
    register_notes,
    reject_curate_proposal,
)


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
            )
        elif args.command == "curate-approve":
            payload = approve_curate_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_approval=args.confirmed_approval,
            )
        else:
            payload = reject_curate_proposal(
                args.vault,
                proposal_id=args.proposal_id,
                confirmed_rejection=args.confirmed_rejection,
            )
    except (BootstrapError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0
