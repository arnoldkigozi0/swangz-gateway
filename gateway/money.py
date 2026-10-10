"""The Money area: what voice, image and video work costs, and reports.

Media rates are dated. A rate applies to requests made on or after its effective date; adding a new rate
never changes a cost already recorded, because each request stores its cost and the rate it came from
(`requests.cost_source = "rate:<id>@<effective>"`). Every amount the console shows says which kind it is:
*estimated* (from the price table or a media rate), *unpriced* (no price or rate for it yet), or
*allocated* (a share of a fixed plan). Vendor invoices are not imported, so nothing here is *actual*.
"""

import csv
import fnmatch
import io
import json
import time

from . import proxy
from .admin import ApiError, route

UNITS = ("character", "request", "image", "video", "second", "minute", "credit")


def unit_key(unit):
    u = (unit or "").strip().lower()
    return u[:-1] if u.endswith("s") and u[:-1] in UNITS else u


def find_rate(db, provider, unit, service, ts):
    """The rate in force at `ts` for this provider and unit: the most specific service pattern first,
    then the most recent effective date."""
    best = None
    for r in db.q("SELECT * FROM media_rates WHERE provider = ? AND effective <= ? ORDER BY effective DESC, id DESC", (provider, ts)):
        if unit_key(r["unit"]) != unit_key(unit):
            continue
        pattern = r["service"] or "*"
        if pattern != "*" and not any(fnmatch.fnmatchcase((s or "").lower(), pattern.lower()) for s in service):
            continue
        rank = (pattern != "*", r["effective"])
        if best is None or rank > best[0]:
            best = (rank, r)
    return best[1] if best else None


def media_cost(db, rec):
    """(cost in USD, cost_source) for a finished voice/image/video request, or (None, None) when no rate fits."""
    rate = find_rate(db, rec["provider"], rec.get("unit"), (rec.get("model"), rec.get("media_type")), rec.get("ts") or time.time())
    if not rate:
        return None, None
    return round(float(rec.get("units") or 0) * rate["usd_per_unit"], 6), f"rate:{rate['id']}@{int(rate['effective'])}"


def describe_source(db, source):
    """What a stored cost_source means, for the record page: 'Estimated from the price for claude-… set 1 Oct 2026'."""
    if not source:
        return None
    kind, _, rest = source.partition(":")
    ref, _, when = rest.partition("@")
    try:
        when = float(when)
    except ValueError:
        when = None
    if kind == "price":
        return {"basis": "estimated", "from": "price table", "ref": ref, "as_of": when}
    if kind == "rate":
        row = db.one("SELECT provider, service, unit, usd_per_unit FROM media_rates WHERE id = ?", (int(ref) if ref.isdigit() else -1,))
        return {"basis": "estimated", "from": "media rate", "ref": ref, "as_of": when, "rate": row}
    return {"basis": "estimated", "from": kind, "ref": ref, "as_of": when}


# ---------------------------------------------------------------- media rates


@route("GET", r"/media-rates")
def list_media_rates(ctx):
    rows = ctx.db.q("SELECT * FROM media_rates ORDER BY provider, service, unit, effective DESC")
    now = time.time()
    current = set()
    for r in rows:
        key = (r["provider"], r["service"], unit_key(r["unit"]))
        if r["effective"] <= now and key not in current:
            current.add(key)
            r["current"] = True
        else:
            r["current"] = False
            r["scheduled"] = r["effective"] > now
    unpriced = ctx.db.q(
        "SELECT provider, media_type, unit, COUNT(*) AS requests, SUM(units) AS units FROM requests"
        " WHERE kind = 'media' AND outcome = 'ok' AND cost IS NULL AND ts >= ? GROUP BY provider, media_type, unit"
        " ORDER BY requests DESC", (now - 30 * 86400,))
    return {"items": rows, "units": UNITS, "unpriced": unpriced,
            "providers": [{"name": p.name, "label": p.label} for p in ctx.gw.settings.providers.values() if not p.is_chat]}


@route("POST", r"/media-rates", area="money")
def add_media_rate(ctx):
    b = ctx.body
    provider = str(b.get("provider") or "").strip()
    if provider not in ctx.gw.settings.providers:
        raise ApiError(400, "pick one of the gateway's providers")
    unit = unit_key(b.get("unit"))
    if unit not in UNITS:
        raise ApiError(400, "unit must be one of: " + ", ".join(UNITS))
    try:
        usd = float(b.get("usd_per_unit"))
    except (TypeError, ValueError):
        raise ApiError(400, "usd_per_unit must be a number of dollars")
    if usd < 0:
        raise ApiError(400, "a rate cannot be negative")
    service = str(b.get("service") or "*").strip()[:80] or "*"
    effective = b.get("effective")
    if effective:
        from .admin import _date_to_ts

        effective = _date_to_ts(effective)
    else:
        effective = time.time()
    rid = ctx.db.x("INSERT INTO media_rates(provider, service, unit, usd_per_unit, effective, note, created, created_by) VALUES(?,?,?,?,?,?,?,?)",
                   (provider, service, unit, usd, effective, str(b.get("note") or "")[:200], time.time(), ctx.admin["username"])).lastrowid
    ctx.audit("set a media rate", f"{provider} · {service}", f"${usd} per {unit} from {time.strftime('%Y-%m-%d', time.gmtime(effective))}",
              after={"provider": provider, "service": service, "unit": unit, "usd_per_unit": usd, "effective": effective},
              correlation=f"media-rate:{rid}")
    return {"ok": True, "id": rid}


@route("DELETE", r"/media-rates/(?P<rid>\d+)", area="money")
def remove_media_rate(ctx, rid):
    row = ctx.db.one("SELECT * FROM media_rates WHERE id = ?", (int(rid),))
    if not row:
        raise ApiError(404, "no such rate")
    used = ctx.db.scalar("SELECT COUNT(*) FROM requests WHERE cost_source LIKE ?", (f"rate:{row['id']}@%",)) or 0
    if used:
        raise ApiError(400, f"{used} recorded request(s) were priced with this rate; add a newer rate instead of removing it")
    ctx.db.x("DELETE FROM media_rates WHERE id = ?", (row["id"],))
    ctx.audit("removed a media rate", f"{row['provider']} · {row['service']}", before=row, correlation=f"media-rate:{rid}")
    return {"ok": True}


# ---------------------------------------------------------------- reports

REPORTS = {
    "usage": "AI usage by person",
    "spend": "Spend by person",
    "departments": "Usage and spend by department",
    "tools": "Tool usage",
    "models": "Model usage",
    "purposes": "Usage by purpose",
    "licences": "Licences and seats",
    "security": "Security signals",
    "shared": "Shared accounts: who held them",
}


def _range(ctx):
    now = time.time()
    since = ctx.arg("since", cast=float)
    until = ctx.arg("until", cast=float) or now + 1
    if since is None:
        _, month = proxy.period_starts(now, ctx.gw.settings.tz_offset_minutes)
        since = month
    if until <= since:
        raise ApiError(400, "until must be after since")
    return since, until


COUNTED = "r.kind NOT IN ('other', 'media-status')"


def build_report(ctx, kind, since, until):
    db = ctx.db
    notes = ["Costs are estimated from the price table and media rates in force when each request ran; "
             "\"unpriced\" counts requests with no price yet. Vendor invoices are not imported."]
    if kind in ("usage", "spend"):
        cols = [("person", "Person"), ("department", "Department"), ("requests", "Requests"), ("tokens", "Tokens"),
                ("cost", "Estimated cost (USD)"), ("unpriced", "Unpriced requests"), ("refused", "Refused")]
        rows = db.q(
            "SELECT COALESCE(p.name, 'No valid key') AS person, COALESCE(p.department, '') AS department,"
            " SUM(r.outcome = 'ok') AS requests, COALESCE(SUM(r.in_tok + r.out_tok + r.cache_write_tok + r.cache_read_tok), 0) AS tokens,"
            " ROUND(COALESCE(SUM(r.cost), 0), 4) AS cost, SUM(r.cost IS NULL AND r.outcome = 'ok') AS unpriced,"
            " SUM(r.outcome != 'ok') AS refused FROM requests r LEFT JOIN people p ON p.id = r.person_id"
            f" WHERE r.ts >= ? AND r.ts < ? AND {COUNTED} GROUP BY r.person_id ORDER BY " + ("cost DESC" if kind == "spend" else "requests DESC"),
            (since, until))
    elif kind == "departments":
        cols = [("department", "Department"), ("people", "People active"), ("requests", "Requests"), ("cost", "Estimated cost (USD)"),
                ("unpriced", "Unpriced requests")]
        rows = db.q(
            "SELECT COALESCE(NULLIF(p.department, ''), 'No department') AS department, COUNT(DISTINCT r.person_id) AS people,"
            " SUM(r.outcome = 'ok') AS requests, ROUND(COALESCE(SUM(r.cost), 0), 4) AS cost,"
            " SUM(r.cost IS NULL AND r.outcome = 'ok') AS unpriced FROM requests r JOIN people p ON p.id = r.person_id"
            f" WHERE r.ts >= ? AND r.ts < ? AND {COUNTED} GROUP BY department ORDER BY cost DESC", (since, until))
    elif kind == "tools":
        from . import insight

        usage, _ = insight.usage_rows(db, since, until)
        agg = {}
        for u in usage:
            a = agg.setdefault(u["tool"], {"tool": u["tool"], "people": set(), "requests": 0, "opens": 0, "visits": 0, "cost": 0.0, "refused": 0})
            a["people"].add(u["person_id"])
            for k in ("requests", "opens", "visits", "refused"):
                a[k] += u[k]
            a["cost"] += u["cost"]
        rows = sorted(({**a, "people": len(a["people"]), "cost": round(a["cost"], 4)} for a in agg.values()),
                      key=lambda a: -(a["requests"] + a["opens"] + a["visits"]))
        cols = [("tool", "Tool"), ("people", "People"), ("requests", "Requests"), ("opens", "Opened from the portal"),
                ("visits", "Website visits"), ("cost", "Estimated cost (USD)"), ("refused", "Refused")]
    elif kind == "models":
        cols = [("model", "Model"), ("provider", "Provider"), ("requests", "Requests"), ("tokens", "Tokens"),
                ("cost", "Estimated cost (USD)"), ("unpriced", "Unpriced requests"), ("people", "People")]
        rows = db.q(
            "SELECT r.model, r.provider, COUNT(*) AS requests, COALESCE(SUM(r.in_tok + r.out_tok + r.cache_write_tok + r.cache_read_tok), 0) AS tokens,"
            " ROUND(COALESCE(SUM(r.cost), 0), 4) AS cost, SUM(r.cost IS NULL) AS unpriced, COUNT(DISTINCT r.person_id) AS people"
            f" FROM requests r WHERE r.ts >= ? AND r.ts < ? AND {COUNTED} AND r.outcome = 'ok' AND r.model IS NOT NULL"
            " GROUP BY r.model, r.provider ORDER BY cost DESC, requests DESC", (since, until))
    elif kind == "purposes":
        cols = [("purpose", "Purpose"), ("requests", "Requests"), ("declared", "Declared"), ("derived", "Derived from the tool"),
                ("inferred", "Inferred"), ("people", "People"), ("cost", "Estimated cost (USD)")]
        names = {r["id"]: r["name"] for r in db.q("SELECT id, name FROM purposes")}
        rows = db.q(
            "SELECT COALESCE(r.purpose, '') AS purpose, COUNT(*) AS requests, COALESCE(SUM(r.purpose_source = 'declared'), 0) AS declared,"
            " COALESCE(SUM(r.purpose_source = 'derived'), 0) AS derived, COALESCE(SUM(r.purpose_source = 'inferred'), 0) AS inferred,"
            " COUNT(DISTINCT r.person_id) AS people, ROUND(COALESCE(SUM(r.cost), 0), 4) AS cost FROM requests r"
            f" WHERE r.ts >= ? AND r.ts < ? AND {COUNTED} AND r.outcome = 'ok' GROUP BY r.purpose ORDER BY requests DESC", (since, until))
        for r in rows:
            r["purpose"] = names.get(r["purpose"], r["purpose"]) if r["purpose"] else "Unknown"
        notes.append("Declared purposes were stated by the person or their tool; derived ones come from the tool itself; "
                     "inferred ones from keyword rules over the prompt (Settings → Purposes). Unknown means none was strong enough.")
    elif kind == "licences":
        from .admin import licence_data

        lic = licence_data(db, ctx.gw.settings)
        cols = [("tool", "Tool"), ("plan", "Plan"), ("seats", "Seats paid"), ("assigned", "Given out"), ("active", "Active in 30 days"),
                ("idle", "Idle"), ("monthly_cost", "Monthly cost (USD)"), ("cost_per_active", "Per active user (USD)")]
        rows = [{"tool": t["name"], "plan": t.get("plan") or "", "seats": t.get("seats"), "assigned": t["assigned"], "active": t["active"],
                 "idle": len(t["idle"]), "monthly_cost": t.get("monthly_cost"), "cost_per_active": t.get("cost_per_active")}
                for t in lic["tools"]]
        notes = ["Plan costs are what is set on each subscription (allocated, not metered). Active = opened, visited or used through "
                 "the gateway in the last 30 days, whatever the report's range."]
    elif kind == "security":
        from . import insight

        days = max(1, min(90, int((until - since) / 86400) or 1))
        events = insight.security_events(ctx, days)
        cols = [("time", "When"), ("severity", "Severity"), ("type", "Kind"), ("person", "Person"), ("text", "What happened"),
                ("evidence", "Evidence")]
        rows = [{"time": e["ts"], "severity": e["severity"], "type": e["type"], "person": e.get("person") or "",
                 "text": e["text"], "evidence": e.get("evidence") or ""} for e in events if since <= e["ts"] < until]
        notes = ["Signals are things worth a look, each with the evidence behind it. Unusual is not the same as wrong."]
    elif kind == "shared":
        cols = [("tool", "Shared account"), ("person", "Person"), ("turns", "Turns"), ("minutes", "Minutes held"), ("last", "Last turn")]
        rows = db.q(
            "SELECT t.name AS tool, p.name AS person, COUNT(*) AS turns,"
            " ROUND(SUM(MIN(COALESCE(tt.ended, tt.expires), ?) - tt.started) / 60.0, 1) AS minutes, MAX(tt.started) AS last"
            " FROM tool_turns tt JOIN tools t ON t.id = tt.tool_id JOIN people p ON p.id = tt.person_id"
            " WHERE tt.started >= ? AND tt.started < ? GROUP BY tt.tool_id, tt.person_id ORDER BY t.name, minutes DESC",
            (time.time(), since, until))
        notes = ["A turn is the time a person held the shared account. Match a vendor's usage history to these intervals to put a name on it."]
    else:
        raise ApiError(404, "no such report")
    return {"kind": kind, "title": REPORTS[kind], "since": since, "until": until, "generated": time.time(),
            "columns": [{"key": k, "label": label} for k, label in cols], "rows": rows, "notes": notes}


@route("GET", r"/reports")
def list_reports(ctx):
    return {"items": [{"kind": k, "title": v} for k, v in REPORTS.items()]}


@route("GET", r"/reports/(?P<kind>[a-z]+)")
def report(ctx, kind):
    if kind not in REPORTS:
        raise ApiError(404, "no such report")
    since, until = _range(ctx)
    data = build_report(ctx, kind, since, until)
    if ctx.arg("format") != "csv":
        return data
    from .admin import _csv_safe

    offset = ctx.gw.settings.tz_offset_minutes * 60
    stamp = lambda ts: time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts + offset))  # noqa: E731
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Swangz AI Hub report: {data['title']}"])
    w.writerow([f"Range: {stamp(since)} to {stamp(until)} (gateway time, UTC{'+' if offset >= 0 else '-'}{abs(offset) // 3600:02d}:{abs(offset) % 3600 // 60:02d})"])
    w.writerow([f"Generated: {stamp(data['generated'])} by {ctx.admin['username']}"])
    for note in data["notes"]:
        w.writerow([note])
    w.writerow([])
    w.writerow([c["label"] for c in data["columns"]])
    for r in data["rows"]:
        out = []
        for c in data["columns"]:
            v = r.get(c["key"])
            if c["key"] in ("time", "last") and isinstance(v, (int, float)):
                v = stamp(v)
            out.append(_csv_safe(str(v)) if isinstance(v, str) else ("" if v is None else v))
        w.writerow(out)
    ctx.audit("exported a report", data["title"], f"{len(data['rows'])} rows, {stamp(since)} to {stamp(until)}",
              correlation=f"report:{kind}")
    return (buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
            {"Content-Disposition": f'attachment; filename="swangz-ai-{kind}-report.csv"', "Cache-Control": "no-store"})
