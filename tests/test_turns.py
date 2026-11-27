"""Shared company accounts after turns were retired (owner directive, 27 Nov 2026).

A tool set up as one company login (`signin = 'shared'`) opens for every person assigned it, at the same time, with no
turn, wait, countdown or sign-out. The account limitation is stated to the person and the admin instead. Past turns
stay in the history, and migration v31 closed any turn still open."""

import json
import os
import tempfile
import time
import unittest

from gateway import db as gdb, security, turns

from .test_portal import PortalBase


class TurnBase(PortalBase):
    def setUp(self):
        super().setUp()
        rig = self.rig
        rig.api("PUT", "/subscriptions/midjourney", {"state": "active", "monthly_cost": 60})
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"signin": "shared", "turn_minutes": 60})[0], 200)
        self.assertEqual(rig.api("POST", f"/people/{rig.person_id}/tools/midjourney")[0], 200)
        # a second person on the same shared tool
        self.other = rig.gw.db.x("INSERT INTO people(name, email, department, status, created) VALUES(?,?,?,?,?)",
                                 ("Okello Brian", "brian@swangzavenue.com", "Creative", "active", time.time())).lastrowid
        rig.gw.db.x("UPDATE people SET pw_hash = ? WHERE id = ?", (security.hash_password("another-long-pw", 1000), self.other))
        rig.api("POST", f"/people/{self.other}/tools/midjourney")

    def as_other(self, method, path, body=None):
        """Call the staff API as Brian, on his own session."""
        s, h, _ = self.rig.request("POST", "/api/login", {"email": "brian@swangzavenue.com", "password": "another-long-pw"},
                                   {"x-swangz-app": "1"})
        self.assertEqual(s, 200)
        cookie = h["set-cookie"].split(";")[0]
        status, _, payload = self.rig.request(method, "/api" + path, body, {"x-swangz-app": "1", "cookie": cookie})
        return status, json.loads(payload) if payload else None

    def go_as_other(self, tool_id):
        s, h, _ = self.rig.request("POST", "/api/login", {"email": "brian@swangzavenue.com", "password": "another-long-pw"},
                                   {"x-swangz-app": "1"})
        cookie = h["set-cookie"].split(";")[0]
        status, h2, payload = self.rig.request("GET", "/go/" + tool_id, None, {"cookie": cookie})
        return status, h2, payload.decode()


class EveryoneAtOnceTests(TurnBase):
    def test_two_people_open_the_same_shared_tool_at_the_same_time(self):
        status, h, _ = self.go("midjourney")
        self.assertEqual((status, h["location"]), (302, "https://www.midjourney.com/"))
        status, h, _ = self.go_as_other("midjourney")
        self.assertEqual((status, h["location"]), (302, "https://www.midjourney.com/"))
        # and again, and again: nobody is ever told to wait
        for _ in range(3):
            self.assertEqual(self.go("midjourney")[0], 302)
            self.assertEqual(self.go_as_other("midjourney")[0], 302)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns"), 0)  # no turn is ever taken
        opened = self.rig.gw.db.q("SELECT person_id, outcome FROM launches WHERE tool_id = 'midjourney'")
        self.assertEqual({r["outcome"] for r in opened}, {"opened"})
        self.assertEqual({r["person_id"] for r in opened}, {self.rig.person_id, self.other})  # each open is attributed

    def test_one_person_opens_several_tools_at_once(self):
        self.rig.api("PUT", "/subscriptions/canva", {"state": "active"})
        self.rig.api("POST", f"/people/{self.rig.person_id}/tools/canva")
        self.assertEqual(self.go("midjourney")[0], 302)
        self.assertEqual(self.go("canva")[0], 302)
        self.assertEqual(self.go("midjourney")[0], 302)

    def test_the_staff_app_states_the_limitation_and_has_no_turn(self):
        me = self.staff("GET", "/me")[1]
        mj = next(t for t in me["catalog"] if t["id"] == "midjourney")
        self.assertNotIn("turn", mj)
        self.assertIn("one company login", mj["account_note"])
        self.assertIn("seat of your own", mj["account_note"])
        other = next(t for t in me["catalog"] if t["id"] == "canva")
        self.assertIsNone(other["account_note"])  # a seat tool carries no note

    def test_the_old_hand_back_call_still_answers_and_signs_nothing_out(self):
        status, out = self.staff("POST", "/tools/midjourney/turn/end")
        self.assertEqual((status, out["ended"], out["sign_out_hosts"]), (200, 0, []))

    def test_a_tool_that_is_not_shared_is_unchanged(self):
        self.rig.api("PATCH", "/tools/midjourney", {"signin": "seat"})
        self.assertEqual(self.go("midjourney")[0], 302)
        self.assertEqual(self.go_as_other("midjourney")[0], 302)


class NothingIsSignedOutTests(TurnBase):
    def ext_token(self, email="grace@swangzavenue.com", password="a-long-password"):
        s, out = self.staff("POST", "/extension/login", {"email": email, "password": password})
        self.assertEqual(s, 200)
        return out["token"]

    def gate(self, path, body=None, token=None, method="POST"):
        headers = {"x-swangz-app": "1", "authorization": "Bearer " + token}
        s, _, payload = self.rig.request(method, "/api" + path, body, headers)
        return s, json.loads(payload) if payload else None

    def test_the_browser_gate_lets_everyone_assigned_in_without_a_turn(self):
        token = self.ext_token()
        s, out = self.gate("/gate/open", {"host": "midjourney.com"}, token)
        self.assertEqual((s, out["allowed"], out["state"]), (200, True, "enabled"))
        brian = self.ext_token("brian@swangzavenue.com", "another-long-pw")
        s, out = self.gate("/gate/open", {"host": "midjourney.com"}, brian)
        self.assertEqual((s, out["allowed"]), (200, True))

    def test_an_older_extension_is_told_to_sign_out_of_nothing(self):
        token = self.ext_token()
        self.go("midjourney")
        s, out = self.gate("/gate/turns", None, token, method="GET")
        self.assertEqual((s, out), (200, {"holding": [], "sign_out": []}))

    def test_a_person_who_is_not_assigned_is_still_refused(self):
        self.rig.api("DELETE", f"/people/{self.other}/tools/midjourney")
        brian = self.ext_token("brian@swangzavenue.com", "another-long-pw")
        s, out = self.gate("/gate/open", {"host": "midjourney.com"}, brian)
        self.assertEqual((s, out["allowed"]), (200, False))
        self.assertEqual(self.go_as_other("midjourney")[0], 403)

    def test_suspension_still_cuts_access(self):
        self.rig.api("POST", f"/people/{self.other}/suspend")
        self.assertNotEqual(self.go_as_other("midjourney")[0], 302)
        self.assertEqual(self.go("midjourney")[0], 302)  # the other person is unaffected


class HistoryTests(TurnBase):
    def test_past_turns_stay_readable_and_a_leftover_one_can_be_closed(self):
        now = time.time()
        db = self.rig.gw.db
        db.x("INSERT INTO tool_turns(tool_id, person_id, started, expires, ended, ended_by, reason) VALUES(?,?,?,?,?,?,?)",
             ("midjourney", self.rig.person_id, now - 7200, now - 3600, now - 3600, "system", "time was up"))
        db.x("INSERT INTO tool_turns(tool_id, person_id, started, expires) VALUES(?,?,?,?)",
             ("midjourney", self.other, now - 60, now + 3600))  # as if left open by an older server
        status, out = self.rig.api("GET", "/turns")
        self.assertEqual(status, 200)
        self.assertEqual([t["person"] for t in out["now"]], ["Okello Brian"])
        self.assertIn("Nansubuga Grace", [t["person"] for t in out["recent"]])
        self.assertEqual(self.rig.api("POST", "/tools/midjourney/turn/end", {"person_id": self.other}, who="viewer")[0], 403)
        status, out = self.rig.api("POST", "/tools/midjourney/turn/end", {"person_id": self.other})
        self.assertEqual((status, out["ended"]), (200, 1))
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM tool_turns"), 2)  # closed, never deleted

    def test_migration_v31_closes_open_turns_and_keeps_every_row(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "gateway.db")
        old = gdb.SCHEMA
        try:
            gdb.SCHEMA = old[:30]
            d = gdb.DB(path)
            pid = d.x("INSERT INTO people(name, email, department, status, created) VALUES('A','a@swangzavenue.com','','active',0)").lastrowid
            d.x("INSERT INTO tools(id, name, category, kind, url, hosts, created) VALUES('t','T','x','site','https://t.example','t.example',0)")
            d.x("INSERT INTO tool_turns(tool_id, person_id, started, expires) VALUES('t', ?, 1, 9999999999)", (pid,))
            d.x("INSERT INTO tool_turns(tool_id, person_id, started, expires, ended, ended_by, reason) VALUES('t', ?, 1, 2, 2, 'self', 'handed back')", (pid,))
            d.conn.close()
        finally:
            gdb.SCHEMA = old
        d = gdb.DB(path)
        self.assertEqual(d.scalar("SELECT v FROM meta WHERE k='schema'"), str(len(gdb.SCHEMA)))
        rows = d.q("SELECT * FROM tool_turns ORDER BY id")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["ended"] for r in rows))
        self.assertEqual(rows[0]["ended_by"], "system")
        self.assertIn("turns retired", rows[0]["reason"])
        self.assertEqual((rows[1]["ended_by"], rows[1]["reason"]), ("self", "handed back"))  # history untouched
        self.assertEqual(d.one("SELECT apps_json, apps_reported FROM devices LIMIT 1"), None)
        self.assertIn("apps_json", [c["name"] for c in d.q("PRAGMA table_info(devices)")])

    def test_sharing_settings_are_still_checked(self):
        rig = self.rig
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"seats_at_once": "lots"})[0], 400)
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"turn_minutes": "soon"})[0], 400)


class LimitationTests(TurnBase):
    def test_admins_are_told_the_limitation_where_they_decide(self):
        status, out = self.rig.api("GET", f"/policies/explain?person={self.rig.person_id}&tool=midjourney")
        self.assertEqual(status, 200)
        step = next(s for s in out["steps"] if s["check"] == "Account limitation")
        self.assertEqual(step["result"], "info")
        self.assertIn("one company login", step["detail"])
        self.assertTrue(out["allowed"])

    def test_the_note_is_none_for_every_other_sign_in(self):
        for signin in ("sso", "seat", "own", "api"):
            self.assertIsNone(turns.account_note({"name": "X", "signin": signin}))
            self.assertIsNone(turns.admin_note({"name": "X", "signin": signin}))
        self.assertIn("2 people are assigned", turns.admin_note({"name": "X", "signin": "shared"}, 2))


class SharedGoogleHostTests(TurnBase):
    """D-027: clearing a shared tool's site clears its whole registrable domain, so google.com is never shared."""

    ext_token, gate = NothingIsSignedOutTests.ext_token, NothingIsSignedOutTests.gate

    def refusals(self):
        return self.rig.gw.db.q("SELECT * FROM audit WHERE detail LIKE 'shared_google_host:%' ORDER BY id")

    def tool(self, tool_id):
        return self.rig.gw.db.one("SELECT * FROM tools WHERE id = ?", (tool_id,))

    def assert_refused(self, answer, hosts):
        status, body = answer
        self.assertEqual((status, body.get("code"), body.get("details")), (400, "shared_google_host", {"hosts": hosts}))

    def test_adding_a_shared_tool_on_google_is_refused_and_recorded(self):
        count = self.rig.gw.db.scalar("SELECT COUNT(*) FROM tools")
        cases = [
            ({"hosts": "gemini.google.com"}, ["gemini.google.com"]),
            ({"hosts": "example.org, google.com"}, ["google.com"]),
            ({"url": "https://www.notebooklm.google.com/x"}, ["notebooklm.google.com", "www.notebooklm.google.com"]),
            ({"hosts": "example.org", "url": "https://AI.Google.com./"}, ["ai.google.com."]),
            ({"hosts": "example.org", "launch_url": "https://someone@accounts.google.com:443/o"}, ["accounts.google.com"]),
            ({"hosts": "example.org", "launch_url": "https://gemini.google\u3002com/"}, ["gemini.google\u3002com"]),
            ({"hosts": "example.org", "launch_url": "https://gemini.google%2Ecom/"}, ["gemini.google%2ecom"]),
            ({"hosts": "example.org", "workspace_url": "https://browser.google.com/"}, ["browser.google.com"]),
        ]
        for body, hosts in cases:
            with self.subTest(body=body):
                self.assert_refused(self.rig.api("POST", "/tools", {"name": "Team G", "signin": "shared", **body}), hosts)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tools"), count)
        rows = self.refusals()
        self.assertEqual(len(rows), len(cases))
        self.assertEqual((rows[0]["action"], rows[0]["target"], rows[0]["outcome"], rows[0]["area"]),
                         ("was refused a change", "Team G", "refused", "govern"))
        self.assertTrue(rows[0]["actor"])

    def test_an_edit_that_would_share_a_google_tool_is_refused_and_changes_nothing(self):
        before = self.tool("gemini")
        self.assert_refused(self.rig.api("PATCH", "/tools/gemini", {"signin": "shared"}), ["gemini.google.com"])
        self.assertEqual(self.tool("gemini"), before)
        # ai.google.com belongs to no other tool, so only this rule refuses it
        for body in ({"hosts": "midjourney.com,ai.google.com"}, {"url": "https://ai.google.com/"},
                     {"launch_url": "https://ai.google.com/app"}):
            with self.subTest(body=body):
                before = self.tool("midjourney")
                self.assert_refused(self.rig.api("PATCH", "/tools/midjourney", body), ["ai.google.com"])
                self.assertEqual(self.tool("midjourney"), before)
        self.assertEqual({r["correlation"] for r in self.refusals()}, {"tool:gemini", "tool:midjourney"})
        self.assertEqual(len(self.refusals()), 4)

    def test_other_sign_in_methods_and_look_alike_names_still_save(self):
        self.assertEqual(self.rig.api("PATCH", "/tools/gemini", {"signin": "seat"})[0], 200)
        status, _ = self.rig.api("POST", "/tools", {"name": "Look Alike", "signin": "shared",
                                                    "hosts": "notgoogle.com, google.com.example.org",
                                                    "url": "https://example.org/?next=https://google.com/"})
        self.assertEqual(status, 200)
        self.assertEqual(self.refusals(), [])

    def test_an_old_shared_google_row_is_never_in_a_sign_out_list(self):
        # saved before the refusal existed: written straight to the database
        self.rig.gw.db.x("UPDATE tools SET signin = 'shared' WHERE id = 'gemini'")
        self.rig.gw.db.x("UPDATE tools SET hosts = 'midjourney.com,gemini.google.com,google.com' WHERE id = 'midjourney'")
        token = self.ext_token()
        s, out = self.gate("/gate/turns", None, token, method="GET")
        self.assertEqual((s, out), (200, {"holding": [], "sign_out": []}))  # turns retired: nothing is ever signed out
        self.go("midjourney")
        status, out = self.staff("POST", "/tools/midjourney/turn/end")
        self.assertEqual((status, out["sign_out_hosts"]), (200, []))
        # such a row stays fixable
        self.assertEqual(self.rig.api("PATCH", "/tools/gemini", {"signin": "own"})[0], 200)


if __name__ == "__main__":
    unittest.main()
