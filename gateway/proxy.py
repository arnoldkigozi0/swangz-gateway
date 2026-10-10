"""The way through: who is this, are they allowed, forward, stream back, write it all down.

Requests are passed through in the provider's own dialect, byte for byte (one exception: OpenAI
chat streams are asked to include usage, so the cost can be counted). Nothing is translated, so
Claude Code, Codex and the official SDKs behave exactly as they do against the provider directly.
"""

import calendar
import fnmatch
import re
import http.client
import json
import ssl
import threading
import time

from . import parse, pricing, purpose, security, store

STRIP_REQUEST = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection", "te",
    "trailer", "trailers", "transfer-encoding", "upgrade", "host", "content-length", "authorization",
    "x-api-key", "x-goog-api-key", "accept-encoding", "cookie", "forwarded", "x-forwarded-for",
    "x-forwarded-proto", "x-forwarded-host", "x-real-ip", "xi-api-key", "hf-api-key", "hf-secret",
    "x-sgw-internal", "x-sgw-person", "x-swangz-purpose", "x-swangz-project",
}
STRIP_RESPONSE = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
    "transfer-encoding", "upgrade", "content-length", "set-cookie",
}
MAX_PARSED_BYTES = 32 * 1024 * 1024

# Everyone's traffic leaves on the company's one provider key, so anything that key can read, every
# gateway key could read too: files someone uploaded, batch results, stored responses, the org's
# admin API. Only the endpoints that AI tools use to talk to a model go through. Admins can add more
# with GATEWAY_EXTRA_ENDPOINTS="POST /v1/images/generations, GET /v1/files".
ALLOWED_ENDPOINTS = {
    "anthropic": ["POST /v1/messages", "POST /v1/messages/count_tokens", "GET /v1/models", "GET /v1/models/*"],
    "openai": ["POST /v1/responses", "POST /v1/responses/compact", "POST /v1/chat/completions", "POST /v1/completions",
               "POST /v1/embeddings", "GET /v1/models", "GET /v1/models/*"],
    # creating speech, sound and transcripts, and listing voices — not the account's history,
    # which would show everyone's generations to everyone
    "elevenlabs": ["POST /v1/text-to-speech/*", "POST /v1/speech-to-speech/*", "POST /v1/sound-generation",
                   "POST /v1/speech-to-text", "POST /v1/text-to-dialogue", "POST /v1/text-to-dialogue/*",
                   "POST /v1/music", "POST /v1/music/*", "GET /v1/voices", "GET /v2/voices", "GET /v1/voices/*",
                   "GET /v1/models"],
    # starting generations and following their status
    "higgsfield": ["POST /*", "GET /requests/*", "GET /v1/job-sets/*", "GET /v1/motions", "GET /v1/text2image/soul-styles"],
    # any other service added by an admin: its whole API, on the admin's say-so
    "media": ["ANY /*"],
}


def endpoint_allowed(dialect, method, path, extra=""):
    p = path.split("?", 1)[0].rstrip("/") or "/"
    rules = ALLOWED_ENDPOINTS.get(dialect, []) + [r.strip() for r in extra.split(",") if r.strip()]
    for rule in rules:
        rule_method, _, rule_path = rule.partition(" ")
        if rule_method.upper() in (method, "ANY") and fnmatch.fnmatchcase(p, rule_path.strip()):
            return True
    return False


class BodyTooLarge(Exception):
    pass


class Pool:
    """A few idle keep-alive connections per provider, so agents don't pay a TLS handshake per turn."""

    def __init__(self, timeout, size=8):
        self.timeout = timeout
        self.size = size
        self.idle = {}
        self.lock = threading.Lock()
        self.tls = ssl.create_default_context()

    def get(self, provider):
        with self.lock:
            conns = self.idle.get(provider.name) or []
            if conns:
                return conns.pop(), True
        if provider.scheme == "https":
            conn = http.client.HTTPSConnection(provider.host, provider.port, timeout=self.timeout, context=self.tls)
        else:
            conn = http.client.HTTPConnection(provider.host, provider.port, timeout=self.timeout)
        return conn, False

    def put(self, provider, conn):
        with self.lock:
            conns = self.idle.setdefault(provider.name, [])
            if len(conns) < self.size:
                conns.append(conn)
                return
        conn.close()


def period_starts(now, offset_minutes):
    """Start of today and of this month, in the company's time zone, as UTC timestamps."""
    shift = offset_minutes * 60
    local = now + shift
    day = local - (local % 86400)
    t = time.gmtime(local)
    month = calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0))
    return day - shift, month - shift


def model_allowed(patterns, model):
    rules = [p.strip() for p in (patterns or "").replace("\n", ",").split(",") if p.strip()]
    if not rules or not model:
        return True
    return any(fnmatch.fnmatchcase(model, rule) for rule in rules)


def error_body(dialect, etype, message, code=None):
    message = "Swangz AI Hub gateway: " + message
    if dialect == "anthropic":
        return {"type": "error", "error": {"type": etype, "message": message}}
    return {"error": {"message": message, "type": etype, "code": code or etype, "param": None}}


def _cut_event(dialect, kind, message):
    message = "Swangz AI Hub gateway: " + message
    if dialect == "anthropic":
        data = {"type": "error", "error": {"type": "permission_error", "message": message}}
        return b"event: error\ndata: " + json.dumps(data).encode() + b"\n\n"
    if kind == "responses":
        data = {"type": "response.failed", "response": {"status": "failed", "error": {"code": "access_revoked", "message": message}}}
        return b"event: response.failed\ndata: " + json.dumps(data).encode() + b"\n\n"
    data = {"error": {"message": message, "type": "permission_error", "code": "access_revoked"}}
    return b"data: " + json.dumps(data).encode() + b"\n\n"


class Call:
    """Everything known about one request, filled in as it goes and written once at the end."""

    def __init__(self, gw, h, provider, rest, query):
        self.gw, self.h, self.provider = gw, h, provider
        self.started = time.time()
        self.kind = parse.endpoint_kind(provider.dialect, rest, h.command)
        self.media = None
        self.rest = rest
        self.query = query
        self.raw = b""
        self.body = None
        self.summary = parse.summarize_request("other", None)
        self.key = None
        self.flags = []
        self.rec = {
            "ts": self.started, "person_id": None, "key_id": None, "provider": provider.name,
            "method": h.command, "path": rest + ("?" + query if query else ""), "kind": self.kind,
            "client": parse.client_name(h.headers), "client_ip": gw.client_ip(h),
            "user_agent": (h.headers.get("user-agent") or "")[:300], "session": None, "model": None,
            "stream": 0, "status": None, "outcome": "ok", "reason": None, "duration_ms": None, "ttft_ms": None,
            "in_tok": 0, "out_tok": 0, "cache_write_tok": 0, "cache_read_tok": 0, "reasoning_tok": 0,
            "cost": None, "prompt": None, "actions": None, "reply": None, "flags": "",
            "req_list_field": None, "req_head": None, "req_items": None, "req_bytes": 0,
            "resp_blob": None, "resp_format": None, "resp_bytes": 0,
            "request_class": None, "agent": None, "turn_id": None,
            "media_type": None, "units": None, "unit": None, "result_urls": None, "resp_ctype": None,
            "rule": None,
        }

    # ------------------------------------------------------------ steps

    def run(self):
        h = self.h
        if self.provider.dialect == "anthropic" and self.rest == "/api/hello" and h.command in ("HEAD", "GET"):
            # Claude Code warms the connection with this probe, without a key. Answer it here.
            return h.send_bytes(200, b"" if h.command == "HEAD" else b'{"ok":true}', "application/json")
        try:
            self.raw = h.read_body(self.gw.settings.max_body_bytes)
        except BodyTooLarge:
            h.close_connection = True
            return self.refuse(413, "request_too_large", "this request is larger than the gateway accepts.", "blocked", "too large", store=False)
        self.rec["req_bytes"] = len(self.raw)
        self._read_body()

        row, key_id = self.gw.identify_internal(h) or self.gw.identify(security.client_token(h.headers))
        self.rec["key_id"] = key_id
        if row is None:
            return self.refuse(401, "authentication_error", "this key is not a valid Swangz gateway key.", "denied", "bad key", store=False)
        self.key = row
        self.rec["person_id"] = row["person_id"]
        if row["id"]:
            self.gw.db.x("UPDATE keys SET last_used = ? WHERE id = ?", (self.started, row["id"]))
        elif h.headers.get("x-sgw-ref"):  # a Studio request: let the staff app find its own record
            self.rec["turn_id"] = h.headers["x-sgw-ref"][:80]

        if not endpoint_allowed(self.provider.dialect, self.h.command, self.rest, self.gw.extra_endpoints):
            return self.refuse(403, "permission_error",
                               f"{self.h.command} {self.rest.split('?')[0]} is not available through the gateway.",
                               "blocked", "endpoint not allowed")
        gate = self.gw.gate(row, self.rec["model"], self.kind, self.provider) \
            or self.gw.dev_tool_gate(row, self.rec["client"])
        if gate:
            status, etype, message, why = gate
            return self.refuse(status, etype, message, "blocked", why)
        from . import reporting, policy
        if self.kind not in ("other", "media-status"):
            tool = self.gw.db.one("SELECT * FROM tools WHERE id=?", (row.get("hub_tool_id"),)) if row.get("hub_tool_id") else policy.request_tool(self.gw.db, self.rec["client"], self.provider.name)
            if row.get("hub_tool_id") and (not tool or tool.get("provider") != self.provider.name):
                return self.refuse(403, "permission_error", "This device key is scoped to a different tool/provider.", "blocked", "key tool scope")
            if row.get("hub_tool_id"):
                from . import entitle
                person = self.gw.db.one("SELECT * FROM people WHERE id=?", (row["person_id"],))
                if not entitle.is_enabled(self.gw.db, person, tool)[0]:
                    return self.refuse(403, "permission_error", "This scoped tool is no longer assigned and available.", "blocked", "tool entitlement")
            self.rec["hub_tool_id"] = (tool or {}).get("id")
            candidates = [tool["id"]] if tool else []
            if not row.get("hub_tool_id"):
                # Legacy keys cannot assert a trusted client identity. Fail closed across outstanding
                # tools on that provider, so changing the user agent or issuing a new key cannot bypass it.
                candidates += [t["id"] for t in self.gw.db.q("SELECT id FROM tools WHERE provider=?", (self.provider.name,))]
            for tid in dict.fromkeys(candidates):
                denial = reporting.gate(self.gw, row["person_id"], tid)
                if denial:
                    self.rec["rule"] = "weekly_report_required"
                    return self.refuse(403, "weekly_report_required", denial["message"], "blocked", "weekly_report_required", extra=denial)
        ruled = self.gw.policy_gate(row, self.rec["model"], self.kind, self.provider, self.rec["client"])
        if ruled:
            status, etype, message, why, self.rec["rule"] = ruled
            return self.refuse(status, etype, message, "blocked", why)
        if self.flags and self.gw.db.get_setting("block_secrets", "0") == "1":
            return self.refuse(403, "permission_error",
                               "this request contains what looks like a credential (" + ", ".join(self.flags)
                               + "). Remove it and try again.", "blocked", "secret in prompt")
        if not self.provider.api_key():
            return self.refuse(403, "permission_error",
                               f"the '{self.provider.name}' provider has no API key on the gateway yet. Tell an admin.",
                               "blocked", "provider not configured")
        self.forward()

    def _read_body(self):
        ctype = (self.h.headers.get("content-type") or "").lower()
        if self.raw and ("json" in ctype or self.raw[:1] in (b"{", b"[")):
            try:
                self.body = json.loads(self.raw)
            except ValueError:
                self.body = None
        if self.kind == "media":
            self.media = parse.summarize_media_request(self.provider.dialect, self.rest, self.body, ctype)
            self.rec.update(model=self.media["model"], prompt=self.media["prompt"], media_type=self.media["media_type"],
                            units=self.media["units"], unit=self.media["unit"],
                            actions=json.dumps([self.media["action"]]))
            self.flags = parse.find_secrets(self.media["prompt"]) if self.media["prompt"] else []
        elif isinstance(self.body, dict):
            self.summary = parse.summarize_request(self.kind, self.body)
            self.rec["model"] = self.summary["model"]
            self.rec["stream"] = int(self.summary["stream"])
            self.rec["prompt"] = self.summary["prompt"]
            self.flags = parse.find_secrets(self.summary["tail"]) if self.summary["tail"] else []
        self.rec["session"] = parse.session_of(self.h.headers, self.body)
        self.rec.update(parse.request_meta(self.h.headers, self.body))
        flags = ["secret:" + f for f in self.flags]
        if self.summary.get("attachments"):
            flags.append(f"attachments:{self.summary['attachments']}")
        self.rec["flags"] = ",".join(flags)

    def refuse(self, status, etype, message, outcome, why, store=True, extra=None):
        body = error_body(self.provider.dialect, etype, message)
        if extra:
            body["error"].update(extra)
        payload = json.dumps(body).encode()
        # A policy refusal won't change on a retry; an unreachable provider might.
        retry = "true" if status >= 500 or status == 429 else "false"
        self.h.send_bytes(status, payload, "application/json", {"x-should-retry": retry})
        self.rec.update(status=status, outcome=outcome, reason=why)
        self.write(None, b"" if not store else None, keep_request=store)

    def forward(self):
        gw, h, provider = self.gw, self.h, self.provider
        payload = self.raw
        if self.kind == "chat" and isinstance(self.body, dict) and self.body.get("stream"):
            options = dict(self.body.get("stream_options") or {})
            if not options.get("include_usage"):
                options["include_usage"] = True
                patched = dict(self.body, stream_options=options)
                payload = json.dumps(patched).encode()

        headers = {}
        for k, v in h.headers.items():
            if k.lower() not in STRIP_REQUEST:
                headers[k] = v
        headers.update(provider.auth_headers())
        headers["Accept-Encoding"] = "identity"
        if payload or h.command in ("POST", "PUT", "PATCH"):
            headers["Content-Length"] = str(len(payload))
        target = provider.base_path + self.rest + ("?" + self.query if self.query else "")

        ticket = gw.live.start(person_id=self.key["person_id"], person=self.key["person_name"],
                               key_id=self.key["id"], provider=provider.name, model=self.rec["model"],
                               client=self.rec["client"], session=self.rec["session"], prompt=self.rec["prompt"])
        try:
            resp, conn = self._send(ticket, target, payload, headers)
        except (OSError, http.client.HTTPException) as exc:
            gw.live.finish(ticket)
            if ticket.reason:
                return self.refuse(403, "permission_error", ticket.reason, "cut", ticket.reason)
            return self.refuse(502, "api_error", f"could not reach {provider.name} ({exc.__class__.__name__}).",
                               "error", "upstream unreachable")
        try:
            self._relay(ticket, resp, conn)
        finally:
            gw.live.finish(ticket)

    def _send(self, ticket, target, payload, headers):
        pool = self.gw.pool
        for attempt in (1, 2):
            conn, reused = pool.get(self.provider)
            self.gw.live.attach(ticket, conn)
            try:
                conn.request(self.h.command, target, body=payload or None, headers=headers)
                return conn.getresponse(), conn
            except (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError):
                conn.close()
                if not reused or attempt == 2 or ticket.reason:
                    raise
            except Exception:
                conn.close()
                raise
        raise http.client.HTTPException("unreachable")

    def _relay(self, ticket, resp, conn):
        h = self.h
        status = resp.status
        ctype = resp.getheader("content-type") or ""
        is_sse = "text/event-stream" in ctype.lower()
        reader = parse.StreamReader(self.kind) if is_sse and self.kind != "other" else None
        length = resp.getheader("content-length")
        chunked = is_sse or length is None or bool(resp.chunked)

        h.send_response(status)
        for k, v in resp.getheaders():
            if k.lower() not in STRIP_RESPONSE:
                h.send_header(k, v)
        h.send_header("Transfer-Encoding" if chunked else "Content-Length", "chunked" if chunked else length)
        h.end_headers()

        kept, size, outcome, why = [], 0, "ok", None
        while True:
            try:
                data = resp.read1(65536) if chunked else resp.read(65536)
            except (OSError, http.client.HTTPException, ValueError):
                if not ticket.reason:
                    outcome, why = "error", "upstream connection dropped"
                break
            if not data:
                break
            if ticket.first_byte is None:
                ticket.first_byte = time.time()
                self.rec["ttft_ms"] = int((ticket.first_byte - self.started) * 1000)
            if reader is not None:
                reader.feed(data)
            elif size < MAX_PARSED_BYTES:
                kept.append(data)
            size += len(data)
            ticket.out_bytes = size
            try:
                h.wfile.write(b"%x\r\n%s\r\n" % (len(data), data) if chunked else data)
            except OSError:
                outcome, why = "aborted", "the person's tool disconnected"
                break
            if ticket.reason:
                break

        if ticket.reason:
            outcome, why = "cut", ticket.reason
            if chunked:
                try:
                    if is_sse:
                        event = _cut_event(self.provider.dialect, self.kind, ticket.reason)
                        h.wfile.write(b"%x\r\n%s\r\n" % (len(event), event))
                    h.wfile.write(b"0\r\n\r\n")
                except OSError:
                    pass
        elif outcome == "ok" and chunked:
            try:
                h.wfile.write(b"0\r\n\r\n")
            except OSError:
                outcome, why = "aborted", "the person's tool disconnected"

        if outcome == "ok" and not resp.will_close and not ticket.reason:
            self.gw.pool.put(self.provider, conn)
        else:
            conn.close()
            if outcome != "ok":
                h.close_connection = True

        final = None
        if reader is not None:
            final = reader.finish()
        elif kept and "json" in ctype.lower():
            try:
                final = json.loads(b"".join(kept))
            except ValueError:
                final = None
        summary = None
        if self.kind in ("media", "media-status"):
            self._media_result(ctype, final, size, status)
        elif isinstance(final, dict):
            summary = parse.summarize_response(self.kind, self.provider.dialect, final)
        if outcome == "ok" and status >= 400:
            outcome = "error"
            why = (summary or {}).get("error") or self.rec.pop("reason_detail", None) or f"HTTP {status}"
        elif outcome == "ok" and summary and summary.get("error"):
            outcome, why = "error", summary["error"]
        self.rec.pop("reason_detail", None)
        self.rec.update(status=status, outcome=outcome, reason=why, resp_bytes=size, resp_ctype=ctype[:80] or None)
        self.write(summary, b"".join(kept) if final is None else None, final=final)

    def _media_result(self, ctype, final, size, status):
        """What a voice/image/video service sent back; a finished job is copied onto the request that started it."""
        result = parse.summarize_media_response(ctype, final if isinstance(final, dict) else None, size)
        if status >= 400:
            self.rec["reason_detail"] = result.get("error") or f"HTTP {status}"
        self.rec["reply"] = result["reply"]
        if result["urls"]:
            self.rec["result_urls"] = json.dumps(result["urls"])
        if self.kind == "media":
            self.rec["turn_id"] = result["job_id"] or self.rec["turn_id"]
            return
        job = result["job_id"] or next(iter(re.findall(r"/requests/([^/]+)/", self.rest)), None)
        self.rec["turn_id"] = job
        if job and (result["urls"] or result["status"] in ("completed", "failed", "nsfw")):
            self.gw.db.x("UPDATE requests SET reply = ?, result_urls = COALESCE(?, result_urls) WHERE provider = ? AND kind = 'media'"
                         " AND turn_id = ?", (result["reply"], self.rec["result_urls"], self.provider.name, job))

    # ------------------------------------------------------------ the record

    def write(self, summary, raw_response, final=None, keep_request=True):
        gw, rec = self.gw, self.rec
        rec["duration_ms"] = int((time.time() - self.started) * 1000)
        if summary:
            usage = summary["usage"]
            rec.update(in_tok=usage["input"], out_tok=usage["output"],
                       cache_write_tok=usage["cache_write"] + usage["cache_write_1h"],
                       cache_read_tok=usage["cache_read"], reasoning_tok=usage["reasoning"])
            rec["model"] = rec["model"] or summary["model"]
            rec["reply"] = summary["reply"] or None
            rec["actions"] = json.dumps(summary["actions"]) if summary["actions"] else None
            price = pricing.find_price(gw.prices(), summary["model"] or rec["model"])
            rec["cost"] = pricing.cost(price, usage)
            # which price row made this cost, and as of when — the cost is never recalculated later
            rec["cost_source"] = f"price:{price['model']}@{int(price['updated'])}" if price else None
        elif rec["kind"] == "media" and rec["outcome"] == "ok" and rec.get("units"):
            from . import money

            rec["cost"], rec["cost_source"] = money.media_cost(gw.db, rec)
        if rec["kind"] not in ("other", "media-status"):
            rec.update(purpose.classify(gw.db, rec, self.h.headers, enabled=gw.db.get_setting("purpose_inference", "1") == "1"))
        keep_bodies = gw.db.get_setting("store_bodies", "1") == "1"
        try:
            with gw.db.tx():
                if keep_bodies and keep_request and (self.body is not None or self.raw):
                    field = parse.list_field(self.kind, self.body) if isinstance(self.body, dict) else None
                    rec["req_list_field"] = field
                    rec["req_head"], rec["req_items"] = store.store_request_body(
                        gw.db, self.body if isinstance(self.body, dict) else None, self.raw, field)
                if keep_bodies and (final is not None or raw_response):
                    rec["resp_blob"], rec["resp_format"] = store.store_response(gw.db, final, raw_response)
                cols = list(rec)
                gw.db.x(f"INSERT INTO requests({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        [rec[c] for c in cols])
        except Exception as exc:  # the person's work already went through; never fail it for logging
            gw.log(f"could not record request: {exc!r}")
