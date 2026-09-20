from __future__ import annotations

import hashlib
import json
from pathlib import Path

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.ids import uuid7
from knowledge_core.persistence import lifecycle as lifecycle_store
from knowledge_core.persistence import relations as relation_store
from knowledge_core.persistence import review as review_store
from knowledge_core.workflows.maintain import sync_object_in_connection


def _relation_fingerprint(conn, relation) -> str:
    provenance = relation_store.list_relation_provenance(conn, relation.identity)
    payload = json.dumps(
        {
            "identity": relation.identity,
            "source": relation.source_ref,
            "type": relation.relation_type,
            "target": relation.target_ref,
            "provenance": provenance,
            "revision": relation.revision,
            "status": relation.status,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _knowledge_conflict_member(
    root: Path,
    conn,
    *,
    candidate_id: str,
    ordinal: int,
    identity: str,
) -> review_store.ConflictCandidateMemberRecord:
    item = sync_object_in_connection(root, conn, identity)
    if item.kind != "knowledge_asset":
        raise BootstrapError(f"Conflict member is not a Knowledge Asset: {identity}")
    lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(conn, identity)
    if lifecycle != "current":
        raise BootstrapError(f"Conflict member is not current Knowledge: {identity}")
    return review_store.ConflictCandidateMemberRecord(
        candidate_id=candidate_id,
        ordinal=ordinal,
        member_kind="knowledge_asset",
        member_ref=item.identity,
        basis_identity=item.identity,
        revision=item.revision,
        fingerprint=item.fingerprint,
        canonical_locator=item.locator,
    )


def _source_finding_conflict_member(
    root: Path,
    conn,
    *,
    candidate_id: str,
    ordinal: int,
    finding_id: str,
) -> review_store.ConflictCandidateMemberRecord:
    finding = review_store.get_source_finding(conn, finding_id)
    if finding is None:
        raise BootstrapError(f"Source Review finding does not exist: {finding_id}")
    target = sync_object_in_connection(root, conn, finding.target_identity)
    lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(
        conn, finding.target_identity
    )
    if target.kind != "knowledge_asset" or lifecycle != "current":
        raise BootstrapError(
            f"Source Review finding target is not current Knowledge: {finding.target_identity}"
        )
    if (
        target.revision != finding.target_revision
        or target.fingerprint != finding.target_fingerprint
    ):
        raise BootstrapError(
            "Source Review finding basis is stale; re-review the Source before using it in a conflict"
        )
    return review_store.ConflictCandidateMemberRecord(
        candidate_id=candidate_id,
        ordinal=ordinal,
        member_kind="source_finding",
        member_ref=finding.finding_id,
        basis_identity=finding.target_identity,
        revision=finding.target_revision,
        fingerprint=finding.target_fingerprint,
        canonical_locator=finding.source_locator,
    )


def _relation_conflict_member(
    conn,
    *,
    candidate_id: str,
    ordinal: int,
    relation_identity: str,
) -> review_store.ConflictCandidateMemberRecord:
    relation = relation_store.get_relation_record(conn, relation_identity)
    if relation is None:
        raise BootstrapError(f"Relation Record does not exist: {relation_identity}")
    if relation.status != "active":
        raise BootstrapError(f"Relation Record is not active: {relation_identity}")
    return review_store.ConflictCandidateMemberRecord(
        candidate_id=candidate_id,
        ordinal=ordinal,
        member_kind="relation_record",
        member_ref=relation.identity,
        basis_identity=relation.identity,
        revision=relation.revision,
        fingerprint=_relation_fingerprint(conn, relation),
        canonical_locator=f"relation:{relation.identity}",
    )


def propose_conflict(
    vault: Path,
    *,
    knowledge_ids: list[str],
    source_finding_ids: list[str],
    relation_ids: list[str],
    conflict: str,
    evidence: str,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not conflict.strip():
        raise BootstrapError("Conflict candidate requires a non-empty conflict statement")
    if not evidence.strip():
        raise BootstrapError("Conflict candidate requires concrete evidence")

    ordered_knowledge = list(dict.fromkeys(knowledge_ids))
    ordered_findings = list(dict.fromkeys(source_finding_ids))
    ordered_relations = list(dict.fromkeys(relation_ids))
    member_keys = (
        [("knowledge_asset", item) for item in ordered_knowledge]
        + [("source_finding", item) for item in ordered_findings]
        + [("relation_record", item) for item in ordered_relations]
    )
    if len(member_keys) < 2:
        raise BootstrapError(
            "Conflict candidate requires at least two distinct review members"
        )
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate_id = str(uuid7())
        members: list[review_store.ConflictCandidateMemberRecord] = []
        with storage.transaction(conn):
            ordinal = 0
            for identity in ordered_knowledge:
                members.append(
                    _knowledge_conflict_member(
                        root,
                        conn,
                        candidate_id=candidate_id,
                        ordinal=ordinal,
                        identity=identity,
                    )
                )
                ordinal += 1
            for finding_id in ordered_findings:
                members.append(
                    _source_finding_conflict_member(
                        root,
                        conn,
                        candidate_id=candidate_id,
                        ordinal=ordinal,
                        finding_id=finding_id,
                    )
                )
                ordinal += 1
            for relation_identity in ordered_relations:
                members.append(
                    _relation_conflict_member(
                        conn,
                        candidate_id=candidate_id,
                        ordinal=ordinal,
                        relation_identity=relation_identity,
                    )
                )
                ordinal += 1
        with storage.transaction(conn):
            review_store.insert_conflict_candidate(
                conn,
                candidate_id=candidate_id,
                conflict=conflict.strip(),
                evidence=evidence.strip(),
                members=members,
            )
        candidate = review_store.get_conflict_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError("Conflict candidate could not be read after creation")
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": "semantic_conflict",
        "status": candidate.status,
        "conflict": candidate.conflict,
        "evidence": candidate.evidence,
        "members": [
            {
                "member_kind": member.member_kind,
                "identity": member.member_ref,
                "member_ref": member.member_ref,
                "basis_identity": member.basis_identity,
                "revision": member.revision,
                "fingerprint": member.fingerprint,
                "canonical_locator": member.canonical_locator,
            }
            for member in members
        ],
    }


def _current_conflict_member(
    root: Path,
    conn,
    member: review_store.ConflictCandidateMemberRecord,
) -> tuple[review_store.ConflictCandidateMemberRecord, bool]:
    if member.member_kind == "knowledge_asset":
        current = _knowledge_conflict_member(
            root,
            conn,
            candidate_id=member.candidate_id,
            ordinal=member.ordinal,
            identity=member.member_ref,
        )
        stale = (
            current.basis_identity != member.basis_identity
            or current.revision != member.revision
            or current.fingerprint != member.fingerprint
        )
        return current, stale

    if member.member_kind == "source_finding":
        current = _source_finding_conflict_member(
            root,
            conn,
            candidate_id=member.candidate_id,
            ordinal=member.ordinal,
            finding_id=member.member_ref,
        )
        stale = (
            current.basis_identity != member.basis_identity
            or current.revision != member.revision
            or current.fingerprint != member.fingerprint
        )
        return current, stale

    if member.member_kind == "relation_record":
        current = _relation_conflict_member(
            conn,
            candidate_id=member.candidate_id,
            ordinal=member.ordinal,
            relation_identity=member.member_ref,
        )
        stale = (
            current.revision != member.revision
            or current.fingerprint != member.fingerprint
        )
        return current, stale

    raise BootstrapError(
        f"Unsupported conflict candidate member kind: {member.member_kind}"
    )


def inspect_conflict_candidate(
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
        candidate = review_store.get_conflict_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Conflict candidate does not exist: {candidate_id}")
        stored_members = review_store.list_conflict_candidate_members(
            conn, candidate_id
        )
        current_members: list[review_store.ConflictCandidateMemberRecord] = []
        stale = False
        with storage.transaction(conn):
            for member in stored_members:
                current, member_stale = _current_conflict_member(
                    root, conn, member
                )
                current_members.append(current)
                stale = stale or member_stale
            if candidate.status == "pending" and stale:
                review_store.mark_conflict_candidate_stale(conn, candidate_id)
        candidate = review_store.get_conflict_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(
                "Conflict candidate disappeared during inspection"
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": "semantic_conflict",
        "status": candidate.status,
        "conflict": candidate.conflict,
        "evidence": candidate.evidence,
        "members": [
            {
                "member_kind": member.member_kind,
                "member_ref": member.member_ref,
                "basis_identity": member.basis_identity,
                "revision": member.revision,
                "fingerprint": member.fingerprint,
                "canonical_locator": member.canonical_locator,
            }
            for member in stored_members
        ],
        "current_members": [
            {
                "member_kind": member.member_kind,
                "member_ref": member.member_ref,
                "basis_identity": member.basis_identity,
                "revision": member.revision,
                "fingerprint": member.fingerprint,
                "canonical_locator": member.canonical_locator,
            }
            for member in current_members
        ],
    }


def reject_conflict_candidate(
    vault: Path,
    *,
    candidate_id: str,
    confirmed_rejection: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_rejection:
        raise BootstrapError(
            "Rejecting a conflict candidate requires explicit user rejection"
        )
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = review_store.get_conflict_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(f"Conflict candidate does not exist: {candidate_id}")
        if candidate.status not in {"pending", "stale"}:
            raise BootstrapError(
                f"Conflict candidate cannot be rejected from status: {candidate.status}"
            )
        with storage.transaction(conn):
            review_store.reject_conflict_candidate(conn, candidate_id)
        candidate = review_store.get_conflict_candidate(conn, candidate_id)
        if candidate is None:
            raise BootstrapError(
                "Conflict candidate disappeared after rejection"
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": "semantic_conflict",
        "status": candidate.status,
        "conflict": candidate.conflict,
        "evidence": candidate.evidence,
    }


def _relation_endpoint_basis(root: Path, conn, ref: str) -> dict[str, object]:
    record = storage.get_by_identity(conn, ref)
    if record is None:
        return {
            "kind": "external",
            "ref": ref,
            "revision": None,
            "fingerprint": None,
        }
    synced = sync_object_in_connection(root, conn, ref)
    return {
        "kind": "knowledge",
        "ref": ref,
        "revision": synced.revision,
        "fingerprint": synced.fingerprint,
    }


def propose_relation_maintenance(
    vault: Path,
    *,
    relation_identity: str,
    candidate_kind: str,
    evidence: str,
    source_finding_id: str | None = None,
) -> dict[str, object]:
    root = _vault_root(vault)
    if candidate_kind not in {"relation_stale", "relation_conflict"}:
        raise BootstrapError(
            "Relation maintenance kind must be relation_stale or relation_conflict"
        )
    if not evidence.strip():
        raise BootstrapError("Relation maintenance candidate requires concrete evidence")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        relation = relation_store.get_relation_record(conn, relation_identity)
        if relation is None:
            raise BootstrapError(
                f"Relation Record does not exist: {relation_identity}"
            )
        if relation.status != "active":
            raise BootstrapError(
                f"Relation Record is not active: {relation_identity}"
            )
        candidate_id = str(uuid7())
        evidence_member = None
        with storage.transaction(conn):
            source = _relation_endpoint_basis(root, conn, relation.source_ref)
            target = _relation_endpoint_basis(root, conn, relation.target_ref)
            if source_finding_id is not None:
                evidence_member = _source_finding_conflict_member(
                    root,
                    conn,
                    candidate_id=candidate_id,
                    ordinal=0,
                    finding_id=source_finding_id,
                )
        relation_fingerprint = _relation_fingerprint(conn, relation)
        with storage.transaction(conn):
            review_store.insert_relation_maintenance_candidate(
                conn,
                candidate_id=candidate_id,
                candidate_kind=candidate_kind,
                relation_identity=relation.identity,
                relation_revision=relation.revision,
                relation_fingerprint=relation_fingerprint,
                source_kind=str(source["kind"]),
                source_ref=str(source["ref"]),
                source_revision=source["revision"],
                source_fingerprint=source["fingerprint"],
                target_kind=str(target["kind"]),
                target_ref=str(target["ref"]),
                target_revision=target["revision"],
                target_fingerprint=target["fingerprint"],
                evidence=evidence.strip(),
                source_finding_id=None if evidence_member is None else evidence_member.member_ref,
                evidence_basis_identity=None if evidence_member is None else evidence_member.basis_identity,
                evidence_basis_revision=None if evidence_member is None else evidence_member.revision,
                evidence_basis_fingerprint=None if evidence_member is None else evidence_member.fingerprint,
            )
        candidate = review_store.get_relation_maintenance_candidate(
            conn, candidate_id
        )
        if candidate is None:
            raise BootstrapError(
                "Relation maintenance candidate could not be read after creation"
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": candidate.candidate_kind,
        "status": candidate.status,
        "relation_identity": candidate.relation_identity,
        "relation_revision": candidate.relation_revision,
        "relation_fingerprint": candidate.relation_fingerprint,
        "source": source,
        "target": target,
        "evidence": candidate.evidence,
        "source_finding": (
            None
            if evidence_member is None
            else {
                "finding_id": evidence_member.member_ref,
                "basis_identity": evidence_member.basis_identity,
                "revision": evidence_member.revision,
                "fingerprint": evidence_member.fingerprint,
                "source_locator": evidence_member.canonical_locator,
            }
        ),
        "revoke_governance": "relation-revoke with expected revision",
        "replacement_governance": "relation-propose -> relation-approve",
    }


def inspect_relation_maintenance_candidate(
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
        candidate = review_store.get_relation_maintenance_candidate(
            conn, candidate_id
        )
        if candidate is None:
            raise BootstrapError(
                f"Relation maintenance candidate does not exist: {candidate_id}"
            )

        relation = relation_store.get_relation_record(
            conn, candidate.relation_identity
        )
        relation_stale = (
            relation is None
            or relation.status != "active"
        )
        current_evidence = None
        evidence_stale = False
        with storage.transaction(conn):
            current_source = _relation_endpoint_basis(
                root, conn, candidate.source_ref
            )
            current_target = _relation_endpoint_basis(
                root, conn, candidate.target_ref
            )
            if candidate.source_finding_id is not None:
                finding = review_store.get_source_finding(
                    conn, candidate.source_finding_id
                )
                if finding is None:
                    evidence_stale = True
                else:
                    evidence_target = sync_object_in_connection(
                        root, conn, finding.target_identity
                    )
                    evidence_lifecycle = lifecycle_store.get_knowledge_asset_lifecycle(
                        conn, finding.target_identity
                    )
                    current_evidence = {
                        "finding_id": finding.finding_id,
                        "basis_identity": finding.target_identity,
                        "revision": evidence_target.revision,
                        "fingerprint": evidence_target.fingerprint,
                        "source_locator": finding.source_locator,
                        "lifecycle": evidence_lifecycle,
                    }
                    evidence_stale = (
                        finding.target_identity != candidate.evidence_basis_identity
                        or finding.target_revision != candidate.evidence_basis_revision
                        or finding.target_fingerprint != candidate.evidence_basis_fingerprint
                        or evidence_target.revision != candidate.evidence_basis_revision
                        or evidence_target.fingerprint != candidate.evidence_basis_fingerprint
                        or evidence_lifecycle != "current"
                    )
        if relation is not None:
            current_relation_fingerprint = _relation_fingerprint(conn, relation)
            relation_stale = relation_stale or (
                relation.revision != candidate.relation_revision
                or current_relation_fingerprint
                != candidate.relation_fingerprint
            )
        else:
            current_relation_fingerprint = None

        endpoint_stale = (
            current_source["kind"] != candidate.source_kind
            or current_source["revision"] != candidate.source_revision
            or current_source["fingerprint"] != candidate.source_fingerprint
            or current_target["kind"] != candidate.target_kind
            or current_target["revision"] != candidate.target_revision
            or current_target["fingerprint"] != candidate.target_fingerprint
        )
        if candidate.status == "pending" and (
            relation_stale or endpoint_stale or evidence_stale
        ):
            with storage.transaction(conn):
                review_store.mark_relation_maintenance_candidate_stale(
                    conn, candidate_id
                )
            candidate = review_store.get_relation_maintenance_candidate(
                conn, candidate_id
            )
            if candidate is None:
                raise BootstrapError(
                    "Relation maintenance candidate disappeared after stale transition"
                )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": candidate.candidate_kind,
        "status": candidate.status,
        "relation_identity": candidate.relation_identity,
        "relation_revision": candidate.relation_revision,
        "relation_fingerprint": candidate.relation_fingerprint,
        "current_relation_revision": None if relation is None else relation.revision,
        "current_relation_fingerprint": current_relation_fingerprint,
        "source": {
            "kind": candidate.source_kind,
            "ref": candidate.source_ref,
            "revision": candidate.source_revision,
            "fingerprint": candidate.source_fingerprint,
        },
        "target": {
            "kind": candidate.target_kind,
            "ref": candidate.target_ref,
            "revision": candidate.target_revision,
            "fingerprint": candidate.target_fingerprint,
        },
        "current_source": current_source,
        "current_target": current_target,
        "evidence": candidate.evidence,
        "source_finding": (
            None
            if candidate.source_finding_id is None
            else {
                "finding_id": candidate.source_finding_id,
                "basis_identity": candidate.evidence_basis_identity,
                "revision": candidate.evidence_basis_revision,
                "fingerprint": candidate.evidence_basis_fingerprint,
            }
        ),
        "current_source_finding": current_evidence,
        "revoke_governance": "relation-revoke with expected revision",
        "replacement_governance": "relation-propose -> relation-approve",
    }


def reject_relation_maintenance_candidate(
    vault: Path,
    *,
    candidate_id: str,
    confirmed_rejection: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_rejection:
        raise BootstrapError(
            "Rejecting a relation maintenance candidate requires explicit user rejection"
        )
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        candidate = review_store.get_relation_maintenance_candidate(
            conn, candidate_id
        )
        if candidate is None:
            raise BootstrapError(
                f"Relation maintenance candidate does not exist: {candidate_id}"
            )
        if candidate.status not in {"pending", "stale"}:
            raise BootstrapError(
                "Relation maintenance candidate cannot be rejected "
                f"from status: {candidate.status}"
            )
        with storage.transaction(conn):
            review_store.reject_relation_maintenance_candidate(
                conn, candidate_id
            )
        candidate = review_store.get_relation_maintenance_candidate(
            conn, candidate_id
        )
        if candidate is None:
            raise BootstrapError(
                "Relation maintenance candidate disappeared after rejection"
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": candidate.candidate_kind,
        "status": candidate.status,
        "relation_identity": candidate.relation_identity,
        "evidence": candidate.evidence,
    }
