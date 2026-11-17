"""D-024: machine-policy integrity on company devices only (W6, #160). docs/DECISIONS.md D-024.

The app reports what it finds on company devices, re-checks at every heartbeat and before every Open (never reusing a
result older than 60 s), and refuses on the device in `enforce` before any browser starts. Personal devices send no
`policy` field and the server never refuses them for policy. Fixtures only: nothing is installed on a real machine."""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import core, machine_policy as mp
from swangz_client import workspace_launcher as wl

from .test_machine_policy import FakeKey, FakeRegistry, as_registry, prepare, prepared
from .test_managed_workspace import SHA, OTHER_SHA, Base


def write_pack(folder, policy, name="swangz.json", raw=None):
    folder.mkdir(exist_ok=True)
    (folder / name).write_bytes(raw if raw is not None else prepare.encode(policy))


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.folder = self.tmp / "managed"
        self.policy = prepared()
        write_pack(self.folder, self.policy)

    def check(self):
        return mp.check("chrome", platform="linux", root=self.folder)


class TamperTests(Fixture):
    def test_the_pack_in_place_passes_with_the_baseline_hash(self):
        result = self.check()
        self.assertEqual((result.ok, result.sha256), (True, mp.baseline_sha(self.policy)), result)

    def test_the_pack_removed_fails(self):
        (self.folder / "swangz.json").unlink()
        self.assertEqual(self.check().report(), {"ok": False, "sha256": ""})

    def test_one_allowlist_entry_edited_changes_the_hash(self):
        edited = json.loads(json.dumps(self.policy))
        allow = edited["URLAllowlist"]
        allow[0] = allow[0] + ".example"  # still an acceptable entry: only the hash can tell
        write_pack(self.folder, edited)
        result = self.check()
        self.assertNotEqual(result.sha256, mp.baseline_sha(self.policy))

    def test_an_extra_weakening_key_fails(self):
        cases = [
            ("zz-open.json", {"URLAllowlist": ["*"]}),                 # a second file that disagrees: a conflict
            ("zz-incognito.json", {"IncognitoModeAvailability": 0}),  # private windows back on
        ]
        for name, extra in cases:
            with self.subTest(name):
                write_pack(self.folder, None, name, json.dumps(extra).encode())
                self.assertFalse(self.check().ok)
                (self.folder / name).unlink()
        for key in mp.FORBIDDEN:  # outside the baseline: caught by problems_in(), the hash unchanged
            with self.subTest(key):
                write_pack(self.folder, dict(self.policy, **{key: {"*": {"installation_mode": "allowed"}}}))
                result = self.check()
                self.assertFalse(result.ok)
                self.assertIn("forbidden:" + key, result.problems)
                self.assertEqual(result.sha256, mp.baseline_sha(self.policy))
                write_pack(self.folder, None, "zz-extra.json", json.dumps({key: ["URLAllowlist"]}).encode())
                write_pack(self.folder, self.policy)
                self.assertIn("forbidden:" + key, self.check().problems)  # also from a second file
                (self.folder / "zz-extra.json").unlink()
        weakened = dict(self.policy, URLAllowlist=self.policy["URLAllowlist"] + ["mail.google.com"])
        write_pack(self.folder, weakened)
        self.assertFalse(self.check().ok)

    def test_a_forbidden_key_in_the_windows_registry_fails(self):
        reg = as_registry(self.policy)
        reg.values["ExtensionSettings"] = json.dumps({"*": {"installation_mode": "allowed"}})
        reg.subkeys["PolicyListMultipleSourceMergeList"] = FakeKey({"1": "URLAllowlist"})
        result = mp.check("chrome", platform="win32", registry=FakeRegistry({mp.WINDOWS_KEYS["chrome"]: reg}))
        self.assertFalse(result.ok)
        self.assertIn("forbidden:ExtensionSettings", result.problems)
        self.assertIn("forbidden:PolicyListMultipleSourceMergeList", result.problems)
        self.assertEqual(result.sha256, mp.baseline_sha(self.policy))

    def test_reordered_keys_and_whitespace_keep_the_same_hash(self):
        reordered = {k: self.policy[k] for k in reversed(list(self.policy))}
        write_pack(self.folder, None, raw=json.dumps(reordered, indent=7).encode())
        result = self.check()
        self.assertEqual((result.ok, result.sha256), (True, mp.baseline_sha(self.policy)))


def client(tmp, device):
    with mock.patch.object(core.Store, "device", return_value=device):
        return core.Client(paths=core.Paths(tmp / "home", tmp / "data"))


class ClientCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def body(self, c, device):
        c.store.state = lambda: {"installed": {}}
        c.store.device = lambda: device
        return c._heartbeat_body()

    def test_a_company_enrolment_has_the_check_and_a_personal_one_does_not(self):
        company = {"owner_kind": "company", "key_storage": "file"}
        personal = {"owner_kind": "personal", "key_storage": "file"}
        self.assertIs(client(self.tmp, company).policy_check, mp.report)
        c = client(self.tmp, personal)
        self.assertIsNone(c.policy_check)
        self.assertNotIn("policy", self.body(c, personal))
        self.assertIsNone(client(self.tmp, None).policy_check)  # not signed in: no check

    def test_a_device_record_without_owner_kind_is_armed_by_the_hubs_manifest(self):
        c = client(self.tmp, {"server": "https://hub.example"})
        self.assertIsNone(c.policy_check)
        c.store.device = lambda: {"server": "https://hub.example"}
        c._guard = lambda fn: {"device": {"owner_kind": "company"}, "packages": [], "apps": []}
        c.refresh()
        self.assertIs(c.policy_check, mp.report)
        c.policy_check = None
        c._guard = lambda fn: {"device": {"owner_kind": "personal"}, "packages": [], "apps": []}
        c.refresh()
        self.assertIsNone(c.policy_check)

    def test_signing_out_drops_the_check_and_the_baseline(self):
        c = client(self.tmp, {"owner_kind": "company"})
        c._policy_block = {"sha256": "a" * 64, "mode": "enforce"}
        c._arm_policy_check(None)
        self.assertIsNone(c.policy_check)
        self.assertIsNone(c._policy_block)

    def test_the_heartbeat_with_a_report_is_under_2_kb(self):
        device = {"owner_kind": "company", "key_storage": "file"}
        c = client(self.tmp, device)
        c.policy_check = lambda: {"ok": True, "sha256": "a" * 64}
        body = self.body(c, device)
        self.assertEqual(body["policy"], {"ok": True, "sha256": "a" * 64})
        self.assertLess(len(json.dumps(body).encode()), 2048)

    def test_a_check_that_raises_reports_failing_and_the_heartbeat_is_still_sent(self):
        device = {"owner_kind": "company", "key_storage": "file", "server": "https://hub.example"}
        c = client(self.tmp, device)
        def boom():
            raise RuntimeError("unreadable")
        c.policy_check = boom
        c.store.state = lambda: {"installed": {}}
        c.store.device = lambda: device
        c.store.key = lambda: "k"
        c._reconnect_pending = lambda: False
        sent = []
        api = mock.Mock()
        api.call = lambda method, path, body=None, **kw: sent.append((path, body)) or {"ok": True}
        c.api = lambda: api
        self.assertEqual(c.heartbeat(), {"ok": True})
        self.assertEqual([(p, b["policy"]) for p, b in sent], [("/device/heartbeat", {"ok": False, "sha256": ""})])

    def test_a_result_is_never_reused_after_60_seconds(self):
        c = client(self.tmp, {"owner_kind": "company"})
        now, calls = [1000.0], []
        c.monotonic = lambda: now[0]
        c.policy_check = lambda: calls.append(1) or {"ok": True, "sha256": "a" * 64}
        c.policy_report()
        now[0] += 59
        c.policy_report()
        self.assertEqual(len(calls), 1)
        now[0] += 2  # 61 s after the first check
        c.policy_report()
        self.assertEqual(len(calls), 2)
        now[0] -= 500  # a clock that went back is never trusted
        c.policy_report()
        self.assertEqual(len(calls), 3)


class OpenGateTests(Base):
    """The app's own check before Open, against a real Hub rig (the fake upstream; no provider)."""
    OWNER = "company"

    def app(self, mode, report, expected=SHA, owner_kind="company"):
        self.enable_canva()
        self.db.set_setting("managed_policy_sha256", expected)
        self.db.set_setting("managed_policy_mode", mode)
        tmp = Path(tempfile.mkdtemp(prefix="sgw-d024-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "data").mkdir(mode=0o700)
        server = f"http://127.0.0.1:{self.rig.port}"
        device = {"server": server, "owner_kind": owner_kind}
        c = client(tmp, device)
        c.store.manifest = lambda: {
            "apps": [{"id": "canva", "name": "Canva", "open": server + "/go/canva", "hosts": ["canva.com"], "workspace": True}],
            "browser": {"contract": 2, "person_id": str(self.rig.person_id), "device_id": self.did,
                        "workspace": {"state": "active", "generation": 1}, "policy": {"sha256": expected, "mode": mode}}}
        c.store.device = lambda: device
        c._reconnect_pending = lambda: False
        c.api = lambda: c._api_factory(server, self.key)
        if c.policy_check is not None:
            c.policy_check = lambda: report
        started = []
        c.launcher = wl.Launcher(tmp / "data", popen=lambda argv, **kw: started.append(argv) or mock.Mock(poll=lambda: None),
                                 finder=lambda: "/opt/google/chrome/chrome", acl=lambda p: True)
        return c, started

    def launches(self):
        return [(r["outcome"], r["rule"]) for r in self.db.q("SELECT outcome, rule FROM launches ORDER BY id")]

    def test_enforce_with_a_mismatch_is_refused_on_the_device_and_by_the_server(self):
        for report in ({"ok": True, "sha256": OTHER_SHA}, {"ok": False, "sha256": SHA}, {"ok": False, "sha256": ""}):
            with self.subTest(report):
                c, started = self.app("enforce", report)
                with self.assertRaises(wl.LaunchError) as caught:
                    c.open_app("canva")
                self.assertEqual(caught.exception.code, "workspace_policy")
                self.assertEqual(started, [])  # no popen
                self.assertEqual(self.launches(), [])  # refused before the Hub recorded an open
        self.beat({"browser_contract": 2, "policy": {"ok": True, "sha256": OTHER_SHA}})
        status, out, _ = self.api("POST", "/device/open", {"tool": "canva"}, key=self.key)
        self.assertEqual((status, out.get("code")), (409, "workspace_policy"), out)

    def test_enforce_with_a_matching_report_opens(self):
        c, started = self.app("enforce", {"ok": True, "sha256": SHA})
        self.beat({"browser_contract": 2, "policy": {"ok": True, "sha256": SHA}})
        self.assertEqual(c.open_app("canva"), "workspace")
        self.assertEqual(len(started), 1)

    def test_warn_with_a_mismatch_opens_and_the_console_shows_not_in_force(self):
        c, started = self.app("warn", {"ok": False, "sha256": ""})
        self.assertEqual(c.open_app("canva"), "workspace")
        self.assertEqual(len(started), 1)
        self.assertEqual(self.launches(), [("opened", None)])
        self.assertEqual(c._heartbeat_body()["policy"], {"ok": False, "sha256": ""})  # reported at the next check-in
        self.beat({"browser_contract": 2, "policy": {"ok": False, "sha256": ""}})
        self.assertIn("not in force", self.db.scalar("SELECT action FROM audit WHERE action LIKE '%browser policy%'"))
        self.assertEqual(self.db.scalar("SELECT policy_ok FROM devices WHERE device_id = ?", (self.did,)), 0)

    def test_the_heartbeat_answer_updates_the_baseline_the_app_compares_with(self):
        c, _ = self.app("warn", {"ok": True, "sha256": OTHER_SHA})
        self.assertEqual(c.policy_expected(), (SHA, "warn"))
        c._policy_block = {"sha256": OTHER_SHA, "mode": "enforce"}
        self.assertEqual(c.policy_expected(), (OTHER_SHA, "enforce"))
        c.policy_gate()  # OTHER_SHA matches now: no refusal


class PersonalDeviceTests(Base):
    OWNER = "personal"

    def test_enforce_never_refuses_a_personal_device_for_policy(self):
        self.enable_canva()
        self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA, "managed_policy_mode": "enforce"})
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)  # no report at all
        self.beat({"browser_contract": 2, "policy": {"ok": False, "sha256": ""}})  # even a failing claim
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)
        status, out, _ = self.api("POST", "/device/open", {"tool": "canva"}, key=self.key)
        self.assertEqual(status, 200, out)

    def test_a_personal_app_in_enforce_opens_without_any_check(self):
        tmp = Path(tempfile.mkdtemp(prefix="sgw-d024p-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        c = client(tmp, {"owner_kind": "personal"})
        c.store.manifest = lambda: {"browser": {"contract": 2, "policy": {"sha256": SHA, "mode": "enforce"}}}
        self.assertIsNone(c.policy_gate())

    def test_a_suspended_personal_workspace_is_still_refused(self):
        self.enable_canva()
        self.workspace("suspend")
        self.assertEqual(self.go(f"?d={self.did}")[0], 403)


if __name__ == "__main__":
    unittest.main()
