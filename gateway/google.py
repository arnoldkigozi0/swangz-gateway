"""Sign in with Google, for staff and for admins (OpenID Connect, authorization-code flow).

  /auth/google/start?app=staff|admin   -> Google's sign-in page
  /auth/google/callback                -> back from Google with a one-time code
  /auth/options                        -> {"google": true|false}, so the apps know to show the button

The gateway swaps the code for an ID token directly with Google over TLS. OpenID Connect Core
§3.1.3.7 lets a client trust an ID token received that way without checking its signature; the
gateway still checks the issuer, the audience (our client id), expiry, the nonce, and that Google has
verified the email address.

Google only proves *who* someone is. They still need an account here — a person with that email
(staff) or a console user whose username is that email (admins) — and every existing rule applies:
Swangz emails only, suspended people and ended accounts are refused.
"""

import base64
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import security

STATE_SECONDS = 600
STATE_COOKIE = "sgw_oauth"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
APPS = {"staff": "/", "admin": "/admin"}

_states = {}  # sha256(state) -> (app, nonce, expires); a sign-in only has to survive ten minutes
_lock = threading.Lock()


def redirect_uri(gw, h):
    s = gw.settings
    return s.google_redirect_uri or f"{web_url(gw, h)}/auth/google/callback"


def web_url(gw, h):
    """Where people open the apps: GATEWAY_WEB_URL (a Netlify front door), else the gateway itself."""
    return gw.settings.web_url or gw.public_url(h)


def _cookie_value(header, name):
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def _back(h, app, error=None, headers=None):
    """Send the browser back to the app it came from — always a path on this same site."""
    where = APPS.get(app, "/") + (f"?auth_error={error}" if error else "")
    clear = f"{STATE_COOKIE}=; Path=/auth/google; HttpOnly; SameSite=Lax; Max-Age=0"
    out = {"Location": where, "Cache-Control": "no-store", "Set-Cookie": [clear]}
    for k, v in (headers or {}).items():
        if k == "Set-Cookie":
            out["Set-Cookie"].append(v)
        else:
            out[k] = v
    h.send_bytes(302, b"", "text/plain", out)


def options(h, gw):
    h.send_json(200, {"google": gw.settings.google_enabled})


def start(h, gw, query):
    app = urllib.parse.parse_qs(query).get("app", ["staff"])[-1]
    if app not in APPS:
        app = "staff"
    s = gw.settings
    if not s.google_enabled:
        return _back(h, app, "off")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(16)
    now = time.time()
    with _lock:
        for k in [k for k, v in _states.items() if v[2] < now]:
            del _states[k]
        _states[security.sha256(state)] = (app, nonce, now + STATE_SECONDS)
    params = {"client_id": s.google_client_id, "redirect_uri": redirect_uri(gw, h), "response_type": "code",
              "scope": "openid email profile", "state": state, "nonce": nonce, "prompt": "select_account"}
    # the state is also kept in this browser, so a sign-in started elsewhere can't be finished here
    secure = "; Secure" if gw.secure_request(h) else ""
    h.send_bytes(302, b"", "text/plain", {
        "Location": s.google_auth_url + "?" + urllib.parse.urlencode(params), "Cache-Control": "no-store",
        "Set-Cookie": f"{STATE_COOKIE}={state}; Path=/auth/google; HttpOnly; SameSite=Lax; Max-Age={STATE_SECONDS}{secure}"})


def _claims(id_token):
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None


def _exchange(gw, h, code):
    """The one-time code -> the ID token's claims, straight from Google. None if anything is off."""
    s = gw.settings
    form = urllib.parse.urlencode({"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                   "redirect_uri": redirect_uri(gw, h), "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request(s.google_token_url, data=form, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read(256 * 1024))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        gw.log(f"google sign-in: token exchange failed: {exc!r}")
        return None
    return _claims(str(data.get("id_token") or "")) if isinstance(data, dict) else None


def _valid(claims, client_id, nonce):
    if not isinstance(claims, dict):
        return False
    aud = claims.get("aud")
    return (claims.get("iss") in ISSUERS
            and (aud == client_id or (isinstance(aud, list) and client_id in aud))
            and float(claims.get("exp") or 0) > time.time()
            and claims.get("nonce") == nonce
            and claims.get("email_verified") in (True, "true")
            and bool(claims.get("email")))


def callback(h, gw, query):
    from . import admin, entitle, staff
    from .admin import Ctx

    q = {k: v[-1] for k, v in urllib.parse.parse_qs(query).items()}
    state = q.get("state", "")
    with _lock:
        entry = _states.pop(security.sha256(state), None) if state else None
    app = entry[0] if entry else "staff"
    if not entry or entry[2] < time.time() or _cookie_value(h.headers.get("cookie"), STATE_COOKIE) != state:
        return _back(h, app, "expired")
    if q.get("error") or not q.get("code"):
        return _back(h, app, "cancelled")
    claims = _exchange(gw, h, q["code"])
    if not _valid(claims, gw.settings.google_client_id, entry[1]):
        return _back(h, app, "google")
    email = str(claims["email"]).strip().lower()
    ctx = Ctx(h, gw, "")

    if app == "admin":
        row = gw.db.one("SELECT * FROM admins WHERE lower(username) = ?", (email,))
        if not row:
            gw.audit(email, "Google sign-in to the console refused", "", "no console user with that email", ctx.ip)
            return _back(h, app, "no_account")
        return _back(h, app, headers=admin.start_session(ctx, row, "signed in with Google"))

    if not gw.settings.email_allowed(email):
        gw.audit(email, "Google sign-in refused", "", "not a Swangz email", ctx.ip)
        return _back(h, app, "not_allowed")
    person = gw.db.one("SELECT * FROM people WHERE lower(email) = ? AND email != ''", (email,))
    if not person:
        gw.audit(email, "Google sign-in refused", "", "no account with that email", ctx.ip)
        return _back(h, app, "no_account")
    if person["status"] != "active" or entitle.access_ended(person):
        return _back(h, app, "paused")
    gw.audit(person["name"], "signed in with Google", "", "", ctx.ip)
    return _back(h, app, headers=staff._start_session(ctx, person["id"]))
