"""Taking a single company login from someone asks, on Needs attention, for its password to be changed (D-028)."""

import time
import unittest

from tests.support import Rig
from tests.test_v2 import add_admin

KEY = "login-password-midjourney"


class LoginReminderTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db = self.rig.gw.db
        for role in ("viewer", "billing", "operations"):
            if not self.db.one("SELECT 1 FROM admins WHERE username = ?", (role + "@swangzavenue.com",)):
                add_admin(self.db, role, role)
        self.ok("PATCH", "/tools/midjourney", {"signin": "shared"})
        self.joan = self.person("Akello Joan", "Creative")
        self.brian = self.person("Okello Brian", "Creative")

    def person(self, name, department=""):
        return self.db.x("INSERT INTO people(name, email, department, created) VALUES(?,?,?,?)",
                         (name, name.split()[-1].lower() + "@swangzavenue.com", department, time.time())).lastrowid

    def ok(self, method, path, body=None, who="owner"):
        status, out = self.rig.api(method, path, body, who=who)
        self.assertEqual(status, 200, out)
        return out

    def grant(self, pid, tool="midjourney"):
        self.ok("POST", f"/people/{pid}/tools/{tool}")

    def item(self, key=KEY, who="owner"):
        return next((i for i in self.ok("GET", "/attention", who=who)["items"] if i["key"] == key), None)

    def test_revoking_it_from_a_person_asks_for_a_new_password(self):
        self.grant(self.joan)
        self.assertIsNone(self.item())
        self.ok("DELETE", f"/people/{self.joan}/tools/midjourney")
        item = self.item()
        self.assertEqual((item["severity"], item["area"], item["count"]), ("medium", "Access", 1))
        self.assertEqual(item["title"], "Change the password of Midjourney's company login")
        self.assertTrue(item["text"].startswith("Akello Joan no longer has access"), item["text"])
        self.assertEqual(item["href"], "#/tools?open=midjourney&tab=access")
        self.assertEqual(self.item(who="viewer")["text"], item["text"])

    def test_suspending_a_person_asks_and_giving_access_back_withdraws_it(self):
        self.grant(self.joan)
        self.ok("POST", f"/people/{self.joan}/suspend")
        self.assertIn("Akello Joan", self.item()["text"])
        self.ok("POST", f"/people/{self.joan}/resume")
        self.assertIsNone(self.item())

    def test_every_other_console_way_of_taking_it_away_asks_too(self):
        self.ok("POST", "/teams/Creative/tools/midjourney")
        self.ok("DELETE", "/teams/Creative/tools/midjourney")
        item = self.item()
        self.assertEqual(item["count"], 3)  # the whole team
        self.assertTrue(item["text"].startswith("Akello Joan, Nansubuga Grace and Okello Brian no longer have access"), item["text"])
        self.ok("POST", "/tools/midjourney/login-password-changed")

        self.grant(self.joan)
        self.ok("DELETE", f"/people/{self.joan}/tools")
        self.assertEqual(self.item()["count"], 1)
        self.ok("POST", "/tools/midjourney/login-password-changed")

        self.ok("POST", "/teams/Creative/tools/midjourney")
        self.ok("PATCH", f"/people/{self.brian}", {"department": "Finance"})
        self.assertTrue(self.item()["text"].startswith("Okello Brian no longer has access"))

    def test_nothing_is_asked_when_no_single_login_was_lost(self):
        self.grant(self.joan, "canva")
        self.ok("DELETE", f"/people/{self.joan}/tools/canva")  # not a company login
        self.ok("DELETE", f"/people/{self.joan}/tools/midjourney")  # never had it
        self.ok("POST", f"/people/{self.brian}/suspend")  # holds nothing
        self.grant(self.joan)
        self.ok("POST", "/teams/Creative/tools/midjourney")
        self.ok("DELETE", f"/people/{self.joan}/tools/midjourney")  # still has it through the team
        self.ok("PATCH", f"/people/{self.joan}", {"title": "Designer"})
        self.assertEqual([i for i in self.ok("GET", "/attention")["items"] if i["key"].startswith("login-password-")], [])

    def test_only_a_governing_admin_can_record_the_change_and_it_is_audited(self):
        self.grant(self.joan)
        self.ok("DELETE", f"/people/{self.joan}/tools/midjourney")
        for who in ("viewer", "billing"):
            self.assertEqual(self.rig.api("POST", "/tools/midjourney/login-password-changed", who=who)[0], 403, who)
        self.assertIsNotNone(self.item())
        self.assertEqual(self.rig.api("POST", "/tools/no-such-tool/login-password-changed", who="operations")[0], 404)
        self.assertEqual(self.ok("POST", "/tools/midjourney/login-password-changed", who="operations")["cleared"], 1)
        self.assertIsNone(self.item())
        self.assertEqual(self.ok("POST", "/tools/midjourney/login-password-changed")["cleared"], 0)
        rows = self.db.q("SELECT outcome, correlation, target FROM audit WHERE action = ? ORDER BY id",
                         ("recorded a new password for a company login",))
        self.assertEqual([(r["outcome"], r["correlation"]) for r in rows if r["outcome"] != "refused"],
                         [("ok", "tool:midjourney"), ("no-op", "tool:midjourney")])
        # losing it again later asks again
        self.grant(self.brian)
        self.ok("POST", f"/people/{self.brian}/suspend")
        self.assertTrue(self.item()["text"].startswith("Okello Brian no longer has access"))


if __name__ == "__main__":
    unittest.main()
