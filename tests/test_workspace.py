"""The shared workspace: a pool of company browsers, one per person on a turn, each signed in to the tool
once by an admin. The gateway makes a sign-in for every turn and removes it when the turn ends."""

import base64
import hashlib
import hmac
import json
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        status, out = self.rig.api("GET", "/workspace")
        self.assertEqual((status, out["configured"], out["active"], out["relay"]), (200, False, "server", ""))
        self.assertNotIn("browsers", out)
        self.rig.gw.settings.workspace_agent_url = "http://127.0.0.1:9"
        self.assertIn("did not answer", self.rig.api("GET", "/workspace")[1]["error"])

    def test_the_mode_is_checked(self):
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_mode": "kasm"})[0], 400)
        self.assertEqual(self.rig.api("GET", "/catalog")[1]["workspace_agent"], True)


class PlacesTests(ThreePeople):
    """The company browsers on the rented server or on one of Swangz's computers — one place at a time."""

    def setUp(self):
        super().setUp()
        self.server_ws = AgentRig()
        self.addCleanup(self.server_ws.close)
        settings = self.rig.gw.settings
        settings.workspace_agent_url, settings.workspace_agent_token = self.server_ws.url, TOKEN
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"workspace_mode": "agent", "seats_at_once": 3})[0], 200)
        status, out = self.rig.api("POST", "/workspace/hosts/windows/key")
        self.assertEqual(status, 200)
        self.key = out["key"]
        self.pc = AgentRig(token=self.key)  # the Windows PC's agent, which shares the key
        self.addCleanup(self.pc.close)

    def hello(self, key=None, host="windows", url="https://quiet-river.trycloudflare.com/agent", headers=None):
        h = {"x-swangz-app": "1", "authorization": "Bearer " + (key or self.key), **(headers or {})}
        status, _, payload = self.rig.request("POST", "/api/workspace/hello",
                                              {"host": host, "url": url, "info": {"system": "Windows", "memory_gb": 31.2}}, h)
        return status, json.loads(payload)

    def connect_pc(self):
        self.assertEqual(self.hello()[0], 200)
        # the tunnel's address stands in for the agent here; in the tests it answers on plain http
        self.rig.gw.db.x("UPDATE workspace_hosts SET url = ? WHERE id = 'windows'", (self.pc.url,))

    def open_until_in(self):
        for _ in range(5):
            status, h, body = self.go("midjourney")
            if status != 200:
                return status, h, body
        raise AssertionError("the browser never became ready")

    def holder(self, ws):
        browsers = ws.call("GET", "/status", token=ws.cfg["token"])[1]["browsers"]
        return next(b for b in browsers if b["slot"] == "midjourney-1")["holder"]

    def test_a_computer_gets_a_key_and_checks_in(self):
        rig = self.rig
        self.assertRegex(self.key, r"^[0-9a-f]{64}$")
        command = rig.api("POST", "/workspace/hosts/mac/key")[1]["command"]
        self.assertIn("python3 workspace_agent/computer.py setup --host mac --gateway https://ai.example.test --key ", command)
        self.assertEqual(rig.api("POST", "/workspace/hosts/windows/key", who="viewer")[0], 403)
        self.assertEqual(rig.api("POST", "/workspace/hosts/server/key")[0], 404)
        self.assertEqual(self.hello(key="f" * 64)[0], 401)
        self.assertEqual(self.hello(host="mac")[0], 401)  # the PC's key isn't the Mac's
        self.assertEqual(self.hello(url="http://insecure.example/agent")[0], 400)
        status, _, _ = rig.request("POST", "/api/workspace/hello", {"host": "windows"}, {"authorization": "Bearer " + self.key})
        self.assertEqual(status, 403)  # no app header
        status, out = self.hello()
        self.assertEqual((status, out["active"], out["ice_servers"]), (200, False, []))
        self.assertEqual(out["tools"], {"midjourney": {"start_url": "https://www.midjourney.com/", "browsers": 3}})
        pc = next(h for h in rig.api("GET", "/workspace")[1]["hosts"] if h["id"] == "windows")
        self.assertEqual((pc["set_up"], pc["connected"], pc["online"], pc["active"], pc["info"]["memory_gb"]),
                         (True, True, True, False, 31.2))
        # a new key cuts the old one off
        rig.api("POST", "/workspace/hosts/windows/key")
        self.assertEqual(self.hello()[0], 401)
        self.assertFalse(next(h for h in rig.api("GET", "/workspace")[1]["hosts"] if h["id"] == "windows")["connected"])

    def test_switching_to_the_computer_moves_people_off_the_server(self):
        rig = self.rig
        self.connect_pc()
        self.assertEqual(self.open_until_in()[0], 302)
        self.assertEqual(self.turn_of(rig.person_id)["ws_host"], "server")
        status, out = rig.api("POST", "/workspace/use", {"host": "windows"})
        self.assertEqual((status, out["active"], out["moved"]), (200, "windows", 1))
        turn = self.turn_of(rig.person_id)
        self.assertEqual(turn["reason"], "the company browsers moved to the Windows PC")
        rig.wait_for(lambda: self.turn_of(rig.person_id)["ws_closed"])
        self.assertIsNone(self.holder(self.server_ws))  # her sign-in there is gone
        # Open again: a browser on the PC
        self.assertEqual(self.open_until_in()[0], 302)
        self.assertEqual(self.turn_of(rig.person_id)["ws_host"], "windows")
        self.assertEqual(self.holder(self.pc)["name"], "Nansubuga Grace")
        self.assertIsNone(self.holder(self.server_ws))
        self.assertTrue(self.hello()[1]["active"])  # the PC is told it's the one in use
        self.connect_pc()
        self.assertTrue(rig.gw.db.one("SELECT 1 FROM audit WHERE action = 'switched the company browsers'"))
        # and back
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "server"})[1]["moved"], 1)
        rig.wait_for(lambda: self.holder(self.pc) is None)

    def test_a_browser_is_let_go_where_it_is_even_while_that_place_is_down(self):
        rig = self.rig
        self.connect_pc()
        rig.api("POST", "/workspace/use", {"host": "windows"})
        self.open_until_in()
        self.pc.stop_agent()  # the PC is switched off
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "server"})[1]["moved"], 1)
        rig.gw.workspaces.sweep()
        self.assertIsNone(self.turn_of(rig.person_id)["ws_closed"])  # not yet: the gateway keeps asking
        self.pc.start_agent()
        rig.gw.db.x("UPDATE workspace_hosts SET url = ? WHERE id = 'windows'", (self.pc.url,))
        rig.gw.workspaces.sweep()
        self.assertTrue(self.turn_of(rig.person_id)["ws_closed"])
        self.assertIsNone(self.holder(self.pc))

    def test_switching_needs_a_connected_place_and_an_owner(self):
        rig = self.rig
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "windows"})[0], 409)  # hasn't checked in
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "mac"})[0], 409)
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "nowhere"})[0], 404)
        self.connect_pc()
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "windows"}, who="viewer")[0], 403)
        self.assertEqual(rig.api("POST", "/workspace/use", {"host": "windows"})[0], 200)
        self.assertEqual(rig.api("GET", "/catalog")[1]["workspace_host"], "windows")
        self.assertEqual(rig.api("DELETE", "/workspace/hosts/windows")[0], 409)  # in use
        rig.api("POST", "/workspace/use", {"host": "server"})
        self.assertEqual(rig.api("DELETE", "/workspace/hosts/windows")[0], 200)
        self.assertFalse(next(h for h in rig.api("GET", "/workspace")[1]["hosts"] if h["id"] == "windows")["set_up"])
        self.assertEqual(self.hello()[0], 401)

    def test_each_places_browsers_can_be_signed_in_before_switching(self):
        rig = self.rig
        self.connect_pc()
        status, out = rig.api("GET", "/workspace?host=windows")
        self.assertEqual((status, out["host"], out["active"], out["label"]), (200, "windows", "server", "the Windows PC"))
        self.assertEqual([b["slot"] for b in out["browsers"]], ["midjourney-1", "midjourney-2"])
        self.assertEqual(rig.api("POST", "/workspace/browsers/midjourney-1/open?host=windows")[1]["state"], "starting")
        status, out = rig.api("POST", "/workspace/browsers/midjourney-1/open?host=windows")
        self.assertEqual(out["state"], "ready")
        self.assertEqual(self.holder(self.pc)["kind"], "admin")
        self.assertIsNone(self.holder(self.server_ws))
        self.assertEqual(rig.api("POST", "/workspace/browsers/midjourney-1/close?host=windows")[0], 200)
        self.assertEqual(rig.api("GET", "/workspace?host=mac")[1]["configured"], False)
        self.assertEqual(rig.api("GET", "/workspace?host=elsewhere")[0], 404)


class RelayTests(unittest.TestCase):
    def setUp(self):
        from .support import Rig

        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.relay = self.rig.gw.workspaces.relay

    def test_none_without_settings(self):
        self.assertEqual((self.relay.kind, self.relay.ice_servers()), ("", []))

    def test_your_own_coturn_gets_credentials_that_run_out(self):
        s = self.rig.gw.settings
        s.turn_urls, s.turn_secret = ("turn:turn.swangzavenue.com:3478", "turns:turn.swangzavenue.com:5349"), "coturn-secret"
        [server] = self.relay.ice_servers()
        expires, who = server["username"].split(":")
        self.assertEqual(who, "swangz")
        self.assertAlmostEqual(int(expires), time.time() + workspace.RELAY_TTL, delta=5)
        mac = hmac.new(b"coturn-secret", server["username"].encode(), hashlib.sha1).digest()
        self.assertEqual(server["credential"], base64.b64encode(mac).decode())
        self.assertEqual(server["urls"], ["turn:turn.swangzavenue.com:3478", "turns:turn.swangzavenue.com:5349"])

    def test_cloudflare_is_asked_once_and_port_53_is_left_out(self):
        asked = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                asked.append((self.path, self.headers.get("authorization"),
                              json.loads(self.rfile.read(int(self.headers["content-length"])))))
                data = json.dumps({"iceServers": [
                    {"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.cloudflare.com:53"]},
                    {"urls": ["turn:turn.cloudflare.com:3478?transport=udp", "turn:turn.cloudflare.com:53?transport=udp",
                              "turns:turn.cloudflare.com:443?transport=tcp"], "username": "cf-user", "credential": "cf-pass"}]}).encode()
                self.send_response(201)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        fake = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        s = self.rig.gw.settings
        s.turn_cloudflare_key_id, s.turn_cloudflare_token = "key-id-1", "cf-api-token"
        self.relay.CLOUDFLARE = f"http://127.0.0.1:{fake.server_address[1]}/v1/turn/keys/{{}}/credentials/generate-ice-servers"
        servers = self.relay.ice_servers()
        self.assertEqual(servers, [{"urls": ["stun:stun.cloudflare.com:3478"]},
                                   {"urls": ["turn:turn.cloudflare.com:3478?transport=udp", "turns:turn.cloudflare.com:443?transport=tcp"],
                                    "username": "cf-user", "credential": "cf-pass"}])
        self.assertEqual(asked, [("/v1/turn/keys/key-id-1/credentials/generate-ice-servers", "Bearer cf-api-token",
                                  {"ttl": workspace.RELAY_TTL})])
        self.assertEqual(self.relay.ice_servers(), servers)
        self.assertEqual(len(asked), 1)  # kept until half their life is gone
        self.assertEqual(self.rig.api("GET", "/workspace")[1]["relay"], "cloudflare")


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
