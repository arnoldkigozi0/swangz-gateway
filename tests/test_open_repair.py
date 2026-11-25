"""#333: every refused Open ends in plain next steps and nothing opens anywhere else; a person's workspace folder
works from paths with spaces, is never another person's, and survives an app restart."""
import ast
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import browser_profiles as bp
from swangz_client import cli, core
from swangz_client import repair
from swangz_client import workspace_launcher as wl
from tests import test_workspace_launcher as twl

ROOT = Path(__file__).resolve().parents[1]
URL = twl.URL
HOSTS = twl.HOSTS


class CoverageTests(unittest.TestCase):
    def test_every_device_refusal_has_its_own_next_steps(self):
        self.assertEqual(set(wl.MESSAGES), set(repair._DEVICE))
        for code, message in wl.MESSAGES.items():
            fix = repair.explain(wl.LaunchError(code))
            self.assertEqual((fix.code, fix.message), (code, message))
            self.assertTrue(fix.title and fix.steps, code)
            self.assertLessEqual(set(fix.actions), set(repair.LABELS), code)
            self.assertEqual(repair.CHROME in fix.actions, code == "no_browser", code)

    def test_an_unknown_device_code_still_ends_in_a_repair(self):
        fix = repair.explain(wl.LaunchError("something_new"))
        self.assertEqual((fix.code, fix.message), ("something_new", wl.MESSAGES["launch_failed"]))
        self.assertTrue(fix.steps)

    def test_no_repair_names_an_address(self):
        for table in (repair._DEVICE, repair._HUB):
            for title, steps, _ in table.values():
                self.assertNotRegex(" ".join((title, *steps)), r"(?i)https?:|www\.|\.com")
        self.assertNotIn("://", (ROOT / "swangz_client" / "repair.py").read_text(encoding="utf-8"))

    def test_every_refusal_the_open_route_sends_is_explained(self):
        """The codes `gateway/device_open.py` and the checks it shares with /go/ answer with."""
        expected = {
            (429, "rate_limited"): "Swangz AI Hub is busy",
            (404, "unknown_tool"): "This tool isn't in your list any more",
            (409, "shared_account"): "This one opens from Swangz AI Hub",
            (409, "no_address"): "This tool isn't set up to open yet",
            (409, "host_not_allowed"): "This tool isn't set up to open yet",
            (409, "unsafe_address"): "This tool's address needs fixing",
            (409, "inside_other_tool"): "This tool isn't set up to open yet",
            (409, "workspace_policy"): "The company browser settings aren't in force",
            (403, "workspace_suspended"): "Your workspace is paused",
            (403, "workspace_retired"): "Your workspace was removed from this device",
            (403, "weekly_report_required"): "Your weekly report is due",
            (403, "not_assigned"): "This tool isn't open to you right now",
            (403, "locked"): "This tool isn't open to you right now",
            (403, "policy"): "This tool isn't open to you right now",
            (401, "device_unknown"): "Swangz AI Hub doesn't recognise this device",
            (0, "offline"): "Can't reach Swangz AI Hub",
            (200, "invalid_response"): "Swangz AI Hub had a problem",
            (503, ""): "Swangz AI Hub had a problem",
            (429, ""): "Swangz AI Hub is busy",
        }
        for (status, code), title in expected.items():
            fix = repair.explain(core.ApiFailure(status, code, "The Hub's own words."))
            self.assertEqual((fix.title, fix.message, fix.code), (title, "The Hub's own words.", code), (status, code))

    def test_a_disconnected_device_and_other_failures_are_not_repairs(self):
        for exc in (core.Revoked(401, "device_revoked", "x"), core.KeyRotated(401, "device_key_rotated", "x"),
                    core.NotSignedIn("x"), core.NeedsReconnect("x"), ValueError("x"), KeyError("x"), OSError("x")):
            self.assertIsNone(repair.explain(exc), type(exc).__name__)


class CommandLineTests(unittest.TestCase):
    def run_open(self, error):
        client = mock.Mock()
        client.open_app.side_effect = error
        out = io.StringIO()
        with mock.patch("webbrowser.open") as wb, mock.patch("swangz_client.shell.open_url") as shell_open, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(["open", "chatgpt"], client=client)
        wb.assert_not_called()
        shell_open.assert_not_called()
        return code, out.getvalue()

    def test_open_prints_the_steps_for_a_refusal_made_here(self):
        code, out = self.run_open(wl.LaunchError("no_browser"))
        self.assertEqual(code, 1)
        for part in ("Google Chrome is needed", wl.MESSAGES["no_browser"], "1. Get Google Chrome", wl.INSTALL_PAGE):
            self.assertIn(part, out)

    def test_open_prints_the_steps_for_a_refusal_from_the_hub(self):
        code, out = self.run_open(core.ApiFailure(403, "not_assigned", "ChatGPT isn't assigned to you."))
        self.assertEqual(code, 1)
        for part in ("This tool isn't open to you right now", "ChatGPT isn't assigned to you.", "1. If you need it"):
            self.assertIn(part, out)
        self.assertNotIn("http", out)


class NoOtherBrowserTests(unittest.TestCase):
    def test_only_the_shell_module_can_reach_the_default_browser(self):
        """core takes `open_url` from the shell for the Hub's own approval page only (see InventoryTests)."""
        importers = set()
        for path in sorted((ROOT / "swangz_client").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
                if "webbrowser" in names or getattr(node, "module", None) == "webbrowser":
                    importers.add(path.name)
        self.assertEqual(importers, {"shell.py"})

    def test_the_open_path_never_names_it(self):
        sources = {name: (ROOT / "swangz_client" / name).read_text(encoding="utf-8") for name in
                   ("core.py", "workspace_launcher.py", "workspace_state.py", "browser_profiles.py", "repair.py")}
        for name in ("workspace_launcher.py", "workspace_state.py", "browser_profiles.py", "repair.py"):
            self.assertNotRegex(sources[name], r"webbrowser|open_url|startfile|xdg-open", name)
        opening = [n for n in ast.walk(ast.parse(sources["core.py"]))
                   if isinstance(n, ast.FunctionDef) and n.name in ("open_app", "_open_in_workspace", "_open_failed")]
        self.assertEqual(len(opening), 3)
        for fn in opening:
            self.assertNotRegex(ast.get_source_segment(sources["core.py"], fn), r"self\.open_url|webbrowser|startfile")


class FolderUseTests(twl.Base):
    def client(self, person="7", data=None):
        if data is not None:
            self.data = data
        client, opened, api = twl.OpenAppTests.client(self)
        manifest = client.store.manifest()
        manifest["browser"]["person_id"] = person
        client.store.manifest = lambda: manifest
        return client, opened

    def folder_of(self, call):
        argv = call[0]
        self.assertTrue(argv[1].startswith("--user-data-dir="), argv)
        return Path(argv[1].split("=", 1)[1])

    def restart(self):
        self.launcher = wl.Launcher(self.data, popen=self.launcher.popen, finder=self.launcher.finder, acl=lambda p: True)

    def test_the_same_folder_and_what_is_in_it_survive_an_app_restart(self):
        first, _ = self.client()
        first.open_app("chatgpt")
        folder = self.folder_of(self.calls[-1])
        (folder / "Default").mkdir(mode=0o700)
        (folder / "Default" / "Cookies").write_bytes(b"signed in")  # stands for the provider's own session
        self.restart()
        again, _ = self.client()
        again.open_app("chatgpt")
        self.assertEqual(self.folder_of(self.calls[-1]), folder)
        self.assertEqual((folder / "Default" / "Cookies").read_bytes(), b"signed in")

    def test_a_second_person_is_never_given_the_first_persons_folder(self):
        first, _ = self.client("7")
        first.open_app("chatgpt")
        theirs = self.folder_of(self.calls[-1])
        self.restart()
        second, _ = self.client("8")
        second.open_app("chatgpt")
        mine = self.folder_of(self.calls[-1])
        self.assertNotEqual(mine, theirs)
        self.assertNotIn(str(theirs), " ".join(self.calls[-1][0]))
        marker = json.loads((mine / bp.MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["person_id"], "8")

    def test_a_hub_denial_or_missing_browser_starts_no_process_and_no_browser(self):
        denied = core.ApiFailure(403, "not_assigned", "No.")

        def missing():
            raise wl.LaunchError("no_browser")
        for finder, error in ((self.launcher.finder, denied), (missing, None)):
            self.launcher.finder = finder
            client, opened = self.client()
            if error:
                client.api().call.side_effect = error
            with mock.patch("webbrowser.open") as wb, mock.patch("swangz_client.shell.open_url") as shell_open:
                with self.assertRaises((wl.LaunchError, core.ApiFailure)) as ctx:
                    client.open_app("chatgpt")
            self.assertIsNotNone(repair.explain(ctx.exception))
            wb.assert_not_called()
            shell_open.assert_not_called()
            opened.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_a_tool_no_longer_listed_is_refused_without_calling_the_hub(self):
        client, opened = self.client()
        with self.assertRaises(wl.LaunchError) as ctx:
            client.open_app("midjourney")
        self.assertEqual(ctx.exception.code, "unavailable")
        client.api().call.assert_not_called()
        self.assertEqual(self.calls, [])

    @unittest.skipIf(os.name == "nt", "a script stands in for the browser")
    def test_a_real_start_from_folders_with_spaces_and_accents_keeps_each_path_whole(self):
        data = self.tmp / "Application Support" / "Swangz Données" / "Nakato Grace's data"
        data.mkdir(parents=True, mode=0o700)
        program = self.tmp / "Google Chrome.app" / "Google Chrome"
        program.parent.mkdir(mode=0o700)
        seen = self.tmp / "argv.json"
        program.write_text(f"#!{sys.executable}\nimport json, sys\n"
                           f"open({str(seen)!r}, 'w').write(json.dumps(sys.argv))\n", encoding="utf-8")
        program.chmod(0o700)
        self.data = data
        self.launcher = wl.Launcher(data, finder=lambda: str(program), acl=lambda p: True)
        client, opened = self.client()
        client.open_app("chatgpt")
        self.launcher.process.wait(timeout=30)
        argv = json.loads(seen.read_text(encoding="utf-8"))
        folder = Path(argv[1].split("=", 1)[1])
        self.assertEqual(folder.parent, data / "browser-profiles")
        self.assertTrue((folder / bp.MARKER).is_file())
        self.assertEqual(argv, [str(program), "--user-data-dir=" + str(folder), *wl.FIXED_SWITCHES, URL])
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
