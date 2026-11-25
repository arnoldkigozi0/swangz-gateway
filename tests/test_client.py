"""The Swangz app's core, driven against a real running gateway: sign in with a code, what gets installed on a
personal and on a company device, removal, revocation, and the ways a package or manifest could be hostile."""

import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from gateway import enroll
from swangz_client import __version__, agents, browser_profiles as bp, bundles, cli, core, keystore, shell

from .test_devices import DeviceBase, make_zip


class ClientBase(DeviceBase):
    owner = "personal"

    def setUp(self):
        super().setUp()
        # Never touch the test runner's real credential service.
        backend_patch = patch.object(keystore, "put", side_effect=keystore.Unavailable("fixture has no keychain"))
        backend_patch.start()
        self.addCleanup(backend_patch.stop)
        # Fixture-only configuration coverage; no claim about the real Claude binary's prefix handling.
        gate_patch = patch.object(agents, "CLAUDE_PREFIX_VERIFIED", True)
        gate_patch.start()
        self.addCleanup(gate_patch.stop)
        self.server = f"http://127.0.0.1:{self.rig.port}"
        self.rig.gw.settings.public_url = self.server  # so the links in what the server says are ones the client can reach
        self.root = Path(tempfile.mkdtemp(prefix="sgw-client-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home, self.data = self.root / "home", self.root / "data"
        self.home.mkdir()
        self.opened = []
        self.client = self.make_client()
        self.gw = self.rig.gw

    def make_client(self, **kw):
        return core.Client(core.Paths(self.home, self.data), sleep=lambda s: None, open_url=self.browser, **kw)

    def browser(self, url):
        """What the person does in their browser: look at the page and press Approve."""
        self.opened.append(url)
        if "/device" in url:
            code = parse_qs(urlsplit(url).query)["code"][0]
            status, text, _ = self.approve(code, self.owner)
            assert status == 200, text

    def sign_in(self, owner=None):
        if owner:
            self.owner = owner
        return self.client.login(self.server, "Grace's laptop")

    def tamper_entitlement(self, tool, give):
        if give:
            self.gw.db.x("INSERT OR IGNORE INTO entitlements(tool_id, person_id, granted) VALUES(?,?,?)", (tool, self.rig.person_id, time.time()))
        else:
            self.gw.db.x("DELETE FROM entitlements WHERE tool_id = ?", (tool,))


class SignInTests(ClientBase):
    def test_signing_in_stores_the_key_privately_and_nothing_else_leaks_it(self):
        info = self.sign_in()
        self.assertEqual((info["person"]["name"], info["owner_kind"], info["server"]), ("Nansubuga Grace", "personal", self.server))
        key = (self.data / "device.key").read_text().strip()
        self.assertTrue(key.startswith("sgw_"))
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE((self.data / "device.key").stat().st_mode), 0o600)
        self.assertNotIn(key, (self.data / "device.json").read_text())
        self.assertEqual(len(self.opened), 1)
        self.assertIn("/device?code=", self.opened[0])
        self.assertTrue(self.client.signed_in())

    def test_the_code_is_shown_to_the_person(self):
        shown = []
        self.client.login(self.server, "x", on_code=lambda code, url: shown.append((code, url)))
        self.assertRegex(shown[0][0], r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")
        self.assertIn(shown[0][0], shown[0][1])

    def test_a_refused_or_expired_sign_in_fails_cleanly(self):
        self.client.open_url = lambda url: self.approve(parse_qs(urlsplit(url).query)["code"][0], decision="deny")
        with self.assertRaises(core.ApiFailure) as caught:
            self.client.login(self.server, "x")
        self.assertEqual(caught.exception.code, "access_denied")
        self.assertFalse(self.client.signed_in())
        self.client.open_url = lambda url: None
        with self.assertRaises(core.ApiFailure) as caught:
            self.client.login(self.server, "x", timeout=0)
        self.assertEqual(caught.exception.code, "expired_token")

    def test_a_dropped_connection_while_waiting_does_not_end_the_sign_in(self):
        """Seen on a lossy Wi-Fi: one timed-out poll ended the sign-in, and the code approved a moment later was never
        collected. Waiting rides out dropped connections until the code expires."""
        real, drops = self.client._api_factory, {"left": 2}

        def factory(server):
            api = real(server)
            call = api.call

            def flaky(method, path, *a, **kw):
                if path == "/device/token" and drops["left"]:
                    drops["left"] -= 1
                    raise core.ApiFailure(0, "offline", f"Couldn't reach {server} (timed out).")
                return call(method, path, *a, **kw)
            api.call = flaky
            return api
        self.client._api_factory = factory
        info = self.client.login(self.server, "Grace's laptop")
        self.assertEqual(drops["left"], 0)
        self.assertEqual(info["owner_kind"], "personal")
        self.assertTrue(self.client.signed_in())
        self.assertEqual(self.gw.db.scalar("SELECT COUNT(*) FROM devices"), 1)

    def test_cancelling_stops_waiting(self):
        self.client.open_url = lambda url: None
        with self.assertRaises(core.ApiFailure) as caught:
            self.client.login(self.server, "x", cancelled=lambda: True)
        self.assertEqual(caught.exception.code, "cancelled")

    def test_server_addresses_are_checked(self):
        self.assertEqual(core.normalise_server("ai.swangzavenue.com/"), "https://ai.swangzavenue.com")
        self.assertEqual(core.normalise_server("http://localhost:8787"), "http://localhost:8787")
        for bad in ("", "ftp://x.com", "http://ai.swangzavenue.com", "https://user:pw@x.com", "https://x.com/path", "https://x.com?q=1", "https://"):
            with self.assertRaises(ValueError, msg=bad):
                core.normalise_server(bad)

    def test_moving_to_a_new_server_address_means_signing_out_then_connecting_again(self):
        """docs/SERVER-DAY.md step 9: an enrolled app keeps its server address and has no command to change it."""
        self.sign_in()
        old_key = (self.data / "device.key").read_text().strip()
        moved = f"http://localhost:{self.rig.port}"  # the same rig under a second address stands in for the new server
        with self.assertRaisesRegex(ValueError, "Sign out of this device before connecting it again"):
            self.client.login(moved, "Grace's laptop")
        self.assertEqual((len(self.opened), self.client.status()["server"]), (1, self.server))  # nothing was asked of the new one
        self.assertTrue(self.client.logout())  # the old server is told, so the old key stops working there
        self.assertEqual(self.gw.db.scalar("SELECT COUNT(*) FROM keys WHERE revoked IS NULL AND device_id IS NOT NULL"), 0)
        self.rig.gw.settings.public_url = moved
        info = self.client.login(moved, "Grace's laptop")
        self.assertEqual((info["server"], self.client.status()["server"]), (moved, moved))
        self.assertNotEqual((self.data / "device.key").read_text().strip(), old_key)

    def test_not_signed_in_means_not_signed_in(self):
        with self.assertRaises(core.NotSignedIn):
            self.client.sync()
        self.assertFalse(self.client.status()["signed_in"])


class PersonalDeviceTests(ClientBase):
    def test_a_personal_device_changes_nothing_outside_swangz_s_own_folder(self):
        self.sign_in("personal")
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text('{"theme": "mine"}')
        before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))
        out = self.client.sync()
        results = {pid: outcome for pid, outcome, _ in out["results"]}
        self.assertEqual(results, {"claude-code": "installed", "codex": "installed", "access-gate": "installed"})
        self.assertEqual(sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*")), before)
        self.assertEqual((self.home / ".claude" / "settings.json").read_text(), '{"theme": "mine"}')
        self.assertFalse((self.home / ".codex").exists())
        self.assertFalse((self.home / ".profile").exists())
        gate = next(self.data.glob("extension/access-gate/*/manifest.json"))
        self.assertEqual(json.loads(gate.read_text())["manifest_version"], 3)

    def test_the_agents_run_through_the_gateway_for_that_one_run(self):
        self.sign_in("personal")
        self.client.sync()
        key = (self.data / "device.key").read_text().strip()
        argv, env = self.client.agent_command("claude-code", ["--resume"])
        self.assertEqual(argv, ["claude", "--resume"])
        self.assertEqual((env["ANTHROPIC_BASE_URL"], env["ANTHROPIC_AUTH_TOKEN"]), (self.server + "/anthropic", key))
        argv, env = self.client.agent_command("codex", ["exec", "hi"])
        self.assertEqual(env["SWANGZ_AI_KEY"], key)
        self.assertIn(f'model_providers.swangz.base_url="{self.server}/openai/v1"', argv)
        self.assertEqual(argv[-2:], ["exec", "hi"])
        self.assertNotIn(key, " ".join(argv))  # never on a command line, where `ps` shows it

    def test_running_an_agent_that_is_not_installed_says_how(self):
        self.sign_in()
        self.client.sync()
        with self.assertRaises(FileNotFoundError) as caught:
            self.client.run = lambda *a, **k: SimpleNamespace(returncode=0)
            old = os.environ["PATH"]
            os.environ["PATH"] = ""
            try:
                self.client.run_agent("claude-code")
            finally:
                os.environ["PATH"] = old
        self.assertIn("npm install -g @anthropic-ai/claude-code", str(caught.exception))

    def test_running_an_agent_that_was_not_offered_is_refused(self):
        self.tamper_entitlement("codex", False)
        self.sign_in()
        self.client.sync()
        with self.assertRaises(core.NotSignedIn):
            self.client.agent_command("codex")

    def test_the_server_sees_the_device_check_in(self):
        info = self.sign_in()
        self.client.sync()
        row = self.gw.db.one("SELECT * FROM devices WHERE key_id = ?", (info["key_id"],))
        self.assertEqual(row["app_version"], __version__)
        self.assertEqual(sorted(p["id"] for p in json.loads(row["packages_json"])), ["access-gate", "claude-code", "codex"])

    def test_a_second_sync_changes_nothing_and_force_redoes_it(self):
        self.sign_in()
        self.client.sync()
        self.assertEqual({o for _, o, _ in self.client.sync()["results"]}, {"current"})
        self.assertEqual({o for _, o, _ in self.client.sync(force=True)["results"]}, {"updated"})

    def test_what_the_window_shows(self):
        self.sign_in()
        self.client.sync()
        rows = {r["id"]: r for r in self.client.packages()}
        self.assertEqual({r["state"] for r in rows.values()}, {"installed"})
        self.assertEqual(rows["claude-code"]["mode"], "scoped")
        status = self.client.status()
        self.assertEqual((status["signed_in"], status["person"]["name"], status["update_available"]), (True, "Nansubuga Grace", False))
        self.assertIn("never reads your files", status["recording"])

    def test_apps_open_through_swangz(self):
        self.gw.db.x("INSERT INTO subscriptions(tool_id, state, updated) VALUES('canva', 'active', ?) ON CONFLICT(tool_id) DO UPDATE SET state = 'active'", (time.time(),))
        self.tamper_entitlement("canva", True)
        self.sign_in()
        self.client.sync()
        # Section 9.1: a tool opens only in the Swangz workspace window; without one nothing opens, never the default browser.
        from swangz_client import workspace_launcher as wl
        before = list(self.opened)
        with patch.object(self.client.store, "manifest", return_value={**(self.client.store.manifest() or {}), "browser": {"contract": 1}}):
            with self.assertRaises(wl.LaunchError):
                self.client.open_app("canva")
        self.assertEqual(self.opened, before)
        with self.assertRaises(wl.LaunchError) as ctx:  # not in this person's list: refused in plain words
            self.client.open_app("chatgpt")
        self.assertEqual(ctx.exception.code, "unavailable")
        self.assertEqual(self.opened, before)


class CompanyDeviceTests(ClientBase):
    owner = "company"

    def setUp(self):
        super().setUp()
        self.claude = self.home / ".claude" / "settings.json"
        self.codex = self.home / ".codex" / "config.toml"
        self.claude.parent.mkdir()
        self.codex.parent.mkdir()
        self.claude_original = json.dumps({"theme": "dark", "env": {"EDITOR": "vim"}}, indent=2) + "\n"
        self.codex_original = '# my codex\nmodel = "o3"\n\n[tui]\nnotifications = true\n'
        self.claude.write_text(self.claude_original)
        self.codex.write_text(self.codex_original)
        self.sign_in("company")

    def test_agents_are_pointed_at_the_gateway_and_keep_everything_else(self):
        self.client.sync()
        key = (self.data / "device.key").read_text().strip()
        settings = json.loads(self.claude.read_text())
        self.assertEqual((settings["theme"], settings["env"]["EDITOR"]), ("dark", "vim"))
        self.assertEqual(settings["env"]["ANTHROPIC_BASE_URL"], self.server + "/anthropic")
        self.assertIn("key --for claude-code", settings["apiKeyHelper"])
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", settings["env"])
        self.assertNotIn(key, self.claude.read_text())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.claude.stat().st_mode), 0o600)
        self.assertEqual((self.data / "backups" / "claude-settings.json.orig").read_text(), self.claude_original)
        toml = self.codex.read_text()
        if sys.version_info < (3, 11):
            self.assertEqual(toml, self.codex_original)
            record = self.client.status()["installed"]["codex"]
            self.assertEqual(record["mode"], "scoped")
            self.assertTrue(record["gated"])
            self.assertFalse((self.home / ".profile").exists())
            self.assertFalse((self.data / "backups" / "codex-config.toml.orig").exists())
            argv, env = self.client.agent_command("codex")
            self.assertEqual(argv, ["codex", *agents.codex_overrides(self.server + "/openai/v1")])
            self.assertEqual(env["SWANGZ_AI_KEY"], key)
            return
        self.assertTrue(toml.startswith(agents.BEGIN))
        self.assertIn(f'base_url = "{self.server}/openai/v1"', toml)
        self.assertTrue(toml.endswith(self.codex_original))
        self.assertNotIn(key, toml)  # Codex reads the key from the environment
        if os.name == "posix":
            profile = (self.home / ".profile").read_text()
            self.assertIn("SWANGZ_AI_KEY", profile)
            self.assertNotIn(key, profile)  # it reads our private key file
            self.assertIn("key --for codex", profile)
            self.assertNotIn("device.key", profile)
        self.assertEqual((self.data / "backups" / "codex-config.toml.orig").read_text(), self.codex_original)
        argv, _ = self.client.agent_command("codex")
        self.assertEqual(argv, ["codex"])  # no overrides needed: the config does it

    def test_taking_a_right_away_puts_that_tool_s_settings_back(self):
        self.client.sync()
        self.tamper_entitlement("codex", False)
        results = {pid: o for pid, o, _ in self.client.sync()["results"]}
        self.assertEqual(results["codex"], "removed")
        self.assertEqual(self.codex.read_text(), self.codex_original)
        if os.name == "posix":
            profile = self.home / ".profile"
            if sys.version_info < (3, 11):
                self.assertFalse(profile.exists())
            else:
                self.assertNotIn("SWANGZ_AI_KEY", profile.read_text())
        self.assertIn("ANTHROPIC_BASE_URL", self.claude.read_text())  # Claude Code is still offered

    def test_signing_out_restores_the_settings_and_keeps_what_the_person_changed_since(self):
        self.client.sync()
        settings = json.loads(self.claude.read_text())
        settings["model"] = "added-by-person-later"
        settings["env"]["ANTHROPIC_BASE_URL"] = "https://their-own-proxy.example"  # they repointed it themselves
        self.claude.write_text(json.dumps(settings))
        self.assertTrue(self.client.logout())
        after = json.loads(self.claude.read_text())
        self.assertEqual(after["model"], "added-by-person-later")
        self.assertEqual(after["env"]["ANTHROPIC_BASE_URL"], "https://their-own-proxy.example")  # not ours any more: kept
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", after["env"])
        self.assertEqual(after["env"]["EDITOR"], "vim")
        self.assertEqual(self.codex.read_text(), self.codex_original)
        self.assertFalse(self.client.signed_in())
        self.assertFalse(list(self.data.glob("device.*")))

    def test_settings_that_cannot_be_read_safely_are_left_alone(self):
        self.claude.write_text("{ not json")
        self.codex.write_text('model_provider = "mine"\n')
        results = {pid: (o, d) for pid, o, d in self.client.sync()["results"]}
        self.assertEqual(results["claude-code"][0], "failed")
        self.assertIn("left it alone", results["claude-code"][1])
        if sys.version_info < (3, 11):
            self.assertEqual(results["codex"][0], "installed")
            record = self.client.status()["installed"]["codex"]
            self.assertEqual(record["mode"], "scoped")
            self.assertTrue(record["gated"])
            self.assertFalse((self.home / ".profile").exists())
        else:
            self.assertEqual(results["codex"][0], "failed")
        self.assertEqual(self.claude.read_text(), "{ not json")
        self.assertEqual(self.codex.read_text(), 'model_provider = "mine"\n')
        self.assertEqual(results["access-gate"][0], "installed")  # one failing never stops the others


class RevocationTests(ClientBase):
    owner = "company"

    def test_when_the_server_disconnects_the_device_swangz_removes_itself(self):
        (self.home / ".codex").mkdir()
        original = 'model = "o3"\n'
        (self.home / ".codex" / "config.toml").write_text(original)
        info = self.sign_in("company")
        self.client.sync()
        self.assertEqual(self.rig.api("POST", f"/keys/{info['key_id']}/revoke")[0], 200)
        with self.assertRaises(core.Revoked):
            self.client.sync()
        self.assertFalse(self.client.signed_in())
        self.assertEqual((self.home / ".codex" / "config.toml").read_text(), original)
        self.assertFalse((self.data / "packages").exists())
        self.assertFalse((self.data / "extension").exists())
        self.assertFalse((self.data / "device.key").exists())

    def test_a_check_in_from_a_disconnected_device_does_the_same(self):
        info = self.sign_in()
        self.client.sync()
        self.gw.db.x("UPDATE keys SET revoked = ? WHERE id = ?", (time.time(), info["key_id"]))
        with self.assertRaises(core.Revoked):
            self.client.heartbeat()
        self.assertFalse(self.client.signed_in())

    def test_logout_tells_the_server_so_the_key_stops_working_everywhere(self):
        info = self.sign_in()
        key = (self.data / "device.key").read_text().strip()
        self.assertTrue(self.client.logout())
        self.assertIsNotNone(self.gw.db.scalar("SELECT revoked FROM keys WHERE id = ?", (info["key_id"],)))
        status, _, _ = self.rig.anthropic({"model": "claude-test", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}, key=key)
        self.assertIn(status, (401, 403))  # a revoked key is refused at the door, as for any other

    def test_logout_still_cleans_up_when_the_server_cannot_be_reached(self):
        self.sign_in()
        self.client.sync()
        self.rig.server.shutdown()
        self.rig.server.server_close()
        self.assertFalse(self.client.logout())
        self.assertFalse(self.client.signed_in())

    def test_logout_turns_start_at_login_off(self):
        # A signed-out app has nothing to start for: the macOS login item / Linux .desktop file goes with the sign-in.
        for platform_name in ("darwin", "linux"):
            self.sign_in()  # on this system; only start-at-login and sign out see the other platform
            with self.subTest(platform_name), patch.dict(os.environ), patch.object(sys, "platform", platform_name):
                os.environ.pop("XDG_CONFIG_HOME", None)
                shell.set_autostart(self.client.paths, True, command=["/opt/swangz/swangz"])
                f = shell.autostart_file(self.client.paths)
                self.assertTrue(f.exists())
                self.assertTrue(str(f).startswith(str(self.client.paths.home)))  # the test's home, never the runner's
                self.client.logout()
                self.assertFalse(f.exists())
                self.assertFalse(shell.autostart_enabled(self.client.paths))

    def test_logout_still_signs_out_when_start_at_login_cannot_be_removed(self):
        self.sign_in()
        with patch.object(shell, "set_autostart", side_effect=PermissionError("read-only")):
            self.assertTrue(self.client.logout())
        self.assertFalse(self.client.signed_in())

    def test_logout_turns_start_at_login_off_even_when_clean_up_fails(self):
        self.sign_in()
        with patch.object(self.client, "remove_everything", side_effect=OSError("file in use")), \
                patch.object(shell, "set_autostart") as autostart:
            with self.assertRaises(OSError):
                self.client.logout()
        autostart.assert_called_once_with(self.client.paths, False)


class WindowsAutostartTests(unittest.TestCase):
    """Turning start-at-sign-in off on Windows: an absent Run value is already off; any other registry error is raised."""

    def fake_winreg(self, delete_error):
        import contextlib
        reg = SimpleNamespace(HKEY_CURRENT_USER="HKCU", KEY_SET_VALUE=2, REG_SZ=1, deleted=[])

        def delete(key, name):
            reg.deleted.append(name)
            if delete_error:
                raise delete_error
        reg.OpenKey = lambda *a: contextlib.nullcontext("run-key")
        reg.DeleteValue = delete
        return reg

    def turn_off(self, delete_error):
        reg = self.fake_winreg(delete_error)
        with patch.dict(sys.modules, {"winreg": reg}), patch.object(sys, "platform", "win32"):
            shell.set_autostart(None, False, command=["Swangz.exe"])
        return reg

    def test_an_absent_run_value_is_already_off(self):
        self.assertEqual(self.turn_off(FileNotFoundError(2, "not found")).deleted, ["Swangz"])
        self.assertEqual(self.turn_off(None).deleted, ["Swangz"])

    def test_other_registry_errors_are_raised(self):
        with self.assertRaises(PermissionError):
            self.turn_off(PermissionError(5, "access denied"))

    def test_an_absent_run_key_is_already_off_but_not_silently_enabled(self):
        reg = self.fake_winreg(None)
        reg.OpenKey = Mock(side_effect=FileNotFoundError(2, "Run key absent"))
        with patch.dict(sys.modules, {"winreg": reg}), patch.object(sys, "platform", "win32"):
            shell.set_autostart(None, False, command=["Swangz.exe"])
            with self.assertRaises(FileNotFoundError):
                shell.set_autostart(None, True, command=["Swangz.exe"])

    def test_access_denied_opening_the_run_key_is_not_an_absent_key(self):
        reg = self.fake_winreg(None)
        reg.OpenKey = Mock(side_effect=PermissionError(5, "access denied"))
        with patch.dict(sys.modules, {"winreg": reg}), patch.object(sys, "platform", "win32"):
            with self.assertRaises(PermissionError):
                shell.set_autostart(None, False, command=["Swangz.exe"])


class DeviceRemovalStartupTests(unittest.TestCase):
    """Port-free Windows registry/state tests: use the real cleanup and startup functions, no real registry or key."""

    def setUp(self):
        import contextlib
        self.values = {"Swangz": "Swangz.exe --background", "Another app": "untouched"}
        self.reg = SimpleNamespace(HKEY_CURRENT_USER="HKCU", KEY_SET_VALUE=2)
        self.reg.OpenKey = lambda *args: contextlib.nullcontext("Run")
        def delete(key, name):
            if name not in self.values:
                raise FileNotFoundError(name)
            del self.values[name]
        self.reg.DeleteValue = delete
        for p in (patch.dict(sys.modules, {"winreg": self.reg}), patch.object(sys, "platform", "win32")):
            p.start()
            self.addCleanup(p.stop)

    def client(self):
        client = object.__new__(core.Client)
        client.paths = SimpleNamespace()
        client.store = Mock()
        client.store.state.return_value = {"installed": {}}
        client.store.roots.return_value = []
        client.workspace = Mock()
        client._arm_policy_check = Mock()
        client._reconnect_pending = Mock(return_value=False)
        client.api = Mock()
        return client

    def test_direct_cleanup_guard_revocation_and_logout_remove_only_our_run_value(self):
        for route in ("cleanup", "revoke", "logout"):
            with self.subTest(route=route):
                self.values["Swangz"] = "Swangz.exe --background"
                client = self.client()
                if route == "revoke":
                    with self.assertRaises(core.Revoked):
                        client._guard(Mock(side_effect=core.Revoked(401, "device_revoked", "disconnected")))
                elif route == "logout":
                    self.assertTrue(client.logout())
                else:
                    client.remove_everything()
                self.assertEqual(self.values, {"Another app": "untouched"})
                client.store.wipe.assert_called_once_with()

    def test_removal_is_idempotent_with_an_absent_run_value(self):
        client = self.client()
        client.remove_everything()
        client.remove_everything()
        self.assertEqual(self.values, {"Another app": "untouched"})
        self.assertEqual(client.store.wipe.call_count, 2)

    def test_startup_is_disabled_even_if_reading_local_state_fails(self):
        client = self.client()
        client.store.state.side_effect = OSError("unreadable state")
        with self.assertRaisesRegex(OSError, "unreadable state"):
            client.remove_everything()
        self.assertNotIn("Swangz", self.values)

    def test_registry_denial_does_not_prevent_credential_removal(self):
        client = self.client()
        self.reg.DeleteValue = Mock(side_effect=PermissionError("registry denied"))
        with patch.object(sys, "stderr", io.StringIO()) as err:
            client.remove_everything()
        client.store.wipe.assert_called_once_with()
        client.workspace.forget.assert_called_once_with()
        lines = err.getvalue().splitlines()
        self.assertEqual(len(lines), 1)  # one line, naming the error type and the retry; no path or value
        self.assertIn("couldn't turn off start at login (PermissionError)", lines[0])
        self.assertIn("swangz autostart off", lines[0])

    def test_revocation_during_rotation_removes_startup_too(self):
        client = self.client()
        client.store.device.return_value = {"server": "https://hub.example.com"}
        client._heartbeat_body = Mock(return_value={})
        client._api_factory = Mock()
        client._api_factory.return_value.call.side_effect = core.Revoked(401, "device_revoked", "disconnected")
        with self.assertRaises(core.Revoked):
            client._confirm_staged((12, "synthetic-credential"))
        self.assertNotIn("Swangz", self.values)
        client.store.wipe.assert_called_once_with()


class MacLinuxRemovalStartupTests(unittest.TestCase):
    """Sentinel's #281 Low finding: revocation and `swangz cleanup` drop the macOS LaunchAgent / Linux .desktop file
    too, not only the Windows Run value, so a revoked app does not relaunch at every login."""

    def client(self, home):
        client = DeviceRemovalStartupTests.client(self)
        client.paths = SimpleNamespace(home=home)
        return client

    def each_platform(self):
        for name in ("darwin", "linux"):
            home = tempfile.mkdtemp(prefix="sgw-home-")
            self.addCleanup(shutil.rmtree, home, True)
            with self.subTest(name), patch.dict(os.environ), patch.object(sys, "platform", name):
                os.environ.pop("XDG_CONFIG_HOME", None)
                yield name, home

    def test_revoke_and_cleanup_remove_the_launch_agent_and_the_desktop_file(self):
        for name, home in self.each_platform():
            for route in ("revoke", "cleanup"):
                client = self.client(home)
                shell.set_autostart(client.paths, True, command=["/opt/swangz/swangz"])
                f = shell.autostart_file(client.paths)
                self.assertTrue(f.is_file() and str(f).startswith(home))
                if route == "revoke":
                    with self.assertRaises(core.Revoked):
                        client._guard(Mock(side_effect=core.Revoked(401, "device_revoked", "disconnected")))
                else:
                    client.remove_everything()
                self.assertFalse(f.exists(), f"{name} {route}: {f}")
                self.assertFalse(shell.autostart_enabled(client.paths))
                client.store.wipe.assert_called_once_with()

    def test_linux_from_source_starts_in_the_folder_that_holds_the_package(self):
        """The session runs autostart entries from the home folder, where `python3 -m swangz_client` cannot import."""
        home = tempfile.mkdtemp(prefix="sgw-home-")
        self.addCleanup(shutil.rmtree, home, True)
        paths = SimpleNamespace(home=home)
        with patch.dict(os.environ), patch.object(sys, "platform", "linux"):
            os.environ.pop("XDG_CONFIG_HOME", None)
            shell.set_autostart(paths, True)
            entry = dict(line.split("=", 1) for line in shell.autostart_file(paths).read_text().splitlines() if "=" in line)
            with patch.object(sys, "frozen", True, create=True):
                shell.set_autostart(paths, True, command=["/opt/swangz/Swangz"])
                packaged = shell.autostart_file(paths).read_text()
        source = Path(shell.__file__).resolve().parent.parent
        self.assertEqual(entry["Path"], str(source))
        run = subprocess.run([*shlex.split(entry["Exec"].replace("--background", "--version"))],
                             cwd=entry["Path"], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Path=", packaged)

    def test_an_absent_file_is_already_off_and_a_failure_never_blocks_removal(self):
        for name, home in self.each_platform():
            client = self.client(home)
            client.remove_everything()  # nothing there: a no-op
            client.store.wipe.assert_called_once_with()
            client = self.client(home)
            with patch.object(Path, "unlink", side_effect=PermissionError("read-only")), \
                    patch.object(Path, "exists", return_value=True), patch.object(sys, "stderr", io.StringIO()) as err:
                client.remove_everything()
            client.store.wipe.assert_called_once_with()
            self.assertEqual(len(err.getvalue().splitlines()), 1)


class PackageTests(ClientBase):
    def publish(self, version="1.0.0", files=None, **kw):
        path = make_zip(os.path.join(self.tmp, f"p{version}.zip"), files or {"README.md": f"v{version}", "prompts/a.txt": "hello"})
        return enroll.publish(self.gw, path, "brand-prompts", version, "Brand prompts", audience=kw.pop("audience", {"people": [self.rig.person_id]}), **kw)

    def folder(self, version):
        return self.data / "packages" / "brand-prompts" / version

    def test_a_published_package_is_installed_updated_and_removed(self):
        self.sign_in()
        self.publish("1.0.0")
        self.assertEqual({pid: o for pid, o, _ in self.client.sync()["results"]}["brand-prompts"], "installed")
        self.assertEqual((self.folder("1.0.0") / "prompts" / "a.txt").read_text(), "hello")
        time.sleep(0.01)
        self.publish("1.1.0", files={"README.md": "new"})
        self.assertEqual({pid: o for pid, o, _ in self.client.sync()["results"]}["brand-prompts"], "updated")
        self.assertEqual((self.folder("1.1.0") / "README.md").read_text(), "new")
        self.assertFalse(self.folder("1.0.0").exists())  # the old version is gone
        self.assertEqual(self.client.packages()[-1]["state"], "installed")
        self.gw.db.x("DELETE FROM package_grants")
        self.assertEqual({pid: o for pid, o, _ in self.client.sync()["results"]}["brand-prompts"], "removed")
        self.assertFalse((self.data / "packages" / "brand-prompts").exists())

    def test_a_download_that_does_not_match_its_checksum_is_not_installed(self):
        self.sign_in()
        self.publish("1.0.0")
        self.client.sync()
        time.sleep(0.01)
        self.publish("1.1.0")
        self.gw.db.x("UPDATE packages SET sha256 = ? WHERE version = '1.1.0'", ("0" * 64,))
        # the server notices its own file no longer matches and refuses to send it; either way nothing is installed
        out = {pid: (o, d) for pid, o, d in self.client.sync()["results"]}
        self.assertEqual(out["brand-prompts"][0], "failed")
        self.assertTrue(self.folder("1.0.0").exists())  # the working version stays
        self.assertFalse(self.folder("1.1.0").exists())

    def test_a_hostile_package_cannot_write_outside_its_folder(self):
        self.sign_in()
        evil = os.path.join(self.tmp, "evil.zip")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../escaped.txt", "x")
        raw = Path(evil).read_bytes()
        with self.assertRaisesRegex(bundles.BundleError, "unsafe file name"):
            bundles.install(self.client.paths, "brand-prompts", "1.0.0", raw, __import__("hashlib").sha256(raw).hexdigest())
        self.assertFalse((self.data / "packages" / "escaped.txt").exists())
        self.assertFalse((self.data / "escaped.txt").exists())
        self.assertFalse((self.data / "packages" / "brand-prompts").exists())

    def test_zip_tricks_are_refused(self):
        import hashlib
        import io

        def attempt(build):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                build(z)
            data = buf.getvalue()
            return lambda: bundles.install(self.client.paths, "tricks", "1", data, hashlib.sha256(data).hexdigest())

        def link(z):
            info = zipfile.ZipInfo("shortcut")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")

        for build, why in ((lambda z: z.writestr("/abs.txt", "x"), "unsafe file name"), (lambda z: z.writestr("C:/win.txt", "x"), "unsafe file name"),
                           (lambda z: z.writestr("a\\..\\b.txt", "x"), "unsafe file name"), (link, "contains a link")):
            with self.assertRaisesRegex(bundles.BundleError, why):
                attempt(build)()
        with self.assertRaisesRegex(bundles.BundleError, "not a zip"):
            bundles.install(self.client.paths, "tricks", "1", b"nope", __import__("hashlib").sha256(b"nope").hexdigest())
        with self.assertRaisesRegex(bundles.BundleError, "unsafe name"):
            bundles.install(self.client.paths, "../x", "1", b"x", "0")
        self.assertFalse((self.data / "packages" / "tricks").exists())
        self.assertEqual([p.name for p in (self.data / "packages").glob(".incoming*")] if (self.data / "packages").exists() else [], [])

    def test_a_manifest_can_never_send_the_key_to_another_address(self):
        self.sign_in()
        api = self.client.api()
        with self.assertRaises(core.ApiFailure) as caught:
            api.download("https://evil.example/steal")
        self.assertEqual(caught.exception.code, "foreign_url")
        with self.assertRaises(core.ApiFailure):
            api.download(self.server.replace("127.0.0.1", "localhost") + "/api/device/extension")  # same machine, other name: still another origin

    def test_a_client_too_old_for_the_server_is_told_to_update(self):
        self.sign_in()
        original = enroll.CLIENT_MINIMUM
        try:
            enroll.CLIENT_MINIMUM = "9.0.0"
            with self.assertRaises(core.ClientTooOld):
                self.client.sync()
        finally:
            enroll.CLIENT_MINIMUM = original

    def test_the_client_and_server_agree_on_the_version(self):
        self.assertEqual(__version__, enroll.CLIENT_LATEST)
        self.assertEqual(core.version_tuple("0.10.2"), (0, 10, 2))
        self.assertGreater(core.version_tuple("0.10.0"), core.version_tuple("0.9.9"))


class SettingsFileTests(unittest.TestCase):
    def test_marked_blocks_come_out_exactly_as_they_went_in(self):
        for text in ("", "a = 1\n", "a = 1", "\n\nx\n", "a\n\n[t]\nb = 2\n"):
            for at_start in (True, False):
                self.assertEqual(agents.without_block(agents.with_block(text, "B", at_start=at_start)), text)
                twice = agents.with_block(agents.with_block(text, "B", at_start=at_start), "C", at_start=at_start)
                self.assertEqual((twice.count(agents.BEGIN), "C" in twice, "B" in twice), (1, True, False))

    def test_the_codex_block_is_first_because_toml_needs_top_level_keys_before_tables(self):
        text = agents.with_block('[tui]\nx = 1\n', agents.codex_block("https://h/openai/v1"), at_start=True)
        if sys.version_info >= (3, 11):
            import tomllib

            parsed = tomllib.loads(text)
            self.assertEqual(parsed["model_provider"], "swangz")
            self.assertEqual(parsed["model_providers"]["swangz"]["base_url"], "https://h/openai/v1")
            self.assertEqual(parsed["tui"], {"x": 1})


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sgw-shell-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paths = core.Paths(self.tmp / "home", self.tmp / "data")

    # D-026 "Amendment 25 Nov (cleanup tokens)". Windows answers are stood in here, so every system runs them.
    ME, ADMINS = "S-1-5-21-1-2-3-1001", "S-1-5-32-544"

    def windows_refusal(self, kind=1, user=ME, owner=ME):
        from swangz_client import winacl

        def answer(value):
            return {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
        with patch.object(shell.sys, "platform", "win32"), \
                patch.object(winacl, "token_elevation_type", **answer(kind)), \
                patch.object(winacl, "current_sid", **answer(user)), \
                patch.object(winacl, "owner_sid", **answer(owner)) as asked:
            refused = shell.cleanup_refusal(self.paths.data)
        if asked.called:
            asked.assert_called_once_with(str(self.paths.data))
        return refused

    def test_cleanup_allows_a_default_or_limited_token_and_refuses_a_full_one(self):
        self.assertIsNone(self.windows_refusal(kind=1))  # default: UAC off, or the built-in Administrator
        self.assertIsNone(self.windows_refusal(kind=3))  # limited
        self.assertEqual(self.windows_refusal(kind=2), "elevated_refused")  # full: raised by UAC
        self.assertEqual(self.windows_refusal(kind=0), "elevated_refused")  # an answer nobody defined

    def test_cleanup_refuses_the_three_service_accounts(self):
        for sid in ("S-1-5-18", "S-1-5-19", "S-1-5-20"):
            for kind in (1, 3):
                with self.subTest(sid=sid, kind=kind):
                    self.assertEqual(self.windows_refusal(kind=kind, user=sid, owner=sid), "elevated_refused")

    def test_cleanup_refuses_a_folder_somebody_else_owns(self):
        for owner in ("S-1-5-21-1-2-3-1002", self.ADMINS, "S-1-5-18"):
            with self.subTest(owner=owner):
                self.assertEqual(self.windows_refusal(owner=owner), "wrong_account")

    def test_cleanup_refuses_what_it_cannot_read(self):
        for answers, expected in (({"kind": OSError("token")}, "elevated_refused"),
                                  ({"user": OSError("sid")}, "elevated_refused"),
                                  ({"user": None}, "elevated_refused"),
                                  ({"owner": OSError(5, "owner")}, "wrong_account"),
                                  ({"owner": None}, "wrong_account")):
            with self.subTest(answers=answers):
                self.assertEqual(self.windows_refusal(**answers), expected)
        # no folder: nothing has an owner, so a second run (or an account that never signed in) is not refused
        self.assertIsNone(self.windows_refusal(owner=FileNotFoundError("gone")))

    def test_cleanup_on_macos_and_linux_wants_the_folders_owner_and_never_root(self):
        self.paths.data.mkdir(parents=True)
        owner = os.stat(self.paths.data).st_uid
        for platform in ("linux", "darwin"):
            with patch.object(shell.sys, "platform", platform):
                for euid, expected in ((0, "elevated_refused"), (owner + 1, "wrong_account")):
                    with self.subTest(platform=platform, euid=euid), \
                            patch.object(shell.os, "geteuid", return_value=euid, create=True):
                        self.assertEqual(shell.cleanup_refusal(self.paths.data), expected)
                if os.name != "nt" and owner:  # the real owner of a real folder
                    with patch.object(shell.os, "geteuid", return_value=owner, create=True):
                        self.assertIsNone(shell.cleanup_refusal(self.paths.data))
                        self.assertIsNone(shell.cleanup_refusal(self.tmp / "not-there"))
                        with patch.object(shell.os, "stat", side_effect=PermissionError(13, "no")):
                            self.assertEqual(shell.cleanup_refusal(self.paths.data), "wrong_account")
                with patch.object(shell.os, "geteuid", side_effect=OSError("no"), create=True):
                    self.assertEqual(shell.cleanup_refusal(self.paths.data), "elevated_refused")

    def test_hub_links_use_only_enrolled_origin_and_never_device_credentials(self):
        device = {"server": "https://hub.example:8443", "key": "never-in-url"}
        client = SimpleNamespace(signed_in=lambda: True, store=SimpleNamespace(device=lambda: device))
        expected = {"weekly": "/#/weekly", "devices": "/#/devices", "admin": "/admin"}
        with patch.object(shell, "open_url", return_value=True) as opened:
            for page, path in expected.items():
                self.assertEqual(shell.open_hub(client, page), device["server"] + path)
                opened.assert_called_with(device["server"] + path)
        # Reject arbitrary routes, embedded credentials, query strings and foreign destinations.
        with patch.object(shell, "open_url") as opened:
            for bad in ("https://elsewhere.example/", "/admin", "../admin", "tools", "home", "/go/canva"):
                with self.assertRaises(KeyError):
                    shell.open_hub(client, bad)
            for bad in (None, "javascript:alert(1)", "https://user:secret@hub.example",
                        "https://hub.example?key=secret", "https://hub.example/#secret"):
                device["server"] = bad
                with self.assertRaises(ValueError):
                    shell.open_hub(client, "weekly")
            opened.assert_not_called()

    def test_hub_browser_routes_exclude_provider_launches(self):
        # Only these account/reporting surfaces are exempt from the managed workspace.
        self.assertEqual(set(shell.HUB_PAGES.values()), {"/#/weekly", "/#/devices", "/admin"})
        self.assertTrue(all("/go/" not in path for path in shell.HUB_PAGES.values()))

    def test_hub_open_reports_browser_failure_and_requires_connection(self):
        client = SimpleNamespace(signed_in=lambda: False)
        with patch.object(shell, "open_url") as opened:
            with self.assertRaises(core.NotSignedIn):
                shell.open_hub(client, "admin")
            opened.assert_not_called()
        client = SimpleNamespace(signed_in=lambda: True,
                                 store=SimpleNamespace(device=lambda: {"server": "https://hub.example"}))
        with patch.object(shell, "open_url", return_value=False):
            with self.assertRaisesRegex(OSError, "browser could not open"):
                shell.open_hub(client, "weekly")

    def test_start_at_login_on_linux_and_macos(self):
        for platform_name in ("linux", "darwin"):
            real = sys.platform
            sys.platform = platform_name
            try:
                os.environ.pop("XDG_CONFIG_HOME", None)
                shell.set_autostart(self.paths, True, command=["/opt/swangz/swangz"])
                f = shell.autostart_file(self.paths)
                self.assertTrue(f.exists() and shell.autostart_enabled(self.paths))
                text = f.read_text() if platform_name == "linux" else f.read_bytes().decode("latin-1")
                self.assertIn("--background", text)
                self.assertIn("swangz", text)
                shell.set_autostart(self.paths, False)
                self.assertFalse(f.exists())
            finally:
                sys.platform = real

    def test_a_terminal_is_opened_the_way_each_system_does_it(self):
        real = sys.platform
        try:
            sys.platform = "win32"
            cmd = shell.terminal_command(["swangz", "run", "claude"], "C:\\Work")
            self.assertEqual(cmd[:3], ["cmd.exe", "/c", "start"])
            sys.platform = "darwin"
            cmd = shell.terminal_command(["swangz", "run", "claude"], "/Users/x/My Work")
            self.assertEqual(cmd[0], "osascript")
            self.assertIn("My Work", cmd[2])
            self.assertIn("swangz run claude", cmd[2])
            sys.platform = "linux"
            cmd = shell.terminal_command(["swangz", "run", "claude"], "/home/x")
            self.assertTrue(cmd is None or "swangz run claude" in cmd[-1])
        finally:
            sys.platform = real


class CommandLineTests(ClientBase):
    def run_cli(self, *argv):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv), client=self.client)
        return code, out.getvalue()

    def test_the_commands(self):
        code, text = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("swangz login", text)
        code, text = self.run_cli("login", "--server", self.server, "--name", "Grace's laptop")
        self.assertEqual(code, 0, text)
        self.assertIn("Signed in as Nansubuga Grace", text)
        self.assertIn("installed  claude-code", text)
        self.assertIn("never reads your files", text)
        code, text = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("Grace's laptop (personal)", text)
        code, text = self.run_cli("packages")
        self.assertIn("Browser access gate", text)
        code, text = self.run_cli("sync")
        self.assertIn("current", text)
        code, text = self.run_cli("logout")
        self.assertEqual(code, 0)
        self.assertIn("taken off this device", text)
        self.assertNotIn("Swangz has been removed", text)  # the browser folders are not removed (yet)
        self.assertIn("Not removed: browser folders that hold provider and Google sign-ins", text)
        self.assertIn(str(self.client.paths.data / "browser-profiles"), text)
        self.assertEqual(self.run_cli("sync")[0], 2)

    def signed_in_with_folders(self):
        """A signed-in device with saved browser sign-ins; start at login is never the test runner's real one."""
        allowed = patch.object(shell, "cleanup_refusal", return_value=None)  # the rule itself: ShellTests
        allowed.start()
        self.addCleanup(allowed.stop)
        autostart = patch.object(shell, "set_autostart")
        self.autostart = autostart.start()
        self.addCleanup(autostart.stop)
        info = self.sign_in()
        self.profiles = self.data / "browser-profiles"
        self.profiles.mkdir(mode=0o700, exist_ok=True)
        for name in ("a" * 32, "b" * 32):
            (self.profiles / name / "Default").mkdir(parents=True, mode=0o700)
            (self.profiles / name / "Default" / "Cookies").write_bytes(b"session")
        self.report = self.root / "report.txt"
        return info

    def revoked(self, info):
        return self.gw.db.one("SELECT revoked FROM keys WHERE id = ?", (info["key_id"],))["revoked"] is not None

    def left_in_profiles(self):
        return sorted(p.name for p in self.profiles.iterdir() if p.name != ".lock")

    def test_cleanup_signs_out_deletes_every_folder_and_stops_start_at_login(self):
        info = self.signed_in_with_folders()
        code, text = self.run_cli("cleanup", "--report", str(self.report))
        self.assertEqual(code, 0, text)
        self.assertIn("removed from this account, saved browser sign-ins included", text)
        self.assertTrue(self.revoked(info))  # the Hub was told while the key still existed
        self.assertFalse((self.data / "device.json").exists())
        self.assertFalse((self.data / "device.key").exists())
        self.assertEqual(self.left_in_profiles(), [])
        self.autostart.assert_called_with(self.client.paths, False)
        self.assertEqual(self.report.read_text(encoding="utf-8-sig"), "")
        # a second run changes nothing
        before = sorted(str(p) for p in self.root.rglob("*"))
        self.assertEqual(self.run_cli("cleanup", "--report", str(self.report)), (0, text))
        self.assertEqual(sorted(str(p) for p in self.root.rglob("*")), before)

    def test_a_refused_cleanup_says_why_and_changes_nothing(self):
        info = self.signed_in_with_folders()
        before = {str(p): p.read_bytes() if p.is_file() else None for p in self.root.rglob("*")}
        for reason in ("elevated_refused", "wrong_account"):
            with self.subTest(reason=reason), patch.object(shell, "cleanup_refusal", return_value=reason):
                code, text = self.run_cli("cleanup", "--report", str(self.report))
                self.assertEqual(code, 1)
                self.assertIn(f"({reason})", text)
                self.assertNotIn("was removed from this account", text)
                with self.assertRaises(core.CleanupRefused) as refused:
                    self.client.cleanup()
                self.assertEqual(refused.exception.code, reason)
                # the command refuses before it even builds the client
                with patch.object(core, "Client") as made, patch.object(cli, "say"):
                    self.assertEqual(cli.main(["cleanup"]), 1)
                made.assert_not_called()
        self.assertEqual({str(p): p.read_bytes() if p.is_file() else None for p in self.root.rglob("*")}, before)
        self.assertFalse(self.revoked(info))
        self.autostart.assert_not_called()

    def test_cleanup_names_what_it_could_not_delete_and_exits_non_zero(self):
        info = self.signed_in_with_folders()
        (self.profiles / ("a" * 32) / "stuck").write_bytes(b"in use")
        real = bp._remove_tree

        def stuck(path, entry):
            if (path / "stuck").exists():
                raise PermissionError(13, "in use")
            return real(path, entry)
        with patch.object(bp, "_remove_tree", stuck):
            code, text = self.run_cli("cleanup", "--report", str(self.report))
        self.assertEqual(code, 1, text)
        left, = self.left_in_profiles()
        path = str(self.profiles / left)
        self.assertEqual(self.report.read_text(encoding="utf-8-sig").splitlines(), [path])
        self.assertTrue(self.report.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertIn(f"Not deleted: {path}", text)
        self.assertIn("not completely removed", text)
        self.assertNotIn("saved browser sign-ins included", text)
        self.assertTrue(self.revoked(info))  # the folder that stayed does not keep the key
        self.assertFalse((self.data / "device.key").exists())
        self.assertEqual(self.run_cli("cleanup")[0], 0)  # the next run finishes the job
        self.assertEqual(self.left_in_profiles(), [])

    @unittest.skipIf(os.name == "nt", "SingletonLock is the Linux and macOS lock")
    def test_cleanup_never_reports_success_while_a_browser_holds_a_folder(self):
        info = self.signed_in_with_folders()
        held = self.profiles / ("a" * 32)
        os.symlink("host-%d" % os.getpid(), held / "SingletonLock")  # this process stands for the open browser
        code, text = self.run_cli("cleanup", "--report", str(self.report))
        self.assertEqual(code, 1, text)
        self.assertIn(f"Not deleted: {held} (in_use)", text)
        self.assertIn("Close any workspace window, then run cleanup again", text)
        self.assertNotIn("saved browser sign-ins included", text)
        self.assertEqual(self.report.read_text(encoding="utf-8-sig").splitlines(), [str(held)])
        self.assertEqual(self.left_in_profiles(), [held.name])
        self.assertEqual((held / "Default" / "Cookies").read_bytes(), b"session")
        self.assertTrue(self.revoked(info))
        (held / "SingletonLock").unlink()  # the browser closed
        self.assertEqual(self.run_cli("cleanup")[0], 0)
        self.assertEqual(self.left_in_profiles(), [])

    def test_printed_commands_are_quoted_for_this_systems_terminal(self):
        program = ["C:\\Program Files\\Swangz\\Swangz.exe"]
        with patch.object(shell, "app_command", return_value=program):
            with patch.object(cli.sys, "platform", "win32"):
                self.assertEqual(cli.sign_out_command(), '"C:\\Program Files\\Swangz\\Swangz.exe" logout')
                self.assertEqual(cli.typed_command("cleanup"), '"C:\\Program Files\\Swangz\\Swangz.exe" cleanup')
            with patch.object(cli.sys, "platform", "darwin"):
                self.assertEqual(cli.sign_out_command(), "'C:\\Program Files\\Swangz\\Swangz.exe' logout")

    def test_cleanup_still_deletes_when_the_server_cannot_be_reached(self):
        info = self.signed_in_with_folders()
        with patch.object(core.Api, "call", side_effect=core.ApiFailure(0, "unreachable", "offline")):
            code, text = self.run_cli("cleanup")
        self.assertEqual(code, 0, text)
        self.assertIn("ask an admin to disconnect this device", text)
        self.assertFalse((self.data / "device.key").exists())
        self.assertEqual(self.left_in_profiles(), [])
        self.assertFalse(self.revoked(info))

    def test_cleanup_goes_on_when_taking_the_app_off_fails(self):
        self.signed_in_with_folders()
        with patch.object(self.client, "remove_everything", side_effect=OSError("disk says no")):
            code, text = self.run_cli("cleanup")
        self.assertEqual(code, 1, text)
        self.assertIn("Not removed: Swangz's key, agents or packages: disk says no", text)
        self.assertEqual(self.left_in_profiles(), [])
        self.autostart.assert_called_with(self.client.paths, False)

    def test_cleanup_after_sign_out_deletes_the_folders_that_stayed(self):
        self.signed_in_with_folders()
        code, text = self.run_cli("logout")
        self.assertEqual(code, 0, text)
        self.assertIn("To delete them, run: ", text)
        self.assertIn(" cleanup", text)
        self.assertEqual(self.left_in_profiles(), ["a" * 32, "b" * 32])  # sign out keeps them
        code, text = self.run_cli("cleanup")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.left_in_profiles(), [])

    def test_a_disconnected_device_gets_a_plain_message(self):
        info = self.sign_in()
        self.gw.db.x("UPDATE keys SET revoked = ? WHERE id = ?", (time.time(), info["key_id"]))
        code, text = self.run_cli("sync")
        self.assertEqual(code, 3)
        self.assertIn("was disconnected", text)
        self.assertNotIn("has been removed", text)  # the browser folders stay until deletion is built
        self.assertIn("Not removed: browser folders that hold provider and Google sign-ins", text)


if __name__ == "__main__":
    unittest.main()
