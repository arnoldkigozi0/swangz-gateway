"""What a person can do after Open refused (#333). Every refusal ends here: nothing opens anywhere else.

Pure: a refusal goes in, plain words and a few action ids come out; no I/O. No action ever carries a tool or provider
address. The window turns the ids into buttons (`gui.py`) and the command line prints the same steps (`cli.py`).
"""
from collections import namedtuple

from . import core, workspace_launcher as wl

Repair = namedtuple("Repair", "code title message steps actions")

RETRY = "retry"    # ask the Hub again, then open the same tool
CHROME = "chrome"  # Google's own Chrome download page (workspace_launcher.INSTALL_PAGE), nothing else
WEEKLY = "weekly"  # the Hub's weekly reports page
LABELS = {RETRY: "Try again", CHROME: "Get Google Chrome", WEEKLY: "Open weekly reports"}

AGAIN = "Then press Try again."
ADMIN = "Ask your Swangz admin"

# code -> (title, steps, actions)
_DEVICE = {
    "no_browser": ("Google Chrome is needed",
                   ("Get Google Chrome from Google's own download page and install it.", AGAIN), (CHROME, RETRY)),
    "folder": ("Your workspace folder can't be used safely",
               ("Close any Swangz workspace window that is still open.", AGAIN,
                ADMIN + " for help if it happens again."), (RETRY,)),
    "launch_failed": ("Google Chrome didn't start",
                      ("Close the Swangz workspace window, if one is open.", AGAIN,
                       "Restart this computer if it still doesn't start."), (RETRY,)),
    "unsafe_address": ("This tool's address needs fixing",
                       (ADMIN + " to check this tool's web address in Swangz AI Hub.", AGAIN), (RETRY,)),
    "no_hosts": ("This tool's list of sites is missing",
                 ("Press Try again to fetch the latest list.", ADMIN + " to check the tool if it is still missing."), (RETRY,)),
    "not_active": ("Your workspace is paused",
                   ("Close any open workspace window.", ADMIN + " to turn it back on.", AGAIN), (RETRY,)),
    "retired": ("Your workspace was removed from this device",
                ("Close any open workspace window.", ADMIN + " if you still need it here."), (RETRY,)),
    "purge_pending": ("Still cleaning up an old workspace",
                      ("Close any open workspace window.", "Wait a minute, then press Try again.",
                       ADMIN + " if it still doesn't clear."), (RETRY,)),
    "generation_rollback": ("This device is ahead of Swangz AI Hub",
                            (ADMIN + " to check this device in Swangz AI Hub.", AGAIN), (RETRY,)),
    "workspace_unknown": ("Swangz can't tell if your workspace is on",
                          ("Check your internet connection.", AGAIN), (RETRY,)),
    "refused_by_hub": ("Swangz AI Hub didn't accept this device",
                       ("Press Try again.", "If it is refused again, sign out on the This device page and connect again, "
                                            "or ask your Swangz admin."), (RETRY,)),
    "revoked": ("This device was disconnected", (ADMIN + " before connecting it again.",), ()),
    "signed_out": ("You're signed out", ("Connect this device again to open your tools.",), ()),
    "no_workspace": ("This device has no workspace yet",
                     ("Update the Swangz app.", AGAIN, ADMIN + " if nothing changes."), (RETRY,)),
    "workspace_policy": ("The company browser settings aren't in force",
                         (ADMIN + " to install or repair the company Chrome settings on this computer.", AGAIN), (RETRY,)),
    "shared_account": ("This one opens from Swangz AI Hub",
                       ("Open Swangz AI Hub and press Open there. That is where turns are handed out.",), ()),
    "shared_account_company": ("This shared account doesn't open here yet",
                               (ADMIN + " if you need this tool.",), ()),
    "unavailable": ("This tool isn't in your list any more",
                    ("Press Sync now to see your current tools.", ADMIN + " if you still need it."), ()),
}

# Codes only the Hub sends (POST /api/device/open, or any device call made on the way to it).
_HUB = {
    "offline": ("Can't reach Swangz AI Hub", ("Check your internet connection.", AGAIN), (RETRY,)),
    "busy": ("Swangz AI Hub is busy", ("Wait a minute.", AGAIN), (RETRY,)),
    "hub_problem": ("Swangz AI Hub had a problem",
                    ("Wait a minute.", AGAIN, ADMIN + " if it keeps happening."), (RETRY,)),
    "weekly_report_required": ("Your weekly report is due",
                               ("Send your weekly report in Swangz AI Hub.", AGAIN), (WEEKLY, RETRY)),
    "device_unknown": ("Swangz AI Hub doesn't recognise this device",
                       ("Press Try again.", "If it is refused again, sign out on the This device page and connect again."),
                       (RETRY,)),
    "address": ("This tool isn't set up to open yet",
                (ADMIN + " to check this tool in Swangz AI Hub.", AGAIN), (RETRY,)),
    "denied": ("This tool isn't open to you right now",
               ("If you need it, ask for access in Swangz AI Hub under Requests, or ask your Swangz admin.", AGAIN), (RETRY,)),
}
_HUB_ALIASES = {"rate_limited": "busy", "invalid_response": "hub_problem", "no_address": "address",
                "host_not_allowed": "address", "inside_other_tool": "address", "unknown_tool": "unavailable",
                "workspace_suspended": "not_active", "workspace_retired": "retired"}


def _make(code, key, message):
    title, steps, actions = _DEVICE.get(key) or _HUB[key]
    return Repair(code, title, message, steps, actions)


def for_code(code):
    """A refusal this device made itself (`workspace_launcher.LaunchError`)."""
    key = code if code in _DEVICE else "launch_failed"
    return _make(code, key, wl.MESSAGES[key])


def explain(exc):
    """-> a Repair for a refused Open, or None when it isn't one (a disconnected or signed-out device, an unexpected
    error): the caller then handles it as it handles any other failure."""
    if isinstance(exc, wl.LaunchError):
        return for_code(exc.code)
    if not isinstance(exc, core.ApiFailure) or isinstance(exc, (core.Revoked, core.KeyRotated)):
        return None
    code = exc.code
    key = _HUB_ALIASES.get(code, code)
    if key not in _HUB and key not in _DEVICE:
        if exc.status == 0:
            key = "offline"
        elif exc.status == 429:
            key = "busy"
        elif exc.status >= 500 or exc.status < 400:
            key = "hub_problem"
        else:
            key = "denied"
    return _make(code, key, exc.message)


def lines(repair):
    """The same panel as text, for the command line."""
    out = [f"{repair.title}.", repair.message]
    out += [f"  {n}. {step}" for n, step in enumerate(repair.steps, 1)]
    if CHROME in repair.actions:
        out.append("  Google Chrome: " + wl.INSTALL_PAGE)
    return out
