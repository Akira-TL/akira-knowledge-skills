from __future__ import annotations

from pathlib import Path

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.ids import uuid7
from knowledge_core.persistence import lifecycle as lifecycle_store
from knowledge_core.persistence import review as review_store
from knowledge_core.workflows.maintain import sync_object_in_connection


def _candidate_payload(candidate: review_store.MaintenanceCandidateRecord) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_kind": candidate.candidate_kind,
        "status": candidate.status,
        "target_identity": candidate.target_identity,
        "target_revision": candidate.target_revision,
        "target_fingerprint": candidate.target_fingerprint,
        "source_locator": candidate.source_locator,
        "basis_source_id": candidate.basis_source_id,
        "basis_revision": candidate.basis_revision,
        "basis_fingerprint": candidate.basis_fingerprint,
        "observed_source_id": candidate.observed_source_id,
        "observed_revision": candidate.observed_revision,
        "observed_fingerprint": candidate.observed_fingerprint,
        "evidence": candidate.evidence,
        "source_finding_id": candidate.source_finding_id,
    }


def plan_source_review(
    vault: Path,
    *,
    identity: str,
) -> dict[str, object]:
    root = _vault_root(vault)
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
            raise BootstrapError(
                f"Source review target is not current Knowledge: {identity}"
            )
        sources = review_store.list_target_sources(
            conn,
            target_identity=identity,
        )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "target_identity": identity,
        "target_revision": target.revision,
        "target_fingerprint": target.fingerprint,
        "canonical_locator": target.locator,
        "current_lifecycle": lifecycle,
        "sources": sources,
        "next_step": (
            "verify each Source with source-specific access, "
            "then call maintain-review-source"
        ),
    }


def review_source(
    vault: Path,
    *,
    identity: str,
    source_locator: str,
    basis_source_id: str,
    basis_revision: str,
    basis_fingerprint: str,
    evidence: str,
    unknown: bool,
    observed_source_id: str | None,
    observed_revision: str | None,
    observed_fingerprint: str | None,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not source_locator.strip():
        raise BootstrapError("Source review requires a non-empty source locator")
    if not basis_source_id.strip():
        raise BootstrapError("Source review requires a non-empty basis source identity")
    if not basis_revision.strip():
        raise BootstrapError("Source review requires a non-empty basis revision")
    if not basis_fingerprint.strip():
        raise BootstrapError("Source review requires a non-empty basis fingerprint")
    if not evidence.strip():
        raise BootstrapError("Source review requires concrete evidence")
    observed = (observed_source_id, observed_revision, observed_fingerprint)
    if unknown:
        if any(item is not None for item in observed):
            raise BootstrapError(
                "Unknown Source state cannot include observed source identity/revision/fingerprint"
            )
    elif any(item is None or not item.strip() for item in observed):
        raise BootstrapError(
            "Confirmed Source review requires observed source identity, revision, and fingerprint"
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
            raise BootstrapError(
                f"Source review target is not current Knowledge: {identity}"
            )
        if not review_store.source_in_target_provenance(
            conn,
            target_identity=identity,
            source_locator=source_locator,
        ):
            raise BootstrapError(
                "Source is not in the target Knowledge provenance chain: "
                f"{source_locator}"
            )

        source_state = "unknown"
        if not unknown:
            assert observed_source_id is not None
            assert observed_revision is not None
            assert observed_fingerprint is not None
            if observed_source_id != basis_source_id:
                raise BootstrapError(
                    "Source identity changed during review; "
                    "do not treat a different Source owner as a revision of the original Source"
                )
            source_state = (
                "changed"
                if (
                    observed_revision != basis_revision
                    or observed_fingerprint != basis_fingerprint
                )
                else "unchanged"
            )

        finding_id = str(uuid7())
        candidate_id: str | None = str(uuid7()) if source_state == "changed" else None
        with storage.transaction(conn):
            review_store.insert_source_review(
                conn,
                finding_id=finding_id,
                source_state=source_state,
                target_identity=identity,
                target_revision=target.revision,
                target_fingerprint=target.fingerprint,
                source_locator=source_locator,
                basis_source_id=basis_source_id,
                basis_revision=basis_revision,
                basis_fingerprint=basis_fingerprint,
                observed_source_id=observed_source_id,
                observed_revision=observed_revision,
                observed_fingerprint=observed_fingerprint,
                evidence=evidence.strip(),
            )
            if candidate_id is not None:
                assert observed_source_id is not None
                assert observed_revision is not None
                assert observed_fingerprint is not None
                review_store.insert_source_stale_candidate(
                    conn,
                    candidate_id=candidate_id,
                    finding_id=finding_id,
                    target_identity=identity,
                    target_revision=target.revision,
                    target_fingerprint=target.fingerprint,
                    source_locator=source_locator,
                    basis_source_id=basis_source_id,
                    basis_revision=basis_revision,
                    basis_fingerprint=basis_fingerprint,
                    observed_source_id=observed_source_id,
                    observed_revision=observed_revision,
                    observed_fingerprint=observed_fingerprint,
                    evidence=evidence.strip(),
                )
                candidate = review_store.get_candidate(conn, candidate_id)
                if candidate is None:
                    raise BootstrapError("Source stale candidate could not be read after creation")
            else:
                candidate = None
    finally:
        conn.close()

    return {
        "vault": str(root),
        "finding_id": finding_id,
        "finding_kind": "source_review",
        "source_state": source_state,
        "target_identity": identity,
        "target_revision": target.revision,
        "target_fingerprint": target.fingerprint,
        "canonical_locator": target.locator,
        "source_locator": source_locator,
        "governance_path": (
            "knowledge-curate update proposal or knowledge-maintain lifecycle proposal"
        ),
        "basis": {
            "source_id": basis_source_id,
            "revision": basis_revision,
            "fingerprint": basis_fingerprint,
        },
        "observed": (
            None
            if unknown
            else {
                "source_id": observed_source_id,
                "revision": observed_revision,
                "fingerprint": observed_fingerprint,
            }
        ),
        "evidence": evidence.strip(),
        "candidate": None if candidate is None else _candidate_payload(candidate),
    }


def inspect_review_candidate(
    vault: Path,
    *,
    candidate_id: str,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = review_store.get_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Maintenance candidate does not exist: {candidate_id}")

        target = None
        if candidate.status == "pending":
            with storage.transaction(conn):
                target = sync_object_in_connection(
                    root,
                    conn,
                    candidate.target_identity,
                )
            if target.kind != "knowledge_asset":
                raise BootstrapError(
                    "Maintenance candidate target is not a knowledge asset"
                )
            if (
                target.revision != candidate.target_revision
                or target.fingerprint != candidate.target_fingerprint
            ):
                with storage.transaction(conn):
                    review_store.mark_candidate_stale(conn, candidate_id)
                candidate = review_store.get_candidate(conn, candidate_id)
                if candidate is None:
                    raise BootstrapError(
                        "Maintenance candidate disappeared after stale transition"
                    )
        if target is None:
            with storage.transaction(conn):
                target = sync_object_in_connection(
                    root,
                    conn,
                    candidate.target_identity,
                )
        lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(
            conn,
            candidate.target_identity,
        )
    finally:
        conn.close()

    return {
        "vault": str(root),
        **_candidate_payload(candidate),
        "canonical_locator": target.locator,
        "current_target_revision": target.revision,
        "current_target_fingerprint": target.fingerprint,
        "current_lifecycle": lifecycle,
        "governance_path": (
            "knowledge-curate update proposal or knowledge-maintain lifecycle proposal"
        ),
    }


def reject_review_candidate(
    vault: Path,
    *,
    candidate_id: str,
    confirmed_rejection: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_rejection:
        raise BootstrapError(
            "Rejecting a maintenance candidate requires explicit user rejection"
        )
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = review_store.get_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Maintenance candidate does not exist: {candidate_id}")
        if candidate.status not in {"pending", "stale"}:
            raise BootstrapError(
                f"Maintenance candidate cannot be rejected from status: {candidate.status}"
            )
        with storage.transaction(conn):
            review_store.reject_candidate(conn, candidate_id)
        candidate = review_store.get_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(
                "Maintenance candidate disappeared after rejection"
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        **_candidate_payload(candidate),
    }
