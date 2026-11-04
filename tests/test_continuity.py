"""Continuity part 1 (G5, no schema change): a session is checked against the person on every request, a device
key and a web session never stand in for each other, disconnecting a device leaves the web sessions alone, one
sign-out ends one session, and every one of these actions leaves an audit record with counts and no secret."""

import json
import time

from .test_device_lifecycle import BODY, Lifecycle

EMAIL, PASSWORD = "grace@swangzavenue.com", "a-good-password-1"


class Continuity(Lifecycle):
    def sign_in(self):
        """A second, separate web session: a cookie of its own."""
        status, h, payload = self.rig.request("POST", "/api/login", {"email": EMAIL, "password": PASSWORD}, {"x-swangz-app": "1"})
        self.assertEqual(status, 200, payload)
        return h["set-cookie"].split(";")[0]

    def extension_token(self):
        status, out = self.staff("POST", "/extension/login", {"email": EMAIL, "password": PASSWORD}, cookie="")
        self.assertEqual(status, 200, out)
        return out["token"]

    def me(self, cookie=None, bearer=None):
        headers = {"x-swangz-app": "1"}
        if cookie:
            headers["cookie"] = cookie
        if bearer:
            headers["authorization"] = "Bearer " + bearer
        return self.rig.request("GET", "/api/me", None, headers)[0]

    def gate(self, bearer):
        return self.rig.request("GET", "/api/gate/config", None, {"x-swangz-app": "1", "authorization": "Bearer " + bearer})[0]

    def sessions(self):
        return self.db.scalar("SELECT COUNT(*) FROM staff_sessions WHERE person_id = ?", (self.rig.person_id,))

    def set_person(self, **fields):
        self.db.x(f"UPDATE people SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ?", [*fields.values(), self.rig.person_id])

    def audit_text(self):
        return json.dumps(self.db.q("SELECT * FROM audit"), default=str)

    def entry(self, action):
        rows = self.audits(action)
        self.assertEqual(len(rows), 1, rows)
        return rows[0], json.loads(rows[0]["before_json"] or "null"), json.loads(rows[0]["after_json"] or "null")


class SessionIsCheckedEveryRequest(Continuity):
    def test_a_suspended_person_s_existing_session_and_extension_token_open_nothing(self):
        token = self.extension_token()
        self.assertEqual((self.me(self.person_cookie), self.me(bearer=token), self.gate(token)), (200, 200, 200))
        self.set_person(status="suspended")  # not through the admin route, which deletes sessions: the check is per request
        self.assertEqual((self.me(self.person_cookie), self.me(bearer=token), self.gate(token)), (401, 401, 401))
        self.set_person(status="active")  # the rows were never touched, so restoring the person restores the sessions
        self.assertEqual((self.me(self.person_cookie), self.me(bearer=token), self.gate(token)), (200, 200, 200))

    def test_ended_access_opens_nothing_and_a_later_end_date_does_not(self):
        token = self.extension_token()
        self.set_person(access_until=time.time() - 5)
        self.assertEqual((self.me(self.person_cookie), self.me(bearer=token), self.gate(token)), (401, 401, 401))
        self.set_person(access_until=time.time() + 3600)
        self.assertEqual((self.me(self.person_cookie), self.me(bearer=token)), (200, 200))

    def test_a_personal_address_outside_the_allowed_accounts_opens_nothing(self):
        self.set_person(email="grace@gmail.com")
        self.assertEqual(self.me(self.person_cookie), 401)

    def test_signing_in_is_refused_with_the_right_password_for_a_suspended_or_ended_person(self):
        self.set_person(status="suspended")
        before = self.sessions()
        for path in ("/login", "/extension/login"):
            status, out = self.staff("POST", path, {"email": EMAIL, "password": PASSWORD}, cookie="")
            self.assertEqual((status, out.get("code")), (403, "person_paused"), path)
        self.assertEqual(self.sessions(), before)  # nothing was minted
        self.set_person(status="active", access_until=time.time() - 5)
        for path in ("/login", "/extension/login"):
            self.assertEqual(self.staff("POST", path, {"email": EMAIL, "password": PASSWORD}, cookie="")[0], 403, path)
        self.assertEqual(self.sessions(), before)
        self.assertEqual(self.audits("signed in to Swangz AI Hub"), [])
        self.assertEqual(self.audits("connected the access extension"), [])

    def test_a_wrong_password_still_says_the_same_thing_whatever_the_status(self):
        self.set_person(status="suspended")
        status, out = self.staff("POST", "/login", {"email": EMAIL, "password": "not-the-password"}, cookie="")
        self.assertEqual((status, out.get("code")), (401, None))  # no hint that the account exists, or why it is shut


class DeviceKeysAndSessionsStayApart(Continuity):
    def test_a_device_key_is_not_a_session_whichever_way_it_is_presented(self):
        as_cookie = f"sgw_staff={self.key}"
        self.assertEqual(self.me(cookie=as_cookie), 401)
        self.assertEqual(self.me(bearer=self.key), 401)
        self.assertEqual(self.gate(self.key), 401)

    def test_a_session_or_extension_token_is_not_a_device_key_or_an_api_key(self):
        session = self.person_cookie.split("=", 1)[1]
        for token in (session, self.extension_token()):
            self.assertEqual(self.manifest(token)[0], 401)
            self.assertEqual(self.api("POST", "/device/rotate", {}, key=token)[0], 401)
            self.assertEqual(self.api("POST", "/device/signout", {}, key=token)[0], 401)
            self.assertIn(self.rig.anthropic(BODY, key=token)[0], (401, 403))
        self.assertEqual(self.unrevoked(), 1)  # and nothing happened to the device
        self.assertEqual(self.manifest()[0], 200)

    def test_a_revoked_device_key_does_not_become_a_session(self):
        self.assertEqual(self.staff("POST", f"/keys/{self.device['key_id']}/revoke", cookie=self.person_cookie)[0], 200)
        self.assertEqual((self.me(bearer=self.key), self.me(cookie=f"sgw_staff={self.key}")), (401, 401))


class DisconnectingADeviceLeavesTheWebAlone(Continuity):
    def test_the_person_disconnecting_mid_rotation_cuts_both_keys_and_live_requests_but_not_sessions(self):
        out = self.rotate()[1]
        ext = self.extension_token()
        other = self.sign_in()
        live = self.rig.gw.live
        tickets = [live.start(key_id=self.device["key_id"], person_id=self.rig.person_id),
                   live.start(key_id=out["key_id"], person_id=self.rig.person_id)]
        mine = live.start(key_id="someotherkey", person_id=self.rig.person_id)  # a different key of the same person
        sessions = self.sessions()
        self.assertEqual(self.staff("POST", f"/keys/{self.device['key_id']}/revoke", cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.unrevoked(), 0)
        self.assertEqual(self.code(self.key), (401, "device_revoked"))
        self.assertEqual(self.code(out["key"]), (401, "device_revoked"))
        self.assertTrue(all(t.reason for t in tickets))
        self.assertFalse(mine.reason)
        self.assertEqual(self.sessions(), sessions)
        self.assertEqual((self.me(self.person_cookie), self.me(other), self.me(bearer=ext)), (200, 200, 200))
        entry, before, after = self.entry("disconnected a device%")
        self.assertEqual(entry["correlation"], f"device:{self.device_id}")
        self.assertEqual(sorted(before["keys"]), sorted([self.device["key_id"], out["key_id"]]))
        self.assertEqual(after, {"keys_revoked": 2, "requests_cut": 2})

    def test_an_administrator_revoking_mid_rotation_does_the_same(self):
        out = self.rotate()[1]
        cookie = self.sign_in()
        live = self.rig.gw.live
        ticket = live.start(key_id=out["key_id"], person_id=self.rig.person_id)
        self.assertEqual(self.rig.api("POST", f"/keys/{out['key_id']}/revoke")[0], 200)
        self.assertEqual(self.unrevoked(), 0)
        self.assertTrue(ticket.reason)
        self.assertEqual((self.me(self.person_cookie), self.me(cookie)), (200, 200))
        entry, before, after = self.entry("revoked a key")
        self.assertEqual(entry["correlation"], f"device:{self.device_id}")
        self.assertEqual(sorted(before["keys"]), sorted([self.device["key_id"], out["key_id"]]))
        self.assertEqual(after, {"keys_revoked": 2, "requests_cut": 1})
        self.assertIn("1 request(s) cut", entry["detail"])

    def test_a_single_key_revoke_is_audited_with_the_same_shape(self):
        self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")
        _, before, after = self.entry("revoked a key")
        self.assertEqual((before, after), ({"keys": [self.device["key_id"]]}, {"keys_revoked": 1, "requests_cut": 0}))

    def test_the_app_signing_itself_out_mid_rotation_ends_both_keys_and_leaves_sessions(self):
        out = self.rotate()[1]
        live = self.rig.gw.live
        ticket = live.start(key_id=self.device["key_id"], person_id=self.rig.person_id)
        self.assertEqual(self.api("POST", "/device/signout", {}, key=self.key)[0], 200)  # the new key has not been used yet: both are live
        self.assertEqual(self.unrevoked(), 0)
        self.assertTrue(ticket.reason)
        self.assertEqual(self.me(self.person_cookie), 200)
        entry, before, after = self.entry("signed a device out of Swangz")
        self.assertEqual(entry["correlation"], f"device:{self.device_id}")
        self.assertEqual(sorted(before["keys"]), sorted([self.device["key_id"], out["key_id"]]))
        self.assertEqual(after, {"keys_revoked": 2, "requests_cut": 1})

    def test_a_second_device_is_untouched(self):
        second = self.enrol(name="Grace's phone")
        self.assertEqual(self.staff("POST", f"/keys/{self.device['key_id']}/revoke", cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.manifest(second["key"])[0], 200)


class SigningOutEndsOneSession(Continuity):
    def test_one_sign_out_leaves_the_other_sessions_the_extension_and_the_devices(self):
        other, ext = self.sign_in(), self.extension_token()
        self.assertEqual(self.sessions(), 3)
        status, h, _ = self.rig.request("POST", "/api/logout", {}, {"x-swangz-app": "1", "cookie": self.person_cookie})
        self.assertEqual(status, 200)
        self.assertIn("sgw_staff=;", h["set-cookie"].replace(" ", ""))
        self.assertEqual(self.me(self.person_cookie), 401)
        self.assertEqual((self.me(other), self.me(bearer=ext), self.manifest()[0]), (200, 200, 200))
        self.assertEqual(self.sessions(), 2)
        self.assertEqual(self.unrevoked(), 1)
        entry, before, after = self.entry("signed out of the web app")
        self.assertEqual(entry["correlation"], f"person:{self.rig.person_id}")
        self.assertEqual((before, after), ({"sessions_ended": 0}, {"sessions_ended": 1, "sessions_remaining": 2}))

    def test_signing_out_twice_or_without_a_session_changes_and_records_nothing(self):
        cookie = self.person_cookie
        for _ in range(2):
            self.assertEqual(self.rig.request("POST", "/api/logout", {}, {"x-swangz-app": "1", "cookie": cookie})[0], 200)
        self.assertEqual(self.rig.request("POST", "/api/logout", {}, {"x-swangz-app": "1"})[0], 200)
        self.assertEqual(len(self.audits("signed out of the web app")), 1)


class AuditsCarryCountsAndNoSecrets(Continuity):
    def test_suspending_records_what_it_ended_and_resuming_restores_nothing_it_did_not_take(self):
        ext = self.extension_token()
        live = self.rig.gw.live
        ticket = live.start(key_id=self.device["key_id"], person_id=self.rig.person_id)
        self.assertEqual(self.rig.api("POST", f"/people/{self.rig.person_id}/suspend")[0], 200)
        self.assertTrue(ticket.reason)
        entry, before, after = self.entry("suspended a person")
        self.assertEqual(entry["correlation"], f"person:{self.rig.person_id}")
        self.assertEqual(before, {"status": "active"})
        self.assertEqual((after["status"], after["requests_cut"], after["web_sessions_ended"], after["turns_ended"]), ("suspended", 1, 2, 0))
        self.assertEqual((self.me(self.person_cookie), self.me(bearer=ext)), (401, 401))
        self.assertEqual(self.sessions(), 0)
        self.assertEqual(self.rig.api("POST", f"/people/{self.rig.person_id}/resume")[0], 200)
        _, before, after = self.entry("restored a person")
        self.assertEqual((before, after), ({"status": "suspended"}, {"status": "active"}))
        self.assertEqual(self.me(self.person_cookie), 401)  # a restored person signs in again; old sessions are gone

    def test_no_session_extension_or_device_secret_reaches_the_audit_log(self):
        ext = self.extension_token()
        out = self.rotate()[1]
        other = self.sign_in()
        self.staff("POST", f"/keys/{self.device['key_id']}/revoke", cookie=self.person_cookie)
        self.rig.request("POST", "/api/logout", {}, {"x-swangz-app": "1", "cookie": other})
        self.rig.api("POST", f"/people/{self.rig.person_id}/suspend")
        text = self.audit_text()
        for secret in (ext, other.split("=", 1)[1], self.person_cookie.split("=", 1)[1], out["key"], out["key"].split("_", 2)[2],
                       self.key, self.key.split("_", 2)[2], PASSWORD):
            self.assertNotIn(secret, text)
