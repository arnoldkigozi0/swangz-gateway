"""The Control Room's Workstations page: the owner's list on one screen (directive, 27 Nov 2026).

Swangz AI Hub is one installed AI workstation app per employee plus this Control Room. It is not a booking or
timed-turn system: everyone authorised works at the same time with their own seat or account. Where a tool is one
company login (`tools.signin = 'shared'`), nothing is timed; the page names the account limitation instead.

One read, `GET /admin/api/workstations`, aggregating tables that already exist:

1. employees and departments (`people`);
2. devices running the Swangz app (`devices` + their keys): online or not, app version, Chrome and the AI apps the
   app reported (`apps_json`, schema v31 — read with `SELECT *` and `.get()`, so a database without the column yet
   simply reports nothing), whose computer it is, and the workspace state;
3. assigned apps, who has what (`entitlements`, direct and through a department);
4. accounts and subscriptions: seats against single company logins (`subscriptions`, `tools.signin`);
5. activity observed in Swangz (`launches`, `site_usage`, `requests` counts), kept apart from provider-reported
   usage and billing, which no provider sends yet;
6. weekly staff reports for the last closed week (`hub_reports`).

Metadata only: no prompt or reply text, no passwords, keys, tokens or cookies, no subscription notes, no
addresses. Any console user may read it (everyone in the console can see everything); changes stay on the
existing routes (suspend: `POST /devices/<id>/workspace`, revoke: `POST /keys/<id>/revoke`).
"""

import json
import time

from . import managed, reporting
from .admin import route as admin_route

ONLINE_SECONDS = 20 * 60          # a device seen within 20 minutes is online
WEEK = 7 * 86400
APP_STATES = ("installed", "missing", "installing", "failed", "web")
SUBMITTED = ("submitted", "resubmitted", "reviewed", "confirmed")
OUTSTANDING = ("draft", "returned")
TURNS_RETIRED = "2026-11-27"

SIGNIN_LABEL = {"sso": "Company sign-in (SSO)", "seat": "A seat each", "shared": "One company login",
                "own": "Their own account", "api": "Company key"}
LIMITATION = ("One login the company pays for. Most providers allow one person per login, so when several people use "
              "it, it can be busy, sign people out or break the provider's terms.")
RECOMMENDATION = "Give each person a seat of their own, or set up company sign-in (SSO)."
PROVIDER_REPORTED = ("No provider reports usage or billing to Swangz yet, so there is nothing to show here. The numbers "
                     "above are only what Swangz itself saw.")


def _apps(raw, names):
    """The app's own list of what is on the computer. Anything unreadable is left out, never guessed."""
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    out = []
    for item in items[:100] if isinstance(items, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            continue
        app_id = item["id"].strip()[:64]
        state = item.get("state") if item.get("state") in APP_STATES else "unknown"
        out.append({"id": app_id, "name": "Chrome" if app_id == "chrome" else names.get(app_id, app_id),
                    "state": state, "version": str(item.get("version") or "")[:40]})
    return out


def _employees(people, connected_people):
    active = [p for p in people if p["status"] == "active"]
    departments = {}
    for p in active:
        if p["department"]:
            departments[p["department"]] = departments.get(p["department"], 0) + 1
    with_device = sum(1 for p in active if p["id"] in connected_people)
    return {"total": len(people), "active": len(active), "suspended": len(people) - len(active),
            "departments": [{"name": n, "people": c} for n, c in sorted(departments.items(), key=lambda x: (-x[1], x[0].lower()))],
            "no_department": sum(1 for p in active if not p["department"]),
            "with_device": with_device, "without_device": len(active) - with_device}


def _devices(gw, people_by_id, names, now):
    db = gw.db
    active_key = {r["device_id"]: r["kid"] for r in db.q(
        "SELECT device_id, MIN(id) AS kid FROM keys WHERE revoked IS NULL AND device_id IS NOT NULL GROUP BY device_id")}
    out = []
    for d in db.q("SELECT * FROM devices"):
        person = people_by_id.get(d["person_id"]) or {}
        device_id = d.get("device_id") or d["key_id"]
        key_id = active_key.get(device_id)
        kind = managed.kind_report(d)
        apps = _apps(d.get("apps_json"), names)
        chrome = next((a for a in apps if a["id"] == "chrome"), None)
        try:
            workspace = managed.effective_state(gw, person, d) if person else "suspended"
        except Exception:  # an unreadable person row reads as closed, as the app is told
            workspace = "suspended"
        last = d.get("last_seen") or 0
        out.append({
            "device_id": device_id, "name": d["name"], "os": d.get("os") or "", "arch": d.get("arch") or "",
            "app_version": d.get("app_version") or "", "person_id": d["person_id"], "person": person.get("name") or "",
            "department": person.get("department") or "", "enrolled": d.get("enrolled"), "last_seen": last or None,
            "online": bool(key_id) and bool(last) and now - last <= ONLINE_SECONDS,
            "connected": bool(key_id), "key_id": key_id,
            "owner_kind": kind["effective_kind"], "owner_confirmed": kind["owner_confirmed"],
            "workspace": workspace, "apps": [a for a in apps if a["id"] != "chrome"],
            "chrome": chrome["state"] if chrome else None, "chrome_version": chrome["version"] if chrome else "",
            "apps_reported": d.get("apps_reported") or None,
        })
    out.sort(key=lambda x: (not x["connected"], not x["online"], -(x["last_seen"] or 0), x["name"].lower()))
    connected = [x for x in out if x["connected"]]
    summary = {"total": len(out), "connected": len(connected), "online": sum(1 for x in connected if x["online"]),
               "offline": sum(1 for x in connected if not x["online"]), "disconnected": len(out) - len(connected),
               "suspended": sum(1 for x in connected if x["workspace"] != "active"),
               "apps_reported": sum(1 for x in connected if x["apps_reported"]),
               "chrome_missing": sum(1 for x in connected if x["chrome"] in ("missing", "failed"))}
    return summary, out[:300]


def _holders(db, people, now):
    """{tool id: [active people who have it]} — their own grant or their department's, end dates respected."""
    direct, by_dept = {}, {}
    for r in db.q("SELECT tool_id, person_id, department FROM entitlements WHERE expires IS NULL OR expires > ?", (now,)):
        if r["person_id"] is not None:
            direct.setdefault(r["tool_id"], set()).add(r["person_id"])
        elif r["department"]:
            by_dept.setdefault(r["tool_id"], set()).add(r["department"])
    out = {}
    for tool_id in set(direct) | set(by_dept):
        ids = direct.get(tool_id, set())
        depts = by_dept.get(tool_id, set())
        out[tool_id] = ([p for p in people if p["status"] == "active" and (p["id"] in ids or (p["department"] and p["department"] in depts))],
                        sorted(depts))
    return out


def _apps_and_accounts(db, tools, holders):
    subs = {s["tool_id"]: s for s in db.q("SELECT tool_id, state, plan, seats, monthly_cost, renews_on FROM subscriptions")}
    assigned, accounts = [], []
    for t in tools:
        people, teams = holders.get(t["id"], ([], []))
        signin = "api" if t["kind"] == "dev" else (t.get("signin") or "seat")
        if people or teams:
            assigned.append({"tool_id": t["id"], "name": t["name"], "category": t["category"], "kind": t["kind"],
                             "signin": signin, "people": len(people), "teams": teams,
                             "names": [p["name"] for p in sorted(people, key=lambda p: p["name"].lower())[:6]]})
        sub = subs.get(t["id"]) or {}
        state = sub.get("state") or "none"
        if not people and not teams and state not in ("active", "past_due"):
            continue
        if t["kind"] == "dev":
            continue  # coding agents run on the company key; there is no account to hold
        shared = signin == "shared"
        accounts.append({"tool_id": t["id"], "name": t["name"], "kind": t["kind"], "signin": signin,
                         "signin_label": SIGNIN_LABEL.get(signin, signin), "state": state, "plan": sub.get("plan") or "",
                         "seats": sub.get("seats"), "monthly_cost": sub.get("monthly_cost"), "renews_on": sub.get("renews_on"),
                         "assigned": len(people), "over_seats": bool(sub.get("seats")) and len(people) > sub["seats"],
                         "limitation": {"text": LIMITATION, "recommendation": RECOMMENDATION} if shared else None})
    assigned.sort(key=lambda x: (-x["people"], x["name"].lower()))
    accounts.sort(key=lambda x: (x["limitation"] is None, not x["over_seats"], x["name"].lower()))
    summary = {"tools": len(accounts), "single_logins": sum(1 for a in accounts if a["limitation"]),
               "seats": sum(1 for a in accounts if a["signin"] == "seat"), "sso": sum(1 for a in accounts if a["signin"] == "sso"),
               "over_seats": sum(1 for a in accounts if a["over_seats"])}
    return assigned, accounts, summary


def _activity(db, now):
    since = now - WEEK
    counts = db.one(
        "SELECT (SELECT COUNT(*) FROM launches WHERE ts >= ? AND outcome = 'opened') AS opens,"
        " (SELECT COUNT(*) FROM launches WHERE ts >= ? AND outcome != 'opened') AS opens_refused,"
        " (SELECT COUNT(*) FROM site_usage WHERE started >= ? AND outcome = 'allowed') AS visits,"
        " (SELECT COUNT(*) FROM site_usage WHERE started >= ? AND outcome != 'allowed') AS visits_blocked,"
        " (SELECT COUNT(*) FROM requests WHERE ts >= ?) AS requests", (since,) * 5)
    people = db.scalar(
        "SELECT COUNT(DISTINCT person_id) FROM (SELECT person_id FROM launches WHERE ts >= ? AND outcome = 'opened'"
        " UNION SELECT person_id FROM site_usage WHERE started >= ? AND outcome = 'allowed'"
        " UNION SELECT person_id FROM requests WHERE ts >= ?) WHERE person_id IS NOT NULL", (since,) * 3) or 0
    recent = db.q(
        "SELECT * FROM (SELECT 'open' AS kind, l.ts, l.person_id, p.name AS person, l.tool_id, t.name AS tool, l.outcome,"
        " NULL AS seconds FROM launches l LEFT JOIN people p ON p.id = l.person_id LEFT JOIN tools t ON t.id = l.tool_id"
        " WHERE l.ts >= ?"
        " UNION ALL SELECT 'visit' AS kind, s.started AS ts, s.person_id, p.name AS person, s.tool_id, t.name AS tool, s.outcome,"
        " s.seconds FROM site_usage s LEFT JOIN people p ON p.id = s.person_id LEFT JOIN tools t ON t.id = s.tool_id"
        " WHERE s.started >= ?) ORDER BY ts DESC LIMIT 8", (since, since))
    return {"source": "observed", "label": "Observed in Swangz", "days": 7, "people": people, **counts, "recent": recent,
            "provider": {"available": False, "label": "Provider-reported usage and billing", "text": PROVIDER_REPORTED}}


def _weekly(gw, now):
    db = gw.db
    try:
        reporting.compile_closed(gw, now)  # the same lazy compile the reporting pages run before they read
    except Exception:
        pass  # the counts below are still true for what is compiled
    current = reporting.week(gw, now)
    last = reporting.week(gw, current["starts"] - 3600)
    rows = db.q("SELECT state, COUNT(*) AS n FROM hub_reports WHERE kind = 'weekly' AND archived_at IS NULL AND week_start = ?"
                " GROUP BY state", (last["week_start"],))
    by_state = {r["state"]: r["n"] for r in rows}
    outstanding = db.scalar("SELECT COUNT(*) FROM hub_reports WHERE kind = 'weekly' AND archived_at IS NULL AND state IN (?, ?)",
                            OUTSTANDING) or 0
    return {"week_start": last["week_start"], "week_end": last["week_end"],
            "submitted": sum(by_state.get(s, 0) for s in SUBMITTED), "missing": sum(by_state.get(s, 0) for s in OUTSTANDING),
            "outstanding_all": outstanding}


def summary(gw, now=None):
    now = time.time() if now is None else now
    db = gw.db
    people = db.q("SELECT id, name, department, status, email FROM people ORDER BY name COLLATE NOCASE")
    people_by_id = {p["id"]: p for p in people}
    tools = db.q("SELECT id, name, category, kind, signin FROM tools WHERE archived = 0 ORDER BY name COLLATE NOCASE")
    names = {t["id"]: t["name"] for t in db.q("SELECT id, name FROM tools")}
    device_summary, devices = _devices(gw, people_by_id, names, now)
    connected_people = {d["person_id"] for d in devices if d["connected"]}
    holders = _holders(db, people, now)
    assigned, accounts, account_summary = _apps_and_accounts(db, tools, holders)
    return {
        "generated": now, "online_minutes": ONLINE_SECONDS // 60, "turns_retired": TURNS_RETIRED,
        "employees": _employees(people, connected_people),
        "devices": {"summary": device_summary, "items": devices},
        "assigned": {"tools": len(assigned), "items": assigned},
        "accounts": {"summary": account_summary, "items": accounts},
        "activity": _activity(db, now),
        "weekly": _weekly(gw, now),
    }


@admin_route("GET", r"/workstations")
def workstations(ctx):
    """Read-only, so no area: every console user may see it. Suspend and revoke use their own routes."""
    return summary(ctx.gw)
