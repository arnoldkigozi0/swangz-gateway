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
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
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


class Staff:
    """A person's own browser, signed in to the staff app: it approves a device code on /device."""

    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, form=None):
        data, headers = None, {"x-swangz-app": "1"}
        if body is not None:
            data, headers["content-type"] = json.dumps(body).encode(), "application/json"
        if form is not None:
            data, headers["content-type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def approve(self, code):
        status, page = self.call("GET", "/device?code=" + urllib.parse.quote(code))
        csrf = re.search(r"name=csrf value='([0-9a-f]+)'", page)
        if status != 200 or not csrf:
            return status
        return self.call("POST", "/device", form={"code": code, "csrf": csrf.group(1), "owner": "personal",
                                                  "decision": "approve"})[0]


def add_person(owner, base, name, email):
    """The admin adds a second person and sends a sign-in link; the person sets a password with it (a throwaway one,
    for this fixture Hub only). Returns (person id, their signed-in browser)."""
    status, out = owner.call("POST", "/people", {"name": name, "email": email, "department": "Creative"})
    if status != 200:
        raise RuntimeError(f"adding {email} failed: {status} {out}")
    pid = out["id"]
    status, out = owner.call("POST", f"/people/{pid}/invite")
    if status != 200:
        raise RuntimeError(f"the sign-in link for {email} failed: {status} {out}")
    staff = Staff(base)
    status, text = staff.call("POST", "/api/welcome", {"token": out["link"].rsplit("/", 1)[1],
                                                       "password": "journey-" + secrets.token_hex(12)})
    if status != 200:
        raise RuntimeError(f"{email} could not set a password: {status} {text[:300]}")
    return pid, staff


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


def marker_of(folder):
    return json.loads((folder / MARKER).read_text(encoding="utf-8"))


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


def kept(check, data, folder, marker, when):
    """The person's workspace folder and its marker are still there, unchanged (after an upgrade, after sign out)."""
    now = [p.name for p in workspace_folders(data)]
    same = (folder / MARKER).is_file() and marker_of(folder) == marker
    check(f"workspace: {when}, the person's folder and its marker are kept unchanged", folder.name in now and same,
          f"{folder.name} in [{', '.join(now)}]")


def second_person(check, enrol, run_app, data, owner, base, first, first_marker, tool=TOOL):
    """A second person signs this device in and opens the same tool: they get a workspace folder of their own,
    marked for them, and the first person's folder is left as it was. enrol(approve) signs the installed app in,
    with approve(code) approving the code as the second person; it returns the app's device id."""
    pid, staff = add_person(owner, base, "Okello Brian", "brian.okello@swangzavenue.com")
    check("second person: the admin adds them and they sign in to the staff app", bool(pid), f"person {pid}")
    check("second person: the admin grants them the same tool", grant(owner, pid, tool), tool)
    device_id = enrol(staff.approve)
    check("second person: the installed app signs in as them", bool(device_id), str(device_id))
    before = time.time() - 1
    code, out = run_app("open", tool)
    check("second person: the installed app opens the tool in its workspace window", code == 0, f"exit {code} {out[-300:]}")
    folders = workspace_folders(data)
    theirs = [p for p in folders if p != first]
    check("second person: a separate workspace folder of their own, beside the first person's",
          len(folders) == 2 and first in folders and len(theirs) == 1, ", ".join(p.name for p in folders))
    folder = theirs[0]
    try:
        marker = marker_of(folder)
        check("second person: their folder is marked for them on this device, not for the first person",
              marker.get("person_id") == str(pid) != first_marker.get("person_id") and marker.get("device_id") == device_id,
              f"person {marker.get('person_id')}, device {marker.get('device_id')}")
        check("second person: Google Chrome started on their folder", chrome_wrote(folder), folder.name)
        status, out = owner.call("GET", f"/launches?person={pid}&since={before}")
        opened = [r for r in out.get("items", []) if r.get("tool_id") == tool and r.get("outcome") == "opened"]
        check("second person: the Hub records the open under their name", status == 200 and len(opened) >= 1,
              f"{len(opened)} open(s)")
    finally:
        close_chrome(folder)
    kept(check, data, first, first_marker, "with a second person on this device")
    return pid, folder


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
    """(status, record) of this person's first request after `after`; the Hub writes it just after it answers.
    A refused list call raises; a record that never appears is (None, None)."""
    deadline = time.monotonic() + timeout
    while True:
        status, out = console.call("GET", f"/requests?person={person_id}&after={after}&limit=5")
        if status != 200:
            raise RuntimeError(f"listing requests failed: {status} {out}")
        items = out.get("items", [])
        if items:
            return console.call("GET", f"/requests/{items[-1]['id']}")
        if time.monotonic() > deadline:
            return None, None
        time.sleep(0.3)


def newest(console, person_id):
    """The id of this person's newest request; 0 only when the Hub answers and they have none. A refusal raises."""
    status, out = console.call("GET", f"/requests?person={person_id}&limit=1")
    if status != 200 or not isinstance(out.get("items"), list):
        raise RuntimeError(f"listing requests failed: {status} {out}")
    return out["items"][0]["id"] if out["items"] else 0


def read_bytes(path, tries=20):
    """The file's bytes. On Windows a byte range SQLite holds an exclusive lock on cannot be read for a moment."""
    for _ in range(tries):
        try:
            return Path(path).read_bytes()
        except PermissionError:
            time.sleep(0.5)
    return None


def traces(hub_data, logs, marker):
    """Where `marker` appears in the Hub's own storage: every file in its data folder byte for byte (the database, its
    WAL and shared-memory files, anything else), every stored body blob decompressed (including blobs no request
    points at any more) and the Hub's log files. An empty list means the text was not kept anywhere."""
    needle, found = marker.encode(), []
    for path in sorted(Path(hub_data).rglob("*")):
        if path.is_file():
            data = read_bytes(path)
            if data is None:
                found.append("unreadable " + path.name)  # a file the scan cannot read fails the step, it is not skipped
            elif needle in data:
                found.append(path.name)
    db = Path(hub_data) / "gateway.db"
    if db.is_file():
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            for digest, data in con.execute("SELECT hash, data FROM blobs"):
                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    pass
                if needle in data:
                    found.append("blob " + digest[:12])
        finally:
            con.close()
    for log in logs:
        if Path(log).is_file() and needle in (read_bytes(log) or b""):
            found.append("log " + Path(log).name)
    return found


def f18(check, program, env, base, owner, person_id, hub_data, logs=(), cwd=None, withheld_role="viewer"):
    """F-18 / D-023 round trip with the installed app's own credential. hub_data is the fixture Hub's data folder and
    logs its log files: with storage off the prompt must be nowhere in them."""
    status, settings = owner.call("GET", "/settings")
    check("F-18: prompt and reply storage is off by default", status == 200 and settings.get("store_bodies") is False,
          f"store_bodies={settings.get('store_bodies')}")
    code, key = device_key(program, env, cwd)
    check("F-18: the installed app hands its device key to a coding agent through a pipe", code == 0 and len(key) >= 20,
          f"exit {code}")  # never the key

    off = "swangz-f18-off-" + secrets.token_hex(8)
    start = newest(owner, person_id)
    check("F-18: a request with the app's credential goes through the Hub", send(base, key, off) == 200)
    status, rec = record(owner, person_id, start)
    check("F-18 off: the owner's record lookup answers", status == 200 and rec is not None, f"status {status}")
    text = json.dumps(rec)
    check("F-18 off: the request is recorded, with no prompt and an empty reply", off not in text
          and rec.get("prompt") is None and not rec.get("reply"), f"request #{rec.get('id')}")
    leaks = traces(hub_data, logs, off)
    check("F-18 off: the prompt is nowhere in the Hub's database, WAL, stored bodies (orphans too) or logs", not leaks,
          ", ".join(leaks) or "not found")

    try:
        check("F-18: the owner turns storage on", owner.call("PUT", "/settings", {"store_bodies": True})[0] == 200)
        on = "swangz-f18-on-" + secrets.token_hex(8)
        start = newest(owner, person_id)
        check("F-18 on: a second request goes through the Hub", send(base, key, on) == 200)
        status, rec = record(owner, person_id, start)
        check("F-18 on: a role with the trust area reads the prompt", status == 200 and rec is not None
              and on in json.dumps(rec), f"status {status}, request #{(rec or {}).get('id')}")
        check("F-18 on: the same scan finds the stored prompt (the scan can see what it looks for)",
              bool(traces(hub_data, (), on)))
        other = Console(base, withheld_role)
        seen = other.call("GET", f"/requests/{rec['id']}")
        listed = other.call("GET", f"/requests?person={person_id}&limit=5")
        check(f"F-18 on: a role without it ({withheld_role}) gets the record with the content withheld",
              seen[0] == 200 and seen[1].get("content") == "withheld" and on not in json.dumps(seen[1])
              and listed[0] == 200 and on not in json.dumps(listed[1]), f"{seen[0]} content={seen[1].get('content')}")
    finally:
        reset = owner.call("PUT", "/settings", {"store_bodies": False})[0]
        status, settings = owner.call("GET", "/settings")
        check("F-18: storage is off again", reset == 200 and settings.get("store_bodies") is False)
