"""Verified, compressed copies of the database, kept on the server and optionally sent off it.

    python3 -m gateway backup [--dir DIR] [--keep N] [--no-remote]

Each run takes a consistent copy with SQLite's backup API (safe while the gateway is running; a plain
`cp` of a live WAL database is not), checks its integrity, compresses it to
`gateway-YYYYmmdd-HHMMSS.db.gz` with a `.sha256` beside it (mode 0600), and keeps the newest `--keep`.

With GATEWAY_BACKUP_REMOTE set (an rsync destination such as
`u123456@u123456.your-storagebox.de:swangz/`), the new copy is also sent there with rsync over SSH. Only
the new file is sent and nothing is ever deleted remotely, so a compromised or broken server cannot erase
the off-server history. A failed copy fails the command, so systemd shows the backup as failed.

It opens the database read-only and never through `DB`, so it never runs a migration.
"""

import gzip
import hashlib
import os
import shlex
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path

PREFIX = "gateway-"
SUFFIX = ".db.gz"


class BackupError(RuntimeError):
    pass


def take(db_path, out_dir, keep=14, now=None):
    """-> {"path", "sha256", "bytes", "removed": [...]}. Raises BackupError if the copy is not sound."""
    src = Path(db_path)
    if not src.is_file():
        raise BackupError(f"no database at {src}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now if now is not None else time.time()))
    final = out / f"{PREFIX}{stamp}{SUFFIX}"
    if final.exists():
        raise BackupError(f"{final} already exists")
    raw = out / f".{PREFIX}{stamp}.db.partial"
    packed = out / f".{PREFIX}{stamp}{SUFFIX}.partial"
    try:
        fd = os.open(raw, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True)) as s, \
                closing(sqlite3.connect(raw)) as d:
            s.backup(d)
            d.execute("PRAGMA journal_mode=DELETE")  # one self-contained file, no -wal/-shm beside a restore
            result = d.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise BackupError(f"integrity check failed: {result}")
        fd = os.open(packed, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with open(raw, "rb") as f_in, os.fdopen(fd, "wb") as f_out, gzip.GzipFile(fileobj=f_out, mode="wb", mtime=0) as z:
            shutil.copyfileobj(f_in, z, 1 << 20)
        digest = _sha256(packed)
        os.replace(packed, final)
        side = final.with_name(final.name + ".sha256")
        fd = os.open(side, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"{digest}  {final.name}\n")
    finally:
        for p in (raw, packed, raw.with_name(raw.name + "-journal")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    return {"path": str(final), "sha256": digest, "bytes": final.stat().st_size, "removed": prune(out, keep)}


def prune(out_dir, keep):
    """Keep the newest `keep` backups (and their .sha256); -> the names removed. keep <= 0 keeps all."""
    if keep <= 0:
        return []
    found = sorted(p for p in Path(out_dir).glob(f"{PREFIX}*{SUFFIX}") if p.is_file())
    removed = []
    for p in found[:-keep]:
        p.unlink()
        side = p.with_name(p.name + ".sha256")
        if side.exists():
            side.unlink()
        removed.append(p.name)
    return removed


def send(path, remote, ssh="", run=subprocess.run):
    """rsync one backup (and its .sha256) to `remote`. Never deletes anything there."""
    files = [str(path), str(path) + ".sha256"]
    cmd = ["rsync", "--times", "--chmod=F600", "--partial"]
    if ssh:
        cmd += ["-e", ssh]
    cmd += [*files, remote]
    p = run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise BackupError(f"off-server copy failed (rsync exit {p.returncode}): {(p.stderr or '').strip()[:500]}")
    return cmd


def default_ssh(data_dir, port=""):
    """The ssh command rsync uses: a key and known_hosts kept in the data folder, the only place the
    service may write (ProtectSystem=strict)."""
    ssh_dir = Path(data_dir).resolve() / ".ssh"
    parts = ["ssh", "-i", str(ssh_dir / "backup_key"), "-o", f"UserKnownHostsFile={ssh_dir / 'known_hosts'}",
             "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes"]
    if port:
        parts += ["-p", str(int(port))]
    return shlex.join(parts)


def verify(path):
    """Re-read a backup: checksum matches its .sha256 and the database inside passes integrity_check."""
    path = Path(path)
    side = path.with_name(path.name + ".sha256")
    if side.exists() and side.read_text().split()[0] != _sha256(path):
        raise BackupError(f"{path.name}: checksum does not match")
    tmp = path.with_name("." + path.name + ".verify")
    try:
        with gzip.open(path, "rb") as f_in, open(tmp, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out, 1 << 20)
        with closing(sqlite3.connect(tmp.resolve().as_uri() + "?mode=ro", uri=True)) as c:
            result = c.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise BackupError(f"{path.name}: integrity check failed: {result}")
    finally:
        for p in (tmp, tmp.with_name(tmp.name + "-wal"), tmp.with_name(tmp.name + "-shm")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    return True


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
