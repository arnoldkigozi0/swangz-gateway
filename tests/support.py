import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import warnings

from gateway import security
from gateway.config import Provider, Settings
from gateway.server import make_server

from .fake_upstream import FakeUpstream

os.environ.setdefault("GATEWAY_ACCESS_LOG", "0")
os.environ.setdefault("GATEWAY_FETCH_ICONS", "0")  # never reach the internet for logos in tests
# the stand-in provider leaves sockets for the gateway to close when a stream is cut; that's expected
warnings.simplefilter("ignore", ResourceWarning)


class Rig:
    """A gateway in front of a fake provider, with one owner, one viewer, and one person holding a key."""

    def __init__(self):
        self.fake = FakeUpstream()
        self.tmp = tempfile.mkdtemp(prefix="sgw-test-")
        os.environ["FAKE_ANTHROPIC_KEY"] = "sk-ant-provider-secret"
        os.environ["FAKE_OPENAI_KEY"] = "sk-openai-provider-secret"
        providers = {
            "anthropic": Provider("anthropic", self.fake.url, "FAKE_ANTHROPIC_KEY", "anthropic"),
            "openai": Provider("openai", self.fake.url, "FAKE_OPENAI_KEY", "openai"),
            "nokey": Provider("nokey", self.fake.url, "FAKE_MISSING_KEY", "openai"),
            "elevenlabs": Provider("elevenlabs", self.fake.url, "FAKE_ELEVEN_KEY", "elevenlabs", label="ElevenLabs"),
            "higgsfield": Provider("higgsfield", self.fake.url, "FAKE_HF_KEY", "higgsfield", label="Higgsfield"),
        }
        os.environ["FAKE_ELEVEN_KEY"] = "eleven-provider-secret"
        os.environ["FAKE_HF_KEY"] = "hf-id:hf-provider-secret"
        self.settings = Settings(host="127.0.0.1", port=0, data_dir=self.tmp, pbkdf2_iterations=1000,
                                 providers=providers, public_url="https://ai.example.test")
        self.server, self.gw = make_server(self.settings)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        now = time.time()
        db = self.gw.db
        db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
             ("owner", security.hash_password("owner-password", 1000), "owner", now))
        db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
             ("viewer", security.hash_password("viewer-password", 1000), "viewer", now))
        self.person_id = db.x("INSERT INTO people(name, department, created) VALUES(?,?,?)", ("Nansubuga Grace", "Creative", now)).lastrowid
        self.key_id, self.key, secret_hash, hint = security.new_key()
        db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,?,?,?,?,?)",
             (self.key_id, self.person_id, "laptop", secret_hash, hint, now))
        # a real person who uses Claude Code / Codex has been assigned them by an admin
        for tool_id in ("claude-code", "codex"):
            db.x("INSERT OR IGNORE INTO entitlements(tool_id, person_id, granted) VALUES(?,?,?)",
                 (tool_id, self.person_id, now))
        self.cookies = {}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.gw.db.close()
        self.fake.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ raw HTTP

    def request(self, method, path, body=None, headers=None, conn=None):
        """Provider calls wait until the gateway has written their record (it does so just after replying)."""
        is_provider = path.split("/")[1] in self.settings.providers
        before = self.gw.db.scalar("SELECT COUNT(*) FROM requests") if is_provider else 0
        result = self._request(method, path, body, headers, conn)
        if is_provider:
            self.wait_for(lambda: self.gw.db.scalar("SELECT COUNT(*) FROM requests") > before)
        return result

    def _request(self, method, path, body=None, headers=None, conn=None):
        own = conn is None
        conn = conn or http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        hdrs = {"content-type": "application/json"} if data is not None else {}
        hdrs.update(headers or {})
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        if own:
            conn.close()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, payload

    def anthropic(self, body, key=None, extra=None):
        headers = {"x-api-key": key or self.key, "anthropic-version": "2023-06-01", "user-agent": "claude-cli/2.1.286 (external, cli)"}
        headers.update(extra or {})
        return self.request("POST", "/anthropic/v1/messages", body, headers)

    def openai(self, path, body, key=None, extra=None):
        headers = {"authorization": f"Bearer {key or self.key}", "user-agent": "codex_exec/0.155.0"}
        headers.update(extra or {})
        return self.request("POST", "/openai/v1" + path, body, headers)

    # ------------------------------------------------------------ console

    def login(self, who="owner"):
        status, headers, body = self.request("POST", "/admin/api/login", {"username": who, "password": f"{who}-password"},
                                             {"x-gateway-admin": "1"})
        assert status == 200, body
        self.cookies[who] = headers["set-cookie"].split(";")[0]
        return self.cookies[who]

    def api(self, method, path, body=None, who="owner"):
        if who not in self.cookies:
            self.login(who)
        headers = {"cookie": self.cookies[who], "x-gateway-admin": "1"}
        status, h, payload = self.request(method, "/admin/api" + path, body, headers)
        try:
            return status, json.loads(payload)
        except ValueError:
            return status, payload

    def last_record(self):
        return self.gw.db.one("SELECT * FROM requests ORDER BY id DESC LIMIT 1")

    def wait_for(self, predicate, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            value = predicate()
            if value:
                return value
            time.sleep(0.02)
        raise AssertionError("timed out waiting")


def sse_events(payload):
    events = []
    for block in payload.decode().split("\n\n"):
        name, data = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((name, "\n".join(data)))
    return events
