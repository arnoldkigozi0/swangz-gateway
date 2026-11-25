"""D-023 (F-18, R-8): prompt and reply text are not kept by default, and only the trust area may read them.

Storage off writes every content column as NULL. With storage on, a marker is planted in a stored prompt, reply and
actions, and in a request in flight; viewer, billing and operations crawl every GET under /api/admin (the route table,
plus the searches and CSV variants) and never see it. Security and owner do, and the read is audited."""
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from gateway import admin, config
from gateway.db import DB, SCHEMA

from .test_core_proof import CoreBase, concrete
from .test_v2 import add_admin

# D-023 is SCHEMA[D023] (meta 'schema' = D023 means it has not run yet); later migrations are undone by _upgrade.
D023 = next(i for i, s in enumerate(SCHEMA) if isinstance(s, str) and "INSERT OR IGNORE" in s and "store_bodies" in s)
LATER_TOOL_COLUMNS = ("info_url", "modes", "oauth_hosts", "last_verified")  # v29
LATER_DEVICE_COLUMNS = ("owner_confirmed", "owner_confirmed_at", "owner_confirmed_by")  # v30

MARK = "okapi-lantern-content-9353"
CONTENT_COLUMNS = ("prompt", "reply", "actions", "req_head", "req_items", "resp_blob")
WITHHELD_ROLES = ("viewer", "billing", "operations")
TRUSTED_ROLES = ("security", "owner")
SESSION = "sess-okapi-1"


class DefaultTests(unittest.TestCase):
    def test_the_default_lives_in_one_place_and_is_off(self):
        self.assertEqual(config.STORE_BODIES_DEFAULT, "0")

    def test_a_fresh_database_reads_storage_as_off(self):
        db = DB(":memory:")
        self.assertEqual(db.get_setting("store_bodies"), "0")
        self.assertFalse(config.stores_bodies(db))

    def _upgrade(self, saved):
        tmp = tempfile.mkdtemp(prefix="sgw-d023-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "old.db")
        before = DB(path)  # at the newest schema; rewind it to just before the D-023 migration
        self.assertEqual(len(SCHEMA), D023 + 3, "a migration was added after v30: undo it here as well")
        before.x("UPDATE meta SET v = ? WHERE k = 'schema'", (str(D023),))
        for column in LATER_TOOL_COLUMNS:
            before.x(f"ALTER TABLE tools DROP COLUMN {column}")
        for column in LATER_DEVICE_COLUMNS:
            before.x(f"ALTER TABLE devices DROP COLUMN {column}")
        before.x("DELETE FROM settings WHERE k = 'store_bodies'")
        if saved is not None:
            before.set_setting("store_bodies", saved)
        before.close()
        db = DB(path)
        self.addCleanup(db.close)
        return db.get_setting("store_bodies")

    def test_the_migration_turns_an_unset_switch_off(self):
        self.assertEqual(self._upgrade(None), "0")

    def test_an_admins_saved_choice_survives_the_migration(self):
        self.assertEqual(self._upgrade("1"), "1")
        self.assertEqual(self._upgrade("0"), "0")

    def test_the_migration_only_inserts_where_missing(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO settings VALUES ('store_bodies', '1')")
        conn.executescript(SCHEMA[D023])
        self.assertEqual(conn.execute("SELECT v FROM settings WHERE k = 'store_bodies'").fetchone()[0], "1")


class Base(CoreBase):
    def setUp(self):
        super().setUp()
        for role in ("billing", "security", "operations"):
            add_admin(self.db, role, role)

    def plant(self):
        """A request on record whose prompt, reply and actions carry the marker, in a known session."""
        self.db.set_setting("store_bodies", "1")
        self.assertEqual(self.rig.anthropic({"model": "claude-test", "max_tokens": 5,
                                             "messages": [{"role": "user", "content": MARK}]}, key=self.key)[0], 200)
        row = self.rig.last_record()
        self.db.x("UPDATE requests SET session = ?, reply = ?, actions = ? WHERE id = ?",
                  (SESSION, "reply " + MARK, '[{"kind": "bash", "text": "echo ' + MARK + '"}]', row["id"]))
        return self.rig.last_record()

    def get(self, who, path):
        if who not in self.rig.cookies:
            self.rig.login(who)
        status, _, payload = self.rig.request("GET", "/admin/api" + path, None,
                                              {"cookie": self.rig.cookies[who], "x-gateway-admin": "1"})
        return status, payload.decode("utf-8", "replace")

    def paths(self, rid):
        values = {"rid": rid, "pid": self.pid, "tid": "claude-code", "aid": 1, "kid": self.device["key_id"],
                  "sid": SESSION, "nid": 1, "iid": 1, "lid": 1, "mid": 1, "kind": "usage", "dept": "Creative",
                  "model": "claude-test", "host": "chatgpt.com", "action": "x", "slot": "1"}
        out = []
        for method, rx, _fn, role, _area in admin.ROUTES:
            path = concrete(rx, values)
            if method == "GET" and role is not None and path is not None:
                out.append(path)
        out += [f"/requests?q={MARK}", f"/requests?q={MARK[:8]}&all=1", f"/timeline?q={MARK}", f"/timeline?q={MARK}&days=30",
                f"/search?q={MARK}", f"/search?q={MARK[:6]}", f"/requests/{rid}?download=1", f"/export.csv?person={self.pid}",
                "/export.csv?since=0", f"/sessions/{SESSION}", f"/people/{self.pid}", f"/devices/{self.device['key_id']}"]
        out += [f"/reports/{kind}?format=csv" for kind in ("usage", "spend", "departments", "tools", "models",
                                                             "purposes", "licences", "security", "shared")]
        return out


class StorageOffTests(Base):
    def test_with_storage_off_every_content_column_is_null(self):
        self.assertFalse(config.stores_bodies(self.db))  # nobody switched it on: the default
        self.assertEqual(self.rig.anthropic({"model": "claude-test", "max_tokens": 5,
                                             "messages": [{"role": "user", "content": MARK}]}, key=self.key)[0], 200)
        row = self.rig.last_record()
        self.assertEqual((row["person_id"], row["outcome"]), (self.pid, "ok"))  # who, what, when are still recorded
        for col in CONTENT_COLUMNS:
            self.assertIsNone(row[col], col)
        dump = repr([tuple(r.values()) for r in self.db.q("SELECT * FROM requests")])
        self.assertNotIn(MARK, dump)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM blobs"), 0)

    def test_purpose_inference_still_labels_the_request_with_storage_off(self):
        self.assertEqual(self.rig.anthropic({"model": "claude-test", "max_tokens": 5, "messages": [
            {"role": "user", "content": "draft a press release and a social media caption for the launch"}]},
            key=self.key)[0], 200)
        row = self.rig.last_record()
        self.assertIsNone(row["prompt"])
        self.assertEqual(row["purpose_source"], "inferred")
        self.assertTrue(row["purpose"])

    def test_live_shows_no_prompt_even_to_trusted_roles_with_storage_off(self):
        seen = {}
        original = self.rig.gw.live.start

        def start(**info):
            ticket = original(**info)
            for who in TRUSTED_ROLES:
                seen[who] = self.get(who, "/overview")  # the Live list is served here
            return ticket

        self.rig.gw.live.start = start
        self.addCleanup(setattr, self.rig.gw.live, "start", original)
        self.assertEqual(self.rig.anthropic({"model": "claude-test", "max_tokens": 5,
                                             "messages": [{"role": "user", "content": MARK}]}, key=self.key)[0], 200)
        self.assertEqual(set(seen), set(TRUSTED_ROLES))
        for who, (status, body) in seen.items():
            self.assertEqual(status, 200, who)
            self.assertIn("claude-test", body, who)  # the request was in flight and listed
            self.assertNotIn(MARK, body, who)

    def test_the_settings_and_staff_privacy_page_say_it_is_off(self):
        self.assertFalse(self.rig.api("GET", "/settings")[1]["store_bodies"])
        status, out = self.staff("GET", "/me", cookie=self.person_cookie)
        self.assertEqual(status, 200)
        self.assertFalse(out["privacy"]["store_bodies"])


class ReadGateTests(Base):
    def test_roles_without_trust_never_see_content_anywhere(self):
        rid = self.plant()["id"]
        ticket = self.rig.gw.live.start(person_id=self.pid, person="Nansubuga Grace", key_id=self.device["key_id"],
                                        provider="anthropic", model="claude-test", client="claude-code", session=SESSION,
                                        prompt="live " + MARK)
        self.addCleanup(self.rig.gw.live.finish, ticket)
        paths = self.paths(rid)
        self.assertGreaterEqual(len(paths), 60)
        for who in WITHHELD_ROLES:
            seen = {}
            for path in paths:
                status, text = self.get(who, path)
                seen[path] = status
                self.assertNotIn(MARK, text, f"{path} ({status}) returns content to {who}")
            for path in ("/requests", f"/requests/{rid}", f"/sessions/{SESSION}", "/timeline", "/overview", f"/people/{self.pid}"):
                self.assertEqual(seen.get(path), 200, (who, path))
            # the fields are there, blanked, and say why
            _, rec = self.rig.api("GET", f"/requests/{rid}", who=who)
            self.assertEqual(rec["content"], "withheld")
            for k in ("prompt", "reply", "actions", "request", "response"):
                self.assertIsNone(rec[k], (who, k))
            _, listing = self.rig.api("GET", "/requests", who=who)
            self.assertTrue(listing["items"] and all(i["content"] == "withheld" for i in listing["items"]))
            # a search on the marker matches metadata only, so nothing comes back
            self.assertEqual(self.rig.api("GET", f"/requests?q={MARK}", who=who)[1]["items"], [])
            _, tl = self.rig.api("GET", f"/timeline?q={MARK}&type=request", who=who)
            self.assertEqual([e for e in tl.get("items", tl.get("events", [])) if e.get("type") == "request"], [], who)
            # metadata searches still work for them
            self.assertTrue(self.rig.api("GET", "/requests?q=Nansubuga", who=who)[1]["items"])
            # playing back what was generated is content too
            self.assertEqual(self.get(who, f"/requests/{rid}/media")[0], 403)

    def test_security_and_owner_read_content_and_the_read_is_audited(self):
        rid = self.plant()["id"]
        for who in TRUSTED_ROLES:
            username = f"{who}@swangzavenue.com"
            start = self.db.scalar("SELECT COALESCE(MAX(id), 0) FROM audit")
            status, rec = self.rig.api("GET", f"/requests/{rid}", who=who)
            self.assertEqual(status, 200)
            self.assertIn(MARK, rec["prompt"])
            self.assertNotIn("content", rec)
            self.assertIn(MARK, self.get(who, f"/sessions/{SESSION}")[1])
            self.assertIn(MARK, self.get(who, f"/requests?q={MARK}")[1])
            self.assertIn(MARK, self.get(who, f"/search?q={MARK}")[1])
            self.assertIn(MARK, self.get(who, f"/export.csv?person={self.pid}")[1])
            actions = [r["action"] for r in self.db.q("SELECT action FROM audit WHERE id > ? AND actor = ?", (start, username))]
            for expected in ("opened the full record", "viewed a session's content", "searched request content",
                             "exported records"):
                self.assertIn(expected, actions, (who, actions))
            self.assertGreaterEqual(actions.count("searched request content"), 2, (who, actions))

    def test_no_audit_line_carries_the_content_itself(self):
        rid = self.plant()["id"]
        for who in TRUSTED_ROLES + WITHHELD_ROLES:
            self.get(who, f"/requests?q={MARK}")
            self.get(who, f"/search?q={MARK}")
            self.get(who, f"/requests/{rid}")
        dump = repr([tuple(r.values()) for r in self.db.q("SELECT * FROM audit")])
        self.assertNotIn(MARK, dump)


if __name__ == "__main__":
    unittest.main()
