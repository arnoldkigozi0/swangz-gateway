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
        self.assertIn('pyinstaller==$env:PYINSTALLER_VERSION', WORKFLOW)
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
        self.assertIn("if: always()", WORKFLOW)


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
