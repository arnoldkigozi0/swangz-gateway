"""D-026 E3-E5: machine-policy conflicts fail closed, the ownership hash, and controls that are not guaranteed.
Read only throughout: the stand-in registry has no write calls at all, so any attempt to write would raise."""

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swangz_client import machine_policy as mp
from tests.test_machine_policy import FakeKey, FakeRegistry, as_registry, prepare, prepared

CHROME = mp.WINDOWS_KEYS["chrome"]
REG_SZ, REG_DWORD, REG_BINARY = 1, 4, 3


class TypedKey(FakeKey):
    """A key whose values carry an explicit registry type: {name: (type, data)}."""


class TypedRegistry(FakeRegistry):
    def EnumValue(self, key, i):
        items = list(key.values.items())
        if i >= len(items):
            raise OSError("no more")
        name, value = items[i]
        if isinstance(key, TypedKey):
            return name, value[1], value[0]
        return name, value, REG_DWORD if isinstance(value, int) else REG_SZ


def registry(policy=None, marker=None, user=None, **more):
    tree = {}
    if policy is not None:
        tree[CHROME] = policy if isinstance(policy, FakeKey) else as_registry(policy)
    if marker is not None:
        tree[mp.MARKER_KEY] = FakeKey(marker)
    tree.update(more)
    return TypedRegistry(tree, user)


class Base(unittest.TestCase):
    def setUp(self):
        self.policy = prepared()

    def check(self, reg):
        return mp.check("chrome", platform="win32", registry=reg)

    def pinned(self, reg):
        """The marker Swangz would have written: the hash of the key as read back."""
        return {"sha256": mp.tree_sha(mp.read_tree(reg, reg.HKEY_LOCAL_MACHINE, CHROME)), "written": "2026-11-25"}


class StricterCheckTests(Base):
    """E3 (a), (b), (c)."""

    def test_the_pack_alone_passes(self):
        self.assertTrue(self.check(registry(self.policy)).ok)

    def test_an_extra_value_fails_as_unexpected(self):
        for name, value in (("ProxySettings", '{"ProxyMode":"direct"}'), ("CloudManagementEnrollmentToken", "t"),
                            ("ExtensionInstallSources", "x")):
            key = as_registry(self.policy)
            key.values[name] = value
            with self.subTest(name=name):
                result = self.check(registry(key))
                self.assertFalse(result.ok)
                self.assertIn("unexpected:" + name, result.problems)

    def test_an_unknown_subkey_fails_as_unexpected(self):
        key = as_registry(self.policy)
        key.subkeys["ExtensionInstallSources"] = FakeKey({"1": "https://evil.example/*"})
        result = self.check(registry(key))
        self.assertIn("unexpected:ExtensionInstallSources", result.problems)
        self.assertFalse(result.ok)

    def test_an_hkcu_value_fails_as_user_policy(self):
        user = {CHROME: FakeKey({"DeveloperToolsAvailability": 1}, {"URLAllowlist": FakeKey({"1": "*"})})}
        result = self.check(registry(self.policy, user=user))
        self.assertFalse(result.ok)
        self.assertIn("user_policy:DeveloperToolsAvailability", result.problems)
        self.assertIn("user_policy:URLAllowlist", result.problems)

    def test_an_empty_hkcu_key_does_not_fail(self):
        self.assertTrue(self.check(registry(self.policy, user={CHROME: FakeKey()})).ok)

    def test_hkcu_alone_never_passes(self):
        result = self.check(registry(None, user={CHROME: as_registry(self.policy)}))
        self.assertFalse(result.ok)
        self.assertIn("missing", result.problems)

    def test_a_non_empty_recommended_fails(self):
        key = as_registry(self.policy)
        key.subkeys["Recommended"] = FakeKey(subkeys={"URLAllowlist": FakeKey({"1": "*"})})
        self.assertIn("recommended", self.check(registry(key)).problems)

    def test_linux_unexpected_name_and_recommended_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            managed = Path(tmp) / "managed"
            managed.mkdir()
            (managed / "swangz.json").write_bytes(prepare.encode(dict(self.policy, ProxySettings={"ProxyMode": "direct"})))
            result = mp.check("chrome", platform="linux", root=managed)
            self.assertIn("unexpected:ProxySettings", result.problems)
            (managed / "swangz.json").write_bytes(prepare.encode(self.policy))
            self.assertTrue(mp.check("chrome", platform="linux", root=managed).ok)
            (Path(tmp) / "recommended").mkdir()
            self.assertTrue(mp.check("chrome", platform="linux", root=managed).ok)  # empty: nothing applies
            (Path(tmp) / "recommended" / "r.json").write_text('{"IncognitoModeAvailability": 0}')
            result = mp.check("chrome", platform="linux", root=managed)
            self.assertFalse(result.ok)
            self.assertIn("recommended", result.problems)

    def test_macos_unexpected_name(self):
        import plistlib
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "com.google.Chrome.plist").write_bytes(plistlib.dumps(dict(self.policy, ProxyMode="direct")))
            result = mp.check("chrome", platform="darwin", root=tmp)
            self.assertIn("unexpected:ProxyMode", result.problems)


class S1S2S3Tests(Base):
    """E4: #194 S1 stays done; S2 and S3."""

    def test_s1_extension_settings_stays_forbidden(self):
        self.assertIn("ExtensionSettings", mp.FORBIDDEN)
        key = as_registry(self.policy)
        key.values["ExtensionSettings"] = '{"*":{"installation_mode":"allowed"}}'
        result = self.check(registry(key))
        self.assertIn("forbidden:ExtensionSettings", result.problems)
        self.assertNotIn("unexpected:ExtensionSettings", result.problems)

    def test_s2_any_exception_from_merge_or_problems_in_is_unreadable(self):
        original = mp.merge, mp.problems_in
        for target, error in (("merge", TypeError("x")), ("problems_in", RecursionError()), ("merge", KeyError("k"))):
            with self.subTest(target=target, error=type(error).__name__):
                def boom(*a, **k):
                    raise error
                setattr(mp, target, boom)
                try:
                    result = self.check(registry(self.policy))
                finally:
                    mp.merge, mp.problems_in = original
                self.assertFalse(result.ok)
                self.assertEqual(result.problems, ["unreadable"])
                self.assertEqual(result.report(), {"ok": False, "sha256": ""})

    def test_s2_a_reader_that_raises_anything_is_unreadable(self):
        class Odd(TypedRegistry):
            def EnumValue(self, key, i):
                raise ValueError("odd")
        self.assertEqual(self.check(Odd({CHROME: as_registry(self.policy)})).problems, ["unreadable"])

    def test_s3_a_hidden_json_file_is_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "swangz.json").write_bytes(prepare.encode(self.policy))
            (Path(tmp) / ".x.json").write_text("{}")
            result = mp.check("chrome", platform="linux", root=tmp)
            self.assertFalse(result.ok)
            self.assertEqual(result.problems, ["unreadable:.x.json"])


class OwnershipTests(Base):
    """E3's hash rule, read only. Each refusing state leaves the key, any added value and the marker unchanged."""

    def snapshot(self, reg):
        return json.dumps({p: (k.values, {n: s.values for n, s in k.subkeys.items()}) for p, k in reg.tree.items()},
                          sort_keys=True, default=str)

    def test_key_absent_marker_absent_may_be_written(self):
        self.assertEqual(mp.ownership(registry()), ("absent", None))

    def test_matching_key_is_ours(self):
        reg = registry(self.policy)
        reg.tree[mp.MARKER_KEY] = FakeKey(self.pinned(reg))
        state, sha = mp.ownership(reg)
        self.assertEqual(state, "ours")
        self.assertEqual(sha, reg.tree[mp.MARKER_KEY].values["sha256"])

    def test_a_foreign_key_without_marker_is_a_conflict(self):
        reg = registry(self.policy)
        before = self.snapshot(reg)
        self.assertEqual(mp.ownership(reg)[0], "conflict")
        self.assertEqual(self.snapshot(reg), before)

    def test_a_value_changed_or_added_after_the_write_is_a_conflict_and_nothing_moves(self):
        for change in ("changed", "added", "list_entry", "subkey"):
            reg = registry(self.policy)
            reg.tree[mp.MARKER_KEY] = FakeKey(self.pinned(reg))
            key = reg.tree[CHROME]
            if change == "changed":
                key.values["DeveloperToolsAvailability"] = 1
            elif change == "added":
                key.values["ProxySettings"] = "{}"
            elif change == "list_entry":
                key.subkeys["URLAllowlist"].values["99"] = "https://evil.example"
            else:
                key.subkeys["Recommended"] = FakeKey({"x": 1})
            before = self.snapshot(reg)
            with self.subTest(change=change):
                self.assertEqual(mp.ownership(reg)[0], "conflict")
                self.assertEqual(self.snapshot(reg), before)

    def test_key_absent_marker_present_is_only_a_stale_marker(self):
        self.assertEqual(mp.ownership(registry(marker={"sha256": "a" * 64}))[0], "stale_marker")

    def test_a_marker_without_a_hash_is_a_conflict(self):
        self.assertEqual(mp.ownership(registry(self.policy, marker={"written": "x"}))[0], "conflict")

    def test_an_unreadable_key_is_unreadable(self):
        class Denied(TypedRegistry):
            def EnumKey(self, key, i):
                raise PermissionError("no")
            def EnumValue(self, key, i):
                raise ValueError("bad")
        self.assertEqual(mp.ownership(Denied({CHROME: as_registry(self.policy)}))[0], "unreadable")

    def test_a_huge_or_deep_tree_is_unreadable(self):
        deep = FakeKey()
        node = deep
        for i in range(mp.TREE_DEPTH + 2):
            node.subkeys["k"] = FakeKey()
            node = node.subkeys["k"]
        self.assertEqual(mp.ownership(registry(deep))[0], "unreadable")

    def test_the_hash_is_order_independent_and_changes_with_type_name_or_data(self):
        rows = [("", "a", REG_DWORD, 1), ("URLAllowlist", "1", REG_SZ, "https://x"), ("", "b", REG_SZ, "v")]
        base = mp.tree_sha(rows)
        self.assertEqual(mp.tree_sha(list(reversed(rows))), base)
        for changed in ([("", "a", REG_SZ, 1)] + rows[1:],                # type
                        [("", "c", REG_DWORD, 1)] + rows[1:],             # name
                        [("", "a", REG_DWORD, 0)] + rows[1:],             # data
                        [("Other", "a", REG_DWORD, 1)] + rows[1:],        # subkey path
                        rows + [("", "d", REG_SZ, "")]):                  # an added value
            self.assertNotEqual(mp.tree_sha(changed), base)

    def test_value_names_are_hashed_lowercased_and_binary_data_is_typed(self):
        a = TypedKey({"SyncDisabled": (REG_DWORD, 1), "Blob": (REG_BINARY, b"\x01")})
        b = TypedKey({"syncdisabled": (REG_DWORD, 1), "blob": (REG_BINARY, b"\x01")})
        ha = mp.tree_sha(mp.read_tree(registry(a), "HKLM", CHROME))
        self.assertEqual(ha, mp.tree_sha(mp.read_tree(registry(b), "HKLM", CHROME)))
        c = TypedKey({"SyncDisabled": (REG_DWORD, 1), "Blob": (REG_SZ, "hex:01")})
        self.assertNotEqual(ha, mp.tree_sha(mp.read_tree(registry(c), "HKLM", CHROME)))

    def test_ownership_reads_only_the_64_bit_view(self):
        reg = registry(self.policy, marker={"sha256": "x"})
        mp.ownership(reg)
        self.assertTrue(all(a == reg.KEY_READ | reg.KEY_WOW64_64KEY for a in reg.access))


class NoWriterTests(unittest.TestCase):
    """E1/E3: the app has no policy writer yet; personal devices therefore never call one. This module must stay
    read-only until D-025 point 2 exists."""

    def test_the_policy_module_never_writes_the_registry_or_files(self):
        source = Path(mp.__file__).read_text(encoding="utf-8")
        for call in ("SetValue", "CreateKey", "DeleteKey", "DeleteValue", "write_text", "write_bytes", "open(path, \"w",
                     "os.remove", "unlink", "rmtree"):
            self.assertNotIn(call, source)
        self.assertIsNone(re.search(r"open\([^)]*['\"][wa]", source))


class UnenforcedTests(Base):
    """E5: reported, never assumed."""

    OFF_STORE = "a" * 32 + ";https://ai.swangzavenue.com/extension/update.xml"
    ON_STORE = "b" * 32 + ";" + mp.WEB_STORE_UPDATE

    def test_off_store_force_install_is_not_guaranteed_on_an_unmanaged_computer(self):
        policy = {"ExtensionInstallForcelist": [self.OFF_STORE, self.ON_STORE]}
        for platform in ("win32", "darwin"):
            gaps = mp.not_guaranteed(policy, {"domain": False, "mdm": False}, platform)
            self.assertEqual(gaps["not_guaranteed"], ["ExtensionInstallForcelist:off_store:" + "a" * 32])
            self.assertFalse(gaps["enforced"])
            unknown = mp.not_guaranteed(policy, {"domain": None, "mdm": None}, platform)  # unknown = unmanaged
            self.assertEqual(unknown["not_guaranteed"], gaps["not_guaranteed"])

    def test_a_managed_computer_lists_nothing_but_is_still_not_called_enforced(self):
        policy = {"ExtensionInstallForcelist": [self.OFF_STORE]}
        for managed in ({"domain": True, "mdm": False}, {"domain": False, "mdm": True}):
            gaps = mp.not_guaranteed(policy, managed, "win32")
            self.assertEqual(gaps["not_guaranteed"], [])
            self.assertFalse(gaps["enforced"])  # only a chrome://policy acceptance check may say enforced
        self.assertEqual(mp.ACCEPTED, frozenset())

    def test_enforced_only_for_an_accepted_machine_type(self):
        gaps = mp.not_guaranteed({}, {"domain": True}, "win32", accepted={"win32:managed"})
        self.assertTrue(gaps["enforced"])

    def test_mac_management_is_read_without_privilege(self):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            out = "Enrolled via DEP: No\nMDM enrollment: Yes (User Approved)\n" if "profiles" in argv[0] else ""
            return SimpleNamespace(returncode=0, stdout=out)
        self.assertEqual(mp.management("darwin", run=run), {"domain": False, "mdm": True})
        self.assertFalse(any("sudo" in " ".join(a) for a in calls))

        def failing(argv, **kw):
            raise OSError("missing")
        self.assertEqual(mp.management("darwin", run=failing), {"domain": None, "mdm": None})

    def test_windows_management(self):
        enrol = {r"SOFTWARE\Microsoft\Enrollments": FakeKey(subkeys={"ABC": FakeKey({"ProviderID": "MS DM Server"}),
                                                                       "Context": FakeKey()})}
        reg = TypedRegistry(enrol)
        self.assertEqual(mp.management("win32", registry=reg, netjoin=lambda: True), {"domain": True, "mdm": True})
        self.assertEqual(mp.management("win32", registry=TypedRegistry({}), netjoin=lambda: False),
                         {"domain": False, "mdm": False})

        def broken():
            raise OSError("netapi")
        self.assertEqual(mp.management("win32", registry=TypedRegistry({}), netjoin=broken)["domain"], None)

    def test_setup_report_lists_gaps_conflicts_and_never_says_enforced(self):
        policy = dict(self.policy, ExtensionInstallForcelist=[self.OFF_STORE])
        reg = registry(policy)  # present, no marker: not exactly ours
        out = mp.setup_report("win32", registry=reg, netjoin=lambda: False)
        self.assertEqual(out["ownership"], "conflict")
        self.assertIn("ExtensionInstallForcelist:off_store:" + "a" * 32, out["not_guaranteed"])
        text = "\n".join(out["lines"])
        self.assertIn("Not guaranteed on this computer", text)
        self.assertIn("Nothing was changed", text)
        self.assertNotIn("Enforced", text.replace("Not yet confirmed as enforced", ""))
        self.assertFalse(out["enforced"])

    def test_linux_lists_nothing_and_has_no_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "swangz.json").write_bytes(prepare.encode(self.policy))
            out = mp.setup_report("linux", root=tmp)
        self.assertTrue(out["ok"])
        self.assertEqual(out["not_guaranteed"], [])
        self.assertNotIn("ownership", out)

    def test_the_heartbeat_report_still_has_exactly_two_fields(self):
        self.assertEqual(set(mp.check("chrome", platform="win32", registry=registry(self.policy)).report()),
                         {"ok", "sha256"})

    @unittest.skipUnless(os.name == "nt", "the real registry exists only on Windows")
    def test_the_real_windows_reads_never_raise(self):
        out = mp.setup_report()
        print("\n  management:", out["management"], "ownership:", out["ownership"])
        self.assertIn(out["ownership"], ("absent", "ours", "conflict", "stale_marker", "unreadable"))


if __name__ == "__main__":
    unittest.main()
