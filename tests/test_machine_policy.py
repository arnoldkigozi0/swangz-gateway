"""W5 of docs/MANAGED-WORKSPACE.md: the app reads the effective machine policy where each OS keeps it and says whether
the company baseline is in force. Read-only; these tests never write a real policy location and run on every runner
of the W6 matrix (the Linux, macOS and Windows readers are each exercised against a stand-in on every OS)."""

import copy
import importlib.util
import json
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import core, machine_policy as mp

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("swangz_chrome_prepare_w5", ROOT / "deploy" / "chrome-policy" / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def prepared():
    template = json.loads(prepare.TEMPLATE.read_text(encoding="utf-8"))
    return prepare.prepare(template, "ai.swangzavenue.com", "a" * 32, "https://clients2.google.com/service/update2/crx")


# ------------------------------------------------------------------ a stand-in for winreg

REG_DWORD, REG_SZ = 4, 1


class FakeKey:
    def __init__(self, values=None, subkeys=None):
        self.values, self.subkeys = dict(values or {}), dict(subkeys or {})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRegistry:
    """The calls `read_windows` makes, over a nested dict. Opening a missing key raises OSError, as winreg does."""

    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ, KEY_WOW64_64KEY = 0x20019, 0x0100

    def __init__(self, tree):
        self.tree = tree  # {"Software\\Policies\\Google\\Chrome": FakeKey}
        self.opened = []

    def OpenKey(self, parent, sub, reserved=0, access=None):
        self.opened.append(sub)
        self.access = getattr(self, "access", []) + [access]
        if parent == self.HKEY_LOCAL_MACHINE:
            if sub not in self.tree:
                raise FileNotFoundError(sub)
            return self.tree[sub]
        if sub not in parent.subkeys:
            raise FileNotFoundError(sub)
        return parent.subkeys[sub]

    def EnumValue(self, key, i):
        items = list(key.values.items())
        if i >= len(items):
            raise OSError("no more")
        name, value = items[i]
        return name, value, REG_DWORD if isinstance(value, int) else REG_SZ

    def EnumKey(self, key, i):
        names = list(key.subkeys)
        if i >= len(names):
            raise OSError("no more")
        return names[i]


def as_registry(policy):
    """What the Chrome ADMX / an admin's .reg puts in HKLM for this JSON policy: booleans as DWORD 0/1, lists as a
    subkey with values "1", "2", ..., dictionary policies as one JSON string."""
    values, subkeys = {}, {}
    for key, value in policy.items():
        if key in mp.JSON_STRING:
            values[key] = json.dumps(value)
        elif isinstance(value, list):
            # stored out of order on purpose: the reader must order by number, not by enumeration
            entries = [(str(i + 1), v) for i, v in enumerate(value)]
            subkeys[key] = FakeKey(dict(reversed(entries)))
        elif isinstance(value, bool):
            values[key] = int(value)
        else:
            values[key] = value
    return FakeKey(values, subkeys)


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.policy = prepared()

    def linux(self, *files):
        folder = self.tmp / "managed"
        folder.mkdir(exist_ok=True)
        for name, value in files:
            (folder / name).write_bytes(value if isinstance(value, bytes) else prepare.encode(value))
        return mp.check("chrome", platform="linux", root=folder)

    def mac(self, device=None, user=None, name="com.google.Chrome.plist"):
        """`user` writes a per-user copy, which is NOT machine scope and must be ignored."""
        root = self.tmp / "Managed Preferences"
        root.mkdir(exist_ok=True)
        if device is not None:
            (root / name).write_bytes(device if isinstance(device, bytes) else plistlib.dumps(device))
        if user is not None:
            (root / "ada").mkdir(exist_ok=True)
            (root / "ada" / name).write_bytes(plistlib.dumps(user))
        return mp.check("chrome", platform="darwin", root=root)

    def windows(self, policy, where=mp.WINDOWS_KEYS["chrome"], browser="chrome"):
        registry = FakeRegistry({where: as_registry(policy)} if policy is not None else {})
        return mp.check(browser, platform="win32", registry=registry)


class TheBaselineHashTests(Fixture):
    def test_the_hash_is_the_same_on_all_three_systems_and_equals_what_the_generator_prints(self):
        want = prepare.baseline_sha(self.policy)
        linux, mac, win = self.linux(("swangz.json", self.policy)), self.mac(self.policy), self.windows(self.policy)
        for result in (linux, mac, win):
            self.assertTrue(result.ok, result)
            self.assertEqual(result.sha256, want)
        self.assertRegex(want, r"\A[0-9a-f]{64}\Z")

    def test_both_sides_cover_the_same_policies(self):
        self.assertEqual(set(prepare.BASELINE_KEYS), set(mp.KNOWN))
        self.assertEqual(prepare.REQUIRED, mp.REQUIRED)
        self.assertEqual(prepare.REQUIRED_BLOCKS, mp.REQUIRED_BLOCKS)

    def test_any_change_to_a_known_policy_changes_the_hash_and_unknown_ones_do_not(self):
        base = self.linux(("swangz.json", self.policy)).sha256
        changed = copy.deepcopy(self.policy)
        changed["URLAllowlist"].append("example.org")
        self.assertNotEqual(mp.baseline_sha(changed), base)
        other = dict(self.policy, HomepageLocation="https://example.org")
        self.assertEqual(mp.baseline_sha(other), base)

    def test_the_command_prints_the_baseline_to_pin(self):
        import contextlib
        import io
        out, buf = self.tmp / "prepared.json", io.StringIO()
        with contextlib.redirect_stdout(buf):
            prepare.main(["--hub-host", "ai.swangzavenue.com", "--extension-id", "a" * 32,
                          "--update-url", "https://clients2.google.com/service/update2/crx", "--output", str(out)])
        line = [l for l in buf.getvalue().splitlines() if l.startswith("Baseline SHA-256")]
        self.assertEqual(len(line), 1)
        self.assertEqual(line[0].rsplit(": ", 1)[1], prepare.baseline_sha(json.loads(out.read_text())))


class LinuxTests(Fixture):
    def test_missing_folder_or_empty_folder_fails(self):
        self.assertEqual(mp.check("chrome", platform="linux", root=self.tmp / "nope").problems, ["missing"])
        self.assertEqual(self.linux().problems, ["missing"])

    def test_every_required_setting_is_checked(self):
        for key in mp.REQUIRED:
            without = {k: v for k, v in self.policy.items() if k != key}
            for name in os.listdir(self.tmp / "managed") if (self.tmp / "managed").exists() else ():
                os.unlink(self.tmp / "managed" / name)
            result = self.linux(("swangz.json", without))
            self.assertFalse(result.ok, key)
            self.assertIn("missing:" + key, result.problems)

    def test_a_weakened_value_fails_including_a_same_looking_type(self):
        cases = {"DeveloperToolsAvailability": 0, "IncognitoModeAvailability": 0, "BrowserSignin": 1,
                 "SyncDisabled": 1, "RemoteDebuggingAllowed": True, "AutoLaunchProtocolsFromOrigins": [{"protocol": "x"}]}
        for key, value in cases.items():
            for p in (self.tmp / "managed").glob("*") if (self.tmp / "managed").exists() else ():
                p.unlink()
            result = self.linux(("swangz.json", dict(self.policy, **{key: value})))
            self.assertIn("wrong:" + key, result.problems, key)

    def test_default_deny_and_extension_lists(self):
        weak = [
            ("URLBlocklist", ["file://*"], "missing_block:*"),
            ("URLBlocklist", ["*", "file://*", "chrome://*"], "missing_block:view-source:*"),
            ("URLAllowlist", ["*"], "open:URLAllowlist"),
            ("URLAllowlist", self.policy["URLAllowlist"] + ["https://*"], "open:URLAllowlist"),
            ("URLAllowlist", [], "missing:URLAllowlist"),
            ("ExtensionInstallBlocklist", [], "wrong:ExtensionInstallBlocklist"),
            ("ExtensionInstallForcelist", [], "missing:ExtensionInstallForcelist"),
            ("ExtensionInstallAllowlist", ["SWANGZ_EXTENSION_ID"], "placeholder:ExtensionInstallAllowlist"),
        ]
        for key, value, problem in weak:
            for p in (self.tmp / "managed").glob("*") if (self.tmp / "managed").exists() else ():
                p.unlink()
            result = self.linux(("swangz.json", dict(self.policy, **{key: value})))
            self.assertFalse(result.ok, (key, value))
            self.assertIn(problem, result.problems)

    def test_policy_split_across_files_is_merged_and_a_conflict_fails(self):
        a = {k: v for k, v in self.policy.items() if k.startswith("URL")}
        b = {k: v for k, v in self.policy.items() if not k.startswith("URL")}
        result = self.linux(("10-urls.json", a), ("20-rest.json", b))
        self.assertTrue(result.ok, result)
        self.assertEqual(result.sha256, prepare.baseline_sha(self.policy))
        self.assertEqual(result.sources, ["10-urls.json", "20-rest.json"])
        result = self.linux(("05-local.json", {"DeveloperToolsAvailability": 1}))
        self.assertFalse(result.ok)
        self.assertIn("conflict:DeveloperToolsAvailability", result.problems)

    def test_an_unreadable_or_oversized_file_fails_and_never_raises(self):
        self.assertEqual(self.linux(("swangz.json", b"{not json")).problems, ["unreadable:swangz.json"])
        for p in (self.tmp / "managed").glob("*"):
            p.unlink()
        self.assertEqual(self.linux(("big.json", b" " * (mp.MAX_BYTES + 1))).problems, ["unreadable:big.json"])
        for p in (self.tmp / "managed").glob("*"):
            p.unlink()
        self.assertEqual(self.linux(("list.json", b"[]")).problems, ["unreadable:list.json"])

    def test_any_other_file_in_the_folder_fails_the_check(self):
        # Chrome applies every file in the folder, not just *.json: one we don't read could undo the policy.
        for name, data in (("README", b"not policy"), ("extra.conf", b'{"URLAllowlist": ["*"]}'),
                           (".hidden.json", b"{"), (".hidden", b"{}")):
            for p in (self.tmp / "managed").glob("*"):
                p.unlink()
            result = self.linux(("swangz.json", self.policy), (name, data))
            self.assertEqual((result.ok, result.problems), (False, ["unreadable:" + name]), name)

    def test_the_report_carries_two_fields_and_no_site_or_value(self):
        bad = self.linux(("swangz.json", dict(self.policy, URLAllowlist=["secret-intranet.example", "*"])))
        self.assertEqual(set(bad.report()), {"ok", "sha256"})
        self.assertNotIn("secret-intranet", json.dumps(bad.report()) + " ".join(bad.problems))
        self.assertLess(len(json.dumps(bad.report())), 120)

    def test_reading_writes_nothing(self):
        self.linux(("swangz.json", self.policy))
        folder = self.tmp / "managed"
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
        with mock.patch("os.open", side_effect=AssertionError("os.open")):  # the reader uses builtins open "rb" only
            mp.check("chrome", platform="linux", root=folder)
        self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}, before)

    def test_chromium_has_its_own_folder(self):
        self.assertEqual(mp.LINUX_DIRS["chromium"], "/etc/chromium/policies/managed")
        self.assertEqual(mp.LINUX_DIRS["chrome"], "/etc/opt/chrome/policies/managed")
        self.assertEqual(mp.LINUX_DIRS["chromium-browser"], "/etc/chromium-browser/policies/managed")


class FailClosedTests(Fixture):
    """Sentinel's W5 checklist item 3: anything doubtful is a failing check, never a pass and never an exception."""

    def test_a_key_given_twice_in_one_file_fails(self):
        text = prepare.encode(self.policy).decode()
        doubled = text.replace('"IncognitoModeAvailability": 1', '"IncognitoModeAvailability": 0, "IncognitoModeAvailability": 1')
        self.assertNotEqual(text, doubled)
        result = self.linux(("swangz.json", doubled.encode()))
        self.assertFalse(result.ok)
        self.assertEqual(result.problems, ["unreadable:swangz.json"])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_a_symlinked_file_or_folder_fails(self):
        real = self.tmp / "real.json"
        real.write_bytes(prepare.encode(self.policy))
        folder = self.tmp / "managed"
        folder.mkdir()
        (folder / "swangz.json").symlink_to(real)
        self.assertEqual(mp.check("chrome", platform="linux", root=folder).problems, ["unreadable:swangz.json"])
        (folder / "swangz.json").unlink()
        (folder / "swangz.json").write_bytes(prepare.encode(self.policy))
        self.assertTrue(mp.check("chrome", platform="linux", root=folder).ok)
        link = self.tmp / "linked"
        link.symlink_to(folder, target_is_directory=True)
        self.assertEqual(mp.check("chrome", platform="linux", root=link).problems, ["unreadable:linked"])

    def test_a_folder_in_place_of_a_file_fails(self):
        folder = self.tmp / "managed"
        (folder / "swangz.json").mkdir(parents=True)
        self.assertEqual(mp.check("chrome", platform="linux", root=folder).problems, ["unreadable:swangz.json"])

    def test_the_policy_file_removed_is_a_failing_report(self):
        result = self.linux(("swangz.json", self.policy))
        self.assertEqual(result.report(), {"ok": True, "sha256": mp.baseline_sha(self.policy)})
        (self.tmp / "managed" / "swangz.json").unlink()
        self.assertEqual(mp.check("chrome", platform="linux", root=self.tmp / "managed").report(), {"ok": False, "sha256": ""})


class WhichBrowserTests(unittest.TestCase):
    """Checklist item 1: the report is about the browser the launcher starts (Chrome, or .deb Chromium)."""

    def test_browser_kind(self):
        for path, kind in (("/opt/google/chrome/chrome", "chrome"), ("/usr/lib/chromium/chromium", "chromium"),
                           ("/usr/lib/chromium-browser/chromium-browser", "chromium-browser"),
                           ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "chrome"),
                           ("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "chrome"),
                           (None, None), ("/usr/bin/chromium", None), ("/home/me/chromium/chrome", None),
                           ("/snap/bin/chromium", None), ("/opt/google/chrome/chrome-beta", None)):
            self.assertEqual(mp.browser_kind(path), kind, path)

    def test_every_launcher_browser_has_an_exact_policy_home(self):
        from swangz_client import workspace_launcher as wl
        for path in wl.LINUX_BROWSERS:
            self.assertIn(mp.browser_kind(path), mp.LINUX_DIRS, path)
        for path in wl.MAC_BROWSERS:
            self.assertIn(mp.browser_kind(path), mp.MAC_DOMAINS, path)
        for root in ("C:\\Program Files", "C:\\Program Files (x86)", "C:\\Users\\a\\AppData\\Local"):
            self.assertEqual(mp.browser_kind("\\".join((root, *wl.WINDOWS_TAIL))), "chrome", root)

    def test_an_unknown_browser_or_family_fails(self):
        self.assertEqual(mp.report(finder=lambda: "/usr/local/bin/chrome"), {"ok": False, "sha256": ""})
        self.assertEqual(mp.check("chromium-browser", platform="darwin").problems, ["unknown_browser"])
        self.assertEqual(mp.check("chromium-browser", platform="win32").problems, ["unknown_browser"])

    def test_ubuntu_chromium_browser_reads_its_own_folder(self):
        seen = []
        with mock.patch.object(mp, "read_linux", side_effect=lambda b, r=None: seen.append(b) or []), \
                mock.patch.object(mp.sys, "platform", "linux"):  # the Linux reader, on every CI runner
            mp.report(finder=lambda: "/usr/lib/chromium-browser/chromium-browser")
        self.assertEqual(seen, ["chromium-browser"])

    def test_report_checks_the_launchers_browser_family(self):
        seen = []
        with mock.patch.object(mp, "check", side_effect=lambda b: seen.append(b) or mp.Result(False, None, [], [])):
            mp.report(finder=lambda: "/usr/lib/chromium/chromium")
            mp.report(finder=lambda: "/opt/google/chrome/chrome")
            mp.report("chromium")
        self.assertEqual(seen, ["chromium", "chrome", "chromium"])

    def test_no_browser_is_a_failing_report(self):
        def none():
            raise RuntimeError("no_browser")
        self.assertEqual(mp.report(finder=none), {"ok": False, "sha256": ""})


class MacTests(Fixture):
    def test_device_wide_plist(self):
        result = self.mac(self.policy)
        self.assertTrue(result.ok, result)
        self.assertEqual(result.sources, ["com.google.Chrome.plist"])

    def test_a_per_user_plist_is_not_machine_scope_and_is_never_read(self):
        self.assertEqual(self.mac(user=self.policy).problems, ["missing"])
        result = self.mac(device=self.policy, user={"IncognitoModeAvailability": 0})
        self.assertTrue(result.ok, result)
        self.assertEqual(result.sources, ["com.google.Chrome.plist"])

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_a_symlinked_plist_fails(self):
        real = self.tmp / "elsewhere.plist"
        real.write_bytes(plistlib.dumps(self.policy))
        root = self.tmp / "Managed Preferences"
        root.mkdir()
        (root / "com.google.Chrome.plist").symlink_to(real)
        self.assertEqual(mp.check("chrome", platform="darwin", root=root).problems, ["unreadable:com.google.Chrome.plist"])

    def test_missing_and_unreadable(self):
        self.assertEqual(self.mac().problems, ["missing"])
        self.assertEqual(self.mac(device=b"not a plist").problems, ["unreadable:com.google.Chrome.plist"])

    def test_chromium_domain(self):
        root = self.tmp / "Managed Preferences"
        root.mkdir()
        (root / "org.chromium.Chromium.plist").write_bytes(plistlib.dumps(self.policy))
        self.assertTrue(mp.check("chromium", platform="darwin", root=root).ok)
        self.assertFalse(mp.check("chrome", platform="darwin", root=root).ok)


class WindowsTests(Fixture):
    def test_registry_policy_passes_with_dwords_list_subkeys_and_json_strings(self):
        result = self.windows(self.policy)
        self.assertTrue(result.ok, result)
        self.assertEqual(result.sources, ["HKLM\\Software\\Policies\\Google\\Chrome"])

    def test_a_list_is_read_in_numeric_order(self):
        registry = FakeRegistry({mp.WINDOWS_KEYS["chrome"]: FakeKey(subkeys={"URLBlocklist": FakeKey({"10": "c", "2": "b", "1": "a", "x": "ignored"})})})
        [(_, policy)] = mp.read_windows("chrome", registry)
        self.assertEqual(policy["URLBlocklist"], ["a", "b", "c"])

    def test_missing_key_and_wrong_dword(self):
        self.assertEqual(self.windows(None).problems, ["missing"])
        result = self.windows(dict(self.policy, DeveloperToolsAvailability=1))
        self.assertIn("wrong:DeveloperToolsAvailability", result.problems)
        # a 2 in a true/false DWORD is not quietly read as true
        reg = as_registry(self.policy)
        reg.values["SyncDisabled"] = 2
        result = mp.check("chrome", platform="win32", registry=FakeRegistry({mp.WINDOWS_KEYS["chrome"]: reg}))
        self.assertIn("wrong:SyncDisabled", result.problems)

    def test_chromium_key_and_only_hklm(self):
        result = self.windows(self.policy, where=mp.WINDOWS_KEYS["chromium"], browser="chromium")
        self.assertTrue(result.ok, result)
        registry = FakeRegistry({mp.WINDOWS_KEYS["chromium"]: as_registry(self.policy)})
        self.assertFalse(mp.check("chrome", platform="win32", registry=registry).ok)

    def test_only_the_64_bit_view_of_hklm_is_read(self):
        registry = FakeRegistry({mp.WINDOWS_KEYS["chrome"]: as_registry(self.policy)})
        self.assertTrue(mp.check("chrome", platform="win32", registry=registry).ok)
        self.assertTrue(registry.access)
        self.assertTrue(all(a == registry.KEY_READ | registry.KEY_WOW64_64KEY for a in registry.access), registry.access)

    def test_recommended_is_not_read(self):
        key = as_registry(self.policy)
        key.subkeys["Recommended"] = FakeKey({"IncognitoModeAvailability": 0})
        registry = FakeRegistry({mp.WINDOWS_KEYS["chrome"]: key})
        self.assertTrue(mp.check("chrome", platform="win32", registry=registry).ok)
        self.assertNotIn("Recommended", registry.opened)

    def test_a_registry_error_is_a_failing_check(self):
        class Broken(FakeRegistry):
            def EnumValue(self, key, i):
                raise PermissionError("denied")

            def EnumKey(self, key, i):
                raise PermissionError("denied")

        result = mp.check("chrome", platform="win32", registry=Broken({mp.WINDOWS_KEYS["chrome"]: as_registry(self.policy)}))
        self.assertFalse(result.ok)

    @unittest.skipUnless(os.name == "nt", "the real registry exists only on Windows")
    def test_the_real_registry_read_never_raises(self):
        result = mp.check("chrome")  # a CI runner has no company policy: expected to fail, never to raise
        self.assertIsInstance(result.ok, bool)
        self.assertEqual(set(result.report()), {"ok", "sha256"})


class HeartbeatTests(unittest.TestCase):
    """The heartbeat changes only when the managed workspace turns the check on (contract 1 stays as it was)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.client = core.Client(paths=core.Paths(data=Path(tmp.name)))
        self.client.store.state = lambda: {"installed": {}}
        self.client.store.device = lambda: {"key_storage": "file"}

    def test_off_by_default(self):
        body = self.client._heartbeat_body()
        self.assertNotIn("policy", body)  # no report until the managed workspace turns the check on
        # W4 (#191) always asks for the contract-2 answer; without it the field is absent. Either way, never another value.
        self.assertIn(body.get("browser_contract", 2), (2,))

    def test_on_it_reports_ok_and_hash_with_contract_2(self):
        self.client.policy_check = lambda: {"ok": True, "sha256": "a" * 64}
        body = self.client._heartbeat_body()
        self.assertEqual(body["browser_contract"], 2)
        self.assertEqual(body["policy"], {"ok": True, "sha256": "a" * 64})

    def test_a_check_that_raises_or_answers_nonsense_reports_failing(self):
        def boom():
            raise RuntimeError("x")
        for check in (boom, lambda: None, lambda: {"ok": "yes"}, lambda: {"ok": 1, "sha256": 5}):
            self.client.policy_check = check
            self.assertEqual(self.client._heartbeat_body()["policy"], {"ok": False, "sha256": ""})

    def test_report_on_this_computer_never_raises(self):
        out = mp.report()
        self.assertEqual(set(out), {"ok", "sha256"})
        self.assertIsInstance(out["ok"], bool)


if __name__ == "__main__":
    unittest.main()
