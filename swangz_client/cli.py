"""swangz — the Swangz app from a terminal.

    swangz                      open the app window
    swangz login [--server URL] [--name NAME]
    swangz status | sync | packages | apps
    swangz open TOOL            open a website tool through Swangz
    swangz run claude|codex …   run a coding agent through the company gateway, for this one run
    swangz autostart on|off     start the app when you sign in to this computer
    swangz logout               take Swangz off this device
"""

import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys
import time

from . import __version__, agents, core, keystore, shell, workspace_launcher

AGENTS = {"claude": "claude-code", "codex": "codex"}


def say(text=""):
    print(text, flush=True)


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
    sub.add_parser("cleanup")
    p = sub.add_parser("key", help="credential helper for an installed coding agent (pipe only)")
    p.add_argument("--for", dest="tool", required=True, choices=("claude-code", "codex"))
    sub.add_parser("gui")
    p = sub.add_parser("update", help="check, stage or apply an authenticated app release")
    p.add_argument("action", choices=("status", "check", "apply"), nargs="?", default="status")
    args = parser.parse_args(command_argv)
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
        return run(args, client)
    except core.Revoked:
        say("This device was disconnected from Swangz AI Hub, so Swangz has been removed from it.")
        return 3
    except core.NeedsReconnect as exc:
        say(str(exc) + "  Run: swangz logout, then swangz login")
        return 4
    except core.NotSignedIn as exc:
        say(str(exc) + "  Run: swangz login")
        return 2
    except workspace_launcher.LaunchError as exc:
        say(str(exc) + ("  " + workspace_launcher.INSTALL_PAGE if exc.install else ""))
        return 1
    except (core.ApiFailure, core.ClientTooOld, keystore.KeyStoreError, agents.AgentConfigError, ValueError, OSError) as exc:
        if args.cmd == "key":
            print("The credential helper could not complete. Open Swangz to retry.", file=sys.stderr)
        else:
            say(getattr(exc, "message", None) or str(exc))
        return 1
    except KeyboardInterrupt:
        return 130


def run(args, client):
    cmd = args.cmd
    if cmd in (None, "gui"):
        from . import gui

        return gui.main(client, background=args.background)
    if cmd == "login":
        server = args.server or input("Your Swangz AI Hub address (for example https://ai.swangzavenue.com): ")

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
        for a in client.apps():
            say(f"{a['id']:<20} {a['name']:<24}{'  (company browser)' if a['company_browser'] else ''}")
        return 0
    if cmd == "open":
        client.refresh()
        how = client.open_app(args.tool)
        say("Opened in the Swangz workspace window." if how == "workspace" else "Opening " + how)
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
        say("Swangz has been removed from this device." + ("" if told else " (The server couldn't be reached, so ask an admin to disconnect this device too.)"))
        return 0
    if cmd == "cleanup":
        client.remove_everything()
        say("Local Swangz data removed. Disconnect this device in the Hub if it is still enrolled.")
        return 0
    return 1


def sync_and_report(client, force=False):
    out = client.sync(force=force)
    failed = 0
    for pid, outcome, detail in out["results"]:
        say(f"  {outcome:<10} {pid}  {detail}".rstrip())
        failed += outcome == "failed"
    say(f"\n{out['manifest']['recording']}")
    return 1 if failed else 0
