"""Open a provider in the Swangz workspace window (docs/MANAGED-WORKSPACE.md 9.1, W3 server side).

The workspace browser has no Hub session, so it never opens `/go/<tool>`. Instead the app asks here, with its
device key, for the provider's own address. The answer goes through exactly the checks `/go/` makes
(`staff.launch_checks`: entitlement, weekly report, the global pause, company policies), then the workspace state
of THIS device (suspended, retired, or `enforce` with no fresh passing policy report), and each answer is recorded
as a launch, opened or refused, just as `/go/` records it.

The address must be safe to hand to a browser started from the command line: https only, no user name or password
in it, no port but 443, a DNS name rather than an address, on one of the tool's allowed hosts, not the Hub itself,
and with no query or fragment field that looks like a credential. Anything else is refused and recorded; the
admin fixes the tool's address or hosts. The answer never carries a key, a token or a Hub session.

Shared company accounts (`signin = 'shared'`) are handed out one turn at a time through `/go/`; they are refused
here with `shared_account` until turns are wired into the workspace (not part of W3).
"""

import ipaddress
import re
import time
from urllib.parse import parse_qsl, urlsplit

from . import enroll, managed, turns
from .admin import ApiError
from .staff import launch_checks, route

TOOL_ID = re.compile(r"[a-z0-9-]{1,80}")
HOST = re.compile(r"(?=.{1,253}\Z)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
MAX_URL = 2048
CREDENTIAL_FIELDS = {"password", "passwd", "pwd", "pass", "token", "access_token", "id_token", "refresh_token", "auth_token",
                     "api_key", "apikey", "key", "secret", "client_secret", "session", "sessionid", "session_id", "sid",
                     "auth", "authorization", "jwt", "bearer", "otp", "credentials"}
UNSAFE = "This tool's address isn't safe to open in your Swangz workspace. Ask your admin to check the tool's address."


def allowed_hosts(tool):
    """The tool's governed hosts, as the access gate reads them. Malformed entries are dropped, never widened."""
    out = []
    for raw in (tool.get("hosts") or "").split(","):
        host = raw.strip().lower()
        if host.startswith("www."):
            host = host[4:]
        if HOST.fullmatch(host) and host not in out:
            out.append(host)
    return out


def _on(host, hosts):
    return any(host == h or host.endswith("." + h) for h in hosts)


def check_url(url, hosts, hub_host=""):
    """-> None when the address is safe to start the workspace browser on, else the refusal code."""
    url = url or ""
    if not url or len(url) > MAX_URL or any(ord(c) <= 0x20 or ord(c) == 0x7F or c == "\\" for c in url):
        return "unsafe_address"
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "unsafe_address"
    if parts.scheme != "https" or "@" in parts.netloc or parts.username is not None or parts.password is not None:
        return "unsafe_address"
    if port not in (None, 443):
        return "unsafe_address"
    host = (parts.hostname or "").rstrip(".")
    try:
        ipaddress.ip_address(host.strip("[]"))
        return "unsafe_address"  # an address, not a name: never a provider's official sign-in
    except ValueError:
        pass
    if not HOST.fullmatch(host) or host in ("localhost",):
        return "unsafe_address"
    if hub_host and (host == hub_host or host.endswith("." + hub_host)):
        return "unsafe_address"  # the Hub itself: the workspace has no Hub session, and /go/ is never opened there
    for field, _ in parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(parts.fragment, keep_blank_values=True):
        if field.strip().lower() in CREDENTIAL_FIELDS:
            return "unsafe_address"
    if not _on(host, hosts):
        return "host_not_allowed"
    return None


def _hub_host(ctx):
    try:
        return (urlsplit(ctx.gw.public_url(ctx.h)).hostname or "").lower()
    except ValueError:
        return ""


@route("POST", r"/device/open", signed_in=False)
def device_open(ctx):
    """Body `{"tool": "<tool id>"}`, device key as `Authorization: Bearer`, header `X-Swangz-App: 1`.
    200 `{"ok": true, "tool": {"id", "name"}, "url", "allowed_hosts", "workspace": {"state", "generation"}}`."""
    person, device, _ = enroll.device_key_auth(ctx)
    tool_id = ctx.body.get("tool")
    tool = ctx.db.one("SELECT * FROM tools WHERE id = ? AND archived = 0", (tool_id,)) \
        if isinstance(tool_id, str) and TOOL_ID.fullmatch(tool_id) else None
    if not tool:
        raise ApiError(404, "That tool isn't in the catalog any more. Your admin may have removed it.", "unknown_tool")
    ok, state, reason, rule, report_denial = launch_checks(ctx.gw, person, tool)
    code = None if ok else (rule.split(":")[0] if rule else state or "refused")
    if ok:
        shut = managed.launch_refusal(ctx.gw, person, {"d": [device["device_id"]]})
        if shut:
            ok, (reason, rule) = False, shut
            code = rule
    hosts, url = allowed_hosts(tool), None
    if ok and turns.is_shared(tool):
        ok, code, rule = False, "shared_account", "shared_account"
        reason = f"{tool['name']} is a shared company account. Open it from Swangz AI Hub, where turns are handed out."
    if ok:
        url = next((u.strip() for u in (tool.get("launch_url"), tool.get("url")) if (u or "").strip()), "")
        if not url:
            ok, code, reason = False, "no_address", "This tool has no web address yet. Ask your admin."
        elif not hosts:
            ok, code, reason = False, "host_not_allowed", UNSAFE
        else:
            problem = check_url(url, hosts, _hub_host(ctx))
            if problem:
                ok, code, reason = False, problem, UNSAFE
    cur = ctx.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome, ip, user_agent, reason, rule, device_id)"
                   " VALUES(?,?,?,?,?,?,?,?,?)",
                   (tool["id"], person["id"], time.time(), "opened" if ok else "refused", ctx.ip,
                    (ctx.h.headers.get("user-agent") or "")[:200], "" if ok else (reason or "")[:300], None if ok else (rule or code),
                    device["device_id"]))
    if not ok:
        status = 409 if code in ("no_address", "unsafe_address", "host_not_allowed", "shared_account") else 403
        details = {"report": report_denial["href"]} if report_denial else None
        raise ApiError(status, reason or "This tool isn't open to you right now.", code, details)
    return 200, {"ok": True, "tool": {"id": tool["id"], "name": tool["name"]}, "url": url, "allowed_hosts": hosts,
                 "launch": cur.lastrowid,
                 "workspace": managed.heartbeat_answer(ctx.gw, person, device)["workspace"]}, {"Cache-Control": "no-store"}


# Why the app could not start the window after the Hub said yes. Short codes only: never an address, a path or a message.
FAILED_CODES = {"no_browser", "unsafe_address", "no_hosts", "folder", "launch_failed", "purge_pending", "purge_unsupported",
                "generation_rollback", "not_active", "retired"}
FAILED_WINDOW = 300


@route("POST", r"/device/open/failed", signed_in=False)
def device_open_failed(ctx):
    """Body `{"launch": <id from /device/open>, "reason": "<code>"}`, device key. The window did not start, so that open
    is recorded as `failed` instead of `opened`. Only an open this device made for this person in the last five minutes
    that is still `opened` changes; anything else changes nothing. 200 `{"ok": true, "recorded": bool}`."""
    person, device, _ = enroll.device_key_auth(ctx)
    launch, reason = ctx.body.get("launch"), ctx.body.get("reason")
    if type(launch) is not int or not 1 <= launch <= 2 ** 63 - 1:
        raise ApiError(400, "That isn't a launch this app can report on.", "bad_request")
    reason = reason if reason in FAILED_CODES else "launch_failed"
    cur = ctx.db.x("UPDATE launches SET outcome = 'failed', reason = ?, rule = ? WHERE id = ? AND person_id = ?"
                   " AND device_id = ? AND outcome = 'opened' AND ts >= ?",
                   ("The Swangz app reported that the workspace window didn't start.", "app:" + reason, launch, person["id"],
                    device["device_id"], time.time() - FAILED_WINDOW))
    recorded = cur.rowcount == 1
    if recorded:
        ctx.gw.audit(person["name"], "reported a workspace window that did not start", ip=ctx.ip,
                     before={"outcome": "opened"}, after={"outcome": "failed", "code": reason},
                     correlation=f"device:{device['device_id']}")
    return 200, {"ok": True, "recorded": recorded}, {"Cache-Control": "no-store"}
