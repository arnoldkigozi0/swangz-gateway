"""The shared workspace: a pool of company browsers, one per person on a turn, each signed in to the tool
once by an admin. The gateway makes a sign-in for every turn and removes it when the turn ends."""

import time
import unittest
import urllib.parse

from gateway import security, turns, workspace

from .fake_neko import FakeNeko
from .test_turns import TurnBase
from .test_workspace_agent import TOKEN, AgentRig


def signin_in(location):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(location).query))
    return q.get("usr"), q.get("pwd")


class ThreePeople(TurnBase):
    def go_as_third(self):
        db = self.rig.gw.db
        if not hasattr(self, "third"):
            self.third = db.x("INSERT INTO people(name, email, department, status, created, pw_hash) VALUES(?,?,?,?,?,?)",
                              ("Akello Joy", "joy@swangzavenue.com", "Creative", "active", time.time(),
                               security.hash_password("third-long-pw", 1000))).lastrowid
            self.rig.api("POST", f"/people/{self.third}/tools/midjourney")
        _, h, _ = self.rig.request("POST", "/api/login", {"email": "joy@swangzavenue.com", "password": "third-long-pw"},
                                   {"x-swangz-app": "1"})
        status, h2, payload = self.rig.request("GET", "/go/midjourney", None, {"cookie": h["set-cookie"].split(";")[0]})
        return status, h2, payload.decode()

    def turn_of(self, person_id):
        return self.rig.gw.db.one("SELECT * FROM tool_turns WHERE person_id = ? ORDER BY id DESC LIMIT 1", (person_id,))


class PoolBase(ThreePeople):
    """Midjourney as a shared account in two fixed company browsers, with the gateway managing sign-ins."""

    def setUp(self):
        super().setUp()
        self.a, self.b = FakeNeko(), FakeNeko()
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)
        self.rig.gw.settings.workspace_token = "neko-api-token"
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {
            "workspace_url": f"{self.a.url}/\n{self.b.url}/", "seats_at_once": 3})[0], 200)
        self.grace = workspace.username(self.rig.person_id)


class OpeningTests(PoolBase):
    def test_open_signs_you_into_a_browser_of_your_own(self):
        status, h, _ = self.go("midjourney")
        self.assertEqual(status, 302)
        self.assertTrue(h["location"].startswith(self.a.url + "/?"))
        self.assertEqual(h["referrer-policy"], "no-referrer")
        usr, pwd = signin_in(h["location"])
        self.assertEqual(usr, self.grace)
        self.assertGreaterEqual(len(pwd), 20)
        member = self.a.members[usr]
        self.assertEqual((member["profile"]["name"], member["profile"]["is_admin"]), ("Nansubuga Grace", False))
        self.assertTrue(self.a.sign_in(usr, pwd))
        self.assertEqual(self.b.members, {})  # the other browser knows nothing about her
        turn = self.turn_of(self.rig.person_id)
        self.assertEqual((turn["workspace"], turn["ws_member"], turn["ws_closed"]), (self.a.url + "/", usr, None))
        # the gateway never stores the password it made
        self.assertNotIn(pwd, str(self.rig.gw.db.q("SELECT * FROM tool_turns")))

    def test_two_people_get_two_browsers_and_a_third_waits(self):
        self.assertTrue(self.go("midjourney")[1]["location"].startswith(self.a.url))
        status, h, _ = self.go_as_other("midjourney")
        self.assertEqual(status, 302)
        self.assertTrue(h["location"].startswith(self.b.url))
        # three people may share it, but there are only two browsers
        status, _, body = self.go_as_third()
        self.assertEqual(status, 403)
        self.assertIn("Nansubuga Grace, Okello Brian is using the shared Midjourney account", body)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 2)
        me = self.staff("GET", "/me")[1]
        self.assertEqual(next(t for t in me["catalog"] if t["id"] == "midjourney")["turn"]["seats"], 2)

    def test_a_freed_browser_goes_to_the_next_person(self):
        self.go("midjourney")
        self.go_as_other("midjourney")
        self.staff("POST", "/tools/midjourney/turn/end")
        status, h, _ = self.go_as_third()
        self.assertEqual(status, 302)
        self.assertTrue(h["location"].startswith(self.a.url))

    def test_opening_again_gives_a_new_password_and_drops_the_old_tab(self):
        usr, first = signin_in(self.go("midjourney")[1]["location"])
        self.assertTrue(self.a.sign_in(usr, first))
        usr2, second = signin_in(self.go("midjourney")[1]["location"])
        self.assertEqual(usr2, usr)
        self.assertNotEqual(second, first)
        self.assertNotIn(usr, self.a.sessions)  # the first tab was let go
        self.assertFalse(self.a.sign_in(usr, first))
        self.assertTrue(self.a.sign_in(usr, second))
        self.assertEqual(list(self.a.members), [usr])
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns"), 1)

    def test_a_leftover_sign_in_is_replaced_not_trusted(self):
        self.a.members[self.grace] = {"password": "left-behind", "profile": {"name": "?", "is_admin": True}}
        status, h, _ = self.go("midjourney")
        self.assertEqual(status, 302)
        self.assertFalse(self.a.sign_in(self.grace, "left-behind"))
        self.assertTrue(self.a.sign_in(*signin_in(h["location"])))
        self.assertFalse(self.a.members[self.grace]["profile"]["is_admin"])

    def test_admins_see_which_browser_each_person_is_in(self):
        self.go("midjourney")
        self.go_as_other("midjourney")
        now = {t["person"]: t["workspace"] for t in self.rig.api("GET", "/turns")[1]["now"]}
        self.assertEqual(now, {"Nansubuga Grace": self.a.url + "/", "Okello Brian": self.b.url + "/"})


class EndingTests(PoolBase):
    def test_handing_back_removes_the_sign_in_at_once(self):
        usr, pwd = signin_in(self.go("midjourney")[1]["location"])
        self.assertTrue(self.a.sign_in(usr, pwd))
        self.assertEqual(self.staff("POST", "/tools/midjourney/turn/end")[0], 200)
        self.rig.wait_for(lambda: usr not in self.a.members)
        self.assertNotIn(usr, self.a.sessions)
        self.rig.wait_for(lambda: self.turn_of(self.rig.person_id)["ws_closed"])
        self.assertFalse(self.a.sign_in(usr, pwd))

    def test_a_turn_that_runs_out_is_closed_by_the_sweep(self):
        self.go("midjourney")
        self.rig.gw.db.x("UPDATE tool_turns SET expires = ? WHERE ended IS NULL", (time.time() - 1,))
        self.rig.gw.workspaces.sweep()
        self.assertNotIn(self.grace, self.a.members)
        turn = self.turn_of(self.rig.person_id)
        self.assertEqual(turn["ended_by"], "system")
        self.assertTrue(turn["ws_closed"])

    def test_an_admin_taking_it_back_removes_the_sign_in(self):
        self.go("midjourney")
        self.assertEqual(self.rig.api("POST", "/tools/midjourney/turn/end", {"person_id": self.rig.person_id})[0], 200)
        self.rig.wait_for(lambda: self.grace not in self.a.members)

    def test_suspending_someone_removes_their_sign_in(self):
        self.go("midjourney")
        self.rig.api("POST", f"/people/{self.rig.person_id}/suspend")
        self.rig.wait_for(lambda: self.grace not in self.a.members)

    def test_clean_up_waits_for_a_browser_that_is_down(self):
        self.go("midjourney")
        self.a.broken = True
        self.staff("POST", "/tools/midjourney/turn/end")
        self.rig.gw.workspaces.sweep()
        self.assertIn(self.grace, self.a.members)  # still there, and the gateway knows it
        self.assertIsNone(self.turn_of(self.rig.person_id)["ws_closed"])
        self.a.broken = False
        self.rig.gw.workspaces.sweep()
        self.assertNotIn(self.grace, self.a.members)
        self.assertTrue(self.turn_of(self.rig.person_id)["ws_closed"])

    def test_coming_straight_back_is_not_undone_by_the_old_turn(self):
        self.go("midjourney")
        old = self.turn_of(self.rig.person_id)
        turns.end(self.rig.gw.db, "midjourney", self.rig.person_id, "self", "handed back")  # not swept yet
        status, h, _ = self.go("midjourney")
        self.assertEqual(status, 302)
        self.rig.gw.workspaces.sweep()
        self.assertTrue(self.rig.gw.db.scalar("SELECT ws_closed FROM tool_turns WHERE id = ?", (old["id"],)))
        self.assertTrue(self.a.sign_in(*signin_in(h["location"])))  # the new turn's sign-in survived


class TroubleTests(PoolBase):
    def test_a_browser_that_does_not_answer_frees_the_seat(self):
        self.a.broken = True
        status, _, body = self.go("midjourney")
        self.assertEqual(status, 403)
        self.assertIn("isn&#x27;t answering right now", body)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 0)
        self.assertEqual(self.rig.gw.db.scalar("SELECT outcome FROM launches ORDER BY id DESC LIMIT 1"), "refused")
        self.a.broken = False
        self.assertEqual(self.go("midjourney")[0], 302)

    def test_a_wrong_token_is_treated_as_not_answering(self):
        self.rig.gw.settings.workspace_token = "not-the-token"
        self.assertEqual(self.go("midjourney")[0], 403)
        self.assertEqual(self.a.members, {})

    def test_without_the_token_browsers_are_still_handed_out_one_each(self):
        self.rig.gw.settings.workspace_token = ""
        self.assertEqual(self.go("midjourney")[1]["location"], self.a.url + "/")
        self.assertEqual(self.go_as_other("midjourney")[1]["location"], self.b.url + "/")
        self.assertEqual((self.a.calls, self.b.calls), ([], []))

    def test_deleting_a_tool_takes_back_its_sign_ins_first(self):
        rig = self.rig
        tid = rig.api("POST", "/tools", {"name": "Suno Team", "url": "https://suno.com", "signin": "shared",
                                          "workspace_url": self.b.url + "/"})[1]["id"]
        rig.api("PUT", f"/subscriptions/{tid}", {"state": "active", "monthly_cost": 30})
        rig.api("POST", f"/people/{rig.person_id}/tools/{tid}")
        self.assertEqual(self.go(tid)[0], 302)
        self.b.broken = True
        self.assertEqual(rig.api("DELETE", f"/tools/{tid}")[0], 502)  # would leave someone signed in
        self.assertTrue(rig.gw.db.one("SELECT 1 FROM tools WHERE id = ?", (tid,)))
        self.b.broken = False
        self.assertEqual(rig.api("DELETE", f"/tools/{tid}")[0], 200)
        self.assertEqual(self.b.members, {})


class SettingsTests(PoolBase):
    def test_the_browser_list_is_checked_and_tidied(self):
        rig = self.rig
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"workspace_url": "https://ok.example/\njavascript:alert(1)"})[0], 400)
        many = "\n".join(f"https://ws.example/b{i}/" for i in range(workspace.MAX_BROWSERS + 1))
        self.assertEqual(rig.api("PATCH", "/tools/midjourney", {"workspace_url": many})[0], 400)
        rig.api("PATCH", "/tools/midjourney", {"workspace_url": " https://a.example/ \n\nhttps://b.example/"})
        self.assertEqual(rig.gw.db.scalar("SELECT workspace_url FROM tools WHERE id = 'midjourney'"),
                         "https://a.example/\nhttps://b.example/")
        self.assertTrue(rig.api("GET", "/catalog")[1]["workspace_managed"])


class AgentModeTests(ThreePeople):
    """Midjourney taking its browsers from the Workspace Agent: two browsers, started when needed."""

    def setUp(self):
        super().setUp()
        self.ws = AgentRig()
        self.addCleanup(self.ws.close)
        settings = self.rig.gw.settings
        settings.workspace_agent_url, settings.workspace_agent_token = self.ws.url, TOKEN
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_mode": "agent", "seats_at_once": 3})[0], 200)
        self.n1 = self.ws.nekos["midjourney-1"]

    def open_until_in(self, go):
        for _ in range(5):
            status, h, body = go("midjourney")
            if status != 200:
                return status, h, body
            self.assertIn("Starting your Midjourney browser", body)
            self.assertIn('http-equiv=refresh content=3', body)
        raise AssertionError("the browser never became ready")

    def test_open_waits_for_the_browser_then_signs_you_in(self):
        status, _, body = self.go("midjourney")
        self.assertEqual(status, 200)  # the starting page, which asks again by itself
        self.assertIn("Starting your Midjourney browser", body)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM launches"), 0)  # not opened yet
        status, h, _ = self.open_until_in(self.go)
        self.assertEqual(status, 302)
        self.assertTrue(h["location"].startswith("https://ws.example.test/midjourney-1/?usr="))
        usr, pwd = signin_in(h["location"])
        self.assertEqual(usr, workspace.username(self.rig.person_id))
        self.assertTrue(self.n1.sign_in(usr, pwd))
        turn = self.turn_of(self.rig.person_id)
        self.assertEqual((turn["workspace"], turn["ws_member"]), ("agent:midjourney-1", usr))
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM launches WHERE outcome = 'opened'"), 1)
        me = self.staff("GET", "/me")[1]
        self.assertTrue(next(t for t in me["catalog"] if t["id"] == "midjourney")["workspace"])

    def test_handing_back_releases_and_recycles_the_browser(self):
        self.open_until_in(self.go)
        self.staff("POST", "/tools/midjourney/turn/end")
        self.rig.wait_for(lambda: ("DELETE", "/midjourney-1/api/members/" + workspace.username(self.rig.person_id), None)
                          in self.n1.calls)
        self.rig.wait_for(lambda: self.turn_of(self.rig.person_id)["ws_closed"])
        self.assertIsNone(next(b for b in self.ws.call("GET", "/status")[1]["browsers"] if b["slot"] == "midjourney-1")["holder"])

    def test_a_turn_that_runs_out_releases_its_browser(self):
        self.open_until_in(self.go)
        self.rig.gw.db.x("UPDATE tool_turns SET expires = ? WHERE ended IS NULL", (time.time() - 1,))
        self.rig.gw.workspaces.sweep()
        self.assertTrue(self.turn_of(self.rig.person_id)["ws_closed"])
        self.assertTrue(all(b["holder"] is None for b in self.ws.call("GET", "/status")[1]["browsers"]))

    def test_when_every_browser_is_busy_the_next_person_is_told_and_keeps_no_seat(self):
        self.open_until_in(self.go)
        self.assertEqual(self.open_until_in(lambda tool: self.go_as_other(tool))[0], 302)
        status, _, body = self.go_as_third()
        self.assertEqual(status, 403)
        self.assertIn("All of Swangz&#x27;s browsers for Midjourney are in use", body)
        self.assertEqual(self.turn_of(self.third)["ended_by"], "system")

    def test_when_the_whole_workspace_server_is_full_people_are_told_so(self):
        self.ws.agent.cfg["max_running"] = 1
        self.open_until_in(self.go)
        status, _, body = self.go_as_other("midjourney")
        self.assertEqual(status, 403)
        self.assertIn("Every one of Swangz&#x27;s company browsers is in use right now", body)

    def test_a_workspace_server_that_does_not_answer_frees_the_seat(self):
        self.rig.gw.settings.workspace_agent_url = "http://127.0.0.1:9"
        status, _, body = self.go("midjourney")
        self.assertEqual(status, 403)
        self.assertIn("isn&#x27;t answering right now", body)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 0)

    def test_without_a_workspace_server_nobody_is_sent_anywhere(self):
        self.rig.gw.settings.workspace_agent_url = ""
        self.assertEqual(self.go("midjourney")[0], 403)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM tool_turns WHERE ended IS NULL"), 0)

    def test_the_console_lists_the_browsers_and_an_admin_signs_one_in(self):
        rig = self.rig
        status, out = rig.api("GET", "/workspace")
        self.assertEqual((status, out["configured"], out["health"]["ok"]), (200, True, True))
        self.assertEqual([b["slot"] for b in out["browsers"]], ["midjourney-1", "midjourney-2"])
        self.assertEqual(rig.api("POST", "/workspace/browsers/midjourney-2/open", who="viewer")[0], 403)
        self.assertEqual(rig.api("POST", "/workspace/browsers/midjourney-2/open"), (200, {"state": "starting", "url": None}))
        status, out = rig.api("POST", "/workspace/browsers/midjourney-2/open")
        self.assertEqual((status, out["state"]), (200, "ready"))
        usr, _ = signin_in(out["url"])
        self.assertTrue(self.ws.nekos["midjourney-2"].members[usr]["profile"]["is_admin"])
        self.assertTrue(rig.gw.db.one("SELECT 1 FROM audit WHERE action = 'opened a workspace browser to sign it in'"))
        self.assertEqual(rig.api("POST", "/workspace/browsers/midjourney-2/close")[0], 200)
        self.assertIsNone(rig.api("GET", "/workspace")[1]["browsers"][1]["holder"])

    def test_the_console_says_when_there_is_no_workspace_server(self):
        self.rig.gw.settings.workspace_agent_url = ""
        self.assertEqual(self.rig.api("GET", "/workspace"), (200, {"configured": False}))
        self.rig.gw.settings.workspace_agent_url = "http://127.0.0.1:9"
        self.assertIn("did not answer", self.rig.api("GET", "/workspace")[1]["error"])

    def test_the_mode_is_checked(self):
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_mode": "kasm"})[0], 400)
        self.assertEqual(self.rig.api("GET", "/catalog")[1]["workspace_agent"], True)


class HelperTests(unittest.TestCase):
    def test_the_link_keeps_the_browser_address(self):
        self.assertEqual(workspace.link("https://ws.example/chatgpt-1/?room=x", "swangz-4", "p w"),
                         "https://ws.example/chatgpt-1/?room=x&usr=swangz-4&pwd=p+w")
        self.assertEqual(workspace.link("https://ws.example", "swangz-4", "pw"), "https://ws.example/?usr=swangz-4&pwd=pw")
        self.assertEqual(workspace.api_root("https://ws.example/chatgpt-1/?room=x#y"), "https://ws.example/chatgpt-1")

    def test_only_a_shared_tool_has_browsers(self):
        tool = {"signin": "shared", "workspace_url": "https://a.example/\nhttps://a.example/\nvnc://x\n"}
        self.assertEqual(workspace.browsers(tool), ["https://a.example/"])
        self.assertEqual(workspace.browsers({**tool, "signin": "seat"}), [])
        self.assertEqual(turns.seats({**tool, "seats_at_once": 4}), 1)
        self.assertEqual(turns.seats({"signin": "shared", "seats_at_once": 4}), 4)


if __name__ == "__main__":
    unittest.main()
