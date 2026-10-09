"""The control room's lenses: what changed, what needs attention, who used what, from which device.

Read-only views over records the gateway already keeps — requests through the gateway, opens from
the portal, the website gate's visits, shared-account turns, keys and the audit log. Nothing here is
guessed beyond what those records hold. Where a value is an estimate (cost, from the price table) or
simply not known (where an IP address is in the world), the answer says so rather than inventing it.

The routes register on the console API (admin.ROUTES), so they share its sign-in and roles: every
lens here is read-only and open to viewers as well as owners.
"""

import json
import re
import time

from . import geo, proxy, turns
from .admin import ApiError, licence_data, route

DAY = 86400
# requests that count as use: not the token counts and job polls a tool makes on the side — unless
# they were refused, because a refusal always counts
COUNTED = "(r.kind NOT IN ('other', 'media-status') OR r.outcome != 'ok')"
USED = "r.kind NOT IN ('other', 'media-status')"
TOKENS = "(r.in_tok + r.out_tok + r.cache_write_tok + r.cache_read_tok)"


# ---------------------------------------------------------------- shared helpers


def _window(ctx, default_days=1):
    """since/until from the query string; by default from the start of today (company time) to now."""
    now = time.time()
    day, _ = proxy.period_starts(now, ctx.gw.settings.tz_offset_minutes)
    since = ctx.arg("since", cast=float)
    until = ctx.arg("until", cast=float) or now + 1
    if since is None:
        since = day - (default_days - 1) * DAY
    if until <= since:
        raise ApiError(400, "until must be after since")
    return since, until


_OS = (("windows", "Windows"), ("iphone", "iOS"), ("ipad", "iPadOS"), ("android", "Android"), ("cros", "ChromeOS"),
       ("mac os", "macOS"), ("macos", "macOS"), ("macintosh", "macOS"), ("darwin", "macOS"), ("ubuntu", "Linux"),
       ("linux", "Linux"))
_BROWSERS = (("edg/", "Edge"), ("opr/", "Opera"), ("firefox/", "Firefox"), ("fxios", "Firefox"), ("crios", "Chrome"),
             ("chrome/", "Chrome"), ("safari/", "Safari"))


def describe_agent(ua):
    """{'os': 'Windows', 'browser': 'Chrome'} as far as a user agent says — None for what it doesn't.
    Coding tools often name no operating system at all, and then neither do we."""
    low = (ua or "").lower()
    return {"os": next((name for needle, name in _OS if needle in low), None),
            "browser": next((name for needle, name in _BROWSERS if needle in low), None)}


def platform(ua, app=None):
    """'Chrome on Windows', 'Codex on macOS', or None."""
    d = describe_agent(ua)
    first = app or d["browser"]
    if first and d["os"]:
        return f"{first} on {d['os']}"
    return first or d["os"]


def ip_kind(ip):
    """What can honestly be said about an address: a known network's name, an approximate city and country
    from the offline location table, or just its type (gateway/geo.py)."""
    from . import geo

    return geo.label(ip)


class Tools:
    """Catalog tools by id, and which one a proxied request belongs to (as catalog.provider_tool does)."""

    def __init__(self, db):
        rows = db.q("SELECT id, name, kind, provider, category, color, signin FROM tools ORDER BY rowid")
        self.by_id = {r["id"]: r for r in rows}
        self.by_provider = {}
        for r in rows:
            if r["kind"] == "api" and r["provider"]:
                self.by_provider.setdefault(r["provider"], r)

    def for_request(self, client, provider):
        if client == "Claude Code" and "claude-code" in self.by_id:
            return self.by_id["claude-code"]
        if client == "Codex" and "codex" in self.by_id:
            return self.by_id["codex"]
        return self.by_provider.get(provider)


def tool_requests_where(tool):
    """SQL (on requests r) for the gateway traffic that belongs to a catalog tool, or None for a website."""
    if tool["kind"] == "dev":
        client = {"claude-code": "Claude Code", "codex": "Codex"}.get(tool["id"], tool["name"])
        return "r.client = ?", [client]
    if tool["kind"] == "api" and tool["provider"]:
        return "r.provider = ? AND r.client NOT IN ('Claude Code', 'Codex')", [tool["provider"]]
    return None


def _in(values):
    values = list(values)
    return ",".join("?" * len(values)) or "NULL", values


def _active_people(db, since, until):
    return db.scalar(
        "SELECT COUNT(DISTINCT pid) FROM ("
        " SELECT person_id AS pid FROM requests r WHERE r.ts >= ? AND r.ts < ? AND r.person_id IS NOT NULL"
        f" AND r.outcome = 'ok' AND {USED}"
        " UNION SELECT person_id FROM launches WHERE ts >= ? AND ts < ? AND person_id IS NOT NULL AND outcome = 'opened'"
        " UNION SELECT person_id FROM site_usage WHERE started >= ? AND started < ? AND person_id IS NOT NULL"
        " AND outcome = 'allowed')", (since, until) * 3) or 0


def usage_rows(db, since, until, person=None, tool_id=None):
    """Who used what in a window: one row per person and tool, across the three records —
    requests through the gateway, opens from the portal, and website-gate visits."""
    tools = Tools(db)
    rows = {}

    def row(r, tool, app=None):
        key = (r["person_id"], tool["id"] if tool else "app:" + (app or "?"))
        if key not in rows:
            rows[key] = {"person_id": r["person_id"], "person": r["name"], "department": r["department"] or "",
                         "tool_id": tool["id"] if tool else None, "tool": tool["name"] if tool else (app or "Unknown tool"),
                         "category": tool["category"] if tool else "", "apps": set(), "requests": 0, "cost": 0.0,
                         "tokens": 0, "generations": 0, "refused": 0, "opens": 0, "visits": 0, "seconds": 0,
                         "blocked": 0, "last": 0}
        return rows[key]

    who = " AND {col} = ?" if person else ""
    extra = [person] if person else []
    for r in db.q(
            f"SELECT r.person_id, p.name, p.department, r.client, r.provider, COUNT(*) AS n, COALESCE(SUM(r.cost), 0) AS cost,"
            f" COALESCE(SUM({TOKENS}), 0) AS tokens, SUM(r.kind = 'media') AS media, SUM(r.outcome != 'ok') AS refused,"
            " MAX(r.ts) AS last FROM requests r JOIN people p ON p.id = r.person_id"
            f" WHERE r.ts >= ? AND r.ts < ? AND {COUNTED}" + who.format(col="r.person_id")
            + " GROUP BY r.person_id, r.client, r.provider", [since, until] + extra):
        x = row(r, tools.for_request(r["client"], r["provider"]), r["client"] or r["provider"])
        x["requests"] += r["n"] - (r["refused"] or 0)
        x["refused"] += r["refused"] or 0
        x["cost"] += r["cost"] or 0
        x["tokens"] += r["tokens"] or 0
        x["generations"] += r["media"] or 0
        x["last"] = max(x["last"], r["last"] or 0)
        if r["client"] and r["client"] != "unknown":
            x["apps"].add(r["client"])
    for r in db.q(
            "SELECT l.person_id, p.name, p.department, l.tool_id, SUM(l.outcome = 'opened') AS opened,"
            " SUM(l.outcome != 'opened') AS refused, MAX(l.ts) AS last FROM launches l JOIN people p ON p.id = l.person_id"
            " WHERE l.ts >= ? AND l.ts < ?" + who.format(col="l.person_id") + " GROUP BY l.person_id, l.tool_id",
            [since, until] + extra):
        x = row(r, tools.by_id.get(r["tool_id"]), "A removed tool")
        x["opens"] += r["opened"] or 0
        x["refused"] += r["refused"] or 0
        x["last"] = max(x["last"], r["last"] or 0)
    for r in db.q(
            "SELECT su.person_id, p.name, p.department, su.tool_id, SUM(su.outcome = 'allowed') AS visits,"
            " SUM(su.outcome = 'blocked') AS blocked, COALESCE(SUM(su.seconds), 0) AS seconds, MAX(su.started) AS last"
            " FROM site_usage su JOIN people p ON p.id = su.person_id WHERE su.started >= ? AND su.started < ?"
            + who.format(col="su.person_id") + " GROUP BY su.person_id, su.tool_id", [since, until] + extra):
        x = row(r, tools.by_id.get(r["tool_id"]), "A removed tool")
        x["visits"] += r["visits"] or 0
        x["blocked"] += r["blocked"] or 0
        x["seconds"] += r["seconds"] or 0
        x["last"] = max(x["last"], r["last"] or 0)
    out = [dict(x, apps=sorted(x["apps"])) for x in rows.values() if not tool_id or x["tool_id"] == tool_id]
    out.sort(key=lambda x: -x["last"])
    return out, tools


def _people_totals(rows):
    people = {}
    for x in rows:
        p = people.setdefault(x["person_id"], {"person_id": x["person_id"], "person": x["person"],
                                               "department": x["department"], "tools": 0, "requests": 0, "cost": 0.0,
                                               "opens": 0, "visits": 0, "seconds": 0, "refused": 0, "last": 0})
        p["tools"] += 1
        for k in ("requests", "cost", "opens", "visits", "seconds", "refused"):
            p[k] += x[k]
        p["last"] = max(p["last"], x["last"])
    return sorted(people.values(), key=lambda p: (-p["cost"], -(p["requests"] + p["opens"] + p["visits"])))


def _tool_totals(rows):
    tools = {}
    for x in rows:
        key = x["tool_id"] or x["tool"]
        t = tools.setdefault(key, {"tool_id": x["tool_id"], "tool": x["tool"], "category": x["category"], "people": 0,
                                   "requests": 0, "cost": 0.0, "opens": 0, "visits": 0, "seconds": 0, "last": 0})
        t["people"] += 1
        for k in ("requests", "cost", "opens", "visits", "seconds"):
            t[k] += x[k]
        t["last"] = max(t["last"], x["last"])
    return sorted(tools.values(), key=lambda t: -(t["requests"] + t["opens"] + t["visits"]))


def _days(ctx, days):
    off = ctx.gw.settings.tz_offset_minutes * 60
    today, _ = proxy.period_starts(time.time(), ctx.gw.settings.tz_offset_minutes)
    since = today - (days - 1) * DAY
    return off, since, [since + i * DAY for i in range(days)]


def _bucket(off, ts):
    return int((ts + off) // DAY)


# ---------------------------------------------------------------- trends: the overview's shape over time


@route("GET", r"/trends")
def trends(ctx):
    """A day-by-day series (company time) of use and spend, with the window before it to compare."""
    db = ctx.db
    days = max(7, min(ctx.arg("days", 30, int), 92))
    off, since, starts = _days(ctx, days)
    now = time.time()
    series = {_bucket(off, s): {"start": s, "requests": 0, "cost": 0.0, "tokens": 0, "refused": 0, "opens": 0,
                                "visits": 0, "seconds": 0, "people": 0} for s in starts}
    for r in db.q(f"SELECT CAST((r.ts + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n, COALESCE(SUM(r.cost), 0) AS cost,"
                  f" COALESCE(SUM({TOKENS}), 0) AS tokens, SUM(r.outcome != 'ok') AS refused"
                  f" FROM requests r WHERE r.ts >= ? AND {COUNTED} GROUP BY d", (off, since)):
        if r["d"] in series:
            series[r["d"]].update(requests=r["n"], cost=r["cost"], tokens=r["tokens"], refused=r["refused"] or 0)
    for r in db.q("SELECT CAST((ts + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n FROM launches"
                  " WHERE ts >= ? AND outcome = 'opened' GROUP BY d", (off, since)):
        if r["d"] in series:
            series[r["d"]]["opens"] = r["n"]
    for r in db.q("SELECT CAST((started + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n, COALESCE(SUM(seconds), 0) AS s"
                  " FROM site_usage WHERE started >= ? AND outcome = 'allowed' GROUP BY d", (off, since)):
        if r["d"] in series:
            series[r["d"]].update(visits=r["n"], seconds=r["s"])
    for r in db.q(
            "SELECT CAST((t + ?) / 86400 AS INTEGER) AS d, COUNT(DISTINCT pid) AS n FROM ("
            " SELECT r.ts AS t, r.person_id AS pid FROM requests r WHERE r.ts >= ? AND r.person_id IS NOT NULL"
            f" AND r.outcome = 'ok' AND {USED}"
            " UNION ALL SELECT ts, person_id FROM launches WHERE ts >= ? AND person_id IS NOT NULL AND outcome = 'opened'"
            " UNION ALL SELECT started, person_id FROM site_usage WHERE started >= ? AND person_id IS NOT NULL"
            " AND outcome = 'allowed') GROUP BY d", (off, since, since, since)):
        if r["d"] in series:
            series[r["d"]]["people"] = r["n"]

    def totals(a, b):
        row = db.one(f"SELECT COUNT(*) AS requests, COALESCE(SUM(r.cost), 0) AS cost FROM requests r"
                     f" WHERE r.ts >= ? AND r.ts < ? AND {USED}", (a, b))
        row["people"] = _active_people(db, a, b)
        row["opens"] = db.scalar("SELECT COUNT(*) FROM launches WHERE ts >= ? AND ts < ? AND outcome = 'opened'", (a, b)) or 0
        return row

    rows, _ = usage_rows(db, since, now + 1)
    return {
        "days": [series[k] for k in sorted(series)], "since": since, "tz_offset_minutes": ctx.gw.settings.tz_offset_minutes,
        "current": totals(since, now + 1), "previous": totals(since - days * DAY, since),
        "top_people": _people_totals(rows)[:8], "top_tools": _tool_totals(rows)[:8],
        "tools_used": len(_tool_totals(rows)), "people_active": len({x["person_id"] for x in rows}),
    }


# ---------------------------------------------------------------- who used what


@route("GET", r"/usage")
def usage(ctx):
    """One row per person and tool for a window (default: today), across every record we keep."""
    since, until = _window(ctx)
    rows, _ = usage_rows(ctx.db, since, until, ctx.arg("person", cast=int), ctx.arg("tool"))
    return {"since": since, "until": until, "rows": rows, "people": _people_totals(rows), "tools": _tool_totals(rows)}


# ---------------------------------------------------------------- who did what, when, where


@route("GET", r"/timeline")
def timeline(ctx):
    """Every event in one stream, newest first: AI requests, tools opened from the portal, and AI
    websites visited through the browser gate. Paged with ?before=<ts>."""
    db = ctx.db
    since, until = _window(ctx, default_days=7)
    before = ctx.arg("before", cast=float)
    if before:
        until = min(until, before)
    limit = max(1, min(ctx.arg("limit", 60, int), 200))
    person, dept, kind = ctx.arg("person", cast=int), ctx.arg("dept"), ctx.arg("type")
    tool = db.one("SELECT * FROM tools WHERE id = ?", (ctx.arg("tool"),)) if ctx.arg("tool") else None
    if ctx.arg("tool") and not tool:
        raise ApiError(404, "no such tool")
    q = ctx.arg("q")
    like = "%" + q.replace("%", "").replace("_", "") + "%" if q else None
    tools = Tools(db)
    events = []

    def scope(person_col, args):
        sql = ""
        if person:
            sql += f" AND {person_col} = ?"
            args.append(person)
        if dept:
            sql += " AND p.department = ?"
            args.append(dept)
        return sql

    if kind in (None, "request"):
        args = [since, until]
        sql = (f"SELECT r.id, r.ts, r.person_id, p.name AS person, p.department, r.client, r.provider, r.model, r.kind,"
               f" r.media_type, r.outcome, r.reason, r.cost, {TOKENS} AS tokens, r.duration_ms, r.session, r.prompt,"
               " r.actions, r.flags, r.client_ip, r.key_id, k.label AS device, r.user_agent, r.agent, r.purpose, r.purpose_source,"
               " r.purpose_confidence, r.project, r.rule"
               " FROM requests r LEFT JOIN people p ON p.id = r.person_id LEFT JOIN keys k ON k.id = r.key_id"
               f" WHERE r.ts >= ? AND r.ts < ? AND {COUNTED}") + scope("r.person_id", args)
        where = tool_requests_where(tool) if tool else ("", [])
        if tool and where is None:
            sql = None
        elif tool:
            sql += " AND " + where[0]
            args += where[1]
        if sql and like:
            sql += " AND (r.prompt LIKE ? OR r.actions LIKE ? OR p.name LIKE ? OR r.client LIKE ? OR r.model LIKE ?)"
            args += [like] * 5
        if sql:
            for r in db.q(sql + " ORDER BY r.ts DESC LIMIT ?", args + [limit + 1]):
                t = tools.for_request(r["client"], r["provider"])
                try:
                    n_actions = len(json.loads(r.pop("actions") or "[]"))
                except ValueError:
                    n_actions = 0
                events.append({
                    "type": "request", "id": r["id"], "ts": r["ts"], "person_id": r["person_id"], "person": r["person"],
                    "department": r["department"], "tool_id": t["id"] if t else None, "tool": t["name"] if t else None,
                    "app": r["client"] or None, "model": r["model"], "kind": r["kind"], "media_type": r["media_type"],
                    "outcome": r["outcome"], "reason": r["reason"], "cost": r["cost"], "tokens": r["tokens"],
                    "duration_ms": r["duration_ms"], "session": r["session"], "agent": r["agent"],
                    "prompt": (r["prompt"] or "")[:240] or None, "actions": n_actions,
                    "credential": "secret:" in (r["flags"] or ""), "device": r["device"], "key_id": r["key_id"],
                    "platform": platform(r["user_agent"], r["client"] if r["client"] not in ("", "unknown") else None),
                    "ip": r["client_ip"] or None, "place": ip_kind(r["client_ip"]),
                    "purpose": r["purpose"], "purpose_source": r["purpose_source"], "purpose_confidence": r["purpose_confidence"],
                    "project": r["project"], "rule": r["rule"],
                })
    if kind in (None, "launch"):
        args = [since, until]
        sql = ("SELECT l.id, l.ts, l.person_id, p.name AS person, p.department, l.tool_id, t.name AS tool, l.outcome,"
               " l.ip, l.user_agent, l.reason, l.rule FROM launches l LEFT JOIN people p ON p.id = l.person_id"
               " LEFT JOIN tools t ON t.id = l.tool_id WHERE l.ts >= ? AND l.ts < ?") + scope("l.person_id", args)
        if tool:
            sql += " AND l.tool_id = ?"
            args.append(tool["id"])
        if like:
            sql += " AND (p.name LIKE ? OR t.name LIKE ?)"
            args += [like, like]
        for r in db.q(sql + " ORDER BY l.ts DESC LIMIT ?", args + [limit + 1]):
            events.append({"type": "launch", "id": r["id"], "ts": r["ts"], "person_id": r["person_id"], "person": r["person"],
                           "department": r["department"], "tool_id": r["tool_id"], "tool": r["tool"], "outcome": r["outcome"],
                           "platform": platform(r["user_agent"]), "ip": r["ip"] or None, "place": ip_kind(r["ip"]),
                           "reason": r["reason"] or None, "rule": r["rule"]})
    if kind in (None, "site"):
        args = [since, until]
        sql = ("SELECT su.id, su.started AS ts, su.person_id, p.name AS person, p.department, su.tool_id, t.name AS tool,"
               " su.host, su.outcome, su.seconds, su.reason, su.rule FROM site_usage su LEFT JOIN people p ON p.id = su.person_id"
               " LEFT JOIN tools t ON t.id = su.tool_id WHERE su.started >= ? AND su.started < ?") + scope("su.person_id", args)
        if tool:
            sql += " AND su.tool_id = ?"
            args.append(tool["id"])
        if like:
            sql += " AND (p.name LIKE ? OR t.name LIKE ? OR su.host LIKE ?)"
            args += [like] * 3
        for r in db.q(sql + " ORDER BY su.started DESC LIMIT ?", args + [limit + 1]):
            events.append({"type": "site", "id": r["id"], "ts": r["ts"], "person_id": r["person_id"], "person": r["person"],
                           "department": r["department"], "tool_id": r["tool_id"], "tool": r["tool"] or r["host"],
                           "host": r["host"], "outcome": r["outcome"], "seconds": r["seconds"], "reason": r["reason"] or None,
                           "rule": r["rule"]})
    if kind in (None, "turn"):
        args = [since, until]
        sql = ("SELECT tt.id, tt.started AS ts, tt.person_id, p.name AS person, p.department, tt.tool_id, t.name AS tool,"
               " tt.expires, tt.ended, tt.ended_by, tt.reason, tt.ws_host FROM tool_turns tt LEFT JOIN people p ON p.id = tt.person_id"
               " LEFT JOIN tools t ON t.id = tt.tool_id WHERE tt.started >= ? AND tt.started < ?") + scope("tt.person_id", args)
        if tool:
            sql += " AND tt.tool_id = ?"
            args.append(tool["id"])
        if like:
            sql += " AND (p.name LIKE ? OR t.name LIKE ?)"
            args += [like, like]
        for r in db.q(sql + " ORDER BY tt.started DESC LIMIT ?", args + [limit + 1]):
            events.append({"type": "turn", "id": r["id"], "ts": r["ts"], "person_id": r["person_id"], "person": r["person"],
                           "department": r["department"], "tool_id": r["tool_id"], "tool": r["tool"], "expires": r["expires"],
                           "ended": r["ended"], "ended_by": r["ended_by"] or None, "reason": r["reason"] or None,
                           "where": r["ws_host"] or None})
    if kind in (None, "access") and not tool:
        # sign-ins and access changes about a person, from the audit log (entries that name the person they concern)
        args = [since, until]
        sql = ("SELECT a.id, a.ts, a.actor, a.action, a.target, a.detail, a.ip, a.outcome, a.reason, a.correlation, p.id AS person_id,"
               " p.name AS person, p.department FROM audit a JOIN people p ON a.correlation = 'person:' || p.id"
               " WHERE a.ts >= ? AND a.ts < ? AND a.correlation LIKE 'person:%'") + scope("p.id", args)
        if like:
            sql += " AND (p.name LIKE ? OR a.action LIKE ? OR a.actor LIKE ?)"
            args += [like] * 3
        for r in db.q(sql + " ORDER BY a.ts DESC LIMIT ?", args + [limit + 1]):
            events.append({"type": "access", "id": r["id"], "ts": r["ts"], "person_id": r["person_id"], "person": r["person"],
                           "department": r["department"], "actor": r["actor"], "action": r["action"], "target": r["target"],
                           "detail": r["detail"] or None, "outcome": r["outcome"], "audit_reason": r["reason"] or None,
                           "ip": r["ip"] or None, "place": ip_kind(r["ip"]) if r["ip"] else None,
                           "self": r["actor"] == r["person"]})
    events.sort(key=lambda e: -e["ts"])
    more = len(events) > limit
    events = events[:limit]
    return {"items": events, "more": more, "next_before": events[-1]["ts"] if more and events else None,
            "since": since, "until": until}


# ---------------------------------------------------------------- devices


def _device_state(k, now):
    if k.get("revoked"):
        return "revoked"
    if k.get("person_status") and k["person_status"] != "active":
        return "suspended"
    if not k.get("last_used"):
        return "unused"
    return "active" if k["last_used"] >= now - 7 * DAY else "idle"


KEY_COLUMNS = ("k.id, k.label, k.hint, k.person_id, p.name AS person, p.department, p.status AS person_status,"
               " k.created, k.created_by, k.revoked, k.revoked_by, k.last_used")


@route("GET", r"/devices")
def devices(ctx):
    """Every device that holds a gateway key — one key per laptop or coding tool — with what it was
    last used for and from where; plus the browsers staff opened tools from in the portal."""
    db = ctx.db
    now = time.time()
    keys = db.q(f"SELECT {KEY_COLUMNS} FROM keys k JOIN people p ON p.id = k.person_id"
                " ORDER BY k.revoked IS NOT NULL, COALESCE(k.last_used, k.created) DESC")
    stats = {r["key_id"]: r for r in db.q(
        "SELECT key_id, COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost, COUNT(DISTINCT client_ip) AS ips"
        f" FROM requests r WHERE r.ts >= ? AND r.key_id IS NOT NULL AND {USED} GROUP BY key_id", (now - 30 * DAY,))}
    last = {r["key_id"]: r for r in db.q(
        "SELECT r.key_id, r.client, r.client_ip, r.user_agent FROM requests r JOIN"
        " (SELECT key_id, MAX(id) AS id FROM requests WHERE key_id IS NOT NULL GROUP BY key_id) m ON m.id = r.id")}
    items = []
    for k in keys:
        s, l = stats.get(k["id"]) or {}, last.get(k["id"]) or {}
        app = l.get("client") if l.get("client") not in (None, "", "unknown") else None
        items.append(dict(k, state=_device_state(k, now), app=app, platform=platform(l.get("user_agent"), app),
                          os=describe_agent(l.get("user_agent"))["os"], last_ip=l.get("client_ip") or None,
                          place=ip_kind(l.get("client_ip")) if l.get("client_ip") else None,
                          requests_30d=s.get("requests", 0), cost_30d=s.get("cost", 0.0), ips_30d=s.get("ips", 0)))
    browsers = {}
    for r in db.q("SELECT l.person_id, p.name, l.user_agent, l.ip, MAX(l.ts) AS last, COUNT(*) AS opens FROM launches l"
                  " JOIN people p ON p.id = l.person_id WHERE l.ts >= ? GROUP BY l.person_id, l.user_agent", (now - 90 * DAY,)):
        d = describe_agent(r["user_agent"])
        key = (r["person_id"], d["browser"], d["os"])
        b = browsers.setdefault(key, {"person_id": r["person_id"], "person": r["name"], "browser": d["browser"],
                                      "os": d["os"], "opens": 0, "last": 0, "last_ip": None})
        b["opens"] += r["opens"]
        if r["last"] > b["last"]:
            b["last"], b["last_ip"] = r["last"], r["ip"] or None
    counts = {s: sum(1 for i in items if i["state"] == s) for s in ("active", "idle", "unused", "revoked", "suspended")}
    return {"items": items, "browsers": sorted(browsers.values(), key=lambda b: -b["last"]), "counts": counts}


@route("GET", r"/devices/(?P<kid>[0-9a-f]{12})")
def device(ctx, kid):
    """Everything done from one device: where it connected from, which apps and models, its sessions,
    anything refused or flagged, and its last 30 days of use."""
    db = ctx.db
    now = time.time()
    k = db.one(f"SELECT {KEY_COLUMNS} FROM keys k JOIN people p ON p.id = k.person_id WHERE k.id = ?", (kid,))
    if not k:
        raise ApiError(404, "no such device")
    totals = db.one(f"SELECT MIN(r.ts) AS first, COUNT(*) AS requests, COALESCE(SUM(r.cost), 0) AS cost,"
                    f" COALESCE(SUM({TOKENS}), 0) AS tokens FROM requests r WHERE r.key_id = ? AND {USED}", (kid,))
    ips = db.q("SELECT client_ip AS ip, MIN(ts) AS first, MAX(ts) AS last, COUNT(*) AS requests FROM requests"
               " WHERE key_id = ? GROUP BY client_ip ORDER BY last DESC LIMIT 12", (kid,))
    for ip in ips:
        ip["place"] = ip_kind(ip["ip"])
    apps = db.q(f"SELECT r.client, MAX(r.ts) AS last, r.user_agent, COUNT(*) AS requests FROM requests r"
                f" WHERE r.key_id = ? AND {USED} GROUP BY r.client ORDER BY last DESC", (kid,))
    for a in apps:
        a["platform"] = platform(a.pop("user_agent"), a["client"] if a["client"] not in ("", "unknown") else None)
    models = db.q(f"SELECT r.model, COUNT(*) AS requests, COALESCE(SUM(r.cost), 0) AS cost FROM requests r"
                  f" WHERE r.key_id = ? AND r.model IS NOT NULL AND {USED} GROUP BY r.model ORDER BY requests DESC LIMIT 10", (kid,))
    sessions = db.q(
        "SELECT session, MIN(ts) AS started, MAX(ts) AS last, COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost,"
        " MAX(client) AS client, (SELECT prompt FROM requests r2 WHERE r2.session = r.session AND r2.prompt IS NOT NULL"
        " ORDER BY r2.id LIMIT 1) AS first_prompt FROM requests r WHERE key_id = ? AND session IS NOT NULL"
        f" AND {USED} GROUP BY session ORDER BY last DESC LIMIT 15", (kid,))
    flagged = db.q("SELECT id, ts, outcome, reason, flags, client, model FROM requests WHERE key_id = ?"
                   " AND (flags LIKE '%secret:%' OR outcome != 'ok') ORDER BY id DESC LIMIT 12", (kid,))
    off, since, starts = _days(ctx, 30)
    series = {_bucket(off, s): {"start": s, "requests": 0, "cost": 0.0} for s in starts}
    for r in db.q(f"SELECT CAST((r.ts + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n, COALESCE(SUM(r.cost), 0) AS cost"
                  f" FROM requests r WHERE r.key_id = ? AND r.ts >= ? AND {USED} GROUP BY d", (off, kid, since)):
        if r["d"] in series:
            series[r["d"]].update(requests=r["n"], cost=r["cost"])
    last = apps[0] if apps else {}
    return dict(k, state=_device_state(k, now), app=last.get("client") if last.get("client") not in (None, "", "unknown") else None,
                platform=last.get("platform"), first_used=totals["first"], totals=totals, ips=ips, apps=apps, models=models,
                sessions=sessions, flagged=flagged, series=[series[d] for d in sorted(series)])


# ---------------------------------------------------------------- one tool's own profile


@route("GET", r"/tools/(?P<tid>[a-z0-9-]+)/usage")
def tool_usage(ctx, tid):
    """A tool's last 30 days: who used it, how often, from which devices, what it cost, what was refused."""
    db = ctx.db
    tool = db.one("SELECT * FROM tools WHERE id = ?", (tid,))
    if not tool:
        raise ApiError(404, "no such tool")
    now = time.time()
    _, month = proxy.period_starts(now, ctx.gw.settings.tz_offset_minutes)
    off, since, starts = _days(ctx, 30)
    rows, _ = usage_rows(db, since, now + 1, tool_id=tid)
    series = {_bucket(off, s): {"start": s, "uses": 0} for s in starts}
    for sql in ("SELECT CAST((ts + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n FROM launches WHERE tool_id = ? AND ts >= ?"
                " AND outcome = 'opened' GROUP BY d",
                "SELECT CAST((started + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n FROM site_usage WHERE tool_id = ?"
                " AND started >= ? AND outcome = 'allowed' GROUP BY d"):
        for r in db.q(sql, (off, tid, since)):
            if r["d"] in series:
                series[r["d"]]["uses"] += r["n"]
    where = tool_requests_where(tool)
    devices, cost, refused_requests = [], 0.0, []
    if where:
        for r in db.q(f"SELECT CAST((r.ts + ?) / 86400 AS INTEGER) AS d, COUNT(*) AS n FROM requests r"
                      f" WHERE {where[0]} AND r.ts >= ? AND {USED} GROUP BY d", [off] + where[1] + [since]):
            if r["d"] in series:
                series[r["d"]]["uses"] += r["n"]
        devices = db.q(f"SELECT r.key_id, k.label, p.name AS person, r.person_id, COUNT(*) AS requests, MAX(r.ts) AS last"
                       f" FROM requests r JOIN keys k ON k.id = r.key_id JOIN people p ON p.id = r.person_id"
                       f" WHERE {where[0]} AND r.ts >= ? AND {USED} GROUP BY r.key_id ORDER BY last DESC LIMIT 20",
                       where[1] + [since])
        cost = db.scalar(f"SELECT COALESCE(SUM(r.cost), 0) FROM requests r WHERE {where[0]} AND r.ts >= ?",
                         where[1] + [since]) or 0.0
        refused_requests = db.q(f"SELECT r.id, r.ts, p.name AS person, r.person_id, r.outcome, r.reason FROM requests r"
                                f" LEFT JOIN people p ON p.id = r.person_id WHERE {where[0]} AND r.ts >= ?"
                                f" AND r.outcome IN ('blocked', 'denied') ORDER BY r.id DESC LIMIT 10", where[1] + [since])
    denials = [{"type": "launch", "ts": r["ts"], "person": r["person"], "person_id": r["person_id"],
                "reason": "opened from the portal while not entitled"} for r in db.q(
        "SELECT l.ts, p.name AS person, l.person_id FROM launches l LEFT JOIN people p ON p.id = l.person_id"
        " WHERE l.tool_id = ? AND l.ts >= ? AND l.outcome != 'opened' ORDER BY l.id DESC LIMIT 10", (tid, since))]
    denials += [{"type": "site", "ts": r["ts"], "person": r["person"], "person_id": r["person_id"],
                 "reason": "website blocked by the browser gate"} for r in db.q(
        "SELECT su.started AS ts, p.name AS person, su.person_id FROM site_usage su LEFT JOIN people p ON p.id = su.person_id"
        " WHERE su.tool_id = ? AND su.started >= ? AND su.outcome = 'blocked' ORDER BY su.id DESC LIMIT 10", (tid, since))]
    denials += [{"type": "request", "ts": r["ts"], "person": r["person"], "person_id": r["person_id"], "id": r["id"],
                 "reason": r["reason"] or r["outcome"]} for r in refused_requests]
    denials.sort(key=lambda d: -d["ts"])
    month_rows, _ = usage_rows(db, month, now + 1, tool_id=tid)
    return {"people": sorted(rows, key=lambda x: -(x["requests"] + x["opens"] + x["visits"])),
            "series": [series[d] for d in sorted(series)], "devices": devices, "cost_30d": cost,
            "denials": denials[:15], "active_month": len({x["person_id"] for x in month_rows
                                                          if x["requests"] + x["opens"] + x["visits"]})}


# ---------------------------------------------------------------- spend: what cost us money


@route("GET", r"/spend")
def spend(ctx):
    """Metered spend (requests through the gateway, priced from the price table when they ran) for a
    window, broken down every useful way, each against the same-length window before it."""
    db = ctx.db
    since, until = _window(ctx, default_days=30)
    span = until - since
    prev = (since - span, since)
    tools = Tools(db)

    def group(expr, a, b, extra_cols=""):
        return {r["k"]: r for r in db.q(
            f"SELECT {expr} AS k{extra_cols}, COUNT(*) AS requests, COALESCE(SUM(r.cost), 0) AS cost,"
            " SUM(r.cost IS NULL AND r.outcome = 'ok') AS unpriced"
            f" FROM requests r LEFT JOIN people p ON p.id = r.person_id WHERE r.ts >= ? AND r.ts < ? AND {USED}"
            " GROUP BY k", (a, b))}

    def compare(now_rows, then_rows, label):
        out = []
        for k, r in now_rows.items():
            before = (then_rows.get(k) or {}).get("cost", 0.0)
            out.append({"key": k, "label": label(k, r), "cost": r["cost"], "requests": r["requests"],
                        "unpriced": r["unpriced"] or 0, "previous": before,
                        "change": (r["cost"] - before) / before if before else None})
        for k, r in then_rows.items():
            if k not in now_rows and r["cost"]:
                out.append({"key": k, "label": label(k, r), "cost": 0.0, "requests": 0, "unpriced": 0,
                            "previous": r["cost"], "change": -1.0})
        return sorted(out, key=lambda x: (-x["cost"], -x["requests"]))

    people = compare(group("r.person_id", since, until, ", MAX(p.name) AS name"), group("r.person_id", *prev, ", MAX(p.name) AS name"),
                     lambda k, r: r.get("name") or "No valid key")
    depts = compare(group("COALESCE(NULLIF(p.department, ''), '—')", since, until), group("COALESCE(NULLIF(p.department, ''), '—')", *prev),
                    lambda k, r: "No department" if k == "—" else k)
    models = compare(group("COALESCE(r.model, '')", since, until), group("COALESCE(r.model, '')", *prev),
                     lambda k, r: k or "No model")
    by_app = {}
    for a, b, which in ((since, until, "now"), (prev[0], prev[1], "then")):
        for r in db.q(f"SELECT r.client, r.provider, COUNT(*) AS requests, COALESCE(SUM(r.cost), 0) AS cost,"
                      f" SUM(r.cost IS NULL AND r.outcome = 'ok') AS unpriced FROM requests r"
                      f" WHERE r.ts >= ? AND r.ts < ? AND {USED} GROUP BY r.client, r.provider", (a, b)):
            t = tools.for_request(r["client"], r["provider"])
            key = t["id"] if t else (r["client"] or r["provider"])
            slot = by_app.setdefault(key, {"now": {"cost": 0.0, "requests": 0, "unpriced": 0}, "then": {"cost": 0.0, "requests": 0, "unpriced": 0},
                                           "label": t["name"] if t else (r["client"] or r["provider"]), "tool_id": t["id"] if t else None})
            for f in ("cost", "requests", "unpriced"):
                slot[which][f] += r[f] or 0
    tool_rows = sorted(({"key": k, "tool_id": v["tool_id"], "label": v["label"], "cost": v["now"]["cost"],
                         "requests": v["now"]["requests"], "unpriced": v["now"]["unpriced"], "previous": v["then"]["cost"],
                         "change": (v["now"]["cost"] - v["then"]["cost"]) / v["then"]["cost"] if v["then"]["cost"] else None}
                        for k, v in by_app.items() if v["now"]["requests"] or v["then"]["cost"]),
                       key=lambda x: (-x["cost"], -x["requests"]))
    total = sum(x["cost"] for x in people)
    previous = sum(x["previous"] for x in people)
    # an increase worth a look: at least half again what it was, and at least a dollar more
    increases = [dict(x, dimension=dim) for dim, rows in (("person", people), ("tool", tool_rows), ("model", models))
                 for x in rows if x["previous"] and x["cost"] >= x["previous"] * 1.5 and x["cost"] - x["previous"] >= 1]
    increases += [dict(x, dimension=dim, new=True) for dim, rows in (("person", people), ("tool", tool_rows))
                  for x in rows if not x["previous"] and x["cost"] >= 5]
    increases.sort(key=lambda x: -(x["cost"] - x["previous"]))
    off = ctx.gw.settings.tz_offset_minutes * 60
    days = {}
    for r in db.q(f"SELECT CAST((r.ts + ?) / 86400 AS INTEGER) AS d, COALESCE(SUM(r.cost), 0) AS cost, COUNT(*) AS n"
                  f" FROM requests r WHERE r.ts >= ? AND r.ts < ? AND {USED} GROUP BY d", (off, since, until)):
        days[r["d"]] = {"start": r["d"] * DAY - off, "cost": r["cost"], "requests": r["n"]}
    first, final = _bucket(off, since), _bucket(off, until - 1)
    series = [days.get(d, {"start": d * DAY - off, "cost": 0.0, "requests": 0}) for d in range(first, final + 1)] \
        if final - first <= 400 else []
    lic = licence_data(db, ctx.gw.settings)
    idle = [{"tool_id": t["id"], "tool": t["name"], "idle": len(t["idle"]), "assigned": t["assigned"],
             "monthly_cost": t["monthly_cost"], "idle_cost": (t["monthly_cost"] or 0) / max(t["assigned"], 1) * len(t["idle"])}
            for t in lic["tools"] if t["idle"] and t["monthly_cost"]]
    return {"since": since, "until": until, "total": total, "previous_total": previous,
            "change": (total - previous) / previous if previous else None,
            "unpriced": sum(x["unpriced"] for x in people), "requests": sum(x["requests"] for x in people),
            "people": people, "departments": depts, "models": models, "tools": tool_rows, "series": series,
            "increases": increases[:10], "subscriptions_month": lic["summary"]["subscriptions_month"],
            "idle": sorted(idle, key=lambda x: -x["idle_cost"])}


# ---------------------------------------------------------------- security


SEVERITY = {"high": 3, "medium": 2, "low": 1, "info": 0}


def _a(noun):
    return ("an " if noun[:1].upper() in "AEIOU" else "a ") + noun


def _unusual(db, now):
    """People busier than their own normal: this hour's requests against their usual active hour, and
    today's spend against their usual day. A prompt to look, never a finding of wrongdoing."""
    out = []
    hour = {r["person_id"]: r for r in db.q(
        f"SELECT r.person_id, p.name, COUNT(*) AS n, MAX(r.client) AS client FROM requests r JOIN people p ON p.id = r.person_id"
        f" WHERE r.ts >= ? AND {USED} AND r.outcome = 'ok' GROUP BY r.person_id", (now - 3600,))}
    if hour:
        marks, ids = _in(hour)
        base = {r["person_id"]: r for r in db.q(
            f"SELECT person_id, COUNT(*) AS n, COUNT(DISTINCT CAST(ts / 3600 AS INTEGER)) AS hours FROM requests r"
            f" WHERE r.ts >= ? AND r.ts < ? AND {USED} AND r.outcome = 'ok' AND r.person_id IN ({marks}) GROUP BY person_id",
            [now - 15 * DAY, now - 3600] + ids)}
        for pid, h in hour.items():
            b = base.get(pid)
            usual = b["n"] / b["hours"] if b and b["hours"] >= 3 else None
            if usual and h["n"] >= 30 and h["n"] >= 4 * usual:
                out.append({"type": "unusual", "severity": "medium", "ts": now, "person_id": pid, "person": h["name"],
                            "title": "Unusual usage",
                            "text": f"{h['name']} made {h['n'] / usual:.0f}× their usual number of AI requests in the last hour "
                                    f"({h['n']} against about {usual:.0f} in a typical active hour).",
                            "tool": h["client"] or None, "href": f"#/activity?tab=timeline&person={pid}",
                            "evidence": "Compared with their own last 14 days of use."})
            elif usual is None and h["n"] >= 60:
                out.append({"type": "unusual", "severity": "low", "ts": now, "person_id": pid, "person": h["name"],
                            "title": "Busy hour", "text": f"{h['name']} made {h['n']} AI requests in the last hour, with too little "
                                                          "history to say what is normal for them.",
                            "tool": h["client"] or None, "href": f"#/activity?tab=timeline&person={pid}",
                            "evidence": "Fewer than 3 active hours of history."})
    return out


def _personal(db, now, since, offset_minutes):
    """Signals against each person's own normal: a new place, a new device, unusual hours, a model new to
    the company, and repeated refusals. Each says what it was compared with. Unusual is not wrong."""
    out = []
    names = {r["id"]: r["name"] for r in db.q("SELECT id, name FROM people")}
    # a new place: where requests came from, against the 30 days before the window
    places, label = {}, {}
    for r in db.q("SELECT person_id, client_ip, MIN(ts) AS first, MAX(id) AS last_id FROM requests WHERE ts >= ? AND ts < ?"
                  " AND person_id IS NOT NULL AND client_ip IS NOT NULL AND client_ip != '' AND outcome = 'ok'"
                  " GROUP BY person_id, client_ip", (since - 30 * DAY, now)):
        key = geo.place_key(r["client_ip"], db)
        label.setdefault(key, geo.label(r["client_ip"], db))
        seen = places.setdefault(r["person_id"], {})
        if key not in seen or r["first"] < seen[key][0]:
            seen[key] = (r["first"], r["client_ip"], r["last_id"])
    for pid, seen in places.items():
        before = {k for k, v in seen.items() if v[0] < since}
        if not before:
            continue  # no history to compare with: everything would look new
        for key, (first, ip, rid) in seen.items():
            if first >= since:
                usual = ", ".join(sorted(label[k] for k in before))[:200]
                out.append({"type": "new_place", "severity": "low", "ts": first, "person_id": pid, "person": names.get(pid),
                            "title": "Used from a new place",
                            "text": f"{names.get(pid) or 'Someone'} sent AI requests from {label[key]} for the first time in 30 days; "
                                    f"before that, from {usual}.",
                            "ip": ip, "place": label[key], "href": f"#/records/{rid}",
                            "evidence": "Places come from named networks, else the location table (approximate), else the address "
                                        "type. Mobile data and VPNs change places often."})
    # a new device: a key's first request, for someone who already used another
    for r in db.q("SELECT k.id, k.label, k.person_id, MIN(r.ts) AS first FROM requests r JOIN keys k ON k.id = r.key_id"
                  " WHERE r.ts >= ? GROUP BY k.id HAVING first >= ?", (since - 30 * DAY, since)):
        others = db.scalar("SELECT COUNT(DISTINCT key_id) FROM requests WHERE person_id = ? AND key_id IS NOT NULL AND key_id != ?"
                           " AND ts < ?", (r["person_id"], r["id"], r["first"])) or 0
        if others:
            out.append({"type": "new_device", "severity": "info", "ts": r["first"], "person_id": r["person_id"],
                        "person": names.get(r["person_id"]), "title": "A new device started using AI",
                        "text": f"{r['label']} made its first request; {names.get(r['person_id']) or 'they'} already used "
                                f"{others} other device{'s' if others != 1 else ''}.",
                        "device": r["label"], "href": f"#/devices/{r['id']}", "evidence": "From the key's first recorded request."})
    # unusual hours: against the hours this person usually works, in gateway time
    shift = offset_minutes * 60
    window = {}
    for r in db.q("SELECT person_id, CAST(((ts + ?) % 86400) / 3600 AS INTEGER) AS hour, COUNT(*) AS n, MAX(id) AS last_id"
                  " FROM requests WHERE ts >= ? AND person_id IS NOT NULL AND outcome = 'ok' AND kind NOT IN ('other', 'media-status')"
                  " GROUP BY person_id, hour", (shift, since)):
        window.setdefault(r["person_id"], []).append(r)
    for pid, hours in window.items():
        base = {r["hour"]: r["n"] for r in db.q(
            "SELECT CAST(((ts + ?) % 86400) / 3600 AS INTEGER) AS hour, COUNT(*) AS n FROM requests WHERE person_id = ? AND ts >= ?"
            " AND ts < ? AND outcome = 'ok' AND kind NOT IN ('other', 'media-status') GROUP BY hour", (shift, pid, since - 30 * DAY, since))}
        total = sum(base.values())
        days_seen = db.scalar("SELECT COUNT(DISTINCT CAST((ts + ?) / 86400 AS INTEGER)) FROM requests WHERE person_id = ? AND ts >= ?"
                              " AND ts < ?", (shift, pid, since - 30 * DAY, since)) or 0
        if total < 50 or days_seen < 5:
            continue
        odd = [h for h in hours if base.get(h["hour"], 0) / total < 0.01]
        n = sum(h["n"] for h in odd)
        if n >= 5:
            usual = sorted(h for h, c in base.items() if c / total >= 0.02)
            span = f"{usual[0]:02d}:00–{usual[-1] + 1:02d}:00" if usual else "no clear pattern"
            out.append({"type": "off_hours", "severity": "low", "ts": now, "person_id": pid, "person": names.get(pid),
                        "title": "Used at unusual hours",
                        "text": f"{names.get(pid) or 'Someone'} made {n} requests at " + ", ".join(f"{h['hour']:02d}:00" for h in sorted(odd, key=lambda h: h["hour"]))
                                + f", hours they rarely use; they usually work {span}.",
                        "href": f"#/records/{max(h['last_id'] for h in odd)}",
                        "evidence": f"Compared with their own previous 30 days ({total} requests on {days_seen} days), in gateway time."})
    # a model new to the company
    for r in db.q("SELECT model, MIN(ts) AS first, MIN(id) AS id, COUNT(DISTINCT person_id) AS people FROM requests WHERE ts >= ?"
                  " AND outcome = 'ok' AND model IS NOT NULL AND model != '' AND kind IN ('messages', 'chat', 'responses', 'completions')"
                  " GROUP BY model", (since,)):
        if not db.one("SELECT 1 FROM requests WHERE model = ? AND ts < ? AND ts >= ? LIMIT 1", (r["model"], since, since - 90 * DAY)) \
                and db.one("SELECT 1 FROM requests WHERE ts < ? LIMIT 1", (since,)):
            out.append({"type": "new_model", "severity": "info", "ts": r["first"], "title": "A model new to Swangz",
                        "text": f"{r['model']} was used for the first time in 90 days, by {r['people']} "
                                f"{'person' if r['people'] == 1 else 'people'}. Check it is approved in the model registry.",
                        "href": f"#/records/{r['id']}", "evidence": "No earlier request named this model in the last 90 days."})
    # repeated refusals in the last day, across every channel
    since_day = now - DAY
    refused = {}
    for table, ts, cond in (("requests", "ts", "outcome = 'blocked' AND (reason IS NULL OR reason != 'secret in prompt')"),
                            ("launches", "ts", "outcome != 'opened'"), ("site_usage", "started", "outcome = 'blocked'")):
        for r in db.q(f"SELECT person_id, COUNT(*) AS n FROM {table} WHERE {ts} >= ? AND person_id IS NOT NULL AND {cond}"
                      " GROUP BY person_id", (since_day,)):
            refused.setdefault(r["person_id"], {})[table] = r["n"]
    for pid, by in refused.items():
        n = sum(by.values())
        if n >= 10:
            out.append({"type": "denials", "severity": "medium" if n >= 30 else "low", "ts": now, "person_id": pid, "person": names.get(pid),
                        "title": "Refused again and again",
                        "text": f"{names.get(pid) or 'Someone'} was refused {n} times in 24 hours ({by.get('requests', 0)} requests, "
                                f"{by.get('launches', 0)} opens, {by.get('site_usage', 0)} website visits).",
                        "href": f"#/activity?tab=timeline&person={pid}",
                        "evidence": "Often a tool retrying by itself, or a grant that ended. Worth a word, not a conclusion."})
    return out


def security_events(ctx, days):
    db = ctx.db
    now = time.time()
    since = now - days * DAY
    events = []
    for r in db.q("SELECT r.id, r.ts, r.person_id, p.name AS person, r.client, r.model, r.flags, r.outcome, k.label AS device"
                  " FROM requests r LEFT JOIN people p ON p.id = r.person_id LEFT JOIN keys k ON k.id = r.key_id"
                  " WHERE r.ts >= ? AND r.flags LIKE '%secret:%' ORDER BY r.id DESC LIMIT 200", (since,)):
        kinds = [f[7:] for f in r["flags"].split(",") if f.startswith("secret:")]
        refused = r["outcome"] == "blocked"
        events.append({"type": "credential", "severity": "medium", "ts": r["ts"], "person_id": r["person_id"],
                       "person": r["person"], "title": "Credential detected in a request",
                       "text": f"A request contained what looks like {_a(' and '.join(kinds)) if kinds else 'a credential'}. "
                               + ("It was refused, so it never reached the provider." if refused
                                  else "It went through and was flagged — the key may be worth rotating."),
                       "tool": r["client"] or None, "device": r["device"], "href": f"#/records/{r['id']}",
                       "evidence": "Pattern match on the text sent; it can be a test or example key."})
    for r in db.q("SELECT client_ip, COUNT(*) AS n, MAX(ts) AS last, MAX(client) AS client FROM requests"
                  " WHERE ts >= ? AND outcome = 'denied' GROUP BY client_ip ORDER BY last DESC LIMIT 50", (since,)):
        events.append({"type": "wrong_key", "severity": "medium" if r["n"] >= 5 else "low", "ts": r["last"],
                       "title": "Requests with an unknown or revoked key",
                       "text": f"{r['n']} request{'s' if r['n'] != 1 else ''} from {r['client_ip'] or 'an unknown address'} "
                               f"used a key the gateway doesn't recognise, and {'was' if r['n'] == 1 else 'were'} refused.",
                       "tool": r["client"] or None, "ip": r["client_ip"] or None, "place": ip_kind(r["client_ip"]),
                       "href": "#/activity?tab=ai&outcome=denied",
                       "evidence": "Often an old key left in a config file after it was revoked."})
    for r in db.q("SELECT r.person_id, p.name AS person, r.reason, COUNT(*) AS n, MAX(r.ts) AS last, MAX(r.id) AS id"
                  " FROM requests r LEFT JOIN people p ON p.id = r.person_id WHERE r.ts >= ? AND r.outcome = 'blocked'"
                  " AND (r.reason IS NULL OR r.reason != 'secret in prompt') GROUP BY r.person_id, r.reason"
                  " ORDER BY last DESC LIMIT 50", (since,)):
        events.append({"type": "blocked", "severity": "low", "ts": r["last"], "person_id": r["person_id"], "person": r["person"],
                       "title": "Request refused by a rule",
                       "text": f"{r['n']} request{'s' if r['n'] != 1 else ''} refused: {r['reason'] or 'a gateway rule'}.",
                       "href": f"#/records/{r['id']}", "evidence": "The gateway's own rules (model, budget, rate limit, pause)."})
    for r in db.q("SELECT l.person_id, p.name AS person, t.name AS tool, COUNT(*) AS n, MAX(l.ts) AS last FROM launches l"
                  " LEFT JOIN people p ON p.id = l.person_id LEFT JOIN tools t ON t.id = l.tool_id"
                  " WHERE l.ts >= ? AND l.outcome != 'opened' GROUP BY l.person_id, l.tool_id ORDER BY last DESC LIMIT 50", (since,)):
        events.append({"type": "denied_open", "severity": "low", "ts": r["last"], "person_id": r["person_id"],
                       "person": r["person"], "title": "Tool opened without access",
                       "text": f"{r['person'] or 'Someone'} tried to open {r['tool'] or 'a removed tool'} from the portal "
                               f"{'once' if r['n'] == 1 else str(r['n']) + ' times'} while it wasn't enabled for them.",
                       "tool": r["tool"], "href": f"#/activity?tab=opens&person={r['person_id'] or ''}",
                       "evidence": "Usually an old bookmark, or a grant that ended."})
    for r in db.q("SELECT su.person_id, p.name AS person, t.name AS tool, su.host, COUNT(*) AS n, MAX(su.started) AS last"
                  " FROM site_usage su LEFT JOIN people p ON p.id = su.person_id LEFT JOIN tools t ON t.id = su.tool_id"
                  " WHERE su.started >= ? AND su.outcome = 'blocked' GROUP BY su.person_id, su.tool_id ORDER BY last DESC LIMIT 50",
                  (since,)):
        events.append({"type": "site_blocked", "severity": "low", "ts": r["last"], "person_id": r["person_id"],
                       "person": r["person"], "title": "AI website blocked",
                       "text": f"The browser gate blocked {r['tool'] or r['host']} for {r['person'] or 'someone'} "
                               f"{'once' if r['n'] == 1 else str(r['n']) + ' times'}.",
                       "tool": r["tool"] or r["host"], "href": "#/activity?tab=sites",
                       "evidence": "Recorded by the browser extension: the site and the time, nothing on the page."})
    for r in db.q("SELECT ip, COUNT(*) AS n, MAX(ts) AS last, GROUP_CONCAT(DISTINCT actor) AS names FROM audit"
                  " WHERE ts >= ? AND action = 'failed sign-in' GROUP BY ip ORDER BY last DESC LIMIT 30", (since,)):
        events.append({"type": "signin", "severity": "medium" if r["n"] >= 5 else "low", "ts": r["last"],
                       "title": "Failed console sign-ins",
                       "text": f"{r['n']} failed sign-in{'s' if r['n'] != 1 else ''} to the control room from "
                               f"{r['ip'] or 'an unknown address'} (usernames tried: {r['names'] or '—'}).",
                       "ip": r["ip"] or None, "place": ip_kind(r["ip"]), "href": "#/audit?q=failed%20sign-in",
                       "evidence": "Sign-in is throttled after repeated failures from one address."})
    for r in db.q("SELECT k.id, k.label, k.revoked, k.revoked_by, p.name AS person, k.person_id FROM keys k"
                  " JOIN people p ON p.id = k.person_id WHERE k.revoked >= ? ORDER BY k.revoked DESC LIMIT 50", (since,)):
        by_self = r["revoked_by"] == "self"
        events.append({"type": "revoked", "severity": "info", "ts": r["revoked"], "person_id": r["person_id"],
                       "person": r["person"], "title": "Key revoked",
                       "text": f"{r['label']} ({r['person']}) was disconnected "
                               + ("by them in the staff app." if by_self else f"by {r['revoked_by'] or 'an admin'}."),
                       "device": r["label"], "href": f"#/devices/{r['id']}", "evidence": "From the key's own record."})
    for r in db.q("SELECT ts, actor, target FROM audit WHERE ts >= ? AND action = 'suspended a person' ORDER BY id DESC LIMIT 20",
                  (since,)):
        events.append({"type": "suspended", "severity": "info", "ts": r["ts"], "person": r["target"],
                       "title": "Access suspended", "text": f"{r['actor']} suspended {r['target']}.",
                       "href": "#/audit", "evidence": "From the audit log."})
    events += _unusual(db, now)
    events += _personal(db, now, since, ctx.gw.settings.tz_offset_minutes)
    for e in events:
        if e.get("ip") and "place" in e:
            e["location"] = geo.describe(e["ip"], db)
    events.sort(key=lambda e: (-e["ts"]))
    return events


@route("GET", r"/security")
def security_view(ctx):
    """Signals worth a look, each with how sure the evidence is. Severity is about what to check
    first, not a judgement on the person."""
    days = max(1, min(ctx.arg("days", 7, int), 90))
    events = security_events(ctx, days)
    worst = max((SEVERITY[e["severity"]] for e in events), default=0)
    posture = "elevated" if worst >= 3 else "watch" if worst == 2 else "healthy"
    counts = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    st = ctx.db
    return {"days": days, "posture": posture, "events": events[:300], "counts": counts,
            "settings": {"block_secrets": st.get_setting("block_secrets", "0") == "1",
                         "rate_per_min": int(st.get_setting("rate_per_min", "0") or 0),
                         "paused": st.get_setting("paused", "0") == "1"}}


# ---------------------------------------------------------------- what needs attention


@route("GET", r"/attention")
def attention(ctx):
    """Everything an admin should look at, on one list, most urgent first."""
    db = ctx.db
    now = time.time()
    day, month = proxy.period_starts(now, ctx.gw.settings.tz_offset_minutes)
    items = []

    def add(key, severity, area, title, text, href, count=None):
        items.append({"key": key, "severity": severity, "area": area, "title": title, "text": text, "href": href, "count": count})

    if db.get_setting("paused", "0") == "1":
        add("paused", "high", "Access", "AI access is paused for everyone",
            "Requests and tool launches are refused until an owner resumes access.", "#/settings")
    sec = security_events(ctx, 7)
    for kind, title, href in (("credential", "Credentials detected in requests", "#/security"),
                              ("unusual", "Unusual usage", "#/security"),
                              ("wrong_key", "Requests with unknown keys", "#/security"),
                              ("signin", "Failed console sign-ins", "#/security"),
                              ("denials", "Repeated refusals", "#/security"),
                              ("new_place", "Used from a new place", "#/security"),
                              ("off_hours", "Used at unusual hours", "#/security")):
        hits = [e for e in sec if e["type"] == kind]
        if hits:
            worst = max(hits, key=lambda e: SEVERITY[e["severity"]])
            add("sec-" + kind, worst["severity"], "Security", title,
                worst["text"] if len(hits) == 1 else f"{len(hits)} in the last 7 days. Latest: {hits[0]['text']}", href, len(hits))
    errors = db.scalar("SELECT COUNT(*) FROM requests WHERE ts >= ? AND outcome = 'error'", (now - DAY,)) or 0
    if errors:
        add("errors", "low", "Reliability", f"{errors} failed request{'s' if errors != 1 else ''} in the last 24 hours",
            "The provider returned an error or couldn't be reached.", "#/activity?tab=ai&outcome=error", errors)
    for p in db.q("SELECT p.id, p.name, p.daily_budget, p.monthly_budget,"
                  " (SELECT COALESCE(SUM(cost), 0) FROM requests WHERE person_id = p.id AND ts >= ?) AS today,"
                  " (SELECT COALESCE(SUM(cost), 0) FROM requests WHERE person_id = p.id AND ts >= ?) AS month"
                  " FROM people p WHERE p.status = 'active' AND (p.daily_budget IS NOT NULL OR p.monthly_budget IS NOT NULL)",
                  (day, month)):
        for spent, limit, period in ((p["today"], p["daily_budget"], "daily"), (p["month"], p["monthly_budget"], "monthly")):
            if limit is None:
                continue
            if spent >= limit:
                add(f"budget-{p['id']}-{period}", "medium", "Spend", f"{p['name']} has reached their {period} budget",
                    f"${spent:,.2f} of ${limit:,.2f}. New requests are refused until it resets or the budget is raised.",
                    f"#/people/{p['id']}")
            elif limit and spent >= 0.8 * limit:
                add(f"budget-{p['id']}-{period}", "low", "Spend", f"{p['name']} is near their {period} budget",
                    f"${spent:,.2f} of ${limit:,.2f} used.", f"#/people/{p['id']}")
    lic = licence_data(db, ctx.gw.settings)
    for t in lic["tools"]:
        if t["over_seats"]:
            add(f"seats-{t['id']}", "medium", "Licences", f"{t['name']}: more people than paid seats",
                f"{t['assigned']} people hold it; the plan pays for {t['seats']}.", f"#/tools?open={t['id']}&tab=access")
    if lic["summary"]["idle_seats"]:
        add("idle", "low", "Licences", f"{lic['summary']['idle_seats']} seats unused for 30 days",
            (f"About ${lic['summary']['idle_cost']:,.2f} a month is paying for seats nobody opens." if lic["summary"]["idle_cost"]
             else "Given to people who haven't used them in 30 days.") + " Reclaim them on the Licences page.",
            "#/licences", lic["summary"]["idle_seats"])
    for t in lic["renewals"]:
        if t["renews_on"] <= now + 14 * DAY:
            add(f"renew-{t['id']}", "low", "Licences", f"{t['name']} renews {time.strftime('%d %b', time.gmtime(t['renews_on']))}",
                f"{'$%s a month' % format(t['monthly_cost'], ',.2f') if t['monthly_cost'] else 'Cost not set'} — check it's still needed.",
                f"#/tools?open={t['id']}&tab=billing")
    for t in db.q("SELECT * FROM tools WHERE signin = 'shared' AND archived = 0"):
        held = turns.holders(db, t["id"])
        if held and len(held) >= turns.seats(t):
            add(f"full-{t['id']}", "info", "Workspace", f"{t['name']}'s shared account is fully in use",
                f"{len(held)} of {turns.seats(t)} at once — others are turned away until a turn ends.",
                f"#/tools?open={t['id']}&tab=access")
    # company browsers on one of Swangz's own computers: while it is offline, nobody on a shared tool gets one
    if db.scalar("SELECT COUNT(*) FROM tools WHERE signin = 'shared' AND workspace_mode = 'agent' AND archived = 0"):
        for h in ctx.gw.workspaces.hosts():
            if h["active"] and h["kind"] == "computer" and not h.get("online"):
                add("ws-offline", "high" if h.get("set_up") else "medium", "Workspace",
                    f"{h['label'][:1].upper() + h['label'][1:]} isn't online",
                    "The company browsers are set to run there, so Open can't give anyone one until it checks in again — "
                    "or switch back to the rented server.", "#/settings?tab=browsers")
    opened = db.scalar("SELECT COUNT(*) FROM access_requests WHERE state = 'open'") or 0
    if opened:
        add("requests", "info", "Access", f"{opened} tool request{'s' if opened != 1 else ''} waiting",
            "Staff asked for tools; grant or decline them.", "#/requests", opened)
    ending = db.q("SELECT id, name, access_until FROM people WHERE status = 'active' AND access_until > ? AND access_until <= ?"
                  " ORDER BY access_until", (now, now + 7 * DAY))
    for p in ending:
        add(f"ending-{p['id']}", "info", "Access", f"{p['name']}'s access ends soon",
            f"Their account stops working after {time.strftime('%d %b', time.gmtime(p['access_until'] - DAY))}.", f"#/people/{p['id']}")
    missing = [p for p in ctx.gw.settings.providers.values() if not p.api_key()]
    if missing:
        add("providers", "info", "System", "Providers without a company key",
            ", ".join(p.label or p.name for p in missing) + " — staff tools pointed at these are refused.", "#/settings?tab=addresses",
            len(missing))
    from .admin import _totals  # the same unpriced count the Live page shows
    unpriced = _totals(db, month)["unpriced"]
    if unpriced:
        add("unpriced", "low", "Spend", f"{unpriced} request{'s' if unpriced != 1 else ''} this month have no price",
            "Their model isn't in the price table, so spend is understated.", "#/settings?tab=prices", unpriced)
    items.sort(key=lambda i: -SEVERITY[i["severity"]])
    return {"items": items, "counts": {s: sum(1 for i in items if i["severity"] == s) for s in SEVERITY}}


# ---------------------------------------------------------------- search everything


@route("GET", r"/search")
def search(ctx):
    """The command menu's search: people, tools, devices, requests, sessions and the audit log."""
    db = ctx.db
    q = (ctx.arg("q") or "").strip()[:100]
    if not q:
        return {"groups": []}
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    groups = []

    def group(name, rows):
        if rows:
            groups.append({"group": name, "items": rows})

    if len(q) >= 2:
        group("People", [{"title": r["name"], "sub": " · ".join(x for x in (r["title"], r["department"], r["email"]) if x)
                          or "No details", "href": f"#/people/{r['id']}", "status": r["status"]}
                         for r in db.q("SELECT id, name, title, department, email, status FROM people WHERE name LIKE ?"
                                       " OR email LIKE ? OR department LIKE ? ORDER BY name COLLATE NOCASE LIMIT 6",
                                       (like, like, like))])
        group("Tools", [{"title": r["name"], "sub": r["category"] + (" · removed" if r["archived"] else ""),
                         "href": f"#/tools?open={r['id']}", "tool_id": r["id"]}
                        for r in db.q("SELECT id, name, category, archived FROM tools WHERE name LIKE ? OR category LIKE ?"
                                      " ORDER BY archived, name LIMIT 6", (like, like))])
        group("Devices", [{"title": r["label"], "sub": f"{r['name']} · {r['hint']}" + (" · revoked" if r["revoked"] else ""),
                           "href": f"#/devices/{r['id']}"}
                          for r in db.q("SELECT k.id, k.label, k.hint, k.revoked, p.name FROM keys k JOIN people p"
                                        " ON p.id = k.person_id WHERE k.label LIKE ? OR k.hint LIKE ? OR k.id LIKE ?"
                                        " ORDER BY k.revoked IS NOT NULL, k.last_used DESC LIMIT 6", (like, like, like))])
    found = []
    m = re.fullmatch(r"#?(\d{1,12})", q)
    if m:
        r = db.one("SELECT r.id, r.ts, r.client, r.model, p.name FROM requests r LEFT JOIN people p ON p.id = r.person_id"
                   " WHERE r.id = ?", (int(m.group(1)),))
        if r:
            found.append({"title": f"Request #{r['id']}", "sub": " · ".join(x for x in (r["name"], r["client"], r["model"]) if x),
                          "href": f"#/records/{r['id']}", "ts": r["ts"]})
    if len(q) >= 3:
        found += [{"title": (r["prompt"] or "")[:90], "sub": " · ".join(x for x in (r["name"], r["client"]) if x),
                   "href": f"#/records/{r['id']}", "ts": r["ts"]}
                  for r in db.q("SELECT r.id, r.ts, r.prompt, r.client, p.name FROM requests r LEFT JOIN people p"
                                " ON p.id = r.person_id WHERE r.ts >= ? AND r.prompt LIKE ? ORDER BY r.id DESC LIMIT 5",
                                (time.time() - 90 * DAY, like))]
    group("Requests", found)
    if len(q) >= 6:
        group("Sessions", [{"title": r["session"][:40], "sub": " · ".join(x for x in (r["name"], r["client"]) if x),
                            "href": f"#/sessions/{r['session']}", "ts": r["last"]}
                           for r in db.q("SELECT r.session, MAX(r.ts) AS last, MAX(r.client) AS client, MAX(p.name) AS name"
                                         " FROM requests r LEFT JOIN people p ON p.id = r.person_id WHERE r.session LIKE ?"
                                         " GROUP BY r.session ORDER BY last DESC LIMIT 4", (q.replace("%", "") + "%",))])
    if len(q) >= 3:
        group("Audit", [{"title": f"{r['actor']} {r['action']}", "sub": r["target"] or r["detail"] or "",
                         "href": "#/audit?q=" + re.sub(r"[^\w@. -]", "", q)[:60], "ts": r["ts"]}
                        for r in db.q("SELECT ts, actor, action, target, detail FROM audit WHERE action LIKE ? OR target LIKE ?"
                                      " OR actor LIKE ? ORDER BY id DESC LIMIT 4", (like, like, like))])
    return {"groups": groups}
