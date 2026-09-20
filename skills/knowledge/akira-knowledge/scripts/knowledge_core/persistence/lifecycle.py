from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from knowledge_core import storage


@dataclass(frozen=True)
class LifecycleProposalRecord:
    proposal_id: str
    proposal_kind: str
    status: str
    target_identity: str
    base_revision: int
    replacement_identity: str | None
    replacement_revision: int | None
    reason: str
    created_at: str
    decided_at: str | None


def migrate_schema_v2_to_v3(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        BEGIN IMMEDIATE;

        ALTER TABLE knowledge_asset_lifecycle RENAME TO knowledge_asset_lifecycle_v2;
        CREATE TABLE knowledge_asset_lifecycle (
            identity TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('current', 'retired', 'superseded')),
            superseded_by TEXT,
            updated_at TEXT NOT NULL,
            CHECK (
                (status = 'superseded' AND superseded_by IS NOT NULL)
                OR (status != 'superseded' AND superseded_by IS NULL)
            ),
            FOREIGN KEY (identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            FOREIGN KEY (superseded_by) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        INSERT INTO knowledge_asset_lifecycle(identity, status, superseded_by, updated_at)
            SELECT identity, status, NULL, updated_at
            FROM knowledge_asset_lifecycle_v2;
        DROP TABLE knowledge_asset_lifecycle_v2;

        ALTER TABLE knowledge_asset_lifecycle_events
            RENAME TO knowledge_asset_lifecycle_events_v2;
        CREATE TABLE knowledge_asset_lifecycle_events (
            identity TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            status TEXT NOT NULL CHECK (status IN ('current', 'retired', 'superseded')),
            event TEXT NOT NULL,
            reason TEXT NOT NULL,
            superseded_by TEXT,
            recorded_at TEXT NOT NULL,
            CHECK (
                (status = 'superseded' AND superseded_by IS NOT NULL)
                OR (status != 'superseded' AND superseded_by IS NULL)
            ),
            PRIMARY KEY (identity, revision),
            FOREIGN KEY (identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            FOREIGN KEY (superseded_by) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        INSERT INTO knowledge_asset_lifecycle_events(
            identity, revision, status, event, reason, superseded_by, recorded_at
        )
            SELECT identity, revision, status, event, reason, NULL, recorded_at
            FROM knowledge_asset_lifecycle_events_v2;
        DROP TABLE knowledge_asset_lifecycle_events_v2;

        ALTER TABLE lifecycle_proposals RENAME TO lifecycle_proposals_v2;
        CREATE TABLE lifecycle_proposals (
            proposal_id TEXT PRIMARY KEY,
            proposal_kind TEXT NOT NULL CHECK (proposal_kind IN ('retire', 'supersede')),
            status TEXT NOT NULL CHECK (status IN ('pending', 'rejected', 'applied')),
            target_identity TEXT NOT NULL,
            base_revision INTEGER NOT NULL CHECK (base_revision >= 1),
            replacement_identity TEXT,
            replacement_revision INTEGER CHECK (
                replacement_revision IS NULL OR replacement_revision >= 1
            ),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            CHECK (
                (proposal_kind = 'supersede'
                    AND replacement_identity IS NOT NULL
                    AND replacement_revision IS NOT NULL)
                OR (proposal_kind = 'retire'
                    AND replacement_identity IS NULL
                    AND replacement_revision IS NULL)
            ),
            FOREIGN KEY (target_identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            FOREIGN KEY (replacement_identity) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        INSERT INTO lifecycle_proposals(
            proposal_id, proposal_kind, status, target_identity, base_revision,
            replacement_identity, replacement_revision, reason, created_at, decided_at
        )
            SELECT proposal_id, proposal_kind, status, target_identity, base_revision,
                   NULL, NULL, reason, created_at, decided_at
            FROM lifecycle_proposals_v2;
        DROP TABLE lifecycle_proposals_v2;
        CREATE INDEX lifecycle_proposals_status_idx
            ON lifecycle_proposals(status);

        UPDATE schema_meta
            SET value = '3'
            WHERE key = 'schema_version';

        COMMIT;
        """
    )


def get_knowledge_asset_lifecycle(conn: sqlite3.Connection, identity: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM knowledge_asset_lifecycle WHERE identity = ?",
        (identity,),
    ).fetchone()
    return None if row is None else str(row["status"])


def insert_lifecycle_proposal(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    proposal_kind: str,
    target_identity: str,
    base_revision: int,
    reason: str,
    replacement_identity: str | None = None,
    replacement_revision: int | None = None,
) -> None:
    timestamp = storage.now_utc()
    conn.execute(
        "INSERT INTO lifecycle_proposals("
        "proposal_id, proposal_kind, status, target_identity, base_revision, "
        "replacement_identity, replacement_revision, reason, created_at"
        ") VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)",
        (
            proposal_id,
            proposal_kind,
            target_identity,
            base_revision,
            replacement_identity,
            replacement_revision,
            reason,
            timestamp,
        ),
    )


def get_lifecycle_proposal(
    conn: sqlite3.Connection,
    proposal_id: str,
) -> LifecycleProposalRecord | None:
    row = conn.execute(
        "SELECT proposal_id, proposal_kind, status, target_identity, base_revision, "
        "replacement_identity, replacement_revision, reason, created_at, decided_at "
        "FROM lifecycle_proposals WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    if row is None:
        return None
    return LifecycleProposalRecord(**dict(row))


def apply_retire_lifecycle_proposal(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    identity: str,
    locator: str,
    fingerprint: str,
) -> int:
    record = storage.get_by_identity(conn, identity)
    if record is None or record.kind != "knowledge_asset":
        raise storage.StorageError(f"knowledge asset does not exist: {identity}")
    lifecycle = get_knowledge_asset_lifecycle(conn, identity)
    if lifecycle != "current":
        raise storage.StorageError(f"knowledge asset is not current: {identity}")

    proposal = get_lifecycle_proposal(conn, proposal_id)
    if proposal is None or proposal.status != "pending" or proposal.proposal_kind != "retire":
        raise storage.StorageError("retire proposal is not pending")
    if proposal.target_identity != identity:
        raise storage.StorageError("retire proposal target does not match knowledge asset")

    new_revision = record.revision + 1
    timestamp = storage.now_utc()
    conn.execute(
        "UPDATE knowledge_asset_lifecycle "
        "SET status = 'retired', updated_at = ? "
        "WHERE identity = ?",
        (timestamp, identity),
    )
    conn.execute(
        "UPDATE objects SET locator = ?, revision = ?, authority_fingerprint = ?, updated_at = ? "
        "WHERE identity = ?",
        (locator, new_revision, fingerprint, timestamp, identity),
    )
    conn.execute(
        "INSERT INTO revisions(identity, revision, event, locator, authority_fingerprint, recorded_at) "
        "VALUES (?, ?, 'retired', ?, ?, ?)",
        (identity, new_revision, locator, fingerprint, timestamp),
    )
    conn.execute(
        "INSERT INTO knowledge_asset_lifecycle_events("
        "identity, revision, status, event, reason, recorded_at"
        ") VALUES (?, ?, 'retired', 'retired', ?, ?)",
        (identity, new_revision, proposal.reason, timestamp),
    )
    changed = conn.execute(
        "UPDATE lifecycle_proposals SET status = 'applied', decided_at = ? "
        "WHERE proposal_id = ? AND status = 'pending'",
        (timestamp, proposal_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("retire proposal is not pending")
    return new_revision


def apply_supersede_lifecycle_proposal(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    identity: str,
    replacement_identity: str,
    locator: str,
    fingerprint: str,
) -> int:
    record = storage.get_by_identity(conn, identity)
    replacement = storage.get_by_identity(conn, replacement_identity)
    if record is None or record.kind != "knowledge_asset":
        raise storage.StorageError(f"knowledge asset does not exist: {identity}")
    if replacement is None or replacement.kind != "knowledge_asset":
        raise storage.StorageError(f"replacement knowledge asset does not exist: {replacement_identity}")
    if identity == replacement_identity:
        raise storage.StorageError("knowledge asset cannot supersede itself")

    lifecycle = get_knowledge_asset_lifecycle(conn, identity)
    replacement_lifecycle = get_knowledge_asset_lifecycle(conn, replacement_identity)
    if lifecycle != "current":
        raise storage.StorageError(f"knowledge asset is not current: {identity}")
    if replacement_lifecycle != "current":
        raise storage.StorageError(f"replacement knowledge asset is not current: {replacement_identity}")

    proposal = get_lifecycle_proposal(conn, proposal_id)
    if proposal is None or proposal.status != "pending" or proposal.proposal_kind != "supersede":
        raise storage.StorageError("supersede proposal is not pending")
    if proposal.target_identity != identity:
        raise storage.StorageError("supersede proposal target does not match knowledge asset")
    if proposal.replacement_identity != replacement_identity:
        raise storage.StorageError("supersede proposal replacement does not match knowledge asset")

    new_revision = record.revision + 1
    timestamp = storage.now_utc()
    conn.execute(
        "UPDATE knowledge_asset_lifecycle "
        "SET status = 'superseded', superseded_by = ?, updated_at = ? "
        "WHERE identity = ?",
        (replacement_identity, timestamp, identity),
    )
    conn.execute(
        "UPDATE objects SET locator = ?, revision = ?, authority_fingerprint = ?, updated_at = ? "
        "WHERE identity = ?",
        (locator, new_revision, fingerprint, timestamp, identity),
    )
    conn.execute(
        "INSERT INTO revisions(identity, revision, event, locator, authority_fingerprint, recorded_at) "
        "VALUES (?, ?, 'superseded', ?, ?, ?)",
        (identity, new_revision, locator, fingerprint, timestamp),
    )
    conn.execute(
        "INSERT INTO knowledge_asset_lifecycle_events("
        "identity, revision, status, event, reason, superseded_by, recorded_at"
        ") VALUES (?, ?, 'superseded', 'superseded', ?, ?, ?)",
        (
            identity,
            new_revision,
            proposal.reason,
            replacement_identity,
            timestamp,
        ),
    )
    changed = conn.execute(
        "UPDATE lifecycle_proposals SET status = 'applied', decided_at = ? "
        "WHERE proposal_id = ? AND status = 'pending'",
        (timestamp, proposal_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("supersede proposal is not pending")
    return new_revision
