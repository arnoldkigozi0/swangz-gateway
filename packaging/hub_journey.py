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
LATER_TOOL = "perplexity"  # granted and taken away while the app is closed (grants_after_restart)
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

def offered_apps(data):
    """The website tools the app's last sync was offered (its saved manifest), as a set of tool ids."""
    try:
        manifest = json.loads((Path(data) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {a.get("id") for a in manifest.get("apps") or []}


def grants_after_restart(check, start, stop, data, owner, person_id, tool=LATER_TOOL, timeout=60):
    """With the app closed, the admin grants a tool and later takes it away. Nothing on the device changes while it is
    closed; starting the app again (it syncs on start, nobody runs sync) is what offers the tool, and then stops
    offering it. `start()` returns the running program, `stop(proc)` closes it."""
    def settle(wanted):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if wanted(offered_apps(data)):
                return True
            time.sleep(0.5)
        return False

    before = offered_apps(data)
    granted = tool not in before and grant(owner, person_id, tool)
    unchanged = tool not in offered_apps(data)
    proc = start()
    try:
        appeared = settle(lambda apps: tool in apps)
    finally:
        stop(proc)
    check("a grant made while the app was closed is offered after the app starts again", granted and unchanged and appeared,
          f"{tool}: before {tool in before}, closed {not unchanged}, after start {appeared}")
    removed = owner.call("DELETE", f"/people/{person_id}/tools/{tool}")[0] == 200
    kept = tool in offered_apps(data)
    proc = start()
    try:
        gone = settle(lambda apps: tool not in apps)
    finally:
        stop(proc)
    check("a grant taken away while the app was closed is no longer offered after it starts again", removed and kept and gone,
          f"{tool}: removed {removed}, still offered while closed {kept}, gone after start {gone}")
    return before


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


def chrome_on(folder):
    """True while a Chrome process runs whose command line names this workspace folder (`--user-data-dir`)."""
    needle = str(folder)
    if os.name == "nt":
        script = ("if (Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
                  "$_.CommandLine.Contains($env:SWANGZ_WS_FOLDER) }) { exit 0 } else { exit 1 }")
        return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=60,
                              env={**os.environ, "SWANGZ_WS_FOLDER": needle}).returncode == 0
    return subprocess.run(["pgrep", "-f", "--", "--user-data-dir=" + needle], capture_output=True, timeout=60).returncode == 0


def both_running(a, b, timeout=45):
    """Both folders have a Chrome on them at the same moment (polled until both are seen in one round)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chrome_on(a) and chrome_on(b):
            return True
        time.sleep(1)
    return False


def device_of(data):
    """(key id, device id) from an app data folder's own record and manifest."""
    try:
        device = json.loads((Path(data) / "device.json").read_text(encoding="utf-8"))
        manifest = json.loads((Path(data) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    return device.get("key_id"), (manifest.get("browser") or {}).get("device_id")


def two_at_once(check, owner, a, b, tool=TOOL):
    """Deliverable 5 level B (docs/TWO-PEOPLE-AT-ONCE-PLAN.md): two copies of the installed app, each with its own data
    folder (SWANGZ_HOME), signed in as two different people AT THE SAME TIME on one OS user. `a` and `b` are dicts:
    name, person_id, data, run (run_app for that copy) and key (() -> that copy's device key from its own store, the
    OS credential store looked up by its key id, or None; in memory only, never printed).
    Both are signed in already and granted `tool`. Then the admin disconnects b's device; a carries on.

    Same OS user, so this says nothing about OS-level separation (ACLs, a second user: owner checks O-1 to O-3); the
    windows are Chrome on a fixture tool, not a real provider sign-in."""
    sides = (a, b)
    for me, other in ((a, b), (b, a)):  # B1
        code, out = me["run"]("status")
        check(f"two at once: {me['name']}'s copy is signed in as them while the other copy is signed in too",
              code == 0 and me["name"] in out and other["name"] not in out, f"exit {code}")
    ids = [device_of(s["data"]) for s in sides]  # B3
    keys = [s["key"]() for s in sides]
    check("two at once: two devices, two key ids, two stored device keys, each found under its own key id and different"
          " (compared in memory, never shown)",
          all(k and d for k, d in ids) and ids[0][0] != ids[1][0] and ids[0][1] != ids[1][1]
          and all(keys) and keys[0] != keys[1],
          f"keys {ids[0][0]} / {ids[1][0]}, devices {ids[0][1]} / {ids[1][1]}")
    before = time.time() - 1
    folders = []
    try:
        for s, (_, device_id) in zip(sides, ids):  # B2
            code, out = s["run"]("open", tool)
            mine = [f for f in workspace_folders(s["data"])
                    if marker_of(f).get("person_id") == str(s["person_id"]) and marker_of(f).get("device_id") == device_id]
            check(f"two at once: {s['name']}'s copy opens the tool in a workspace folder marked for them and this device",
                  code == 0 and len(mine) == 1, f"exit {code}, {len(mine)} folder(s)")
            folders.append(mine[0])
        check("two at once: two Chrome windows run together, on two different folders in two different data folders",
              folders[0] != folders[1] and both_running(*folders) and all(chrome_wrote(f) for f in folders),
              f"{folders[0].name} / {folders[1].name}")
        # B4: b's data folder is new, so it must hold nothing of a's
        a_in_b = [f.name for f in workspace_folders(b["data"]) if marker_of(f).get("person_id") == str(a["person_id"])]
        check("two at once: no folder of the first person's in the second copy's data folder", not a_in_b,
              f"{len(a_in_b)} folder(s)")
        for s in sides:  # B5
            status, out = owner.call("GET", f"/launches?person={s['person_id']}&since={before}")
            opened = [r for r in out.get("items", []) if r.get("tool_id") == tool and r.get("outcome") == "opened"]
            check(f"two at once: the Hub records {s['name']}'s open under their name", status == 200 and len(opened) >= 1,
                  f"{len(opened)} open(s)")
        status, out = owner.call("GET", "/devices")
        rows = {r.get("id"): r for r in out.get("items", [])} if status == 200 else {}
        live = [rows.get(k) or {} for k, _ in ids]
        check("two at once: the admin's Devices list shows both devices connected, each under its own person",
              all(str(r.get("person_id")) == str(s["person_id"]) and r.get("revoked") is None for r, s in zip(live, sides)),
              ", ".join(f"{r.get('person')} {r.get('id')}" for r in live))
    finally:
        for f in folders:  # B8
            close_chrome(f)
    # B4, key half: scanned once both windows are closed, because a running Chrome holds its profile files locked on
    # Windows and every locked file counts as a failure (unreadable is never passed silently)
    leaks = files_holding(keys[1], [a["data"]]) + files_holding(keys[0], [b["data"]])
    check("two at once: with both windows closed, neither data folder holds the other device's key (an unreadable file"
          " fails)", not leaks, f"{len(leaks)} file(s): " + ", ".join(Path(h).name for h in leaks[:5]))
    marker_a = marker_of(folders[0])
    status, _ = owner.call("POST", f"/keys/{ids[1][0]}/revoke")  # B6, B7
    code_b, _ = b["run"]("sync")
    code_a, _ = a["run"]("sync")
    left_b = sorted(p.name for p in Path(b["data"]).iterdir()) if Path(b["data"]).exists() else []
    check(f"two at once: the admin disconnects {b['name']}'s device; its next sync is refused and removes only its own"
          " data, keeping its workspace folder (R-12)", status == 200 and code_b == 3 and set(left_b) <= {"browser-profiles"},
          f"HTTP {status}, sync exit {code_b}, left {left_b}")
    code, out = a["run"]("status")
    check(f"two at once: {a['name']} stays signed in and syncing, with the same key and an unchanged folder",
          code_a == 0 and code == 0 and a["name"] in out and device_of(a["data"]) == ids[0]
          and a["key"]() == keys[0] and marker_of(folders[0]) == marker_a, f"sync exit {code_a}, status exit {code}")
    return [f.name for f in folders]


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


def files_holding(secret, roots, skip=()):
    """Every file under roots whose bytes contain secret, and every file that could not be read (so a locked file is
    reported, never silently passed). The device key must be in no log or file but its own store."""
    needle, hits = secret.encode(), []
    for root in roots:
        for p in Path(root).rglob("*") if Path(root).exists() else ():
            if p.is_file() and not p.is_symlink() and p.name not in skip:
                data = read_bytes(p)
                if data is None or needle in data:
                    hits.append(("unreadable: " if data is None else "") + str(p))
    return hits


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
