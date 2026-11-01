"""Postgres storage for the complaint module (schema ``civic_flow`` in the shared CitySense database).

Enabled when ``COMPLAINT_DATABASE_URL`` is set (docker compose sets it); otherwise the module keeps
its JSON files (local dev, tests). Records are stored as JSONB documents with the fields the
module queries on (status, timestamps) promoted to columns, so the domain models stay unchanged.
On first start an empty table is filled from the existing JSON file, so no data is lost.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Iterable, Optional

DATABASE_URL = os.getenv("COMPLAINT_DATABASE_URL") or None

_LOCK = threading.RLock()
_conn = None

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS civic_flow;
CREATE TABLE IF NOT EXISTS civic_flow.complaints (
    tracking_id  TEXT PRIMARY KEY,
    status       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL,
    data         JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flow_complaints_created ON civic_flow.complaints (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_flow_complaints_status ON civic_flow.complaints (status);
CREATE TABLE IF NOT EXISTS civic_flow.notices (
    id            TEXT PRIMARY KEY,
    publish_date  TIMESTAMPTZ NOT NULL,
    expiry_date   TIMESTAMPTZ,
    pinned        BOOLEAN NOT NULL DEFAULT false,
    data          JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flow_notices_publish ON civic_flow.notices (publish_date DESC);
CREATE TABLE IF NOT EXISTS civic_flow.photos (
    name          TEXT PRIMARY KEY,
    content_type  TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 10485760),
    data          BYTEA NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def enabled() -> bool:
    return DATABASE_URL is not None


def _connection():
    """One shared connection, reopened if the database restarted. Callers hold _LOCK."""
    global _conn
    import psycopg
    from psycopg.types.json import set_json_loads

    if _conn is None or _conn.closed or _conn.broken:
        _conn = psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=5)
        set_json_loads(json.loads, _conn)
    return _conn


def _run(sql: str, params: Iterable[Any] | None = None, fetch: bool = False):
    with _LOCK:
        for attempt in (1, 2):
            try:
                with _connection().cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall() if fetch else None
            except Exception:
                if attempt == 2:
                    raise
                global _conn
                _conn = None  # reconnect once (e.g. database restarted)


def init(seed_complaints: list[dict] | None = None, seed_notices: list[dict] | None = None) -> None:
    """Create the schema and, if the tables are empty, import the existing JSON data."""
    from psycopg.types.json import Jsonb

    with _LOCK:
        with _connection().transaction():
            with _connection().cursor() as cur:
                cur.execute(SCHEMA_SQL)
                cur.execute("SELECT count(*) FROM civic_flow.complaints")
                if cur.fetchone()[0] == 0 and seed_complaints:
                    for c in seed_complaints:
                        cur.execute(*_upsert_complaint_sql(c, Jsonb))
                cur.execute("SELECT count(*) FROM civic_flow.notices")
                if cur.fetchone()[0] == 0 and seed_notices:
                    for n in seed_notices:
                        cur.execute(*_upsert_notice_sql(n, Jsonb))


# ── complaints ────────────────────────────────────────────────────────────────

def _upsert_complaint_sql(c: dict, Jsonb):
    return (
        """INSERT INTO civic_flow.complaints (tracking_id, status, created_at, updated_at, data)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (tracking_id) DO UPDATE
           SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at, data = EXCLUDED.data""",
        (c["tracking_id"], str(c.get("status")), c["created_at"], c.get("updated_at") or c["created_at"], Jsonb(c)),
    )


def list_complaints() -> list[dict]:
    rows = _run("SELECT data FROM civic_flow.complaints ORDER BY created_at DESC", fetch=True)
    return [r[0] for r in rows]


def get_complaint(tracking_id: str) -> Optional[dict]:
    rows = _run("SELECT data FROM civic_flow.complaints WHERE lower(tracking_id) = lower(%s)", (tracking_id,), fetch=True)
    return rows[0][0] if rows else None


def upsert_complaint(c: dict) -> None:
    from psycopg.types.json import Jsonb

    _run(*_upsert_complaint_sql(c, Jsonb))


def replace_complaints(items: list[dict]) -> None:
    from psycopg.types.json import Jsonb

    with _LOCK:
        with _connection().transaction():
            with _connection().cursor() as cur:
                cur.execute("DELETE FROM civic_flow.complaints")
                for c in items:
                    cur.execute(*_upsert_complaint_sql(c, Jsonb))


# ── notices ───────────────────────────────────────────────────────────────────

def _upsert_notice_sql(n: dict, Jsonb):
    return (
        """INSERT INTO civic_flow.notices (id, publish_date, expiry_date, pinned, data)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE
           SET publish_date = EXCLUDED.publish_date, expiry_date = EXCLUDED.expiry_date,
               pinned = EXCLUDED.pinned, data = EXCLUDED.data""",
        (n["id"], n["publishDate"], n.get("expiryDate") or None, bool(n.get("isPinned")), Jsonb(n)),
    )


def list_notices() -> list[dict]:
    rows = _run("SELECT data FROM civic_flow.notices ORDER BY publish_date DESC", fetch=True)
    return [r[0] for r in rows]


def replace_notices(items: list[dict]) -> None:
    from psycopg.types.json import Jsonb

    with _LOCK:
        with _connection().transaction():
            with _connection().cursor() as cur:
                cur.execute("DELETE FROM civic_flow.notices")
                for n in items:
                    cur.execute(*_upsert_notice_sql(n, Jsonb))


# ── photos (complaint evidence) ───────────────────────────────────────────────

def save_photo(name: str, content_type: str, data: bytes) -> None:
    _run(
        "INSERT INTO civic_flow.photos (name, content_type, size_bytes, data) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (name) DO NOTHING",
        (name, content_type, len(data), data),
    )


def get_photo(name: str) -> Optional[tuple[bytes, str]]:
    rows = _run("SELECT data, content_type FROM civic_flow.photos WHERE name = %s", (name,), fetch=True)
    return (bytes(rows[0][0]), rows[0][1]) if rows else None
