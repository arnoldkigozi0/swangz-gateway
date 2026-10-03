"""A stand-in for one Neko browser's API (github.com/m1k1o/neko, v3): health, members and sessions.

Behaves like Neko's object member provider: a member's id is its username, deleting a member also ends
its session, a member that already exists is refused with 422, and unknown members get 404. It answers
under any path prefix (Neko's server.path_prefix). `booting` makes /health fail that many times, like a
browser that is still starting. Every call is kept in .calls for assertions.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        neko = self.server.neko
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"null") if n else None
        path = self.path.split("?")[0]
        neko.calls.append((self.command, path, body))
        if neko.broken:
            return self._reply(503, {"message": "down for maintenance"})
        if self.command == "GET" and path.endswith("/health"):  # no token needed, like Neko's
            with neko.lock:
                if neko.booting > 0:
                    neko.booting -= 1
                    return self._reply(503, {"message": "starting"})
            return self._reply(200, {})
        if self.headers.get("authorization") != "Bearer " + neko.token:
            return self._reply(401, {"message": "invalid token"})
        parts = path.strip("/").split("/")
        parts = parts[parts.index("api"):] if "api" in parts else parts  # api, members|sessions, id, action
        with neko.lock:
            if parts[:2] == ["api", "members"] and len(parts) == 2 and self.command == "POST":
                if body["username"] in neko.members:
                    return self._reply(422, {"message": "member already exists"})
                neko.members[body["username"]] = {"password": body["password"], "profile": body["profile"]}
                return self._reply(200, {"id": body["username"], "profile": body["profile"]})
            if parts[:2] == ["api", "members"] and len(parts) >= 3:
                member = neko.members.get(parts[2])
                if member is None:
                    return self._reply(404, {"message": "member not found"})
                if self.command == "DELETE" and len(parts) == 3:
                    del neko.members[parts[2]]
                    neko.sessions.discard(parts[2])
                    return self._reply(204)
                if self.command == "POST" and len(parts) == 3:
                    member["profile"] = body
                    return self._reply(204)
                if self.command == "POST" and parts[3:] == ["password"]:
                    member["password"] = body["password"]
                    return self._reply(204)
            if parts[:2] == ["api", "sessions"] and parts[3:] == ["disconnect"] and self.command == "POST":
                if parts[2] not in neko.sessions:
                    return self._reply(404, {"message": "session not found"})
                neko.sessions.discard(parts[2])
                return self._reply(204)
        return self._reply(404, {"message": "not found"})

    do_DELETE = do_GET = do_POST

    def _reply(self, status, obj=None):
        data = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(status)
        if data:
            self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeNeko:
    def __init__(self, token="neko-api-token"):
        self.token = token
        self.members = {}  # id (= username) -> {"password", "profile"}
        self.sessions = set()  # ids of members whose browser tab is connected
        self.calls = []
        self.broken = False
        self.booting = 0
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.neko = self
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def sign_in(self, username, password):
        """What the browser does with the link's usr/pwd. -> True when Neko lets them in."""
        with self.lock:
            member = self.members.get(username)
            if not member or member["password"] != password or username in self.sessions:
                return False
            self.sessions.add(username)
            return True

    def reset(self):
        """The container was replaced: an object provider keeps its members in memory, so all are gone."""
        with self.lock:
            self.members.clear()
            self.sessions.clear()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
