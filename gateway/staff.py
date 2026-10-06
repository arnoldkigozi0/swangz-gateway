"""The staff app's API: sign in, connect a tool, look after your own devices.

For staff, Swangz AI is simply how they reach AI tools at work. This API only ever returns the
signed-in person's own profile, budget and keys.
"""

import html
import http.client
import json
import re
import secrets
import ssl
import time
from urllib.parse import quote, unquote

from . import guides, parse, proxy, security, store
from .admin import ApiError, Ctx

COOKIE = "sgw_staff"
SESSION_SECONDS = 14 * 86400
INVITE_SECONDS = 7 * 86400
ROUTES = []


def route(method, pattern, signed_in=True):
    def wrap(fn):
        ROUTES.append((method, re.compile(pattern), fn, signed_in))
        return fn

    return wrap


def dispatch(h, gw, path, query):
    sub = path[len("/api"):]
    for method, rx, fn, signed_in in ROUTES:
        m = rx.fullmatch(sub)
        if not m or method != h.command:
            continue
        ctx = Ctx(h, gw, query)
        try:
            if h.command != "GET" and h.headers.get("x-swangz-app") != "1":
                raise ApiError(403, "missing app header")
            ctx.person = current_person(ctx)
            if signed_in and not ctx.person:
                raise ApiError(401, "Please sign in.")
            if h.command in ("POST", "PUT", "PATCH", "DELETE"):
                raw = h.read_body(64 * 1024)
                if raw:
                    try:
                        ctx.body = json.loads(raw)
                    except ValueError:
                        raise ApiError(400, "body must be JSON")
                    if not isinstance(ctx.body, dict):
                        raise ApiError(400, "body must be a JSON object")
            result = fn(ctx, **{k: unquote(v) for k, v in m.groupdict().items()})
        except ApiError as err:
            return h.send_json(err.status, {"error": err.message})
        if isinstance(result, tuple):
            if isinstance(result[0], bytes):
                return h.send_bytes(200, result[0], result[1], result[2])
            return h.send_json(result[0], result[1], result[2] if len(result) > 2 else None)
        return h.send_json(200, result)
    return h.send_json(404, {"error": "no such endpoint"})


def current_person(ctx):
    # The web app uses a cookie; the browser extension can't send a Lax cookie cross-site, so it
    # presents the same session token as a bearer instead.
    token = _cookie(ctx.h.headers.get("cookie") or "", COOKIE)
    if not token:
        auth = (ctx.h.headers.get("authorization") or "").strip()
        if auth[:7].lower() == "bearer ":
            token = auth[7:].strip()
    if not token:
        return None
    return ctx.db.one(
        "SELECT p.* FROM staff_sessions s JOIN people p ON p.id = s.person_id WHERE s.token_hash = ? AND s.expires > ?",
        (security.sha256(token), time.time()))


def _cookie(header, name):
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def _session_cookie(ctx, token, max_age):
    # A staff app hosted on another origin (e.g. Netlify) needs SameSite=None so the browser sends
    # this cookie to the gateway; that requires Secure. Same-origin keeps the stricter Lax.
    cross = ctx.gw.cross_site(ctx.h)
    same_site = "None" if cross else "Lax"
    value = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite={same_site}; Max-Age={max_age}"
    if cross or ctx.gw.secure_request(ctx.h):
        value += "; Secure"
    return value


def _start_session(ctx, person_id):
    token = security.new_session_token()
    now = time.time()
    ctx.db.x("INSERT INTO staff_sessions(token_hash, person_id, created, expires, ip) VALUES(?,?,?,?,?)",
             (security.sha256(token), person_id, now, now + SESSION_SECONDS, ctx.ip))
    ctx.db.x("UPDATE people SET last_login = ? WHERE id = ?", (now, person_id))
    return {"Set-Cookie": _session_cookie(ctx, token, SESSION_SECONDS)}


def new_invite(db, person_id):
    """A one-time sign-in link token, valid for a week. Only its hash is stored."""
    token = secrets.token_urlsafe(24)
    db.x("UPDATE people SET invite_hash = ?, invite_expires = ? WHERE id = ?",
         (security.sha256(token), time.time() + INVITE_SECONDS, person_id))
    return token


def _invited(ctx, token):
    if not token:
        return None
    return ctx.db.one("SELECT * FROM people WHERE invite_hash = ? AND invite_expires > ?",
                      (security.sha256(token), time.time()))


# ---------------------------------------------------------------- signing in


@route("POST", r"/login", signed_in=False)
def login(ctx):
    email = str(ctx.body.get("email") or "").strip().lower()
    password = str(ctx.body.get("password") or "")
    if ctx.gw.throttle.blocked("staff:" + ctx.ip):
        raise ApiError(429, "Too many attempts. Wait ten minutes and try again.")
    person = ctx.db.one("SELECT * FROM people WHERE lower(email) = ? AND email != ''", (email,)) if email else None
    if not person or not person["pw_hash"] or not security.check_password(password, person["pw_hash"]):
        ctx.gw.throttle.fail("staff:" + ctx.ip)
        raise ApiError(401, "That email and password don't match.")
    ctx.gw.throttle.clear("staff:" + ctx.ip)
    return 200, {"ok": True}, _start_session(ctx, person["id"])


@route("POST", r"/logout", signed_in=False)
def logout(ctx):
    token = _cookie(ctx.h.headers.get("cookie") or "", COOKIE)
    if token:
        ctx.db.x("DELETE FROM staff_sessions WHERE token_hash = ?", (security.sha256(token),))
    return 200, {"ok": True}, {"Set-Cookie": _session_cookie(ctx, "", 0)}


@route("GET", r"/welcome/(?P<token>[A-Za-z0-9_\-]{20,64})", signed_in=False)
def welcome_check(ctx, token):
    person = _invited(ctx, token)
    if not person:
        raise ApiError(404, "This sign-in link has expired or was already used. Ask your admin for a new one.")
    return {"name": person["name"], "email": person["email"], "has_password": bool(person["pw_hash"])}


@route("POST", r"/welcome", signed_in=False)
def welcome(ctx):
    person = _invited(ctx, str(ctx.body.get("token") or ""))
    if not person:
        raise ApiError(404, "This sign-in link has expired or was already used. Ask your admin for a new one.")
    password = str(ctx.body.get("password") or "")
    if len(password) < 10:
        raise ApiError(400, "Use at least 10 characters.")
    ctx.db.x("UPDATE people SET pw_hash = ?, invite_hash = NULL, invite_expires = NULL WHERE id = ?",
             (security.hash_password(password, ctx.gw.settings.pbkdf2_iterations), person["id"]))
    ctx.db.x("DELETE FROM staff_sessions WHERE person_id = ?", (person["id"],))
    ctx.gw.audit(person["name"], "set their Swangz AI password", "", "", ctx.ip)
    return 200, {"ok": True}, _start_session(ctx, person["id"])


@route("POST", r"/password")
def change_password(ctx):
    if not security.check_password(str(ctx.body.get("current") or ""), ctx.person["pw_hash"] or ""):
        raise ApiError(400, "Your current password isn't right.")
    new = str(ctx.body.get("new") or "")
    if len(new) < 10:
        raise ApiError(400, "Use at least 10 characters.")
    ctx.db.x("UPDATE people SET pw_hash = ? WHERE id = ?",
             (security.hash_password(new, ctx.gw.settings.pbkdf2_iterations), ctx.person["id"]))
    return {"ok": True}


# ---------------------------------------------------------------- the person's own things


def _self_keys_allowed(ctx):
    return ctx.db.get_setting("staff_self_keys", "1") == "1"


@route("GET", r"/me")
def me(ctx):
    from . import catalog as catalog_mod
    from . import entitle, turns

    p = ctx.person
    day, month = proxy.period_starts(time.time(), ctx.gw.settings.tz_offset_minutes)
    keys = ctx.db.q("SELECT id, label, hint, created, last_used, revoked FROM keys WHERE person_id = ?"
                    " ORDER BY revoked IS NOT NULL, created DESC", (p["id"],))
    # which app each device is used with (Claude Code, Codex…) — the device's identity, never its activity
    apps = {r["key_id"]: r["client"] for r in ctx.db.q(
        "SELECT r.key_id, r.client FROM requests r JOIN (SELECT key_id, MAX(id) AS id FROM requests WHERE person_id = ?"
        " AND key_id IS NOT NULL GROUP BY key_id) m ON m.id = r.id", (p["id"],))}
    for k in keys:
        k["client"] = apps.get(k["id"]) if apps.get(k["id"]) not in (None, "", "unknown") else None
    catalog = entitle.for_person(ctx.db, p)
    enabled_ids = {t["id"] for t in catalog if t["state"] == "enabled"}
    pending = {r["tool_id"] for r in ctx.db.q(
        "SELECT tool_id FROM access_requests WHERE person_id = ? AND state = 'open'", (p["id"],))}
    logos = {r["tool_id"]: r["fetched"] for r in ctx.db.q("SELECT tool_id, fetched FROM tool_icons WHERE ok = 1")}
    opened = {r["tool_id"]: r["last"] for r in ctx.db.q(
        "SELECT tool_id, MAX(ts) AS last FROM launches WHERE person_id = ? AND outcome = 'opened' GROUP BY tool_id", (p["id"],))}
    ends = entitle.grant_ends(ctx.db, p)
    rows = {r["id"]: r for r in ctx.db.q("SELECT * FROM tools WHERE archived = 0")}
    direct = {r["tool_id"] for r in ctx.db.q("SELECT tool_id FROM entitlements WHERE person_id = ?", (p["id"],))}
    opens_30d = {r["tool_id"]: r["n"] for r in ctx.db.q(
        "SELECT tool_id, COUNT(*) AS n FROM launches WHERE person_id = ? AND outcome = 'opened' AND ts >= ?"
        " GROUP BY tool_id", (p["id"], time.time() - 30 * 86400))}
    for t in catalog:
        # why they have it: their own grant, or their team's
        t["grant"] = "direct" if t["id"] in direct else ("team" if t["assigned"] else None)
        t["opens_30d"] = opens_30d.get(t["id"], 0)
        t["pending"] = t["id"] in pending
        t["turn"] = turns.state_for(ctx.db, rows[t["id"]], p) if t["id"] in rows else None
        t["icon"] = f"/icons/{t['id']}?v={int(logos[t['id']])}" if t["id"] in logos else None
        t["workspace"] = catalog_mod.uses_workspace(rows[t["id"]]) if t["id"] in rows else False
        t["last_opened"] = opened.get(t["id"])
        t["ends"] = ends.get(t["id"])
    # connection guides only for the API/dev tools this person is actually entitled to
    guide_provider = {"anthropic", "openai", "elevenlabs", "higgsfield"}
    allow_providers = {row["provider"] for row in ctx.db.q(
        "SELECT provider FROM tools WHERE id IN (%s) AND provider != ''" % ",".join("?" * len(enabled_ids) or "''"),
        tuple(enabled_ids)) if enabled_ids} & guide_provider
    connect = [g for g in guides.guides(ctx.gw, None, ctx.gw.public_url(ctx.h))
               if _guide_provider(g["id"]) in allow_providers]
    out = {
        "name": p["name"], "email": p["email"],
        "title": p["title"], "department": p["department"],
        "active": p["status"] == "active" and ctx.db.get_setting("paused", "0") != "1",
        "suspended": p["status"] != "active", "paused": ctx.db.get_setting("paused", "0") == "1",
        "catalog": catalog,
        "keys": keys,
        "can_add_keys": _self_keys_allowed(ctx) and p["status"] == "active",
        "connect": connect,
        "base_url": ctx.gw.public_url(ctx.h),
        "budget_visible": bool(p["budget_visible"]),
        "access_until": p.get("access_until"),
        # the tools they asked for and what was decided
        "access_requests": ctx.db.q(
            "SELECT ar.id, ar.tool_id, t.name AS tool, ar.reason, ar.state, ar.created, ar.decided, ar.decision_note"
            " FROM access_requests ar JOIN tools t ON t.id = ar.tool_id WHERE ar.person_id = ?"
            " ORDER BY ar.created DESC LIMIT 30", (p["id"],)),
        # what the company records, stated plainly on the staff app's privacy page
        "privacy": {
            "retention_days": int(ctx.db.get_setting("retention_days", "90") or 0),
            "store_bodies": ctx.db.get_setting("store_bodies", "1") == "1",
            "block_secrets": ctx.db.get_setting("block_secrets", "0") == "1",
            "gate_log_full": ctx.db.get_setting("gate_log_full", "0") == "1",
            "support_contact": ctx.db.get_setting("support_contact", "") or "",
        },
    }
    if p["budget_visible"]:
        out["budget"] = {"daily": p["daily_budget"], "monthly": p["monthly_budget"],
                         "today": ctx.gw.spend(p["id"], day), "month": ctx.gw.spend(p["id"], month)}
    return out


_GUIDE_TO_PROVIDER = {"claude-code": "anthropic", "anthropic-sdk": "anthropic", "codex": "openai",
                      "openai-compatible": "openai", "elevenlabs": "elevenlabs", "higgsfield": "higgsfield"}


def _guide_provider(guide_id):
    return _GUIDE_TO_PROVIDER.get(guide_id, "")


@route("POST", r"/tools/(?P<tid>[a-z0-9-]+)/request")
def request_access(ctx, tid):
    tool = ctx.db.one("SELECT * FROM tools WHERE id = ? AND archived = 0", (tid,))
    if not tool:
        raise ApiError(404, "No such tool.")
    existing = ctx.db.one("SELECT id FROM access_requests WHERE tool_id = ? AND person_id = ? AND state = 'open'",
                          (tid, ctx.person["id"]))
    if existing:
        return {"ok": True, "already": True}
    reason = str(ctx.body.get("reason") or "").strip()[:500]
    ctx.db.x("INSERT INTO access_requests(tool_id, person_id, reason, created) VALUES(?,?,?,?)",
             (tid, ctx.person["id"], reason, time.time()))
    ctx.gw.audit(ctx.person["name"], "asked for a tool", tool["name"], reason, ctx.ip)
    return {"ok": True}


@route("POST", r"/tools/(?P<tid>[a-z0-9-]+)/turn/end")
def end_turn(ctx, tid):
    """Hand the shared account back so the next person can have it."""
    from . import turns

    tool = ctx.db.one("SELECT * FROM tools WHERE id = ?", (tid,))
    if not tool:
        raise ApiError(404, "No such tool.")
    n = turns.end(ctx.db, tid, ctx.person["id"], "self", "handed back")
    if n:
        ctx.gw.audit(ctx.person["name"], "handed back a shared account", tool["name"], "", ctx.ip)
        ctx.gw.workspaces.soon()  # their workspace sign-in goes now, not at the next sweep
    return {"ok": True, "ended": n, "sign_out_hosts": [h for h in (tool["hosts"] or "").split(",") if h]}


@route("POST", r"/workspace/hello", signed_in=False)
def workspace_hello(ctx):
    """One of Swangz's computers that runs company browsers, checking in with its key (not a person): where
    its browsers answer now. Under /api/ so it reaches the gateway through the Netlify front door too."""
    auth = (ctx.h.headers.get("authorization") or "").strip()
    key = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    try:
        return ctx.gw.workspaces.hello(str(ctx.body.get("host") or ""), key, str(ctx.body.get("url") or ""),
                                       ctx.body.get("info"))
    except PermissionError:
        raise ApiError(401, "that key isn't this computer's — make a new one in the console and run setup again")
    except ValueError as exc:
        raise ApiError(400, str(exc))


# ---------------------------------------------------------------- opening a tool from the portal


def launch(h, gw, tool_id):
    """/go/<tool>: the portal's Open button. Checks that this person may use the tool right now, logs
    the launch (who, which tool, when), and sends the browser on to the tool's sign-in link — or, for a
    shared account in the company workspace, into a browser of their own, signed in for this turn."""
    from . import catalog, entitle, turns, workspace

    ctx = Ctx(h, gw, "")
    person = current_person(ctx)
    if not person:
        return h.send_bytes(302, b"", "text/plain", {"Location": "/", "Cache-Control": "no-store"})
    tool = gw.db.one("SELECT * FROM tools WHERE id = ? AND archived = 0", (tool_id,)) \
        if re.fullmatch(r"[a-z0-9-]{1,80}", tool_id) else None
    if not tool:
        return _launch_page(h, 404, "That tool isn't in the catalog any more.", "Your admin may have removed it.")
    ok, state, reason = entitle.is_enabled(gw.db, person, tool)
    if gw.db.get_setting("paused", "0") == "1":
        ok, reason = False, "AI access is paused for everyone right now."
    target = catalog.launch_target(tool)
    if ok and not target:
        ok, reason = False, "This tool has no web address yet. Ask your admin."
    # a shared company account is handed out one turn at a time
    if ok and turns.is_shared(tool):
        where = workspace.mode(tool)
        pool = workspace.browsers(tool)
        asked = time.time()
        with gw.db.tx():  # so two people opening at once can't both get the last seat or the same browser
            turn, busy = turns.take(gw.db, tool, person)
            browser = gw.workspaces.assign(tool, turn) if turn and pool else None
        fresh = bool(turn) and turn["started"] >= asked
        full = f"All of Swangz's browsers for {tool['name']} are in use. Try again shortly."
        if not turn:
            who = ", ".join(t["person"] for t in busy)
            until = min(t["expires"] for t in busy)
            ok, reason = False, (f"{who} is using the shared {tool['name']} account until "
                                 f"{_clock(gw, until)}. You'll get it next — try again then.")
        elif pool and not browser:
            ok, reason = False, full
        elif where:
            try:
                target = gw.workspaces.open(tool, {**turn, "workspace": browser or turn["workspace"]}, person)
            except workspace.Starting:
                return _starting_page(h, tool)  # the turn is theirs; this page asks again until it's ready
            except workspace.Full as exc:
                ok, reason = False, ("Every one of Swangz's company browsers is in use right now. Try again "
                                     "shortly." if exc.server else full)
            except workspace.Unavailable as exc:
                gw.log(f"workspace: {tool['name']} for {person['name']}: {exc}")
                ok, reason = False, (f"Swangz's shared browser for {tool['name']} isn't answering right now. "
                                     "Try again in a minute, or tell your admin.")
        if ok and turn:
            gw.audit(person["name"], "took a turn on a shared account", tool["name"],
                     f"until {_clock(gw, turn['expires'])}", ctx.ip)
        elif turn and (fresh or (where == "agent" and not gw.workspaces.has_browser(turn["id"]))):
            # nobody got in on this turn: don't hold the seat (or a browser) for them
            turns.end(gw.db, tool["id"], person["id"], "system", reason[:200])
            gw.workspaces.soon()
    gw.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome, ip, user_agent) VALUES(?,?,?,?,?,?)",
            (tool["id"], person["id"], time.time(), "opened" if ok else "refused", ctx.ip,
             (h.headers.get("user-agent") or "")[:200]))
    if not ok:
        return _launch_page(h, 403, f"{tool['name']} isn't open to you right now", reason)
    return h.send_bytes(302, b"", "text/plain", {"Location": target, "Cache-Control": "no-store",
                                                  "Referrer-Policy": "no-referrer"})


def _clock(gw, ts):
    return time.strftime("%H:%M", time.gmtime(ts + gw.settings.tz_offset_minutes * 60))


def _starting_page(h, tool):
    """The person's browser on the workspace server is starting. This page asks /go again every few
    seconds — a plain refresh, no script — and lands in the browser as soon as it's ready. (Waiting here
    instead of holding the request open keeps under Netlify's 26-second proxy limit.)"""
    from .server import CONSOLE_HEADERS

    body = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width, initial-scale=1'>"
            "<meta http-equiv=refresh content=3><title>Starting your browser · Swangz AI</title>"
            "<link rel=stylesheet href=/static/tokens.css><link rel=stylesheet href=/static/portal.css></head>"
            "<body><main class=launch-msg><div class=launch-card>"
            "<img src=/static/icon.svg alt='' width=40 height=40>"
            f"<h1>Starting your {html.escape(tool['name'])} browser…</h1>"
            "<p>It's starting on Swangz's own server and opens here by itself as soon as it's ready — "
            "usually within half a minute.</p>"
            "<a class='btn btn--solid' href=/>Back to Swangz AI</a></div></main></body></html>")
    h.send_bytes(200, body.encode(), "text/html; charset=utf-8", {"Cache-Control": "no-store", **CONSOLE_HEADERS})


def _launch_page(h, status, title, text):
    from .server import CONSOLE_HEADERS

    body = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width, initial-scale=1'><title>Swangz AI</title>"
            "<link rel=stylesheet href=/static/tokens.css><link rel=stylesheet href=/static/portal.css></head>"
            "<body><main class=launch-msg><div class=launch-card>"
            "<img src=/static/icon.svg alt='' width=40 height=40>"
            f"<h1>{html.escape(title)}</h1><p>{html.escape(text)}</p>"
            "<a class='btn btn--solid' href=/>Back to Swangz AI</a></div></main></body></html>")
    h.send_bytes(status, body.encode(), "text/html; charset=utf-8", {"Cache-Control": "no-store", **CONSOLE_HEADERS})


# ---------------------------------------------------------------- the browser access gate

EXTENSION_SECONDS = 30 * 86400


@route("POST", r"/extension/login", signed_in=False)
def extension_login(ctx):
    """The company browser extension signs in here and keeps a token. Same password as the app."""
    email = str(ctx.body.get("email") or "").strip().lower()
    password = str(ctx.body.get("password") or "")
    if ctx.gw.throttle.blocked("ext:" + ctx.ip):
        raise ApiError(429, "Too many attempts. Wait ten minutes.")
    person = ctx.db.one("SELECT * FROM people WHERE lower(email) = ? AND email != ''", (email,)) if email else None
    if not person or not person["pw_hash"] or not security.check_password(password, person["pw_hash"]):
        ctx.gw.throttle.fail("ext:" + ctx.ip)
        raise ApiError(401, "That email and password don't match.")
    ctx.gw.throttle.clear("ext:" + ctx.ip)
    token = security.new_session_token()
    now = time.time()
    ctx.db.x("INSERT INTO staff_sessions(token_hash, person_id, created, expires, ip) VALUES(?,?,?,?,?)",
             (security.sha256(token), person["id"], now, now + EXTENSION_SECONDS, ctx.ip))
    ctx.gw.audit(person["name"], "connected the access extension", "", "", ctx.ip)
    return {"token": token, "name": person["name"], "policy": _gate_policy(ctx)}


def _gate_policy(ctx):
    full = ctx.db.get_setting("gate_log_full", "0") == "1"
    return ("Swangz AI records which approved tool you open, when, and for how long — the same as any "
            "company system. It does not read the pages or what you type."
            + (" Your admin has turned on full-content logging for compliance." if full else ""))


@route("GET", r"/gate/config", signed_in=False)
def gate_config(ctx):
    """The hosts the gate governs, so the extension only acts on those. Needs a valid token."""
    if not ctx.person:
        raise ApiError(401, "Sign in through the extension.")
    from . import catalog

    hosts = {}
    for h, tool in catalog.host_index(ctx.db).items():
        hosts[h] = tool["id"]
    return {"hosts": hosts, "policy": _gate_policy(ctx), "base_url": ctx.gw.public_url(ctx.h)}


@route("GET", r"/gate/turns")
def gate_turns(ctx):
    """Which shared tools this person still holds. The extension signs the browser out of any
    shared tool they are NOT holding, so the next person never inherits the session."""
    from . import turns

    mine = turns.held_by(ctx.db, ctx.person["id"])
    out, drop = [], []
    for tool in ctx.db.q("SELECT * FROM tools WHERE signin = 'shared' AND archived = 0"):
        hosts = [h for h in (tool["hosts"] or "").split(",") if h]
        if not hosts:
            continue
        if tool["id"] in mine:
            out.append({"tool_id": tool["id"], "hosts": hosts, "expires": mine[tool["id"]]["expires"]})
        else:
            drop.append({"tool_id": tool["id"], "hosts": hosts})
    return {"holding": out, "sign_out": drop}


@route("POST", r"/gate/open")
def gate_open(ctx):
    """The person navigated to an AI site. Decide allow/block and start a usage record. No page data."""
    from . import catalog, entitle

    host = str(ctx.body.get("host") or "").strip().lower()[:200]  # noqa: E501
    tool = catalog.match_host(catalog.host_index(ctx.db), host)
    paused = ctx.db.get_setting("paused", "0") == "1"
    if ctx.person["status"] != "active" or paused:
        allowed, reason, state = False, ("AI access is paused." if paused else "Your access is paused."), "suspended"
    elif not tool:
        return {"known": False, "allowed": True}  # not an AI tool we govern; the extension does nothing
    else:
        from . import turns

        ok, state, reason = entitle.is_enabled(ctx.db, ctx.person, tool)
        if ok and turns.is_shared(tool):
            ok, why = turns.may_open(ctx.db, tool, ctx.person)
            if not why:
                why = reason
            state, reason = ("no_turn" if not ok else state), (why if not ok else reason)
        allowed = ok
    outcome = "allowed" if allowed else "blocked"
    rid = ctx.db.x("INSERT INTO site_usage(tool_id, person_id, host, outcome, started) VALUES(?,?,?,?,?)",
                   (tool["id"] if tool else None, ctx.person["id"], host, outcome, time.time())).lastrowid
    pending = bool(tool and ctx.db.one("SELECT 1 FROM access_requests WHERE tool_id = ? AND person_id = ? AND state = 'open'",
                                       (tool["id"], ctx.person["id"])))
    return {"known": True, "allowed": allowed, "id": rid, "tool_id": tool["id"] if tool else None,
            "tool": tool["name"] if tool else None, "state": state if tool else None,
            "reason": reason if not allowed else None, "pending": pending,
            "app_url": ctx.gw.public_url(ctx.h)}


@route("POST", r"/gate/close")
def gate_close(ctx):
    """End a usage record with how long the tab was open. Still no page data."""
    try:
        rid = int(ctx.body.get("id") or 0)
        seconds = max(0, min(int(ctx.body.get("seconds") or 0), 86400))
    except (TypeError, ValueError):
        raise ApiError(400, "bad id or seconds")
    ctx.db.x("UPDATE site_usage SET ended = ?, seconds = ? WHERE id = ? AND person_id = ?",
             (time.time(), seconds, rid, ctx.person["id"]))
    return {"ok": True}


@route("POST", r"/keys")
def add_key(ctx):
    p = ctx.person
    if p["status"] != "active":
        raise ApiError(403, "Your access is paused. Talk to your admin.")
    if not _self_keys_allowed(ctx):
        raise ApiError(403, "Ask your admin to connect a new device for you.")
    if ctx.db.scalar("SELECT COUNT(*) FROM keys WHERE person_id = ? AND revoked IS NULL", (p["id"],)) >= 10:
        raise ApiError(400, "You have ten devices connected. Disconnect one you no longer use first.")
    label = str(ctx.body.get("label") or "").strip()[:80] or "My device"
    key_id, full, secret_hash, hint = security.new_key()
    ctx.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created, created_by) VALUES(?,?,?,?,?,?,?)",
             (key_id, p["id"], label, secret_hash, hint, time.time(), "self"))
    ctx.gw.audit(p["name"], "connected a device (issued own key)", p["name"], f"{label} ({hint})", ctx.ip)
    return {"id": key_id, "key": full, "hint": hint, "label": label, "tools": guides.guides(ctx.gw, full, ctx.gw.public_url(ctx.h))}


@route("POST", r"/keys/(?P<kid>[0-9a-f]{12})/revoke")
def revoke_key(ctx, kid):
    row = ctx.db.one("SELECT * FROM keys WHERE id = ? AND person_id = ?", (kid, ctx.person["id"]))
    if not row:
        raise ApiError(404, "No such device.")
    if not row["revoked"]:
        ctx.db.x("UPDATE keys SET revoked = ?, revoked_by = ? WHERE id = ?", (time.time(), "self", kid))
        ctx.gw.live.cut("this device was disconnected.", key_id=kid)
        ctx.gw.audit(ctx.person["name"], "disconnected a device (revoked own key)", ctx.person["name"],
                     f"{row['label']} ({row['hint']})", ctx.ip)
    return {"ok": True}


# ---------------------------------------------------------------- Studio: voice, image and video

VOICE_MODELS = [("eleven_multilingual_v2", "Multilingual — best quality"), ("eleven_flash_v2_5", "Flash — fastest")]
IMAGE_ENDPOINT = "flux-pro/kontext/max/text-to-image"
VIDEO_ENDPOINT = "v1/image2video/dop"


def _service(ctx, dialect):
    """The first configured provider of this kind that the person is allowed to use, or None."""
    allowed = [x.strip().lower() for x in (ctx.person.get("allowed_services") or "").split(",") if x.strip()]
    for p in ctx.gw.settings.providers.values():
        if p.dialect == dialect and p.api_key() and (not allowed or p.name.lower() in allowed):
            return p
    return None


def _through_gateway(ctx, provider, method, path, body=None, ref=None):
    """Call a provider the way any tool would — through this gateway — so the request is checked
    (paused, suspended, allowed services, budgets) and recorded like everything else."""
    gw = ctx.gw
    if gw.settings.tls_cert:
        conn = http.client.HTTPSConnection("127.0.0.1", gw.port, timeout=300, context=ssl._create_unverified_context())
    else:
        conn = http.client.HTTPConnection("127.0.0.1", gw.port, timeout=300)
    day = time.strftime("%Y%m%d", time.gmtime(time.time() + gw.settings.tz_offset_minutes * 60))
    headers = {"x-sgw-internal": gw.internal_secret, "x-sgw-person": str(ctx.person["id"]), "user-agent": "Swangz AI Studio",
               "x-session-id": f"studio-{ctx.person['id']}-{day}"}
    if ref:
        headers["x-sgw-ref"] = ref
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    try:
        conn.request(method, f"/{provider.name}{path}", body=data, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.getheader("content-type") or "", resp.read()
    except OSError:
        raise ApiError(502, "Couldn't reach the service. Try again in a moment.")
    finally:
        conn.close()


def _error_from(payload, fallback):
    try:
        d = json.loads(payload)
    except ValueError:
        return fallback
    if not isinstance(d, dict):
        return fallback
    err = d.get("error")
    if isinstance(err, dict) and err.get("message"):
        msg = str(err["message"]).replace("Swangz AI gateway: ", "")
        return msg[:1].upper() + msg[1:]
    detail = d.get("detail")
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("status")
    return str(detail) if detail else fallback


def _voices(ctx, provider):
    cached_at, voices = ctx.gw.voice_cache
    if voices and time.time() - cached_at < 600:
        return voices
    status, _, payload = _through_gateway(ctx, provider, "GET", "/v1/voices")
    if status != 200:
        return voices
    try:
        data = json.loads(payload)
    except ValueError:
        return voices
    voices = [{"id": v.get("voice_id"), "name": v.get("name"),
               "about": ", ".join(str(x) for x in (v.get("labels") or {}).values() if x)[:80]}
              for v in data.get("voices") or [] if isinstance(v, dict) and v.get("voice_id")]
    ctx.gw.voice_cache = (time.time(), voices)
    return voices


def _await_record(ctx, sql, args, tries=60):
    """The gateway writes a request's record just after it finishes replying; give it a moment."""
    for _ in range(tries):
        row = ctx.db.one(sql, args)
        if row:
            return row
        time.sleep(0.05)
    return None


def _creation(row):
    if not row:
        return {}
    return {"id": row["id"], "ts": row["ts"], "type": row["media_type"], "prompt": row["prompt"], "status": row["reply"],
            "outcome": row["outcome"], "reason": row["reason"],
            "job": row["turn_id"] if row["provider"] != "elevenlabs" else None,
            "urls": json.loads(row["result_urls"]) if row["result_urls"] else [],
            "audio": f"/api/studio/media/{row['id']}" if row["resp_blob"] and (row["resp_ctype"] or "").startswith("audio/") else None}


@route("GET", r"/studio")
def studio(ctx):
    voice, visual = _service(ctx, "elevenlabs"), _service(ctx, "higgsfield")
    recent = ctx.db.q("SELECT * FROM requests WHERE person_id = ? AND kind = 'media' AND client = 'Swangz AI Studio'"
                      " ORDER BY id DESC LIMIT 12", (ctx.person["id"],))
    return {"voice": bool(voice), "image": bool(visual), "video": bool(visual),
            "voices": _voices(ctx, voice) if voice else [],
            "voice_models": [{"id": m, "name": n} for m, n in VOICE_MODELS],
            "recent": [_creation(r) for r in recent]}


@route("POST", r"/studio/voice")
def studio_voice(ctx):
    provider = _service(ctx, "elevenlabs")
    if not provider:
        raise ApiError(403, "Voice isn't switched on for you.")
    text = str(ctx.body.get("text") or "").strip()
    voice = str(ctx.body.get("voice_id") or "").strip()
    model = str(ctx.body.get("model_id") or VOICE_MODELS[0][0])
    if not text:
        raise ApiError(400, "Type what you want spoken.")
    if len(text) > 5000:
        raise ApiError(400, "Keep it under 5,000 characters per clip.")
    if not re.fullmatch(r"[A-Za-z0-9]{6,64}", voice):
        raise ApiError(400, "Pick a voice.")
    ref = secrets.token_hex(8)
    status, ctype, payload = _through_gateway(ctx, provider, "POST", f"/v1/text-to-speech/{quote(voice)}?output_format=mp3_44100_128",
                                              {"text": text, "model_id": model}, ref)
    if status != 200 or not ctype.startswith("audio/"):
        raise ApiError(status if status >= 400 else 502, _error_from(payload, "The voice service didn't return audio."))
    return _creation(_await_record(ctx, "SELECT * FROM requests WHERE turn_id = ? AND person_id = ? AND resp_blob IS NOT NULL",
                                   (ref, ctx.person["id"])))


@route("POST", r"/studio/generate")
def studio_generate(ctx):
    provider = _service(ctx, "higgsfield")
    if not provider:
        raise ApiError(403, "Image and video aren't switched on for you.")
    kind = ctx.body.get("kind")
    prompt = str(ctx.body.get("prompt") or "").strip()
    if not prompt:
        raise ApiError(400, "Describe what you want to make.")
    if kind == "image":
        aspect = ctx.body.get("aspect_ratio") if ctx.body.get("aspect_ratio") in ("1:1", "16:9", "9:16", "4:5", "3:4") else "16:9"
        path, body = "/" + IMAGE_ENDPOINT, {"prompt": prompt, "aspect_ratio": aspect, "safety_tolerance": 2}
    elif kind == "video":
        image = str(ctx.body.get("image_url") or "").strip()
        if not image.startswith("https://"):
            raise ApiError(400, "A video starts from a picture: paste an https link to the image.")
        path, body = "/" + VIDEO_ENDPOINT, {"model": "dop-turbo", "prompt": prompt,
                                            "input_images": [{"type": "image_url", "image_url": image}]}
    else:
        raise ApiError(400, "Choose image or video.")
    ref = secrets.token_hex(8)
    status, _, payload = _through_gateway(ctx, provider, "POST", path, body, ref)
    if status >= 400:
        raise ApiError(status, _error_from(payload, "The service didn't accept that."))
    try:
        job = json.loads(payload).get("request_id")
    except (ValueError, AttributeError):
        job = None
    row = _await_record(ctx, "SELECT * FROM requests WHERE person_id = ? AND kind = 'media' AND turn_id IN (?, ?) ORDER BY id DESC",
                        (ctx.person["id"], job or ref, ref))
    return _creation(row)


@route("GET", r"/studio/jobs/(?P<job>[A-Za-z0-9_\-]{6,80})")
def studio_job(ctx, job):
    provider = _service(ctx, "higgsfield")
    row = ctx.db.one("SELECT * FROM requests WHERE turn_id = ? AND person_id = ? AND kind = 'media'", (job, ctx.person["id"]))
    if not provider or not row:
        raise ApiError(404, "No such job.")
    status, _, payload = _through_gateway(ctx, provider, "GET", f"/requests/{quote(job)}/status")
    if status >= 400:
        raise ApiError(status, _error_from(payload, "Couldn't check on that job."))
    try:
        data = json.loads(payload)
    except ValueError:
        data = {}
    result = parse.summarize_media_response("application/json", data if isinstance(data, dict) else None, len(payload))
    out = _creation(row)
    out.update(state=result["status"], urls=result["urls"] or out["urls"], status=result["reply"] or out["status"])
    return out


@route("GET", r"/studio/media/(?P<rid>\d+)")
def studio_media(ctx, rid):
    row = ctx.db.one("SELECT * FROM requests WHERE id = ? AND person_id = ?", (int(rid), ctx.person["id"]))
    data = store.load_response_bytes(ctx.db, row) if row else None
    if not data:
        raise ApiError(404, "Not found.")
    return data, row["resp_ctype"] or "audio/mpeg", {"Cache-Control": "private, max-age=3600"}
