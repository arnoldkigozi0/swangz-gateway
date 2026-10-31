"""Forward-only v21: the Swangz app on people's own devices (enrolment, check-ins) and the packages
Swangz publishes to it. Nothing here changes an earlier table: an enrolled device is an ordinary gateway
key (`keys`) with a row of facts beside it, so every request, budget, policy and revocation that already
works for a key works for the app."""

MIGRATION = """
CREATE TABLE device_codes (
 id INTEGER PRIMARY KEY,
 device_hash TEXT NOT NULL UNIQUE,
 user_code TEXT NOT NULL UNIQUE,
 created REAL NOT NULL,
 expires REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','used','denied')),
 person_id INTEGER REFERENCES people(id),
 label TEXT NOT NULL DEFAULT '',
 os TEXT NOT NULL DEFAULT '',
 arch TEXT NOT NULL DEFAULT '',
 app_version TEXT NOT NULL DEFAULT '',
 owner_kind TEXT NOT NULL DEFAULT 'personal' CHECK (owner_kind IN ('personal','company')),
 ip TEXT NOT NULL DEFAULT '',
 polled REAL NOT NULL DEFAULT 0,
 key_id TEXT
);
CREATE INDEX device_codes_created ON device_codes(ip, created);
CREATE TABLE devices (
 key_id TEXT PRIMARY KEY REFERENCES keys(id),
 person_id INTEGER NOT NULL REFERENCES people(id),
 name TEXT NOT NULL,
 os TEXT NOT NULL DEFAULT '',
 arch TEXT NOT NULL DEFAULT '',
 app_version TEXT NOT NULL DEFAULT '',
 owner_kind TEXT NOT NULL DEFAULT 'personal' CHECK (owner_kind IN ('personal','company')),
 enrolled REAL NOT NULL,
 last_seen REAL,
 last_ip TEXT NOT NULL DEFAULT '',
 packages_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX devices_person ON devices(person_id);
CREATE TABLE packages (
 id TEXT NOT NULL,
 version TEXT NOT NULL,
 name TEXT NOT NULL,
 kind TEXT NOT NULL DEFAULT 'tool',
 description TEXT NOT NULL DEFAULT '',
 platforms TEXT NOT NULL DEFAULT '',
 sha256 TEXT NOT NULL,
 size INTEGER NOT NULL,
 published REAL NOT NULL,
 published_by TEXT NOT NULL DEFAULT '',
 withdrawn REAL,
 PRIMARY KEY (id, version)
);
CREATE TABLE package_grants (
 package_id TEXT NOT NULL,
 person_id INTEGER REFERENCES people(id),
 department TEXT,
 granted REAL NOT NULL
);
CREATE UNIQUE INDEX package_grants_person ON package_grants(package_id, person_id) WHERE person_id IS NOT NULL;
CREATE UNIQUE INDEX package_grants_dept ON package_grants(package_id, department) WHERE department IS NOT NULL
"""
