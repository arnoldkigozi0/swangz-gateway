"""Production hosting pieces: the database backup, the sized workspace config, and the deploy files."""

import gzip
import io
import json
import os
import re
import shlex
import sqlite3
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from gateway import backup
from gateway.__main__ import run_backup
from gateway.db import DB
from workspace_agent.agent import check_config

ROOT = Path(__file__).resolve().parent.parent


def fill(db_path):
    db = DB(str(db_path))
    db.x("INSERT INTO audit(ts, actor, action, target, detail, ip) VALUES(1, 'test', 'something', '', '', '')")
    db.conn.close()


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "gateway.db"
        fill(self.db)
        self.out = self.dir / "backups"

    def tearDown(self):
        self.tmp.cleanup()

    def test_takes_a_verified_private_compressed_copy(self):
        r = backup.take(self.db, self.out, keep=5, now=1_800_000_000)
        path = Path(r["path"])
        self.assertTrue(path.name.startswith("gateway-") and path.name.endswith(".db.gz"))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        side = path.with_name(path.name + ".sha256").read_text()
        self.assertEqual(side.split(), [r["sha256"], path.name])
        self.assertTrue(backup.verify(path))
        restored = self.dir / "restored.db"
        restored.write_bytes(gzip.decompress(path.read_bytes()))
        with sqlite3.connect(restored) as c:
            self.assertEqual(c.execute("SELECT action FROM audit WHERE actor='test'").fetchone()[0], "something")
        self.assertEqual([p.name for p in self.out.iterdir() if p.name.startswith(".")], [], "no partial files left")

    def test_works_while_the_gateway_holds_the_database_open(self):
        live = DB(str(self.db))
        live.x("INSERT INTO audit(ts, actor, action, target, detail, ip) VALUES(2, 'live', 'during', '', '', '')")
        try:
            path = backup.take(self.db, self.out, now=1_800_000_000)["path"]
        finally:
            live.conn.close()
        restored = self.dir / "r.db"
        restored.write_bytes(gzip.decompress(Path(path).read_bytes()))
        with sqlite3.connect(restored) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit WHERE actor='live'").fetchone()[0], 1)

    def test_keeps_only_the_newest(self):
        for i in range(5):
            backup.take(self.db, self.out, keep=3, now=1_800_000_000 + i * 86400)
        kept = sorted(p.name for p in self.out.glob("gateway-*.db.gz"))
        self.assertEqual(len(kept), 3)
        self.assertEqual(len(list(self.out.glob("*.sha256"))), 3)
        self.assertIn("gateway-20270119-", kept[-1])  # the newest survives
        self.assertIn("gateway-20270117-", kept[0])

    def test_never_overwrites_and_refuses_a_missing_database(self):
        backup.take(self.db, self.out, now=1_800_000_000)
        with self.assertRaises(backup.BackupError):
            backup.take(self.db, self.out, now=1_800_000_000)
        with self.assertRaises(backup.BackupError):
            backup.take(self.dir / "nope.db", self.out)

    def test_verify_catches_a_damaged_copy(self):
        path = Path(backup.take(self.db, self.out, now=1_800_000_000)["path"])
        data = bytearray(path.read_bytes())
        data[-20] ^= 0xFF
        path.write_bytes(bytes(data))
        with self.assertRaises(backup.BackupError):
            backup.verify(path)

    def test_does_not_migrate_an_older_database(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE meta SET v='5' WHERE k='schema'")
        path = backup.take(self.db, self.out, now=1_800_000_000)["path"]
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT v FROM meta WHERE k='schema'").fetchone()[0], "5")
        self.assertTrue(backup.verify(path))

    def test_send_copies_only_the_new_file_and_never_deletes(self):
        path = backup.take(self.db, self.out, now=1_800_000_000)["path"]
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stderr="")

        backup.send(path, "u1@box.example:swangz/", "ssh -p 23", run=run)
        cmd = calls[0]
        self.assertEqual(cmd[0], "rsync")
        self.assertFalse([a for a in cmd if "delete" in a or a.startswith("--remove")])
        self.assertEqual(cmd[-3:], [path, path + ".sha256", "u1@box.example:swangz/"])
        self.assertIn("ssh -p 23", cmd)

        def failing(cmd, **kw):
            return SimpleNamespace(returncode=12, stderr="connection refused")

        with self.assertRaisesRegex(backup.BackupError, "connection refused"):
            backup.send(path, "u1@box.example:swangz/", run=failing)

    def test_default_ssh_keeps_its_files_in_the_writable_data_folder(self):
        parts = shlex.split(backup.default_ssh(self.dir, "23"))
        self.assertIn(str(self.dir.resolve() / ".ssh" / "backup_key"), parts)
        self.assertIn(f"UserKnownHostsFile={self.dir.resolve() / '.ssh' / 'known_hosts'}", parts)
        self.assertIn("BatchMode=yes", parts)
        self.assertEqual(parts[-2:], ["-p", "23"])

    def test_command_line(self):
        settings = SimpleNamespace(data_dir=str(self.dir), db_path=str(self.db))
        args = SimpleNamespace(cmd="backup", dir=None, keep=None, no_remote=False)
        out = io.StringIO()
        with redirect_stdout(out):
            run_backup(args, settings, env={"GATEWAY_BACKUP_KEEP": "2"})
        self.assertIn("integrity ok", out.getvalue())
        self.assertIn("lives only on this server", out.getvalue())
        made = list(self.out.glob("gateway-*.db.gz"))
        self.assertEqual(len(made), 1)
        with redirect_stdout(io.StringIO()):
            run_backup(SimpleNamespace(cmd="backup-verify", file=str(made[0])), settings, env={})
        with self.assertRaises(SystemExit):
            run_backup(SimpleNamespace(cmd="backup", dir=None, keep=None, no_remote=False),
                       SimpleNamespace(data_dir=str(self.dir), db_path=str(self.dir / "missing.db")), env={})


class SizedWorkspaceConfigTests(unittest.TestCase):
    def test_ten_browser_example_is_valid_and_sized(self):
        raw = json.loads((ROOT / "workspace_agent" / "agent.10-browsers.example.json").read_text())
        raw.update(token="x" * 64, public_ip="203.0.113.7")
        cfg = check_config(raw)
        self.assertEqual(cfg["max_running"], 10)
        self.assertEqual(len(cfg["browsers"]), 10)
        self.assertEqual(sorted(b["n"] for b in cfg["browsers"].values()), list(range(1, 11)))
        self.assertEqual(cfg["screen"], "1280x720@25")

    def test_its_tools_are_real_catalogue_ids(self):
        from gateway import catalog

        raw = json.loads((ROOT / "workspace_agent" / "agent.10-browsers.example.json").read_text())
        text = (ROOT / "gateway" / "catalog.py").read_text()
        for tool in raw["tools"]:
            self.assertIn(f'["{tool}", ', text, tool)
        self.assertTrue(catalog)


class DeployFileTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        for name in ("setup-gateway-server.sh", "setup-workspace-server.sh", "firewall.sh", "laptop-demo.sh"):
            p = subprocess.run(["bash", "-n", str(ROOT / "deploy" / name)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"{name}: {p.stderr}")

    def test_documents_the_setup_script_points_to_exist(self):
        for name in ("setup-gateway-server.sh", "setup-workspace-server.sh"):
            text = (ROOT / "deploy" / name).read_text()
            for ref in set(re.findall(r"((?:docs|deploy|workspace_agent)/[\w./-]+\.(?:md|json|sh|service|timer))", text)):
                self.assertTrue((ROOT / ref).exists(), f"{name} mentions {ref}, which does not exist")

    def test_caddy_sends_hsts_and_streams(self):
        text = (ROOT / "deploy" / "Caddyfile").read_text()
        self.assertIn('Strict-Transport-Security "max-age=31536000"', text)
        self.assertIn("flush_interval -1", text)

    def test_backup_timer_runs_the_backup_as_the_gateway_user(self):
        service = (ROOT / "deploy" / "swangz-gateway-backup.service").read_text()
        timer = (ROOT / "deploy" / "swangz-gateway-backup.timer").read_text()
        self.assertIn("ExecStart=/usr/bin/python3 -m gateway backup", service)
        self.assertIn("User=swangz", service)
        self.assertIn("ReadWritePaths=/opt/swangz-gateway/data", service)
        self.assertIn("Persistent=true", timer)
        setup = (ROOT / "deploy" / "setup-gateway-server.sh").read_text()
        self.assertIn("swangz-gateway-backup.timer", setup)
        self.assertIn("open_firewall", setup)

    def test_firewall_keeps_ssh_open_on_its_real_port(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log"
            for cmd in ("apt-get", "ufw"):
                f = Path(d) / cmd
                f.write_text(f'#!/bin/sh\necho "{cmd} $*" >> "{log}"\n')
                f.chmod(0o755)
            sshd = Path(d) / "sshd"
            sshd.write_text("#!/bin/sh\necho 'port 2222'\n")
            sshd.chmod(0o755)
            env = {**os.environ, "PATH": f"{d}:{os.environ['PATH']}"}
            script = f'set -euo pipefail; . "{ROOT / "deploy" / "firewall.sh"}"; open_firewall 80/tcp 443/tcp 59101/udp'
            p = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            lines = log.read_text().splitlines()
            self.assertIn("ufw allow 2222/tcp comment ssh", lines)
            self.assertIn("ufw allow 59101/udp", lines)
            self.assertLess(lines.index("ufw allow 2222/tcp comment ssh"), lines.index("ufw --force enable"))
            log.unlink()
            p = subprocess.run(["bash", "-c", script], env={**env, "SKIP_FIREWALL": "1"}, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
