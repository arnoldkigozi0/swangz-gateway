"""#333, D-026 D1-D4: a refused Open reaches no browser and starts no process; a company computer is never told to use
another browser for a shared account; and only the listed places may open anything in the default browser."""
import ast
import re
import contextlib
import io
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from swangz_client import cli, core
from swangz_client import repair
from swangz_client import workspace_launcher as wl
from tests import test_workspace_launcher as twl

ROOT = Path(__file__).resolve().parents[1]
PERSONAL_WORDS = "This is a shared company account. Open it from Swangz AI Hub, where turns are handed out."
COMPANY_WORDS = ("This is a shared company account. It does not open on this company computer yet; ask your "
                 "administrator.")
ELSEWHERE = r"(?i)hub|browser|chrome|chromium|edge|safari|firefox|/go/|https?:|www\."

APPS = [
    {"id": "chatgpt", "name": "ChatGPT", "open": "https://hub.example/go/chatgpt?d=dev-1", "hosts": twl.HOSTS,
     "workspace": True},
    {"id": "midjourney", "name": "Midjourney", "open": "https://hub.example/go/midjourney?d=dev-1", "hosts": twl.HOSTS,
     "workspace": False, "signin": "shared", "company_browser": True},
    {"id": "canva", "name": "Canva", "open": "https://hub.example/go/canva?d=dev-1", "hosts": twl.HOSTS, "signin": "own"},
]


class RefusalTests(twl.Base):
    """Company and personal computers alike: shared, Hub-denied, unknown and non-workspace tools."""

    def client(self, kind="personal", record=None, **kw):
        client, opened, api = twl.OpenAppTests.client(self, **{"apps": APPS, **kw})
        manifest = client.store.manifest()
        if kind:
            manifest["device"] = {"owner_kind": kind}
        client.store.manifest = lambda: manifest
        device = {"server": "https://hub.example", **({"owner_kind": record} if record else {})}
        client.store.device = lambda: device
        client.policy_check = None  # the machine policy gate has its own tests
        return client, opened, api

    def refused(self, client, opened, tool):
        """Open `tool`, expect a refusal, and prove that nothing was opened or started. -> the exception."""
        with mock.patch("webbrowser.open") as wb, mock.patch("webbrowser.open_new") as new, \
                mock.patch("webbrowser.open_new_tab") as tab, mock.patch("swangz_client.shell.open_url") as shell_open, \
                mock.patch("swangz_client.shell.open_hub") as hub, mock.patch("subprocess.Popen") as popen:
            with self.assertRaises((wl.LaunchError, core.ApiFailure)) as ctx:
                client.open_app(tool)
        for fake in (opened, wb, new, tab, shell_open, hub, popen):
            fake.assert_not_called()
        self.assertEqual(self.calls, [], tool)
        return ctx.exception

    def test_no_refused_tool_reaches_a_browser_or_starts_a_process(self):
        denied = core.ApiFailure(403, "not_assigned", "ChatGPT isn't assigned to you.")
        for kind in ("company", "personal"):
            shared = "shared_account_company" if kind == "company" else "shared_account"
            for tool, api_error, code in (("midjourney", None, shared), ("canva", None, shared),
                                          ("chatgpt", denied, "not_assigned"), ("nothing", None, "unavailable")):
                client, opened, api = self.client(kind, api_error=api_error)
                exc = self.refused(client, opened, tool)
                self.assertEqual(exc.code, code, (kind, tool))
                if tool != "chatgpt":
                    api.call.assert_not_called()  # never recorded at the Hub as an open

    def test_no_chrome_opens_nothing(self):
        def missing():
            raise wl.LaunchError("no_browser")
        self.launcher.finder = missing
        for kind in ("company", "personal"):
            client, opened, api = self.client(kind)
            self.assertEqual(self.refused(client, opened, "chatgpt").code, "no_browser")
            api.call.assert_not_called()

    def test_a_company_computer_is_told_to_ask_the_administrator(self):
        for tool in ("midjourney", "canva"):
            client, opened, _ = self.client("company")
            exc = self.refused(client, opened, tool)
            self.assertEqual(str(exc), COMPANY_WORDS)

    def test_a_personal_computer_keeps_the_hub_wording(self):
        client, opened, _ = self.client("personal", record="personal")
        exc = self.refused(client, opened, "midjourney")
        self.assertEqual((exc.code, str(exc)), ("shared_account", PERSONAL_WORDS))

    def test_either_record_saying_company_is_enough(self):
        for kind, record in (("company", None), (None, "company"), ("personal", "company"), ("company", "personal")):
            client, opened, _ = self.client(kind, record=record)
            self.assertEqual(self.refused(client, opened, "midjourney").code, "shared_account_company", (kind, record))

    def test_the_hubs_shared_refusal_is_reworded_only_on_a_company_computer(self):
        """The tool became shared after the last sync: the app asks, and the Hub's own words name the Hub's page."""
        words = "ChatGPT is a shared company account. Open it from Swangz AI Hub, where turns are handed out."
        for kind in ("company", "personal"):
            client, opened, api = self.client(kind, api_error=core.ApiFailure(409, "shared_account", words))
            exc = self.refused(client, opened, "chatgpt")
            api.call.assert_called_once()
            if kind == "company":
                self.assertEqual((exc.code, str(exc)), ("shared_account_company", COMPANY_WORDS))
            else:
                self.assertEqual((exc.code, exc.message), ("shared_account", words))


# Only shapes gateway/enroll.py's manifest can produce: under contract 2 every app carries `hosts` and
# `workspace = not shared`, so the only non-workspace tool is a shared account; without contract 2 neither key is sent.
ROW_APPS = [
    {"id": "chatgpt", "name": "ChatGPT", "signin": "own", "company_browser": False,
     "open": "https://hub.example/go/chatgpt?d=dev-1", "hosts": twl.HOSTS, "workspace": True},
    {"id": "midjourney", "name": "Midjourney", "signin": "shared", "company_browser": True,
     "open": "https://hub.example/go/midjourney?d=dev-1", "hosts": twl.HOSTS, "workspace": False},
]
NO_CONTRACT_APPS = [{k: v for k, v in a.items() if k not in ("hosts", "workspace")} | {"open": a["open"].split("?")[0]}
                    for a in ROW_APPS]


class AppsRowTests(RefusalTests):
    """The Apps page's line for each tool agrees with what a real Client's open_app does (#333 D-026 D4), in
    open_app's order: contract 2, workspace state, a refusal the latch holds, the workspace tool, then ownership."""

    def note(self, client, tool):
        try:
            from swangz_client import gui
        except ImportError:  # no tkinter on this Python
            self.skipTest("needs tkinter")
        return gui.app_note(client, next(a for a in client.apps() if a["id"] == tool))

    def check(self, words, code, kind="personal", tools=("chatgpt", "midjourney"), **kw):
        kw = {"apps": ROW_APPS, **kw}
        for tool in tools:
            client, opened, _ = self.client(kind, **kw)
            self.assertEqual(self.note(client, tool), words, (kind, tool))
            self.assertEqual(self.refused(client, opened, tool).code, code, (kind, tool))

    def test_without_a_contract_2_workspace_nothing_opens(self):
        for kind in ("company", "personal"):
            self.check("Doesn't open until this device has a Swangz workspace window. Update Swangz, or ask your admin",
                       "no_workspace", kind, contract=None, apps=NO_CONTRACT_APPS)

    def test_a_retired_workspace_says_so(self):
        for kind in ("company", "personal"):
            self.check("Doesn't open: your admin removed the Swangz workspace from this device", "retired", kind,
                       state="retired")

    def test_a_suspended_or_unknown_workspace_is_paused(self):
        for kind in ("company", "personal"):
            for state in ("suspended", "something-new"):
                self.check("Doesn't open while this device's workspace is paused. Ask your admin", "not_active", kind,
                           state=state)

    def test_a_refusal_the_latch_holds_wins_over_an_active_manifest(self):
        for code in ("revoked", "refused_by_hub", "generation_rollback"):
            for tool in ("chatgpt", "midjourney"):
                client, opened, _ = self.client("personal", apps=ROW_APPS)
                client.workspace.refuse(code, close=False)
                self.assertEqual(self.note(client, tool), "Doesn't open right now. Press Open to see why", code)
                self.assertEqual(self.refused(client, opened, tool).code, code)

    def test_the_workspace_tool_opens_in_the_workspace_window(self):
        for kind in ("company", "personal"):
            client, opened, _ = self.client(kind, apps=ROW_APPS)
            self.assertEqual(self.note(client, "chatgpt"), "Opens in your Swangz workspace window")
            self.assertEqual(client.open_app("chatgpt"), "workspace")
            opened.assert_not_called()

    def test_a_shared_account_row_depends_on_whose_computer_it_is(self):
        self.check("Shared company account. Doesn't open on this company computer yet; ask your administrator",
                   "shared_account_company", "company", tools=("midjourney",))
        self.check("Shared company account, one turn at a time. Open it from Swangz AI Hub", "shared_account",
                   "personal", tools=("midjourney",))

    def test_no_row_promises_a_company_browser_of_your_own(self):
        for kind in ("company", "personal"):
            for kw in ({}, {"state": "retired"}, {"contract": None, "apps": NO_CONTRACT_APPS}):
                client, _, _ = self.client(kind, **{"apps": ROW_APPS, **kw})
                for app in client.apps():
                    self.assertNotIn("company browser", self.note(client, app["id"]), (kind, kw, app["id"]))


class RepairPanelTests(unittest.TestCase):
    def test_the_company_panel_has_no_button_and_names_no_other_way_in(self):
        fix = repair.explain(wl.LaunchError("shared_account_company"))
        self.assertEqual((fix.message, fix.actions), (COMPANY_WORDS, ()))
        self.assertNotRegex(" ".join((fix.title, fix.message, *fix.steps)), ELSEWHERE)

    def test_the_personal_panel_is_unchanged(self):
        fix = repair.explain(wl.LaunchError("shared_account"))
        self.assertEqual((fix.title, fix.message, fix.actions), ("This one opens from Swangz AI Hub", PERSONAL_WORDS, ()))

    def test_the_command_line_prints_the_company_steps_without_another_way_in(self):
        client = mock.Mock()
        client.open_app.side_effect = wl.LaunchError("shared_account_company")
        out = io.StringIO()
        with mock.patch("webbrowser.open") as wb, mock.patch("swangz_client.shell.open_url") as shell_open, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(cli.main(["open", "midjourney"], client=client), 1)
        wb.assert_not_called()
        shell_open.assert_not_called()
        self.assertIn(COMPANY_WORDS, out.getvalue())
        self.assertNotRegex(out.getvalue(), ELSEWHERE)


# ------------------------------------------------------------------ the static allow-list

OPENERS = ("open_url", "webbrowser", "startfile", "ShellExecute", "ShellExecuteW", "ShellExecuteA", "ShellExecuteExW",
           "ShellExecuteExA")
OPENER_TEXT = (*OPENERS, "xdg-open")
# Programs that can hand an address to the default browser. Caught as an argv's first item (a list or tuple literal,
# or the program argument of os.exec*/os.spawn*/os.system/subprocess), or at the start of a shell string.
LAUNCHERS = ("open", "cmd", "explorer", "osascript", "xdg-open", "rundll32", "powershell", "pwsh", "gio",
             "x-www-browser", "sensible-browser", "gnome-open", "kde-open")
RUNNERS = ("system", "popen", "Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput",
           "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe", "spawnv", "spawnve", "spawnvp",
           "spawnvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "posix_spawn", "posix_spawnp")
# `open` and `start` are ordinary words too, so as a shell string they count only at the very start, followed by an
# address, a quote or an option, or followed by nothing when written lower- or upper-case (`'open ' + url`,
# `'START ' + url`; never `'Open ' + name`).
SHELL_LAUNCH = re.compile(r"(?:(?i:\s*(?:\S*[/\\])?(?:explorer|osascript|xdg-open|rundll32|powershell|pwsh|x-www-browser"
                          r"|sensible-browser|gnome-open|kde-open)(?:\.exe)?(?:\s|$))"
                          r"|(?i:\s*(?:\S*[/\\])?gio\s+open\b)"
                          r"|(?i:\s*(?:\S*[/\\])?cmd(?:\.exe)?\s+/[ck]\s+start\b)"
                          r"|(?:start|open|START|OPEN)\s+(?:$|-|[\"'{]|https?:)"
                          r"|(?i:(?:start|open)\s+(?:-|[\"'{]|https?:)))")
# Anywhere in a string: PowerShell's Start-Process, the Shell API by name, rundll32's URL handler, AppleScript's
# `open location`.
ANYWHERE = re.compile(r"(?i)\bstart-process\b|\bshellexecute|\bfileprotocolhandler\b|\bopen\s+location\b")
# Known limits, stated rather than caught: a program name held in a variable or built at run time ('xdg-' + 'open',
# a name from a file or the Hub), a getattr/__import__ whose name is computed, ctypes reaching the Shell API by a
# computed name or ordinal, and native code. These would need a run-time check, not a source scan.


def launcher(text):
    """-> True when `text`, an argv's first item, names one of LAUNCHERS (any folder, any case, with or without .exe)."""
    name = re.split(r"[/\\]", text.strip())[-1].lower()
    return (name[:-4] if name.endswith(".exe") else name) in LAUNCHERS


def browser_references(source):
    """-> Counter of the enclosing "Class.function" for every way `source` can reach the default browser: the names
    above used, aliased or imported, or spelled as a string (getattr, __import__, a command)."""
    found = Counter()
    tree = ast.parse(source)
    argv0 = {id(n.elts[0]) for n in ast.walk(tree) if isinstance(n, (ast.List, ast.Tuple)) and n.elts}
    for n in ast.walk(tree):  # the program argument: os.spawn* take a mode first
        name = getattr(n, "func", None) and getattr(n.func, "attr", getattr(n.func, "id", None))
        if isinstance(n, ast.Call) and name in RUNNERS:
            at = 1 if name.startswith("spawn") else 0
            if len(n.args) > at:
                argv0.add(id(n.args[at]))

    def visit(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = (*scope, node.name)
        hits = []
        if isinstance(node, ast.Name):
            hits = [node.id]
        elif isinstance(node, ast.Attribute):
            hits = [node.attr]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in OPENER_TEXT or SHELL_LAUNCH.match(node.value) or ANYWHERE.search(node.value) \
                    or (id(node) in argv0 and launcher(node.value)):
                hits = ["xdg-open"]  # any launcher counts once, as a way to the default browser
        elif isinstance(node, ast.Import):
            hits = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            hits = [(node.module or "").split(".")[0], *(a.name for a in node.names)]
        if any(h in OPENER_TEXT for h in hits):
            found[".".join(scope) or "<module>"] += 1
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, ())
    return found


class BrowserCallerTests(unittest.TestCase):
    """D-026 D1-D2. The count matters: a second use inside an allowed function fails here too."""

    ALLOWED = {
        # shell.open_url and shell.open_hub (fixed Hub pages), and the import they need
        ("shell.py", "<module>"): 1, ("shell.py", "open_url"): 1, ("shell.py", "open_hub"): 1,
        # the device-code step: the Hub's own approval page. __init__ only wires shell.open_url into the client.
        ("core.py", "Client.__init__"): 3, ("core.py", "Client.login"): 1, ("gui.py", "App._show_code"): 1,
        # the Chrome-page repair button: INSTALL_PAGE and nothing else
        ("gui.py", "App.repair_action"): 1,
        # a terminal window for a coding agent: `cmd.exe /c start ... cmd.exe /k` on Windows, Terminal via osascript on
        # macOS. Both start a fixed terminal program on the agent's own command, never an address.
        ("shell.py", "terminal_command"): 2,
        # D-026 A2: the system folder's Windows PowerShell, run on a fixed script that only reads Chrome's Authenticode
        # signature; the file name travels in an environment variable and nothing it runs takes an address.
        ("chrome_verify.py", "_powershell"): 1,
        # D-026 B1/B5: the UAC prompt. ShellExecuteExW with the "runas" verb starts this program's own file with the
        # fixed arguments "admin chrome-install"; it is never given an address.
        ("chrome_install.py", "Windows.elevate"): 1,
    }

    def sources(self):
        paths = sorted((ROOT / "swangz_client").glob("*.py"))
        self.assertLessEqual({"core.py", "gui.py", "cli.py", "repair.py", "workspace_launcher.py", "shell.py"},
                             {p.name for p in paths})
        return {p.name: p.read_text(encoding="utf-8") for p in paths}

    def test_only_the_listed_places_can_reach_the_default_browser(self):
        found = {(name, where): n for name, source in self.sources().items()
                 for where, n in browser_references(source).items()}
        self.assertEqual(found, self.ALLOWED)

    def test_the_gui_opens_only_the_approval_page_and_the_chrome_page(self):
        calls = {}
        for fn in ast.walk(ast.parse(self.sources()["gui.py"])):
            if isinstance(fn, ast.FunctionDef):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "open_url":
                        calls[fn.name] = [ast.unparse(a) for a in node.args]
        self.assertEqual(calls, {"_show_code": ["url"], "repair_action": ["INSTALL_PAGE"]})

    def test_the_scan_catches_every_way_of_adding_a_caller(self):
        for source, where in (
            ("def open_app(t):\n    shell.open_url(t)\n", "open_app"),
            ("class App:\n    def fix(self):\n        return lambda: self.client.open_url('x')\n", "App.fix"),
            ("def a():\n    import webbrowser as w\n    w.open('x')\n", "a"),
            ("from .shell import open_url as go\n", "<module>"),
            ("from webbrowser import open as go\n", "<module>"),
            ("def a():\n    getattr(shell, 'open_url')('x')\n", "a"),
            ("def a():\n    __import__('webbrowser').open('x')\n", "a"),
            ("def a():\n    os.startfile('x')\n", "a"),
            ("def a():\n    subprocess.run(['xdg-open', 'x'])\n", "a"),
            ("def a(u):\n    subprocess.run(['open', u])\n", "a"),
            ("def a(u):\n    subprocess.Popen(['/usr/bin/open', '-a', 'Safari', u])\n", "a"),
            ("def a(u):\n    subprocess.run(('cmd', '/c', 'start', '', u))\n", "a"),
            ("def a(u):\n    subprocess.run(['CMD.EXE', '/C', 'start', u])\n", "a"),
            ("def a(u):\n    os.system('cmd /c start ' + u)\n", "a"),
            ("def a(u):\n    os.system('start \"\" ' + u)\n", "a"),
            ("def a(u):\n    subprocess.run(['explorer', u])\n", "a"),
            ("def a(u):\n    subprocess.run([r'C:\\Windows\\explorer.exe', u])\n", "a"),
            ("def a(u):\n    subprocess.run(f'explorer {u}', shell=True)\n", "a"),
            ("def a(u):\n    os.system('open ' + u)\n", "a"),
            ("def a(u):\n    os.system(f'open \"{u}\"')\n", "a"),
            ("def a(u):\n    subprocess.run(['osascript', '-e', 'open location \"' + u + '\"'])\n", "a"),
            ("def a(u):\n    subprocess.run(['powershell', '-c', 'Start-Process ' + u])\n", "a"),
            ("def a(u):\n    subprocess.run('pwsh -c \"Start-Process ' + u + '\"', shell=True)\n", "a"),
            ("def a(u):\n    subprocess.run(['rundll32', 'url.dll,FileProtocolHandler', u])\n", "a"),
            ("def a(u):\n    subprocess.run(['gio', 'open', u])\n", "a"),
            ("def a(u):\n    os.system('gio open ' + u)\n", "a"),
            ("def a(u):\n    os.execv('/usr/bin/open', ['open', u])\n", "a"),
            ("def a(u):\n    os.execlp('xdg-open', 'xdg-open', u)\n", "a"),
            ("def a(u):\n    os.spawnlp(os.P_NOWAIT, 'open', 'open', u)\n", "a"),
            ("def a(u):\n    os.system('START ' + u)\n", "a"),
            ("def a(u):\n    os.system('START \"\" ' + u)\n", "a"),
            ("def a(u):\n    ctypes.windll.shell32.ShellExecuteW(None, 'open', u, None, None, 1)\n", "a"),
            ("def a(u):\n    subprocess.run(['sensible-browser', u])\n", "a"),
        ):
            self.assertIn(where, browser_references(source), source)


    def test_the_terminal_commands_are_exactly_these(self):
        """shell.terminal_command is allowed above only because it starts a terminal on the agent's own command. Its
        argument lists are pinned here, so a version that hands `start`, `open` or osascript an address fails."""
        import subprocess
        import sys
        from swangz_client import shell
        args = ["/Apps/Swangz", "run", "claude-code"]
        with mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(shell.terminal_command(args, "C:\\Users\\g"),
                             ["cmd.exe", "/c", "start", "Swangz", "/D", "C:\\Users\\g", "cmd.exe", "/k",
                              subprocess.list2cmdline(args)])
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(shell.terminal_command(args, "/Users/g"),
                             ["osascript", "-e", 'tell application "Terminal" to do script '
                              '"cd /Users/g && /Apps/Swangz run claude-code"', "-e", 'tell application "Terminal" to activate'])
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch("shutil.which", lambda t: "/usr/bin/xterm" if t == "xterm" else None):
            self.assertEqual(shell.terminal_command(args, "/home/g"),
                             ["xterm", "-e", "bash", "-lc", "cd /home/g && /Apps/Swangz run claude-code; exec bash"])

    def test_the_only_terminal_is_the_app_running_a_coding_agent(self):
        """Every open_terminal / terminal_command caller in the app, with its exact arguments: the app's own program
        with `run <agent>`, never an address."""
        calls = []
        for name, source in self.sources().items():
            for fn in ast.walk(ast.parse(source)):
                if isinstance(fn, ast.FunctionDef):
                    for node in ast.walk(fn):
                        if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) \
                                in ("open_terminal", "terminal_command"):
                            calls.append((name, fn.name, [ast.unparse(a) for a in node.args]))
        self.assertEqual(sorted(calls), [("gui.py", "open_agent", ["shell.app_command() + ['run', short]"]),
                                         ("shell.py", "open_terminal", ["args", "cwd"])])

    def test_ordinary_words_are_not_launchers(self):
        """`open` is also a sub-command, a dict key and a word in help text; only a command shape counts."""
        for source in ("a = app['open']\n", "p = sub.add_parser('open')\n", "x = 'open the window minimised'\n",
                       "def f():\n    return 'open'\n", "x = 'start Swangz at sign-in'\n", "x = 'Open ' + name\n", "log(t + ' open ' + u)\n", "x = ['opener', 'cmdline']\n"):
            self.assertEqual(browser_references(source), Counter(), source)


if __name__ == "__main__":
    unittest.main()
