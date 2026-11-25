"""The Windows installer's promises, checked on any OS (the build and the real install run on windows-latest in CI)."""

import http.server
import json
import importlib.util
import re
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from swangz_client import cli

ROOT = Path(__file__).resolve().parent.parent
ISS = (ROOT / "packaging" / "windows" / "swangz.iss").read_text(encoding="utf-8")
CODE = "\n".join(l for l in ISS.splitlines() if not l.lstrip().startswith((";", "//")))  # without comments
WORKFLOW = (ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")


def section(name):
    m = re.search(r"^\[" + re.escape(name) + r"\]\n(.*?)(?=^\[|\Z)", ISS, re.M | re.S)
    return m.group(1) if m else ""


def lines(name):
    return [l for l in section(name).splitlines() if l.strip() and not l.lstrip().startswith(";")]


class InstallerScriptTests(unittest.TestCase):
    def test_per_person_install_with_no_administrator_rights(self):
        setup = section("Setup")
        self.assertIn("PrivilegesRequired=lowest", setup)
        self.assertNotIn("PrivilegesRequiredOverridesAllowed", setup)
        self.assertIn("DefaultDirName={autopf}\\Swangz", setup)  # {autopf} = %LOCALAPPDATA%\Programs when not elevated
        for entry in lines("Registry"):
            self.assertIn("Root: HKCU", entry)  # nothing machine-wide

    def test_start_menu_always_desktop_and_startup_optional_and_off_by_default(self):
        tasks = {re.search(r'Name: "(\w+)"', l).group(1): l for l in lines("Tasks")}
        self.assertEqual(set(tasks), {"desktopicon", "startup"})
        self.assertTrue(all("Flags: unchecked" in l for l in tasks.values()))
        icons = lines("Icons")
        self.assertTrue(any(l.startswith('Name: "{autoprograms}\\Swangz"') and "Tasks:" not in l for l in icons))
        self.assertTrue(any(l.startswith('Name: "{autodesktop}\\Swangz"') and "Tasks: desktopicon" in l for l in icons))

    def test_startup_uses_the_apps_own_run_value_and_uninstall_removes_it(self):
        (entry,) = lines("Registry")
        self.assertIn(r'Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"', entry)
        self.assertIn('ValueName: "Swangz"', entry)  # the same value swangz_client.shell.set_autostart writes
        self.assertIn("--background", entry)
        self.assertIn("Tasks: startup", entry)
        self.assertIn("uninsdeletevalue", entry)
        self.assertIn("RegDeleteValue(HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 'Swangz')",
                      section("Code"))
        from swangz_client import shell
        self.assertIn('"Swangz"', Path(shell.__file__).read_text(encoding="utf-8"))

    def test_uninstall_removes_swangz_from_this_account_first_and_reports_what_stays(self):
        # D-026 C4: from [Code], because the result of an [UninstallRun] entry is read by nobody
        self.assertEqual(section("UninstallRun"), "")
        self.assertEqual(section("UninstallDelete"), "")
        for entry in lines("Run"):
            self.assertNotRegex(entry, r"\b(cleanup|logout)\b")
        self.assertNotRegex(CODE, r"\blogout\b")  # cleanup signs out first
        self.assertNotIn("DelTree", CODE)  # only the program deletes inside the person's folders, link-safely
        body = CODE.split("procedure RemoveFromThisAccount;", 1)[1].split("procedure CurUninstallStepChanged", 1)[0]
        # the person's own running copy is stopped first, so it cannot hold a folder or rewrite its state
        stop = body.index("Exec(ExpandConstant('{sys}\\taskkill.exe'), "
                          "ExpandConstant('/F /T /IM Swangz.exe /FI \"USERNAME eq {username}\"')")
        run = body.index("Ran := Exec(ExpandConstant('{app}\\Swangz.exe'), 'cleanup --report \"' + Report + '\"'")
        self.assertLess(stop, run)
        self.assertEqual(body.count("ewWaitUntilTerminated"), 2)
        checked = body.index("if Ran and (ResultCode = 0) then")
        self.assertLess(run, checked)
        for needed in ("could not remove everything from this account", "Log(Message);",
                       '"Remove Swangz from this account" on This device', "disconnect this device "):
            self.assertGreater(body.index(needed), checked)
        # the report is read first: the line about the Hub is shown whether or not cleanup succeeded
        self.assertLess(body.index("LoadStringsFromFile(Report, Left)"), checked)
        self.assertIn("Pos('Have this device disconnected from the Hub', Left[I])", body)
        success = body[checked:body.index("exit;", checked)]
        self.assertIn("MsgBox(Disconnect, mbInformation, MB_OK)", success)
        self.assertIn("Message + #13#10 + #13#10 + Disconnect", body)
        self.assertTrue(cli.DISCONNECT.startswith("Have this device disconnected from the Hub"))
        # a refusal is reported, never retried with other or more rights
        self.assertNotRegex(CODE, r"(?i)runas|ShellExec|AsOriginalUser")
        self.assertEqual(CODE.count("'cleanup "), 1)
        self.assertRegex(body, r"if not UninstallSilent then\s+MsgBox\(Message")
        step = CODE.split("procedure CurUninstallStepChanged", 1)[1]
        self.assertRegex(step, r"if CurUninstallStep = usUninstall then\s+RemoveFromThisAccount;")  # before files go
        self.assertIn("CloseApplications=force", ISS)  # a reinstall closes a running copy too

    def test_no_code_line_starts_with_a_hash_the_preprocessor_would_read(self):
        # "#13#10" at the start of a line is an unknown preprocessor directive to ISCC: the script does not compile
        for line in CODE.splitlines():
            self.assertNotRegex(line, r"^\s*#(?!define|ifn?def|if |else|endif|error|include)")

    def test_no_server_address_secret_or_updater_is_built_in(self):
        self.assertIsNone(re.search(r"https?://", ISS))
        self.assertNotRegex(CODE.lower(), r"token|password|secret|api[_-]?key|server")
        self.assertNotRegex(CODE.lower(), r"schtasks|taskscheduler|update")
        self.assertIn("UNSIGNED", ISS)
        self.assertNotIn("SignTool", ISS)
        from swangz_client import release_keys
        self.assertIs(release_keys.ENABLED, False)
        self.assertEqual(release_keys.KEYS, {})

    def test_the_only_file_installed_is_the_program(self):
        (entry,) = lines("Files")
        self.assertIn('DestName: "Swangz.exe"', entry)


class WorkflowTests(unittest.TestCase):
    def test_build_tools_are_pinned_and_the_build_is_labelled(self):
        self.assertRegex(WORKFLOW, r"PYINSTALLER_VERSION: '\d+\.\d+\.\d+'")
        self.assertRegex(WORKFLOW, r"INNO_SETUP_VERSION: '\d+\.\d+\.\d+'")
        self.assertIn("pip install --require-hashes --only-binary :all: -r packaging\\requirements-windows-build.txt", WORKFLOW)
        self.assertNotIn('pip install "pyinstaller', WORKFLOW)  # never an unhashed install
        reqs = (ROOT / "packaging" / "requirements-windows-build.txt").read_text(encoding="utf-8")
        version = re.search(r"PYINSTALLER_VERSION: '([\d.]+)'", WORKFLOW).group(1)
        self.assertIn(f"pyinstaller=={version} ", reqs)
        pins = re.findall(r"^([\w-]+)==\S+ \\\n\s+--hash=sha256:[0-9a-f]{64}$", reqs, re.M)
        self.assertEqual(sorted(pins), sorted(["pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
                                               "pywin32-ctypes", "packaging", "setuptools"]))
        self.assertRegex(WORKFLOW, r"INNO_SETUP_SHA256: '[0-9a-f]{64}'")
        self.assertIn("does not match the pin", WORKFLOW)
        self.assertNotIn("choco install", WORKFLOW)
        self.assertIn("RC — UNSIGNED — INTERNAL TEST ONLY", WORKFLOW)
        self.assertIn("runs-on: windows-latest", WORKFLOW)

    def test_read_only_token_and_no_release_or_secret(self):
        self.assertIn("permissions:\n  contents: read", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"gh release|softprops|action-gh-release|signtool")

    def test_checksum_and_acceptance_evidence_are_produced(self):
        self.assertIn(".sha256", WORKFLOW)
        self.assertIn("installer_e2e.py --setup $env:SETUP --evidence evidence", WORKFLOW)

    def test_upgrade_runs_from_the_previous_build_which_is_not_released(self):
        self.assertIn("--previous $env:PREVIOUS_SETUP --previous-version $env:PREVIOUS_VERSION --new-version $env:NEW_VERSION",
                      WORKFLOW)
        self.assertIn('/DOutputDir=$PWD\\previous"', WORKFLOW)  # the previous installer stays out of artifacts/
        self.assertIn("GITHUB_RUN_NUMBER", WORKFLOW)  # this build's PATCH is raised, so it is always newer
        self.assertIn('if ($version -ne $env:NEW_VERSION)', WORKFLOW)
        uploads = re.findall(r"path: (\S+)", WORKFLOW)
        self.assertEqual(sorted(uploads), ["artifacts/", "evidence/"])

    def test_the_e2e_checks_the_upgrade_reached_windows_and_the_hub(self):
        e2e = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        for needle in ('reg_value(UNINSTALL_KEY, "DisplayVersion")', "SELECT app_version FROM devices",
                       '"the upgrade lost the device"', "install(\"install.log\", first)"):
            self.assertIn(needle, e2e)
        self.assertIn("if: always()", WORKFLOW)

    def test_an_older_build_is_refused(self):
        code = ISS.split("[Code]", 1)[1]
        self.assertIn("function InitializeSetup(): Boolean;", code)
        self.assertIn("CompareVersions('{#AppVersion}', Installed) < 0", code)
        self.assertIn("Result := False;", code)
        # the key read is this app's own Apps & features entry, the same one the e2e checks
        e2e = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        key = e2e.split('UNINSTALL_KEY = r"', 1)[1].split('"', 1)[0]
        self.assertIn(key.replace("\\", "\\"), code)
        self.assertIn("HKEY_CURRENT_USER", code)
        # the e2e runs the previous installer over this build, expects exit 1 and an unchanged install
        step = e2e.split("# 6b. an older build is refused", 1)[1].split("# 7.", 1)[0]
        for needle in ("expected=1", "downgrade.log", 'f"Refused: Swangz {new_version} is installed"',
                       "exe.read_bytes() == before", 'reg_value(UNINSTALL_KEY, "DisplayVersion")'):
            self.assertIn(needle, step)
        self.assertLess(e2e.index("# 6. upgrade"), e2e.index("# 6b."))

    def test_the_e2e_signs_out_before_the_uninstall_and_checks_the_run_value_is_gone(self):
        e2e = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        sign_out, uninstall = e2e.index('app("logout")'), e2e.index("# 8. uninstall while the program runs")
        self.assertLess(sign_out, uninstall)
        self.assertIn('"sign out left the start-at-sign-in value"', e2e[sign_out:uninstall])
        self.assertIn('app("autostart", "on")', e2e[sign_out:uninstall])  # the uninstall still proves it removes the value


class RestartEvidenceTests(unittest.TestCase):
    """The Windows gaps closed after macOS #277: the key in no log or file after the outage, a real Hub process
    restart (new pid, same key hash, no new sign-in code), and the Hub address unchanged across the upgrade."""

    def setUp(self):
        self.e2e = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")

    def section(self, start, end):
        return self.e2e.split(start, 1)[1].split(end, 1)[0]

    def test_the_key_is_searched_for_after_the_outage(self):
        leak = self.section("# 5a.", "# 5c.")
        self.assertIn('hub_journey.files_holding(stored_raw(), [data, evidence], skip={"device.key", "device.key.next"})', leak)
        self.assertIn("require(not leaks", leak)
        self.assertLess(self.e2e.index('passed("network interruption'), self.e2e.index("# 5a."))
        self.assertNotIn("stored_raw()}", self.e2e)  # the key itself is never formatted into a message

    def test_a_real_hub_process_restart_on_the_same_port_and_data(self):
        restart = self.section("# 5c.", "# 5b.")
        steps = ["rig.server.shutdown()", "rig.gw.db.close()", 'app("sync", expected=1)', '"HUB_FIXTURE_DATA": rig.tmp',
                 '"HUB_FIXTURE_PORT": str(rig.port)', '"PYTHONTZPATH"', 'again["pid"] != os.getpid()', 'app("sync")',
                 "after_key == before_key", "tuple(after_codes) == tuple(before_codes)", "now > seen",
                 "hub.terminate()", "make_server(rig.settings)", "sign_in_codes() == before_codes"]
        at = [restart.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the restart steps are out of order")
        self.assertNotIn("relay.stop()", restart)  # the Hub process stops, not the relay

    def test_the_hub_address_is_unchanged_across_the_upgrade(self):
        upgrade = self.section("# 6. upgrade", "# 6b.")
        self.assertLess(upgrade.index('["server"]'), upgrade.index('install("upgrade.log"'))
        self.assertIn("address == moved == origin", upgrade)


class EnrolmentRefusalTests(unittest.TestCase):
    """Deliverable 3 gaps through the installed program: wrong, expired and reused sign-in codes; and (5d) grants that
    take effect only when the program starts again."""

    def setUp(self):
        self.e2e = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")

    def section(self, start, end):
        return self.e2e.split(start, 1)[1].split(end, 1)[0]

    def test_wrong_then_expired_code_while_the_program_waits(self):
        refused = self.section("# 3a.", "device = enrol()")
        steps = ['[str(exe), "login", "--server", origin', "That code isn't right", "fixture.csrf(row[\"user_code\"])",
                 "hub_enroll._csrf(rig.gw, session, row[\"user_code\"])", '"csrf": real', 'require(status == 400',
                 "== \"pending\"", "login.poll() is None and not", "UPDATE device_codes SET expires", "login.communicate(timeout=120)",
                 "login.returncode == 1", '"expired" in (out + err).lower()', "keys_issued() == issued",
                 'unusable(row["user_code"])']
        at = [refused.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the refused-code steps are out of order")
        self.assertLess(self.e2e.index("# 3a."), self.e2e.index("device = enrol()"))
        self.assertNotIn('"csrf": "0" * 64', refused)  # no made-up token: a 400 must mean the code is wrong
        # the expired code stays 'pending' at the Hub, so the real enrolment after it must take the newest live code
        enrol = self.section("def enrol(approve=None, env=env, data=data):", "# 3a.")
        self.assertIn("status = 'pending' AND expires > ?", enrol)
        self.assertIn("ORDER BY id DESC LIMIT 1", enrol)

    def test_a_used_code_is_not_reusable(self):
        used = self.section("# 3b.", "# 4. restart")
        for needle in ("unusable(used)", 'expected=1', "sign_in_codes() == codes", "keys_issued() == issued",
                       '["key_id"] == key_id'):
            self.assertIn(needle, used)
        self.assertLess(self.e2e.index("enrol against the CI Hub"), self.e2e.index("# 3b."))

    def test_grants_take_effect_after_the_program_starts_again(self):
        grants = self.section("# 5d.", "# 6. upgrade")
        self.assertIn('[str(exe), "--background"]', grants)
        self.assertIn("hub_journey.grants_after_restart(check, start_program, close_program, data, owner, rig.person_id)", grants)
        self.assertNotIn('app("sync")', grants)  # the program's own start-up sync is what is proven


def load_e2e():
    spec = importlib.util.spec_from_file_location("installer_e2e", ROOT / "packaging" / "windows" / "installer_e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RelayTests(unittest.TestCase):
    """The relay the Windows run uses to cut and restore the network: same port before and after."""

    def setUp(self):
        class Hello(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hello)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self, port):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            return r.read()

    def test_cut_and_restore_on_the_same_port(self):
        relay = load_e2e().Relay(self.server.server_address[1])
        relay.start()
        self.addCleanup(relay.stop)
        port = relay.port
        self.assertEqual(self.get(port), b"ok")
        relay.stop()
        with self.assertRaises((urllib.error.URLError, ConnectionError, OSError)):
            self.get(port)
        relay.start()
        self.assertEqual(relay.port, port)
        self.assertEqual(self.get(port), b"ok")


if __name__ == "__main__":
    unittest.main()


class _Key:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def Close(self):
        pass


class WritableRegistry:
    """Just enough of `winreg` to write a policy pack and read it back with the app's own reader, on any OS."""
    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = "HKLM", "HKCU"  # HKCU paths are kept under "HKCU\\..."
    KEY_READ, KEY_WOW64_64KEY, KEY_ALL_ACCESS = 0x20019, 0x0100, 0xF003F
    REG_SZ, REG_DWORD = 1, 4

    def __init__(self):
        self.keys = {}  # path -> {name: (value, kind)}
        self.access = []

    def _path(self, parent, sub):
        if parent == self.HKEY_CURRENT_USER:
            return "HKCU\\" + sub
        return sub if parent == self.HKEY_LOCAL_MACHINE else parent.path + "\\" + sub

    def OpenKey(self, parent, sub, reserved=0, access=None):
        self.access.append(access)
        path = self._path(parent, sub)
        if path not in self.keys:
            raise FileNotFoundError(path)
        return _Key(path)

    def CreateKeyEx(self, parent, sub, reserved=0, access=None):
        self.access.append(access)
        path = self._path(parent, sub)
        parts = path.split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        return _Key(path)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys[key.path][name] = (value, kind)

    def EnumValue(self, key, i):
        items = list(self.keys[key.path].items())
        if i >= len(items):
            raise OSError("no more")
        name, (value, kind) = items[i]
        return name, value, kind

    def children(self, path):
        return [p.rsplit("\\", 1)[1] for p in self.keys if p.startswith(path + "\\") and "\\" not in p[len(path) + 1:]]

    def EnumKey(self, key, i):
        names = self.children(key.path)
        if i >= len(names):
            raise OSError("no more")
        return names[i]

    def DeleteKeyEx(self, root, path, access=0, reserved=0):
        self.access.append(access)
        if self.children(path):
            raise PermissionError("a key with subkeys cannot be deleted")
        del self.keys[path]


class WindowsPolicyTamperTests(unittest.TestCase):
    """D-024 W5 on Windows (packaging/windows/policy.py): the pack written where the app reads it, the five cases."""

    def setUp(self):
        import sys
        from unittest import mock

        sys.path.insert(0, str(ROOT / "packaging"))
        self.addCleanup(sys.path.remove, str(ROOT / "packaging"))
        self.reg = WritableRegistry()
        for patch in (mock.patch.dict(sys.modules, {"winreg": self.reg}),
                      mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"})):
            patch.start()
            self.addCleanup(patch.stop)
        spec = importlib.util.spec_from_file_location("windows_policy", ROOT / "packaging" / "windows" / "policy.py")
        self.p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.p)
        self.src = (ROOT / "packaging" / "windows" / "policy.py").read_text(encoding="utf-8")
        self.e2e = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")

    def prepared(self):
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            return self.p.macos_policy.prepare(work)

    def test_the_location_is_the_one_the_app_reads(self):
        from swangz_client import machine_policy
        self.assertEqual(self.p.KEY, machine_policy.WINDOWS_KEYS["chrome"])
        self.assertEqual(set(self.p.LISTS), set(machine_policy.LISTS))
        self.assertEqual(set(self.p.JSON_STRING), set(machine_policy.JSON_STRING))

    def test_the_written_pack_reads_back_as_the_printed_baseline(self):
        policy, baseline = self.prepared()
        seen = self.p.install(policy)
        self.assertTrue(seen.ok, seen.problems)
        self.assertEqual(seen.sha256, baseline)
        chrome = self.reg.keys[self.p.KEY]
        self.assertEqual(chrome["BrowserSignin"], (0, self.reg.REG_DWORD))
        self.assertEqual(chrome["SyncDisabled"], (1, self.reg.REG_DWORD))
        self.assertEqual(chrome["AutoLaunchProtocolsFromOrigins"][1], self.reg.REG_SZ)
        self.assertEqual(self.reg.keys[self.p.KEY + "\\URLBlocklist"]["1"], (policy["URLBlocklist"][0], self.reg.REG_SZ))
        self.assertTrue(all(a & self.reg.KEY_WOW64_64KEY for a in self.reg.access), "the 64-bit view, as the app reads")

    def test_each_tampered_pack_replaces_the_last_and_reads_as_expected(self):
        from swangz_client import machine_policy
        policy, baseline = self.prepared()
        self.p.install(policy)
        seen = self.p.install(self.p.macos_policy.without_default_deny(policy))
        self.assertFalse(seen.ok)
        self.assertNotIn("*", self.reg.keys[self.p.KEY + "\\URLBlocklist"].values(), "no value left from the last pack")
        seen = self.p.install(self.p.macos_policy.extra_block(policy))
        self.assertTrue(seen.ok, seen.problems)
        self.assertNotEqual(seen.sha256, baseline)
        self.assertEqual(self.p.install(policy).sha256, baseline)
        self.p.remove()
        self.assertFalse(self.p.present())
        self.assertEqual(self.reg.keys, {k: v for k, v in self.reg.keys.items() if not k.startswith(self.p.KEY)})
        self.assertEqual(machine_policy.check("chrome", "win32").problems, ["missing"])
        self.p.remove()  # removing an absent pack is not an error

    def test_the_five_cases_in_order_and_the_runner_is_always_restored(self):
        body = self.src[self.src.index("def run("):]
        steps = ['synced("intact", True, True)', 'opened("intact")', "without_default_deny(policy)",
                 'refused("tampered, default-deny removed")', 'synced("tampered, default-deny removed", False, False)',
                 "after == before + 1", "extra_block(policy)", 'refused("tampered, valid but not the pinned pack")',
                 'synced("tampered, valid but not the pinned pack", True, False)', "        install(policy)\n",
                 'opened("restored")', 'synced("restored", True, True)', "        remove()\n", 'refused("removed")',
                 'synced("removed", False, False)', 'run_app("logout")']
        at = [body.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the policy cases are out of order")
        self.assertIn('"managed_policy_mode": "enforce"', body[:body.index("try:")])
        tail = body[body.index("    finally:"):]
        for needed in ("remove()", '"managed_policy_mode": "warn"', "policy-tamper.json"):
            self.assertIn(needed, tail)

    def test_the_journey_runs_it_as_a_company_device_and_signs_in_again_before_the_uninstall(self):
        call = self.e2e.index("windows_policy.run(")
        self.assertLess(self.e2e.index('report["second_person"] = second'), call)
        self.assertLess(call, self.e2e.rindex('app("autostart", "on")'))
        block = self.e2e[self.e2e.index("# 7c."):self.e2e.index("# 8. uninstall")]
        for needle in ('app("logout")', 'fixture.approve(c, "company")', 'Path(rig.tmp) / "gateway.db"',
                       "device = enrol(approve_second[0])", 'key_id = device["key_id"]', "== second"):
            self.assertIn(needle, block)
        self.assertLess(block.index("windows_policy.run("), block.index("device = enrol(approve_second[0])"))

    def test_the_uninstall_runs_as_the_second_person_and_really_deletes(self):
        self.assertIn("approve_second[:] = [approve]", self.e2e[self.e2e.index("def enrol_second"):])
        self.assertIn('held = data / "browser-profiles" / report["two_at_once"][0]', self.e2e)
        # the app's own fixed folder, which is the only one it makes the person the owner of
        self.assertIn('data, home = Path(winacl.local_app_data()) / "Swangz", work / "home"', self.e2e)
        self.assertNotIn('"SWANGZ_HOME": str(data),', self.e2e)
        after = self.e2e[self.e2e.index("# 8. uninstall"):self.e2e.index("report[\"ok\"] = True")]
        # the app's own rule is asked with the token the uninstaller gets, before it runs, and must allow it
        self.assertLess(after.index("refusal = shell.cleanup_refusal(data)"), after.index('"/VERYSILENT"'))
        self.assertLess(after.index("require(refusal is None and"), after.index('"/VERYSILENT"'))
        self.assertNotIn("if refusal:", after)
        for needed in ('not in log,', "the Hub did not disconnect the device", "require(not held.exists(),",
                       'hub_journey.removed(check, data, "after the uninstall")'):
            self.assertGreater(after.index(needed), after.index('"/VERYSILENT"'))

    def test_a_refused_open_starts_no_chrome_and_each_sync_must_report_afresh(self):
        refused = self.src[self.src.index("def refused("):self.src.index("def synced(")]
        self.assertIn("chrome_running(f, timeout=5)", refused)
        self.assertIn("and not running", refused)
        synced = self.src[self.src.index("def synced("):self.src.index('synced("intact"')]
        self.assertLess(synced.index('get("policy_reported")'), synced.index('run_app("sync")'))
        self.assertIn('fresh = (row.get("policy_reported") or 0) > earlier', synced)
        self.assertIn("code == 0 and fresh and", synced)

    def test_it_refuses_to_touch_the_registry_off_a_github_hosted_runner(self):
        """A real Swangz PC holds the company pack in this key: run, install and remove all refuse there."""
        from unittest import mock
        policy, _ = self.prepared()
        self.reg.CreateKeyEx(self.reg.HKEY_LOCAL_MACHINE, self.p.KEY)
        self.reg.SetValueEx(_Key(self.p.KEY), "BrowserSignin", 0, self.reg.REG_DWORD, 0)
        company_pack = {k: dict(v) for k, v in self.reg.keys.items()}
        for env in ({}, {"GITHUB_ACTIONS": "true"}, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
                    {"RUNNER_ENVIRONMENT": "github-hosted"}):
            with self.subTest(env=env), mock.patch.dict("os.environ", env, clear=True):
                calls = []
                with self.assertRaisesRegex(SystemExit, "runner only"):
                    self.p.run(lambda *a: calls.append(a), None, None, None, None, None, None, None)
                self.assertEqual(calls, [], "refused before any step, pin or write")
                with self.assertRaisesRegex(SystemExit, "runner only"):
                    self.p.install(policy)
                with self.assertRaisesRegex(SystemExit, "runner only"):
                    self.p.remove()
                self.assertEqual(self.reg.keys, company_pack, "the machine's own pack is untouched")

    def test_the_macos_steps_refuse_off_a_github_hosted_runner_too(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"}, clear=True):
            with self.assertRaisesRegex(SystemExit, "runner only"):
                self.p.macos_policy.run(None, None, None, None, None, None, None, None)

    def test_each_cleanup_step_runs_even_when_the_one_before_fails(self):
        import tempfile
        from unittest import mock
        policy, baseline = self.prepared()
        settings = []

        class Owner:
            def call(self, method, path, body=None):
                settings.append(body)
                return 200, {}

        checks = []
        with tempfile.TemporaryDirectory() as evidence, \
                mock.patch.object(self.p, "install", side_effect=RuntimeError("the case failed")), \
                mock.patch.object(self.p, "remove", side_effect=PermissionError("access denied")):
            with self.assertRaisesRegex(RuntimeError, "the case failed"):  # the real failure is the one reported
                self.p.run(lambda *a: checks.append(a), None, None, Owner(), None, None, None, evidence)
            written = json.loads((Path(evidence) / "policy-tamper.json").read_text(encoding="utf-8"))
        self.assertEqual(settings[-1], {"managed_policy_sha256": "", "managed_policy_mode": "warn"})
        self.assertIn("access denied", written["cleanup_errors"][0])
        body = self.src[self.src.index("    finally:"):]
        self.assertIn('check("policy: the runner is restored', body, "a failed cleanup is a failed step when the cases pass")
