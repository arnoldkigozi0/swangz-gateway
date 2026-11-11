"""Offline checks: no Chrome process, network, credentials, device policy or session."""
import copy
import importlib.util
import json
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
                           ("URLAllowlist", ["example.com"])):
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
            alias.symlink_to(out)
            with self.assertRaises(FileExistsError):
                module.write_new(alias, policy)
            self.assertEqual(json.loads(out.read_text()), policy)
            with self.assertRaises(module.PolicyPreparationError):
                module.write_new(module.TEMPLATE, policy)


if __name__ == "__main__":
    unittest.main()
