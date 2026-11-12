"""Port-free tests for inert profile preparation; never touch a real browser profile."""
import ast
import errno
import json
import os
import select
import shutil
import signal
import stat
import tempfile
import time
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from swangz_client import browser_profiles as bp


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.data = self.base / "data"
        self.data.mkdir(mode=0o700)
        self.profiles = bp.Profiles(self.data)
        self.owner = bp.Owner("https://hub.example", "person_1", "device-1")

    def owner2(self):
        return bp.Owner("https://hub.example", "person_2", "device-1")

    def marker(self, path):
        return json.loads((path / bp.MARKER).read_text())

    def write_marker(self, path, marker):
        (path / bp.MARKER).write_text(json.dumps(marker))

    def error(self, code, fn, *args):
        with self.assertRaises(bp.ProfileError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def snapshot(self, root=None):
        root = self.base if root is None else root
        return {str(p.relative_to(root)): ("directory",) if p.is_dir() else ("file", p.read_bytes())
                for p in (root, *root.rglob("*"))}

    def windows_batch_refusal(self, result, candidates, unknown=()):
        self.assertFalse(result["complete"])
        self.assertEqual(result["retired"], [])
        self.assertCountEqual(result["skipped"],
                              [{"name": p.name, "reason": "unsupported_platform"} for p in candidates]
                              + [{"name": p.name, "reason": "unknown_entry"} for p in unknown])

    def test_prepare_reuses_exact_owner(self):
        p = self.profiles.prepare(self.owner)
        self.assertRegex(p.name, r"^[0-9a-f]{32}$")
        self.assertEqual(self.profiles.prepare(self.owner), p)
        self.assertEqual(self.marker(p)["profile_id"], p.name)
        self.assertEqual(set(self.marker(p)), {"version", "profile_id", "origin", "person_id", "device_id", "os_user", "seat", "state", "created"})

    def test_different_owners_do_not_reuse(self):
        a = self.profiles.prepare(self.owner)
        b = self.profiles.prepare(self.owner2())
        self.assertNotEqual(a, b)
        if os.name == "nt":
            before = self.snapshot()
            self.error("unsupported_platform", self.profiles.retire, a.name, self.owner2())
            self.assertEqual(self.snapshot(), before)
        else:
            self.error("owner_mismatch", self.profiles.retire, a.name, self.owner2())
        self.assertTrue(a.exists() and b.exists())

    def test_origin_normalization(self):
        a = bp.Owner("HTTPS://HUB.EXAMPLE:443/", "p", "d")
        b = bp.Owner("https://hub.example", "p", "d")
        self.assertEqual(a.fields, b.fields)
        self.assertEqual(bp.Owner("http://localhost:8000", "p", "d").fields["origin"], "http://localhost:8000")
        self.assertEqual(bp.Owner("http://[::1]:8000", "p", "d").fields["origin"], "http://[::1]:8000")

    def test_origin_refuses_insecure_and_nonorigins_even_with_override(self):
        with patch.dict(os.environ, {"SWANGZ_ALLOW_HTTP": "1"}):
            for origin in ("http://outside.example", "https://user:secret@hub.example", "https://hub.example/path", "https://hub.example?x=1", "file:///tmp", "https://hub.example:bad", "https://bad host", "https://host\\escape"):
                self.error("origin_invalid", bp.Owner, origin, "p", "d")

    def test_identifiers(self):
        for bad in ("", "../p", "a/b", "a\\b", "p@company.example", "a" * 65, 1, None):
            self.error("owner_invalid", bp.Owner, "https://hub.example", bad, "d")
            self.error("owner_invalid", bp.Owner, "https://hub.example", "p", bad)

    def test_seat_generations(self):
        for bad in (None, True, 0, -1, 1.5, "1"):
            self.error("owner_invalid", bp.Owner, "https://hub.example", "p", "d", "seat", bad)
        self.error("owner_invalid", bp.Owner, "https://hub.example", "p", "d", None, 1)
        self.assertEqual(bp.Owner("https://hub.example", "p", "d", "seat", 2).fields["seat"], {"id": "seat", "generation": 2})

    def test_generation_changes_refuse(self):
        owner = lambda gen: bp.Owner("https://hub.example", "p", "d", "seat", gen)
        p = self.profiles.prepare(owner(2))
        self.error("superseded_present", self.profiles.prepare, owner(3))
        self.error("newer_generation_present", self.profiles.prepare, owner(1))
        self.assertTrue(p.exists())

    def test_duplicate_markers_refuse_without_deleting(self):
        a = self.profiles.prepare(self.owner)
        b = a.parent / ("b" * 32)
        shutil.copytree(a, b)
        marker = self.marker(b); marker["profile_id"] = b.name; self.write_marker(b, marker)
        self.error("duplicate_profiles", self.profiles.prepare, self.owner)
        self.assertTrue(a.exists() and b.exists())

    def test_copied_marker_not_reused_or_retired_by_owner(self):
        a = self.profiles.prepare(self.owner)
        b = a.parent / ("b" * 32)
        shutil.copytree(a, b)
        self.assertEqual(self.profiles.prepare(self.owner), a)
        if os.name == "nt":
            before = self.snapshot()
            self.error("unsupported_platform", self.profiles.retire, b.name, self.owner)
            self.assertEqual(self.snapshot(), before)
        else:
            self.error("marker_invalid", self.profiles.retire, b.name, self.owner)
        self.assertTrue(b.exists())

    def test_corrupt_marker_retirement_semantics(self):
        a = self.profiles.prepare(self.owner)
        (a / bp.MARKER).write_text("broken")
        if os.name == "nt":
            before = self.snapshot()
            self.error("unsupported_platform", self.profiles.retire, a.name, self.owner)
            self.assertEqual(self.snapshot(), before)
        else:
            self.error("marker_invalid", self.profiles.retire, a.name, self.owner)
        b = self.profiles.prepare(self.owner)
        self.assertNotEqual(a, b)
        before = self.snapshot()
        result = self.profiles.retire_all()
        if os.name == "nt":
            self.windows_batch_refusal(result, (a, b))
            self.assertEqual(self.snapshot(), before)
        else:
            self.assertEqual(set(result["retired"]), {a.name, b.name})
            self.assertTrue(result["complete"])

    def test_owner_retirement_does_not_delete_others(self):
        a = self.profiles.prepare(self.owner)
        b = self.profiles.prepare(self.owner2())
        before = self.snapshot()
        result = self.profiles.retire_owner(self.owner)
        if os.name == "nt":
            self.windows_batch_refusal(result, (a, b))
            self.assertEqual(self.snapshot(), before)
        else:
            self.assertEqual(result["retired"], [a.name]); self.assertTrue(b.exists())

    def test_unknown_entry_reported_but_safe_entry_retired(self):
        a = self.profiles.prepare(self.owner)
        unknown = a.parent / "keep-this"; unknown.mkdir(mode=0o700)
        before = self.snapshot()
        result = self.profiles.retire_all()
        if os.name == "nt":
            self.windows_batch_refusal(result, (a,), unknown=(unknown,))
            self.assertEqual(self.snapshot(), before)
        else:
            self.assertEqual(result["retired"], [a.name]); self.assertFalse(result["complete"])
            self.assertEqual(result["skipped"][0]["name"], "keep-this"); self.assertTrue(unknown.exists())

    def test_owner_marker_mutation_is_rejected(self):
        self.owner.fields["token"] = "never persist"
        self.error("owner_invalid", self.profiles.prepare, self.owner)
        self.assertFalse(self.profiles.root.exists())

    def test_marker_extra_secret_field_is_invalid(self):
        p = self.profiles.prepare(self.owner)
        marker = self.marker(p); marker["token"] = "not allowed"; self.write_marker(p, marker)
        if os.name == "nt":
            before = self.snapshot()
            self.error("unsupported_platform", self.profiles.retire, p.name, self.owner)
            self.assertEqual(self.snapshot(), before)
        else:
            self.error("marker_invalid", self.profiles.retire, p.name, self.owner)

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_root_preflight_blocks_all_cleanup(self):
        p = self.profiles.prepare(self.owner)
        self.profiles.root.chmod(0o755)
        self.error("unsafe_permissions", self.profiles.retire_all)
        self.assertTrue(p.exists())

    def test_absent_marker_device_wide_retirement(self):
        a = self.profiles.prepare(self.owner); (a / bp.MARKER).unlink()
        if os.name == "nt":
            before = self.snapshot()
            self.windows_batch_refusal(self.profiles.retire_all(), (a,))
            self.assertEqual(self.snapshot(), before)
        else:
            self.assertTrue(self.profiles.retire_all()["complete"]); self.assertFalse(a.exists())

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_permissions_and_unsafe_marker(self):
        a = self.profiles.prepare(self.owner)
        for p in (self.profiles.root, a):
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((a / bp.MARKER).stat().st_mode), 0o600)
        (a / bp.MARKER).chmod(0o644)
        self.error("marker_invalid", self.profiles.retire, a.name, self.owner)

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_data_preflight_never_chmods_or_removes(self):
        a = self.profiles.prepare(self.owner); self.data.chmod(0o777)
        self.error("unsafe_permissions", self.profiles.retire_all)
        self.assertTrue(a.exists()); self.assertEqual(stat.S_IMODE(self.data.stat().st_mode), 0o777)

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_unsafe_profile_is_skipped(self):
        a = self.profiles.prepare(self.owner); b = self.profiles.prepare(self.owner2()); b.chmod(0o755)
        result = self.profiles.retire_all()
        self.assertEqual(result["retired"], [a.name]); self.assertFalse(result["complete"]); self.assertTrue(b.exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink setup and semantics")
    def test_symlinked_data_and_root_refused(self):
        alias = self.base / "alias"; alias.symlink_to(self.data, target_is_directory=True)
        self.error("unsafe_link", bp.Profiles(alias).prepare, self.owner)
        self.profiles.root.symlink_to(self.base, target_is_directory=True)
        self.error("unsafe_link", self.profiles.prepare, self.owner)

    @unittest.skipIf(os.name == "nt", "POSIX symlink setup and semantics")
    def test_symlinked_ancestor_is_allowed(self):
        parent = self.base / "alias"; parent.symlink_to(self.base, target_is_directory=True)
        p = bp.Profiles(parent / "data").prepare(self.owner)
        self.assertTrue(p.exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink purge semantics")
    def test_purge_does_not_follow_interior_links(self):
        a = self.profiles.prepare(self.owner)
        outside = self.base / "outside"; outside.mkdir(); (outside / "precious").write_text("keep")
        (a / "link").symlink_to(outside, target_is_directory=True)
        nested = a / "nested"; nested.mkdir(); (nested / "link").symlink_to(outside / "precious")
        self.profiles.retire(a.name, self.owner)
        self.assertEqual((outside / "precious").read_text(), "keep")

    def test_mock_windows_reparse_attributes_refused(self):
        info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=info):
            self.error("unsafe_link", bp._check, self.data)

    def test_temp_recovery_marked_unmarked_and_fresh(self):
        self.profiles.prepare(self.owner)
        for i in range(3):
            p = self.profiles.root / (".tmp-" + str(i) * 32); p.mkdir(mode=0o700)
            if i == 1: (p / bp.MARKER).write_text("incomplete")
            if i < 2: os.utime(p, (time.time() - 200,) * 2)
        before = self.snapshot()
        self.profiles.prepare(self.owner)
        if os.name == "nt":
            self.assertEqual(self.snapshot(), before)
        else:
            self.assertFalse((self.profiles.root / (".tmp-" + "0" * 32)).exists())
            self.assertFalse((self.profiles.root / (".tmp-" + "1" * 32)).exists())
        self.assertTrue((self.profiles.root / (".tmp-" + "2" * 32)).exists())

    def test_crash_before_publish_discards_stage_after_stale_limit(self):
        with patch.object(bp.os, "rename", side_effect=OSError("crash before publish")):
            with self.assertRaises(OSError): self.profiles.prepare(self.owner)
        stage, = self.profiles.root.glob(".tmp-*")
        self.assertTrue((stage / bp.MARKER).exists())
        os.utime(stage, (time.time() - 200,) * 2)
        before = self.snapshot(stage)
        p = self.profiles.prepare(self.owner)
        if os.name == "nt":
            self.assertEqual(self.snapshot(stage), before)
            self.assertTrue(p.exists()); self.assertNotEqual(p, stage)
        else:
            self.assertFalse(stage.exists()); self.assertTrue(p.exists())

    def test_retired_recovery(self):
        a = self.profiles.prepare(self.owner)
        retired = a.parent / (".retired-" + "e" * 32); a.rename(retired)
        if os.name == "nt":
            before = self.snapshot(retired)
            self.profiles.prepare(self.owner)
            self.assertEqual(self.snapshot(retired), before)
        else:
            self.profiles.prepare(self.owner); self.assertFalse(retired.exists())

    def test_nested_lock_and_old_json_preserved(self):
        with self.profiles._locked():
            self.error("busy", self.profiles.prepare, self.owner)
        lock = self.profiles.root / ".lock"
        before = lock.stat()
        for pid in (os.getpid(), 999999999):
            raw = json.dumps({"pid": pid, "at": 1, "nonce": "old-format"}).encode()
            lock.write_bytes(raw)
            os.utime(lock, (1, 1))
            self.profiles.prepare(self.owner)
            self.assertEqual(lock.read_bytes(), raw)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), (before.st_dev, before.st_ino))

    @unittest.skipUnless(hasattr(os, "fork"), "needs POSIX fork")
    def test_aged_live_holder_stays_exclusive(self):
        ready_r, ready_w = os.pipe(); stop_r, stop_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                with self.profiles._locked():
                    os.utime(self.profiles.root / ".lock", (time.time() - 10000,) * 2)
                    os.write(ready_w, b"enter\n"); os.read(stop_r, 1)
                os.write(ready_w, b"exit\n"); os._exit(0)
            except BaseException: os._exit(1)
        try:
            self.assertTrue(select.select([ready_r], [], [], 5)[0])
            self.assertEqual(os.read(ready_r, 100), b"enter\n")
            before = (self.profiles.root / ".lock").stat()
            with self.assertRaises(bp.ProfileError) as caught:
                with self.profiles._locked(): self.fail("overlapping critical sections")
            self.assertEqual(caught.exception.code, "busy")
        finally:
            os.write(stop_w, b"x")
            _, status = os.waitpid(pid, 0)
            exited = os.read(ready_r, 100)
            for fd in (ready_r, ready_w, stop_r, stop_w): os.close(fd)
        self.assertEqual(status, 0); self.assertEqual(exited, b"exit\n")
        with self.profiles._locked():
            after = (self.profiles.root / ".lock").stat()
            self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))

    @unittest.skipUnless(hasattr(os, "fork"), "needs POSIX SIGKILL")
    def test_killed_holder_releases_without_age_wait(self):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                with self.profiles._locked():
                    os.write(w, b"held")
                    while True: signal.pause()
            except BaseException: os._exit(1)
        try:
            self.assertTrue(select.select([r], [], [], 5)[0]); self.assertEqual(os.read(r, 4), b"held")
            before = (self.profiles.root / ".lock").stat()
        finally:
            os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0); os.close(r); os.close(w)
        with self.profiles._locked():
            after = (self.profiles.root / ".lock").stat()
            self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))

    def test_lock_inode_survives_all_operations(self):
        a = self.profiles.prepare(self.owner)
        lock = self.profiles.root / ".lock"; before = lock.stat()
        if os.name == "nt":
            files_before = self.snapshot()
            self.error("unsupported_platform", self.profiles.retire, a.name, self.owner)
            self.assertEqual(self.profiles.prepare(self.owner), a)
            self.windows_batch_refusal(self.profiles.retire_all(), (a,))
            self.assertEqual(self.snapshot(), files_before)
        else:
            self.profiles.retire(a.name, self.owner)
            self.profiles.prepare(self.owner); self.profiles.retire_all()
        after = lock.stat()
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual(lock.read_bytes(), b"")

    @unittest.skipIf(os.name == "nt", "POSIX objects")
    def test_unsafe_lock_objects_refused_without_cleanup(self):
        for kind, code in (("symlink", "unsafe_link"), ("directory", "unsafe_type"), ("hardlink", "unsafe_hardlink"), ("mode", "unsafe_permissions")):
            with self.subTest(kind=kind):
                data = self.base / kind; data.mkdir(mode=0o700); profiles = bp.Profiles(data)
                p = profiles.prepare(self.owner); lock = profiles.root / ".lock"; lock.unlink()
                outside = data / "outside"; outside.write_bytes(b"untouched"); outside.chmod(0o600)
                if kind == "symlink": lock.symlink_to(outside)
                elif kind == "directory": lock.mkdir(mode=0o700)
                elif kind == "hardlink": os.link(outside, lock)
                else: lock.write_bytes(b"old"); lock.chmod(0o644)
                self.error(code, profiles.retire_all)
                self.assertTrue(p.exists()); self.assertEqual(outside.read_bytes(), b"untouched")
                self.assertTrue(lock.exists())

    @unittest.skipIf(os.name == "nt", "POSIX flock")
    def test_enolck_closes_descriptor_before_mutation(self):
        import fcntl
        p = self.profiles.prepare(self.owner); seen = []
        def unavailable(fd, flags):
            seen.append(fd); raise OSError(errno.ENOLCK, "no locks")
        with patch.object(fcntl, "flock", side_effect=unavailable), patch.object(self.profiles, "_cleanup") as cleanup:
            self.error("lock_unavailable", self.profiles.retire_all); cleanup.assert_not_called()
        self.assertTrue(p.exists()); self.assertEqual(len(seen), 1)
        with self.assertRaises(OSError): os.fstat(seen[0])

    def test_lock_descriptor_is_noninheritable(self):
        original = bp._lock_os; seen = []
        def inspect(fd, acquire):
            if acquire: seen.append(os.get_inheritable(fd))
            return original(fd, acquire)
        with patch.object(bp, "_lock_os", side_effect=inspect):
            with self.profiles._locked(): pass
        self.assertEqual(seen, [False])

    @unittest.skipIf(os.name == "nt", "POSIX inode validation")
    def test_post_open_inode_mismatch_closes_descriptor(self):
        self.profiles.prepare(self.owner)
        real_stat, real_open = Path.lstat, os.open
        count, opened = [], []
        def replaced(path):
            info = real_stat(path)
            if path.name == '.lock':
                count.append(1)
                if len(count) == 2:
                    values = list(info); values[1] += 1; return os.stat_result(values)
            return info
        def opened_fd(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if Path(path).name == '.lock': opened.append(fd)
            return fd
        with patch.object(Path, 'lstat', replaced), patch.object(bp.os, 'open', opened_fd), patch.object(self.profiles, '_cleanup') as cleanup:
            self.error('path_changed', self.profiles.retire_all); cleanup.assert_not_called()
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError): os.fstat(opened[0])

    @unittest.skipIf(os.name == "nt", "POSIX backend unavailable")
    def test_missing_lock_backend_refuses_without_cleanup(self):
        with patch.dict(sys.modules, {'fcntl': None}), patch.object(self.profiles, '_cleanup') as cleanup:
            self.error('lock_unavailable', self.profiles.prepare, self.owner)
            cleanup.assert_not_called()
        with self.profiles._locked(): pass

    def test_mock_windows_lock_api_and_busy(self):
        calls = []
        win = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=lambda fd, action, length: calls.append((action, length, os.lseek(fd, 0, os.SEEK_CUR))))
        with patch.object(bp, "_WINDOWS", True), patch.dict(sys.modules, {"msvcrt": win}):
            with self.profiles._locked(): pass
            self.assertEqual(calls, [(1, 1, 0), (2, 1, 0)])
            win.locking = Mock(side_effect=PermissionError(errno.EACCES, "busy"))
            with self.assertRaises(bp.ProfileError) as caught:
                with self.profiles._locked(): self.fail("busy lock entered")
            self.assertEqual(caught.exception.code, "busy")

    def test_mock_windows_busy_without_edeadlock_alias(self):
        codes = SimpleNamespace(EACCES=errno.EACCES, EDEADLK=errno.EDEADLK)
        self.assertFalse(hasattr(codes, "EDEADLOCK"))
        win = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2,
                              locking=Mock(side_effect=OSError(codes.EDEADLK, "busy")))
        with patch.object(bp, "_WINDOWS", True), patch.object(bp, "errno", codes), patch.dict(sys.modules, {"msvcrt": win}):
            with self.assertRaises(bp.ProfileError) as caught:
                with self.profiles._locked(): self.fail("busy lock entered")
            self.assertEqual(caught.exception.code, "busy")
        win.locking.assert_called_once()

    def test_mock_windows_retirement_refuses_without_mutation(self):
        p = self.profiles.prepare(self.owner)
        temp = self.profiles.root / (".tmp-" + "d" * 32); temp.mkdir(mode=0o700); os.utime(temp, (1, 1))
        retired = self.profiles.root / (".retired-" + "e" * 32); retired.mkdir(mode=0o700)
        before = {str(x.relative_to(self.profiles.root)): x.read_bytes() for x in self.profiles.root.rglob("*") if x.is_file()}
        with patch.object(bp, "_WINDOWS", True), patch.object(bp, "_os_user", return_value=self.owner.fields["os_user"]), patch.object(bp, "_lock_os"), patch.object(bp.os, "rename") as rename:
            self.error("unsupported_platform", self.profiles.retire, p.name, self.owner)
            for operation in (self.profiles.retire_all, lambda: self.profiles.retire_owner(self.owner)):
                result = operation(); self.assertFalse(result["complete"])
                self.assertEqual(result["retired"], []); self.assertEqual({v["reason"] for v in result["skipped"]}, {"unsupported_platform"})
            self.profiles.prepare(self.owner)
            rename.assert_not_called()
            with patch.object(Path, "iterdir", side_effect=AssertionError("must not enumerate")):
                self.error("unsupported_platform", bp._purge, p)
        self.assertTrue(temp.exists() and retired.exists() and p.exists())
        after = {str(x.relative_to(self.profiles.root)): x.read_bytes() for x in self.profiles.root.rglob("*") if x.is_file()}
        self.assertEqual(before, after)

    def test_mock_windows_empty_batch_is_incomplete(self):
        with patch.object(bp, '_WINDOWS', True), patch.object(bp, '_lock_os'):
            result = self.profiles.retire_all()
        self.assertEqual(result, {'retired': [], 'skipped': [], 'complete': False})

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX fork and pipe contention")
    def test_two_process_lock_has_exactly_one_winner(self):
        # The winner holds its lock until both results arrive; no network or multiprocessing server.
        start_r, start_w = os.pipe(); out_r, out_w = os.pipe(); done_r, done_w = os.pipe()
        pids = []
        try:
            for _ in range(2):
                pid = os.fork()
                if pid == 0:
                    try:
                        os.read(start_r, 1)
                        try:
                            with self.profiles._locked():
                                os.write(out_w, b"winner\n"); os.read(done_r, 1)
                        except bp.ProfileError as exc: os.write(out_w, (exc.code + "\n").encode())
                        os._exit(0)
                    except BaseException: os._exit(1)
                pids.append(pid)
            os.write(start_w, b"xx")
            raw = b""
            while raw.count(b"\n") < 2:
                self.assertTrue(select.select([out_r], [], [], 5)[0], "children completed")
                raw += os.read(out_r, 100)
            self.assertEqual(sorted(raw.splitlines()), [b"busy", b"winner"])
        finally:
            os.write(done_w, b"xx")
            for pid in pids:
                _, status = os.waitpid(pid, 0); self.assertEqual(status, 0)
            for fd in (start_r, start_w, out_r, out_w, done_r, done_w): os.close(fd)

    def test_traversal_retirement_refused(self):
        for name in ("../data", "..", "/tmp", "a" * 31, "A" * 32):
            if os.name == "nt":
                before = self.snapshot()
                self.error("unsupported_platform", self.profiles.retire, name, self.owner)
                self.assertEqual(self.snapshot(), before)
            else:
                self.error("profile_invalid", self.profiles.retire, name, self.owner)

    def test_temporary_home_unchanged(self):
        home = self.base / "home"; home.mkdir(); (home / "existing").write_text("unchanged")
        before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            self.profiles.prepare(self.owner); self.profiles.retire_all()
        after = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_only_the_workspace_launcher_imports_it(self):
        # W3 (docs/W3-THREAT-NOTE.md, T1): the launcher is the one production user; everything else stays out.
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob("*.py"):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts) or rel.parts[0] == "tests" or path.name in ("browser_profiles.py", "workspace_launcher.py"): continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import): self.assertFalse(any("browser_profiles" in n.name for n in node.names), str(rel))
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("browser_profiles", node.module or "", str(rel))
                    self.assertFalse(any(n.name == "browser_profiles" for n in node.names), str(rel))


if __name__ == "__main__":
    unittest.main()
