"""Desktop and command-line AI apps on Windows and macOS: find them, install them with consent, open them, repair them.

The table below (`APPS`) is fixed and code-reviewed, keyed by the Hub's tool id. The Hub only says *which* tools a person
may use; it never sends a command, a path, a package id or an address for this module to run or open, so a compromised
Hub cannot make a device run anything. Every package id, path and address in the table was read on the vendor's own
page or the package manager's own record on the date in `verified`; anything that could not be checked is either left
out (the tool stays `web`) or sends the person to the vendor's own download page, and the entry's `note` says so.

What each tool is, per system:

- ``web``: browser only. It opens in the person's Swangz Chrome window (`core.Client.open_app`), never here.
- ``native``: the vendor's desktop app. Found only at fixed install paths (Program Files, ``%LocalAppData%\\Programs``,
  /Applications, ~/Applications) or, for a Microsoft Store app, by its package family folder. Installed on Windows with
  ``winget install --id <exact id> --exact --source <winget|msstore>`` after the person presses Install and agrees to a
  dialog naming the app, its publisher and the source; without winget, and always on macOS, the vendor's download page
  opens and the person runs the installer themselves. Swangz never downloads or runs an installer itself on macOS.
- ``cli``: the vendor's command-line tool. Installed with the vendor's documented command in a terminal window the
  person can see, after consent. Claude Code and Codex then run through `swangz run`, pointed at the company gateway.

Never elevated: Swangz itself asks for no administrator rights on any system. An installer that wants them asks
Windows itself, and the person can say no. Every process gets an argument list (never a shell string from this module), a timeout, and an environment
without Swangz or provider keys; nothing secret goes on a command line or in a log.
"""

import json
import os
import plistlib
import shutil
import subprocess
import sys
import threading
import time
from collections import namedtuple
from pathlib import Path

VERIFIED = "2026-11-27"
NATIVE, CLI, WEB = "native", "cli", "web"
STATES = ("installed", "missing", "installing", "failed", "web")  # what the Hub accepts; "unknown" is never sent
WINGET_EXPORT_TIMEOUT = 120
WINGET_EXPORT_MAX = 4 * 1024 * 1024
REPORT_MAX = 60
VERSION_MAX = 40
CACHE_SECONDS = 300  # detection is a handful of file checks; the cache only keeps redraws and check-ins cheap
WINGET_INSTALL_TIMEOUT = 30 * 60
WINGET_CHECK_TIMEOUT = 60
PLIST_MAX = 1024 * 1024
LOG = "apps-open.log"
CREATE_NO_WINDOW = 0x08000000
# winget's own exit codes (github.com/microsoft/winget-cli, doc/.../winget/returnCodes.md, read 27 Nov 2026):
WINGET_UP_TO_DATE = 0x8A15002B         # APPINSTALLER_CLI_ERROR_UPDATE_NOT_APPLICABLE: "No applicable update found"
WINGET_NOT_FOUND = 0x8A150014          # APPINSTALLER_CLI_ERROR_NO_APPLICATIONS_FOUND: "No packages found"
WINGET_ALREADY_INSTALLED = 0x8A150061  # APPINSTALLER_CLI_ERROR_PACKAGE_ALREADY_INSTALLED

# method: NATIVE / CLI / WEB. winget + source: the exact winget-pkgs id ("winget") or Store product id ("msstore").
# family: a Store/MSIX package family name, found by its %LocalAppData%\Packages folder. aumid: the Store app's
# AppUserModelID for launching (left empty unless published). paths: fixed install paths. bundle: the macOS bundle id
# checked in the app's Info.plist. download: the vendor's official page. updates: "self" / "winget" / "store" / "cli".
# cli: key into CLI_INSTALL. check: False when the winget package is only the installer's channel (Adobe Creative
# Cloud), so its presence says nothing about the app itself. sources: where each fact was read. note: the caveats.
Way = namedtuple("Way", "method winget source family aumid paths bundle download updates cli sources note check")
Way.__new__.__defaults__ = ("", "", "", "", (), "", "", "", "", (), "", True)
Entry = namedtuple("Entry", "name publisher windows macos verified")
Plan = namedtuple("Plan", "tool action kind name publisher where argv url")

WEB_ONLY = Way(WEB)


def web(note=""):
    return Way(WEB, note=note)


# ---------------------------------------------------------------------------------------------------------- the table
# Path tokens: {ProgramFiles} (from HKLM, never the environment), {LocalAppData}, {AppData}, {Home}.
# `updates`: "self" = the app updates itself; "winget" = `winget upgrade` updates it; "store" = the Microsoft Store does.

WINGET_PKGS = "https://github.com/microsoft/winget-pkgs/tree/master/manifests/"
CASK = "https://formulae.brew.sh/cask/"
STORE = "https://apps.microsoft.com/detail/"


def mac_app(app, bundle="", download="", cask="", updates="self", note="", extra=()):
    """A macOS desktop app found at /Applications or ~/Applications, its Info.plist naming `bundle` (when known)."""
    return Way(NATIVE, paths=("/Applications/" + app, "{Home}/Applications/" + app), bundle=bundle, download=download,
               updates=updates, sources=tuple(s for s in ((CASK + cask) if cask else "", download, *extra) if s), note=note)


def win_app(winget, folder, download="", paths=(), family="", source="winget", updates="", note="", extra=()):
    """A Windows desktop app installed by winget (`source` "winget": the winget-pkgs id; "msstore": the Store id)."""
    where = (WINGET_PKGS + folder) if source == "winget" else (STORE + winget)
    return Way(NATIVE, winget=winget, source=source, family=family, paths=tuple(paths), download=download,
               updates=updates, sources=tuple(s for s in (where, download, *extra) if s), note=note)


APPS = {
    # --- assistants
    "chatgpt": Entry("ChatGPT", "OpenAI",
                     win_app("OpenAI.ChatGPT", "o/OpenAI/ChatGPT", "https://chatgpt.com/download",
                             family="OpenAI.Codex_2p2nqsd0c76g0", updates="winget", extra=(STORE + "9PLM9XGG6VKS",),
                             note="The ChatGPT app now includes Codex: winget's MSIX carries the family "
                                  "OpenAI.Codex_2p2nqsd0c76g0. The old Store id 9NT1R1C2HH7J is 'ChatGPT Classic'; not used."),
                     mac_app("ChatGPT.app", "com.openai.codex", "https://chatgpt.com/download", "chatgpt",
                             note="The Mac ChatGPT app carries Codex's bundle id (cask quit id)."), VERIFIED),
    "claude": Entry("Claude", "Anthropic",
                    win_app("Anthropic.Claude", "a/Anthropic/Claude", "https://claude.com/download",
                            family="Claude_pzs8sxrjxfjjc", updates="winget",
                            note="winget offers an MSIX (family Claude_pzs8sxrjxfjjc) and a per-user exe whose folder "
                                 "the manifest does not state; the exe install is found through winget's own list."),
                    mac_app("Claude.app", "com.anthropic.claudefordesktop", "https://claude.com/download", "claude"),
                    VERIFIED),
    "gemini": Entry("Gemini", "Google",
                    win_app("Google.GeminiDesktop", "g/Google/GeminiDesktop", "https://gemini.google/desktop/"),
                    mac_app("Gemini.app", "com.google.GeminiMacOS", "https://gemini.google/desktop/", "google-gemini",
                            note="Cask google-gemini, NOT 'gemini' (a duplicate-file finder). Apple silicon, macOS 15+."),
                    VERIFIED),
    "perplexity": Entry("Perplexity", "Perplexity AI",
                        win_app("9P9XG917PWCJ", "", family="PerplexityAI.PerplexityApp_3jh4kjrg4dzr2", source="msstore",
                                updates="store", download=STORE + "9P9XG917PWCJ",
                                note="No winget-community id (the folder holds no manifests): Microsoft Store only."),
                        mac_app("Perplexity.app", "ai.perplexity.macv3", "", "perplexity",
                                note="Download page not verified (it refuses automated reads): found, never installed."),
                        VERIFIED),
    "copilot": Entry("Microsoft Copilot", "Microsoft",
                     win_app("9NHT9RB2F4HD", "", family="Microsoft.Copilot_8wekyb3d8bbwe", source="msstore",
                             updates="store", download="https://www.microsoft.com/en-us/copilot/download-copilot-app",
                             note="winget Microsoft.Copilot is an enterprise machine-wide MSI; the Store app is used."),
                     Way(NATIVE, download="https://www.microsoft.com/en-us/copilot/download-copilot-app",
                         sources=(CASK + "microsoft-copilot", "https://www.microsoft.com/en-us/copilot/download-copilot-app"),
                         note="The Mac app's name and bundle id are not published: Swangz opens the download page but "
                              "can't check whether it is installed."), VERIFIED),
    "grok": Entry("Grok", "xAI", web("No official Grok chat desktop app: xAI's winget and cask entries are other "
                                     "products (Grok Bot, Grok Build)."), web(), VERIFIED),
    "deepl": Entry("DeepL", "DeepL SE",
                   win_app("DeepL.DeepL", "d/DeepL/DeepL", "https://www.deepl.com/en/windows-app"),
                   mac_app("DeepL.app", "", "https://www.deepl.com/en/macos-app", "deepl",
                           note="Bundle id not confirmed (the cask lists three); found by its app name only."), VERIFIED),
    "grammarly": Entry("Grammarly", "Grammarly",
                       win_app("Grammarly.Grammarly", "g/Grammarly/Grammarly", "https://www.grammarly.com/desktop/windows"),
                       mac_app("Grammarly Desktop.app", "", "https://www.grammarly.com/desktop", "grammarly-desktop",
                               note="Bundle id not published; found by its app name only."), VERIFIED),
    "notion-ai": Entry("Notion", "Notion Labs",
                       win_app("Notion.Notion", "n/Notion/Notion", "https://www.notion.com/desktop",
                               family="com.notion.app.desktop.notion_87smfmv0eebam",
                               note="The family applies to winget's MSIX variant only."),
                       mac_app("Notion.app", "notion.id", "https://www.notion.com/desktop", "notion"), VERIFIED),
    "loom-ai": Entry("Loom", "Loom (Atlassian)",
                     win_app("Loom.Loom", "l/Loom/Loom", "https://www.loom.com/download"),
                     mac_app("Loom.app", "com.loom.desktop", "https://www.loom.com/download", "loom"), VERIFIED),
    "airtable-ai": Entry("Airtable", "Airtable",
                         Way(NATIVE, download="https://www.airtable.com/downloads",
                             sources=("https://www.airtable.com/downloads",),
                             note="Not in winget or the Store: download page only, and Swangz can't check for it."),
                         mac_app("Airtable.app", "com.FormaGrid.Airtable", "https://www.airtable.com/downloads", "airtable"),
                         VERIFIED),
    # --- coding
    "cursor": Entry("Cursor", "Anysphere",
                    win_app("Anysphere.Cursor", "a/Anysphere/Cursor", "https://cursor.com/download"),
                    mac_app("Cursor.app", "com.todesktop.230313mzl4w4u92", "https://cursor.com/download", "cursor"),
                    VERIFIED),
    "antigravity": Entry("Google Antigravity", "Google",
                         win_app("Google.Antigravity", "g/Google/Antigravity", "https://antigravity.google/download",
                                 note="Google now ships two apps: Antigravity (this one, winget Google.Antigravity) and "
                                      "Antigravity IDE (Google.AntigravityIDE). Change here if the catalogue means the IDE."),
                         mac_app("Antigravity.app", "com.google.antigravity", "https://antigravity.google/download",
                                 "antigravity", note="IDE alternative: cask antigravity-ide (com.google.antigravity-ide)."),
                         VERIFIED),
    "claude-code": Entry("Claude Code", "Anthropic",
                         Way(CLI, winget="Anthropic.ClaudeCode", source="winget", cli="claude-code",
                             paths=("{Home}\\.local\\bin\\claude.exe",), download="https://code.claude.com/docs/en/setup",
                             updates="winget", sources=(WINGET_PKGS + "a/Anthropic/ClaudeCode",
                                                        "https://code.claude.com/docs/en/setup"),
                             note="Anthropic documents winget; winget installs don't update themselves (Repair updates)."),
                         Way(CLI, cli="claude-code", paths=("{Home}/.local/bin/claude",),
                             download="https://code.claude.com/docs/en/setup", updates="cli",
                             sources=("https://code.claude.com/docs/en/setup", CASK + "claude-code")), VERIFIED),
    "codex": Entry("Codex CLI", "OpenAI",
                   Way(CLI, winget="OpenAI.Codex", source="winget", cli="codex",
                       paths=("{LocalAppData}\\Programs\\OpenAI\\Codex\\bin\\codex.exe",),
                       download="https://github.com/openai/codex", updates="winget",
                       sources=(WINGET_PKGS + "o/OpenAI/Codex", "https://github.com/openai/codex")),
                   Way(CLI, cli="codex", paths=("{Home}/.local/bin/codex",), download="https://github.com/openai/codex",
                       sources=("https://github.com/openai/codex", "https://chatgpt.com/codex/install.sh", CASK + "codex")),
                   VERIFIED),
    # --- design, video, voice
    "canva": Entry("Canva", "Canva",
                   win_app("Canva.Canva", "c/Canva/Canva", "https://www.canva.com/download/windows/",
                           paths=("{LocalAppData}\\Programs\\Canva\\Canva.exe",),
                           note="Path from the winget manifest's InstallationMetadata."),
                   mac_app("Canva.app", "com.canva.CanvaDesktop", "https://www.canva.com/download/mac/", "canva"),
                   VERIFIED),
    "figma-ai": Entry("Figma", "Figma, Inc.",
                      win_app("Figma.Figma", "f/Figma/Figma", "https://www.figma.com/downloads/"),
                      mac_app("Figma.app", "com.figma.Desktop", "https://www.figma.com/downloads/", "figma"), VERIFIED),
    "capcut": Entry("CapCut", "ByteDance",
                    win_app("ByteDance.CapCut", "b/ByteDance/CapCut", "https://www.capcut.com/tools/desktop-video-editor"),
                    mac_app("CapCut.app", "com.lemon.lvoverseas", "https://www.capcut.com/tools/desktop-video-editor",
                            "capcut", updates=""), VERIFIED),
    "descript": Entry("Descript", "Descript",
                      win_app("Descript.Descript", "d/Descript/Descript", "https://www.descript.com/download"),
                      mac_app("Descript.app", "com.descript.beachcube", "https://www.descript.com/download", "descript"),
                      VERIFIED),
    "davinci-resolve": Entry("DaVinci Resolve", "Blackmagic Design",
                             Way(NATIVE, download="https://www.blackmagicdesign.com/products/davinciresolve",
                                 sources=("https://www.blackmagicdesign.com/products/davinciresolve",),
                                 note="Not in winget or the Store; Blackmagic's download asks for a form. Download page "
                                      "only, and Swangz can't check for it."),
                             Way(NATIVE, download="https://www.blackmagicdesign.com/products/davinciresolve",
                                 sources=("https://www.blackmagicdesign.com/products/davinciresolve",
                                          "https://apps.apple.com/app/davinci-resolve/id571213070"),
                                 note="The direct download's app name and bundle id are not verified (only the App "
                                      "Store build's): download page only, and Swangz can't check for it."), VERIFIED),
    "topaz-video-ai": Entry("Topaz Video", "Topaz Labs",
                            Way(NATIVE, download="https://www.topazlabs.com/downloads",
                                sources=("https://www.topazlabs.com/downloads",),
                                note="winget only has the old Video Enhance AI: download page only, not checkable."),
                            Way(NATIVE, download="https://www.topazlabs.com/topaz-video",
                                sources=(CASK + "topaz-video", "https://www.topazlabs.com/topaz-video"),
                                note="Installed as a .pkg whose app name is not published: download page only."),
                            VERIFIED),
    "adobe-premiere": Entry("Adobe Premiere Pro", "Adobe",
                            Way(NATIVE, winget="Adobe.CreativeCloud", source="winget", check=False,
                                download="https://www.adobe.com/download/creative-cloud",
                                sources=(WINGET_PKGS + "a/Adobe/CreativeCloud",),
                                note="Installs Adobe Creative Cloud (for everyone on the computer, so Windows asks "
                                     "permission); then install Premiere Pro from Creative Cloud. Premiere's own path is "
                                     "not published, so Swangz can't check for it."),
                            Way(NATIVE, download="https://www.adobe.com/download/creative-cloud",
                                sources=(CASK + "adobe-creative-cloud",),
                                note="Get Creative Cloud, then Premiere Pro from it. Not checkable."), VERIFIED),
    "photoshop": Entry("Adobe Photoshop", "Adobe",
                       Way(NATIVE, winget="Adobe.CreativeCloud", source="winget", check=False,
                           download="https://www.adobe.com/download/creative-cloud",
                           sources=(WINGET_PKGS + "a/Adobe/CreativeCloud", STORE + "XPFD4T9N395QN6"),
                           note="Installs Adobe Creative Cloud, then install Photoshop from it (the Store listing "
                                "XPFD4T9N395QN6 is a stub for the same). Not checkable."),
                       Way(NATIVE, download="https://www.adobe.com/download/creative-cloud",
                           sources=(CASK + "adobe-creative-cloud",),
                           note="Get Creative Cloud, then Photoshop from it. Not checkable."), VERIFIED),
    # --- web only (checked 27 Nov 2026: no official desktop app)
    "adobe-firefly": Entry("Adobe Firefly", "Adobe", web("No standalone desktop app; Firefly is on the web and inside "
                                                          "Creative Cloud apps."), web(), VERIFIED),
    "google-flow": Entry("Google Flow", "Google", web("Web only: https://flow.google.com/"), web(), VERIFIED),
    "elevenlabs": Entry("ElevenLabs", "ElevenLabs", web("Web only: no winget, Store or cask entry."), web(), VERIFIED),
    "higgsfield-ai": Entry("Higgsfield AI", "Higgsfield", web("Web only: no winget, Store or cask entry."), web(),
                           VERIFIED),
}

# The vendor-documented command-line installs on macOS, run in a Terminal window the person can see. On Windows the
# same tools install through winget (Way.winget), also in a visible window.
CLI_INSTALL = {
    "claude-code": {"command": "claude", "where": "Anthropic's install script (claude.ai/install.sh)",
                    "macos": ("bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash")},
    "codex": {"command": "codex", "where": "OpenAI's install script (chatgpt.com/codex/install.sh)",
              "macos": ("bash", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh")},
}


# ---------------------------------------------------------------------------------------------------------- helpers

def os_key(platform=None):
    platform = platform or sys.platform
    if platform in ("win32", "cygwin"):
        return "windows"
    if platform == "darwin":
        return "macos"
    return "linux"


def entry(tool_id):
    return APPS.get(tool_id)


def way(tool_id, system):
    """-> the Way for this tool on this system. Anything not in the table, and Linux (source only), is `web`."""
    e = APPS.get(tool_id)
    if e is None or system not in ("windows", "macos"):
        return WEB_ONLY
    return getattr(e, system)


def badges(tool_id, system, has_web):
    """The labels on a tool's card: Web when it opens in Swangz Chrome, Desktop / CLI from the table."""
    out = ["Web"] if has_web else []
    w = way(tool_id, system)
    if w.method == NATIVE:
        out.append("Desktop")
    elif w.method == CLI:
        out.append("CLI")
    return out


def _clip(version):
    text = "".join(c for c in str(version or "") if c.isprintable()).strip()
    return text[:VERSION_MAX]


def _startfile(path):
    """Windows: open the detected program file itself (its path comes from the fixed table, never from the Hub)."""
    os.startfile(path)  # noqa: S606 — a fixed, detected program path


def _open_page(url):
    """The vendor's official download page from the fixed table, in the person's browser (it is not the tool)."""
    from . import shell
    return shell.open_url(url)


def _open_terminal(args):
    """A terminal window the person can see, running a vendor-documented install command from CLI_INSTALL."""
    from . import shell
    return shell.open_terminal(args)


def _windows_version(path):
    """The file version of a Windows program from its version resource (no process started). '' when unreadable."""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        ver.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(wintypes.UINT))
        ver.VerQueryValueW.restype = wintypes.BOOL
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size or size > 4 * 1024 * 1024:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return ""
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)) or length.value < 16:
            return ""
        info = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
        if info[0] != 0xFEEF04BD:  # VS_FIXEDFILEINFO's signature
            return ""
        ms, ls = info[2], info[3]
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:  # noqa: BLE001 — a version is a nicety, never a failure
        return ""


def _read_plist(path):
    with open(path, "rb") as f:
        data = f.read(PLIST_MAX + 1)
    if len(data) > PLIST_MAX:
        raise ValueError("too large")
    out = plistlib.loads(data)
    if not isinstance(out, dict):
        raise ValueError("not a dictionary")
    return out


def parse_winget_export(data):
    """`winget export` JSON -> {lower-case PackageIdentifier: Version or ''} (learn.microsoft.com, winget export:
    Sources[].Packages[].PackageIdentifier, Version with --include-versions). ValueError when it isn't that shape."""
    doc = json.loads(data.decode("utf-8-sig") if isinstance(data, bytes) else data)
    if not isinstance(doc, dict) or not isinstance(doc.get("Sources"), list):
        raise ValueError("not a winget export")
    out = {}
    for source in doc["Sources"]:
        for pkg in (source.get("Packages") if isinstance(source, dict) else None) or []:
            pid = pkg.get("PackageIdentifier") if isinstance(pkg, dict) else None
            if isinstance(pid, str) and 0 < len(pid) <= 128:
                version = pkg.get("Version")
                out[pid.lower()] = version if isinstance(version, str) else ""
    return out


def _windows_dir():
    """C:\\Windows from GetSystemDirectoryW's parent (never the environment), for explorer.exe."""
    from . import chrome_verify
    system = chrome_verify.windows_folders().get("System")
    return os.path.dirname(system) if system and os.path.isabs(system) else None


def child_env(environ=None):
    from .workspace_launcher import child_env as strip
    return strip(environ)


# ---------------------------------------------------------------------------------------------------------- the manager

class Manager:
    """Detection, install, repair, update checks and launch for the apps in APPS, on this computer.

    Every seam is a parameter so the tests run with fake runners and a fake filesystem: nothing here touches the network
    or installs anything in a test."""

    def __init__(self, data, platform=None, run=subprocess.run, popen=subprocess.Popen, exists=os.path.exists,
                 env=None, home=None, which=shutil.which, start=None, open_page=None, open_terminal=None,
                 read_plist=None, file_version=None, folders=None, clock=time.time, windows_dir=None, browser=None):
        self.data = Path(data)
        self.platform = platform or sys.platform
        self.system = os_key(self.platform)
        self.run, self.popen, self.exists, self.which, self.clock = run, popen, exists, which, clock
        self.env = dict(os.environ if env is None else env)
        self.home = str(home or Path.home())
        self.start = start or _startfile
        self.open_page = open_page or _open_page
        self.open_terminal = open_terminal or _open_terminal
        self.read_plist = read_plist or _read_plist
        self.file_version = file_version or _windows_version
        self._folders = folders
        self._windows_dir = windows_dir or _windows_dir
        self._browser = browser
        self._lock = threading.Lock()
        self._cache = {}     # tool id -> (time, detection)
        self._busy = {}      # tool id -> "installing" while an install or repair runs
        self._failed = {}    # tool id -> plain message of the last failed install or repair
        self._winget = None  # (time, {lower-case id: version}) from the last `winget export`
        self._export_lock = threading.Lock()  # one `winget export` at a time (check-in and Re-check share the file)

    # ------------------------------------------------------------ where things are

    def folders(self):
        """{token: folder} for path tokens. {ProgramFiles} comes from HKLM (chrome_verify), never the environment."""
        out = {"Home": self.home}
        if self.system == "windows":
            fixed = self._folders() if callable(self._folders) else (self._folders or None)
            if fixed is None:
                from . import chrome_verify
                fixed = chrome_verify.windows_folders()
            out["ProgramFiles"] = fixed.get("ProgramFiles")
            out["LocalAppData"] = self.env.get("LOCALAPPDATA") or self.env.get("LocalAppData")
            out["AppData"] = self.env.get("APPDATA") or self.env.get("AppData")
        return out

    def expand(self, template):
        """A table path with its tokens filled in, or None when a token is unknown or the result is not absolute."""
        folders = self.folders()
        text = template
        for token, folder in folders.items():
            marker = "{" + token + "}"
            if marker in text:
                if not folder:
                    return None
                text = text.replace(marker, folder)
        if "{" in text:
            return None
        if self.system == "windows":
            import ntpath
            text = text.replace("/", "\\")
            return text if ntpath.isabs(text) else None
        return text if text.startswith("/") else None

    def winget(self):
        """winget.exe at its documented App Execution Alias folder, else PATH (labelled as the fallback)."""
        if self.system != "windows":
            return None, ""
        local = self.folders().get("LocalAppData")
        if local:
            fixed = local.rstrip("\\/") + "\\Microsoft\\WindowsApps\\winget.exe"
            if self.exists(fixed):
                return fixed, "fixed"
        found = self.which("winget") if self.which else None
        return (found, "PATH") if found else (None, "")

    # ------------------------------------------------------------ detection

    def detect(self, tool_id, fresh=False):
        """-> {"state", "version", "path", "via"} for this tool here. `via` says how it was found: "fixed path",
        "store", "PATH (fallback)". Web tools are {"state": "web"}. Never raises; never starts the app."""
        w = way(tool_id, self.system)
        if w.method == WEB:
            return {"state": "web", "version": "", "path": "", "via": ""}
        now = self.clock()
        with self._lock:
            hit = self._cache.get(tool_id)
            if hit and not fresh and 0 <= now - hit[0] < CACHE_SECONDS:
                found = dict(hit[1])
            else:
                found = None
        if found is None:
            try:
                found = self._detect(tool_id, w)
            except Exception:  # noqa: BLE001 — an unreadable place is "not found", never a crash
                found = {"state": "missing", "version": "", "path": "", "via": ""}
            with self._lock:
                self._cache[tool_id] = (now, dict(found))
        with self._lock:
            if tool_id in self._busy:
                found["state"] = "installing"
            elif found["state"] in ("missing", "unknown") and tool_id in self._failed:
                found["state"] = "failed"
                found["message"] = self._failed[tool_id]
        return found

    def _detect(self, tool_id, w):
        none = {"state": "missing", "version": "", "path": "", "via": ""}
        for template in w.paths:
            path = self.expand(template)
            if not path or not self.exists(path):
                continue
            if self.system == "macos" and path.endswith(".app"):
                version = self._mac_version(path, w.bundle)
                if version is None:
                    continue  # something else is at that path: not this vendor's app
                return {"state": "installed", "version": version, "path": path, "via": "fixed path"}
            version = self.file_version(path) if self.system == "windows" and path.lower().endswith(".exe") else ""
            return {"state": "installed", "version": _clip(version), "path": path, "via": "fixed path"}
        if w.family and self.system == "windows":
            local = self.folders().get("LocalAppData")
            if local and self.exists(local.rstrip("\\/") + "\\Packages\\" + w.family):
                return {"state": "installed", "version": "", "path": "", "via": "store"}
        listed = None
        if self.system == "windows" and w.winget and w.check:
            listed = self.winget_listed()
            if listed is not None and w.winget.lower() in listed:
                return {"state": "installed", "version": _clip(listed[w.winget.lower()]), "path": "", "via": "winget"}
        if w.method == CLI and w.cli in CLI_INSTALL:
            name = CLI_INSTALL[w.cli]["command"]
            found = self.which(name) if self.which else None
            if found:
                return {"state": "installed", "version": "", "path": found, "via": "PATH (fallback)"}
        # "missing" only when there was a real way to look; otherwise say so rather than guess
        checkable = bool(w.paths or (w.family and self.system == "windows") or listed is not None or w.method == CLI)
        return none if checkable else dict(none, state="unknown")

    # ------------------------------------------------------------ winget's own list of what it installed

    def winget_listed(self):
        """{lower-case package id: version} from the last `winget export`, or None when there is none yet. Never runs
        winget itself: `refresh_winget` does that, off the window's thread."""
        with self._lock:
            return dict(self._winget[1]) if self._winget is not None else None

    def refresh_winget(self, max_age=CACHE_SECONDS):
        """Run `winget export` (a read: it lists installed packages that winget knows, with versions) into a private
        file, read it, delete it. At most once per `max_age`; blocking, so never on the window's thread."""
        if self.system != "windows":
            return None
        now = self.clock()
        with self._lock:
            if self._winget is not None and 0 <= now - self._winget[0] < max_age:
                return dict(self._winget[1])
        exe, _ = self.winget()
        if not exe:
            return None
        if not self._export_lock.acquire(blocking=False):  # another thread is exporting: use what there is
            return self.winget_listed()
        try:
            return self._export(exe, now)
        finally:
            self._export_lock.release()

    def _export(self, exe, now):
        out = self.data / ".winget-export.json"
        argv = [exe, "export", "-o", str(out), "--include-versions", "--accept-source-agreements",
                "--disable-interactivity"]
        listed = None
        try:
            self.run(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     timeout=WINGET_EXPORT_TIMEOUT, env=child_env(self.env), creationflags=CREATE_NO_WINDOW)
            listed = parse_winget_export(self.read_export(out))
        except (OSError, subprocess.SubprocessError, ValueError):
            listed = None
        finally:
            try:
                out.unlink()
            except OSError:
                pass
        if listed is not None:
            with self._lock:
                self._winget = (now, listed)
                self._cache.clear()
        return listed

    @staticmethod
    def read_export(path):
        with open(path, "rb") as f:
            data = f.read(WINGET_EXPORT_MAX + 1)
        if len(data) > WINGET_EXPORT_MAX:
            raise ValueError("too large")
        return data

    def _mac_version(self, app, bundle):
        """-> the app's short version when its Info.plist names the table's bundle id; None for any other app."""
        try:
            info = self.read_plist(os.path.join(app, "Contents", "Info.plist"))
        except Exception:  # noqa: BLE001
            return None
        if bundle and info.get("CFBundleIdentifier") != bundle:
            return None
        return _clip(info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or "")

    def forget(self, tool_id=None):
        with self._lock:
            if tool_id is None:
                self._cache.clear()
            else:
                self._cache.pop(tool_id, None)

    def chrome(self):
        """Google Chrome at its fixed paths (the workspace launcher's own list): {"state", "version", "path"}.
        Presence only: the publisher check (D-026 A2-A4) runs before every Open, not here."""
        try:
            if self._browser is not None:
                path = self._browser()
            else:
                from . import workspace_launcher as wl
                path = wl.find_browser(self.platform)
        except Exception:  # noqa: BLE001 — LaunchError("no_browser") and anything else: not there
            return {"state": "missing", "version": "", "path": ""}
        version = ""
        if self.system == "windows":
            version = self.file_version(path)
        elif self.system == "macos":
            app = path.split("/Contents/MacOS/")[0]
            version = self._mac_version(app, "com.google.Chrome") or ""
        return {"state": "installed", "version": _clip(version), "path": path}

    def report(self, tool_ids):
        """The heartbeat's `apps`: Chrome first, then each tool, at most REPORT_MAX entries of
        {"id", "state", "version"}. File checks are cached; on Windows `winget export` runs at most every few minutes
        (the heartbeat is already off the window's thread). A tool Swangz can't check is left out, never "missing".
        Never raises."""
        try:
            self.refresh_winget()
        except Exception:  # noqa: BLE001
            pass
        out = []
        try:
            c = self.chrome()
            out.append({"id": "chrome", "state": c["state"], "version": c["version"]})
        except Exception:  # noqa: BLE001
            out.append({"id": "chrome", "state": "missing", "version": ""})
        seen = {"chrome"}
        for tool_id in tool_ids:
            if len(out) >= REPORT_MAX:
                break
            if not isinstance(tool_id, str) or not tool_id or len(tool_id) > 64 or tool_id in seen:
                continue
            seen.add(tool_id)
            d = self.detect(tool_id)
            if d["state"] not in STATES:
                continue  # "unknown": nothing honest to say
            out.append({"id": tool_id, "state": d["state"], "version": _clip(d.get("version"))})
        return out

    # ------------------------------------------------------------ what each action would do

    def plan(self, tool_id, action="install"):
        """-> the Plan for installing ("install") or repairing/updating ("repair") this tool here, or None when there is
        nothing to install (a web tool, Linux). Pure: it runs nothing. The person sees `consent_text(plan)` first."""
        e, w = APPS.get(tool_id), way(tool_id, self.system)
        if e is None or w.method == WEB:
            return None
        if self.system == "windows" and w.winget and w.source in ("winget", "msstore"):
            exe, _ = self.winget()
            if exe:
                installed = self.detect(tool_id, fresh=True)["state"] == "installed"
                verb = "upgrade" if action == "repair" and installed and w.check else "install"
                argv = (exe, verb, "--id", w.winget, "--exact", "--source", w.source,
                        "--accept-source-agreements", "--accept-package-agreements")
                where = "the Microsoft Store" if w.source == "msstore" else "winget, Microsoft's app installer"
                # A command-line tool installs in a window the person can watch; a desktop app installs quietly.
                return Plan(tool_id, action, "terminal" if w.method == CLI else "winget", e.name, e.publisher, where,
                            argv, "")
        if w.method == CLI:
            spec = CLI_INSTALL.get(w.cli) or {}
            argv = spec.get(self.system)
            if argv:
                return Plan(tool_id, action, "terminal", e.name, e.publisher, spec.get("where", "the vendor"),
                            tuple(argv), "")
        if w.download:
            return Plan(tool_id, action, "page", e.name, e.publisher, "the vendor's download page", (), w.download)
        return None

    def consent_text(self, plan):
        doing = {"install": "Install", "repair": "Repair or update"}.get(plan.action, "Install")
        lines = [f"{doing} {plan.name} on this computer?", "", f"App: {plan.name}", f"Publisher: {plan.publisher}",
                 f"From: {plan.where}", ""]
        if plan.kind == "winget":
            lines.append("Swangz asks Windows' own installer to fetch it from that source. If the app installs for "
                         "everyone on this computer, Windows may ask for permission first; saying no changes nothing.")
        elif plan.kind == "terminal":
            lines.append("A terminal window opens and runs the install, so you can watch it. Swangz runs nothing as "
                         "administrator.")
        else:
            lines.append("Your browser opens the publisher's own download page. Download and run the installer from "
                         "there, then come back and press Re-check.")
        w = way(plan.tool, self.system)
        if not w.check and w.note:
            lines += ["", w.note]
        return "\n".join(lines)

    # ------------------------------------------------------------ doing it (after consent)

    def install(self, tool_id, consent, action="install"):
        """Plan, ask, then do. `consent(text)` must return True; anything else runs nothing. -> result dict."""
        plan = self.plan(tool_id, action)
        if plan is None:
            return {"state": "web", "message": "Nothing to install: this tool opens in Swangz Chrome."}
        if consent is None or consent(self.consent_text(plan)) is not True:
            return {"state": self.detect(tool_id)["state"], "message": "Nothing was changed."}
        return self.execute(plan)

    def execute(self, plan):
        """Carry out a Plan the person agreed to. Blocking for winget (run it off the window's thread)."""
        if not isinstance(plan, Plan) or self.plan(plan.tool, plan.action) != plan:
            return {"state": "failed", "message": "That step is out of date. Press Re-check, then try again."}
        if plan.kind == "page":
            try:
                opened = self.open_page(plan.url)
            except Exception:  # noqa: BLE001
                opened = False
            if not opened:
                return {"state": "missing", "message": "Your browser didn't open. Get it from " + plan.url}
            return {"state": "missing", "message": f"Opened {plan.name}'s download page. Install it from there, then "
                                                   "press Re-check."}
        if plan.kind == "terminal":
            try:
                opened = self.open_terminal(list(plan.argv))
            except Exception:  # noqa: BLE001
                opened = False
            self.forget(plan.tool)
            if not opened:
                return {"state": "failed", "message": "Couldn't open a terminal window. Ask your admin for help."}
            return {"state": "installing", "message": f"Installing {plan.name} in a terminal window. When it finishes, "
                                                      "press Re-check."}
        with self._lock:
            if plan.tool in self._busy:
                return {"state": "installing", "message": f"{plan.name} is already being installed."}
            self._busy[plan.tool] = "installing"
            self._failed.pop(plan.tool, None)
        try:
            code = self._winget_run(plan.argv, WINGET_INSTALL_TIMEOUT)
        finally:
            with self._lock:
                self._busy.pop(plan.tool, None)
            self.forget(plan.tool)
        if code in (0, WINGET_ALREADY_INSTALLED) or (plan.argv[1] == "upgrade" and code == WINGET_UP_TO_DATE):
            try:
                self.refresh_winget(max_age=0)
            except Exception:  # noqa: BLE001
                pass
            found = self.detect(plan.tool, fresh=True)
            if found["state"] == "installed":
                note = " It is up to date." if code == WINGET_UP_TO_DATE else ""
                return {"state": "installed", "message": f"{plan.name} is installed.{note}"}
            return {"state": found["state"], "message": f"winget finished, but Swangz can't find {plan.name} in its usual "
                                                        "place yet. Press Re-check in a minute."}
        message = (f"{plan.name} wasn't installed (winget stopped with code {code}). Press Repair to try again, or ask "
                   "your admin." if code is not None else
                   f"{plan.name} wasn't installed: the installer didn't finish in time. Press Repair to try again.")
        with self._lock:
            self._failed[plan.tool] = message
        return {"state": "failed", "message": message}

    def _winget_run(self, argv, timeout):
        """-> winget's exit code (unsigned), or None on a timeout or when it can't start. Output is not kept."""
        kw = {"creationflags": CREATE_NO_WINDOW} if self.system == "windows" else {}
        try:
            done = self.run(list(argv), shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, env=child_env(self.env), **kw)
        except (OSError, subprocess.SubprocessError):
            return None
        return done.returncode & 0xFFFFFFFF if isinstance(done.returncode, int) else None

    def check_update(self, tool_id):
        """-> plain words on whether an update is waiting. Windows + winget: a dry `winget list --upgrade-available`
        (it changes nothing); otherwise what the table says about how the app updates."""
        w = way(tool_id, self.system)
        if w.method == WEB:
            return "Opens on the web: nothing to update on this computer."
        exe, _ = self.winget()
        if self.system == "windows" and exe and w.winget and w.source in ("winget", "msstore"):
            kw = {"creationflags": CREATE_NO_WINDOW}
            argv = [exe, "list", "--id", w.winget, "--exact", "--source", w.source, "--upgrade-available",
                    "--accept-source-agreements", "--disable-interactivity"]
            try:
                done = self.run(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=WINGET_CHECK_TIMEOUT, env=child_env(self.env),
                                text=True, **kw)
            except (OSError, subprocess.SubprocessError):
                return self.update_words(w)
            code = done.returncode & 0xFFFFFFFF if isinstance(done.returncode, int) else None
            if code == 0 and w.winget.lower() in (done.stdout or "").lower():
                return "An update is waiting. Press Repair to install it."
            if code in (0, WINGET_NOT_FOUND):
                return "No update waiting."
        return self.update_words(w)

    @staticmethod
    def update_words(w):
        return {"self": "Updates itself.", "store": "The Microsoft Store keeps it up to date.",
                "winget": "Press Repair to update it.", "cli": "Updates itself when you run it."}.get(
                    w.updates, "Updates through its own installer.")

    # ------------------------------------------------------------ opening

    def launch(self, tool_id):
        """Open the installed desktop app. -> plain words. Raises LookupError with plain words when it can't."""
        e, w = APPS.get(tool_id), way(tool_id, self.system)
        if e is None or w.method != NATIVE:
            raise LookupError("This one doesn't have a desktop app on this computer.")
        found = self.detect(tool_id, fresh=True)
        if found["state"] != "installed":
            raise LookupError(f"{e.name} isn't installed on this computer. Press Install.")
        start_menu = LookupError(f"Open {e.name} from the Start menu.")  # found, but no published way to start it
        try:
            if self.system == "windows" and found["via"] == "store":
                folder = self._windows_dir() if w.aumid else None
                if not folder:
                    raise start_menu
                self.popen([folder + "\\explorer.exe", "shell:AppsFolder\\" + w.aumid], shell=False, close_fds=True,
                           env=child_env(self.env), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            elif self.system == "windows":
                if found["via"] != "fixed path" or not found.get("path"):
                    raise start_menu
                self.start(found["path"])
            elif self.system == "macos" and found["via"] == "fixed path" and found.get("path"):
                self.popen(["/usr/bin/open", "-a", found["path"]], shell=False, close_fds=True,
                           env=child_env(self.env), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            elif self.system == "macos":
                raise LookupError(f"Open {e.name} from your Applications folder.")
            else:
                raise LookupError("Desktop apps open from Swangz on Windows and macOS only.")
        except OSError:
            raise LookupError(f"{e.name} didn't start. Press Repair.") from None
        self.log(tool_id)
        return f"Opened {e.name}."

    def log(self, tool_id):
        """Access-level only and bounded: `<time> desktop <tool id>`, the same shape as workspace-open.log."""
        from .core import write_private
        path = self.data / LOG
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[-99:] if path.exists() else []
            write_private(path, "\n".join(lines + [f"{int(self.clock())} desktop {tool_id}"]) + "\n")
        except OSError:
            pass


def recent_opens(data, limit=20):
    """-> [(time, tool id, "web"|"desktop")] newest first, from this device's two local open logs (no network)."""
    out = []
    for name, kind in (("workspace-open.log", "web"), (LOG, "desktop")):
        try:
            lines = (Path(data) / name).read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            continue
        for line in lines[-200:]:
            parts = line.split()
            if len(parts) == 3 and parts[0].isdigit() and parts[1] in ("desktop", "open"):
                out.append((int(parts[0]), parts[2], kind))
    out.sort(key=lambda r: r[0], reverse=True)
    return out[:limit]
