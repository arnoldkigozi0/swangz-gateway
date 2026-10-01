"""The console's API. Viewers can see everything; only owners can change anything.

Every change — and every time someone opens a person's full record — is written to the audit log,
so the people doing the watching are watched too.
"""

import csv
import io
import json
import re
import time
from urllib.parse import parse_qs, unquote

from . import guides, proxy, security, store

SESSION_COOKIE = "sgw_admin"
SESSION_SECONDS = 12 * 3600
ROUTES = []


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def route(method, pattern, role="viewer"):
    def wrap(fn):
        ROUTES.append((method, re.compile(pattern), fn, role))
        return fn

    return wrap


class Ctx:
    def __init__(self, h, gw, query):
        self.h, self.gw, self.db = h, gw, gw.db
        self.query = {k: v[-1] for k, v in parse_qs(query).items()}
        self.ip = gw.client_ip(h)
        self.admin = None
        self.body = {}

    def arg(self, name, default=None, cast=str):
        if name not in self.query or self.query[name] == "":
            return default
        try:
            return cast(self.query[name])
        except ValueError:
            raise ApiError(400, f"bad value for {name}")

    def audit(self, action, target="", detail=""):
        self.gw.audit(self.admin["username"] if self.admin else "anonymous", action, target, detail, self.ip)


def dispatch(h, gw, path, query):
    sub = path[len("/admin/api"):]
    for method, rx, fn, role in ROUTES:
        m = rx.fullmatch(sub)
        if not m or method != h.command:
            continue
        ctx = Ctx(h, gw, query)
        try:
            if h.command != "GET" and h.headers.get("x-gateway-admin") != "1":
                raise ApiError(403, "missing console header")
            if role:
                ctx.admin = current_admin(ctx)
                if not ctx.admin:
                    raise ApiError(401, "sign in first")
                if role == "owner" and ctx.admin["role"] != "owner":
                    raise ApiError(403, "only an owner can do that")
            if h.command in ("POST", "PUT", "PATCH", "DELETE"):
                raw = h.read_body(1024 * 1024)
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
        if isinstance(result, tuple):  # (status, body, headers) or (bytes, ctype, headers)
            if isinstance(result[0], bytes):
                return h.send_bytes(200, result[0], result[1], result[2])
            return h.send_json(result[0], result[1], result[2] if len(result) > 2 else None)
        return h.send_json(200, result)
    return h.send_json(404, {"error": "no such endpoint"})


# ---------------------------------------------------------------- sessions


def current_admin(ctx):
    token = _cookie(ctx.h.headers.get("cookie") or "", SESSION_COOKIE)
    if not token:
        return None
    row = ctx.db.one(
        "SELECT a.id, a.username, a.role FROM admin_sessions s JOIN admins a ON a.id = s.admin_id"
        " WHERE s.token_hash = ? AND s.expires > ?", (security.sha256(token), time.time()))
    return row


def _cookie(header, name):
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def _session_cookie(ctx, token, max_age):
    flags = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
    if ctx.gw.secure_request(ctx.h):
        flags += "; Secure"
    return flags


@route("POST", r"/login", role=None)
def login(ctx):
    username = str(ctx.body.get("username") or "").strip()
    password = str(ctx.body.get("password") or "")
    if ctx.gw.throttle.blocked(ctx.ip):
        raise ApiError(429, "too many failed sign-ins from here; wait ten minutes")
    row = ctx.db.one("SELECT * FROM admins WHERE username = ?", (username,))
    if not row or not security.check_password(password, row["pw_hash"]):
        ctx.gw.throttle.fail(ctx.ip)
        ctx.gw.audit(username or "?", "failed sign-in", "", "", ctx.ip)
        raise ApiError(401, "wrong username or password")
    ctx.gw.throttle.clear(ctx.ip)
    token = security.new_session_token()
    now = time.time()
    ctx.db.x("INSERT INTO admin_sessions(token_hash, admin_id, created, expires, ip) VALUES(?,?,?,?,?)",
             (security.sha256(token), row["id"], now, now + SESSION_SECONDS, ctx.ip))
    ctx.db.x("UPDATE admins SET last_login = ? WHERE id = ?", (now, row["id"]))
    ctx.admin = row
    ctx.audit("signed in")
    return 200, {"username": row["username"], "role": row["role"]}, {"Set-Cookie": _session_cookie(ctx, token, SESSION_SECONDS)}


@route("POST", r"/logout", role=None)
def logout(ctx):
    token = _cookie(ctx.h.headers.get("cookie") or "", SESSION_COOKIE)
    if token:
        ctx.db.x("DELETE FROM admin_sessions WHERE token_hash = ?", (security.sha256(token),))
    return 200, {"ok": True}, {"Set-Cookie": _session_cookie(ctx, "", 0)}


@route("GET", r"/me")
def me(ctx):
    return {"username": ctx.admin["username"], "role": ctx.admin["role"], "base_url": ctx.gw.public_url(ctx.h),
            "providers": _providers(ctx), "tz_offset_minutes": ctx.gw.settings.tz_offset_minutes}


@route("POST", r"/password")
def change_password(ctx):
    row = ctx.db.one("SELECT * FROM admins WHERE id = ?", (ctx.admin["id"],))
    if not security.check_password(str(ctx.body.get("current") or ""), row["pw_hash"]):
        raise ApiError(400, "the current password is wrong")
    new = str(ctx.body.get("new") or "")
    _check_password_strength(new)
    ctx.db.x("UPDATE admins SET pw_hash = ? WHERE id = ?",
             (security.hash_password(new, ctx.gw.settings.pbkdf2_iterations), row["id"]))
    ctx.audit("changed own password")
    return {"ok": True}


def _check_password_strength(pw):
    if len(pw) < 10:
        raise ApiError(400, "use at least 10 characters")


# ---------------------------------------------------------------- overview


def _providers(ctx):
    return [{"name": p.name, "label": p.label, "dialect": p.dialect, "chat": p.is_chat, "configured": bool(p.api_key()),
             "upstream": p.base_url, "key_env": p.key_env} for p in ctx.gw.settings.providers.values()]


def _totals(db, since):
    row = db.one(
        "SELECT COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost,"
        " COALESCE(SUM(in_tok + out_tok + cache_write_tok + cache_read_tok), 0) AS tokens,"
        " COUNT(DISTINCT person_id) AS people,"
        " SUM(outcome = 'blocked') AS blocked, SUM(outcome = 'denied') AS denied, SUM(outcome = 'cut') AS cut,"
        " SUM(outcome = 'error') AS errors, SUM(flags LIKE '%secret:%') AS secrets,"
        " SUM(cost IS NULL AND kind NOT IN ('other', 'media-status') AND outcome = 'ok') AS unpriced"
        " FROM requests WHERE ts >= ? AND (kind NOT IN ('other', 'media-status') OR outcome != 'ok')", (since,))
    return {k: (v or 0) for k, v in row.items()}


@route("GET", r"/overview")
def overview(ctx):
    db = ctx.db
    now = time.time()
    day, month = proxy.period_starts(now, ctx.gw.settings.tz_offset_minutes)
    people_today = db.q(
        "SELECT p.id, p.name, p.department, COUNT(r.id) AS requests, COALESCE(SUM(r.cost), 0) AS cost,"
        " MAX(r.ts) AS last FROM requests r JOIN people p ON p.id = r.person_id"
        " WHERE r.ts >= ? AND r.kind NOT IN ('other', 'media-status') GROUP BY p.id ORDER BY cost DESC, requests DESC", (day,))
    models = db.q(
        "SELECT model, provider, COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost,"
        " SUM(cost IS NULL) AS unpriced, SUM(in_tok + out_tok + cache_write_tok + cache_read_tok) AS tokens"
        " FROM requests WHERE ts >= ? AND kind NOT IN ('other', 'media-status') AND model IS NOT NULL"
        " GROUP BY model, provider ORDER BY cost DESC, requests DESC LIMIT 20", (month,))
    clients = db.q(
        "SELECT client, COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost FROM requests"
        " WHERE ts >= ? AND kind NOT IN ('other', 'media-status') GROUP BY client ORDER BY requests DESC", (month,))
    return {
        "now": now, "day_start": day, "month_start": month,
        "paused": db.get_setting("paused", "0") == "1",
        "today": _totals(db, day), "month": _totals(db, month),
        "live": ctx.gw.live.snapshot(),
        "people_today": people_today, "models_month": models, "clients_month": clients,
        "providers": _providers(ctx),
    }


# ---------------------------------------------------------------- requests

LIST_COLUMNS = ("r.id, r.ts, r.person_id, p.name AS person, r.key_id, r.provider, r.kind, r.client, r.session,"
                " r.model, r.stream, r.status, r.outcome, r.reason, r.duration_ms, r.ttft_ms, r.in_tok, r.out_tok,"
                " r.cache_write_tok, r.cache_read_tok, r.reasoning_tok, r.cost, r.prompt, r.actions, r.reply,"
                " r.flags, r.client_ip, r.request_class, r.agent, r.turn_id, r.media_type, r.units, r.unit, r.result_urls,"
                " r.resp_ctype")


def _shape(row, clip=600):
    row = dict(row)
    row["actions"] = json.loads(row["actions"]) if row.get("actions") else []
    if "result_urls" in row:
        row["result_urls"] = json.loads(row["result_urls"]) if row.get("result_urls") else []
    for k in ("prompt", "reply"):
        if clip and row.get(k) and len(row[k]) > clip:
            row[k] = row[k][: clip - 1] + "…"
    return row


@route("GET", r"/requests")
def list_requests(ctx):
    where, args = [], []
    for name, col, cast in (("person", "r.person_id", int), ("session", "r.session", str),
                            ("client", "r.client", str), ("outcome", "r.outcome", str), ("model", "r.model", str),
                            ("key", "r.key_id", str)):
        value = ctx.arg(name, cast=cast)
        if value is not None:
            where.append(f"{col} = ?")
            args.append(value)
    if ctx.arg("before", cast=int):
        where.append("r.id < ?")
        args.append(ctx.arg("before", cast=int))
    if ctx.arg("after", cast=int) is not None:
        where.append("r.id > ?")
        args.append(ctx.arg("after", cast=int))
    if ctx.arg("since", cast=float):
        where.append("r.ts >= ?")
        args.append(ctx.arg("since", cast=float))
    if ctx.arg("kind") in ("media", "messages", "chat", "responses"):
        where.append("r.kind = ?")
        args.append(ctx.arg("kind"))
    if ctx.arg("flag") == "secret":
        where.append("r.flags LIKE '%secret:%'")
    if ctx.arg("only") == "prompts":
        where.append("r.prompt IS NOT NULL")
    q = ctx.arg("q")
    if q:
        where.append("(r.prompt LIKE ? OR r.reply LIKE ? OR r.actions LIKE ?)")
        like = "%" + q.replace("%", "").replace("_", "") + "%"
        args += [like, like, like]
    if not ctx.arg("all"):
        where.append("(r.kind NOT IN ('other', 'media-status') OR r.outcome != 'ok')")
    limit = max(1, min(ctx.arg("limit", 50, int), 500))
    sql = (f"SELECT {LIST_COLUMNS} FROM requests r LEFT JOIN people p ON p.id = r.person_id"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY r.id DESC LIMIT ?")
    rows = ctx.db.q(sql, args + [limit + 1])
    return {"items": [_shape(r) for r in rows[:limit]], "more": len(rows) > limit}


@route("GET", r"/requests/(?P<rid>\d+)")
def get_request(ctx, rid):
    row = ctx.db.one(
        f"SELECT {LIST_COLUMNS}, r.method, r.path, r.user_agent, r.req_bytes, r.resp_bytes, r.req_head, r.req_items,"
        " r.req_list_field, r.resp_blob, r.resp_format, k.label AS key_label"
        " FROM requests r LEFT JOIN people p ON p.id = r.person_id LEFT JOIN keys k ON k.id = r.key_id WHERE r.id = ?",
        (int(rid),))
    if not row:
        raise ApiError(404, "no such record")
    request_body = store.load_request_body(ctx.db, row)
    response_body = store.load_response(ctx.db, row)
    out = _shape({k: v for k, v in row.items() if k not in ("req_head", "req_items", "resp_blob")}, clip=0)
    out["request"] = request_body
    out["response"] = response_body
    out["stored"] = request_body is not None or response_body is not None
    ctx.audit("opened the full record", f"request #{rid}", f"person: {row.get('person') or '-'}")
    if ctx.arg("download"):
        data = json.dumps({"record": out}, indent=2, default=str).encode()
        return data, "application/json", {"Content-Disposition": f'attachment; filename="swangz-ai-record-{rid}.json"',
                                           "Cache-Control": "no-store"}
    return out


@route("GET", r"/requests/(?P<rid>\d+)/media")
def get_media(ctx, rid):
    """Play back what a voice/sound service returned (stored as received)."""
    row = ctx.db.one("SELECT r.id, r.resp_blob, r.resp_ctype, p.name AS person FROM requests r"
                     " LEFT JOIN people p ON p.id = r.person_id WHERE r.id = ?", (int(rid),))
    data = store.load_response_bytes(ctx.db, row) if row else None
    if not data:
        raise ApiError(404, "nothing stored for this request")
    ctx.audit("played back a generation", f"request #{rid}", f"person: {row['person'] or '-'}")
    return data, (row["resp_ctype"] or "application/octet-stream"), {"Cache-Control": "no-store"}


@route("GET", r"/sessions/(?P<sid>[^/]+)")
def get_session(ctx, sid):
    rows = ctx.db.q(f"SELECT {LIST_COLUMNS} FROM requests r LEFT JOIN people p ON p.id = r.person_id"
                    " WHERE r.session = ? AND (r.kind NOT IN ('other', 'media-status') OR r.outcome != 'ok') ORDER BY r.id ASC LIMIT 2000", (sid,))
    if not rows:
        raise ApiError(404, "no such session")
    items = [_shape(r, clip=0) for r in rows]
    return {"session": sid, "person": rows[0]["person"], "person_id": rows[0]["person_id"],
            "client": rows[0]["client"], "items": items,
            "cost": sum(r["cost"] or 0 for r in rows), "started": rows[0]["ts"], "last": rows[-1]["ts"]}


@route("POST", r"/live/(?P<tid>\d+)/cut", role="owner")
def cut_live(ctx, tid):
    n = ctx.gw.live.cut("an administrator stopped this request.", ticket_id=int(tid))
    ctx.audit("stopped a request in flight", f"live #{tid}")
    return {"cut": n}


# ---------------------------------------------------------------- people and keys

PERSON_FIELDS = ("name", "email", "department", "title", "daily_budget", "monthly_budget", "allowed_models",
                 "allowed_services", "notes")


def _person_values(body, partial):
    values = {}
    for field in PERSON_FIELDS:
        if field not in body:
            continue
        v = body[field]
        if field in ("daily_budget", "monthly_budget"):
            if v in (None, ""):
                v = None
            else:
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    raise ApiError(400, f"{field} must be a number of dollars")
                if v < 0:
                    raise ApiError(400, f"{field} cannot be negative")
        else:
            v = str(v or "").strip()
        values[field] = v
    if values.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["email"]):
        raise ApiError(400, "that email address doesn't look right")
    if not partial and not values.get("name"):
        raise ApiError(400, "a person needs a name")
    if partial and "name" in values and not values["name"]:
        raise ApiError(400, "a person needs a name")
    return values


def _email_free(ctx, email, person_id=None):
    if email and ctx.db.one("SELECT id FROM people WHERE lower(email) = lower(?) AND id != ?", (email, person_id or -1)):
        raise ApiError(400, "someone else already uses that email")


def _sign_in_state(p):
    if p.get("pw_hash"):
        return "active"
    if p.get("invite_expires") and p["invite_expires"] > time.time():
        return "invited"
    return "none"


def _spend_map(db, since):
    return {r["person_id"]: r for r in db.q(
        "SELECT person_id, COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost, MAX(ts) AS last FROM requests"
        " WHERE ts >= ? AND kind NOT IN ('other', 'media-status') GROUP BY person_id", (since,))}


@route("GET", r"/people")
def list_people(ctx):
    day, month = proxy.period_starts(time.time(), ctx.gw.settings.tz_offset_minutes)
    today, this_month = _spend_map(ctx.db, day), _spend_map(ctx.db, month)
    last = {r["person_id"]: r["last"] for r in ctx.db.q("SELECT person_id, MAX(ts) AS last FROM requests GROUP BY person_id")}
    live = {}
    for t in ctx.gw.live.snapshot():
        live[t["person_id"]] = live.get(t["person_id"], 0) + 1
    people = ctx.db.q(
        "SELECT p.*, (SELECT COUNT(*) FROM keys k WHERE k.person_id = p.id AND k.revoked IS NULL) AS active_keys"
        " FROM people p ORDER BY p.status, p.name COLLATE NOCASE")
    for p in people:
        p["sign_in"] = _sign_in_state(p)
        for secret in ("pw_hash", "invite_hash"):
            p.pop(secret, None)
        p["today"] = {"requests": today.get(p["id"], {}).get("requests", 0), "cost": today.get(p["id"], {}).get("cost", 0)}
        p["month"] = {"requests": this_month.get(p["id"], {}).get("requests", 0), "cost": this_month.get(p["id"], {}).get("cost", 0)}
        p["last_seen"] = last.get(p["id"])
        p["live"] = live.get(p["id"], 0)
    return {"items": people}


@route("POST", r"/people", role="owner")
def create_person(ctx):
    values = _person_values(ctx.body, partial=False)
    _email_free(ctx, values.get("email"))
    values["created"] = time.time()
    cols = list(values)
    cur = ctx.db.x(f"INSERT INTO people({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [values[c] for c in cols])
    ctx.audit("added a person", values["name"])
    return {"id": cur.lastrowid}


@route("GET", r"/people/(?P<pid>\d+)")
def get_person(ctx, pid):
    pid = int(pid)
    person = ctx.db.one("SELECT * FROM people WHERE id = ?", (pid,))
    if not person:
        raise ApiError(404, "no such person")
    person["sign_in"] = _sign_in_state(person)
    for secret in ("pw_hash", "invite_hash"):
        person.pop(secret, None)
    day, month = proxy.period_starts(time.time(), ctx.gw.settings.tz_offset_minutes)
    person["keys"] = ctx.db.q("SELECT id, label, hint, created, created_by, revoked, revoked_by, last_used"
                              " FROM keys WHERE person_id = ? ORDER BY revoked IS NOT NULL, created DESC", (pid,))
    person["today"] = {"cost": ctx.gw.spend(pid, day)}
    person["month"] = {"cost": ctx.gw.spend(pid, month)}
    person["sessions"] = ctx.db.q(
        "SELECT session, MIN(ts) AS started, MAX(ts) AS last, COUNT(*) AS requests, COALESCE(SUM(cost), 0) AS cost,"
        " MAX(client) AS client, (SELECT prompt FROM requests r2 WHERE r2.session = r.session AND r2.prompt IS NOT NULL"
        " ORDER BY r2.id LIMIT 1) AS first_prompt FROM requests r WHERE person_id = ? AND session IS NOT NULL"
        " AND kind NOT IN ('other', 'media-status') GROUP BY session ORDER BY last DESC LIMIT 40", (pid,))
    person["live"] = [t for t in ctx.gw.live.snapshot() if t["person_id"] == pid]
    return person


@route("PATCH", r"/people/(?P<pid>\d+)", role="owner")
def update_person(ctx, pid):
    values = _person_values(ctx.body, partial=True)
    if not values:
        return {"ok": True}
    if not ctx.db.one("SELECT id FROM people WHERE id = ?", (int(pid),)):
        raise ApiError(404, "no such person")
    _email_free(ctx, values.get("email"), int(pid))
    ctx.db.x(f"UPDATE people SET {', '.join(f'{c} = ?' for c in values)} WHERE id = ?", [*values.values(), int(pid)])
    ctx.audit("changed a person", f"person #{pid}", json.dumps(values, default=str))
    return {"ok": True}


@route("POST", r"/people/(?P<pid>\d+)/(?P<action>suspend|resume)", role="owner")
def suspend_person(ctx, pid, action):
    pid = int(pid)
    person = ctx.db.one("SELECT name FROM people WHERE id = ?", (pid,))
    if not person:
        raise ApiError(404, "no such person")
    ctx.db.x("UPDATE people SET status = ? WHERE id = ?", ("suspended" if action == "suspend" else "active", pid))
    cut = 0
    if action == "suspend":
        cut = ctx.gw.live.cut("this person's AI access was suspended by an administrator.", person_id=pid)
        ctx.db.x("DELETE FROM staff_sessions WHERE person_id = ?", (pid,))
    ctx.audit("suspended a person" if action == "suspend" else "restored a person", person["name"],
              f"{cut} request(s) cut" if cut else "")
    return {"ok": True, "cut": cut}


@route("POST", r"/people/(?P<pid>\d+)/keys", role="owner")
def issue_key(ctx, pid):
    pid = int(pid)
    person = ctx.db.one("SELECT name FROM people WHERE id = ?", (pid,))
    if not person:
        raise ApiError(404, "no such person")
    label = str(ctx.body.get("label") or "").strip()[:80] or "key"
    key_id, full, secret_hash, hint = security.new_key()
    ctx.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created, created_by) VALUES(?,?,?,?,?,?,?)",
             (key_id, pid, label, secret_hash, hint, time.time(), ctx.admin["username"]))
    ctx.audit("issued a key", person["name"], f"{label} ({hint})")
    return {"id": key_id, "key": full, "hint": hint, "label": label, "tools": guides.guides(ctx.gw, full, ctx.gw.public_url(ctx.h))}


@route("POST", r"/people/(?P<pid>\d+)/invite", role="owner")
def invite_person(ctx, pid):
    person = ctx.db.one("SELECT name, email FROM people WHERE id = ?", (int(pid),))
    if not person:
        raise ApiError(404, "no such person")
    if not person["email"]:
        raise ApiError(400, "add their email first — it is what they sign in with")
    from . import staff  # staff builds on this module's ApiError and Ctx

    token = staff.new_invite(ctx.db, int(pid))
    link = f"{ctx.gw.public_url(ctx.h)}/#/welcome/{token}"
    ctx.audit("created a sign-in link", person["name"], "valid 7 days")
    return {"link": link, "expires_days": 7, "email": person["email"]}


@route("POST", r"/keys/(?P<kid>[0-9a-f]{12})/revoke", role="owner")
def revoke_key(ctx, kid):
    row = ctx.db.one("SELECT k.*, p.name FROM keys k JOIN people p ON p.id = k.person_id WHERE k.id = ?", (kid,))
    if not row:
        raise ApiError(404, "no such key")
    if not row["revoked"]:
        ctx.db.x("UPDATE keys SET revoked = ?, revoked_by = ? WHERE id = ?", (time.time(), ctx.admin["username"], kid))
    cut = ctx.gw.live.cut("this key was revoked by an administrator.", key_id=kid)
    ctx.audit("revoked a key", row["name"], f"{row['label']} ({row['hint']})" + (f", {cut} request(s) cut" if cut else ""))
    return {"ok": True, "cut": cut}


# ---------------------------------------------------------------- the switch, settings, prices


@route("POST", r"/pause", role="owner")
def pause(ctx):
    paused = bool(ctx.body.get("paused"))
    ctx.db.set_setting("paused", "1" if paused else "0")
    cut = ctx.gw.live.cut("AI access was paused for everyone by an administrator.", everything=True) if paused else 0
    ctx.audit("paused AI access for everyone" if paused else "resumed AI access for everyone", "", f"{cut} request(s) cut" if cut else "")
    return {"paused": paused, "cut": cut}


@route("GET", r"/settings")
def get_settings(ctx):
    db = ctx.db
    return {"paused": db.get_setting("paused", "0") == "1",
            "retention_days": int(db.get_setting("retention_days", "90") or 0),
            "block_secrets": db.get_setting("block_secrets", "0") == "1",
            "store_bodies": db.get_setting("store_bodies", "1") == "1",
            "staff_self_keys": db.get_setting("staff_self_keys", "1") == "1",
            "providers": _providers(ctx), "base_url": ctx.gw.public_url(ctx.h),
            "tz_offset_minutes": ctx.gw.settings.tz_offset_minutes,
            "db_bytes": (db.scalar("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()") or 0),
            "records": db.scalar("SELECT COUNT(*) FROM requests") or 0}


@route("PUT", r"/settings", role="owner")
def put_settings(ctx):
    changed = {}
    if "retention_days" in ctx.body:
        try:
            days = int(ctx.body["retention_days"])
        except (TypeError, ValueError):
            raise ApiError(400, "retention_days must be a whole number (0 = keep forever)")
        if days < 0:
            raise ApiError(400, "retention_days cannot be negative")
        changed["retention_days"] = days
    for flag in ("block_secrets", "store_bodies", "staff_self_keys"):
        if flag in ctx.body:
            changed[flag] = "1" if ctx.body[flag] else "0"
    for k, v in changed.items():
        ctx.db.set_setting(k, v)
    if changed:
        ctx.audit("changed settings", "", json.dumps(changed))
    return {"ok": True}


@route("GET", r"/prices")
def list_prices(ctx):
    used = {r["model"]: r for r in ctx.db.q(
        "SELECT model, COUNT(*) AS requests, SUM(cost IS NULL) AS unpriced FROM requests"
        " WHERE model IS NOT NULL AND kind NOT IN ('other', 'media-status') GROUP BY model")}
    rows = ctx.db.q("SELECT * FROM prices ORDER BY provider, model")
    listed = {r["model"] for r in rows}
    missing = [m for m, r in used.items() if r["unpriced"] and m not in listed]
    return {"items": rows, "unpriced_models": sorted(missing)}


@route("PUT", r"/prices/(?P<model>[^/]+)", role="owner")
def put_price(ctx, model):
    fields = {}
    for k in ("input", "output", "cache_write", "cache_write_1h", "cache_read"):
        v = ctx.body.get(k)
        if v in (None, ""):
            if k in ("input", "output"):
                raise ApiError(400, f"{k} price is required")
            fields[k] = None
            continue
        try:
            fields[k] = float(v)
        except (TypeError, ValueError):
            raise ApiError(400, f"{k} must be dollars per million tokens")
        if fields[k] < 0:
            raise ApiError(400, "prices cannot be negative")
    ctx.db.x("INSERT OR REPLACE INTO prices(model, provider, input, output, cache_write, cache_write_1h, cache_read, updated)"
             " VALUES(?,?,?,?,?,?,?,?)", (model, str(ctx.body.get("provider") or ""), fields["input"], fields["output"],
                                          fields["cache_write"], fields["cache_write_1h"], fields["cache_read"], time.time()))
    ctx.gw.reload_prices()
    ctx.audit("set a model price", model, json.dumps(fields))
    return {"ok": True}


@route("DELETE", r"/prices/(?P<model>[^/]+)", role="owner")
def delete_price(ctx, model):
    ctx.db.x("DELETE FROM prices WHERE model = ?", (model,))
    ctx.gw.reload_prices()
    ctx.audit("removed a model price", model)
    return {"ok": True}


# ---------------------------------------------------------------- admins and the audit log


@route("GET", r"/admins", role="owner")
def list_admins(ctx):
    return {"items": ctx.db.q("SELECT id, username, role, created, last_login FROM admins ORDER BY username")}


@route("POST", r"/admins", role="owner")
def add_admin(ctx):
    username = str(ctx.body.get("username") or "").strip()
    role = ctx.body.get("role") or "viewer"
    if not re.fullmatch(r"[A-Za-z0-9._@-]{2,64}", username):
        raise ApiError(400, "username: 2-64 letters, digits, . _ @ -")
    if role not in ("owner", "viewer"):
        raise ApiError(400, "role must be owner or viewer")
    password = str(ctx.body.get("password") or "")
    _check_password_strength(password)
    if ctx.db.one("SELECT id FROM admins WHERE username = ?", (username,)):
        raise ApiError(400, "that username is taken")
    ctx.db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
             (username, security.hash_password(password, ctx.gw.settings.pbkdf2_iterations), role, time.time()))
    ctx.audit("added a console user", username, role)
    return {"ok": True}


@route("DELETE", r"/admins/(?P<aid>\d+)", role="owner")
def remove_admin(ctx, aid):
    aid = int(aid)
    if aid == ctx.admin["id"]:
        raise ApiError(400, "you cannot remove yourself")
    row = ctx.db.one("SELECT username, role FROM admins WHERE id = ?", (aid,))
    if not row:
        raise ApiError(404, "no such console user")
    if row["role"] == "owner" and ctx.db.scalar("SELECT COUNT(*) FROM admins WHERE role = 'owner'") <= 1:
        raise ApiError(400, "keep at least one owner")
    ctx.db.x("DELETE FROM admins WHERE id = ?", (aid,))
    ctx.audit("removed a console user", row["username"])
    return {"ok": True}


@route("GET", r"/audit")
def list_audit(ctx):
    limit = max(1, min(ctx.arg("limit", 100, int), 500))
    before = ctx.arg("before", cast=int)
    rows = ctx.db.q("SELECT * FROM audit" + (" WHERE id < ?" if before else "") + " ORDER BY id DESC LIMIT ?",
                    ([before] if before else []) + [limit + 1])
    return {"items": rows[:limit], "more": len(rows) > limit}


@route("GET", r"/export\.csv")
def export_csv(ctx):
    since = ctx.arg("since", 0.0, float)
    until = ctx.arg("until", time.time() + 1, float)
    person = ctx.arg("person", cast=int)
    sql = ("SELECT r.*, p.name AS person, p.department FROM requests r LEFT JOIN people p ON p.id = r.person_id"
           " WHERE r.ts >= ? AND r.ts < ?" + (" AND r.person_id = ?" if person else "") + " ORDER BY r.id")
    rows = ctx.db.q(sql, [since, until] + ([person] if person else []))
    offset = ctx.gw.settings.tz_offset_minutes * 60
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "time", "person", "department", "tool", "provider", "model", "session", "outcome", "reason",
                "input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens", "cost_usd", "prompt",
                "actions", "flags", "ip"])
    for r in rows:
        actions = " | ".join(a["text"] for a in json.loads(r["actions"])) if r["actions"] else ""
        w.writerow([r["id"], time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["ts"] + offset)), r["person"] or "",
                    r["department"] or "", r["client"], r["provider"], r["model"] or "", r["session"] or "",
                    r["outcome"], r["reason"] or "", r["in_tok"], r["out_tok"], r["cache_write_tok"], r["cache_read_tok"],
                    "" if r["cost"] is None else f"{r['cost']:.6f}", _csv_safe(r["prompt"]), _csv_safe(actions),
                    r["flags"], r["client_ip"]])
    ctx.audit("exported records", f"{len(rows)} rows")
    return (buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="swangz-ai-activity.csv"', "Cache-Control": "no-store"})


def _csv_safe(text):
    """Spreadsheets run cells that start with = + - @ as formulas; prompts are untrusted text."""
    text = text or ""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
