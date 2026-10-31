"""The device itself: starting at login, a terminal window, the web browser."""

import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

LABEL = "com.swangzavenue.swangz"


def app_command():
    """How to start this app again: the packaged program itself, or `python -m swangz_client`."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "swangz_client"]


# ---------------------------------------------------------------- start at login


def autostart_file(paths):
    home = Path(paths.home)
    if sys.platform == "darwin":
        return home / "Library" / "LaunchAgents" / (LABEL + ".plist")
    if sys.platform == "win32":
        return None  # a registry value, not a file
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "autostart" / "swangz.desktop"


def autostart_enabled(paths, winreg=None):
    if sys.platform == "win32":
        try:
            import winreg as reg
            with reg.OpenKey(reg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                reg.QueryValueEx(k, "Swangz")
            return True
        except (ImportError, OSError):
            return False
    f = autostart_file(paths)
    return bool(f and f.exists())


def set_autostart(paths, on, command=None):
    command = (command or app_command()) + ["--background"]
    if sys.platform == "win32":
        import winreg as reg
        with reg.OpenKey(reg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, reg.KEY_SET_VALUE) as k:
            if on:
                reg.SetValueEx(k, "Swangz", 0, reg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    reg.DeleteValue(k, "Swangz")
                except OSError:
                    pass
        return
    f = autostart_file(paths)
    if not on:
        if f.exists():
            f.unlink()
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        f.write_bytes(plistlib.dumps({"Label": LABEL, "ProgramArguments": command, "RunAtLoad": True, "ProcessType": "Interactive"}))
    else:
        f.write_text("[Desktop Entry]\nType=Application\nName=Swangz\nComment=Swangz AI Hub\n"
                     f"Exec={' '.join(shlex.quote(c) for c in command)}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n", encoding="utf-8")


# ---------------------------------------------------------------- a terminal, and the web browser


def terminal_command(args, cwd=None):
    """The command that opens a terminal window running `args`, for this kind of computer — or None."""
    cwd = str(cwd or Path.home())
    if sys.platform == "win32":
        return ["cmd.exe", "/c", "start", "Swangz", "/D", cwd, "cmd.exe", "/k", subprocess.list2cmdline(args)]
    line = "cd " + shlex.quote(cwd) + " && " + " ".join(shlex.quote(a) for a in args)
    if sys.platform == "darwin":
        script = line.replace("\\", "\\\\").replace('"', '\\"')
        return ["osascript", "-e", f'tell application "Terminal" to do script "{script}"', "-e", 'tell application "Terminal" to activate']
    for term, flag in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xfce4-terminal", "-e"), ("xterm", "-e")):
        if shutil.which(term):
            inner = ["bash", "-lc", line + "; exec bash"]
            return [term, flag, *inner]
    return None


def open_terminal(args, cwd=None):
    cmd = terminal_command(args, cwd)
    if not cmd:
        return False
    subprocess.Popen(cmd)
    return True


def open_url(url):
    return webbrowser.open(url)
