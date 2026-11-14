"""One real person's whole path, over HTTP only (delivery priority, function track item 2).

An admin adds a person, a tool and its subscription and grants it; the person sets a password from their sign-in
link, sees the tool, opens it through /go/; the admin sees the launch in Activity; the grant is taken away and
the very next open is refused; the week closes and the person submits the weekly report that open made due, which
the admin then sees; the person signs out and their session is gone. Nothing is written to the database directly:
every step is a request a browser would make, or the server's own hourly report job."""

import json
import time
import unittest

from gateway import reporting

from .support import Rig

PASSWORD = "a-good-first-password"
APP = {"x-swangz-app": "1"}


class RealUserJourneyTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)

    def staff(self, method, path, body=None, cookie=None):
        headers = dict(APP)
        if cookie:
            headers["cookie"] = cookie
        status, h, payload = self.rig.request(method, path, body, headers)
        try:
            return status, h, json.loads(payload)
        except ValueError:
            return status, h, payload.decode("utf-8", "replace")

    def launches(self, pid):
        status, page = self.rig.api("GET", f"/timeline?type=launch&person={pid}")
        self.assertEqual(status, 200, page)
        return [e for e in page["items"] if e["type"] == "launch" and e["person_id"] == pid]

    def test_add_grant_sign_in_open_see_revoke_sign_out(self):
        api = self.rig.api
        # the admin adds a person, a tool and its subscription, and grants it
        status, person = api("POST", "/people", {"name": "Namara Joy", "email": "joy@swangzavenue.com",
                                                 "department": "Creative"})
        self.assertEqual(status, 200, person)
        pid = person["id"]
        status, tool = api("POST", "/tools", {"name": "Journey Sketch", "kind": "site", "signin": "own",
                                              "url": "https://sketch.example.test/"})
        self.assertEqual(status, 200, tool)
        tid = tool["id"]
        self.assertEqual(api("PUT", f"/subscriptions/{tid}", {"state": "active", "seats": 3})[0], 200)
        self.assertEqual(api("POST", f"/people/{pid}/tools/{tid}", {})[0], 200)
        status, invite = api("POST", f"/people/{pid}/invite", {})
        self.assertEqual(status, 200, invite)
        token = invite["link"].rsplit("/", 1)[1]

        # the person sets a password from the link, which signs them in
        status, h, body = self.staff("POST", "/api/welcome", {"token": token, "password": PASSWORD})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.staff("POST", "/api/welcome", {"token": token, "password": PASSWORD})[0], 404)  # used once
        self.staff("POST", "/api/logout", {}, h["set-cookie"].split(";")[0])
        status, h, body = self.staff("POST", "/api/login", {"email": "joy@swangzavenue.com", "password": PASSWORD})
        self.assertEqual(status, 200, body)
        cookie = h["set-cookie"].split(";")[0]

        # they see the tool, enabled, and open it
        status, _, me = self.staff("GET", "/api/me", cookie=cookie)
        self.assertEqual(status, 200, me)
        mine = {t["id"]: t for t in me["catalog"]}
        self.assertIn(tid, mine)
        self.assertEqual(mine[tid]["state"], "enabled", mine[tid])
        status, h, _ = self.staff("GET", f"/go/{tid}", cookie=cookie)
        self.assertEqual(status, 302)
        self.assertEqual(h["location"], "https://sketch.example.test/")

        # the admin sees the launch in Activity
        seen = self.launches(pid)
        self.assertEqual(len(seen), 1, seen)
        self.assertEqual(seen[0]["person"], "Namara Joy")
        self.assertIn("Journey Sketch", json.dumps(seen[0]))

        # the grant is taken away: the very next open is refused, on the same session, and that is recorded too
        self.assertEqual(api("DELETE", f"/people/{pid}/tools/{tid}")[0], 200)
        status, h, page = self.staff("GET", f"/go/{tid}", cookie=cookie)
        self.assertEqual(status, 403, page)
        self.assertNotIn("location", h)
        self.assertEqual(len(self.launches(pid)), 2)
        status, _, me = self.staff("GET", "/api/me", cookie=cookie)
        self.assertNotEqual({t["id"]: t for t in me["catalog"]}[tid]["state"], "enabled")

        # the week closes (the hourly job, run with the clock a week on): the open made a weekly report due, which the
        # person fills in and submits from the staff app, and the admin sees it waiting for review
        reporting.compile_closed(self.rig.gw, now=time.time() + 8 * 86400)
        status, _, mine = self.staff("GET", "/api/hub/reports", cookie=cookie)
        self.assertEqual(status, 200, mine)
        due = [r for r in mine["items"] if r["kind"] == "weekly" and r["tool_id"] == tid]
        self.assertEqual(len(due), 1, mine)
        rid = due[0]["id"]
        self.assertEqual(due[0]["evidence"]["launches"], 1, due[0])
        status, _, body = self.staff("PUT", f"/api/hub/reports/{rid}", {"reason": "Sketched the spring campaign"}, cookie)
        self.assertEqual(status, 200, body)
        status, _, body = self.staff("POST", f"/api/hub/reports/{rid}/submit",
                                     {"usage_confirmation": "used", "reason": "Sketched the spring campaign"}, cookie)
        self.assertEqual(status, 200, body)
        status, page = api("GET", f"/hub/reports?person={pid}")
        self.assertEqual(status, 200, page)
        self.assertEqual([r["state"] for r in page["items"] if r["id"] == rid], ["submitted"], page)

        # they sign out: the same cookie no longer opens anything
        self.assertEqual(self.staff("POST", "/api/logout", {}, cookie)[0], 200)
        self.assertEqual(self.staff("GET", "/api/me", cookie=cookie)[0], 401)
        status, h, _ = self.staff("GET", f"/go/{tid}", cookie=cookie)
        self.assertEqual((status, h.get("location")), (302, "/"))

        # the audit log holds each change, with who made it
        actions = [r["action"] for r in self.rig.gw.db.q("SELECT action FROM audit ORDER BY id")]
        for expected in ("added a person", "turned a tool on for a person", "created a sign-in link",
                         "set their Swangz AI Hub password"):
            self.assertIn(expected, actions)


if __name__ == "__main__":
    unittest.main()
