"""The Windows installer's promises, checked on any OS (the build and the real install run on windows-latest in CI)."""

import http.server
import importlib.util
import re
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

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

    def test_uninstall_signs_the_device_out_first(self):
        stop, entry = lines("UninstallRun")
        # the person's own running copy is stopped before sign-out, so it cannot hold the program or rewrite its state
        self.assertIn('Filename: "{sys}\\taskkill.exe"', stop)
        self.assertIn('/IM Swangz.exe', stop)
        self.assertIn('USERNAME eq {username}', stop)
        self.assertIn("waituntilterminated", stop)
        self.assertIn("CloseApplications=force", ISS)  # a reinstall closes a running copy too
        self.assertIn('Parameters: "logout"', entry)
        self.assertIn("waituntilterminated", entry)
        self.assertIn("skipifdoesntexist", entry)

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
        steps = ['[str(exe), "login", "--server", origin', "That code isn't right", 'require(status == 400',
                 "== \"pending\"", "login.poll() is None and not", "UPDATE device_codes SET expires", "login.communicate(timeout=120)",
                 "login.returncode == 1", '"expired" in (out + err).lower()', "keys_issued() == issued",
                 'unusable(row["user_code"])']
        at = [refused.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the refused-code steps are out of order")
        self.assertLess(self.e2e.index("# 3a."), self.e2e.index("device = enrol()"))

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
