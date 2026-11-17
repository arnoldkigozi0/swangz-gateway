"""W7 of docs/MANAGED-WORKSPACE.md: the managed workspace leaves what a person already has exactly as it was.

Server side: a gateway API key that an automation (n8n, Make, Zapier, a script) holds and the device's own key keep
WORKING, not merely existing, before the workspace is touched, after every workspace action, and with the browser
policy failing in `enforce` mode. Their stored rows do not change by a byte. Only revoking the device or suspending
the person stops them, and each of those stops only what it names.

Device side: preparing and retiring workspace profiles touches nothing outside the app's own `browser-profiles`
folder: not the person's existing Chrome, Chromium or Edge profiles, not their coding agents' settings, not an n8n
folder. Runs on every OS of the W6 matrix.
"""

import os
import tempfile
import unittest
from pathlib import Path

from swangz_client import browser_profiles as bp

from .test_managed_workspace import Base, SHA

ACTIONS = ("suspend", "reactivate", "retire", "reactivate", "reset", "suspend", "retire")
ASK = {"model": "claude-opus-5-5", "max_tokens": 16, "messages": [{"role": "user", "content": "hello from an automation"}]}
WORKSPACE_COLUMNS = {"workspace_state", "workspace_generation", "workspace_changed", "workspace_changed_by",
                     "policy_ok", "policy_sha", "policy_reported", "policy_source", "last_seen", "seen_ip", "app_version"}


def _gateway_timezone_available():
    """The gateway is a Linux server. Windows Python ships no time-zone database unless the third-party `tzdata`
    package is installed, and the gateway's settings need one, so the server half of W7 runs on Linux and macOS."""
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Africa/Kampala")
        return True
    except Exception:
        return False


@unittest.skipUnless(_gateway_timezone_available(), "the gateway needs a time-zone database (Windows has none without tzdata); "
                     "the gateway runs on Linux, so this server check is proven on the Linux and macOS runners")
class ServerKeysAndAutomationsTests(Base):
    def setUp(self):
        super().setUp()
        status, out = self.rig.api("POST", f"/people/{self.rig.person_id}/keys", {"label": "n8n automation", "tool_id": ""})
        self.assertEqual(status, 200, out)
        self.automation_key, self.automation_id = out["key"], out["id"]

    def keys(self):
        """Every stored field except `last_used`, which a working key is expected to move."""
        return [{k: v for k, v in r.items() if k != "last_used"} for r in self.db.q("SELECT * FROM keys ORDER BY id")]

    def device_row(self):
        row = dict(self.db.one("SELECT * FROM devices WHERE device_id = ?", (self.did,)))
        return {k: v for k, v in row.items() if k not in WORKSPACE_COLUMNS}

    def assert_everything_works(self, when):
        for key in (self.automation_key, self.rig.key):
            status, _, payload = self.rig.anthropic(ASK, key=key)
            self.assertEqual(status, 200, f"{when}: {payload[:200]!r}")
        status, _, _ = self.rig.openai("/chat/completions", {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]},
                                       key=self.automation_key)
        self.assertEqual(status, 200, when)
        self.assertEqual(self.beat({"browser_contract": 2})[0], 200, when)
        self.assertEqual(self.api("GET", "/device/manifest", key=self.key)[0], 200, when)

    def test_keys_and_the_device_work_before_and_after_every_workspace_action(self):
        keys, device = self.keys(), self.device_row()
        self.assert_everything_works("before the workspace was touched")
        for n, action in enumerate(ACTIONS):
            status, out = self.workspace(action)
            self.assertEqual(status, 200, (action, out))
            self.assert_everything_works(f"after {action} (step {n})")
            self.assertEqual(self.keys(), keys, f"a key row changed after {action}")
            self.assertEqual(self.device_row(), device, f"the device row changed outside the workspace columns after {action}")

    def test_a_failing_policy_report_in_enforce_mode_stops_no_key(self):
        self.db.set_setting("managed_policy_mode", "enforce")
        self.db.set_setting("managed_policy_sha256", SHA)
        keys = self.keys()
        status, _ = self.beat({"browser_contract": 2, "policy": {"ok": False, "sha256": "c" * 64}})
        self.assertEqual(status, 200)
        self.assert_everything_works("with the policy failing in enforce mode")
        self.assertEqual(self.keys(), keys)

    def test_workspace_actions_write_no_key_audit_line(self):
        for action in ACTIONS:
            self.workspace(action)
        lines = self.db.q("SELECT action FROM audit WHERE correlation = ?", (f"device:{self.did}",))
        self.assertTrue(lines)
        self.assertTrue(all(r["action"].endswith(" the workspace on a device") for r in lines), [r["action"] for r in lines])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE action LIKE '%revoked%'"), 0)

    def test_revoking_the_device_stops_the_device_only(self):
        self.workspace("suspend")
        status, out = self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")
        self.assertEqual(status, 200, out)
        self.assertEqual(self.beat()[0], 401)
        for key in (self.automation_key, self.rig.key):
            self.assertEqual(self.rig.anthropic(ASK, key=key)[0], 200, "revoking one device left the automation keys working")

    def test_suspending_the_person_stops_their_automation_keys(self):
        status, out = self.rig.api("POST", f"/people/{self.rig.person_id}/suspend")
        self.assertEqual(status, 200, out)
        self.assertNotEqual(self.rig.anthropic(ASK, key=self.automation_key)[0], 200)
        self.rig.api("POST", f"/people/{self.rig.person_id}/resume")
        self.assertEqual(self.rig.anthropic(ASK, key=self.automation_key)[0], 200, "resuming the person brings the same key back")


def snapshot(root):
    out = {}
    for path in sorted(Path(root).rglob("*")):
        rel = path.relative_to(root).as_posix()
        st = path.lstat()
        out[rel] = ("dir", None, st.st_mtime_ns) if path.is_dir() else ("file", path.read_bytes(), st.st_mtime_ns)
    return out


# What a person typically already has on each OS, in the places those programs really keep it.
EXISTING = {
    "linux": [".config/google-chrome/Default/Preferences", ".config/google-chrome/Profile 1/Bookmarks",
              ".config/chromium/Default/Preferences", ".config/microsoft-edge/Default/Preferences"],
    "darwin": ["Library/Application Support/Google/Chrome/Default/Preferences",
               "Library/Application Support/Google/Chrome/Profile 1/Bookmarks", "Library/Application Support/Chromium/Default/Preferences"],
    "win32": ["AppData/Local/Google/Chrome/User Data/Default/Preferences", "AppData/Local/Google/Chrome/User Data/Profile 1/Bookmarks",
              "AppData/Local/Microsoft/Edge/User Data/Default/Preferences"],
}
AUTOMATIONS = [".n8n/config", ".n8n/database.sqlite", ".claude/settings.json", ".codex/config.toml", "make-scenarios/export.json",
               "zapier/cli.json"]


class DeviceExistingContextsTests(unittest.TestCase):
    """The app's data folder sits next to the person's own files in a temporary home; the home is compared byte for
    byte (and by modification time) before and after every workspace operation."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        files = [f for group in EXISTING.values() for f in group] + AUTOMATIONS
        for i, rel in enumerate(files):
            path = self.home / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{rel} belongs to the person {i}".encode())
        self.data = self.home / "swangz-data"
        self.data.mkdir(mode=0o700)
        self.profiles = bp.Profiles(self.data)
        self.owner = bp.Owner("https://hub.example", "person_7", "device-1")

    def outside(self):
        snap = snapshot(self.home)
        return {k: v for k, v in snap.items() if not (k == "swangz-data" or k.startswith("swangz-data/"))}

    def test_preparing_and_retiring_the_workspace_touches_nothing_outside_its_folder(self):
        before = self.outside()
        self.assertGreaterEqual(len(before), len(AUTOMATIONS) + 10)
        profile = self.profiles.prepare(self.owner)
        self.assertEqual(profile.parent, self.data / "browser-profiles")
        self.assertEqual(self.outside(), before, "prepare")
        self.assertEqual(self.profiles.prepare(self.owner), profile)  # a second Open reuses it
        self.assertEqual(self.outside(), before, "second prepare")
        self.profiles.prepare(bp.Owner("https://hub.example", "person_8", "device-1"))
        if os.name == "nt":  # retiring is refused on Windows and reported, never half done
            out = self.profiles.retire_owner(self.owner)
            self.assertFalse(out["complete"])
            self.assertIn({"name": profile.name, "reason": "unsupported_platform"}, out["skipped"])
            self.assertTrue(profile.exists())
        else:
            out = self.profiles.retire_owner(self.owner)
            self.assertEqual(out["retired"], [profile.name])
            self.assertFalse(profile.exists())
            self.assertTrue(self.profiles.retire_all()["complete"])
        self.assertEqual(self.outside(), before, "retire")

    def test_existing_browser_profiles_inside_the_data_folder_are_not_adopted(self):
        """A folder someone copied into the app's root is not this person's workspace and is never handed out."""
        root = self.data / "browser-profiles"
        self.profiles.prepare(self.owner)
        stranger = root / "Default"
        stranger.mkdir()
        (stranger / "Preferences").write_text("{}")
        profile = self.profiles.prepare(self.owner)
        self.assertNotEqual(profile.name, "Default")
        self.assertEqual((stranger / "Preferences").read_text(), "{}")
        if os.name != "nt":
            out = self.profiles.retire_owner(self.owner)
            self.assertIn({"name": "Default", "reason": "unknown_entry"}, out["skipped"])
            self.assertTrue((stranger / "Preferences").exists(), "an unknown folder is skipped, never deleted")


if __name__ == "__main__":
    unittest.main()
