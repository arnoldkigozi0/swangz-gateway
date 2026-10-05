"""Swangz Workspace Agent: runs on the workspace server, next to Docker, and nowhere else.

The gateway never touches Docker or Neko in this mode. It asks this agent, over one small API with one
token, for a company browser for someone's turn, and tells it when the turn is over:

  GET  /health                                  is Docker answering, how many browsers are running
  GET  /status                                  every browser: its tool, state, who holds it, since when
  POST /allocate    {tool, lease, user, name}   -> {state: "ready", slot, url} | {state: "starting", slot}
  POST /release     {lease}                     the turn is over: their sign-in goes, the browser is recycled
  POST /admin-open  {slot, name}                an admin signs this browser in to its tool, by hand, once
  POST /admin-close {slot}

A browser (a "slot") is one Chromium for one tool: its own Neko container, its own profile volume where
the tool's sign-in lives (swangz-ws-profile-<slot>), its own path and WebRTC port. Browsers are listed in the config, because each
must be signed in to its tool by an admin once. Containers only run while needed: started for the first
turn, recycled after every turn (started fresh, still signed in), stopped when idle.

Every container start gets a new random Neko API token that only this agent knows; there is no fixed
Neko password anywhere. A person gets a Neko sign-in made for their turn, deleted when the turn ends —
and if Neko doesn't answer then, the container is removed instead, so a turn that's over is over.

Standard library only. Linux, Python 3.10+, Docker.

  python3 agent.py serve  [--config /etc/swangz-workspace/agent.json]
  python3 agent.py caddy  [--config …]    print the Caddy routes for the agent and every browser
  python3 agent.py check  [--config …]    check the config, Docker and the image
"""

import argparse
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_CONFIG = "/etc/swangz-workspace/agent.json"
DEFAULTS = {
    "listen": "127.0.0.1:8790",
    "image": "ghcr.io/m1k1o/neko/chromium:latest",
    "memory": "2g", "cpus": "1.5", "shm": "2g", "screen": "1600x900@30",
    "http_port_base": 8100, "webrtc_port_base": 59100,
    "idle_minutes": 15,  # a free browser that stays unused this long is stopped, to give the RAM back
    "max_running": 0,  # browsers running at once on the whole server, all tools together (0 = no limit)
    "start_timeout": 120,  # seconds a browser may take to start before it counts as failed
    "admin_minutes": 30,  # an admin's sign-in session on a browser ends by itself after this
    "recycle": True,  # restart a browser after every turn, so the next person gets a fresh window
    "fresh_start": False,  # open the tool's start page instead of restoring the last tabs (see WORKSPACE.md)
    "gateway_ip": "",  # when set, Caddy only lets this address reach the agent
}
SWEEP_SECONDS = 15
NEKO_TIMEOUT = 10
TOOL_ID = re.compile(r"[a-z0-9-]{1,60}")
USER = re.compile(r"[a-z0-9-]{1,40}")
LEASE = re.compile(r"[A-Za-z0-9:._-]{1,80}")

# Neko's own Chromium policy (apps/chromium/policies.json), with what Swangz needs on top: cookies are
# kept so the browser stays signed in, and developer tools stay off so nobody can copy the session out.
POLICY = {
    "AutofillAddressEnabled": False, "AutofillCreditCardEnabled": False, "BrowserSignin": 0,
    "DefaultNotificationsSetting": 2, "DeveloperToolsAvailability": 2, "EditBookmarksEnabled": False,
    "FullscreenAllowed": True, "IncognitoModeAvailability": 1, "SyncDisabled": True, "AutoplayAllowed": True,
    "BrowserAddPersonEnabled": False, "BrowserGuestModeEnabled": False, "DefaultPopupsSetting": 2,
    "DownloadRestrictions": 3, "VideoCaptureAllowed": True, "AllowFileSelectionDialogs": False,
    "PromptForDownloadLocation": False, "BookmarkBarEnabled": False, "PasswordManagerEnabled": False,
    "BrowserLabsEnabled": False, "CommandLineFlagSecurityWarningsEnabled": False,
    "URLAllowlist": ["file:///home/neko/Downloads"],
    "URLBlocklist": ["file://*", "chrome://policy", "chrome://settings", "chrome://flags", "chrome://inspect"],
    "ExtensionInstallForcelist": ["ddkjiahejlhfcafbddmgiahcphecmpfh;https://clients2.google.com/service/update2/crx",
                                  "mnjggcdmjocbbbhaepdhchncahnbgone;https://clients2.google.com/service/update2/crx"],
    "ExtensionInstallAllowlist": ["ddkjiahejlhfcafbddmgiahcphecmpfh", "mnjggcdmjocbbbhaepdhchncahnbgone"],
    "ExtensionInstallBlocklist": ["*"],
    "DefaultCookiesSetting": 1,
    "RestoreOnStartup": 1,
}

STAFF = {"is_admin": False, "can_login": True, "can_connect": True, "can_watch": True, "can_host": True,
         "can_share_media": False, "can_access_clipboard": True, "sends_inactive_cursor": True,
         "can_see_inactive_cursors": False}
ADMIN = {**STAFF, "is_admin": True, "can_see_inactive_cursors": True}


class ConfigError(Exception):
    pass


class AgentError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra  # sent back alongside the error


def load_config(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return check_config(raw)


def check_config(raw):
    cfg = {**DEFAULTS, **raw}
    for key in ("token", "public_url", "public_ip", "data"):
        if not cfg.get(key):
            raise ConfigError(f"'{key}' is required")
    if len(cfg["token"]) < 32:
        raise ConfigError("'token' must be at least 32 characters — use: openssl rand -hex 32")
    if not cfg["public_url"].startswith("https://"):
        raise ConfigError("'public_url' must start with https://")
    cfg["public_url"] = cfg["public_url"].rstrip("/")
    if type(cfg["max_running"]) is not int or cfg["max_running"] < 0:
        raise ConfigError("'max_running' is how many browsers may run at once, a whole number (0 = no limit)")
    browsers, numbers = {}, set()
    for tool, spec in (cfg.get("tools") or {}).items():
        if not TOOL_ID.fullmatch(tool):
            raise ConfigError(f"tool id {tool!r}: use the gateway's tool id (lowercase letters, digits, dashes)")
        start_url = str(spec.get("start_url") or "")
        if start_url and not start_url.startswith(("https://", "http://")):
            raise ConfigError(f"{tool}: start_url must be a web address")
        for n in spec.get("browsers") or []:
            if not isinstance(n, int) or not 1 <= n <= 99:
                raise ConfigError(f"{tool}: browser numbers are whole numbers from 1 to 99")
            if n in numbers:
                raise ConfigError(f"browser number {n} is used twice — every browser needs its own number")
            numbers.add(n)
            slot = f"{tool}-{n}"
            browsers[slot] = {"slot": slot, "tool": tool, "n": n, "start_url": start_url,
                              "fresh_start": bool(spec.get("fresh_start", cfg["fresh_start"]))}
    if not browsers:
        raise ConfigError("no browsers: list them under 'tools', e.g. {\"chatgpt\": {\"browsers\": [1, 2]}}")
    cfg["browsers"] = browsers
    return cfg


def container_name(slot):
    return "swangz-ws-" + slot


def profile_volume(slot):
    return "swangz-ws-profile-" + slot


def policy_for(browser):
    policy = dict(POLICY)
    if browser["start_url"]:
        policy["NewTabPageLocation"] = browser["start_url"]
        policy["HomepageLocation"] = browser["start_url"]
        if browser["fresh_start"]:  # the tool's page every time; only for tools whose sign-in survives that
            policy.update(RestoreOnStartup=4, RestoreOnStartupURLs=[browser["start_url"]])
    return policy


class DockerError(Exception):
    pass


class Docker:
    """The few Docker commands the agent needs, through the docker CLI — argument lists, never a shell."""

    def __init__(self, binary="docker"):
        self.binary = binary

    def _run(self, *args):
        try:
            return subprocess.run([self.binary, *args], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DockerError(f"docker {args[0]}: {exc}") from None

    def ok(self):
        try:
            return self._run("version", "--format", "{{.Server.Version}}").returncode == 0
        except DockerError:
            return False

    def image_present(self, image):
        return self._run("image", "inspect", image).returncode == 0

    def running(self, name):
        p = self._run("inspect", "--format", "{{.State.Running}}", name)
        return p.returncode == 0 and p.stdout.strip() == "true"

    def remove(self, name):
        """Gone afterwards, whether it existed or not. Raises only when Docker itself fails."""
        p = self._run("rm", "-f", name)
        if p.returncode != 0 and "no such container" not in p.stderr.lower():
            raise DockerError(p.stderr.strip() or "docker rm failed")

    def run(self, name, args):
        p = self._run("run", "-d", "--name", name, *args)
        if p.returncode != 0:
            raise DockerError(p.stderr.strip() or "docker run failed")


class Agent:
    def __init__(self, cfg, docker=None, neko_base=None):
        self.cfg = cfg
        self.docker = docker or Docker()
        self._neko_base = neko_base  # tests point each browser at a stand-in
        self.lock = threading.RLock()
        for sub in ("policies", "env"):
            os.makedirs(os.path.join(cfg["data"], sub), exist_ok=True)
        self.state_path = os.path.join(cfg["data"], "state.json")
        self.slots = {slot: self._blank() for slot in cfg["browsers"]}
        self._load()

    @staticmethod
    def _blank():
        return {"lease": None, "kind": None, "user": "", "name": "", "since": 0.0,
                "token": "", "started": 0.0, "last_used": 0.0, "status": "stopped"}

    # ------------------------------------------------------------ state that survives a restart

    def _load(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                saved = json.load(f)
        except (FileNotFoundError, ValueError):
            saved = {}
        for slot, s in saved.items():
            if slot in self.slots:
                self.slots[slot].update({k: s[k] for k in self._blank() if k in s})
        # a container this agent can't talk to (no token) is removed; a held browser restarts when asked
        for slot, s in self.slots.items():
            name = container_name(slot)
            try:
                if self.docker.running(name) and s["token"]:
                    s["status"] = "starting"  # its health is checked before anyone is sent in
                    continue
                self.docker.remove(name)
            except DockerError as exc:
                log(f"start-up: {slot}: {exc}")
            s.update(status="stopped", token="")
        self._save()

    def _save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.slots, f)
        os.chmod(tmp, 0o600)  # holds each browser's API token
        os.replace(tmp, self.state_path)

    # ------------------------------------------------------------ containers

    def neko_base(self, slot):
        if self._neko_base:
            return self._neko_base(slot)
        return f"http://127.0.0.1:{self.cfg['http_port_base'] + self.cfg['browsers'][slot]['n']}/{slot}"

    def _start(self, slot):
        cfg, b, s = self.cfg, self.cfg["browsers"][slot], self.slots[slot]
        token = secrets.token_hex(32)
        policy = os.path.join(cfg["data"], "policies", slot + ".json")
        with open(policy, "w", encoding="utf-8") as f:
            json.dump(policy_for(b), f, indent=2)
        http_port, rtc = cfg["http_port_base"] + b["n"], cfg["webrtc_port_base"] + b["n"]
        env = {"NEKO_MEMBER_PROVIDER": "object", "NEKO_SESSION_API_TOKEN": token, "NEKO_SERVER_PROXY": "true",
               "NEKO_SERVER_PATH_PREFIX": "/" + slot, "NEKO_WEBRTC_ICELITE": "true",
               "NEKO_WEBRTC_NAT1TO1": cfg["public_ip"], "NEKO_WEBRTC_UDPMUX": str(rtc),
               "NEKO_WEBRTC_TCPMUX": str(rtc), "NEKO_DESKTOP_SCREEN": cfg["screen"]}
        env_file = os.path.join(cfg["data"], "env", slot + ".env")  # not on the command line, where ps shows it
        fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(f"{k}={v}\n" for k, v in env.items()))
        name = container_name(slot)
        self.docker.remove(name)
        self.docker.run(name, [
            # --pull never: a missing image fails at once with a clear error, instead of a long download
            # while every other request waits ("agent.py check" says when the image needs pulling)
            "--pull", "never", "--label", "swangz.workspace=1", "--label", "swangz.browser=" + slot, "--restart", "no",
            "--shm-size", cfg["shm"], "--memory", cfg["memory"], "--cpus", str(cfg["cpus"]), "--pids-limit", "1024",
            "-p", f"127.0.0.1:{http_port}:8080", "-p", f"{rtc}:{rtc}/udp", "-p", f"{rtc}:{rtc}/tcp",
            # the tool's sign-in lives here. A named volume: Docker gives it the browser's own owner
            # (uid 1000) from the image, and it outlives every container that uses it
            "-v", f"{profile_volume(slot)}:/home/neko/.config/chromium",
            "-v", f"{policy}:/etc/chromium/policies/managed/policies.json:ro",
            "--env-file", env_file, cfg["image"]])
        s.update(token=token, started=time.time(), status="starting")

    def _stop(self, slot):
        self.docker.remove(container_name(slot))
        self.slots[slot].update(token="", status="stopped")

    def _running_besides(self, slot):
        return [sl for sl, s in self.slots.items() if sl != slot and s["status"] != "stopped"]

    def _make_room(self, slot):
        """Before a browser starts on a server already running max_running: the free browsers unused the
        longest stop, whichever tool they're for. When every running browser is someone's, it's full."""
        cap = self.cfg["max_running"]
        up = self._running_besides(slot)
        if not cap or len(up) < cap:
            return
        free = sorted((sl for sl in up if not self.slots[sl]["lease"]),
                      key=lambda sl: max(self.slots[sl]["last_used"], self.slots[sl]["started"]))
        need = len(up) - cap + 1
        if len(free) < need:
            raise AgentError(409, f"the workspace server is full: all {cap} browsers it runs at once are in use",
                             full="server")
        for sl in free[:need]:
            self._stop(sl)

    def _healthy(self, slot):
        try:
            with urllib.request.urlopen(self.neko_base(slot) + "/health", timeout=3) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _ready(self, slot):
        """True when the browser is up and answering; False while it starts (starting it if need be)."""
        s = self.slots[slot]
        if not s["token"] or not self.docker.running(container_name(slot)):
            self._make_room(slot)
            self._start(slot)
            return False
        if self._healthy(slot):
            s["status"] = "running"
            return True
        if time.time() - s["started"] > self.cfg["start_timeout"]:
            self._stop(slot)
            raise AgentError(503, f"{slot} didn't start within {self.cfg['start_timeout']} seconds")
        s["status"] = "starting"
        return False

    # ------------------------------------------------------------ Neko

    def _neko(self, slot, method, path, body=None, ok=(200, 204)):
        req = urllib.request.Request(self.neko_base(slot) + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + self.slots[slot]["token"],
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=NEKO_TIMEOUT) as resp:
                status = resp.status
                resp.read(64 * 1024)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        except (urllib.error.URLError, OSError) as exc:
            raise AgentError(502, f"{slot} did not answer ({getattr(exc, 'reason', exc)})") from None
        if status not in ok:
            raise AgentError(502, f"{slot} answered {method} {path} with {status}")
        return status

    def _sign_in(self, slot, user, name, profile):
        """A Neko sign-in for this person, with a new password. -> the link that uses it."""
        password = secrets.token_urlsafe(18)
        profile = {**profile, "name": name}
        self._neko(slot, "POST", f"/api/sessions/{user}/disconnect", ok=(204, 404))  # an older tab lets go
        if self._neko(slot, "POST", "/api/members", {"username": user, "password": password, "profile": profile},
                      ok=(200, 422)) == 422:  # still there from before: it gets this password, not trust
            self._neko(slot, "POST", f"/api/members/{user}", profile, ok=(204,))
            self._neko(slot, "POST", f"/api/members/{user}/password", {"password": password}, ok=(204,))
        query = urllib.parse.urlencode({"usr": user, "pwd": password})
        return f"{self.cfg['public_url']}/{slot}/?{query}"

    def _revoke(self, slot):
        """End whoever holds this browser. Their sign-in is deleted (Neko drops the session); if Neko
        doesn't answer, the container goes instead. Only then is the browser free."""
        s = self.slots[slot]
        gone = False
        if s["token"] and s["user"]:
            try:
                self._neko(slot, "DELETE", f"/api/members/{s['user']}", ok=(204, 404))
                gone = True
            except AgentError:
                pass
        if not gone:
            self._stop(slot)  # raises DockerError if even that fails: the lease is kept, the caller retries
        s.update(lease=None, kind=None, user="", name="", since=0.0, last_used=time.time())
        cap = self.cfg["max_running"]
        if cap and len(self._running_besides(slot)) >= cap:
            try:
                self._stop(slot)  # no room to keep it ready: it starts again when it's next needed
            except DockerError as exc:
                log(f"release {slot}: {exc}")  # still free; the idle sweep stops it
        elif self.cfg["recycle"]:
            try:
                self._start(slot)  # a fresh window for the next person, still signed in to the tool
            except DockerError:
                s.update(token="", status="stopped")  # started again on the next turn

    # ------------------------------------------------------------ the API

    def _slot_of(self, lease):
        return next((slot for slot, s in self.slots.items() if s["lease"] == lease), None)

    def allocate(self, tool, lease, user, name):
        with self.lock:
            if not any(b["tool"] == tool for b in self.cfg["browsers"].values()):
                raise AgentError(404, f"no browsers for {tool} on this workspace server")
            slot = self._slot_of(lease)
            if not slot:  # back with a new turn before the old one was released: same browser
                slot = next((sl for sl, s in self.slots.items() if s["kind"] == "staff" and s["user"] == user
                             and self.cfg["browsers"][sl]["tool"] == tool), None)
            if not slot:
                rank = {"running": 0, "starting": 1, "stopped": 2}
                free = sorted((sl for sl, s in self.slots.items() if not s["lease"]
                               and self.cfg["browsers"][sl]["tool"] == tool), key=lambda sl: rank[self.slots[sl]["status"]])
                if not free:
                    raise AgentError(409, f"all {tool} browsers are in use")
                slot = free[0]
                self.slots[slot].update(since=time.time())
            self.slots[slot].update(lease=lease, kind="staff", user=user, name=name)
            try:
                if not self._ready(slot):
                    return 202, {"state": "starting", "slot": slot}
                return 200, {"state": "ready", "slot": slot, "url": self._sign_in(slot, user, name, STAFF)}
            except AgentError as exc:
                if exc.status in (409, 503):  # it failed to start, or the server had no room: it's free again
                    self.slots[slot].update(lease=None, kind=None, user="", name="", since=0.0)
                raise
            finally:
                self._save()

    def release(self, lease):
        with self.lock:
            slot = self._slot_of(lease)
            if not slot:
                return 404, {"error": "no browser holds that lease"}
            try:
                self._revoke(slot)
            finally:
                self._save()
            return 200, {"ok": True, "slot": slot}

    def admin_open(self, slot, name):
        with self.lock:
            s = self.slots.get(slot)
            if s is None:
                raise AgentError(404, "no such browser")
            if s["lease"] and s["kind"] != "admin":
                raise AgentError(409, f"{s['name']} is using {slot} right now")
            if not s["lease"]:
                s.update(lease="admin:" + slot, kind="admin", user="admin-" + secrets.token_hex(3), name=name,
                         since=time.time())
            try:
                if not self._ready(slot):
                    return 202, {"state": "starting", "slot": slot}
                return 200, {"state": "ready", "slot": slot, "url": self._sign_in(slot, s["user"], name, ADMIN)}
            except AgentError as exc:
                if exc.status in (409, 503):
                    s.update(lease=None, kind=None, user="", name="", since=0.0)
                raise
            finally:
                self._save()

    def admin_close(self, slot):
        return self.release("admin:" + slot)

    def status(self):
        with self.lock:
            out = []
            for slot, s in self.slots.items():
                b = self.cfg["browsers"][slot]
                holder = {"kind": s["kind"], "name": s["name"], "user": s["user"], "lease": s["lease"],
                          "since": s["since"]} if s["lease"] else None
                out.append({"slot": slot, "tool": b["tool"], "n": b["n"], "state": s["status"],
                            "holder": holder, "last_used": s["last_used"] or None})
            capacity = {}
            for b in self.cfg["browsers"].values():
                capacity[b["tool"]] = capacity.get(b["tool"], 0) + 1
            return {"browsers": sorted(out, key=lambda r: (r["tool"], r["n"])), "capacity": capacity}

    def health(self):
        docker = self.docker.ok()
        with self.lock:
            running = sum(1 for s in self.slots.values() if s["status"] != "stopped")
        return {"ok": docker, "docker": docker, "running": running, "browsers": len(self.slots),
                "max_running": self.cfg["max_running"]}

    # ------------------------------------------------------------ housekeeping

    def sweep(self):
        """Admin sessions that ran out end; containers that died are noticed; idle browsers stop."""
        with self.lock:
            now = time.time()
            for slot, s in self.slots.items():
                try:
                    if s["kind"] == "admin" and now - s["since"] > self.cfg["admin_minutes"] * 60:
                        self._revoke(slot)
                    elif s["status"] != "stopped" and not self.docker.running(container_name(slot)):
                        s.update(token="", status="stopped")  # restarted when it's next needed
                    elif not s["lease"] and s["status"] != "stopped" and \
                            now - max(s["last_used"], s["started"]) > self.cfg["idle_minutes"] * 60:
                        self._stop(slot)
                except (AgentError, DockerError) as exc:
                    log(f"sweep {slot}: {exc}")
            self._save()

    def start_sweeping(self, every=SWEEP_SECONDS):
        def loop():
            while True:
                time.sleep(every)
                try:
                    self.sweep()
                except Exception as exc:  # keep sweeping whatever happened
                    log(f"sweep failed: {exc!r}")

        threading.Thread(target=loop, name="sweep", daemon=True).start()


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SwangzWorkspaceAgent/1.0"
    sys_version = ""
    agent = None

    def log_message(self, fmt, *args):
        if os.environ.get("SWANGZ_WORKSPACE_ACCESS_LOG", "1") != "0":
            log("%s %s" % (self.address_string(), fmt % args))

    def do_GET(self):
        self._route()

    do_POST = do_GET

    def _route(self):
        agent = self.agent
        path = self.path.split("?")[0]
        try:
            if not hmac.compare_digest(self.headers.get("authorization") or "", "Bearer " + agent.cfg["token"]):
                return self._reply(401, {"error": "wrong or missing token"})
            if self.command == "GET" and path == "/health":
                return self._reply(200, agent.health())
            if self.command == "GET" and path == "/status":
                return self._reply(200, agent.status())
            if self.command != "POST":
                return self._reply(404, {"error": "not found"})
            body = self._body()
            if path == "/allocate":
                tool, lease = str(body.get("tool") or ""), str(body.get("lease") or "")
                user, name = str(body.get("user") or ""), str(body.get("name") or "").strip()[:80]
                if not (TOOL_ID.fullmatch(tool) and LEASE.fullmatch(lease) and USER.fullmatch(user)):
                    return self._reply(400, {"error": "tool, lease and user are required"})
                return self._reply(*agent.allocate(tool, lease, user, name or user))
            if path == "/release":
                lease = str(body.get("lease") or "")
                if not LEASE.fullmatch(lease):
                    return self._reply(400, {"error": "lease is required"})
                return self._reply(*agent.release(lease))
            if path in ("/admin-open", "/admin-close"):
                slot = str(body.get("slot") or "")
                if not TOOL_ID.fullmatch(slot):
                    return self._reply(400, {"error": "slot is required"})
                if path == "/admin-open":
                    return self._reply(*agent.admin_open(slot, str(body.get("name") or "admin").strip()[:80]))
                return self._reply(*agent.admin_close(slot))
            return self._reply(404, {"error": "not found"})
        except AgentError as exc:
            return self._reply(exc.status, {"error": str(exc), **exc.extra})
        except DockerError as exc:
            log(f"docker: {exc}")
            return self._reply(503, {"error": f"docker: {exc}"})
        except ValueError:
            return self._reply(400, {"error": "the body must be JSON"})
        except Exception as exc:
            log(f"{self.command} {path} failed: {exc!r}")
            return self._reply(500, {"error": "internal error"})

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        if n > 64 * 1024:
            raise ValueError("too large")
        data = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return data

    def _reply(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def make_server(agent, listen=None):
    host, _, port = (listen or agent.cfg["listen"]).rpartition(":")
    handler = type("BoundHandler", (Handler,), {"agent": agent})
    server = ThreadingHTTPServer((host or "127.0.0.1", int(port)), handler)
    server.daemon_threads = True
    return server


def caddy_routes(cfg):
    host = urllib.parse.urlsplit(cfg["public_url"]).netloc
    lines = [f"{host} {{", "    # the agent: only the gateway may reach it, and only with the token",
             "    handle_path /agent/* {"]
    if cfg["gateway_ip"]:
        lines += [f"        @outside not remote_ip {cfg['gateway_ip']}", "        respond @outside 403"]
    lines += [f"        reverse_proxy {cfg['listen']}", "    }"]
    for slot, b in sorted(cfg["browsers"].items(), key=lambda kv: kv[1]["n"]):
        # `handle`, not `handle_path`: Neko expects its path prefix to arrive intact
        lines += [f"    handle /{slot}/* {{", f"        reverse_proxy 127.0.0.1:{cfg['http_port_base'] + b['n']}", "    }"]
    lines += ["    handle {", "        respond 404", "    }", "}"]
    return "\n".join(lines)


def log(message):
    sys.stderr.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    sys.stderr.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent.py", description="Swangz Workspace Agent")
    parser.add_argument("command", choices=("serve", "caddy", "check"))
    parser.add_argument("--config", default=os.environ.get("SWANGZ_WORKSPACE_CONFIG", DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except (OSError, ValueError, ConfigError) as exc:
        sys.exit(f"config {args.config}: {exc}")
    if args.command == "caddy":
        print(caddy_routes(cfg))
        return
    docker = Docker()
    if args.command == "check":
        cap = cfg["max_running"]
        print(f"config ok: {len(cfg['browsers'])} browser(s)" + (f", at most {cap} running at once" if cap else ""))
        for slot, b in sorted(cfg["browsers"].items(), key=lambda kv: kv[1]["n"]):
            print(f"  {slot:24} {cfg['public_url']}/{slot}/   webrtc port {cfg['webrtc_port_base'] + b['n']} (udp+tcp)")
        print("docker:", "ok" if docker.ok() else "NOT REACHABLE — is this user in the docker group?")
        print("image:", cfg["image"], "present" if docker.ok() and docker.image_present(cfg["image"])
              else "missing — run: docker pull " + cfg["image"])
        return
    agent = Agent(cfg, docker)
    agent.start_sweeping()
    server = make_server(agent)
    log(f"Swangz Workspace Agent on {cfg['listen']} — {len(cfg['browsers'])} browser(s), image {cfg['image']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
