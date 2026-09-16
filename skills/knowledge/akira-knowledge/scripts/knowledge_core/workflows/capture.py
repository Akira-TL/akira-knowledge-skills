from __future__ import annotations

from pathlib import Path
from typing import Sequence

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _safe_relative, _vault_root, _within_scope, _write_atomic
from knowledge_core.ids import uuid7
from knowledge_core.markdown import authority_fingerprint, create_material_markdown


def capture_material(
    vault: Path,
    *,
    capture_note: str,
    sources: Sequence[str],
    confirmed_intent: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_intent:
        raise BootstrapError(
            "Capture requires explicit persistent intent; ordinary conversation must not be persisted"
        )
    if not capture_note:
        raise BootstrapError("Capture note must not be empty")

    config = storage.read_config(root)
    if config is None:
        raise BootstrapError("Vault is not bootstrapped; approve and register a Knowledge scope first")
    default_value = config.get("default_write_root")
    scopes_value = config.get("managed_scopes")
    if not isinstance(default_value, str) or not isinstance(scopes_value, list) or not all(
        isinstance(item, str) for item in scopes_value
    ):
        raise BootstrapError("Akira Knowledge config has invalid management scope data")
    default_root, default_path = _safe_relative(root, default_value, must_exist=False)
    if not _within_scope(default_root, tuple(scopes_value)):
        raise BootstrapError("Configured default write root is outside managed scopes")
    if default_path.exists() and not default_path.is_dir():
        raise BootstrapError("Configured default write root is not a directory")

    db = storage.db_path(root)
    if not db.exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    identity = str(uuid7())
    filename = f"材料-{identity}.md"
    locator = (Path(default_root) / filename).as_posix() if default_root != "." else filename
    target = root / locator
    if target.exists():
        raise BootstrapError(f"Generated material locator already exists: {locator}")

    markdown = create_material_markdown(
        identity=identity,
        status="待处理",
        capture_note=capture_note,
    )
    fingerprint = authority_fingerprint(markdown)

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        duplicate_candidates: dict[str, list[str]] = {}
        for source in sources:
            matches = storage.find_materials_by_source(conn, source)
            if matches:
                duplicate_candidates[source] = matches

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with storage.transaction(conn):
                _write_atomic(target, markdown)
                storage.insert_material_capture(
                    conn,
                    identity=identity,
                    locator=locator,
                    fingerprint=fingerprint,
                    sources=tuple(sources),
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
    finally:
        conn.close()

    return {
        "vault": str(root),
        "identity": identity,
        "kind": "material_record",
        "status": "待处理",
        "revision": 1,
        "locator": locator,
        "sources": list(sources),
        "duplicate_candidates": duplicate_candidates,
    }
