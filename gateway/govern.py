"""The Govern area's API: the purpose taxonomy, the model registry and company policies — and the
read-only tools that show what a change would do before anyone makes it (the policy, revoke and seat
simulators) and why something is allowed or refused right now (explain).

Reading is open to every console user. Changing needs the govern area (gateway/authz.py), and every
change is audited with what it was before and after. The simulators and explain never change anything.
"""

import re
import time

from . import entitle, insight, policy, proxy, purpose, turns
from .admin import ApiError, route

DAY = 86400
MODEL_STATUSES = ("approved", "experimental", "restricted", "deprecated", "disabled")
REPLAY_LIMIT = 200000  # the most events one simulation replays; it says so when it stops early


def _clock(settings, ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts + settings.tz_offset_minutes * 60))


# ---------------------------------------------------------------- purposes


@route("GET", r"/purposes")
def list_purposes(ctx):
    since = time.time() - 30 * DAY
    usage = {r["purpose"]: r for r in ctx.db.q(
        "SELECT purpose, COUNT(*) AS requests, SUM(purpose_source = 'declared') AS declared,"
        " SUM(purpose_source = 'derived') AS derived, SUM(purpose_source = 'inferred') AS inferred,"
        " COUNT(DISTINCT person_id) AS people FROM requests WHERE ts >= ? AND purpose IS NOT NULL GROUP BY purpose", (since,))}
    unknown = ctx.db.scalar("SELECT COUNT(*) FROM requests WHERE ts >= ? AND purpose IS NULL AND outcome = 'ok'"
                            " AND kind NOT IN ('other', 'media-status')", (since,)) or 0
    items = []
    for r in ctx.db.q("SELECT * FROM purposes ORDER BY archived, sort, name"):
        u = usage.get(r["id"]) or {}
        items.append({**r, "keywords": [k for k in (r["keywords"] or "").split(",") if k],
                      **{k: u.get(k) or 0 for k in ("requests", "declared", "derived", "inferred", "people")}})
    return {"items": items, "unknown_30d": unknown,
            "inference": ctx.db.get_setting("purpose_inference", "1") == "1",
            "thresholds": {"strong": purpose.MIN_STRONG, "shown": purpose.MIN_SHOWN}}


def _purpose_values(body, partial):
    out = {}
    if "name" in body or not partial:
        name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()[:60]
        if not name:
            raise ApiError(400, "give the purpose a name")
        out["name"] = name
    if "description" in body:
        out["description"] = str(body.get("description") or "").strip()[:200]
    if "keywords" in body:
        raw = body["keywords"]
        raw = raw.split(",") if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
        words = []
        for w in raw:
            w = re.sub(r"\s+", " ", str(w)).strip().lower()[:40]
            if w and w not in words:
                words.append(w)
        if len(words) > 80:
            raise ApiError(400, "keep a purpose to 80 keywords or fewer")
        out["keywords"] = ",".join(words)
    if "archived" in body:
        out["archived"] = 1 if body["archived"] else 0
    if "sort" in body:
        try:
            out["sort"] = int(body["sort"])
        except (TypeError, ValueError):
            raise ApiError(400, "sort must be a whole number")
    return out


def _name_taken(db, name, but=None):
    row = db.one("SELECT id FROM purposes WHERE LOWER(name) = LOWER(?)", (name,))
    return bool(row) and row["id"] != but


@route("POST", r"/purposes", area="govern")
def add_purpose(ctx):
    values = _purpose_values(ctx.body, partial=False)
    pid = re.sub(r"[^a-z0-9]+", "-", values["name"].lower()).strip("-")[:40] or "purpose"
    if ctx.db.one("SELECT 1 FROM purposes WHERE id = ?", (pid,)) or _name_taken(ctx.db, values["name"]):
        raise ApiError(400, "there is already a purpose with that name")
    sort = (ctx.db.scalar("SELECT MAX(sort) FROM purposes") or 0) + 1
    ctx.db.x("INSERT INTO purposes(id, name, description, keywords, sort, builtin, updated) VALUES(?,?,?,?,?,0,?)",
             (pid, values["name"], values.get("description", ""), values.get("keywords", ""), values.get("sort", sort), time.time()))
    purpose.invalidate(ctx.db)
    ctx.audit("added a purpose", values["name"], after=values, correlation=f"purpose:{pid}")
    return {"ok": True, "id": pid}


@route("PUT", r"/purposes/(?P<pid>[a-z0-9-]{1,40})", area="govern")
def edit_purpose(ctx, pid):
    row = ctx.db.one("SELECT * FROM purposes WHERE id = ?", (pid,))
    if not row:
        raise ApiError(404, "no such purpose")
    values = _purpose_values(ctx.body, partial=True)
    if "name" in values and _name_taken(ctx.db, values["name"], but=pid):
        raise ApiError(400, "there is already a purpose with that name")
    changed = {k: v for k, v in values.items() if row.get(k) != v}
    if changed:
        ctx.db.x(f"UPDATE purposes SET {', '.join(f'{k} = ?' for k in changed)}, updated = ? WHERE id = ?",
                 [*changed.values(), time.time(), pid])
        purpose.invalidate(ctx.db)
        ctx.audit("changed a purpose", row["name"], ", ".join(sorted(changed)), before={k: row[k] for k in changed},
                  after=changed, correlation=f"purpose:{pid}")
    return {"ok": True}


@route("DELETE", r"/purposes/(?P<pid>[a-z0-9-]{1,40})", area="govern")
def remove_purpose(ctx, pid):
    row = ctx.db.one("SELECT * FROM purposes WHERE id = ?", (pid,))
    if not row:
        raise ApiError(404, "no such purpose")
    if row["builtin"]:
        raise ApiError(400, "built-in purposes can be archived, not deleted")
    used = ctx.db.scalar("SELECT COUNT(*) FROM requests WHERE purpose = ?", (pid,)) or 0
    if used:
        raise ApiError(400, f"{used} recorded request(s) carry this purpose; archive it instead")
    ctx.db.x("DELETE FROM purposes WHERE id = ?", (pid,))
    purpose.invalidate(ctx.db)
    ctx.audit("removed a purpose", row["name"], before=row, correlation=f"purpose:{pid}")
    return {"ok": True}


@route("POST", r"/purposes/test")
def test_purpose(ctx):
    """Try the keyword rules on a sample text. Nothing is stored."""
    text = str(ctx.body.get("text") or "")[:purpose.SCAN_CHARS]
    tx = purpose.taxonomy(ctx.db)
    pid, confidence, words = purpose.infer(tx, text)
    shown = bool(pid) and confidence >= purpose.MIN_SHOWN
    return {"purpose": pid if shown else None, "name": tx.by_id[pid]["name"] if shown else None,
            "candidate": pid, "confidence": confidence, "evidence": words, "strong": bool(pid) and confidence >= purpose.MIN_STRONG,
            "note": "Inference is off, so live requests would not get this." if ctx.db.get_setting("purpose_inference", "1") != "1" else ""}


# ---------------------------------------------------------------- the model registry

MODEL_ID = r"(?P<mid>[A-Za-z0-9][A-Za-z0-9._:@/\[\]-]{0,119})"


def _chat_providers(ctx):
    return {name for name, p in ctx.gw.settings.providers.items() if p.is_chat}


@route("GET", r"/models")
def list_models(ctx):
    """Every chat model the gateway knows of — registered, priced, or seen in the last 30 days — with how it
    is governed and used. A model nobody registered is 'unlisted': allowed, as before the registry."""
    since = time.time() - 30 * DAY
    chat = _chat_providers(ctx)
    used = {r["model"]: r for r in ctx.db.q(
        "SELECT model, provider, SUM(outcome = 'ok') AS requests, COUNT(DISTINCT person_id) AS people,"
        " ROUND(COALESCE(SUM(cost), 0), 4) AS cost, SUM(cost IS NULL AND outcome = 'ok') AS unpriced, MAX(ts) AS last,"
        " SUM(rule LIKE 'model:%') AS refused FROM requests WHERE ts >= ? AND model IS NOT NULL AND model != ''"
        " AND kind NOT IN ('other', 'media-status', 'media') GROUP BY model", (since,))}
    prices = ctx.gw.prices()
    registry = policy.registry(ctx.db)
    items = []
    for mid in set(registry) | {m for m, r in used.items() if r["provider"] in chat} | set(prices):
        reg = registry.get(mid)
        governing = reg or policy.find_model(registry, mid)
        u = used.get(mid) or {}
        price = prices.get(mid)
        items.append({
            "id": mid, "provider": (reg or {}).get("provider") or u.get("provider") or (price or {}).get("provider") or "",
            "label": (reg or {}).get("label") or "", "registered": bool(reg),
            "status": governing["status"] if governing else "unlisted",
            "governed_by": governing["id"] if governing and not reg else None,
            "classification": governing["classification"] if governing else None,
            "allowed_departments": [d for d in ((governing or {}).get("allowed_departments") or "").split(",") if d],
            "note": (reg or {}).get("note") or "", "updated": (reg or {}).get("updated"), "updated_by": (reg or {}).get("updated_by"),
            "priced": price is not None or bool(policy.find_model(prices, mid)),
            "requests": u.get("requests") or 0, "people": u.get("people") or 0, "cost": u.get("cost") or 0.0,
            "unpriced": u.get("unpriced") or 0, "refused": u.get("refused") or 0, "last": u.get("last"),
        })
    items.sort(key=lambda m: (-(m["requests"]), not m["registered"], m["id"]))
    return {"items": items, "statuses": MODEL_STATUSES, "classifications": policy.CLASSIFICATIONS,
            "departments": [r["department"] for r in ctx.db.q(
                "SELECT DISTINCT department FROM people WHERE department != '' ORDER BY department COLLATE NOCASE")]}


@route("PUT", r"/models/" + MODEL_ID, area="govern")
def put_model(ctx, mid):
    b = ctx.body
    old = ctx.db.one("SELECT * FROM models WHERE id = ?", (mid,))
    status = b.get("status", (old or {}).get("status", "approved"))
    if status not in MODEL_STATUSES:
        raise ApiError(400, "status must be one of: " + ", ".join(MODEL_STATUSES))
    classification = b.get("classification", (old or {}).get("classification", "internal"))
    if classification not in policy.CLASSIFICATIONS:
        raise ApiError(400, "classification must be one of: " + ", ".join(policy.CLASSIFICATIONS))
    depts = b.get("allowed_departments", (old or {}).get("allowed_departments", ""))
    depts = depts.split(",") if isinstance(depts, str) else depts if isinstance(depts, list) else []
    depts = ",".join(sorted({str(d).strip()[:60] for d in depts if str(d).strip()}, key=str.lower))
    if status == "restricted" and not depts:
        raise ApiError(400, "a restricted model needs the departments that may use it")
    provider = str(b.get("provider", (old or {}).get("provider", "")) or "").strip()
    if provider and provider not in ctx.gw.settings.providers:
        raise ApiError(400, "provider must be one of the gateway's providers")
    ctxw = b.get("context_window", (old or {}).get("context_window"))
    try:
        ctxw = int(ctxw) if ctxw not in (None, "") else None
    except (TypeError, ValueError):
        raise ApiError(400, "context_window must be a whole number of tokens")
    values = {"provider": provider, "label": str(b.get("label", (old or {}).get("label", "")) or "").strip()[:80],
              "status": status, "classification": classification, "allowed_departments": depts,
              "modality": str(b.get("modality", (old or {}).get("modality", "")) or "").strip()[:40],
              "context_window": ctxw, "note": str(b.get("note", (old or {}).get("note", "")) or "").strip()[:300]}
    now = time.time()
    if old:
        changed = {k: v for k, v in values.items() if old.get(k) != v}
        if not changed:
            return {"ok": True}
        ctx.db.x(f"UPDATE models SET {', '.join(f'{k} = ?' for k in changed)}, updated = ?, updated_by = ? WHERE id = ?",
                 [*changed.values(), now, ctx.admin["username"], mid])
        ctx.audit("changed a model's rules", mid, ", ".join(sorted(changed)), before={k: old[k] for k in changed},
                  after=changed, correlation=f"model:{mid}")
    else:
        ctx.db.x("INSERT INTO models(id, provider, label, status, classification, allowed_departments, modality, context_window, note,"
                 " updated, updated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 (mid, *values.values(), now, ctx.admin["username"]))
        ctx.audit("registered a model", mid, status, after=values, correlation=f"model:{mid}")
    ctx.gw.reload_governance()
    return {"ok": True}


@route("DELETE", r"/models/" + MODEL_ID, area="govern")
def remove_model(ctx, mid):
    row = ctx.db.one("SELECT * FROM models WHERE id = ?", (mid,))
    if not row:
        raise ApiError(404, "that model isn't in the registry")
    ctx.db.x("DELETE FROM models WHERE id = ?", (mid,))
    ctx.gw.reload_governance()
    ctx.audit("removed a model from the registry", mid, "back to unlisted (allowed)", before=row, correlation=f"model:{mid}")
    return {"ok": True}


# ---------------------------------------------------------------- policies


def _names(db):
    people = {r["id"]: r["name"] for r in db.q("SELECT id, name FROM people")}
    tools = {r["id"]: r["name"] for r in db.q("SELECT id, name FROM tools")}
    return people, tools


def describe(p, people, tools):
    """One plain sentence for a policy, e.g. 'Refuses Midjourney for Marketing, on any channel.'"""
    s, sc, pr = p["subjects"], p["scope"], p["params"]
    who = "everyone" if s.get("everyone") else " and ".join(
        x for x in (", ".join(s.get("departments") or []) and "the " + ", ".join(s["departments"]) + " department" + ("s" if len(s["departments"]) > 1 else ""),
                    ", ".join(people.get(i, f"person #{i}") for i in s.get("people") or [])) if x)
    parts = []
    if sc.get("tools"):
        parts.append(", ".join(tools.get(t, t) for t in sc["tools"]))
    if sc.get("models"):
        parts.append("models " + ", ".join(sc["models"]))
    if sc.get("providers"):
        parts.append("the " + ", ".join(sc["providers"]) + " service")
    if sc.get("classifications"):
        parts.append(" or ".join(sc["classifications"]) + " tools and models")
    what = " · ".join(parts) or "all AI"
    channels = {"request": "requests through the gateway", "launch": "opening from Swangz AI", "site": "website visits"}
    where = "any channel" if not sc.get("channels") else ", ".join(channels[c] for c in sc["channels"])
    if p["effect"] == "deny":
        return f"Refuses {what} for {who}, on {where}."
    if p["effect"] == "hours":
        days = ", ".join(policy.DAYS[d] for d in pr.get("days") or [])
        return f"Allows {what} for {who} only on {days}, {pr.get('start')}–{pr.get('end')} gateway time ({where})."
    return f"Stops {what} for {who} once their estimated spend this month reaches ${pr.get('limit_usd', 0):,.2f}."


def _hits(db, since):
    hits = {}
    for table, col in (("requests", "ts"), ("launches", "ts"), ("site_usage", "started")):
        for r in db.q(f"SELECT rule, COUNT(*) AS n FROM {table} WHERE rule LIKE 'policy:%' AND {col} >= ? GROUP BY rule", (since,)):
            pid = r["rule"].split(":", 1)[1]
            if pid.isdigit():
                hits[int(pid)] = hits.get(int(pid), 0) + r["n"]
    return hits


@route("GET", r"/policies")
def list_policies(ctx):
    people, tools = _names(ctx.db)
    hits = _hits(ctx.db, time.time() - 30 * DAY)
    items = []
    for p in policy.load(ctx.db, include_disabled=True):
        items.append({**p, "summary": describe(p, people, tools), "refused_30d": hits.get(p["id"], 0)})
    return {"items": items, "effects": policy.EFFECTS, "channels": policy.CHANNELS, "classifications": policy.CLASSIFICATIONS,
            "days": policy.DAYS, "tz_offset_minutes": ctx.gw.settings.tz_offset_minutes,
            "departments": [r["department"] for r in ctx.db.q(
                "SELECT DISTINCT department FROM people WHERE department != '' ORDER BY department COLLATE NOCASE")]}


def _checked(ctx, body):
    try:
        values = policy.validate(body)
    except ValueError as exc:
        raise ApiError(400, str(exc))
    people = values["subjects"]["people"]
    if people:
        known = {r["id"] for r in ctx.db.q(f"SELECT id FROM people WHERE id IN ({','.join('?' * len(people))})", people)}
        if set(people) - known:
            raise ApiError(400, "one of the people named doesn't exist")
    tools = values["scope"].get("tools") or []
    if tools:
        known = {r["id"] for r in ctx.db.q(f"SELECT id FROM tools WHERE id IN ({','.join('?' * len(tools))})", tools)}
        if set(tools) - known:
            raise ApiError(400, "one of the tools named isn't in the catalogue")
    providers = values["scope"].get("providers") or []
    if set(providers) - set(ctx.gw.settings.providers):
        raise ApiError(400, "one of the providers named isn't one of the gateway's")
    return values


def _stored(values):
    import json

    return {**values, **{k: json.dumps(values[k], sort_keys=True) for k in ("subjects", "scope", "params")}}


@route("POST", r"/policies", area="govern")
def add_policy(ctx):
    values = _checked(ctx, ctx.body)
    row = _stored(values)
    now = time.time()
    pid = ctx.db.x("INSERT INTO policies(name, effect, enabled, subjects, scope, params, note, created, created_by, updated, updated_by)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (row["name"], row["effect"], row["enabled"], row["subjects"], row["scope"], row["params"], row["note"],
                    now, ctx.admin["username"], now, ctx.admin["username"])).lastrowid
    ctx.gw.reload_governance()
    people, tools = _names(ctx.db)
    ctx.audit("added a policy", values["name"], describe(values, people, tools), after=values, correlation=f"policy:{pid}")
    return {"ok": True, "id": pid}


def _policy(ctx, pid):
    row = ctx.db.one("SELECT * FROM policies WHERE id = ?", (int(pid),))
    if not row:
        raise ApiError(404, "no such policy")
    return policy.parse_row(row)


@route("PUT", r"/policies/(?P<pid>\d+)", area="govern")
def edit_policy(ctx, pid):
    old = _policy(ctx, pid)
    values = _checked(ctx, {**ctx.body, "enabled": ctx.body.get("enabled", bool(old["enabled"]))})
    row = _stored(values)
    ctx.db.x("UPDATE policies SET name = ?, effect = ?, enabled = ?, subjects = ?, scope = ?, params = ?, note = ?, updated = ?,"
             " updated_by = ? WHERE id = ?", (row["name"], row["effect"], row["enabled"], row["subjects"], row["scope"], row["params"],
                                               row["note"], time.time(), ctx.admin["username"], old["id"]))
    ctx.gw.reload_governance()
    keys = ("name", "effect", "enabled", "subjects", "scope", "params", "note")
    changed = [k for k in keys if old.get(k) != values.get(k)]
    ctx.audit("changed a policy", values["name"], ", ".join(changed) or "no change",
              before={k: old[k] for k in changed}, after={k: values[k] for k in changed}, correlation=f"policy:{pid}",
              outcome="ok" if changed else "no-op")
    return {"ok": True}


@route("PATCH", r"/policies/(?P<pid>\d+)", area="govern")
def switch_policy(ctx, pid):
    old = _policy(ctx, pid)
    if "enabled" not in ctx.body:
        raise ApiError(400, "send enabled: true or false")
    on = 1 if ctx.body["enabled"] else 0
    ctx.db.x("UPDATE policies SET enabled = ?, updated = ?, updated_by = ? WHERE id = ?", (on, time.time(), ctx.admin["username"], old["id"]))
    ctx.gw.reload_governance()
    ctx.audit("switched a policy " + ("on" if on else "off"), old["name"], before={"enabled": old["enabled"]}, after={"enabled": on},
              correlation=f"policy:{pid}", outcome="ok" if on != old["enabled"] else "no-op")
    return {"ok": True}


@route("DELETE", r"/policies/(?P<pid>\d+)", area="govern")
def remove_policy(ctx, pid):
    old = _policy(ctx, pid)
    ctx.db.x("DELETE FROM policies WHERE id = ?", (old["id"],))
    ctx.gw.reload_governance()
    ctx.audit("removed a policy", old["name"], before={k: old[k] for k in ("name", "effect", "enabled", "subjects", "scope", "params")},
              correlation=f"policy:{pid}")
    return {"ok": True}


# ---------------------------------------------------------------- the policy simulator (read-only)


class _ToolIndex:
    def __init__(self, db):
        rows = db.q("SELECT id, name, kind, provider, classification FROM tools ORDER BY rowid")
        self.by_id = {r["id"]: r for r in rows}
        self.api = {}
        for r in rows:
            if r["kind"] == "api" and r["provider"]:
                self.api.setdefault(r["provider"], r)

    def for_request(self, client, provider):
        tid = {"Claude Code": "claude-code", "Codex": "codex"}.get(client)
        return self.by_id.get(tid) if tid in self.by_id else self.api.get(provider)


def _overlaps(a, b):
    """Could two policies apply to the same person and the same thing?"""
    sa, sb = a["subjects"], b["subjects"]
    if not (sa.get("everyone") or sb.get("everyone")):
        same_dept = {d.lower() for d in sa.get("departments") or []} & {d.lower() for d in sb.get("departments") or []}
        same_people = set(sa.get("people") or []) & set(sb.get("people") or [])
        if not (same_dept or same_people or (sa.get("departments") and sb.get("people")) or (sa.get("people") and sb.get("departments"))):
            return False
    for k in ("tools", "providers", "classifications", "channels"):
        if a["scope"].get(k) and b["scope"].get(k) and not set(a["scope"][k]) & set(b["scope"][k]):
            return False
    return True


def simulate(db, settings, draft, days=30, replacing=None, now=None):
    """Replay the last `days` of what actually happened — requests that went through, tools opened, websites
    visited — against a draft policy, and report what it would have refused. Changes nothing."""
    now = now or time.time()
    since = now - days * DAY
    p = {**draft, "id": None}
    registry = policy.registry(db)
    tools = _ToolIndex(db)
    channels = p["scope"].get("channels") or list(policy.CHANNELS)
    events, truncated = [], False
    if "request" in channels:
        rows = db.q("SELECT r.id, r.ts, r.person_id, r.key_id, r.client, r.provider, r.model, r.cost, p.name AS person, p.department"
                    " FROM requests r JOIN people p ON p.id = r.person_id WHERE r.ts >= ? AND r.ts < ? AND r.outcome = 'ok'"
                    " AND r.kind NOT IN ('other', 'media-status') ORDER BY r.ts DESC LIMIT ?", (since, now, REPLAY_LIMIT + 1))
        truncated |= len(rows) > REPLAY_LIMIT
        for r in rows[:REPLAY_LIMIT]:
            tool = tools.for_request(r["client"], r["provider"])
            reg = policy.find_model(registry, r["model"])
            classes = sorted({c for c in ((tool or {}).get("classification"), (reg or {}).get("classification")) if c})
            events.append(("request", r, tool, {"channel": "request", "tool_id": tool["id"] if tool else None, "provider": r["provider"],
                                                "model": r["model"], "classifications": classes}))
    for channel, sql in (("launch", "SELECT l.id, l.ts, l.person_id, l.tool_id, p.name AS person, p.department FROM launches l"
                                    " JOIN people p ON p.id = l.person_id WHERE l.ts >= ? AND l.ts < ? AND l.outcome = 'opened'"
                                    " ORDER BY l.ts DESC LIMIT ?"),
                         ("site", "SELECT s.id, s.started AS ts, s.person_id, s.tool_id, p.name AS person, p.department FROM site_usage s"
                                  " JOIN people p ON p.id = s.person_id WHERE s.started >= ? AND s.started < ? AND s.outcome = 'allowed'"
                                  " ORDER BY s.started DESC LIMIT ?")):
        if channel not in channels:
            continue
        rows = db.q(sql, (since, now, REPLAY_LIMIT + 1))
        truncated |= len(rows) > REPLAY_LIMIT
        for r in rows[:REPLAY_LIMIT]:
            tool = tools.by_id.get(r["tool_id"])
            if tool:
                events.append((channel, r, tool, policy.tool_scope(tool, channel)))
    events.sort(key=lambda e: e[1]["ts"])

    # a cap counts spend as it accrues: what it refuses doesn't add to the month
    running = {}
    counting = {**p, "scope": {k: v for k, v in p["scope"].items() if k != "classifications"}}

    def month(ts):
        m = proxy.period_starts(ts, settings.tz_offset_minutes)[1]
        if m not in running:
            running[m] = policy.scoped_spend(db, p, m, since) if m < since else 0.0
        return m

    others = [q for q in policy.load(db) if q["id"] != replacing and q["effect"] != "cap"]
    checked = {c: 0 for c in policy.CHANNELS}
    refused = {c: 0 for c in policy.CHANNELS}
    people, by_tool, devices, overlap, examples = {}, {}, set(), {}, []
    spend, unpriced = 0.0, 0
    for channel, r, tool, what in events:
        checked[channel] += 1
        who = {"person_id": r["person_id"], "department": r["department"]}
        m = month(r["ts"]) if p["effect"] == "cap" else None
        d = policy.evaluate(db, settings, who, what, policies=[p], now=r["ts"], spend=lambda _p: running[m])
        if d.allowed:
            if m is not None and channel == "request" and policy.subject_matches(counting, who)[0] \
                    and policy.scope_matches(counting, what)[0]:
                running[m] += r["cost"] or 0.0
            continue
        refused[channel] += 1
        person = people.setdefault(r["person_id"], {"person_id": r["person_id"], "person": r["person"], "department": r["department"] or "",
                                                    "refused": 0, "request": 0, "launch": 0, "site": 0})
        person["refused"] += 1
        person[channel] += 1
        key = tool["id"] if tool else (r.get("provider") or "?")
        t = by_tool.setdefault(key, {"tool_id": tool["id"] if tool else None, "tool": tool["name"] if tool else (r.get("provider") or "Unknown"),
                                     "refused": 0})
        t["refused"] += 1
        if channel == "request":
            if r["key_id"]:
                devices.add(r["key_id"])
            if r["cost"] is None:
                unpriced += 1
            else:
                spend += r["cost"]
        for q in others:
            if not policy.evaluate(db, settings, who, what, policies=[q], now=r["ts"]).allowed:
                overlap.setdefault(q["id"], {"id": q["id"], "name": q["name"], "events": 0})["events"] += 1
        if len(examples) < 12:
            examples.append({"ts": r["ts"], "channel": channel, "person": r["person"], "tool": t["tool"],
                             "model": r.get("model"), "why": d.trace[-1]["why"]})

    conflicts = []
    for q in policy.load(db):
        if q["id"] == replacing or not _overlaps(p, q):
            continue
        if (q["effect"], q["subjects"], q["scope"], {k: v for k, v in q["params"].items() if k != "message"}) == \
                (p["effect"], p["subjects"], p["scope"], {k: v for k, v in p["params"].items() if k != "message"}):
            conflicts.append({"id": q["id"], "name": q["name"], "kind": "duplicate", "text": "does exactly the same thing"})
        elif q["effect"] == "hours" and p["effect"] == "hours" and q["params"] != p["params"]:
            conflicts.append({"id": q["id"], "name": q["name"], "kind": "hours",
                              "text": "also sets permitted hours for some of the same people; where both apply, only the time inside both is allowed"})
        elif q["effect"] == "deny" and p["effect"] != "deny":
            conflicts.append({"id": q["id"], "name": q["name"], "kind": "shadowed",
                              "text": "already refuses some of what this covers outright"})
    total = sum(refused.values())
    return {
        "window": {"since": since, "until": now, "days": days},
        "checked": checked, "refused": {**refused, "total": total},
        "people": sorted(people.values(), key=lambda x: -x["refused"])[:50], "people_count": len(people),
        "tools": sorted(by_tool.values(), key=lambda x: -x["refused"])[:30],
        "devices": len(devices), "spend": round(spend, 4), "unpriced": unpriced,
        "already_refused": sorted(overlap.values(), key=lambda x: -x["events"]), "conflicts": conflicts,
        "examples": examples, "truncated": truncated,
        "notes": ["Read-only: nothing was changed, and nobody was told.",
                  "Replays what actually happened: requests that went through, tools opened and websites visited. "
                  "Someone refused might have done something else instead.",
                  "People are matched on their department as it is today.",
                  *(["Spend is estimated from recorded costs; requests with no price yet are counted as unpriced."] if refused["request"] else []),
                  *([f"Only the latest {REPLAY_LIMIT:,} events per channel were replayed."] if truncated else [])],
    }


@route("POST", r"/policies/simulate")
def simulate_policy(ctx):
    draft = ctx.body.get("policy") if isinstance(ctx.body.get("policy"), dict) else ctx.body
    values = _checked(ctx, {**draft, "enabled": True})
    try:
        days = max(1, min(90, int(ctx.body.get("days") or 30)))
        replacing = int(ctx.body["replacing"]) if ctx.body.get("replacing") else None
    except (TypeError, ValueError):
        raise ApiError(400, "days and replacing must be whole numbers")
    people, tools = _names(ctx.db)
    return {**simulate(ctx.db, ctx.gw.settings, values, days, replacing), "summary": describe(values, people, tools)}


# ---------------------------------------------------------------- what-if: revoking, and seats


def _person_and_tool(ctx, b):
    try:
        pid = int(b.get("person_id"))
    except (TypeError, ValueError):
        raise ApiError(400, "send person_id")
    person = ctx.db.one("SELECT * FROM people WHERE id = ?", (pid,))
    if not person:
        raise ApiError(404, "no such person")
    tool = ctx.db.one("SELECT * FROM tools WHERE id = ?", (str(b.get("tool_id") or ""),))
    if not tool:
        raise ApiError(404, "no such tool")
    return person, tool


@route("POST", r"/simulate/revoke")
def simulate_revoke(ctx):
    """What turning one tool off for one person would change. Changes nothing."""
    person, tool = _person_and_tool(ctx, ctx.body)
    now = time.time()
    grants = ctx.db.q("SELECT * FROM entitlements WHERE tool_id = ? AND (person_id = ? OR (department != '' AND department = ?))"
                      " AND (expires IS NULL OR expires > ?)", (tool["id"], person["id"], person["department"] or "\0", now))
    direct = next((g for g in grants if g["person_id"] == person["id"]), None)
    team = next((g for g in grants if g["department"]), None)
    ok, state, reason = entitle.is_enabled(ctx.db, person, tool)
    rows, _ = insight.usage_rows(ctx.db, now - 30 * DAY, now, person=person["id"], tool_id=tool["id"])
    use = {k: sum(r[k] for r in rows) for k in ("requests", "opens", "visits", "seconds", "cost")}
    use["last"] = max((r["last"] for r in rows), default=None) or None
    where = insight.tool_requests_where(tool)
    devices = ctx.db.q("SELECT k.id, k.label, MAX(r.ts) AS last FROM requests r JOIN keys k ON k.id = r.key_id"
                       f" WHERE r.person_id = ? AND r.ts >= ? AND {where[0]} GROUP BY k.id ORDER BY last DESC",
                       [person["id"], now - 30 * DAY, *where[1]]) if where else []
    turn = turns.held_by(ctx.db, person["id"]).get(tool["id"])
    open_ask = ctx.db.one("SELECT id, created FROM access_requests WHERE tool_id = ? AND person_id = ? AND state = 'open'",
                          (tool["id"], person["id"]))
    effects = []
    if not direct and not team:
        effects.append(f"{person['name']} isn't assigned {tool['name']}, so there is nothing to revoke.")
    elif direct and team:
        effects.append(f"Their own grant goes, but they keep {tool['name']} through the {team['department']} department's grant.")
    elif direct:
        effects.append(f"Their own grant goes; {tool['name']} becomes unavailable to them" + ("." if ok else f" (it already is: {reason.lower()})"))
    else:
        effects.append(f"They have {tool['name']} through the {team['department']} department, not a grant of their own: "
                       "revoking it for them alone changes nothing. Turn it off for the department, or move them.")
    lost = bool(direct) and not team and ok
    if lost and (use["requests"] or use["opens"] or use["visits"]):
        effects.append(f"In the last 30 days they used it: {use['requests']} requests, {use['opens']} opens, {use['visits']} website visits.")
    if lost and devices:
        effects.append(f"{len(devices)} of their keys used it; requests from those keys to {tool['name']} would be refused.")
    if lost and turn:
        effects.append(f"They hold the shared account until {_clock(ctx.gw.settings, turn['expires'])}; revoking doesn't end that turn — "
                       "end it from the tool's page.")
    if open_ask:
        effects.append("They have an open request for this tool, which stays open.")
    return {"person": {"id": person["id"], "name": person["name"], "department": person["department"] or ""},
            "tool": {"id": tool["id"], "name": tool["name"], "kind": tool["kind"], "signin": tool["signin"]},
            "now": {"enabled": ok, "state": state, "reason": reason},
            "grants": {"direct": bool(direct), "direct_expires": (direct or {}).get("expires"),
                       "department": team["department"] if team else None},
            "after": {"enabled": ok and not lost}, "usage_30d": use, "devices": devices,
            "turn": {"expires": turn["expires"]} if turn else None, "open_request": bool(open_ask), "effects": effects,
            "notes": ["Read-only: nothing was changed."]}


@route("POST", r"/simulate/seats")
def simulate_seats(ctx):
    """What a different number of seats on a tool would mean: who keeps one, who is left without, and the
    cost if the price per seat stays as it is now. Changes nothing."""
    tool = ctx.db.one("SELECT * FROM tools WHERE id = ?", (str(ctx.body.get("tool_id") or ""),))
    if not tool:
        raise ApiError(404, "no such tool")
    try:
        seats = int(ctx.body.get("seats"))
    except (TypeError, ValueError):
        raise ApiError(400, "seats must be a whole number")
    if seats < 0 or seats > 10000:
        raise ApiError(400, "seats must be between 0 and 10000")
    now = time.time()
    sub = ctx.db.one("SELECT * FROM subscriptions WHERE tool_id = ?", (tool["id"],)) or {}
    assigned = ctx.db.q(
        "SELECT DISTINCT p.id, p.name, p.department FROM people p JOIN entitlements e ON e.tool_id = ?"
        " AND (e.person_id = p.id OR (e.department != '' AND e.department = p.department))"
        " WHERE p.status = 'active' AND (e.expires IS NULL OR e.expires > ?) ORDER BY p.name COLLATE NOCASE", (tool["id"], now))
    rows, _ = insight.usage_rows(ctx.db, now - 30 * DAY, now, tool_id=tool["id"])
    activity = {r["person_id"]: r for r in rows}
    ranked = []
    for p in assigned:
        a = activity.get(p["id"]) or {}
        uses = (a.get("requests") or 0) + (a.get("opens") or 0) + (a.get("visits") or 0)
        ranked.append({"person_id": p["id"], "person": p["name"], "department": p["department"] or "", "uses_30d": uses,
                       "seconds_30d": a.get("seconds") or 0, "last": a.get("last") or None})
    ranked.sort(key=lambda x: (-(x["uses_30d"] > 0), -(x["last"] or 0), -x["uses_30d"]))
    keep, without = ranked[:seats], ranked[seats:]
    shared = turns.is_shared(tool)
    out = {"tool": {"id": tool["id"], "name": tool["name"], "signin": tool["signin"]}, "seats": seats,
           "current": {"seats": sub.get("seats"), "monthly_cost": sub.get("monthly_cost"), "plan": sub.get("plan") or "",
                       "state": sub.get("state") or "none"},
           "assigned": len(assigned), "active_30d": sum(1 for x in ranked if x["uses_30d"]),
           "keep": keep, "without": without, "notes": ["Read-only: nothing was changed."]}
    if sub.get("monthly_cost") and sub.get("seats"):
        per = sub["monthly_cost"] / sub["seats"]
        out["cost"] = {"per_seat": round(per, 2), "monthly": round(per * seats, 2), "change": round(per * seats - sub["monthly_cost"], 2),
                       "basis": "allocated"}
        out["notes"].append("The new cost assumes the price per seat stays as it is now; vendors often price tiers differently.")
    else:
        out["cost"] = None
        out["notes"].append("No plan cost and seat count are set for this tool, so the cost is unpriced.")
    if shared:
        intervals = ctx.db.q("SELECT started, COALESCE(ended, expires) AS ended FROM tool_turns WHERE tool_id = ? AND started >= ?",
                             (tool["id"], now - 30 * DAY))
        edges = sorted([(r["started"], 1) for r in intervals] + [(min(r["ended"], now), -1) for r in intervals], key=lambda e: (e[0], e[1]))
        peak = level = 0
        for _, step in edges:
            level += step
            peak = max(peak, level)
        waits = ctx.db.scalar("SELECT COUNT(*) FROM launches WHERE tool_id = ? AND ts >= ? AND outcome = 'refused'"
                              " AND reason LIKE '%is using the shared%'", (tool["id"], now - 30 * DAY)) or 0
        out["shared"] = {"seats_at_once": turns.seats(tool), "peak_at_once_30d": peak, "turns_30d": len(intervals), "waits_30d": waits}
        out["notes"].append("For a shared account, seats are how many people can hold it at once; everyone assigned can take turns.")
    return out


# ---------------------------------------------------------------- explain: why allowed, why refused


def _step(steps, check, result, detail):
    steps.append({"check": check, "result": result, "detail": detail})


def explain_access(gw, person, tool, model, channel, provider_name):
    db, now = gw.db, time.time()
    steps = []
    registry, _ = gw.governance()
    paused = db.get_setting("paused", "0") == "1"
    _step(steps, "Everyone's AI access", "fail" if paused else "pass",
          "Paused for everyone by an administrator (the kill switch)." if paused else "Not paused.")
    active = person["status"] == "active"
    ended = bool(person.get("access_until")) and person["access_until"] <= now
    _step(steps, "Their account", "pass" if active and not ended else "fail",
          "Suspended." if not active else "Their access period ended." if ended else
          "Active" + (f", until {_clock(gw.settings, person['access_until'])}." if person.get("access_until") else "."))
    if channel == "request":
        provider = gw.settings.providers.get(provider_name)
        if not provider:
            _step(steps, "Service", "fail", f"'{provider_name}' isn't one of the gateway's services.")
        else:
            off = provider.name in (db.get_setting("disabled_providers", "") or "").split(",")
            _step(steps, "Service", "fail" if off or not provider.api_key() else "pass",
                  f"{provider.label} is switched off by an administrator." if off else
                  f"{provider.label} has no API key on the gateway yet." if not provider.api_key() else f"{provider.label} is on.")
            services = [s.strip().lower() for s in (person.get("allowed_services") or "").split(",") if s.strip()]
            _step(steps, "Their services", "pass" if not services or provider.name.lower() in services else "fail",
                  "No limit on services." if not services else f"Limited to: {', '.join(services)}.")
            if provider.is_chat:
                if not model:
                    _step(steps, "Their model rules", "skip", "No model named.")
                else:
                    allowed = proxy.model_allowed(person.get("allowed_models"), model)
                    _step(steps, "Their model rules", "pass" if allowed else "fail",
                          "No model limit." if not (person.get("allowed_models") or "").strip() else
                          f"Allowed models: {person['allowed_models']}.")
                    reg = policy.find_model(registry, model)
                    blocked = policy.model_gate(registry, model, person.get("department"))
                    _step(steps, "Model registry", "fail" if blocked else "pass",
                          blocked[0][:1].upper() + blocked[0][1:] if blocked else
                          f"{reg['id']} is {reg['status']} ({reg['classification']})." if reg else
                          "Not in the registry, so allowed as before.")
        if tool and tool["kind"] == "dev":
            granted = tool["id"] in entitle.person_grants(db, person)
            _step(steps, "Developer tool", "pass" if granted else "fail",
                  f"{tool['name']} is assigned to them." if granted else f"{tool['name']} isn't assigned to them.")
        if person.get("daily_budget") is not None or person.get("monthly_budget") is not None:
            day, month = proxy.period_starts(now, gw.settings.tz_offset_minutes)
            msgs, over = [], False
            for label, budget, since in (("today", person.get("daily_budget"), day), ("this month", person.get("monthly_budget"), month)):
                if budget is not None:
                    used = gw.spend(person["id"], since)
                    over |= used >= budget
                    msgs.append(f"${used:.2f} of ${budget:.2f} {label}")
            _step(steps, "Their budget", "fail" if over else "pass", "; ".join(msgs) + ".")
        else:
            _step(steps, "Their budget", "pass", "No budget set.")
        what = policy.request_scope(db, registry, {"claude-code": "Claude Code", "codex": "Codex"}.get((tool or {}).get("id")),
                                    provider_name, model)
    else:
        ok, state, reason = entitle.is_enabled(db, person, tool)
        _step(steps, "Assignment and subscription", "pass" if ok else "fail", reason)
        what = policy.tool_scope(tool, channel)
    decision = policy.evaluate(db, gw.settings, {"person_id": person["id"], "department": person.get("department")}, what)
    applied = [t for t in decision.trace if t.get("applies")]
    _step(steps, "Company policies", "pass" if decision.allowed else "fail",
          decision.message[:1].upper() + decision.message[1:] if not decision.allowed else
          ("; ".join(f"{t['name']}: {t['why']}" for t in applied) if applied else
           "None apply." if decision.trace else "There are no policies."))
    if tool and turns.is_shared(tool) and channel != "request":
        holders = turns.holders(db, tool["id"])
        mine = any(t["person_id"] == person["id"] for t in holders)
        free = len(holders) < turns.seats(tool)
        _step(steps, "Shared account", "info",
              "They hold a turn now." if mine else "A seat is free: Open gives them a turn." if free else
              "Every seat is taken right now: " + ", ".join(t["person"] for t in holders) + ".")
    failed = next((s for s in steps if s["result"] == "fail"), None)
    return {"person": {"id": person["id"], "name": person["name"], "department": person.get("department") or ""},
            "tool": {"id": tool["id"], "name": tool["name"]} if tool else None, "model": model, "channel": channel,
            "provider": provider_name, "allowed": failed is None, "decided_by": failed["check"] if failed else None,
            "steps": steps, "policy_trace": decision.trace, "as_of": now,
            "notes": ["The rules as they stand now. The per-minute rate limit depends on the moment and isn't checked here."]}


@route("GET", r"/policies/explain")
def explain(ctx):
    pid = ctx.arg("person", cast=int)
    person = ctx.db.one("SELECT * FROM people WHERE id = ?", (pid,)) if pid else None
    if not person:
        raise ApiError(400, "pick a person: ?person=<id>")
    tool_id, model, provider = ctx.arg("tool"), ctx.arg("model"), ctx.arg("provider")
    tool = ctx.db.one("SELECT * FROM tools WHERE id = ?", (tool_id,)) if tool_id else None
    if tool_id and not tool:
        raise ApiError(404, "no such tool")
    channel = ctx.arg("channel") or ("request" if model or provider or (tool and tool["kind"] != "site") else "launch")
    if channel not in policy.CHANNELS:
        raise ApiError(400, "channel must be request, launch or site")
    if channel == "request":
        if not provider and tool:
            provider = tool["provider"] or {"claude-code": "anthropic", "codex": "openai"}.get(tool["id"])
        if not provider:
            raise ApiError(400, "for a request, name the tool or the provider")
        if not tool:
            tool = ctx.db.one("SELECT * FROM tools WHERE kind = 'api' AND provider = ? ORDER BY rowid LIMIT 1", (provider,))
    elif not tool:
        raise ApiError(400, "name the tool: ?tool=<id>")
    return explain_access(ctx.gw, person, tool, model, channel, provider)
