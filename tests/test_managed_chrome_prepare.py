"""Offline checks: no Chrome process, network, credentials, device policy or session."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "deploy" / "chrome-policy" / "prepare.py"
spec = importlib.util.spec_from_file_location("swangz_chrome_prepare", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ManagedChromePreparationTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads(module.TEMPLATE.read_text(encoding="utf-8"))
        self.hub = "ai.swangzavenue.com"
        self.ext = "a" * 32
        self.update = "https://clients2.google.com/service/update2/crx"

    def render(self, **changes):
        p = {"template": self.template, "hub_host": self.hub, "extension_id": self.ext,
             "extension_update_url": self.update}
        p.update(changes)
        return module.prepare(**p)

    def test_fills_only_expected_placeholders_without_mutating_template(self):
        original = copy.deepcopy(self.template)
        value = self.render()
        self.assertEqual(value["URLAllowlist"][0], self.hub)
        self.assertEqual(value["ExtensionInstallAllowlist"], [self.ext])
        self.assertEqual(value["ExtensionInstallForcelist"], [self.ext + ";" + self.update])
        self.assertEqual(value["BrowserAddPersonEnabled"], False)
        self.assertEqual(value["BrowserGuestModeEnabled"], False)
        self.assertEqual(value["SyncDisabled"], True)
        self.assertEqual(self.template, original)
        self.assertNotIn("SWANGZ_", json.dumps(value))

    def test_rejects_malformed_hub_hosts(self):
        invalid = ("example.com", "localhost", "internal.local", "ai.swangzavenue.com:443",
                   "https://ai.swangzavenue.com", "*.swangzavenue.com", "ai.swangzavenue.com/path",
                   " ai.swangzavenue.com", "AI.swangzavenue.com", "my@swangzavenue.com",
                   "12.34.56.78", "-bad.swangzavenue.com", "test..com", "evil.com\n*.site")
        for host in invalid:
            with self.subTest(host=host), self.assertRaises(module.PolicyPreparationError):
                self.render(hub_host=host)

    def test_rejects_malformed_extension_id_and_update_url(self):
        for ext in ("SWANGZ_EXTENSION_ID", "z" * 32, "A" * 32, "a" * 31, "a" * 32 + ";evil"):
            with self.subTest(ext=ext), self.assertRaises(module.PolicyPreparationError):
                self.render(extension_id=ext)
        for url in ("http://clients2.google.com/service/update2/crx", "file:///tmp/update.xml",
                    "https://user:secret@updates.example.org/check", "https://host.com/",
                    "https://host.com/file?token=abc", "https://host.com/file#fragment",
                    "https://host.com:8443/file", "https://localhost/update.xml",
                    "https://127.0.0.1/update.xml", "https://host.com/evil\\escape"):
            with self.subTest(url=url), self.assertRaises(module.PolicyPreparationError):
                self.render(extension_update_url=url)

    def test_fails_closed_if_essential_policy_disabled_or_placeholders_changed(self):
        for key, value in (("BrowserAddPersonEnabled", True), ("BrowserSignin", 1),
                           ("RemoteDebuggingAllowed", True), ("SyncDisabled", False),
                           ("ExtensionInstallBlocklist", []), ("URLBlocklist", []),
                           ("ExtensionInstallForcelist", ["something"]),
                           ("URLAllowlist", ["example.com"]),
                           ("AutoLaunchProtocolsFromOrigins", ["https://evil.example.net"]),
                           ("ExternalProtocolDialogShowAlwaysOpenCheckbox", True)):
            with self.subTest(key=key), self.assertRaises(module.PolicyPreparationError):
                x = copy.deepcopy(self.template)
                x[key] = value
                self.render(template=x)

    def test_refuses_overwrite_or_symlink_and_writes_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "prepared.json"
            policy = self.render()
            module.write_new(out, policy)
            self.assertEqual(json.loads(out.read_text()), policy)
            with self.assertRaises(FileExistsError):
                module.write_new(out, policy)
            alias = Path(d) / "alias.json"
            try:
                alias.symlink_to(out)
            except (OSError, NotImplementedError):
                pass  # Some Windows machines deny creating symlinks for standard accounts.
            else:
                with self.assertRaises(FileExistsError):
                    module.write_new(alias, policy)
            self.assertEqual(json.loads(out.read_text()), policy)
            with self.assertRaises(module.PolicyPreparationError):
                module.write_new(module.TEMPLATE, policy)

    def test_every_d016_setting_is_pinned_and_removing_one_refuses_to_prepare(self):
        for name in ("AutoLaunchProtocolsFromOrigins", "ExternalProtocolDialogShowAlwaysOpenCheckbox"):
            self.assertIn(name, module.REQUIRED)
            x = copy.deepcopy(self.template)
            del x[name]
            with self.subTest(name=name), self.assertRaises(module.PolicyPreparationError):
                self.render(template=x)
        for entry in ("chrome://*", "view-source:*", "file://*"):
            self.assertIn(entry, module.REQUIRED_BLOCKS)
            x = copy.deepcopy(self.template)
            x["URLBlocklist"].remove(entry)
            with self.subTest(entry=entry), self.assertRaises(module.PolicyPreparationError):
                self.render(template=x)
        self.assertEqual(self.render()["AutoLaunchProtocolsFromOrigins"], [])

    def test_refuses_every_active_policy_folder_on_linux_and_macos(self):
        for folder in module.ACTIVE_POLICY_FOLDERS:
            for path in (folder + "/swangz.json", folder + "/sub/swangz.json"):
                with self.subTest(path=path):
                    self.assertTrue(module.is_protected_location(path, windows=False))
        for folder in ("/etc/opt/chrome/policies/recommended", "/etc/chromium/policies/recommended"):
            self.assertIn(folder, module.ACTIVE_POLICY_FOLDERS)
        self.assertFalse(module.is_protected_location("/home/x/prepared.json", windows=False))
        self.assertFalse(module.is_protected_location("/etc/opt/chrome/policies/managed-copy/a.json", windows=False))

    def test_refuses_windows_system_folders_whatever_the_case(self):
        env = {"ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "C:\\Program Files (x86)",
               "WINDIR": "C:\\Windows", "SystemRoot": "C:\\Windows"}
        for path in ("C:\\Windows\\System32\\a.json", "c:\\windows\\a.json", "C:\\Program Files\\Google\\Chrome\\a.json",
                     "C:\\PROGRAM FILES (X86)\\x\\a.json"):
            with self.subTest(path=path):
                self.assertTrue(module.is_protected_location(path, windows=True, environ=env))
        for path in ("C:\\Users\\admin\\prepared.json", "D:\\policy\\prepared.json",
                     "C:\\Program Files Backup\\a.json"):
            with self.subTest(path=path):
                self.assertFalse(module.is_protected_location(path, windows=True, environ=env))
        # Without the variables the usual defaults still protect the system folders.
        self.assertTrue(module.is_protected_location("C:\\Windows\\a.json", windows=True, environ={}))

    def test_write_new_returns_the_sha256_of_the_exact_bytes(self):
        policy = self.render()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "prepared.json"
            digest = module.write_new(out, policy)
            self.assertEqual(digest, hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(digest, hashlib.sha256(module.encode(policy)).hexdigest())
            other = Path(d) / "other.json"
            self.assertEqual(module.write_new(other, policy), digest)  # same input, same hash

    def test_the_command_prints_the_hash_and_still_installs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "prepared.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = module.main(["--hub-host", self.hub, "--extension-id", self.ext,
                                    "--update-url", self.update, "--output", str(out)])
            self.assertEqual(code, 0)
            line = [l for l in buf.getvalue().splitlines() if l.startswith("SHA-256 of the prepared file: ")]
            self.assertEqual(len(line), 1)
            self.assertEqual(line[0].rsplit(": ", 1)[1], hashlib.sha256(out.read_bytes()).hexdigest())
            if os.name != "nt":
                self.assertEqual(out.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
