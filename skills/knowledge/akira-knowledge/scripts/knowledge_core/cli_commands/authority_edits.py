from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_core.service import apply_authority_edit, propose_authority_edit


AUTHORITY_EDIT_COMMANDS = frozenset(
    {
        "maintain-propose-authority-edit",
        "maintain-apply-authority-edit",
    }
)


def register_authority_edit_commands(
    subparsers: argparse._SubParsersAction,
) -> None:
    propose_parser = subparsers.add_parser(
        "maintain-propose-authority-edit",
        help="Create a revision-bound proposal for one human Authority wikilink or Property edit",
    )
    propose_parser.add_argument("--vault", required=True, type=Path)
    propose_parser.add_argument("--identity", required=True)
    propose_parser.add_argument("--base-revision", required=True, type=int)
    group = propose_parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--replace-wikilink",
        nargs=2,
        metavar=("OLD_TARGET", "NEW_TARGET"),
    )
    group.add_argument(
        "--set-property",
        nargs=2,
        metavar=("KEY", "VALUE"),
    )
    propose_parser.add_argument("--reason", required=True)

    apply_parser = subparsers.add_parser(
        "maintain-apply-authority-edit",
        help="Apply an explicitly approved revision-bound human Authority edit",
    )
    apply_parser.add_argument("--vault", required=True, type=Path)
    apply_parser.add_argument("--proposal-id", required=True)
    apply_parser.add_argument("--confirmed-approval", action="store_true")


def dispatch_authority_edit_command(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "maintain-propose-authority-edit":
        return propose_authority_edit(
            args.vault,
            identity=args.identity,
            expected_base_revision=args.base_revision,
            reason=args.reason,
            wikilink_replacement=(
                None if args.replace_wikilink is None else tuple(args.replace_wikilink)
            ),
            property_update=(
                None if args.set_property is None else tuple(args.set_property)
            ),
        )
    if args.command == "maintain-apply-authority-edit":
        return apply_authority_edit(
            args.vault,
            proposal_id=args.proposal_id,
            confirmed_approval=args.confirmed_approval,
        )
    raise ValueError(f"unsupported authority edit command: {args.command}")
