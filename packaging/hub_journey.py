"""Steps both packaged-app journeys share (packaging/macos_journey.py, packaging/windows/installer_e2e.py).

Deliverable 5, the company browser workspace: the installed app opens a granted tool in a real Google Chrome window on
the person's own workspace folder (never the default browser), the folder is marked for this person and this device,
and the Hub records the open. Deliverable 6, F-18 (D-023): a request sent with the installed app's own credential is
not stored by default; once the trust area turns storage on, a role with it reads the prompt and a role without it
gets it withheld; storage goes back off.

Everything talks to the CI fixture Hub over HTTP (tests/fake_upstream.py answers for the provider). The console
accounts are the fixture's own (tests/support.py); there is no real account or credential here. The device key is
read from the app's credential helper into memory only: it is never printed, logged or written to the evidence.
Chrome may fetch the tool's public start page; nobody signs in to it.
"""
import http.cookiejar
import json
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

# The workspace folder's name and marker (swangz_client/browser_profiles.py FOLDER and MARKER). Only the launcher may
# import that module, so they are restated here; tests/test_hub_journey.py checks they still agree.
FOLDER = re.compile(r"[0-9a-f]{32}\Z")
MARKER = ".swangz-profile.json"

TOOL = "canva"  # a website tool on the company plan, not a shared account: it opens in the workspace window
F18_MODEL = "claude-haiku-4-5"


class Console:
    """A control-room session as one of the fixture's console users."""

    def __init__(self, base, who):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, out = self.call("POST", "/login", {"username": who + "@swangzavenue.com", "password": who + "-password"})
        if status != 200:
            raise SystemExit(f"console sign-in as {who} failed: {status}")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + "/admin/api" + path, data=data, method=method,
                                     headers={"content-type": "application/json", "x-gateway-admin": "1"})
        try:
            with self.opener.open(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"raw": raw.decode("utf-8", "replace")[:300]}


def grant(owner, person_id, tool=TOOL):
    """The admin's part: the company plan is active and this person is assigned the tool (idempotent)."""
    a = owner.call("PUT", f"/subscriptions/{tool}", {"state": "active", "monthly_cost": 30, "seats": 5})[0]
    b = owner.call("POST", f"/people/{person_id}/tools/{tool}")[0]
    return a == 200 and b in (200, 409)


# ---------------------------------------------------------------- deliverable 5: the workspace window

def workspace_folders(data):
    root = Path(data) / "browser-profiles"
    if not root.is_dir():
        return []
    return [p for p in root.iterdir() if FOLDER.fullmatch(p.name) and (p / MARKER).is_file()]


def chrome_wrote(folder, timeout=45):
    """Chrome creates `Local State` in a user-data folder it runs on: proof the window started on this folder."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (folder / "Local State").is_file():
            return True
        time.sleep(0.5)
    return False


def close_chrome(folder):
    """End the Chrome the app started on this folder. A CLI open exits right away and cannot close the window it
    started (R-11), so the journey ends exactly the processes whose command line names this folder, and no other."""
    needle = str(folder)
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
                  "$_.CommandLine.Contains($env:SWANGZ_WS_FOLDER) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                  "-ErrorAction SilentlyContinue }")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], env={**os.environ, "SWANGZ_WS_FOLDER": needle},
                       capture_output=True, timeout=60)
    else:
        subprocess.run(["pkill", "-f", "--", "--user-data-dir=" + needle], capture_output=True, timeout=60)
    time.sleep(3)  # let the browser release its files before the uninstall checks the folder


def workspace(check, run_app, data, owner, person_id, tool=TOOL):
    """run_app(*args) -> (exit code, output) runs the installed program. check(name, ok, detail) records one step."""
    check("workspace: the admin grants a website tool", grant(owner, person_id, tool), tool)
    before = time.time() - 1
    code, out = run_app("open", tool)
    check("workspace: the installed app opens the tool in its workspace window", code == 0, f"exit {code} {out[-300:]}")
    folders = workspace_folders(data)
    check("workspace: one workspace folder, inside the app's own data folder", len(folders) == 1,
          ", ".join(p.name for p in folders))
    folder = folders[0]
    try:
        marker = json.loads((folder / MARKER).read_text(encoding="utf-8"))
        browser = json.loads((Path(data) / "manifest.json").read_text(encoding="utf-8")).get("browser") or {}
        check("workspace: the folder belongs to this person on this device (separate employee profile)",
              marker.get("person_id") == str(person_id) == browser.get("person_id")
              and marker.get("device_id") == browser.get("device_id") and marker.get("state") == "prepared",
              f"person {marker.get('person_id')}, device {marker.get('device_id')}")
        check("workspace: Google Chrome started on that folder (not the default browser)", chrome_wrote(folder), folder.name)
        status, out = owner.call("GET", f"/launches?person={person_id}&since={before}")
        opened = [r for r in out.get("items", []) if r.get("tool_id") == tool and r.get("outcome") == "opened"]
        check("workspace: the Hub records the open for this person", status == 200 and len(opened) >= 1, f"{len(opened)} open(s)")
    finally:
        close_chrome(folder)
    return folder


# ---------------------------------------------------------------- deliverable 6: F-18 in the packaged app

def device_key(program, env, cwd=None):
    """The installed app's credential helper, through a pipe (it refuses a terminal). In memory only."""
    out = subprocess.run([str(program), "key", "--for", "claude-code"], env=env, cwd=cwd, capture_output=True, timeout=120)
    return out.returncode, out.stdout.decode("utf-8", "replace").strip()


def send(base, key, text):
    body = json.dumps({"model": F18_MODEL, "max_tokens": 16, "messages": [{"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(base + "/anthropic/v1/messages", data=body, method="POST",
                                 headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01",
                                          "user-agent": "claude-cli/2.1.286 (external, cli)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def record(console, person_id, after, timeout=20):
    """The full record of this person's first request after `after`; the Hub writes it just after it answers."""
    deadline = time.monotonic() + timeout
    while True:
        status, out = console.call("GET", f"/requests?person={person_id}&after={after}&limit=5")
        items = out.get("items", []) if status == 200 else []
        if items:
            return console.call("GET", f"/requests/{items[-1]['id']}")[1]
        if time.monotonic() > deadline:
            return None
        time.sleep(0.3)


def newest(console, person_id):
    status, out = console.call("GET", f"/requests?person={person_id}&limit=1")
    items = out.get("items", []) if status == 200 else []
    return items[0]["id"] if items else 0


def f18(check, program, env, base, owner, person_id, cwd=None, withheld_role="viewer"):
    """F-18 / D-023 round trip with the installed app's own credential."""
    status, settings = owner.call("GET", "/settings")
    check("F-18: prompt and reply storage is off by default", status == 200 and settings.get("store_bodies") is False,
          f"store_bodies={settings.get('store_bodies')}")
    code, key = device_key(program, env, cwd)
    check("F-18: the installed app hands its device key to a coding agent through a pipe", code == 0 and len(key) >= 20,
          f"exit {code}")  # never the key

    off = "swangz-f18-off-" + secrets.token_hex(8)
    start = newest(owner, person_id)
    check("F-18: a request with the app's credential goes through the Hub", send(base, key, off) == 200)
    rec = record(owner, person_id, start)
    text = json.dumps(rec or {})
    check("F-18 off: the request is recorded, with no prompt or reply stored", rec is not None and off not in text
          and rec.get("prompt") is None and rec.get("reply") is None, f"request #{(rec or {}).get('id')}")

    try:
        check("F-18: the owner turns storage on", owner.call("PUT", "/settings", {"store_bodies": True})[0] == 200)
        on = "swangz-f18-on-" + secrets.token_hex(8)
        start = newest(owner, person_id)
        check("F-18 on: a second request goes through the Hub", send(base, key, on) == 200)
        rec = record(owner, person_id, start)
        check("F-18 on: a role with the trust area reads the prompt", rec is not None and on in json.dumps(rec),
              f"request #{(rec or {}).get('id')}")
        other = Console(base, withheld_role)
        seen = other.call("GET", f"/requests/{rec['id']}") if rec else (0, {})
        listed = other.call("GET", f"/requests?person={person_id}&limit=5")
        check(f"F-18 on: a role without it ({withheld_role}) gets the record with the content withheld",
              seen[0] == 200 and seen[1].get("content") == "withheld" and on not in json.dumps(seen[1])
              and listed[0] == 200 and on not in json.dumps(listed[1]), f"{seen[0]} content={seen[1].get('content')}")
    finally:
        reset = owner.call("PUT", "/settings", {"store_bodies": False})[0]
        status, settings = owner.call("GET", "/settings")
        check("F-18: storage is off again", reset == 200 and settings.get("store_bodies") is False)
