from __future__ import annotations

import sqlite3

from knowledge_core.storage import (
    RelationCandidateRecord,
    RelationRecord,
    StorageError,
    now_utc,
)


def insert_relation_candidate(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    source_kind: str,
    source_ref: str,
    source_revision: int | None,
    source_fingerprint: str | None,
    relation_type: str,
    target_kind: str,
    target_ref: str,
    target_revision: int | None,
    target_fingerprint: str | None,
    provenance: str,
) -> None:
    timestamp = now_utc()
    conn.execute(
        "INSERT INTO relation_candidates("
        "candidate_id, status, source_kind, source_ref, source_revision, source_fingerprint, "
        "relation_type, target_kind, target_ref, target_revision, target_fingerprint, "
        "provenance, created_at"
        ") VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            candidate_id,
            source_kind,
            source_ref,
            source_revision,
            source_fingerprint,
            relation_type,
            target_kind,
            target_ref,
            target_revision,
            target_fingerprint,
            provenance,
            timestamp,
        ),
    )


def get_relation_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> RelationCandidateRecord | None:
    row = conn.execute(
        "SELECT candidate_id, status, source_kind, source_ref, source_revision, "
        "source_fingerprint, relation_type, target_kind, target_ref, target_revision, "
        "target_fingerprint, provenance, created_at, decided_at, result_relation_identity "
        "FROM relation_candidates WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    return RelationCandidateRecord(**dict(row))


def mark_relation_candidate_stale(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    timestamp = now_utc()
    changed = conn.execute(
        "UPDATE relation_candidates SET status = 'stale', decided_at = ? "
        "WHERE candidate_id = ? AND status = 'pending'",
        (timestamp, candidate_id),
    ).rowcount
    if changed != 1:
        raise StorageError("relation candidate is not pending")


def reject_relation_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    timestamp = now_utc()
    changed = conn.execute(
        "UPDATE relation_candidates SET status = 'rejected', decided_at = ? "
        "WHERE candidate_id = ? AND status = 'pending'",
        (timestamp, candidate_id),
    ).rowcount
    if changed != 1:
        raise StorageError("relation candidate is not pending")


def get_relation_by_triple(
    conn: sqlite3.Connection,
    *,
    source_ref: str,
    relation_type: str,
    target_ref: str,
) -> RelationRecord | None:
    rows = conn.execute(
        "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
        "FROM relation_records WHERE source_ref = ? AND relation_type = ? AND target_ref = ? "
        "AND status = 'active' "
        "ORDER BY identity",
        (source_ref, relation_type, target_ref),
    ).fetchall()
    if not rows:
        return None
    if len(rows) > 1:
        raise StorageError(
            "multiple Relation Records exist for the same source/type/target triple"
        )
    return RelationRecord(**dict(rows[0]))


def list_relation_provenance(
    conn: sqlite3.Connection,
    relation_identity: str,
) -> list[str]:
    row = conn.execute(
        "SELECT provenance FROM relation_records WHERE identity = ?",
        (relation_identity,),
    ).fetchone()
    if row is None:
        raise StorageError(f"Relation Record does not exist: {relation_identity}")
    additions = conn.execute(
        "SELECT provenance FROM relation_provenance_additions "
        "WHERE relation_identity = ? ORDER BY recorded_at, provenance",
        (relation_identity,),
    ).fetchall()
    return [str(row["provenance"])] + [str(item["provenance"]) for item in additions]


def create_relation_record_from_candidate(
    conn: sqlite3.Connection,
    *,
    relation_identity: str,
    source_ref: str,
    relation_type: str,
    target_ref: str,
    provenance: str,
    candidate_id: str,
) -> None:
    timestamp = now_utc()
    conn.execute(
        "INSERT INTO relation_records(identity, source_ref, relation_type, target_ref, provenance, revision) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (relation_identity, source_ref, relation_type, target_ref, provenance),
    )
    conn.execute(
        "INSERT INTO relation_events(relation_identity, revision, event, provenance, recorded_at) "
        "VALUES (?, 1, 'created_from_candidate', ?, ?)",
        (relation_identity, provenance, timestamp),
    )
    changed = conn.execute(
        "UPDATE relation_candidates SET status = 'accepted', decided_at = ?, "
        "result_relation_identity = ? WHERE candidate_id = ? AND status = 'pending'",
        (timestamp, relation_identity, candidate_id),
    ).rowcount
    if changed != 1:
        raise StorageError("relation candidate is not pending")


def add_relation_provenance_from_candidate(
    conn: sqlite3.Connection,
    *,
    relation_identity: str,
    provenance: str,
    candidate_id: str,
) -> tuple[int, bool]:
    record = conn.execute(
        "SELECT provenance, revision, status FROM relation_records WHERE identity = ?",
        (relation_identity,),
    ).fetchone()
    if record is None:
        raise StorageError(f"Relation Record does not exist: {relation_identity}")
    if str(record["status"]) != "active":
        raise StorageError(f"Relation Record is not active: {relation_identity}")

    existing = {str(record["provenance"])}
    existing.update(
        str(row["provenance"])
        for row in conn.execute(
            "SELECT provenance FROM relation_provenance_additions WHERE relation_identity = ?",
            (relation_identity,),
        ).fetchall()
    )
    timestamp = now_utc()
    changed_revision = False
    revision = int(record["revision"])
    if provenance not in existing:
        revision += 1
        conn.execute(
            "INSERT INTO relation_provenance_additions(relation_identity, provenance, recorded_at) "
            "VALUES (?, ?, ?)",
            (relation_identity, provenance, timestamp),
        )
        conn.execute(
            "UPDATE relation_records SET revision = ? WHERE identity = ?",
            (revision, relation_identity),
        )
        conn.execute(
            "INSERT INTO relation_events(relation_identity, revision, event, provenance, recorded_at) "
            "VALUES (?, ?, 'provenance_added', ?, ?)",
            (relation_identity, revision, provenance, timestamp),
        )
        changed_revision = True

    changed = conn.execute(
        "UPDATE relation_candidates SET status = 'accepted', decided_at = ?, "
        "result_relation_identity = ? WHERE candidate_id = ? AND status = 'pending'",
        (timestamp, relation_identity, candidate_id),
    ).rowcount
    if changed != 1:
        raise StorageError("relation candidate is not pending")
    return revision, changed_revision


def get_relation_record(
    conn: sqlite3.Connection,
    relation_identity: str,
) -> RelationRecord | None:
    row = conn.execute(
        "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
        "FROM relation_records WHERE identity = ?",
        (relation_identity,),
    ).fetchone()
    if row is None:
        return None
    return RelationRecord(**dict(row))


def revoke_relation_record(
    conn: sqlite3.Connection,
    *,
    relation_identity: str,
    expected_revision: int,
) -> tuple[RelationRecord, bool]:
    record = get_relation_record(conn, relation_identity)
    if record is None:
        raise StorageError(f"Relation Record does not exist: {relation_identity}")
    if record.revision != expected_revision:
        raise StorageError(
            "Relation Record revision changed after it was read; "
            "re-read current relation Authority before revoking"
        )
    if record.status == "revoked":
        return record, False
    if record.status != "active":
        raise StorageError(
            f"Unsupported Relation Record status: {record.status}"
        )

    new_revision = record.revision + 1
    timestamp = now_utc()
    conn.execute(
        "UPDATE relation_records SET status = 'revoked', revision = ? "
        "WHERE identity = ? AND status = 'active' AND revision = ?",
        (new_revision, relation_identity, expected_revision),
    )
    conn.execute(
        "INSERT INTO relation_events(relation_identity, revision, event, provenance, recorded_at) "
        "VALUES (?, ?, 'revoked', NULL, ?)",
        (relation_identity, new_revision, timestamp),
    )
    updated = get_relation_record(conn, relation_identity)
    if updated is None:
        raise StorageError(f"Relation Record does not exist: {relation_identity}")
    return updated, True


def list_active_relation_records(conn: sqlite3.Connection) -> list[RelationRecord]:
    rows = conn.execute(
        "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
        "FROM relation_records WHERE status = 'active' ORDER BY identity"
    ).fetchall()
    return [RelationRecord(**dict(row)) for row in rows]


def list_relation_neighbors(
    conn: sqlite3.Connection,
    *,
    seed_ref: str,
    direction: str,
    relation_type: str | None,
) -> list[RelationRecord]:
    if direction not in {"outgoing", "incoming"}:
        raise StorageError(f"unsupported relation traversal direction: {direction}")
    endpoint_column = "source_ref" if direction == "outgoing" else "target_ref"
    sql = (
        "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
        f"FROM relation_records WHERE {endpoint_column} = ? AND status = 'active'"
    )
    params: list[object] = [seed_ref]
    if relation_type is not None:
        sql += " AND relation_type = ?"
        params.append(relation_type)
    sql += " ORDER BY identity"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [RelationRecord(**dict(row)) for row in rows]
