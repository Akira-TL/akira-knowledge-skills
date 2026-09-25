from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from knowledge_core import storage


@dataclass(frozen=True)
class BatchRecord:
    batch_id: str
    status: str
    created_at: str
    approved_at: str | None
    executed_at: str | None


@dataclass(frozen=True)
class BatchItemRecord:
    item_id: str
    batch_id: str
    ordinal: int
    item_kind: str
    governance_ref: str
    target_identity: str | None
    relation_identity: str | None
    evidence: str
    proposed_change: str
    approval_result: str
    status: str
    result_json: str | None
    error: str | None


@dataclass(frozen=True)
class BatchItemBasisRecord:
    item_id: str
    ordinal: int
    basis_kind: str
    role: str
    identity: str
    revision: int
    fingerprint: str


_REQUIRED_TABLES = (
    "maintenance_batches",
    "maintenance_batch_items",
    "maintenance_batch_item_bases",
)


def migrate_schema_v6_to_v7(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        BEGIN IMMEDIATE;

        CREATE TABLE maintenance_batches (
            batch_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (
                status IN ('pending', 'approved', 'completed', 'partial')
            ),
            created_at TEXT NOT NULL,
            approved_at TEXT,
            executed_at TEXT
        );

        CREATE TABLE maintenance_batch_items (
            item_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            item_kind TEXT NOT NULL CHECK (
                item_kind IN (
                    'knowledge_update',
                    'lifecycle_retire',
                    'lifecycle_supersede',
                    'authority_edit',
                    'relation_candidate',
                    'relation_revoke'
                )
            ),
            governance_ref TEXT NOT NULL,
            target_identity TEXT,
            relation_identity TEXT,
            evidence TEXT NOT NULL,
            proposed_change TEXT NOT NULL,
            approval_result TEXT NOT NULL DEFAULT 'pending' CHECK (
                approval_result IN ('pending', 'approved', 'rejected')
            ),
            status TEXT NOT NULL CHECK (
                status IN (
                    'pending',
                    'approved',
                    'rejected',
                    'succeeded',
                    'stale',
                    'failed'
                )
            ),
            result_json TEXT,
            error TEXT,
            UNIQUE (batch_id, ordinal),
            FOREIGN KEY (batch_id)
                REFERENCES maintenance_batches(batch_id)
                ON DELETE RESTRICT
        );
        CREATE INDEX maintenance_batch_items_batch_idx
            ON maintenance_batch_items(batch_id, ordinal);
        CREATE INDEX maintenance_batch_items_status_idx
            ON maintenance_batch_items(batch_id, status);

        CREATE TABLE maintenance_batch_item_bases (
            item_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            basis_kind TEXT NOT NULL CHECK (basis_kind IN ('object', 'relation')),
            role TEXT NOT NULL,
            identity TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            fingerprint TEXT NOT NULL,
            PRIMARY KEY (item_id, ordinal),
            FOREIGN KEY (item_id)
                REFERENCES maintenance_batch_items(item_id)
                ON DELETE RESTRICT
        );
        CREATE INDEX maintenance_batch_item_bases_identity_idx
            ON maintenance_batch_item_bases(basis_kind, identity);

        UPDATE schema_meta
            SET value = '7'
            WHERE key = 'schema_version';

        COMMIT;
        """
    )


def validate_schema_v7(conn: sqlite3.Connection) -> None:
    present = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ("
            "'maintenance_batches', "
            "'maintenance_batch_items', "
            "'maintenance_batch_item_bases'"
            ")"
        ).fetchall()
    }
    missing = [name for name in _REQUIRED_TABLES if name not in present]
    if missing:
        raise storage.StorageError(
            "Batch structured governance is missing required tables: "
            + ", ".join(missing)
        )


def insert_batch(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
) -> None:
    conn.execute(
        "INSERT INTO maintenance_batches(batch_id, status, created_at) "
        "VALUES (?, 'pending', ?)",
        (batch_id, storage.now_utc()),
    )


def insert_batch_item(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    batch_id: str,
    ordinal: int,
    item_kind: str,
    governance_ref: str,
    target_identity: str | None,
    relation_identity: str | None,
    evidence: str,
    proposed_change: str,
    bases: list[BatchItemBasisRecord],
) -> None:
    conn.execute(
        """
        INSERT INTO maintenance_batch_items(
            item_id, batch_id, ordinal, item_kind, governance_ref,
            target_identity, relation_identity,
            evidence, proposed_change, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            item_id,
            batch_id,
            ordinal,
            item_kind,
            governance_ref,
            target_identity,
            relation_identity,
            evidence,
            proposed_change,
        ),
    )
    for basis in bases:
        conn.execute(
            """
            INSERT INTO maintenance_batch_item_bases(
                item_id, ordinal, basis_kind, role,
                identity, revision, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                basis.ordinal,
                basis.basis_kind,
                basis.role,
                basis.identity,
                basis.revision,
                basis.fingerprint,
            ),
        )


def get_batch(
    conn: sqlite3.Connection,
    batch_id: str,
) -> BatchRecord | None:
    row = conn.execute(
        "SELECT batch_id, status, created_at, approved_at, executed_at "
        "FROM maintenance_batches WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        return None
    return BatchRecord(**dict(row))


def list_batch_items(
    conn: sqlite3.Connection,
    batch_id: str,
) -> list[BatchItemRecord]:
    rows = conn.execute(
        """
        SELECT item_id, batch_id, ordinal, item_kind, governance_ref,
               target_identity, relation_identity,
               evidence, proposed_change, approval_result,
               status, result_json, error
        FROM maintenance_batch_items
        WHERE batch_id = ?
        ORDER BY ordinal
        """,
        (batch_id,),
    ).fetchall()
    return [BatchItemRecord(**dict(row)) for row in rows]


def list_item_bases(
    conn: sqlite3.Connection,
    item_id: str,
) -> list[BatchItemBasisRecord]:
    rows = conn.execute(
        """
        SELECT item_id, ordinal, basis_kind, role,
               identity, revision, fingerprint
        FROM maintenance_batch_item_bases
        WHERE item_id = ?
        ORDER BY ordinal
        """,
        (item_id,),
    ).fetchall()
    return [BatchItemBasisRecord(**dict(row)) for row in rows]


def approve_batch_subset(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    approved_item_ids: set[str],
) -> None:
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise storage.StorageError(f"maintenance batch does not exist: {batch_id}")
    if batch.status != "pending":
        raise storage.StorageError(f"maintenance batch is not pending: {batch_id}")

    items = list_batch_items(conn, batch_id)
    known_ids = {item.item_id for item in items}
    unknown = approved_item_ids - known_ids
    if unknown:
        raise storage.StorageError(
            "approved batch item does not belong to batch: "
            + ", ".join(sorted(unknown))
        )

    timestamp = storage.now_utc()
    for item in items:
        new_status = "approved" if item.item_id in approved_item_ids else "rejected"
        changed = conn.execute(
            "UPDATE maintenance_batch_items "
            "SET status = ?, approval_result = ? "
            "WHERE item_id = ? AND status = 'pending' "
            "AND approval_result = 'pending'",
            (new_status, new_status, item.item_id),
        ).rowcount
        if changed != 1:
            raise storage.StorageError(
                f"maintenance batch item is not pending: {item.item_id}"
            )

    changed = conn.execute(
        "UPDATE maintenance_batches "
        "SET status = 'approved', approved_at = ? "
        "WHERE batch_id = ? AND status = 'pending'",
        (timestamp, batch_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError(f"maintenance batch is not pending: {batch_id}")


def record_item_execution(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    status: str,
    result_json: str | None,
    error: str | None,
) -> None:
    if status not in {"succeeded", "stale", "failed"}:
        raise storage.StorageError(f"unsupported batch execution status: {status}")
    changed = conn.execute(
        "UPDATE maintenance_batch_items "
        "SET status = ?, result_json = ?, error = ? "
        "WHERE item_id = ? AND status = 'approved'",
        (status, result_json, error, item_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError(
            f"maintenance batch item is not approved: {item_id}"
        )


def finalize_batch_execution(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
) -> str:
    items = list_batch_items(conn, batch_id)
    statuses = {item.status for item in items}
    if "approved" in statuses or "pending" in statuses:
        raise storage.StorageError(
            "maintenance batch cannot be finalized while items remain executable"
        )
    final_status = (
        "partial"
        if statuses.intersection({"stale", "failed"})
        else "completed"
    )
    conn.execute(
        "UPDATE maintenance_batches "
        "SET status = ?, executed_at = COALESCE(executed_at, ?) "
        "WHERE batch_id = ? AND status IN ('approved', 'partial', 'completed')",
        (final_status, storage.now_utc(), batch_id),
    )
    return final_status
