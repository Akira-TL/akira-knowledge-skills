from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Sequence


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS search_index_meta ("
        "identity TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, indexed_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(identity UNINDEXED, content)"
    )


def reset(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS search_fts")
    conn.execute("DROP TABLE IF EXISTS search_index_meta")
    initialize(conn)


def state(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT identity, fingerprint FROM search_index_meta ORDER BY identity"
    ).fetchall()
    return {str(row["identity"]): str(row["fingerprint"]) for row in rows}


def count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM search_fts").fetchone()
    return int(row["count"])


def rebuild(
    conn: sqlite3.Connection,
    documents: Sequence[tuple[str, str, str]],
) -> None:
    timestamp = _now_utc()
    conn.execute("DELETE FROM search_fts")
    conn.execute("DELETE FROM search_index_meta")
    for identity, fingerprint, content in documents:
        conn.execute(
            "INSERT INTO search_fts(identity, content) VALUES (?, ?)",
            (identity, content),
        )
        conn.execute(
            "INSERT INTO search_index_meta(identity, fingerprint, indexed_at) VALUES (?, ?, ?)",
            (identity, fingerprint, timestamp),
        )


def query(
    conn: sqlite3.Connection,
    query: str,
) -> list[tuple[str, str]]:
    phrase = '"' + query.replace('"', '""') + '"'
    rows = conn.execute(
        "SELECT identity, snippet(search_fts, 1, '[', ']', ' … ', 12) AS evidence "
        "FROM search_fts WHERE search_fts MATCH ? ORDER BY rank",
        (phrase,),
    ).fetchall()
    return [(str(row["identity"]), str(row["evidence"])) for row in rows]
