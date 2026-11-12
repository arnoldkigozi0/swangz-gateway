"""W6 of docs/MANAGED-WORKSPACE.md: the cross-platform matrix for where the workspace lives and how it is started.

Two kinds of test, both standard library only:

* Table tests pretend to be each OS (`sys.platform`, environment) and run everywhere, so a Linux developer sees a
  Windows path mistake. They prove the arithmetic, not the OS.
* Native tests run only on the OS they name and are skipped elsewhere with the reason printed. Run on the
  ubuntu, windows and macos runners of `.github/workflows/browser-profiles.yml`, they are what proves behaviour on
  that OS. A skip on every runner is listed in the PR as "not proven".

The launcher of W3 (browser discovery, launch arguments) is covered once it lands on `feature/managed-workspace`;
until then those tests skip with a reason instead of passing quietly.
"""

import importlib
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch

from swangz_client import browser_profiles as bp
from swangz_client import core

HOME = {"linux": "/home/grace", "darwin": "/Users/grace", "win32": "C:\\Users\\grace"}


def data_dir(platform, home, env):
    with patch.object(sys, "platform", platform), patch.dict(os.environ, env, clear=True):
        return core.default_data_dir(home)


class DataFolderTableTests(unittest.TestCase):
    """Where the app's folder, and so every workspace profile, lands on each OS."""

    def parts(self, path):
        return tuple(str(path).replace("\\", "/").split("/"))

    def test_windows_uses_local_app_data_not_roaming(self):
        got = data_dir("win32", HOME["win32"], {"LOCALAPPDATA": "C:\\Users\\grace\\AppData\\Local", "APPDATA": "C:\\Users\\grace\\AppData\\Roaming"})
        self.assertEqual(self.parts(got)[-2:], ("Local", "Swangz"))
        self.assertNotIn("Roaming", self.parts(got), "a roaming profile would copy the workspace to other machines")

    def test_windows_without_local_app_data_falls_back_under_home(self):
        got = data_dir("win32", HOME["win32"], {})
        self.assertEqual(self.parts(got)[-4:], ("grace", "AppData", "Local", "Swangz"))

    def test_macos_uses_application_support(self):
        got = data_dir("darwin", HOME["darwin"], {"XDG_DATA_HOME": "/elsewhere"})
        self.assertEqual(self.parts(got), ("", "Users", "grace", "Library", "Application Support", "Swangz"))

    def test_linux_follows_xdg_data_home_then_local_share(self):
        self.assertEqual(self.parts(data_dir("linux", HOME["linux"], {"XDG_DATA_HOME": "/data/grace"})), ("", "data", "grace", "swangz"))
        self.assertEqual(self.parts(data_dir("linux", HOME["linux"], {})), ("", "home", "grace", ".local", "share", "swangz"))

    def test_no_os_puts_it_inside_a_browsers_own_folder(self):
        for platform, env in (("win32", {}), ("darwin", {}), ("linux", {})):
            got = "/".join(self.parts(data_dir(platform, HOME[platform], env))).lower()
            for browser in ("google/chrome", "google-chrome", "chromium", "microsoft/edge", "bravesoftware"):
                self.assertNotIn(browser, got, platform)

    def test_swangz_home_overrides_on_every_os(self):
        for platform in HOME:
            with patch.object(sys, "platform", platform), patch.dict(os.environ, {"SWANGZ_HOME": "/override"}, clear=True):
                self.assertEqual(core.Paths(home=HOME[platform]).data, Path("/override"), platform)


class ProfileFolderTests(unittest.TestCase):
    """Runs natively on each runner: real folders, real permissions."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"
        self.data.mkdir(mode=0o700)
        self.profiles = bp.Profiles(self.data)
        self.owner = bp.Owner("https://hub.example", "person_7", "device-1")

    def test_one_folder_per_person_device_and_os_user_under_the_apps_folder(self):
        a = self.profiles.prepare(self.owner)
        self.assertEqual(a.parent, self.data / "browser-profiles")
        self.assertRegex(a.name, r"^[0-9a-f]{32}$")
        self.assertEqual(self.profiles.prepare(self.owner), a)
        other = self.profiles.prepare(bp.Owner("https://hub.example", "person_7", "device-2"))
        self.assertNotEqual(other, a)
        self.assertNotIn(" ", str(a.relative_to(self.data)), "no spaces the launcher would have to quote")

    @unittest.skipIf(os.name == "nt", "POSIX permission bits; Windows ACLs are checked by W3 and listed as not proven until then")
    def test_folders_are_owner_only_on_linux_and_macos(self):
        a = self.profiles.prepare(self.owner)
        for path in (self.data / "browser-profiles", a):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700, path)
        self.assertEqual(stat.S_IMODE((a / bp.MARKER).stat().st_mode), 0o600)

    @unittest.skipIf(os.name == "nt", "retiring is refused on Windows (see the next test)")
    def test_retire_removes_the_folder_on_linux_and_macos(self):
        a = self.profiles.prepare(self.owner)
        self.assertEqual(self.profiles.retire_owner(self.owner)["retired"], [a.name])
        self.assertFalse(a.exists())

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_retire_is_refused_on_windows_rather_than_half_done(self):  # pragma: no cover - Windows runner
        a = self.profiles.prepare(self.owner)
        out = self.profiles.retire_owner(self.owner)
        self.assertFalse(out["complete"])
        self.assertIn({"name": a.name, "reason": "unsupported_platform"}, out["skipped"])
        self.assertTrue(a.exists())

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows runners")
    def test_a_symlinked_root_is_refused(self):
        real = self.data.parent / "elsewhere"
        real.mkdir(mode=0o700)
        (self.data / "browser-profiles").symlink_to(real, target_is_directory=True)
        with self.assertRaises(bp.ProfileError):
            self.profiles.prepare(self.owner)
        self.assertEqual(list(real.iterdir()), [])


class NativeDataFolderTests(unittest.TestCase):
    """The real `default_data_dir` on the runner's own OS, with its real environment."""

    def test_the_real_folder_for_this_os(self):
        got = core.default_data_dir(Path.home())
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA")
            self.assertTrue(local, "a Windows runner has LOCALAPPDATA")
            self.assertEqual(got, Path(local) / "Swangz")
            self.assertIsInstance(PureWindowsPath(got), PureWindowsPath)
        elif sys.platform == "darwin":
            self.assertEqual(got, Path.home() / "Library" / "Application Support" / "Swangz")
        else:
            base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
            self.assertEqual(got, Path(base) / "swangz")
            self.assertIsInstance(PurePosixPath(got), PurePosixPath)


LAUNCHER = None
for _name in ("swangz_client.workspace", "swangz_client.launcher"):
    try:
        LAUNCHER = importlib.import_module(_name)
        break
    except ImportError:
        pass


@unittest.skipIf(LAUNCHER is None, "W3 launcher not on this branch yet: launch arguments are NOT PROVEN by this run")
class LaunchArgumentTests(unittest.TestCase):  # filled in against W3's contract when it lands
    def test_placeholder(self):  # pragma: no cover
        self.fail("W3 has landed: replace this placeholder with the launch-argument matrix")


if __name__ == "__main__":
    unittest.main()
