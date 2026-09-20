from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from knowledge_core import storage


@dataclass(frozen=True)
class ConflictCandidateRecord:
    candidate_id: str
    status: str
    conflict: str
    evidence: str
    created_at: str
    decided_at: str | None


@dataclass(frozen=True)
class ConflictCandidateMemberRecord:
    candidate_id: str
    ordinal: int
    member_kind: str
    member_ref: str
    basis_identity: str
    revision: int
    fingerprint: str
    canonical_locator: str


@dataclass(frozen=True)
class RelationMaintenanceCandidateRecord:
    candidate_id: str
    candidate_kind: str
    status: str
    relation_identity: str
    relation_revision: int
    relation_fingerprint: str
    source_kind: str
    source_ref: str
    source_revision: int | None
    source_fingerprint: str | None
    target_kind: str
    target_ref: str
    target_revision: int | None
    target_fingerprint: str | None
    evidence: str
    source_finding_id: str | None
    evidence_basis_identity: str | None
    evidence_basis_revision: int | None
    evidence_basis_fingerprint: str | None
    created_at: str
    decided_at: str | None


@dataclass(frozen=True)
class SourceFindingRecord:
    finding_id: str
    finding_kind: str
    source_state: str
    target_identity: str
    target_revision: int
    target_fingerprint: str
    source_locator: str
    basis_source_id: str
    basis_revision: str
    basis_fingerprint: str
    observed_source_id: str | None
    observed_revision: str | None
    observed_fingerprint: str | None
    evidence: str
    created_at: str


@dataclass(frozen=True)
class MaintenanceCandidateRecord:
    candidate_id: str
    candidate_kind: str
    status: str
    target_identity: str
    target_revision: int
    target_fingerprint: str
    source_locator: str
    basis_source_id: str
    basis_revision: str
    basis_fingerprint: str
    observed_source_id: str
    observed_revision: str
    observed_fingerprint: str
    evidence: str
    source_finding_id: str
    created_at: str
    decided_at: str | None


_REQUIRED_TABLES = ("review_findings", "maintenance_candidates")
_V5_REQUIRED_TABLES = (
    "review_findings",
    "maintenance_candidates",
    "conflict_candidates",
    "conflict_candidate_members",
    "relation_maintenance_candidates",
)


def migrate_schema_to_v4(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        BEGIN IMMEDIATE;

        CREATE TABLE review_findings (
            finding_id TEXT PRIMARY KEY,
            finding_kind TEXT NOT NULL CHECK (finding_kind = 'source_review'),
            source_state TEXT NOT NULL CHECK (source_state IN ('changed', 'unchanged', 'unknown')),
            target_identity TEXT NOT NULL,
            target_revision INTEGER NOT NULL CHECK (target_revision >= 1),
            target_fingerprint TEXT NOT NULL,
            source_locator TEXT NOT NULL,
            basis_source_id TEXT NOT NULL,
            basis_revision TEXT NOT NULL,
            basis_fingerprint TEXT NOT NULL,
            observed_source_id TEXT,
            observed_revision TEXT,
            observed_fingerprint TEXT,
            evidence TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (target_identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            CHECK (
                (source_state = 'unknown'
                    AND observed_source_id IS NULL
                    AND observed_revision IS NULL
                    AND observed_fingerprint IS NULL)
                OR (source_state != 'unknown'
                    AND observed_source_id IS NOT NULL
                    AND observed_revision IS NOT NULL
                    AND observed_fingerprint IS NOT NULL)
            )
        );
        CREATE INDEX review_findings_target_idx
            ON review_findings(target_identity, created_at);

        CREATE TABLE maintenance_candidates (
            candidate_id TEXT PRIMARY KEY,
            candidate_kind TEXT NOT NULL CHECK (candidate_kind = 'source_stale'),
            status TEXT NOT NULL CHECK (status IN ('pending', 'rejected', 'stale')),
            target_identity TEXT NOT NULL,
            target_revision INTEGER NOT NULL CHECK (target_revision >= 1),
            target_fingerprint TEXT NOT NULL,
            source_locator TEXT NOT NULL,
            basis_source_id TEXT NOT NULL,
            basis_revision TEXT NOT NULL,
            basis_fingerprint TEXT NOT NULL,
            observed_source_id TEXT NOT NULL,
            observed_revision TEXT NOT NULL,
            observed_fingerprint TEXT NOT NULL,
            evidence TEXT NOT NULL,
            source_finding_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            FOREIGN KEY (target_identity) REFERENCES objects(identity) ON DELETE RESTRICT,
            FOREIGN KEY (source_finding_id) REFERENCES review_findings(finding_id) ON DELETE RESTRICT
        );
        CREATE INDEX maintenance_candidates_status_idx
            ON maintenance_candidates(status);
        CREATE INDEX maintenance_candidates_target_idx
            ON maintenance_candidates(target_identity, status);

        INSERT INTO schema_meta(key, value)
            VALUES ('schema_version', '4')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;

        COMMIT;
        """
    )


def migrate_schema_v4_to_v5(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        BEGIN IMMEDIATE;

        CREATE TABLE conflict_candidates (
            candidate_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('pending', 'rejected', 'stale')),
            conflict TEXT NOT NULL,
            evidence TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT
        );
        CREATE INDEX conflict_candidates_status_idx
            ON conflict_candidates(status);

        CREATE TABLE conflict_candidate_members (
            candidate_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            member_kind TEXT NOT NULL CHECK (
                member_kind IN ('knowledge_asset', 'source_finding', 'relation_record')
            ),
            member_ref TEXT NOT NULL,
            basis_identity TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            fingerprint TEXT NOT NULL,
            canonical_locator TEXT NOT NULL,
            PRIMARY KEY (candidate_id, ordinal),
            FOREIGN KEY (candidate_id) REFERENCES conflict_candidates(candidate_id) ON DELETE RESTRICT
        );
        CREATE INDEX conflict_candidate_members_ref_idx
            ON conflict_candidate_members(member_kind, member_ref);

        CREATE TABLE relation_maintenance_candidates (
            candidate_id TEXT PRIMARY KEY,
            candidate_kind TEXT NOT NULL CHECK (
                candidate_kind IN ('relation_stale', 'relation_conflict')
            ),
            status TEXT NOT NULL CHECK (status IN ('pending', 'rejected', 'stale')),
            relation_identity TEXT NOT NULL,
            relation_revision INTEGER NOT NULL CHECK (relation_revision >= 1),
            relation_fingerprint TEXT NOT NULL,
            source_kind TEXT NOT NULL CHECK (source_kind IN ('knowledge', 'external')),
            source_ref TEXT NOT NULL,
            source_revision INTEGER,
            source_fingerprint TEXT,
            target_kind TEXT NOT NULL CHECK (target_kind IN ('knowledge', 'external')),
            target_ref TEXT NOT NULL,
            target_revision INTEGER,
            target_fingerprint TEXT,
            evidence TEXT NOT NULL,
            source_finding_id TEXT,
            evidence_basis_identity TEXT,
            evidence_basis_revision INTEGER,
            evidence_basis_fingerprint TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            CHECK (
                (source_kind = 'knowledge'
                    AND source_revision IS NOT NULL
                    AND source_fingerprint IS NOT NULL)
                OR (source_kind = 'external'
                    AND source_revision IS NULL
                    AND source_fingerprint IS NULL)
            ),
            CHECK (
                (target_kind = 'knowledge'
                    AND target_revision IS NOT NULL
                    AND target_fingerprint IS NOT NULL)
                OR (target_kind = 'external'
                    AND target_revision IS NULL
                    AND target_fingerprint IS NULL)
            ),
            CHECK (
                (source_finding_id IS NULL
                    AND evidence_basis_identity IS NULL
                    AND evidence_basis_revision IS NULL
                    AND evidence_basis_fingerprint IS NULL)
                OR (source_finding_id IS NOT NULL
                    AND evidence_basis_identity IS NOT NULL
                    AND evidence_basis_revision IS NOT NULL
                    AND evidence_basis_fingerprint IS NOT NULL)
            ),
            FOREIGN KEY (source_finding_id) REFERENCES review_findings(finding_id) ON DELETE RESTRICT
        );
        CREATE INDEX relation_maintenance_candidates_status_idx
            ON relation_maintenance_candidates(status);
        CREATE INDEX relation_maintenance_candidates_relation_idx
            ON relation_maintenance_candidates(relation_identity, status);

        UPDATE schema_meta
            SET value = '5'
            WHERE key = 'schema_version';

        COMMIT;
        """
    )


def validate_schema_v5(conn: sqlite3.Connection) -> None:
    present = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ("
            "'review_findings', 'maintenance_candidates', "
            "'conflict_candidates', 'conflict_candidate_members', "
            "'relation_maintenance_candidates'"
            ")"
        ).fetchall()
    }
    missing = [name for name in _V5_REQUIRED_TABLES if name not in present]
    if missing:
        raise storage.StorageError(
            "Review structured Authority is missing required v5 tables: "
            + ", ".join(missing)
        )


def validate_schema_v4(conn: sqlite3.Connection) -> None:
    present = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('review_findings', 'maintenance_candidates')"
        ).fetchall()
    }
    missing = [name for name in _REQUIRED_TABLES if name not in present]
    if missing:
        raise storage.StorageError(
            "Review structured Authority is missing required tables: "
            + ", ".join(missing)
        )


def list_target_sources(
    conn: sqlite3.Connection,
    *,
    target_identity: str,
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT DISTINCT
               ms.material_identity,
               ms.locator AS source_locator,
               ms.captured_at,
               o.revision AS material_revision
        FROM knowledge_asset_materials kam
        JOIN material_sources ms
          ON ms.material_identity = kam.material_identity
        JOIN objects o
          ON o.identity = ms.material_identity
        WHERE kam.asset_identity = ?
        ORDER BY ms.locator, ms.material_identity
        """,
        (target_identity,),
    ).fetchall()
    sources: list[dict[str, object]] = []
    for row in rows:
        source_locator = str(row["source_locator"])
        verified = conn.execute(
            """
            SELECT observed_source_id, observed_revision, observed_fingerprint,
                   evidence, created_at
            FROM review_findings
            WHERE target_identity = ?
              AND source_locator = ?
              AND source_state IN ('changed', 'unchanged')
            ORDER BY created_at DESC, finding_id DESC
            LIMIT 1
            """,
            (target_identity, source_locator),
        ).fetchone()
        last_verified = (
            None
            if verified is None
            else {
                "source_id": str(verified["observed_source_id"]),
                "revision": str(verified["observed_revision"]),
                "fingerprint": str(verified["observed_fingerprint"]),
                "evidence": str(verified["evidence"]),
                "verified_at": str(verified["created_at"]),
            }
        )
        sources.append(
            {
                "material_identity": str(row["material_identity"]),
                "material_revision": int(row["material_revision"]),
                "source_locator": source_locator,
                "captured_at": str(row["captured_at"]),
                "last_verified": last_verified,
            }
        )
    return sources


def source_in_target_provenance(
    conn: sqlite3.Connection,
    *,
    target_identity: str,
    source_locator: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM knowledge_asset_materials kam
        JOIN material_sources ms
          ON ms.material_identity = kam.material_identity
        WHERE kam.asset_identity = ?
          AND ms.locator = ?
        LIMIT 1
        """,
        (target_identity, source_locator),
    ).fetchone()
    return row is not None


def insert_source_review(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    source_state: str,
    target_identity: str,
    target_revision: int,
    target_fingerprint: str,
    source_locator: str,
    basis_source_id: str,
    basis_revision: str,
    basis_fingerprint: str,
    evidence: str,
    observed_source_id: str | None = None,
    observed_revision: str | None = None,
    observed_fingerprint: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO review_findings(
            finding_id, finding_kind, source_state,
            target_identity, target_revision, target_fingerprint,
            source_locator,
            basis_source_id, basis_revision, basis_fingerprint,
            observed_source_id, observed_revision, observed_fingerprint,
            evidence, created_at
        ) VALUES (?, 'source_review', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            finding_id,
            source_state,
            target_identity,
            target_revision,
            target_fingerprint,
            source_locator,
            basis_source_id,
            basis_revision,
            basis_fingerprint,
            observed_source_id,
            observed_revision,
            observed_fingerprint,
            evidence,
            storage.now_utc(),
        ),
    )


def get_source_finding(
    conn: sqlite3.Connection,
    finding_id: str,
) -> SourceFindingRecord | None:
    row = conn.execute(
        """
        SELECT finding_id, finding_kind, source_state,
               target_identity, target_revision, target_fingerprint,
               source_locator,
               basis_source_id, basis_revision, basis_fingerprint,
               observed_source_id, observed_revision, observed_fingerprint,
               evidence, created_at
        FROM review_findings
        WHERE finding_id = ?
        """,
        (finding_id,),
    ).fetchone()
    if row is None:
        return None
    return SourceFindingRecord(**dict(row))


def insert_source_stale_candidate(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    finding_id: str,
    target_identity: str,
    target_revision: int,
    target_fingerprint: str,
    source_locator: str,
    basis_source_id: str,
    basis_revision: str,
    basis_fingerprint: str,
    observed_source_id: str,
    observed_revision: str,
    observed_fingerprint: str,
    evidence: str,
) -> None:
    conn.execute(
        """
        INSERT INTO maintenance_candidates(
            candidate_id, candidate_kind, status,
            target_identity, target_revision, target_fingerprint,
            source_locator,
            basis_source_id, basis_revision, basis_fingerprint,
            observed_source_id, observed_revision, observed_fingerprint,
            evidence, source_finding_id, created_at
        ) VALUES (?, 'source_stale', 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            target_identity,
            target_revision,
            target_fingerprint,
            source_locator,
            basis_source_id,
            basis_revision,
            basis_fingerprint,
            observed_source_id,
            observed_revision,
            observed_fingerprint,
            evidence,
            finding_id,
            storage.now_utc(),
        ),
    )


def insert_conflict_candidate(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    conflict: str,
    evidence: str,
    members: list[ConflictCandidateMemberRecord],
) -> None:
    timestamp = storage.now_utc()
    conn.execute(
        "INSERT INTO conflict_candidates("
        "candidate_id, status, conflict, evidence, created_at"
        ") VALUES (?, 'pending', ?, ?, ?)",
        (candidate_id, conflict, evidence, timestamp),
    )
    for member in members:
        conn.execute(
            "INSERT INTO conflict_candidate_members("
            "candidate_id, ordinal, member_kind, member_ref, basis_identity, "
            "revision, fingerprint, canonical_locator"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                candidate_id,
                member.ordinal,
                member.member_kind,
                member.member_ref,
                member.basis_identity,
                member.revision,
                member.fingerprint,
                member.canonical_locator,
            ),
        )


def get_conflict_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> ConflictCandidateRecord | None:
    row = conn.execute(
        "SELECT candidate_id, status, conflict, evidence, created_at, decided_at "
        "FROM conflict_candidates WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    return ConflictCandidateRecord(**dict(row))


def list_conflict_candidate_members(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> list[ConflictCandidateMemberRecord]:
    rows = conn.execute(
        "SELECT candidate_id, ordinal, member_kind, member_ref, basis_identity, "
        "revision, fingerprint, canonical_locator "
        "FROM conflict_candidate_members WHERE candidate_id = ? ORDER BY ordinal",
        (candidate_id,),
    ).fetchall()
    return [ConflictCandidateMemberRecord(**dict(row)) for row in rows]


def insert_relation_maintenance_candidate(
    conn: sqlite3.Connection,
    *,
    candidate_id: str,
    candidate_kind: str,
    relation_identity: str,
    relation_revision: int,
    relation_fingerprint: str,
    source_kind: str,
    source_ref: str,
    source_revision: int | None,
    source_fingerprint: str | None,
    target_kind: str,
    target_ref: str,
    target_revision: int | None,
    target_fingerprint: str | None,
    evidence: str,
    source_finding_id: str | None = None,
    evidence_basis_identity: str | None = None,
    evidence_basis_revision: int | None = None,
    evidence_basis_fingerprint: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO relation_maintenance_candidates(
            candidate_id, candidate_kind, status,
            relation_identity, relation_revision, relation_fingerprint,
            source_kind, source_ref, source_revision, source_fingerprint,
            target_kind, target_ref, target_revision, target_fingerprint,
            evidence, source_finding_id, evidence_basis_identity,
            evidence_basis_revision, evidence_basis_fingerprint, created_at
        ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            candidate_kind,
            relation_identity,
            relation_revision,
            relation_fingerprint,
            source_kind,
            source_ref,
            source_revision,
            source_fingerprint,
            target_kind,
            target_ref,
            target_revision,
            target_fingerprint,
            evidence,
            source_finding_id,
            evidence_basis_identity,
            evidence_basis_revision,
            evidence_basis_fingerprint,
            storage.now_utc(),
        ),
    )


def get_relation_maintenance_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> RelationMaintenanceCandidateRecord | None:
    row = conn.execute(
        """
        SELECT candidate_id, candidate_kind, status,
               relation_identity, relation_revision, relation_fingerprint,
               source_kind, source_ref, source_revision, source_fingerprint,
               target_kind, target_ref, target_revision, target_fingerprint,
               evidence, source_finding_id, evidence_basis_identity,
               evidence_basis_revision, evidence_basis_fingerprint,
               created_at, decided_at
        FROM relation_maintenance_candidates
        WHERE candidate_id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    return RelationMaintenanceCandidateRecord(**dict(row))


def mark_relation_maintenance_candidate_stale(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    changed = conn.execute(
        "UPDATE relation_maintenance_candidates "
        "SET status = 'stale', decided_at = ? "
        "WHERE candidate_id = ? AND status = 'pending'",
        (storage.now_utc(), candidate_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("relation maintenance candidate is not pending")


def reject_relation_maintenance_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    changed = conn.execute(
        "UPDATE relation_maintenance_candidates "
        "SET status = 'rejected', decided_at = ? "
        "WHERE candidate_id = ? AND status IN ('pending', 'stale')",
        (storage.now_utc(), candidate_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("relation maintenance candidate cannot be rejected")


def mark_conflict_candidate_stale(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    changed = conn.execute(
        "UPDATE conflict_candidates "
        "SET status = 'stale', decided_at = ? "
        "WHERE candidate_id = ? AND status = 'pending'",
        (storage.now_utc(), candidate_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("conflict candidate is not pending")


def reject_conflict_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    changed = conn.execute(
        "UPDATE conflict_candidates "
        "SET status = 'rejected', decided_at = ? "
        "WHERE candidate_id = ? AND status IN ('pending', 'stale')",
        (storage.now_utc(), candidate_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("conflict candidate cannot be rejected")


def mark_candidate_stale(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    changed = conn.execute(
        "UPDATE maintenance_candidates "
        "SET status = 'stale', decided_at = ? "
        "WHERE candidate_id = ? AND status = 'pending'",
        (storage.now_utc(), candidate_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("maintenance candidate is not pending")


def reject_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> None:
    changed = conn.execute(
        "UPDATE maintenance_candidates "
        "SET status = 'rejected', decided_at = ? "
        "WHERE candidate_id = ? AND status IN ('pending', 'stale')",
        (storage.now_utc(), candidate_id),
    ).rowcount
    if changed != 1:
        raise storage.StorageError("maintenance candidate cannot be rejected")


def get_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> MaintenanceCandidateRecord | None:
    row = conn.execute(
        """
        SELECT candidate_id, candidate_kind, status,
               target_identity, target_revision, target_fingerprint,
               source_locator,
               basis_source_id, basis_revision, basis_fingerprint,
               observed_source_id, observed_revision, observed_fingerprint,
               evidence, source_finding_id, created_at, decided_at
        FROM maintenance_candidates
        WHERE candidate_id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    return MaintenanceCandidateRecord(**dict(row))
