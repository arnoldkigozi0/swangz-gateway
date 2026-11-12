"""W5 of docs/MANAGED-WORKSPACE.md: is the company browser policy in force on this computer?

Reads the effective machine policy from where the OS keeps it, READ-ONLY:

* Linux: every `*.json` in `/etc/opt/chrome/policies/managed` (Chromium: `/etc/chromium/policies/managed`);
* macOS: `/Library/Managed Preferences/com.google.Chrome.plist` (Chromium: `org.chromium.Chromium`);
* Windows: `HKLM\\Software\\Policies\\Google\\Chrome` (Chromium: `...\\Chromium`) in the 64-bit view; a list policy
  is a subkey whose values are named 1, 2, 3, ...

Machine scope only: per-user copies (macOS `/Library/Managed Preferences/<user>/`, Windows HKCU) and Linux's
`recommended` folder are never read, so a person can't make the check pass from their own account. Anything doubtful
fails the check: an unreadable, invalid or oversized file, a symlink in place of a file or of the folder, a key given
twice in one file, or two sources that disagree.

It checks every control `deploy/chrome-policy/prepare.py` requires plus the default-deny and extension lists, and
reports `{"ok": bool, "sha256": "<64 hex>"}` for the heartbeat (W2 contract 2). It never writes policy, never opens
a browser profile and never reads anything a provider stored. The report is the app's own claim, a tamper signal
for the console; the server shows it as "reported by the app" and only ever uses it to take access away.

`sha256` is the **baseline hash**: SHA-256 of a canonical encoding (sorted keys, compact) of the policies in
`KNOWN`, with Windows' 0/1 numbers turned back into true/false where the policy is a true/false one (and its JSON
string turned back into a list). It is the same
on all three OSes for the same policy, unlike a hash of the file bytes, which only exists on Linux. The admin pins
the value `prepare.py` prints as "baseline".
"""

import hashlib
import json
import os
import plistlib
import stat
import sys
from pathlib import Path

REQUIRED = {
    "BrowserSignin": 0,
    "SyncDisabled": True,
    "BrowserAddPersonEnabled": False,
    "BrowserGuestModeEnabled": False,
    "IncognitoModeAvailability": 1,
    "DeveloperToolsAvailability": 2,
    "RemoteDebuggingAllowed": False,
    "PasswordManagerEnabled": False,
    "AutoLaunchProtocolsFromOrigins": [],
    "ExternalProtocolDialogShowAlwaysOpenCheckbox": False,
}
REQUIRED_BLOCKS = ("*", "file://*", "chrome://*", "view-source:*")
LISTS = ("URLBlocklist", "URLAllowlist", "ExtensionInstallBlocklist", "ExtensionInstallAllowlist", "ExtensionInstallForcelist")
KNOWN = tuple(REQUIRED) + LISTS + ("DownloadRestrictions",)
BOOLEAN = frozenset(k for k, v in REQUIRED.items() if isinstance(v, bool))
JSON_STRING = frozenset({"AutoLaunchProtocolsFromOrigins"})  # a "dictionary" policy: one JSON string on Windows
OPEN_ALLOW = frozenset({"*", "*://*", "http://*", "https://*"})
MAX_BYTES = 1 << 20

LINUX_DIRS = {"chrome": "/etc/opt/chrome/policies/managed", "chromium": "/etc/chromium/policies/managed"}
MAC_DOMAINS = {"chrome": "com.google.Chrome", "chromium": "org.chromium.Chromium"}
MAC_ROOT = "/Library/Managed Preferences"
WINDOWS_KEYS = {"chrome": r"Software\Policies\Google\Chrome", "chromium": r"Software\Policies\Chromium"}


class Unreadable(Exception):
    pass


def _bounded(path):
    """Read one policy file: a regular file, never through a symlink, at most MAX_BYTES."""
    path = Path(path)
    try:
        info = os.lstat(path)
    except OSError:
        raise Unreadable(path.name) from None
    if not stat.S_ISREG(info.st_mode):  # a symlink, folder or device in place of the file fails closed
        raise Unreadable(path.name)
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Unreadable(path.name)
    return data


def read_linux(browser="chrome", root=None):
    """-> list of (source, dict). Files are read in name order, as Chrome does."""
    folder = Path(root or LINUX_DIRS[browser])
    try:
        info = os.lstat(folder)
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(info.st_mode):  # a symlinked folder is not the machine's own policy
        raise Unreadable(folder.name)
    out = []
    for path in sorted(folder.iterdir()):
        if path.suffix != ".json" or path.name.startswith("."):
            continue
        try:
            value = json.loads(_bounded(path).decode("utf-8"), object_pairs_hook=_no_duplicates)
        except (OSError, UnicodeDecodeError, ValueError):
            raise Unreadable(path.name) from None
        if not isinstance(value, dict):
            raise Unreadable(path.name)
        out.append((path.name, value))
    return out


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def read_macos(browser="chrome", root=None):
    """The device-wide managed plist only; the per-user copy is not machine scope."""
    root = Path(root or MAC_ROOT)
    name = MAC_DOMAINS[browser] + ".plist"
    out = []
    for path in (root / name,):
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        try:
            value = plistlib.loads(_bounded(path))
        except (OSError, ValueError, plistlib.InvalidFileException):
            raise Unreadable(path.name) from None
        if not isinstance(value, dict):
            raise Unreadable(path.name)
        out.append((str(path.relative_to(root)), value))
    return out


def read_windows(browser="chrome", registry=None):
    """`registry` is `winreg` (or a stand-in with the same calls, for tests on other systems)."""
    if registry is None:
        import winreg as registry  # pragma: no cover - Windows only
    try:
        key = registry.OpenKey(registry.HKEY_LOCAL_MACHINE, WINDOWS_KEYS[browser], 0,
                               registry.KEY_READ | registry.KEY_WOW64_64KEY)
    except OSError:
        return []
    policy = {}
    with key:
        i = 0
        while True:
            try:
                name, value, _kind = registry.EnumValue(key, i)
            except OSError:
                break
            policy[name] = value
            i += 1
        i = 0
        while True:
            try:
                sub = registry.EnumKey(key, i)
            except OSError:
                break
            i += 1
            if sub not in LISTS:
                continue  # `Recommended` and anything else: not machine-enforced list policy, not read
            entries = []
            with registry.OpenKey(key, sub, 0, registry.KEY_READ | registry.KEY_WOW64_64KEY) as lst:
                j = 0
                while True:
                    try:
                        name, value, _kind = registry.EnumValue(lst, j)
                    except OSError:
                        break
                    j += 1
                    if name.isdigit():  # Chrome reads only the numbered values of a list key, so do we
                        entries.append((int(name), value))
            policy[sub] = [v for _, v in sorted(entries)]
    return [("HKLM\\" + WINDOWS_KEYS[browser], _from_registry(policy))] if policy else []


def normalise(policy):
    """The KNOWN policies only."""
    return {key: policy[key] for key in KNOWN if key in policy}


def _from_registry(policy):
    """The registry has no true/false and no lists of objects: Chrome reads a DWORD 0/1 as a boolean policy and a
    dictionary policy as one JSON string. Turn them back into what the JSON pack says. Only exact 0/1 are booleans;
    anything else stays as it is and fails the check. Linux and macOS files are typed already and are NOT coerced
    (Chrome ignores a number given for a true/false policy there)."""
    out = dict(policy)
    for key in BOOLEAN & out.keys():
        if type(out[key]) is int and out[key] in (0, 1):
            out[key] = bool(out[key])
    for key in JSON_STRING & out.keys():
        if isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except ValueError:
                pass
    return out


def baseline_sha(policy):
    encoded = json.dumps(normalise(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def merge(sources):
    """Chrome takes a policy from the first source that sets it. Two sources that disagree on a KNOWN policy are a
    problem in themselves: which one wins is not something the app should guess."""
    merged, problems = {}, []
    for _, policy in sources:
        policy = normalise(policy)
        for key, value in policy.items():
            if key in merged and merged[key] != value:
                problems.append("conflict:" + key)
            merged.setdefault(key, value)
    return merged, problems


def problems_in(policy):
    """Short names of what is missing or wrong. Never values: the report stays small and says nothing about sites."""
    out = []
    for key, want in REQUIRED.items():
        got = policy.get(key)
        if key not in policy:
            out.append("missing:" + key)
        elif type(got) is not type(want) or got != want:
            out.append("wrong:" + key)
    for key in LISTS:
        if key in policy and (not isinstance(policy[key], list) or not all(isinstance(v, str) for v in policy[key])):
            out.append("wrong:" + key)
    blocks = policy.get("URLBlocklist") if isinstance(policy.get("URLBlocklist"), list) else []
    out += ["missing_block:" + entry for entry in REQUIRED_BLOCKS if entry not in blocks]
    allow = policy.get("URLAllowlist")
    if not isinstance(allow, list) or not allow:
        out.append("missing:URLAllowlist")
    elif any(entry in OPEN_ALLOW for entry in allow if isinstance(entry, str)):
        out.append("open:URLAllowlist")
    if policy.get("ExtensionInstallBlocklist") != ["*"]:
        out.append("wrong:ExtensionInstallBlocklist")
    for key in ("ExtensionInstallAllowlist", "ExtensionInstallForcelist"):
        value = policy.get(key)
        if not isinstance(value, list) or not value:
            out.append("missing:" + key)
        elif any("SWANGZ_" in str(v) for v in value):
            out.append("placeholder:" + key)
    if any("SWANGZ_" in str(v) for v in policy.get("URLAllowlist") or []):
        out.append("placeholder:URLAllowlist")
    return list(dict.fromkeys(out))


class Result:
    def __init__(self, ok, sha256, problems, sources):
        self.ok, self.sha256, self.problems, self.sources = ok, sha256, problems, sources

    def report(self):
        """What goes in the heartbeat as `policy` (W2 contract 2). Exactly two fields."""
        return {"ok": self.ok, "sha256": self.sha256 or ""}

    def __repr__(self):
        return f"Result(ok={self.ok}, sha256={self.sha256!r}, problems={self.problems!r}, sources={self.sources!r})"


def check(browser="chrome", platform=None, **where):
    """Read and judge the machine policy. Any failure to read is a failing result, never an exception."""
    platform = platform or sys.platform
    try:
        if platform == "win32":
            sources = read_windows(browser, where.get("registry"))
        elif platform == "darwin":
            sources = read_macos(browser, where.get("root"))
        else:
            sources = read_linux(browser, where.get("root"))
    except Unreadable as exc:
        return Result(False, None, ["unreadable:" + str(exc)], [])
    except OSError:
        return Result(False, None, ["unreadable"], [])
    if not sources:
        return Result(False, None, ["missing"], [])
    merged, problems = merge(sources)
    problems += problems_in(merged)
    return Result(not problems, baseline_sha(merged), problems, [name for name, _ in sources])


def browser_kind(binary):
    """The policy family of the browser the workspace launcher starts: .deb Chromium reads Chromium's policy, not
    Chrome's, so checking Chrome's would report a policy that browser never loads."""
    name = str(binary or "").replace("\\", "/").lower()
    return "chromium" if "/chromium" in name else "chrome"


def report(browser=None, finder=None):
    """The heartbeat field for this computer: `Client.policy_check = machine_policy.report`. With no browser named it
    checks the family of the one the launcher would start; no browser found is a failing check."""
    if browser is None:
        try:
            if finder is None:
                from .workspace_launcher import find_browser as finder
            browser = browser_kind(finder())
        except Exception:
            return {"ok": False, "sha256": ""}
    return check(browser).report()
