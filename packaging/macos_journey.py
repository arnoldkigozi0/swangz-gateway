"""The macOS release-candidate journey, run on a macos-latest runner against a gateway started in CI.

    python3 packaging/macos_journey.py --old OLD.dmg --new NEW.dmg --evidence DIR

1. install the OLD (previous) build from its DMG into a fresh Applications folder; check its signature state
2. launch the window, take a screenshot, quit
3. enrol: `Swangz login`, the code approved by the person signed in to the staff app, as a person would in a browser
4. restart: launch and quit again; the device is still signed in and syncs
4b. Hub down: the app reaches the Hub through a relay that is cut; sync fails, nothing is lost or claimed; the relay
   comes back on the same address and the next sync checks in with no new sign-in
5. upgrade: replace the app with the NEW build from its DMG; the version changes, the sign-in and data stay.
   With --new-app, the mounted DMG's app is first compared entry by entry with that build, and everything on the
   volume (READ ME FIRST.txt included) is secret-scanned (DIR/secret-scan-dmg.json)
6. uninstall: `Swangz logout`, the server shows the device disconnected, the app's data and login item are gone,
   the bundle is removed

Every step writes to DIR/journey.log and DIR/journey.json (uploaded as evidence). Gatekeeper is never bypassed:
`spctl --assess` is run and its refusal of the unsigned build is recorded as the expected result. The fixture
server is tests/browser/demo.py (a stand-in for every provider; nothing real is called).
"""

import argparse
import hashlib
import importlib.util
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import secret_scan  # noqa: E402  packaging/secret_scan.py, the same scan the workflow runs over dist/

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


def relay_class():
    """The Windows acceptance run's relay (packaging/windows/installer_e2e.py): stop() is the network going away,
    start() brings it back on the same port, so the device's saved Hub address does not change."""
    spec = importlib.util.spec_from_file_location("installer_e2e", ROOT / "packaging" / "windows" / "installer_e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Relay


def start_server(public_url):
    """The fixture Hub, announcing public_url (the relay) as its address, so the codes and links it hands the app are
    on the server the app signed in to (the app refuses anything else)."""
    proc = subprocess.Popen([sys.executable, str(ROOT / "tests" / "browser" / "demo.py")], cwd=ROOT,
                            env={**os.environ, "HUB_FIXTURE_PUBLIC_URL": public_url},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = proc.stdout.readline()
    if not line:
        raise SystemExit("fixture server did not start: " + proc.stderr.read()[-2000:])
    return proc, json.loads(line)["port"]


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


def tree_digest(root):
    """Every entry under root: relative path -> its kind and content (file SHA-256 + executable bit, link target).
    Links are recorded, never followed, so two trees compare equal only if they hold exactly the same things."""
    root, out = Path(root), {}
    for here, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(here) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                out[rel] = ("link", os.readlink(p))
            elif p.is_dir():
                out[rel] = ("dir",)
            else:
                out[rel] = ("file", hashlib.sha256(p.read_bytes()).hexdigest(), os.access(p, os.X_OK))
    return out


def differences(a, b, limit=10):
    keys = sorted(set(a) | set(b))
    return [f"{k}: {'missing' if k not in a else a[k][0]} != {'missing' if k not in b else b[k][0]}"
            for k in keys if a.get(k) != b.get(k)][:limit]


VOLUME_CONTENT = {"Swangz.app", "Applications", "READ ME FIRST.txt"}
# What macOS itself puts on a mounted HFS+ volume; any other hidden entry fails the check above.
VOLUME_SYSTEM = {".fseventsd", ".Trashes", ".Spotlight-V100", ".DS_Store", ".HFS+ Private Directory Data\r",
                 ".journal", ".journal_info_block"}


def check_mounted(j, mount, expected_app, report):
    """What a person actually gets: the mounted DMG's app must be the very app the workflow scanned and listed
    in the SBOM, and the volume must hold only the app, READ ME FIRST.txt and the Applications link (plus macOS's own
    system entries), and every visible file on it is secret-scanned.
    The Applications link and the volume's hidden system folders (.fseventsd, .Trashes) are not content."""
    mount = Path(mount)
    top = {p.name for p in mount.iterdir()}
    extra = sorted(top - VOLUME_CONTENT - VOLUME_SYSTEM)
    link = mount / "Applications"
    j.step("the volume holds nothing else: the app, the RC notice, an Applications link to /Applications",
           VOLUME_CONTENT <= top and not extra and link.is_symlink() and os.readlink(link) == "/Applications",
           ", ".join(sorted(top)) + (f"; unexpected: {', '.join(extra)}" if extra else ""))
    got, want = tree_digest(mount / "Swangz.app"), tree_digest(expected_app)
    j.step("the app inside the mounted DMG is byte-for-byte the scanned build", got == want,
           f"{len(got)} entries compared with {expected_app}" if got == want else "; ".join(differences(got, want)))
    paths = [p for p in sorted(mount.iterdir()) if not p.is_symlink() and not p.name.startswith(".")]
    result = secret_scan.scan(paths)
    Path(report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    j.step("secret scan of the mounted DMG (the app and the RC notice: every visible file on the volume)",
           not result["hits"] and not result["unreadable"],
           f"{', '.join(p.name for p in paths)}: {len(result['files'])} files, "
           f"{result['inner_entries_scanned']} archive entries, {len(result['unreadable'])} unreadable, "
           f"{len(result['hits'])} hits" + "".join(f"; {h['pattern']} @ {h['where']}" for h in result["hits"][:5]))


def install(j, dmg, apps, expected_app=None):
    mount = Path(tempfile.mkdtemp(prefix="swangz-dmg-"))
    j.run(["hdiutil", "attach", dmg, "-nobrowse", "-readonly", "-mountpoint", mount], check=True)
    try:
        listing = sorted(p.name for p in mount.iterdir())
        j.step(f"DMG {Path(dmg).name} holds the app, an Applications link and the RC notice",
               {"Swangz.app", "Applications", "READ ME FIRST.txt"} <= set(listing), ", ".join(listing))
        if expected_app:
            check_mounted(j, mount, expected_app, j.evidence / "secret-scan-dmg.json")
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
    ap.add_argument("--new-app", help="the built Swangz.app the workflow scanned; the new DMG's app must equal it")
    args = ap.parse_args(argv)
    j = Journey(args.evidence)
    apps = Path(tempfile.mkdtemp(prefix="Applications-"))
    home = Path.home()
    data = home / "Library" / "Application Support" / "Swangz"
    login_item = home / "Library" / "LaunchAgents" / "com.swangzavenue.swangz.plist"
    env = {**os.environ, "BROWSER": "/usr/bin/true"}  # the code is approved by the fixture's browser, not Safari
    relay = relay_class()(None)
    relay.start()
    app_url = f"http://127.0.0.1:{relay.port}"  # the Hub's public address: everyone reaches it only through the relay
    server, relay.target = start_server(app_url)  # the fixture's own port; relay.target is read per connection
    j.note(f"fixture server on port {relay.target}, reached through the relay at {app_url}")
    try:
        browser = Browser(app_url)
        j.step("person signs in to the staff app", browser.sign_in() == 200)

        app = install(j, args.old, apps)
        code, out = j.run([binary(app), "--version"], env=env)
        j.step("old build installed from its DMG", code == 0 and args.old_version in out, out)
        code, _ = j.run([binary(app), "--self-check", j.evidence / "self-check-old.json"], env=env)
        j.step("frozen app self-check (imports, state, sign-in window, updates off)", code == 0)
        signature_state(j, app)
        j.step("window opens (first launch)", launch_and_quit(j, app, j.evidence / "1-first-launch.png"))

        j.note("$ Swangz login --server " + app_url)
        proc = subprocess.Popen([str(binary(app)), "login", "--server", app_url, "--name", DEVICE], env=env,
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

        # Hub down, then back: the same check as the Windows run (row 2-R of docs/RELEASE-EVIDENCE.md)
        state = lambda: json.loads((data / "state.json").read_text(encoding="utf-8"))
        synced, used = state().get("last_sync"), [k.get("last_used") for k in browser.my_devices() or []]
        relay.stop()
        code, out = j.run([binary(app), "sync"], env=env)
        j.step("Hub unreachable: sync fails and says so", code != 0, f"exit {code}")
        j.step("Hub unreachable: no sync is claimed, the device record is kept",
               state().get("last_sync") == synced and (data / "device.json").is_file())
        code, out = j.run([binary(app), "status"], env=env)
        j.step("Hub unreachable: status still names the person and this device", PERSON in out and DEVICE in out, f"exit {code}")
        time.sleep(1.1)  # last_used is stored to the second
        relay.start()
        j.step("Hub back on the same address", relay.port == urllib.parse.urlsplit(app_url).port, app_url)
        code, out = j.run([binary(app), "sync"], env=env)
        device = json.loads((data / "device.json").read_text(encoding="utf-8"))
        j.step("Hub back: the next sync succeeds with no new sign-in",
               code == 0 and (state().get("last_sync") or 0) > (synced or 0) and not device.get("reconnect"), f"exit {code}")
        now = [k.get("last_used") for k in browser.my_devices() or []]
        j.step("Hub back: the server records the device's check-in", now != used and any(now), f"{used} -> {now}")

        keep = sorted(p.name for p in data.iterdir()) if data.exists() else []
        app = install(j, args.new, apps, args.new_app)
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
        relay.stop()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    j.note(f"journey passed: {len(j.results)} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
