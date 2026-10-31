"""The Swangz app on people's own devices: enrolling with a code, what each device is offered, check-ins,
revocation and the packages Swangz publishes."""

import hashlib
import io
import json
import os
import re
import tempfile
import time
import unittest
import zipfile
from urllib.parse import quote, urlencode

from gateway import enroll
from gateway.db import SCHEMA

from .support import Rig
from .test_gateway import StaffBase


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


class DeviceBase(StaffBase):
    """A person who can sign in to the staff app (an invite link sets their password)."""

    def setUp(self):
        super().setUp()
        self.token = self.invite()
        status, out = self.staff("POST", "/welcome", {"token": self.token, "password": "a-good-password-1"})
        self.assertEqual(status, 200, out)
        self.person_cookie = self.cookie
        self.tmp = tempfile.mkdtemp(prefix="sgw-pkg-")

    # ------------------------------------------------------------ the device's side

    def api(self, method, path, body=None, key=None, ip=None):
        headers = {"x-swangz-app": "1"}
        if key:
            headers["authorization"] = "Bearer " + key
        status, h, payload = self.rig.request(method, "/api" + path, body, headers)
        try:
            return status, json.loads(payload), h
        except ValueError:
            return status, payload, h

    def ask(self, **extra):
        body = {"name": "Grace's laptop", "os": "Windows 11", "arch": "x86_64", "app_version": "0.1.0", **extra}
        status, out, _ = self.api("POST", "/device/code", body)
        self.assertEqual(status, 200, out)
        return out

    # ------------------------------------------------------------ the person's side (a browser)

    def page(self, method="GET", query="", form=None, cookie=None):
        """cookie=None: signed in as the person; cookie="": no cookie at all."""
        cookie = self.person_cookie if cookie is None else cookie
        headers = {"cookie": cookie} if cookie else {}
        body = None
        if form is not None:
            body = urlencode(form).encode()
            headers["content-type"] = "application/x-www-form-urlencoded"
        status, h, payload = self.rig.request(method, "/device" + query, body, headers)
        return status, payload.decode("utf-8", "replace"), h

    def csrf(self, code):
        status, text, _ = self.page(query="?code=" + code)
        self.assertEqual(status, 200, text)
        return re.search(r"name=csrf value='([0-9a-f]+)'", text).group(1)

    def approve(self, code, owner="personal", decision="approve"):
        return self.page("POST", form={"code": code, "csrf": self.csrf(code), "owner": owner, "decision": decision})

    def enrol(self, owner="personal", **extra):
        asked = self.ask(**extra)
        status, text, _ = self.approve(asked["user_code"], owner)
        self.assertEqual(status, 200, text)
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual(status, 200, out)
        return out


class EnrolmentTests(DeviceBase):
    def test_the_whole_flow_gives_the_device_a_key_once(self):
        asked = self.ask()
        self.assertRegex(asked["user_code"], r"^[BCDFGHJKMNPQRSTVWXZ2-9]{4}-[BCDFGHJKMNPQRSTVWXZ2-9]{4}$")
        self.assertEqual(asked["verification_uri"], "https://ai.example.test/device")
        self.assertIn(asked["user_code"], asked["verification_uri_complete"])
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual((status, out["code"]), (400, "authorization_pending"))
        self.assertEqual(self.approve(asked["user_code"])[0], 200)
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual(status, 200)
        self.assertTrue(out["key"].startswith("sgw_"))
        self.assertEqual((out["person"]["name"], out["owner_kind"]), ("Nansubuga Grace", "personal"))
        # the key is stored hashed, labelled with the device, and the device row sits beside it
        key = self.rig.gw.db.one("SELECT * FROM keys WHERE id = ?", (out["key_id"],))
        self.assertEqual((key["label"], key["created_by"], key["person_id"]), ("Grace's laptop", "device enrolment", self.rig.person_id))
        self.assertNotIn(out["key"], json.dumps(key, default=str))
        device = self.rig.gw.db.one("SELECT * FROM devices WHERE key_id = ?", (out["key_id"],))
        self.assertEqual((device["os"], device["arch"], device["app_version"], device["owner_kind"]), ("windows", "x86_64", "0.1.0", "personal"))
        # it can be collected only once
        status, again, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual((status, again["code"]), (400, "invalid_grant"))
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM keys WHERE created_by = 'device enrolment'"), 1)
        actions = [r["action"] for r in self.rig.gw.db.q("SELECT action FROM audit")]
        self.assertIn("approved a device sign-in", actions)
        self.assertIn("enrolled a device", actions)

    def test_the_key_works_like_any_other_gateway_key(self):
        out = self.enrol()
        status, _, _ = self.rig.anthropic({"model": "claude-test", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}, key=out["key"])
        self.assertEqual(status, 200)
        last = self.rig.gw.db.one("SELECT person_id, key_id FROM requests ORDER BY id DESC LIMIT 1")
        self.assertEqual((last["person_id"], last["key_id"]), (self.rig.person_id, out["key_id"]))

    def test_the_company_owned_choice_is_recorded(self):
        out = self.enrol(owner="company")
        self.assertEqual(out["owner_kind"], "company")
        self.assertEqual(self.rig.gw.db.scalar("SELECT owner_kind FROM devices WHERE key_id = ?", (out["key_id"],)), "company")

    def test_cancelling_refuses_the_device(self):
        asked = self.ask()
        self.assertEqual(self.approve(asked["user_code"], decision="deny")[0], 200)
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual((status, out["code"]), (400, "access_denied"))
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM devices"), 0)

    def test_an_expired_code_and_unknown_codes_are_refused(self):
        asked = self.ask()
        self.rig.gw.db.x("UPDATE device_codes SET expires = ?", (time.time() - 1,))
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual((status, out["code"]), (400, "expired_token"))
        self.assertIn("It was already used or has expired", self.page(query="?code=" + asked["user_code"])[1])
        for bad in ("", "short", "x" * 43):
            status, out, _ = self.api("POST", "/device/token", {"device_code": bad})
            self.assertEqual((status, out["code"]), (400, "invalid_grant"))

    def test_polling_too_fast_is_told_to_slow_down(self):
        asked = self.ask()
        self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual(out["code"], "slow_down")

    def test_guessing_device_codes_is_throttled(self):
        for _ in range(8):
            self.api("POST", "/device/token", {"device_code": "x" * 43})
        status, out, _ = self.api("POST", "/device/token", {"device_code": "x" * 43})
        self.assertEqual((status, out["code"]), (429, "slow_down"))

    def test_asking_for_codes_is_limited_per_address(self):
        for _ in range(enroll.CODES_PER_HOUR):
            self.ask()
        status, out, _ = self.api("POST", "/device/code", {"name": "x"})
        self.assertEqual((status, out["code"]), (429, "slow_down"))

    def test_a_device_can_not_start_without_the_app_header(self):
        status, h, payload = self.rig.request("POST", "/api/device/code", {"name": "x"})
        self.assertEqual(status, 403)

    def test_the_stranger_cannot_approve(self):
        asked = self.ask()
        status, text, _ = self.page(query="?code=" + asked["user_code"], cookie="")
        self.assertEqual(status, 401)
        self.assertIn("Sign in first", text)
        status, text, _ = self.page("POST", form={"code": asked["user_code"], "csrf": "0" * 32, "decision": "approve"}, cookie="")
        self.assertEqual(status, 401)
        self.assertEqual(self.rig.gw.db.scalar("SELECT status FROM device_codes"), "pending")

    def test_approval_needs_the_page_s_own_csrf_token(self):
        asked = self.ask()
        code = asked["user_code"]
        for token in ("", "0" * 32, "not-a-token"):
            status, text, _ = self.page("POST", form={"code": code, "csrf": token, "decision": "approve"})
            self.assertEqual(status, 400, token)
        # a token made for another code (or another person's session) is no good either
        other = self.ask()
        stolen = self.csrf(other["user_code"])
        self.assertEqual(self.page("POST", form={"code": code, "csrf": stolen, "decision": "approve"})[0], 400)
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM device_codes WHERE status = 'approved'"), 0)

    def test_the_approval_page_says_what_is_asking_and_escapes_it(self):
        asked = self.ask(name="<script>alert(1)</script>")
        status, text, headers = self.page(query="?code=" + quote(asked["user_code"].lower().replace("-", " ")))
        self.assertEqual(status, 200)
        self.assertNotIn("<script>alert", text)
        self.assertIn("&lt;script&gt;", text)
        for expected in ("windows", "x86_64", "0.1.0", "Only approve this if you started it yourself", "never reads your files"):
            self.assertIn(expected, text)
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
        self.assertIn("no-store", headers["cache-control"])

    def test_the_ten_device_limit_and_the_admin_switch_apply(self):
        db = self.rig.gw.db
        db.x("UPDATE keys SET revoked = NULL")
        for i in range(9):
            db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,?,?,?,?,?)",
                 (f"{i:012x}", self.rig.person_id, f"old {i}", "x", "h", time.time()))
        asked = self.ask()
        self.assertEqual(self.approve(asked["user_code"])[0], 400)  # that is ten with the first key
        db.x("DELETE FROM keys WHERE label LIKE 'old %'")
        db.set_setting("staff_self_keys", "0")
        self.assertEqual(self.approve(asked["user_code"])[0], 403)
        db.set_setting("staff_self_keys", "1")
        self.assertEqual(self.approve(asked["user_code"])[0], 200)

    def test_a_person_paused_after_approving_gets_no_key(self):
        asked = self.ask()
        self.approve(asked["user_code"])
        self.rig.gw.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (self.rig.person_id,))
        status, out, _ = self.api("POST", "/device/token", {"device_code": asked["device_code"]})
        self.assertEqual((status, out["code"]), (400, "access_denied"))
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM devices"), 0)


class ManifestTests(DeviceBase):
    def setUp(self):
        super().setUp()
        self.device = self.enrol()
        self.key = self.device["key"]

    def manifest(self, key=None):
        return self.api("GET", "/device/manifest", key=key or self.key)

    def ids(self, manifest):
        return [p["id"] for p in manifest["packages"]]

    def test_it_offers_exactly_what_the_person_is_assigned(self):
        status, m, _ = self.manifest()
        self.assertEqual(status, 200)
        self.assertEqual(self.ids(m), ["claude-code", "codex", "access-gate"])
        self.assertEqual((m["person"]["name"], m["server"]), ("Nansubuga Grace", "https://ai.example.test"))
        self.assertEqual(m["client"], {"latest": enroll.CLIENT_LATEST, "minimum": enroll.CLIENT_MINIMUM})
        self.assertIn("never reads your files", m["recording"])
        self.assertNotIn(self.key, json.dumps(m))  # the key is never in what it is told
        self.rig.gw.db.x("DELETE FROM entitlements WHERE tool_id = 'codex'")
        self.assertEqual(self.ids(self.manifest()[1]), ["claude-code", "access-gate"])  # taken away: gone at the next sync

    def test_coding_agents_point_at_the_gateway_and_obey_the_kind_of_device(self):
        agents = {p["id"]: p["install"] for p in self.manifest()[1]["packages"] if p["kind"] == "agent"}
        self.assertEqual(agents["claude-code"]["base_url"], "https://ai.example.test/anthropic")
        self.assertEqual(agents["codex"]["base_url"], "https://ai.example.test/openai/v1")
        self.assertEqual((agents["claude-code"]["mode"], agents["codex"]["mode"]), ("scoped", "scoped"))  # a personal device
        self.assertEqual(agents["codex"]["env_key"], "SWANGZ_AI_KEY")
        company = self.enrol(owner="company")
        agents = {p["id"]: p["install"] for p in self.manifest(company["key"])[1]["packages"] if p["kind"] == "agent"}
        self.assertEqual((agents["claude-code"]["mode"], agents["codex"]["mode"]), ("managed", "managed"))

    def test_a_tool_with_its_company_subscription_cancelled_is_not_offered(self):
        db = self.rig.gw.db
        db.x("UPDATE tools SET archived = 1 WHERE id = 'claude-code'")
        self.assertNotIn("claude-code", self.ids(self.manifest()[1]))

    def test_apps_are_the_website_tools_the_person_may_open(self):
        db = self.rig.gw.db
        db.x("INSERT INTO subscriptions(tool_id, state, updated) VALUES('canva', 'active', ?) ON CONFLICT(tool_id) DO UPDATE SET state = 'active'", (time.time(),))
        db.x("INSERT OR IGNORE INTO entitlements(tool_id, person_id, granted) VALUES('canva', ?, ?)", (self.rig.person_id, time.time()))
        apps = {a["id"]: a for a in self.manifest()[1]["apps"]}
        self.assertIn("canva", apps)
        self.assertEqual(apps["canva"]["open"], "https://ai.example.test/go/canva")
        self.assertNotIn("chatgpt", apps)  # not assigned
        self.assertFalse(apps["canva"]["company_browser"])

    def test_the_browser_access_gate_comes_with_a_checksum_the_download_matches(self):
        gate = next(p for p in self.manifest()[1]["packages"] if p["id"] == "access-gate")["install"]
        status, data, headers = self.api("GET", "/device/extension", key=self.key)
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/zip")
        self.assertEqual((hashlib.sha256(data).hexdigest(), len(data)), (gate["sha256"], gate["size"]))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn("manifest.json", z.namelist())
            self.assertFalse([n for n in z.namelist() if n.endswith(".md")])
        again = self.api("GET", "/device/extension", key=self.key)[1]
        self.assertEqual(again, data)  # the same bytes every time

    def test_wrong_missing_revoked_and_paused_keys_are_refused(self):
        self.assertEqual(self.api("GET", "/device/manifest")[1]["code"], "device_unknown")
        self.assertEqual(self.api("GET", "/device/manifest", key="sgw_aaaaaaaaaaaa_bad")[0], 401)
        self.assertEqual(self.api("GET", "/device/manifest", key=self.rig.key)[1]["code"], "not_enrolled")  # a hand-made key
        db = self.rig.gw.db
        db.set_setting("paused", "1")
        self.assertEqual(self.manifest()[1]["code"], "paused")
        db.set_setting("paused", "0")
        db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (self.rig.person_id,))
        self.assertEqual(self.manifest()[1]["code"], "person_paused")
        db.x("UPDATE people SET status = 'active' WHERE id = ?", (self.rig.person_id,))
        db.x("UPDATE people SET access_until = ? WHERE id = ?", (time.time() - 5, self.rig.person_id))
        self.assertEqual(self.manifest()[1]["code"], "access_ended")
        db.x("UPDATE people SET access_until = NULL WHERE id = ?", (self.rig.person_id,))
        self.assertEqual(self.manifest()[0], 200)

    def test_disconnecting_the_device_from_the_console_or_the_staff_app_ends_it(self):
        status, out = self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")
        self.assertEqual(status, 200, out)
        status, out, _ = self.manifest()
        self.assertEqual((status, out["code"]), (401, "device_revoked"))
        second = self.enrol()
        self.assertEqual(self.staff("POST", f"/keys/{second['key_id']}/revoke", cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.manifest(second["key"])[1]["code"], "device_revoked")

    def test_signing_out_from_the_app_revokes_its_key(self):
        self.assertEqual(self.api("POST", "/device/signout", key=self.key)[0], 200)
        self.assertEqual(self.manifest()[1]["code"], "device_revoked")
        self.assertIn("signed a device out of Swangz", [r["action"] for r in self.rig.gw.db.q("SELECT action FROM audit")])


class HeartbeatTests(DeviceBase):
    def test_a_check_in_updates_the_device_and_the_control_room_sees_it(self):
        device = self.enrol()
        body = {"os": "Windows 11", "arch": "AMD64", "app_version": "0.1.1",
                "packages": [{"id": "claude-code", "version": "1"}, {"id": "bad id", "version": "1"}, "junk"]}
        status, out, _ = self.api("POST", "/device/heartbeat", body, key=device["key"])
        self.assertEqual((status, out["ok"], out["latest_client"]), (200, True, enroll.CLIENT_LATEST))
        row = self.rig.gw.db.one("SELECT * FROM devices WHERE key_id = ?", (device["key_id"],))
        self.assertEqual((row["app_version"], row["arch"]), ("0.1.1", "AMD64"))
        self.assertEqual(json.loads(row["packages_json"]), [{"id": "claude-code", "version": "1"}])
        self.assertIsNotNone(self.rig.gw.db.scalar("SELECT last_used FROM keys WHERE id = ?", (device["key_id"],)))
        status, listing = self.rig.api("GET", "/devices")
        mine = next(d for d in listing["items"] if d["id"] == device["key_id"])
        self.assertEqual((mine["app_version"], mine["owner_kind"], mine["packages"]), ("0.1.1", "personal", [{"id": "claude-code", "version": "1"}]))
        self.assertEqual(mine["label"], "Grace's laptop")


class PackageTests(DeviceBase):
    def setUp(self):
        super().setUp()
        self.device = self.enrol()
        self.key = self.device["key"]
        self.zip1 = make_zip(os.path.join(self.tmp, "t1.zip"), {"README.md": "v1", "prompts/a.txt": "hello"})
        self.gw = self.rig.gw

    def publish(self, version="1.0.0", path=None, **kw):
        kw.setdefault("audience", {"people": [self.rig.person_id]})
        return enroll.publish(self.gw, path or self.zip1, "brand-prompts", version, "Brand prompts", description="Shared prompts", **kw)

    def offered(self, key=None):
        m = self.api("GET", "/device/manifest", key=key or self.key)[1]
        return {p["id"]: p for p in m["packages"]}

    def test_a_published_package_reaches_the_people_it_was_granted_to_only(self):
        result = self.publish()
        offered = self.offered()["brand-prompts"]
        self.assertEqual((offered["version"], offered["kind"], offered["install"]["sha256"]), ("1.0.0", "tool", result["sha256"]))
        status, data, headers = self.api("GET", f"/device/packages/brand-prompts/1.0.0", key=self.key)
        self.assertEqual((status, hashlib.sha256(data).hexdigest(), headers["x-swangz-sha256"]), (200, result["sha256"], result["sha256"]))
        # somebody else, not granted
        other = self.gw.db.x("INSERT INTO people(name, email, department, created) VALUES(?,?,?,?)", ("Okello Brian", "brian@swangzavenue.com", "Finance", time.time())).lastrowid
        okey = self.add_enrolled(other)
        self.assertNotIn("brand-prompts", self.offered(okey))
        self.assertEqual(self.api("GET", "/device/packages/brand-prompts/1.0.0", key=okey)[0], 404)

    def add_enrolled(self, person_id):
        from gateway import security

        key_id, full, secret_hash, hint = security.new_key()
        self.gw.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,?,?,?,?,?)", (key_id, person_id, "x", secret_hash, hint, time.time()))
        self.gw.db.x("INSERT INTO devices(key_id, person_id, name, os, owner_kind, enrolled) VALUES(?,?,?,?,?,?)", (key_id, person_id, "x", "linux", "personal", time.time()))
        return full

    def test_grants_by_department_and_for_everyone(self):
        self.publish(audience={"departments": ["Creative"]})
        self.assertIn("brand-prompts", self.offered())
        okey = self.add_enrolled(self.gw.db.x("INSERT INTO people(name, email, department, created) VALUES(?,?,?,?)", ("Okello Brian", "brian@swangzavenue.com", "Finance", time.time())).lastrowid)
        self.assertNotIn("brand-prompts", self.offered(okey))
        self.gw.db.x("INSERT INTO package_grants(package_id, department, granted) VALUES('brand-prompts', '*', ?)", (time.time(),))
        self.assertIn("brand-prompts", self.offered(okey))

    def test_a_newer_version_replaces_the_old_and_a_withdrawn_one_disappears(self):
        self.publish("1.0.0")
        time.sleep(0.01)
        self.publish("1.1.0", path=make_zip(os.path.join(self.tmp, "t2.zip"), {"README.md": "v2"}), audience=None)
        self.assertEqual(self.offered()["brand-prompts"]["version"], "1.1.0")
        status, out = self.rig.api("POST", "/packages/brand-prompts/1.1.0/withdraw", {"reason": "bad file"})
        self.assertEqual(status, 200, out)
        self.assertEqual(self.offered()["brand-prompts"]["version"], "1.0.0")
        self.assertEqual(self.api("GET", "/device/packages/brand-prompts/1.1.0", key=self.key)[0], 404)

    def test_platforms_are_respected(self):
        self.publish(platforms="macos,linux")
        self.assertNotIn("brand-prompts", self.offered())  # this device is Windows
        self.gw.db.x("UPDATE devices SET os = 'macos'")
        self.assertIn("brand-prompts", self.offered())

    def test_unsafe_and_invalid_packages_are_refused_at_publish(self):
        bad = make_zip(os.path.join(self.tmp, "evil.zip"), {"../../etc/passwd": "x"})
        with self.assertRaisesRegex(enroll.PackageError, "unsafe path"):
            self.publish(path=bad)
        absolute = make_zip(os.path.join(self.tmp, "abs.zip"), {"/etc/cron.d/x": "x"})
        with self.assertRaisesRegex(enroll.PackageError, "unsafe path"):
            self.publish(path=absolute)
        notzip = os.path.join(self.tmp, "n.zip")
        with open(notzip, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaisesRegex(enroll.PackageError, "not a zip"):
            self.publish(path=notzip)
        for pid, version in (("Bad_ID", "1"), ("x", "1"), ("ok-id", "../1"), ("ok-id", "")):
            with self.assertRaises(enroll.PackageError):
                enroll.publish(self.gw, self.zip1, pid, version, "n")
        with self.assertRaises(enroll.PackageError):
            self.publish(platforms="beos")
        self.publish()
        with self.assertRaisesRegex(enroll.PackageError, "already published"):
            self.publish()
        self.assertEqual(self.gw.db.scalar("SELECT COUNT(*) FROM packages"), 1)

    def test_a_damaged_file_on_the_server_is_never_sent(self):
        self.publish()
        with open(enroll.package_path(self.gw, "brand-prompts", "1.0.0"), "ab") as f:
            f.write(b"tampered")
        status, out, _ = self.api("GET", "/device/packages/brand-prompts/1.0.0", key=self.key)
        self.assertEqual(status, 500)
        self.assertIn("damaged", out["error"])

    def test_admin_routes_need_the_govern_area(self):
        self.publish()
        self.assertEqual(self.rig.api("GET", "/packages", who="viewer")[0], 200)
        body = {"department": "Finance"}
        self.assertEqual(self.rig.api("POST", "/packages/brand-prompts/grants", body, who="viewer")[0], 403)
        self.assertEqual(self.rig.api("POST", "/packages/brand-prompts/1.0.0/withdraw", {}, who="viewer")[0], 403)
        self.assertEqual(self.rig.api("POST", "/packages/brand-prompts/grants", body)[0], 200)
        self.assertEqual(self.rig.api("POST", "/packages/brand-prompts/grants", {})[0], 400)
        self.assertEqual(self.rig.api("POST", "/packages/nope/grants", body)[0], 404)
        listing = self.rig.api("GET", "/packages")[1]
        self.assertIn({"package_id": "brand-prompts", "person_id": None, "department": "Finance", "person": None}, listing["grants"])
        self.assertEqual(self.rig.api("DELETE", "/packages/brand-prompts/grants", body)[1]["removed"], 1)


class MigrationTests(unittest.TestCase):
    def test_v21_adds_the_device_tables_and_nothing_else_changes(self):
        self.assertGreaterEqual(len(SCHEMA), 21)
        from gateway.db import DB

        db = DB(":memory:")
        names = {r["name"] for r in db.q("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"device_codes", "devices", "packages", "package_grants", "keys", "people"} <= names)


if __name__ == "__main__":
    unittest.main()
