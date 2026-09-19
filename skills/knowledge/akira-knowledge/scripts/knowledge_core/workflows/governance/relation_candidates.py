from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledge_core import storage
from knowledge_core.persistence import relations as relation_store
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.ids import uuid7
from knowledge_core.workflows.maintain import SyncResult, sync_object_in_connection


@dataclass(frozen=True)
class EndpointSnapshot:
    kind: str
    ref: str
    revision: int | None
    fingerprint: str | None
    locator: str | None


def _validate_endpoint_input(
    *,
    identity: str | None,
    external_ref: str | None,
    label: str,
) -> tuple[str | None, str | None]:
    if (identity is None) == (external_ref is None):
        raise BootstrapError(
            f"Relation {label} requires exactly one Knowledge identity or external reference"
        )
    if identity is not None and not identity.strip():
        raise BootstrapError(f"Relation {label} Knowledge identity must not be empty")
    if external_ref is not None and not external_ref.strip():
        raise BootstrapError(f"Relation {label} external reference must not be empty")
    return (
        None if identity is None else identity.strip(),
        None if external_ref is None else external_ref.strip(),
    )


def _snapshot_from_sync(result: SyncResult) -> EndpointSnapshot:
    return EndpointSnapshot(
        kind="knowledge",
        ref=result.identity,
        revision=result.revision,
        fingerprint=result.fingerprint,
        locator=result.locator,
    )


def _prepare_endpoint(
    root: Path,
    conn,
    *,
    identity: str | None,
    external_ref: str | None,
    label: str,
) -> EndpointSnapshot:
    identity, external_ref = _validate_endpoint_input(
        identity=identity,
        external_ref=external_ref,
        label=label,
    )
    if identity is not None:
        return _snapshot_from_sync(sync_object_in_connection(root, conn, identity))
    assert external_ref is not None
    return EndpointSnapshot(
        kind="external",
        ref=external_ref,
        revision=None,
        fingerprint=None,
        locator=None,
    )


def _endpoint_payload(snapshot: EndpointSnapshot) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": snapshot.kind,
        "ref": snapshot.ref,
        "revision": snapshot.revision,
        "authority_fingerprint": snapshot.fingerprint,
    }
    if snapshot.locator is not None:
        payload["canonical_locator"] = snapshot.locator
    return payload


def _stored_endpoint_payload(
    *,
    kind: str,
    ref: str,
    revision: int | None,
    fingerprint: str | None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "ref": ref,
        "revision": revision,
        "authority_fingerprint": fingerprint,
    }


def create_relation_candidate(
    vault: Path,
    *,
    source_identity: str | None,
    source_external: str | None,
    relation_type: str,
    target_identity: str | None,
    target_external: str | None,
    provenance: str,
) -> dict[str, object]:
    root = _vault_root(vault)
    relation_type = relation_type.strip()
    provenance = provenance.strip()
    if not relation_type:
        raise BootstrapError("Relation type must not be empty")
    if not provenance:
        raise BootstrapError("Relation provenance must not be empty")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            source = _prepare_endpoint(
                root,
                conn,
                identity=source_identity,
                external_ref=source_external,
                label="source",
            )
            target = _prepare_endpoint(
                root,
                conn,
                identity=target_identity,
                external_ref=target_external,
                label="target",
            )
            candidate_id = str(uuid7())
            relation_store.insert_relation_candidate(
                conn,
                candidate_id=candidate_id,
                source_kind=source.kind,
                source_ref=source.ref,
                source_revision=source.revision,
                source_fingerprint=source.fingerprint,
                relation_type=relation_type,
                target_kind=target.kind,
                target_ref=target.ref,
                target_revision=target.revision,
                target_fingerprint=target.fingerprint,
                provenance=provenance,
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate_id,
        "status": "pending",
        "source": _endpoint_payload(source),
        "type": relation_type,
        "target": _endpoint_payload(target),
        "provenance": provenance,
    }


def inspect_relation_candidate(
    vault: Path,
    *,
    candidate_id: str,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    current_source: EndpointSnapshot | None = None
    current_target: EndpointSnapshot | None = None
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = relation_store.get_relation_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Relation Candidate does not exist: {candidate_id}")

        if candidate.status == "pending":
            with storage.transaction(conn):
                if candidate.source_kind == "knowledge":
                    current_source = _snapshot_from_sync(
                        sync_object_in_connection(root, conn, candidate.source_ref)
                    )
                else:
                    current_source = EndpointSnapshot(
                        kind="external",
                        ref=candidate.source_ref,
                        revision=None,
                        fingerprint=None,
                        locator=None,
                    )
                if candidate.target_kind == "knowledge":
                    current_target = _snapshot_from_sync(
                        sync_object_in_connection(root, conn, candidate.target_ref)
                    )
                else:
                    current_target = EndpointSnapshot(
                        kind="external",
                        ref=candidate.target_ref,
                        revision=None,
                        fingerprint=None,
                        locator=None,
                    )

                stale = (
                    candidate.source_kind == "knowledge"
                    and current_source.fingerprint != candidate.source_fingerprint
                ) or (
                    candidate.target_kind == "knowledge"
                    and current_target.fingerprint != candidate.target_fingerprint
                )
                if stale:
                    relation_store.mark_relation_candidate_stale(conn, candidate_id)

            candidate = relation_store.get_relation_candidate(conn, candidate_id)
            assert candidate is not None

        payload: dict[str, object] = {
            "vault": str(root),
            "candidate_id": candidate.candidate_id,
            "status": candidate.status,
            "source": _stored_endpoint_payload(
                kind=candidate.source_kind,
                ref=candidate.source_ref,
                revision=candidate.source_revision,
                fingerprint=candidate.source_fingerprint,
            ),
            "type": candidate.relation_type,
            "target": _stored_endpoint_payload(
                kind=candidate.target_kind,
                ref=candidate.target_ref,
                revision=candidate.target_revision,
                fingerprint=candidate.target_fingerprint,
            ),
            "provenance": candidate.provenance,
        }
        if current_source is not None:
            payload["current_source"] = _endpoint_payload(current_source)
        if current_target is not None:
            payload["current_target"] = _endpoint_payload(current_target)
        return payload
    finally:
        conn.close()


def approve_relation_candidate(
    vault: Path,
    *,
    candidate_id: str,
    confirmed_approval: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_approval:
        raise BootstrapError("Approving a Relation Candidate requires explicit user approval")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    stale = False
    relation_identity: str | None = None
    relation_revision: int | None = None
    relation_created = False
    provenance_added = False
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = relation_store.get_relation_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Relation Candidate does not exist: {candidate_id}")
        if candidate.status != "pending":
            raise BootstrapError(f"Relation Candidate is not pending: {candidate_id}")

        with storage.transaction(conn):
            if candidate.source_kind == "knowledge":
                current_source = _snapshot_from_sync(
                    sync_object_in_connection(root, conn, candidate.source_ref)
                )
            else:
                current_source = EndpointSnapshot(
                    kind="external",
                    ref=candidate.source_ref,
                    revision=None,
                    fingerprint=None,
                    locator=None,
                )
            if candidate.target_kind == "knowledge":
                current_target = _snapshot_from_sync(
                    sync_object_in_connection(root, conn, candidate.target_ref)
                )
            else:
                current_target = EndpointSnapshot(
                    kind="external",
                    ref=candidate.target_ref,
                    revision=None,
                    fingerprint=None,
                    locator=None,
                )

            stale = (
                candidate.source_kind == "knowledge"
                and current_source.fingerprint != candidate.source_fingerprint
            ) or (
                candidate.target_kind == "knowledge"
                and current_target.fingerprint != candidate.target_fingerprint
            )
            if stale:
                relation_store.mark_relation_candidate_stale(conn, candidate_id)
            else:
                existing = relation_store.get_relation_by_triple(
                    conn,
                    source_ref=candidate.source_ref,
                    relation_type=candidate.relation_type,
                    target_ref=candidate.target_ref,
                )
                if existing is None:
                    relation_identity = str(uuid7())
                    relation_store.create_relation_record_from_candidate(
                        conn,
                        relation_identity=relation_identity,
                        source_ref=candidate.source_ref,
                        relation_type=candidate.relation_type,
                        target_ref=candidate.target_ref,
                        provenance=candidate.provenance,
                        candidate_id=candidate_id,
                    )
                    relation_revision = 1
                    relation_created = True
                    provenance_added = True
                else:
                    relation_identity = existing.identity
                    relation_revision, provenance_added = (
                        relation_store.add_relation_provenance_from_candidate(
                            conn,
                            relation_identity=relation_identity,
                            provenance=candidate.provenance,
                            candidate_id=candidate_id,
                        )
                    )

        if stale:
            raise BootstrapError(
                "Relation Candidate is stale because an endpoint Authority changed; "
                "re-read current Authority and create a new Candidate"
            )

        assert relation_identity is not None
        assert relation_revision is not None
        provenance_entries = relation_store.list_relation_provenance(conn, relation_identity)
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate_id,
        "status": "accepted",
        "relation_identity": relation_identity,
        "relation_revision": relation_revision,
        "relation_created": relation_created,
        "provenance_added": provenance_added,
        "source": candidate.source_ref,
        "type": candidate.relation_type,
        "target": candidate.target_ref,
        "provenance": provenance_entries,
    }


def reject_relation_candidate(
    vault: Path,
    *,
    candidate_id: str,
    confirmed_rejection: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_rejection:
        raise BootstrapError("Rejecting a Relation Candidate requires explicit user rejection")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = relation_store.get_relation_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Relation Candidate does not exist: {candidate_id}")
        if candidate.status != "pending":
            raise BootstrapError(f"Relation Candidate is not pending: {candidate_id}")
        with storage.transaction(conn):
            relation_store.reject_relation_candidate(conn, candidate_id)
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate_id,
        "status": "rejected",
    }
