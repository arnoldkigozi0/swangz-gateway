"""W4: what the Hub's answers mean for the workspace window on this device (docs/W4-THREAT-NOTE.md).

One reducer (`apply`) reads the workspace block wherever an authenticated answer carries it: the heartbeat, the
manifest and `/device/open`. `failure` handles calls that got no usable answer. The result is a small latch file,
written before anything is closed or deleted, that says whether Open is refused and which folders still have to be
purged. It holds ids, states and generations only; nothing from inside the browser's folder is ever read.

Close: only the window this app started (`Launcher.close`). Purge: only `Profiles.retire(profile_id, owner)` for the
enrolled owner's folders, never `retire_all`, and only on an authenticated `retired` or a higher generation.
"""
import json
import time

from . import browser_profiles as bp

LATCH = "workspace-state.json"
STATES = ("active", "suspended", "retired")
GRACE_FAILURES = 2  # ruling 2: the last two check-ins both failed ...
NOTICE_PURGED = "Your admin removed the Swangz workspace from this device. Its saved sign-ins were deleted."
NOTICE_PURGE_FAILED = "Swangz couldn't delete the workspace folder your admin removed. It will try again; Open stays off until then."


class Malformed(Exception):
    pass


def parse(workspace):
    """A contract-2 workspace block -> (state, generation). Anything else raises Malformed (ruling 2 and 3)."""
    if not isinstance(workspace, dict):
        raise Malformed
    state, generation = workspace.get("state"), workspace.get("generation")
    if not isinstance(state, str) or state not in STATES or type(generation) is not int or generation < 1:
        raise Malformed
    return state, generation


def _owner_key(owner):
    f = owner.fields
    return {"origin": f["origin"], "person_id": f["person_id"], "device_id": f["device_id"]}


class WorkspaceState:
    def __init__(self, client, monotonic=time.monotonic):
        self.client, self.monotonic = client, monotonic
        self.last_answer = monotonic()  # app start counts as fresh: the grace never starts already spent
        self.failures = 0

    # ------------------------------------------------------------ the latch

    @property
    def path(self):
        return self.client.paths.data / LATCH

    def latch(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            return {"refused": "workspace_unknown"}  # an unreadable latch refuses; it never purges
        return data if isinstance(data, dict) else {"refused": "workspace_unknown"}

    def _save(self, data):
        from .core import write_private
        self.client.paths.data.mkdir(parents=True, exist_ok=True)
        write_private(self.path, json.dumps(data))

    def _update(self, **changes):
        data = {**self.latch(), **changes}
        self._save(data)
        return data

    # ------------------------------------------------------------ helpers

    def _owner(self):
        """The enrolled owner from the stored contract-2 manifest, or None."""
        from . import workspace_launcher as wl
        browser = (self.client.store.manifest() or {}).get("browser") or {}
        device = self.client.store.device() or {}
        if not isinstance(browser, dict) or browser.get("contract") != 2:
            return None
        try:
            return wl.owner(device.get("server"), browser.get("person_id"), browser.get("device_id"))
        except wl.LaunchError:
            return None

    def close(self):
        launcher = getattr(self.client, "launcher", None)
        if launcher is not None:
            try:
                launcher.close()
            except OSError:
                pass  # a failed close never defers a purge (ruling 4)

    def _profiles(self):
        return bp.Profiles(self.client.paths.data)

    def refuse(self, code, close=True):
        self._update(refused=code)
        if close:
            self.close()

    # ------------------------------------------------------------ authenticated answers

    def apply(self, block):
        """`block` is {"contract": 2, "workspace": {...}} from an authenticated 200 answer, or None/other when the
        answer did not carry contract 2 (no change)."""
        if not isinstance(block, dict) or type(block.get("contract")) is not int or block.get("contract") != 2:
            return
        self.answered()
        try:
            state, generation = parse(block.get("workspace"))
        except Malformed:
            self.refuse("workspace_unknown")
            return
        owner = self._owner()
        if state == "suspended":
            self._update(state=state, generation=generation)
            self.refuse("not_active")
            return
        if state == "retired":
            self._purge(owner, state, generation, lambda have: True, "retired")
            return
        folders = self._find(owner)
        have = max((g for _, g in folders), default=None)
        if have is not None and generation < have:
            self._update(state=state, generation=generation)
            self.refuse("generation_rollback", close=False)
            return
        if have is not None and generation > have:
            self._purge(owner, state, generation, lambda g: g < generation, None)
            return
        data = self.latch()
        if data.get("purge_pending"):
            self._update(state=state, generation=generation, keep_refused=None)
            self.resume()
            return
        self._update(state=state, generation=generation, refused=None)

    def answered(self):
        """Any authenticated answer: the offline grace starts again, and an offline refusal ends."""
        self.last_answer, self.failures = self.monotonic(), 0
        if self.latch().get("refused") == "offline":
            self._update(refused=None)

    def _find(self, owner):
        if owner is None:
            return []
        try:
            return self._profiles().find(owner)
        except (bp.ProfileError, OSError):
            return []

    def _purge(self, owner, state, generation, select, keep_refused):
        """Ruling 4: latch first, refuse, close, retire, then clear. A failure keeps it pending."""
        targets = [pid for pid, g in self._find(owner) if select(g)]
        latch = {"state": state, "generation": generation, "refused": keep_refused or "purge_pending",
                 "keep_refused": keep_refused}
        if targets:
            latch["purge_pending"] = targets
            latch["owner"] = _owner_key(owner)
        self._update(**latch)
        self.close()
        self.resume()

    def resume(self):
        """Retry a pending purge (app start, every heartbeat, before Open). -> True when nothing is pending."""
        data = self.latch()
        pending = data.get("purge_pending") or []
        if not pending:
            return True
        owner = self._owner()
        if owner is None or _owner_key(owner) != data.get("owner"):
            return False  # only the enrolled owner's folders, and only with that owner's marker
        profiles, left, error = self._profiles(), [], None
        for pid in pending:
            try:
                profiles.retire(pid, owner)
            except FileNotFoundError:
                continue
            except bp.ProfileError as exc:
                if exc.code == "marker_invalid":
                    try:
                        (profiles.root / pid).lstat()
                    except FileNotFoundError:
                        continue  # already gone
                left.append(pid)
                error = exc.code
            except OSError:
                left.append(pid)
                error = "purge_failed"
        if left:
            self._update(purge_pending=left, purge_error=error, notice=NOTICE_PURGE_FAILED)
            return False
        self._update(purge_pending=None, owner=None, purge_error=None, notice=NOTICE_PURGED,
                     refused=data.get("keep_refused"))
        return True

    # ------------------------------------------------------------ calls without a usable answer

    def failure(self, exc):
        """A device call failed. 401/403 -> close and refuse now. Transport, 5xx, non-JSON -> close only after two
        failed check-ins with the last authenticated answer at least 2 x the heartbeat old (D-021)."""
        from .core import ApiFailure, KeyRotated, Revoked, HEARTBEAT_SECONDS
        if isinstance(exc, (KeyRotated,)) or not isinstance(exc, ApiFailure):
            return
        if isinstance(exc, Revoked):
            self.revoked()
            return
        if exc.status in (401, 403):
            self.refuse("refused_by_hub")
            return
        self.failures += 1
        if self.failures >= GRACE_FAILURES and self.monotonic() - self.last_answer >= 2 * HEARTBEAT_SECONDS:
            self.refuse("offline")

    def warning(self):
        """The one-time 'window will close' line while the grace is running out, or None."""
        from .core import HEARTBEAT_SECONDS
        if self.failures >= 1 and self.monotonic() - self.last_answer >= 2 * HEARTBEAT_SECONDS - 120:
            return "Can't reach Swangz: your workspace window will close in 2 minutes. Save your work."
        return None

    def revoked(self):
        """401 device_revoked: close before the device is wiped. The folder is not purged."""
        self.refuse("revoked")

    def signed_out(self):
        self.refuse("signed_out")

    # ------------------------------------------------------------ Open

    def check_open(self):
        """Raise LaunchError when Open is refused. A pending purge is retried first."""
        from . import workspace_launcher as wl
        data = self.latch()
        if data.get("purge_pending") and not self.resume():
            raise wl.LaunchError("purge_pending")
        data = self.latch()
        refused = data.get("refused")
        if refused:
            raise wl.LaunchError(refused)
