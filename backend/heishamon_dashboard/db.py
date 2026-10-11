"""SQLite connection and schema (spec §5.2)."""
import sqlite3

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER);
CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS samples (
    topic_id INTEGER, ts INTEGER, num REAL, txt TEXT, valid INTEGER NOT NULL,
    PRIMARY KEY (topic_id, ts)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS rollup_1m (
    topic_id INTEGER, bucket INTEGER, first_ts INTEGER, last_ts INTEGER,
    covered_seconds REAL NOT NULL, avg REAL, min REAL, max REAL, last REAL,
    PRIMARY KEY (topic_id, bucket)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS rollup_1h (
    topic_id INTEGER, bucket INTEGER, first_ts INTEGER, last_ts INTEGER,
    covered_seconds REAL NOT NULL, avg REAL, min REAL, max REAL, last REAL,
    PRIMARY KEY (topic_id, bucket)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS rollup_state (topic_id INTEGER PRIMARY KEY, materialized_until INTEGER);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY, uuid TEXT UNIQUE NOT NULL,
    submitted_ts INTEGER, published_ts INTEGER, name TEXT, payload TEXT, retained INTEGER,
    class TEXT, prev_value TEXT, status TEXT,
    confirmed_ts INTEGER, attempts INTEGER, detail TEXT, keys TEXT);
CREATE TABLE IF NOT EXISTS events (ts INTEGER, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS outages (
    start_ts INTEGER, end_ts INTEGER, kind TEXT, topic_id INTEGER);
CREATE TABLE IF NOT EXISTS frontier (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    flush_ts INTEGER, device_online INTEGER, last_qualifying_ts INTEGER);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS commands_submitted ON commands (submitted_ts);
CREATE INDEX IF NOT EXISTS outages_start ON outages (start_ts);
"""


class SchemaError(RuntimeError):
    """The database was written by a newer schema than this build understands."""


def connect(path: str) -> sqlite3.Connection:
    """Open (and if needed create) the database: WAL, synchronous=NORMAL, manual transactions."""
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        return
    version = row[0]
    if version > SCHEMA_VERSION:
        raise SchemaError(f"database schema {version} is newer than supported {SCHEMA_VERSION}")
    # forward migrations go here; version 1 is the first schema
    if version < SCHEMA_VERSION:
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
