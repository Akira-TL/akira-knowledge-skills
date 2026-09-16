from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from knowledge_core.service import BootstrapError, capture_material, inspect_vault, register_notes


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
        else:
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
    except (BootstrapError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0
