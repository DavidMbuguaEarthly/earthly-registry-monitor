"""
SQLite layer for the monitor.

Single table 'documents' keyed by file_id. Tracks every doc Verra has shown
us, when we first noticed it, and when we last saw it (to detect updates).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    file_id         INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL,
    project_name    TEXT NOT NULL,
    section         TEXT NOT NULL,
    title           TEXT NOT NULL,
    date_updated    TEXT NOT NULL,
    url             TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project ON documents(project_id);
"""


def now_iso() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(db_path: Path) -> sqlite3.Connection:
    """Open the DB (creating it if needed) and ensure the schema exists."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_document(conn: sqlite3.Connection, file_id: int) -> sqlite3.Row | None:
    """Look up a document by its Verra FileID. Returns None if not seen before."""
    cur = conn.execute("SELECT * FROM documents WHERE file_id = ?", (file_id,))
    return cur.fetchone()


def insert_document(conn: sqlite3.Connection, doc: dict) -> None:
    """Insert a freshly discovered document."""
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO documents (
            file_id, project_id, project_name, section,
            title, date_updated, url, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc["file_id"], doc["project_id"], doc["project_name"], doc["section"],
            doc["title"], doc["date_updated"], doc["url"], ts, ts,
        ),
    )
    conn.commit()


def update_document(conn: sqlite3.Connection, doc: dict) -> None:
    """Update an existing document (date_updated, title, or URL changed)."""
    conn.execute(
        """
        UPDATE documents
        SET title = ?, date_updated = ?, url = ?, last_seen_at = ?
        WHERE file_id = ?
        """,
        (doc["title"], doc["date_updated"], doc["url"], now_iso(), doc["file_id"]),
    )
    conn.commit()


def touch_last_seen(conn: sqlite3.Connection, file_id: int) -> None:
    """Update last_seen_at without changing anything else (doc unchanged)."""
    conn.execute(
        "UPDATE documents SET last_seen_at = ? WHERE file_id = ?",
        (now_iso(), file_id),
    )
    conn.commit()


def total_docs(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]