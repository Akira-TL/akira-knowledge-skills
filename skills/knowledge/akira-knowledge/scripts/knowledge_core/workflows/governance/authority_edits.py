from __future__ import annotations

from pathlib import Path

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root, _write_atomic
from knowledge_core.ids import uuid7
from knowledge_core.markdown import (
    MarkdownConflict,
    authority_fingerprint,
    replace_wikilink_target,
    set_user_property,
)
from knowledge_core.persistence import authority_edits as authority_edit_store
from knowledge_core.persistence import lifecycle as lifecycle_store
from knowledge_core.workflows.maintain import sync_object_in_connection


def propose_authority_edit(
    vault: Path,
    *,
    identity: str,
    expected_base_revision: int,
    reason: str,
    wikilink_replacement: tuple[str, str] | None,
    property_update: tuple[str, str] | None,
) -> dict[str, object]:
    root = _vault_root(vault)
    if expected_base_revision < 1:
        raise BootstrapError(
            "Authority edit proposal base revision must be at least 1"
        )
    if not reason.strip():
        raise BootstrapError("Authority edit proposal requires a non-empty reason")
    if (wikilink_replacement is None) == (property_update is None):
        raise BootstrapError(
            "Authority edit proposal requires exactly one wikilink or Property edit"
        )
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            target = sync_object_in_connection(root, conn, identity)
        if target.kind != "knowledge_asset":
            raise BootstrapError(f"Knowledge asset does not exist: {identity}")
        lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(conn, identity)
        if lifecycle != "current":
            raise BootstrapError(f"Knowledge asset is not current: {identity}")
        if target.revision != expected_base_revision:
            raise BootstrapError(
                "Target revision changed during authority edit proposal preparation; "
                "re-read current Authority and create a new proposal"
            )

        try:
            if wikilink_replacement is not None:
                old_target, new_target = wikilink_replacement
                transformed, replacements = replace_wikilink_target(
                    target.text,
                    old_target=old_target,
                    new_target=new_target,
                )
                edit_kind = "wikilink"
                edit_detail: dict[str, object] = {
                    "old_target": old_target,
                    "new_target": new_target,
                    "replacement_count": replacements,
                }
            else:
                assert property_update is not None
                key, value = property_update
                transformed = set_user_property(
                    target.text,
                    key=key,
                    value=value,
                )
                edit_kind = "property"
                edit_detail = {
                    "property": key,
                    "value": value,
                }
        except MarkdownConflict as exc:
            raise BootstrapError(f"Cannot prepare authority edit safely: {exc}") from exc

        if transformed == target.text:
            raise BootstrapError("Authority edit proposal does not change human Authority")

        proposal_id = str(uuid7())
        with storage.transaction(conn):
            authority_edit_store.insert_authority_edit_proposal(
                conn,
                proposal_id=proposal_id,
                target_identity=identity,
                base_revision=target.revision,
                edit_kind=edit_kind,
                proposed_authority_text=transformed,
                reason=reason.strip(),
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "proposal_kind": "authority_edit",
        "edit_kind": edit_kind,
        "status": "pending",
        "target_identity": identity,
        "base_revision": target.revision,
        "canonical_locator": target.locator,
        "reason": reason.strip(),
        "edit": edit_detail,
        "proposed_authority_text": transformed,
    }


def apply_authority_edit(
    vault: Path,
    *,
    proposal_id: str,
    confirmed_approval: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_approval:
        raise BootstrapError(
            "Applying an authority edit proposal requires explicit user approval"
        )
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    path: Path | None = None
    original: str | None = None
    try:
        storage.initialize_schema(conn)
        conn.commit()
        proposal = authority_edit_store.get_authority_edit_proposal(
            conn, proposal_id
        )
        if proposal is None:
            raise BootstrapError(
                f"Authority edit proposal does not exist: {proposal_id}"
            )
        if proposal.status != "pending":
            raise BootstrapError(
                f"Authority edit proposal is not pending: {proposal_id}"
            )

        with storage.transaction(conn):
            target = sync_object_in_connection(
                root,
                conn,
                proposal.target_identity,
            )
        if target.kind != "knowledge_asset":
            raise BootstrapError(
                "Authority edit proposal target is not a Knowledge Asset"
            )
        lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(
            conn,
            proposal.target_identity,
        )
        if lifecycle != "current":
            raise BootstrapError(
                f"Authority edit proposal target is not current: {proposal.target_identity}"
            )
        if target.revision != proposal.base_revision:
            raise BootstrapError(
                "Authority edit proposal is stale because target Authority "
                "changed since its base revision"
            )

        path = root / target.locator
        original = target.text
        transformed = proposal.proposed_authority_text
        fingerprint = authority_fingerprint(transformed)

        try:
            with storage.transaction(conn):
                _write_atomic(path, transformed)
                new_revision = authority_edit_store.apply_authority_edit(
                    conn,
                    proposal_id=proposal_id,
                    identity=proposal.target_identity,
                    locator=target.locator,
                    fingerprint=fingerprint,
                )
        except Exception:
            if path is not None and original is not None:
                try:
                    _write_atomic(path, original)
                except OSError:
                    pass
            raise
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "proposal_kind": "authority_edit",
        "edit_kind": proposal.edit_kind,
        "status": "applied",
        "stable_identity": proposal.target_identity,
        "canonical_locator": target.locator,
        "revision": new_revision,
        "reason": proposal.reason,
    }
