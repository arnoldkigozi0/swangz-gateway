"""Turns on a shared company account.

Swangz pays for one account on some tools and the whole team uses it. Nobody can tell who spent the
credits, because everyone looks like the same account to the vendor.

A turn fixes that from this side. A tool marked `signin = 'shared'` is handed out to one person at a
time (or `seats_at_once` people), for `turn_minutes`. While Grace holds the turn:

  * the portal opens the tool for her and for nobody else;
  * the browser extension lets her onto the site and blocks everyone else;
  * when the turn ends — she hands it back, it runs out, an admin takes it, or she closes Chrome —
    the extension signs that browser out of the tool, so the next person starts clean.

So any credits the vendor shows burned between 14:00 and 15:00 belong to whoever held the turn then.
That is the attribution a shared login otherwise throws away.
"""

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
    db.x("UPDATE tool_turns SET ended = expires, ended_by = 'system', reason = 'time was up'"
         " WHERE ended IS NULL AND expires <= ?", (time.time(),))


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


def take(db, tool, person):
    """Give this person a turn on the tool.

    -> (turn, None) when they have it (an existing turn is returned as-is, not extended), or
       (None, [the people holding it]) when every seat is taken.
    """
    current = holders(db, tool["id"])
    mine = [t for t in current if t["person_id"] == person["id"]]
    if mine:
        return mine[0], None
    if len(current) >= seats(tool):
        return None, current
    now = time.time()
    rid = db.x("INSERT INTO tool_turns(tool_id, person_id, started, expires) VALUES(?,?,?,?)",
               (tool["id"], person["id"], now, now + minutes(tool) * 60)).lastrowid
    return db.one("SELECT * FROM tool_turns WHERE id = ?", (rid,)), None


def end(db, tool_id, person_id, by="", reason=""):
    """Hand a turn back. Returns how many were closed."""
    return db.x("UPDATE tool_turns SET ended = ?, ended_by = ?, reason = ? WHERE tool_id = ? AND person_id = ?"
                " AND ended IS NULL", (time.time(), by, reason, tool_id, person_id)).rowcount


def end_all_for(db, person_id, by="", reason=""):
    """Used when someone is suspended, their account ends, or they sign out of everything."""
    return db.x("UPDATE tool_turns SET ended = ?, ended_by = ?, reason = ? WHERE person_id = ? AND ended IS NULL",
                (time.time(), by, reason, person_id)).rowcount


def state_for(db, tool, person):
    """What the staff app shows on a shared tool's tile."""
    if not is_shared(tool):
        return None
    current = holders(db, tool["id"])
    mine = next((t for t in current if t["person_id"] == person["id"]), None)
    others = [t for t in current if t["person_id"] != person["id"]]
    return {
        "shared": True,
        "mine": {"expires": mine["expires"], "started": mine["started"]} if mine else None,
        "others": [{"person": t["person"], "expires": t["expires"]} for t in others],
        "free": len(current) < seats(tool),
        "seats": seats(tool),
        "minutes": minutes(tool),
    }


def may_open(db, tool, person):
    """Can this person be let onto a shared tool's site right now? -> (ok, reason)."""
    if not is_shared(tool):
        return True, ""
    current = holders(db, tool["id"])
    if any(t["person_id"] == person["id"] for t in current):
        return True, ""
    if len(current) < seats(tool):
        return False, "Open it from Swangz AI to take your turn on the shared account."
    who = ", ".join(t["person"] for t in current)
    return False, f"{who} has the shared account right now. Swangz AI will tell you when it is free."
