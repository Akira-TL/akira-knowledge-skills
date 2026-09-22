from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from knowledge_core import storage


@dataclass(frozen=True)
class AuthorityEditProposalRecord:
    proposal_id: str
    status: str
    target_identity: str
    base_revision: int
    edit_kind: str
    proposed_authority_text: str
    reason: str
    created_at: str
    decided_at: str | None


_REQUIRED_TABLE = "authority_edit_proposals"


def migrate_schema_v5_to_v6(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        BEGIN IMMEDIATE;

        CREATE TABLE authority_edit_proposals (
            proposal_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('pending', 'applied')),
            target_identity TEXT NOT NULL,
            base_revision INTEGER NOT NULL CHECK (base_revision >= 1),
            edit_kind TEXT NOT NULL CHECK (edit_kind IN ('wikilink', 'property')),
            proposed_authority_text TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            FOREIGN KEY (target_identity) REFERENCES objects(identity) ON DELETE RESTRICT
        );
        CREATE INDEX authority_edit_proposals_status_idx
            ON authority_edit_proposals(status);

        UPDATE schema_meta
            SET value = '6'
            WHERE key = 'schema_version';

        COMMIT;
        """
    )


def validate_schema_v6(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name = ?",
        (_REQUIRED_TABLE,),
    ).fetchone()
    if row is None:
        raise storage.StorageError(
            "Authority edit structured governance is missing required table: "
            + _REQUIRED_TABLE
        )


def insert_authority_edit_proposal(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    target_identity: str,
    base_revision: int,
    edit_kind: str,
    proposed_authority_text: str,
    reason: str,
) -> None:
    conn.execute(
        """
        INSERT INTO authority_edit_proposals(
            proposal_id, status, target_identity, base_revision,
            edit_kind, proposed_authority_text, reason, created_at
        ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal_id,
            target_identity,
            base_revision,
            edit_kind,
            proposed_authority_text,
            reason,
            storage.now_utc(),
        ),
    )


def get_authority_edit_proposal(
    conn: sqlite3.Connection,
    proposal_id: str,
) -> AuthorityEditProposalRecord | None:
    row = conn.execute(
        """
        SELECT proposal_id, status, target_identity, base_revision,
               edit_kind, proposed_authority_text, reason,
               created_at, decided_at
        FROM authority_edit_proposals
        WHERE proposal_id = ?
        """,
        (proposal_id,),
    ).fetchone()
    if row is None:
        return None
    return AuthorityEditProposalRecord(**dict(row))


def apply_authority_edit(
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

    proposal = get_authority_edit_proposal(conn, proposal_id)
    if proposal is None or proposal.status != "pending":
        raise storage.StorageError("authority edit proposal is not pending")
    if proposal.target_identity != identity:
        raise storage.StorageError(
            "authority edit proposal target does not match knowledge asset"
        )

    new_revision = record.revision + 1
    timestamp = storage.now_utc()
    conn.execute(
        "UPDATE objects "
        "SET locator = ?, revision = ?, authority_fingerprint = ?, updated_at = ? "
        "WHERE identity = ?",
        (locator, new_revision, fingerprint, timestamp, identity),
    )
    conn.execute(
        "INSERT INTO revisions("
        "identity, revision, event, locator, authority_fingerprint, recorded_at"
        ") VALUES (?, ?, 'authority_edit_applied', ?, ?, ?)",
        (identity, new_revision, locator, fingerprint, timestamp),
    )
    changed = conn.execute(
        "UPDATE authority_edit_proposals "
        "SET status = 'applied', decided_at = ? "
        "WHERE proposal_id = ? AND status = 'pending'",
        (timestamp, proposal_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("authority edit proposal is not pending")
    return new_revision
