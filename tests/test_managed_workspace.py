"""Managed workspace, server side: contract 2 (W2), suspend / retire / reactivate (W4), the reported policy (W5).
docs/MANAGED-WORKSPACE.md. Everything here can only take access away; no provider credential is involved."""

import json
import re
import time
import unittest

from gateway import managed, security

from .test_devices import DeviceBase

MANIFEST = "/device/manifest"
SHA = "a" * 64
OTHER_SHA = "b" * 64


class Base(DeviceBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db
        self.device = self.enrol()
        self.key, self.did = self.device["key"], self.device["device_id"]

    def manifest(self, query="?browser_contract=2", key=None):
        status, out, _ = self.api("GET", MANIFEST + query, key=key or self.key)
        self.assertEqual(status, 200, out)
        return out

    def block(self, query="?browser_contract=2"):
        return self.manifest(query).get("browser")

    def beat(self, body=None, key=None):
        status, out, _ = self.api("POST", "/device/heartbeat", body or {}, key=key or self.key)
        return status, out

    def workspace(self, action, did=None, who="owner"):
        return self.rig.api("POST", f"/devices/{did or self.did}/workspace", {"action": action}, who=who)

    def state(self):
        return self.db.one("SELECT workspace_state AS s, workspace_generation AS g FROM devices WHERE device_id = ?", (self.did,))

    def enable_canva(self):
        self.rig.api("PUT", "/subscriptions/canva", {"state": "active", "monthly_cost": 30, "seats": 5})
        self.assertEqual(self.rig.api("POST", f"/people/{self.rig.person_id}/tools/canva")[0], 200)

    def go(self, query=""):
        status, h, payload = self.rig.request("GET", "/go/canva" + query, None, {"cookie": self.person_cookie})
        return status, h, payload.decode()


class ContractTwoTests(Base):
    def test_contract_2_carries_the_state_the_generation_and_the_policy_baseline(self):
        b = self.block()
        self.assertEqual(b, {"contract": 2, "person_id": str(self.rig.person_id), "device_id": self.did, "profiles": [{"kind": "personal"}],
                             "workspace": {"state": "active", "generation": 1}, "policy": {"sha256": None, "mode": "warn"}})

    def test_contract_1_is_byte_identical_and_so_is_a_manifest_with_no_contract(self):
        one, plain = self.manifest("?browser_contract=1"), self.manifest("")
        self.assertEqual(one["browser"], {"contract": 1, "person_id": str(self.rig.person_id), "device_id": self.did, "profiles": [{"kind": "personal"}]})
        self.assertNotIn("browser", plain)
        two = self.manifest()
        for m in (one, plain, two):
            m.pop("generated")
            m.pop("browser", None)
        self.assertEqual(one, plain)
        self.assertEqual(two, plain)  # no tool is granted here, so no `open` link differs either

    def test_only_exactly_one_value_of_1_or_2_negotiates(self):
        for q in ("?browser_contract=3", "?browser_contract=02", "?browser_contract=2.0", "?browser_contract=", "?browser_contract=2&browser_contract=2",
                  "?browser_contract=1&browser_contract=2", "?browser_contract=2&browser_contract=1", "?browser_contract=%32x", "?browser_contract=2+"):
            self.assertNotIn("browser", self.manifest(q), q)
        self.assertEqual(self.block("?browser_contract=%32")["contract"], 2)  # a percent-escaped 2 is a 2, as for 1

    def test_the_block_is_built_from_the_rows_and_settings_never_from_the_request(self):
        self.assertEqual(self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA, "managed_policy_mode": "enforce"})[0], 200)
        want = self.block()
        for q in ("&state=retired", "&generation=9", "&sha256=" + OTHER_SHA, "&mode=warn", "&workspace=suspended", "&policy_ok=1", "&d=nope"):
            self.assertEqual(self.block("?browser_contract=2" + q), want, q)
        self.assertEqual(want["policy"], {"sha256": SHA, "mode": "enforce"})

    def test_it_carries_no_email_name_key_or_secret(self):
        text = json.dumps(self.block()).lower()
        row = self.db.one("SELECT * FROM people WHERE id = ?", (self.rig.person_id,))
        key = self.db.one("SELECT * FROM keys WHERE id = ?", (self.device["key_id"],))
        for forbidden in (row["email"], row["name"], key["hint"], key["secret_hash"], self.key, "@", "password", "cookie", "token"):
            self.assertNotIn(forbidden.lower(), text)

    def test_a_person_the_account_rule_no_longer_allows_has_no_workspace(self):
        self.db.x("UPDATE people SET email = 'x@elsewhere.example' WHERE id = ?", (self.rig.person_id,))
        status, out, _ = self.api("GET", MANIFEST + "?browser_contract=2", key=self.key)
        if status == 200:  # today the key check refuses such a person first; if it ever lets them through the block says retired
            self.assertEqual((out["browser"]["profiles"], out["browser"]["workspace"]["state"]), ([], "retired"))
        else:
            self.assertEqual(status, 401)
            self.assertNotIn("browser", out)

    def test_refusals_carry_no_block(self):
        self.assertEqual(self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")[0], 200)
        status, out, _ = self.api("GET", MANIFEST + "?browser_contract=2", key=self.key)
        self.assertEqual((status, out["code"]), (401, "device_revoked"))
        self.assertNotIn("browser", out)

    def test_open_links_name_the_device_only_under_contract_2(self):
        self.enable_canva()
        two, one = self.manifest(), self.manifest("?browser_contract=1")
        self.assertEqual([a["open"] for a in two["apps"] if a["id"] == "canva"], [f"{two['server']}/go/canva?d={self.did}"])
        self.assertEqual([a["open"] for a in one["apps"] if a["id"] == "canva"], [f"{one['server']}/go/canva"])

    def test_contract_2_apps_carry_their_hosts_and_the_workspace_flag_and_contract_1_does_not(self):
        self.enable_canva()
        two, one = self.manifest(), self.manifest("?browser_contract=1")
        app = [a for a in two["apps"] if a["id"] == "canva"][0]
        self.assertTrue(app["hosts"] and all(isinstance(h, str) and "/" not in h for h in app["hosts"]), app)
        self.assertIs(app["workspace"], True)
        old = [a for a in one["apps"] if a["id"] == "canva"][0]
        self.assertEqual(set(old), {"id", "name", "category", "signin", "company_browser", "open"})


class SettingsTests(Base):
    def test_the_baseline_and_the_mode_are_validated_and_audited(self):
        for body in ({"managed_policy_mode": "block"}, {"managed_policy_mode": ""}, {"managed_policy_sha256": "abc"}, {"managed_policy_sha256": "G" * 64},
                     {"managed_policy_sha256": SHA + "0"}):
            self.assertEqual(self.rig.api("PUT", "/settings", body)[0], 400, body)
        self.assertEqual(self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA.upper(), "managed_policy_mode": "enforce"})[0], 200)
        got = self.rig.api("GET", "/settings")[1]
        self.assertEqual((got["managed_policy_sha256"], got["managed_policy_mode"]), (SHA, "enforce"))
        row = self.db.one("SELECT * FROM audit WHERE action = 'changed settings' ORDER BY id DESC LIMIT 1")
        self.assertIn("managed_policy_mode", row["target"])
        self.assertEqual(self.rig.api("PUT", "/settings", {"managed_policy_sha256": ""})[0], 200)
        self.assertIsNone(self.block()["policy"]["sha256"])

    def test_an_unreadable_stored_value_falls_back_to_warn_and_no_baseline(self):
        self.db.set_setting("managed_policy_mode", "nonsense")
        self.db.set_setting("managed_policy_sha256", "zz")
        self.assertEqual(self.block()["policy"], {"sha256": None, "mode": "warn"})

    def test_a_viewer_cannot_change_them(self):
        self.assertEqual(self.rig.api("PUT", "/settings", {"managed_policy_mode": "enforce"}, who="viewer")[0], 403)
        self.assertEqual(managed.mode(self.db), "warn")


class HeartbeatTests(Base):
    def test_an_older_app_gets_exactly_the_answer_it_always_got(self):
        status, out = self.beat()
        self.assertEqual(status, 200)
        self.assertEqual(set(out), {"ok", "latest_client", "server_time"})
        for body in ({"browser_contract": 1}, {"browser_contract": "2"}, {"browser_contract": True}, {"browser_contract": 2.0}, {"browser_contract": [2]}):
            self.assertEqual(set(self.beat(body)[1]), {"ok", "latest_client", "server_time"}, body)

    def test_contract_2_adds_the_state_and_the_baseline_and_stays_under_2_kb(self):
        self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA, "managed_policy_mode": "enforce"})
        status, out = self.beat({"browser_contract": 2})
        self.assertEqual(status, 200)
        self.assertEqual(out["workspace"], {"state": "active", "generation": 1})
        self.assertEqual(out["policy"], {"sha256": SHA, "mode": "enforce"})
        self.assertLess(len(json.dumps(out)), 2048)
        self.assertLess(len(json.dumps(out)), 400)  # in practice far less: a pinned ceiling so it cannot creep up

    def test_a_typical_request_is_under_2_kb_and_a_huge_package_list_is_still_cut_to_100(self):
        typical = {"browser_contract": 2, "os": "linux", "arch": "x86_64", "app_version": "0.1.0", "key_storage": "keychain",
                   "packages": [{"id": "access-gate", "version": "abcdef123456"}], "policy": {"ok": True, "sha256": SHA}}
        self.assertLess(len(json.dumps(typical)), 2048)
        many = dict(typical, packages=[{"id": f"pkg-{i:03d}", "version": "1"} for i in range(500)])
        self.assertEqual(self.beat(many)[0], 200)
        self.assertEqual(len(json.loads(self.db.scalar("SELECT packages_json FROM devices WHERE device_id = ?", (self.did,)))), 100)

    def test_the_answer_follows_the_state(self):
        for action, want in (("suspend", ("suspended", 1)), ("reactivate", ("active", 1)), ("retire", ("retired", 1)), ("reactivate", ("active", 2))):
            self.assertEqual(self.workspace(action)[0], 200, action)
            out = self.beat({"browser_contract": 2})[1]
            self.assertEqual((out["workspace"]["state"], out["workspace"]["generation"]), want, action)
            self.assertEqual(self.block()["workspace"], out["workspace"])


class RevocationTests(Base):
    def test_suspend_then_reactivate_keeps_the_device_key_and_the_generation(self):
        status, out = self.workspace("suspend")
        self.assertEqual((status, out["workspace"], out["changed"]), (200, {"state": "suspended", "generation": 1}, True))
        self.assertEqual(self.beat({"browser_contract": 2})[0], 200)  # the key still works: the app is told, not locked out
        self.assertEqual(self.manifest()["browser"]["workspace"]["state"], "suspended")
        out = self.workspace("reactivate")[1]
        self.assertEqual(out["workspace"], {"state": "active", "generation": 1})  # same generation: the app keeps its folder and the sign-in in it

    def test_retire_closes_it_for_good_and_a_later_reactivate_starts_a_new_generation(self):
        self.assertEqual(self.workspace("retire")[1]["workspace"], {"state": "retired", "generation": 1})
        self.assertEqual(self.workspace("suspend")[0], 409)
        self.assertEqual(self.workspace("reset")[0], 409)
        self.assertEqual(self.workspace("reactivate")[1]["workspace"], {"state": "active", "generation": 2})

    def test_reset_bumps_the_generation_when_a_seat_changes_hands(self):
        self.assertEqual(self.workspace("reset")[1]["workspace"], {"state": "active", "generation": 2})
        self.assertEqual(self.workspace("suspend")[1]["workspace"], {"state": "suspended", "generation": 2})
        self.assertEqual(self.workspace("reset")[1]["workspace"], {"state": "suspended", "generation": 3})

    def test_repeating_an_action_changes_nothing_and_is_not_audited_twice(self):
        self.workspace("suspend")
        n = self.db.scalar("SELECT COUNT(*) FROM audit WHERE action LIKE '% the workspace on a device'")
        out = self.workspace("suspend")[1]
        self.assertEqual((out["changed"], out["workspace"]["state"]), (False, "suspended"))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE action LIKE '% the workspace on a device'"), n)

    def test_every_change_is_audited_with_before_and_after(self):
        self.workspace("suspend")
        row = self.db.one("SELECT * FROM audit WHERE action = 'suspend the workspace on a device'")
        self.assertEqual(json.loads(row["before_json"]), {"state": "active", "generation": 1})
        self.assertEqual(json.loads(row["after_json"]), {"state": "suspended", "generation": 1})
        self.assertEqual(row["correlation"], f"device:{self.did}")
        who = self.db.one("SELECT workspace_changed_by AS w, workspace_changed AS t FROM devices WHERE device_id = ?", (self.did,))
        self.assertEqual(who["w"], "owner@swangzavenue.com")
        self.assertLess(time.time() - who["t"], 60)

    def test_unknown_actions_and_devices_are_refused(self):
        self.assertEqual(self.rig.api("POST", f"/devices/{self.did}/workspace", {"action": "delete"})[0], 400)
        self.assertEqual(self.rig.api("POST", f"/devices/{self.did}/workspace", {})[0], 400)
        self.assertEqual(self.workspace("suspend", did="nosuchdevice")[0], 404)
        self.assertIn(self.workspace("suspend", did="../etc")[0], (400, 404))
        self.assertEqual(self.state(), {"s": "active", "g": 1})

    def test_only_the_right_console_roles_may_change_it_and_strangers_cannot(self):
        self.assertEqual(self.workspace("suspend", who="viewer")[0], 403)
        self.assertEqual(self.rig.request("POST", f"/admin/api/devices/{self.did}/workspace", {"action": "suspend"}, {"x-gateway-admin": "1"})[0], 401)
        self.assertEqual(self.state(), {"s": "active", "g": 1})
        denied = self.db.scalar("SELECT COUNT(*) FROM audit WHERE actor = 'viewer@swangzavenue.com' AND outcome = 'denied'")
        self.assertGreaterEqual(denied, 1)

    def test_a_person_cannot_suspend_their_own_workspace_or_anyone_elses_from_the_device_api(self):
        for path in (f"/device/{self.did}/workspace", f"/devices/{self.did}/workspace"):
            status, _, _ = self.api("POST", path, {"action": "reactivate"}, key=self.key)
            self.assertIn(status, (401, 404), path)

    def test_the_workspace_state_never_touches_keys_or_api_automation(self):
        """W7: revoking the workspace alone must not revoke the device key or a gateway API key."""
        status, out = self.rig.api("POST", f"/people/{self.rig.person_id}/keys", {"label": "n8n automation", "tool_id": ""})
        self.assertEqual(status, 200, out)
        for action in ("suspend", "retire", "reactivate", "reset"):
            self.workspace(action)
            self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM keys WHERE revoked IS NULL AND person_id = ?", (self.rig.person_id,)) >= 2, True, action)
            self.assertEqual(self.beat()[0], 200, action)
            self.assertEqual(self.api("GET", MANIFEST, key=self.key)[0], 200, action)

    def test_open_is_refused_in_plain_words_for_a_suspended_or_retired_workspace_and_logged(self):
        self.enable_canva()
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)
        for action, word in (("suspend", "paused"), ("retire", "closed")):
            self.workspace(action)
            status, _, body = self.go(f"?d={self.did}")
            self.assertEqual(status, 403, action)
            self.assertIn(word, body)
            row = self.db.one("SELECT * FROM launches ORDER BY id DESC LIMIT 1")
            self.assertEqual((row["outcome"], row["rule"]), ("refused", f"workspace_{'suspended' if action == 'suspend' else 'retired'}"))
        self.workspace("reactivate")
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)

    def test_the_device_claim_can_only_refuse_never_open(self):
        self.enable_canva()
        self.workspace("suspend")
        self.assertEqual(self.go("")[0], 302)  # no claim: the staff web app is unchanged (the app and the machine policy hold the line)
        self.assertEqual(self.go("?d=")[0], 302)
        self.assertEqual(self.go("?d=" + "x" * 80)[0], 302)
        self.assertEqual(self.go(f"?d=nosuch")[0], 302)  # someone else's or unknown device id: ignored, not an oracle
        self.assertEqual(self.go(f"?d={self.did}&d=other")[0], 302)  # repeated: not a valid claim


class PolicyReportTests(Base):
    def report(self, ok, sha=SHA, **extra):
        return self.beat({"browser_contract": 2, "policy": {"ok": ok, "sha256": sha}, **extra})

    def row(self):
        return self.db.one("SELECT policy_ok AS ok, policy_sha AS sha, policy_reported AS at FROM devices WHERE device_id = ?", (self.did,))

    def test_a_report_is_stored_as_reported_and_nothing_else_is(self):
        self.assertEqual(self.row(), {"ok": None, "sha": "", "at": None})
        self.assertEqual(self.report(True)[0], 200)
        row = self.row()
        self.assertEqual((row["ok"], row["sha"]), (1, SHA))
        self.assertLess(time.time() - row["at"], 60)

    def test_a_malformed_report_changes_nothing(self):
        self.report(True)
        before = self.row()
        for bad in ({"ok": "yes"}, {"ok": 1}, {"sha256": SHA}, "ok", ["ok"], None, {"ok": None}):
            self.beat({"policy": bad})
            self.assertEqual(self.row(), before, bad)
        self.report(False, sha="not-a-hash")
        self.assertEqual(self.row()["sha"], "")  # a bad hash is dropped, the failing report still counts

    def test_the_move_to_failing_is_audited_once_and_a_repeat_is_not(self):
        self.report(True)
        self.report(False)
        self.report(False)
        rows = self.db.q("SELECT * FROM audit WHERE action = 'device reported its browser policy is not in force'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["after_json"]), {"policy_ok": 0, "reported_by": "the app"})

    def test_warn_mode_never_refuses_open(self):
        self.enable_canva()
        self.assertEqual(managed.mode(self.db), "warn")
        for case in (None, False):
            if case is not None:
                self.report(case)
            self.assertEqual(self.go(f"?d={self.did}")[0], 302)

    def test_enforce_refuses_open_when_the_report_is_missing_stale_failing_or_the_wrong_baseline(self):
        self.enable_canva()
        self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA, "managed_policy_mode": "enforce"})
        status, _, body = self.go(f"?d={self.did}")
        self.assertEqual(status, 403)
        self.assertIn("has not reported", body)
        self.assertEqual(self.db.scalar("SELECT rule FROM launches ORDER BY id DESC LIMIT 1"), "workspace_policy")
        self.report(False)
        self.assertIn("not in force", self.go(f"?d={self.did}")[2])
        self.report(True, sha=OTHER_SHA)
        self.assertIn("expects", self.go(f"?d={self.did}")[2])
        self.report(True, sha=SHA)
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)  # a good, fresh report opens it
        self.db.x("UPDATE devices SET policy_reported = ? WHERE device_id = ?", (time.time() - managed.POLICY_STALE_SECONDS - 5, self.did))
        self.assertIn("recently", self.go(f"?d={self.did}")[2])

    def test_enforce_without_a_stored_baseline_still_needs_a_passing_report(self):
        self.enable_canva()
        self.rig.api("PUT", "/settings", {"managed_policy_mode": "enforce"})
        self.assertEqual(self.go(f"?d={self.did}")[0], 403)
        self.report(True, sha=OTHER_SHA)
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)

    def test_enforce_never_blocks_a_request_that_makes_no_device_claim(self):
        self.enable_canva()
        self.rig.api("PUT", "/settings", {"managed_policy_mode": "enforce"})
        self.assertEqual(self.go("")[0], 302)

    def test_a_policy_report_never_unlocks_a_suspended_workspace(self):
        self.enable_canva()
        self.workspace("suspend")
        self.report(True)
        self.assertEqual(self.go(f"?d={self.did}")[0], 403)


class ConsoleListTests(Base):
    def test_the_devices_list_shows_the_state_and_the_reported_policy_as_a_report(self):
        def item():
            out = self.rig.api("GET", "/devices")[1]
            return next(i for i in out["items"] if i.get("device_id") == self.did)

        one = item()
        self.assertEqual((one["workspace_state"], one["workspace_generation"], one["policy_ok"], one["policy_reported"]), ("active", 1, None, None))
        self.beat({"browser_contract": 2, "policy": {"ok": False, "sha256": SHA}})
        self.workspace("suspend")
        two = item()
        self.assertEqual((two["workspace_state"], two["policy_ok"], two["policy_source"]), ("suspended", False, "reported by the app"))
        self.assertEqual(self.rig.api("GET", "/devices", who="viewer")[0], 200)  # everyone in the console can see it


class NoCredentialTests(unittest.TestCase):
    def test_the_module_reads_stores_and_sends_no_provider_credential(self):
        import inspect

        src = inspect.getsource(managed).lower()
        for word in ("cookie", "password", "session_id", "set-cookie", "authorization", "bearer"):
            self.assertNotIn(word, src.replace("no provider password, cookie, token or session", ""), word)


if __name__ == "__main__":
    unittest.main()
