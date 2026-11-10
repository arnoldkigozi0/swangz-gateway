"""Signed client releases: the gateway is a distribution point, never a source of trust.

It may withhold an update; it can never forge one. A release is made and signed offline (the private key is
never on this machine) and published from the command line, where it is checked against the public keys
pinned in swangz_client/release_keys.py before a single byte is stored. The device then re-verifies
everything itself, so a damaged or hostile server can only make an update fail to arrive.

    data/releases/<channel>/<version>/   release.json, release.json.sig and the listed artifacts (0700/0600)
    data/releases/<channel>/current.json {"version": "x.y.z"} — replaced atomically; deleting it withdraws

Served to an enrolled device (its own key, nothing else) at /api/device/releases/<channel>/<file>, byte for
byte, never edited, re-encoded, compressed, ranged or redirected. `pilot` is only for people on the pilot list.
"""

import contextlib
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import threading
import time

from . import __version__, security
from .admin import ApiError
from .staff import Streamed, route

try:
    import fcntl
except ImportError:  # not POSIX; the gateway runs on Linux, publishing is a single operator anyway
    fcntl = None

CHANNELS = ("stable", "pilot")
MAX_MANIFEST = 64 * 1024
SIG_BYTES = 512
MAX_ARTIFACT = 150 * 1024 * 1024
BLOCK = 64 * 1024
MIN_FREE = 1024 * 1024 * 1024  # publishing leaves at least this much free on top of what it writes
KEEP = 2  # the current release and one previous
DOWNLOAD_LIMIT, DOWNLOAD_WINDOW = 3, 3600  # artifact downloads per device per hour
VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SHA256 = re.compile(r"[0-9a-f]{64}")
RESERVED = {"release.json", "release.json.sig", "release.json.sig.hex", "current.json"}
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", *["COM" + str(i) for i in range(1, 10)], *["LPT" + str(i) for i in range(1, 10)]}
GONE = "No release is available."


class ReleaseError(ValueError):
    """A publish/withdraw/pilot command was refused; the message says why."""


class _Missing(Exception):
    pass


def check_gateway_version():
    """The version the gateway tells devices it is (X-Swangz-Gateway-Version) must be strict x.y.z."""
    if not isinstance(__version__, str) or not VERSION.fullmatch(__version__):
        raise RuntimeError(f"gateway.__version__ must be x.y.z, not {__version__!r}")


def valid_name(name):
    """The same filename rule swangz_client.updater applies to an artifact, plus the names this store owns."""
    if not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name or name.endswith("."):
        return False
    return name.split(".")[0].upper() not in WINDOWS_DEVICES and name not in RESERVED


def _tuple(version):
    return tuple(int(x) for x in version.split("."))


def root(data_dir):
    return os.path.join(os.path.abspath(data_dir), "releases")


def _fsync_dir(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


# ---------------------------------------------------------------- reading what is stored (serving)


def _open_in(data_dir, channel, version, name):
    """Open one stored file for reading, or raise _Missing. Never follows a link: every folder on the way is
    lstat-ed, the file is opened O_NOFOLLOW and must be a regular file with one name, and the resolved path
    must be exactly where it should be inside the channel folder."""
    base = root(data_dir)
    dirs = [base, os.path.join(base, channel)]
    if version:
        dirs.append(os.path.join(dirs[1], version))
    path = os.path.join(dirs[-1], name)
    try:
        for d in dirs:
            if not stat.S_ISDIR(os.lstat(d).st_mode):
                raise _Missing()
        want = os.path.join(os.path.realpath(dirs[1]), *([version] if version else []), name)
        if os.path.realpath(path) != want:
            raise _Missing()
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        raise _Missing() from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise _Missing()
    except BaseException:
        os.close(fd)
        raise
    return fd, st


def _read_stored(data_dir, channel, version, name, limit):
    fd, st = _open_in(data_dir, channel, version, name)
    with os.fdopen(fd, "rb") as f:
        if st.st_size > limit:
            raise _Missing()
        data = f.read(limit + 1)
    if len(data) > limit:
        raise _Missing()
    return data


def current(data_dir, channel):
    """The version a channel serves now, or None (no release, withdrawn, or an unreadable pointer)."""
    try:
        value = json.loads(_read_stored(data_dir, channel, None, "current.json", 1024))
        version = value.get("version") if isinstance(value, dict) else None
    except (_Missing, ValueError, UnicodeError):
        return None
    return version if isinstance(version, str) and VERSION.fullmatch(version) else None


def _versions(data_dir, channel):
    try:
        names = os.listdir(os.path.join(root(data_dir), channel))
    except OSError:
        return []
    return sorted((n for n in names if VERSION.fullmatch(n)), key=_tuple, reverse=True)


def pilot_list(db):
    try:
        value = json.loads(db.get_setting("release_pilot", "[]") or "[]")
    except ValueError:
        return []
    return sorted({x for x in value if type(x) is int}) if isinstance(value, list) else []


def channel_for(db, person_id):
    return "pilot" if person_id in pilot_list(db) else "stable"


def latest_hint(gw, person, fallback):
    """client.latest in the manifest and heartbeat: what this person's channel serves now. A hint only —
    the device trusts nothing it has not verified itself."""
    try:
        return current(gw.settings.data_dir, channel_for(gw.db, person["id"])) or fallback
    except Exception:
        return fallback


# ---------------------------------------------------------------- the device routes


def _limiter(gw):
    with _lock:
        if getattr(gw, "release_limiter", None) is None:
            gw.release_limiter = security.LoginThrottle(limit=DOWNLOAD_LIMIT, window=DOWNLOAD_WINDOW)
        return gw.release_limiter


_lock = threading.Lock()


def _download_record(ctx, person, device, channel, version, name, outcome):
    """One access-level record per artifact download: who, which device, which release and file, how it ended.
    Never the key, never file contents; polling the manifest records nothing."""
    ctx.gw.audit(person["name"], "downloaded a release file", f"{channel} {version}", f"{name}; device {device['key_id']}",
                 ctx.ip, outcome=outcome, correlation=f"release:{channel}:{version}")


@route("GET", r"/device/releases/(?P<channel>stable|pilot)/(?P<name>[^/]{1,200})", signed_in=False)
def device_release(ctx, channel, name):
    from .enroll import device_auth

    person, device = device_auth(ctx)  # unchanged: unknown/revoked/paused/ended/not-enrolled are refused here
    db, data_dir = ctx.db, ctx.gw.settings.data_dir
    if channel == "pilot" and person["id"] not in pilot_list(db):
        raise ApiError(404, GONE)
    version = current(data_dir, channel)
    if not version:
        raise ApiError(404, GONE)
    plain = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    try:
        if name == "release.json":
            raw = _read_stored(data_dir, channel, version, "release.json", MAX_MANIFEST)
            return raw, "application/json", {**plain, "X-Swangz-Gateway-Version": __version__}
        if name == "release.json.sig":
            sig = _read_stored(data_dir, channel, version, "release.json.sig", SIG_BYTES)
            if len(sig) != SIG_BYTES:
                raise _Missing()
            return sig, "application/octet-stream", plain
        if not valid_name(name):
            raise ApiError(404, GONE)
        listed = _listed(_read_stored(data_dir, channel, version, "release.json", MAX_MANIFEST))
    except _Missing:
        raise ApiError(404, GONE) from None
    if name not in listed:
        raise ApiError(404, GONE)
    limiter = _limiter(ctx.gw)
    if limiter.blocked("reldl:" + device["key_id"]):
        _download_record(ctx, person, device, channel, version, name, "denied")
        raise ApiError(429, "Too many downloads from this device. Try again later.", "slow_down")
    try:
        fd, st = _open_in(data_dir, channel, version, name)
    except _Missing:
        _download_record(ctx, person, device, channel, version, name, "failed")
        raise ApiError(404, GONE) from None
    if st.st_size != listed[name]:
        os.close(fd)
        _download_record(ctx, person, device, channel, version, name, "failed")
        ctx.gw.log(f"release {channel} {version}: {name} on disk does not match its listed size")
        raise ApiError(500, "That file is damaged on the server. Tell your admin.")
    limiter.fail("reldl:" + device["key_id"])  # counts this download against the device's hourly allowance
    sent = _stream(ctx.h, fd, st.st_size)
    _download_record(ctx, person, device, channel, version, name, "ok" if sent else "interrupted")
    return Streamed()


def _listed(raw):
    """{file: size} from the current release.json — parsed only to look a name up."""
    try:
        artifacts = json.loads(raw).get("artifacts")
    except (ValueError, UnicodeError, AttributeError):
        raise _Missing() from None
    out = {}
    for item in artifacts if isinstance(artifacts, list) else []:
        if isinstance(item, dict) and isinstance(item.get("file"), str) and type(item.get("size")) is int:
            out[item["file"]] = item["size"]
    return out


def _stream(h, fd, size):
    """Send the file in 64 KiB blocks (never reading it whole). True when every byte went out."""
    headers = {"Content-Type": "application/octet-stream", "Content-Length": str(size), "Cache-Control": "no-store",
              "X-Content-Type-Options": "nosniff", **getattr(h, "_cors", {})}
    sent = 0
    try:
        h.send_response(200)
        for k, v in headers.items():
            h.send_header(k, v)
        h.end_headers()
        while sent < size:
            block = os.read(fd, min(BLOCK, size - sent))
            if not block:
                break
            h.wfile.write(block)
            sent += len(block)
    except OSError:  # the device went away mid-download
        pass
    finally:
        os.close(fd)
    if sent != size:
        h.close_connection = True  # a short body must not be mistaken for the start of the next response
    return sent == size


# ---------------------------------------------------------------- publishing (command line only)


def _audit(db, action, target, detail, before, after, correlation):
    def js(v):
        return None if v is None else json.dumps(v, default=str, sort_keys=True)[:8000]
    db.x("INSERT INTO audit(ts, actor, action, target, detail, ip, reason, before_json, after_json, outcome, correlation, area)"
         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
         (time.time(), "command line", action, target, detail[:2000], "", "", js(before), js(after), "ok", correlation, ""))


@contextlib.contextmanager
def _locked(base):
    os.makedirs(base, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(base, ".lock"), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if fcntl:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ReleaseError("another release command is running") from None
        yield
    finally:
        os.close(fd)


def _source(directory, name, limit):
    """A file from the folder being published: a regular file, not a link, no larger than the limit."""
    path = os.path.join(directory, name)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise ReleaseError(f"{name} is missing or is a link" if exc.errno in (errno.ENOENT, errno.ELOOP) else f"{name}: {exc.strerror}") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ReleaseError(f"{name} is not a regular file")
        if st.st_size > limit:
            raise ReleaseError(f"{name} is larger than {limit} bytes")
    except BaseException:
        os.close(fd)
        raise
    return fd, st


def _write_new(path, fd_in, expect=None):
    """Copy 64 KiB at a time into a new 0600 file. -> (size, sha256 hex). Refuses a source that is not `expect` bytes."""
    digest, total = hashlib.sha256(), 0
    out = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(out, "wb") as f:
            while True:
                block = os.read(fd_in, BLOCK)
                if not block:
                    break
                total += len(block)
                if expect is not None and total > expect:
                    raise ReleaseError("a file is larger than the size the signed manifest lists")
                digest.update(block)
                f.write(block)
            f.flush()
            os.fsync(f.fileno())
    finally:
        os.close(fd_in)
    return total, digest.hexdigest()


def _check_manifest(manifest, signer, channel):
    from swangz_client import updater

    if type(manifest.get("schema")) is not int or manifest["schema"] != 1 or manifest.get("key_id") != signer:
        raise ReleaseError("the manifest's schema or key id is wrong")
    if manifest.get("channel") != channel:
        raise ReleaseError(f"the manifest is for channel {manifest.get('channel')!r}, not {channel!r}")
    try:
        updater.version(manifest.get("version"))
    except updater.UpdateError:
        raise ReleaseError("the manifest's version must be x.y.z") from None
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts or not all(isinstance(a, dict) for a in artifacts):
        raise ReleaseError("the manifest lists no artifacts")
    seen = set()
    for a in artifacts:
        name = a.get("file")
        if not valid_name(name):
            raise ReleaseError(f"unsafe or reserved artifact name {name!r}")
        if name in seen:
            raise ReleaseError(f"{name} is listed twice")
        seen.add(name)
        if type(a.get("size")) is not int or not 0 < a["size"] <= MAX_ARTIFACT:
            raise ReleaseError(f"{name}: the size must be 1 to {MAX_ARTIFACT} bytes")
        if not isinstance(a.get("sha256"), str) or not SHA256.fullmatch(a["sha256"]):
            raise ReleaseError(f"{name}: the sha256 must be 64 lowercase hex digits")
    return manifest["version"], artifacts


def _remove(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def publish(db, data_dir, directory, channel):
    """Check a signed release folder and make it the channel's current release. Raises ReleaseError."""
    from swangz_client import release_keys, updater

    if channel not in CHANNELS:
        raise ReleaseError("the channel is stable or pilot")
    if not release_keys.KEYS:
        raise ReleaseError("no release key is pinned in swangz_client/release_keys.py, so nothing can be verified")
    if not os.path.isdir(directory):
        raise ReleaseError("that is not a folder")
    fd, _ = _source(directory, "release.json", MAX_MANIFEST)
    with os.fdopen(fd, "rb") as f:
        raw = f.read(MAX_MANIFEST + 1)
    fd, _ = _source(directory, "release.json.sig", SIG_BYTES)
    with os.fdopen(fd, "rb") as f:
        signature = f.read(SIG_BYTES + 1)
    if not raw or len(signature) != SIG_BYTES:
        raise ReleaseError(f"release.json must not be empty and release.json.sig must be exactly {SIG_BYTES} bytes")
    try:
        signer = updater.verify(raw, signature, release_keys.KEYS)
        manifest = updater.decode(raw)
    except updater.UpdateError as exc:
        raise ReleaseError(str(exc)) from None
    version, artifacts = _check_manifest(manifest, signer, channel)

    base, chan = root(data_dir), os.path.join(root(data_dir), channel)
    with _locked(base):
        os.makedirs(chan, mode=0o700, exist_ok=True)
        for d in (base, chan):
            if os.path.islink(d) or not os.path.isdir(d):
                raise ReleaseError("the release folder is a link")
            os.chmod(d, 0o700)
        for leftover in os.listdir(chan):  # a publish that died halfway
            if leftover.startswith(".tmp-") or leftover.startswith("current.json.tmp-"):
                _remove(os.path.join(chan, leftover))
        before = current(data_dir, channel)
        known = _versions(data_dir, channel)
        if version in known:
            raise ReleaseError(f"{channel} {version} already exists; a release is never overwritten — publish a higher version")
        floor = max([_tuple(v) for v in known] + ([_tuple(before)] if before else []), default=None)
        if floor is not None and _tuple(version) <= floor:
            raise ReleaseError(f"{version} is not higher than {'.'.join(map(str, floor))}; a rollback is a new, higher, signed version")
        need = sum(a["size"] for a in artifacts) + len(raw) + SIG_BYTES + MIN_FREE
        if shutil.disk_usage(base).free < need:
            raise ReleaseError("not enough free disk space to publish safely")

        tmp = os.path.join(chan, ".tmp-" + secrets.token_hex(8))
        final = os.path.join(chan, version)
        os.mkdir(tmp, 0o700)
        try:
            for name, data in (("release.json", raw), ("release.json.sig", signature)):
                out = os.open(os.path.join(tmp, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(out, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
            for a in artifacts:  # only the listed files are copied; anything else in the folder is ignored
                src, st = _source(directory, a["file"], MAX_ARTIFACT)
                if st.st_size != a["size"]:
                    os.close(src)
                    raise ReleaseError(f"{a['file']}: the file is {st.st_size} bytes but the manifest says {a['size']}")
                size, sha = _write_new(os.path.join(tmp, a["file"]), src, a["size"])
                if size != a["size"] or not hmac.compare_digest(sha, a["sha256"]):
                    raise ReleaseError(f"{a['file']}: the size or SHA-256 does not match the signed manifest")
            _fsync_dir(tmp)
            os.rename(tmp, final)
            _fsync_dir(chan)
        except BaseException:
            _remove(tmp)
            raise
        pointer = os.path.join(chan, "current.json.tmp-" + secrets.token_hex(8))
        try:
            out = os.open(pointer, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(out, "wb") as f:
                f.write(json.dumps({"version": version}, sort_keys=True).encode())
                f.flush()
                os.fsync(f.fileno())
            os.replace(pointer, os.path.join(chan, "current.json"))  # the one atomic step that makes it live
            _fsync_dir(chan)
        except BaseException:
            _remove(pointer)
            _remove(final)  # not live, so nothing refers to it; the previous release stays current
            raise
        for old in _versions(data_dir, channel)[KEEP:]:
            _remove(os.path.join(chan, old))
    after = {"current": version, "key_id": signer, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
             "artifacts": [{"file": a["file"], "size": a["size"], "sha256": a["sha256"]} for a in artifacts]}
    _audit(db, "published a release", f"{channel} {version}", f"key {signer}; {len(artifacts)} file(s)",
           {"current": before}, after, f"release:{channel}:{version}")
    return {"channel": channel, "version": version, "previous": before, "files": [a["file"] for a in artifacts]}


def withdraw(db, data_dir, channel):
    """Stop serving a channel (its devices get 404). The files stay on disk; the next release must be higher."""
    if channel not in CHANNELS:
        raise ReleaseError("the channel is stable or pilot")
    chan = os.path.join(root(data_dir), channel)
    with _locked(root(data_dir)):
        version = current(data_dir, channel)
        if not version:
            raise ReleaseError(f"{channel} has no current release")
        os.unlink(os.path.join(chan, "current.json"))
        _fsync_dir(chan)
    _audit(db, "withdrew a release", f"{channel} {version}", "devices on this channel now get 404",
           {"current": version}, {"current": None}, f"release:{channel}:{version}")
    return {"channel": channel, "version": version}


def pilot_change(db, action, person_id):
    """Add or remove a person on the pilot list. -> True when the list changed."""
    person = db.one("SELECT id, name FROM people WHERE id = ?", (person_id,))
    if not person:
        raise ReleaseError("no such person")
    before = pilot_list(db)
    after = sorted(set(before) | {person_id}) if action == "add" else [x for x in before if x != person_id]
    if after == before:
        return False
    db.set_setting("release_pilot", json.dumps(after))
    _audit(db, "added to the release pilot" if action == "add" else "removed from the release pilot", person["name"], "",
           {"pilot": before}, {"pilot": after}, "release:pilot:list")
    return True
