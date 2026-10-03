"""The shared workspace: company browsers on Swangz's own server, each signed in to a tool once by an admin.

For a `shared` tool, `tools.workspace_url` holds one or more browser addresses, one per line. Each is a
Neko browser (github.com/m1k1o/neko): one Chromium, one screen, with a persistent profile that an admin
has signed in to the tool by hand. The list is a pool. Everyone holding a turn gets a browser to
themselves, so as many people can work at once as there are browsers (and `seats_at_once` allows).

With GATEWAY_WORKSPACE_TOKEN set (Neko's API token, the same on every browser) the gateway also decides
who gets into each browser:

  * Open makes a sign-in for this person on their browser: their own workspace username
    (swangz-<person id>) with a new random password, sent along in the link. Nobody else has a sign-in
    there, so nobody else gets in.
  * When the turn ends (handed back, run out, taken back, suspended) the gateway deletes that sign-in,
    and Neko drops the session on the spot.

The tool's own password never reaches the gateway. It lives in the browser profile, on that server.
Without the token, Open still hands out one browser per person, but sends them to the plain address and
the browser's own login decides who gets in.
"""

import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 10
SWEEP_SECONDS = 15
MAX_BROWSERS = 20
COMPLAIN_EVERY = 600  # a workspace that stays down is logged every ten minutes, not every sweep

# What a staff member may do in their browser. Not an admin of it: they can't change Neko's settings,
# see other sign-ins, or let anyone else in.
PROFILE = {"is_admin": False, "can_login": True, "can_connect": True, "can_watch": True, "can_host": True,
           "can_share_media": False, "can_access_clipboard": True, "sends_inactive_cursor": True,
           "can_see_inactive_cursors": False}


class Unavailable(Exception):
    """The workspace server didn't answer, or refused the gateway."""


def browsers(tool):
    """The tool's browser addresses, in order. Empty unless the tool is a shared company account."""
    if (tool.get("signin") or "") != "shared":
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

    @property
    def managed(self):
        return bool(self.gw.settings.workspace_token)

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

    def open(self, turn, person):
        """-> where to send this person: their browser, signed in for this turn when the gateway manages
        the workspace. Raises Unavailable when the browser's server doesn't answer."""
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

    # ------------------------------------------------------------ taking them back

    def close(self, turn):
        """Remove the sign-in a finished turn had. Deleting the member also ends its session in Neko."""
        browser, user = turn["workspace"], turn["ws_member"]
        if user and browser and self.managed:
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

    # ------------------------------------------------------------ Neko's API

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
