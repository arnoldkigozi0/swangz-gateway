"""D-026 A1, B1-B6: Chrome is installed when missing, on Windows only, from Google only, after consent, by an
elevated step that checks itself and the download. Stand-ins for every Windows call, download and program, so these
run on any system; nothing here has run on a physical Windows PC or Mac."""

import ast
import base64
import io
import json
import ntpath
import os
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from swangz_client import chrome_install as ci
from tests.test_chrome_verify import GOOGLE, name

ROOT = Path(__file__).resolve().parent.parent
PF = r"C:\Program Files"
PD = r"C:\Program Data With Spaces"  # every path the elevated step builds has a space in it
APP = PF + r"\Swangz"
EXE = APP + r"\Swangz.exe"
INTERNAL = APP + r"\_internal"
CHROME = PF + r"\Google\Chrome\Application\chrome.exe"
SAFE = "O:SYD:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)(A;OICIIO;GA;;;CO)"
USER = "S-1-5-21-1-2-3-1001"
OTHER = name(("C", "US"), ("O", "Not Google LLC"), ("CN", "Someone"))


class FakeWindows:
    def __init__(self, sddl=None, existing=(), links=(), elevate_answer=0, program_files=PF):
        self.folders = {"ProgramFiles": program_files, "ProgramFiles(x86)": PF + " (x86)",
                        "System": r"C:\Windows\System32"}
        self.sddl, self.present, self.links = dict(sddl or {}), set(existing), set(links)
        self.made, self.removed, self.elevated, self.answer = [], [], [], elevate_answer
        self.program_files = program_files

    def known_folder(self, guid):
        return {ci.FOLDERID_PROGRAM_DATA: PD, ci.FOLDERID_PROGRAM_FILES: self.program_files}[guid]

    def system_folders(self):
        return dict(self.folders)

    def read_sddl(self, path):
        return self.sddl.get(path, SAFE)

    def is_link(self, path):
        return path in self.links

    def make_folder(self, path):
        if path in self.present:
            raise FileExistsError(path)
        self.present.add(path)
        self.made.append(path)

    def remove(self, path):
        self.present.discard(path)
        self.removed.append(path)

    def elevate(self, exe, params):
        self.elevated.append((exe, params))
        return self.answer


class Machine:
    """subprocess.run, the download and the file system around one install."""

    def __init__(self, win, signer=GOOGLE, status="Valid", msi_exit=0, chrome_after=True, chrome_before=False,
                 fetch_error=None, chrome_signer=GOOGLE):
        self.win, self.signer, self.status, self.msi_exit = win, signer, status, msi_exit
        self.chrome_after, self.chrome_signer, self.fetch_error = chrome_after, chrome_signer, fetch_error
        self.files = {CHROME} if chrome_before else set()
        self.calls, self.fetched = [], []

    def fetch(self, url, path):
        self.fetched.append((url, path))
        assert ntpath.dirname(path) in self.win.present, "downloaded outside the staging folder"
        if self.fetch_error:
            raise ci.Failed("download_failed", self.fetch_error)
        self.files.add(path)
        return 123

    def exists(self, path):
        return path in self.files

    def run(self, argv, **kw):
        self.calls.append((argv, kw))
        program = ntpath.basename(argv[0].replace("/", "\\")).lower()
        if program == "powershell.exe":
            target = kw["env"]["SWANGZ_CHROME_PATH"]
            signer = self.chrome_signer if target == CHROME else self.signer
            body = {"status": self.status, "subject": base64.b64encode(signer).decode() if signer else None}
            return SimpleNamespace(returncode=0, stdout=json.dumps(body).encode(), stderr=b"")
        if program == "msiexec.exe":
            if self.msi_exit in ci.MSI_SUCCESS and self.chrome_after:
                self.files.add(CHROME)
            return SimpleNamespace(returncode=self.msi_exit, stdout=b"", stderr=b"")
        raise AssertionError("unexpected program %r" % argv[0])

    def msiexec(self):
        return [c for c in self.calls if ntpath.basename(c[0][0]).lower() == "msiexec.exe"]

    def install(self):
        return ci.install_windows(self.win, run=self.run, fetch=self.fetch, remove=self.win.remove, exists=self.exists,
                                  digest=lambda p: "ab" * 32)


def staging_folders(win):
    return [p for p in win.made if ntpath.dirname(p) == PD + r"\Swangz"]


class InstallTests(unittest.TestCase):
    def test_missing_chrome_is_downloaded_checked_installed_and_checked_again(self):
        win = FakeWindows()
        m = Machine(win)
        evidence = m.install()
        self.assertEqual(evidence["result"], "installed")
        self.assertEqual(evidence["chrome"], CHROME)
        self.assertEqual(evidence["msi_sha256"], "ab" * 32)  # evidence only
        self.assertEqual(m.fetched[0][0], "https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi")
        # signature of the MSI, msiexec, signature of the installed chrome.exe: in that order
        programs = [ntpath.basename(c[0][0]).lower() for c in m.calls]
        self.assertEqual(programs, ["powershell.exe", "msiexec.exe", "powershell.exe"])
        self.assertEqual(m.calls[2][1]["env"]["SWANGZ_CHROME_PATH"], CHROME)
        # the staging folder: admin-only root, a 128-bit random child, deleted afterwards
        self.assertEqual(win.made[0], PD + r"\Swangz")
        [staging] = staging_folders(win)
        self.assertRegex(ntpath.basename(staging), r"^[0-9a-f]{32}$")
        self.assertEqual(win.removed, [staging])
        self.assertNotIn(staging, win.present)

    def test_a_path_with_spaces_stays_one_argument_and_nothing_goes_through_a_shell(self):
        win = FakeWindows()
        m = Machine(win)
        m.install()
        [(argv, kw)] = m.msiexec()
        msi = m.fetched[0][1]
        self.assertIn(" ", msi)
        self.assertEqual(argv, [r"C:\Windows\System32\msiexec.exe", "/i", msi, "/qn", "/norestart"])
        for argv, kw in m.calls:
            self.assertIs(kw["shell"], False)
            self.assertIsInstance(argv, list)
            # no variable from the environment: only SystemRoot, from GetSystemDirectory (+ the file for the check)
            self.assertLessEqual(set(kw["env"]), {"SystemRoot", "SWANGZ_CHROME_PATH"})
            self.assertEqual(kw["env"]["SystemRoot"], r"C:\Windows")

    def test_a_wrong_signer_an_unsigned_file_or_a_bad_status_runs_nothing_and_leaves_no_staging(self):
        for signer, status in ((OTHER, "Valid"), (None, "NotSigned"), (GOOGLE, "HashMismatch")):
            with self.subTest(status=status):
                win = FakeWindows()
                m = Machine(win, signer=signer, status=status)
                with self.assertRaises(ci.Failed) as caught:
                    m.install()
                self.assertEqual(caught.exception.code, "bad_signature")
                self.assertEqual(m.msiexec(), [])
                [staging] = staging_folders(win)
                self.assertEqual(win.removed, [staging])

    def test_a_failed_download_runs_nothing_and_leaves_no_staging(self):
        win = FakeWindows()
        m = Machine(win, fetch_error="truncated")
        with self.assertRaises(ci.Failed) as caught:
            m.install()
        self.assertEqual(caught.exception.code, "download_failed")
        self.assertEqual(m.calls, [])
        self.assertEqual(win.removed, staging_folders(win))

    def test_msiexec_failing_is_an_install_failure_and_the_staging_is_still_deleted(self):
        for exit_code in (1603, 1618):
            with self.subTest(exit_code=exit_code):
                win = FakeWindows()
                m = Machine(win, msi_exit=exit_code)
                with self.assertRaises(ci.Failed) as caught:
                    m.install()
                self.assertEqual(caught.exception.code, "install_failed")
                self.assertEqual(win.removed, staging_folders(win))

    def test_a_restart_needed_still_counts_as_installed(self):
        self.assertEqual(Machine(FakeWindows(), msi_exit=3010).install()["result"], "installed")

    def test_no_chrome_after_a_successful_msiexec_is_a_failure(self):
        with self.assertRaises(ci.Failed) as caught:
            Machine(FakeWindows(), chrome_after=False).install()
        self.assertEqual(caught.exception.code, "install_failed")

    def test_an_installed_chrome_that_fails_the_check_is_refused(self):
        with self.assertRaises(ci.Failed) as caught:
            Machine(FakeWindows(), chrome_signer=OTHER).install()
        self.assertEqual(caught.exception.code, "bad_signature")

    def test_a_good_chrome_already_installed_is_left_alone(self):
        win = FakeWindows()
        m = Machine(win, chrome_before=True)
        self.assertEqual(m.install()["result"], "already")
        self.assertEqual((m.fetched, m.msiexec(), win.made), ([], [], []))

    def test_a_staging_folder_someone_else_made_or_can_change_stops_the_install(self):
        root = PD + r"\Swangz"
        for kw in ({"sddl": {root: SAFE + "(A;OICI;0x1301bf;;;BU)"}},  # Users may modify
                   {"sddl": {root: "O:%sD:P(A;OICI;FA;;;SY)" % USER}},  # owned by the person
                   {"sddl": {root: "O:BAD:NO_ACCESS_CONTROL"}},
                   {"links": {root}}):
            with self.subTest(kw=kw):
                win = FakeWindows(existing={root}, **kw)
                m = Machine(win)
                with self.assertRaises(ci.Failed) as caught:
                    m.install()
                self.assertEqual(caught.exception.code, "staging_unsafe")
                self.assertEqual((m.fetched, m.calls), ([], []))

    def test_an_existing_safe_staging_root_is_reused(self):
        win = FakeWindows(existing={PD + r"\Swangz"})
        self.assertEqual(Machine(win).install()["result"], "installed")

    def test_a_random_staging_folder_that_already_exists_stops_the_install(self):
        win = FakeWindows()
        m = Machine(win)
        with mock.patch.object(ci.secrets, "token_hex", return_value="0" * 32):
            win.present.add(PD + "\\Swangz\\" + "0" * 32)
            with self.assertRaises(ci.Failed) as caught:
                m.install()
        self.assertEqual(caught.exception.code, "staging_unsafe")
        self.assertEqual(m.fetched, [])


class SddlTests(unittest.TestCase):
    def test_program_files_defaults_are_safe(self):
        self.assertTrue(ci.sddl_safe(SAFE))
        self.assertTrue(ci.sddl_safe("O:S-1-5-80-956008885-3418522649-1831038044-1849834513-2271427685"
                                     "G:S-1-5-80-956008885-3418522649-1831038044-1849834513-2271427685"
                                     "D:PAI(A;;FA;;;S-1-5-80-956008885-3418522649-1831038044-1849834513-2271427685)"
                                     "(A;;0x1200a9;;;BU)(A;;0x1200a9;;;AC)(A;OICIIO;GA;;;CO)"))
        self.assertTrue(ci.sddl_safe(ci.STAGING_SDDL))

    def test_any_write_delete_or_permission_right_for_someone_else_is_unsafe(self):
        for ace in ("(A;;FA;;;BU)", "(A;;0x2;;;BU)", "(A;;SD;;;WD)", "(A;;WD;;;AU)", "(A;;WO;;;%s)" % USER,
                    "(A;;GW;;;BU)", "(A;;GA;;;IU)", "(A;OICI;0x1301bf;;;AU)", "(A;;DC;;;BU)"):
            with self.subTest(ace=ace):
                self.assertFalse(ci.sddl_safe(SAFE + ace))

    def test_untrusted_owner_unknown_rights_and_garbage_are_unsafe(self):
        for sddl in ("O:%sD:P(A;;FA;;;SY)" % USER, "O:BUD:P(A;;FA;;;SY)", "O:BAD:P(A;;ZZ;;;BU)", "O:BA",
                     "", "garbage", "O:BAD:P(A;;FA;;;SY", "O:BAD:P(XX;;FR;;;BU)"):
            with self.subTest(sddl=sddl):
                self.assertFalse(ci.sddl_safe(sddl))

    def test_deny_and_inherit_only_entries_do_not_make_a_folder_unsafe(self):
        self.assertTrue(ci.sddl_safe(SAFE + "(D;;FA;;;BU)(A;OICIIO;FA;;;BU)"))


class SelfCheckTests(unittest.TestCase):
    def check(self, win=None, executable=EXE, meipass=INTERNAL, frozen=True):
        ci.self_check(win or FakeWindows(), executable, meipass, frozen, PF)

    def refused(self, **kw):
        with self.assertRaises(ci.Failed) as caught:
            self.check(**kw)
        self.assertEqual(caught.exception.code, "admin_install_required")

    def test_the_company_one_folder_build_in_program_files_passes(self):
        self.check()
        self.check(executable=r"c:\program files\swangz\Swangz.exe", meipass=r"C:\PROGRAM FILES\Swangz\_internal")

    def test_not_frozen_or_a_one_file_build_is_refused(self):
        self.refused(frozen=False)
        self.refused(meipass=r"C:\Users\amy\AppData\Local\Temp\_MEI12345")
        self.refused(meipass=None)

    def test_a_per_user_install_is_refused(self):
        local = r"C:\Users\amy\AppData\Local\Programs\Swangz"
        self.refused(executable=local + r"\Swangz.exe", meipass=local + r"\_internal")
        self.refused(executable=PF + r"\Swangz.exe", meipass=PF + r"\_internal")  # Program Files itself
        self.refused(executable=r"C:\Program Files Evil\Swangz\Swangz.exe",
                     meipass=r"C:\Program Files Evil\Swangz\_internal")

    def test_a_folder_the_person_can_change_anywhere_up_to_program_files_is_refused(self):
        writable = SAFE + "(A;OICI;0x1301bf;;;%s)" % USER
        for path in (APP, PF, EXE, INTERNAL):
            with self.subTest(path=path):
                self.refused(win=FakeWindows(sddl={path: writable}))
        win = FakeWindows()
        win.read_sddl = mock.Mock(side_effect=OSError(5, "denied"))
        self.refused(win=win)


class AdminEntryTests(unittest.TestCase):
    def run_admin(self, argv, win=None, install=None, **kw):
        win = win or FakeWindows()
        install = install or mock.Mock(return_value={"result": "installed", "chrome": CHROME})
        args = dict(win=win, frozen=True, executable=EXE, meipass=INTERNAL, install=install)
        args.update(kw)
        with mock.patch.object(ci, "_write_log") as log:
            return ci.admin_main(argv, **args), install, log

    def test_only_admin_and_one_known_action_is_accepted(self):
        for argv in ([], ["admin"], ["admin", "chrome-install", "x"], ["admin", "Chrome-Install"],
                     ["admin", "--url=http://evil"], ["chrome-install"], ["admin", "chrome-install "]):
            with self.subTest(argv=argv):
                code, install, _ = self.run_admin(argv)
                self.assertEqual(code, ci.EXIT["usage"])
                install.assert_not_called()

    def test_chrome_install_runs_after_the_self_check(self):
        code, install, log = self.run_admin(["admin", "chrome-install"])
        self.assertEqual(code, 0)
        install.assert_called_once()
        self.assertEqual(log.call_args[0][1]["code"], "installed")

    def test_a_failed_self_check_installs_nothing(self):
        for kw in ({"frozen": False}, {"meipass": r"C:\Users\amy\AppData\Local\Temp\_MEI1"},
                   {"executable": r"C:\Users\amy\AppData\Local\Programs\Swangz\Swangz.exe",
                    "meipass": r"C:\Users\amy\AppData\Local\Programs\Swangz\_internal"},
                   {"win": FakeWindows(sddl={APP: SAFE + "(A;;FA;;;BU)"})}):
            with self.subTest(kw=kw):
                code, install, _ = self.run_admin(["admin", "chrome-install"], **kw)
                self.assertEqual(code, ci.EXIT["admin_install_required"])
                install.assert_not_called()

    def test_each_failure_has_its_own_exit_code_and_unexpected_errors_fail_closed(self):
        for error, code in ((ci.Failed("bad_signature"), 13), (ci.Failed("staging_unsafe"), 11),
                            (ci.Failed("download_failed"), 12), (ci.Failed("install_failed"), 14),
                            (RuntimeError("boom"), 16)):
            with self.subTest(error=error):
                got, _, log = self.run_admin(["admin", "chrome-install"], install=mock.Mock(side_effect=error))
                self.assertEqual(got, code)
                self.assertNotEqual(log.call_args[0][1]["code"], "installed")

    def test_the_policy_actions_are_not_built_yet(self):
        for action in ("policy-write", "policy-remove"):
            code, install, _ = self.run_admin(["admin", action])
            self.assertEqual(code, ci.EXIT["not_built"])
            install.assert_not_called()

    def test_off_windows_the_elevated_entry_does_nothing(self):
        with mock.patch.object(ci.sys, "platform", "linux"):
            self.assertEqual(ci.admin_main(["admin", "chrome-install"]), ci.EXIT["admin_install_required"])

    def test_the_packaged_app_dispatches_admin_before_loading_the_client(self):
        source = (ROOT / "packaging" / "swangz_app.py").read_text(encoding="utf-8")
        main = source.split('if __name__ == "__main__":', 1)[1]
        self.assertNotIn("from swangz_client.cli import main", source.split('if __name__ == "__main__":', 1)[0])
        self.assertLess(main.index("admin_main(sys.argv[1:])"), main.index("from swangz_client.cli import main"))
        self.assertIn("swangz_client.chrome_install", (ROOT / "packaging" / "build.py").read_text(encoding="utf-8"))


class ConsentTests(unittest.TestCase):
    def ask(self, win=None, agree=True, platform="win32", **kw):
        shown = []

        def consent(text):
            shown.append(text)
            return agree

        args = dict(executable=EXE, meipass=INTERNAL, frozen=True)
        args.update(kw)
        code, message = ci.request_install(platform, consent=consent, win=win, **args)
        return code, message, shown

    def test_the_person_agrees_then_windows_asks_and_chrome_is_installed(self):
        win = FakeWindows(elevate_answer=0)
        code, message, shown = self.ask(win)
        self.assertEqual(code, "installed")
        self.assertEqual(win.elevated, [(EXE, "admin chrome-install")])
        self.assertIn("dl.google.com", shown[0])
        self.assertIn("Google LLC", shown[0])
        self.assertIn("If you say no, nothing changes", shown[0])

    def test_declining_our_step_or_the_uac_prompt_changes_nothing(self):
        win = FakeWindows()
        code, message, _ = self.ask(win, agree=False)
        self.assertEqual((code, win.elevated, win.made), ("declined", [], []))
        win = FakeWindows(elevate_answer=ci.DECLINED)
        code, message, _ = self.ask(win)
        self.assertEqual(code, "declined")
        self.assertEqual(win.made, [])
        self.assertIn("Nothing was changed", message)
        self.assertEqual(ci.request_install("win32", consent=None, win=FakeWindows(), executable=EXE,
                                            meipass=INTERNAL, frozen=True)[0], "declined")

    def test_the_elevated_steps_failures_come_back_as_repair_codes(self):
        for exit_code, code in ((13, "bad_signature"), (12, "download_failed"), (14, "install_failed"),
                                (11, "staging_unsafe"), (10, "admin_install_required"), (77, "failed")):
            with self.subTest(exit_code=exit_code):
                got, message, _ = self.ask(FakeWindows(elevate_answer=exit_code))
                self.assertEqual(got, code)
                self.assertTrue(message.startswith("Chrome was not installed") or "Ask your administrator" in message)

    def test_the_per_user_build_never_offers_elevation(self):
        local = r"C:\Users\amy\AppData\Local\Programs\Swangz"
        win = FakeWindows()
        code, message, shown = self.ask(win, executable=local + r"\Swangz.exe", meipass=local + r"\_internal")
        self.assertEqual(code, "ask_admin")
        self.assertIn("ask your administrator to install the company build", message.lower())
        self.assertEqual((shown, win.elevated), ([], []))

    def test_macos_and_linux_install_nothing_and_say_what_is_accepted(self):
        code, message, shown = self.ask(platform="darwin")
        self.assertEqual(code, "mac_page")
        self.assertIn("/Applications", message)
        self.assertEqual(shown, [])
        self.assertEqual(self.ask(platform="linux")[0], "linux")


class Response(io.BytesIO):
    def __init__(self, body, length=None, url="https://dl.google.com/x.msi", fail_after=None):
        super().__init__(body)
        self.headers = {} if length is False else {"Content-Length": str(len(body) if length is None else length)}
        self.url, self.fail_after = url, fail_after

    def geturl(self):
        return self.url

    def read(self, n=-1):
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise ConnectionResetError("reset")
        return super().read(min(n, 4) if n > 0 else n)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "chrome.msi")

    def get(self, response, **kw):
        return ci.download("https://dl.google.com/x.msi", self.path, fetch=lambda url, timeout: response, **kw)

    def failed(self, response, **kw):
        with self.assertRaises(ci.Failed) as caught:
            self.get(response, **kw)
        self.assertEqual(caught.exception.code, "download_failed")

    def test_a_complete_download(self):
        self.assertEqual(self.get(Response(b"0123456789")), 10)
        self.assertEqual(Path(self.path).read_bytes(), b"0123456789")

    def test_truncated_oversize_unannounced_or_interrupted_downloads_fail(self):
        self.failed(Response(b"01234", length=10))
        os.unlink(self.path)
        self.failed(Response(b"0123456789", length=5))
        os.unlink(self.path)
        self.failed(Response(b"0123456789"), cap=9)
        self.failed(Response(b"0123456789", length=False))
        self.failed(Response(b"0123456789", fail_after=4))

    def test_only_https_and_never_an_existing_file(self):
        with self.assertRaises(ci.Failed):
            ci.download("http://dl.google.com/x.msi", self.path, fetch=lambda u, timeout: Response(b"x"))
        self.failed(Response(b"x", url="http://dl.google.com/x.msi"))
        Path(self.path).write_bytes(b"planted")
        with self.assertRaises(FileExistsError):
            self.get(Response(b"x"))

    def test_a_network_error_is_a_failed_download(self):
        def broken(url, timeout):
            raise urllib.error.URLError("no route")
        with self.assertRaises(ci.Failed) as caught:
            ci.download("https://dl.google.com/x.msi", self.path, fetch=broken)
        self.assertEqual(caught.exception.code, "download_failed")

    def test_a_redirect_to_http_is_refused_and_proxies_are_not_read(self):
        handler = ci._HttpsOnlyRedirects()
        request = ci.urllib.request.Request("https://dl.google.com/x.msi")
        with self.assertRaises(ci.Failed):
            handler.redirect_request(request, None, 302, "Found", {}, "http://evil.example/x.msi")
        self.assertIsNotNone(handler.redirect_request(request, None, 302, "Found", {}, "https://redirector.gvt1.com/x"))
        with mock.patch.dict(os.environ, {"https_proxy": "http://proxy.example:1", "HTTPS_PROXY": "http://p:1"}):
            built = ci.opener()
        # an empty ProxyHandler replaces the default one that reads the environment, so no proxy is ever used
        self.assertEqual([h for h in built.handlers if isinstance(h, ci.urllib.request.ProxyHandler)], [])
        self.assertTrue(any(isinstance(h, ci._HttpsOnlyRedirects) for h in built.handlers))

    def test_the_staging_folder_is_removed_with_what_is_in_it(self):
        folder = Path(self.tmp.name) / "stage"
        (folder / "inner").mkdir(parents=True)
        (folder / "chrome.msi").write_bytes(b"x")
        (folder / "inner" / "f").write_bytes(b"y")
        ci._remove_tree(str(folder))
        self.assertFalse(folder.exists())
        ci._remove_tree(str(folder))  # already gone is fine


class StaticTests(unittest.TestCase):
    """B2, B3, B6, read from the source."""

    def client_sources(self):
        return {p.name: p.read_text(encoding="utf-8") for p in sorted((ROOT / "swangz_client").glob("*.py"))}

    def test_the_elevated_step_reads_no_environment_and_nothing_from_the_persons_folders(self):
        source = (ROOT / "swangz_client" / "chrome_install.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                    for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertLessEqual(imported & {"core", "state", "config", "workspace_state", "browser_profiles", "cli", "gui",
                                         "shell", "repair", "tempfile", "getpass"}, set())
        for word in ("environ", "getenv", "expanduser", "expandvars", "gettempdir", "APPDATA", "LOCALAPPDATA",
                     "TEMP", "%ProgramData%", "PATH", "data_dir", "shell=True", "cmd.exe"):
            with self.subTest(word=word):
                self.assertNotRegex(source, r"\b%s\b" % re.escape(word) if word.isidentifier() else re.escape(word))

    def test_no_service_task_daemon_or_stored_password_in_the_client(self):
        pattern = re.compile(r"(?i)schtasks|CreateService|New-Service|\bsc(\.exe)?\s+create|LaunchDaemons|sudoers|"
                             r"Register-ScheduledTask|admin_password|administrator password")
        for file, source in self.client_sources().items():
            with self.subTest(file=file):
                self.assertNotRegex(source, pattern)

    def test_the_macos_client_never_asks_for_root_itself(self):
        pattern = re.compile(r"(?i)with administrator privileges|AuthorizationExecute|\bsudo\b|xattr\s+-d|"
                             r"com\.apple\.quarantine")
        for file, source in self.client_sources().items():
            with self.subTest(file=file):
                self.assertNotRegex(source, pattern)

    def test_the_only_download_address_is_googles_and_nothing_is_bundled(self):
        source = (ROOT / "swangz_client" / "chrome_install.py").read_text(encoding="utf-8")
        hosts = set(re.findall(r"https?://([^/\"' ]+)", source))
        self.assertEqual(hosts, {"dl.google.com", "www.google.com"})
        from swangz_client import workspace_launcher
        self.assertEqual(ci.INSTALL_PAGE, workspace_launcher.INSTALL_PAGE)
        for path in (ROOT / "packaging").rglob("*"):
            if path.is_file():
                self.assertNotRegex(path.name.lower(), r"chrome.*\.(msi|exe|pkg|dmg)$")


@unittest.skipUnless(sys.platform == "win32", "the real Windows calls run on Windows only")
class NativeWindowsTests(unittest.TestCase):
    """Real ctypes calls on the Windows CI runner. Nothing is downloaded, installed or elevated."""

    def setUp(self):
        self.win = ci.Windows()

    def test_known_folders_come_from_the_shell_not_the_environment(self):
        pf = self.win.known_folder(ci.FOLDERID_PROGRAM_FILES)
        self.assertTrue(ntpath.isabs(pf))
        self.assertEqual(ntpath.normcase(pf), ntpath.normcase(self.win.system_folders()["ProgramFiles"]))
        self.assertTrue(os.path.isdir(self.win.known_folder(ci.FOLDERID_PROGRAM_DATA)))

    def test_program_files_is_safe_and_the_persons_temp_folder_is_not(self):
        pf = self.win.known_folder(ci.FOLDERID_PROGRAM_FILES)
        self.assertTrue(ci.sddl_safe(self.win.read_sddl(pf)), self.win.read_sddl(pf))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(ci.sddl_safe(self.win.read_sddl(tmp)), self.win.read_sddl(tmp))

    def test_the_staging_folder_is_created_admin_only_and_never_twice(self):
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            self.skipTest("owner Administrators needs an elevated runner")
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "with space")
            self.win.make_folder(folder)
            try:
                sddl = self.win.read_sddl(folder)
                self.assertTrue(ci.sddl_safe(sddl), sddl)
                self.assertTrue(sddl.startswith("O:BA"), sddl)
                self.assertIn("D:P", sddl)
                self.assertFalse(self.win.is_link(folder))
                with self.assertRaises(FileExistsError):
                    self.win.make_folder(folder)
                Path(folder, "chrome.msi").write_bytes(b"x")
            finally:
                ci._remove_tree(folder)
            self.assertFalse(os.path.exists(folder))


if __name__ == "__main__":
    unittest.main()
