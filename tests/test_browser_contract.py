"""Personal browser manifest contract v1: inert, negotiated, server-built from authenticated rows only."""

import ast
import inspect
import json
import re
import time
import unittest

from gateway import admin, enroll, staff
from gateway.db import SCHEMA

from .test_devices import DeviceBase

PATH = "/device/manifest"
ID_PERSON = re.compile(r"[1-9][0-9]*")
ID_DEVICE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class Base(DeviceBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db
        self.device = self.enrol()
        self.key = self.device["key"]

    def get(self, query="?browser_contract=1", key=None):
        status, out, _ = self.api("GET", PATH + query, key=key or self.key)
        return status, out

    def block(self, query="?browser_contract=1", key=None):
        status, out = self.get(query, key)
        self.assertEqual(status, 200, out)
        return out.get("browser")

    def second_person_device(self):
        rig = self.rig
        status, out = rig.api("POST", "/people", {"name": "Kato Brian", "monthly_budget": 40})
        self.assertEqual(status, 200, out)
        pid = out["id"] if "id" in out else out["person"]["id"]
        rig.api("PATCH", f"/people/{pid}", {"email": "kato@swangzavenue.com"})
        _, inv = rig.api("POST", f"/people/{pid}/invite")
        self.cookie = None
        status, _ = self.staff("POST", "/welcome", {"token": inv["link"].rsplit("/", 1)[1], "password": "another-good-pass-2"})
        self.assertEqual(status, 200)
        grace_cookie, self.person_cookie = self.person_cookie, self.cookie
        try:
            dev = self.enrol(name="Kato's laptop")
        finally:
            self.person_cookie = grace_cookie
        return pid, dev


class NegotiationTests(Base):
    def test_exactly_one_browser_contract_1_adds_the_block(self):
        out = self.get()[1]
        self.assertEqual(out["browser"], {"contract": 1, "person_id": str(self.rig.person_id),
                                          "device_id": self.device["device_id"], "profiles": [{"kind": "personal"}]})

    def test_anything_else_omits_the_block_and_the_old_manifest_is_unchanged(self):
        plain = self.get("")[1]
        self.assertNotIn("browser", plain)
        for q in ("?browser_contract=2", "?browser_contract=01", "?browser_contract=true", "?browser_contract=",
                  "?browser_contract", "?browser_contract=1&browser_contract=1", "?browser_contract=1&browser_contract=2",
                  "?browser_contract=2&browser_contract=1", "?Browser_Contract=1", "?browser_contract=1%20", "?browser_contract=%31x"):
            status, out = self.get(q)
            self.assertEqual(status, 200, q)
            self.assertNotIn("browser", out, q)
            self.assertEqual({k: v for k, v in out.items() if k != "generated"}, {k: v for k, v in plain.items() if k != "generated"}, q)

    def test_negotiating_changes_nothing_else_in_the_manifest(self):
        plain, neg = self.get("")[1], self.get()[1]
        neg.pop("browser")
        for m in (plain, neg):
            m.pop("generated")
        self.assertEqual(plain, neg)


class BlockShapeTests(Base):
    def test_ids_match_the_patterns_and_the_block_carries_nothing_else(self):
        b = self.block()
        self.assertEqual(set(b), {"contract", "person_id", "device_id", "profiles"})
        self.assertIs(type(b["contract"]), int)
        self.assertRegex(b["person_id"], ID_PERSON)
        self.assertRegex(b["device_id"], ID_DEVICE)
        self.assertEqual(b["profiles"], [{"kind": "personal"}])

    def test_no_secret_email_name_or_hint_is_in_the_block(self):
        text = json.dumps(self.block())
        row = self.db.one("SELECT * FROM people WHERE id = ?", (self.rig.person_id,))
        key = self.db.one("SELECT * FROM keys WHERE id = ?", (self.device["key_id"],))
        for forbidden in (row["email"], row["name"], key["hint"], key["secret_hash"], self.key, self.key.split("_", 2)[2], "grace", "@"):
            self.assertNotIn(forbidden.lower(), text.lower())

    def test_request_supplied_identity_is_ignored(self):
        other = "9999"
        for q in (f"?browser_contract=1&person_id={other}&device_id=evil", f"?browser_contract=1&person=7&device=../x&profiles=team",
                  f"?browser_contract=1&kind=seat&email=x@y.z"):
            self.assertEqual(self.block(q), {"contract": 1, "person_id": str(self.rig.person_id),
                                             "device_id": self.device["device_id"], "profiles": [{"kind": "personal"}]})
        status, out, _ = self.api("GET", PATH + "?browser_contract=1", key=self.key)
        self.assertEqual(status, 200)

    def test_two_people_get_their_own_ids(self):
        pid, dev = self.second_person_device()
        a, b = self.block(), self.block(key=dev["key"])
        self.assertEqual((a["person_id"], b["person_id"]), (str(self.rig.person_id), str(pid)))
        self.assertEqual((a["device_id"], b["device_id"]), (self.device["device_id"], dev["device_id"]))
        self.assertNotEqual(a["device_id"], b["device_id"])
        self.assertNotIn(dev["device_id"], json.dumps(a))
        self.assertNotIn(self.device["device_id"], json.dumps(b))

    def test_two_devices_of_one_person_have_distinct_device_ids(self):
        second = self.enrol(name="Grace's phone")
        a, b = self.block(), self.block(key=second["key"])
        self.assertEqual(a["person_id"], b["person_id"])
        self.assertNotEqual(a["device_id"], b["device_id"])
        self.assertEqual(b["device_id"], second["device_id"])


class RotationTests(Base):
    def test_device_id_is_stable_across_rotation_and_the_old_key_is_refused(self):
        before = self.block()
        status, rotated, _ = self.api("POST", "/device/rotate", {}, key=self.key)
        self.assertEqual(status, 200, rotated)
        after = self.block(key=rotated["key"])  # first use confirms the rotation
        self.assertEqual(before, after)
        status, out = self.get(key=self.key)
        self.assertEqual((status, out["code"]), (401, "device_key_rotated"))
        self.assertNotIn("browser", out)
        self.assertEqual(self.block(key=rotated["key"]), before)


class RefusalTests(Base):
    def refused(self, code, status):
        got, out = self.get()
        self.assertEqual((got, out.get("code")), (status, code))
        self.assertNotIn("browser", out)
        self.assertEqual(set(out), {"error", "code"} & set(out) | (set(out) - {"browser"}))

    def test_every_refusal_code_omits_the_block(self):
        pid = self.rig.person_id
        self.assertEqual(self.get(key="sgw_aaaaaaaaaaaa_bad")[1].get("code"), "device_unknown")
        self.assertNotIn("browser", self.get(key="sgw_aaaaaaaaaaaa_bad")[1])
        status, out = self.get(key=self.rig.key)  # a hand-made key
        self.assertEqual(out["code"], "not_enrolled")
        self.assertNotIn("browser", out)
        self.db.set_setting("paused", "1")
        self.refused("paused", 403)
        self.db.set_setting("paused", "0")
        self.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (pid,))
        self.refused("person_paused", 403)
        self.db.x("UPDATE people SET status = 'active' WHERE id = ?", (pid,))
        self.db.x("UPDATE people SET access_until = ? WHERE id = ?", (time.time() - 5, pid))
        self.refused("access_ended", 403)
        self.db.x("UPDATE people SET access_until = NULL WHERE id = ?", (pid,))
        self.assertIn("browser", self.get()[1])
        self.assertEqual(self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")[0], 200)
        self.refused("device_revoked", 401)

    def test_person_paused_and_access_ended_beat_the_global_pause(self):
        pid = self.rig.person_id
        self.db.set_setting("paused", "1")
        self.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (pid,))
        self.refused("person_paused", 403)
        self.db.x("UPDATE people SET status = 'active', access_until = ? WHERE id = ?", (time.time() - 5, pid))
        self.refused("access_ended", 403)
        self.db.x("UPDATE people SET access_until = NULL WHERE id = ?", (pid,))
        self.refused("paused", 403)

    def test_paused_and_ended_together_say_person_paused(self):
        pid = self.rig.person_id
        self.db.x("UPDATE people SET status = 'suspended', access_until = ? WHERE id = ?", (time.time() - 5, pid))
        self.refused("person_paused", 403)

    def test_the_refusals_are_the_same_with_and_without_negotiation(self):
        self.db.set_setting("paused", "1")
        self.assertEqual(self.get("")[1]["code"], self.get()[1]["code"])
        self.assertEqual(self.get("")[0], self.get()[0])

    def test_not_enrolled_after_the_device_row_is_gone(self):
        self.db.x("DELETE FROM devices WHERE device_id = ?", (self.device["device_id"],))
        self.refused("not_enrolled", 403)


class _H:
    """Just enough of a request for the block builder: its path."""
    def __init__(self, path):
        self.path = path


class EmailRuleTests(Base):
    def test_over_http_a_disallowed_email_is_refused_by_existing_auth_and_gets_no_block(self):
        # Existing behaviour, deliberately not changed here: gw.identify refuses a key whose person's email the account
        # rule no longer allows, so the device is 'unknown' before any manifest is built.
        self.assertEqual(self.block()["profiles"], [{"kind": "personal"}])
        for email in ("grace@example.com", "", "not an email", "x@swangzavenue.com.evil.io"):
            self.db.x("UPDATE people SET email = ? WHERE id = ?", (email, self.rig.person_id))
            for q in ("?browser_contract=1", ""):
                status, out = self.get(q)
                self.assertEqual((status, out.get("code")), (401, "device_unknown"), (email, q))
                self.assertNotIn("browser", out)

    def test_the_builder_itself_gives_empty_profiles_for_a_disallowed_email_and_only_the_ids(self):
        gw = self.rig.gw
        device = self.db.one("SELECT * FROM devices WHERE device_id = ?", (self.device["device_id"],))
        person = self.db.one("SELECT * FROM people WHERE id = ?", (self.rig.person_id,))
        want = {"contract": 1, "person_id": str(self.rig.person_id), "device_id": self.device["device_id"]}
        self.assertEqual(enroll._browser_block(gw, _H("/api/device/manifest?browser_contract=1"), person, device),
                         {**want, "profiles": [{"kind": "personal"}]})
        for email in ("grace@example.com", "", "not an email", "x@swangzavenue.com.evil.io", None):
            blocked = enroll._browser_block(gw, _H("/api/device/manifest?browser_contract=1"), {**person, "email": email}, device)
            self.assertEqual(blocked, {**want, "profiles": []}, email)
            self.assertIsNone(enroll._browser_block(gw, _H("/api/device/manifest"), {**person, "email": email}, device))

    def test_ids_that_break_the_patterns_are_never_emitted(self):
        gw = self.rig.gw
        device = self.db.one("SELECT * FROM devices WHERE device_id = ?", (self.device["device_id"],))
        person = self.db.one("SELECT * FROM people WHERE id = ?", (self.rig.person_id,))
        h = _H("/x?browser_contract=1")
        for pid in (0, -3, "01", "7 ", "x"):
            self.assertIsNone(enroll._browser_block(gw, h, {**person, "id": pid}, device), pid)
        for did in ("", "a" * 65, "has space", "../x", "a.b", "é"):
            self.assertIsNone(enroll._browser_block(gw, h, person, {**device, "device_id": did}), did)
        self.assertIsNotNone(enroll._browser_block(gw, h, person, {**device, "device_id": "a" * 64}))


class SourceTests(Base):
    def test_no_registry_or_seat_authority_in_the_block_or_its_source(self):
        src = ""
        for fn in (enroll._browser_block, enroll._browser_negotiated):
            tree = ast.parse(inspect.getsource(fn))
            node = tree.body[0]
            node.body = [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]  # no docstring
            src += ast.unparse(node)
        for word in ("provider_account", "registry", "seat", "entitle",):
            self.assertNotIn(word, src.lower())
        self.assertEqual({p["kind"] for p in self.block()["profiles"]}, {"personal"})

    def test_adding_a_provider_account_or_seat_tool_changes_nothing(self):
        before = self.block()
        self.db.x("UPDATE tools SET signin = 'seat' WHERE id IN (SELECT id FROM tools LIMIT 3)")
        self.assertEqual(self.block(), before)

    def test_no_new_route_and_no_schema_change(self):
        routes = sorted((m, rx.pattern) for m, rx, fn, *_ in staff.ROUTES + admin.ROUTES if fn.__module__ == "gateway.enroll")
        self.assertEqual(len(routes), 12)
        self.assertEqual([r for r in routes if r[1].startswith("/device/")], [
            ("GET", "/device/extension"), ("GET", "/device/manifest"),
            ("GET", "/device/packages/(?P<pid>[a-z0-9-]{2,60})/(?P<version>[0-9A-Za-z._-]{1,32})"),
            ("POST", "/device/code"), ("POST", "/device/heartbeat"), ("POST", "/device/rotate"),
            ("POST", "/device/signout"), ("POST", "/device/token")])
        self.assertEqual(len(SCHEMA), 25)  # v23 session kinds, v24-v25 provider registry; the browser contract itself adds no migration


class NegotiationSemanticsTests(Base):
    """The query is read like any URL query: percent-escapes decode first, then the value must be exactly `1`.
    `+` is a space in a query, so it never makes a `1`. Nothing here changes who is refused or what a refusal says."""

    def test_percent_encoded_one_is_one_and_encoded_name_is_the_name(self):
        for q in ("?browser_contract=%31", "?browser%5Fcontract=1", "?browser%5fcontract=%31"):
            self.assertEqual((self.block(q) or {}).get("contract"), 1, q)

    def test_plus_spaces_nul_and_odd_escapes_never_negotiate(self):
        plain = {k: v for k, v in self.get("")[1].items() if k != "generated"}
        for q in ("?browser_contract=1+", "?browser_contract=+1", "?browser_contract=%2B1", "?browser_contract=1%2B",
                  "?browser_contract=%201", "?browser_contract=1%00", "?browser_contract=1%0A", "?browser_contract=%0D1",
                  "?browser_contract=1%", "?browser_contract=%3", "?browser_contract=1;x", "?browser_contract=1?x",
                  "?browser_contract=%EF%BC%91", "?+browser_contract=1", "?browser_contract+=1"):
            status, out = self.get(q)
            self.assertEqual(status, 200, q)
            self.assertNotIn("browser", out, q)
            self.assertEqual({k: v for k, v in out.items() if k != "generated"}, plain, q)

    def test_the_same_name_spelled_two_ways_is_repeated_and_does_not_negotiate(self):
        for q in ("?browser_contract=1&browser%5Fcontract=1", "?browser%5Fcontract=%31&browser_contract=1"):
            status, out = self.get(q)
            self.assertEqual(status, 200, q)
            self.assertNotIn("browser", out, q)

    def test_encoded_forms_keep_the_refusals_and_ignore_extra_identity(self):
        status, out = self.get("?browser_contract=%31&person_id=999&device_id=x")
        self.assertEqual((status, out["browser"]["person_id"], out["browser"]["device_id"]),
                         (200, str(self.rig.person_id), self.device["device_id"]))
        self.db.set_setting("paused", "1")
        for q in ("?browser_contract=%31", "?browser_contract=1+"):
            status, out = self.get(q)
            self.assertEqual((status, out["code"]), (403, "paused"), q)
            self.assertNotIn("browser", out, q)

    def test_a_company_owned_device_keeps_its_owner_kind_and_gets_the_same_personal_block(self):
        """`personal` means bound to the person, not to a personal device: owner_kind is reported as it is and the
        block does not depend on it."""
        company = self.enrol(owner="company", name="Office desktop")
        status, out = self.get(key=company["key"])
        self.assertEqual(status, 200, out)
        self.assertEqual(out["device"]["owner_kind"], "company")
        self.assertEqual(out["browser"], {"contract": 1, "person_id": str(self.rig.person_id),
                                          "device_id": company["device_id"], "profiles": [{"kind": "personal"}]})
        plain = self.get("", key=company["key"])[1]
        self.assertEqual(plain["device"]["owner_kind"], "company")
        self.assertNotIn("browser", plain)
        mine = self.block()  # the personal device is unaffected and has its own device id
        self.assertEqual(mine["profiles"], out["browser"]["profiles"])
        self.assertNotEqual(mine["device_id"], out["browser"]["device_id"])


if __name__ == "__main__":
    unittest.main()
