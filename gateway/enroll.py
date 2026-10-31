"""The Swangz app on people's own devices: enrolment, what each device is offered, and check-ins.

A person installs the Swangz app on any device (company-owned or their own), runs "sign in", and
approves it from the Swangz AI Hub in their browser with a short code — the device-code flow, so no
password or key is ever typed or pasted on the device:

  1. the app asks for a code                         POST /api/device/code      (nobody signed in yet)
  2. the person opens /device, checks what is asking and approves it (their own signed-in browser)
  3. the app collects its key, once                  POST /api/device/token
  4. the app asks what this person is offered        GET  /api/device/manifest   (Bearer: its key)
  5. the app downloads what it needs and checks in   GET  /api/device/packages/…, POST /api/device/heartbeat

An enrolled device *is* a gateway key (`keys`) with a row of facts beside it (`devices`), so budgets,
policies, the kill switch, "disconnect this device" and the control room's Devices page all apply
unchanged. What the app is offered is worked out by the server from the same rule as everything else
(company subscription active **and** the person assigned): the app only installs what it is told, and a
withdrawn right is gone at the next check-in.

What is recorded about a device is its name, operating system, app version, which packages are
installed and when it last checked in — plus, as always, every AI request that goes through the
gateway. Never files, screens, keystrokes or other programs on the device. On a *personal* device the
app changes nothing outside its own folder and a command it runs for the person (`swangz run …`);
only a *company* device has its coding agents pointed at the gateway for good.
"""

import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import shutil
import time
import zipfile
from urllib.parse import parse_qs, quote

from . import entitle, security
from .admin import ApiError
from .admin import route as admin_route
from .staff import COOKIE, Ctx, _cookie, current_person, route

CLIENT_LATEST = "0.1.0"
CLIENT_MINIMUM = "0.1.0"
CODE_SECONDS = 15 * 60
POLL_SECONDS = 3
MAX_DEVICES = 10
CODES_PER_HOUR = 30
USER_CODE_ALPHABET = "BCDFGHJKMNPQRSTVWXZ23456789"  # no vowels (no words) and nothing easily misread
PACKAGE_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,59}")
PACKAGE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,31}")
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
PLATFORMS = ("windows", "macos", "linux", "android", "ios")
OWNER_KINDS = ("personal", "company")

RECORDING = ("Swangz AI Hub records this device's name, operating system, app version, the packages installed "
             "on it and when it last checked in, and every AI request sent through the company gateway "
             "(who, which tool, model, tokens, cost). It never reads your files, screen, keystrokes or other "
             "programs.")


# ---------------------------------------------------------------- small helpers


def _os_name(text):
    t = (text or "").lower()
    for key, name in (("win", "windows"), ("darwin", "macos"), ("mac", "macos"), ("linux", "linux"),
                      ("android", "android"), ("ios", "ios"), ("iphone", "ios")):
        if key in t:
            return name
    return ""


def _clean(text, limit):
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "")).strip()[:limit]


def _version(text):
    text = str(text or "").strip()
    return text if re.fullmatch(r"[0-9A-Za-z._+-]{1,32}", text) else ""


def _new_user_code():
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def normalise_code(text):
    raw = re.sub(r"[^A-Za-z0-9]", "", str(text or "")).upper()
    return raw[:4] + "-" + raw[4:] if len(raw) == 8 and all(c in USER_CODE_ALPHABET for c in raw) else ""


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _data_dir(gw):
    return os.path.join(gw.settings.data_dir, "packages")


def package_path(gw, pid, version):
    return os.path.join(_data_dir(gw), pid, version + ".zip")


# ---------------------------------------------------------------- 1. the app asks for a code


@route("POST", r"/device/code", signed_in=False)
def device_code(ctx):
    """Start a sign-in from a device. Returns a long secret for the app to poll with and a short code for the
    person to enter, on a page of their own signed-in browser."""
    db = ctx.db
    if ctx.gw.throttle.blocked("devcode:" + ctx.ip):
        raise ApiError(429, "Too many attempts. Wait a few minutes.", "slow_down")
    if db.scalar("SELECT COUNT(*) FROM device_codes WHERE ip = ? AND created > ?", (ctx.ip, time.time() - 3600)) >= CODES_PER_HOUR:
        raise ApiError(429, "Too many sign-in attempts from this address. Try again later.", "slow_down")
    device = secrets.token_urlsafe(32)
    now = time.time()
    for _ in range(5):  # a clash on 27^8 is rare enough to simply try again
        code = _new_user_code()
        if not db.one("SELECT 1 FROM device_codes WHERE user_code = ?", (code,)):
            break
    label = _clean(ctx.body.get("name"), 80)
    db.x("INSERT INTO device_codes(device_hash, user_code, created, expires, label, os, arch, app_version, ip)"
         " VALUES(?,?,?,?,?,?,?,?,?)",
         (security.sha256(device), code, now, now + CODE_SECONDS, label, _os_name(ctx.body.get("os")) or _clean(ctx.body.get("os"), 20).lower(),
          _clean(ctx.body.get("arch"), 20), _version(ctx.body.get("app_version")), ctx.ip))
    base = ctx.gw.public_url(ctx.h)
    return {"device_code": device, "user_code": code, "verification_uri": base + "/device",
            "verification_uri_complete": base + "/device?code=" + quote(code), "interval": POLL_SECONDS, "expires_in": CODE_SECONDS}


# ---------------------------------------------------------------- 3. the app collects its key, once


@route("POST", r"/device/token", signed_in=False)
def device_token(ctx):
    db = ctx.db
    if ctx.gw.throttle.blocked("devtoken:" + ctx.ip):
        raise ApiError(429, "Too many attempts. Wait a few minutes.", "slow_down")
    secret = str(ctx.body.get("device_code") or "")
    row = db.one("SELECT * FROM device_codes WHERE device_hash = ?", (security.sha256(secret),)) if len(secret) >= 32 else None
    if not row:
        ctx.gw.throttle.fail("devtoken:" + ctx.ip)
        raise ApiError(400, "That sign-in code is not known. Start again.", "invalid_grant")
    now = time.time()
    if row["status"] in ("pending", "approved") and row["expires"] < now:
        raise ApiError(400, "That sign-in expired. Start again.", "expired_token")
    if row["status"] == "denied":
        raise ApiError(400, "The sign-in was refused.", "access_denied")
    if row["status"] == "used":
        raise ApiError(400, "That sign-in was already used. Start again.", "invalid_grant")
    if row["status"] == "pending":
        too_fast = now - row["polled"] < POLL_SECONDS - 1
        db.x("UPDATE device_codes SET polled = ? WHERE id = ?", (now, row["id"]))
        raise ApiError(400, "Waiting for you to approve it in your browser.", "slow_down" if too_fast else "authorization_pending")
    person = db.one("SELECT * FROM people WHERE id = ?", (row["person_id"],))
    if not person or person["status"] != "active" or not ctx.gw.settings.email_allowed(person["email"]) or entitle.access_ended(person):
        db.x("UPDATE device_codes SET status = 'denied' WHERE id = ?", (row["id"],))
        raise ApiError(400, "This account can't connect devices right now.", "access_denied")
    key_id, full, secret_hash, hint = security.new_key()
    with db.tx():
        claimed = db.x("UPDATE device_codes SET status = 'used', key_id = ? WHERE id = ? AND status = 'approved'",
                       (key_id, row["id"])).rowcount
        if claimed != 1:
            raise ApiError(400, "That sign-in was already used. Start again.", "invalid_grant")
        name = row["label"] or "My device"
        db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created, created_by) VALUES(?,?,?,?,?,?,?)",
             (key_id, person["id"], name, secret_hash, hint, now, "device enrolment"))
        db.x("INSERT INTO devices(key_id, person_id, name, os, arch, app_version, owner_kind, enrolled, last_seen, last_ip)"
             " VALUES(?,?,?,?,?,?,?,?,?,?)",
             (key_id, person["id"], name, row["os"], row["arch"], row["app_version"], row["owner_kind"], now, now, ctx.ip))
    ctx.gw.audit(person["name"], "enrolled a device", person["name"], f"{name} ({row['os'] or '?'}, {row['owner_kind']}, {hint})", ctx.ip)
    return {"key": full, "key_id": key_id, "server": ctx.gw.public_url(ctx.h), "owner_kind": row["owner_kind"],
            "person": {"name": person["name"], "email": person["email"]}}


# ---------------------------------------------------------------- the device, once it has a key


def device_auth(ctx):
    """-> (key row joined with its person, device row). Refuses a wrong, revoked or paused key — the app treats a
    401 `device_revoked` as "remove Swangz from this device"."""
    if ctx.gw.throttle.blocked("devauth:" + ctx.ip):
        raise ApiError(429, "Too many attempts. Wait a few minutes.", "slow_down")
    auth = (ctx.h.headers.get("authorization") or "").strip()
    token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    key, _ = ctx.gw.identify(token)
    if not key:
        ctx.gw.throttle.fail("devauth:" + ctx.ip)
        raise ApiError(401, "This device is not signed in to Swangz AI Hub.", "device_unknown")
    if key["revoked"]:
        raise ApiError(401, "This device was disconnected. Sign in again to use it.", "device_revoked")
    person = ctx.db.one("SELECT * FROM people WHERE id = ?", (key["person_id"],))
    if not person or person["status"] != "active":
        raise ApiError(403, "Your access is paused. Talk to your admin.", "person_paused")
    if entitle.access_ended(person):
        raise ApiError(403, "Your account's access has ended.", "access_ended")
    if ctx.gw.db.get_setting("paused", "0") == "1":
        raise ApiError(403, "AI access is paused for everyone right now.", "paused")
    device = ctx.db.one("SELECT * FROM devices WHERE key_id = ?", (key["id"],))
    if not device:
        raise ApiError(403, "This key was not made by the Swangz app. Sign in with the app to enrol this device.", "not_enrolled")
    return person, device


def _agents(gw, base):
    anthropic = next((p for p in gw.settings.providers.values() if p.dialect == "anthropic" and p.api_key()), None)
    openai = gw.settings.providers.get("openai") or next((p for p in gw.settings.providers.values() if p.dialect == "openai"), None)
    return (f"{base}/{anthropic.name}" if anthropic else None), (f"{base}/{openai.name}/v1" if openai and openai.api_key() else None)


def granted_packages(db, person, os_name):
    """The newest published version of every package this person may have on this kind of device."""
    out = []
    for p in db.q("SELECT pk.* FROM packages pk WHERE pk.withdrawn IS NULL AND pk.published = ("
                  " SELECT MAX(published) FROM packages x WHERE x.id = pk.id AND x.withdrawn IS NULL) ORDER BY pk.name"):
        if p["platforms"] and os_name and os_name not in p["platforms"].split(","):
            continue
        if db.one("SELECT 1 FROM package_grants WHERE package_id = ? AND (person_id = ? OR department = '*'"
                  " OR (department IS NOT NULL AND department = ?))", (p["id"], person["id"], person.get("department") or "\0")):
            out.append(p)
    return out


_extension_cache = {}


def extension_zip():
    """The browser access gate, zipped from extension/ — the same bytes every time so its checksum is stable."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extension")
    files = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if not f.endswith((".md", ".pyc")))
    stamp = tuple((f, os.path.getmtime(f)) for f in files)
    if _extension_cache.get("stamp") != stamp:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                info = zipfile.ZipInfo(os.path.relpath(f, root).replace(os.sep, "/"), (2026, 1, 1, 0, 0, 0))
                info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
                with open(f, "rb") as fh:
                    z.writestr(info, fh.read())
        data = buf.getvalue()
        _extension_cache.update(stamp=stamp, data=data, sha=hashlib.sha256(data).hexdigest())
    return _extension_cache["data"], _extension_cache["sha"]


def build_manifest(gw, h, person, device):
    """Everything this device is offered right now. Rules, not suggestions: the app installs exactly this."""
    from . import catalog

    db, base = gw.db, gw.public_url(h)
    anthropic_url, openai_url = _agents(gw, base)
    managed = device["owner_kind"] == "company"
    packages = []
    for tool_id, name, blurb in (("claude-code", "Claude Code", "Anthropic's coding agent, for automation on this device."),
                                 ("codex", "Codex", "OpenAI's coding agent, for automation on this device.")):
        url = anthropic_url if tool_id == "claude-code" else openai_url
        tool = db.one("SELECT * FROM tools WHERE id = ? AND archived = 0", (tool_id,))
        if not (tool and url and entitle.is_enabled(db, person, tool)[0]):
            continue
        install = {"type": "agent", "tool": tool_id, "base_url": url, "mode": "managed" if managed else "scoped"}
        if tool_id == "codex":
            install.update(provider="swangz", display_name="Swangz AI Hub", env_key="SWANGZ_AI_KEY", wire_api="responses")
        else:
            install.update(env={"ANTHROPIC_BASE_URL": url})
        packages.append({"id": tool_id, "name": name, "version": "1", "kind": "agent", "description": blurb, "install": install})
    data, sha = extension_zip()
    packages.append({"id": "access-gate", "name": "Browser access gate", "version": sha[:12], "kind": "extension",
                     "description": "Keeps AI websites inside what the company has turned on for you, and records only which tool and how long.",
                     "install": {"type": "extension", "url": base + "/api/device/extension", "sha256": sha, "size": len(data),
                                 "how": "Open chrome://extensions, turn on Developer mode, choose Load unpacked and pick this folder."}})
    for p in granted_packages(db, person, device["os"]):
        packages.append({"id": p["id"], "name": p["name"], "version": p["version"], "kind": p["kind"], "description": p["description"],
                         "install": {"type": "bundle", "url": f"{base}/api/device/packages/{p['id']}/{p['version']}",
                                     "sha256": p["sha256"], "size": p["size"]}})
    apps = []
    for t in entitle.for_person(db, person, include_disabled=False):
        if t["kind"] != "site" or not t["launchable"]:
            continue
        tool = db.one("SELECT * FROM tools WHERE id = ?", (t["id"],))
        apps.append({"id": t["id"], "name": t["name"], "category": t["category"], "signin": t["signin"],
                     "company_browser": bool(tool and catalog.uses_workspace(tool)), "open": f"{base}/go/{t['id']}"})
    return {"server": base, "person": {"name": person["name"], "email": person["email"], "department": person.get("department") or ""},
            "device": {"id": device["key_id"], "name": device["name"], "os": device["os"], "owner_kind": device["owner_kind"]},
            "client": {"latest": CLIENT_LATEST, "minimum": CLIENT_MINIMUM}, "packages": packages, "apps": apps,
            "recording": RECORDING, "generated": time.time()}


@route("GET", r"/device/manifest", signed_in=False)
def device_manifest(ctx):
    person, device = device_auth(ctx)
    return build_manifest(ctx.gw, ctx.h, person, device)


@route("POST", r"/device/heartbeat", signed_in=False)
def device_heartbeat(ctx):
    person, device = device_auth(ctx)
    installed = []
    for item in (ctx.body.get("packages") or [])[:100]:
        if isinstance(item, dict) and PACKAGE_ID.fullmatch(str(item.get("id") or "")):
            installed.append({"id": item["id"], "version": _version(item.get("version")) or "?"})
    now = time.time()
    ctx.db.x("UPDATE devices SET last_seen = ?, last_ip = ?, os = COALESCE(NULLIF(?, ''), os), arch = COALESCE(NULLIF(?, ''), arch),"
             " app_version = COALESCE(NULLIF(?, ''), app_version), packages_json = ? WHERE key_id = ?",
             (now, ctx.ip, _os_name(ctx.body.get("os")), _clean(ctx.body.get("arch"), 20), _version(ctx.body.get("app_version")),
              json.dumps(installed), device["key_id"]))
    ctx.db.x("UPDATE keys SET last_used = ? WHERE id = ?", (now, device["key_id"]))
    return {"ok": True, "latest_client": CLIENT_LATEST, "server_time": now}


@route("GET", r"/device/extension", signed_in=False)
def device_extension(ctx):
    device_auth(ctx)
    return extension_zip()[0], "application/zip", {"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="swangz-access-gate.zip"'}


@route("GET", r"/device/packages/(?P<pid>[a-z0-9-]{2,60})/(?P<version>[0-9A-Za-z._-]{1,32})", signed_in=False)
def device_package(ctx, pid, version):
    person, device = device_auth(ctx)
    pkg = ctx.db.one("SELECT * FROM packages WHERE id = ? AND version = ? AND withdrawn IS NULL", (pid, version))
    allowed = pkg and any(p["id"] == pid for p in granted_packages(ctx.db, person, device["os"]))
    if not allowed:
        raise ApiError(404, "That package isn't available to you.")
    path = package_path(ctx.gw, pid, version)
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_PACKAGE_BYTES + 1)
    except OSError:
        raise ApiError(404, "That package file is missing on the server. Tell your admin.")
    if hashlib.sha256(data).hexdigest() != pkg["sha256"]:
        ctx.gw.log(f"package {pid} {version} on disk does not match its recorded checksum")
        raise ApiError(500, "That package file is damaged on the server. Tell your admin.")
    return data, "application/zip", {"Cache-Control": "no-store", "X-Swangz-Sha256": pkg["sha256"]}


@route("POST", r"/device/signout", signed_in=False)
def device_signout(ctx):
    """The app signs itself out: this device's key is revoked, exactly like "disconnect this device"."""
    person, device = device_auth(ctx)
    ctx.db.x("UPDATE keys SET revoked = ?, revoked_by = ? WHERE id = ? AND revoked IS NULL", (time.time(), "device", device["key_id"]))
    ctx.gw.live.cut("this device was signed out.", key_id=device["key_id"])
    ctx.gw.audit(person["name"], "signed a device out of Swangz", person["name"], device["name"], ctx.ip)
    return {"ok": True}


# ---------------------------------------------------------------- 2. the person approves it, in their own browser


def _csrf(gw, cookie_token, user_code):
    msg = (security.sha256(cookie_token) + ":" + user_code).encode()
    return hmac.new(gw.internal_secret.encode(), msg, hashlib.sha256).hexdigest()[:32]


def _page(h, status, title, body):
    from .server import CONSOLE_HEADERS

    doc = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
           "<meta name=viewport content='width=device-width, initial-scale=1'>"
           f"<title>{html.escape(title)} · Swangz AI Hub</title>"
           "<link rel=stylesheet href=/static/tokens.css><link rel=stylesheet href=/static/portal.css></head>"
           "<body><main class=launch-msg><div class='launch-card device-card'>"
           f"<img src=/static/icon.svg alt='' width=40 height=40><h1>{html.escape(title)}</h1>{body}"
           "</div></main></body></html>")
    h.send_bytes(status, doc.encode(), "text/html; charset=utf-8", {"Cache-Control": "no-store", **CONSOLE_HEADERS})


def _field(label, value):
    return f"<tr><th scope=row>{html.escape(label)}</th><td>{html.escape(value or '—')}</td></tr>"


def page(h, gw, query):
    """/device: approve (or refuse) a device that is waiting with a code. GET shows what is asking, POST decides."""
    ctx = Ctx(h, gw, query)
    person = current_person(ctx)
    token = _cookie(h.headers.get("cookie") or "", COOKIE)
    code = normalise_code(ctx.query.get("code", ""))
    if h.command == "POST":
        form = {k: v[-1] for k, v in parse_qs((h.read_body(8192) or b"").decode("utf-8", "replace")).items()}
        code = normalise_code(form.get("code"))
    else:
        form = {}
    if not person:
        return _page(h, 401, "Sign in first",
                     "<p>Sign in to Swangz AI Hub in this browser, then open this page again to connect your device.</p>"
                     "<a class='btn btn--solid' href=/>Sign in</a>")
    row = gw.db.one("SELECT * FROM device_codes WHERE user_code = ?", (code,)) if code else None
    if h.command == "POST":
        return _decide(h, gw, ctx, person, token, row, form)
    if not code or not row:
        note = "<p>That code isn't right.</p>" if ctx.query.get("code") else "<p>Enter the code the Swangz app is showing on your device.</p>"
        return _page(h, 200, "Connect a device",
                     note + "<form method=get action=/device class=device-form><label>Code<input name=code autocomplete=off "
                     "autocapitalize=characters maxlength=9 required placeholder='ABCD-EFGH'></label>"
                     "<button class='btn btn--solid' type=submit>Continue</button></form>")
    if row["status"] != "pending" or row["expires"] < time.time():
        return _page(h, 200, "This code can't be used", "<p>It was already used or has expired. Start again from the app on your device.</p>")
    fields = _field("Device name", row["label"]) + _field("System", " ".join(x for x in (row["os"], row["arch"]) if x)) + \
        _field("App version", row["app_version"]) + _field("Asked from address", row["ip"]) + \
        _field("Asked at", time.strftime("%H:%M", time.gmtime(row["created"] + gw.settings.tz_offset_minutes * 60)))
    csrf = _csrf(gw, token, code)
    body = (f"<p>A device is asking to sign in as <strong>{html.escape(person['name'])}</strong>.</p>"
            f"<table class=device-facts>{fields}</table>"
            "<p class=device-warn>Only approve this if you started it yourself, just now, on a device you are looking at. "
            "No one from Swangz will ever ask you to approve a code.</p>"
            "<form method=post action=/device class=device-form>"
            f"<input type=hidden name=code value='{html.escape(code)}'><input type=hidden name=csrf value='{csrf}'>"
            "<fieldset><legend>Whose device is it?</legend>"
            "<label><input type=radio name=owner value=personal checked> My own device — Swangz keeps to its own folder and never changes my other settings</label>"
            "<label><input type=radio name=owner value=company> A company-owned device — Swangz points its coding agents at the company gateway</label>"
            "</fieldset>"
            f"<p class=device-note>{html.escape(RECORDING)}</p>"
            "<div class=device-actions><button class='btn' name=decision value=deny type=submit>Cancel</button>"
            "<button class='btn btn--solid' name=decision value=approve type=submit>Approve this device</button></div></form>")
    _page(h, 200, "Connect this device?", body)


def _decide(h, gw, ctx, person, token, row, form):
    code = row["user_code"] if row else ""
    if not row or not hmac.compare_digest(str(form.get("csrf") or ""), _csrf(gw, token, code)):
        return _page(h, 400, "That didn't work", "<p>Open the link from your device again and retry.</p>")
    if row["status"] != "pending" or row["expires"] < time.time():
        return _page(h, 200, "This code can't be used", "<p>It was already used or has expired. Start again from the app on your device.</p>")
    if form.get("decision") != "approve":
        gw.db.x("UPDATE device_codes SET status = 'denied' WHERE id = ? AND status = 'pending'", (row["id"],))
        gw.audit(person["name"], "refused a device sign-in", person["name"], row["label"] or row["os"], ctx.ip)
        return _page(h, 200, "Cancelled", "<p>That device was not connected.</p><a class='btn btn--solid' href=/>Back to Swangz AI Hub</a>")
    if person["status"] != "active":
        return _page(h, 403, "Your access is paused", "<p>Talk to your admin.</p>")
    if gw.db.get_setting("staff_self_keys", "1") != "1":
        return _page(h, 403, "Ask your admin", "<p>Your admin connects new devices for you.</p>")
    if gw.db.scalar("SELECT COUNT(*) FROM keys WHERE person_id = ? AND revoked IS NULL", (person["id"],)) >= MAX_DEVICES:
        return _page(h, 400, "Ten devices are connected",
                     "<p>Disconnect one you no longer use in <strong>Devices</strong>, then try again.</p><a class='btn btn--solid' href=/>Back to Swangz AI Hub</a>")
    owner = form.get("owner") if form.get("owner") in OWNER_KINDS else "personal"
    gw.db.x("UPDATE device_codes SET status = 'approved', person_id = ?, owner_kind = ? WHERE id = ? AND status = 'pending'",
            (person["id"], owner, row["id"]))
    gw.audit(person["name"], "approved a device sign-in", person["name"], f"{row['label'] or '?'} · {row['os'] or '?'} · {owner}", ctx.ip)
    _page(h, 200, "Device connected",
          "<p>You can go back to the Swangz app on your device — it finishes by itself in a few seconds.</p>"
          "<a class='btn btn--solid' href=/>Back to Swangz AI Hub</a>")


# ---------------------------------------------------------------- packages Swangz publishes


class PackageError(ValueError):
    pass


def safe_members(names):
    """Refuse a package whose files would land outside its own folder."""
    for name in names:
        parts = name.replace("\\", "/").split("/")
        if name.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", name) or ".." in parts or "\x00" in name:
            raise PackageError(f"unsafe path in the package: {name!r}")


def publish(gw, path, pid, version, name, *, kind="tool", description="", platforms="", audience=None, by="command line"):
    """Add a package version from a .zip. Anyone already granted the package gets the new version at their next
    sync. `audience`: {"departments": [...], "people": [ids]} added to who may have it (use "*" for everyone)."""
    if not PACKAGE_ID.fullmatch(pid or ""):
        raise PackageError("the package id is lowercase letters, digits and dashes (2–60 characters)")
    if not PACKAGE_VERSION.fullmatch(version or ""):
        raise PackageError("the version is letters, digits and . _ - (up to 32 characters)")
    plats = [x.strip().lower() for x in str(platforms or "").split(",") if x.strip()]
    if any(x not in PLATFORMS for x in plats):
        raise PackageError("platforms are some of: " + ", ".join(PLATFORMS))
    size = os.path.getsize(path)
    if not 0 < size <= MAX_PACKAGE_BYTES:
        raise PackageError(f"a package is up to {MAX_PACKAGE_BYTES // 2 ** 20} MB")
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                raise PackageError(f"the zip is damaged ({bad})")
            safe_members(z.namelist())
    except zipfile.BadZipFile:
        raise PackageError("that file is not a zip")
    if gw.db.one("SELECT 1 FROM packages WHERE id = ? AND version = ?", (pid, version)):
        raise PackageError(f"{pid} {version} is already published — publish a new version instead")
    dest = package_path(gw, pid, version)
    os.makedirs(os.path.dirname(dest), mode=0o700, exist_ok=True)
    shutil.copyfile(path, dest)
    os.chmod(dest, 0o600)
    now = time.time()
    gw.db.x("INSERT INTO packages(id, version, name, kind, description, platforms, sha256, size, published, published_by)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (pid, version, _clean(name, 80) or pid, _clean(kind, 20) or "tool", _clean(description, 400), ",".join(plats),
             _sha256_file(dest), size, now, by))
    for dept in (audience or {}).get("departments", []):
        gw.db.x("INSERT OR IGNORE INTO package_grants(package_id, department, granted) VALUES(?,?,?)", (pid, str(dept), now))
    for person_id in (audience or {}).get("people", []):
        gw.db.x("INSERT OR IGNORE INTO package_grants(package_id, person_id, granted) VALUES(?,?,?)", (pid, int(person_id), now))
    return {"id": pid, "version": version, "sha256": _sha256_file(dest), "size": size}


@admin_route("GET", r"/packages")
def list_packages(ctx):
    """Every package Swangz has published, its versions and who may have it."""
    versions = ctx.db.q("SELECT * FROM packages ORDER BY id, published DESC")
    grants = ctx.db.q("SELECT g.package_id, g.person_id, g.department, p.name AS person FROM package_grants g"
                      " LEFT JOIN people p ON p.id = g.person_id ORDER BY g.package_id")
    return {"versions": versions, "grants": grants}


@admin_route("POST", r"/packages/(?P<pid>[a-z0-9-]{2,60})/grants", area="govern")
def grant_package(ctx, pid):
    if not ctx.db.one("SELECT 1 FROM packages WHERE id = ?", (pid,)):
        raise ApiError(404, "no such package")
    dept, person_id = str(ctx.body.get("department") or "").strip(), ctx.body.get("person_id")
    if bool(dept) == bool(person_id):
        raise ApiError(400, 'give either a department ("*" for everyone) or a person')
    if person_id:
        if not str(person_id).isdigit() or not ctx.db.one("SELECT 1 FROM people WHERE id = ?", (int(person_id),)):
            raise ApiError(404, "no such person")
        ctx.db.x("INSERT OR IGNORE INTO package_grants(package_id, person_id, granted) VALUES(?,?,?)", (pid, int(person_id), time.time()))
    else:
        ctx.db.x("INSERT OR IGNORE INTO package_grants(package_id, department, granted) VALUES(?,?,?)", (pid, dept[:80], time.time()))
    ctx.audit("granted a package", pid, dept or f"person:{person_id}", after={"department": dept or None, "person_id": person_id})
    return {"ok": True}


@admin_route("DELETE", r"/packages/(?P<pid>[a-z0-9-]{2,60})/grants", area="govern")
def revoke_package(ctx, pid):
    dept, person_id = str(ctx.body.get("department") or "").strip(), ctx.body.get("person_id")
    if bool(dept) == bool(person_id):
        raise ApiError(400, 'give either a department ("*" for everyone) or a person')
    if person_id:
        n = ctx.db.x("DELETE FROM package_grants WHERE package_id = ? AND person_id = ?", (pid, int(person_id or 0))).rowcount
    else:
        n = ctx.db.x("DELETE FROM package_grants WHERE package_id = ? AND department = ?", (pid, dept)).rowcount
    ctx.audit("took a package away", pid, dept or f"person:{person_id}", before={"department": dept or None, "person_id": person_id})
    return {"ok": True, "removed": n}


@admin_route("POST", r"/packages/(?P<pid>[a-z0-9-]{2,60})/(?P<version>[0-9A-Za-z._-]{1,32})/withdraw", area="govern")
def withdraw_package(ctx, pid, version):
    n = ctx.db.x("UPDATE packages SET withdrawn = ? WHERE id = ? AND version = ? AND withdrawn IS NULL", (time.time(), pid, version)).rowcount
    if not n:
        raise ApiError(404, "no such published version")
    ctx.audit("withdrew a package version", f"{pid} {version}", ctx.reason)
    return {"ok": True}
