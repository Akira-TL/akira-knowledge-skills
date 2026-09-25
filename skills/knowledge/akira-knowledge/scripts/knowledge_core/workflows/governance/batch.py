from __future__ import annotations

import json
from pathlib import Path

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _vault_root
from knowledge_core.ids import uuid7
from knowledge_core.persistence import authority_edits as authority_edit_store
from knowledge_core.persistence import batch as batch_store
from knowledge_core.persistence import lifecycle as lifecycle_store
from knowledge_core.persistence import relations as relation_store
from knowledge_core.persistence import review as review_store
from knowledge_core.workflows.governance.authority_edits import apply_authority_edit
from knowledge_core.workflows.governance.conflicts import (
    inspect_relation_maintenance_candidate,
)
from knowledge_core.workflows.governance.relation_candidates import (
    approve_relation_candidate,
)
from knowledge_core.workflows.maintain import (
    apply_retire_proposal,
    apply_supersede_proposal,
    apply_update_proposal,
    revoke_relation,
)


def _object_basis(
    conn,
    *,
    item_id: str,
    ordinal: int,
    role: str,
    identity: str,
    expected_revision: int,
) -> batch_store.BatchItemBasisRecord:
    record = storage.get_by_identity(conn, identity)
    if record is None:
        raise BootstrapError(f"Batch basis object does not exist: {identity}")
    if record.revision != expected_revision:
        raise BootstrapError(
            f"Batch basis revision changed before batch creation: {identity}"
        )
    return batch_store.BatchItemBasisRecord(
        item_id=item_id,
        ordinal=ordinal,
        basis_kind="object",
        role=role,
        identity=identity,
        revision=record.revision,
        fingerprint=record.authority_fingerprint,
    )


def _relation_basis(
    *,
    item_id: str,
    ordinal: int,
    role: str,
    identity: str,
    revision: int,
    fingerprint: str,
) -> batch_store.BatchItemBasisRecord:
    return batch_store.BatchItemBasisRecord(
        item_id=item_id,
        ordinal=ordinal,
        basis_kind="relation",
        role=role,
        identity=identity,
        revision=revision,
        fingerprint=fingerprint,
    )


def _item_payload(
    conn,
    item: batch_store.BatchItemRecord,
) -> dict[str, object]:
    result = None if item.result_json is None else json.loads(item.result_json)
    return {
        "item_id": item.item_id,
        "item_kind": item.item_kind,
        "governance_ref": item.governance_ref,
        "target_identity": item.target_identity,
        "relation_identity": item.relation_identity,
        "evidence": item.evidence,
        "proposed_change": item.proposed_change,
        "approval_result": item.approval_result,
        "status": item.status,
        "bases": [
            {
                "basis_kind": basis.basis_kind,
                "role": basis.role,
                "identity": basis.identity,
                "revision": basis.revision,
                "fingerprint": basis.fingerprint,
            }
            for basis in batch_store.list_item_bases(conn, item.item_id)
        ],
        "result": result,
        "error": item.error,
    }


def _batch_payload(conn, batch_id: str) -> dict[str, object]:
    batch = batch_store.get_batch(conn, batch_id)
    if batch is None:
        raise BootstrapError(f"Maintenance batch does not exist: {batch_id}")
    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "items": [
            _item_payload(conn, item)
            for item in batch_store.list_batch_items(conn, batch_id)
        ],
    }


def _add_update_item(
    conn,
    *,
    batch_id: str,
    ordinal: int,
    proposal_id: str,
) -> None:
    proposal = storage.get_proposal(conn, proposal_id)
    if (
        proposal is None
        or proposal.status != "pending"
        or proposal.proposal_kind != "update"
        or proposal.target_identity is None
        or proposal.base_revision is None
    ):
        raise BootstrapError(
            f"Batch update governance ref is not a pending update proposal: {proposal_id}"
        )
    item_id = str(uuid7())
    bases = [
        _object_basis(
            conn,
            item_id=item_id,
            ordinal=0,
            role="target",
            identity=proposal.target_identity,
            expected_revision=proposal.base_revision,
        )
    ]
    materials = storage.get_proposal_materials(conn, proposal_id)
    for basis_ordinal, (material_identity, basis_revision) in enumerate(
        materials, start=1
    ):
        bases.append(
            _object_basis(
                conn,
                item_id=item_id,
                ordinal=basis_ordinal,
                role="material",
                identity=material_identity,
                expected_revision=basis_revision,
            )
        )
    batch_store.insert_batch_item(
        conn,
        item_id=item_id,
        batch_id=batch_id,
        ordinal=ordinal,
        item_kind="knowledge_update",
        governance_ref=proposal_id,
        target_identity=proposal.target_identity,
        relation_identity=None,
        evidence=(
            "existing update proposal materials: "
            + ", ".join(identity for identity, _ in materials)
        ),
        proposed_change=f"apply existing Knowledge update proposal {proposal_id}",
        bases=bases,
    )


def _add_lifecycle_item(
    conn,
    *,
    batch_id: str,
    ordinal: int,
    proposal_id: str,
    expected_kind: str,
) -> None:
    proposal = lifecycle_store.get_lifecycle_proposal(conn, proposal_id)
    if (
        proposal is None
        or proposal.status != "pending"
        or proposal.proposal_kind != expected_kind
    ):
        raise BootstrapError(
            f"Batch lifecycle governance ref is not a pending {expected_kind} proposal: "
            f"{proposal_id}"
        )
    item_id = str(uuid7())
    bases = [
        _object_basis(
            conn,
            item_id=item_id,
            ordinal=0,
            role="target",
            identity=proposal.target_identity,
            expected_revision=proposal.base_revision,
        )
    ]
    proposed_change = f"{expected_kind} Knowledge Asset {proposal.target_identity}"
    if expected_kind == "supersede":
        if (
            proposal.replacement_identity is None
            or proposal.replacement_revision is None
        ):
            raise BootstrapError("Supersede proposal is missing replacement basis")
        bases.append(
            _object_basis(
                conn,
                item_id=item_id,
                ordinal=1,
                role="replacement",
                identity=proposal.replacement_identity,
                expected_revision=proposal.replacement_revision,
            )
        )
        proposed_change += f" by {proposal.replacement_identity}"
    batch_store.insert_batch_item(
        conn,
        item_id=item_id,
        batch_id=batch_id,
        ordinal=ordinal,
        item_kind=(
            "lifecycle_retire"
            if expected_kind == "retire"
            else "lifecycle_supersede"
        ),
        governance_ref=proposal_id,
        target_identity=proposal.target_identity,
        relation_identity=None,
        evidence=proposal.reason,
        proposed_change=proposed_change,
        bases=bases,
    )


def _add_authority_edit_item(
    conn,
    *,
    batch_id: str,
    ordinal: int,
    proposal_id: str,
) -> None:
    proposal = authority_edit_store.get_authority_edit_proposal(conn, proposal_id)
    if proposal is None or proposal.status != "pending":
        raise BootstrapError(
            "Batch authority-edit governance ref is not a pending proposal: "
            f"{proposal_id}"
        )
    item_id = str(uuid7())
    bases = [
        _object_basis(
            conn,
            item_id=item_id,
            ordinal=0,
            role="target",
            identity=proposal.target_identity,
            expected_revision=proposal.base_revision,
        )
    ]
    batch_store.insert_batch_item(
        conn,
        item_id=item_id,
        batch_id=batch_id,
        ordinal=ordinal,
        item_kind="authority_edit",
        governance_ref=proposal_id,
        target_identity=proposal.target_identity,
        relation_identity=None,
        evidence=proposal.reason,
        proposed_change=(
            f"apply existing {proposal.edit_kind} authority-edit proposal "
            f"{proposal_id}"
        ),
        bases=bases,
    )


def _add_relation_candidate_item(
    conn,
    *,
    batch_id: str,
    ordinal: int,
    candidate_id: str,
) -> None:
    candidate = relation_store.get_relation_candidate(conn, candidate_id)
    if candidate is None or candidate.status != "pending":
        raise BootstrapError(
            f"Batch Relation Candidate is not pending: {candidate_id}"
        )
    item_id = str(uuid7())
    bases: list[batch_store.BatchItemBasisRecord] = []
    for role, kind, ref, revision, fingerprint in (
        (
            "source",
            candidate.source_kind,
            candidate.source_ref,
            candidate.source_revision,
            candidate.source_fingerprint,
        ),
        (
            "target",
            candidate.target_kind,
            candidate.target_ref,
            candidate.target_revision,
            candidate.target_fingerprint,
        ),
    ):
        if kind != "knowledge":
            continue
        if revision is None or fingerprint is None:
            raise BootstrapError(
                f"Relation Candidate local {role} is missing revision/fingerprint basis"
            )
        basis = _object_basis(
            conn,
            item_id=item_id,
            ordinal=len(bases),
            role=role,
            identity=ref,
            expected_revision=revision,
        )
        if basis.fingerprint != fingerprint:
            raise BootstrapError(
                f"Relation Candidate local {role} fingerprint changed before batch creation"
            )
        bases.append(basis)
    batch_store.insert_batch_item(
        conn,
        item_id=item_id,
        batch_id=batch_id,
        ordinal=ordinal,
        item_kind="relation_candidate",
        governance_ref=candidate_id,
        target_identity=None,
        relation_identity=None,
        evidence=candidate.provenance,
        proposed_change=(
            f"approve Relation Candidate {candidate.source_ref} "
            f"{candidate.relation_type} {candidate.target_ref}"
        ),
        bases=bases,
    )


def _add_relation_revoke_item(
    conn,
    *,
    batch_id: str,
    ordinal: int,
    candidate_id: str,
) -> None:
    candidate = review_store.get_relation_maintenance_candidate(
        conn, candidate_id
    )
    if candidate is None or candidate.status != "pending":
        raise BootstrapError(
            f"Batch relation maintenance candidate is not pending: {candidate_id}"
        )
    relation = relation_store.get_relation_record(
        conn, candidate.relation_identity
    )
    if (
        relation is None
        or relation.status != "active"
        or relation.revision != candidate.relation_revision
    ):
        raise BootstrapError(
            "Relation maintenance candidate basis changed before batch creation"
        )
    item_id = str(uuid7())
    bases = [
        _relation_basis(
            item_id=item_id,
            ordinal=0,
            role="relation",
            identity=candidate.relation_identity,
            revision=candidate.relation_revision,
            fingerprint=candidate.relation_fingerprint,
        )
    ]
    for role, kind, ref, revision, fingerprint in (
        (
            "source",
            candidate.source_kind,
            candidate.source_ref,
            candidate.source_revision,
            candidate.source_fingerprint,
        ),
        (
            "target",
            candidate.target_kind,
            candidate.target_ref,
            candidate.target_revision,
            candidate.target_fingerprint,
        ),
    ):
        if kind == "knowledge":
            if revision is None or fingerprint is None:
                raise BootstrapError(
                    f"Relation maintenance {role} basis is incomplete"
                )
            basis = _object_basis(
                conn,
                item_id=item_id,
                ordinal=len(bases),
                role=role,
                identity=ref,
                expected_revision=revision,
            )
            if basis.fingerprint != fingerprint:
                raise BootstrapError(
                    f"Relation maintenance {role} fingerprint changed before batch creation"
                )
            bases.append(basis)
    if (
        candidate.evidence_basis_identity is not None
        and candidate.evidence_basis_revision is not None
        and candidate.evidence_basis_fingerprint is not None
    ):
        evidence_basis = _object_basis(
            conn,
            item_id=item_id,
            ordinal=len(bases),
            role="evidence",
            identity=candidate.evidence_basis_identity,
            expected_revision=candidate.evidence_basis_revision,
        )
        if evidence_basis.fingerprint != candidate.evidence_basis_fingerprint:
            raise BootstrapError(
                "Relation maintenance evidence basis changed before batch creation"
            )
        bases.append(evidence_basis)
    batch_store.insert_batch_item(
        conn,
        item_id=item_id,
        batch_id=batch_id,
        ordinal=ordinal,
        item_kind="relation_revoke",
        governance_ref=candidate_id,
        target_identity=None,
        relation_identity=candidate.relation_identity,
        evidence=candidate.evidence,
        proposed_change=(
            "revoke Relation Record through existing expected-revision governance "
            f"{candidate.relation_identity}"
        ),
        bases=bases,
    )


def create_batch(
    vault: Path,
    *,
    update_proposals: list[str],
    retire_proposals: list[str],
    supersede_proposals: list[str],
    authority_edit_proposals: list[str],
    relation_candidates: list[str],
    relation_revoke_candidates: list[str],
) -> dict[str, object]:
    root = _vault_root(vault)
    refs = (
        len(update_proposals)
        + len(retire_proposals)
        + len(supersede_proposals)
        + len(authority_edit_proposals)
        + len(relation_candidates)
        + len(relation_revoke_candidates)
    )
    if refs == 0:
        raise BootstrapError("Maintenance batch requires at least one governed item")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        batch_id = str(uuid7())
        with storage.transaction(conn):
            batch_store.insert_batch(conn, batch_id=batch_id)
            ordinal = 0
            for proposal_id in update_proposals:
                _add_update_item(
                    conn,
                    batch_id=batch_id,
                    ordinal=ordinal,
                    proposal_id=proposal_id,
                )
                ordinal += 1
            for proposal_id in retire_proposals:
                _add_lifecycle_item(
                    conn,
                    batch_id=batch_id,
                    ordinal=ordinal,
                    proposal_id=proposal_id,
                    expected_kind="retire",
                )
                ordinal += 1
            for proposal_id in supersede_proposals:
                _add_lifecycle_item(
                    conn,
                    batch_id=batch_id,
                    ordinal=ordinal,
                    proposal_id=proposal_id,
                    expected_kind="supersede",
                )
                ordinal += 1
            for proposal_id in authority_edit_proposals:
                _add_authority_edit_item(
                    conn,
                    batch_id=batch_id,
                    ordinal=ordinal,
                    proposal_id=proposal_id,
                )
                ordinal += 1
            for candidate_id in relation_candidates:
                _add_relation_candidate_item(
                    conn,
                    batch_id=batch_id,
                    ordinal=ordinal,
                    candidate_id=candidate_id,
                )
                ordinal += 1
            for candidate_id in relation_revoke_candidates:
                _add_relation_revoke_item(
                    conn,
                    batch_id=batch_id,
                    ordinal=ordinal,
                    candidate_id=candidate_id,
                )
                ordinal += 1
        return {
            "vault": str(root),
            **_batch_payload(conn, batch_id),
        }
    finally:
        conn.close()


def approve_batch(
    vault: Path,
    *,
    batch_id: str,
    item_ids: list[str],
    confirmed_approval: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_approval:
        raise BootstrapError(
            "Approving a maintenance batch subset requires explicit user approval"
        )
    if not item_ids:
        raise BootstrapError("Maintenance batch approval requires at least one item")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            batch_store.approve_batch_subset(
                conn,
                batch_id=batch_id,
                approved_item_ids=set(item_ids),
            )
        return {
            "vault": str(root),
            **_batch_payload(conn, batch_id),
        }
    finally:
        conn.close()


def _execute_governed_item(
    root: Path,
    item: batch_store.BatchItemRecord,
) -> dict[str, object]:
    if item.item_kind == "knowledge_update":
        return apply_update_proposal(
            root,
            proposal_id=item.governance_ref,
            confirmed_approval=True,
        )
    if item.item_kind == "lifecycle_retire":
        return apply_retire_proposal(
            root,
            proposal_id=item.governance_ref,
            confirmed_approval=True,
        )
    if item.item_kind == "lifecycle_supersede":
        return apply_supersede_proposal(
            root,
            proposal_id=item.governance_ref,
            confirmed_approval=True,
        )
    if item.item_kind == "authority_edit":
        return apply_authority_edit(
            root,
            proposal_id=item.governance_ref,
            confirmed_approval=True,
        )
    if item.item_kind == "relation_candidate":
        return approve_relation_candidate(
            root,
            candidate_id=item.governance_ref,
            confirmed_approval=True,
        )
    if item.item_kind == "relation_revoke":
        if item.relation_identity is None:
            raise BootstrapError("Batch relation revoke item is missing relation identity")
        inspected = inspect_relation_maintenance_candidate(
            root,
            candidate_id=item.governance_ref,
        )
        if inspected["status"] != "pending":
            raise BootstrapError(
                "Relation maintenance candidate is stale; "
                "re-review current relation/endpoint/evidence Authority"
            )
        return revoke_relation(
            root,
            relation_identity=item.relation_identity,
            expected_revision=int(inspected["relation_revision"]),
            confirmed_revoke=True,
        )
    raise BootstrapError(f"Unsupported maintenance batch item kind: {item.item_kind}")


def _is_stale_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "stale",
            "revision changed",
            "authority changed",
            "fingerprint changed",
            "is not current",
        )
    )


def execute_batch(
    vault: Path,
    *,
    batch_id: str,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        batch = batch_store.get_batch(conn, batch_id)
        if batch is None:
            raise BootstrapError(f"Maintenance batch does not exist: {batch_id}")
        if batch.status not in {"approved", "partial", "completed"}:
            raise BootstrapError(
                f"Maintenance batch is not approved for execution: {batch_id}"
            )
        items = batch_store.list_batch_items(conn, batch_id)
    finally:
        conn.close()

    for item in items:
        if item.status != "approved":
            continue

        try:
            result = _execute_governed_item(root, item)
        except Exception as exc:
            error = str(exc)
            status = "stale" if _is_stale_error(error) else "failed"
            conn = storage.connect(root)
            try:
                storage.initialize_schema(conn)
                with storage.transaction(conn):
                    batch_store.record_item_execution(
                        conn,
                        item_id=item.item_id,
                        status=status,
                        result_json=None,
                        error=error,
                    )
            finally:
                conn.close()
            continue

        conn = storage.connect(root)
        try:
            storage.initialize_schema(conn)
            with storage.transaction(conn):
                batch_store.record_item_execution(
                    conn,
                    item_id=item.item_id,
                    status="succeeded",
                    result_json=json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    error=None,
                )
        finally:
            conn.close()

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        batch = batch_store.get_batch(conn, batch_id)
        if batch is None:
            raise BootstrapError(f"Maintenance batch does not exist: {batch_id}")
        if batch.status == "approved":
            with storage.transaction(conn):
                batch_store.finalize_batch_execution(
                    conn,
                    batch_id=batch_id,
                )
        return {
            "vault": str(root),
            **_batch_payload(conn, batch_id),
        }
    finally:
        conn.close()
