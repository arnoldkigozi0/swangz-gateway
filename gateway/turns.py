"""Shared company accounts: turns are RETIRED (owner directive, 27 Nov 2026).

Until 27 Nov 2026 a tool marked `signin = 'shared'` was handed out one person at a time for `turn_minutes`, and
the browser extension signed people out when a turn ended. The owner removed that from the product: every
authorised employee works at the same time, in their own Swangz Chrome profile, with their own seat or account.
Nobody waits, is timed out or is signed out by Swangz.

What stays:
  * `signin = 'shared'` still marks a tool set up as ONE company login. That is an *account limitation*, stated
    plainly (`account_note`) to the person and the admin, never enforced with timers. Most providers allow one
    person per login; the fix is a seat per person or single sign-on, which only the admin can buy or set up.
  * The `tool_turns` table and its history: past turns stay readable (who held which account, when). No new turn
    is ever taken; migration v31 closed every turn that was still open.
  * `end` / `end_all_for` / `expire` close leftover rows (suspension, account end), so nothing is left dangling.

Removing turns must not be used to get around a provider's licence: Swangz never shares a password, a session or
a cookie between people (CLAUDE.md, D-026 G). It only says where an account can't serve several people at once.
"""

import json
import time

from . import workspace

DEFAULT_MINUTES = 120
MAX_MINUTES = 12 * 60


def is_shared(tool):
    return (tool.get("signin") or "") == "shared"


def seats(tool):
    """How many people may hold it at once. In a workspace each needs a browser of their own."""
    n = max(1, int(tool.get("seats_at_once") or 1))
    pool = workspace.browsers(tool)
    return min(n, len(pool)) if pool else n


def minutes(tool):
    return max(5, min(int(tool.get("turn_minutes") or DEFAULT_MINUTES), MAX_MINUTES))


def expire(db):
    """Close turns whose time is up. Cheap, so every read can call it first."""
    now = time.time()
    db.x("UPDATE tool_turns SET ended = expires, ended_by = 'system', reason = 'time was up'"
         " WHERE ended IS NULL AND expires <= ?", (now,))
    release_ended_accounts(db, now)


def release_ended_accounts(db, now=None):
    """A holder whose account end date (`access_until`) has passed no longer holds anything. Every read and every
    claim goes through expire(), so this is the one place that releases them, the same way suspension does:
    turns.end_all_for, one audit row with the count. -> how many turns were ended."""
    now = time.time() if now is None else now
    total = 0
    for p in db.q("SELECT DISTINCT p.id, p.name FROM tool_turns t JOIN people p ON p.id = t.person_id"
                  " WHERE t.ended IS NULL AND p.access_until IS NOT NULL AND p.access_until > 0 AND p.access_until <= ?", (now,)):
        n = end_all_for(db, p["id"], "system", "their access ended")
        if n:  # only the caller that actually ended them records it
            total += n
            db.x("INSERT INTO audit(ts, actor, action, target, detail, ip, reason, before_json, after_json, outcome, correlation, area)"
                 " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                 (now, "system", "ended a person's turns (their access ended)", p["name"], f"{n} turn(s) ended", "", "their access ended",
                  json.dumps({"turns_open": n}), json.dumps({"turns_ended": n}), "ok", f"person:{p['id']}", ""))
    return total


def holders(db, tool_id):
    """The turns running right now on this tool, oldest first."""
    expire(db)
    return db.q(
        "SELECT t.*, p.name AS person FROM tool_turns t JOIN people p ON p.id = t.person_id"
        " WHERE t.tool_id = ? AND t.ended IS NULL ORDER BY t.started", (tool_id,))


def held_by(db, person_id):
    """{tool id: turn} for the turns this person is holding now."""
    expire(db)
    return {r["tool_id"]: r for r in db.q(
        "SELECT * FROM tool_turns WHERE person_id = ? AND ended IS NULL", (person_id,))}


def end(db, tool_id, person_id, by="", reason=""):
    """Hand a turn back. Returns how many were closed."""
    return db.x("UPDATE tool_turns SET ended = ?, ended_by = ?, reason = ? WHERE tool_id = ? AND person_id = ?"
                " AND ended IS NULL", (time.time(), by, reason, tool_id, person_id)).rowcount


def end_all_for(db, person_id, by="", reason=""):
    """Used when someone is suspended, their account ends, or they sign out of everything."""
    return db.x("UPDATE tool_turns SET ended = ?, ended_by = ?, reason = ? WHERE person_id = ? AND ended IS NULL",
                (time.time(), by, reason, person_id)).rowcount


def account_note(tool):
    """Plain words for a tool set up as one company login, or None. Shown to the person and the admin; never a gate."""
    if not is_shared(tool):
        return None
    return (f"{tool.get('name') or 'This tool'} is set up as one company login. The provider may not let several people "
            "use one login at the same time. If it asks you to sign in or says the account is busy, ask your admin for "
            "a seat of your own.")


def admin_note(tool, assigned=None):
    """The same limitation in an admin's words, with what to do about it."""
    if not is_shared(tool):
        return None
    who = f"{assigned} people are assigned it. " if assigned and assigned > 1 else ""
    return (f"{tool.get('name') or 'This tool'} is one company login. {who}Most providers' terms allow one person per "
            "login, so several people can't rely on it at once. Give each person a seat of their own on the company "
            "plan, or set up single sign-on. Swangz does not share passwords or sessions, and no longer hands out turns.")
