from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _safe_relative, _vault_root, _within_scope, _write_atomic
from knowledge_core.ids import uuid7
from knowledge_core.markdown import AK_ID, AK_KIND, AK_STATUS, MarkdownConflict, authority_fingerprint, create_knowledge_asset_markdown, registration_values, replace_knowledge_property
from knowledge_core.workflows.maintain import sync_object_in_connection
from knowledge_core.writing import compare_human_readable_knowledge, format_writing_findings, inspect_human_readable_knowledge


@dataclass(frozen=True)
class MaterialProcessingPlan:
    identity: str
    locator: str
    original: str
    transformed: str
    fingerprint: str
    status: str
    revision: int


def create_curate_proposal(
    vault: Path,
    *,
    proposed_body: str,
    material_ids: Sequence[str],
    target_identity: str | None = None,
    expected_base_revision: int | None = None,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not proposed_body:
        raise BootstrapError("Curate proposal body must not be empty")
    writing_review: dict[str, object] | None = None
    if target_identity is None:
        writing_review = inspect_human_readable_knowledge(proposed_body)
        if writing_review["errors"]:
            raise BootstrapError(
                "Curate proposal violates the Human-readable Knowledge Writing Contract: "
                + format_writing_findings(writing_review["errors"])
            )
        if writing_review["warnings"]:
            raise BootstrapError(
                "Curate proposal still has Human-readable Writing findings: "
                + format_writing_findings(writing_review["warnings"])
            )
    if not material_ids:
        raise BootstrapError("Curate proposal requires at least one material record")
    material_ids = tuple(dict.fromkeys(material_ids))
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            material_syncs = [
                sync_object_in_connection(root, conn, identity)
                for identity in material_ids
            ]
            target_sync = (
                sync_object_in_connection(root, conn, target_identity)
                if target_identity is not None
                else None
            )

        material_bases: list[tuple[str, int]] = []
        for result in material_syncs:
            if result.kind != "material_record":
                raise BootstrapError(f"Material record does not exist: {result.identity}")
            material_bases.append((result.identity, result.revision))

        proposal_kind = "create"
        base_revision: int | None = None
        if target_sync is not None:
            if target_sync.kind != "knowledge_asset":
                raise BootstrapError(f"Knowledge asset does not exist: {target_sync.identity}")
            if expected_base_revision is None:
                raise BootstrapError(
                    "Update proposal requires the base revision that was actually read"
                )
            if target_sync.revision != expected_base_revision:
                raise BootstrapError(
                    "Target revision changed during proposal preparation; "
                    "re-read current Authority and create a new proposal"
                )
            proposal_kind = "update"
            base_revision = expected_base_revision
            writing_review = compare_human_readable_knowledge(
                target_sync.text,
                proposed_body,
            )
            regression_errors = writing_review["regressions"]["errors"]
            if regression_errors:
                raise BootstrapError(
                    "Curate update proposal introduces Human-readable Writing regressions: "
                    + format_writing_findings(regression_errors)
                )
            regression_warnings = writing_review["regressions"]["warnings"]
            if regression_warnings:
                raise BootstrapError(
                    "Curate update proposal introduces Human-readable Writing findings: "
                    + format_writing_findings(regression_warnings)
                )
        elif expected_base_revision is not None:
            raise BootstrapError("base revision is only valid for an update proposal")

        proposal_id = str(uuid7())
        with storage.transaction(conn):
            storage.insert_proposal(
                conn,
                proposal_id=proposal_id,
                proposal_kind=proposal_kind,
                proposed_body=proposed_body,
                material_bases=material_bases,
                target_identity=target_identity,
                base_revision=base_revision,
            )
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "proposal_kind": proposal_kind,
        "status": "pending",
        "target_identity": target_identity,
        "base_revision": base_revision,
        "material_bases": [
            {"identity": identity, "revision": revision}
            for identity, revision in material_bases
        ],
        "proposed_body": proposed_body,
        "writing_review": writing_review,
    }


def reject_curate_proposal(
    vault: Path,
    *,
    proposal_id: str,
    confirmed_rejection: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_rejection:
        raise BootstrapError("Rejecting a proposal requires explicit user rejection")
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        proposal = storage.get_proposal(conn, proposal_id)
        if proposal is None:
            raise BootstrapError(f"Proposal does not exist: {proposal_id}")
        if proposal.status != "pending":
            raise BootstrapError(f"Proposal is not pending: {proposal_id}")
        with storage.transaction(conn):
            storage.reject_proposal(conn, proposal_id)
    finally:
        conn.close()

    return {
        "vault": str(root),
        "proposal_id": proposal_id,
        "status": "rejected",
    }


def approve_curate_proposal(
    vault: Path,
    *,
    proposal_id: str,
    confirmed_approval: bool,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not confirmed_approval:
        raise BootstrapError("Applying a Curate proposal requires explicit user approval")

    config = storage.read_config(root)
    if config is None:
        raise BootstrapError("Vault is not bootstrapped")
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
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    asset_target: Path | None = None
    material_plans: list[MaterialProcessingPlan] = []
    changed_materials: list[Path] = []
    try:
        storage.initialize_schema(conn)
        conn.commit()
        proposal = storage.get_proposal(conn, proposal_id)
        if proposal is None:
            raise BootstrapError(f"Proposal does not exist: {proposal_id}")
        if proposal.status != "pending":
            raise BootstrapError(f"Proposal is not pending: {proposal_id}")
        if proposal.proposal_kind == "update":
            raise BootstrapError(
                "Existing knowledge update execution requires the revision-safe update workflow"
            )

        material_bases = storage.get_proposal_materials(conn, proposal_id)
        if not material_bases:
            raise BootstrapError("Create proposal has no material provenance")
        for material_identity, _basis_revision in material_bases:
            record = storage.get_by_identity(conn, material_identity)
            if record is None or record.kind != "material_record":
                raise BootstrapError(f"Material record does not exist: {material_identity}")
            status = storage.get_material_status(conn, material_identity)
            if status is None:
                raise BootstrapError(f"Material state does not exist: {material_identity}")
            path = root / record.locator
            if not path.exists() or not path.is_file():
                raise BootstrapError(f"Material Markdown is missing: {record.locator}")
            text = path.read_text(encoding="utf-8")
            values = registration_values(text)
            if (
                values.get(AK_ID) != material_identity
                or values.get(AK_KIND) != "material_record"
                or values.get(AK_STATUS) != status
            ):
                raise BootstrapError(
                    f"Material Markdown properties disagree with structured Authority: {record.locator}"
                )
            fingerprint = authority_fingerprint(text)
            if fingerprint != record.authority_fingerprint:
                raise BootstrapError(
                    f"Material Markdown changed since last confirmed revision: {record.locator}"
                )
            transformed = text
            if status == "待处理":
                try:
                    transformed = replace_knowledge_property(
                        text,
                        key=AK_STATUS,
                        value="已处理",
                    )
                except MarkdownConflict as exc:
                    raise BootstrapError(
                        f"Cannot safely update material status {record.locator}: {exc}"
                    ) from exc
            material_plans.append(
                MaterialProcessingPlan(
                    identity=material_identity,
                    locator=record.locator,
                    original=text,
                    transformed=transformed,
                    fingerprint=fingerprint,
                    status=status,
                    revision=record.revision,
                )
            )

        asset_identity = str(uuid7())
        filename = f"知识-{asset_identity}.md"
        asset_locator = (
            (Path(default_root) / filename).as_posix()
            if default_root != "."
            else filename
        )
        asset_target = root / asset_locator
        if asset_target.exists():
            raise BootstrapError(f"Generated knowledge asset locator already exists: {asset_locator}")
        asset_markdown = create_knowledge_asset_markdown(
            identity=asset_identity,
            body=proposal.proposed_body,
        )
        asset_fingerprint = authority_fingerprint(asset_markdown)
        asset_target.parent.mkdir(parents=True, exist_ok=True)

        try:
            with storage.transaction(conn):
                _write_atomic(asset_target, asset_markdown)
                for plan in material_plans:
                    if plan.transformed != plan.original:
                        path = root / plan.locator
                        _write_atomic(path, plan.transformed)
                        changed_materials.append(path)
                storage.insert_knowledge_asset_from_proposal(
                    conn,
                    identity=asset_identity,
                    locator=asset_locator,
                    fingerprint=asset_fingerprint,
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
            asset_target.unlink(missing_ok=True)
            for plan in material_plans:
                path = root / plan.locator
                if path in changed_materials:
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
        "asset_identity": asset_identity,
        "asset_locator": asset_locator,
        "revision": 1,
        "material_revisions": material_revisions,
    }
