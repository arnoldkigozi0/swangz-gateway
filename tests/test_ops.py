"""Small-server operations: which build is running, the scheduled restore check, and audit coverage of admin actions."""
import ast
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from gateway import __version__, backup, build
from gateway.__main__ import run_backup
from gateway.db import DB, SCHEMA
from tests.support import Rig

ROOT = Path(__file__).resolve().parent.parent
SHA = "0123456789abcdef0123456789abcdef01234567"


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_is_empty_not_a_guess(self):
        self.assertEqual(build.commit(self.root, {}), "")

    def test_the_environment_wins_and_is_validated(self):
        (self.root / "COMMIT").write_text("f" * 40)
        self.assertEqual(build.commit(self.root, {"GATEWAY_COMMIT": SHA.upper()}), SHA[:12])
        for bad in ("main", "0123", "x" * 40, "0123456; rm", "<b>0123456</b>"):
            self.assertEqual(build.commit(self.root, {"GATEWAY_COMMIT": bad}), "f" * 12, bad)

    def test_the_commit_file_from_the_setup_script(self):
        (self.root / "COMMIT").write_text(SHA + "\n")
        self.assertEqual(build.commit(self.root, {}), SHA[:12])
        (self.root / "COMMIT").write_text("not a commit\n")
        self.assertEqual(build.commit(self.root, {}), "")

    def test_a_checkout_on_a_branch_detached_and_packed(self):
        git = self.root / ".git"
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "HEAD").write_text("ref: refs/heads/main\n")
        (git / "refs" / "heads" / "main").write_text(SHA + "\n")
        self.assertEqual(build.commit(self.root, {}), SHA[:12])
        (git / "refs" / "heads" / "main").unlink()
        (git / "packed-refs").write_text("# pack-refs with: peeled\n" + "a" * 40 + " refs/heads/other\n" + "b" * 40 + " refs/heads/main\n")
        self.assertEqual(build.commit(self.root, {}), "b" * 12)
        (git / "HEAD").write_text("c" * 40 + "\n")
        self.assertEqual(build.commit(self.root, {}), "c" * 12)
        (git / "HEAD").write_text("ref: refs/../../etc/passwd\n")
        self.assertEqual(build.commit(self.root, {}), "")

    def test_a_worktree_pointer(self):
        real = self.root / "repo.git"
        (real / "worktrees" / "wt").mkdir(parents=True)
        (real / "refs" / "heads").mkdir(parents=True)
        (real / "refs" / "heads" / "feature").write_text("d" * 40)
        (real / "worktrees" / "wt" / "HEAD").write_text("ref: refs/heads/feature\n")
        (real / "worktrees" / "wt" / "commondir").write_text("../..\n")
        tree = self.root / "tree"
        tree.mkdir()
        (tree / ".git").write_text(f"gitdir: {real / 'worktrees' / 'wt'}\n")
        self.assertEqual(build.commit(tree, {}), "d" * 12)

    def test_info_is_only_version_and_commit(self):
        self.assertEqual(set(build.info()), {"version", "commit"})
        self.assertEqual(build.info()["version"], __version__)


class RunningBuildTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_healthz_says_which_build_and_nothing_else(self):
        status, _, payload = self.rig.request("GET", "/healthz")
        body = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"ok", "uptime_seconds", "version", "commit"})
        self.assertEqual(body["version"], __version__)
        self.assertRegex(body["commit"], r"^([0-9a-f]{7,12})?$")

    def test_console_build_and_health_agree_and_need_a_console_session(self):
        status, body = self.rig.api("GET", "/build", who="viewer")
        self.assertEqual((status, set(body)), (200, {"version", "commit"}))
        _, health = self.rig.api("GET", "/health", who="viewer")
        self.assertEqual((health["version"], health["commit"]), (body["version"], body["commit"]))
        status, _, _ = self.rig.request("GET", "/admin/api/build", None, {"x-gateway-admin": "1"})
        self.assertEqual(status, 401)

    def test_refreshing_a_logo_is_audited(self):
        before = self.rig.gw.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'refreshed a tool logo'")
        status, _ = self.rig.api("POST", "/tools/chatgpt/logo/refresh")
        self.assertEqual(status, 200)
        row = self.rig.gw.db.one("SELECT * FROM audit WHERE action = 'refreshed a tool logo' ORDER BY id DESC LIMIT 1")
        self.assertEqual(self.rig.gw.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'refreshed a tool logo'"), before + 1)
        self.assertEqual((row["actor"], row["correlation"]), ("owner@swangzavenue.com", "tool:chatgpt"))


class RestoreCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "gateway.db"
        DB(str(self.db)).conn.close()
        self.out = self.dir / "backups"

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_newest_backup_restores(self):
        backup.take(self.db, self.out, now=time.time() - 7200)
        newest = backup.take(self.db, self.out)
        got = backup.check_latest(self.out)
        self.assertEqual((got["path"], got["schema"]), (newest["path"], len(SCHEMA)))
        self.assertGreater(got["tables"], 10)
        self.assertEqual([p.name for p in self.out.iterdir() if p.name.startswith(".")], [], "no scratch copy left")

    def test_fails_with_no_backup_a_stale_one_a_missing_checksum_or_damage(self):
        self.out.mkdir()
        with self.assertRaisesRegex(backup.BackupError, "no backup"):
            backup.check_latest(self.out)
        path = Path(backup.take(self.db, self.out)["path"])
        with self.assertRaisesRegex(backup.BackupError, "hours old"):
            backup.check_latest(self.out, 36, now=time.time() + 40 * 3600)
        self.assertTrue(backup.check_latest(self.out, 0, now=time.time() + 4000 * 3600))
        side = path.with_name(path.name + ".sha256")
        kept = side.read_text()
        side.unlink()
        with self.assertRaisesRegex(backup.BackupError, "sha256 file is missing"):
            backup.check_latest(self.out)
        side.write_text(kept)
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0xFF
        path.write_bytes(bytes(data))
        with self.assertRaises(backup.BackupError):
            backup.check_latest(self.out)
        self.assertEqual([p.name for p in self.out.iterdir() if p.name.startswith(".")], [])

    def test_a_valid_sqlite_file_that_is_not_a_gateway_database_fails(self):
        import sqlite3
        other = self.dir / "other.db"
        with sqlite3.connect(other) as c:
            c.execute("CREATE TABLE t(x)")
        backup.take(other, self.out)
        with self.assertRaisesRegex(backup.BackupError, "not a gateway database"):
            backup.check_latest(self.out)

    def test_command_line(self):
        settings = SimpleNamespace(db_path=str(self.db), data_dir=str(self.dir))
        args = SimpleNamespace(cmd="backup-verify", file=None, latest=True, dir=None, max_age_hours=36)
        with self.assertRaises(SystemExit) as failed:
            run_backup(args, settings, env={})
        self.assertIn("no backup", str(failed.exception))
        backup.take(self.db, self.out)
        mtime = os.path.getmtime(self.db)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(run_backup(args, settings, env={}), 0)
        self.assertIn("restore check ok", out.getvalue())
        self.assertEqual(os.path.getmtime(self.db), mtime, "the live database is never written")
        with self.assertRaises(SystemExit):
            run_backup(SimpleNamespace(cmd="backup-verify", file=None, latest=False), settings, env={})

    def test_the_timer_and_setup_script_wire_it(self):
        service = (ROOT / "deploy" / "swangz-gateway-backup-verify.service").read_text()
        timer = (ROOT / "deploy" / "swangz-gateway-backup-verify.timer").read_text()
        self.assertIn("ExecStart=/usr/bin/python3 -m gateway backup-verify --latest", service)
        self.assertIn("User=swangz", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("Persistent=true", timer)
        setup = (ROOT / "deploy" / "setup-gateway-server.sh").read_text()
        self.assertIn("swangz-gateway-backup-verify.timer", setup)
        self.assertIn('> "$APP/COMMIT"', setup)
        self.assertIn("backup-verify --latest", (ROOT / "docs" / "HUB-DELIVERY.md").read_text())


class AuditCoverageTests(unittest.TestCase):
    """Every console route that can change something (it names an area) writes an audit entry: either in its own
    body or through the one helper listed for it here. A new route with neither fails this test."""

    DELEGATES = {  # route function -> the function that audits for it
        ("business.py", "admin_amend"): "amend",
        ("business.py", "report_pricing"): "amend",
        ("hub_api.py", "admin_review"): "reporting.review",
    }

    def test_every_state_changing_console_route_audits(self):
        missing, seen = [], 0
        for path in sorted((ROOT / "gateway").glob("*.py")):
            src = path.read_text()
            helpers = {n.name: ast.get_source_segment(src, n) for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)}
            for fn in ast.walk(ast.parse(src)):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                for dec in fn.decorator_list:
                    if not (isinstance(dec, ast.Call) and "area" in {k.arg for k in dec.keywords}):
                        continue
                    if dec.args and getattr(dec.args[0], "value", "") == "GET":
                        continue
                    seen += 1
                    body = ast.get_source_segment(src, fn)
                    if "audit(" in body:
                        continue
                    helper = self.DELEGATES.get((path.name, fn.name))
                    if helper and helper.split(".")[-1] + "(" in body:
                        target = helpers.get(helper) if "." not in helper else (ROOT / "gateway" / "reporting.py").read_text()
                        if target and "audit(" in target:
                            continue
                    missing.append(f"{path.name}:{fn.name}")
        self.assertGreater(seen, 60, "the sweep found the console's routes")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
