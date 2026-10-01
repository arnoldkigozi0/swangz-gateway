"""HTTP: providers under /<name>/..., the console at /, its API under /admin/api/."""

import hmac
import json
import os
import re
import ssl
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import admin, pricing, proxy, security, staff, store
from .db import DB
from .live import Live

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                ".ico": "image/x-icon"}
CONSOLE_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; media-src 'self' https: blob:; style-src 'self'; "
                               "script-src 'self'; font-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class Gateway:
    def __init__(self, settings):
        self.settings = settings
        self.db = DB(settings.db_path)
        pricing.seed(self.db)
        self.live = Live()
        self.pool = proxy.Pool(settings.upstream_timeout)
        self.throttle = security.LoginThrottle()
        self._prices = None
        self._prices_lock = threading.Lock()
        self.trust_proxy = os.environ.get("GATEWAY_TRUST_PROXY", "") in ("1", "true", "yes")
        self.extra_endpoints = os.environ.get("GATEWAY_EXTRA_ENDPOINTS", "")
        # tunnels that terminate https without saying so (localhost.run): treat every request as https
        self.force_https = os.environ.get("GATEWAY_FORCE_HTTPS", "") in ("1", "true", "yes")
        # The staff app's Studio calls providers through the gateway itself, over loopback, with this
        # per-process secret instead of a key — so Studio work is checked and recorded like any other.
        self.internal_secret = security.new_session_token()
        self.port = settings.port
        self.voice_cache = (0, [])
        self._bootstrap()

    # ------------------------------------------------------------ lookups

    def prices(self):
        with self._prices_lock:
            if self._prices is None:
                self._prices = pricing.load(self.db)
            return self._prices

    def reload_prices(self):
        with self._prices_lock:
            self._prices = None

    def identify(self, token):
        """-> (key row joined with its person, key_id) — row is None when the key is wrong."""
        key_id, secret = security.split_key(token)
        if not key_id:
            return None, None
        row = self.db.one(
            "SELECT k.*, p.name AS person_name, p.status AS person_status, p.allowed_models, p.allowed_services,"
            " p.daily_budget, p.monthly_budget FROM keys k JOIN people p ON p.id = k.person_id WHERE k.id = ?",
            (key_id,),
        )
        if not row or not security.secret_matches(secret, row["secret_hash"]):
            return None, key_id
        return row, key_id

    def identify_internal(self, h):
        """A Studio request from the staff app (loopback + this process's secret) -> (person as a key row, None)."""
        secret = h.headers.get("x-sgw-internal")
        if not secret or not hmac.compare_digest(secret, self.internal_secret):
            return None
        if (h.client_address[0] if h.client_address else "") not in ("127.0.0.1", "::1"):
            return None
        try:
            pid = int(h.headers.get("x-sgw-person") or 0)
        except ValueError:
            return None
        row = self.db.one("SELECT NULL AS id, NULL AS revoked, p.id AS person_id, p.name AS person_name, p.status AS person_status,"
                          " p.allowed_models, p.allowed_services, p.daily_budget, p.monthly_budget FROM people p WHERE p.id = ?", (pid,))
        return (row, None) if row else None

    def gate(self, key, model, kind, provider=None):
        """None when the request may go ahead, else (status, error type, message, short reason)."""
        if self.db.get_setting("paused", "0") == "1":
            return 403, "permission_error", "AI access is paused for everyone by an administrator.", "paused"
        if key["revoked"]:
            return 403, "permission_error", "this key was revoked by an administrator.", "key revoked"
        if key["person_status"] != "active":
            return 403, "permission_error", "your AI access is suspended. Talk to an administrator.", "suspended"
        services = [s.strip().lower() for s in (key.get("allowed_services") or "").split(",") if s.strip()]
        if provider is not None and services and provider.name.lower() not in services:
            return 403, "permission_error", f"{provider.label} isn't switched on for you. Talk to an administrator.", "service not allowed"
        # model rules are about chat and coding models; voice/image/video services have their own rule above
        if (provider is None or provider.is_chat) and not proxy.model_allowed(key["allowed_models"], model):
            return 403, "permission_error", f"you are not cleared to use the model '{model}'.", "model not allowed"
        if kind != "other" and (key["daily_budget"] is not None or key["monthly_budget"] is not None):
            day, month = proxy.period_starts(time.time(), self.settings.tz_offset_minutes)
            if key["daily_budget"] is not None and self.spend(key["person_id"], day) >= key["daily_budget"]:
                return 403, "permission_error", f"your daily AI budget (${key['daily_budget']:.2f}) is used up.", "daily budget"
            if key["monthly_budget"] is not None and self.spend(key["person_id"], month) >= key["monthly_budget"]:
                return 403, "permission_error", f"your monthly AI budget (${key['monthly_budget']:.2f}) is used up.", "monthly budget"
        return None

    def spend(self, person_id, since):
        return self.db.scalar("SELECT COALESCE(SUM(cost), 0) FROM requests WHERE person_id = ? AND ts >= ?",
                              (person_id, since)) or 0.0

    def public_url(self, h=None):
        """The address people reach the gateway at. A fixed GATEWAY_PUBLIC_URL wins; otherwise it is
        read from the request (behind a proxy or tunnel: X-Forwarded-Host/-Proto when trusted), so
        setup instructions always match the link the person actually used."""
        if self.settings.public_url or h is None:
            return self.settings.base_url()
        host = h.headers.get("x-forwarded-host") if self.trust_proxy else None
        host = (host or h.headers.get("host") or "").split(",")[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?|\[[0-9a-fA-F:]+\](:\d{1,5})?", host):
            return self.settings.base_url()
        proto = (h.headers.get("x-forwarded-proto") or "").split(",")[0].strip() if self.trust_proxy else ""
        scheme = proto if proto in ("http", "https") else ("https" if self.settings.tls_cert else "http")
        if self.force_https and not re.match(r"(localhost|127\.|\[::1\])", host):
            scheme = "https"
        return f"{scheme}://{host}"

    def secure_request(self, h):
        """Was this request made over https (directly, or through a trusted proxy)?"""
        if self.settings.secure_cookies or self.settings.tls_cert or self.force_https:
            return True
        return self.trust_proxy and (h.headers.get("x-forwarded-proto") or "").startswith("https")

    def client_ip(self, h):
        if self.trust_proxy:
            forwarded = h.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()[:64]
        return h.client_address[0] if h.client_address else ""

    def audit(self, actor, action, target="", detail="", ip=""):
        self.db.x("INSERT INTO audit(ts, actor, action, target, detail, ip) VALUES(?,?,?,?,?,?)",
                  (time.time(), actor, action, str(target), str(detail)[:2000], ip))

    def log(self, message):
        sys.stderr.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
        sys.stderr.flush()

    # ------------------------------------------------------------ housekeeping

    def _bootstrap(self):
        s = self.settings
        if s.bootstrap_admin and s.bootstrap_password and not self.db.scalar("SELECT COUNT(*) FROM admins"):
            self.db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
                      (s.bootstrap_admin, security.hash_password(s.bootstrap_password, s.pbkdf2_iterations),
                       "owner", time.time()))
            self.audit("system", "created the first owner from the environment", s.bootstrap_admin)

    def maintain(self):
        days = int(self.db.get_setting("retention_days", "90") or 0)
        removed, orphans = store.purge(self.db, days)
        if removed or orphans:
            self.log(f"retention: removed {removed} old records and {orphans} unreferenced bodies")

    def start_maintenance(self, every=3600):
        def loop():
            while True:
                try:
                    self.maintain()
                except Exception as exc:
                    self.log(f"maintenance failed: {exc!r}")
                time.sleep(every)

        threading.Thread(target=loop, name="maintenance", daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SwangzGateway/1.0"
    sys_version = ""
    timeout = 300  # an idle keep-alive connection is dropped after five minutes
    gw = None

    def do_GET(self):
        self.route()

    do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_GET

    def route(self):
        self._body = None
        self._responded = False
        path, _, query = self.path.partition("?")
        try:
            if ".." in path or "\\" in path:
                return self.send_json(400, {"error": "bad path"})
            if path.startswith("/admin/api/"):
                return admin.dispatch(self, self.gw, path, query)
            if path.startswith("/api/"):
                return staff.dispatch(self, self.gw, path, query)
            first, _, rest = path.lstrip("/").partition("/")
            provider = self.gw.settings.providers.get(first)
            if provider is not None:
                return proxy.Call(self.gw, self, provider, "/" + rest if rest else "", query).run()
            if path == "/healthz":
                return self.send_json(200, {"ok": True})
            if self.command in ("GET", "HEAD"):
                return self.serve_static(path)
            self.send_json(404, {"error": "not found"})
        except Exception:
            self.gw.log("unhandled error on " + self.command + " " + path + "\n" + traceback.format_exc())
            self.close_connection = True
            if not self._responded:
                try:
                    self.send_json(500, {"error": "internal error"})
                except OSError:
                    pass
        finally:
            if self._body is None and int(self.headers.get("content-length") or 0) > 0:
                self.close_connection = True
            if "chunked" in (self.headers.get("transfer-encoding") or "").lower() and self._body is None:
                self.close_connection = True

    # ------------------------------------------------------------ bodies and replies

    def read_body(self, limit):
        if self._body is not None:
            return self._body
        if "chunked" in (self.headers.get("transfer-encoding") or "").lower():
            parts, total = [], 0
            while True:
                line = self.rfile.readline(1024)
                size = int(line.split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline(1024) not in (b"\r\n", b"\n", b""):
                        pass
                    break
                total += size
                if total > limit:
                    raise proxy.BodyTooLarge()
                parts.append(self.rfile.read(size))
                self.rfile.readline(8)
            self._body = b"".join(parts)
            return self._body
        n = int(self.headers.get("content-length") or 0)
        if n > limit:
            raise proxy.BodyTooLarge()
        self._body = self.rfile.read(n) if n else b""
        return self._body

    def send_response(self, code, message=None):
        self._responded = True
        super().send_response(code, message)

    def send_bytes(self, status, data, ctype, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            if isinstance(v, (list, tuple)):
                for item in v:
                    self.send_header(k, item)
            else:
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, status, obj, headers=None):
        merged = {"Cache-Control": "no-store", **CONSOLE_HEADERS, **(headers or {})}
        self.send_bytes(status, json.dumps(obj, default=str).encode(), "application/json; charset=utf-8", merged)

    def serve_static(self, path):
        """/ is the staff app, /admin the console, /static/… their files (fonts in /static/fonts/)."""
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            folder, _, leaf = name.rpartition("/")
            if folder not in ("", "fonts") or not leaf or leaf not in os.listdir(os.path.join(STATIC_DIR, folder)):
                return self.send_bytes(404, b"not found", "text/plain")
        elif path == "/admin" or path.startswith("/admin/"):
            name = "admin.html"
        elif "." in path.rsplit("/", 1)[-1]:
            return self.send_bytes(404, b"not found", "text/plain")
        else:
            name = "index.html"
        with open(os.path.join(STATIC_DIR, name), "rb") as f:
            data = f.read()
        ext = os.path.splitext(name)[1]
        # small files; always revalidate so a new release never runs against a stale script
        self.send_bytes(200, data, STATIC_TYPES.get(ext, "application/octet-stream"),
                        {"Cache-Control": "no-cache", **CONSOLE_HEADERS})

    def log_message(self, fmt, *args):
        if os.environ.get("GATEWAY_ACCESS_LOG", "1") != "0":
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


def make_server(settings):
    gw = Gateway(settings)
    handler = type("BoundHandler", (Handler,), {"gw": gw})
    server = Server((settings.host, settings.port), handler)
    gw.port = server.server_address[1]
    if settings.tls_cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(settings.tls_cert, settings.tls_key or None)
        server.socket = ctx.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    return server, gw

