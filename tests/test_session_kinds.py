"""G5 continuity part 2: the read-only paused view, session kinds (schema v23), and what a session may reach."""

import json
import os
import re
import tempfile
import time
import unittest
from unittest import mock

import gateway.db as dbmod
from gateway import reporting, security, staff
from gateway.db import DB, SCHEMA

from .test_devices import DeviceBase

EMAIL, PASSWORD = "grace@swangzavenue.com", "a-good-password-1"
ALLOWED = {("GET", r"/me"), ("GET", r"/hub/reports"), ("GET", r"/hub/reports/(?P<rid>\d+)"),
           ("GET", r"/hub/notifications"), ("POST", r"/logout")}


class Base(DeviceBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db
        self.pid = self.rig.person_id

    def set_person(self, **fields):
        self.db.x(f"UPDATE people SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ?", [*fields.values(), self.pid])

    def pause(self):
        self.set_person(status="suspended")  # not through the admin route (that deletes sessions): checked per request

    def call(self, method, path, body=None, cookie=None, bearer=None):
        headers = {"x-swangz-app": "1"}
        if cookie:
            headers["cookie"] = cookie
        if bearer:
            headers["authorization"] = "Bearer " + bearer
        status, h, payload = self.rig.request(method, "/api" + path, body, headers)
        try:
            return status, json.loads(payload) if payload else None
        except ValueError:
            return status, payload

    def extension_token(self):
        status, out = self.call("POST", "/extension/login", {"email": EMAIL, "password": PASSWORD})
        self.assertEqual(status, 200, out)
        return out["token"]

    def kinds(self):
        return {r["kind"] for r in self.db.q("SELECT kind FROM staff_sessions WHERE person_id = ?", (self.pid,))}


def sample(rx):
    """A concrete path that the route's pattern accepts."""
    path = re.sub(r"\(\?P<\w+>[^)]*\)", "1", rx.pattern)
    if rx.fullmatch(path):
        return path
    for filler in ("a" * 30, "0123456789ab"):
        path = re.sub(r"\(\?P<\w+>[^)]*\)", filler, rx.pattern)
        if rx.fullmatch(path):
            return path
    raise AssertionError("no sample for " + rx.pattern)


class PausedViewTests(Base):
    def test_the_routes_a_paused_person_may_use_are_exactly_these_and_none_but_logout_writes(self):
        found = {(m, rx.pattern) for m, rx, fn, signed_in, paused_ok in staff.ROUTES if paused_ok}
        self.assertEqual(found, ALLOWED)
        self.assertEqual({m for m, p in found if p != r"/logout"}, {"GET"})

    def test_registering_a_write_as_paused_ok_fails_at_registration(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.assertRaises(ValueError):
                staff.route(method, r"/something", paused_ok=True)
        before = len(staff.ROUTES)
        staff.route("POST", r"/logout", signed_in=False, paused_ok=True)  # the one allowed write
        del staff.ROUTES[before:]

    def test_the_allowed_routes_answer_a_paused_person_and_the_me_view_is_trimmed(self):
        self.set_person(department="Finance")
        other = self.db.x("INSERT INTO people(name, email, created) VALUES('Other', 'other@swangzavenue.com', 1)")
        start = reporting.week(self.rig.gw)["starts"] - 7 * 86400
        for pid in (self.pid, self.db.scalar("SELECT id FROM people WHERE email = 'other@swangzavenue.com'")):
            self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('chatgpt', ?, ?, 'opened')", (pid, start + 100))
        reporting.compile_closed(self.rig.gw)
        mine = self.db.scalar("SELECT id FROM hub_reports WHERE person_id = ?", (self.pid,))
        theirs = self.db.scalar("SELECT id FROM hub_reports WHERE person_id != ?", (self.pid,))
        self.assertTrue(mine and theirs)
        self.pause()
        self.db.x("INSERT INTO hub_notifications(person_id, title, href, created, dedupe_key) VALUES(?, 'Hello', '', 1, 'k1')", (self.pid,))
        c = self.person_cookie
        status, me = self.call("GET", "/me", cookie=c)
        self.assertEqual(status, 200)
        self.assertEqual(sorted(me), ["name", "paused_view", "reason", "status", "support_contact"])
        self.assertEqual((me["paused_view"], me["status"]), (True, "paused"))
        self.assertEqual(self.call("GET", "/hub/reports", cookie=c)[0], 200)
        self.assertEqual(self.call("GET", f"/hub/reports/{mine}", cookie=c)[0], 200)
        self.assertEqual(self.call("GET", f"/hub/reports/{theirs}", cookie=c)[0], 404)  # own only
        status, out = self.call("GET", "/hub/notifications", cookie=c)
        self.assertEqual(status, 200)
        self.assertIn("Hello", [i["title"] for i in out["items"]])
        # a notice written before the title named its tool is named when read
        self.db.x("UPDATE hub_notifications SET title = 'Complete your weekly tool report' WHERE dedupe_key = ?", (f"report-required:{mine}",))
        titles = [i["title"] for i in self.call("GET", "/hub/notifications", cookie=c)[1]["items"]]
        self.assertTrue(any(t.startswith("Complete your weekly report for ChatGPT, week of ") for t in titles), titles)
        self.assertNotIn("Complete your weekly tool report", titles)
        self.assertTrue(all(set(i) == {"id", "title", "href", "created", "read", "email_state"} for i in self.call("GET", "/hub/notifications", cookie=c)[1]["items"]))
        self.assertEqual(self.call("POST", "/logout", {}, cookie=c)[0], 200)

    def test_every_other_signed_in_route_refuses_a_paused_web_session(self):
        self.pause()
        checked = 0
        for method, rx, fn, signed_in, paused_ok in staff.ROUTES:
            if not signed_in or paused_ok:
                continue
            status, out = self.call(method, sample(rx), {}, cookie=self.person_cookie)
            self.assertEqual((status, out.get("code")), (403, "person_paused"), (method, rx.pattern))
            checked += 1
        self.assertGreaterEqual(checked, 30)  # every module's routes are in the sweep

    def test_go_device_gate_studio_and_keys_open_nothing_for_a_paused_person(self):
        self.pause()
        c = self.person_cookie
        status, h, payload = self.rig.request("GET", "/go/chatgpt", None, {"cookie": c})
        self.assertEqual(status, 403)
        self.assertIn(b"paused", payload.lower())
        self.assertEqual(self.page(cookie=c)[0], 403)
        self.assertEqual(self.page("POST", form={"code": "ABCD-EFGH"}, cookie=c)[0], 403)
        for method, path in (("GET", "/studio"), ("POST", "/studio/voice"), ("POST", "/keys"), ("GET", "/gate/turns"),
                             ("POST", "/gate/open"), ("POST", "/gate/close"), ("POST", "/tools/chatgpt/request")):
            self.assertEqual(self.call(method, path, {}, cookie=c)[0], 403, path)
        self.assertEqual(self.call("GET", "/gate/config", cookie=c)[0], 401)  # the gate takes the extension's own sign-in only

    def test_a_paused_extension_session_and_extension_sign_in_are_refused(self):
        token = self.extension_token()
        self.pause()
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 401)
        self.assertEqual(self.call("GET", "/gate/turns", bearer=token)[0], 401)
        self.assertEqual(self.call("GET", "/me", bearer=token)[0], 401)  # never the paused view: that is for web sessions only
        status, out = self.call("POST", "/extension/login", {"email": EMAIL, "password": PASSWORD})
        self.assertEqual((status, out.get("code")), (403, "person_paused"))

    def test_an_invite_is_still_refused_for_a_paused_person(self):
        self.pause()
        token = self.invite()
        self.assertEqual(self.call("POST", "/welcome", {"token": token, "password": "another-good-password"})[0], 403)

    def test_ended_access_gets_the_same_paused_view_and_nothing_else(self):
        self.set_person(access_until=time.time() - 5)
        c = self.person_cookie
        status, me = self.call("GET", "/me", cookie=c)
        self.assertEqual((status, me["paused_view"], sorted(me)), (200, True, ["name", "paused_view", "reason", "status", "support_contact"]))
        for path in ("/hub/reports", "/hub/notifications"):
            self.assertEqual(self.call("GET", path, cookie=c)[0], 200, path)
        for method, rx, fn, signed_in, paused_ok in staff.ROUTES:
            if signed_in and not paused_ok:
                self.assertEqual(self.call(method, sample(rx), {}, cookie=c)[0], 403, (method, rx.pattern))
        self.assertEqual(self.rig.request("GET", "/go/chatgpt", None, {"cookie": c})[0], 403)
        self.assertEqual(self.page(cookie=c)[0], 403)
        self.assertEqual(self.call("POST", "/logout", {}, cookie=c)[0], 200)

    def test_ended_access_still_opens_nothing_for_the_extension_the_proxy_the_device_and_an_invite(self):
        token = self.extension_token()
        device = self.enrol()
        self.set_person(access_until=time.time() - 5)
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 401)
        status, out = self.call("POST", "/extension/login", {"email": EMAIL, "password": PASSWORD})
        self.assertEqual((status, out.get("code")), (403, "person_paused"))
        self.assertEqual(self.call("POST", "/welcome", {"token": self.invite(), "password": "another-good-password"})[0], 403)
        self.assertEqual(self.api("GET", "/device/manifest", key=device["key"])[0], 403)
        self.assertEqual(self.rig.anthropic({"model": "claude-test", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
                                            key=device["key"])[0], 403)

    def test_a_paused_session_is_checked_every_request_and_activation_restores_the_full_view(self):
        self.pause()
        self.assertTrue(self.call("GET", "/me", cookie=self.person_cookie)[1]["paused_view"])
        self.set_person(status="active")
        status, me = self.call("GET", "/me", cookie=self.person_cookie)
        self.assertEqual(status, 200)
        self.assertNotIn("paused_view", me)

    def test_suspending_through_the_console_still_ends_every_session(self):
        token = self.extension_token()
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 200)
        status, _ = self.rig.api("POST", f"/people/{self.pid}/suspend")
        self.assertEqual(status, 200)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM staff_sessions WHERE person_id = ?", (self.pid,)), 0)
        self.assertEqual(self.call("GET", "/me", cookie=self.person_cookie)[0], 401)  # sign in again for the paused view


class SessionKindTests(Base):
    def test_sign_in_makes_a_web_row_and_the_extension_an_extension_row_with_last_seen(self):
        self.assertEqual(self.kinds(), {"web"})  # the invite's own sign-in
        self.call("POST", "/login", {"email": EMAIL, "password": PASSWORD})
        token = self.extension_token()
        self.assertEqual(self.kinds(), {"web", "extension"})
        self.assertEqual(self.db.scalar("SELECT kind FROM staff_sessions WHERE token_hash = ?", (security.sha256(token),)), "extension")
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 200)
        self.assertGreater(self.db.scalar("SELECT last_seen FROM staff_sessions WHERE token_hash = ?", (security.sha256(token),)), 0)

    def test_a_cookie_only_works_for_a_web_row_and_a_bearer_only_for_an_extension_row(self):
        token = self.extension_token()
        web = self.person_cookie.split("=", 1)[1]
        self.assertEqual(self.call("GET", "/me", cookie="sgw_staff=" + token)[0], 401)       # an extension token as a cookie
        self.assertEqual(self.call("GET", "/gate/config", bearer=web)[0], 401)              # a web token as a bearer
        self.assertEqual(self.call("GET", "/me", bearer=web)[0], 401)

    def test_an_extension_session_reaches_only_the_extension_gate_and_logout(self):
        token = self.extension_token()
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 200)
        self.assertEqual(self.call("GET", "/gate/turns", bearer=token)[0], 200)
        # the blocked page's "Request access" is the one other thing it may do
        self.assertEqual(self.call("POST", "/tools/chatgpt/request", {"reason": "need it"}, bearer=token)[0], 200)
        self.assertEqual(self.call("POST", "/tools/chatgpt/request", {}, cookie="sgw_staff=" + token)[0], 401)
        for method, path in (("GET", "/me"), ("GET", "/studio"), ("POST", "/keys"), ("GET", "/hub/reports"),
                             ("POST", "/tools/chatgpt/turn/end"), ("GET", "/hub/notifications")):
            status, out = self.call(method, path, {}, bearer=token)
            self.assertIn(status, (401, 403), path)
            if status == 403:
                self.assertEqual(out.get("code"), "session_kind", path)
        self.assertEqual(self.page(cookie="")[0], 401)
        status, h, _ = self.rig.request("GET", "/device", None, {"authorization": "Bearer " + token})
        self.assertEqual(status, 401)  # /device takes the browser's cookie only
        status, h, _ = self.rig.request("GET", "/go/chatgpt", None, {"authorization": "Bearer " + token})
        self.assertEqual(status, 302)
        self.assertEqual(h["location"], "/")

    def test_a_web_sign_out_ends_only_a_web_row_and_never_an_extension_row(self):
        token = self.extension_token()  # the bearer's own sign-out is ExtensionLogoutTests
        self.assertEqual(self.call("POST", "/logout", {}, cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.call("GET", "/me", cookie=self.person_cookie)[0], 401)
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 200)


class ExtensionLogoutTests(Base):
    """A bearer's /logout ends that one extension session, and nothing else."""

    def rows(self, kind):
        return self.db.scalar("SELECT COUNT(*) FROM staff_sessions WHERE person_id = ? AND kind = ?", (self.pid, kind))

    def test_the_bearer_ends_its_own_extension_session_only(self):
        first, second = self.extension_token(), self.extension_token()
        web_before = self.rows("web")
        self.assertEqual(self.call("POST", "/logout", {}, bearer=first), (200, {"ok": True}))
        self.assertIsNone(self.db.one("SELECT 1 FROM staff_sessions WHERE token_hash = ?", (security.sha256(first),)))
        self.assertEqual(self.call("GET", "/gate/config", bearer=first)[0], 401)   # dead at once, not at expiry
        self.assertEqual(self.call("POST", "/gate/open", {"host": "chatgpt.com"}, bearer=first)[0], 401)
        self.assertEqual(self.call("GET", "/gate/turns", bearer=second)[0], 200)   # the other browser's extension
        self.assertEqual((self.rows("extension"), self.rows("web")), (1, web_before))
        self.assertEqual(self.call("GET", "/me", cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM keys WHERE person_id = ? AND revoked IS NULL", (self.pid,)),
                         self.db.scalar("SELECT COUNT(*) FROM keys WHERE person_id = ?", (self.pid,)), "no key is touched")

    def test_it_is_audited_once_with_counts_and_no_token(self):
        token = self.extension_token()
        self.call("POST", "/logout", {}, bearer=token)
        self.call("POST", "/logout", {}, bearer=token)  # again: already gone, nothing to record
        rows = self.db.q("SELECT * FROM audit WHERE action = 'access extension session ended'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["correlation"], f"person:{self.pid}")
        self.assertEqual(json.loads(rows[0]["after_json"])["sessions_ended"], 1)
        self.assertNotIn(token, json.dumps([dict(r) for r in rows]))
        self.assertNotIn(security.sha256(token), json.dumps([dict(r) for r in rows]))

    def test_kinds_stay_apart_at_logout(self):
        token = self.extension_token()
        web = self.person_cookie.split("=", 1)[1]
        self.assertEqual(self.call("POST", "/logout", {}, bearer=web)[0], 200)          # a web token as a bearer
        self.assertEqual(self.call("GET", "/me", cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.call("POST", "/logout", {}, cookie="sgw_staff=" + token)[0], 200)   # an extension token as a cookie
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 200)
        self.assertEqual(self.call("POST", "/logout", {}, bearer="not-a-session")[0], 200)
        self.assertEqual(self.call("POST", "/logout", {}, bearer=self.rig.key)[0], 200)  # a device/API key is never a session
        self.assertEqual(self.rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]})[0], 200)
        self.assertEqual((self.rows("extension"), self.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'access extension session ended'")), (1, 0))

    def test_cookie_and_bearer_together_end_one_of_each(self):
        token = self.extension_token()
        self.assertEqual(self.call("POST", "/logout", {}, cookie=self.person_cookie, bearer=token)[0], 200)
        self.assertEqual(self.call("GET", "/me", cookie=self.person_cookie)[0], 401)
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 401)

    def test_a_paused_or_ended_person_can_still_end_their_extension_session(self):
        for change in ({"status": "suspended"}, {"status": "active", "access_until": 1}):
            self.set_person(status="active", access_until=None)
            token = self.extension_token()
            self.set_person(**change)
            self.assertEqual(self.call("POST", "/logout", {}, bearer=token)[0], 200, change)
            self.assertIsNone(self.db.one("SELECT 1 FROM staff_sessions WHERE token_hash = ?", (security.sha256(token),)), change)

    def test_it_still_needs_the_app_header(self):
        token = self.extension_token()
        status, _, _ = self.rig.request("POST", "/api/logout", {}, {"authorization": "Bearer " + token})
        self.assertNotEqual(status, 200)
        self.assertEqual(self.call("GET", "/gate/config", bearer=token)[0], 200)


class UpgradeTests(unittest.TestCase):
    def test_a_v22_database_keeps_every_session_as_an_extension_session(self):
        path = os.path.join(tempfile.mkdtemp(prefix="sgw-v23-"), "g.db")
        with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:22]):
            old = DB(path)
            self.assertEqual(old.scalar("SELECT v FROM meta WHERE k = 'schema'"), "22")
            old.x("INSERT INTO people(id, name, email, created) VALUES(1, 'A', 'a@swangzavenue.com', 1)")
            for t in ("cookie-token", "bearer-token"):
                old.x("INSERT INTO staff_sessions(token_hash, person_id, created, expires) VALUES(?, 1, 1, ?)",
                      (security.sha256(t), time.time() + 3600))
            old.close()
        db = DB(path)
        self.assertEqual(db.scalar("SELECT v FROM meta WHERE k = 'schema'"), str(len(SCHEMA)))
        self.assertGreaterEqual(len(SCHEMA), 23)
        rows = db.q("SELECT kind, last_seen FROM staff_sessions")
        self.assertEqual([(r["kind"], r["last_seen"]) for r in rows], [("extension", None)] * 2)  # nothing deleted
        with self.assertRaises(Exception):
            db.x("UPDATE staff_sessions SET kind = 'other'")
        db.close()
        DB(path).close()  # opening again changes nothing

    def test_after_the_upgrade_an_old_cookie_is_refused_and_an_old_bearer_works_on_the_gate_only(self):
        class Upgraded(Base):
            def runTest(self):
                pass
        t = Upgraded()
        t.setUp()
        try:
            token = "old-session-token-0123456789"
            t.db.x("INSERT INTO staff_sessions(token_hash, person_id, created, expires) VALUES(?,?,?,?)",
                   (security.sha256(token), t.pid, time.time(), time.time() + 3600))  # no kind: the v23 default
            self.assertEqual(t.db.scalar("SELECT kind FROM staff_sessions WHERE token_hash = ?", (security.sha256(token),)), "extension")
            self.assertEqual(t.call("GET", "/me", cookie="sgw_staff=" + token)[0], 401)
            self.assertEqual(t.call("GET", "/gate/config", bearer=token)[0], 200)
            self.assertEqual(t.page(cookie="")[0], 401)
            self.assertEqual(t.call("POST", "/keys", {"label": "x"}, bearer=token)[0], 403)
            self.assertEqual(t.call("GET", "/studio", bearer=token)[0], 403)
        finally:
            t.tearDown()


if __name__ == "__main__":
    unittest.main()
