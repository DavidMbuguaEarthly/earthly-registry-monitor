"""
SQLite layer for the monitor.

Keyed by doc_key = "{project_id}:{document_id}", since the new S&P API gives
each document a unique `id` but no FileID and no per-document date/URL.

Schema note: we no longer store a per-document date (the API's doc_modify_date
is always null). We track existence + state_code, and detect NEW documents and
state_code changes. "first_seen_at" is when OUR system first saw the doc.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_key         TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL,
    project_id      INTEGER NOT NULL,
    project_name    TEXT NOT NULL,
    section         TEXT NOT NULL,
    title           TEXT NOT NULL,
    state_code      TEXT,
    url             TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project ON documents(project_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_document(conn: sqlite3.Connection, doc_key: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM documents WHERE doc_key = ?", (doc_key,))
    return cur.fetchone()


def insert_document(conn: sqlite3.Connection, doc: dict) -> None:
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO documents (
            doc_key, doc_id, project_id, project_name, section,
            title, state_code, url, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc["doc_key"], doc["doc_id"], doc["project_id"], doc["project_name"],
            doc["section"], doc["title"], doc["state_code"], doc["url"], ts, ts,
        ),
    )
    conn.commit()


def update_document(conn: sqlite3.Connection, doc: dict) -> None:
    conn.execute(
        """
        UPDATE documents
        SET title = ?, section = ?, state_code = ?, url = ?, last_seen_at = ?
        WHERE doc_key = ?
        """,
        (doc["title"], doc["section"], doc["state_code"], doc["url"],
         now_iso(), doc["doc_key"]),
    )
    conn.commit()


def touch_last_seen(conn: sqlite3.Connection, doc_key: str) -> None:
    conn.execute(
        "UPDATE documents SET last_seen_at = ? WHERE doc_key = ?",
        (now_iso(), doc_key),
    )
    conn.commit()


def total_docs(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]