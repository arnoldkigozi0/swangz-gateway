"""The Swangz app's brain: sign in with a code, what this device is offered, install / update / remove, run.

Everything the window and the command line do goes through `Client`, so both behave the same and the logic
can be tested without a window. The server decides what this device is offered (the same rule as everywhere
in Swangz AI Hub: company subscription active **and** the person assigned); this program installs exactly
that and removes what is no longer offered. If the server says this device was disconnected, everything
Swangz put here is removed.
"""

import json
import hmac
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from . import __version__, agents, bundles, keystore, shell

TIMEOUT = 30
MAX_DOWNLOAD = 150 * 1024 * 1024
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")
HEARTBEAT_SECONDS = 15 * 60  # the window's sync/check-in interval; a refused key is not retried faster than this
ROTATE_AFTER_DAYS = 30  # used when the manifest does not say
ROTATE_LOCK_STALE = 180  # a rotation is two short calls; a lock older than this is from a hung or dead process
SESSION_MAX_AGE = 7 * 86400  # a session marker older than this is not believed, even if its pid is alive again


class ApiFailure(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code or "", message


class Revoked(ApiFailure):
    """The server explicitly revoked this device."""


class KeyRotated(ApiFailure):
    """401 device_key_rotated: *this key* was replaced by a newer one on the same device. Never a reason to wipe."""

    used = None  # the key that was refused


class NeedsReconnect(Exception):
    """This device's only key was replaced and no newer one reached the app. Nothing is removed; the person
    reconnects the device."""


class NotSignedIn(Exception):
    pass


class ClientTooOld(Exception):
    pass


# ---------------------------------------------------------------- where things live


def default_data_dir(home):
    home = Path(home)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "Swangz"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Swangz"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "swangz"


class Paths:
    """`home` is the person's home folder (the tools' own settings live under it); `data` is Swangz's folder."""

    def __init__(self, home=None, data=None):
        self.home = Path(home or os.environ.get("SWANGZ_TEST_HOME") or Path.home())
        self.data = Path(data or os.environ.get("SWANGZ_HOME") or default_data_dir(self.home))
        self.legacy_data = None
        if sys.platform == "win32" and data is None and not os.environ.get("SWANGZ_HOME"):
            old = Path(os.environ.get("APPDATA") or self.home / "AppData" / "Roaming") / "Swangz"
            if old != self.data:
                self.legacy_data = old


def write_private(path, text):
    keystore.write_private(path, text)


class RotationLock:
    """One rotation at a time on this data folder, across processes (the window and `swangz sync` share it).
    The file is created exclusively; a lock whose owner is gone, or that is older than ROTATE_LOCK_STALE, is
    taken over. Not re-entrant: a second holder in the same process is refused like any other."""

    def __init__(self, path, alive, stale=ROTATE_LOCK_STALE):
        self.path, self.alive, self.stale = Path(path), alive, stale
        self._mine = None

    def _read(self):
        try:
            return self.path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _is_stale(self, text):
        try:
            owner = json.loads(text)
            pid, at = owner["pid"], float(owner["at"])
            if isinstance(pid, bool) or not isinstance(pid, int):
                raise ValueError
        except (TypeError, ValueError, KeyError):
            try:  # unreadable or half-written: judge it by the file's age alone
                return time.time() - self.path.stat().st_mtime > self.stale
            except OSError:
                return False
        return time.time() - at > self.stale or not self.alive(pid)

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"pid": os.getpid(), "at": time.time()})
        for _ in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                seen = self._read()
                if seen is None or not self._is_stale(seen):
                    if seen is None:
                        continue  # it vanished between the two calls; try to create it again
                    return False
                if self._read() == seen:  # break it only if it is still the same stale lock
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            self._mine = text
            return True
        return False

    def release(self):
        mine, self._mine = self._mine, None
        if mine is not None and self._read() == mine:  # never remove a lock somebody else took over
            self.path.unlink(missing_ok=True)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


class Store:
    """device.json (who this device is), device.key (its key; private), state.json (what is installed)."""

    def __init__(self, paths, credentials=None):
        self.paths = paths
        self.credentials = credentials or keystore
        self.lock = threading.RLock()
        self.migration_attempted = False

    def roots(self):
        return [self.paths.data] + ([self.paths.legacy_data] if self.paths.legacy_data else [])

    def _read(self, name, default):
        for root in self.roots():
            try:
                return json.loads((root / name).read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                return default
        return default

    def device(self):
        return self._read("device.json", None)

    def key(self):
        with self.lock:
            info = self.device()
            if not info or info.get("cleanup_pending"):
                return None
            if info.get("key_storage") == "keychain":
                secret = self.credentials.get(info["server"], info["key_id"])
                if not secret:
                    raise keystore.KeyStoreError("The device credential is missing from the keychain. Retry or sign out to reconnect.")
                self._erase_legacy(info)
                return secret
            for root in self.roots():
                path = root / "device.key"
                try:
                    if path.is_symlink():
                        raise keystore.KeyStoreError("Refused to read a linked credential file.")
                    secret = keystore.check_secret(path.read_text(encoding="utf-8").strip())
                except FileNotFoundError:
                    continue
                if not self.migration_attempted:
                    self.migration_attempted = True
                    self._store_key(info, secret)
                return secret
            # An interrupted new enrolment may have written the native item before committing metadata.
            if info.get("keychain_pending"):
                secret = self.credentials.get(info["server"], info["key_id"])
                if secret:
                    info.update(key_storage="keychain", keychain_pending=False)
                    self._save_info(info)
                    self._erase_legacy(info)
                    return secret
            return None

    def _save_info(self, info):
        write_private(self.paths.data / "device.json", json.dumps(info, indent=2))

    def _erase_legacy(self, info):
        try:
            for root in self.roots():
                keystore.erase_file(root / "device.key")
        except (OSError, keystore.KeyStoreError):
            info["credential_warning"] = "Keychain verified; an old key file still needs removal. Retry or sign out."
            self._save_info(info)
        else:
            if info.get("credential_warning", "").startswith("Keychain verified;"):
                info.pop("credential_warning", None)
                self._save_info(info)

    def _store_key(self, info, secret):
        info = dict(info)
        info.update(key_storage="file", keychain_pending=True)
        # Journal only identity, never the secret. A restart can recover a completed native put.
        self._save_info(info)
        try:
            self.credentials.put(info["server"], info["key_id"], secret)
            read_back = self.credentials.get(info["server"], info["key_id"])
            if not read_back or not hmac.compare_digest(secret, read_back):
                raise keystore.KeyStoreError("The stored device credential could not be verified.")
        except keystore.KeyStoreError as exc:
            if isinstance(exc, keystore.Unavailable):
                info["keychain_pending"] = False
            # Never erase an existing usable file until its replacement is read and compared.
            local = self.paths.data / "device.key"
            write_private(local, secret)
            if local.read_text(encoding="utf-8") != secret:
                raise keystore.KeyStoreError("The local credential file could not be verified.")
            info["credential_warning"] = "Key kept in a protected file — this device has no working keychain."
            self._save_info(info)
            for root in self.roots()[1:]:
                keystore.erase_file(root / "device.key")
            return
        info.update(key_storage="keychain", keychain_pending=False)
        info.pop("credential_warning", None)
        self._save_info(info)  # Commit before overwrite: interrupted scrubbing cannot lose the credential.
        self._erase_legacy(info)

    def save_device(self, info, key):
        with self.lock:
            self._store_key(info, keystore.check_secret(key))
            self.migration_attempted = True

    # ---- rotation: a new key is written here, and verified, before it is ever used

    def staged(self):
        """-> (key_id, secret) of a key written by a rotation and not yet current, or None."""
        with self.lock:
            info = self.device()
            if not info or info.get("cleanup_pending") or not info.get("next_key_id"):
                return None
            if info.get("next_key_storage") == "keychain":
                secret = self.credentials.get(info["server"], info["next_key_id"])
            else:
                try:
                    secret = keystore.check_secret((self.paths.data / "device.key.next").read_text(encoding="utf-8").strip())
                except FileNotFoundError:
                    secret = None
            return (info["next_key_id"], secret) if secret else None

    def stage(self, key_id, secret):
        """Write the new key next to the current one and read it back. Only identity is journalled in device.json."""
        keystore.check_secret(secret)
        keystore.account(self.device()["server"], key_id)  # rejects a malformed id
        with self.lock:
            info = self.device()
            info.update(next_key_id=key_id, next_key_storage="file")
            self._save_info(info)  # a restart can find the item even if we stop before using it
            if self.device().get("key_storage") == "keychain":
                try:
                    self.credentials.put(info["server"], key_id, secret)
                    back = self.credentials.get(info["server"], key_id)
                    if back and hmac.compare_digest(secret, back):
                        info["next_key_storage"] = "keychain"
                        self._save_info(info)
                        return
                except keystore.KeyStoreError:
                    pass
                self._forget_item(info["server"], key_id)  # the put may have stored something we could not read back
            nxt = self.paths.data / "device.key.next"
            write_private(nxt, secret)
            if nxt.read_text(encoding="utf-8") != secret:
                raise keystore.KeyStoreError("The new device credential could not be verified.")

    def _forget_item(self, server, key_id):
        """Remove a keychain item we are not going to use; if that cannot be confirmed, remember it for wipe()."""
        try:
            self.credentials.delete(server, key_id)
            if self.credentials.get(server, key_id) is None:
                return
        except keystore.KeyStoreError:
            pass
        now = self.device()
        now["stale_key_ids"] = (now.get("stale_key_ids") or []) + [key_id]
        self._save_info(now)

    def promote(self):
        """Make the staged key the current one. The old one is deleted afterwards (and retried at sign-out if that fails)."""
        with self.lock:
            staged = self.staged()
            if not staged:
                return False
            nid, secret = staged
            info = self.device()
            old_id, old_storage, next_storage = info["key_id"], info.get("key_storage"), info.get("next_key_storage")
            new = {k: v for k, v in info.items() if k not in ("next_key_id", "next_key_storage", "reconnect")}
            new.update(key_id=nid, key_issued=time.time())
            if next_storage == "keychain":
                new.update(key_storage="keychain", keychain_pending=False)
                self._save_info(new)  # the pointer moves only after the new item was read back
            else:
                self._store_key(new, secret)  # keychain if it works now, else the protected file
            keystore.erase_file(self.paths.data / "device.key.next")
            if old_storage == "keychain":
                try:
                    self.credentials.delete(info["server"], old_id)
                except keystore.KeyStoreError:
                    now = self.device()
                    now["stale_key_ids"] = (now.get("stale_key_ids") or []) + [old_id]
                    self._save_info(now)
            return True

    def state(self):
        s = self._read("state.json", {})
        s.setdefault("installed", {})
        return s

    def save_state(self, state):
        write_private(self.paths.data / "state.json", json.dumps(state, indent=2))

    def manifest(self):
        return self._read("manifest.json", None)

    def save_manifest(self, manifest):
        write_private(self.paths.data / "manifest.json", json.dumps(manifest))

    def wipe(self):
        with self.lock:
            info = self.device()
            if info:
                # A tombstone survives failure, so a second logout retries the exact item.
                info["cleanup_pending"] = True
                self._save_info(info)
                if info.get("key_storage") == "keychain" or info.get("keychain_pending"):
                    self.credentials.delete(info["server"], info["key_id"])
                    if self.credentials.get(info["server"], info["key_id"]) is not None:
                        raise keystore.KeyStoreError("Keychain removal is incomplete. Retry signing out.")
                # a staged (not yet current) key and any old item that could not be deleted at rotation
                extra = list(info.get("stale_key_ids") or [])
                if info.get("next_key_id") and info.get("next_key_storage") == "keychain":
                    extra.append(info["next_key_id"])
                for key_id in extra:
                    self.credentials.delete(info["server"], key_id)
                    if self.credentials.get(info["server"], key_id) is not None:
                        raise keystore.KeyStoreError("Keychain removal is incomplete. Retry signing out.")
            for root in reversed(self.roots()):
                keystore.erase_file(root / "device.key")
                keystore.erase_file(root / "device.key.next")
                for name in ("state.json", "manifest.json", "device.json", "credential-access.log", "rotate.lock"):
                    (root / name).unlink(missing_ok=True)


def normalise_server(text):
    text = (text or "").strip()
    if any(ord(c) < 33 or ord(c) > 126 or c in '\\"' for c in text):
        raise ValueError("Invalid characters in the Hub address.")
    if not text or re.fullmatch(r"(?i)[a-z][a-z0-9+.-]*:/*", text):
        raise ValueError("Enter the address of your Swangz AI Hub.")
    text = text.rstrip("/")
    if "://" not in text:
        text = "https://" + text
    u = urllib.parse.urlsplit(text)
    try:
        port = u.port
    except ValueError:
        raise ValueError("Invalid port in the Hub address.") from None
    if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
        raise ValueError("That doesn't look like the address of a Swangz AI Hub (for example https://ai.swangzavenue.com).")
    if u.scheme == "http" and u.hostname not in LOCAL_HOSTS and os.environ.get("SWANGZ_ALLOW_HTTP") != "1":
        raise ValueError("Swangz only connects over https. (For a test server on this computer, http://localhost works.)")
    host = u.hostname.lower()
    if not re.fullmatch(r"[a-z0-9.:-]+", host):
        raise ValueError("Invalid hostname in the Hub address.")
    host = f"[{host}]" if ":" in host else host
    authority = host + (f":{port}" if port and port != {"https": 443, "http": 80}[u.scheme] else "")
    return f"{u.scheme}://{authority}"


def same_origin_url(url, server):
    if not isinstance(url, str) or any(ord(c) < 33 or ord(c) > 126 or c in '\\"' for c in url):
        raise ApiFailure(0, "foreign_url", "The Hub supplied an unsafe address.")
    u = urllib.parse.urlsplit(url)
    try:
        origin = normalise_server(f"{u.scheme}://{u.netloc}")
    except ValueError:
        origin = None
    if origin != normalise_server(server) or u.fragment:
        raise ApiFailure(0, "foreign_url", "The Hub supplied an address outside the server this device signed in to.")
    return url


class PinnedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, server):
        self.server = server

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        same_origin_url(newurl, self.server)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


RECONNECT = "Reconnect this device: its key was renewed and the new one did not reach this app. Nothing was removed."


def version_tuple(text):
    out = []
    for part in str(text or "0").split("."):
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def system_facts():
    system = {"Windows": "Windows", "Darwin": "macOS"}.get(platform.system(), platform.system() or "Linux")
    return {"os": system + " " + (platform.release() or ""), "arch": platform.machine() or "", "app_version": __version__}


def device_name():
    return (platform.node() or "My device").split(".")[0][:60]


# ---------------------------------------------------------------- talking to the server


class Api:
    def __init__(self, server, key=None, timeout=TIMEOUT, opener=None):
        self.server, self.key, self.timeout = normalise_server(server), key, timeout
        self.opener = opener or urllib.request.build_opener(PinnedRedirect(self.server))

    def _request(self, method, url, body=None, auth=True):
        same_origin_url(url, self.server)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"X-Swangz-App": "1", "Accept": "application/json", "User-Agent": f"SwangzApp/{__version__} ({platform.system()})"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.key:
            headers["Authorization"] = "Bearer " + self.key
        return urllib.request.Request(url, data=data, method=method, headers=headers)

    def _open(self, req, limit):
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.read(limit + 1), resp.headers
        except urllib.error.HTTPError as exc:
            body = exc.read(64 * 1024)
            exc.close()
            return exc.code, body, exc.headers
        except (urllib.error.URLError, OSError) as exc:
            raise ApiFailure(0, "offline", f"Couldn't reach {self.server} ({getattr(exc, 'reason', exc)}).")

    def call(self, method, path, body=None, auth=True):
        status, raw, _ = self._open(self._request(method, self.server + "/api" + path, body, auth), 4 * 1024 * 1024)
        try:
            out = json.loads(raw or b"{}")
        except ValueError:
            out = {}
        if not isinstance(out, dict):
            raise ApiFailure(status, "invalid_response", "The Hub returned an invalid response.")
        if status >= 400:
            code, message = out.get("code", ""), out.get("error") or f"The server answered {status}."
            if status == 401 and code == "device_revoked":
                raise Revoked(status, code, message)
            if status == 401 and code == "device_key_rotated":
                exc = KeyRotated(status, code, message)
                exc.used = self.key
                raise exc
            if status == 401 and code == "device_unknown":
                message = "The Hub no longer recognises this device. Local data was kept. Retry, or sign out and reconnect."
            raise ApiFailure(status, code, message)
        return out

    def download(self, url, limit=MAX_DOWNLOAD):
        """Fetch a file the manifest named — but only from the server this device signed in to, so a manifest can
        never send the key anywhere else."""
        same_origin_url(url, self.server)
        status, raw, _ = self._open(self._request("GET", url), limit)
        if status >= 400:
            try:
                err = json.loads(raw or b"{}")
            except ValueError:
                err = {}
            if status == 401 and err.get("code") == "device_revoked":
                raise Revoked(status, err.get("code"), err.get("error") or "")
            if status == 401 and err.get("code") == "device_key_rotated":
                exc = KeyRotated(status, err.get("code"), err.get("error") or "")
                exc.used = self.key
                raise exc
            raise ApiFailure(status, err.get("code", ""), err.get("error") or f"The download failed ({status}).")
        if len(raw) > limit:
            raise ApiFailure(0, "too_large", "That download is larger than Swangz allows.")
        return raw


# ---------------------------------------------------------------- the client


class Client:
    def __init__(self, paths=None, api_factory=None, sleep=time.sleep, open_url=None, run=subprocess.run, credentials=None):
        self.paths = paths or Paths()
        self.store = Store(self.paths, credentials)
        self._upgrading = False
        self._api_factory = api_factory or (lambda server, key=None: Api(server, key))
        self.sleep, self.open_url, self.run = sleep, open_url or shell.open_url, run

    # ------------------------------------------------------------ who this device is

    def signed_in(self):
        device = self.store.device()
        if not device or device.get("cleanup_pending"):
            return False
        try:
            return bool(self.store.key())
        except keystore.KeyStoreError:
            return True  # Keep the device screen and its retry/sign-out actions available.

    def _upgrade_agents(self, key):
        if self._upgrading:
            return
        self._upgrading = True
        try:
            state, device = self.store.state(), self.store.device()
            for pid, record in list(state["installed"].items()):
                if pid not in ("claude-code", "codex") or record.get("credential_config") == 2:
                    continue
                # Remove the old credential copies first; a gated path must not retain a copied key.
                remove = agents.remove_claude if pid == "claude-code" else agents.remove_codex
                if pid == "codex":
                    remove(self.paths, record, key=key)
                else:
                    remove(self.paths, record)
                for root in self.store.roots():
                    backup_paths = Paths(self.paths.home, root)
                    agents.scrub_backup(backup_paths, key)
                base_url = self._agent_url(record["base_url"], pid, device["server"])
                fn = agents.install_claude if pid == "claude-code" else agents.install_codex
                replacement = fn(self.paths, base_url, key, record.get("mode"))
                state["installed"][pid] = {**record, **replacement}
                self.store.save_state(state)
        finally:
            self._upgrading = False

    @staticmethod
    def _agent_url(url, tool, server):
        same_origin_url(url, server)
        expected = "/anthropic" if tool == "claude-code" else "/openai/v1"
        if urllib.parse.urlsplit(url).path != expected or urllib.parse.urlsplit(url).query:
            raise agents.AgentConfigError("The Hub supplied an unsupported coding-agent endpoint.")
        return url

    def api(self):
        device, key = self.store.device(), self.store.key()
        if not (device and key):
            raise NotSignedIn("This device isn't signed in to Swangz yet.")
        self._upgrade_agents(key)
        return self._api_factory(device["server"], key)

    def login(self, server, name=None, on_code=None, cancelled=lambda: False, timeout=None):
        """Sign this device in. `on_code(user_code, url)` is told what to show the person. -> the device record."""
        server = normalise_server(server)
        if self.store.device():
            raise ValueError("Sign out of this device before connecting it again.")
        api = self._api_factory(server)
        started = api.call("POST", "/device/code", {"name": (name or device_name()), **system_facts()}, auth=False)
        url = started.get("verification_uri_complete") or started["verification_uri"]
        same_origin_url(url, server)
        if on_code:
            on_code(started["user_code"], url)
        try:
            self.open_url(url)
        except Exception:  # noqa: BLE001 — the code is shown anyway
            pass
        interval = max(1, int(started.get("interval") or 3))
        deadline = time.time() + min(int(started.get("expires_in") or 900), 900 if timeout is None else timeout)
        while time.time() < deadline:
            if cancelled():
                raise ApiFailure(0, "cancelled", "Sign-in cancelled.")
            self.sleep(interval)
            try:
                out = api.call("POST", "/device/token", {"device_code": started["device_code"]}, auth=False)
            except ApiFailure as exc:
                if exc.code == "authorization_pending":
                    continue
                if exc.code == "slow_down":
                    interval += 5
                    continue
                raise
            # The address the person entered is the pin; response metadata cannot replace it.
            info = {"server": server, "key_id": out["key_id"], "owner_kind": out["owner_kind"],
                    "name": name or device_name(), "person": out["person"], "signed_in": time.time(), "key_issued": time.time()}
            self.store.save_device(info, out["key"])
            self.store.save_state({"installed": {}, "last_sync": None})
            return info
        raise ApiFailure(0, "expired_token", "The sign-in code expired before it was approved. Try again.")

    # ------------------------------------------------------------ what is offered, and putting it here

    def _guard(self, fn):
        """Run a device call. Revoked -> remove everything. KeyRotated -> reload the key from the store and try
        once more; with no newer key, say the device needs reconnecting. A rotated key never removes anything."""
        if self._reconnect_pending():
            raise NeedsReconnect(RECONNECT)
        for attempt in (0, 1):
            try:
                return fn()
            except Revoked:
                self.remove_everything()
                raise
            except KeyRotated as exc:
                if attempt or not self._adopt_newer_key(exc.used):
                    self._mark_reconnect()
                    raise NeedsReconnect(RECONNECT) from None

    def _adopt_newer_key(self, used):
        """After device_key_rotated: is there a newer key in the store than the one that was refused?"""
        with self.store.lock:
            staged = self.store.staged()
            if staged and staged[1] != used:
                return self.store.promote()
            try:
                current = self.store.key()
            except keystore.KeyStoreError:
                return False
            return bool(current) and current != used

    def _mark_reconnect(self):
        with self.store.lock:
            info = self.store.device()
            if info and not info.get("cleanup_pending"):
                info["reconnect"] = {"key_id": info["key_id"], "at": time.time()}
                self.store._save_info(info)

    def _reconnect_pending(self):
        """True while a refused-key device should wait: calls are not retried faster than the heartbeat."""
        with self.store.lock:
            info = self.store.device()
            mark = (info or {}).get("reconnect")
            if not mark:
                return False
            if mark.get("key_id") != info.get("key_id") or info.get("next_key_id"):
                info.pop("reconnect", None)  # a newer key arrived (another window, a staged rotation)
                self.store._save_info(info)
                return False
            return time.time() - float(mark.get("at") or 0) < HEARTBEAT_SECONDS

    def refresh(self):
        """Ask what this device is offered now (no changes made). -> the manifest, also kept for the window."""
        manifest = self._guard(lambda: self.api().call("GET", "/device/manifest"))
        server = self.store.device()["server"]
        for pkg in manifest.get("packages", []):
            install = pkg.get("install") or {}
            if install.get("type") == "agent":
                self._agent_url(install.get("base_url"), pkg["id"], server)
            elif install.get("url"):
                same_origin_url(install["url"], server)
        for app in manifest.get("apps", []):
            same_origin_url(app["open"], server)
        if version_tuple(manifest.get("client", {}).get("minimum")) > version_tuple(__version__):
            raise ClientTooOld(f"This version of Swangz ({__version__}) is too old. Please update it.")
        self.store.save_manifest(manifest)
        return manifest

    def sync(self, force=False):
        """Make this device match what it is offered. -> {"results": [(id, outcome, detail)], "manifest"}.
        One package failing never stops the others."""
        manifest = self.refresh()
        state, device, key = self.store.state(), self.store.device(), self.store.key()
        api, results = self.api(), []
        wanted = {p["id"]: p for p in manifest["packages"]}
        for pid, pkg in wanted.items():
            have = state["installed"].get(pid)
            mode = (pkg.get("install") or {}).get("mode")
            if have and have.get("version") == pkg["version"] and (have.get("mode") == mode or have.get("gated")) and not force:
                results.append((pid, "current", f"{pkg['name']} {pkg['version']}"))
                continue
            try:
                record = self._install(api, pkg, key, device)
            except Revoked:
                self.remove_everything()
                raise
            except (agents.AgentConfigError, bundles.BundleError, ApiFailure, OSError) as exc:
                results.append((pid, "failed", getattr(exc, "message", None) or str(exc)))
                continue
            state["installed"][pid] = {"version": pkg["version"], "kind": pkg["kind"], "name": pkg["name"], "at": time.time(), **record}
            results.append((pid, "updated" if have else "installed", record.get("detail", "")))
        for pid in [p for p in state["installed"] if p not in wanted]:
            self._uninstall(pid, state["installed"][pid])
            del state["installed"][pid]
            results.append((pid, "removed", "no longer offered to you"))
        state["last_sync"] = time.time()
        state["latest_client"] = manifest.get("client", {}).get("latest")
        self.store.save_state(state)
        heartbeat = self.heartbeat()
        try:
            if heartbeat is not None and not any(outcome == "failed" for _, outcome, _ in results):
                self.updater().synced()
            if state.get("latest_client") and version_tuple(state["latest_client"]) > version_tuple(__version__):
                self.updater().check()  # hint triggers a check; signed bytes alone select a file
        except (ValueError, ApiFailure, OSError):
            pass  # update cleanup/checks never stop ordinary work, including lock contention
        return {"results": results, "manifest": manifest, "rotation": self.maintain_credential()}

    def _install(self, api, pkg, key, device):
        install = pkg.get("install") or {}
        kind = install.get("type")
        if kind == "agent":
            if pkg["id"] not in ("claude-code", "codex"):
                raise agents.AgentConfigError("Unknown coding agent.")
            self._agent_url(install["base_url"], pkg["id"], device["server"])
            previous = self.store.state()["installed"].get(pkg["id"])
            if previous:
                self._uninstall(pkg["id"], previous)
            fn = agents.install_claude if pkg["id"] == "claude-code" else agents.install_codex
            return fn(self.paths, install["base_url"], key, install.get("mode"))
        if kind == "bundle":
            data = api.download(install["url"])
            folder = bundles.install(self.paths, pkg["id"], pkg["version"], data, install["sha256"])
            return {"mode": None, "folder": str(folder), "detail": f"Installed in {folder}"}
        if kind == "extension":
            data = api.download(install["url"])
            folder = bundles.install(self.paths, "access-gate", pkg["version"], data, install["sha256"],
                                     base=self.paths.data / "extension")
            return {"mode": None, "folder": str(folder), "detail": f"Unpacked in {folder}. {install.get('how', '')}".strip()}
        raise bundles.BundleError(f"this version of Swangz doesn't know how to install a '{kind}' package — please update the app")

    def _uninstall(self, pid, record):
        if pid == "claude-code":
            agents.remove_claude(self.paths, record)
        elif pid == "codex":
            key = self.store.key() if (record.get("env") or {}).get("kind") == "windows-user-env" else None
            agents.remove_codex(self.paths, record, key=key)
        elif pid == "access-gate":
            shutil.rmtree(self.paths.data / "extension", ignore_errors=True)
        else:
            bundles.remove(self.paths, pid)

    def remove_package(self, pid):
        state = self.store.state()
        if pid in state["installed"]:
            self._uninstall(pid, state["installed"][pid])
            del state["installed"][pid]
            self.store.save_state(state)

    def remove_everything(self):
        """Take Swangz off this device: everything it installed, and the key. (Run when the server disconnects the
        device, and when the person signs out.)"""
        state = self.store.state()
        for pid, record in list(state["installed"].items()):
            self._uninstall(pid, record)
        for root in self.store.roots():
            for sub in ("packages", "extension", "backups", "sessions"):
                try:
                    shutil.rmtree(root / sub)
                except FileNotFoundError:
                    pass
        self.store.wipe()

    def _heartbeat_body(self):
        state = self.store.state()
        storage = (self.store.device() or {}).get("key_storage", "file")
        body = {**system_facts(), "key_storage": storage,
                "packages": [{"id": pid, "version": r.get("version", "?")} for pid, r in state["installed"].items()]}
        if storage == "keychain":  # which native store holds it; a file has no backend to name
            body["key_backend"] = keystore.backend_name()
        return body

    def heartbeat(self):
        state = self.store.state()
        self.store.key()
        body = self._heartbeat_body()
        try:
            out = self._guard(lambda: self.api().call("POST", "/device/heartbeat", body))
        except ApiFailure as exc:
            if isinstance(exc, Revoked):
                raise
            return None
        if out.get("latest_client") and out["latest_client"] != state.get("latest_client"):
            state["latest_client"] = out["latest_client"]
            self.store.save_state(state)
        return out

    # ------------------------------------------------------------ the device key: rotation

    @staticmethod
    def _pid_alive(pid):
        if pid == os.getpid():
            return True
        if sys.platform == "win32":
            import ctypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.restype = ctypes.c_void_p
            handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
            finally:
                kernel.CloseHandle(ctypes.c_void_p(handle))
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    @contextmanager
    def _session(self):
        """A coding-agent run holds the key in its environment, so the key must not change under it."""
        folder = self.paths.data / "sessions"
        folder.mkdir(parents=True, exist_ok=True)
        marker = folder / f"{os.getpid()}-{time.time_ns()}"
        marker.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}), encoding="utf-8")
        try:
            yield
        finally:
            marker.unlink(missing_ok=True)

    @staticmethod
    def _read_marker(marker):
        """-> (pid, start time). Older markers only have the pid in the name; their start is the file's age."""
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            pid, started = data["pid"], data["started"]
            if isinstance(pid, int) and not isinstance(pid, bool) and isinstance(started, (int, float)):
                return pid, float(started)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        try:
            pid = int(marker.name.split("-")[0])
        except ValueError:
            return None, None
        try:
            return pid, marker.stat().st_mtime
        except OSError:
            return pid, None

    def in_session(self):
        """Is a coding agent started by this app running (in this or another Swangz process)?"""
        live = False
        try:
            markers = list((self.paths.data / "sessions").iterdir())
        except FileNotFoundError:
            return False
        for marker in markers:
            pid, started = self._read_marker(marker)
            if pid is None:
                continue
            if started is not None and time.time() - started > SESSION_MAX_AGE:
                marker.unlink(missing_ok=True)  # far too old to be believed: its pid has likely been reused
            elif self._pid_alive(pid):
                live = True
            else:
                marker.unlink(missing_ok=True)  # the run ended without cleaning up
        return live

    def rotation_due(self, now=None):
        info, manifest = self.store.device() or {}, self.store.manifest() or {}
        cred = manifest.get("credential") if isinstance(manifest.get("credential"), dict) else {}
        days = cred.get("rotate_after_days")
        days = days if isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= 365 else ROTATE_AFTER_DAYS
        issued = next((v for v in (info.get("key_issued"), cred.get("issued"), info.get("signed_in"))
                       if isinstance(v, (int, float)) and not isinstance(v, bool)), None)
        if issued is None:
            return False  # nothing to measure from; the next login or rotation records it
        return (time.time() if now is None else now) - issued >= days * 86400

    def maintain_credential(self, now=None):
        """Called at the end of a sync (start-up and every idle check-in): finish a rotation that was started, or
        start one if the key is old. Never while a coding agent started by this app is running, and a failure
        here never fails the sync. -> "rotated" | None."""
        info = self.store.device()
        if not info or info.get("cleanup_pending") or self.in_session():
            return None
        lock = RotationLock(self.paths.data / "rotate.lock", self._pid_alive)
        if not lock.acquire():
            return None  # another Swangz process on this device is rotating; it will finish or time out
        try:
            staged = self.store.staged()
            if staged:
                return self._confirm_staged(staged)
            if self.rotation_due(now):
                return self._rotate()
        except Revoked:
            raise
        except NeedsReconnect:
            raise
        except (ApiFailure, keystore.KeyStoreError, OSError):
            return None  # try again at the next check-in; the current key still works
        finally:
            lock.release()
        return None

    def _rotate(self):
        try:
            out = self.api().call("POST", "/device/rotate", {})
        except Revoked:
            self.remove_everything()
            raise
        except KeyRotated as exc:
            if self._adopt_newer_key(exc.used):
                return None
            self._mark_reconnect()
            raise NeedsReconnect(RECONNECT) from None
        key_id, key = out.get("key_id"), out.get("key")
        if not isinstance(key_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key_id):
            raise ApiFailure(0, "invalid_response", "The Hub returned an invalid key.")
        self.store.stage(key_id, key)  # on disk and read back BEFORE the first use
        return self._confirm_staged((key_id, key))

    def _confirm_staged(self, staged):
        """One device call with the new key (a check-in). Only after it succeeds does the new key become current."""
        key_id, key = staged
        device = self.store.device()
        try:
            self._api_factory(device["server"], key).call("POST", "/device/heartbeat", self._heartbeat_body())
        except Revoked:
            self.remove_everything()
            raise
        except ApiFailure:
            return None  # stays staged; the old key works until its grace ends, then the store's newer key is used
        return "rotated" if self.store.promote() else None

    def logout(self):
        """Tell the server, then take Swangz off this device. The server is told first; if it can't be reached the
        local removal still happens (the key can be disconnected from the control room)."""
        told = True
        try:
            self.api().call("POST", "/device/signout")
        except (ApiFailure, NotSignedIn, keystore.KeyStoreError, agents.AgentConfigError):
            told = False
        self.remove_everything()
        return told

    # ------------------------------------------------------------ what the window shows

    def updater(self):
        from .updater import Updater
        return Updater(self)

    def status(self):
        credential_error = None
        try:
            key = self.store.key()
            if key:
                self._upgrade_agents(key)
        except (keystore.KeyStoreError, agents.AgentConfigError, OSError) as exc:
            credential_error = str(exc)
        device, state, manifest = self.store.device(), self.store.state(), self.store.manifest()
        updates = self.updater().status()
        return {"signed_in": self.signed_in(), "server": (device or {}).get("server"), "person": (device or {}).get("person"),
                "device": device, "installed": state["installed"], "last_sync": state.get("last_sync"),
                "update_available": updates["status"] == "staged", "updates": updates,
                "client_version": __version__, "recording": (manifest or {}).get("recording"),
                "autostart": shell.autostart_enabled(self.paths), "key_storage": (device or {}).get("key_storage"),
                "credential_warning": credential_error or (device or {}).get("credential_warning"),
                "cleanup_pending": bool((device or {}).get("cleanup_pending")),
                "reconnect": bool((device or {}).get("reconnect"))}

    def packages(self):
        """Every package this device is offered, with where it stands here."""
        manifest, installed = self.store.manifest() or {"packages": []}, self.store.state()["installed"]
        rows = []
        for p in manifest["packages"]:
            have = installed.get(p["id"])
            state = "available" if not have else ("installed" if have.get("version") == p["version"] else "update")
            rows.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "description": p.get("description", ""),
                         "version": p["version"], "installed_version": (have or {}).get("version"), "state": state,
                         "detail": (have or {}).get("detail", ""), "mode": (p.get("install") or {}).get("mode")})
        return rows

    def apps(self):
        return (self.store.manifest() or {}).get("apps", [])

    # ------------------------------------------------------------ running things

    def agent_command(self, tool, args=()):
        """-> (argv, env) to run Claude Code or Codex through the gateway for this one run."""
        record = self.store.state()["installed"].get(tool)
        key = self.store.key()
        if not (record and key):
            raise NotSignedIn(f"{'Claude Code' if tool == 'claude-code' else 'Codex'} isn't set up on this device. Open Swangz and sync.")
        exe = {"claude-code": "claude", "codex": "codex"}[tool]
        self._upgrade_agents(key)
        record = self.store.state()["installed"][tool]
        self._agent_url(record["base_url"], tool, self.store.device()["server"])
        env = dict(os.environ)
        if tool == "claude-code":
            env.update(ANTHROPIC_BASE_URL=record["base_url"], ANTHROPIC_AUTH_TOKEN=key, CLAUDE_CODE_GATEWAY_HINT_HEADERS="1")
            return [exe, *args], env
        env["SWANGZ_AI_KEY"] = key
        extra = agents.codex_overrides(record["base_url"]) if record.get("mode") != "managed" else []
        return [exe, *extra, *args], env

    def run_agent(self, tool, args=()):
        argv, env = self.agent_command(tool, args)
        if not shutil.which(argv[0]):
            hint = {"claude": "npm install -g @anthropic-ai/claude-code", "codex": "npm install -g @openai/codex"}[argv[0]]
            raise FileNotFoundError(f"{argv[0]} isn't installed on this device. Install it first ({hint}), then run this again.")
        with self._session():
            return self.run(argv, env=env).returncode

    def helper_key(self, tool):
        if tool not in ("claude-code", "codex") or tool not in self.store.state()["installed"]:
            raise NotSignedIn("This coding agent is not set up on this device.")
        key = self.store.key()
        if not key:
            raise NotSignedIn("This device is not signed in.")
        # Local access-level record only, bounded in size; no credential, args or environment.
        path = self.paths.data / "credential-access.log"
        lines = path.read_text(encoding="utf-8").splitlines()[-99:] if path.exists() else []
        write_private(path, "\n".join(lines + [f"{int(time.time())} key {tool}"]) + "\n")
        return key

    def open_app(self, tool_id):
        """Open a website tool through Swangz (which checks access, records it and, for a shared account, puts the
        person in a company browser of their own)."""
        for app in self.apps():
            if app["id"] == tool_id:
                same_origin_url(app["open"], self.store.device()["server"])
                self.open_url(app["open"])
                return app["open"]
        raise KeyError(tool_id)
