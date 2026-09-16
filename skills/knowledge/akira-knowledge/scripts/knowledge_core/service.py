from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Sequence

from knowledge_core.ids import uuid7
from knowledge_core.markdown import (
    AK_ID,
    AK_KIND,
    AK_STATUS,
    MarkdownConflict,
    authority_fingerprint,
    create_knowledge_asset_markdown,
    create_material_markdown,
    has_knowledge_keys,
    inject_registration,
    registration_values,
    replace_knowledge_property,
)
from knowledge_core import storage


class BootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionNote:
    path: str
    has_frontmatter: bool
    has_reserved_knowledge_properties: bool


@dataclass(frozen=True)
class RegistrationPlan:
    locator: str
    original: str
    transformed: str
    identity: str
    kind: str
    fingerprint: str
    already_registered: bool


@dataclass(frozen=True)
class MaterialProcessingPlan:
    identity: str
    locator: str
    original: str
    transformed: str
    fingerprint: str
    status: str
    revision: int


def _vault_root(vault: Path) -> Path:
    root = vault.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise BootstrapError(f"Vault does not exist or is not a directory: {vault}")
    return root


def _safe_relative(root: Path, value: str, *, must_exist: bool) -> tuple[str, Path]:
    raw = Path(value)
    if raw.is_absolute():
        raise BootstrapError(f"Vault-relative path required: {value}")
    candidate = root / raw
    try:
        resolved = candidate.resolve(strict=must_exist)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"Path escapes Vault or cannot be resolved: {value}") from exc
    return relative.as_posix() if relative.as_posix() else ".", resolved


def _within_scope(locator: str, scopes: Sequence[str]) -> bool:
    path = Path(locator)
    for scope in scopes:
        if scope == ".":
            return True
        scope_path = Path(scope)
        if path == scope_path or scope_path in path.parents:
            return True
    return False


def inspect_vault(vault: Path) -> dict[str, object]:
    root = _vault_root(vault)
    notes: list[InspectionNote] = []
    for path in sorted(root.rglob("*.md")):
        if storage.SYSTEM_DIR in path.parts:
            continue
        if path.is_symlink():
            continue
        try:
            relative = path.resolve().relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            raise BootstrapError(f"Cannot inspect Markdown {path}: {exc}") from exc
        notes.append(
            InspectionNote(
                path=relative,
                has_frontmatter=text.startswith("---\n"),
                has_reserved_knowledge_properties=has_knowledge_keys(text),
            )
        )

    return {
        "vault": str(root),
        "markdown_count": len(notes),
        "notes": [asdict(note) for note in notes],
        "system_exists": storage.system_dir(root).exists(),
        "config_exists": storage.config_path(root).exists(),
        "database_exists": storage.db_path(root).exists(),
    }


def _normalize_scopes(root: Path, scopes: Sequence[str]) -> tuple[str, ...]:
    if not scopes:
        raise BootstrapError("At least one approved management scope is required")
    normalized: list[str] = []
    for scope in scopes:
        rel, resolved = _safe_relative(root, scope, must_exist=True)
        if not resolved.is_dir() and not resolved.is_file():
            raise BootstrapError(f"Management scope is neither file nor directory: {scope}")
        normalized.append(rel)
    return tuple(dict.fromkeys(normalized))


def _validate_note(root: Path, note: str) -> tuple[str, Path]:
    locator, path = _safe_relative(root, note, must_exist=True)
    if path.is_symlink():
        raise BootstrapError(f"Refusing to register symlinked Markdown: {note}")
    if path.suffix.lower() != ".md" or not path.is_file():
        raise BootstrapError(f"Registration target must be an existing Markdown file: {note}")
    return locator, path


def _write_atomic(path: Path, text: str) -> None:
    mode = (path.stat().st_mode & 0o7777) if path.exists() else 0o644
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


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


def create_curate_proposal(
    vault: Path,
    *,
    proposed_body: str,
    material_ids: Sequence[str],
    target_identity: str | None = None,
) -> dict[str, object]:
    root = _vault_root(vault)
    if not proposed_body:
        raise BootstrapError("Curate proposal body must not be empty")
    if not material_ids:
        raise BootstrapError("Curate proposal requires at least one material record")
    material_ids = tuple(dict.fromkeys(material_ids))
    if not storage.db_path(root).exists():
        raise BootstrapError("Knowledge structured Authority store is missing")

    conn = storage.connect(root)
    try:
        storage.initialize_schema(conn)
        conn.commit()
        material_bases: list[tuple[str, int]] = []
        for identity in material_ids:
            record = storage.get_by_identity(conn, identity)
            if record is None or record.kind != "material_record":
                raise BootstrapError(f"Material record does not exist: {identity}")
            if storage.get_material_status(conn, identity) is None:
                raise BootstrapError(f"Material state does not exist: {identity}")
            material_bases.append((identity, record.revision))

        proposal_kind = "create"
        base_revision: int | None = None
        if target_identity is not None:
            target = storage.get_by_identity(conn, target_identity)
            if target is None or target.kind != "knowledge_asset":
                raise BootstrapError(f"Knowledge asset does not exist: {target_identity}")
            proposal_kind = "update"
            base_revision = target.revision

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


def register_notes(
    vault: Path,
    *,
    scopes: Sequence[str],
    notes: Sequence[str],
    default_write_root: str,
    kind: str = "knowledge_asset",
) -> dict[str, object]:
    root = _vault_root(vault)
    normalized_scopes = _normalize_scopes(root, scopes)
    default_root, _ = _safe_relative(root, default_write_root, must_exist=False)
    if not _within_scope(default_root, normalized_scopes):
        raise BootstrapError(
            f"Default write root is outside approved management scopes: {default_root}"
        )
    if not notes:
        raise BootstrapError("At least one explicitly approved Markdown note is required")
    if kind != "knowledge_asset":
        raise BootstrapError("Existing Vault registration currently supports only knowledge_asset")

    # Preflight every requested note before any Vault mutation.
    note_entries = [_validate_note(root, note) for note in notes]
    for locator, _ in note_entries:
        if not _within_scope(locator, normalized_scopes):
            raise BootstrapError(
                f"Approved note is outside approved management scopes: {locator}"
            )

    storage.read_config(root)  # Fail closed on an invalid pre-existing config before mutation.
    sys_dir = storage.system_dir(root)
    if sys_dir.exists() and not sys_dir.is_dir():
        raise BootstrapError(f"{storage.SYSTEM_DIR} exists but is not a directory")

    # The DB may not exist yet. If it does, inspect it before mutating Markdown.
    existing_records: dict[str, storage.ObjectRecord] = {}
    if storage.db_path(root).exists():
        try:
            conn = storage.connect(root)
            storage.initialize_schema(conn)
            conn.commit()
            for locator, _ in note_entries:
                record = storage.get_by_locator(conn, locator)
                if record:
                    existing_records[locator] = record
        except Exception as exc:
            raise BootstrapError(f"Cannot read existing Knowledge registry: {exc}") from exc
        finally:
            if "conn" in locals():
                conn.close()

    plans: list[RegistrationPlan] = []
    for locator, path in note_entries:
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise BootstrapError(f"Cannot read registration target {locator}: {exc}") from exc

        record = existing_records.get(locator)
        if record is None:
            if has_knowledge_keys(original):
                raise BootstrapError(
                    f"Unregistered Markdown already uses reserved Akira Knowledge properties: {locator}"
                )
            identity = str(uuid7())
            try:
                transformed = inject_registration(original, identity=identity, kind=kind)
            except MarkdownConflict as exc:
                raise BootstrapError(f"Cannot safely register {locator}: {exc}") from exc
            fingerprint = authority_fingerprint(transformed)
            plans.append(
                RegistrationPlan(
                    locator=locator,
                    original=original,
                    transformed=transformed,
                    identity=identity,
                    kind=kind,
                    fingerprint=fingerprint,
                    already_registered=False,
                )
            )
            continue

        values = registration_values(original)
        if values.get(AK_ID) != record.identity or values.get(AK_KIND) != record.kind:
            raise BootstrapError(
                f"Registered Markdown properties disagree with SQLite registry: {locator}"
            )
        fingerprint = authority_fingerprint(original)
        if fingerprint != record.authority_fingerprint:
            raise BootstrapError(
                f"Registered Markdown changed since last confirmed revision; revision-safe update is required: {locator}"
            )
        plans.append(
            RegistrationPlan(
                locator=locator,
                original=original,
                transformed=original,
                identity=record.identity,
                kind=record.kind,
                fingerprint=fingerprint,
                already_registered=True,
            )
        )

    storage.ensure_system_dir(root)
    conn = storage.connect(root)
    changed_paths: list[Path] = []
    try:
        storage.initialize_schema(conn)
        conn.commit()
        with storage.transaction(conn):
            for plan in plans:
                if not plan.already_registered:
                    path = root / plan.locator
                    _write_atomic(path, plan.transformed)
                    changed_paths.append(path)
                    storage.insert_registration(
                        conn,
                        identity=plan.identity,
                        kind=plan.kind,
                        locator=plan.locator,
                        fingerprint=plan.fingerprint,
                    )
            config_text = storage.serialize_config(
                scopes=normalized_scopes,
                default_write_root=default_root,
            )
            config_target = storage.config_path(root)
            previous_config = (
                config_target.read_text(encoding="utf-8") if config_target.exists() else None
            )
            config_target.write_text(config_text, encoding="utf-8")
    except Exception:
        for plan in plans:
            path = root / plan.locator
            if path in changed_paths:
                try:
                    _write_atomic(path, plan.original)
                except OSError:
                    pass
        config_target = storage.config_path(root)
        if "previous_config" in locals():
            if previous_config is None:
                config_target.unlink(missing_ok=True)
            else:
                config_target.write_text(previous_config, encoding="utf-8")
        raise
    finally:
        conn.close()

    return {
        "vault": str(root),
        "schema_version": storage.SCHEMA_VERSION,
        "managed_scopes": list(normalized_scopes),
        "default_write_root": default_root,
        "registered": [
            {
                "locator": plan.locator,
                "identity": plan.identity,
                "kind": plan.kind,
                "revision": 1,
                "already_registered": plan.already_registered,
            }
            for plan in plans
        ],
    }
