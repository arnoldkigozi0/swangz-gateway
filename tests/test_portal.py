"""Opening tools from the portal, managing the catalog, time-limited access, logos and licences."""

import base64
import json
import time
import unittest

from gateway import icons, security

from .support import Rig
from .test_gateway import StaffBase

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class PortalBase(StaffBase):
    def setUp(self):
        super().setUp()
        rig = self.rig
        rig.api("PATCH", f"/people/{rig.person_id}", {"email": "grace@swangzavenue.com"})
        rig.gw.db.x("UPDATE people SET pw_hash = ? WHERE id = ?", (security.hash_password("a-long-password", 1000), rig.person_id))
        status, _ = self.staff("POST", "/login", {"email": "grace@swangzavenue.com", "password": "a-long-password"})
        self.assertEqual(status, 200)

    def go(self, tool_id, cookie=True):
        headers = {"cookie": self.cookie} if cookie else {}
        status, h, payload = self.rig.request("GET", "/go/" + tool_id, None, headers)
        return status, h, payload.decode()

    def enable(self, tool_id):
        self.rig.api("PUT", f"/subscriptions/{tool_id}", {"state": "active", "monthly_cost": 30, "seats": 5})
        self.assertEqual(self.rig.api("POST", f"/people/{self.rig.person_id}/tools/{tool_id}")[0], 200)


class LaunchTests(PortalBase):
    def test_open_sends_you_to_the_tool_and_logs_it(self):
        self.enable("canva")
        status, h, _ = self.go("canva")
        self.assertEqual((status, h["location"]), (302, "https://www.canva.com/"))
        row = self.rig.gw.db.one("SELECT * FROM launches ORDER BY id DESC LIMIT 1")
        self.assertEqual((row["tool_id"], row["person_id"], row["outcome"]), ("canva", self.rig.person_id, "opened"))
        # the staff app shows when they last opened it
        me = self.staff("GET", "/me")[1]
        self.assertTrue(next(t for t in me["catalog"] if t["id"] == "canva")["last_opened"])

    def test_the_company_sign_in_link_wins_over_the_website(self):
        self.enable("canva")
        sso = "https://www.canva.com/login/sso?domain=swangzavenue.com"
        self.assertEqual(self.rig.api("PATCH", "/tools/canva", {"launch_url": sso, "signin": "sso"})[0], 200)
        self.assertEqual(self.go("canva")[1]["location"], sso)
        me = self.staff("GET", "/me")[1]
        self.assertEqual(next(t for t in me["catalog"] if t["id"] == "canva")["signin"], "sso")

    def test_a_tool_you_dont_hold_is_refused_and_logged(self):
        status, h, body = self.go("midjourney")
        self.assertEqual(status, 403)
        self.assertIn("Midjourney isn", body)
        self.assertIn("Content-Security-Policy".lower(), h)
        self.assertEqual(self.rig.gw.db.scalar("SELECT outcome FROM launches ORDER BY id DESC LIMIT 1"), "refused")

    def test_signed_out_goes_to_the_portal(self):
        self.enable("canva")
        status, h, _ = self.go("canva", cookie=False)
        self.assertEqual((status, h["location"]), (302, "/"))
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM launches"), 0)

    def test_pause_and_suspend_stop_launches(self):
        self.enable("canva")
        self.rig.api("POST", "/pause", {"paused": True})
        self.assertEqual(self.go("canva")[0], 403)
        self.rig.api("POST", "/pause", {"paused": False})
        self.assertEqual(self.go("canva")[0], 302)
        self.rig.api("POST", f"/people/{self.rig.person_id}/suspend")
        self.assertEqual(self.go("canva")[0], 302)  # suspending also signs them out of the portal...
        self.assertEqual(self.go("canva")[1]["location"], "/")  # ...so they land on the sign-in page

    def test_only_web_addresses_are_ever_opened(self):
        self.enable("canva")
        self.assertEqual(self.rig.api("PATCH", "/tools/canva", {"launch_url": "javascript:alert(1)"})[0], 400)
        self.rig.gw.db.x("UPDATE tools SET url = 'javascript:alert(1)', launch_url = '' WHERE id = 'canva'")
        status, _, body = self.go("canva")
        self.assertEqual(status, 403)
        self.assertIn("no web address", body)

    def test_removed_tools_cannot_be_opened(self):
        self.enable("canva")
        self.rig.api("POST", "/tools/canva/archive")
        self.assertEqual(self.go("canva")[0], 404)


class TimeLimitTests(PortalBase):
    def test_a_grant_can_end_on_a_date(self):
        rig = self.rig
        rig.api("PUT", "/subscriptions/canva", {"state": "active"})
        self.assertEqual(rig.api("POST", f"/people/{rig.person_id}/tools/canva", {"until": "2001-01-01"})[0], 400)
        until = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 3 * 86400))
        self.assertEqual(rig.api("POST", f"/people/{rig.person_id}/tools/canva", {"until": until})[0], 200)
        me = self.staff("GET", "/me")[1]
        canva = next(t for t in me["catalog"] if t["id"] == "canva")
        self.assertEqual(canva["state"], "enabled")
        self.assertTrue(canva["ends"])
        # once the end date passes, the tool is no longer theirs
        rig.gw.db.x("UPDATE entitlements SET expires = ? WHERE tool_id = 'canva'", (time.time() - 1,))
        me = self.staff("GET", "/me")[1]
        self.assertEqual(next(t for t in me["catalog"] if t["id"] == "canva")["state"], "not_assigned")
        self.assertEqual(self.go("canva")[0], 403)

    def test_an_account_can_end_on_a_date(self):
        rig = self.rig
        self.assertEqual(rig.api("PATCH", f"/people/{rig.person_id}", {"access_until": "2001-01-01"})[0], 200)
        me = self.staff("GET", "/me")[1]
        self.assertTrue(all(t["state"] == "suspended" for t in me["catalog"]))
        # their API key stops too
        status, _, payload = rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]},
                                           extra={"user-agent": "Anthropic/Python 1.2"})
        self.assertEqual(status, 403)
        self.assertIn("access period has ended", payload.decode())
        # clearing the date restores them
        rig.api("PATCH", f"/people/{rig.person_id}", {"access_until": ""})
        self.assertEqual(rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]},
                                       extra={"user-agent": "Anthropic/Python 1.2"})[0], 200)

    def test_remove_every_tool_at_once(self):
        rig = self.rig
        self.enable("canva")
        status, out = rig.api("DELETE", f"/people/{rig.person_id}/tools")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(out["removed"], 3)  # canva + the rig's claude-code and codex
        self.assertEqual(rig.gw.db.scalar("SELECT COUNT(*) FROM entitlements WHERE person_id = ?", (rig.person_id,)), 0)
        self.assertEqual(rig.api("DELETE", f"/people/{rig.person_id}/tools", who="viewer")[0], 403)


class CatalogAdminTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_add_a_tool_with_everything_the_portal_needs(self):
        rig = self.rig
        status, out = rig.api("POST", "/tools", {"name": "Lovable", "category": "Coding", "url": "https://www.lovable.dev/",
                                                 "signin": "sso", "launch_url": "https://lovable.dev/sso",
                                                 "description": "Build apps by chatting.", "color": "#FF4D8D"})
        self.assertEqual(status, 200)
        row = rig.gw.db.one("SELECT * FROM tools WHERE id = ?", (out["id"],))
        self.assertEqual((row["hosts"], row["signin"], row["color"], row["builtin"]), ("lovable.dev", "sso", "#FF4D8D", 0))

    def test_bad_input_is_refused(self):
        rig = self.rig
        self.assertEqual(rig.api("POST", "/tools", {"name": ""})[0], 400)
        self.assertEqual(rig.api("POST", "/tools", {"name": "X", "url": "ftp://x.com"})[0], 400)
        self.assertEqual(rig.api("POST", "/tools", {"name": "X", "color": "red"})[0], 400)
        self.assertEqual(rig.api("PATCH", "/tools/canva", {"name": ""})[0], 400)

    def test_remove_restore_and_delete(self):
        rig = self.rig
        tid = rig.api("POST", "/tools", {"name": "Gamma", "url": "https://gamma.app"})[1]["id"]
        # built-ins are removed and restored, never deleted
        self.assertEqual(rig.api("POST", "/tools/canva/archive")[0], 200)
        cat = rig.api("GET", "/catalog")[1]
        self.assertIn("canva", {t["id"] for t in cat["removed"]})
        self.assertNotIn("canva", {t["id"] for t in cat["tools"]})
        self.assertEqual(rig.api("DELETE", "/tools/canva")[0], 400)
        self.assertEqual(rig.api("POST", "/tools/canva/restore")[0], 200)
        # a tool an admin added can be deleted outright
        self.assertEqual(rig.api("DELETE", f"/tools/{tid}", who="viewer")[0], 403)
        self.assertEqual(rig.api("DELETE", f"/tools/{tid}")[0], 200)
        self.assertIsNone(rig.gw.db.one("SELECT 1 FROM tools WHERE id = ?", (tid,)))

    def test_logo_upload_and_serving(self):
        rig = self.rig
        data = "data:image/png;base64," + base64.b64encode(PNG).decode()
        self.assertEqual(rig.api("PUT", "/tools/canva/logo", {"data": data})[0], 200)
        self.assertEqual(rig.api("PUT", "/tools/canva/logo", {"data": "data:image/png;base64,bm90IGFuIGltYWdl"})[0], 400)
        status, h, body = rig.request("GET", "/icons/canva")
        self.assertEqual((status, h["content-type"], body), (200, "image/png", PNG))
        self.assertIn("sandbox", h["content-security-policy"])
        self.assertEqual(rig.request("GET", "/icons/midjourney")[0], 404)
        self.assertIn(rig.request("GET", "/icons/..%2fetc")[0], (400, 404))
        canva = next(t for t in rig.api("GET", "/catalog")[1]["tools"] if t["id"] == "canva")
        self.assertTrue(canva["icon"].startswith("/icons/canva?v="))

    def test_who_holds_a_tool(self):
        rig = self.rig
        rig.api("PUT", "/subscriptions/canva", {"state": "active"})
        rig.api("POST", f"/people/{rig.person_id}/tools/canva")
        status, out = rig.api("GET", "/tools/canva/access")
        self.assertEqual(status, 200)
        grace = next(p for p in out["people"] if p["id"] == rig.person_id)
        self.assertTrue(grace["granted"])
        self.assertIn({"name": "Creative", "on": False}, out["teams"])


class LicenceTests(PortalBase):
    def test_paid_seats_against_real_use(self):
        rig = self.rig
        other = rig.gw.db.x("INSERT INTO people(name, department, created) VALUES(?,?,?)", ("Okello Brian", "Creative", time.time())).lastrowid
        renews = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 10 * 86400))
        rig.api("PUT", "/subscriptions/midjourney", {"state": "active", "monthly_cost": 60, "seats": 1, "renews_on": renews})
        rig.api("POST", f"/people/{rig.person_id}/tools/midjourney")
        rig.api("POST", f"/people/{other}/tools/midjourney")
        self.assertEqual(self.go("midjourney")[0], 302)  # Grace uses it; Brian never has
        status, lic = rig.api("GET", "/licences")
        self.assertEqual(status, 200)
        mj = next(t for t in lic["tools"] if t["id"] == "midjourney")
        self.assertEqual((mj["assigned"], mj["active"], mj["over_seats"], mj["cost_per_active"]), (2, 1, True, 60))
        self.assertEqual([p["name"] for p in mj["idle"]], ["Okello Brian"])
        # Brian's Midjourney seat, plus Grace's Claude Code and Codex, which she has never used
        self.assertEqual(lic["summary"]["idle_seats"], 3)
        self.assertAlmostEqual(lic["summary"]["idle_cost"], 30)
        self.assertIn("midjourney", [t["id"] for t in lic["renewals"]])
        launches = rig.api("GET", "/launches")[1]["items"]
        self.assertEqual((launches[0]["tool"], launches[0]["person"]), ("Midjourney", "Nansubuga Grace"))
        self.assertEqual(rig.api("GET", "/overview")[1]["launches_today"], 1)


class LogoParsingTests(unittest.TestCase):
    def test_sniff(self):
        self.assertEqual(icons.sniff(PNG), "image/png")
        self.assertEqual(icons.sniff(b"\x00\x00\x01\x00rest"), "image/x-icon")
        self.assertEqual(icons.sniff(b'  <svg xmlns="http://www.w3.org/2000/svg"></svg>'), "image/svg+xml")
        self.assertIsNone(icons.sniff(b"<html><body>not found</body></html>"))

    def test_best_icon_first(self):
        page = ('<head><link rel="icon" href="/favicon-16.png" sizes="16x16">'
                '<link rel="icon" href="/favicon-32.png" sizes="32x32"><link rel="icon" href="/logo.svg" type="image/svg+xml">'
                '<link rel="apple-touch-icon" href="https://cdn.example.com/touch.png"><link rel="stylesheet" href="/x.css"></head>')
        got = icons.candidates("https://example.com/home", page)
        self.assertEqual(got, ["https://cdn.example.com/touch.png", "https://example.com/favicon-32.png",
                               "https://example.com/favicon-16.png", "https://example.com/logo.svg",
                               "https://example.com/favicon.ico"])
        self.assertEqual(icons.candidates("https://example.com/", "")[-1], "https://example.com/favicon.ico")

    def test_never_fetches_from_the_local_network(self):
        self.assertFalse(icons._public("localhost"))
        self.assertFalse(icons._public("127.0.0.1"))
        self.assertFalse(icons._public("192.168.1.1"))
        self.assertIsNone(icons.fetch({"url": "http://127.0.0.1:1/"}))

    def test_uploads_must_be_small_images(self):
        with self.assertRaises(ValueError):
            icons.from_data_url("https://example.com/logo.png")
        with self.assertRaises(ValueError):
            icons.from_data_url("data:image/png;base64," + base64.b64encode(b"x" * 400_000).decode())
        self.assertEqual(icons.from_data_url("data:image/png;base64," + base64.b64encode(PNG).decode())[0], "image/png")


if __name__ == "__main__":
    unittest.main()
