"""Windows installer acceptance on a CI runner: silent install -> launch -> enrol -> restart -> reconnect -> upgrade from the previous build over a running copy
-> the older build refused -> uninstall while running.

    python packaging/windows/installer_e2e.py --setup artifacts/Swangz-Setup-0.1.0-UNSIGNED.exe --evidence evidence

Runs only on Windows (GitHub Actions windows-latest). The Hub is the test suite's isolated gateway on 127.0.0.1 with fake
providers; nothing on the internet and no real account is used. The app reaches the Hub through a small local relay that
this script can cut and restore, which is how a network interruption is made. Every step is written to
<evidence>/report.json, with the installer's and uninstaller's own logs beside it. Exit 0 only when every step passed.
"""

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zoneinfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{2027a02e-ebf5-41b9-8a7d-9e10a26e1770}_is1"


def stopped(proc, message, timeout=60):
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(message) from None


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Relay:
    """127.0.0.1:<port> -> the Hub. stop() is the network going away (listener and open connections closed); start()
    brings it back on the same port, so the device's saved server address is unchanged."""

    def __init__(self, target_port):
        self.target, self.port, self.sock, self.conns = target_port, None, None, []
        self.lock = threading.Lock()

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":  # rebinding after a cut needs it on POSIX; on Windows the option would allow port sharing
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", self.port or 0))
        s.listen(32)
        self.port, self.sock = s.getsockname()[1], s
        threading.Thread(target=self._accept, args=(s,), daemon=True).start()

    def stop(self):
        sock, self.sock = self.sock, None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)  # wakes a blocked accept() on Linux; closing alone does not
            except OSError:
                pass
            sock.close()
        with self.lock:
            conns, self.conns = self.conns, []
        for c in conns:
            try:
                c.close()
            except OSError:
                pass

    def _accept(self, listener):
        while True:
            try:
                client, _ = listener.accept()
            except OSError:
                return
            try:
                upstream = socket.create_connection(("127.0.0.1", self.target), timeout=10)
            except OSError:
                client.close()
                continue
            with self.lock:
                self.conns += [client, upstream]
            for a, b in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pipe, args=(a, b), daemon=True).start()

    @staticmethod
    def _pipe(src, dst):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


def reg_value(key, name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def shell_folder(name):
    return Path(reg_value(r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders", name))


def kampala_zone(tmpdir):
    """Windows has no IANA zone database; give the gateway fixture its fixed EAT offset (as packaging/smoke.py does)."""
    from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError, reset_tzpath
    try:
        ZoneInfo("Africa/Kampala")
    except ZoneInfoNotFoundError:
        zone = Path(tmpdir) / "Africa" / "Kampala"
        zone.parent.mkdir(parents=True)
        zone.write_bytes(b"TZif\x00" + b"\x00" * 15 + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
                         + struct.pack(">lbb", 3 * 3600, 0, 0) + b"EAT\x00")
        reset_tzpath([str(tmpdir), *TZPATH])


class Tee:
    """The in-process Hub logs to sys.stderr; this keeps a copy in a file the F-18 scan reads."""

    def __init__(self, stream, path):
        self.stream, self.file = stream, open(path, "a", encoding="utf-8")

    def write(self, text):
        self.file.write(text)
        self.file.flush()
        return self.stream.write(text)

    def flush(self):
        self.file.flush()
        self.stream.flush()

    def close(self):
        self.file.close()


def e2e(setup, evidence, previous=None, previous_version=None, new_version=None):
    """With `previous`, steps 1-5 run on the previous build and step 6 upgrades it to `setup`; otherwise step 6 reinstalls."""
    from tests.test_devices import DeviceBase

    evidence.mkdir(parents=True, exist_ok=True)
    report = {"os": platform.platform(), "setup": setup.name, "steps": [], "ok": False,
              "previous": previous.name if previous else None, "previous_version": previous_version, "new_version": new_version}
    first = previous or setup
    fixture, relay, gui, initialized = DeviceBase(), None, None, False
    work = Path(tempfile.mkdtemp(prefix="swangz-installer-e2e-"))
    hub_log = evidence / "hub-fixture.log"
    real_stderr, sys.stderr = sys.stderr, Tee(sys.stderr, hub_log)
    try:
        kampala_zone(work / "tz")
        fixture.setUp()
        initialized = True
        rig = fixture.rig
        relay = Relay(rig.port)
        relay.start()
        origin = f"http://127.0.0.1:{relay.port}"
        rig.gw.settings.public_url = origin
        data, home = work / "data", work / "home"
        home.mkdir()
        env = {**os.environ, "SWANGZ_HOME": str(data), "SWANGZ_TEST_HOME": str(home),
               "BROWSER": f'"{sys.executable}" "{Path(__file__).resolve()}" --browser %s'}
        for name in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(name, None)
        for name in ("SWANGZ_SERVER", "SWANGZ_ALLOW_HTTP"):
            env.pop(name, None)  # fresh-install/address checks must not inherit a runner's configuration
        app_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Swangz"
        exe = app_dir / "Swangz.exe"

        def passed(message):
            report["steps"].append(message)
            print("PASS " + message, flush=True)

        def run(cmd, expected=0, timeout=180):
            result = subprocess.run([str(c) for c in cmd], env=env, capture_output=True, text=True, timeout=timeout, cwd=work)
            require(result.returncode == expected, f"{cmd[0]} {cmd[1:]} exited {result.returncode}, expected {expected}: "
                    + result.stdout[-2000:] + result.stderr[-2000:])
            return result

        def app(*args, expected=0):
            return run([exe, *args], expected=expected)

        def install(log, installer=setup):
            run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=desktopicon,startup",
                 f"/LOG={evidence / log}"])

        def heartbeat(key_id):
            return rig.gw.db.scalar("SELECT last_seen FROM devices WHERE key_id = ?", (key_id,))

        def sign_in_codes():
            return (rig.gw.db.scalar("SELECT COUNT(*) FROM device_codes"),
                    rig.gw.db.scalar("SELECT COALESCE(MAX(id), 0) FROM device_codes"))

        # 1. silent install, per person, with both optional tasks
        install("install.log", first)
        start_menu = shell_folder("Programs") / "Swangz.lnk"
        desktop = shell_folder("Desktop") / "Swangz.lnk"
        run_value = reg_value(RUN_KEY, "Swangz")
        require(exe.is_file(), f"not installed at {exe}")
        require(start_menu.is_file(), f"no Start-menu shortcut at {start_menu}")
        require(desktop.is_file(), f"no desktop shortcut at {desktop}")
        require(run_value and "Swangz.exe" in run_value and run_value.endswith("--background"), f"Run value: {run_value!r}")
        require(reg_value(UNINSTALL_KEY, "UninstallString"), "no Apps & features entry")
        report["installed"] = {"exe": str(exe), "start_menu": str(start_menu), "desktop": str(desktop), "run": run_value,
                               "display_version": reg_value(UNINSTALL_KEY, "DisplayVersion")}
        passed("silent install (no administrator rights): program, Start-menu and desktop shortcuts, start-at-sign-in value,"
               " Apps & features entry")

        # 2. launch: the installed program, its window, updates off; then started the way Windows starts it at sign-in
        app("--version")
        check = work / "self-check.json"
        app("--self-check", check)
        check = json.loads(check.read_text(encoding="utf-8"))
        require(check["frozen"] and check["window"] == "signin", f"self-check: {check}")
        require(not (data / "device.json").exists() and check.get("hub_address") == "",
                "fresh install saved or prefilled a Hub address")
        app("status", expected=2)
        codes = sign_in_codes()
        for address in ("http://hub.example.com", "http://192.0.2.10:8787"):
            run([exe, "login", "--server", address, "--name", "CI installer"], expected=1, timeout=60)
            require(not (data / "device.json").exists(), "refused address left a device record")
            require(sign_in_codes() == codes, "refused address requested a sign-in code")
        passed("fresh install: sign-in window has no Hub address; status exits 2; non-https addresses exit 1 without"
               " saving a device or issuing a sign-in code")
        require(check["updates_enabled"] is False and check["production_keys"] == 0, "the update gate is not off")
        if previous_version:
            require(check["version"] == previous_version, f"installed {check['version']}, expected {previous_version}")
        report["self_check"] = check
        gui = subprocess.Popen([str(exe), "--background"], env=env, cwd=work)
        time.sleep(8)
        require(gui.poll() is None, f"the program started at sign-in exited with {gui.returncode}")
        gui.terminate()
        gui.wait(30)
        gui = None
        passed(f"launch: --version, the Tk {check['tk']} sign-in window, the --background start; updates off, no release keys")

        # 3. enrol: first run asks for the Hub address; the person approves the code in their browser
        def enrol(approve=None):
            login = subprocess.Popen(    [str(exe), "login", "--server", origin, "--name", "CI installer"], env=env, cwd=work,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline, code = time.monotonic() + 90, None
                while time.monotonic() < deadline and code is None and login.poll() is None:
                    code = rig.gw.db.one("SELECT user_code FROM device_codes WHERE status = 'pending' AND expires > ?"
                                     " ORDER BY id DESC LIMIT 1", (time.time(),))
                    time.sleep(0.2)
                require(code is not None, "the installed program did not ask for a device code")
                ok = approve(code["user_code"]) == 200 if approve else fixture.approve(code["user_code"], "personal")[0] == 200
                require(ok, "approval failed")
                out, err = login.communicate(timeout=120)
                require(login.returncode == 0, "login/sync failed: " + out[-2000:] + err[-2000:])
            finally:
                if login.poll() is None:
                    login.kill()
                    login.communicate()
            device = json.loads((data / "device.json").read_text(encoding="utf-8"))
            require(device["server"] == origin, "wrong server saved")
            return device

        # 3a. refused sign-in codes, through the installed program: while it waits, a wrong code entered on /device
        #     approves nothing; the code it shows then expires, `login` ends with exit 1 and saves no device or key, and
        #     the expired code can no longer be approved
        from gateway import enroll as hub_enroll

        def keys_issued():
            return rig.gw.db.scalar("SELECT COUNT(*) FROM keys")

        def unusable(code):
            status, text, _ = fixture.page(query="?code=" + code)
            return status == 200 and "already used or has expired" in text and "name=csrf" not in text

        issued = keys_issued()
        login = subprocess.Popen([str(exe), "login", "--server", origin, "--name", "CI installer"], env=env, cwd=work,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out = err = ""
        try:
            deadline, row = time.monotonic() + 90, None
            while time.monotonic() < deadline and row is None and login.poll() is None:
                row = rig.gw.db.one("SELECT id, user_code FROM device_codes WHERE status = 'pending' AND expires > ?"
                                     " ORDER BY id DESC LIMIT 1", (time.time(),))
                time.sleep(0.2)
            require(row is not None, "the installed program did not ask for a device code")
            wrong = hub_enroll._new_user_code()
            while rig.gw.db.one("SELECT id FROM device_codes WHERE user_code = ?", (wrong,)):
                wrong = hub_enroll._new_user_code()
            status, text, _ = fixture.page(query="?code=" + wrong)
            require(status == 200 and "That code isn't right" in text and "name=csrf" not in text,
                    "a wrong code was offered for approval")
            # a REAL token, fetched from the waiting code's own /device form in this signed-in browser (as the macOS
            # journey does), and checked against the Hub's own CSRF rule for this session: so the 400 below can only
            # mean the code is wrong, never a bad token
            real = fixture.csrf(row["user_code"])
            session = hub_enroll._cookie(fixture.person_cookie, hub_enroll.COOKIE)
            require(hmac.compare_digest(real, hub_enroll._csrf(rig.gw, session, row["user_code"])),
                    "the token fetched from /device is not the Hub's real token for this session")
            status, text, _ = fixture.page("POST", form={"code": wrong, "csrf": real, "owner": "personal", "decision": "approve"})
            require(status == 400 and "Open the link from your device again and retry." in text, f"approving a wrong code with a real token answered {status}")
            require(rig.gw.db.scalar("SELECT status FROM device_codes WHERE id = ?", (row["id"],)) == "pending",
                    "a wrong code changed the waiting sign-in")
            require(login.poll() is None and not (data / "device.json").exists(), "the program stopped waiting after a wrong code")
            passed("wrong sign-in code: /device says the code isn't right; posted with a real CSRF token (the Hub's own,"
                   " for this session) it is refused 400 and approves nothing; the installed program keeps waiting")
            rig.gw.db.x("UPDATE device_codes SET expires = ? WHERE id = ?", (time.time() - 1, row["id"]))
            out, err = login.communicate(timeout=120)
        finally:
            if login.poll() is None:
                login.kill()
                login.communicate()
        require(login.returncode == 1, f"login with an expired code exited {login.returncode}: " + out[-1000:] + err[-1000:])
        require("expired" in (out + err).lower(), "login did not say the code expired")
        require(not (data / "device.json").exists() and keys_issued() == issued, "an expired code left a device or issued a key")
        require(unusable(row["user_code"]), "the expired code can still be approved")
        passed("expired sign-in code: the installed program's login exits 1 saying it expired, no device or key is saved,"
               " and /device refuses that code")

        device = enrol()
        key_id = device["key_id"]
        report["key_storage"] = device["key_storage"]
        from swangz_client import keystore

        def stored_secret():
            return keystore.CredentialManager().get(origin, key_id)

        def stored_raw():
            # Read only into memory, never written: only its SHA-256 or a yes/no reaches the report or a message.
            record = json.loads((data / "device.json").read_text(encoding="utf-8"))
            secret = ((data / "device.key").read_text(encoding="utf-8").strip()
                      if record["key_storage"] == "file" else stored_secret())
            require(bool(secret), "no stored device credential to compare")
            return secret

        def stored_fingerprint():
            return hashlib.sha256(stored_raw().encode()).hexdigest()

        in_os_store = device["key_storage"] != "file"
        if in_os_store:
            require(stored_secret(), "the device key is not in Windows Credential Manager")
        passed(f"enrol against the CI Hub: device code approved, first sync done; key storage {device['key_storage']}")

        # 3b. a used code is not reusable: /device refuses it, and a second login on the signed-in program is refused
        #     without asking the Hub for a new code
        used = rig.gw.db.scalar("SELECT user_code FROM device_codes WHERE key_id = ?", (key_id,))
        require(used and unusable(used), "the used sign-in code can still be approved")
        codes, issued = sign_in_codes(), keys_issued()
        run([exe, "login", "--server", origin, "--name", "CI installer again"], expected=1, timeout=60)
        require(sign_in_codes() == codes and keys_issued() == issued, "a second login asked for a code or issued a key")
        require(json.loads((data / "device.json").read_text(encoding="utf-8"))["key_id"] == key_id,
                "the second login replaced the device")
        passed("used sign-in code: /device refuses it again; a second login on the signed-in program exits 1, asks for no"
               " new code and keeps the same device and key")


        # 4. restart: a new process (and the window started and closed again) is still signed in and syncs
        seen = heartbeat(key_id)
        gui = subprocess.Popen([str(exe), "--background"], env=env, cwd=work)
        time.sleep(8)
        gui.terminate()
        gui.wait(30)
        gui = None
        app("status")
        time.sleep(0.05)
        app("sync")
        require(heartbeat(key_id) > seen, "no check-in after the restart")
        passed("restart: the program closed and started again, still signed in; sync and check-in recorded by the Hub")

        # 5. network interruption: the Hub is unreachable, nothing is lost; it comes back and the app reconnects by itself
        before_key, before_codes = stored_fingerprint(), sign_in_codes()
        synced = json.loads((data / "state.json").read_text(encoding="utf-8"))["last_sync"]
        relay.stop()
        down_check = work / "self-check-offline.json"
        app("--self-check", down_check)
        require(json.loads(down_check.read_text(encoding="utf-8"))["window"] == "home",
                "Hub down at app start: window did not open on Home")
        gui = subprocess.Popen([str(exe), "--background"], env=env, cwd=work)
        time.sleep(8)  # allow the normal startup sync to run while the relay is down
        require(gui.poll() is None, "Hub down at app start: the window exited")
        gui.terminate()
        gui.wait(30)
        gui = None
        passed("Hub down at app start: the installed Home window opens and the background process stays running")
        app("sync", expected=1)  # the windowed program has no console; its exit code is the evidence (1 = could not reach)
        require(json.loads((data / "state.json").read_text(encoding="utf-8"))["last_sync"] == synced, "offline sync claimed success")
        require((data / "device.json").is_file(), "the device record was lost while offline")
        app("status")
        seen = heartbeat(key_id)
        relay.start()
        time.sleep(0.05)
        app("sync")
        require(heartbeat(key_id) > seen, "no check-in after the network came back")
        after_device = json.loads((data / "device.json").read_text(encoding="utf-8"))
        require(not after_device.get("reconnect"), "asked to reconnect")
        after_key, after_codes = stored_fingerprint(), sign_in_codes()
        require(after_device["key_id"] == key_id and after_key == before_key, "outage changed the device credential")
        require(after_codes == before_codes, "outage issued a new sign-in code")
        report["reconnect"] = {"key_sha256_before": before_key, "key_sha256_after": after_key,
                               "sign_in_codes_before": before_codes, "sign_in_codes_after": after_codes}
        passed("network interruption: sync exited 1 and recorded no sync, credentials and state kept; on return the next sync"
               " checked in with the same key SHA-256 and unchanged sign-in-code count")

        # 5a. after the outage the device key is in no log or file: the app's data folder (but the key's own file when
        #     it is file-stored) and this journey's evidence, the Hub fixture's log included
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # packaging/
        import hub_journey
        leaks = hub_journey.files_holding(stored_raw(), [data, evidence], skip={"device.key", "device.key.next"})
        require(not leaks, "the device key is in: " + ", ".join(leaks))
        report["key_in_no_file"] = {"searched": [str(data), str(evidence)], "hits": 0}
        passed(f"after the outage the device key is in no log or file (searched {data} and {evidence})")

        # 5c. a real Hub PROCESS restart: the journey's own Hub stops, a new process (tests/browser/demo.py restart mode)
        #     serves the same data folder on the same port, then the journey's Hub comes back on that port again
        from contextlib import closing
        import sqlite3

        def peek(sql, args=()):  # read the Hub's database while the journey's own Hub is stopped
            with closing(sqlite3.connect(Path(rig.tmp) / "gateway.db", timeout=30)) as c:
                return c.execute(sql, args).fetchone()

        before_key, synced = stored_fingerprint(), json.loads((data / "state.json").read_text(encoding="utf-8"))["last_sync"]
        before_codes, seen = sign_in_codes(), heartbeat(key_id)
        rig.server.shutdown()
        rig.server.server_close()
        rig.gw.db.close()
        app("sync", expected=1)
        require(json.loads((data / "state.json").read_text(encoding="utf-8"))["last_sync"] == synced, "sync claimed success with the Hub stopped")
        require((data / "device.json").is_file(), "the device record was lost while the Hub was stopped")
        hub = subprocess.Popen([sys.executable, str(ROOT / "tests" / "browser" / "demo.py")], cwd=ROOT, text=True,
                               env={**os.environ, "HUB_FIXTURE_DATA": rig.tmp, "HUB_FIXTURE_PORT": str(rig.port),
                                    "HUB_FIXTURE_PUBLIC_URL": origin, "HUB_FIXTURE_KEEP": "1",
                                    # the child needs the same zone search path kampala_zone() gave this process
                                    "PYTHONTZPATH": os.pathsep.join(zoneinfo.TZPATH)},
                               stdout=subprocess.PIPE, stderr=sys.stderr.file if isinstance(sys.stderr, Tee) else None)
        try:
            line = hub.stdout.readline()
            require(bool(line), "the restarted Hub process did not start")
            again = json.loads(line)
            require(again["pid"] != os.getpid() and again["port"] == rig.port and again["data"] == rig.tmp,
                    f"restarted Hub: pid {again['pid']} (journey {os.getpid()}), port {again['port']}, data {again['data']}")
            time.sleep(0.05)
            app("sync")
            after_device = json.loads((data / "device.json").read_text(encoding="utf-8"))
            require(not after_device.get("reconnect"), "asked to reconnect after the Hub restart")
            after_key = stored_fingerprint()
            after_codes = peek("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM device_codes")
            now = peek("SELECT last_seen FROM devices WHERE key_id = ?", (key_id,))[0]
            require(after_device["key_id"] == key_id and after_key == before_key, "the Hub restart changed the device credential")
            require(tuple(after_codes) == tuple(before_codes), "the Hub restart issued a new sign-in code")
            require(now > seen, "no check-in recorded by the restarted Hub")
        finally:
            hub.terminate()  # Windows: TerminateProcess, as when a service is stopped hard; the data folder stays
            hub.wait(30)
            hub.stdout.close()
        report["hub_restart"] = {"journey_pid": os.getpid(), "hub_pid": again["pid"], "port": rig.port,
                                 "key_sha256_before": before_key, "key_sha256_after": after_key,
                                 "sign_in_codes_before": before_codes, "sign_in_codes_after": list(after_codes)}
        passed(f"Hub process restart: sync exited 1 while stopped; a new Hub process (pid {again['pid']}) on the same port"
               " and data: the next sync checked in with the same key SHA-256, no reconnect and no new sign-in code")
        from gateway.server import make_server  # the journey's own Hub again, on the same port and data
        import threading
        rig.settings.port = rig.port
        rig.server, rig.gw = make_server(rig.settings)
        rig.gw.settings.public_url = origin
        threading.Thread(target=rig.server.serve_forever, daemon=True).start()
        seen = heartbeat(key_id)
        time.sleep(0.05)
        app("sync")
        require(heartbeat(key_id) > seen and sign_in_codes() == before_codes, "no check-in after the journey's Hub came back")
        passed("the journey's Hub back on the same port and data: the next sync checks in, still no new sign-in code")

        # 5b. deliverable 5 and F-18 (packaging/hub_journey.py): the installed program opens a granted tool in its Chrome
        #     workspace window on the person's own folder; a request with its own credential is not stored by default,
        #     and once stored only a role with the trust area reads it
        def check(name, ok, detail=""):
            require(ok, f"{name}: {detail}")
            passed(name + (f" ({detail})" if detail else ""))

        def run_app(*args):
            result = subprocess.run([str(exe), *args], env=env, capture_output=True, text=True, timeout=180, cwd=work)
            return result.returncode, (result.stdout + result.stderr).strip()

        owner = hub_journey.Console(origin, "owner")
        folder = hub_journey.workspace(check, run_app, data, owner, rig.person_id)
        marker = hub_journey.marker_of(folder)
        report["workspace_folder"] = folder.name
        hub_journey.f18(check, exe, env, origin, owner, rig.person_id, rig.tmp, [hub_log], cwd=work)

        # 5d. grants after an app restart: with the program closed the admin grants a tool, then takes it away; each time
        #     the device's offer only changes when the program starts again (it syncs on start; nobody runs sync)
        def start_program():
            proc = subprocess.Popen([str(exe), "--background"], env=env, cwd=work)
            time.sleep(1)
            require(proc.poll() is None, f"the program exited with {proc.returncode} on start")
            return proc

        def close_program(proc):
            proc.terminate()
            proc.wait(30)

        hub_journey.grants_after_restart(check, start_program, close_program, data, owner, rig.person_id)

        # 6. upgrade to this build over a running copy (or, with no previous build, reinstall the same version): the
        #    installer closes the program; the person's device, key and settings stay, and the Hub sees the new version
        address = json.loads((data / "device.json").read_text(encoding="utf-8"))["server"]
        gui = subprocess.Popen([str(exe), "--background"], env=env, cwd=work)
        time.sleep(8)
        require(gui.poll() is None, "the program did not start before the upgrade")
        install("upgrade.log" if previous else "reinstall.log")
        stopped(gui, "the installer did not close the running program")
        gui = None
        require(json.loads((data / "device.json").read_text(encoding="utf-8"))["key_id"] == key_id, "the upgrade lost the device")
        if in_os_store:
            require(stored_secret(), "the upgrade lost the device key in Windows Credential Manager")
        app("status")
        seen = heartbeat(key_id)
        time.sleep(0.05)
        app("sync")
        require(heartbeat(key_id) > seen, "no check-in after the upgrade")
        if previous:
            shown = reg_value(UNINSTALL_KEY, "DisplayVersion")
            hub = rig.gw.db.scalar("SELECT app_version FROM devices WHERE key_id = ?", (key_id,))
            require(shown == new_version, f"Apps & features shows {shown}, expected {new_version}")
            require(hub == new_version, f"the Hub records app version {hub}, expected {new_version}")
            report["upgrade"] = {"from": previous_version, "to": new_version, "apps_and_features": shown, "hub_app_version": hub}
            passed(f"upgrade {previous_version} -> {new_version} over a running copy: the installer closed it; Apps & features"
                   " and the Hub's check-in show the new version; same device and key, still signed in, no new sign-in")
        else:
            passed("reinstall (same version) over a running copy: the installer closed it; same device, still signed in, syncs")
        hub_journey.kept(check, data, folder, marker, "after the upgrade")
        moved = json.loads((data / "device.json").read_text(encoding="utf-8"))["server"]
        check("after the upgrade the Hub address is unchanged and the new build syncs to it",
              address == moved == origin, f"{address} -> {moved}")

        # 6b. an older build is refused: the previous installer, run over this build, ends with exit code 1 and changes
        #     nothing (same version in Apps & features, same program, still signed in)
        if previous:
            before = exe.read_bytes()
            run([previous, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={evidence / 'downgrade.log'}"], expected=1)
            log = (evidence / "downgrade.log").read_text(encoding="utf-8", errors="replace")
            require(f"Refused: Swangz {new_version} is installed" in log, "the downgrade log does not say why it was refused")
            shown = reg_value(UNINSTALL_KEY, "DisplayVersion")
            require(shown == new_version, f"after the refused downgrade Apps & features shows {shown}, expected {new_version}")
            require(exe.read_bytes() == before, "the refused downgrade changed the installed program")
            app("status")
            report["downgrade"] = {"installer": previous_version, "installed": new_version, "exit_code": 1,
                                   "apps_and_features": shown}
            passed(f"older build refused: the {previous_version} installer over {new_version} exits 1, says why in its log and"
                   " changes nothing")

        # 7. sign out from the app: the Hub disconnects the device, local data and the key go, and the start-at-sign-in
        #    Run value is removed (a signed-out app has nothing to start for)
        require(reg_value(RUN_KEY, "Swangz"), "the start-at-sign-in value was gone before sign out")
        app("logout")
        require(reg_value(RUN_KEY, "Swangz") is None, "sign out left the start-at-sign-in value")
        require(not (data / "device.json").exists(), "sign out left local credentials")
        if in_os_store:
            require(stored_secret() is None, "sign out left the device key in Windows Credential Manager")
        require(rig.gw.db.scalar("SELECT revoked FROM keys WHERE id = ?", (key_id,)) is not None,
                "the Hub did not disconnect the signed-out device")
        passed("sign out: device disconnected at the Hub, local credentials removed, start-at-sign-in value gone")

        hub_journey.kept(check, data, folder, marker, "after sign out")

        # 7b. revoked while away: a separate signed-in browser reaches the fixture directly, not the stopped relay.
        device = enrol()
        key_id = device["key_id"]
        app("autostart", "on")
        require(reg_value(RUN_KEY, "Swangz"), "startup was not enabled before revocation")
        before_key, before_codes = stored_fingerprint(), sign_in_codes()
        relay.stop()
        require(fixture.staff("POST", f"/keys/{key_id}/revoke", cookie=fixture.person_cookie)[0] == 200,
                "the person could not disconnect the device while it was away")
        app("sync", expected=1)
        require((data / "device.json").is_file(), "offline revoked device lost its record before learning of revocation")
        require(stored_fingerprint() == before_key, "offline revoked device changed its stored credential")
        passed("revoked while away: separate browser disconnects the device; offline sync exits 1 and keeps its credential")
        relay.start()
        app("sync", expected=3)
        require(reg_value(RUN_KEY, "Swangz") is None, "revocation left the start-at-sign-in value")
        leftovers = {p.name for p in data.iterdir()} if data.exists() else set()
        require(leftovers <= {"browser-profiles"}, "revoked device left app data: " + ", ".join(sorted(leftovers)))
        if device["key_storage"] != "file":
            require(stored_secret() is None, "revocation left a Windows Credential Manager entry")
        require(sign_in_codes() == before_codes, "revocation issued a new sign-in code")
        app("status", expected=2)
        report["revoked_while_away"] = {"offline_exit": 1, "return_exit": 3, "signed_out_exit": 2,
                                         "startup_removed": True, "kept": sorted(leftovers)}
        passed("startup-enabled revocation: sync exits 3, Run value, device data and stored key removed, status exits 2;"
               " only browser-profiles may remain (R-12)")

        hub_journey.kept(check, data, folder, marker, "after revocation")

        # a second person enrols this PC (and switches start-at-sign-in back on, so the uninstall below is proven to
        # remove both itself): they get a workspace folder of their own, and the first person's is left as it was
        approve_second = []  # the second person's own browser approves their codes; kept to sign them in again below

        def enrol_second(approve):
            approve_second[:] = [approve]
            enrol(approve)
            return json.loads((data / "manifest.json").read_text(encoding="utf-8")).get("browser", {}).get("device_id")

        second, _ = hub_journey.second_person(check, enrol_second, run_app, data, owner, origin, folder, marker)
        device = json.loads((data / "device.json").read_text(encoding="utf-8"))
        key_id = device["key_id"]
        require(rig.gw.db.scalar("SELECT person_id FROM keys WHERE id = ?", (key_id,)) == second,
                "the second enrolment's key is not the second person's")
        report["second_person"] = second

        # 7c. machine-policy tamper (D-024 W5, the Windows twin of the macOS steps): the second person signs out, the
        #     first signs this PC in as a COMPANY device with the Chrome policy pack pinned in enforce mode, and the five
        #     cases run through the installed program (packaging/windows/policy.py); then the SECOND person signs in again,
        #     so the uninstall below runs with someone other than the first folder's owner signed in
        app("logout")
        import policy as windows_policy

        def enrol_company():
            enrol(lambda c: fixture.approve(c, "company")[0])
            return json.loads((data / "manifest.json").read_text(encoding="utf-8")).get("browser", {}).get("device_id")

        report["policy_tamper"] = windows_policy.run(check, run_app, enrol_company, owner, Path(rig.tmp) / "gateway.db",
                                                     rig.person_id, data, evidence)
        device = enrol(approve_second[0])
        key_id = device["key_id"]
        require(rig.gw.db.scalar("SELECT person_id FROM keys WHERE id = ?", (key_id,)) == second,
                "the enrolment before the uninstall is not the second person's")
        app("autostart", "on")
        require(reg_value(RUN_KEY, "Swangz"), "autostart on did not write the Run value")

        # 8. uninstall while the program runs (as it does when started at sign-in): it is stopped, the device is signed out
        #    at the Hub, local data and the Credential Manager entry removed, program, shortcuts and Run value gone
        gui = subprocess.Popen([str(exe), "--background"], env=env, cwd=work)
        time.sleep(8)
        require(gui.poll() is None, "the program did not start before the uninstall")
        quiet = reg_value(UNINSTALL_KEY, "UninstallString").strip('"')
        run([quiet, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={evidence / 'uninstall.log'}"])
        deadline = time.monotonic() + 120  # the uninstaller finishes from a copy of itself in %TEMP%
        while time.monotonic() < deadline and (exe.exists() or reg_value(UNINSTALL_KEY, "UninstallString")):
            time.sleep(1)
        require(not exe.exists(), "the program is still there")
        require(not start_menu.exists() and not desktop.exists(), "a shortcut is still there")
        require(reg_value(RUN_KEY, "Swangz") is None, "the start-at-sign-in value is still there")
        require(reg_value(UNINSTALL_KEY, "UninstallString") is None, "still listed in Apps & features")
        stopped(gui, "the uninstaller did not stop the running program")
        gui = None
        require(not (data / "device.json").exists(), "local credentials left behind")
        if in_os_store:
            require(stored_secret() is None, "the device key is still in Windows Credential Manager")
        revoked = rig.gw.db.scalar("SELECT revoked FROM keys WHERE id = ?", (key_id,))  # the final enrolment's key
        require(revoked is not None, "the Hub did not disconnect the device")
        # the uninstall ran with the second person signed in: the first person's workspace folder is still theirs (R-12)
        hub_journey.kept(check, data, folder, marker, "after the uninstall, with the second person signed in")
        passed("silent uninstall while running: program stopped, device disconnected at the Hub, local credentials"
               + (" and Credential Manager entry" if in_os_store else "") + " removed, program, shortcuts, Run value"
               " and Apps & features entry gone")
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        if gui is not None and gui.poll() is None:
            gui.kill()
        if relay:
            relay.stop()
        if isinstance(sys.stderr, Tee):
            sys.stderr.close()
            sys.stderr = real_stderr
        if initialized:
            fixture.tearDown()
            shutil.rmtree(fixture.tmp, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
        (evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--browser":
        return 0  # stands in for the person's browser; the script approves the code through the Hub itself
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--setup", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--previous", type=Path, help="the previous build's installer: install it first, then upgrade to --setup")
    p.add_argument("--previous-version")
    p.add_argument("--new-version")
    args = p.parse_args()
    require(not args.previous or (args.previous_version and args.new_version), "--previous needs both versions")
    require(sys.platform == "win32", "Windows only")
    e2e(args.setup.resolve(), args.evidence.resolve(), args.previous.resolve() if args.previous else None,
        args.previous_version, args.new_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
