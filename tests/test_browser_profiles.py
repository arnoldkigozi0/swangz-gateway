"""Port-free tests for inert profile preparation; never touch a real browser profile."""
import ast
import json
import os
import select
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
        self.error("marker_invalid", self.profiles.retire, b.name, self.owner)
        self.assertTrue(b.exists())

    def test_corrupt_marker_retirement_semantics(self):
        a = self.profiles.prepare(self.owner)
        (a / bp.MARKER).write_text("broken")
        self.error("marker_invalid", self.profiles.retire, a.name, self.owner)
        b = self.profiles.prepare(self.owner)
        self.assertNotEqual(a, b)
        result = self.profiles.retire_all()
        self.assertEqual(set(result["retired"]), {a.name, b.name})
        self.assertTrue(result["complete"])

    def test_owner_retirement_does_not_delete_others(self):
        a = self.profiles.prepare(self.owner)
        b = self.profiles.prepare(self.owner2())
        result = self.profiles.retire_owner(self.owner)
        self.assertEqual(result["retired"], [a.name]); self.assertTrue(b.exists())

    def test_unknown_entry_reported_but_safe_entry_retired(self):
        a = self.profiles.prepare(self.owner)
        unknown = a.parent / "keep-this"; unknown.mkdir(mode=0o700)
        result = self.profiles.retire_all()
        self.assertEqual(result["retired"], [a.name]); self.assertFalse(result["complete"])
        self.assertEqual(result["skipped"][0]["name"], "keep-this"); self.assertTrue(unknown.exists())

    def test_owner_marker_mutation_is_rejected(self):
        self.owner.fields["token"] = "never persist"
        self.error("owner_invalid", self.profiles.prepare, self.owner)
        self.assertFalse(self.profiles.root.exists())

    def test_marker_extra_secret_field_is_invalid(self):
        p = self.profiles.prepare(self.owner)
        marker = self.marker(p); marker["token"] = "not allowed"; self.write_marker(p, marker)
        self.error("marker_invalid", self.profiles.retire, p.name, self.owner)

    @unittest.skipIf(os.name == "nt", "POSIX modes")
    def test_root_preflight_blocks_all_cleanup(self):
        p = self.profiles.prepare(self.owner)
        self.profiles.root.chmod(0o755)
        self.error("unsafe_permissions", self.profiles.retire_all)
        self.assertTrue(p.exists())

    def test_absent_marker_device_wide_retirement(self):
        a = self.profiles.prepare(self.owner); (a / bp.MARKER).unlink()
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

    @unittest.skipIf(os.name == "nt", "symlink setup needs native Windows Actions")
    def test_symlinked_data_and_root_refused(self):
        alias = self.base / "alias"; alias.symlink_to(self.data, target_is_directory=True)
        self.error("unsafe_link", bp.Profiles(alias).prepare, self.owner)
        self.profiles.root.symlink_to(self.base, target_is_directory=True)
        self.error("unsafe_link", self.profiles.prepare, self.owner)

    @unittest.skipIf(os.name == "nt", "symlink setup needs native Windows Actions")
    def test_symlinked_ancestor_is_allowed(self):
        parent = self.base / "alias"; parent.symlink_to(self.base, target_is_directory=True)
        p = bp.Profiles(parent / "data").prepare(self.owner)
        self.assertTrue(p.exists())

    @unittest.skipIf(os.name == "nt", "symlink setup needs native Windows Actions")
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
        self.profiles.prepare(self.owner)
        self.assertFalse((self.profiles.root / (".tmp-" + "0" * 32)).exists())
        self.assertFalse((self.profiles.root / (".tmp-" + "1" * 32)).exists())
        self.assertTrue((self.profiles.root / (".tmp-" + "2" * 32)).exists())

    def test_crash_before_publish_discards_stage_after_stale_limit(self):
        with patch.object(bp.os, "rename", side_effect=OSError("crash before publish")):
            with self.assertRaises(OSError): self.profiles.prepare(self.owner)
        stage, = self.profiles.root.glob(".tmp-*")
        self.assertTrue((stage / bp.MARKER).exists())
        os.utime(stage, (time.time() - 200,) * 2)
        p = self.profiles.prepare(self.owner)
        self.assertFalse(stage.exists()); self.assertTrue(p.exists())

    def test_retired_recovery(self):
        a = self.profiles.prepare(self.owner)
        retired = a.parent / (".retired-" + "e" * 32); a.rename(retired)
        self.profiles.prepare(self.owner); self.assertFalse(retired.exists())

    def test_lock_busy_stale_and_release_only_own(self):
        with self.profiles._locked():
            self.error("busy", self.profiles.prepare, self.owner)
        lock = self.profiles.root / ".lock"; lock.write_text("incomplete"); lock.chmod(0o600)
        os.utime(lock, (time.time() - 200,) * 2)
        self.profiles.prepare(self.owner); self.assertFalse(lock.exists())
        with self.profiles._locked(): lock.write_text("replacement")
        self.assertEqual(lock.read_text(), "replacement")

    @unittest.skipUnless(hasattr(os, "fork"), "native Windows locking requires Actions")
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
            self.error("profile_invalid", self.profiles.retire, name, self.owner)

    def test_temporary_home_unchanged(self):
        home = self.base / "home"; home.mkdir(); (home / "existing").write_text("unchanged")
        before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            self.profiles.prepare(self.owner); self.profiles.retire_all()
        after = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_no_production_imports(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob("*.py"):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts) or rel.parts[0] == "tests" or path.name == "browser_profiles.py": continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import): self.assertFalse(any("browser_profiles" in n.name for n in node.names), str(rel))
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("browser_profiles", node.module or "", str(rel))
                    self.assertFalse(any(n.name == "browser_profiles" for n in node.names), str(rel))


if __name__ == "__main__":
    unittest.main()
