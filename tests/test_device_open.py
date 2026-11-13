"""POST /api/device/open: the provider address for the Swangz workspace window (docs/MANAGED-WORKSPACE.md 9.1, W3).
Same checks and launch record as /go/, plus this device's workspace state, plus a safe-address check."""

import time
import unittest
from unittest import mock

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
                               "allowed_hosts": ["canva.com"], "workspace": {"state": "active", "generation": 1}})
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

    def test_opens_are_limited_per_person_and_a_refused_burst_writes_no_launch_rows(self):
        self.enable_canva()
        with mock.patch.object(device_open, "OPENS_PER_MIN", 3):
            self.assertEqual([self.open()[0] for _ in range(3)], [200, 200, 200])
            status, out, _ = self.open()
            self.assertEqual((status, out.get("code")), (429, "rate_limited"), out)
        self.assertEqual(len(self.launches()), 3)

    def test_unknown_or_malformed_tool_ids(self):
        for tool in ("no-such-tool", "Canva", "../canva", "", None, 7, ["canva"]):
            status, out, _ = self.open(tool=tool)
            self.assertEqual((status, out.get("code")), (404, "unknown_tool"), tool)
        self.db.x("UPDATE tools SET archived = 1 WHERE id = 'canva'")
        self.assertEqual(self.open()[0], 404)


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
