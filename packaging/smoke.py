"""Actions-only smoke of the built executable, using the existing isolated gateway fixture.

No test suite, external provider, credential backend override or update key is used.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def smoke(binary, report_path):
    from tests.test_devices import DeviceBase

    report = {"os": platform.system(), "arch": platform.machine(), "steps": [], "ok": False}
    fixture = DeviceBase()
    initialized = False
    timezone_dir = tempfile.TemporaryDirectory(prefix="swangz-smoke-timezone-")
    try:
        # Windows has no system IANA database. Supply only the gateway fixture's
        # current fixed EAT offset, not a runtime client dependency or a claim
        # about historical timezone rules. The desktop itself needs no tzdata.
        from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError, reset_tzpath
        try:
            ZoneInfo("Africa/Kampala")
            report["gateway_timezone"] = "system Africa/Kampala"
        except ZoneInfoNotFoundError:
            zone = Path(timezone_dir.name) / "Africa" / "Kampala"
            zone.parent.mkdir(parents=True)
            zone.write_bytes(b"TZif\x00" + b"\x00" * 15 + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
                             + struct.pack(">lbb", 3 * 3600, 0, 0) + b"EAT\x00")
            reset_tzpath([timezone_dir.name, *TZPATH])
            report["gateway_timezone"] = "fixture fixed EAT UTC+03:00 (current smoke only)"
        fixture.setUp()
        initialized = True
        rig = fixture.rig
        origin = f"http://127.0.0.1:{rig.port}"
        rig.gw.settings.public_url = origin
        # The fixture only talks to fake upstreams. Personal agents are configs;
        # the extension is downloaded from this local gateway, never the internet.
        with tempfile.TemporaryDirectory(prefix="swangz-packaged-smoke-") as tmp:
            home, data = Path(tmp) / "home", Path(tmp) / "data"
            home.mkdir()
            env = {**os.environ, "SWANGZ_HOME": str(data), "SWANGZ_TEST_HOME": str(home),
                   "BROWSER": f'"{sys.executable}" "{Path(__file__).resolve()}" --browser %s'}
            # Freeze must be self-contained; do not inherit the source interpreter's paths.
            for name in ("PYTHONPATH", "PYTHONHOME"):
                env.pop(name, None)

            def run(*args, expected=0):
                result = subprocess.run([str(binary), *args], env=env, capture_output=True,
                                        text=True, timeout=90, cwd=tmp)
                require(result.returncode == expected,
                        f"{args[0]} exited {result.returncode}, expected {expected}: "
                        + result.stdout[-3000:] + result.stderr[-3000:])
                return result

            def passed(message):
                report["steps"].append(message)
                print("PASS " + message, flush=True)

            run("--version")
            passed("packaged --version: exit 0")
            run("status", expected=2)
            passed("fresh status: exit 2 (signed out)")
            check_path = Path(tmp) / "self-check.json"
            run("--self-check", str(check_path))
            check = json.loads(check_path.read_text(encoding="utf-8"))
            require(check["frozen"] and check["window"] == "signin", "not a frozen sign-in window")
            require(not check["updates_enabled"] and check["production_keys"] == 0,
                    "production update gate changed")
            report["self_check"] = check
            passed(f"self-check: frozen imports, state, Tk {check['tk']} sign-in window; updates off, no keys")

            login = subprocess.Popen([str(binary), "login", "--server", origin, "--name", "CI UNSIGNED-TEST"],
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=tmp)
            try:
                deadline = time.monotonic() + 60
                code = None
                while time.monotonic() < deadline:
                    code = rig.gw.db.one("SELECT user_code FROM device_codes WHERE status = 'pending'")
                    if code or login.poll() is not None:
                        break
                    time.sleep(0.1)
                require(code is not None, "packaged login did not request a device code")
                status, _, _ = fixture.approve(code["user_code"], "personal")
                require(status == 200, "local browser approval failed")
                stdout, stderr = login.communicate(timeout=90)
                require(login.returncode == 0, "packaged login/sync failed: " + stdout[-3000:] + stderr[-3000:])
            finally:
                if login.poll() is None:
                    login.kill()
                    login.communicate()
            device = json.loads((data / "device.json").read_text(encoding="utf-8"))
            require(device["owner_kind"] == "personal" and device["server"] == origin, "wrong enrolled device")
            report["key_storage"] = device["key_storage"]
            passed(f"device-code sign-in + approval + initial sync: exit 0; storage={device['key_storage']}")
            before = json.loads((data / "state.json").read_text(encoding="utf-8"))["last_sync"]
            time.sleep(0.05)
            run("sync")
            state = json.loads((data / "state.json").read_text(encoding="utf-8"))
            require(state["last_sync"] > before and "access-gate" in state["installed"], "sync did not install extension")
            require(rig.gw.db.scalar("SELECT COUNT(*) FROM devices WHERE last_seen IS NOT NULL") == 1,
                    "gateway did not record the heartbeat")
            passed("second sync: exit 0; state advanced, local extension installed, gateway heartbeat recorded")
            run("status")
            passed("signed-in status: exit 0 (credential read)")
            run("logout")
            require(not (data / "device.json").exists() and not (data / "device.key").exists(),
                    "sign-out left local credentials")
            require(not (data / "extension").exists(), "sign-out left installed extension")
            require(rig.gw.db.scalar("SELECT COUNT(*) FROM keys WHERE revoked IS NOT NULL AND created_by = 'device enrolment'") == 1,
                    "gateway did not revoke the device")
            run("status", expected=2)
            passed("sign-out: exit 0; server revoked, local credentials/extension removed, status exit 2")
            report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        if initialized:
            fixture.tearDown()
            shutil.rmtree(fixture.tmp, ignore_errors=True)
        timezone_dir.cleanup()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    # webbrowser's BROWSER command invokes this no-op rather than a real browser.
    # The parent approves the pending code through the real local gateway page.
    if len(sys.argv) > 1 and sys.argv[1] == "--browser":
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    smoke(args.binary.resolve(), args.report.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
