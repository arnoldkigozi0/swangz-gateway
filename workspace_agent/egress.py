"""Domain-only egress log and guard for private workspaces. Standard library only.

A private workspace's Chromium is forced (by managed policy, which the person cannot change) to send
everything through one small forward proxy that this module runs, one listener per browser. The proxy:

  * **records which website** (host name and port) a person's browser connected to, when, how many times
    and how many bytes moved — nothing else. For HTTPS it only ever sees the host name in the CONNECT
    line; for plain HTTP it drops the path and query before anything is logged. No page content, no
    URLs beyond the host, no keystrokes.
  * **keeps the browser inside the internet**: a destination is refused unless every address its name
    resolves to is a public one, so a workspace can't reach this server's agent (127.0.0.1), the cloud
    metadata address, other containers or a private network. The proxy connects to the address it
    checked, never resolving the name a second time (no DNS-rebinding window).
  * **refuses abuse ports** (mail, SSH, databases, remote desktop), so a workspace can't be used to
    send spam or probe other machines.
  * only talks to **private-network peers** (the Docker bridge), so it is never an open proxy even if a
    firewall rule is missing.

It is not a network jail: it relies on Chromium's policy to use the proxy. See docs/SECURITY.md.

The log (`VisitLog`) aggregates per person, website and minute, and keeps numbered entries on disk, so
the gateway can pull "everything after entry N" and never miss or double-count one.
"""

import collections
import ipaddress
import json
import os
import re
import select
import socket
import socketserver
import threading
import time
import urllib.parse

DENIED_PORTS = frozenset({22, 23, 25, 110, 135, 139, 143, 445, 465, 587, 993, 995, 1433, 3306, 3389, 5432, 5900, 6379,
                          11211, 27017})
HEADER_LIMIT = 16 * 1024
CONNECT_TIMEOUT = 15
IDLE_SECONDS = 600
MAX_CONNECTIONS = 200  # open at once, per browser
HOST = re.compile(r"[a-z0-9]([a-z0-9._-]{0,251}[a-z0-9])?")
HOP = {"connection", "keep-alive", "proxy-connection", "proxy-authorization", "proxy-authenticate", "te", "trailer",
       "upgrade-insecure-requests"}


PEER_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fc00::/7", "::1/128"))


def private_peer(address):
    """May this client use the proxy at all? Only the Docker bridge, a LAN and this machine — the ranges
    Docker hands out — never an address from the internet (nor a documentation or reserved range)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in net for net in PEER_NETWORKS if net.version == ip.version)


def public_ip(ip):
    return ip.is_global and not ip.is_multicast


def parse_host(text):
    """'example.com' | 'EXAMPLE.com.' | '[2001:db8::1]' | '203.0.113.9' -> normalised host, or None if it isn't one."""
    text = (text or "").strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    text = text.lower().rstrip(".")
    return text if HOST.fullmatch(text) else None


class VisitLog:
    """Websites seen, per person, aggregated per minute and numbered, so a reader can ask for what is new."""

    def __init__(self, path=None, window=60, keep=20000, clock=time.time):
        self.path, self.window, self.keep, self.clock = path, window, keep, clock
        self.lock = threading.Lock()
        self.buckets = {}  # (user, host, port, outcome, reason) -> {first, last, conns, up, down}
        self.entries = collections.deque(maxlen=keep)
        self.seq = 0
        self.active = {}  # user -> when this person's browser last moved data
        self._load()

    def _load(self):
        if not self.path:
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        self.seq = max(self.seq, int(entry["seq"]))
                        self.entries.append(entry)
                    except (ValueError, KeyError, TypeError):
                        continue
        except FileNotFoundError:
            pass

    def record(self, user, host, port, outcome="allowed", reason="", conns=1, up=0, down=0):
        now = self.clock()
        key = (user, host, int(port), outcome, reason)
        with self.lock:
            b = self.buckets.get(key)
            if b is None:
                b = self.buckets[key] = {"first": now, "last": now, "conns": 0, "up": 0, "down": 0}
            b["last"] = now
            b["conns"] += conns
            b["up"] += up
            b["down"] += down
            if outcome == "allowed":
                self.active[user] = now

    def flush(self, force=False):
        """Turn buckets that are a window old (or all of them, when forced) into numbered entries."""
        now = self.clock()
        out = []
        with self.lock:
            for key in [k for k, b in self.buckets.items() if force or now - b["first"] >= self.window]:
                b = self.buckets.pop(key)
                self.seq += 1
                user, host, port, outcome, reason = key
                entry = {"seq": self.seq, "ts": round(b["first"], 3), "last": round(b["last"], 3), "user": user,
                         "host": host, "port": port, "outcome": outcome, "reason": reason, "conns": b["conns"],
                         "up": b["up"], "down": b["down"]}
                self.entries.append(entry)
                out.append(entry)
        if out and self.path:
            self._append(out)
        return out

    def _append(self, entries):
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries))
            if os.path.getsize(self.path) > 8 * 1024 * 1024:  # keep the file bounded: rewrite with what we hold
                tmp = self.path + ".tmp"
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    with self.lock:
                        keep = list(self.entries)[-self.keep // 2:]
                    f.write("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in keep))
                os.replace(tmp, self.path)
        except OSError:
            pass  # the in-memory entries still serve the gateway; a full disk must not stop browsing

    def since(self, after=0, limit=500):
        """-> {"entries": [...numbered after `after`, oldest first], "last": newest number, "reset": bool}.
        `reset` is true when the reader is ahead of this log (it was lost): start again from the top."""
        self.flush()
        limit = max(1, min(int(limit), 2000))
        with self.lock:
            reset = after > self.seq
            start = 0 if reset else after
            found = [e for e in self.entries if e["seq"] > start][:limit]
            return {"entries": found, "last": self.seq, "reset": reset}

    def last_active(self, user):
        return self.active.get(user, 0.0)


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


class EgressProxy:
    """One forward proxy per browser slot. `who(slot)` says whose browser it is right now ('' = nobody's:
    refused). `allow_ip(ip)` is the destination rule — public addresses only, unless a test says otherwise."""

    def __init__(self, visits, who, allow_ip=public_ip, allow_peer=private_peer, resolve=None, denied_ports=DENIED_PORTS):
        self.visits, self.who, self.allow_ip, self.allow_peer = visits, who, allow_ip, allow_peer
        self.resolve = resolve or self._resolve
        self.denied_ports = denied_ports
        self.servers = {}
        self.open = {}

    @staticmethod
    def _resolve(host, port):
        try:
            ip = ipaddress.ip_address(host)
            return [str(ip)]
        except ValueError:
            pass
        found = []
        for family, _, _, _, addr in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
            if addr[0] not in found:
                found.append(addr[0])
        return found

    def listen(self, slot, host, port):
        """Start the listener for one browser. -> the port it got (0 asks for any, for tests)."""
        proxy = self
        gate = threading.BoundedSemaphore(MAX_CONNECTIONS)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                if not proxy.allow_peer(self.client_address[0]):
                    return
                if not gate.acquire(blocking=False):
                    return _reply(self.request, 503, "too many connections for this browser")
                try:
                    proxy._serve(slot, self.request)
                except OSError:
                    pass
                finally:
                    gate.release()

        server = _Server((host, port), Handler)
        self.servers[slot] = server
        threading.Thread(target=server.serve_forever, name=f"egress-{slot}", daemon=True).start()
        return server.server_address[1]

    def close(self):
        for server in self.servers.values():
            server.shutdown()
            server.server_close()
        self.servers.clear()

    # ------------------------------------------------------------ one request

    def _serve(self, slot, conn):
        conn.settimeout(30)
        head, rest = _read_head(conn)
        if head is None:
            return _reply(conn, 400, "bad request")
        lines = head.split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3 or not parts[2].startswith("HTTP/"):
            return _reply(conn, 400, "bad request")
        method, target = parts[0].upper(), parts[1]
        user = self.who(slot)
        if not user:
            return _reply(conn, 403, "this browser is not in use")
        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            host, port, request = parse_host(host), _port(port), None
        else:
            try:
                u = urllib.parse.urlsplit(target)
                host, port = parse_host(u.hostname), u.port or 80
            except ValueError:
                host, port = None, None
            if not target.lower().startswith("http://") or not host:
                return _reply(conn, 400, "this is a proxy: use an http:// or https:// address")
            headers = [h for h in lines[1:] if h and h.split(":", 1)[0].strip().lower() not in HOP]
            request = (f"{method} {u.path or '/'}{'?' + u.query if u.query else ''} HTTP/1.1\r\n"
                       + "\r\n".join(headers) + "\r\nConnection: close\r\n\r\n").encode("latin-1", "replace")
        if not host or not port:
            return _reply(conn, 400, "bad destination")
        why = self._refuse(host, port)
        if isinstance(why, str):
            self.visits.record(user, host, port, "blocked", why)
            return _reply(conn, 403, "blocked by Swangz workspace policy: " + why)
        upstream = None
        for ip in why:  # the addresses already checked: connect to one of those, never resolve again
            try:
                upstream = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT)
                break
            except OSError:
                continue
        if upstream is None:
            self.visits.record(user, host, port, "failed", "could not connect")
            return _reply(conn, 502, "could not connect")
        self.visits.record(user, host, port, "allowed")
        up = down = 0
        try:
            if request is None:
                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            else:
                upstream.sendall(request)
            if rest:
                upstream.sendall(rest)
                up += len(rest)
            moved = _pipe(conn, upstream)
            up, down = up + moved[0], moved[1]
        finally:
            upstream.close()
            self.visits.record(user, host, port, "allowed", conns=0, up=up, down=down)

    def _refuse(self, host, port):
        """-> the addresses to connect to, or a short reason string if this destination is refused."""
        if port in self.denied_ports:
            return f"port {port} is not allowed"
        try:
            ips = self.resolve(host, port)
        except OSError:
            return "the name did not resolve"
        if not ips:
            return "the name did not resolve"
        for ip in ips:
            try:
                if not self.allow_ip(ipaddress.ip_address(ip)):
                    return "internal or private address"
            except ValueError:
                return "the name did not resolve"
        return ips


def _port(text):
    try:
        port = int(text)
    except ValueError:
        return None
    return port if 1 <= port <= 65535 else None


def _read_head(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        if len(data) > HEADER_LIMIT:
            return None, b""
        chunk = conn.recv(4096)
        if not chunk:
            return None, b""
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return head.decode("latin-1"), rest


def _reply(conn, status, why):
    body = why.encode()
    reason = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway", 503: "Service Unavailable"}.get(status, "Error")
    try:
        conn.sendall(f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
                     "Connection: close\r\n\r\n".encode() + body)
    except OSError:
        pass


def _pipe(client, upstream, idle=IDLE_SECONDS):
    """Copy both ways until either side closes or goes quiet. -> (bytes client sent, bytes upstream sent)."""
    client.settimeout(idle)
    upstream.settimeout(idle)
    sent = [0, 0]
    try:
        while True:
            ready, _, broken = select.select([client, upstream], [], [client, upstream], idle)
            if not ready or broken:
                break
            for s in ready:
                data = s.recv(65536)
                if not data:
                    return tuple(sent)
                if s is client:
                    upstream.sendall(data)
                    sent[0] += len(data)
                else:
                    client.sendall(data)
                    sent[1] += len(data)
    except OSError:
        pass
    return tuple(sent)
