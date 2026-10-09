"""Company rules, evaluated the same way every time.

A policy is data, not code, and is decided here deterministically — never by a model. Each has:

* **subjects** — who it is about: `{"everyone": true}`, `{"departments": ["Marketing"]}`, `{"people": [7, 9]}`
* **scope** — what it covers (an empty list means any): `tools` (catalogue ids), `models` (patterns such as
  `claude-opus-*`), `providers`, `classifications` (of the tool or model: public / internal / confidential /
  restricted) and `channels` (`request` through the gateway, `launch` from the portal, `site` in the browser)
* **effect** — what happens when both match:
  * `deny` — refuse, always
  * `hours` — refuse outside the permitted days and hours (`params.days` 0=Mon…6=Sun, `params.start`/`end`
    "08:00", in gateway time)
  * `cap` — refuse AI requests once the subjects' spend this month reaches `params.limit_usd`

Policies only ever take access away: entitlements, budgets and model rules grant it, as before, and a
policy can stop something those would allow. With no policies, nothing changes. Every evaluation can
return its full trace — each policy, whether it applied, and why — which is how "why was this denied?"
is answered.
"""

import fnmatch
import json
import time

from . import proxy

EFFECTS = ("deny", "hours", "cap")
CHANNELS = ("request", "launch", "site")
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class Decision:
    def __init__(self, allowed=True, policy=None, message="", trace=None):
        self.allowed, self.policy, self.message, self.trace = allowed, policy, message, trace or []

    def as_dict(self):
        return {"allowed": self.allowed, "policy": {"id": self.policy["id"], "name": self.policy["name"]} if self.policy else None,
                "message": self.message, "trace": self.trace}


def load(db, include_disabled=False):
    rows = db.q("SELECT * FROM policies" + ("" if include_disabled else " WHERE enabled = 1") + " ORDER BY id")
    return [parse_row(r) for r in rows]


def parse_row(r):
    r = dict(r)
    for k in ("subjects", "scope", "params"):
        if isinstance(r.get(k), str):
            try:
                r[k] = json.loads(r[k] or "{}")
            except ValueError:
                r[k] = {}
        r[k] = r.get(k) or {}
    return r


def validate(body):
    """A policy from the console -> clean columns, or ValueError with what to fix."""
    name = str(body.get("name") or "").strip()[:120]
    if not name:
        raise ValueError("give the policy a name")
    effect = body.get("effect")
    if effect not in EFFECTS:
        raise ValueError("effect must be deny, hours or cap")
    subj = body.get("subjects") or {}
    subjects = {"everyone": bool(subj.get("everyone")),
                "departments": sorted({str(d).strip() for d in subj.get("departments") or [] if str(d).strip()}),
                "people": sorted({int(p) for p in subj.get("people") or [] if str(p).strip().lstrip("-").isdigit()})}
    if not (subjects["everyone"] or subjects["departments"] or subjects["people"]):
        raise ValueError("say who the policy is about: everyone, departments or people")
    sc = body.get("scope") or {}
    scope = {}
    for k in ("tools", "models", "providers"):
        vals = sorted({str(v).strip() for v in sc.get(k) or [] if str(v).strip()})
        if vals:
            scope[k] = vals
    cls = [c for c in sc.get("classifications") or [] if c in CLASSIFICATIONS]
    if cls:
        scope["classifications"] = sorted(set(cls))
    ch = [c for c in sc.get("channels") or [] if c in CHANNELS]
    if ch:
        scope["channels"] = sorted(set(ch))
    pr = body.get("params") or {}
    params = {}
    if effect == "hours":
        days = sorted({int(d) for d in pr.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            raise ValueError("pick the days the hours apply to")
        start, end = _hm(pr.get("start")), _hm(pr.get("end"))
        if start is None or end is None or start == end:
            raise ValueError("permitted hours need a start and an end, e.g. 08:00 and 19:00")
        params = {"days": days, "start": pr.get("start"), "end": pr.get("end")}
    elif effect == "cap":
        try:
            limit = float(pr.get("limit_usd"))
        except (TypeError, ValueError):
            raise ValueError("a cap needs limit_usd, the monthly spend in dollars")
        if limit < 0:
            raise ValueError("a cap cannot be negative")
        params = {"limit_usd": limit}
        scope["channels"] = ["request"]  # only gateway requests cost metered money
    message = str(pr.get("message") or "").strip()[:200]
    if message:
        params["message"] = message
    return {"name": name, "effect": effect, "subjects": subjects, "scope": scope, "params": params,
            "note": str(body.get("note") or "").strip()[:500], "enabled": 1 if body.get("enabled", True) else 0}


def _hm(text):
    try:
        h, m = str(text or "").split(":")
        h, m = int(h), int(m)
    except ValueError:
        return None
    return h * 60 + m if 0 <= h <= 23 and 0 <= m <= 59 else None


def _local(ts, offset_minutes):
    t = time.gmtime(ts + offset_minutes * 60)
    return t.tm_wday, t.tm_hour * 60 + t.tm_min


def subject_matches(p, who):
    s = p["subjects"]
    if s.get("everyone"):
        return True, "everyone"
    dept = (who.get("department") or "").strip().lower()
    if dept and dept in {d.lower() for d in s.get("departments") or []}:
        return True, f"department {who.get('department')}"
    if who.get("person_id") in set(s.get("people") or []):
        return True, "named person"
    return False, "not about this person"


def scope_matches(p, what):
    sc = p["scope"]
    if sc.get("channels") and what.get("channel") not in sc["channels"]:
        return False, f"not for {what.get('channel')}s"
    if sc.get("tools") and what.get("tool_id") not in sc["tools"]:
        return False, "a different tool"
    if sc.get("providers") and what.get("provider") not in sc["providers"]:
        return False, "a different provider"
    if sc.get("models"):
        model = what.get("model") or ""
        if not model or not any(fnmatch.fnmatchcase(model, pat) for pat in sc["models"]):
            return False, "a different model"
    if sc.get("classifications") and not (set(what.get("classifications") or []) & set(sc["classifications"])):
        return False, "a different classification"
    return True, "in scope"


def evaluate(db, settings, who, what, policies=None, now=None, spend=None):
    """Decide one action. who = {person_id, department}; what = {channel, tool_id, model, provider,
    classifications}. `spend(policy)` -> this month's spend for a cap (computed if not given)."""
    now = now or time.time()
    trace = []
    for p in policies if policies is not None else load(db):
        ok_s, why_s = subject_matches(p, who)
        if not ok_s:
            trace.append({"id": p.get("id"), "name": p["name"], "applies": False, "why": why_s})
            continue
        ok_c, why_c = scope_matches(p, what)
        if not ok_c:
            trace.append({"id": p.get("id"), "name": p["name"], "applies": False, "why": why_c})
            continue
        refuse, why = False, ""
        if p["effect"] == "deny":
            refuse, why = True, "denied for " + why_s
        elif p["effect"] == "hours":
            day, minute = _local(now, settings.tz_offset_minutes)
            start, end = _hm(p["params"]["start"]), _hm(p["params"]["end"])
            inside_day = day in p["params"]["days"]
            inside_time = start <= minute < end if start < end else (minute >= start or minute < end)
            refuse = not (inside_day and inside_time)
            hours = f"{', '.join(DAYS[d] for d in p['params']['days'])} {p['params']['start']}–{p['params']['end']}"
            why = (f"outside permitted hours ({hours})" if refuse else f"within permitted hours ({hours})")
        elif p["effect"] == "cap":
            used = spend(p) if spend else month_spend(db, settings, p, now)
            limit = p["params"]["limit_usd"]
            refuse = used >= limit
            why = f"${used:.2f} of ${limit:.2f} used this month" + (" — the cap is reached" if refuse else "")
        trace.append({"id": p.get("id"), "name": p["name"], "applies": True, "refuses": refuse, "why": why})
        if refuse:
            msg = p["params"].get("message") or f"this is outside the company rule “{p['name']}” ({why})."
            return Decision(False, p, msg, trace)
    return Decision(True, None, "", trace)


def month_spend(db, settings, p, now=None):
    """The subjects' metered spend since the start of this month (gateway time), on what the cap covers."""
    _, month = proxy.period_starts(now or time.time(), settings.tz_offset_minutes)
    return scoped_spend(db, p, month, now or time.time() + 1)


def spend_filter(db, p):
    """SQL (on requests r joined to people p) for the spend a cap counts: its subjects' requests within its
    tool, provider and model scope. A classification scope does not narrow the count."""
    s, sc = p["subjects"], p["scope"]
    clauses, args = [], []
    if not s.get("everyone"):
        who, wargs = [], []
        depts = [d.lower() for d in s.get("departments") or []]
        if depts:
            who.append(f"LOWER(p.department) IN ({','.join('?' * len(depts))})")
            wargs += depts
        people = list(s.get("people") or [])
        if people:
            who.append(f"r.person_id IN ({','.join('?' * len(people))})")
            wargs += people
        clauses.append("(" + (" OR ".join(who) or "0") + ")")
        args += wargs
    if sc.get("providers"):
        clauses.append(f"r.provider IN ({','.join('?' * len(sc['providers']))})")
        args += sc["providers"]
    if sc.get("models"):
        clauses.append("(" + " OR ".join("r.model GLOB ?" for _ in sc["models"]) + ")")
        args += sc["models"]
    if sc.get("tools"):
        from . import insight

        parts = []
        for tid in sc["tools"]:
            tool = db.one("SELECT id, name, kind, provider FROM tools WHERE id = ?", (tid,))
            where = insight.tool_requests_where(tool) if tool else None
            if where:
                parts.append("(" + where[0] + ")")
                args += where[1]
        clauses.append("(" + (" OR ".join(parts) or "0") + ")")
    return " AND ".join(clauses) or "1", args


def scoped_spend(db, p, since, until):
    where, args = spend_filter(db, p)
    return db.scalar("SELECT COALESCE(SUM(r.cost), 0) FROM requests r LEFT JOIN people p ON p.id = r.person_id"
                     f" WHERE r.ts >= ? AND r.ts < ? AND {where}", [since, until, *args]) or 0.0


def request_tool(db, client, provider):
    """The catalogue tool a gateway request belongs to (as insight.Tools.for_request decides), with its
    classification — or None."""
    tid = {"Claude Code": "claude-code", "Codex": "codex"}.get(client)
    if tid:
        row = db.one("SELECT id, classification FROM tools WHERE id = ?", (tid,))
        if row:
            return row
    return db.one("SELECT id, classification FROM tools WHERE kind = 'api' AND provider = ? ORDER BY rowid LIMIT 1", (provider,))


def request_scope(db, registry, client, provider, model):
    """`what` for a gateway request: its tool, provider, model and the classifications of both."""
    tool = request_tool(db, client, provider)
    row = find_model(registry, model)
    classes = sorted({c for c in ((tool or {}).get("classification"), (row or {}).get("classification")) if c})
    return {"channel": "request", "tool_id": tool["id"] if tool else None, "provider": provider, "model": model,
            "classifications": classes}


def tool_scope(tool, channel):
    """`what` for opening a tool from the portal (launch) or visiting its website (site)."""
    return {"channel": channel, "tool_id": tool["id"], "provider": tool.get("provider") or None, "model": None,
            "classifications": [tool.get("classification") or "internal"]}


# ---------------------------------------------------------------- the model registry


def registry(db):
    """The model registry as {model id: row}."""
    return {r["id"]: r for r in db.q("SELECT * FROM models")}


def find_model(registry, model):
    """The registry row for a model: exact id first, then the longest id it starts with."""
    if not model:
        return None
    if model in registry:
        return registry[model]
    best = None
    for name in registry:
        if model.startswith(name + "-") or model.startswith(name + "@") or model.startswith(name + "["):
            if best is None or len(name) > len(best):
                best = name
    return registry[best] if best else None


def model_gate(registry, model, department):
    """None when the model may be used, else (message, short reason)."""
    row = find_model(registry, model)
    if not row:
        return None
    if row["status"] == "disabled":
        return f"the model '{model}' is switched off for everyone.", "model disabled"
    if row["status"] == "restricted":
        allowed = {d.strip().lower() for d in (row["allowed_departments"] or "").split(",") if d.strip()}
        if (department or "").strip().lower() not in allowed:
            return f"the model '{model}' is restricted to some departments.", "model restricted"
    return None
