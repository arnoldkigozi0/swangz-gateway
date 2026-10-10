"""The shared workspace: company browsers on Swangz's own server, each signed in to a tool once by an admin.

A `shared` tool can open into one of two kinds of workspace (`mode()`):

  * **agent** (`tools.workspace_mode = 'agent'`) — the production set-up. The Swangz Workspace Agent
    (workspace_agent/agent.py) runs on the workspace server next to Docker and owns the browsers: it
    starts a Neko container when a turn needs one, signs the person in, and on release removes the
    sign-in and recycles the browser. The gateway only holds the agent's address and token
    (GATEWAY_WORKSPACE_AGENT / GATEWAY_WORKSPACE_AGENT_TOKEN) — never Docker, never a Neko token. A
    browser that is still starting shows the person a page that waits for it.

  * **static** — `tools.workspace_url` lists browser addresses, one per line, each a Neko container
    someone runs by hand. Kept for development, tests and as a fallback; described below.

In both, everyone holding a turn gets a browser to themselves, so several people can work on one tool
at once, and each person's workspace sign-in lives exactly as long as their turn.

Static mode: each address is a Neko browser (github.com/m1k1o/neko): one Chromium, one screen, with a
persistent profile that an admin has signed in to the tool by hand. The list is a pool, capping
`seats_at_once`. With GATEWAY_WORKSPACE_TOKEN set (Neko's API token, the same on every browser) the
gateway also decides who gets into each browser:

  * Open makes a sign-in for this person on their browser: their own workspace username
    (swangz-<person id>) with a new random password, sent along in the link. Nobody else has a sign-in
    there, so nobody else gets in.
  * When the turn ends (handed back, run out, taken back, suspended) the gateway deletes that sign-in,
    and Neko drops the session on the spot.

The tool's own password never reaches the gateway. It lives in the browser profile, on that server.
Without the token, Open still hands out one browser per person, but sends them to the plain address and
the browser's own login decides who gets in.

Where agent mode's browsers run (`HOSTS`) is the admin's choice, one place at a time: the rented server
(GATEWAY_WORKSPACE_AGENT, in the environment), or one of Swangz's own computers — the Windows PC or the
Mac (workspace_agent/computer.py). A computer gets a key in the console and checks in every minute with
the address its tunnel gave it (`hello`); it is told which tools need browsers, and the video relay to use.
Switching (`use`) ends the turns of anyone in a browser at the old place — they press Open again — and
their sign-ins there are removed as soon as it answers, because each turn remembers where its browser is.
"""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 10
AGENT_TIMEOUT = 20  # starting a container takes the agent a second or two; it never waits for the browser
SWEEP_SECONDS = 15
MAX_BROWSERS = 20
COMPLAIN_EVERY = 600  # a workspace that stays down is logged every ten minutes, not every sweep
HOSTS = {"server": "the rented server", "windows": "the Windows PC", "mac": "the Mac"}
COMPUTERS = ("windows", "mac")
ONLINE_SECONDS = 180  # a computer that hasn't checked in for this long counts as offline
RELAY_TTL = 48 * 3600  # how long relay credentials last; new ones are made when half of that is gone

# What a staff member may do in their browser. Not an admin of it: they can't change Neko's settings,
# see other sign-ins, or let anyone else in.
PROFILE = {"is_admin": False, "can_login": True, "can_connect": True, "can_watch": True, "can_host": True,
           "can_share_media": False, "can_access_clipboard": True, "sends_inactive_cursor": True,
           "can_see_inactive_cursors": False}


class Unavailable(Exception):
    """The workspace server didn't answer, or refused the gateway."""


class Full(Exception):
    """Every browser the workspace server has for this tool is in use — or, when `server` is true, the
    server already runs as many browsers as it may, all of them in use."""

    def __init__(self, server=False):
        super().__init__("server" if server else "tool")
        self.server = server


class Starting(Exception):
    """The person's browser is being started; ask again in a moment."""


def mode(tool):
    """'agent', 'static', or '' when Open goes to the tool's own site."""
    if (tool.get("signin") or "") != "shared":
        return ""
    if (tool.get("workspace_mode") or "") == "agent":
        return "agent"
    return "static" if browsers(tool) else ""


def lease_id(turn):
    """What the agent knows a turn by. Includes when it started, so a fresh database's turn #5 can never
    be mistaken for an old one."""
    return f"t{int(turn['id'])}.{int(turn['started'] * 1000)}"


def browsers(tool):
    """The tool's fixed browser addresses (static mode), in order. Empty unless the tool is a shared
    company account using them."""
    if (tool.get("signin") or "") != "shared" or (tool.get("workspace_mode") or "") == "agent":
        return []
    out = []
    for line in (tool.get("workspace_url") or "").splitlines():
        line = line.strip()
        if line.lower().startswith(("https://", "http://")) and line not in out:
            out.append(line)
    return out[:MAX_BROWSERS]


def username(person_id):
    """A person's name in every workspace browser. It never changes, because Neko's page remembers the
    last name used in a browser and prefers it over the one in the link."""
    return f"swangz-{int(person_id)}"


def link(browser, user, password):
    """The browser's address carrying this turn's sign-in. Neko reads usr/pwd, signs in, and strips them
    from the address bar straight away."""
    parts = urllib.parse.urlsplit(browser)
    query = urllib.parse.parse_qsl(parts.query) + [("usr", user), ("pwd", password)]
    return urllib.parse.urlunsplit(parts._replace(path=parts.path or "/", query=urllib.parse.urlencode(query)))


def api_root(browser):
    """Where a browser's API lives: its address without query or fragment (Neko may sit under a path)."""
    parts = urllib.parse.urlsplit(browser)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


class Workspaces:
    def __init__(self, gw):
        self.gw = gw
        self._sweeping = threading.Lock()
        self._locks = {}  # browser -> lock: a sign-in is never made and removed on one browser at once
        self._locks_guard = threading.Lock()
        self._complained = {}
        self.relay = Relay(gw)

    @property
    def managed(self):
        return bool(self.gw.settings.workspace_token)

    # ------------------------------------------------------------ where the browsers run

    @property
    def active(self):
        """Where Open gets browsers now: 'server', 'windows' or 'mac'."""
        host = self.gw.db.get_setting("workspace_host", "server")
        return host if host in HOSTS else "server"

    def connection(self, host):
        """-> (the agent's address, its token), or None while that place isn't connected."""
        if host == "server":
            s = self.gw.settings
            return (s.workspace_agent_url, s.workspace_agent_token) if s.workspace_agent_url and s.workspace_agent_token else None
        row = self.gw.db.one("SELECT url, token FROM workspace_hosts WHERE id = ?", (host,)) if host in COMPUTERS else None
        return (row["url"], row["token"]) if row and row["url"] else None

    @property
    def agent_ready(self):
        return self.connection(self.active) is not None

    def hosts(self):
        """Each place the browsers can run, for the console: set up, online, what it last reported."""
        out = []
        for host, label in HOSTS.items():
            item = {"id": host, "label": label, "active": host == self.active}
            if host == "server":
                item.update(kind="server", set_up=self.connection("server") is not None)
            else:
                row = self.gw.db.one("SELECT url, info, created, seen FROM workspace_hosts WHERE id = ?", (host,))
                info = json.loads(row["info"] or "{}") if row else {}
                item.update(kind="computer", set_up=bool(row), connected=bool(row and row["url"]),
                            seen=row["seen"] if row else None, created=row["created"] if row else None,
                            online=bool(row and row["seen"] and time.time() - row["seen"] < ONLINE_SECONDS),
                            info=info if isinstance(info, dict) else {})
            out.append(item)
        return out

    def new_key(self, host):
        """A new key for this computer. Its old key stops working, and it is offline until it checks in
        with this one."""
        if host not in COMPUTERS:
            raise ValueError("only a computer gets a key here; the rented server's is in the gateway's settings")
        key = secrets.token_hex(32)
        self.gw.db.x("INSERT INTO workspace_hosts(id, token, created) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE"
                     " SET token = excluded.token, url = '', seen = NULL", (host, key, time.time()))
        return key

    def forget(self, host):
        if host == self.active:
            raise ValueError(f"Open uses {HOSTS[host]} now — switch to another place first")
        self.gw.db.x("DELETE FROM workspace_hosts WHERE id = ?", (host,))

    def use(self, host, by):
        """Make `host` where Open gets browsers. One place at a time: anyone in a browser elsewhere is moved
        off — their turn ends; Open again gives them one here — and their sign-in there is removed as soon
        as that place answers. -> how many turns ended."""
        from . import turns

        if host not in HOSTS:
            raise ValueError("no such place")
        if self.connection(host) is None:
            raise ValueError(f"{HOSTS[host]} isn't connected yet")
        with self.gw.db.tx():
            self.gw.db.set_setting("workspace_host", host)
            moved = self.gw.db.q("SELECT tool_id, person_id FROM tool_turns WHERE ended IS NULL AND workspace LIKE 'agent:%'"
                                 " AND (CASE WHEN ws_host = '' THEN 'server' ELSE ws_host END) != ?", (host,))
            for t in moved:
                turns.end(self.gw.db, t["tool_id"], t["person_id"], by, f"the company browsers moved to {HOSTS[host]}")
        self.soon()
        return len(moved)

    def hello(self, host, token, url, info):
        """A workspace machine checking in. -> what it should run: the tools that need browsers and how many,
        and the video relay. Raises PermissionError for a wrong key, ValueError for a bad address."""
        if host == "server":
            known = self.gw.settings.workspace_agent_token
        else:
            row = self.gw.db.one("SELECT token FROM workspace_hosts WHERE id = ?", (host,)) if host in COMPUTERS else None
            known = row["token"] if row else ""
        if not (known and token and hmac.compare_digest(token.encode(), known.encode())):
            raise PermissionError(host)
        if host in COMPUTERS:  # the rented server's address is fixed in the gateway's settings
            if not (url.startswith("https://") and len(url) <= 300 and " " not in url):
                raise ValueError("url must be the agent's https address")
            info = info if isinstance(info, dict) else {}
            self.gw.db.x("UPDATE workspace_hosts SET url = ?, info = ?, seen = ? WHERE id = ?",
                         (url.rstrip("/"), json.dumps(info)[:4000], time.time(), host))
        return {"ok": True, "active": host == self.active, "tools": self.wanted(), "ice_servers": self.relay.ice_servers()}

    def wanted(self):
        """{tool: {start_url, browsers}}: every shared tool that opens into company browsers, and how many
        people may be on it at once — one browser each."""
        rows = self.gw.db.q("SELECT id, url, seats_at_once FROM tools WHERE signin = 'shared' AND workspace_mode = 'agent'"
                            " AND archived = 0")
        return {r["id"]: {"start_url": r["url"] if (r["url"] or "").startswith(("https://", "http://")) else "",
                          "browsers": max(1, min(MAX_BROWSERS, int(r["seats_at_once"] or 1)))} for r in rows}

    def has_browser(self, turn_id):
        """Has this turn actually been given a browser (not just asked for one)?"""
        where = self.gw.db.scalar("SELECT workspace FROM tool_turns WHERE id = ?", (turn_id,)) or ""
        return where not in ("", "agent:")

    def _lock(self, browser):
        with self._locks_guard:
            return self._locks.setdefault(api_root(browser), threading.Lock())

    # ------------------------------------------------------------ handing out browsers

    def assign(self, tool, turn):
        """Give this turn a browser nobody else on the tool is using, and keep it for the whole turn.

        Call it in the same transaction as turns.take, so two people opening at once can't be handed
        the same browser. -> the address, or None when every browser is taken."""
        if turn.get("workspace"):
            return turn["workspace"]
        busy = {r["workspace"] for r in self.gw.db.q(
            "SELECT workspace FROM tool_turns WHERE tool_id = ? AND ended IS NULL AND id != ?", (tool["id"], turn["id"]))}
        free = next((b for b in browsers(tool) if b not in busy), None)
        if free:
            self.gw.db.x("UPDATE tool_turns SET workspace = ? WHERE id = ?", (free, turn["id"]))
        return free

    def open(self, tool, turn, person):
        """-> where to send this person: their browser, signed in for this turn when the gateway manages
        the workspace. Raises Starting (agent: ask again shortly), Full (agent: every browser busy) or
        Unavailable (the workspace didn't answer)."""
        if mode(tool) == "agent":
            return self._open_agent(tool, turn, person)
        browser = turn["workspace"]
        if not self.managed:
            return browser
        user = username(person["id"])
        password = secrets.token_urlsafe(18)
        profile = {**PROFILE, "name": person["name"]}
        with self._lock(browser):
            # written first, so a sign-in can never exist on a browser without a turn that will remove it
            self.gw.db.x("UPDATE tool_turns SET ws_member = ?, ws_closed = NULL WHERE id = ?", (user, turn["id"]))
            # opened again in a new tab: the old tab lets go, or Neko refuses the second sign-in
            self._call(browser, "POST", f"/api/sessions/{user}/disconnect", ok=(204, 404))
            created = self._call(browser, "POST", "/api/members",
                                 {"username": user, "password": password, "profile": profile}, ok=(200, 422))
            if created == 422:  # still there from an earlier turn: it gets this turn's password
                self._call(browser, "POST", f"/api/members/{user}", profile, ok=(204,))
                self._call(browser, "POST", f"/api/members/{user}/password", {"password": password}, ok=(204,))
        return link(browser, user, password)

    def _open_agent(self, tool, turn, person):
        host = self.active
        if not self.agent_ready:
            raise Unavailable(f"{HOSTS[host]} isn't connected (Settings → Company browsers)")
        user = username(person["id"])
        # recorded first: whatever happens next, this turn's end will tell that place to let go
        self.gw.db.x("UPDATE tool_turns SET workspace = CASE WHEN workspace LIKE 'agent:_%' THEN workspace"
                     " ELSE 'agent:' END, ws_member = ?, ws_closed = NULL, ws_host = ? WHERE id = ?",
                     (user, host, turn["id"]))
        status, out = self._agent("POST", "/allocate", {"tool": tool["id"], "lease": lease_id(turn), "user": user,
                                                        "name": person["name"]}, ok=(200, 202, 409), host=host)
        if status == 409:
            raise Full(server=out.get("full") == "server")
        if status == 202:
            raise Starting(out.get("slot"))
        url = str(out.get("url") or "")
        if not url.lower().startswith(("https://", "http://")):
            raise Unavailable("the workspace server sent no usable address")
        self.gw.db.x("UPDATE tool_turns SET workspace = ? WHERE id = ?", ("agent:" + str(out.get("slot") or "?"), turn["id"]))
        return url

    # ------------------------------------------------------------ the workspace server, for the console

    def agent_status(self, host=None):
        """Every browser one place has (the one in use, unless named), and whether it is healthy."""
        _, health = self._agent("GET", "/health", host=host)
        _, status = self._agent("GET", "/status", host=host)
        return {"health": health, **status}

    def admin_open(self, slot, name, host=None):
        """An admin signs a browser in to its tool. -> {"state": "ready", "url"} or {"state": "starting"}.
        Any place, not only the one in use: a computer's browsers can be signed in before switching to it."""
        _, out = self._agent("POST", "/admin-open", {"slot": slot, "name": name}, ok=(200, 202), host=host)
        return out

    def admin_close(self, slot, host=None):
        self._agent("POST", "/admin-close", {"slot": slot}, ok=(200, 404), host=host)

    # ------------------------------------------------------------ taking them back

    def close(self, turn):
        """Remove the sign-in a finished turn had. Deleting the member also ends its session in Neko;
        in agent mode, the agent does that and recycles the browser."""
        browser, user = turn["workspace"], turn["ws_member"]
        if browser.startswith("agent:"):
            host = turn.get("ws_host") or "server"  # where its browser is, which may no longer be the place in use
            if self.connection(host):
                self._agent("POST", "/release", {"lease": lease_id(turn)}, ok=(200, 404), host=host)
        elif user and browser and self.managed:
            with self._lock(browser):
                # the same person may already be back on this browser with a newer turn: leave that one be
                again = self.gw.db.one("SELECT 1 FROM tool_turns WHERE workspace = ? AND ws_member = ? AND ended IS NULL"
                                       " AND id != ?", (browser, user, turn["id"]))
                if not again:
                    self._call(browser, "DELETE", f"/api/members/{user}", ok=(204, 404))
        self.gw.db.x("UPDATE tool_turns SET ws_closed = ? WHERE id = ?", (time.time(), turn["id"]))
        self._complained.pop(turn["id"], None)

    def sweep(self):
        """Close the sign-ins of every turn that has ended. Runs every few seconds when the gateway manages
        the workspace, and straight after someone hands a turn back or an admin takes one."""
        from . import turns

        with self._sweeping:
            turns.expire(self.gw.db)
            from . import reporting
            reporting.close_week_turns(self.gw)
            for turn in self.gw.db.q("SELECT * FROM tool_turns WHERE ended IS NOT NULL AND ws_member != ''"
                                     " AND ws_closed IS NULL ORDER BY id"):
                try:
                    self.close(turn)
                except Unavailable as exc:  # tried again next sweep
                    last = self._complained.get(turn["id"], 0)
                    if time.time() - last >= COMPLAIN_EVERY:
                        self._complained[turn["id"]] = time.time()
                        self.gw.log(f"workspace: could not remove {turn['ws_member']}'s sign-in yet: {exc}")

    def soon(self):
        """Sweep now, off the request thread."""
        threading.Thread(target=self._sweep_quietly, name="workspace-sweep", daemon=True).start()

    def start(self, every=SWEEP_SECONDS):
        def loop():
            while True:
                self._sweep_quietly()
                time.sleep(every)

        threading.Thread(target=loop, name="workspace", daemon=True).start()

    def _sweep_quietly(self):
        try:
            self.sweep()
        except Exception as exc:
            self.gw.log(f"workspace clean-up failed: {exc!r}")

    # ------------------------------------------------------------ the agent's API and Neko's

    def _agent(self, method, path, body=None, ok=(200,), host=None):
        """One call to the Workspace Agent at one place (the one in use, unless named).
        -> (status, JSON reply), if the status is one of `ok`."""
        host = host or self.active
        conn = self.connection(host)
        if conn is None:
            raise Unavailable(f"{HOSTS.get(host, host)} isn't connected")
        root, token = conn
        req = urllib.request.Request(root.rstrip("/") + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + token,
                                              "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=AGENT_TIMEOUT) as resp:
                status, raw = resp.status, resp.read(256 * 1024)
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read(64 * 1024)
            exc.close()
        except (urllib.error.URLError, OSError) as exc:
            raise Unavailable(f"{HOSTS.get(host, host)} did not answer ({getattr(exc, 'reason', exc)})") from None
        try:
            out = json.loads(raw or b"{}")
        except ValueError:
            out = {}
        if status not in ok:
            raise Unavailable(f"{HOSTS.get(host, host)} answered {method} {path} with {status}: "
                              f"{(out.get('error') if isinstance(out, dict) else '') or 'no reason given'}")
        return status, out if isinstance(out, dict) else {}

    def _call(self, browser, method, path, body=None, ok=(200, 204)):
        """One call to a browser's API with the workspace token. -> the HTTP status, if it is one of `ok`."""
        root = api_root(browser)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(root + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self.gw.settings.workspace_token,
            "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                status = resp.status
                resp.read(64 * 1024)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        except (urllib.error.URLError, OSError) as exc:
            raise Unavailable(f"{root} did not answer ({getattr(exc, 'reason', exc)})") from None
        if status not in ok:
            raise Unavailable(f"{root} answered {method} {path} with {status}")
        return status


class Relay:
    """The video relay (TURN) for company browsers on Swangz's own computers. Nothing on the internet can
    reach such a computer, so the browser and the person's screen both connect out to the relay and meet
    there. The gateway keeps the relay's secret and hands out credentials that run out (RELAY_TTL); the
    computer passes them to its browsers, and they to the people working in them.

    Cloudflare's relay (GATEWAY_TURN_CLOUDFLARE_KEY_ID / _TOKEN) is asked for credentials; your own coturn
    (GATEWAY_TURN_URLS / GATEWAY_TURN_SECRET, its use-auth-secret) gets them made here."""

    CLOUDFLARE = "https://rtc.live.cloudflare.com/v1/turn/keys/{}/credentials/generate-ice-servers"

    def __init__(self, gw):
        self.gw = gw
        self._lock = threading.Lock()
        self._cached, self._until = [], 0.0

    @property
    def kind(self):
        s = self.gw.settings
        if s.turn_cloudflare_key_id and s.turn_cloudflare_token:
            return "cloudflare"
        return "own" if s.turn_urls and s.turn_secret else ""

    def ice_servers(self):
        """[{urls, username, credential}, …] like a browser's iceServers, or [] with no relay set up."""
        kind = self.kind
        if not kind:
            return []
        with self._lock:
            if self._cached and time.time() < self._until:
                return self._cached
            try:
                servers = self._cloudflare() if kind == "cloudflare" else self._own()
            except Unavailable as exc:
                self.gw.log(f"video relay: {exc}")
                return self._cached  # the last ones, while they last
            self._cached, self._until = servers, time.time() + RELAY_TTL / 2
            return servers

    def _own(self):
        """coturn's REST credentials: the username is when they run out, the password its HMAC."""
        s = self.gw.settings
        user = f"{int(time.time()) + RELAY_TTL}:swangz"
        password = base64.b64encode(hmac.new(s.turn_secret.encode(), user.encode(), hashlib.sha1).digest()).decode()
        return [{"urls": list(s.turn_urls), "username": user, "credential": password}]

    def _cloudflare(self):
        s = self.gw.settings
        req = urllib.request.Request(self.CLOUDFLARE.format(urllib.parse.quote(s.turn_cloudflare_key_id, safe="")),
                                     method="POST", data=json.dumps({"ttl": RELAY_TTL}).encode(),
                                     headers={"Authorization": "Bearer " + s.turn_cloudflare_token,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                out = json.loads(resp.read(64 * 1024))
        except urllib.error.HTTPError as exc:
            exc.close()
            raise Unavailable(f"Cloudflare refused new relay credentials ({exc.code}) - check the TURN key") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise Unavailable(f"Cloudflare didn't answer ({getattr(exc, 'reason', exc)})") from None
        servers = []
        for server in out.get("iceServers") or [] if isinstance(out, dict) else []:
            urls = server.get("urls") if isinstance(server, dict) else None
            urls = [urls] if isinstance(urls, str) else list(urls or [])
            # browsers block port 53, and a relay address that times out only slows the connection down
            urls = [u for u in urls if isinstance(u, str) and not u.split("?")[0].endswith(":53")]
            if urls:
                servers.append({**server, "urls": urls})
        if not servers:
            raise Unavailable("Cloudflare sent no relay addresses")
        return servers
