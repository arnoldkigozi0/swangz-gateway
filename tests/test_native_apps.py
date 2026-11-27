"""Desktop and command-line AI apps (swangz_client/native_apps.py): the fixed table, detection, consent, install, repair,
launch and the heartbeat report. Fake runners and a fake filesystem only: nothing here touches the network, installs
anything or starts a program.

    python3 -m unittest tests.test_native_apps
"""
import ast
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from swangz_client import core, native_apps as na

ROOT = Path(__file__).resolve().parents[1]
REAL_APPS, REAL_CLI = dict(na.APPS), dict(na.CLI_INSTALL)  # the shipped table, before any test swaps it
WINGET = r"C:\Users\grace\AppData\Local\Microsoft\WindowsApps\winget.exe"
ENV = {"LOCALAPPDATA": r"C:\Users\grace\AppData\Local", "APPDATA": r"C:\Users\grace\AppData\Roaming",
       "ANTHROPIC_API_KEY": "sk-never", "SWANGZ_AI_KEY": "never", "PATH": r"C:\Windows"}
FOLDERS = {"ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)",
           "System": r"C:\Windows\System32"}

TABLE = {
    "desk": na.Entry("Desk", "Desk Inc.", na.Way(na.NATIVE, winget="Desk.Desk", source="winget",
                                                   paths=("{LocalAppData}\\Programs\\Desk\\Desk.exe",
                                                          "{ProgramFiles}\\Desk\\Desk.exe"),
                                                   download="https://desk.example/download", updates="self",
                                                   sources=("https://github.com/microsoft/winget-pkgs",)),
                     na.Way(na.NATIVE, paths=("/Applications/Desk.app", "{Home}/Applications/Desk.app"),
                            bundle="com.desk.app", download="https://desk.example/download", updates="self",
                            sources=("https://formulae.brew.sh/cask/desk",)), na.VERIFIED),
    "storeapp": na.Entry("Store App", "Store Co.", na.Way(na.NATIVE, winget="9ABCDEF12345", source="msstore",
                                                         family="StoreCo.StoreApp_abc123", aumid="StoreCo.StoreApp_abc123!App",
                                                         download="https://store.example/", updates="store",
                                                         sources=("https://apps.microsoft.com/detail/9ABCDEF12345",)),
                         na.web(), na.VERIFIED),
    "pageonly": na.Entry("Page Only", "Page Ltd", na.Way(na.NATIVE, paths=("{ProgramFiles}\\Page\\Page.exe",),
                                                         download="https://page.example/download"),
                         na.Way(na.NATIVE, paths=("/Applications/Page.app",), bundle="com.page.app",
                                download="https://page.example/download"), na.VERIFIED),
    "tool-cli": na.Entry("Tool CLI", "Tool Co.", na.Way(na.CLI, cli="toolcli", paths=("{Home}\\.local\\bin\\tool.exe",),
                                                        download="https://tool.example/docs"),
                         na.Way(na.CLI, cli="toolcli", paths=("{Home}/.local/bin/tool",), download="https://tool.example/docs"),
                         na.VERIFIED),
}
CLI = {"toolcli": {"command": "tool", "where": "Tool Co.'s documented installer",
                   "windows": ("powershell.exe", "-NoProfile", "-Command", "irm https://tool.example/install.ps1 | iex"),
                   "macos": ("bash", "-c", "curl -fsSL https://tool.example/install.sh | bash")}}


class FakeFS:
    def __init__(self, *present):
        self.present = set(present)

    def __call__(self, path):
        return path in self.present


class Runner:
    """A fake subprocess.run: records argv and keyword arguments, answers with `code` and `stdout`."""

    def __init__(self, code=0, stdout="", fs=None, adds=None, raises=None):
        self.calls, self.code, self.stdout, self.fs, self.adds, self.raises = [], code, stdout, fs, adds, raises

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        if self.raises:
            raise self.raises
        if self.fs is not None and self.adds:
            self.fs.present.add(self.adds)
        return SimpleNamespace(returncode=self.code, stdout=self.stdout, stderr="")


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        for target, value in ((na, "APPS"), (na, "CLI_INSTALL")):
            patcher = mock.patch.dict(getattr(target, value), TABLE if value == "APPS" else CLI, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def manager(self, system="windows", fs=None, run=None, **kw):
        platform = {"windows": "win32", "macos": "darwin", "linux": "linux"}[system]
        self.fs = fs or FakeFS()
        self.run = run or Runner()
        self.popen, self.started, self.pages, self.terminals = mock.Mock(), [], [], []
        defaults = dict(platform=platform, run=self.run, popen=self.popen, exists=self.fs, env=ENV,
                        home=r"C:\Users\grace" if system == "windows" else "/Users/grace", which=lambda name: None,
                        start=self.started.append, open_page=lambda url: self.pages.append(url) or True,
                        open_terminal=lambda args: self.terminals.append(args) or True,
                        file_version=lambda path: "1.2.3.4", folders=lambda: FOLDERS,
                        read_plist=lambda path: {"CFBundleIdentifier": "com.desk.app", "CFBundleShortVersionString": "5.6"},
                        windows_dir=lambda: r"C:\Windows", browser=lambda: r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        defaults.update(kw)
        return na.Manager(self.data, **defaults)


class DetectionTests(Base):
    def test_web_and_unknown_tools_and_linux_are_web(self):
        m = self.manager()
        for tool in ("not-in-table", "chatgpt-web-only"):
            self.assertEqual(m.detect(tool)["state"], "web")
        self.assertEqual(self.manager("linux").detect("desk")["state"], "web")
        self.assertEqual(self.manager("macos").detect("storeapp")["state"], "web")

    def test_windows_finds_the_app_at_a_fixed_path_with_its_version(self):
        m = self.manager(fs=FakeFS(r"C:\Program Files\Desk\Desk.exe"))
        self.assertEqual(m.detect("desk"), {"state": "installed", "version": "1.2.3.4",
                                            "path": r"C:\Program Files\Desk\Desk.exe", "via": "fixed path"})

    def test_program_files_comes_from_hklm_not_the_environment(self):
        env = dict(ENV, ProgramFiles=r"C:\Users\grace\evil")
        m = self.manager(fs=FakeFS(r"C:\Users\grace\evil\Desk\Desk.exe"), env=env)
        self.assertEqual(m.detect("desk")["state"], "missing")

    def test_an_unknown_folder_never_becomes_a_relative_path(self):
        m = self.manager(fs=FakeFS(r"\Programs\Desk\Desk.exe", r"Programs\Desk\Desk.exe"),
                         env={}, folders=lambda: {"ProgramFiles": None})
        self.assertEqual(m.detect("desk")["state"], "missing")
        self.assertIsNone(m.expand("{LocalAppData}\\Programs\\Desk\\Desk.exe"))
        self.assertIsNone(m.expand("{Unknown}\\x.exe"))

    def test_a_store_app_is_found_by_its_package_family_folder(self):
        m = self.manager(fs=FakeFS(r"C:\Users\grace\AppData\Local\Packages\StoreCo.StoreApp_abc123"))
        self.assertEqual(m.detect("storeapp"), {"state": "installed", "version": "", "path": "", "via": "store"})

    def test_macos_checks_the_bundle_id_inside_the_app(self):
        fs = FakeFS("/Applications/Desk.app")
        self.assertEqual(self.manager("macos", fs=fs).detect("desk"),
                         {"state": "installed", "version": "5.6", "path": "/Applications/Desk.app", "via": "fixed path"})
        other = self.manager("macos", fs=fs, read_plist=lambda p: {"CFBundleIdentifier": "com.evil.app"})
        self.assertEqual(other.detect("desk")["state"], "missing")
        broken = self.manager("macos", fs=fs, read_plist=mock.Mock(side_effect=ValueError("bad plist")))
        self.assertEqual(broken.detect("desk")["state"], "missing")
        home = self.manager("macos", fs=FakeFS("/Users/grace/Applications/Desk.app"))
        self.assertEqual(home.detect("desk")["path"], "/Users/grace/Applications/Desk.app")

    def test_a_cli_on_path_is_found_only_as_a_labelled_fallback(self):
        m = self.manager("macos", which=lambda name: "/opt/homebrew/bin/tool" if name == "tool" else None)
        self.assertEqual(m.detect("tool-cli"), {"state": "installed", "version": "", "path": "/opt/homebrew/bin/tool",
                                                "via": "PATH (fallback)"})
        fixed = self.manager("macos", fs=FakeFS("/Users/grace/.local/bin/tool"))
        self.assertEqual(fixed.detect("tool-cli")["via"], "fixed path")

    def test_versions_are_printable_and_short(self):
        m = self.manager(fs=FakeFS(r"C:\Program Files\Desk\Desk.exe"), file_version=lambda p: "9\x00" * 40)
        self.assertLessEqual(len(m.detect("desk")["version"]), na.VERSION_MAX)
        self.assertNotIn("\x00", m.detect("desk")["version"])

    def test_detection_never_raises_and_is_cached(self):
        calls = []

        def exists(path):
            calls.append(path)
            raise PermissionError("no")

        m = self.manager(fs=exists)
        self.assertEqual(m.detect("desk")["state"], "missing")
        n = len(calls)
        m.detect("desk")
        self.assertEqual(len(calls), n)  # cached
        m.detect("desk", fresh=True)
        self.assertGreater(len(calls), n)


class ReportTests(Base):
    def test_the_heartbeat_list_has_chrome_first_and_the_exact_shape(self):
        m = self.manager(fs=FakeFS(r"C:\Program Files\Desk\Desk.exe"))
        out = m.report(["desk", "pageonly", "chatgpt", "desk", "", None, "x" * 65])
        self.assertEqual(out, [{"id": "chrome", "state": "installed", "version": "1.2.3.4"},
                               {"id": "desk", "state": "installed", "version": "1.2.3.4"},
                               {"id": "pageonly", "state": "missing", "version": ""},
                               {"id": "chatgpt", "state": "web", "version": ""}])
        for row in out:
            self.assertEqual(set(row), {"id", "state", "version"})
            self.assertIn(row["state"], na.STATES)

    def test_at_most_sixty_and_chrome_missing_is_reported(self):
        def no_chrome():
            from swangz_client import workspace_launcher as wl
            raise wl.LaunchError("no_browser")
        m = self.manager(browser=no_chrome)
        out = m.report([f"tool-{i}" for i in range(100)])
        self.assertEqual(len(out), na.REPORT_MAX)
        self.assertEqual(out[0], {"id": "chrome", "state": "missing", "version": ""})

    def test_installing_and_failed_states_are_reported(self):
        m = self.manager(fs=FakeFS(WINGET), run=Runner(code=1))
        m._busy["desk"] = "installing"
        self.assertEqual(m.report(["desk"])[1]["state"], "installing")
        del m._busy["desk"]
        plan = m.plan("desk")
        m.execute(plan)
        self.assertEqual(m.report(["desk"])[1]["state"], "failed")

    def test_core_sends_the_list_in_the_heartbeat_and_survives_a_broken_manager(self):
        client = core.Client(paths=core.Paths(data=self.data))
        client.store.state = lambda: {"installed": {}}
        client.store.device = lambda: {"key_storage": "file"}
        client.store.manifest = lambda: {"tools": [{"id": "chatgpt", "name": "ChatGPT", "kind": "site"},
                                                   {"id": "antigravity", "name": "Antigravity", "kind": "dev"}],
                                         "apps": [{"id": "canva", "name": "Canva"}],
                                         "packages": [{"id": "codex", "name": "Codex", "install": {"type": "agent"}}]}
        client._native = mock.Mock()
        client._native.report.return_value = [{"id": "chrome", "state": "missing", "version": ""}]
        body = client._heartbeat_body()
        client._native.report.assert_called_once_with(["chatgpt", "antigravity", "canva", "codex"])
        self.assertEqual(body["apps"], [{"id": "chrome", "state": "missing", "version": ""}])
        client._native.report.side_effect = RuntimeError("boom")
        self.assertNotIn("apps", client._heartbeat_body())  # the check-in still goes

    def test_tools_fall_back_to_apps_and_agent_packages_on_an_older_hub(self):
        client = core.Client(paths=core.Paths(data=self.data))
        client.store.manifest = lambda: {"apps": [{"id": "canva", "name": "Canva", "category": "Design"}],
                                         "packages": [{"id": "claude-code", "name": "Claude Code",
                                                       "install": {"type": "agent"}},
                                                      {"id": "brand", "name": "Brand", "install": {"type": "bundle"}}]}
        self.assertEqual(client.tools(), [{"id": "canva", "name": "Canva", "kind": "site", "category": "Design"},
                                          {"id": "claude-code", "name": "Claude Code", "kind": "dev", "category": "Coding"}])
        client.store.manifest = lambda: None
        self.assertEqual(client.tools(), [])


class WingetListTests(Base):
    EXPORT = ('{"$schema": "https://aka.ms/winget-packages.schema.2.0.json", "Sources": [{"Packages": ['
              '{"PackageIdentifier": "Desk.Desk", "Version": "3.1"}, {"PackageIdentifier": "9ABCDEF12345"}],'
              ' "SourceDetails": {"Name": "winget"}}]}')

    def exporter(self, text, code=0):
        data = self.data

        def run(argv, **kw):
            self.exports.append((list(argv), kw))
            (data / ".winget-export.json").write_text(text, encoding="utf-8")
            return SimpleNamespace(returncode=code, stdout="", stderr="")
        self.exports = []
        return run

    def test_parse_reads_ids_and_versions_and_refuses_other_shapes(self):
        self.assertEqual(na.parse_winget_export(self.EXPORT.encode("utf-8-sig")), {"desk.desk": "3.1", "9abcdef12345": ""})
        for bad in ("[]", '{"Sources": 5}', "not json"):
            with self.assertRaises(ValueError):
                na.parse_winget_export(bad)

    def test_an_app_winget_installed_somewhere_unpublished_is_found_through_winget(self):
        m = self.manager(fs=FakeFS(WINGET), run=self.exporter(self.EXPORT))
        self.assertEqual(m.detect("desk")["state"], "missing")  # nothing listed yet, but there are paths to look at
        m.refresh_winget()
        self.assertEqual(m.detect("desk"), {"state": "installed", "version": "3.1", "path": "", "via": "winget"})
        argv, kw = self.exports[0]
        self.assertEqual(argv, [WINGET, "export", "-o", str(self.data / ".winget-export.json"), "--include-versions",
                                "--accept-source-agreements", "--disable-interactivity"])
        self.assertEqual(kw["timeout"], na.WINGET_EXPORT_TIMEOUT)
        self.assertFalse((self.data / ".winget-export.json").exists())  # read, then deleted
        m.refresh_winget()
        self.assertEqual(len(self.exports), 1)  # cached
        with self.assertRaisesRegex(LookupError, "Start menu"):
            m.launch("desk")  # found, but no published path to start it from
        self.assertEqual(self.started, [])

    def test_a_tool_that_cannot_be_checked_is_unknown_and_left_out_of_the_report(self):
        m = self.manager(run=self.exporter("garbage"))
        self.assertEqual(m.detect("desk")["state"], "missing")
        table = dict(TABLE, nocheck=na.Entry("Suite", "Suite Inc.", na.Way(na.NATIVE, winget="Suite.Installer",
                                                                            source="winget", check=False,
                                                                            download="https://suite.example/",
                                                                            note="Installs the suite's installer.",
                                                                            sources=("https://suite.example/",)),
                                             na.Way(na.NATIVE, download="https://suite.example/",
                                                    sources=("https://suite.example/",)), na.VERIFIED))
        with mock.patch.dict(na.APPS, table, clear=True):
            m = self.manager(fs=FakeFS(WINGET), run=self.exporter('{"Sources": [{"Packages": '
                                                                  '[{"PackageIdentifier": "Suite.Installer"}]}]}'))
            m.refresh_winget()
            self.assertEqual(m.detect("nocheck")["state"], "unknown")  # the installer being there says nothing
            self.assertEqual([r["id"] for r in m.report(["nocheck", "desk"])], ["chrome", "desk"])
            self.assertIn("Installs the suite's installer.", m.consent_text(m.plan("nocheck")))
            self.assertEqual(m.plan("nocheck", "repair").argv[1], "install")
            self.assertEqual(self.manager("macos").detect("nocheck")["state"], "unknown")


class PlanAndConsentTests(Base):
    def test_windows_installs_through_winget_with_the_exact_arguments(self):
        m = self.manager(fs=FakeFS(WINGET))
        plan = m.plan("desk")
        self.assertEqual(plan.argv, (WINGET, "install", "--id", "Desk.Desk", "--exact", "--source", "winget",
                                     "--accept-source-agreements", "--accept-package-agreements"))
        store = m.plan("storeapp")
        self.assertEqual(store.argv[3:7], ("9ABCDEF12345", "--exact", "--source", "msstore"))
        self.assertEqual(store.where, "the Microsoft Store")

    def test_winget_on_path_is_the_fallback_and_without_winget_the_download_page_opens(self):
        m = self.manager(which=lambda name: r"C:\Tools\winget.exe" if name == "winget" else None)
        self.assertEqual(m.plan("desk").argv[0], r"C:\Tools\winget.exe")
        m = self.manager()
        plan = m.plan("desk")
        self.assertEqual((plan.kind, plan.url, plan.argv), ("page", "https://desk.example/download", ()))
        self.assertEqual(self.manager(fs=FakeFS(WINGET)).plan("pageonly").kind, "page")

    def test_macos_only_ever_opens_the_vendor_page(self):
        plan = self.manager("macos").plan("desk")
        self.assertEqual((plan.kind, plan.url), ("page", "https://desk.example/download"))

    def test_a_cli_installs_in_a_visible_terminal_with_the_documented_command(self):
        for system in ("windows", "macos"):
            plan = self.manager(system).plan("tool-cli")
            self.assertEqual((plan.kind, plan.argv), ("terminal", CLI["toolcli"][system]))

    def test_the_real_cli_plans_are_exactly_these(self):
        """Pinned: what a person agrees to for Claude Code and Codex on each system (vendor-documented)."""
        with mock.patch.dict(na.APPS, REAL_APPS, clear=True), \
                mock.patch.dict(na.CLI_INSTALL, REAL_CLI, clear=True):
            win = self.manager(fs=FakeFS(WINGET))
            for tool, wid in (("claude-code", "Anthropic.ClaudeCode"), ("codex", "OpenAI.Codex")):
                plan = win.plan(tool)
                self.assertEqual((plan.kind, plan.argv), ("terminal", (WINGET, "install", "--id", wid, "--exact",
                                 "--source", "winget", "--accept-source-agreements", "--accept-package-agreements")))
            mac = self.manager("macos")
            self.assertEqual(mac.plan("claude-code").argv, ("bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"))
            self.assertEqual(mac.plan("codex").argv, ("bash", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh"))
            self.assertEqual(self.manager().plan("claude-code").kind, "page")  # no winget: Anthropic's setup page
            self.assertEqual(self.manager().plan("claude-code").url, "https://code.claude.com/docs/en/setup")

    def test_web_tools_and_linux_have_nothing_to_install(self):
        self.assertIsNone(self.manager().plan("chatgpt"))
        self.assertIsNone(self.manager("linux").plan("desk"))

    def test_repair_upgrades_what_is_installed_and_installs_what_is_missing(self):
        fs = FakeFS(WINGET, r"C:\Program Files\Desk\Desk.exe")
        self.assertEqual(self.manager(fs=fs).plan("desk", "repair").argv[1], "upgrade")
        self.assertEqual(self.manager(fs=FakeFS(WINGET)).plan("desk", "repair").argv[1], "install")

    def test_the_question_names_the_app_the_publisher_and_the_source(self):
        m = self.manager(fs=FakeFS(WINGET))
        text = m.consent_text(m.plan("desk"))
        for said in ("Install Desk on this computer?", "App: Desk", "Publisher: Desk Inc.",
                     "From: winget, Microsoft's app installer"):
            self.assertIn(said, text)

    def test_nothing_runs_unless_the_person_says_yes(self):
        for answer in (False, None, "yes", 1):
            m = self.manager(fs=FakeFS(WINGET))
            out = m.install("desk", consent=lambda text, a=answer: a)
            self.assertEqual(out["message"], "Nothing was changed.")
            self.assertEqual(self.run.calls, [])
            self.assertEqual(self.pages + self.terminals, [])
        m = self.manager(fs=FakeFS(WINGET))
        self.assertEqual(m.install("desk", consent=None)["message"], "Nothing was changed.")
        self.assertEqual(self.run.calls, [])


class ExecuteTests(Base):
    def test_a_winget_install_runs_hidden_with_a_clean_environment_and_a_timeout(self):
        fs = FakeFS(WINGET)
        run = Runner(code=0, fs=fs, adds=r"C:\Users\grace\AppData\Local\Programs\Desk\Desk.exe")
        m = self.manager(fs=fs, run=run)
        out = m.install("desk", consent=lambda text: True)
        self.assertEqual(out, {"state": "installed", "message": "Desk is installed."})
        argv, kw = run.calls[0]
        self.assertEqual(argv[:2], [WINGET, "install"])
        self.assertIs(kw["shell"], False)
        self.assertEqual(kw["timeout"], na.WINGET_INSTALL_TIMEOUT)
        self.assertEqual(kw["creationflags"], na.CREATE_NO_WINDOW)
        self.assertNotIn("ANTHROPIC_API_KEY", kw["env"])
        self.assertNotIn("SWANGZ_AI_KEY", kw["env"])
        self.assertNotIn("sk-never", " ".join(argv))
        self.assertEqual(m.detect("desk")["state"], "installed")

    def test_a_failed_or_timed_out_install_says_so_and_reports_failed(self):
        for run, words in ((Runner(code=0x8A150010), "code 2316632080"),
                           (Runner(raises=subprocess.TimeoutExpired("winget", 1)), "didn't finish in time")):
            m = self.manager(fs=FakeFS(WINGET), run=run)
            out = m.install("desk", consent=lambda text: True)
            self.assertEqual(out["state"], "failed")
            self.assertIn(words, out["message"])
            self.assertEqual(m.detect("desk")["state"], "failed")

    def test_upgrade_with_nothing_to_upgrade_is_up_to_date(self):
        fs = FakeFS(WINGET, r"C:\Program Files\Desk\Desk.exe")
        m = self.manager(fs=fs, run=Runner(code=na.WINGET_UP_TO_DATE))
        out = m.install("desk", consent=lambda text: True, action="repair")
        self.assertEqual(out, {"state": "installed", "message": "Desk is installed. It is up to date."})

    def test_success_that_cannot_be_found_is_not_claimed(self):
        m = self.manager(fs=FakeFS(WINGET), run=Runner(code=0))
        out = m.install("desk", consent=lambda text: True)
        self.assertEqual(out["state"], "missing")
        self.assertIn("can't find Desk", out["message"])

    def test_a_page_plan_opens_only_the_tables_page(self):
        m = self.manager("macos")
        out = m.install("desk", consent=lambda text: True)
        self.assertEqual(self.pages, ["https://desk.example/download"])
        self.assertEqual(self.run.calls, [])
        self.assertIn("download page", out["message"])

    def test_a_terminal_plan_shows_the_command_in_a_terminal(self):
        m = self.manager("macos")
        out = m.install("tool-cli", consent=lambda text: True)
        self.assertEqual(self.terminals, [list(CLI["toolcli"]["macos"])])
        self.assertEqual(out["state"], "installing")
        self.assertEqual(self.run.calls, [])

    def test_a_stale_or_forged_plan_is_refused(self):
        m = self.manager(fs=FakeFS(WINGET))
        plan = m.plan("desk")
        forged = plan._replace(argv=(WINGET, "install", "--id", "Evil.Evil"))
        self.assertEqual(m.execute(forged)["state"], "failed")
        self.assertEqual(m.execute(plan._replace(kind="page", url="https://evil.example/"))["state"], "failed")
        self.assertEqual(self.run.calls, [])
        self.assertEqual(self.pages, [])

    def test_update_check_is_a_dry_list_and_otherwise_says_how_it_updates(self):
        fs = FakeFS(WINGET)
        m = self.manager(fs=fs, run=Runner(code=0, stdout="Desk  Desk.Desk  1.0  1.1  winget"))
        self.assertEqual(m.check_update("desk"), "An update is waiting. Press Repair to install it.")
        argv, kw = self.run.calls[0]
        self.assertEqual(argv, [WINGET, "list", "--id", "Desk.Desk", "--exact", "--source", "winget",
                                "--upgrade-available", "--accept-source-agreements", "--disable-interactivity"])
        self.assertEqual(kw["timeout"], na.WINGET_CHECK_TIMEOUT)
        m = self.manager(fs=fs, run=Runner(code=na.WINGET_NOT_FOUND))
        self.assertEqual(m.check_update("desk"), "No update waiting.")
        self.assertEqual(self.manager("macos").check_update("desk"), "Updates itself.")
        self.assertEqual(self.manager().check_update("chatgpt"), "Opens on the web: nothing to update on this computer.")


class LaunchTests(Base):
    def test_windows_opens_the_detected_program_file(self):
        m = self.manager(fs=FakeFS(r"C:\Program Files\Desk\Desk.exe"))
        self.assertEqual(m.launch("desk"), "Opened Desk.")
        self.assertEqual(self.started, [r"C:\Program Files\Desk\Desk.exe"])
        self.popen.assert_not_called()
        self.assertIn(" desktop desk", (self.data / na.LOG).read_text())

    def test_a_store_app_opens_through_explorer_by_its_app_id(self):
        m = self.manager(fs=FakeFS(r"C:\Users\grace\AppData\Local\Packages\StoreCo.StoreApp_abc123"))
        m.launch("storeapp")
        argv = self.popen.call_args.args[0]
        self.assertEqual(argv, [r"C:\Windows\explorer.exe", r"shell:AppsFolder\StoreCo.StoreApp_abc123!App"])
        self.assertIs(self.popen.call_args.kwargs["shell"], False)

    def test_macos_opens_the_detected_app_by_path(self):
        m = self.manager("macos", fs=FakeFS("/Applications/Desk.app"))
        m.launch("desk")
        self.assertEqual(self.popen.call_args.args[0], ["/usr/bin/open", "-a", "/Applications/Desk.app"])
        self.assertNotIn("ANTHROPIC_API_KEY", self.popen.call_args.kwargs["env"])

    def test_nothing_starts_for_a_missing_web_or_cli_tool(self):
        m = self.manager()
        for tool in ("desk", "chatgpt", "tool-cli"):
            with self.assertRaises(LookupError):
                m.launch(tool)
        self.assertEqual(self.started, [])
        self.popen.assert_not_called()

    def test_a_program_that_fails_to_start_says_repair(self):
        m = self.manager(fs=FakeFS(r"C:\Program Files\Desk\Desk.exe"), start=mock.Mock(side_effect=OSError("x")))
        with self.assertRaisesRegex(LookupError, "Press Repair"):
            m.launch("desk")

    def test_recent_opens_merges_both_logs_newest_first(self):
        (self.data / "workspace-open.log").write_text("100 open canva\nnonsense\n300 open chatgpt\n")
        (self.data / na.LOG).write_text("200 desktop claude\n")
        self.assertEqual(na.recent_opens(self.data), [(300, "chatgpt", "web"), (200, "claude", "desktop"),
                                                      (100, "canva", "web")])


# ------------------------------------------------------------------ the real table

HTTPS = re.compile(r"https://[a-z0-9.-]+\.[a-z]{2,}(/\S*)?\Z")
WINGET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*\.[A-Za-z0-9.+_-]+\Z")
STORE_ID = re.compile(r"[0-9A-Z]{12}\Z")


class TableTests(unittest.TestCase):
    """The shipped table: fixed facts with a source and a date, nothing the Hub could change."""

    def test_every_entry_is_complete_and_sourced(self):
        self.assertTrue(na.APPS)
        for tool, e in na.APPS.items():
            self.assertRegex(tool, r"\A[a-z0-9][a-z0-9-]{0,63}\Z")
            self.assertTrue(e.name and e.publisher, tool)
            self.assertRegex(e.verified, r"\A2026-\d\d-\d\d\Z")
            for system in ("windows", "macos"):
                w = getattr(e, system)
                self.assertIn(w.method, (na.NATIVE, na.CLI, na.WEB), (tool, system))
                if w.method == na.WEB:
                    continue
                self.assertTrue(w.sources, (tool, system))
                for url in (*w.sources, w.download):
                    if url:
                        self.assertRegex(url, HTTPS, (tool, system))
                self.assertTrue(w.download or w.winget or w.cli or w.paths, (tool, system))  # a way in, or a way to look
                if w.winget:
                    self.assertIn(w.source, ("winget", "msstore"), tool)
                    self.assertRegex(w.winget, STORE_ID if w.source == "msstore" else WINGET_ID, tool)
                if w.method == na.CLI:
                    self.assertIn(w.cli, na.CLI_INSTALL, tool)
                for p in w.paths:
                    self.assertTrue(p.startswith(("{", "/")), (tool, p))
                    self.assertNotIn("..", p)
                if system == "macos":
                    for p in w.paths:  # an app bundle at /Applications or ~/Applications, nothing else
                        self.assertRegex(p, r"\A(/Applications|\{Home\}/Applications|\{Home\}/\.local/bin)/[^/]+\Z", tool)

    def test_cli_commands_are_fixed_lists_naming_only_vendor_https_addresses(self):
        for key, spec in na.CLI_INSTALL.items():
            self.assertTrue(spec["command"].isidentifier() or re.fullmatch(r"[a-z-]+", spec["command"]), key)
            for system in ("windows", "macos"):
                argv = spec.get(system)
                if argv is None:
                    continue
                self.assertIsInstance(argv, tuple)
                for url in re.findall(r"https?://\S+", " ".join(argv)):
                    self.assertTrue(url.startswith("https://"), (key, url))

    def test_the_hubs_new_tools_are_in_the_table(self):
        for tool in ("grok", "antigravity", "google-flow", "claude", "chatgpt", "claude-code", "codex"):
            self.assertIn(tool, na.APPS)

    def test_the_module_never_reads_commands_from_the_manifest_or_the_network(self):
        source = (ROOT / "swangz_client" / "native_apps.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for forbidden in ("manifest", "urlopen", "urllib", "Api", "eval", "exec", "store"):
            self.assertNotIn(forbidden, names, forbidden)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("runas", source)
        self.assertNotIn("sudo", source)


if __name__ == "__main__":
    unittest.main()
