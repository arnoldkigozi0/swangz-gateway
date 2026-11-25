"""W5 of docs/MANAGED-WORKSPACE.md: is the company browser policy in force on this computer?

Reads the effective machine policy from where the OS keeps it, READ-ONLY:

* Linux: every file in `/etc/opt/chrome/policies/managed` (Debian Chromium: `/etc/chromium/policies/managed`, Ubuntu's
  chromium-browser: `/etc/chromium-browser/policies/managed`). Chrome applies every file there, so a file that is not
  valid `*.json` policy fails the check rather than being skipped;
* macOS: `/Library/Managed Preferences/com.google.Chrome.plist` (Chromium: `org.chromium.Chromium`);
* Windows: `HKLM\\Software\\Policies\\Google\\Chrome` (Chromium: `...\\Chromium`) in the 64-bit view; a list policy
  is a subkey whose values are named 1, 2, 3, ...

Machine scope only: per-user copies (macOS `/Library/Managed Preferences/<user>/`, Windows HKCU), Windows'
`Recommended` subkey and Linux's `recommended` folder never count towards a pass, so a person can't make the check
pass from their own account. D-026 E3 reads HKCU, `Recommended` and `recommended` only to FAIL the check: any value
there fills a gap the machine key leaves (`user_policy:<name>`, `recommended`). Anything doubtful fails the check: an
unreadable, invalid or oversized file, a hidden file, a symlink in place of a file or of the folder, a key given
twice in one file, two sources that disagree, or a policy name the pack does not set (`unexpected:<name>`).

D-026 E3 `ownership()` says, read only, whether the Windows key is still exactly what Swangz wrote (the marker hash),
and E5 `setup_report()` lists the controls Chrome may ignore on an unmanaged computer. Nothing here writes policy.

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
import re
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
EXTRA = "\x00problems"  # read_windows' own findings travel with its source under a name no policy can have
# D-024 point 5: policies the pack never sets that would quietly undo it. ExtensionSettings can re-allow every extension
# over ExtensionInstallBlocklist; the merge lists let a second source add entries the app never sees; the cloud override
# lets a cloud policy win over the machine's. Present at all, with any value, is a problem. Never part of the hash.
FORBIDDEN = ("ExtensionSettings", "PolicyListMultipleSourceMergeList", "PolicyDictionaryMultipleSourceMergeList",
             "CloudPolicyOverridesPlatformPolicy")
BOOLEAN = frozenset(k for k, v in REQUIRED.items() if isinstance(v, bool))
JSON_STRING = frozenset({"AutoLaunchProtocolsFromOrigins"})  # a "dictionary" policy: one JSON string on Windows
OPEN_ALLOW = frozenset({"*", "*://*", "http://*", "https://*"})
# An allowlist entry that would reopen what the blocklist closes: a non-https scheme (data:, chrome:, file:, …), this
# machine or a bare address, or a Google account surface (mail, drive, account settings, the whole of google.com).
# Sign-in hops such as .accounts.google.com and path-scoped entries such as www.google.com/recaptcha stay allowed.
ACCOUNT_SURFACES = frozenset({"google.com", "www.google.com", "mail.google.com", "drive.google.com", "docs.google.com",
                              "myaccount.google.com", "photos.google.com", "contacts.google.com", "takeout.google.com",
                              "gmail.com", "www.gmail.com", "googlemail.com", "www.googlemail.com"})
# Chrome reads a host made only of numbers as an IPv4 address in any base: 0x7f000001, 0x7f.0.0.1, 0177.0.0.1, 2130706433.
NUMERIC_HOST = re.compile(r"(?:0x[0-9a-f]*|\d+)(?:\.(?:0x[0-9a-f]*|\d+))*")
MAX_BYTES = 1 << 20

LINUX_DIRS = {"chrome": "/etc/opt/chrome/policies/managed", "chromium": "/etc/chromium/policies/managed",
              "chromium-browser": "/etc/chromium-browser/policies/managed"}
# The exact browser the workspace launcher may start (workspace_launcher.LINUX_BROWSERS / MAC_BROWSERS) -> the policy
# family it reads. Anything else has no known policy home, so its check fails.
BROWSERS = {"/opt/google/chrome/chrome": "chrome", "/usr/lib/chromium/chromium": "chromium",
            "/usr/lib/chromium-browser/chromium-browser": "chromium-browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome": "chrome"}
WINDOWS_TAIL = ("google", "chrome", "application", "chrome.exe")
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
        if path.name.startswith(".") or path.suffix != ".json":  # D-026 E4 S3: a hidden file is never judged  # Chrome loads it anyway: a policy we can't judge fails the check
            raise Unreadable(path.name)
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
    policy, extra = {}, []
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
            if sub == "Recommended":
                if _key_has_anything(registry, key, sub):
                    extra.append("recommended")  # D-026 E3 (c): a recommendation fills what the pack leaves open
                continue
            if sub not in LISTS and sub not in FORBIDDEN:
                extra.append("unexpected:" + sub)  # D-026 E3 (a): never read as policy, always reported
                continue
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
    if extra:
        policy[EXTRA] = extra
    return [("HKLM\\" + WINDOWS_KEYS[browser], _from_registry(policy))] if policy else []


def _key_has_anything(registry, parent, sub):
    with registry.OpenKey(parent, sub, 0, registry.KEY_READ | registry.KEY_WOW64_64KEY) as key:
        for enum in (registry.EnumValue, registry.EnumKey):
            try:
                enum(key, 0)
                return True
            except OSError:
                pass
    return False


def read_windows_user(browser="chrome", registry=None):
    """D-026 E3 (b): HKCU's Chrome policy. Never part of the pack: any value or list there fills a gap the machine key
    leaves, so each name is a problem. Read only to fail the check, never to pass it."""
    if registry is None:
        import winreg as registry  # pragma: no cover - Windows only
    try:
        key = registry.OpenKey(registry.HKEY_CURRENT_USER, WINDOWS_KEYS[browser], 0,
                               registry.KEY_READ | registry.KEY_WOW64_64KEY)
    except OSError:
        return []
    names = []
    with key:
        for enum in (lambda i: registry.EnumValue(key, i)[0], lambda i: registry.EnumKey(key, i)):
            i = 0
            while True:
                try:
                    names.append(enum(i))
                except OSError:
                    break
                i += 1
    return ["user_policy:" + n for n in names]


def read_linux_recommended(browser="chrome", root=None):
    """D-026 E3 (c) on Linux: Chrome also loads `recommended` next to `managed`; anything in it is a problem."""
    folder = Path(root or LINUX_DIRS[browser]).parent / "recommended"
    try:
        info = os.lstat(folder)
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(info.st_mode):
        return ["recommended"]
    return ["recommended"] if any(True for _ in folder.iterdir()) else []


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
        problems += policy.get(EXTRA, []) if isinstance(policy.get(EXTRA), list) else []
        # D-026 E3 (a): a name the pack does not set (ProxySettings, CloudManagementEnrollmentToken, ...) fails
        problems += ["unexpected:" + k for k in policy if k not in KNOWN and k not in FORBIDDEN and k != EXTRA]
        for key in FORBIDDEN:  # kept for problems_in(), whatever the value; baseline_sha() never sees them
            if key in policy:
                merged.setdefault(key, policy[key])
        policy = normalise(policy)
        for key, value in policy.items():
            if key in merged and merged[key] != value:
                problems.append("conflict:" + key)
            merged.setdefault(key, value)
    return merged, problems


def allow_problem(entry):
    """-> None for an acceptable URLAllowlist entry, else the short reason (open / scheme / local / account / host)."""
    e = entry.strip().lower()
    if e in OPEN_ALLOW:
        return "open"
    scheme, rest = None, e
    if "://" in e:
        scheme, rest = e.split("://", 1)
    else:
        m = re.match(r"([a-z][a-z0-9+-]*):(?!\d+(?:[/@]|$))", e)
        if m:
            return "scheme"
    if scheme not in (None, "https"):
        return "open" if scheme == "*" else "scheme"
    authority = re.split(r"[/?#]", rest, 1)[0]
    userinfo = "@" in authority  # "user@mail.google.com" still names mail.google.com
    hostport = authority.rsplit("@", 1)[-1]
    path = rest[len(authority):].strip("/")
    if hostport.startswith("["):
        return "local"
    host = hostport.rsplit(":", 1)[0] if ":" in hostport else hostport
    host = host.lstrip(".")
    dotted = host.endswith(".")  # "mail.google.com." is the same site as "mail.google.com" to the browser
    host = host.rstrip(".")
    if not host or host == "*" or "*" in host:
        return "open"
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or NUMERIC_HOST.fullmatch(host):
        return "local"
    google_path = host in ("google.com", "www.google.com") and path and not path.startswith("accounts")
    mail = host.endswith((".gmail.com", ".googlemail.com"))  # every Gmail host, e.g. mail.googlemail.com
    if (host in ACCOUNT_SURFACES or mail) and not google_path:
        return "account"
    if dotted or userinfo:
        return "host"
    return None


def problems_in(policy):
    """Short names of what is missing or wrong. Never values: the report stays small and says nothing about sites."""
    out = ["forbidden:" + key for key in FORBIDDEN if key in policy]
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
    else:
        out += [allow_problem(e) + ":URLAllowlist" for e in allow if isinstance(e, str) and allow_problem(e)]
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
    table = WINDOWS_KEYS if platform == "win32" else MAC_DOMAINS if platform == "darwin" else LINUX_DIRS
    if browser not in table:
        return Result(False, None, ["unknown_browser"], [])
    try:
        outside = []
        if platform == "win32":
            sources = read_windows(browser, where.get("registry"))
            outside = read_windows_user(browser, where.get("registry"))
        elif platform == "darwin":
            sources = read_macos(browser, where.get("root"))
        else:
            sources = read_linux(browser, where.get("root"))
            outside = read_linux_recommended(browser, where.get("root"))
    except Unreadable as exc:
        return Result(False, None, ["unreadable:" + str(exc)], [])
    except OSError:
        return Result(False, None, ["unreadable"], [])
    except Exception:  # D-026 E4 S2: whatever a reader raises, a direct caller gets a failing result
        return Result(False, None, ["unreadable"], [])
    if not sources:
        return Result(False, None, ["missing"] + outside, [])
    try:
        merged, problems = merge(sources)
        problems = outside + problems + problems_in(merged)
        sha = baseline_sha(merged)
    except Exception:  # D-026 E4 S2: a TypeError or RecursionError from merge or problems_in is unreadable
        return Result(False, None, ["unreadable"], [name for name, _ in sources])
    return Result(not problems, sha, list(dict.fromkeys(problems)), [name for name, _ in sources])


def browser_kind(binary):
    """The policy family of the browser the workspace launcher starts: .deb Chromium reads Chromium's policy, not
    Chrome's, so checking Chrome's would report a policy that browser never loads."""
    if not isinstance(binary, str):
        return None
    if binary in BROWSERS:
        return BROWSERS[binary]
    parts = tuple(binary.replace("\\", "/").lower().split("/"))
    if len(parts) > 4 and ":" in parts[0] and parts[-4:] == WINDOWS_TAIL:  # %ProgramFiles%\Google\Chrome\...
        return "chrome"
    return None


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
        if browser is None:
            return {"ok": False, "sha256": ""}
    return check(browser).report()


# ------------------------------------------------------------------ D-026 E3: is the key still exactly ours? (read only)

MARKER_KEY = r"Software\Swangz\ChromePolicy"
TREE_LIMIT = 10000  # values and subkeys read before the key counts as unreadable
TREE_DEPTH = 8


def _data(value):
    if isinstance(value, (bytes, bytearray)):
        return "hex:" + bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [_data(v) for v in value]
    return value


def read_tree(registry, root, path):
    """Every (subkey path, value name lowercased, registry type, data) under root\\path in the 64-bit view, or None
    when the key is absent. Unreadable on any error or on a tree larger than TREE_LIMIT / deeper than TREE_DEPTH."""
    access = registry.KEY_READ | registry.KEY_WOW64_64KEY
    out, count = [], 0

    def walk(key, rel, depth):
        nonlocal count
        if depth > TREE_DEPTH:
            raise Unreadable("depth")
        i = 0
        while True:
            try:
                name, value, kind = registry.EnumValue(key, i)
            except OSError:
                break
            i += 1
            count += 1
            out.append((rel, name.lower(), kind, _data(value)))
        i, subs = 0, []
        while True:
            try:
                subs.append(registry.EnumKey(key, i))
            except OSError:
                break
            i += 1
        count += len(subs)
        if count > TREE_LIMIT:
            raise Unreadable("size")
        for sub in subs:
            with registry.OpenKey(key, sub, 0, access) as child:
                walk(child, (rel + "\\" + sub) if rel else sub, depth + 1)

    try:
        key = registry.OpenKey(registry.HKEY_LOCAL_MACHINE, path, 0, access)
    except FileNotFoundError:
        return None
    with key:
        walk(key, "", 0)
    return out


def tree_sha(entries):
    """The E3 hash: entries sorted and serialised with sort_keys. Order-independent; any type, name or data change
    changes it. The same function hashes the key before any change and as read back after a write."""
    rows = sorted(entries, key=lambda e: json.dumps(e, sort_keys=True, ensure_ascii=True))
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_marker(registry):
    """-> {"sha256": str, "written": ...} or None when the marker key is absent."""
    try:
        key = registry.OpenKey(registry.HKEY_LOCAL_MACHINE, MARKER_KEY, 0, registry.KEY_READ | registry.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return None
    marker, i = {}, 0
    with key:
        while True:
            try:
                name, value, _kind = registry.EnumValue(key, i)
            except OSError:
                break
            i += 1
            marker[name.lower()] = value
    return marker


def ownership(registry=None, browser="chrome"):
    """D-026 E3, read only: what a policy-write or policy-remove would be allowed to do on this computer now.
    -> (state, detail) with state one of
       "absent"        key absent, marker absent: a write may create it;
       "ours"          key present, marker hash equals the key read now: rewrite or remove may act;
       "conflict"      key present and no marker, or a different hash: change nothing, report it;
       "stale_marker"  key absent, marker present: only the marker may go;
       "unreadable"    anything could not be read: treated like a conflict.
    Nothing here writes; the writer (B5, elevated) is not part of the app yet."""
    if registry is None:
        import winreg as registry  # pragma: no cover - Windows only
    try:
        entries = read_tree(registry, registry.HKEY_LOCAL_MACHINE, WINDOWS_KEYS[browser])
        marker = read_marker(registry)
    except Exception:
        return "unreadable", None
    current = None if entries is None else tree_sha(entries)
    pinned = marker.get("sha256") if isinstance(marker, dict) else None
    if entries is None:
        return ("stale_marker", None) if marker is not None else ("absent", None)
    if not isinstance(pinned, str) or pinned != current:
        return "conflict", current
    return "ours", current


# ------------------------------------------------------------------ D-026 E5: what this computer may not enforce

WEB_STORE_UPDATE = "https://clients2.google.com/service/update2/crx"
# The pack's controls, all "configured" until the physical chrome://policy acceptance check shows OK on that machine
# type. Add a machine type here only with that evidence (D-026 E5); until then nothing is reported as enforced.
ACCEPTED = frozenset()


def management(platform=None, run=None, registry=None, netjoin=None):
    """-> {"domain": True/False/None, "mdm": True/False/None}. None means it could not be read, never "no".
    Read only, nothing elevated."""
    platform = platform or sys.platform
    out = {"domain": None, "mdm": None}
    if platform == "win32":
        try:
            out["domain"] = (netjoin or _windows_joined)()
        except Exception:
            pass
        try:
            out["mdm"] = _windows_mdm(registry)
        except Exception:
            pass
    elif platform == "darwin":
        import subprocess
        run = run or subprocess.run
        try:
            done = run(["/usr/bin/profiles", "status", "-type", "enrollment"], capture_output=True, text=True,
                       timeout=20, stdin=subprocess.DEVNULL)
            if done.returncode == 0:
                text = done.stdout.lower()
                out["mdm"] = "mdm enrollment: yes" in text
        except Exception:
            pass
        try:
            done = run(["/usr/sbin/dsconfigad", "-show"], capture_output=True, text=True, timeout=20,
                       stdin=subprocess.DEVNULL)
            if done.returncode == 0:
                out["domain"] = "active directory domain" in done.stdout.lower()
        except Exception:
            pass
    return out


def _windows_joined():  # pragma: no cover - Windows only
    """NetGetJoinInformation: 3 = joined to a domain."""
    import ctypes
    from ctypes import wintypes
    netapi = ctypes.WinDLL("netapi32")
    name, status = wintypes.LPWSTR(), ctypes.c_int()
    if netapi.NetGetJoinInformation(None, ctypes.byref(name), ctypes.byref(status)) != 0:
        raise OSError("NetGetJoinInformation")
    netapi.NetApiBufferFree(name)
    return status.value == 3


def _windows_mdm(registry=None):
    """An MDM enrolment leaves a subkey of HKLM\\SOFTWARE\\Microsoft\\Enrollments with a ProviderID."""
    if registry is None:
        import winreg as registry  # pragma: no cover - Windows only
    access = registry.KEY_READ | registry.KEY_WOW64_64KEY
    try:
        root = registry.OpenKey(registry.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Enrollments", 0, access)
    except FileNotFoundError:
        return False
    with root:
        i = 0
        while True:
            try:
                sub = registry.EnumKey(root, i)
            except OSError:
                return False
            i += 1
            try:
                with registry.OpenKey(root, sub, 0, access) as key:
                    j = 0
                    while True:
                        try:
                            name, value, _ = registry.EnumValue(key, j)
                        except OSError:
                            break
                        j += 1
                        if name.lower() == "providerid" and value:
                            return True
            except OSError:
                continue


def not_guaranteed(policy, managed, platform=None, accepted=ACCEPTED):
    """D-026 E5: the pack's controls Chrome may ignore on this computer, as short names. Never says "enforced":
    `enforced` is True only for a machine type in `accepted` (none yet). Unknown management counts as unmanaged."""
    platform = platform or sys.platform
    is_managed = bool(managed.get("domain") or managed.get("mdm"))
    out = []
    if platform in ("win32", "darwin") and not is_managed:
        forced = policy.get("ExtensionInstallForcelist") if isinstance(policy, dict) else None
        for entry in forced if isinstance(forced, list) else []:
            if not isinstance(entry, str):
                continue
            ext, _, update = entry.partition(";")
            if update and update.strip() != WEB_STORE_UPDATE:
                out.append("ExtensionInstallForcelist:off_store:" + ext.strip()[:32])
    machine = platform + (":managed" if is_managed else ":unmanaged")
    return {"machine": machine, "not_guaranteed": out, "enforced": machine in accepted}


def setup_report(platform=None, browser="chrome", **where):
    """What setup shows before the admin confirms (E5), read only: the check, how the machine is managed, and the
    controls listed as "not guaranteed on this computer". Never writes, never elevates, `enforce` stays off."""
    platform = platform or sys.platform
    result = check(browser, platform, **where)
    managed = management(platform, where.get("run"), where.get("registry"), where.get("netjoin"))
    try:
        sources = (read_windows(browser, where.get("registry")) if platform == "win32" else
                   read_macos(browser, where.get("root")) if platform == "darwin" else
                   read_linux(browser, where.get("root")))
        merged, _ = merge(sources)
    except Exception:
        merged = {}
    gaps = not_guaranteed(merged, managed, platform)
    lines = []
    for problem in result.problems:
        lines.append("Problem: " + problem)
    if managed["domain"] is None and managed["mdm"] is None and platform in ("win32", "darwin"):
        lines.append("Could not read whether this computer is managed; treated as unmanaged.")
    for gap in gaps["not_guaranteed"]:
        lines.append("Not guaranteed on this computer: " + gap)
    if not gaps["enforced"]:
        lines.append("Not yet confirmed as enforced: no chrome://policy acceptance check on this machine type.")
    out = {"ok": result.ok, "problems": result.problems, "management": managed, **gaps, "lines": lines}
    if platform == "win32":
        state, _ = ownership(where.get("registry"), browser)
        out["ownership"] = state
        if state in ("conflict", "unreadable"):
            lines.append("Conflict: the Chrome policy on this computer is not exactly what Swangz wrote. "
                         "Nothing was changed; an administrator must resolve it.")
    return out
