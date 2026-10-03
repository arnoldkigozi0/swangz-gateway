"""Shared company accounts handed out a turn at a time, so spend on them has a name against it."""

import json
import time
import unittest

from gateway import security, turns

from .support import Rig
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


class TakingATurnTests(TurnBase):
    def test_opening_a_shared_tool_takes_the_turn(self):
        status, h, _ = self.go("midjourney")
        self.assertEqual((status, h["location"]), (302, "https://www.midjourney.com/"))
        turn = self.rig.gw.db.one("SELECT * FROM tool_turns WHERE ended IS NULL")
        self.assertEqual((turn["tool_id"], turn["person_id"]), ("midjourney", self.rig.person_id))
        self.assertAlmostEqual(turn["expires"] - turn["started"], 3600, delta=2)
        # the staff app shows she is holding it, and until when
        me = self.staff("GET", "/me")[1]
        mj = next(t for t in me["catalog"] if t["id"] == "midjourney")
        self.assertTrue(mj["turn"]["mine"])
        self.assertEqual(mj["turn"]["seats"], 1)

    def test_a_second_person_is_told_who_has_it(self):
        self.assertEqual(self.go("midjourney")[0], 302)
        status, _, body = self.go_as_other("midjourney")
        self.assertEqual(status, 403)
        self.assertIn("Nansubuga Grace is using the shared Midjourney account until", body)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 1)
        # and the portal tells Brian the same thing on the tile
        me = self.as_other("GET", "/me")[1]
        mj = next(t for t in me["catalog"] if t["id"] == "midjourney")
        self.assertEqual((mj["turn"]["mine"], mj["turn"]["free"]), (None, False))
        self.assertEqual(mj["turn"]["others"][0]["person"], "Nansubuga Grace")

    def test_opening_it_again_keeps_the_same_turn(self):
        self.go("midjourney")
        first = self.rig.gw.db.one("SELECT * FROM tool_turns ORDER BY id DESC LIMIT 1")
        self.go("midjourney")
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns"), 1)
        again = self.rig.gw.db.one("SELECT * FROM tool_turns ORDER BY id DESC LIMIT 1")
        self.assertEqual(first["expires"], again["expires"])  # not quietly extended

    def test_handing_it_back_frees_it(self):
        self.go("midjourney")
        status, out = self.staff("POST", "/tools/midjourney/turn/end")
        self.assertEqual((status, out["ended"]), (200, 1))
        self.assertIn("midjourney.com", out["sign_out_hosts"])
        self.assertEqual(self.go_as_other("midjourney")[0], 302)  # Brian can have it now

    def test_a_turn_runs_out(self):
        self.go("midjourney")
        self.rig.gw.db.x("UPDATE tool_turns SET expires = ? WHERE ended IS NULL", (time.time() - 1,))
        self.assertEqual(self.go_as_other("midjourney")[0], 302)
        done = self.rig.gw.db.one("SELECT * FROM tool_turns WHERE person_id = ?", (self.rig.person_id,))
        self.assertEqual((done["ended_by"], done["reason"]), ("system", "time was up"))

    def test_two_seats_let_two_people_in(self):
        self.rig.api("PATCH", "/tools/midjourney", {"seats_at_once": 2})
        self.assertEqual(self.go("midjourney")[0], 302)
        self.assertEqual(self.go_as_other("midjourney")[0], 302)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 2)

    def test_a_tool_that_is_not_shared_needs_no_turn(self):
        self.enable("canva")
        self.assertEqual(self.go("canva")[0], 302)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns"), 0)


class GateAndSignOutTests(TurnBase):
    def ext_token(self, email="grace@swangzavenue.com", password="a-long-password"):
        s, out = self.staff("POST", "/extension/login", {"email": email, "password": password})
        self.assertEqual(s, 200)
        return out["token"]

    def gate(self, path, body=None, token=None, method="POST"):
        headers = {"x-swangz-app": "1", "authorization": "Bearer " + token}
        s, _, payload = self.rig.request(method, "/api" + path, body, headers)
        return s, json.loads(payload) if payload else None

    def test_the_browser_gate_only_lets_the_holder_in(self):
        token = self.ext_token()
        # no turn yet: the site is blocked and she is pointed back at the portal
        s, out = self.gate("/gate/open", {"host": "midjourney.com"}, token)
        self.assertEqual((s, out["allowed"], out["state"]), (200, False, "no_turn"))
        self.assertIn("take your turn", out["reason"])
        # take the turn from the portal, and the same site opens
        self.go("midjourney")
        s, out = self.gate("/gate/open", {"host": "midjourney.com"}, token)
        self.assertEqual((s, out["allowed"]), (200, True))

    def test_the_extension_is_told_what_to_sign_out_of(self):
        token = self.ext_token()
        s, out = self.gate("/gate/turns", None, token, method="GET")
        self.assertEqual(s, 200)
        self.assertEqual(out["holding"], [])
        self.assertEqual([t["tool_id"] for t in out["sign_out"]], ["midjourney"])
        self.assertIn("midjourney.com", out["sign_out"][0]["hosts"])
        self.go("midjourney")
        s, out = self.gate("/gate/turns", None, token, method="GET")
        self.assertEqual([t["tool_id"] for t in out["holding"]], ["midjourney"])
        self.assertEqual(out["sign_out"], [])

    def test_suspending_someone_takes_their_turn_back(self):
        self.go("midjourney")
        self.rig.api("POST", f"/people/{self.rig.person_id}/suspend")
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 0)
        self.assertEqual(self.go_as_other("midjourney")[0], 302)


class AdminTurnTests(TurnBase):
    def test_admins_see_who_has_what_and_can_take_it_back(self):
        self.go("midjourney")
        status, out = self.rig.api("GET", "/turns")
        self.assertEqual(status, 200)
        self.assertEqual((out["now"][0]["person"], out["now"][0]["tool"]), ("Nansubuga Grace", "Midjourney"))
        self.assertEqual([t["name"] for t in out["tools"]], ["Midjourney"])
        self.assertEqual(self.rig.api("POST", "/tools/midjourney/turn/end", {"person_id": self.rig.person_id}, who="viewer")[0], 403)
        status, out = self.rig.api("POST", "/tools/midjourney/turn/end", {"person_id": self.rig.person_id})
        self.assertEqual((status, out["ended"]), (200, 1))
        self.assertEqual(self.rig.api("GET", "/turns")[1]["now"], [])
        self.assertTrue(self.rig.gw.db.one("SELECT 1 FROM audit WHERE action = 'took back a shared account'"))
        # and the history says who had it
        self.assertEqual(self.rig.api("GET", "/turns")[1]["recent"][0]["person"], "Nansubuga Grace")

    def test_sharing_settings_are_checked(self):
        rig = self.rig
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"seats_at_once": "lots"})[0], 400)
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"turn_minutes": "soon"})[0], 400)
        rig.api("PATCH", "/tools/midjourney", {"seats_at_once": 0, "turn_minutes": 1})
        row = rig.gw.db.one("SELECT * FROM tools WHERE id = 'midjourney'")
        self.assertEqual((row["seats_at_once"], row["turn_minutes"]), (1, 5))  # clamped to something sane
        rig.api("PATCH", "/tools/midjourney", {"turn_minutes": 99999})
        self.assertEqual(rig.gw.db.scalar("SELECT turn_minutes FROM tools WHERE id = 'midjourney'"), turns.MAX_MINUTES)

    def test_a_new_tool_can_be_shared_from_the_start(self):
        status, out = self.rig.api("POST", "/tools", {"name": "Suno Team", "url": "https://suno.com",
                                                      "signin": "shared", "seats_at_once": 3, "turn_minutes": 45})
        self.assertEqual(status, 200)
        row = self.rig.gw.db.one("SELECT * FROM tools WHERE id = ?", (out["id"],))
        self.assertEqual((row["signin"], row["seats_at_once"], row["turn_minutes"]), ("shared", 3, 45))


if __name__ == "__main__":
    unittest.main()


class WorkspaceTests(TurnBase):
    """A shared account can live in a remote browser on the company's own server."""

    WS = "https://workspace.swangzavenue.com/launch/midjourney"

    def test_open_lands_in_the_workspace_not_the_tool_site(self):
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_url": self.WS})[0], 200)
        status, h, _ = self.go("midjourney")
        self.assertEqual((status, h["location"]), (302, self.WS))
        # and the person is told that is where Open goes
        me = self.staff("GET", "/me")[1]
        self.assertTrue(next(t for t in me["catalog"] if t["id"] == "midjourney")["workspace"])

    def test_the_turn_still_decides_who_gets_in(self):
        self.rig.api("PATCH", "/tools/midjourney", {"workspace_url": self.WS})
        self.assertEqual(self.go("midjourney")[0], 302)
        status, _, body = self.go_as_other("midjourney")
        self.assertEqual(status, 403)
        self.assertIn("Nansubuga Grace is using the shared Midjourney account", body)

    def test_a_workspace_is_ignored_unless_the_tool_is_shared(self):
        self.rig.api("PATCH", "/tools/midjourney", {"workspace_url": self.WS, "signin": "seat"})
        self.assertEqual(self.go("midjourney")[1]["location"], "https://www.midjourney.com/")

    def test_the_address_must_be_a_web_address(self):
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_url": "vnc://10.0.0.5"})[0], 400)
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_url": "javascript:alert(1)"})[0], 400)
