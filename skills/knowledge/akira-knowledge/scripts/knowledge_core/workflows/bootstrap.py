from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from knowledge_core import storage
from knowledge_core.common import BootstrapError, _safe_relative, _vault_root, _within_scope, _write_atomic
from knowledge_core.ids import uuid7
from knowledge_core.markdown import AK_ID, AK_KIND, MarkdownConflict, authority_fingerprint, has_knowledge_keys, inject_registration, registration_values


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

    existing_config = storage.read_config(root)  # Fail closed on invalid pre-existing config.
    database_exists = storage.db_path(root).exists()
    if existing_config is not None and not database_exists:
        raise BootstrapError(
            "Knowledge structured Authority store is missing from an already bootstrapped Vault"
        )
    if existing_config is None and database_exists:
        raise BootstrapError(
            "Knowledge structured Authority store exists without its Vault configuration"
        )

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
