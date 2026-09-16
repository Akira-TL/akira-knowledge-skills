from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Sequence

SYSTEM_DIR = ".akira-knowledge"
CONFIG_NAME = "config.json"
DB_NAME = "knowledge.sqlite"
SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectRecord:
    identity: str
    kind: str
    locator: str
    revision: int
    authority_fingerprint: str


@dataclass(frozen=True)
class ProposalRecord:
    proposal_id: str
    proposal_kind: str
    status: str
    target_identity: str | None
    base_revision: int | None
    proposed_body: str
    result_identity: str | None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def system_dir(vault: Path) -> Path:
    return vault / SYSTEM_DIR


def config_path(vault: Path) -> Path:
    return system_dir(vault) / CONFIG_NAME


def db_path(vault: Path) -> Path:
    return system_dir(vault) / DB_NAME


def config_payload(*, scopes: Sequence[str], default_write_root: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "managed_scopes": list(scopes),
        "default_write_root": default_write_root,
    }


def serialize_config(*, scopes: Sequence[str], default_write_root: str) -> str:
    return json.dumps(
        config_payload(scopes=scopes, default_write_root=default_write_root),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def read_config(vault: Path) -> dict[str, object] | None:
    path = config_path(vault)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"cannot read Akira Knowledge config: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise StorageError("unsupported or invalid Akira Knowledge config schema")
    return payload


def ensure_system_dir(vault: Path) -> Path:
    path = system_dir(vault)
    if path.exists() and not path.is_dir():
        raise StorageError(f"{SYSTEM_DIR} exists but is not a directory")
    path.mkdir(parents=False, exist_ok=True)
    return path


def connect(vault: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(vault))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS objects (
            identity TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            locator TEXT NOT NULL UNIQUE,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            authority_fingerprint TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS revisions (
            identity TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            event TEXT NOT NULL,
            locator TEXT NOT NULL,
            authority_fingerprint TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (identity, revision),
            FOREIGN KEY (identity) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS material_records (
            identity TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('待处理', '已处理')),
            captured_at TEXT NOT NULL,
            FOREIGN KEY (identity) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS material_sources (
            material_identity TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            locator TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY (material_identity, ordinal),
            FOREIGN KEY (material_identity) REFERENCES material_records(identity) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS material_sources_locator_idx
            ON material_sources(locator);
        CREATE TABLE IF NOT EXISTS capture_events (
            material_identity TEXT PRIMARY KEY,
            captured_at TEXT NOT NULL,
            intent_mode TEXT NOT NULL,
            note_fingerprint TEXT NOT NULL,
            FOREIGN KEY (material_identity) REFERENCES material_records(identity) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS proposals (
            proposal_id TEXT PRIMARY KEY,
            proposal_kind TEXT NOT NULL CHECK (proposal_kind IN ('create', 'update')),
            status TEXT NOT NULL CHECK (status IN ('pending', 'rejected', 'applied')),
            target_identity TEXT,
            base_revision INTEGER,
            proposed_body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            result_identity TEXT,
            FOREIGN KEY (target_identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            FOREIGN KEY (result_identity) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS proposal_materials (
            proposal_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            material_identity TEXT NOT NULL,
            basis_revision INTEGER NOT NULL,
            PRIMARY KEY (proposal_id, ordinal),
            FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id) ON DELETE RESTRICT,
            FOREIGN KEY (material_identity) REFERENCES material_records(identity) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS knowledge_asset_materials (
            asset_identity TEXT NOT NULL,
            material_identity TEXT NOT NULL,
            proposal_id TEXT NOT NULL,
            material_basis_revision INTEGER NOT NULL,
            PRIMARY KEY (asset_identity, material_identity, proposal_id),
            FOREIGN KEY (asset_identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            FOREIGN KEY (material_identity) REFERENCES material_records(identity) ON DELETE RESTRICT,
            FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id) ON DELETE RESTRICT
        );
        """
    )
    current = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if current is None:
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
    elif current["value"] != str(SCHEMA_VERSION):
        raise StorageError(
            f"unsupported SQLite schema version {current['value']!r}; expected {SCHEMA_VERSION}"
        )


def get_by_identity(conn: sqlite3.Connection, identity: str) -> ObjectRecord | None:
    row = conn.execute(
        "SELECT identity, kind, locator, revision, authority_fingerprint "
        "FROM objects WHERE identity = ?",
        (identity,),
    ).fetchone()
    if row is None:
        return None
    return ObjectRecord(**dict(row))


def get_by_locator(conn: sqlite3.Connection, locator: str) -> ObjectRecord | None:
    row = conn.execute(
        "SELECT identity, kind, locator, revision, authority_fingerprint "
        "FROM objects WHERE locator = ?",
        (locator,),
    ).fetchone()
    if row is None:
        return None
    return ObjectRecord(**dict(row))


def find_materials_by_source(conn: sqlite3.Connection, locator: str) -> list[str]:
    rows = conn.execute(
        "SELECT material_identity FROM material_sources WHERE locator = ? ORDER BY material_identity",
        (locator,),
    ).fetchall()
    return [row["material_identity"] for row in rows]


def get_material_status(conn: sqlite3.Connection, identity: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM material_records WHERE identity = ?",
        (identity,),
    ).fetchone()
    return None if row is None else str(row["status"])


def insert_proposal(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    proposal_kind: str,
    proposed_body: str,
    material_bases: Sequence[tuple[str, int]],
    target_identity: str | None,
    base_revision: int | None,
) -> None:
    timestamp = now_utc()
    conn.execute(
        "INSERT INTO proposals(proposal_id, proposal_kind, status, target_identity, base_revision, proposed_body, created_at) "
        "VALUES (?, ?, 'pending', ?, ?, ?, ?)",
        (proposal_id, proposal_kind, target_identity, base_revision, proposed_body, timestamp),
    )
    for ordinal, (material_identity, basis_revision) in enumerate(material_bases):
        conn.execute(
            "INSERT INTO proposal_materials(proposal_id, ordinal, material_identity, basis_revision) "
            "VALUES (?, ?, ?, ?)",
            (proposal_id, ordinal, material_identity, basis_revision),
        )


def get_proposal(conn: sqlite3.Connection, proposal_id: str) -> ProposalRecord | None:
    row = conn.execute(
        "SELECT proposal_id, proposal_kind, status, target_identity, base_revision, proposed_body, result_identity "
        "FROM proposals WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    if row is None:
        return None
    return ProposalRecord(**dict(row))


def get_proposal_materials(conn: sqlite3.Connection, proposal_id: str) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT material_identity, basis_revision FROM proposal_materials "
        "WHERE proposal_id = ? ORDER BY ordinal",
        (proposal_id,),
    ).fetchall()
    return [(str(row["material_identity"]), int(row["basis_revision"])) for row in rows]


def reject_proposal(conn: sqlite3.Connection, proposal_id: str) -> None:
    timestamp = now_utc()
    changed = conn.execute(
        "UPDATE proposals SET status = 'rejected', decided_at = ? "
        "WHERE proposal_id = ? AND status = 'pending'",
        (timestamp, proposal_id),
    ).rowcount
    if changed != 1:
        raise StorageError("proposal is not pending")


def insert_knowledge_asset_from_proposal(
    conn: sqlite3.Connection,
    *,
    identity: str,
    locator: str,
    fingerprint: str,
    proposal_id: str,
    material_bases: Sequence[tuple[str, int]],
) -> None:
    timestamp = now_utc()
    conn.execute(
        "INSERT INTO objects(identity, kind, locator, revision, authority_fingerprint, registered_at, updated_at) "
        "VALUES (?, 'knowledge_asset', ?, 1, ?, ?, ?)",
        (identity, locator, fingerprint, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO revisions(identity, revision, event, locator, authority_fingerprint, recorded_at) "
        "VALUES (?, 1, 'created_from_proposal', ?, ?, ?)",
        (identity, locator, fingerprint, timestamp),
    )
    for material_identity, basis_revision in material_bases:
        conn.execute(
            "INSERT INTO knowledge_asset_materials(asset_identity, material_identity, proposal_id, material_basis_revision) "
            "VALUES (?, ?, ?, ?)",
            (identity, material_identity, proposal_id, basis_revision),
        )
    changed = conn.execute(
        "UPDATE proposals SET status = 'applied', decided_at = ?, result_identity = ? "
        "WHERE proposal_id = ? AND status = 'pending'",
        (timestamp, identity, proposal_id),
    ).rowcount
    if changed != 1:
        raise StorageError("proposal is not pending")


def mark_material_processed(
    conn: sqlite3.Connection,
    *,
    identity: str,
    locator: str,
    fingerprint: str,
) -> int:
    record = get_by_identity(conn, identity)
    if record is None or record.kind != "material_record":
        raise StorageError(f"material record does not exist: {identity}")
    status = get_material_status(conn, identity)
    if status is None:
        raise StorageError(f"material state does not exist: {identity}")
    if status == "已处理":
        return record.revision

    new_revision = record.revision + 1
    timestamp = now_utc()
    conn.execute(
        "UPDATE material_records SET status = '已处理' WHERE identity = ?",
        (identity,),
    )
    conn.execute(
        "UPDATE objects SET revision = ?, authority_fingerprint = ?, updated_at = ? WHERE identity = ?",
        (new_revision, fingerprint, timestamp, identity),
    )
    conn.execute(
        "INSERT INTO revisions(identity, revision, event, locator, authority_fingerprint, recorded_at) "
        "VALUES (?, ?, 'processed_by_proposal', ?, ?, ?)",
        (identity, new_revision, locator, fingerprint, timestamp),
    )
    return new_revision


def insert_material_capture(
    conn: sqlite3.Connection,
    *,
    identity: str,
    locator: str,
    fingerprint: str,
    sources: Sequence[str],
) -> None:
    timestamp = now_utc()
    conn.execute(
        "INSERT INTO objects(identity, kind, locator, revision, authority_fingerprint, registered_at, updated_at) "
        "VALUES (?, 'material_record', ?, 1, ?, ?, ?)",
        (identity, locator, fingerprint, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO revisions(identity, revision, event, locator, authority_fingerprint, recorded_at) "
        "VALUES (?, 1, 'captured', ?, ?, ?)",
        (identity, locator, fingerprint, timestamp),
    )
    conn.execute(
        "INSERT INTO material_records(identity, status, captured_at) VALUES (?, '待处理', ?)",
        (identity, timestamp),
    )
    conn.execute(
        "INSERT INTO capture_events(material_identity, captured_at, intent_mode, note_fingerprint) "
        "VALUES (?, ?, 'explicit', ?)",
        (identity, timestamp, fingerprint),
    )
    for ordinal, source in enumerate(sources):
        conn.execute(
            "INSERT INTO material_sources(material_identity, ordinal, locator, captured_at) "
            "VALUES (?, ?, ?, ?)",
            (identity, ordinal, source, timestamp),
        )


def insert_registration(
    conn: sqlite3.Connection,
    *,
    identity: str,
    kind: str,
    locator: str,
    fingerprint: str,
) -> None:
    timestamp = now_utc()
    conn.execute(
        "INSERT INTO objects(identity, kind, locator, revision, authority_fingerprint, registered_at, updated_at) "
        "VALUES (?, ?, ?, 1, ?, ?, ?)",
        (identity, kind, locator, fingerprint, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO revisions(identity, revision, event, locator, authority_fingerprint, recorded_at) "
        "VALUES (?, 1, 'registered', ?, ?, ?)",
        (identity, locator, fingerprint, timestamp),
    )


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
