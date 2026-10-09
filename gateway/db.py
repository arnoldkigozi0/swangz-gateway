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
    # v11: the company browsers can run on one of Swangz's own computers (a Windows PC, a Mac) instead of
    # the rented server — one place at a time, chosen in the console (settings: workspace_host). Each
    # computer has a key, and checks in with the address its tunnel gave it; the gateway has to present
    # that key to the computer, so it is kept as it is. A turn records where its browser is.
    """
    CREATE TABLE workspace_hosts (
        id TEXT PRIMARY KEY CHECK (id IN ('windows', 'mac')),
        token TEXT NOT NULL,
        url TEXT NOT NULL DEFAULT '',
        info TEXT NOT NULL DEFAULT '{}',
        created REAL NOT NULL,
        seen REAL
    );
    ALTER TABLE tool_turns ADD COLUMN ws_host TEXT NOT NULL DEFAULT '';
    """,
    # v12: the control room's device pages read a key's requests on their own
    """
    CREATE INDEX IF NOT EXISTS requests_key_ts ON requests(key_id, ts);
    """,
    # ---- V2 (Oct 2026) ------------------------------------------------------------------------------
    # v13: authority and the audit fabric. A console user's role stays owner or viewer; `areas` grants a
    # viewer write access to whole areas (money, govern, trust, emergency), which is how the billing,
    # security and operations roles are made (gateway/authz.py). Audit entries can now say why, what it
    # was before and after, whether it worked, and what it relates to.
    """
    ALTER TABLE admins ADD COLUMN areas TEXT NOT NULL DEFAULT '';
    ALTER TABLE audit ADD COLUMN reason TEXT NOT NULL DEFAULT '';
    ALTER TABLE audit ADD COLUMN before_json TEXT;
    ALTER TABLE audit ADD COLUMN after_json TEXT;
    ALTER TABLE audit ADD COLUMN outcome TEXT NOT NULL DEFAULT 'ok';
    ALTER TABLE audit ADD COLUMN correlation TEXT;
    ALTER TABLE audit ADD COLUMN area TEXT NOT NULL DEFAULT '';
    CREATE INDEX audit_actor_ts ON audit(actor, ts);
    CREATE INDEX audit_correlation ON audit(correlation);
    """,
    # v14: where. Networks the company knows by name (the office line, a VPN) and an optional offline
    # GeoIP table imported from a CSV, keyed by a sortable address string (gateway/geo.py). Nothing is
    # looked up over the internet.
    """
    CREATE TABLE networks (
        id INTEGER PRIMARY KEY,
        cidr TEXT NOT NULL UNIQUE,
        label TEXT NOT NULL,
        place TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'office' CHECK (kind IN ('office', 'vpn', 'home', 'cloud', 'other')),
        created REAL NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE geoip_ranges (
        start TEXT NOT NULL,
        stop TEXT NOT NULL,
        country TEXT NOT NULL DEFAULT '',
        region TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX geoip_start ON geoip_ranges(start);
    """,
    # v15: for what, and how sure. Each request can carry a purpose — declared by the person or their
    # tool, derived from the tool itself, or inferred by explainable rules — with its confidence and the
    # evidence. A cost now records where it came from (which price row or media rate, effective when).
    # Tools carry a data classification.
    """
    CREATE TABLE purposes (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        keywords TEXT NOT NULL DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,
        builtin INTEGER NOT NULL DEFAULT 0,
        updated REAL NOT NULL
    );
    ALTER TABLE requests ADD COLUMN purpose TEXT;
    ALTER TABLE requests ADD COLUMN purpose_source TEXT;
    ALTER TABLE requests ADD COLUMN purpose_confidence REAL;
    ALTER TABLE requests ADD COLUMN purpose_evidence TEXT;
    ALTER TABLE requests ADD COLUMN project TEXT;
    ALTER TABLE requests ADD COLUMN cost_source TEXT;
    ALTER TABLE requests ADD COLUMN rule TEXT;
    CREATE INDEX requests_purpose_ts ON requests(purpose, ts);
    ALTER TABLE tools ADD COLUMN classification TEXT NOT NULL DEFAULT 'internal';
    ALTER TABLE launches ADD COLUMN reason TEXT NOT NULL DEFAULT '';
    ALTER TABLE site_usage ADD COLUMN reason TEXT NOT NULL DEFAULT '';
    """,
    # v16: governance. A model registry (status, classification, who may use a restricted model),
    # deterministic policies (deny, permitted hours, a department's monthly cap) and media rates with
    # the date they take effect, so old costs are never silently recalculated.
    """
    CREATE TABLE models (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'approved'
            CHECK (status IN ('approved', 'experimental', 'restricted', 'deprecated', 'disabled')),
        classification TEXT NOT NULL DEFAULT 'internal'
            CHECK (classification IN ('public', 'internal', 'confidential', 'restricted')),
        allowed_departments TEXT NOT NULL DEFAULT '',
        modality TEXT NOT NULL DEFAULT '',
        context_window INTEGER,
        note TEXT NOT NULL DEFAULT '',
        updated REAL NOT NULL,
        updated_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE policies (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        effect TEXT NOT NULL CHECK (effect IN ('deny', 'hours', 'cap')),
        enabled INTEGER NOT NULL DEFAULT 1,
        subjects TEXT NOT NULL DEFAULT '{}',
        scope TEXT NOT NULL DEFAULT '{}',
        params TEXT NOT NULL DEFAULT '{}',
        note TEXT NOT NULL DEFAULT '',
        created REAL NOT NULL,
        created_by TEXT NOT NULL DEFAULT '',
        updated REAL NOT NULL,
        updated_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE media_rates (
        id INTEGER PRIMARY KEY,
        provider TEXT NOT NULL,
        service TEXT NOT NULL DEFAULT '*',
        unit TEXT NOT NULL,
        usd_per_unit REAL NOT NULL,
        effective REAL NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        created REAL NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX media_rates_lookup ON media_rates(provider, effective);
    """,
    # v17: trust. Incidents (a security event turned into a tracked case with owner, evidence, notes and
    # a resolution), persisted notifications with per-admin read state, and indexes for the unified
    # timeline (sign-ins, access changes, turns and launches by time).
    """
    CREATE TABLE incidents (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
        status TEXT NOT NULL DEFAULT 'open'
            CHECK (status IN ('open', 'investigating', 'contained', 'resolved', 'dismissed')),
        owner TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        resolution TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        created REAL NOT NULL,
        created_by TEXT NOT NULL,
        updated REAL NOT NULL,
        closed REAL,
        closed_by TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX incidents_status ON incidents(status, updated);
    CREATE TABLE incident_links (
        id INTEGER PRIMARY KEY,
        incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('person', 'device', 'request', 'tool', 'session', 'event')),
        ref TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        added REAL NOT NULL,
        added_by TEXT NOT NULL DEFAULT ''
    );
    CREATE UNIQUE INDEX incident_links_unique ON incident_links(incident_id, kind, ref);
    CREATE TABLE incident_notes (
        id INTEGER PRIMARY KEY,
        incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
        ts REAL NOT NULL,
        author TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'note',
        text TEXT NOT NULL
    );
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY,
        key TEXT NOT NULL UNIQUE,
        severity TEXT NOT NULL CHECK (severity IN ('info', 'notice', 'warning', 'high', 'critical')),
        area TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL,
        text TEXT NOT NULL DEFAULT '',
        href TEXT NOT NULL DEFAULT '',
        first_seen REAL NOT NULL,
        last_seen REAL NOT NULL,
        resolved REAL,
        emailed REAL
    );
    CREATE TABLE notification_reads (
        notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
        admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
        read REAL NOT NULL,
        PRIMARY KEY (notification_id, admin_id)
    );
    CREATE INDEX IF NOT EXISTS launches_ts ON launches(ts);
    CREATE INDEX IF NOT EXISTS site_usage_started ON site_usage(started);
    CREATE INDEX IF NOT EXISTS tool_turns_started ON tool_turns(started);
    """,
    # v18: which company rule refused an Open or a website visit ("policy:<id>"), as requests.rule does
    # for gateway requests — so each policy can say how often it stopped something, on every channel.
    """
    ALTER TABLE launches ADD COLUMN rule TEXT;
    ALTER TABLE site_usage ADD COLUMN rule TEXT;
    CREATE INDEX requests_rule ON requests(rule) WHERE rule IS NOT NULL;
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
