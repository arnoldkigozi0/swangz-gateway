"""The Chrome policy pack for company devices (deploy/chrome-policy): its shape, not Chrome's behaviour."""

import json
import os
import re
import unittest

from gateway import catalog

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "chrome-policy")
PATH = os.path.join(HERE, "swangz-company-chrome.json")
KNOWN = {"URLBlocklist", "URLAllowlist", "BrowserSignin", "SyncDisabled", "BrowserAddPersonEnabled",
         "BrowserGuestModeEnabled", "IncognitoModeAvailability", "DeveloperToolsAvailability", "RemoteDebuggingAllowed",
         "PasswordManagerEnabled", "ExtensionInstallBlocklist", "ExtensionInstallAllowlist", "ExtensionInstallForcelist"}
SIGN_IN = {".accounts.google.com", ".accounts.youtube.com", "login.microsoftonline.com", "login.live.com",
           "appleid.apple.com", "github.com/login", "github.com/session", "github.com/sessions",
           "www.google.com/recaptcha", "challenges.cloudflare.com"}
EXTENSION = re.compile(r"SWANGZ_EXTENSION_ID|[a-p]{32}")


class ChromePolicyPackTests(unittest.TestCase):
    def setUp(self):
        with open(PATH, encoding="utf-8") as f:
            self.policy = json.load(f)

    def test_only_known_policy_names_with_the_right_types(self):
        self.assertEqual(set(self.policy), KNOWN)
        for name, value in self.policy.items():
            if name.startswith(("URL", "ExtensionInstall")):
                self.assertTrue(value and all(isinstance(v, str) and v == v.strip() and v for v in value), name)
                self.assertEqual(len(value), len(set(value)), name)

    def test_navigation_is_default_deny(self):
        self.assertIn("*", self.policy["URLBlocklist"])
        self.assertIn("file://*", self.policy["URLBlocklist"])
        for entry in self.policy["URLAllowlist"]:
            self.assertNotIn("*", entry, "an allow entry never carries a wildcard")
            self.assertNotRegex(entry, r"^(file|chrome|javascript|data)\b", entry)
            self.assertNotRegex(entry.split("/")[0], r"^[0-9.]+$", "no bare addresses")

    def test_every_catalogue_provider_host_is_allowed_and_nothing_else(self):
        hosts = set()
        for row in catalog.SEED:
            hosts.update(dict(zip(catalog.FIELDS, row))["hosts"])
        self.assertTrue(hosts)
        self.assertEqual(set(self.policy["URLAllowlist"]), hosts | SIGN_IN | {"SWANGZ_HUB_HOST"})

    def test_google_is_reachable_only_for_sign_in_and_tools_in_the_catalogue(self):
        google = {e for e in self.policy["URLAllowlist"] if re.search(r"(google|youtube|gmail)\.", e)}
        self.assertEqual(google, {".accounts.google.com", ".accounts.youtube.com", "www.google.com/recaptcha",
                                  "gemini.google.com"})
        for surface in ("google.com", "mail.google.com", "gmail.com", "myaccount.google.com", "drive.google.com",
                        "youtube.com", ".google.com"):
            self.assertNotIn(surface, self.policy["URLAllowlist"])

    def test_browser_sign_in_sync_and_extra_profiles_are_off(self):
        expect = {"BrowserSignin": 0, "SyncDisabled": True, "BrowserAddPersonEnabled": False,
                  "BrowserGuestModeEnabled": False, "IncognitoModeAvailability": 1, "DeveloperToolsAvailability": 2,
                  "RemoteDebuggingAllowed": False, "PasswordManagerEnabled": False}
        for name, value in expect.items():
            self.assertIs(type(self.policy[name]), type(value), name)
            self.assertEqual(self.policy[name], value, name)

    def test_only_the_swangz_extension_and_it_is_forced(self):
        self.assertEqual(self.policy["ExtensionInstallBlocklist"], ["*"])
        (allowed,) = self.policy["ExtensionInstallAllowlist"]
        (forced,) = self.policy["ExtensionInstallForcelist"]
        self.assertRegex(allowed, f"^({EXTENSION.pattern})$")
        ext, _, update = forced.partition(";")
        self.assertEqual(ext, allowed)
        self.assertRegex(update, r"^(SWANGZ_EXTENSION_UPDATE_URL|https://[^\s;]+)$")

    def test_the_readme_names_every_policy_and_says_what_is_untested(self):
        with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
            text = f.read()
        for name in KNOWN:
            self.assertIn(name.replace("ExtensionInstallAllowlist", "allow list").replace(
                "ExtensionInstallForcelist", "force list"), text, name)
        for phrase in ("company", "not been installed on a real device", "What it cannot do", "SWANGZ_EXTENSION_ID",
                       "SWANGZ_HUB_HOST"):
            self.assertIn(phrase, text)

    def test_nothing_applies_the_pack_by_itself(self):
        root = os.path.dirname(os.path.dirname(HERE))
        for folder in ("gateway", "swangz_client", "workspace_agent", "deploy"):
            for base, _, names in os.walk(os.path.join(root, folder)):
                for name in names:
                    if name.endswith((".py", ".sh", ".ps1", ".service")):
                        with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
                            source = f.read()
                        if folder == "deploy" and name == "prepare.py" and os.path.basename(base) == "chrome-policy":
                            # Explicit offline preparation is allowed; automatic policy install remains forbidden.
                            self.assertIn("O_EXCL", source)
                            self.assertIn("Refusing direct writes to active system Chrome policy locations", source)
                            self.assertNotIn("subprocess", source)
                        else:
                            self.assertNotIn("swangz-company-chrome", source, name)


if __name__ == "__main__":
    unittest.main()
