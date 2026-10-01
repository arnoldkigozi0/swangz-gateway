"""The staff app's API: sign in, connect a tool, look after your own devices.

For staff, Swangz AI is simply how they reach AI tools at work. This API only ever returns the
signed-in person's own profile, budget and keys.
"""

import json
import re
import secrets
import time
from urllib.parse import unquote

from . import guides, proxy, security
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
            return h.send_json(result[0], result[1], result[2] if len(result) > 2 else None)
        return h.send_json(200, result)
    return h.send_json(404, {"error": "no such endpoint"})


def current_person(ctx):
    token = _cookie(ctx.h.headers.get("cookie") or "", COOKIE)
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
    value = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
    if ctx.gw.settings.secure_cookies:
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
    p = ctx.person
    day, month = proxy.period_starts(time.time(), ctx.gw.settings.tz_offset_minutes)
    keys = ctx.db.q("SELECT id, label, hint, created, last_used, revoked FROM keys WHERE person_id = ?"
                    " ORDER BY revoked IS NOT NULL, created DESC", (p["id"],))
    models = [m.strip() for m in (p["allowed_models"] or "").replace("\n", ",").split(",") if m.strip()]
    return {
        "name": p["name"], "email": p["email"],
        "title": p["title"], "department": p["department"],
        "active": p["status"] == "active" and ctx.db.get_setting("paused", "0") != "1",
        "suspended": p["status"] != "active", "paused": ctx.db.get_setting("paused", "0") == "1",
        "budget": {"daily": p["daily_budget"], "monthly": p["monthly_budget"],
                   "today": ctx.gw.spend(p["id"], day), "month": ctx.gw.spend(p["id"], month)},
        "models": models,
        "keys": keys,
        "can_add_keys": _self_keys_allowed(ctx) and p["status"] == "active",
        "tools": guides.guides(ctx.gw),
        "base_url": ctx.gw.settings.base_url(),
    }


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
    return {"id": key_id, "key": full, "hint": hint, "label": label, "tools": guides.guides(ctx.gw, full)}


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
