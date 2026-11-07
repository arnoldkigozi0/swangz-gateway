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
from pathlib import Path

from . import __version__, agents, bundles, keystore, shell

TIMEOUT = 30
MAX_DOWNLOAD = 150 * 1024 * 1024
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")


class ApiFailure(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code or "", message


class Revoked(ApiFailure):
    """The server explicitly revoked this device."""


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
            for root in reversed(self.roots()):
                keystore.erase_file(root / "device.key")
                for name in ("state.json", "manifest.json", "device.json", "credential-access.log"):
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
                    "name": name or device_name(), "person": out["person"], "signed_in": time.time()}
            self.store.save_device(info, out["key"])
            self.store.save_state({"installed": {}, "last_sync": None})
            return info
        raise ApiFailure(0, "expired_token", "The sign-in code expired before it was approved. Try again.")

    # ------------------------------------------------------------ what is offered, and putting it here

    def _guard(self, fn):
        try:
            return fn()
        except Revoked:
            self.remove_everything()
            raise

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
        self.heartbeat()
        return {"results": results, "manifest": manifest}

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
            for sub in ("packages", "extension", "backups"):
                try:
                    shutil.rmtree(root / sub)
                except FileNotFoundError:
                    pass
        self.store.wipe()

    def heartbeat(self):
        state = self.store.state()
        self.store.key()
        body = {**system_facts(), "key_storage": (self.store.device() or {}).get("key_storage", "file"),
                "packages": [{"id": pid, "version": r.get("version", "?")} for pid, r in state["installed"].items()]}
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

    def status(self):
        credential_error = None
        try:
            key = self.store.key()
            if key:
                self._upgrade_agents(key)
        except (keystore.KeyStoreError, agents.AgentConfigError, OSError) as exc:
            credential_error = str(exc)
        device, state, manifest = self.store.device(), self.store.state(), self.store.manifest()
        latest = state.get("latest_client")
        return {"signed_in": self.signed_in(), "server": (device or {}).get("server"), "person": (device or {}).get("person"),
                "device": device, "installed": state["installed"], "last_sync": state.get("last_sync"),
                "update_available": bool(latest and version_tuple(latest) > version_tuple(__version__)),
                "client_version": __version__, "recording": (manifest or {}).get("recording"),
                "autostart": shell.autostart_enabled(self.paths), "key_storage": (device or {}).get("key_storage"),
                "credential_warning": credential_error or (device or {}).get("credential_warning"),
                "cleanup_pending": bool((device or {}).get("cleanup_pending"))}

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
