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
    # v4: voice, image and video services (ElevenLabs, Higgsfield, …) and per-person service rules
    """
    ALTER TABLE requests ADD COLUMN media_type TEXT;
    ALTER TABLE requests ADD COLUMN units REAL;
    ALTER TABLE requests ADD COLUMN unit TEXT;
    ALTER TABLE requests ADD COLUMN result_urls TEXT;
    ALTER TABLE requests ADD COLUMN resp_ctype TEXT;
    ALTER TABLE people ADD COLUMN allowed_services TEXT NOT NULL DEFAULT '';
    """,
    # v5: the tool catalog, company subscriptions, per-person/team entitlements, the website access
    # gate's usage log, and budgets hidden from staff until an admin accepts them
    """
    CREATE TABLE tools (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'site' CHECK (kind IN ('api', 'dev', 'site')),
        provider TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',
        hosts TEXT NOT NULL DEFAULT '',
        pricing_url TEXT NOT NULL DEFAULT '',
        entry_usd REAL NOT NULL DEFAULT 0,
        plans TEXT NOT NULL DEFAULT '[]',
        builtin INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,
        created REAL NOT NULL
    );
    CREATE TABLE subscriptions (
        tool_id TEXT PRIMARY KEY REFERENCES tools(id) ON DELETE CASCADE,
        state TEXT NOT NULL DEFAULT 'none' CHECK (state IN ('none', 'active', 'past_due', 'cancelled')),
        plan TEXT NOT NULL DEFAULT '',
        seats INTEGER,
        monthly_cost REAL,
        renews_on REAL,
        note TEXT NOT NULL DEFAULT '',
        updated REAL NOT NULL,
        updated_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE entitlements (
        id INTEGER PRIMARY KEY,
        tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
        person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
        department TEXT,
        granted REAL NOT NULL,
        granted_by TEXT NOT NULL DEFAULT ''
    );
    CREATE UNIQUE INDEX entitlements_person ON entitlements(tool_id, person_id) WHERE person_id IS NOT NULL;
    CREATE UNIQUE INDEX entitlements_dept ON entitlements(tool_id, department) WHERE department IS NOT NULL;
    CREATE TABLE access_requests (
        id INTEGER PRIMARY KEY,
        tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
        person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        reason TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'granted', 'declined')),
        created REAL NOT NULL,
        decided REAL,
        decided_by TEXT NOT NULL DEFAULT '',
        decision_note TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX access_requests_state ON access_requests(state, created);
    -- the website access gate records only this: which tool, who, when, how long. No page content.
    CREATE TABLE site_usage (
        id INTEGER PRIMARY KEY,
        tool_id TEXT REFERENCES tools(id) ON DELETE SET NULL,
        person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
        host TEXT NOT NULL DEFAULT '',
        outcome TEXT NOT NULL DEFAULT 'allowed',
        started REAL NOT NULL,
        ended REAL,
        seconds INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX site_usage_person ON site_usage(person_id, started);
    CREATE INDEX site_usage_tool ON site_usage(tool_id, started);
    ALTER TABLE people ADD COLUMN budget_visible INTEGER NOT NULL DEFAULT 0;
    """,
    # v6: launching tools from the portal. How each tool signs people in (company SSO, a company seat
    # under their work email, their own login, or the company API key), the link the portal opens,
    # a one-line description, brand colour and logo, time-limited access, and the launch log.
    """
    ALTER TABLE tools ADD COLUMN signin TEXT NOT NULL DEFAULT 'seat';
    ALTER TABLE tools ADD COLUMN launch_url TEXT NOT NULL DEFAULT '';
    ALTER TABLE tools ADD COLUMN description TEXT NOT NULL DEFAULT '';
    ALTER TABLE tools ADD COLUMN color TEXT NOT NULL DEFAULT '';
    UPDATE tools SET signin = 'api' WHERE kind = 'dev';
    ALTER TABLE entitlements ADD COLUMN expires REAL;
    ALTER TABLE people ADD COLUMN access_until REAL;
    CREATE TABLE tool_icons (
        tool_id TEXT PRIMARY KEY REFERENCES tools(id) ON DELETE CASCADE,
        data BLOB,
        ctype TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        fetched REAL NOT NULL,
        ok INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE launches (
        id INTEGER PRIMARY KEY,
        tool_id TEXT REFERENCES tools(id) ON DELETE SET NULL,
        person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
        ts REAL NOT NULL,
        outcome TEXT NOT NULL DEFAULT 'opened',
        ip TEXT NOT NULL DEFAULT '',
        user_agent TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX launches_tool ON launches(tool_id, ts);
    CREATE INDEX launches_person ON launches(person_id, ts);
    """,
    # v7: tools that are one company account shared by the whole team. Only so many people may hold
    # it at a time, each for a limited turn, so every credit spent on it has a name against it.
    """
    ALTER TABLE tools ADD COLUMN seats_at_once INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE tools ADD COLUMN turn_minutes INTEGER NOT NULL DEFAULT 120;
    CREATE TABLE tool_turns (
        id INTEGER PRIMARY KEY,
        tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
        person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        started REAL NOT NULL,
        expires REAL NOT NULL,
        ended REAL,
        ended_by TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX tool_turns_open ON tool_turns(tool_id, ended, expires);
    CREATE INDEX tool_turns_person ON tool_turns(person_id, started);
    """,
    # v8: a shared account can live in a remote browser workspace on the company's own server, which
    # the admin signs in once. The portal sends the person holding the turn there instead of to the
    # tool's own website, so they arrive already signed in and the password never leaves the server.
    """
    ALTER TABLE tools ADD COLUMN workspace_url TEXT NOT NULL DEFAULT '';
    """,
    # v9: the workspace is a pool of browsers (workspace_url, one address per line), one per person on it
    # at a time. Each turn records the browser it was given, the sign-in the gateway made for it there,
    # and when that sign-in was removed again.
    """
    ALTER TABLE tool_turns ADD COLUMN workspace TEXT NOT NULL DEFAULT '';
    ALTER TABLE tool_turns ADD COLUMN ws_member TEXT NOT NULL DEFAULT '';
    ALTER TABLE tool_turns ADD COLUMN ws_closed REAL;
    CREATE INDEX tool_turns_ws ON tool_turns(ended, ws_closed);
    """,
    # v10: a shared tool can take its browsers from the Swangz Workspace Agent instead of a fixed list
    # ('agent'); '' keeps the fixed list, or the tool's own site when there is none.
    """
    ALTER TABLE tools ADD COLUMN workspace_mode TEXT NOT NULL DEFAULT '';
    """,
    # v11: the control room's device pages read a key's requests on their own
    """
    CREATE INDEX requests_key_ts ON requests(key_id, ts);
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
