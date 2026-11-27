"""swangz — the Swangz app from a terminal.

    swangz                      open the app window
    swangz login [--server URL] [--name NAME]
    swangz status | sync | packages | apps
    swangz open TOOL            open a website tool through Swangz
    swangz run claude|codex …   run a coding agent through the company gateway, for this one run
    swangz autostart on|off     start the app when you sign in to this computer
    swangz logout               take Swangz off this device (saved browser sign-ins stay)
    swangz cleanup [--report FILE]
                                remove Swangz from this account, saved browser sign-ins included
"""

import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys
import time

from . import __version__, agents, core, keystore, repair, shell, workspace_launcher

AGENTS = {"claude": "claude-code", "codex": "codex"}


def say(text=""):
    print(text, flush=True)


def alert(text):
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Swangz", text)
        root.destroy()
    except Exception:  # no display: the terminal message stands
        pass


def offer_sign_out(text):
    """The older-build refusal as a dialog with a way out: a person who ran a test build (0.1.<run>) and then a
    lower-numbered copy is otherwise stuck, because `swangz` is not on PATH on a Mac. True = they chose Sign out."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        choice = messagebox.askyesno("Swangz", text + "\n\nSign out of Swangz on this computer now? You can sign in "
                                     "again afterwards.", icon="error")
        root.destroy()
        return bool(choice)
    except Exception:  # no display: the terminal message (with the full sign-out command) stands
        return False


def typed_command(verb):
    """The full command for `verb`, for a terminal where `swangz` is not on PATH (the Mac app bundle), quoted the way
    this system's command line reads it."""
    import shlex

    parts = [*shell.app_command(), verb]
    return subprocess.list2cmdline(parts) if sys.platform == "win32" else " ".join(shlex.quote(part) for part in parts)


def sign_out_command():
    return typed_command("logout")


def when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "never"


def main(argv=None, client=None):
    command_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="swangz", description="Swangz AI Hub on this device")
    parser.add_argument("--version", action="version", version=f"swangz {__version__}")
    parser.add_argument("--background", action="store_true", help="open the window minimised (used when starting at login)")
    parser.add_argument("--post-update", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("login")
    p.add_argument("--server")
    p.add_argument("--name")
    sub.add_parser("status")
    p = sub.add_parser("sync")
    p.add_argument("--force", action="store_true")
    sub.add_parser("packages")
    sub.add_parser("apps")
    p = sub.add_parser("open")
    p.add_argument("tool")
    p = sub.add_parser("run")
    p.add_argument("agent", choices=sorted(AGENTS))
    p.add_argument("args", nargs=argparse.REMAINDER)
    p = sub.add_parser("autostart")
    p.add_argument("state", choices=("on", "off"))
    sub.add_parser("logout")
    p = sub.add_parser("cleanup", help="remove Swangz from this account, saved browser sign-ins included")
    p.add_argument("--report", help="write every folder that could not be deleted to this file, one per line, after a "
                                    "line asking for the device to be disconnected where the Hub could not be told")
    p = sub.add_parser("key", help="credential helper for an installed coding agent (pipe only)")
    p.add_argument("--for", dest="tool", required=True, choices=("claude-code", "codex"))
    sub.add_parser("gui")
    p = sub.add_parser("update", help="check, stage or apply an authenticated app release")
    p.add_argument("action", choices=("status", "check", "apply"), nargs="?", default="status")
    args = parser.parse_args(command_argv)
    if args.cmd == "cleanup":  # before the client: a refused run changes nothing of Swangz's
        paths = client.paths if client else core.Paths()
        core.claim_data_folder(paths)  # an install removed before the app ran again (D-026, ruling on #353)
        refused = shell.cleanup_refusal(paths.data)
        if refused:
            write_report(args.report, [DISCONNECT])
            say(str(core.CleanupRefused(refused)))
            return 1
    client = client or core.Client()
    try:
        if args.cmd == "key":
            if sys.stdout.isatty():
                print("Credential helpers require a pipe; refusing terminal output.", file=sys.stderr)
                return 1
            try:
                key = client.helper_key(args.tool)
            except (core.ApiFailure, core.NotSignedIn, core.ClientTooOld, keystore.KeyStoreError,
                    agents.AgentConfigError, ValueError, OSError):
                print("The credential helper could not read this device's key. Open Swangz to retry.", file=sys.stderr)
                return 1
            sys.stdout.write(key)  # Bare token, no banner or newline; access record is a separate private file.
            sys.stdout.flush()
            return 0
        if args.post_update or args.cmd in (None, "gui", "status", "sync", "update"):
            updater = client.updater()
            if args.post_update:
                updater.post_update()
                return 0  # acknowledgement probe exits; restart normally to open the updated app
            if updater.recover():
                subprocess.Popen([str(updater.target), *command_argv], env=dict(os.environ),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return 1
        if args.cmd not in ("logout", "cleanup") and isinstance(getattr(client, "paths", None), core.Paths):
            core.check_newest_app(client.paths)  # after recover(): a rolled-back update has recorded its failed_version
        return run(args, client)
    except core.Revoked:
        say("This device was disconnected from Swangz AI Hub, so the coding agents and packages Swangz installed were "
            "taken off it.")
        say(browser_folders_stay(client))
        return 3
    except core.OlderBuild as exc:
        say(f"{exc}  To sign out, run: {sign_out_command()}")
        if args.cmd in (None, "gui") and offer_sign_out(str(exc)):  # opened from Finder: nobody reads the terminal
            told = client.logout()
            alert("Signed out: the coding agents and packages Swangz installed were taken off this computer. Open it "
                  "again to sign in."
                  + ("" if told else " (The server couldn't be reached, so ask an admin to disconnect this device too.)")
                  + "\n\n" + browser_folders_stay(client))
            return 0
        return 5
    except core.NeedsReconnect as exc:
        say(str(exc) + "  Run: swangz logout, then swangz login")
        return 4
    except core.NotSignedIn as exc:
        say(str(exc) + "  Run: swangz login")
        return 2
    except workspace_launcher.LaunchError as exc:
        say_repair(repair.for_code(exc.code))
        return 1
    except (core.ApiFailure, core.ClientTooOld, keystore.KeyStoreError, agents.AgentConfigError, ValueError, OSError) as exc:
        if args.cmd == "key":
            print("The credential helper could not complete. Open Swangz to retry.", file=sys.stderr)
        else:
            say(getattr(exc, "message", None) or str(exc))
        return 1
    except KeyboardInterrupt:
        return 130


def say_repair(fix):
    for line in repair.lines(fix):
        say(line)


def browser_folders_stay(client):
    """Signing out and revocation leave the company-browser folders on disk; say so. The folder is named by
    browser_profiles alone, reached through the launcher (inventory and import guards)."""
    return ("Not removed: browser folders that hold provider and Google sign-ins stay on this device at "
            f"{workspace_launcher.profiles_folder(client.paths.data)}. To delete them, run: {typed_command('cleanup')}")


DISCONNECT = "Have this device disconnected from the Hub: ask your Swangz administrator to do it in the console."


def write_report(report, lines):
    """The file the Windows uninstaller shows; the byte order mark is how it knows the text is UTF-8."""
    if report:
        Path(report).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8-sig")


def cleanup(client, report=None):
    """-> 0 when nothing of Swangz is left on this account, else 1."""
    try:
        out = client.cleanup()
    except core.CleanupRefused:
        write_report(report, [DISCONNECT])
        raise
    # one line per folder not deleted, after the line that says the Hub still lists this device
    write_report(report, ([] if out["told"] else [DISCONNECT]) + [str(path) for path, _ in out["left"]])
    if not out["told"]:
        say(f"The server couldn't be reached. {DISCONNECT}")
    for problem in out["problems"]:
        say(f"Not removed: {problem}")
    for path, reason in out["left"]:
        say(f"Not deleted: {path} ({reason})")
    if out["left"] or out["problems"]:
        say("Swangz was not completely removed from this account. Close any workspace window, then run cleanup again.")
        return 1
    say("Swangz was removed from this account, saved browser sign-ins included.")
    return 0


def run(args, client):
    cmd = args.cmd
    if cmd in (None, "gui"):
        from . import gui

        return gui.main(client, background=args.background)
    if cmd == "login":
        server = args.server or input(f"Your Swangz AI Hub address (press Enter for {core.DEFAULT_SERVER}): ").strip() \
            or core.DEFAULT_SERVER

        def show(code, url):
            say(f"\nTo connect this device, open\n    {url}\nand check that the code is\n    {code}\nThen press Approve. Waiting…")

        info = client.login(server, args.name, on_code=show)
        say(f"Signed in as {info['person']['name']} ({info['owner_kind']} device).")
        return sync_and_report(client)
    if cmd == "status":
        s = client.status()
        if not s["signed_in"]:
            say("Not signed in. Run: swangz login")
            return 2
        say(f"{s['person']['name']} on {s['server']}")
        say(f"This device: {s['device']['name']} ({s['device']['owner_kind']})   last synced: {when(s['last_sync'])}")
        say("Key storage: " + (s.get("key_storage") or "unknown"))
        say(s["updates"]["message"])
        say("Platform signature: " + s["updates"]["platform_signature"])
        if s.get("credential_warning"):
            say(s["credential_warning"])
        for pid, r in s["installed"].items():
            say(f"  {r.get('name', pid)} {r.get('version', '')}  {r.get('mode') or ''}".rstrip())
        if s["update_available"]:
            say("A newer version of the Swangz app is available.")
        return 0
    if cmd == "sync":
        return sync_and_report(client, force=args.force)
    if cmd == "update":
        updater = client.updater()
        if args.action == "check":
            result = updater.check()
        elif args.action == "apply":
            if not getattr(sys, "frozen", False) or Path(sys.executable).absolute() != updater.target:
                raise ValueError("Applying updates requires a portable executable installed in Swangz's app folder.")
            result = updater.install()
        else:
            result = updater.status()
        say(result["message"])
        say("Platform signature: " + result["platform_signature"])
        return 0
    if cmd == "packages":
        client.refresh()
        for r in client.packages():
            say(f"{r['name']:<24} {r['version']:<10} {r['state']:<10} {r['description']}")
        return 0
    if cmd == "apps":
        client.refresh()
        web = {a["id"] for a in client.apps()}
        from . import native_apps
        system = native_apps.os_key()
        for t in client.tools():
            kinds = "/".join(native_apps.badges(t["id"], system, t["id"] in web)) or "-"
            found = client.native.detect(t["id"])
            state = "" if found["state"] == "web" else found["state"].replace("unknown", "can't check")
            say(f"{t['id']:<20} {t['name']:<24} {kinds:<12} {state}".rstrip())
        return 0
    if cmd == "open":
        try:
            client.refresh()
            client.open_app(args.tool)
        except core.ApiFailure as exc:  # the Hub's refusal gets the same plain next steps as one made on this device
            fix = repair.explain(exc)
            if fix is None:
                raise
            say_repair(fix)
            return 1
        say("Opened in the Swangz workspace window.")
        return 0
    if cmd == "run":
        rest = args.args[1:] if args.args and args.args[0] == "--" else args.args
        return client.run_agent(AGENTS[args.agent], rest)
    if cmd == "autostart":
        shell.set_autostart(client.paths, args.state == "on")
        say("Swangz will start when you sign in." if args.state == "on" else "Swangz will no longer start by itself.")
        return 0
    if cmd == "logout":
        told = client.logout()
        say("Signed out: the coding agents and packages Swangz installed were taken off this device."
            + ("" if told else " (The server couldn't be reached, so ask an admin to disconnect this device too.)"))
        say(browser_folders_stay(client))
        return 0
    if cmd == "cleanup":
        return cleanup(client, args.report)
    return 1


def sync_and_report(client, force=False):
    out = client.sync(force=force)
    failed = 0
    for pid, outcome, detail in out["results"]:
        say(f"  {outcome:<10} {pid}  {detail}".rstrip())
        failed += outcome == "failed"
    say(f"\n{out['manifest']['recording']}")
    return 1 if failed else 0
