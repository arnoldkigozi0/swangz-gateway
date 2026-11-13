"""POST /api/device/open: the provider address for the Swangz workspace window (docs/MANAGED-WORKSPACE.md 9.1, W3).
Same checks and launch record as /go/, plus this device's workspace state, plus a safe-address check."""

import time
import unittest

from gateway import device_open

from .test_managed_workspace import SHA, Base

OPEN = "/device/open"


class DeviceOpenTests(Base):
    def open(self, tool="canva", key=None, headers_app=True):
        if not headers_app:
            status, h, payload = self.rig.request("POST", "/api" + OPEN, {"tool": tool}, {"authorization": "Bearer " + (key or self.key)})
            return status, payload, h
        return self.api("POST", OPEN, {"tool": tool}, key=key or self.key)

    def launches(self):
        return [dict(r) for r in self.db.q("SELECT tool_id, outcome, rule, reason FROM launches ORDER BY id")]

    def tool(self, **fields):
        for k, v in fields.items():
            self.db.x(f"UPDATE tools SET {k} = ? WHERE id = 'canva'", (v,))

    def test_an_entitled_person_gets_the_official_address_and_the_open_is_recorded(self):
        self.enable_canva()
        status, out, h = self.open()
        self.assertEqual(status, 200, out)
        self.assertEqual(out, {"ok": True, "tool": {"id": "canva", "name": "Canva"}, "url": "https://www.canva.com/",
                               "allowed_hosts": ["canva.com"], "launch": out.get("launch"), "workspace": {"state": "active", "generation": 1}})
        self.assertIsInstance(out["launch"], int)
        self.assertEqual(h.get("cache-control"), "no-store")
        self.assertNotIn(self.key, str(out))
        self.assertEqual(self.launches(), [{"tool_id": "canva", "outcome": "opened", "rule": None, "reason": ""}])

    def test_the_answer_matches_go_for_the_same_person_and_tool(self):
        status, out, _ = self.open()  # not assigned yet
        self.assertEqual((status, out.get("code")), (403, "locked"), out)  # the company has no Canva subscription yet
        self.assertEqual(self.go()[0], 403)
        self.enable_canva()
        self.assertEqual(self.open()[0], 200)
        self.assertEqual(self.go()[0], 302)
        self.assertEqual([r["outcome"] for r in self.launches()], ["refused", "refused", "opened", "opened"])

    def test_the_device_key_is_required_and_a_disconnected_device_gets_nothing(self):
        self.enable_canva()
        status, out, _ = self.api("POST", OPEN, {"tool": "canva"})
        self.assertEqual((status, out.get("code")), (401, "device_unknown"))
        self.assertEqual(self.open(key="sgw-not-a-real-key")[0], 401)
        self.db.x("UPDATE keys SET revoked = ? WHERE device_id = ?", (time.time(), self.did))
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (401, "device_revoked"))
        self.assertEqual(self.launches(), [])  # nobody identified: nothing to record against a person

    def test_the_app_header_is_required(self):
        self.enable_canva()
        self.assertEqual(self.open(headers_app=False)[0], 403)
        self.assertEqual(self.launches(), [])

    def test_a_suspended_or_retired_workspace_is_refused_and_reactivating_opens_again(self):
        self.enable_canva()
        self.workspace("suspend")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (403, "workspace_suspended"), out)
        self.workspace("reactivate")
        self.assertEqual(self.open()[0], 200)
        self.workspace("retire")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (403, "workspace_retired"), out)
        self.assertEqual([(r["outcome"], r["rule"]) for r in self.launches()],
                         [("refused", "workspace_suspended"), ("opened", None), ("refused", "workspace_retired")])

    def test_enforce_mode_needs_a_fresh_passing_policy_report_from_this_device(self):
        self.enable_canva()
        self.db.set_setting("managed_policy_sha256", SHA)
        self.db.set_setting("managed_policy_mode", "enforce")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (403, "workspace_policy"), out)
        self.assertEqual(self.beat({"browser_contract": 2, "policy": {"ok": True, "sha256": SHA}})[0], 200)
        self.assertEqual(self.open()[0], 200)

    def test_an_address_off_the_tools_hosts_is_refused_and_recorded(self):
        self.enable_canva()
        self.tool(launch_url="https://evil.example/canva-sso")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (409, "host_not_allowed"), out)
        self.assertNotIn("evil.example", str(out))
        self.tool(launch_url="https://www.canva.com/login?token=abc")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (409, "unsafe_address"), out)
        self.assertNotIn("token=abc", str(out))
        self.tool(launch_url="", hosts="")
        self.assertEqual(self.open()[1].get("code"), "host_not_allowed")  # no governed hosts: fail closed
        self.assertEqual([(r["outcome"], r["rule"]) for r in self.launches()],
                         [("refused", "host_not_allowed"), ("refused", "unsafe_address"), ("refused", "host_not_allowed")])

    def test_a_tool_with_no_address_says_so(self):
        self.enable_canva()
        self.tool(launch_url="", url="")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (409, "no_address"), out)

    def test_a_shared_company_account_is_left_to_the_hub(self):
        self.enable_canva()
        self.tool(signin="shared")
        status, out, _ = self.open()
        self.assertEqual((status, out.get("code")), (409, "shared_account"), out)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM tool_turns"), 0)  # no turn taken from here

    def test_unknown_or_malformed_tool_ids(self):
        for tool in ("no-such-tool", "Canva", "../canva", "", None, 7, ["canva"]):
            status, out, _ = self.open(tool=tool)
            self.assertEqual((status, out.get("code")), (404, "unknown_tool"), tool)
        self.db.x("UPDATE tools SET archived = 1 WHERE id = 'canva'")
        self.assertEqual(self.open()[0], 404)


class DeviceOpenFailedTests(DeviceOpenTests):
    """The app reports a window that didn't start, so the record says `failed`, not `opened` (Probe on #204/#202)."""

    def failed(self, launch, reason="folder", key=None):
        return self.api("POST", OPEN + "/failed", {"launch": launch, "reason": reason}, key=key or self.key)

    def test_the_open_becomes_failed_with_a_code_and_never_counts_as_opened(self):
        self.enable_canva()
        launch = self.open()[1]["launch"]
        status, out, _ = self.failed(launch, "unsafe_address")
        self.assertEqual((status, out), (200, {"ok": True, "recorded": True}))
        self.assertEqual(self.launches(), [{"tool_id": "canva", "outcome": "failed", "rule": "app:unsafe_address",
                                            "reason": "The Swangz app reported that the workspace window didn't start."}])
        self.assertEqual(self.failed(launch)[1]["recorded"], False)  # once only
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM launches WHERE outcome = 'opened'"), 0)

    def test_an_unknown_code_is_stored_as_launch_failed_and_never_echoed(self):
        self.enable_canva()
        launch = self.open()[1]["launch"]
        self.assertEqual(self.failed(launch, "https://secret.example/?token=x")[0], 200)
        self.assertEqual(self.launches()[0]["rule"], "app:launch_failed")
        self.assertNotIn("secret", str(self.launches()))

    def test_only_this_persons_recent_open_changes(self):
        self.enable_canva()
        launch = self.open()[1]["launch"]
        other = self.db.x("INSERT INTO people(name, email, created) VALUES('Other', 'other@swangzavenue.com', ?)", (time.time(),)).lastrowid
        self.db.x("UPDATE launches SET person_id = ? WHERE id = ?", (other, launch))
        self.assertEqual(self.failed(launch)[1]["recorded"], False)
        self.db.x("UPDATE launches SET person_id = ?, ts = ? WHERE id = ?", (self.rig.person_id, time.time() - 301, launch))
        self.assertEqual(self.failed(launch)[1]["recorded"], False)
        self.workspace("suspend")
        refused = self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('canva', ?, ?, 'refused')",
                            (self.rig.person_id, time.time())).lastrowid
        self.assertEqual(self.failed(refused)[1]["recorded"], False)
        self.assertEqual([r["outcome"] for r in self.launches()], ["opened", "refused"])

    def test_a_go_launch_or_another_devices_open_is_never_changed(self):
        """Sentinel on #210: the report must come from the device that made the open."""
        self.enable_canva()
        self.assertEqual(self.go()[0], 302)
        web = self.db.scalar("SELECT id FROM launches ORDER BY id DESC LIMIT 1")
        self.assertIsNone(self.db.scalar("SELECT device_id FROM launches WHERE id = ?", (web,)))
        self.assertEqual(self.failed(web)[1]["recorded"], False)
        launch = self.open()[1]["launch"]
        self.assertEqual(self.db.scalar("SELECT device_id FROM launches WHERE id = ?", (launch,)), self.did)
        self.db.x("UPDATE launches SET device_id = 'another-device' WHERE id = ?", (launch,))
        self.assertEqual(self.failed(launch)[1]["recorded"], False)
        self.assertEqual([r["outcome"] for r in self.launches()], ["opened", "opened"])
        self.assertEqual(self.audits(), [])

    def audits(self):
        return [dict(r) for r in self.db.q("SELECT actor, target, detail, before_json, after_json, correlation FROM audit"
                                            " WHERE action = 'reported a workspace window that did not start'")]

    def test_the_rewrite_is_audited_with_the_code_only(self):
        self.enable_canva()
        launch = self.open()[1]["launch"]
        self.assertEqual(self.failed(launch, "https://secret.example/?token=x")[1]["recorded"], True)
        self.assertEqual(self.audits(), [{"actor": "Nansubuga Grace", "target": "", "detail": "",
                                          "before_json": '{"outcome": "opened"}',
                                          "after_json": '{"code": "launch_failed", "outcome": "failed"}',
                                          "correlation": f"device:{self.did}"}])
        self.assertEqual(self.failed(launch)[1]["recorded"], False)
        self.assertEqual(len(self.audits()), 1)  # a repeat report changes nothing and is not audited again

    def test_the_device_key_is_required_and_the_body_is_checked(self):
        self.enable_canva()
        launch = self.open()[1]["launch"]
        self.assertEqual(self.api("POST", OPEN + "/failed", {"launch": launch, "reason": "folder"})[0], 401)
        self.assertEqual(self.failed(launch, key="sgw-not-a-real-key")[0], 401)
        for bad in ("1", 0, -1, None, 1.0, True, 2 ** 63):
            self.assertEqual(self.failed(bad)[0], 400, bad)
        self.assertEqual(self.launches()[0]["outcome"], "opened")


class SafeAddressTests(unittest.TestCase):
    HOSTS = ["canva.com", "chatgpt.com"]

    def test_safe_addresses(self):
        for url in ("https://www.canva.com/", "https://canva.com", "https://chatgpt.com/?model=gpt-4o",
                    "https://sso.canva.com:443/start?org=swangz", "https://WWW.Canva.com/design#home"):
            self.assertIsNone(device_open.check_url(url, self.HOSTS), url)

    def test_unsafe_addresses(self):
        cases = {
            "http://www.canva.com/": "unsafe_address",
            "javascript:alert(1)": "unsafe_address",
            "file:///etc/passwd": "unsafe_address",
            "https://user:pw@www.canva.com/": "unsafe_address",
            "https://www.canva.com@evil.example/": "unsafe_address",
            "https://www.canva.com:8443/": "unsafe_address",
            "https://www.canva.com:x/": "unsafe_address",
            "https://127.0.0.1/": "unsafe_address",
            "https://[::1]/": "unsafe_address",
            "https://localhost/": "unsafe_address",
            "https://www.canva.com/a b": "unsafe_address",
            "https://www.canva.com/\\evil": "unsafe_address",
            "https://www.canva.com/\n": "unsafe_address",
            "https://www.canva.com/?access_token=x": "unsafe_address",
            "https://www.canva.com/?API_KEY=x": "unsafe_address",
            "https://www.canva.com/#id_token=x": "unsafe_address",
            "https://www.canva.com/?password=": "unsafe_address",
            "https://www.canva.com/" + "a" * 2100: "unsafe_address",
            "": "unsafe_address",
            "https://evilcanva.com/": "host_not_allowed",
            "https://canva.com.evil.example/": "host_not_allowed",
            "https://example.org/": "host_not_allowed",
        }
        for url, code in cases.items():
            self.assertEqual(device_open.check_url(url, self.HOSTS), code, url)

    def test_the_hub_itself_is_never_opened_in_the_workspace(self):
        self.assertEqual(device_open.check_url("https://hub.canva.com/go/canva", self.HOSTS, "hub.canva.com"), "unsafe_address")
        self.assertIsNone(device_open.check_url("https://www.canva.com/", self.HOSTS, "hub.swangz.example"))

    def test_allowed_hosts_drop_malformed_entries_and_never_widen(self):
        tool = {"hosts": " Canva.com, www.chatgpt.com ,*.evil.example,, localhost, 10.0.0.1, .com, canva.com"}
        self.assertEqual(device_open.allowed_hosts(tool), ["canva.com", "chatgpt.com"])


if __name__ == "__main__":
    unittest.main()
