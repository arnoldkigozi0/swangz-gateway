"""One SQLite file holds everything: people, keys, every request, and the bodies behind them.

A single connection guarded by a lock is plenty for one company's traffic; WAL keeps readers
(the console) from waiting on the writer (the proxy).
"""

import os
import sqlite3
import threading
from contextlib import contextmanager

SCHEMA = [
    # v1
    """
    CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT);

    CREATE TABLE admins (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        pw_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('owner', 'viewer')),
        created REAL NOT NULL,
        last_login REAL
    );
    CREATE TABLE admin_sessions (
        token_hash TEXT PRIMARY KEY,
        admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
        created REAL NOT NULL,
        expires REAL NOT NULL,
        ip TEXT
    );

    CREATE TABLE people (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        department TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
        daily_budget REAL,
        monthly_budget REAL,
        allowed_models TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created REAL NOT NULL
    );

    CREATE TABLE keys (
        id TEXT PRIMARY KEY,
        person_id INTEGER NOT NULL REFERENCES people(id),
        label TEXT NOT NULL DEFAULT '',
        secret_hash TEXT NOT NULL,
        hint TEXT NOT NULL,
        created REAL NOT NULL,
        created_by TEXT NOT NULL DEFAULT '',
        revoked REAL,
        revoked_by TEXT,
        last_used REAL
    );
    CREATE INDEX keys_person ON keys(person_id);

    CREATE TABLE requests (
        id INTEGER PRIMARY KEY,
        ts REAL NOT NULL,
        person_id INTEGER,
        key_id TEXT,
        provider TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        kind TEXT NOT NULL,
        client TEXT NOT NULL DEFAULT '',
        client_ip TEXT NOT NULL DEFAULT '',
        user_agent TEXT NOT NULL DEFAULT '',
        session TEXT,
        model TEXT,
        stream INTEGER NOT NULL DEFAULT 0,
        status INTEGER,
        outcome TEXT NOT NULL,
        reason TEXT,
        duration_ms INTEGER,
        ttft_ms INTEGER,
        in_tok INTEGER NOT NULL DEFAULT 0,
        out_tok INTEGER NOT NULL DEFAULT 0,
        cache_write_tok INTEGER NOT NULL DEFAULT 0,
        cache_read_tok INTEGER NOT NULL DEFAULT 0,
        reasoning_tok INTEGER NOT NULL DEFAULT 0,
        cost REAL,
        prompt TEXT,
        actions TEXT,
        reply TEXT,
        flags TEXT NOT NULL DEFAULT '',
        req_list_field TEXT,
        req_head TEXT,
        req_items TEXT,
        req_bytes INTEGER NOT NULL DEFAULT 0,
        resp_blob TEXT,
        resp_format TEXT,
        resp_bytes INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX requests_ts ON requests(ts);
    CREATE INDEX requests_person_ts ON requests(person_id, ts);
    CREATE INDEX requests_session ON requests(session, ts);

    CREATE TABLE blobs (
        hash TEXT PRIMARY KEY,
        data BLOB NOT NULL,
        size INTEGER NOT NULL
    );

    CREATE TABLE prices (
        model TEXT PRIMARY KEY,
        provider TEXT NOT NULL DEFAULT '',
        input REAL NOT NULL,
        output REAL NOT NULL,
        cache_write REAL,
        cache_write_1h REAL,
        cache_read REAL,
        updated REAL NOT NULL
    );

    CREATE TABLE audit (
        id INTEGER PRIMARY KEY,
        ts REAL NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '',
        ip TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX audit_ts ON audit(ts);
    """,
    # v2: who inside the tool made the request — a sub-agent, a compaction, a background task — and
    # which typed prompt it serves
    """
    ALTER TABLE requests ADD COLUMN request_class TEXT;
    ALTER TABLE requests ADD COLUMN agent TEXT;
    ALTER TABLE requests ADD COLUMN turn_id TEXT;
    CREATE INDEX requests_turn ON requests(turn_id);
    """,
    # v3: staff sign in to the Swangz AI app with an email and a password they set from a one-time link
    """
    ALTER TABLE people ADD COLUMN pw_hash TEXT;
    ALTER TABLE people ADD COLUMN invite_hash TEXT;
    ALTER TABLE people ADD COLUMN invite_expires REAL;
    ALTER TABLE people ADD COLUMN last_login REAL;
    CREATE TABLE staff_sessions (
        token_hash TEXT PRIMARY KEY,
        person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        created REAL NOT NULL,
        expires REAL NOT NULL,
        ip TEXT
    );
    """,
]


class DB:
    def __init__(self, path):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.lock = threading.RLock()
        self.blob_cache = set()  # hashes known to be stored; skips re-compressing repeat messages
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def _migrate(self):
        with self.lock:
            has_meta = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
            ).fetchone()
            version = 0
            if has_meta:
                row = self.conn.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
                version = int(row[0]) if row else 0
            for i, script in enumerate(SCHEMA[version:], start=version + 1):
                self.conn.execute("BEGIN")
                try:
                    for stmt in script.split(";"):
                        if stmt.strip():
                            self.conn.execute(stmt)
                    self.conn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('schema', ?)", (str(i),))
                    self.conn.execute("COMMIT")
                except Exception:
                    self.conn.execute("ROLLBACK")
                    raise

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
            return dict(row) if row else None

    def scalar(self, sql, args=()):
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
            return row[0] if row else None

    def x(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args)

    @contextmanager
    def tx(self):
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                yield self
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                self.blob_cache.clear()  # anything added during this transaction is gone again
                raise

    def get_setting(self, key, default=None):
        row = self.one("SELECT v FROM settings WHERE k=?", (key,))
        return row["v"] if row else default

    def set_setting(self, key, value):
        self.x("INSERT OR REPLACE INTO settings(k, v) VALUES(?, ?)", (key, str(value)))

    def close(self):
        with self.lock:
            self.conn.close()
