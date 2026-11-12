"""W3 client: the Swangz workspace window (docs/W3-THREAT-NOTE.md, tests 3-10, and the open_url inventory of §9.1).

Temporary folders and stubs only: no real browser starts, no provider is contacted.
"""
import ast
import builtins
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import browser_profiles as bp
from swangz_client import core
from swangz_client import workspace_launcher as wl

ROOT = Path(__file__).resolve().parents[1]
POSIX = os.name != "nt"
HOSTS = ["chatgpt.com", "openai.com"]
URL = "https://chatgpt.com/?model=auto"


class FakeProc:
    def __init__(self, pid=4242, alive=True):
        self.pid, self.alive, self.terminated = pid, alive, False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.terminated, self.alive = True, False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.alive = False


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        self.data.mkdir(mode=0o700)
        self.owner = bp.Owner("https://hub.example", "7", "dev-1")
        self.calls = []

        def popen(argv, **kw):
            self.calls.append((argv, kw))
            return FakeProc()
        self.launcher = wl.Launcher(self.data, popen=popen, finder=lambda: "/opt/google/chrome/chrome", acl=lambda p: True)


class AddressTests(unittest.TestCase):
    """Test 3: the address check rejects the S2 list against the manifest hosts."""

    def test_bad_addresses_are_refused(self):
        bad = ["javascript:alert(1)", "http://chatgpt.com/", "file:///etc/passwd", "https://user:pw@chatgpt.com/",
               "https://user@chatgpt.com/", "https://evil.example/", "https://chatgpt.com.evil.example/", "https://notchatgpt.com/",
               "https://chatgpt.com/\nx", "https://chatgpt.com/ x", "https://chatgpt.com/\tx", "-https://chatgpt.com/",
               " https://chatgpt.com/", "https://chatgpt.com:8443/", "https://1.2.3.4/", "https://[::1]/", "https://chatgpt.com\\@evil.example/",
               "https://chatgpt.com/" + "a" * 2048, "", None, 5, "HTTPS://chatgpt.com/", "https:/chatgpt.com/", "https://chatgpt.com/\x7f"]
        for url in bad:
            with self.assertRaises(wl.LaunchError, msg=repr(url)) as cm:
                wl.check_url(url, HOSTS)
            self.assertEqual(cm.exception.code, "unsafe_address", repr(url))
            self.assertNotIn(str(url), str(cm.exception)) if url else None

    def test_tool_hosts_and_their_subdomains_pass(self):
        for url in ("https://chatgpt.com/", URL, "https://auth.openai.com/log-in", "https://chatgpt.com:443/x"):
            self.assertEqual(wl.check_url(url, HOSTS), url)

    def test_no_hosts_refuses(self):
        for hosts in (None, [], ["", "a b", "*.com", "https://chatgpt.com"], "chatgpt.com"):
            with self.assertRaises(wl.LaunchError) as cm:
                wl.check_url("https://chatgpt.com/", hosts)
            self.assertEqual(cm.exception.code, "no_hosts", hosts)


class BrowserTests(unittest.TestCase):
    """Test 4: fixed locations only; never PATH, snap, scripts, writable files or the default browser."""

    def test_path_is_never_searched(self):
        fake = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, fake, True)
        (fake / "google-chrome").write_text("#!/bin/sh\n")
        (fake / "google-chrome").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(fake)}), mock.patch("shutil.which") as which:
            with self.assertRaises(wl.LaunchError) as cm:
                wl.find_browser("linux", exists=lambda p: False)
            which.assert_not_called()
        self.assertEqual(cm.exception.code, "no_browser")
        self.assertTrue(cm.exception.install)

    def test_fixed_candidates(self):
        self.assertEqual(wl.candidates("linux"), ["/opt/google/chrome/chrome", "/usr/lib/chromium/chromium",
                                                  "/usr/lib/chromium-browser/chromium-browser"])
        self.assertEqual(wl.candidates("darwin"), ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"])
        env = {"ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "relative\\path", "LocalAppData": "C:\\Users\\a\\AppData\\Local"}
        got = wl.candidates("win32", env)
        self.assertEqual(len(got), 2 if os.name == "nt" else len([v for v in env.values() if os.path.isabs(v)]))
        self.assertTrue(all(p.endswith(os.path.join("Google", "Chrome", "Application", "chrome.exe")) for p in got))
        self.assertEqual(wl.candidates("freebsd"), [])

    def test_first_usable_wins_and_none_means_no_browser(self):
        chromium = "/usr/lib/chromium/chromium"
        self.assertEqual(wl.find_browser("linux", exists=lambda p: p == chromium, usable_linux=lambda p: True), chromium)
        with self.assertRaises(wl.LaunchError):
            wl.find_browser("linux", exists=lambda p: True, usable_linux=lambda p: False)

    def test_default_browser_is_never_used(self):
        with mock.patch("webbrowser.open") as wopen, mock.patch("webbrowser.get") as wget:
            with self.assertRaises(wl.LaunchError):
                wl.find_browser("linux", exists=lambda p: False)
            wopen.assert_not_called(); wget.assert_not_called()

    @unittest.skipUnless(POSIX, "POSIX file modes")
    def test_linux_refuses_scripts_writable_files_and_snap(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        elf, script, writable = d / "elf", d / "script", d / "writable"
        elf.write_bytes(b"\x7fELF" + b"\0" * 60); elf.chmod(0o755)
        script.write_bytes(b"#!/bin/sh\nexec evil\n"); script.chmod(0o755)
        writable.write_bytes(b"\x7fELF" + b"\0" * 60); writable.chmod(0o775)
        self.assertTrue(wl._usable_linux(str(elf)))
        self.assertFalse(wl._usable_linux(str(script)))
        self.assertFalse(wl._usable_linux(str(writable)))
        for snap in ("/snap/chromium/123/usr/lib/chromium-browser/chrome", "/var/lib/snapd/snap/chromium/1/chrome"):
            with mock.patch.object(wl.os.path, "realpath", return_value=snap):
                self.assertFalse(wl._usable_linux(str(elf)))


@unittest.skipUnless(POSIX, "POSIX owner and mode checks; Windows is covered by the ACL tests")
class FolderTests(Base):
    """Test 5: any doubt about the folder refuses launch and leaves it untouched."""

    def prepared(self):
        folder = bp.Profiles(self.data).prepare(self.owner)
        (folder / "Cookies").write_bytes(b"secret")
        return folder

    def snapshot(self, folder):
        return sorted((str(p.relative_to(self.data)), p.is_symlink()) for p in self.data.rglob("*"))

    def refused(self, folder, owner=None):
        before = self.snapshot(folder)
        with self.assertRaises(wl.LaunchError) as cm:
            wl.verify_folder(folder, owner or self.owner)
        self.assertEqual(cm.exception.code, "folder")
        self.assertEqual(self.snapshot(folder), before)

    def test_the_prepared_folder_passes(self):
        folder = self.prepared()
        self.assertEqual(wl.verify_folder(folder, self.owner), folder)

    def test_wrong_mode_refuses(self):
        folder = self.prepared()
        for mode in (0o750, 0o755, 0o500):
            folder.chmod(mode)
            self.refused(folder)
        folder.chmod(0o700)

    def test_wrong_owner_refuses(self):
        folder = self.prepared()
        with mock.patch.object(bp.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(wl.LaunchError):
                wl.verify_folder(folder, self.owner)
        self.assertTrue((folder / "Cookies").exists())

    def test_symlinked_folder_refuses(self):
        folder = self.prepared()
        real = self.tmp / "elsewhere"
        folder.rename(real)
        folder.symlink_to(real, target_is_directory=True)
        self.refused(folder)
        self.assertTrue((real / "Cookies").exists())

    def test_symlinked_root_refuses(self):
        folder = self.prepared()
        root = folder.parent
        moved = self.tmp / "moved-root"
        root.rename(moved)
        root.symlink_to(moved, target_is_directory=True)
        self.refused(root / folder.name)
        self.assertTrue((moved / folder.name / "Cookies").exists())

    def test_missing_marker_refuses(self):
        folder = self.prepared()
        (folder / bp.MARKER).unlink()
        self.refused(folder)

    def test_each_marker_field_mismatch_refuses(self):
        folder = self.prepared()
        for field, value in (("origin", "https://other.example"), ("person_id", "8"), ("device_id", "dev-2"), ("os_user", os.getuid() + 1)):
            other = bp.Owner("https://hub.example", "7", "dev-1")
            other.fields[field] = value
            self.refused(folder, other)
        marker = folder / bp.MARKER
        for field, value in (("state", "retired"), ("os_user", str(os.getuid())), ("origin", "https://other.example")):
            original = marker.read_bytes()
            m = json.loads(original); m[field] = value
            marker.write_text(json.dumps(m)); marker.chmod(0o600)
            self.refused(folder)
            marker.write_bytes(original)


class AclTests(Base):
    """Test 6: on Windows an ACL that isn't owner-only, or that can't be read, refuses launch."""

    def test_unverified_acl_refuses_wherever_it_runs(self):
        folder = self.tmp / "f"
        for check in (lambda p: False, lambda p: None, mock.Mock(side_effect=OSError("unreadable"))):
            with mock.patch.object(bp, "_WINDOWS", True), mock.patch.object(bp, "_check"), \
                    mock.patch.object(bp.Profiles, "_marker", return_value=dict(self.owner.fields)):
                with self.assertRaises(wl.LaunchError) as cm:
                    wl.verify_folder(folder, self.owner, acl=check)
            self.assertEqual(cm.exception.code, "folder")

    @unittest.skipUnless(os.name == "nt", "native Windows ACL (windows-latest runner)")
    def test_native_acl(self):
        from swangz_client import winacl
        self.assertRegex(winacl.current_sid(), r"^S-1-")
        folder = self.tmp / "acl"
        folder.mkdir()
        self.assertFalse(winacl.owner_only(str(folder)))  # inherited entries (SYSTEM, Administrators)
        winacl.restrict(str(folder))
        self.assertTrue(winacl.owner_only(str(folder)))
        subprocess.run(["icacls", str(folder), "/grant", "*S-1-1-0:(R)"], check=True, capture_output=True)
        self.assertFalse(winacl.owner_only(str(folder)))
        self.assertFalse(winacl.owner_only(str(self.tmp / "missing")))


class ProcessTests(Base):
    """Tests 7 and 8: the exact argument list and environment, the Popen call, the log line."""

    def test_exact_argv_and_popen_call(self):
        secrets_env = {"SWANGZ_KEY": "k", "ANTHROPIC_BASE_URL": "u", "ANTHROPIC_AUTH_TOKEN": "t", "OPENAI_API_KEY": "o",
                       "OPENAI_BASE_URL": "b", "HTTPS_PROXY": "p", "https_proxy": "p", "ALL_PROXY": "p", "NO_PROXY": "x",
                       "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1", "GEMINI_API_KEY": "g", "CODEX_HOME": "h", "LANG": "C.UTF-8"}
        with mock.patch.dict(os.environ, secrets_env):
            out = self.launcher.open("chatgpt", URL, HOSTS, self.owner)
        (argv, kw), = self.calls
        folder = bp.Profiles(self.data).prepare(self.owner)
        self.assertEqual(argv, ["/opt/google/chrome/chrome", "--user-data-dir=" + str(folder), "--no-first-run",
                                "--no-default-browser-check", URL])
        for item in argv:
            self.assertFalse(any(item.startswith(s) for s in wl.FORBIDDEN_SWITCHES), item)
        self.assertEqual({k: kw[k] for k in ("shell", "close_fds", "stdin", "stdout", "stderr")},
                         {"shell": False, "close_fds": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                          "stderr": subprocess.DEVNULL})
        env = kw["env"]
        for name in secrets_env:
            if name != "LANG":
                self.assertNotIn(name, env)
        self.assertEqual(env.get("LANG"), "C.UTF-8")
        self.assertEqual(out, {"tool": "chatgpt", "pid": 4242})

    def test_forbidden_switches_cannot_be_built(self):
        for switch in wl.FORBIDDEN_SWITCHES:
            with mock.patch.object(wl, "FIXED_SWITCHES", (switch + "=1",)):
                with self.assertRaises(wl.LaunchError):
                    wl.build_argv("/opt/google/chrome/chrome", "/tmp/x", URL)

    def test_log_line_has_no_address(self):
        self.launcher.clock = lambda: 1700000000
        self.launcher.open("chatgpt", URL, HOSTS, self.owner)
        text = (self.data / wl.LOG).read_text()
        self.assertEqual(text, "1700000000 open chatgpt\n")
        self.assertNotIn("chatgpt.com", text)

    def test_second_open_reuses_the_folder_and_keeps_the_first_pid(self):
        self.launcher.open("chatgpt", URL, HOSTS, self.owner)
        self.launcher.open("chatgpt", "https://chatgpt.com/c/1", HOSTS, self.owner)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][0][1], self.calls[1][0][1])  # same --user-data-dir
        self.assertEqual(self.launcher.pid(), 4242)
        self.assertEqual(len([p for p in (self.data / "browser-profiles").iterdir() if bp.FOLDER.fullmatch(p.name)]), 1)
        first = self.launcher.process
        self.assertTrue(self.launcher.close())
        self.assertTrue(first.terminated)
        self.assertFalse(self.launcher.close())

    def test_refusals_start_nothing(self):
        def no_browser():
            raise wl.LaunchError("no_browser")
        cases = [("chatgpt", "https://evil.example/", HOSTS), ("chatgpt", URL, []), ("../x", URL, HOSTS)]
        for tool, url, hosts in cases:
            with self.assertRaises(wl.LaunchError):
                self.launcher.open(tool, url, hosts, self.owner)
        self.launcher.finder = no_browser
        with self.assertRaises(wl.LaunchError):
            self.launcher.open("chatgpt", URL, HOSTS, self.owner)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.data / wl.LOG).exists())


class OpenAppTests(Base):
    """Test 9: a workspace tool never reaches open_url, on any refusal path."""

    def client(self, state="active", workspace=True, url=URL, api_error=None, contract=2, apps=None):
        paths = core.Paths(self.tmp / "home", self.data)
        opened = mock.Mock()
        c = core.Client(paths, sleep=lambda s: None, open_url=opened)
        app = {"id": "chatgpt", "name": "ChatGPT", "open": "https://hub.example/go/chatgpt?d=dev-1", "hosts": HOSTS,
               "workspace": workspace, "company_browser": False}
        manifest = {"apps": apps or [app], "browser": {"contract": contract, "person_id": "7", "device_id": "dev-1",
                                                       "workspace": {"state": state, "generation": 1}}}
        if contract is None:
            del manifest["browser"]
        c.store.manifest = lambda: manifest
        c.store.device = lambda: {"server": "https://hub.example"}
        c._reconnect_pending = lambda: False
        api = mock.Mock()
        api.call.side_effect = api_error or (lambda method, path, body=None, auth=True: {"ok": True, "url": url})
        c.api = lambda: api
        c.launcher = self.launcher
        return c, opened, api

    def test_workspace_tool_opens_in_the_workspace(self):
        c, opened, api = self.client()
        self.assertEqual(c.open_app("chatgpt"), "workspace")
        api.call.assert_called_once_with("POST", "/device/open", {"tool": "chatgpt"})
        opened.assert_not_called()
        self.assertEqual(self.calls[0][0][-1], URL)

    def test_no_refusal_falls_back_to_the_default_browser(self):
        def no_browser():
            raise wl.LaunchError("no_browser")
        cases = [dict(state="suspended"), dict(state="retired"), dict(url="https://evil.example/"),
                 dict(api_error=core.ApiFailure(403, "not_assigned", "No.")), dict(api_error=core.ApiFailure(409, "unsafe_address", "No."))]
        for case in cases:
            c, opened, _ = self.client(**case)
            with self.assertRaises((wl.LaunchError, core.ApiFailure), msg=case):
                c.open_app("chatgpt")
            opened.assert_not_called()
        c, opened, _ = self.client()
        self.launcher.finder = no_browser
        with self.assertRaises(wl.LaunchError):
            c.open_app("chatgpt")
        opened.assert_not_called()
        c, opened, _ = self.client()
        self.launcher.finder = lambda: "/opt/google/chrome/chrome"
        with mock.patch.object(wl, "verify_folder", side_effect=wl.LaunchError("folder")):
            with self.assertRaises(wl.LaunchError):
                c.open_app("chatgpt")
        opened.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_other_tools_open_go_in_the_workspace(self):
        """Shared-account and other Hub-handled tools open the Hub's /go/ address in the workspace window."""
        c, opened, api = self.client(workspace=False)
        self.launcher.finder = lambda: "/opt/google/chrome/chrome"
        self.assertEqual(c.open_app("chatgpt"), "workspace")
        api.call.assert_not_called()
        opened.assert_not_called()
        self.assertEqual(self.calls[0][0][-1], "https://hub.example/go/chatgpt?d=dev-1")

    def test_no_tool_ever_reaches_open_url_on_a_contract_2_device(self):
        """Manager review of #186: on a contract-2 device open_app never calls shell.open_url, for any tool."""
        apps = [{"id": "chatgpt", "open": "https://hub.example/go/chatgpt?d=dev-1", "hosts": HOSTS, "workspace": True},
                {"id": "midjourney", "open": "https://hub.example/go/midjourney?d=dev-1", "workspace": False,
                 "signin": "shared", "company_browser": True},
                {"id": "canva", "open": "https://hub.example/go/canva?d=dev-1", "workspace": False, "signin": "own"},
                {"id": "bad", "open": "https://evil.example/go/bad?d=dev-1", "workspace": False}]
        for state in ("active", "suspended", "retired"):
            c, opened, _ = self.client(state=state, apps=apps)
            self.launcher.finder = lambda: "/opt/google/chrome/chrome"
            with mock.patch("swangz_client.shell.open_url") as shell_open, mock.patch("webbrowser.open") as wb:
                for app in apps:
                    try:
                        c.open_app(app["id"])
                    except (wl.LaunchError, core.ApiFailure):
                        pass
            opened.assert_not_called()
            shell_open.assert_not_called()
            wb.assert_not_called()

    def test_without_a_workspace_nothing_opens(self):
        for contract in (None, 1):
            for workspace in (True, False):
                c, opened, api = self.client(contract=contract, workspace=workspace)
                with self.assertRaises(wl.LaunchError) as ctx:
                    c.open_app("chatgpt")
                self.assertEqual(ctx.exception.code, "no_workspace")
                self.assertIn("Update Swangz", str(ctx.exception))
                opened.assert_not_called()
                api.call.assert_not_called()
        self.assertEqual(self.calls, [])


class HubUrlTests(unittest.TestCase):
    """The Hub's own /go/ address: exactly the enrolled origin, this tool, this device, nothing else."""

    S = "https://hub.example"

    def test_accepts_the_exact_go_address(self):
        for url in ("https://hub.example/go/canva", "https://hub.example/go/canva?d=dev-1"):
            self.assertEqual(wl.check_hub_url(url, self.S, "canva", "dev-1"), url)
        self.assertEqual(wl.check_hub_url("https://hub.example:8443/go/canva", "https://hub.example:8443", "canva"),
                         "https://hub.example:8443/go/canva")

    def test_refuses_anything_else(self):
        bad = ["http://hub.example/go/canva", "https://hub.example.evil.example/go/canva", "https://evil.example/go/canva",
               "https://user@hub.example/go/canva", "https://user:pw@hub.example/go/canva", "https://hub.example:444/go/canva",
               "https://hub.example/go/chatgpt", "https://hub.example/go/canva/x", "https://hub.example/admin",
               "https://hub.example/go/canva#x", "https://hub.example/go/canva?d=other", "https://hub.example/go/canva?d=dev-1&x=1",
               "https://hub.example/go/canva?token=t", "https://hub.example/go/canva ", "https://hub.example\\@evil/go/canva",
               "https://sub.hub.example/go/canva", "", None, "https://hub.example/go/" + "a" * 2100]
        for url in bad:
            with self.assertRaises(wl.LaunchError, msg=url):
                wl.check_hub_url(url, self.S, "canva", "dev-1")
        for server in ("http://hub.example", "https://hub.example/x", "", None, "https://u@hub.example"):
            with self.assertRaises(wl.LaunchError, msg=server):
                wl.check_hub_url("https://hub.example/go/canva", server, "canva")
        with self.assertRaises(wl.LaunchError):
            wl.check_hub_url("https://hub.example/go/../admin", self.S, "../admin")


class BrowserListTests(unittest.TestCase):
    """Section 9.1 as amended: Google Chrome, and on Linux the .deb Chromium; never Edge, Brave or snap."""

    def test_only_chrome_and_deb_chromium(self):
        env = {"ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "C:\\Program Files (x86)", "LocalAppData": "C:\\L"}
        everything = wl.candidates("linux", env) + wl.candidates("darwin", env) + wl.candidates("win32", env)
        for path in everything:
            low = path.lower()
            self.assertFalse(any(w in low for w in ("edge", "brave", "snap", "opera", "vivaldi", "firefox")), path)
            self.assertTrue("chrome" in low or "chromium" in low, path)
        self.assertTrue(all(p.startswith(("/opt/google/chrome/", "/usr/lib/chromium")) for p in wl.candidates("linux", env)))


@unittest.skipUnless(POSIX, "path tracing uses POSIX paths")
class NoReadingTests(Base):
    """Test 10: nothing under the workspace folder is opened or listed except the marker."""

    def test_only_the_marker_is_touched(self):
        folder = bp.Profiles(self.data).prepare(self.owner)
        for name in ("Cookies", "Local State", "SingletonLock", "Preferences"):
            (folder / name).write_bytes(b"x")
        touched = []
        real_open, real_os_open, real_scandir, real_listdir = builtins.open, os.open, os.scandir, os.listdir

        def note(path):
            if isinstance(path, (str, bytes, os.PathLike)):
                touched.append(os.fspath(path))

        def t_open(path, *a, **k):
            note(path); return real_open(path, *a, **k)

        def t_os_open(path, *a, **k):
            note(path); return real_os_open(path, *a, **k)

        def t_scandir(path="."):
            note(path); return real_scandir(path)

        def t_listdir(path="."):
            note(path); return real_listdir(path)
        with mock.patch("builtins.open", t_open), mock.patch("os.open", t_os_open), mock.patch("os.scandir", t_scandir), \
                mock.patch("os.listdir", t_listdir):
            self.launcher.open("chatgpt", URL, HOSTS, self.owner)
        inside = [p for p in touched if os.path.abspath(p).startswith(str(folder) + os.sep) or os.path.abspath(p) == str(folder)]
        self.assertEqual(sorted(set(inside)), [str(folder / bp.MARKER)])


class InventoryTests(unittest.TestCase):
    """§9.1 and E1: every caller of open_url is listed; a new one fails here. I2: only two modules name the profiles root."""

    # core.login and gui._show_code: the Hub's own /device approval page (not an AI tool); gui.open_app: only the
    # Chrome install page (INSTALL_PAGE), after a no_browser refusal. core.open_app has none: tools never leave the workspace.
    ALLOWED = {("core.py", "login"), ("gui.py", "_show_code"), ("gui.py", "open_app")}

    def test_open_url_callers(self):
        found = set()
        for path in sorted((ROOT / "swangz_client").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for node in ast.walk(fn):
                        if isinstance(node, ast.Call) and (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) == "open_url":
                            found.add((path.name, fn.name))
        self.assertEqual(found, self.ALLOWED)

    def test_gui_open_url_targets(self):
        # gui.open_app may open only the Chrome install page; _show_code only the approval page.
        src = (ROOT / "swangz_client" / "gui.py").read_text(encoding="utf-8")
        self.assertIn("shell.open_url(INSTALL_PAGE)", src)
        self.assertEqual(src.count("open_url("), 2)
        self.assertEqual(wl.INSTALL_PAGE, "https://www.google.com/chrome/")

    def test_profiles_root_is_named_only_by_the_launcher_and_profiles(self):
        for path in sorted((ROOT / "swangz_client").glob("*.py")):
            if path.name in ("browser_profiles.py",):
                continue
            self.assertNotIn("browser-profiles", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
