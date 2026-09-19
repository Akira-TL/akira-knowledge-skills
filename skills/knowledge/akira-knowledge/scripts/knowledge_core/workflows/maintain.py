from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root, _write_atomic
from knowledge_core.ids import uuid7
from knowledge_core.markdown import (
    AK_LIFECYCLE,
    AK_STATUS,
    MarkdownConflict,
    authority_fingerprint,
    replace_human_body,
    replace_knowledge_property,
    set_knowledge_property,
)
from knowledge_core.persistence import relations as relation_store
from knowledge_core.resolution import ResolvedObject, resolve_object


@dataclass(frozen=True)
class SyncResult:
    identity: str
    kind: str
    locator: str
    revision: int
    changed: bool
    event: str | None
    text: str
    fingerprint: str


@dataclass(frozen=True)
class MaterialUpdatePlan:
    identity: str
    locator: str
    original: str
    transformed: str
    fingerprint: str
    status: str


def _validate_structured_projection(
    conn: sqlite3.Connection,
    obj: ResolvedObject,
) -> None:
    if obj.kind != "material_record":
        return
    status = storage.get_material_status(conn, obj.identity)
    if status is None:
        raise BootstrapError(f"Material state does not exist: {obj.identity}")
    if obj.properties.get(AK_STATUS) != status:
        raise BootstrapError(
            "Material status Property disagrees with structured Authority; "
            f"resolve drift before continuing: {obj.locator}"
        )


def sync_object_in_connection(
    root: Path,
    conn: sqlite3.Connection,
    identity: str,
) -> SyncResult:
    record = storage.get_by_identity(conn, identity)
    if record is None:
        raise BootstrapError(f"Knowledge object does not exist: {identity}")
    obj = resolve_object(root, conn, identity)
    _validate_structured_projection(conn, obj)

    locator_changed = obj.locator != record.locator
    fingerprint_changed = obj.fingerprint != record.authority_fingerprint
    if not locator_changed and not fingerprint_changed:
        return SyncResult(
            identity=identity,
            kind=record.kind,
            locator=obj.locator,
            revision=record.revision,
            changed=False,
            event=None,
            text=obj.text,
            fingerprint=obj.fingerprint,
        )

    if locator_changed and fingerprint_changed:
        event = "external_move_and_edit"
    elif locator_changed:
        event = "external_move"
    else:
        event = "external_edit"

    revision = storage.record_external_state_change(
        conn,
        identity=identity,
        locator=obj.locator,
        fingerprint=obj.fingerprint,
        event=event,
    )
    return SyncResult(
        identity=identity,
        kind=record.kind,
        locator=obj.locator,
        revision=revision,
        changed=True,
        event=event,
        text=obj.text,
        fingerprint=obj.fingerprint,
    )


def synchronize_object(vault: Path, *, identity: str) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")
    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            result = sync_object_in_connection(root, conn, identity)
    finally:
        conn.close()
    return {
        "vault": str(root),
        "stable_identity": result.identity,
        "object_kind": result.kind,
        "canonical_locator": result.locator,
        "revision": result.revision,
        "changed": result.changed,
        "event": result.event,
    }


def _only_disjoint_events_since(
    conn: sqlite3.Connection,
    *,
    identity: str,
    base_revision: int,
    allowed_events: set[str],
) -> bool:
    record = storage.get_by_identity(conn, identity)
    if record is None or record.revision < base_revision:
        return False
    if record.revision == base_revision:
        return True
    events = storage.revision_events_after(
        conn,
        identity=identity,
        revision=base_revision,
    )
    return bool(events) and all(event in allowed_events for event in events)


def _sync_and_commit(
    root: Path,
    conn: sqlite3.Connection,
    identity: str,
) -> SyncResult:
    with storage.transaction(conn):
        return sync_object_in_connection(root, conn, identity)


def apply_update_proposal(
    vault: Path,
    *,
    proposal_id: str,
    confirmed_approval: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_approval:
        raise BootstrapError("Applying an update proposal requires explicit user approval")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    changed_material_paths: list[Path] = []
    target_path: Path | None = None
    target_original: str | None = None
    material_plans: list[MaterialUpdatePlan] = []
    try:
        storage.initialize_schema(conn)
        conn.commit()
        proposal = storage.get_proposal(conn, proposal_id)
        if proposal is None:
            raise BootstrapError(f"Proposal does not exist: {proposal_id}")
        if proposal.status != "pending":
            raise BootstrapError(f"Proposal is not pending: {proposal_id}")
        if proposal.proposal_kind != "update" or proposal.target_identity is None:
            raise BootstrapError("Revision-safe maintain flow only applies update proposals")
        if proposal.base_revision is None:
            raise BootstrapError("Update proposal is missing base revision")

        target_sync = _sync_and_commit(root, conn, proposal.target_identity)
        if target_sync.kind != "knowledge_asset":
            raise BootstrapError("Update proposal target is not a knowledge asset")
        if not _only_disjoint_events_since(
            conn,
            identity=proposal.target_identity,
            base_revision=proposal.base_revision,
            allowed_events={"external_move"},
        ):
            raise BootstrapError(
                "Update proposal is stale because target Authority changed since its base revision; "
                "create a new proposal from the current revision"
            )

        material_bases = storage.get_proposal_materials(conn, proposal_id)
        if not material_bases:
            raise BootstrapError("Update proposal has no material provenance")
        for material_identity, basis_revision in material_bases:
            material_sync = _sync_and_commit(root, conn, material_identity)
            if material_sync.kind != "material_record":
                raise BootstrapError(f"Proposal evidence is not a material record: {material_identity}")
            if not _only_disjoint_events_since(
                conn,
                identity=material_identity,
                base_revision=basis_revision,
                allowed_events={"external_move", "processed_by_proposal"},
            ):
                raise BootstrapError(
                    "Update proposal is stale because a material Authority changed since proposal creation; "
                    "create a new proposal from current material revisions"
                )
            status = storage.get_material_status(conn, material_identity)
            if status is None:
                raise BootstrapError(f"Material state does not exist: {material_identity}")
            transformed = material_sync.text
            if status == "待处理":
                try:
                    transformed = replace_knowledge_property(
                        material_sync.text,
                        key=AK_STATUS,
                        value="已处理",
                    )
                except MarkdownConflict as exc:
                    raise BootstrapError(
                        f"Cannot safely update material status {material_sync.locator}: {exc}"
                    ) from exc
            material_plans.append(
                MaterialUpdatePlan(
                    identity=material_identity,
                    locator=material_sync.locator,
                    original=material_sync.text,
                    transformed=transformed,
                    fingerprint=material_sync.fingerprint,
                    status=status,
                )
            )

        target_path = root / target_sync.locator
        target_original = target_sync.text
        target_transformed = replace_human_body(
            target_original,
            body=proposal.proposed_body,
        )
        target_fingerprint = authority_fingerprint(target_transformed)

        try:
            with storage.transaction(conn):
                _write_atomic(target_path, target_transformed)
                for plan in material_plans:
                    if plan.transformed != plan.original:
                        path = root / plan.locator
                        _write_atomic(path, plan.transformed)
                        changed_material_paths.append(path)
                new_revision = storage.apply_knowledge_asset_update(
                    conn,
                    identity=proposal.target_identity,
                    locator=target_sync.locator,
                    fingerprint=target_fingerprint,
                    proposal_id=proposal_id,
                    material_bases=material_bases,
                )
                material_revisions: dict[str, int] = {}
                for plan in material_plans:
                    material_revisions[plan.identity] = storage.mark_material_processed(
                        conn,
                        identity=plan.identity,
                        locator=plan.locator,
                        fingerprint=plan.fingerprint,
                    )
        except Exception:
            if target_path is not None and target_original is not None:
                try:
                    _write_atomic(target_path, target_original)
                except OSError:
                    pass
            for plan in material_plans:
                path = root / plan.locator
                if path in changed_material_paths:
                    try:
                        _write_atomic(path, plan.original)
                    except OSError:
                        pass
            raise
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "status": "applied",
        "stable_identity": proposal.target_identity,
        "canonical_locator": target_sync.locator,
        "revision": new_revision,
        "material_revisions": material_revisions,
    }


def create_retire_proposal(
    vault: Path,
    *,
    identity: str,
    expected_base_revision: int,
    reason: str,
) -> dict[str, object]:
    root = _vault_root(vault)
    if expected_base_revision < 1:
        raise BootstrapError("Retire proposal base revision must be at least 1")
    if not reason.strip():
        raise BootstrapError("Retire proposal requires a non-empty reason")
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
        lifecycle = storage.get_knowledge_asset_lifecycle(conn, identity)
        if lifecycle is None:
            raise BootstrapError(f"Knowledge asset lifecycle does not exist: {identity}")
        if lifecycle != "current":
            raise BootstrapError(f"Knowledge asset is not current: {identity}")
        if target.revision != expected_base_revision:
            raise BootstrapError(
                "Target revision changed during retire proposal preparation; "
                "re-read current Authority and create a new proposal"
            )

        proposal_id = str(uuid7())
        with storage.transaction(conn):
            storage.insert_lifecycle_proposal(
                conn,
                proposal_id=proposal_id,
                proposal_kind="retire",
                target_identity=identity,
                base_revision=expected_base_revision,
                reason=reason.strip(),
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "proposal_kind": "retire",
        "status": "pending",
        "target_identity": identity,
        "base_revision": expected_base_revision,
        "current_lifecycle": lifecycle,
        "proposed_lifecycle": "retired",
        "reason": reason.strip(),
    }


def apply_retire_proposal(
    vault: Path,
    *,
    proposal_id: str,
    confirmed_approval: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_approval:
        raise BootstrapError("Applying a retire proposal requires explicit user approval")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    target_path: Path | None = None
    target_original: str | None = None
    try:
        storage.initialize_schema(conn)
        conn.commit()
        proposal = storage.get_lifecycle_proposal(conn, proposal_id)
        if proposal is None:
            raise BootstrapError(f"Lifecycle proposal does not exist: {proposal_id}")
        if proposal.status != "pending" or proposal.proposal_kind != "retire":
            raise BootstrapError(f"Retire proposal is not pending: {proposal_id}")

        target = _sync_and_commit(root, conn, proposal.target_identity)
        if target.kind != "knowledge_asset":
            raise BootstrapError("Retire proposal target is not a knowledge asset")
        if target.revision != proposal.base_revision:
            raise BootstrapError(
                "Retire proposal is stale because target Authority changed since its base revision; "
                "create a new proposal from the current revision"
            )
        lifecycle = storage.get_knowledge_asset_lifecycle(conn, proposal.target_identity)
        if lifecycle != "current":
            raise BootstrapError("Retire proposal target is no longer current")

        try:
            transformed = set_knowledge_property(
                target.text,
                key=AK_LIFECYCLE,
                value="retired",
            )
        except MarkdownConflict as exc:
            raise BootstrapError(
                f"Cannot safely update lifecycle Property {target.locator}: {exc}"
            ) from exc
        transformed_fingerprint = authority_fingerprint(transformed)
        if transformed_fingerprint != target.fingerprint:
            raise BootstrapError(
                "Lifecycle mirror unexpectedly changed human Authority fingerprint"
            )

        target_path = root / target.locator
        target_original = target.text
        try:
            with storage.transaction(conn):
                _write_atomic(target_path, transformed)
                new_revision = storage.apply_retire_lifecycle_proposal(
                    conn,
                    proposal_id=proposal_id,
                    identity=proposal.target_identity,
                    locator=target.locator,
                    fingerprint=transformed_fingerprint,
                )
        except Exception:
            if target_path is not None and target_original is not None:
                try:
                    _write_atomic(target_path, target_original)
                except OSError:
                    pass
            raise
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "status": "applied",
        "stable_identity": proposal.target_identity,
        "canonical_locator": target.locator,
        "lifecycle": "retired",
        "revision": new_revision,
    }


def revoke_relation(
    vault: Path,
    *,
    relation_identity: str,
    expected_revision: int,
    confirmed_revoke: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_revoke:
        raise BootstrapError("Revoking a Relation Record requires explicit user confirmation")
    if expected_revision < 1:
        raise BootstrapError("Expected relation revision must be at least 1")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            relation, changed = relation_store.revoke_relation_record(
                conn,
                relation_identity=relation_identity,
                expected_revision=expected_revision,
            )
            provenance_entries = relation_store.list_relation_provenance(
                conn,
                relation.identity,
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "relation_identity": relation.identity,
        "source": relation.source_ref,
        "type": relation.relation_type,
        "target": relation.target_ref,
        "provenance": provenance_entries,
        "status": relation.status,
        "revision": relation.revision,
        "changed": changed,
    }
