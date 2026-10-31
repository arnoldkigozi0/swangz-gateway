"""The Swangz app's core, driven against a real running gateway: sign in with a code, what gets installed on a
personal and on a company device, removal, revocation, and the ways a package or manifest could be hostile."""

import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from gateway import enroll
from swangz_client import __version__, agents, bundles, cli, core, shell

from .test_devices import DeviceBase, make_zip


class ClientBase(DeviceBase):
    owner = "personal"

    def setUp(self):
        super().setUp()
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
        self.assertEqual(self.client.open_app("canva"), f"{self.server}/go/canva")
        self.assertEqual(self.opened[-1], f"{self.server}/go/canva")
        with self.assertRaises(KeyError):
            self.client.open_app("chatgpt")


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
        self.assertEqual((settings["env"]["ANTHROPIC_BASE_URL"], settings["env"]["ANTHROPIC_AUTH_TOKEN"]), (self.server + "/anthropic", key))
        toml = self.codex.read_text()
        self.assertTrue(toml.startswith(agents.BEGIN))
        self.assertIn(f'base_url = "{self.server}/openai/v1"', toml)
        self.assertTrue(toml.endswith(self.codex_original))
        self.assertNotIn(key, toml)  # Codex reads the key from the environment
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.claude.stat().st_mode), 0o600)
            profile = (self.home / ".profile").read_text()
            self.assertIn("SWANGZ_AI_KEY", profile)
            self.assertNotIn(key, profile)  # it reads our private key file
        self.assertEqual((self.data / "backups" / "claude-settings.json.orig").read_text(), self.claude_original)
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
            self.assertNotIn("SWANGZ_AI_KEY", (self.home / ".profile").read_text())
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
        self.assertIn("removed from this device", text)
        self.assertEqual(self.run_cli("sync")[0], 2)

    def test_a_disconnected_device_gets_a_plain_message(self):
        info = self.sign_in()
        self.gw.db.x("UPDATE keys SET revoked = ? WHERE id = ?", (time.time(), info["key_id"]))
        code, text = self.run_cli("sync")
        self.assertEqual(code, 3)
        self.assertIn("was disconnected", text)


if __name__ == "__main__":
    unittest.main()
