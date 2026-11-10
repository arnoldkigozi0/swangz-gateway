"""D-003 verified updates; no production trust keys or automatic installation.

The signed manifest selects a single-file portable executable. Installation is
confined to the app's private data/app/Swangz file, not arbitrary caller paths.
Native bundle/installer replacement awaits platform packaging and native tests.
"""

from contextlib import contextmanager
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.request

from . import __version__, core, keystore, release_keys

MAX_MANIFEST = 64 * 1024
MAX_ARTIFACT = 150 * 1024 * 1024
SKEW = 300
ACK_TIMEOUT = 60
SHA256_DER = bytes.fromhex("3031300d060960864801650304020105000420")


class UpdateError(ValueError):
    pass


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})", value):
        raise UpdateError("Invalid release version.")
    return tuple(map(int, value.split(".")))


def verify(raw, signature, keys):
    """Authenticate the exact raw bytes, before any JSON decoding. No padding parser."""
    digest_info = SHA256_DER + hashlib.sha256(raw).digest()
    for key_id, (n, e) in keys.items():
        if not isinstance(n, int) or n.bit_length() != 4096 or e != 65537:
            continue
        length = (n.bit_length() + 7) // 8
        if len(signature) != length or int.from_bytes(signature, "big") >= n:
            continue
        expected = b"\x00\x01" + b"\xff" * (length - len(digest_info) - 3) + b"\x00" + digest_info
        actual = pow(int.from_bytes(signature, "big"), e, n).to_bytes(length, "big")
        if hmac.compare_digest(actual, expected):
            return key_id
    raise UpdateError("Release signature is not trusted.")


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise UpdateError("Duplicate release field.")
        out[key] = value
    return out


def decode(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(UpdateError("Invalid JSON number.")))
    except (ValueError, UnicodeError):
        raise UpdateError("Invalid release metadata.") from None
    if not isinstance(value, dict):
        raise UpdateError("Invalid release metadata.")
    return value


def native_signature_status(path):
    # Future codesign/WinVerifyTrust hook. Never equate release trust with OS signing.
    return "not checked"


def _file(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise UpdateError("Refused a linked update file.")
    return st


def _dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise UpdateError("Refused a linked update directory.")
    if os.name == "nt":
        keystore.protect_windows_file(path)
    else:
        path.chmod(0o700)


def _sync_dir(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _json(path, value):
    keystore.write_private(path, json.dumps(value, sort_keys=True))
    _sync_dir(path.parent)


def _hash(path):
    _file(path)
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _allow_remove(path):
    """Windows read-only is independent of our DACL; clear it before replace/unlink.

    Also handles files staged by older updater builds that used chmod(0500).
    Keep the DACL intact, and refuse links before changing attributes.
    """
    if os.name == "nt" and (path.exists() or path.is_symlink()):
        _file(path)
        path.chmod(stat.S_IREAD | stat.S_IWRITE)


class Updater:
    def __init__(self, client, running=__version__, now=time.time):
        self.client, self.running, self.now = client, running, now
        version(running)
        self.base = client.paths.data.absolute()
        self.root = self.base / "updates"
        self.app = self.base / "app"
        self.target = self.app / ("Swangz.exe" if os.name == "nt" else "Swangz")
        self.prev = self.app / ("Swangz.prev.exe" if os.name == "nt" else "Swangz.prev")
        self.failed = self.app / ("Swangz.failed.exe" if os.name == "nt" else "Swangz.failed")

    def _paths(self):
        if self.base.resolve() != self.base:
            raise UpdateError("Refused a linked app data directory.")
        _dir(self.base)
        _dir(self.root)
        _dir(self.app)

    @contextmanager
    def locked(self):
        self._paths()
        path = self.root / "update.lock"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            _file(path)
            if os.name == "nt":
                import msvcrt
                if not os.fstat(fd).st_size:
                    os.write(fd, b"0")
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)  # releases OS lock, including after a crashed updater

    def _read(self, name):
        path = self.root / name
        try:
            _file(path)
            if path.stat().st_size > MAX_MANIFEST:
                raise UpdateError("Invalid update journal.")
            return decode(path.read_bytes())
        except FileNotFoundError:
            return {}

    def _state(self, **changes):
        state = self._read("state.json")
        state.update(changes)
        _json(self.root / "state.json", state)
        return state

    def status(self):
        if not release_keys.KEYS:
            return {"status": "unavailable", "message": "Updates unavailable: no pinned release key.", "platform_signature": "not checked"}
        if not release_keys.ENABLED:
            return {"status": "unavailable", "message": "Updates unavailable: release gate is closed.", "platform_signature": "not checked"}
        state = self._read("state.json")
        return {"status": state.get("status", "ready"), "message": state.get("message", "Ready to check for updates."),
                "platform_signature": "not checked", "version": state.get("version")}

    def _fetch(self, api, path, cap, output=None):
        """Own pinned opener; never use a caller-provided redirect handler."""
        if not api.server.startswith("https://"):
            # Loopback HTTP is a fake-service route, never a deployed HTTP gateway.
            from urllib.parse import urlsplit
            if urlsplit(api.server).hostname not in core.LOCAL_HOSTS:
                raise UpdateError("Updates require HTTPS.")
        req = api._request("GET", api.server + path)
        opener = urllib.request.build_opener(core.PinnedRedirect(api.server))
        with opener.open(req, timeout=core.TIMEOUT) as response:
            core.same_origin_url(response.geturl(), api.server)
            if response.status != 200:
                raise UpdateError("Release download failed.")
            total, digest, pieces = 0, hashlib.sha256(), []
            while True:
                block = response.read(min(64 * 1024, cap - total + 1))
                if not block:
                    break
                total += len(block)
                if total > cap:
                    raise UpdateError("Release download exceeds its size limit.")
                digest.update(block)
                if output is None:
                    pieces.append(block)
                else:
                    output.write(block)
            return b"".join(pieces), total, digest.hexdigest(), response.headers

    def _validate(self, raw, signature, server_version):
        signer = verify(raw, signature, release_keys.KEYS)
        manifest = decode(raw)
        if type(manifest.get("schema")) is not int or manifest["schema"] != 1 or manifest.get("key_id") != signer:
            raise UpdateError("Invalid release schema or key id.")
        if manifest.get("channel") != release_keys.CHANNEL:
            raise UpdateError("Release channel mismatch.")
        for field in ("released", "expires"):
            if type(manifest.get(field)) is not int:
                raise UpdateError("Invalid release time.")
        if manifest["expires"] <= self.now() or manifest["released"] > self.now() + SKEW or manifest["expires"] <= manifest["released"]:
            raise UpdateError("Release is expired or not yet released.")
        candidate = version(manifest.get("version"))
        state = self._read("state.json")
        floors = [self.running, state.get("highest", "0.0.0"), state.get("failed_version", "0.0.0")]
        if any(candidate <= version(floor) for floor in floors):
            raise UpdateError("Release is older, already accepted or previously failed.")
        if version(manifest.get("min_server")) > version(server_version):
            raise UpdateError("This release requires a newer gateway.")
        system = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform)
        arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not all(isinstance(a, dict) for a in artifacts):
            raise UpdateError("Invalid release artifacts.")
        matches = [a for a in artifacts if a.get("platform") == system and a.get("arch") == arch]
        if len(matches) != 1:
            raise UpdateError("No unique release for this platform and architecture.")
        artifact = matches[0]
        name = artifact.get("file")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) or ".." in name:
            raise UpdateError("Unsafe artifact filename.")
        if (name.endswith(".") or name.split(".")[0].upper() in
                {"CON", "PRN", "AUX", "NUL", *["COM" + str(i) for i in range(1, 10)], *["LPT" + str(i) for i in range(1, 10)]}
                or name in ("release.json", "release.json.sig.hex")):
            raise UpdateError("Reserved artifact filename.")
        if type(artifact.get("size")) is not int or not 0 < artifact["size"] <= MAX_ARTIFACT:
            raise UpdateError("Invalid release size.")
        if not isinstance(artifact.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
            raise UpdateError("Invalid release hash.")
        return manifest, artifact

    def check(self):
        if not release_keys.KEYS or not release_keys.ENABLED:
            return self.status()  # no credentials read, directories created or network used
        with self.locked():
            if self._read("pending.json"):
                raise UpdateError("Finish or recover the pending update first.")
            api = self.client.api()
            prefix = "/api/device/releases/" + release_keys.CHANNEL
            raw, _, _, headers = self._fetch(api, prefix + "/release.json", MAX_MANIFEST)
            signature, _, _, _ = self._fetch(api, prefix + "/release.json.sig", 512)
            manifest, artifact = self._validate(raw, signature, headers.get("X-Swangz-Gateway-Version"))
            folder = self.root / manifest["version"]
            _dir(folder)
            path = folder / artifact["file"]
            # A failed prior download is never a usable candidate. No symlinks followed.
            if path.exists() or path.is_symlink():
                _file(path)
                _allow_remove(path)
                path.unlink()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as output:
                    if os.name == "nt":
                        keystore.protect_windows_file(path)
                    _, size, digest, _ = self._fetch(api, prefix + "/" + artifact["file"], artifact["size"], output)
                    output.flush()
                    os.fsync(output.fileno())
                if not hmac.compare_digest(str(size), str(artifact["size"])) or not hmac.compare_digest(digest, artifact["sha256"]):
                    raise UpdateError("Release size or SHA-256 mismatch.")
                if os.name != "nt":
                    path.chmod(0o500)
            except Exception:
                _allow_remove(path)
                path.unlink(missing_ok=True)
                raise
            # Retain signed input; install re-verifies expiry, compatibility, floors and bytes.
            keystore.write_private(folder / "release.json", raw.decode("utf-8"))
            keystore.write_private(folder / "release.json.sig.hex", signature.hex())
            self._state(status="staged", message="Verified update staged. Platform signature: not checked.",
                        version=manifest["version"], gateway_version=headers.get("X-Swangz-Gateway-Version"),
                        platform_signature=native_signature_status(path))
            return self.status()

    def _journal(self, pending):
        _json(self.root / "pending.json", pending)

    def _acknowledged(self, pending):
        ack = self._read("update-ok")
        return (ack.get("nonce") == pending.get("nonce") and ack.get("version") == pending.get("version")
                and self.target.exists() and hmac.compare_digest(_hash(self.target), pending["sha256"]))

    def _accept(self, pending):
        state = self._read("state.json")
        highest = max(version(state.get("highest", "0.0.0")), version(pending["version"]))
        self._state(highest=".".join(map(str, highest)), status="updated", version=pending["version"],
                    message="Update self-test passed. Platform signature: not checked.")
        pending["phase"] = "ok"
        self._journal(pending)

    def _rollback(self, pending):
        if self.prev.exists():
            _file(self.prev)
            if not hmac.compare_digest(_hash(self.prev), pending["old_sha256"]):
                raise UpdateError("Previous application changed; automatic recovery refused.")
            if self.target.exists():
                _file(self.target)
            _allow_remove(self.prev)
            _allow_remove(self.target)
            if os.name == "nt" and self.target.exists() and os.path.samefile(sys.executable, self.target):
                # Windows permits renaming a loaded exe, but not replacing it.
                # Leave the failed image until a later start, after this process exits.
                self._cleanup_failed()
                if self.failed.exists():
                    raise UpdateError("A failed application is still running. Close it and retry recovery.")
                os.rename(self.target, self.failed)
                _sync_dir(self.app)
            os.replace(self.prev, self.target)
            _sync_dir(self.app)
        elif not self.target.exists() or not hmac.compare_digest(_hash(self.target), pending["old_sha256"]):
            raise UpdateError("Previous application is missing; automatic recovery needs review.")
        # Commit the failed-version floor after restoration and before clearing the journal.
        state = self._read("state.json")
        failed = max(version(state.get("failed_version", "0.0.0")), version(pending["version"]))
        self._state(failed_version=".".join(map(str, failed)), status="update_failed",
                    message="Update failed; previous application restored.")
        (self.root / "pending.json").unlink(missing_ok=True)
        (self.root / "update-ok").unlink(missing_ok=True)
        _sync_dir(self.root)

    def _cleanup_failed(self):
        if self.failed.exists() or self.failed.is_symlink():
            _file(self.failed)
            _allow_remove(self.failed)
            try:
                self.failed.unlink()
            except PermissionError:
                if os.name != "nt":
                    raise
                # The old recovery process may not have exited yet. Retry next start.
            else:
                _sync_dir(self.app)

    def recover(self):
        if not self.root.exists():
            return False
        with self.locked():
            pending = self._read("pending.json")
            if pending:
                if self._acknowledged(pending):
                    self._accept(pending)
                else:
                    self._rollback(pending)
                    return True
            elif self.prev.exists():
                # A previous binary without its journal must never be silently discarded.
                raise UpdateError("Previous application has no update journal; recovery needs review.")
            else:
                self._cleanup_failed()
        return False

    def install(self, launch=subprocess.Popen, monotonic=time.monotonic, sleep=time.sleep):
        if not release_keys.KEYS or not release_keys.ENABLED:
            return self.status()
        with self.locked():
            if self._read("pending.json") or self.prev.exists():
                raise UpdateError("Finish the previous update before installing another.")
            state = self._read("state.json")
            candidate = state.get("version")
            version(candidate)
            folder = self.root / candidate
            if folder.is_symlink():
                raise UpdateError("Refused a linked update directory.")
            _file(folder / "release.json")
            _file(folder / "release.json.sig.hex")
            if (folder / "release.json").stat().st_size > MAX_MANIFEST or (folder / "release.json.sig.hex").stat().st_size != 1024:
                raise UpdateError("Invalid staged release metadata size.")
            raw = (folder / "release.json").read_bytes()
            signature = bytes.fromhex((folder / "release.json.sig.hex").read_text())
            manifest, artifact = self._validate(raw, signature, state.get("gateway_version"))
            if manifest["version"] != candidate:
                raise UpdateError("Staged release version changed.")
            staged = folder / artifact["file"]
            if staged.stat().st_size != artifact["size"] or not hmac.compare_digest(_hash(staged), artifact["sha256"]):
                raise UpdateError("Staged artifact changed.")
            _file(self.target)
            pending = {"version": candidate, "sha256": artifact["sha256"], "old_sha256": _hash(self.target),
                       "phase": "prepared", "nonce": secrets.token_hex(32)}
            self._journal(pending)  # write-ahead journal before touching current
            process = None
            try:
                _allow_remove(self.target)
                os.replace(self.target, self.prev)
                _sync_dir(self.app)
                pending["phase"] = "old_moved"
                self._journal(pending)
                os.replace(staged, self.target)
                _sync_dir(self.app)
                pending["phase"] = "new_moved"
                self._journal(pending)
                if not hmac.compare_digest(_hash(self.target), artifact["sha256"]):
                    raise UpdateError("Installed artifact changed.")
                # Do not inherit coding-agent/provider credentials from a parent shell.
                env = {k: v for k, v in os.environ.items() if k not in
                       ("SWANGZ_AI_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
                env["SWANGZ_HOME"] = str(self.base)
                process = launch([str(self.target), "--post-update"], env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = monotonic() + ACK_TIMEOUT
                while monotonic() < deadline:
                    if self._acknowledged(pending):
                        if process.wait(timeout=max(0.01, deadline - monotonic())) != 0:
                            raise UpdateError("Update self-test process failed.")
                        self._accept(pending)
                        return self.status()
                    if process.poll() is not None:
                        break
                    sleep(0.1)
                raise UpdateError("Update self-test failed or timed out.")
            except Exception:
                try:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                finally:
                    self._rollback(pending)
                raise

    def post_update(self):
        """Called only by the candidate process. Parent owns the install lock and acceptance."""
        self._paths()
        pending = self._read("pending.json")
        if not pending or pending.get("phase") != "new_moved" or pending.get("version") != self.running:
            raise UpdateError("No matching post-update self-test.")
        if not hmac.compare_digest(_hash(self.target), pending["sha256"]):
            raise UpdateError("Installed artifact changed.")
        for module in ("core", "agents", "bundles", "keystore", "cli"):
            importlib.import_module("swangz_client." + module)
        for name in ("state.json", "device.json", "manifest.json"):
            path = self.base / name
            if path.exists():
                _file(path)
                decode(path.read_bytes())  # do not accept Store's corrupt-state default
        device = self.client.store.device()
        if device and not device.get("cleanup_pending"):
            if device.get("key_storage") == "keychain":
                key = self.client.store.credentials.get(device["server"], device["key_id"])
            else:
                path = self.base / "device.key"
                _file(path)
                key = path.read_text(encoding="utf-8").strip()
            keystore.check_secret(key)  # read only; no migration/configuration changes
        _json(self.root / "update-ok", {"version": self.running, "nonce": pending["nonce"]})

    def synced(self):
        """Retire the one backup only after an acknowledged version's successful sync."""
        if not self.root.exists():
            return
        with self.locked():
            pending = self._read("pending.json")
            if pending.get("phase") == "ok" and pending.get("version") == self.running and self._acknowledged(pending):
                if self.prev.exists():
                    _file(self.prev)
                    _allow_remove(self.prev)
                    self.prev.unlink()
                _sync_dir(self.app)
                (self.root / "pending.json").unlink()
                (self.root / "update-ok").unlink(missing_ok=True)
                _sync_dir(self.root)
