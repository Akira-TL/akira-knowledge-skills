from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from knowledge_core import storage


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
    return [
        {
            "material_identity": str(row["material_identity"]),
            "material_revision": int(row["material_revision"]),
            "source_locator": str(row["source_locator"]),
            "captured_at": str(row["captured_at"]),
        }
        for row in rows
    ]


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
