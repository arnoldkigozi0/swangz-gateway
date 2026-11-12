"""The Swangz workspace window (W3, docs/W3-THREAT-NOTE.md).

A provider tool opens in a real Chrome (or .deb Chromium) window that this app starts on the person's own
workspace data folder, never in the person's default browser. The address comes from the Hub
(`POST /api/device/open`, device key), is re-checked here against the hosts in the authenticated contract-2
manifest, and is handed to the browser as the last item of a fixed argument list. Nothing under the workspace
folder is read except its marker; no key, token or address reaches the command line, the environment or the log.
"""
import ipaddress
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import browser_profiles as bp

MAX_URL = 2048
HOST = re.compile(r"(?=.{1,253}\Z)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+\Z")
LINUX_BROWSERS = ("/opt/google/chrome/chrome", "/usr/lib/chromium/chromium", "/usr/lib/chromium-browser/chromium-browser")
MAC_BROWSERS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",)
WINDOWS_ROOTS = ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")
WINDOWS_TAIL = ("Google", "Chrome", "Application", "chrome.exe")
INSTALL_PAGE = "https://www.google.com/chrome/"
FIXED_SWITCHES = ("--no-first-run", "--no-default-browser-check")
FORBIDDEN_SWITCHES = ("--remote-debugging-port", "--remote-debugging-pipe", "--load-extension", "--disable-web-security",
                      "--proxy-server", "--proxy-pac-url", "--enable-automation", "--disable-extensions", "--incognito",
                      "--user-agent", "--profile-directory")
# Everything agents.py or the app may set for a coding agent, plus every proxy variable: none reach the browser.
STRIP_PREFIXES = ("SWANGZ_", "ANTHROPIC_", "OPENAI_", "CLAUDE_", "CODEX_")
STRIP_NAMES = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "FTP_PROXY", "SOCKS_PROXY", "SOCKS5_PROXY"}
LOG = "workspace-open.log"

MESSAGES = {
    "no_browser": "Swangz opens AI tools in Google Chrome, which isn't installed on this computer. Install Chrome, then press Open again.",
    "unsafe_address": "This tool's address isn't allowed. Ask your admin.",
    "not_active": "This device's workspace is paused. Ask your admin.",
    "folder": "Your Swangz workspace folder can't be used safely, so nothing was opened. Ask your admin for help.",
    "launch_failed": "The Swangz workspace window didn't start. Try again.",
    "no_hosts": "Update the Swangz app's list of tools, then press Open again.",
}


class LaunchError(Exception):
    """A refusal with a plain message. `install` says the one button is the browser install page."""

    def __init__(self, code, detail=None):
        super().__init__(MESSAGES.get(code, MESSAGES["launch_failed"]))
        self.code, self.detail, self.install = code, detail, code == "no_browser"


# ------------------------------------------------------------------ S2: the address

def clean_hosts(hosts):
    out = []
    for raw in hosts if isinstance(hosts, list) else []:
        host = raw.strip().lower() if isinstance(raw, str) else ""
        if host.startswith("www."):
            host = host[4:]
        if HOST.fullmatch(host) and host not in out:
            out.append(host)
    return out


def check_url(url, hosts):
    """-> the address, unchanged, or LaunchError("unsafe_address"). https only, no userinfo, no port games, no
    whitespace or control characters, at most 2048 characters, and the host is one of the tool's hosts or under one."""
    allowed = clean_hosts(hosts)
    if not allowed:
        raise LaunchError("no_hosts")
    if not isinstance(url, str) or not url or len(url) > MAX_URL or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        raise LaunchError("unsafe_address")
    try:
        u = urlsplit(url)
        host, port = u.hostname, u.port
    except ValueError:
        raise LaunchError("unsafe_address") from None
    if u.scheme != "https" or not url.startswith("https://") or u.username is not None or u.password is not None or "@" in u.netloc:
        raise LaunchError("unsafe_address")
    if not host or port not in (None, 443) or "\\" in url:
        raise LaunchError("unsafe_address")
    try:
        ipaddress.ip_address(host)
        raise LaunchError("unsafe_address")
    except ValueError:
        pass
    if not HOST.fullmatch(host) or not any(host == h or host.endswith("." + h) for h in allowed):
        raise LaunchError("unsafe_address")
    return url


def owner(server, person_id, device_id):
    """The folder's owner from the enrolled device and the authenticated contract-2 block, or LaunchError("folder")."""
    try:
        return bp.Owner(server, person_id, device_id)
    except bp.ProfileError:
        raise LaunchError("folder") from None


# ------------------------------------------------------------------ S3: which browser

def _windows_candidates(env):
    out = []
    for name in WINDOWS_ROOTS:
        root = env.get(name)
        if root and os.path.isabs(root):
            out.append(os.path.join(root, *WINDOWS_TAIL))
    return out


def candidates(platform=None, env=None):
    platform = platform or sys.platform
    if platform.startswith("linux"):
        return list(LINUX_BROWSERS)
    if platform == "darwin":
        return list(MAC_BROWSERS)
    if platform in ("win32", "cygwin"):
        return _windows_candidates(os.environ if env is None else env)
    return []


def _usable_linux(path):
    real = os.path.realpath(path)
    if real.startswith(("/snap/", "/var/lib/snapd/")):
        return False
    info = os.stat(real)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not info.st_mode & 0o111:
        return False
    with open(real, "rb") as f:  # the binary itself, never anything under a workspace folder
        return f.read(4) == b"\x7fELF"


def find_browser(platform=None, env=None, exists=os.path.isfile, usable_linux=_usable_linux):
    """-> the absolute path of Chrome or .deb Chromium from fixed locations, never PATH, never the default browser.
    LaunchError("no_browser") when none qualifies."""
    platform = platform or sys.platform
    for path in candidates(platform, env):
        try:
            if not exists(path):
                continue
            if platform.startswith("linux") and not usable_linux(path):
                continue
        except OSError:
            continue
        return path
    raise LaunchError("no_browser")


# ------------------------------------------------------------------ I1: the process

def build_argv(binary, folder, url):
    argv = [binary, "--user-data-dir=" + str(folder), *FIXED_SWITCHES, url]
    for item in argv[1:-1]:
        if any(item == s or item.startswith(s + "=") for s in FORBIDDEN_SWITCHES):
            raise LaunchError("launch_failed")
    if url.startswith("-"):
        raise LaunchError("unsafe_address")
    return argv


def child_env(environ=None):
    environ = dict(os.environ if environ is None else environ)
    return {k: v for k, v in environ.items()
            if not k.upper().startswith(STRIP_PREFIXES) and k.upper() not in STRIP_NAMES
            and not k.upper().endswith(("_API_KEY", "_AUTH_TOKEN", "_BASE_URL"))}


# ------------------------------------------------------------------ T1: the folder, just before launch

def verify_folder(folder, owner, acl=None):
    """Re-check the prepared folder right before the browser opens it. Refuses (never purges) on any doubt."""
    folder = Path(folder)
    profiles_root = folder.parent
    try:
        bp._check(profiles_root)
        bp._check(folder)
        marker = bp.Profiles(profiles_root.parent)._marker(folder)
    except (bp.ProfileError, OSError):
        raise LaunchError("folder") from None
    fields = owner.fields
    if any(marker.get(k) != v or type(marker.get(k)) is not type(v) for k, v in fields.items()):
        raise LaunchError("folder")
    if bp._WINDOWS:
        check = acl or _windows_acl_owner_only
        try:
            ok = check(str(folder))
        except Exception:
            ok = False
        if ok is not True:
            raise LaunchError("folder")
    return folder


def _windows_acl_owner_only(path):
    from . import winacl
    return winacl.owner_only(path)


# ------------------------------------------------------------------ the launcher

class Launcher:
    """Starts and remembers only the browser this app started (D1). One per app process."""

    def __init__(self, data, popen=subprocess.Popen, finder=find_browser, acl=None, clock=time.time):
        self.data = Path(data)
        self.popen, self.finder, self.acl, self.clock = popen, finder, acl, clock
        self.process = None

    def running(self):
        return self.process is not None and self.process.poll() is None

    def pid(self):
        return self.process.pid if self.running() else None

    def open(self, tool_id, url, hosts, owner):
        """Check the address, prepare and verify the folder, start (or hand the address to) the browser."""
        if not isinstance(tool_id, str) or not bp.ID.fullmatch(tool_id):
            raise LaunchError("unsafe_address")
        url = check_url(url, hosts)
        binary = self.finder()
        try:
            folder = bp.Profiles(self.data).prepare(owner)
        except (bp.ProfileError, OSError):
            raise LaunchError("folder") from None
        if bp._WINDOWS:
            try:
                from . import winacl
                winacl.restrict(str(folder))
            except Exception:
                raise LaunchError("folder") from None
        verify_folder(folder, owner, self.acl)
        argv = build_argv(binary, folder, url)
        try:
            proc = self.popen(argv, shell=False, close_fds=True, env=child_env(), stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            raise LaunchError("launch_failed") from None
        # A second Open while ours runs: Chrome forwards the address to the running window and this process exits;
        # we keep the PID of the window we started. We never signal a process we didn't start.
        if not self.running():
            self.process = proc
        self._log(tool_id)
        return {"tool": tool_id, "pid": self.pid()}

    def close(self):
        """Close the window this app started (W4 calls this on suspend). Returns whether one was running."""
        if not self.running():
            self.process = None
            return False
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.process = None
        return True

    def _log(self, tool_id):
        """Access-level only and bounded: `<time> open <tool_id>`, never the address."""
        from .core import write_private
        path = self.data / LOG
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-99:] if path.exists() else []
            write_private(path, "\n".join(lines + [f"{int(self.clock())} open {tool_id}"]) + "\n")
        except OSError:
            pass
