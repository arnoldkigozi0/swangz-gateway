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


def e2e(setup, evidence, previous=None, previous_version=None, new_version=None):
    """With `previous`, steps 1-5 run on the previous build and step 6 upgrades it to `setup`; otherwise step 6 reinstalls."""
    from tests.test_devices import DeviceBase

    evidence.mkdir(parents=True, exist_ok=True)
    report = {"os": platform.platform(), "setup": setup.name, "steps": [], "ok": False,
              "previous": previous.name if previous else None, "previous_version": previous_version, "new_version": new_version}
    first = previous or setup
    fixture, relay, gui, initialized = DeviceBase(), None, None, False
    work = Path(tempfile.mkdtemp(prefix="swangz-installer-e2e-"))
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
        def enrol():
            login = subprocess.Popen(    [str(exe), "login", "--server", origin, "--name", "CI installer"], env=env, cwd=work,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline, code = time.monotonic() + 90, None
                while time.monotonic() < deadline and code is None and login.poll() is None:
                    code = rig.gw.db.one("SELECT user_code FROM device_codes WHERE status = 'pending'")
                    time.sleep(0.2)
                require(code is not None, "the installed program did not ask for a device code")
                require(fixture.approve(code["user_code"], "personal")[0] == 200, "approval failed")
                out, err = login.communicate(timeout=120)
                require(login.returncode == 0, "login/sync failed: " + out[-2000:] + err[-2000:])
            finally:
                if login.poll() is None:
                    login.kill()
                    login.communicate()
            device = json.loads((data / "device.json").read_text(encoding="utf-8"))
            require(device["server"] == origin, "wrong server saved")
            return device

        device = enrol()
        key_id = device["key_id"]
        report["key_storage"] = device["key_storage"]
        from swangz_client import keystore

        def stored_secret():
            return keystore.CredentialManager().get(origin, key_id)

        def stored_fingerprint():
            # Read only into memory. Only the SHA-256, never the credential, reaches the report or a message.
            record = json.loads((data / "device.json").read_text(encoding="utf-8"))
            secret = ((data / "device.key").read_text(encoding="utf-8").strip()
                      if record["key_storage"] == "file" else stored_secret())
            require(bool(secret), "no stored device credential to compare")
            return hashlib.sha256(secret.encode()).hexdigest()

        in_os_store = device["key_storage"] != "file"
        if in_os_store:
            require(stored_secret(), "the device key is not in Windows Credential Manager")
        passed(f"enrol against the CI Hub: device code approved, first sync done; key storage {device['key_storage']}")

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

        # 5b. deliverable 5 and F-18 (packaging/hub_journey.py): the installed program opens a granted tool in its Chrome
        #     workspace window on the person's own folder; a request with its own credential is not stored by default,
        #     and once stored only a role with the trust area reads it
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # packaging/
        import hub_journey

        def check(name, ok, detail=""):
            require(ok, f"{name}: {detail}")
            passed(name + (f" ({detail})" if detail else ""))

        def run_app(*args):
            result = subprocess.run([str(exe), *args], env=env, capture_output=True, text=True, timeout=180, cwd=work)
            return result.returncode, (result.stdout + result.stderr).strip()

        owner = hub_journey.Console(origin, "owner")
        report["workspace_folder"] = hub_journey.workspace(check, run_app, data, owner, rig.person_id).name
        hub_journey.f18(check, exe, env, origin, owner, rig.person_id, cwd=work)

        # 6. upgrade to this build over a running copy (or, with no previous build, reinstall the same version): the
        #    installer closes the program; the person's device, key and settings stay, and the Hub sees the new version
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

        # 7b. revoked while away: a separate signed-in browser reaches the fixture directly, not the stopped relay.
        device = enrol()
        key_id = device["key_id"]
        app("autostart", "on")
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
        leftovers = {p.name for p in data.iterdir()} if data.exists() else set()
        require(leftovers <= {"browser-profiles"}, "revoked device left app data: " + ", ".join(sorted(leftovers)))
        require(reg_value(RUN_KEY, "Swangz") is None, "revocation left the start-at-sign-in value")
        if device["key_storage"] != "file":
            require(stored_secret() is None, "revocation left a Windows Credential Manager entry")
        require(sign_in_codes() == before_codes, "revocation issued a new sign-in code")
        app("status", expected=2)
        report["revoked_while_away"] = {"offline_exit": 1, "return_exit": 3, "signed_out_exit": 2,
                                         "kept": sorted(leftovers)}
        passed("revoked on return: sync exits 3, device data and stored key removed, startup off, status exits 2;"
               " only browser-profiles may remain (R-12)")

        # enrol again and switch start-at-sign-in back on, so uninstall is still tested against a connected device
        device = enrol()
        key_id = device["key_id"]
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
