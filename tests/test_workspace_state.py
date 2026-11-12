"""v26: the managed-workspace columns on `devices` (docs/MANAGED-WORKSPACE.md). Migration only; behaviour is in the W2/W4/W5 tests."""
import hashlib
import os
import sqlite3
import tempfile
import time
import unittest

from gateway.db import DB, SCHEMA
from gateway.workspace_schema import MIGRATION
from tests.test_provider_registry import SCHEMA_23_SHA256

COLUMNS = {"workspace_state", "workspace_generation", "workspace_changed", "workspace_changed_by", "policy_ok", "policy_sha", "policy_reported"}


def device(db, did="d1", person=1):
    db.x("INSERT OR IGNORE INTO people(id, name, email, status, created) VALUES(?,?,?,?,?)", (person, "A", f"a{person}@swangzavenue.com", "active", time.time()))
    db.x("INSERT OR IGNORE INTO keys(id, person_id, secret_hash, hint, created) VALUES(?,?,?,?,?)", (did, person, "h" * 64, "swg-...", time.time()))
    db.x("INSERT INTO devices(key_id, person_id, name, enrolled, device_id) VALUES(?,?,?,?,?)", (did, person, "laptop", time.time(), did))


class MigrationTests(unittest.TestCase):
    def test_v26_adds_exactly_seven_columns_to_devices_and_nothing_else(self):
        self.assertEqual(len(SCHEMA), 26)
        self.assertIs(SCHEMA[25], MIGRATION)
        self.assertIsInstance(MIGRATION, tuple)
        self.assertEqual(len(MIGRATION), 7)
        for stmt in MIGRATION:
            self.assertTrue(stmt.startswith("ALTER TABLE devices ADD COLUMN "), stmt)
            self.assertTrue(sqlite3.complete_statement(stmt + ";"))
        cols = {r["name"] for r in DB(":memory:").q("PRAGMA table_info(devices)")}
        self.assertTrue(COLUMNS <= cols)

    def test_earlier_migrations_are_byte_for_byte_unchanged(self):
        self.assertTrue(all(SCHEMA[i] is not MIGRATION for i in range(25)))
        self.assertEqual(hashlib.sha256("\x00".join(SCHEMA[:23]).encode()).hexdigest(), SCHEMA_23_SHA256)

    def test_defaults_an_existing_device_is_active_generation_1_and_has_no_policy_report(self):
        db = DB(":memory:")
        device(db)
        row = db.one("SELECT * FROM devices WHERE device_id = 'd1'")
        self.assertEqual((row["workspace_state"], row["workspace_generation"], row["workspace_changed"], row["workspace_changed_by"]),
                         ("active", 1, None, ""))
        self.assertEqual((row["policy_ok"], row["policy_sha"], row["policy_reported"]), (None, "", None))

    def test_the_database_itself_refuses_nonsense(self):
        db = DB(":memory:")
        device(db)
        for sql in ("UPDATE devices SET workspace_state = 'paused'", "UPDATE devices SET workspace_state = NULL",
                    "UPDATE devices SET workspace_generation = 0", "UPDATE devices SET workspace_generation = NULL",
                    "UPDATE devices SET policy_ok = 2"):
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                db.x(sql)
        for state in ("active", "suspended", "retired"):
            db.x("UPDATE devices SET workspace_state = ?", (state,))

    def test_a_v25_database_upgrades_in_place_keeping_every_row(self):
        path = os.path.join(tempfile.mkdtemp(prefix="sgw-v26-"), "g.db")
        old = DB(path)
        device(old)
        # put it back at v25 as an older server would have left it: drop the seven columns, set the version
        for col in sorted(COLUMNS):
            old.x(f"ALTER TABLE devices DROP COLUMN {col}")
        old.x("UPDATE meta SET v = '25' WHERE k = 'schema'")
        before = old.q("SELECT * FROM devices")
        old.close()
        new = DB(path)
        self.assertEqual(new.scalar("SELECT v FROM meta WHERE k = 'schema'"), "26")
        row = new.one("SELECT * FROM devices")
        for k, v in before[0].items():
            self.assertEqual(row[k], v, k)
        self.assertEqual((row["workspace_state"], row["workspace_generation"]), ("active", 1))
        new.close()
        again = DB(path)  # opening again is a no-op
        self.assertEqual(again.scalar("SELECT v FROM meta WHERE k = 'schema'"), "26")
        again.close()


if __name__ == "__main__":
    unittest.main()
