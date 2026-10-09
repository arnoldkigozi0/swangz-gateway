#!/usr/bin/env python3
"""Keep the laptop gateway online and repair its Netlify front door after tunnel changes."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from gateway.config import load_dotenv

TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com\b")


def log(message):
    print(message, flush=True)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def netlify_token():
    if os.environ.get("NETLIFY_AUTH_TOKEN"):
        return os.environ["NETLIFY_AUTH_TOKEN"]
    config = read_json(Path.home() / ".config/netlify/config.json")
    user = config.get("users", {}).get(config.get("userId"), {})
    return user.get("auth", {}).get("token", "")


def healthy(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=10) as r:
            return r.status == 200 and json.load(r).get("ok") is True
    except (OSError, ValueError):
        return False


def latest_url(path):
    try:
        matches = TUNNEL_URL.findall(Path(path).read_text(errors="replace"))
        return matches[-1] if matches else None
    except OSError:
        return None


class Netlify:
    def __init__(self, token):
        if not token:
            raise RuntimeError("No Netlify login: run netlify login, or set NETLIFY_AUTH_TOKEN.")
        self.token = token

    def api(self, method, path, body=None):
        req = urllib.request.Request("https://api.netlify.com/api/v1" + path, method=method,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Provider responses and credentials never enter the logs.
            raise RuntimeError(f"Netlify returned HTTP {exc.code}") from None

    def site(self, name):
        sites = self.api("GET", "/sites?filter=all")
        matches = [s for s in sites if s["name"] == name]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one Netlify site named {name}.")
        return matches[0]

    def begin(self, site, url):
        if not TUNNEL_URL.fullmatch(url):
            raise ValueError("Expected an HTTPS Cloudflare quick-tunnel URL.")
        self.api("PUT", f"/accounts/{site['account_id']}/env/SWANGZ_GATEWAY?site_id={site['id']}",
            {"key": "SWANGZ_GATEWAY", "values": [{"context": "all", "value": url}]})
        result = self.api("POST", f"/sites/{site['id']}/builds", {"clear_cache": False})
        return result["deploy_id"]


def sync_netlify(url, state_file, stop):
    """Persist an in-progress deployment so a service restart resumes rather than duplicating it."""
    netlify = Netlify(netlify_token())
    site = netlify.site(os.environ.get("NETLIFY_SITE", "swangz-ai"))
    state = read_json(state_file)
    public = site.get("ssl_url") or "https://" + site["name"] + ".netlify.app"
    if state.get("published_url") == url and healthy(public):
        return
    if state.get("pending_url") != url or not state.get("deploy_id"):
        deploy_id = netlify.begin(site, url)
        state.update(pending_url=url, deploy_id=deploy_id, started=time.time())
        save_json(state_file, state)
        log("Netlify is deploying the current tunnel address.")
    for _ in range(120):
        if stop.is_set():
            return
        deploy = netlify.api("GET", "/deploys/" + state["deploy_id"])
        if deploy["state"] == "ready":
            if not healthy(public):
                raise RuntimeError("Netlify deployed; its gateway health check has not recovered yet.")
            state.update(published_url=url, verified=time.time())
            state.pop("pending_url", None)
            state.pop("deploy_id", None)
            save_json(state_file, state)
            log("Netlify is healthy: " + public)
            return
        if deploy["state"] in ("error", "failed", "canceled"):
            state.pop("deploy_id", None)
            save_json(state_file, state)
            raise RuntimeError("Netlify deployment did not finish: " + deploy["state"])
        if stop.wait(5):
            return
    raise RuntimeError("Netlify deployment still pending; will resume checking later.")


class Supervisor:
    def __init__(self, env_file):
        os.environ["GATEWAY_ENV_FILE"] = str(env_file)
        load_dotenv(env_file)
        self.port = int(os.environ.get("GATEWAY_PORT") or os.environ.get("PORT") or 8787)
        self.folder = env_file.parent
        self.logs = self.folder / "logs"
        self.logs.mkdir(exist_ok=True)
        self.stop = threading.Event()
        self.children = {}
        self.files = {}
        self.url = None
        self.sync_thread = None
        self.next_sync = 0
        self.public_failures = 0
        self.local_failures = 0
        self.checked_at = 0
        self.cloudflared = shutil.which("cloudflared") or str(Path.home() / ".local/bin/cloudflared")
        if not Path(self.cloudflared).is_file():
            raise RuntimeError("cloudflared is not installed.")

    def start(self, name, args):
        self.terminate(name)
        self.files[name] = open(self.logs / (name + ".log"), "w")
        self.children[name] = subprocess.Popen(args, cwd=REPO, stdout=self.files[name],
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        log("Started " + name)
        if name == "tunnel":
            self.url = None
            self.public_failures = 0

    def terminate(self, name):
        child = self.children.pop(name, None)
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        stream = self.files.pop(name, None)
        if stream:
            stream.close()

    def ensure(self, name, args):
        if name not in self.children or self.children[name].poll() is not None:
            self.start(name, args)

    def sync(self, url):
        try:
            sync_netlify(url, self.folder / "netlify-sync.json", self.stop)
        except Exception as exc:
            log("Netlify sync will retry: " + str(exc))
        finally:
            self.next_sync = time.monotonic() + 120

    def run(self):
        local = f"http://127.0.0.1:{self.port}"
        try:
            while not self.stop.is_set():
                if os.environ.get("DEMO_PROVIDER_KEY") or os.environ.get("DEMO_MODEL") == "1":
                    self.ensure("model", [sys.executable, "tests/fake_upstream.py", "18902", "--demo"])
                self.ensure("gateway", [sys.executable, "-m", "gateway", "serve"])
                self.ensure("tunnel", [self.cloudflared, "tunnel", "--no-autoupdate", "--url", local])
                url = latest_url(self.logs / "tunnel.log")
                if url and url != self.url:
                    self.url = url
                    (self.folder / "tunnel-url.txt").write_text(url + "\n")
                    self.next_sync = 0
                    log("Current tunnel: " + url)
                if time.monotonic() - self.checked_at >= 60:
                    self.checked_at = time.monotonic()
                    local_ok = healthy(local)
                    self.local_failures = 0 if local_ok else self.local_failures + 1
                    if self.local_failures >= 3:
                        log("Gateway health failed repeatedly; restarting it.")
                        self.terminate("gateway")
                        self.local_failures = 0
                    if self.url and local_ok:
                        self.public_failures = 0 if healthy(self.url) else self.public_failures + 1
                        if self.public_failures >= 3:
                            # An offline PC should not churn through new tunnel addresses.
                            try:
                                with urllib.request.urlopen("https://www.cloudflare.com/cdn-cgi/trace", timeout=10):
                                    log("Tunnel health failed repeatedly; reconnecting.")
                                    self.terminate("tunnel")
                                    self.url = None
                            except OSError:
                                pass
                if (self.url and time.monotonic() >= self.next_sync
                        and (not self.sync_thread or not self.sync_thread.is_alive())):
                    self.sync_thread = threading.Thread(target=self.sync, args=(self.url,), daemon=True)
                    self.sync_thread.start()
                self.stop.wait(5)
        finally:
            self.stop.set()
            for name in list(self.children):
                self.terminate(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path.home() / "swangz-gateway-demo/.env")
    parser.add_argument("--sync", help="Repair Netlify for an already-running tunnel without starting services")
    args = parser.parse_args()
    if not args.env_file.is_file():
        parser.error("The demo .env file is missing.")
    if args.sync:
        load_dotenv(args.env_file)
        sync_netlify(args.sync, args.env_file.parent / "netlify-sync.json", threading.Event())
        return
    supervisor = Supervisor(args.env_file)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: supervisor.stop.set())
    supervisor.run()


if __name__ == "__main__":
    main()
