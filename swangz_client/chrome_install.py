"""D-026 A1, B1-B6: install Google Chrome when it is missing, on Windows only, from Google only, with consent.

Two halves:

- ``request_install`` runs in the person's own (unelevated) app. On macOS and Linux it installs nothing (B6) and says
  which install it will accept. On Windows it offers the elevated step only when the app is the company build in
  ``%ProgramFiles%`` (B5); the per-user build answers "ask your administrator to install the company build". After the
  person agrees to a step that says exactly what will change, the only elevation is the UAC prompt (B1). Declining
  either changes nothing.
- ``admin_main`` is the elevated process, ``Swangz.exe admin <action>`` and nothing else (B3). It reads no environment
  variable and nothing from the person's folders: system programs come from ``GetSystemDirectory``, folders from
  ``SHGetKnownFolderPath``. It checks that it is itself admin-only code (B5), downloads Google's enterprise MSI into a
  fresh admin-only staging folder, checks the MSI is signed by Google LLC (A2), runs ``msiexec``, deletes the staging
  folder whatever happens, and checks the installed ``chrome.exe`` again (A3/A4).

Everything that touches Windows goes through ``Windows`` so the logic is tested on any system.
"""

import json
import ntpath
import os
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import chrome_verify

MSI_URL = "https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi"  # A1, observed 25 Nov 2026
INSTALL_PAGE = "https://www.google.com/chrome/"  # the same page as workspace_launcher.INSTALL_PAGE
MAX_BYTES = 500 * 1024 * 1024
ACTIONS = ("chrome-install", "policy-write", "policy-remove")
CHROME_UNDER_PROGRAM_FILES = ("Google", "Chrome", "Application", "chrome.exe")
MSI_SUCCESS = (0, 1641, 3010)  # done; done and restarting; done, restart needed
MSI_TIMEOUT = 30 * 60
STAGING_SDDL = "O:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
DECLINED = 1223  # ERROR_CANCELLED: the person said no at the UAC prompt

# Exit codes of the elevated process; the unelevated app maps them back to a repair code.
EXIT = {"installed": 0, "usage": 2, "admin_install_required": 10, "staging_unsafe": 11, "download_failed": 12,
        "bad_signature": 13, "install_failed": 14, "not_built": 15, "failed": 16}
CODES = {v: k for k, v in EXIT.items()}

CONSENT = ("Install Google Chrome for everyone on this computer.\n\n"
           "Swangz will ask Windows for administrator permission, then download Google's own Chrome installer from "
           "dl.google.com, check that Google LLC signed it, install it into Program Files and delete the download. "
           "Nothing else on this computer changes. If you say no, nothing changes.")
MESSAGES = {
    "installed": "Google Chrome is installed and checked.",
    "declined": "Nothing was changed. Chrome is still needed; you can install it from this step at any time.",
    "ask_admin": "Ask your administrator to install the company build of Swangz, which can install Chrome.",
    "mac_page": ("Install Google Chrome from Google's page. On a company Mac, your administrator installs Google's "
                 "enterprise package so Chrome is in /Applications and owned by the system; Swangz then checks it."),
    "linux": "Install Google Chrome with your system's package manager; Swangz then checks it.",
    "admin_install_required": "This copy of Swangz cannot install Chrome. Ask your administrator.",
    "staging_unsafe": "Chrome was not installed: the folder Swangz downloads into is not safe. Ask your administrator.",
    "download_failed": "Chrome was not installed: the download from Google failed. Try again later.",
    "bad_signature": "Chrome was not installed: the download was not signed by Google. Nothing was run.",
    "install_failed": "Chrome was not installed: Google's installer reported a problem. Try again or ask your administrator.",
    "failed": "Chrome was not installed. Try again or ask your administrator.",
    "usage": "Chrome was not installed. Try again or ask your administrator.",
    "not_built": "Chrome was not installed. Try again or ask your administrator.",
}


class Failed(Exception):
    def __init__(self, code, detail=""):
        super().__init__(code if not detail else "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


# ------------------------------------------------------------------ B3: the only command line

def parse_admin(argv):
    """argv after the program name -> the action. Exactly ``admin <action>``; anything else is refused."""
    if len(argv) != 2 or argv[0] != "admin" or argv[1] not in ACTIONS:
        raise Failed("usage")
    return argv[1]


# ------------------------------------------------------------------ B5: who owns a folder, and who may change it

TRUSTED_OWNERS = {"BA", "SY", "S-1-5-32-544", "S-1-5-18",
                  "S-1-5-80-956008885-3418522649-1831038044-1849834513-2271427685"}  # Administrators, SYSTEM, TI
WRITE_BITS = (0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x40000000 | 0x10000000)
RIGHTS = {"GA": 0x10000000, "GR": 0x80000000, "GW": 0x40000000, "GX": 0x20000000, "FA": 0x1F01FF, "FR": 0x120089,
          "FW": 0x120116, "FX": 0x1200A0, "RC": 0x20000, "SD": 0x10000, "WD": 0x40000, "WO": 0x80000, "CC": 0x1,
          "DC": 0x2, "LC": 0x4, "SW": 0x8, "RP": 0x10, "WP": 0x20, "DT": 0x40, "LO": 0x80, "CR": 0x100}


def _rights(text):
    if text.lower().startswith("0x"):
        return int(text, 16)
    if len(text) % 2:
        raise ValueError(text)
    mask = 0
    for i in range(0, len(text), 2):
        mask |= RIGHTS[text[i:i + 2]]  # an unknown right raises, so the folder is refused
    return mask


def sddl_safe(sddl):
    """True when the owner is Administrators, SYSTEM or TrustedInstaller and no ACE that applies to this object lets
    anyone else write, delete or change permissions. Anything unreadable is unsafe."""
    try:
        if not sddl.startswith("O:") or "D:" not in sddl:
            return False
        owner = sddl[2:sddl.index("D:")]
        if owner.endswith(")") or "G:" in owner:
            owner = owner.split("G:")[0]
        if owner.upper() not in TRUSTED_OWNERS:
            return False
        dacl = sddl[sddl.index("D:") + 2:]
        if "S:" in dacl:
            dacl = dacl[:dacl.index("S:")]
        flags, _, rest = dacl.partition("(")
        if "NO_ACCESS_CONTROL" in flags.upper() or (rest and not dacl.rstrip().endswith(")")):
            return False
        aces = ("(" + rest).split(")")
        for raw in aces:
            raw = raw.strip()
            if not raw:
                continue
            if not raw.startswith("("):
                return False
            parts = raw[1:].split(";")
            if len(parts) < 6:
                return False
            kind, ace_flags, rights, sid = parts[0].upper(), parts[1].upper(), parts[2], parts[5]
            if "IO" in [ace_flags[i:i + 2] for i in range(0, len(ace_flags), 2)]:
                continue  # inherit-only: applies to children, not to this object
            if kind in ("D", "AU", "AL", "OU", "OL"):
                continue  # deny and audit entries only take away
            if kind not in ("A", "OA", "XA", "ZA"):
                return False
            if sid.upper() in TRUSTED_OWNERS:
                continue
            if _rights(rights) & WRITE_BITS:
                return False
        return True
    except (ValueError, KeyError, IndexError, AttributeError):
        return False


# ------------------------------------------------------------------ Windows calls (ctypes), injectable

FOLDERID_PROGRAM_DATA = "{62AB5D82-FDC1-4DC3-A9DD-070D1D495D97}"
FOLDERID_PROGRAM_FILES = "{905e63b6-c1bf-494e-b29c-65b732d3d21a}"


class Windows:
    """The real Windows calls. Each method is small so tests can stand in for it."""

    def known_folder(self, guid):
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

        g = GUID()
        if ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g)) != 0:
            raise OSError("bad folder id")
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            raise OSError("known folder unavailable")
        try:
            return out.value
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)

    def system_folders(self):
        return chrome_verify.windows_folders()  # HKLM and GetSystemDirectoryW; never the environment

    def read_sddl(self, path):
        import ctypes
        from ctypes import wintypes
        sd = ctypes.c_void_p()
        info = 0x1 | 0x4  # OWNER, DACL
        err = ctypes.windll.advapi32.GetNamedSecurityInfoW(ctypes.c_wchar_p(path), 1, info, None, None, None, None,
                                                         ctypes.byref(sd))
        if err:
            raise OSError(err, "security information unreadable")
        try:
            text = ctypes.c_wchar_p()
            if not ctypes.windll.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    sd, 1, info, ctypes.byref(text), None):
                raise OSError("security descriptor unreadable")
            try:
                return text.value
            finally:
                ctypes.windll.kernel32.LocalFree(wintypes.HLOCAL(ctypes.cast(text, ctypes.c_void_p).value))
        finally:
            ctypes.windll.kernel32.LocalFree(wintypes.HLOCAL(sd.value))

    def is_link(self, path):
        st = os.lstat(path)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT

    def make_folder(self, path):
        """CreateDirectoryW with the protected admin-only DACL; FileExistsError if anything is already there."""
        import ctypes
        from ctypes import wintypes

        class SA(ctypes.Structure):
            _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                        ("bInheritHandle", wintypes.BOOL)]

        sd = ctypes.c_void_p()
        if not ctypes.windll.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                ctypes.c_wchar_p(STAGING_SDDL), 1, ctypes.byref(sd), None):
            raise OSError("security descriptor not built")
        try:
            sa = SA(ctypes.sizeof(SA), sd, False)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            if not kernel32.CreateDirectoryW(ctypes.c_wchar_p(path), ctypes.byref(sa)):
                err = ctypes.get_last_error()
                if err == 183:  # ERROR_ALREADY_EXISTS
                    raise FileExistsError(path)
                raise OSError(err, "folder not created")
        finally:
            ctypes.windll.kernel32.LocalFree(wintypes.HLOCAL(sd.value))

    def elevate(self, exe, params):
        """Start ``exe params`` through the UAC prompt and wait. -> its exit code, or DECLINED."""
        import ctypes
        from ctypes import wintypes

        class SEI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                        ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                        ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

        sei = SEI(cbSize=ctypes.sizeof(SEI), fMask=0x40 | 0x400, lpVerb="runas", lpFile=exe, lpParameters=params,
                  nShow=0)  # NOCLOSEPROCESS | FLAG_NO_UI; hidden window
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        if not shell32.ShellExecuteExW(ctypes.byref(sei)):
            err = ctypes.get_last_error()
            return DECLINED if err == DECLINED else EXIT["failed"]
        kernel32 = ctypes.windll.kernel32
        try:
            kernel32.WaitForSingleObject(sei.hProcess, 0xFFFFFFFF)
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code)):
                return EXIT["failed"]
            return code.value
        finally:
            kernel32.CloseHandle(sei.hProcess)


# ------------------------------------------------------------------ A1: download from Google only

class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise Failed("download_failed", "redirect to a non-https address refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener():
    """HTTPS with certificate checks, redirects only to https, and no proxy read from the environment."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                       urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                                       _HttpsOnlyRedirects())


def download(url, path, fetch=None, cap=MAX_BYTES, timeout=120):
    """Fetch ``url`` into the new file ``path`` (never an existing one). Stops at ``cap`` bytes; a missing or
    unmatched Content-Length is a failed download."""
    if not url.startswith("https://"):
        raise Failed("download_failed", "only https")
    try:
        response = (fetch or opener().open)(url, timeout=timeout)
    except Failed:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise Failed("download_failed", type(exc).__name__) from None
    with response:
        final = response.geturl() or ""
        if not final.startswith("https://"):
            raise Failed("download_failed", "ended on a non-https address")
        try:
            expected = int(response.headers.get("Content-Length", ""))
        except ValueError:
            raise Failed("download_failed", "no size") from None
        if expected <= 0 or expected > cap:
            raise Failed("download_failed", "size %d outside the limit" % expected)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        written = 0
        with os.fdopen(fd, "wb") as out:
            while True:
                try:
                    chunk = response.read(1024 * 1024)
                except (OSError, ValueError) as exc:
                    raise Failed("download_failed", type(exc).__name__) from None
                if not chunk:
                    break
                written += len(chunk)
                if written > cap or written > expected:
                    raise Failed("download_failed", "larger than announced")
                out.write(chunk)
        if written != expected:
            raise Failed("download_failed", "truncated: %d of %d bytes" % (written, expected))
    return written


# ------------------------------------------------------------------ B5: the elevated process checks itself

def _chain(folder, root):
    """``folder`` and each parent up to and including ``root`` (Windows paths, compared case-insensitively)."""
    folder, root = ntpath.normpath(folder), ntpath.normpath(root)
    out = [folder]
    while ntpath.normcase(folder) != ntpath.normcase(root):
        parent = ntpath.dirname(folder)
        if parent == folder:
            raise Failed("admin_install_required", "not under Program Files")
        folder = parent
        out.append(folder)
    return out


def self_check(win, executable, meipass, frozen, program_files):
    """Refuse with admin_install_required unless this is a frozen one-folder build in Program Files that only
    Administrators, SYSTEM or TrustedInstaller can change."""
    if not frozen or not meipass or not executable or not program_files:
        raise Failed("admin_install_required", "not the frozen company build")
    exe = ntpath.normpath(executable)
    folder = ntpath.dirname(exe)
    internal = ntpath.join(folder, "_internal")
    if ntpath.normcase(ntpath.normpath(meipass)) != ntpath.normcase(internal):
        raise Failed("admin_install_required", "a one-file build unpacks into the person's folder")
    if not chrome_verify._under(folder, program_files) or \
            ntpath.normcase(ntpath.normpath(folder)) == ntpath.normcase(ntpath.normpath(program_files)):
        raise Failed("admin_install_required", "not installed under Program Files")
    for path in (*_chain(folder, program_files), exe, internal):
        try:
            if not sddl_safe(win.read_sddl(path)):
                raise Failed("admin_install_required", "someone other than an administrator can change " + path)
        except OSError:
            raise Failed("admin_install_required", "permissions unreadable") from None


# ------------------------------------------------------------------ B5: staging, download, check, install

def _staging_root(win, program_data):
    root = ntpath.join(program_data, "Swangz")
    try:
        win.make_folder(root)
    except FileExistsError:
        try:
            if win.is_link(root) or not sddl_safe(win.read_sddl(root)):
                raise Failed("staging_unsafe", root)
        except OSError:
            raise Failed("staging_unsafe", "unreadable") from None
    except OSError:
        raise Failed("staging_unsafe", "not created") from None
    return root


def installed_chrome(folders, exists=os.path.isfile):
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = folders.get(name)
        if root:
            path = ntpath.join(root, *CHROME_UNDER_PROGRAM_FILES)
            if exists(path):
                return path
    return None


def _check_chrome(path, folders, run, env):
    chrome_verify.check_location(path, "win32", True, folders=folders)
    chrome_verify.check_windows(path, run=run, env=env, folders=folders)


def install_windows(win, run=subprocess.run, fetch=download, remove=None, exists=os.path.isfile,
                    digest=chrome_verify.sha256, log=None):
    """The elevated chrome-install. -> evidence dict. Raises Failed with a repair code."""
    folders = win.system_folders()
    system = folders.get("System")
    if not system or not folders.get("ProgramFiles"):
        raise Failed("failed", "system folders unreadable")
    env = {"SystemRoot": ntpath.dirname(ntpath.normpath(system))}  # the only variable PowerShell and msiexec get
    already = installed_chrome(folders, exists)
    if already:
        try:
            _check_chrome(already, folders, run, env)
            return {"result": "already", "chrome": already}
        except chrome_verify.Refused:
            pass  # a Chrome that fails the check is replaced by Google's own install below
    root = _staging_root(win, win.known_folder(FOLDERID_PROGRAM_DATA))
    staging = ntpath.join(root, secrets.token_hex(16))  # 128 bits
    try:
        win.make_folder(staging)
    except OSError:
        raise Failed("staging_unsafe", "staging folder not created") from None
    evidence = {"url": MSI_URL}
    try:
        msi = ntpath.join(staging, "chrome.msi")
        evidence["bytes"] = fetch(MSI_URL, msi)
        evidence["msi_sha256"] = digest(msi)  # evidence only; the signature decides
        try:
            chrome_verify.check_windows(msi, run=run, env=env, folders=folders)
        except chrome_verify.Refused as exc:
            raise Failed("bad_signature", str(exc)) from None
        try:
            done = run([ntpath.join(system, "msiexec.exe"), "/i", msi, "/qn", "/norestart"], shell=False, env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=MSI_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as exc:
            raise Failed("install_failed", type(exc).__name__) from None
        evidence["msiexec"] = done.returncode
        if done.returncode not in MSI_SUCCESS:
            raise Failed("install_failed", "msiexec exit %d" % done.returncode)
    finally:
        (remove or _remove_tree)(staging)
    chrome = installed_chrome(folders, exists)
    if not chrome:
        raise Failed("install_failed", "chrome.exe not found after install")
    try:
        _check_chrome(chrome, folders, run, env)
    except chrome_verify.Refused as exc:
        raise Failed("bad_signature", "installed Chrome: %s" % exc) from None
    evidence.update(result="installed", chrome=chrome)
    return evidence


def _remove_tree(path):
    """Delete the staging folder and what is in it, without following links."""
    try:
        names = os.listdir(path)
    except FileNotFoundError:
        return
    for name in names:
        full = os.path.join(path, name)
        if os.path.isdir(full) and not os.path.islink(full):
            _remove_tree(full)
        else:
            os.unlink(full)
    os.rmdir(path)


def _write_log(win, line):
    try:
        root = ntpath.join(win.known_folder(FOLDERID_PROGRAM_DATA), "Swangz")
        with open(ntpath.join(root, "chrome-install.log"), "a", encoding="utf-8") as out:
            out.write(json.dumps(line, sort_keys=True) + "\n")
    except OSError:
        pass  # the log is evidence, never a reason to fail


def admin_main(argv, win=None, frozen=None, executable=None, meipass=None, install=install_windows):
    """``Swangz.exe admin <action>``, elevated. -> exit code (EXIT)."""
    try:
        action = parse_admin(argv)
    except Failed:
        return EXIT["usage"]
    if sys.platform not in ("win32", "cygwin") and win is None:
        return EXIT["admin_install_required"]
    win = win or Windows()
    line = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action}
    try:
        self_check(win,
                   sys.executable if executable is None else executable,
                   getattr(sys, "_MEIPASS", None) if meipass is None else meipass,
                   getattr(sys, "frozen", False) if frozen is None else frozen,
                   win.known_folder(FOLDERID_PROGRAM_FILES))
        if action != "chrome-install":
            raise Failed("not_built", action)  # policy-write and policy-remove are not part of the app yet
        line.update(install(win))
        code = "installed"
    except Failed as exc:
        code, line["detail"] = exc.code, exc.detail
    except Exception as exc:  # anything unexpected fails closed
        code, line["detail"] = "failed", type(exc).__name__
    line["code"] = code
    if code != "admin_install_required":
        _write_log(win, line)
    return EXIT.get(code, EXIT["failed"])


# ------------------------------------------------------------------ B1: the person's side

def request_install(platform=None, consent=None, win=None, executable=None, meipass=None, frozen=None):
    """Chrome is missing. -> (code, message). ``consent(text)`` shows the step and returns True only if the person
    agreed; nothing is elevated otherwise."""
    platform = platform or sys.platform
    if platform == "darwin":
        return "mac_page", MESSAGES["mac_page"]
    if platform not in ("win32", "cygwin"):
        return "linux", MESSAGES["linux"]
    win = win or Windows()
    executable = sys.executable if executable is None else executable
    try:
        self_check(win, executable,
                   getattr(sys, "_MEIPASS", None) if meipass is None else meipass,
                   getattr(sys, "frozen", False) if frozen is None else frozen,
                   win.known_folder(FOLDERID_PROGRAM_FILES))
    except (Failed, OSError):
        return "ask_admin", MESSAGES["ask_admin"]
    if consent is None or not consent(CONSENT):
        return "declined", MESSAGES["declined"]
    exit_code = win.elevate(executable, "admin chrome-install")
    if exit_code == DECLINED:
        return "declined", MESSAGES["declined"]
    code = CODES.get(exit_code, "failed")
    return code, MESSAGES.get(code, MESSAGES["failed"])
