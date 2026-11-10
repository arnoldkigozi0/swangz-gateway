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


MIGRATION_22 = """
ALTER TABLE keys ADD COLUMN device_id TEXT;
ALTER TABLE keys ADD COLUMN retire_at REAL;
ALTER TABLE keys ADD COLUMN rotated_from TEXT;
ALTER TABLE keys ADD COLUMN confirmed REAL;
ALTER TABLE devices ADD COLUMN device_id TEXT;
ALTER TABLE devices ADD COLUMN key_storage TEXT NOT NULL DEFAULT '';
ALTER TABLE devices ADD COLUMN key_backend TEXT NOT NULL DEFAULT '';
ALTER TABLE devices ADD COLUMN key_storage_at REAL;
ALTER TABLE devices ADD COLUMN key_issued REAL;
ALTER TABLE devices ADD COLUMN rotations INTEGER NOT NULL DEFAULT 0;
UPDATE devices SET device_id = key_id, key_issued = enrolled;
UPDATE keys SET device_id = id WHERE id IN (SELECT key_id FROM devices);
CREATE UNIQUE INDEX devices_device_id ON devices(device_id);
CREATE INDEX keys_device ON keys(device_id) WHERE device_id IS NOT NULL;
CREATE INDEX keys_retire ON keys(retire_at) WHERE retire_at IS NOT NULL
"""


MIGRATION_23 = """
ALTER TABLE staff_sessions ADD COLUMN kind TEXT NOT NULL DEFAULT 'extension' CHECK (kind IN ('web','extension'));
ALTER TABLE staff_sessions ADD COLUMN last_seen REAL
"""
