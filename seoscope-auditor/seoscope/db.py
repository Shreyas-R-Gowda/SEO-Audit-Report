"""SQLite persistence for audits, crawled pages and issues.

A plain, synchronous sqlite3 wrapper is used deliberately: audits run one
at a time from the dashboard, so there is no concurrency to design around,
and sqlite3 needs no extra dependency or server process.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from seoscope.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    started_at REAL NOT NULL,
    finished_at REAL,
    pages_crawled INTEGER DEFAULT 0,
    max_pages INTEGER DEFAULT 0,
    overall_score REAL,
    category_scores TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id INTEGER NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    status_code INTEGER,
    redirect_chain TEXT,
    load_time_ms REAL,
    title TEXT,
    meta_description TEXT,
    h1_count INTEGER,
    word_count INTEGER,
    canonical TEXT,
    is_indexable INTEGER,
    internal_links INTEGER,
    external_links INTEGER,
    broken_links INTEGER,
    missing_alt_count INTEGER,
    images_count INTEGER,
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id INTEGER NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    page_url TEXT,
    affected_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_pages_audit ON pages(audit_id);
CREATE INDEX IF NOT EXISTS idx_issues_audit ON issues(audit_id);
"""


def get_connection():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_audit(root_url: str, max_pages: int) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO audits (root_url, status, started_at, max_pages) VALUES (?, 'running', ?, ?)",
            (root_url, time.time(), max_pages),
        )
        return cur.lastrowid


def finish_audit(audit_id: int, pages_crawled: int, overall_score: float, category_scores: dict):
    with connect() as conn:
        conn.execute(
            """UPDATE audits
               SET status='completed', finished_at=?, pages_crawled=?,
                   overall_score=?, category_scores=?
               WHERE id=?""",
            (time.time(), pages_crawled, overall_score, json.dumps(category_scores), audit_id),
        )


def fail_audit(audit_id: int, error: str):
    with connect() as conn:
        conn.execute(
            "UPDATE audits SET status='failed', finished_at=?, error=? WHERE id=?",
            (time.time(), error, audit_id),
        )


def add_page(audit_id: int, page: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO pages (
                audit_id, url, status_code, redirect_chain, load_time_ms, title,
                meta_description, h1_count, word_count, canonical, is_indexable,
                internal_links, external_links, broken_links, missing_alt_count,
                images_count, content_hash
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                audit_id, page["url"], page.get("status_code"),
                json.dumps(page.get("redirect_chain", [])), page.get("load_time_ms"),
                page.get("title"), page.get("meta_description"), page.get("h1_count"),
                page.get("word_count"), page.get("canonical"), int(page.get("is_indexable", True)),
                page.get("internal_links"), page.get("external_links"), page.get("broken_links"),
                page.get("missing_alt_count"), page.get("images_count"), page.get("content_hash"),
            ),
        )
        return cur.lastrowid


def add_issue(audit_id: int, issue: dict):
    with connect() as conn:
        conn.execute(
            """INSERT INTO issues (
                audit_id, category, severity, title, description, recommendation,
                page_url, affected_count
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                audit_id, issue["category"], issue["severity"], issue["title"],
                issue["description"], issue["recommendation"], issue.get("page_url"),
                issue.get("affected_count", 1),
            ),
        )


def get_audit(audit_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM audits WHERE id=?", (audit_id,)).fetchone()
        return dict(row) if row else None


def list_audits(limit: int = 25) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audits ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_pages(audit_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pages WHERE audit_id=? ORDER BY id", (audit_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_issues(audit_id: int) -> list[dict]:
    severity_order = "CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM issues WHERE audit_id=? ORDER BY {severity_order}, affected_count DESC",
            (audit_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_audit(audit_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM audits WHERE id=?", (audit_id,))
