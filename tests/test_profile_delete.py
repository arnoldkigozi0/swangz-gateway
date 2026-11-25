"""Deleting a workspace folder on every system: what a link inside it points at is never touched, and a folder that
cannot be deleted yet stays reported and keeps Open off. Real files, links and (on Windows) junctions in a temporary
folder; no browser. The Windows cases run on the Windows runner."""

import hashlib
import errno
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import browser_profiles as bp
from swangz_client import workspace_launcher as wl

WINDOWS = os.name == "nt"
HOLD = "import sys; f = open(sys.argv[1], 'a'); print('held', flush=True); sys.stdin.read()"


def plain(path):
    path = str(path)
    return path[4:] if path.startswith("\\\\?\\") else path


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", plain(link), plain(target)], check=True, capture_output=True)


# Each way a folder entry can point somewhere else on this system.
DIR_LINKS = {"symlink": lambda link, target: os.symlink(plain(target), plain(link), target_is_directory=True)}
if WINDOWS:
    DIR_LINKS["junction"] = junction


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.data = self.base / "data"
        self.data.mkdir(mode=0o700)
        self.profiles = bp.Profiles(self.data)
        self.owner = bp.Owner("https://hub.example", "person_1", "device-1")
        self.outside = self.base / "outside"
        (self.outside / "deeper").mkdir(parents=True)
        (self.outside / "canary").write_bytes(b"belongs to somebody else")
        (self.outside / "deeper" / "canary").write_bytes(b"so does this")
        self.before = self.canaries()

    def canaries(self):
        """Names, content hashes and (Windows) attributes of everything outside the workspace."""
        out = {}
        for path in sorted(self.outside.rglob("*")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            out[path.relative_to(self.outside).as_posix()] = (digest, getattr(path.lstat(), "st_file_attributes", 0) & 0x1)
        return out

    def assert_outside_untouched(self):
        self.assertEqual(self.canaries(), self.before)

    def leftovers(self):
        return sorted(p.name for p in self.profiles.root.iterdir() if p.name != ".lock")

    def profile_with_content(self):
        folder = self.profiles.prepare(self.owner)
        (folder / "Default" / "Cache").mkdir(parents=True)
        (folder / "Default" / "Cookies").write_bytes(b"session")
        (folder / "Default" / "Cache" / "data_0").write_bytes(b"cache")
        return folder

    def block(self, folder):
        """Make deleting fail after the rename, the way this system really does it. -> the undo."""
        stuck = folder / "Default" / "stuck"
        if WINDOWS:  # a read-only file that also lives elsewhere: its attribute is not ours to clear
            shared = self.base / "shared"
            shared.write_bytes(b"shared")
            os.link(shared, stuck)
            os.chmod(shared, stat.S_IREAD)

            def undo():
                self.assertEqual(shared.read_bytes(), b"shared")
                self.assertFalse(shared.stat().st_mode & stat.S_IWRITE, "the other file kept its attribute")
                os.chmod(shared, stat.S_IWRITE)
            return undo
        if os.geteuid() == 0:
            self.skipTest("root ignores folder permissions")
        stuck.mkdir()
        (stuck / "file").write_text("x")
        stuck.chmod(0o500)

        def undo():
            for retired in self.profiles.root.glob(".retired-*"):
                (retired / "Default" / "stuck").chmod(0o700)
        return undo


class LinkTests(Base):
    def test_links_inside_the_folder_go_and_their_targets_stay(self):
        folder = self.profile_with_content()
        for kind, make in DIR_LINKS.items():
            make(folder / f"top-{kind}", self.outside)
            make(folder / "Default" / "Cache" / f"deep-{kind}", self.outside / "deeper")
        os.symlink(self.outside / "canary", folder / "Default" / "file-link")
        os.symlink(self.outside / "missing", folder / "Default" / "dangling")
        self.profiles.retire(folder.name, self.owner)
        self.assertEqual(self.leftovers(), [])
        self.assert_outside_untouched()

    def test_a_linked_root_is_refused_and_never_retargeted(self):
        for kind, make in DIR_LINKS.items():
            with self.subTest(kind=kind):
                data = self.base / f"data-{kind}"
                data.mkdir(mode=0o700)
                target = self.base / f"target-{kind}"
                (target / ("a" * 32)).mkdir(parents=True, mode=0o700)
                (target / ("a" * 32) / "canary").write_text("keep")
                target.chmod(0o700)
                make(data / "browser-profiles", target)
                profiles = bp.Profiles(data)
                for operation in (profiles.retire_all, lambda: profiles.retire_owner(self.owner),
                                  lambda: profiles.retire("a" * 32, self.owner), lambda: profiles.prepare(self.owner)):
                    with self.assertRaises(bp.ProfileError) as caught:
                        operation()
                    self.assertEqual(caught.exception.code, "unsafe_link")
                self.assertEqual([p.name for p in target.iterdir()], ["a" * 32])
                self.assertEqual((target / ("a" * 32) / "canary").read_text(), "keep")

    def test_a_profile_entry_that_is_itself_a_link_is_reported_and_not_followed(self):
        self.profiles.prepare(self.owner)
        for i, make in enumerate(DIR_LINKS.values()):
            make(self.profiles.root / (str(i) * 32), self.outside)
        out = self.profiles.retire_all()
        self.assertFalse(out["complete"])
        self.assertEqual({s["reason"] for s in out["skipped"]}, {"unsafe_link"})
        self.assert_outside_untouched()

    def swapped(self, name, make):
        """Retire a folder while `name` inside it turns into a link between the check and the open."""
        folder = self.profile_with_content()
        done = []

        def swap(path):
            if os.path.basename(path) == name and not done:
                done.append(path)
                os.rename(path, self.base / f"moved-{len(list(self.base.iterdir()))}")
                make(path, self.outside)
        with mock.patch.object(bp, "_before_open", swap):
            out = self.profiles.retire_owner(self.owner)
        self.assertEqual(len(done), 1, "the hook ran on the checked folder")
        return folder, out

    def test_a_folder_swapped_for_a_link_between_check_and_open_is_path_changed(self):
        for kind, make in DIR_LINKS.items():
            for name in ("Default", "Cache"):
                with self.subTest(kind=kind, swapped=name):
                    folder, out = self.swapped(name, make)
                    self.assertEqual(out["skipped"], [{"name": folder.name, "reason": "path_changed"}])
                    self.assertFalse(out["complete"])
                    self.assert_outside_untouched()
                    self.assertTrue(self.profiles.retire_all()["complete"])  # the link itself goes on the next try
                    self.assertEqual(self.leftovers(), [])
                    self.assert_outside_untouched()

    def test_the_retired_folder_swapped_for_a_link_is_path_changed(self):
        for kind, make in DIR_LINKS.items():
            with self.subTest(kind=kind):
                folder = self.profile_with_content()
                done = []

                def swap(path):
                    if ".retired-" in os.path.basename(path) and not done:
                        done.append(path)
                        os.rename(path, self.base / f"kept-{kind}")
                        make(path, self.outside)
                with mock.patch.object(bp, "_before_open", swap):
                    out = self.profiles.retire_owner(self.owner)
                self.assertEqual(out["skipped"], [{"name": folder.name, "reason": "path_changed"}])
                self.assert_outside_untouched()
                # A link left under a retired name is reported, never followed, and keeps Open off.
                with self.assertRaises(bp.ProfileError) as caught:
                    self.profiles.prepare(self.owner)
                self.assertEqual(caught.exception.code, "purge_pending")
                self.assert_outside_untouched()
                for entry in self.profiles.root.glob(".retired-*"):
                    os.rmdir(entry) if kind == "junction" else os.unlink(entry)


class DeleteTests(Base):
    def test_read_only_files_are_deleted(self):
        folder = self.profile_with_content()
        os.chmod(folder / "Default" / "Cookies", stat.S_IREAD)
        if WINDOWS:
            os.chmod(folder / "Default" / "Cache", stat.S_IREAD)
        self.assertTrue(self.profiles.retire_owner(self.owner)["complete"])
        self.assertEqual(self.leftovers(), [])

    def test_paths_longer_than_260_characters_are_deleted(self):
        folder = self.profile_with_content()
        deep = str(folder)
        for _ in range(8):
            deep = os.path.join(deep, "n" * 50)
        long = bp._extended(deep) if WINDOWS else deep
        os.makedirs(long)
        with open(os.path.join(long, "entry"), "w") as f:
            f.write("cached")
        self.assertGreater(len(deep), 400)
        self.assertTrue(self.profiles.retire_owner(self.owner)["complete"])
        self.assertEqual(self.leftovers(), [])

    def test_no_system_is_refused(self):
        self.assertNotIn("unsupported_platform", Path(bp.__file__).read_text(encoding="utf-8"))


class DeleteAllTests(Base):
    """`cleanup`: everything under browser-profiles/ goes, whoever it belongs to; only the root and its lock stay."""

    def test_every_folder_and_stray_entry_goes_and_link_targets_stay(self):
        folder = self.profile_with_content()
        self.profiles.prepare(bp.Owner("https://hub.example", "person_2", "device-1"))
        for kind, make in DIR_LINKS.items():
            make(folder / "Default" / f"deep-{kind}", self.outside / "deeper")
            make(self.profiles.root / f"top-{kind}", self.outside)
        os.symlink(self.outside / "canary", self.profiles.root / "file-link")
        os.symlink(self.outside / "missing", self.profiles.root / "dangling")
        (self.profiles.root / "stray").write_bytes(b"x")
        (self.profiles.root / (".tmp-" + "b" * 32)).mkdir()
        (self.profiles.root / "no-marker").mkdir()
        folder.chmod(0o755)  # modes another operation would refuse never keep sign-ins on the disk
        self.profiles.root.chmod(0o755)
        self.assertEqual(self.profiles.delete_all(), [])
        self.assertEqual(self.leftovers(), [])
        self.assertTrue((self.profiles.root / ".lock").is_file())
        self.assert_outside_untouched()
        self.assertEqual(self.profiles.delete_all(), [])  # a second run changes nothing
        self.assertEqual(self.leftovers(), [])

    def test_nothing_there_creates_nothing(self):
        self.assertEqual(self.profiles.delete_all(), [])
        self.assertEqual(list(self.data.iterdir()), [])
        self.assertEqual(bp.Profiles(self.base / "no-data").delete_all(), [])
        self.assertFalse((self.base / "no-data").exists())

    def test_a_linked_root_or_data_folder_is_reported_and_left_alone(self):
        for kind, make in DIR_LINKS.items():
            with self.subTest(kind=kind):
                data = self.base / f"data-{kind}"
                data.mkdir(mode=0o700)
                make(data / "browser-profiles", self.outside)
                make(self.base / f"linked-data-{kind}", data)
                for profiles in (bp.Profiles(data), bp.Profiles(self.base / f"linked-data-{kind}")):
                    self.assertEqual(profiles.delete_all(), [(str(profiles.root), "unsafe_link")])
                self.assert_outside_untouched()

    def test_what_cannot_be_deleted_is_reported_and_a_later_run_finishes(self):
        folder = self.profile_with_content()
        other = self.profiles.prepare(bp.Owner("https://hub.example", "person_2", "device-1"))
        undo = self.block(folder)
        (path, _), = self.profiles.delete_all()
        retired, = self.profiles.root.glob(".retired-*")
        self.assertEqual(path, str(retired))  # renamed first, so a half-deleted folder is never opened again
        self.assertFalse(other.exists(), "one stuck folder does not keep the others")
        undo()
        self.assertEqual(self.profiles.delete_all(), [])
        self.assertEqual(self.leftovers(), [])
        self.assert_outside_untouched()

    def window(self, folder):
        """A stand-in for a browser still open on `folder`: it holds Chrome's SingletonLock and, like Chrome, keeps
        writing to the folder's path, creating it again if it has gone. -> the function that closes it."""
        script = ("import os, sys, time\n"
                  "folder = sys.argv[1]\n"
                  "os.symlink('this-host-%d' % os.getpid(), os.path.join(folder, 'SingletonLock'))\n"
                  "print('open', flush=True)\n"
                  "while True:\n"
                  "    os.makedirs(os.path.join(folder, 'Default'), mode=0o700, exist_ok=True)\n"
                  "    with open(os.path.join(folder, 'Default', 'Preferences'), 'w') as f:\n"
                  "        f.write('visited')\n"
                  "    time.sleep(0.01)\n")
        proc = subprocess.Popen([sys.executable, "-I", "-c", script, str(folder)], stdout=subprocess.PIPE, text=True)

        def close():
            proc.kill()
            proc.wait(10)
            proc.stdout.close()
        self.addCleanup(close)
        self.assertEqual(proc.stdout.readline().strip(), "open")
        return close

    @unittest.skipIf(WINDOWS, "SingletonLock is the Linux and macOS lock; Windows refuses the rename itself")
    def test_a_folder_an_open_browser_holds_is_reported_left_whole_and_deleted_once_it_closes(self):
        folder = self.profile_with_content()
        other = self.profiles.prepare(bp.Owner("https://hub.example", "person_2", "device-1"))
        close = self.window(folder)
        self.assertEqual(self.profiles.delete_all(), [(str(folder), "in_use")])
        time.sleep(0.1)  # the browser goes on writing
        self.assertEqual((folder / "Default" / "Cookies").read_bytes(), b"session")
        self.assertTrue((folder / bp.MARKER).is_file())
        self.assertFalse(other.exists(), "one held folder does not keep the others")
        self.assertEqual(list(self.profiles.root.glob(".retired-*")), [])
        close()
        self.assertEqual(self.profiles.delete_all(), [])
        self.assertEqual(self.leftovers(), [])

    @unittest.skipIf(WINDOWS, "SingletonLock is the Linux and macOS lock; Windows refuses the rename itself")
    def test_retiring_refuses_a_folder_an_open_browser_holds(self):
        folder = self.profile_with_content()
        close = self.window(folder)
        with self.assertRaises(bp.ProfileError) as refused:
            self.profiles.retire(folder.name, self.owner)
        self.assertEqual(refused.exception.code, "in_use")
        for out in (self.profiles.retire_owner(self.owner), self.profiles.retire_all()):
            self.assertEqual(out, {"retired": [], "skipped": [{"name": folder.name, "reason": "in_use"}],
                                   "complete": False})
        self.assertTrue((folder / bp.MARKER).is_file())
        close()
        self.profiles.retire(folder.name, self.owner)
        self.assertEqual(self.leftovers(), [])

    @unittest.skipIf(WINDOWS, "SingletonLock is the Linux and macOS lock")
    def test_only_a_lock_naming_a_live_process_counts_as_held(self):
        folder = self.profile_with_content()
        lock = folder / "SingletonLock"
        self.assertFalse(bp._in_use(folder))  # no lock
        lock.write_bytes(b"host-%d" % os.getpid())
        self.assertTrue(bp._in_use(folder))  # a lock that cannot be read as a link: not known to be free
        for target, held in (("host-%d" % os.getpid(), True), ("my-host-name-%d" % os.getpid(), True),
                             ("host-0", False), ("host-", False), ("host", False), ("host-abc", False),
                             ("host-" + "9" * 30, False)):
            with self.subTest(target=target):
                lock.unlink()
                os.symlink(target, lock)
                self.assertEqual(bp._in_use(folder), held)
        lock.unlink()
        os.symlink("host-123", lock)
        with mock.patch.object(bp.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(bp._in_use(folder))
        # somebody else's process is still a process; any other error is not an answer, so the folder stays
        for call in ("kill", "readlink"):
            for error in (PermissionError(errno.EACCES, "denied"), OSError(errno.EIO, "io")):
                with self.subTest(call=call, error=error), mock.patch.object(bp.os, call, side_effect=error):
                    self.assertTrue(bp._in_use(folder))

    @unittest.skipUnless(WINDOWS, "the Windows read-only attribute on a link")
    def test_a_read_only_link_never_changes_its_target(self):  # pragma: no cover - Windows runner
        from swangz_client import winacl
        folder = self.profile_with_content()
        target = self.outside / "canary"
        os.chmod(target, stat.S_IREAD)
        self.addCleanup(os.chmod, target, stat.S_IWRITE)
        self.before = self.canaries()
        file_link, dir_link = folder / "Default" / "file-link", folder / "Default" / "junction"
        os.symlink(target, file_link)
        junction(dir_link, self.outside)
        for link in (file_link, dir_link):
            fd = winacl.open_entry(str(link))
            try:
                winacl.set_open_attributes(fd, os.lstat(link).st_file_attributes | stat.FILE_ATTRIBUTE_READONLY)
            finally:
                os.close(fd)
            self.assertTrue(os.lstat(link).st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
        left = self.profiles.delete_all()
        self.assert_outside_untouched()
        if left:
            self.assertEqual([reason for _, reason in left], ["readonly_link"])
        else:
            self.assertEqual(self.leftovers(), [])


class EntrySwapTests(Base):
    """Windows deletes a file or link through a handle on the entry itself: what the handle holds is what is checked."""

    def swapped_cookies(self, make):
        """delete_all while `Cookies` turns into something else after it was listed as an ordinary file."""
        self.profile_with_content()
        done = []

        def swap(path):
            if os.path.basename(path) == "Cookies" and not done:
                done.append(path)
                os.remove(path)
                make(path)
        with mock.patch.object(bp, "_before_delete", swap):
            left = self.profiles.delete_all()
        self.assertEqual(len(done), 1, "the hook ran before the entry was opened")
        return left

    @unittest.skipUnless(WINDOWS, "Windows handle deletion")
    def test_a_file_swapped_for_a_shared_read_only_file_keeps_its_attribute(self):  # pragma: no cover - Windows runner
        shared = self.outside / "canary"
        os.chmod(shared, stat.S_IREAD)
        self.addCleanup(os.chmod, shared, stat.S_IWRITE)
        self.before = self.canaries()
        left = self.swapped_cookies(lambda path: os.link(shared, path))
        self.assertEqual([reason for _, reason in left], ["shared_file"])
        self.assertFalse(shared.stat().st_mode & stat.S_IWRITE, "the file elsewhere kept its attribute")
        self.assert_outside_untouched()

    @unittest.skipUnless(WINDOWS, "Windows handle deletion")
    def test_a_file_swapped_for_a_link_loses_the_link_only(self):  # pragma: no cover - Windows runner
        for kind, make in (("junction", junction), ("symlink", lambda link, target: os.symlink(
                plain(target), plain(link), target_is_directory=True))):
            with self.subTest(kind=kind):
                self.assertEqual(self.swapped_cookies(lambda path: make(path, self.outside)), [])
                self.assertEqual(self.leftovers(), [])
                self.assert_outside_untouched()


class NativeCleanupTests(Base):
    """`swangz cleanup` with the token and folder owner Windows really reports (D-026, "Amendment 25 Nov")."""

    @unittest.skipUnless(WINDOWS, "the real Windows token and folder owner")
    def test_cleanup_with_the_real_token_deletes_and_leaves_a_junctions_target(self):  # pragma: no cover
        from swangz_client import cli, core, shell, winacl
        kind, user = winacl.token_elevation_type(), winacl.current_sid()
        made_by_us = winacl.owner_sid(str(self.data))
        print(f"\ncleanup token: TokenElevationType={kind} user={user} owner of a folder this token made={made_by_us}",
              flush=True)
        if os.environ.get("GITHUB_ACTIONS"):
            self.assertEqual(kind, 1, "the hosted runner has the default token")
        self.assertIn(kind, (1, 3))
        self.assertEqual(shell.cleanup_refusal(self.data), None if made_by_us == user else "wrong_account")
        winacl.restrict(str(self.data))  # the person owns the app data folder
        self.assertEqual(winacl.owner_sid(str(self.data)), user)
        self.assertIsNone(shell.cleanup_refusal(self.data))
        folder = self.profile_with_content()
        junction(folder / "Default" / "junction", self.outside)
        client = core.Client(core.Paths(self.base / "home", self.data))
        with mock.patch.object(shell, "set_autostart"), mock.patch.object(cli, "say"):
            self.assertEqual(cli.main(["cleanup"], client=client), 0)
        self.assertEqual(self.leftovers(), [])
        self.assert_outside_untouched()


class PendingTests(Base):
    """A retired folder that cannot be deleted: reported, Open refused with a reason, deleted before the next launch."""

    def test_pending_refuses_open_for_everyone_and_clears_before_the_next_launch(self):
        folder = self.profile_with_content()
        undo = self.block(folder)
        out = self.profiles.retire_owner(self.owner)
        self.assertFalse(out["complete"])
        self.assertEqual([s["name"] for s in out["skipped"]], [folder.name])
        retired, = self.profiles.root.glob(".retired-*")
        if WINDOWS:
            self.assertFalse((retired / "Default" / "Cookies").exists(), "one stuck entry does not keep the others")
        launcher = wl.Launcher(self.data, finder=lambda: "chrome", acl=lambda p: True)
        for owner in (self.owner, bp.Owner("https://hub.example", "person_2", "device-1")):
            with self.assertRaises(wl.LaunchError) as caught:
                launcher.ready(owner)
            self.assertEqual(caught.exception.code, "purge_pending")
        with self.assertRaises(bp.ProfileError) as caught:
            self.profiles.retire(folder.name, self.owner)
        self.assertEqual(caught.exception.code, "purge_pending")
        undo()
        _, fresh = launcher.ready(self.owner)
        self.assertEqual(self.leftovers(), [fresh.name])
        self.assert_outside_untouched()

    @unittest.skipUnless(WINDOWS, "an open file stops a rename on Windows only")
    def test_a_file_held_open_keeps_the_folder_and_reports_it(self):  # pragma: no cover - Windows runner
        folder = self.profile_with_content()
        holder = subprocess.Popen([sys.executable, "-c", HOLD, str(folder / "Default" / "Cookies")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            self.assertEqual(holder.stdout.readline().strip(), b"held")
            out = self.profiles.retire_owner(self.owner)
            self.assertFalse(out["complete"])
            self.assertEqual([s["name"] for s in out["skipped"]], [folder.name])
            self.assertTrue((folder / "Default" / "Cookies").exists())
        finally:
            holder.communicate(timeout=30)
        self.assertTrue(self.profiles.retire_owner(self.owner)["complete"])
        self.assertEqual(self.leftovers(), [])

    @unittest.skipUnless(WINDOWS, "Windows handle sharing")
    def test_a_held_folder_cannot_be_renamed_or_removed(self):  # pragma: no cover - Windows runner
        from swangz_client import winacl
        folder = self.base / "held"
        folder.mkdir()
        fd = winacl.hold_folder(bp._extended(folder))
        try:
            self.assertRaises(OSError, os.rename, folder, self.base / "renamed")
            self.assertRaises(OSError, os.rmdir, folder)
        finally:
            os.close(fd)
        shutil.rmtree(folder)


if __name__ == "__main__":
    unittest.main()
