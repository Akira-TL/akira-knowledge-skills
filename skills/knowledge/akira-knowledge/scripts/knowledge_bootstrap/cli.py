from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from knowledge_bootstrap.service import BootstrapError, inspect_vault, register_notes


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            payload = inspect_vault(args.vault)
        else:
            payload = register_notes(
                args.vault,
                scopes=args.scope,
                notes=args.note,
                default_write_root=args.default_write_root,
                kind=args.kind,
            )
    except (BootstrapError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0
