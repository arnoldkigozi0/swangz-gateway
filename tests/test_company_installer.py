"""The Windows company build and its installer (#333, D-026 B4, B5, B7), checked on any OS. The one-folder build, the
install for all users and the file permissions run on windows-latest (packaging/windows/company_e2e.py)."""

import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load("company_build", "packaging/build.py")
sbom = load("company_sbom", "packaging/sbom.py")
e2e = load("company_e2e", "packaging/windows/company_e2e.py")
ISS = (ROOT / "packaging" / "windows" / "swangz-company.iss").read_text(encoding="utf-8")
PERSONAL = (ROOT / "packaging" / "windows" / "swangz.iss").read_text(encoding="utf-8")
CODE = "\n".join(l for l in ISS.splitlines() if not l.lstrip().startswith((";", "//")))  # without comments
WORKFLOW = (ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")


def section(name, text=ISS):
    m = re.search(r"^\[" + re.escape(name) + r"\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def lines(name, text=ISS):
    return [l for l in section(name, text).splitlines() if l.strip() and not l.lstrip().startswith(";")]


def app_id(text):
    return re.search(r"^AppId=\{(\{[0-9a-f-]{36}\})$", text, re.M).group(1)


class CompanyInstallerScriptTests(unittest.TestCase):
    def test_it_installs_for_all_users_only(self):
        setup = lines("Setup")
        self.assertIn("PrivilegesRequired=lowest", setup)
        self.assertIn("PrivilegesRequiredOverridesAllowed=commandline", setup)  # /ALLUSERS, never a dialog choice
        self.assertIn("if not IsAdminInstallMode then", CODE)
        init = CODE.split("function InitializeSetup(): Boolean;", 1)[1].split("function PrepareToInstall", 1)[0]
        self.assertIn("Result := Problem = '';", init)

    def test_only_into_program_files(self):
        self.assertIn("DefaultDirName={autopf}\\Swangz", lines("Setup"))
        self.assertIn("DisableDirPage=yes", lines("Setup"))
        check = CODE.split("function PrepareToInstall", 1)[1].split("procedure CurUninstallStepChanged", 1)[0]
        self.assertIn("CompareText(RemoveBackslashUnlessRoot(ExpandConstant('{app}')), "
                      "ExpandConstant('{commonpf64}\\Swangz')) <> 0", check)
        self.assertIn("Result := 'The company build installs only into '", check)

    def test_the_whole_one_folder_program_is_installed_and_old_code_removed(self):
        (files,) = lines("Files")
        self.assertIn('Source: "{#SourceFolder}\\*"; DestDir: "{app}"', files)
        self.assertIn("recursesubdirs", files)
        self.assertEqual(lines("InstallDelete"), ['Type: filesandordirs; Name: "{app}\\_internal"'])
        self.assertIn('#define SourceFolder "..\\..\\dist-company\\Swangz"', ISS)

    def test_pinned_values_are_the_three_prepare_py_needs_in_hklm_64(self):
        entries = lines("Registry")
        pins = {}
        for entry in entries:
            self.assertIn("Root: HKLM64;", entry)
            self.assertIn('Subkey: "Software\\Swangz\\Pinned"', entry)
            self.assertIn("Check: PinsGiven", entry)  # none passed: nothing written, an upgrade keeps what is there
            name = re.search(r'ValueName: "(\w+)"', entry).group(1)
            pins[name] = re.search(r'ValueData: "\{param:(\w+)\|\}"', entry).group(1)
        self.assertEqual(pins, {"hub_host": "HUBHOST", "extension_id": "EXTENSIONID",
                                "extension_update_url": "EXTENSIONUPDATEURL"})
        # what the runner journey passes and reads back
        self.assertEqual({k: f"/{v}=" for k, v in pins.items()}, e2e.SWITCHES)
        self.assertEqual(set(e2e.PINS), set(pins))
        self.assertIn("RegDeleteKeyIncludingSubkeys(HKLM64, 'Software\\Swangz\\Pinned')", CODE)

    def test_some_of_the_values_is_refused(self):
        init = CODE.split("function InitializeSetup(): Boolean;", 1)[1]
        for name in e2e.SWITCHES.values():
            self.assertIn(f"TypedWhole(PinValue('{name.strip('/=')}'))", init)
        self.assertIn("PinsGiven() and not (", init)

    def test_its_own_identity_and_the_same_downgrade_rule(self):
        self.assertNotEqual(app_id(ISS), app_id(PERSONAL))
        self.assertEqual(app_id(ISS), e2e.APP_ID)
        self.assertIn(f"UninstallKey = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{e2e.APP_ID}_is1';", CODE)
        self.assertIn("RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', Installed)", CODE)
        self.assertIn("CompareVersions('{#AppVersion}', Installed) < 0", CODE)
        self.assertIn("OutputBaseFilename=Swangz-Company-Setup-{#AppVersion}-UNSIGNED", lines("Setup"))

        def comparison(text):
            return text.split("// One part of a MAJOR", 1)[1].split("function CompareVersions", 1)[1].split("\nend;", 1)[0]

        self.assertEqual(comparison(ISS), comparison(PERSONAL))

    def test_nothing_of_a_person_runs_or_changes_with_administrator_rights(self):
        # no app code is started by the elevated installer or uninstaller: `logout` would act on files a person can edit
        self.assertEqual(section("Run"), "")
        (stop,) = lines("UninstallRun")
        self.assertIn('Filename: "{sys}\\taskkill.exe"; Parameters: "/F /T /IM Swangz.exe"', stop)
        self.assertNotIn("logout", CODE)
        self.assertNotRegex(CODE, r"HKCU|HKEY_CURRENT_USER|\{localappdata\}|\{userappdata\}")
        self.assertEqual([re.search(r'Name: "(\w+)"', l).group(1) for l in lines("Tasks")], ["desktopicon"])
        self.assertNotIn("Exec(", CODE)

    def test_no_address_secret_browser_policy_service_or_signing(self):
        self.assertIsNone(re.search(r"https?://", ISS))
        self.assertNotRegex(CODE.lower(), r"token|password|secret|api[_-]?key|schtasks|taskscheduler|sc\.exe|"
                                          r"policies\\|chrome")
        self.assertIn("UNSIGNED", ISS)
        self.assertNotIn("SignTool", ISS)

    def test_the_personal_installer_stays_per_person(self):
        self.assertNotIn("HKLM", PERSONAL)
        self.assertNotIn("PrivilegesRequiredOverridesAllowed", section("Setup", PERSONAL))


class CompanyBuildTests(unittest.TestCase):
    def fake_tools(self):
        return mock.patch.dict(sys.modules, {name: types.ModuleType(name) for name in ("PyInstaller", "tkinter")})

    def test_one_folder_on_windows(self):
        with mock.patch.object(build.sys, "platform", "win32"):
            company, personal = build.command("d", "w", onedir=True), build.command("d", "w")
        self.assertIn("--onedir", company)
        self.assertNotIn("--onefile", company)
        self.assertIn("--onefile", personal)  # the per-user program is unchanged

    def test_company_build_has_its_own_folders_and_source_dates(self):
        seen = {}

        def run(cmd, env):
            seen["cmd"] = cmd
            return types.SimpleNamespace(returncode=0)

        with self.fake_tools(), mock.patch.object(build.sys, "platform", "win32"), \
                mock.patch.object(build.subprocess, "run", run), \
                mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1000000000"}), \
                mock.patch.object(build, "normalize_windows_program", lambda p, e: seen.setdefault("program", Path(p))), \
                mock.patch.object(build, "date_files", lambda f, e: seen.setdefault("dated", (Path(f), e))), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(["--company"]), 0)
        cmd = seen["cmd"]
        self.assertEqual(Path(cmd[cmd.index("--distpath") + 1]), build.ROOT / "dist-company")
        self.assertEqual(Path(cmd[cmd.index("--workpath") + 1]), build.ROOT / "build" / "packaging-company")
        self.assertIn("--onedir", cmd)
        self.assertEqual(seen["program"], build.ROOT / "dist-company" / "Swangz" / "Swangz.exe")
        self.assertEqual(seen["dated"], (build.ROOT / "dist-company" / "Swangz", 1000000000))

    def test_company_is_refused_elsewhere(self):
        for platform in ("linux", "darwin"):
            with mock.patch.object(build.sys, "platform", platform), mock.patch.object(build.sys, "stderr"), \
                    self.assertRaises(SystemExit) as stop:
                build.main(["--company"])
            self.assertEqual(stop.exception.code, 2)

    def test_every_file_gets_the_source_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner = Path(tmp) / "_internal" / "a.pyd"
            inner.parent.mkdir()
            inner.write_bytes(b"x")
            build.date_files(tmp, 1000000000)
            self.assertEqual(int(inner.stat().st_mtime), 1000000000)

    def test_the_sbom_reads_the_module_list_of_a_one_folder_program(self):
        class Reader:
            def __init__(self, path):
                if not path.endswith("Swangz.exe"):
                    raise ValueError("not an archive")
                self.toc = {"PYZ-00.pyz": None}

            def open_embedded_archive(self, name):
                return types.SimpleNamespace(toc={"swangz_client.cli": None, "json": None})

        fakes = {name: types.ModuleType(name) for name in ("PyInstaller", "PyInstaller.archive")}
        fakes["PyInstaller.archive.readers"] = types.SimpleNamespace(CArchiveReader=Reader)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, fakes):
            (Path(tmp) / "_internal").mkdir()
            (Path(tmp) / "Swangz.exe").write_bytes(b"MZ program")
            (Path(tmp) / "_internal" / "tk.dll").write_bytes(b"MZ library")
            native, modules = sbom.archive_contents(tmp)
        self.assertEqual(list(native), ["_internal/tk.dll"])
        self.assertEqual(modules, ["json", "swangz_client.cli"])


class CompanyJourneyTests(unittest.TestCase):
    def test_it_runs_on_a_github_hosted_runner_only(self):
        for env in ({}, {"GITHUB_ACTIONS": "true"}, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"}):
            with mock.patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(SystemExit, "runner only"):
                e2e.main(["--setup", "a", "--previous", "b", "--previous-version", "1.0.0", "--new-version", "1.0.1",
                          "--evidence", "never-created"])
        self.assertFalse(Path("never-created").exists())

    def test_the_placeholder_values_pass_the_policy_validators(self):
        prepare = load("company_prepare", "deploy/chrome-policy/prepare.py")
        prepare.hostname(e2e.PINS["hub_host"])
        self.assertTrue(prepare.EXTENSION_ID.fullmatch(e2e.PINS["extension_id"]))
        prepare.update_address(e2e.PINS["extension_update_url"])

    def test_permissions_only_administrators_may_own_or_change(self):
        admins, users, creator = "S-1-5-32-544", "S-1-5-32-545", "S-1-3-0"

        def item(owner=admins, **rule):
            rules = [{"sid": admins, "allow": True, "rights": 0x1F01FF, "inherit_only": False}]
            if rule:
                rules.append({"sid": users, "allow": True, "rights": 0x1200A9, "inherit_only": False, **rule})
            return {"path": "p", "owner": owner, "rules": rules}

        self.assertEqual(e2e.acl_problems([item(), item(rights=0x1200A9)]), [])  # read and execute
        self.assertEqual(e2e.acl_problems([item(sid=creator, rights=0x10000000, inherit_only=True)]), [])
        self.assertEqual(e2e.acl_problems([item(allow=False, rights=0x1F01FF)]), [])
        signed_generic_write = 0x40000000
        signed_generic_all_and_read = -0x70000000  # GENERIC_READ | GENERIC_ALL, as PowerShell's [int] prints it
        for rights in (0x2, 0x4, 0x40, 0x10000, 0x40000, 0x80000, 0x1F01FF, signed_generic_write,
                       signed_generic_all_and_read):
            self.assertEqual(len(e2e.acl_problems([item(rights=rights)])), 1, hex(rights & 0xFFFFFFFF))
        self.assertEqual(len(e2e.acl_problems([item(owner="S-1-5-21-1-2-3-1001")])), 1)


class CompanyWorkflowTests(unittest.TestCase):
    def test_built_checked_scanned_and_uploaded(self):
        order = [WORKFLOW.index(text) for text in (
            "python packaging/build.py --company", "packaging\\windows\\swangz-company.iss",
            "packaging/windows/company_e2e.py", "- name: Secret scan", "name: Swangz-Windows-installer-RC-UNSIGNED")]
        self.assertEqual(order, sorted(order))
        scan = WORKFLOW.split("- name: Secret scan", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("dist-company packaging\\windows\\swangz-company.iss", scan)
        for name in ("- name: Build the company program", "- name: Company installer acceptance"):
            step = WORKFLOW.split(name, 1)[1].split("\n      - ", 1)[0]
            self.assertNotIn("continue-on-error", step)
        # the older-labelled installer is a test input: it goes to previous/, which is not uploaded
        self.assertIn('"/DOutputDir=$PWD\\previous" packaging\\windows\\swangz-company.iss', WORKFLOW)
        self.assertIn("- 'deploy/chrome-policy/prepare.py'", WORKFLOW)
        self.assertIn("--out artifacts\\Swangz-Company-$env:NEW_VERSION.cdx.json", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
