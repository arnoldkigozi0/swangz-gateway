"""Who may use which tool, and why.

A tool is **enabled** for a person only when both are true:
  1. the company subscription for it is active (paid), and
  2. the person is assigned it — directly, or through their department.

Anything else resolves to a reason the staff app can show: locked (no company subscription),
not assigned (paid but not granted to them), past due, or suspended. API and dev tools need no
company subscription of their own — they run on the company API key — so they are gated on
assignment alone (and dev tools, like Claude Code, only ever by direct assignment).
"""

import json


def _plans(tool):
    try:
        return json.loads(tool["plans"]) if tool.get("plans") else []
    except (ValueError, TypeError):
        return []


def person_grants(db, person):
    """The set of tool ids this person is assigned, by their own grant or their department's."""
    rows = db.q(
        "SELECT DISTINCT tool_id FROM entitlements WHERE person_id = ? OR (department != '' AND department = ?)",
        (person["id"], person.get("department") or "\0"))
    return {r["tool_id"] for r in rows}


def subscriptions(db):
    return {s["tool_id"]: s for s in db.q("SELECT * FROM subscriptions")}


def status(tool, assigned, sub, person):
    """-> (state, reason) for one tool and one person.

    state is one of: enabled, locked, not_assigned, past_due, suspended.
    """
    if person and person.get("status") != "active":
        return "suspended", "Your access is paused."
    kind = tool["kind"]
    sub_state = (sub or {}).get("state", "none")
    needs_sub = kind == "site"  # api/dev tools run on the company API key, no per-tool subscription

    if kind == "dev" and not assigned:
        return "not_assigned", "An admin assigns this tool."
    if needs_sub and sub_state in ("none", "cancelled"):
        return "locked", "The company isn't subscribed to this yet."
    if needs_sub and sub_state == "past_due":
        return "past_due", "The company subscription needs renewing."
    if not assigned:
        return "not_assigned", "Available — ask an admin to turn it on for you."
    return "enabled", "Ready to use."


def for_person(db, person, include_disabled=True):
    """Every catalog tool with this person's state on it. The staff tool grid is built from this."""
    grants = person_grants(db, person)
    subs = subscriptions(db)
    out = []
    for tool in db.q("SELECT * FROM tools WHERE archived = 0 ORDER BY category, name"):
        assigned = tool["id"] in grants
        state, reason = status(tool, assigned, subs.get(tool["id"]), person)
        if not include_disabled and state != "enabled":
            continue
        out.append({
            "id": tool["id"], "name": tool["name"], "category": tool["category"], "kind": tool["kind"],
            "url": tool["url"], "pricing_url": tool["pricing_url"], "entry_usd": tool["entry_usd"],
            "state": state, "reason": reason, "assigned": assigned,
        })
    return out


def enabled_tool_ids(db, person):
    return {t["id"] for t in for_person(db, person) if t["state"] == "enabled"}


def is_enabled(db, person, tool):
    """Fast single-tool check used by the proxy and the access gate."""
    if tool is None:
        return False, "unknown", "Unknown tool."
    assigned = tool["id"] in person_grants(db, person)
    sub = db.one("SELECT * FROM subscriptions WHERE tool_id = ?", (tool["id"],))
    state, reason = status(tool, assigned, sub, person)
    return state == "enabled", state, reason
