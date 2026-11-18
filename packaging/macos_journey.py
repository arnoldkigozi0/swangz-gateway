"""The macOS release-candidate journey, run on a macos-latest runner against a gateway started in CI.

    python3 packaging/macos_journey.py --old OLD.dmg --new NEW.dmg --evidence DIR

1. install the OLD (previous) build from its DMG into a fresh Applications folder; check its signature state
2. launch the window, take a screenshot, quit
3. enrol: `Swangz login`, the code approved by the person signed in to the staff app, as a person would in a browser
4. restart: launch and quit again; the device is still signed in and syncs
5. upgrade: replace the app with the NEW build from its DMG; the version changes, the sign-in and data stay
6. uninstall: `Swangz logout`, the server shows the device disconnected, the app's data and login item are gone,
   the bundle is removed

Every step writes to DIR/journey.log and DIR/journey.json (uploaded as evidence). Gatekeeper is never bypassed:
`spctl --assess` is run and its refusal of the unsigned build is recorded as the expected result. The fixture
server is tests/browser/demo.py (a stand-in for every provider; nothing real is called).
"""

import argparse
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMAIL, PASSWORD, PERSON = "grace@swangzavenue.com", "demo-password", "Nansubuga Grace"
DEVICE = "CI Mac"
# swangz_client/core.py remove_everything: the managed-browser folders stay (R-12); each profile is bound to its owner.
KEPT_AFTER_SIGNOUT = {"browser-profiles"}
KEYCHAIN_SERVICE = "Swangz AI Hub"  # swangz_client/keystore.py SERVICE
CODE = re.compile(r"\b([BCDFGHJKMNPQRSTVWXZ2-9]{4}-[BCDFGHJKMNPQRSTVWXZ2-9]{4})\b")


class Journey:
    def __init__(self, evidence):
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.log = open(self.evidence / "journey.log", "a", encoding="utf-8")
        self.results = []

    def note(self, text):
        line = time.strftime("%H:%M:%S ") + text
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    def step(self, name, ok, detail=""):
        self.results.append({"step": name, "result": "pass" if ok else "FAIL", "detail": detail})
        self.note(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
        (self.evidence / "journey.json").write_text(json.dumps(self.results, indent=2), encoding="utf-8")
        if not ok:
            raise SystemExit(f"journey failed at: {name}")

    def run(self, cmd, check=False, **kw):
        self.note("$ " + " ".join(map(str, cmd)))
        out = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, **kw)
        text = (out.stdout + out.stderr).strip()
        if text:
            self.note(text[-4000:])
        if check and out.returncode:
            raise SystemExit(f"command failed ({out.returncode}): {cmd}")
        return out.returncode, text


# ---------------------------------------------------------------- the server and the person's browser


def start_server():
    proc = subprocess.Popen([sys.executable, str(ROOT / "tests" / "browser" / "demo.py")], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = proc.stdout.readline()
    if not line:
        raise SystemExit("fixture server did not start: " + proc.stderr.read()[-2000:])
    return proc, json.loads(line)["url"]


class Browser:
    """The person's own browser: signed in to the staff app, approving the device code on /device."""

    def __init__(self, url):
        self.url = url
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, form=None, headers=None):
        data, h = None, dict(headers or {})
        if body is not None:
            data, h["content-type"] = json.dumps(body).encode(), "application/json"
        if form is not None:
            data, h["content-type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def sign_in(self):
        return self.call("POST", "/api/login", {"email": EMAIL, "password": PASSWORD}, headers={"x-swangz-app": "1"})[0]

    def approve(self, code):
        status, page = self.call("GET", "/device?code=" + urllib.parse.quote(code))
        csrf = re.search(r"name=csrf value='([0-9a-f]+)'", page)
        if status != 200 or not csrf:
            return status
        return self.call("POST", "/device", form={"code": code, "csrf": csrf.group(1), "owner": "personal", "decision": "approve"})[0]

    def my_devices(self):
        status, text = self.call("GET", "/api/me", headers={"x-swangz-app": "1"})
        return [k for k in json.loads(text).get("keys", []) if k.get("label") == DEVICE] if status == 200 else None


# ---------------------------------------------------------------- the Mac side


def install(j, dmg, apps):
    mount = Path(tempfile.mkdtemp(prefix="swangz-dmg-"))
    j.run(["hdiutil", "attach", dmg, "-nobrowse", "-readonly", "-mountpoint", mount], check=True)
    try:
        listing = sorted(p.name for p in mount.iterdir())
        j.step(f"DMG {Path(dmg).name} holds the app, an Applications link and the RC notice",
               {"Swangz.app", "Applications", "READ ME FIRST.txt"} <= set(listing), ", ".join(listing))
        target = apps / "Swangz.app"
        if target.exists():
            shutil.rmtree(target)
        j.run(["ditto", mount / "Swangz.app", target], check=True)  # what dragging to Applications does
    finally:
        j.run(["hdiutil", "detach", mount, "-force"])
    return apps / "Swangz.app"


def binary(app):
    return app / "Contents" / "MacOS" / "Swangz"


def signature_state(j, app):
    code, _ = j.run(["codesign", "--verify", "--deep", "--strict", app])
    j.step("bundle signature is intact (ad hoc, unsigned RC)", code == 0)
    code, text = j.run(["spctl", "--assess", "--type", "execute", "--verbose=2", app])
    # Expected: refused. An unsigned, unnotarized build must NOT pass Gatekeeper; we record that and do not bypass it.
    j.step("Gatekeeper refuses the unsigned RC (expected until Developer ID + notarization)", code != 0, text.splitlines()[-1] if text else "")


def launch_and_quit(j, app, shot):
    before = set(pids(app))
    j.run(["open", "-n", app])
    alive = []
    for _ in range(40):
        time.sleep(0.5)
        alive = [p for p in pids(app) if p not in before]
        if alive:
            break
    time.sleep(4)  # let the window draw
    still = [p for p in alive if p in pids(app)]
    j.run(["screencapture", "-x", shot])
    for p in still:
        j.run(["kill", p])
    for _ in range(20):
        if not [p for p in still if p in pids(app)]:
            break
        time.sleep(0.5)
    return bool(still)


def pids(app):
    out = subprocess.run(["pgrep", "-f", str(binary(app))], capture_output=True, text=True).stdout
    return [p for p in out.split() if p.isdigit()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--old-version", required=True)
    ap.add_argument("--new-version", required=True)
    ap.add_argument("--evidence", required=True)
    args = ap.parse_args(argv)
    j = Journey(args.evidence)
    apps = Path(tempfile.mkdtemp(prefix="Applications-"))
    home = Path.home()
    data = home / "Library" / "Application Support" / "Swangz"
    login_item = home / "Library" / "LaunchAgents" / "com.swangzavenue.swangz.plist"
    env = {**os.environ, "BROWSER": "/usr/bin/true"}  # the code is approved by the fixture's browser, not Safari
    server, url = start_server()
    j.note("fixture server at " + url)
    try:
        browser = Browser(url)
        j.step("person signs in to the staff app", browser.sign_in() == 200)

        app = install(j, args.old, apps)
        code, out = j.run([binary(app), "--version"], env=env)
        j.step("old build installed from its DMG", code == 0 and args.old_version in out, out)
        code, _ = j.run([binary(app), "--self-check", j.evidence / "self-check-old.json"], env=env)
        j.step("frozen app self-check (imports, state, sign-in window, updates off)", code == 0)
        signature_state(j, app)
        j.step("window opens (first launch)", launch_and_quit(j, app, j.evidence / "1-first-launch.png"))

        j.note("$ Swangz login --server " + url)
        proc = subprocess.Popen([str(binary(app)), "login", "--server", url, "--name", DEVICE], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        seen, code_text = [], None
        while code_text is None:
            line = proc.stdout.readline()
            if not line:
                break
            seen.append(line.rstrip())
            m = CODE.search(line)
            code_text = m.group(1) if m else None
        j.step("app shows a sign-in code", bool(code_text), code_text or "\n".join(seen))
        j.step("person approves the code in their browser", browser.approve(code_text) == 200, code_text)
        rest, _ = proc.communicate(timeout=120)
        j.note("\n".join(seen) + "\n" + rest)
        j.step("app finishes signing in", proc.returncode == 0 and PERSON in rest, f"exit {proc.returncode}")
        code, out = j.run([binary(app), "status"], env=env)
        j.step("status shows the person and this device", code == 0 and PERSON in out and DEVICE in out)
        j.step("server lists the device as connected", any(not k.get("revoked") for k in browser.my_devices() or []))
        code, out = j.run([binary(app), "autostart", "on"], env=env)
        j.step("start at login turned on", code == 0 and login_item.exists(), str(login_item))

        j.step("window opens again (restart)", launch_and_quit(j, app, j.evidence / "2-restart.png"))
        code, out = j.run([binary(app), "sync"], env=env)
        j.step("after restart: still signed in and syncs", code == 0)

        keep = sorted(p.name for p in data.iterdir()) if data.exists() else []
        app = install(j, args.new, apps)
        code, out = j.run([binary(app), "--version"], env=env)
        j.step("upgraded in place to the new build", code == 0 and args.new_version in out, out)
        code, _ = j.run([binary(app), "--self-check", j.evidence / "self-check-new.json"], env=env)
        j.step("new build self-check", code == 0)
        signature_state(j, app)
        code, out = j.run([binary(app), "status"], env=env)
        j.step("after upgrade: same person and device, data kept", code == 0 and PERSON in out and DEVICE in out
               and data.exists() and set(keep) <= {p.name for p in data.iterdir()}, ", ".join(keep))
        j.step("window opens after upgrade", launch_and_quit(j, app, j.evidence / "3-after-upgrade.png"))

        j.step("start at login still on before sign out", login_item.exists(), str(login_item))
        code, out = j.run([binary(app), "logout"], env=env)  # sign out alone must remove the login item
        j.step("sign out tells the server and removes Swangz", code == 0 and "removed" in out and "couldn't" not in out, out)
        devices = browser.my_devices() or []
        j.step("server shows the device disconnected", bool(devices) and all(k.get("revoked") for k in devices))
        leftovers = [p.name for p in data.iterdir()] if data.exists() else []
        j.step("no key or device record left in the app's data folder",
               not set(leftovers) & {"device.json", "device.key", "device.key.next", "state.json", "manifest.json"},
               ", ".join(leftovers) or "folder empty or gone")
        code, _ = j.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE])
        j.step("no Swangz item left in the login keychain", code != 0)
        j.step("only the company-browser folder is kept after sign out (by design, R-12)",
               set(leftovers) <= KEPT_AFTER_SIGNOUT, ", ".join(leftovers) or "folder empty or gone")
        j.step("sign out removed the login item", not login_item.exists(), str(login_item))
        code, out = j.run([binary(app), "status"], env=env)
        j.step("status says not signed in", code == 2)
        shutil.rmtree(app)
        j.step("app removed from Applications", not app.exists())
        j.step("no Swangz process left running", not pids(app))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    j.note(f"journey passed: {len(j.results)} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
