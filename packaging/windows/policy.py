"""Deliverable 6, machine-policy integrity through the INSTALLED app on a Windows runner (D-024, W5).

The Windows twin of packaging/macos_policy.py (the macOS steps are Anvil's; this module only reuses its
platform-neutral parts: the pack from `deploy/chrome-policy/prepare.py` with CI placeholders, the two tampered
versions and the Hub read-backs). The pack goes where the app reads it on Windows, `swangz_client/machine_policy.py`
`read_windows`: `HKLM\\Software\\Policies\\Google\\Chrome` in the 64-bit view, written as Chrome's Windows policy
template does (true/false and numbers as DWORD, a list as a subkey of values named 1, 2, 3, ..., a dictionary policy
as one JSON string). The installed Swangz.exe is signed in as a company device and the Hub pins the baseline in
`enforce` mode. Then, as on macOS:

1. intact pack: `sync` reports `ok` with the baseline hash, and `open` starts the workspace window (the control case);
2. default-deny removed (`*` out of URLBlocklist): `open` is refused before anything starts and the Hub records no
   open; `sync` reports `ok: false`, and the Hub writes one audit line for the move to failing;
3. valid but not the pinned pack (an extra blocked host): `open` is refused, `sync` reports a hash that is not the
   baseline;
4. the original pack put back: `open` works again at once and the Hub has the baseline hash again;
5. the pack removed: `open` is refused and `sync` reports `ok: false`.

What this does NOT prove: that Chrome itself applies the registry policy (Chrome's own enforcement is the Linux bypass
suite, `.github/workflows/w6-step5.yml`); tampering by an administrator who also replaces the app; Group Policy or
an MDM writing the key (the journey writes it directly, as an administrator would); the report is the app's own
claim (`gateway/managed.py`), used only to take access away. Runner only: it writes HKLM (the runner is an
administrator) and removes the whole key again afterwards.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # packaging/: macos_policy and hub_journey

import macos_policy  # noqa: E402  the platform-neutral parts only; nothing in it is changed or run for macOS

KEY = r"Software\Policies\Google\Chrome"  # swangz_client/machine_policy.WINDOWS_KEYS["chrome"]
WHERE = "HKLM\\" + KEY
LISTS = ("URLBlocklist", "URLAllowlist", "ExtensionInstallBlocklist", "ExtensionInstallAllowlist", "ExtensionInstallForcelist")
JSON_STRING = ("AutoLaunchProtocolsFromOrigins",)  # machine_policy.JSON_STRING: one JSON string on Windows


def runner_only():
    """This replaces and then deletes the machine's whole Chrome policy key. On a real Swangz PC that would destroy the
    company pack and quietly switch the managed-browser controls off, so it runs on a GitHub-hosted runner only."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("runner only: this rewrites and deletes HKLM Chrome policy; it runs on a GitHub-hosted runner")


def registry_values(policy):
    """-> (scalar values {name: (kind, value)}, list subkeys {name: [str, ...]}), the way Chrome's ADMX writes them."""
    import winreg

    values, lists = {}, {}
    for name, value in policy.items():
        if name in JSON_STRING:
            values[name] = (winreg.REG_SZ, json.dumps(value, separators=(",", ":")))
        elif name in LISTS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise SystemExit(f"{name}: a list policy must be a list of strings")
            lists[name] = value
        elif isinstance(value, bool) or isinstance(value, int):
            values[name] = (winreg.REG_DWORD, int(value))
        elif isinstance(value, str):
            values[name] = (winreg.REG_SZ, value)
        else:
            values[name] = (winreg.REG_SZ, json.dumps(value, separators=(",", ":")))
    return values, lists


def _delete_tree(winreg, root, path):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return
    with key:
        while True:
            try:
                sub = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_tree(winreg, root, path + "\\" + sub)
    winreg.DeleteKeyEx(root, path, winreg.KEY_WOW64_64KEY, 0)


def remove():
    """Take the whole Chrome policy key away (64-bit view), as removing the pack would."""
    import winreg

    runner_only()
    _delete_tree(winreg, winreg.HKEY_LOCAL_MACHINE, KEY)


def present():
    import winreg

    try:
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY).Close()
        return True
    except FileNotFoundError:
        return False


def install(policy):
    """Replace the machine's Chrome policy with `policy` (no values from an earlier pack are left behind).
    Returns what the app's own reader then sees, so the step can show the write round-trips."""
    import winreg

    from swangz_client import machine_policy

    runner_only()
    values, lists = registry_values(policy)
    remove()
    access = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, KEY, 0, access) as key:
        for name, (kind, value) in values.items():
            winreg.SetValueEx(key, name, 0, kind, value)
        for name, entries in lists.items():
            with winreg.CreateKeyEx(key, name, 0, access) as sub:
                for i, entry in enumerate(entries, 1):
                    winreg.SetValueEx(sub, str(i), 0, winreg.REG_SZ, entry)
    return machine_policy.check("chrome", "win32")


def chrome_running(folder, timeout=30):
    """A chrome.exe whose command line names this workspace folder: this Open started a window (the folder and its
    Local State stay from an earlier open, so they alone prove nothing)."""
    script = ("if (Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and "
              "$_.CommandLine.Contains($env:SWANGZ_WS_FOLDER) }) { exit 0 } else { exit 1 }")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=60,
                          env={**os.environ, "SWANGZ_WS_FOLDER": str(folder)}).returncode == 0:
            return True
        time.sleep(1)
    return False


def run(check, run_app, enrol_company, owner, db, person_id, data, evidence, tool="canva"):
    """check(name, ok, detail) records a step; run_app(*args) -> (exit, output) runs the installed program;
    enrol_company() signs it in as a company device and returns its device id; `db` is the Hub's database file."""
    import hub_journey

    runner_only()  # before anything is prepared, pinned or written
    report = {"registry": WHERE, "cases": []}
    work = Path(tempfile.mkdtemp(prefix="swangz-policy-"))
    policy, baseline = macos_policy.prepare(work)
    report["baseline"] = baseline
    check("policy: pack prepared by deploy/chrome-policy/prepare.py (CI placeholders), baseline printed", bool(baseline), baseline)
    status, _ = owner.call("PUT", "/settings", {"managed_policy_sha256": baseline, "managed_policy_mode": "enforce"})
    check("policy: the admin pins the baseline in enforce mode", status == 200, f"HTTP {status}")
    try:
        seen = install(policy)
        check(f"policy: the pack is written to {WHERE} (64-bit view) and the app's reader gets the baseline back",
              seen.ok and seen.sha256 == baseline, f"ok {seen.ok}, sha {str(seen.sha256)[:16]}, problems {seen.problems}")
        device_id = enrol_company()
        row = macos_policy.device_row(db, device_id)
        check("policy: the app is signed in as a company device", row.get("owner_kind") == "company", str(row.get("owner_kind")))

        def opened(label):
            before = time.time() - 1
            code, out = run_app("open", tool)
            folders = hub_journey.workspace_folders(data)
            started = code == 0 and any(chrome_running(f) for f in folders) and any(hub_journey.chrome_wrote(f) for f in folders)
            for f in folders:
                hub_journey.close_chrome(f)
            n = macos_policy.opens(owner, person_id, before, tool)
            check(f"policy {label}: Open starts the workspace window and the Hub records it",
                  code == 0 and started and n >= 1, f"exit {code}, Chrome started {started}, opens {n}")
            report["cases"].append({"case": label, "open_exit": code, "chrome_started": started, "hub_opens": n})

        def refused(label):
            before = time.time() - 1
            code, out = run_app("open", tool)
            n = macos_policy.opens(owner, person_id, before, tool)
            check(f"policy {label}: Open is refused with the policy message and the Hub records no open",
                  code == 1 and macos_policy.REFUSED in out and n == 0, f"exit {code}, opens {n}, {out.strip()[-160:]}")
            report["cases"].append({"case": label, "open_exit": code, "hub_opens": n, "message": macos_policy.REFUSED in out})

        def synced(label, ok, sha_is_baseline):
            code, _ = run_app("sync")
            row = macos_policy.device_row(db, device_id)
            want_sha = (row.get("policy_sha") == baseline) if sha_is_baseline else (row.get("policy_sha") != baseline)
            check(f"policy {label}: sync reports it and the Hub records policy_ok={int(ok)}"
                  + (", the baseline hash" if sha_is_baseline else ", a hash that is not the baseline"),
                  code == 0 and row.get("policy_ok") == int(ok) and want_sha,
                  f"exit {code}, policy_ok {row.get('policy_ok')}, sha {str(row.get('policy_sha'))[:16]}")
            report["cases"].append({"case": label + " (sync)", "sync_exit": code, "hub_policy_ok": row.get("policy_ok"),
                                    "hub_policy_sha": row.get("policy_sha")})

        synced("intact", True, True)
        opened("intact")

        install(macos_policy.without_default_deny(policy))
        before = macos_policy.audit_lines(db, device_id)  # Open refreshes first, so its check-in may carry the report
        refused("tampered, default-deny removed")
        synced("tampered, default-deny removed", False, False)
        after = macos_policy.audit_lines(db, device_id)
        check("policy tampered: the Hub's audit log records the device reporting its policy is not in force",
              after == before + 1, f"{before} -> {after}")

        install(macos_policy.extra_block(policy))
        refused("tampered, valid but not the pinned pack")
        synced("tampered, valid but not the pinned pack", True, False)

        install(policy)
        opened("restored")
        synced("restored", True, True)

        remove()
        check("policy: pack removed", not present(), WHERE)
        refused("removed")
        synced("removed", False, False)

        code, out = run_app("logout")
        check("policy: the company device signs out", code == 0 and "removed" in out, out.strip()[-160:])
    finally:
        # each cleanup step on its own, so a key that cannot be removed does not skip the Hub reset or the evidence
        errors = []
        try:
            remove()
        except Exception as exc:  # noqa: BLE001 - recorded, and failed below
            errors.append(f"removing {WHERE}: {exc!r}")
        try:
            status, _ = owner.call("PUT", "/settings", {"managed_policy_sha256": "", "managed_policy_mode": "warn"})
            if status != 200:
                errors.append(f"resetting the Hub to warn: HTTP {status}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"resetting the Hub to warn: {exc!r}")
        report["cleanup_errors"] = errors
        try:
            (Path(evidence) / "policy-tamper.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"writing policy-tamper.json: {exc!r}")
    # reached only when every case passed: a failed cleanup is then a failed step of its own
    check("policy: the runner is restored (pack removed, Hub back to warn, evidence written)",
          not errors and not present(), "; ".join(errors) or WHERE + " gone")
    return report
