"""Company installer acceptance on a GitHub-hosted Windows runner (#333, D-026 B4, B5, B7).

    python packaging/windows/company_e2e.py --setup artifacts/Swangz-Company-Setup-0.1.1-UNSIGNED.exe
        --previous previous/Swangz-Company-Setup-0.1.0-UNSIGNED.exe --previous-version 0.1.0 --new-version 0.1.1
        --evidence evidence/company

Both installers hold the same one-folder program; the "previous" one only carries an older installer version, which is
what the upgrade and the refused downgrade look at. Steps: refused without /ALLUSERS, refused with some of the pinned
values, refused into another folder; installed for all users with the three values; the folder is writable by
administrators only; the installed program runs from `_internal` beside it; upgraded without values (they are kept);
the older installer refused; uninstalled (program and values removed). The values are placeholders: nothing on the
internet is contacted and no Chrome policy or browser is touched. Exit 0 only when every step passed.

What this does NOT prove: the UAC prompt a person sees (the runner is already elevated), a standard user trying to
change the files by hand (the file permissions are read, not attacked), or anything on a physical computer.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

APP_ID = "{c2bec2d1-7154-4e30-8880-089c20048f8e}"
UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_ID + "_is1"
PINNED_KEY = r"Software\Swangz\Pinned"
PINS = {"hub_host": "hub.swangz-ci.dev", "extension_id": "abcdefghijklmnopabcdefghijklmnop",
        "extension_update_url": "https://clients2.google.com/service/update2/crx"}
SWITCHES = {"hub_host": "/HUBHOST=", "extension_id": "/EXTENSIONID=", "extension_update_url": "/EXTENSIONUPDATEURL="}
# Administrators, SYSTEM, TrustedInstaller: the only accounts that may own or change the program (D-026 B5).
TRUSTED = frozenset({"S-1-5-32-544", "S-1-5-18",
                     "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"})
# Write or append data, write (extended) attributes, delete (children), change permissions or owner, generic write/all.
CHANGE = 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000

# Reads owner and access rules, as SIDs, of the program folder, everything in it, and its parent (Program Files).
ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$sid = [System.Security.Principal.SecurityIdentifier]
$root = $env:SWANGZ_ACL_ROOT
$items = @(Get-Item -LiteralPath (Split-Path $root)) + @(Get-Item -LiteralPath $root) + @(Get-ChildItem -LiteralPath $root -Recurse -Force)
$out = foreach ($item in $items) {
  $acl = Get-Acl -LiteralPath $item.FullName
  [pscustomobject]@{
    path = $item.FullName
    owner = $acl.GetOwner($sid).Value
    rules = @($acl.GetAccessRules($true, $true, $sid) | ForEach-Object {
      [pscustomobject]@{
        sid = $_.IdentityReference.Value
        allow = ($_.AccessControlType -eq 'Allow')
        rights = [int]$_.FileSystemRights
        inherit_only = (($_.PropagationFlags -band [System.Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0)
      }
    })
  }
}
ConvertTo-Json -InputObject @($out) -Depth 5 -Compress
"""


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def runner_only():
    """This installs into Program Files, writes the pinned company values in HKLM and removes both again. On a real
    Swangz PC that would delete the company's pins, so it runs on a GitHub-hosted runner only."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("runner only: this installs for all users and deletes the pinned values; "
                         "it runs on a GitHub-hosted runner")


def acl_problems(items):
    """Every way an account other than Administrators, SYSTEM or TrustedInstaller owns or may change one of `items`.
    Inherit-only rules (CREATOR OWNER on Program Files) grant nothing on the item itself."""
    problems = []
    for item in items:
        if item["owner"] not in TRUSTED:
            problems.append(f"{item['path']}: owned by {item['owner']}")
        for rule in item["rules"]:
            if rule["allow"] and not rule["inherit_only"] and rule["sid"] not in TRUSTED and rule["rights"] & CHANGE:
                problems.append(f"{item['path']}: {rule['sid']} may change it (rights {rule['rights'] & 0xFFFFFFFF:#x})")
    return problems


def machine_values(key):
    """-> {name: value} of an HKLM key in the 64-bit view, or None when the key is absent."""
    import winreg

    try:
        handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return None
    with handle:
        found = (winreg.EnumValue(handle, i) for i in range(winreg.QueryInfoKey(handle)[1]))
        return {name: value for name, value, _ in found}


def person_has_key(key):
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, key))
    except FileNotFoundError:
        return False
    return True


def read_acls(folder):
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ACL_SCRIPT],
                          env={**os.environ, "SWANGZ_ACL_ROOT": str(folder)}, capture_output=True, text=True, timeout=600)
    require(done.returncode == 0, "could not read the file permissions: " + done.stderr[-2000:])
    return json.loads(done.stdout)


def e2e(setup, previous, previous_version, new_version, evidence):
    runner_only()
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"os": platform.platform(), "setup": setup.name, "previous": previous.name,
              "previous_version": previous_version, "new_version": new_version, "steps": [], "ok": False}
    app_dir = Path(os.environ["ProgramW6432"]) / "Swangz"
    exe, uninstaller = app_dir / "Swangz.exe", app_dir / "unins000.exe"
    shortcut = Path(os.environ["ProgramData"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Swangz.lnk"
    own_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Swangz"
    work = Path(tempfile.mkdtemp(prefix="swangz-company-e2e-"))
    pins = [SWITCHES[name] + value for name, value in PINS.items()]

    def passed(message):
        report["steps"].append(message)
        print("PASS " + message, flush=True)

    def run(cmd, expected=0, env=None, timeout=180):
        done = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, cwd=work, env=env)
        require(done.returncode == expected, f"{cmd[0]} {cmd[1:]} exited {done.returncode}, expected {expected}: "
                + done.stdout[-2000:] + done.stderr[-2000:])

    def install(log, *args, installer=setup, expected=0):
        run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={(evidence / log).resolve()}", *args],
            expected=expected)
        return (evidence / log).read_text(encoding="utf-8-sig", errors="replace")

    def nothing_installed(where):
        require(not (where / "Swangz.exe").exists(), f"installed into {where}")
        require(not exe.exists(), f"installed into {app_dir}")
        require(machine_values(PINNED_KEY) is None, "pinned values were written")
        require(machine_values(UNINSTALL_KEY) is None and not person_has_key(UNINSTALL_KEY), "an Apps entry was written")

    def self_check(name):
        out = work / name
        env = {**os.environ, "SWANGZ_HOME": str(work / "data")}
        for variable in ("PYTHONPATH", "PYTHONHOME", "SWANGZ_SERVER", "SWANGZ_ALLOW_HTTP"):
            env.pop(variable, None)
        run([exe, "--self-check", out], env=env)
        return json.loads(out.read_text(encoding="utf-8"))

    try:
        require(not (own_dir / "Swangz.exe").exists(), f"a person's own install is already at {own_dir}")
        nothing_installed(app_dir)

        # 1. without /ALLUSERS: neither the default (per-person) mode nor an explicit one
        for log, args in (("no-switch.log", []), ("currentuser.log", ["/CURRENTUSER"])):
            text = install(log, *args, *pins, expected=1)
            require("Refused: This is the company build." in text, f"{log} does not say why it refused")
            nothing_installed(own_dir)
        passed("without /ALLUSERS (and with /CURRENTUSER): refused, exit 1, nothing installed or recorded")

        # 2. some of the pinned values
        for number, args in enumerate((pins[:1], pins[1:], [*pins[:2], SWITCHES["extension_update_url"]])):
            text = install(f"partial-{number}.log", "/ALLUSERS", *args, expected=1)
            require("Refused: Pass all three of" in text, "partial values: the log does not say why it refused")
            nothing_installed(app_dir)
        passed("one, two or an empty pinned value: refused, exit 1, nothing installed or recorded")

        # 3. into another folder
        elsewhere = work / "elsewhere"
        text = install("other-folder.log", "/ALLUSERS", f"/DIR={elsewhere}", *pins, expected=7)
        require("Refused: The company build installs only into" in text, "other folder: the log does not say why")
        nothing_installed(elsewhere)
        passed("/DIR= outside Program Files\\Swangz: refused before installing (exit 7)")

        # 4. all users, with the values
        install("install.log", "/ALLUSERS", "/TASKS=desktopicon", *pins, installer=previous)
        require(exe.is_file() and (app_dir / "_internal").is_dir(), f"no one-folder program in {app_dir}")
        require(shortcut.is_file(), f"no Start-menu shortcut for everyone at {shortcut}")
        require(not (own_dir / "Swangz.exe").exists() and not person_has_key(UNINSTALL_KEY),
                "something was installed for one person only")
        entry = machine_values(UNINSTALL_KEY)
        require(entry and entry.get("DisplayVersion") == previous_version, f"Apps entry: {entry}")
        recorded = machine_values(PINNED_KEY)
        require(recorded == PINS, f"pinned values: {recorded}")
        sys.path.insert(0, str(ROOT / "deploy" / "chrome-policy"))
        import prepare  # the validators the later policy step uses: what was recorded must pass them

        prepare.hostname(recorded["hub_host"])
        require(prepare.EXTENSION_ID.fullmatch(recorded["extension_id"]), "extension_id is not valid")
        prepare.update_address(recorded["extension_update_url"])
        report["installed"] = {"folder": str(app_dir), "pinned": recorded, "display_version": entry["DisplayVersion"]}
        passed("installed for all users into Program Files\\Swangz: one-folder program, shortcut for everyone, the three"
               " values in HKLM\\Software\\Swangz\\Pinned (64-bit), accepted by prepare.py's validators")

        # 5. only administrators can change it
        items = read_acls(app_dir)
        require(len(items) > 3, f"only {len(items)} items were read")
        problems = acl_problems(items)
        report["acl"] = {"items": len(items), "problems": problems[:50]}
        require(not problems, f"{len(problems)} permission problems, first: {problems[:5]}")
        passed(f"owner and write permissions of Program Files, the program folder and all {len(items) - 2} items in it:"
               " Administrators, SYSTEM and TrustedInstaller only")

        # 6. upgrade without values, over a file an older version could have left behind
        stale = app_dir / "_internal" / "left-behind.pyd"
        stale.write_bytes(b"old")
        install("upgrade.log", "/ALLUSERS")
        require(machine_values(UNINSTALL_KEY).get("DisplayVersion") == new_version, "the upgrade did not reach Windows")
        require(machine_values(PINNED_KEY) == PINS, "the upgrade changed the pinned values")
        require(not stale.exists(), "the upgrade left an old file in _internal")
        check = self_check("self-check.json")
        report["self_check"] = check
        require(check["frozen"] and check["one_folder"] and check["window"] == "signin", f"self-check: {check}")
        require(check["version"] == new_version and check["updates_enabled"] is False, f"self-check: {check}")
        passed("upgrade without values: values kept, no old file left; the installed program runs its sign-in window from"
               " _internal beside it, updates off")

        # 7. the older installer is refused
        before = exe.read_bytes()
        text = install("downgrade.log", "/ALLUSERS", *pins, installer=previous, expected=1)
        require(f"Refused: Swangz {new_version} is installed" in text, "downgrade: the log does not say why it refused")
        require(exe.read_bytes() == before and machine_values(UNINSTALL_KEY).get("DisplayVersion") == new_version
                and machine_values(PINNED_KEY) == PINS, "the refused downgrade changed something")
        passed("the older installer is refused and changes nothing")

        # 8. uninstall
        run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             f"/LOG={(evidence / 'uninstall.log').resolve()}"])
        deadline = time.monotonic() + 120  # the uninstaller carries on from a copy of itself
        while time.monotonic() < deadline and (app_dir.exists() or machine_values(PINNED_KEY) is not None
                                               or machine_values(UNINSTALL_KEY) is not None):
            time.sleep(1)
        require(not app_dir.exists(), f"left behind: {sorted(str(p) for p in app_dir.rglob('*'))[:20]}")
        require(machine_values(PINNED_KEY) is None and machine_values(r"Software\Swangz") is None, "pinned values left")
        require(machine_values(UNINSTALL_KEY) is None and not shortcut.exists(), "Apps entry or shortcut left")
        passed("uninstall: program folder, shortcut, Apps entry and pinned values removed")
        report["ok"] = True
    except Exception as exc:  # noqa: BLE001  recorded, then reported as a failure
        report["failure"] = f"{type(exc).__name__}: {exc}"
        print("FAIL " + report["failure"], file=sys.stderr)
    finally:
        if uninstaller.is_file():
            subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=180)
        (evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--setup", required=True)
    ap.add_argument("--previous", required=True)
    ap.add_argument("--previous-version", required=True)
    ap.add_argument("--new-version", required=True)
    ap.add_argument("--evidence", required=True)
    args = ap.parse_args(argv)
    runner_only()
    return e2e(Path(args.setup).resolve(), Path(args.previous).resolve(), args.previous_version, args.new_version,
               Path(args.evidence).resolve())


if __name__ == "__main__":
    sys.exit(main())
