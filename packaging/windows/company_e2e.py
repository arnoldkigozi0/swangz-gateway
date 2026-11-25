"""Company installer acceptance on a GitHub-hosted Windows runner (#333, D-026 B4, B5, B7).

    python packaging/windows/company_e2e.py --setup artifacts/Swangz-Company-Setup-0.1.1-UNSIGNED.exe
        --previous previous/Swangz-Company-Setup-0.1.0-UNSIGNED.exe --previous-version 0.1.0 --new-version 0.1.1
        --evidence evidence/company

Both installers hold the same one-folder program; the "previous" one only carries an older installer version, which is
what the upgrade and the refused downgrade look at. Steps: refused without /ALLUSERS, refused with some or empty pinned
values, refused into another folder; installed for all users with the three values; the folder is writable by
administrators only; upgrade refused while a program file is held open; upgraded without values (they are kept) while
copies run under the runner's account and under a temporary account without administrator rights, which are closed,
beside a copy in another folder, which is left running; the installed program runs from `_internal` beside it; the older
installer refused without closing anything; uninstalled while copies run (every Swangz.exe closed, program and values
removed). The values are placeholders: the copies are not signed in, nothing on the internet is contacted and no Chrome
policy or browser is touched. Exit 0 only when every step passed.

What this does NOT prove: the UAC prompt a person sees (the runner is already elevated), a standard user trying to
change the files by hand (the file permissions are read, not attacked), a copy on a second signed-in desktop (the other
account's copy runs as a scheduled task), or anything on a physical computer.
"""

import argparse
import json
import os
import platform
import secrets
import shutil
import string
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


# A temporary local account for a copy run by somebody else, and the scheduled task that starts it. Both are removed.
OTHER_USER = "swangz-ci-other"
TASK = "swangz-company-e2e"
# Every running Swangz.exe, with the program it runs from and the account that owns it.
PROCESS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$out = @(Get-CimInstance Win32_Process -Filter "Name='Swangz.exe'" | ForEach-Object {
  $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue
  [pscustomobject]@{ pid = [int]$_.ProcessId; path = $_.ExecutablePath; user = $owner.User }
})
ConvertTo-Json -InputObject $out -Compress
"""
# Holds one file open for reading, as a program that has it loaded would.
HOLD = "import sys, time; f = open(sys.argv[1], 'rb'); print('held', flush=True); time.sleep(900)"


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


def windows_powershell_env(environ, folder):
    """The environment for powershell.exe. The workflow step runs in PowerShell 7, whose PSModulePath makes Windows
    PowerShell fail to load its own modules (Get-Acl); without the variable it builds its default path."""
    env = {name: value for name, value in environ.items() if name.upper() != "PSMODULEPATH"}
    env["SWANGZ_ACL_ROOT"] = str(folder)
    return env


def powershell(script, folder, what):
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=windows_powershell_env(os.environ, folder), capture_output=True, text=True, timeout=600)
    require(done.returncode == 0, f"could not read {what}: " + done.stderr[-2000:])
    return json.loads(done.stdout)


def read_acls(folder):
    return powershell(ACL_SCRIPT, folder, "the file permissions")


def running_copies():
    return [p for p in powershell(PROCESS_SCRIPT, "", "the running processes") if p]


def users_running(processes, exe):
    """The accounts (lower case) with a process running exactly this program file."""
    wanted = str(exe).lower()
    return sorted({str(p.get("user") or "?").lower() for p in processes if str(p.get("path") or "").lower() == wanted})


def wait_for(condition, seconds=90):
    """-> True as soon as `condition()` holds, False when it still does not after `seconds`."""
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() >= deadline:
            return False
        time.sleep(2)
    return True


def new_password():
    """For the temporary account: every character class Windows may demand, 14 long (`net user` asks a question above
    that), starting with a letter so it never reads as an option. It is never printed or written down."""
    classes = (string.ascii_uppercase, string.ascii_lowercase, string.digits, "-_.")
    rest = [secrets.choice(c) for c in classes[1:]] + [secrets.choice("".join(classes[:3])) for _ in range(10)]
    secrets.SystemRandom().shuffle(rest)
    return secrets.choice(classes[0]) + "".join(rest)


def quiet(cmd, what):
    """A command whose arguments hold the temporary password: neither they nor its output are repeated."""
    try:
        done = subprocess.run([str(c) for c in cmd], capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:  # its message would repeat the arguments
        raise RuntimeError(f"could not {what} (timed out)") from None
    require(done.returncode == 0, f"could not {what} (exit {done.returncode})")


def create_other_user(password, exe):
    quiet(["net", "user", OTHER_USER, password, "/add"], "create the temporary account")
    # gives it the right to log on as a batch job, which a scheduled task needs; no administrator rights
    quiet(["net", "localgroup", "Performance Log Users", OTHER_USER, "/add"], "let the temporary account run a task")
    quiet(["schtasks", "/Create", "/F", "/TN", TASK, "/TR", f'"{exe}" --background', "/SC", "ONCE", "/ST", "00:00",
           "/RU", OTHER_USER, "/RP", password], "create the task for the temporary account")


def remove_other_user():
    for cmd in (["schtasks", "/Delete", "/F", "/TN", TASK], ["net", "user", OTHER_USER, "/delete"]):
        subprocess.run(cmd, capture_output=True, timeout=120)


def snapshot(folder):
    """-> {relative path: (size, modification time)} of every file in `folder`."""
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in folder.rglob("*") if p.is_file()}


def e2e(setup, previous, previous_version, new_version, evidence):
    runner_only()
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"os": platform.platform(), "setup": setup.name, "previous": previous.name,
              "previous_version": previous_version, "new_version": new_version, "steps": [], "ok": False}
    app_dir = Path(os.environ["ProgramW6432"]) / "Swangz"
    exe, uninstaller = app_dir / "Swangz.exe", app_dir / "unins000.exe"
    shortcut = Path(os.environ["ProgramData"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Swangz.lnk"
    own_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Swangz"
    work = Path(tempfile.mkdtemp(prefix="swangz-company-e2e-")).resolve()  # long names: process paths are compared
    pins = [SWITCHES[name] + value for name, value in PINS.items()]
    personal = work / "personal" / "Swangz.exe"  # a copy of the program elsewhere, as a person's own install would be
    started = []  # processes this journey started itself
    other_user = False
    me = os.environ["USERNAME"].lower()

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

    def app_env(data):
        env = {**os.environ, "SWANGZ_HOME": str(work / data)}
        for variable in ("PYTHONPATH", "PYTHONHOME", "SWANGZ_SERVER", "SWANGZ_ALLOW_HTTP"):
            env.pop(variable, None)
        return env

    def self_check(name):
        out = work / name
        run([exe, "--self-check", out], env=app_env("data"))
        return json.loads(out.read_text(encoding="utf-8"))

    def start_copy(program, data):
        started.append(subprocess.Popen([str(program), "--background"], env=app_env(data), cwd=work))
        return started[-1]

    def start_other_copy():
        quiet(["schtasks", "/Run", "/TN", TASK], "start the temporary account's copy")

    def all_running(company):
        """Waits for the named accounts' copies of the installed program and the personal copy, then makes sure they
        are still there a little later (a program that exits on start must not pass)."""
        def there():
            processes = running_copies()
            return users_running(processes, exe) == sorted(company) and users_running(processes, personal) == [me]

        require(wait_for(there), f"not running as expected {sorted(company)} and the other folder: {running_copies()}")
        time.sleep(8)
        require(there(), f"a copy did not stay running: {running_copies()}")
        return [{"user": p.get("user"), "path": p.get("path")} for p in running_copies()]

    try:
        require(not (own_dir / "Swangz.exe").exists(), f"a person's own install is already at {own_dir}")
        nothing_installed(app_dir)

        # 1. without /ALLUSERS: neither the default (per-person) mode nor an explicit one
        for log, args in (("no-switch.log", []), ("currentuser.log", ["/CURRENTUSER"])):
            text = install(log, *args, *pins, expected=1)
            require("Refused: This is the company build." in text, f"{log} does not say why it refused")
            nothing_installed(own_dir)
        passed("without /ALLUSERS (and with /CURRENTUSER): refused, exit 1, nothing installed or recorded")

        # 2. some of the pinned values, or switches passed empty
        empty = list(SWITCHES.values())
        for number, args in enumerate((pins[:1], pins[1:], [*pins[:2], empty[2]], empty[:1], empty,
                                       [empty[0].rstrip("=")])):
            text = install(f"partial-{number}.log", "/ALLUSERS", *args, expected=1)
            require("Refused: Pass all three of" in text, f"{args}: the log does not say why it refused")
            nothing_installed(app_dir)
        passed("one, two or an empty pinned value, /HUBHOST= alone, all three empty: refused, exit 1, nothing installed"
               " or recorded")

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

        # 6. an upgrade while something holds a program file open
        deepest = max((p for p in (app_dir / "_internal").rglob("*") if p.is_file()), key=lambda p: (len(p.parts), p))
        before = snapshot(app_dir)
        holder = subprocess.Popen([sys.executable, "-I", "-c", HOLD, str(deepest)], stdout=subprocess.PIPE, text=True,
                                  cwd=work)
        started.append(holder)
        require(holder.stdout.readline().strip() == "held", f"could not hold {deepest} open")
        text = install("in-use.log", "/ALLUSERS", expected=7)
        require("Refused: Swangz is still in use" in text, "file in use: the log does not say why it refused")
        require(holder.poll() is None, "the process holding the file was ended")
        require(snapshot(app_dir) == before and machine_values(UNINSTALL_KEY).get("DisplayVersion") == previous_version
                and machine_values(PINNED_KEY) == PINS, "the refused upgrade changed something")
        holder.kill()
        holder.wait(30)
        passed(f"upgrade while a program file is held open ({deepest.relative_to(app_dir).as_posix()}): refused, exit 7,"
               f" all {len(before)} files, the version and the values unchanged")

        # 7. upgrade without values, over a file an older version could have left behind, while copies are running
        shutil.copytree(app_dir, personal.parent)
        password = new_password()
        other_user = True
        create_other_user(password, exe)
        mine = start_copy(exe, "data-runner")
        own = start_copy(personal, "data-personal")
        start_other_copy()
        report["running_before_upgrade"] = all_running([me, OTHER_USER])
        stale = app_dir / "_internal" / "left-behind.pyd"
        stale.write_bytes(b"old")
        install("upgrade.log", "/ALLUSERS")
        require(machine_values(UNINSTALL_KEY).get("DisplayVersion") == new_version, "the upgrade did not reach Windows")
        require(machine_values(PINNED_KEY) == PINS, "the upgrade changed the pinned values")
        require(not stale.exists(), "the upgrade left an old file in _internal")
        after = running_copies()
        require(not users_running(after, exe), f"installed copies still running: {after}")
        require(mine.poll() is not None, "the runner's copy is still running")
        require(own.poll() is None, "the upgrade ended the copy in another folder")
        passed("upgrade while the installed program ran under two accounts: both copies closed, the copy in another"
               " folder left running, values kept, no old file left")
        check = self_check("self-check.json")
        report["self_check"] = check
        require(check["frozen"] and check["one_folder"] and check["window"] == "signin", f"self-check: {check}")
        require(check["version"] == new_version and check["updates_enabled"] is False, f"self-check: {check}")
        passed("the upgraded program runs its sign-in window from _internal beside it, updates off")

        # 8. the older installer is refused
        mine = start_copy(exe, "data-runner")
        all_running([me])
        before = exe.read_bytes()
        text = install("downgrade.log", "/ALLUSERS", *pins, installer=previous, expected=1)
        require(f"Refused: Swangz {new_version} is installed" in text, "downgrade: the log does not say why it refused")
        require(exe.read_bytes() == before and machine_values(UNINSTALL_KEY).get("DisplayVersion") == new_version
                and machine_values(PINNED_KEY) == PINS, "the refused downgrade changed something")
        require(mine.poll() is None and own.poll() is None, "the refused downgrade ended a running copy")
        passed("the older installer is refused, changes nothing and closes nothing")

        # 9. uninstall while copies are running
        start_other_copy()
        report["running_before_uninstall"] = all_running([me, OTHER_USER])
        run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             f"/LOG={(evidence / 'uninstall.log').resolve()}"])
        deadline = time.monotonic() + 120  # the uninstaller carries on from a copy of itself
        while time.monotonic() < deadline and (app_dir.exists() or machine_values(PINNED_KEY) is not None
                                               or machine_values(UNINSTALL_KEY) is not None):
            time.sleep(1)
        require(not app_dir.exists(), f"left behind: {sorted(str(p) for p in app_dir.rglob('*'))[:20]}")
        require(machine_values(PINNED_KEY) is None and machine_values(r"Software\Swangz") is None, "pinned values left")
        require(machine_values(UNINSTALL_KEY) is None and not shortcut.exists(), "Apps entry or shortcut left")
        require(wait_for(lambda: not running_copies(), 30), f"still running after the uninstall: {running_copies()}")
        require(personal.is_file(), "the uninstall removed the copy in another folder")
        passed("uninstall while copies ran under two accounts and from another folder: every Swangz.exe closed; program"
               " folder, shortcut, Apps entry and pinned values removed; the other folder's files kept")
        report["ok"] = True
    except Exception as exc:  # noqa: BLE001  recorded, then reported as a failure
        report["failure"] = f"{type(exc).__name__}: {exc}"
        print("FAIL " + report["failure"], file=sys.stderr)
    finally:
        for proc in started:
            if proc.poll() is None:
                proc.kill()
        if other_user:
            subprocess.run(["taskkill", "/F", "/T", "/IM", "Swangz.exe"], capture_output=True, timeout=120)
            remove_other_user()
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
