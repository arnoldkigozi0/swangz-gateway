"""The Swangz app's side of device key rotation (D-002): rotate when the key is old, write the new key to the store
before using it, confirm with one device call, reload on device_key_rotated (never wipe), and report where the key
is kept. Runs against a small local stand-in for the Hub's /api/device/* contract (docs/CLIENT.md, schema v22), so it
does not depend on the server branch that implements it."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from swangz_client import agents, cli, core, keystore

from .test_client import ClientBase
from .test_client_credentials import MemoryCredentials

DAY = 86400


class Hub:
    """The device endpoints as docs/CLIENT.md describes them: keys are current, in grace, rotated (replaced) or revoked."""

    def __init__(self, rotate_after_days=30):
        self.keys = {}  # secret -> {"id", "state"}
        self.log = []  # (method, path, key id or None)
        self.heartbeats = []  # bodies
        self.rotate_after_days = rotate_after_days
        self.device_revoked = False
        self.rotate_status = None  # e.g. (429, "slow_down") to refuse a rotation
        self.drop_next_rotate_response = False
        self.first_use = None  # called with the secret the first time a pending key is used
        self.refuse_new_key = False  # 500 for a key that has never been used (simulates a failing confirm)
        self.on_call = None  # called as (path, secret) before a request is handled, outside the Hub's lock
        self.counter = 0
        self.lock = threading.Lock()

    def add(self, secret, state="current"):
        self.counter += 1
        self.keys[secret] = {"id": f"key-{self.counter}", "state": state, "used": state == "current", "old": None}
        return self.keys[secret]["id"]

    def count(self, path):
        return sum(1 for _, p, _ in self.log if p == path)

    def handle(self, method, path, key, body):
        """-> (status, dict) or None to drop the connection."""
        if self.on_call:
            self.on_call(path, key)
        with self.lock:
            entry = self.keys.get(key or "")
            self.log.append((method, path, entry["id"] if entry else None))
            if not entry:
                return 401, {"code": "device_unknown", "error": "unknown"}
            if self.device_revoked or entry["state"] == "revoked":
                return 401, {"code": "device_revoked", "error": "This device was disconnected."}
            if entry["state"] == "rotated":
                return 401, {"code": "device_key_rotated", "error": "This key was replaced by a newer one."}
            if not entry["used"]:
                if self.refuse_new_key:
                    return 500, {"error": "try later"}
                if self.first_use:
                    self.first_use(key)
            if path == "/api/device/rotate":
                if self.rotate_status:
                    return self.rotate_status[0], {"code": self.rotate_status[1], "error": self.rotate_status[1]}
                if entry["state"] == "grace":
                    # docs/CLIENT.md: during grace a rotation is reissued, which revokes the unused new key
                    pending = [v for v in self.keys.values() if v["state"] == "pending" and v["old"] == key]
                    if not pending:
                        return 409, {"code": "rotation_pending", "error": "rotation_pending"}
                    for v in pending:
                        v["state"] = "revoked"
                new_secret = f"sgw_new{self.counter + 1}_" + "x" * 40
                new_id = self.add(new_secret, "pending")
                entry["state"], self.keys[new_secret]["old"] = "grace", key
                if self.drop_next_rotate_response:
                    self.drop_next_rotate_response = False
                    return None
                return 200, {"key": new_secret, "key_id": new_id, "device_id": "dev-1", "rotate_after_days": 30}
            # any other device call: the new key's first use ends the old key
            if entry["state"] == "pending":
                entry["state"], entry["used"] = "current", True
                old = self.keys.get(entry["old"])
                if old:
                    old["state"] = "rotated"
            if path == "/api/device/heartbeat":
                self.heartbeats.append(body)
                return 200, {}
            if path == "/api/device/manifest":
                return 200, {"packages": [], "apps": [], "client": {}, "recording": "Swangz records access.",
                             "credential": {"rotate_after_days": self.rotate_after_days, "issued": time.time()}}
            if path == "/api/device/signout":
                for e in self.keys.values():
                    e["state"] = "revoked"
                return 200, {}
            return 404, {"error": "not found"}

    def end_grace(self):
        """The 10 minutes are up: a key still in grace is retired (and says device_key_rotated from now on)."""
        for e in self.keys.values():
            if e["state"] == "grace":
                e["state"] = "rotated"


def serve(hub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do(self):
            n = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(n) if n else b""
            body = json.loads(raw) if raw else None
            auth = self.headers.get("authorization", "")
            out = hub.handle(self.command, self.path, auth[7:] if auth.startswith("Bearer ") else None, body)
            if out is None:
                self.connection.close()
                return
            payload = json.dumps(out[1]).encode()
            self.send_response(out[0])
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class NoKeychain:
    """A device with no keychain: everything falls back to the protected file."""

    def put(self, server, key_id, secret):
        raise keystore.Unavailable("no keychain")

    def get(self, server, key_id):
        return None

    def delete(self, server, key_id):
        pass


class RotationBase(unittest.TestCase):
    credentials_class = MemoryCredentials
    OLD = "sgw_old_" + "a" * 40

    def setUp(self):
        self.hub = Hub()
        self.server = serve(self.hub)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.root = Path(tempfile.mkdtemp(prefix="swangz-rotation-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.paths = core.Paths(self.root / "home", self.root / "data")
        self.credentials = self.credentials_class()
        self.client = core.Client(self.paths, sleep=lambda s: None, credentials=self.credentials)
        self.old_id = self.hub.add(self.OLD)
        self.client.store.save_device(
            {"server": self.url, "key_id": self.old_id, "owner_kind": "personal", "name": "Grace's laptop",
             "person": {"name": "Grace", "email": "grace@swangzavenue.com"}, "signed_in": time.time(),
             "key_issued": time.time()}, self.OLD)
        self.client.store.save_state({"installed": {}, "last_sync": None})

    def age_key(self, days):
        info = self.client.store.device()
        info["key_issued"] = time.time() - days * DAY
        self.client.store._save_info(info)

    def device(self):
        return self.client.store.device()

    def current_key(self):
        return self.client.store.key()

    def states(self):
        return {v["id"]: v["state"] for v in self.hub.keys.values()}


class RotateWhenDue(RotationBase):
    def test_a_key_older_than_the_manifest_says_is_rotated_at_sync_and_the_new_one_becomes_current(self):
        self.age_key(31)
        out = self.client.sync()
        self.assertEqual(out["rotation"], "rotated")
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)
        new = self.current_key()
        self.assertNotEqual(new, self.OLD)
        self.assertTrue(new.startswith("sgw_new"))
        self.assertEqual(self.states()[self.old_id], "rotated")  # the new key's first call ended the old one
        self.assertEqual(self.device()["key_id"], self.hub.keys[new]["id"])
        self.assertAlmostEqual(self.device()["key_issued"], time.time(), delta=60)
        self.assertNotIn("next_key_id", self.device())
        # the next sync uses the new key and does not rotate again
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)

    def test_a_key_younger_than_thirty_days_is_left_alone(self):
        self.age_key(5)
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertEqual(self.hub.count("/api/device/rotate"), 0)
        self.assertEqual(self.current_key(), self.OLD)

    def test_the_manifest_sets_the_age_and_thirty_is_the_default(self):
        self.hub.rotate_after_days = 3
        self.age_key(5)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        # no credential block (an older Hub): thirty days
        self.client.store.save_manifest({"packages": [], "apps": [], "client": {}, "recording": "x"})
        self.assertFalse(self.client.rotation_due())
        self.age_key(29)
        self.assertFalse(self.client.rotation_due())
        self.age_key(31)
        self.assertTrue(self.client.rotation_due())
        for bad in ("soon", 0, -4, 9999, True, None):
            self.client.store.save_manifest({"packages": [], "credential": {"rotate_after_days": bad}})
            self.age_key(31)
            self.assertTrue(self.client.rotation_due(), bad)  # nonsense falls back to thirty
            self.age_key(5)
            self.assertFalse(self.client.rotation_due(), bad)

    def test_a_device_enrolled_before_this_app_version_uses_the_hubs_issued_time(self):
        info = self.device()
        info.pop("key_issued")
        info["signed_in"] = time.time()  # recent sign-in must not hide an old key the Hub reports
        self.client.store._save_info(info)
        self.client.store.save_manifest({"packages": [], "credential": {"rotate_after_days": 30, "issued": time.time() - 40 * DAY}})
        self.assertTrue(self.client.rotation_due())

    def test_the_new_key_is_in_the_store_before_it_is_first_used(self):
        self.age_key(31)
        seen = []
        self.hub.first_use = lambda secret: seen.append((secret, self.client.store.staged()))
        self.client.sync()
        self.assertEqual(len(seen), 1)
        secret, staged = seen[0]
        self.assertEqual(staged, (self.hub.keys[secret]["id"], secret))  # written and read back, still not current
        self.assertEqual(self.client.store.device()["key_id"], self.hub.keys[secret]["id"])  # now promoted

    def test_one_device_call_with_the_new_key_confirms_it_and_nothing_else_uses_it_first(self):
        self.age_key(31)
        self.client.sync()
        new_id = self.device()["key_id"]
        calls = [(p, k) for _, p, k in self.hub.log if k == new_id]
        # the confirming check-in is the new key's first call; the sync's own next calls come later with the same key
        self.assertEqual(calls[0][0], "/api/device/heartbeat")
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)

    def test_if_the_confirming_call_fails_the_old_key_stays_current_and_the_staged_one_is_confirmed_next_time(self):
        self.age_key(31)
        self.hub.refuse_new_key = True
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertEqual(self.current_key(), self.OLD)  # nothing switched
        staged = self.client.store.staged()
        self.assertIsNotNone(staged)
        self.assertEqual(self.states()[self.old_id], "grace")
        self.hub.refuse_new_key = False
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertEqual(self.current_key(), staged[1])
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)  # not rotated twice

    def test_a_refused_or_failed_rotation_never_fails_the_sync(self):
        self.age_key(31)
        for refusal in ((429, "slow_down"), (409, "rotation_pending"), (500, "oops")):
            self.hub.rotate_status = refusal
            self.assertIsNone(self.client.sync()["rotation"], refusal)
            self.assertEqual(self.current_key(), self.OLD)
        self.assertIsNone(self.client.store.staged())

    def test_an_invalid_key_in_the_response_is_not_stored(self):
        self.age_key(31)
        original = self.hub.handle

        def bad(method, path, key, body):
            out = original(method, path, key, body)
            if path == "/api/device/rotate" and out and out[0] == 200:
                return 200, {"key": "bad\nkey", "key_id": out[1]["key_id"]}
            return out

        self.hub.handle = bad
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertIsNone(self.client.store.staged())
        self.assertEqual(self.current_key(), self.OLD)

    def test_the_key_never_lands_in_device_json_or_the_state_files(self):
        self.age_key(31)
        self.client.sync()
        new = self.current_key()
        for path in self.paths.data.rglob("*"):
            if path.is_file():
                self.assertNotIn(new, path.read_text(errors="replace"), path.name)
                self.assertNotIn(self.OLD, path.read_text(errors="replace"), path.name)


class NeverMidSession(RotationBase):
    def test_no_rotation_while_a_coding_agent_run_is_active(self):
        self.age_key(31)
        with self.client._session():
            self.assertTrue(self.client.in_session())
            self.assertIsNone(self.client.sync()["rotation"])
        self.assertEqual(self.hub.count("/api/device/rotate"), 0)
        self.assertFalse(self.client.in_session())
        self.assertEqual(self.client.sync()["rotation"], "rotated")  # at the next idle check-in

    def test_a_staged_key_is_not_switched_in_during_a_session_either(self):
        self.age_key(31)
        self.hub.refuse_new_key = True
        self.client.sync()
        self.hub.refuse_new_key = False
        with self.client._session():
            self.assertIsNone(self.client.sync()["rotation"])
            self.assertEqual(self.current_key(), self.OLD)

    def test_a_session_in_another_swangz_process_counts(self):
        self.age_key(31)
        (self.paths.data / "sessions").mkdir(parents=True)
        (self.paths.data / "sessions" / f"{os.getppid()}-1").write_text("x")  # our parent is alive
        self.assertTrue(self.client.in_session())
        self.assertIsNone(self.client.sync()["rotation"])

    def test_a_marker_records_when_the_run_started(self):
        with self.client._session():
            (marker,) = (self.paths.data / "sessions").iterdir()
            body = json.loads(marker.read_text())
            self.assertEqual(body["pid"], os.getpid())
            self.assertAlmostEqual(body["started"], time.time(), delta=30)
            self.assertTrue(self.client.in_session())
        self.assertFalse(self.client.in_session())

    def test_a_marker_with_a_start_time_far_in_the_past_is_not_believed_when_its_pid_was_reused(self):
        marker = self.paths.data / "sessions" / f"{os.getppid()}-1"  # a live pid that now belongs to something else
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"pid": os.getppid(), "started": time.time() - core.SESSION_MAX_AGE - 60}))
        self.age_key(31)
        self.assertFalse(self.client.in_session())
        self.assertFalse(marker.exists())
        self.assertEqual(self.client.sync()["rotation"], "rotated")

    def test_a_recent_marker_with_a_live_pid_still_blocks_rotation(self):
        marker = self.paths.data / "sessions" / f"{os.getppid()}-2"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"pid": os.getppid(), "started": time.time() - 3600}))
        self.age_key(31)
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertTrue(marker.exists())

    def test_an_old_style_marker_is_aged_by_its_file_when_it_has_no_start_time(self):
        marker = self.paths.data / "sessions" / f"{os.getppid()}-3"
        marker.parent.mkdir(parents=True)
        marker.write_text("x")
        old = time.time() - core.SESSION_MAX_AGE - 60
        os.utime(marker, (old, old))
        self.assertFalse(self.client.in_session())
        self.assertFalse(marker.exists())

    def test_a_marker_left_by_a_process_that_has_ended_is_ignored_and_cleared(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        marker = self.paths.data / "sessions" / f"{child.pid}-1"
        marker.parent.mkdir(parents=True)
        marker.write_text("x")
        self.age_key(31)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertFalse(marker.exists())

    def test_run_agent_marks_the_session_and_clears_it_when_the_agent_exits(self):
        state = self.client.store.state()
        state["installed"]["claude-code"] = {"base_url": self.url + "/anthropic", "mode": "scoped", "credential_config": 2}
        self.client.store.save_state(state)
        seen = []

        def fake_run(argv, env=None):
            seen.append(self.client.in_session())
            return mock.Mock(returncode=0)

        self.client.run = fake_run
        with mock.patch("swangz_client.core.shutil.which", return_value="/usr/bin/claude"):
            self.assertEqual(self.client.run_agent("claude-code"), 0)
        self.assertEqual(seen, [True])
        self.assertFalse(self.client.in_session())

        def failing(argv, env=None):
            raise OSError("boom")

        self.client.run = failing
        with mock.patch("swangz_client.core.shutil.which", return_value="/usr/bin/claude"):
            with self.assertRaises(OSError):
                self.client.run_agent("claude-code")
        self.assertFalse(self.client.in_session())


class OneRotationAtATime(RotationBase):
    """The window and `swangz sync` are separate processes on one data folder; the in-process lock cannot stop both
    rotating, and a second rotation in grace would revoke the first new key and strand the device (F-C1)."""

    def other_client(self):
        return core.Client(self.paths, sleep=lambda s: None, credentials=self.credentials)

    def lock_path(self):
        return self.paths.data / "rotate.lock"

    def test_a_second_process_starting_mid_rotation_skips_and_the_device_stays_signed_in(self):
        other = self.other_client()
        seen = {}

        def fire(path, key):
            # the first confirm (the new key's first use) happens while the first process holds the lock
            if path == "/api/device/heartbeat" and key.startswith("sgw_new") and "ran" not in seen:
                seen["ran"] = True
                seen["rotation"] = other.maintain_credential()
                seen["lock_held"] = self.lock_path().exists()

        self.hub.on_call = fire
        self.age_key(31)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertIsNone(seen["rotation"])
        self.assertTrue(seen["lock_held"])
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)
        self.assertEqual([v["state"] for v in self.hub.keys.values()].count("pending"), 0)
        self.assertNotIn("reconnect", self.device())
        new = self.current_key()
        self.assertTrue(new.startswith("sgw_new"))
        # both processes carry on with the one new key, and nobody has to reconnect
        self.assertIsNone(other.sync()["rotation"])
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertEqual(other.store.key(), new)
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)
        self.assertFalse(self.lock_path().exists())

    def interleave(self, other):
        """The other process looks at the key between our rotate response and our write of the new key."""
        real_stage = self.client.store.stage
        seen = {}

        def stage(key_id, secret):
            if "ran" not in seen:
                seen["ran"] = True
                seen["rotation"] = other.maintain_credential()
            return real_stage(key_id, secret)

        self.client.store.stage = stage
        return seen

    def test_a_second_process_in_the_gap_before_the_new_key_is_written_does_not_reissue(self):
        other = self.other_client()
        seen = self.interleave(other)
        self.age_key(31)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertIsNone(seen["rotation"])  # it found the lock held and left the key alone
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)  # so nothing was reissued or revoked
        self.assertNotIn("revoked", self.states().values())
        self.assertNotIn("reconnect", self.device())
        self.assertTrue(self.current_key().startswith("sgw_new"))
        self.assertEqual(other.store.key(), self.current_key())

    def test_without_the_lock_that_same_gap_would_reissue_and_lose_the_first_new_key(self):
        """The failure the lock prevents, shown against the same stand-in Hub."""
        other = self.other_client()
        seen = self.interleave(other)
        self.age_key(31)
        with mock.patch.object(core.RotationLock, "acquire", return_value=True):
            try:
                self.client.sync()
            except core.Revoked:
                pass
        self.assertEqual(seen["rotation"], "rotated")
        self.assertEqual(self.hub.count("/api/device/rotate"), 2)
        self.assertIn("revoked", self.states().values())  # the first new key was revoked by the reissue

    def test_two_processes_syncing_at_the_same_moment_rotate_once(self):
        others = [self.other_client() for _ in range(3)]
        everyone = [self.client] + others
        barrier = threading.Barrier(len(everyone))
        results = []
        self.age_key(31)

        def go(client):
            barrier.wait()
            results.append(client.maintain_credential())

        threads = [threading.Thread(target=go, args=(c,)) for c in everyone]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(self.hub.count("/api/device/rotate"), 1)
        self.assertEqual(results.count("rotated"), 1)
        self.assertNotIn("reconnect", self.device())
        for client in everyone:
            self.assertEqual(client.store.key(), self.current_key())
        self.assertTrue(self.current_key().startswith("sgw_new"))
        self.assertFalse(self.lock_path().exists())

    def test_a_lock_held_by_a_live_process_means_no_rotation_this_time(self):
        self.age_key(31)
        self.lock_path().write_text(json.dumps({"pid": os.getppid(), "at": time.time()}))  # our parent is alive
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertEqual(self.hub.count("/api/device/rotate"), 0)
        self.assertTrue(self.lock_path().exists())  # not ours to remove
        self.assertEqual(self.current_key(), self.OLD)

    def test_a_lock_left_by_a_process_that_has_ended_is_taken_over(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        self.lock_path().write_text(json.dumps({"pid": child.pid, "at": time.time()}))
        self.age_key(31)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertFalse(self.lock_path().exists())

    def test_a_lock_older_than_the_timeout_is_taken_over_even_if_its_pid_is_alive(self):
        self.lock_path().write_text(json.dumps({"pid": os.getppid(), "at": time.time() - core.ROTATE_LOCK_STALE - 5}))
        self.age_key(31)
        self.assertEqual(self.client.sync()["rotation"], "rotated")

    def test_an_unreadable_lock_is_judged_by_its_age(self):
        self.lock_path().write_text("{not json")
        self.age_key(31)
        self.assertIsNone(self.client.sync()["rotation"])  # fresh: maybe still being written
        old = time.time() - core.ROTATE_LOCK_STALE - 5
        os.utime(self.lock_path(), (old, old))
        self.assertEqual(self.client.sync()["rotation"], "rotated")

    def test_the_lock_is_released_when_the_rotation_fails(self):
        self.hub.rotate_status = (429, "slow_down")
        self.age_key(31)
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertFalse(self.lock_path().exists())
        self.hub.refuse_new_key = True  # the confirm fails after a successful rotate
        self.hub.rotate_status = None
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertFalse(self.lock_path().exists())

    def test_the_lock_is_released_when_the_device_turns_out_to_be_revoked(self):
        self.hub.device_revoked = True
        self.age_key(31)
        with self.assertRaises(core.Revoked):
            self.client.maintain_credential()
        self.assertFalse(self.lock_path().exists())

    def test_release_never_removes_a_lock_somebody_else_took_over(self):
        lock = core.RotationLock(self.lock_path(), lambda pid: True)
        self.assertTrue(lock.acquire())
        self.lock_path().write_text(json.dumps({"pid": 1, "at": time.time()}))  # taken over after our timeout
        lock.release()
        self.assertTrue(self.lock_path().exists())

    def test_the_lock_is_created_private_and_exclusively(self):
        lock = core.RotationLock(self.lock_path(), lambda pid: True)
        self.assertTrue(lock.acquire())
        self.assertEqual(oct(self.lock_path().stat().st_mode & 0o777), "0o600")
        again = core.RotationLock(self.lock_path(), lambda pid: True)
        self.assertFalse(again.acquire())  # the same process is not let in twice
        lock.release()
        self.assertTrue(again.acquire())
        again.release()

    def test_signing_out_removes_the_lock_file(self):
        self.lock_path().write_text(json.dumps({"pid": os.getppid(), "at": time.time()}))
        self.client.remove_everything()
        self.assertFalse(self.lock_path().exists())


class KeyRotatedNeverWipes(RotationBase):
    def staged_rotation(self):
        """A rotation whose new key reached the store but was not confirmed, and whose grace then ran out."""
        self.age_key(31)
        self.hub.refuse_new_key = True
        self.client.sync()
        self.hub.refuse_new_key = False
        self.hub.end_grace()
        return self.client.store.staged()

    def test_a_rotated_key_reloads_the_newer_key_from_the_store_and_carries_on(self):
        staged = self.staged_rotation()
        self.assertEqual(self.states()[self.old_id], "rotated")
        out = self.client.refresh()  # the call that hits device_key_rotated
        self.assertIn("packages", out)
        self.assertEqual(self.current_key(), staged[1])
        self.assertTrue(self.client.signed_in())
        self.assertNotIn("reconnect", self.device())

    def test_another_window_rotating_first_is_picked_up_without_a_staged_key(self):
        # this process still uses the old key; the store already holds the new, confirmed one
        new = "sgw_other_" + "b" * 40
        new_id = self.hub.add(new)
        self.hub.keys[self.OLD]["state"] = "rotated"
        other = core.Client(self.paths, sleep=lambda s: None, credentials=self.credentials)
        info = other.store.device()
        info["key_id"] = new_id
        other.store._save_info(info)
        self.credentials.put(self.url, new_id, new)
        calls = []
        real = self.client.api

        def api_once():
            api = real()
            if not calls:
                calls.append(1)
                api.key = self.OLD  # a call that had read the key before the other window rotated
            return api

        self.client.api = api_once
        self.client.refresh()
        self.assertEqual(self.current_key(), new)

    def test_with_no_newer_key_it_says_reconnect_and_removes_nothing(self):
        # the rotate response is lost, and the grace ends
        self.age_key(31)
        self.hub.drop_next_rotate_response = True
        self.assertIsNone(self.client.sync()["rotation"])
        self.assertIsNone(self.client.store.staged())
        self.hub.end_grace()
        state = self.client.store.state()
        state["installed"]["brand-prompts"] = {"version": "1", "kind": "tool", "name": "Brand prompts"}
        self.client.store.save_state(state)
        with self.assertRaises(core.NeedsReconnect):
            self.client.refresh()
        # nothing was wiped
        self.assertTrue(self.client.signed_in())
        self.assertEqual(self.current_key(), self.OLD)
        self.assertIn("brand-prompts", self.client.store.state()["installed"])
        self.assertTrue(self.client.status()["reconnect"])
        self.assertIn("Reconnect this device", core.RECONNECT)

    def test_it_does_not_retry_faster_than_the_heartbeat(self):
        self.age_key(31)
        self.hub.drop_next_rotate_response = True
        self.client.sync()
        self.hub.end_grace()
        with self.assertRaises(core.NeedsReconnect):
            self.client.refresh()
        calls = len(self.hub.log)
        for _ in range(3):
            with self.assertRaises(core.NeedsReconnect):
                self.client.sync()
            with self.assertRaises(core.NeedsReconnect):
                self.client.heartbeat()
        self.assertEqual(len(self.hub.log), calls)  # not one more request
        # once a heartbeat interval has passed, one try is allowed
        info = self.device()
        info["reconnect"]["at"] -= core.HEARTBEAT_SECONDS + 1
        self.client.store._save_info(info)
        with self.assertRaises(core.NeedsReconnect):
            self.client.refresh()
        self.assertEqual(len(self.hub.log), calls + 1)
        self.assertTrue(self.client.signed_in())

    def test_a_newer_key_arriving_clears_the_wait_at_once(self):
        self.age_key(31)
        self.hub.drop_next_rotate_response = True
        self.client.sync()
        self.hub.end_grace()
        with self.assertRaises(core.NeedsReconnect):
            self.client.refresh()
        new = "sgw_late_" + "c" * 40
        new_id = self.hub.add(new)
        self.client.store.stage(new_id, new)
        self.client.refresh()  # no waiting: a key newer than the refused one is in the store
        self.assertEqual(self.current_key(), new)
        self.assertNotIn("reconnect", self.device())

    def test_the_command_line_reports_it_without_removing_anything(self):
        self.age_key(31)
        self.hub.drop_next_rotate_response = True
        self.client.sync()
        self.hub.end_grace()
        lines = []
        with mock.patch.object(cli, "say", lines.append):
            self.assertEqual(cli.main(["sync"], client=self.client), 4)
        self.assertIn("Reconnect this device", " ".join(lines))
        self.assertTrue(self.client.signed_in())

    def test_the_window_shows_the_reconnect_notice_and_keeps_the_device(self):
        self.age_key(31)
        self.hub.drop_next_rotate_response = True
        self.client.sync()
        self.hub.end_grace()
        with self.assertRaises(core.NeedsReconnect):
            self.client.refresh()
        self.assertTrue(self.client.status()["reconnect"])
        self.assertTrue(self.client.status()["signed_in"])

    def test_only_device_revoked_removes_everything_including_a_staged_key(self):
        self.age_key(31)
        self.hub.refuse_new_key = True
        self.client.sync()
        staged = self.client.store.staged()
        self.assertIsNotNone(staged)
        self.assertIn((self.url, staged[0]), self.credentials.items)
        self.hub.refuse_new_key = False
        self.hub.device_revoked = True
        with self.assertRaises(core.Revoked):
            self.client.sync()
        self.assertFalse(self.client.signed_in())
        self.assertEqual(self.credentials.items, {})  # the current key, the staged one: all gone
        self.assertFalse(self.paths.data.joinpath("device.json").exists())

    def test_a_revoked_device_during_rotation_removes_everything(self):
        self.age_key(31)
        original = self.hub.handle

        def revoke_on_rotate(method, path, key, body):
            if path == "/api/device/rotate":
                return 401, {"code": "device_revoked", "error": "gone"}
            return original(method, path, key, body)

        self.hub.handle = revoke_on_rotate
        with self.assertRaises(core.Revoked):
            self.client.maintain_credential()
        self.assertFalse(self.client.signed_in())
        self.assertEqual(self.credentials.items, {})


class WhereTheKeyLives(RotationBase):
    def test_the_old_native_item_is_deleted_and_the_new_one_is_the_only_one_left(self):
        old_id = self.device()["key_id"]
        self.assertIn((self.url, old_id), self.credentials.items)
        self.age_key(31)
        self.client.sync()
        new_id = self.device()["key_id"]
        self.assertEqual(list(self.credentials.items), [(self.url, new_id)])
        self.assertEqual(self.device()["key_storage"], "keychain")
        self.assertFalse((self.paths.data / "device.key").exists())
        self.assertFalse((self.paths.data / "device.key.next").exists())
        self.client.remove_everything()
        self.assertEqual(self.credentials.items, {})

    def test_when_the_keychain_cannot_take_the_new_item_it_is_held_in_a_protected_file_until_promoted(self):
        failing = self.credentials
        real_put = failing.put

        def put(server, key_id, secret):
            if secret.startswith("sgw_new"):
                raise keystore.KeyStoreError("full")
            real_put(server, key_id, secret)

        failing.put = put
        self.age_key(31)
        seen = []
        self.hub.first_use = lambda secret: seen.append((self.paths.data / "device.key.next").read_text().strip() == secret)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertEqual(seen, [True])  # it was in the file before first use
        self.assertTrue(self.current_key().startswith("sgw_new"))
        self.assertFalse((self.paths.data / "device.key.next").exists())
        self.assertEqual(self.device()["key_storage"], "file")  # honest: the key is now in a file
        self.assertEqual(oct((self.paths.data / "device.key").stat().st_mode & 0o777), "0o600")
        self.assertEqual(self.credentials.items, {})  # the old keychain item was removed

    def test_an_old_item_that_cannot_be_deleted_is_remembered_and_removed_at_sign_out(self):
        real_delete = self.credentials.delete
        self.credentials.delete = mock.Mock(side_effect=keystore.KeyStoreError("busy"))
        self.age_key(31)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertEqual(self.device()["stale_key_ids"], [self.old_id])
        self.credentials.delete = real_delete
        self.client.remove_everything()
        self.assertEqual(self.credentials.items, {})

    def stage_with_unreadable_item(self, delete_works):
        """The keychain stores the new item but will not give it back."""
        creds = self.credentials
        real_get, real_delete = creds.get, creds.delete
        creds.get = lambda server, key_id: None if key_id == "key-9" else real_get(server, key_id)
        if not delete_works:
            creds.delete = mock.Mock(side_effect=keystore.KeyStoreError("busy"))
        self.client.store.stage("key-9", "sgw_staged_" + "b" * 40)
        return creds, real_get, real_delete

    def test_a_new_item_the_keychain_stored_but_could_not_read_back_is_removed(self):
        creds, _, _ = self.stage_with_unreadable_item(delete_works=True)
        self.assertNotIn((self.url, "key-9"), creds.items)
        self.assertEqual(self.device()["next_key_storage"], "file")  # fell back to the protected file
        self.assertNotIn("stale_key_ids", self.device())

    def test_a_new_item_that_cannot_be_removed_is_remembered_so_sign_out_deletes_it(self):
        creds, real_get, real_delete = self.stage_with_unreadable_item(delete_works=False)
        self.assertIn((self.url, "key-9"), creds.items)
        self.assertEqual(self.device()["stale_key_ids"], ["key-9"])
        self.assertEqual(self.device()["next_key_storage"], "file")
        creds.get, creds.delete = real_get, real_delete
        self.client.remove_everything()
        self.assertEqual(creds.items, {})
        self.assertFalse((self.paths.data / "device.key.next").exists())

    def test_the_heartbeat_reports_the_backend_with_the_storage_mode(self):
        self.client.heartbeat()
        body = self.hub.heartbeats[-1]
        self.assertEqual((body["key_storage"], body["key_backend"]), ("keychain", keystore.backend_name()))
        for name in ("credential-manager", "keychain", "secret-service"):
            with mock.patch.object(keystore, "backend_name", return_value=name):
                self.client.heartbeat()
            self.assertEqual(self.hub.heartbeats[-1]["key_backend"], name)


class FileStorage(RotationBase):
    credentials_class = NoKeychain

    def test_rotation_with_no_keychain_replaces_the_key_file_and_leaves_no_second_copy(self):
        self.assertEqual(self.device()["key_storage"], "file")
        self.client.heartbeat()
        self.assertEqual(self.hub.heartbeats[-1]["key_storage"], "file")
        self.assertNotIn("key_backend", self.hub.heartbeats[-1])  # a file has no native backend to name
        self.age_key(31)
        seen = []
        self.hub.first_use = lambda secret: seen.append((self.paths.data / "device.key.next").read_text().strip() == secret)
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.assertEqual(seen, [True])
        self.assertTrue((self.paths.data / "device.key").read_text().strip().startswith("sgw_new"))
        self.assertFalse((self.paths.data / "device.key.next").exists())
        self.assertEqual(oct((self.paths.data / "device.key").stat().st_mode & 0o777), "0o600")
        self.assertEqual(self.states()[self.old_id], "rotated")
        self.client.remove_everything()
        self.assertEqual(list(self.paths.data.glob("device.key*")), [])

    def test_a_staged_file_is_erased_at_sign_out(self):
        self.age_key(31)
        self.hub.refuse_new_key = True
        self.client.sync()
        self.assertTrue((self.paths.data / "device.key.next").exists())
        self.client.remove_everything()
        self.assertFalse((self.paths.data / "device.key.next").exists())


if __name__ == "__main__":
    unittest.main()


class RealGatewayRotation(ClientBase):
    """The same client against the real gateway (not the stand-in Hub above): rotation, the refused old key, and revocation."""

    owner = "company"

    def age(self, days=31):
        info = self.client.store.device()
        info["key_issued"] = time.time() - days * DAY
        self.client.store._save_info(info)

    def key_row(self, key_id):
        return self.gw.db.one("SELECT revoked, revoked_by, confirmed, retire_at FROM keys WHERE id = ?", (key_id,))

    def keep_something_installed(self):
        state = self.client.store.state()
        state["installed"]["brand-prompts"] = {"version": "1", "kind": "tool", "name": "Brand prompts"}
        self.client.store.save_state(state)

    def test_an_aged_key_is_rotated_and_the_old_one_is_then_refused_as_renewed_not_as_disconnected(self):
        info = self.sign_in()
        old_id, old_key = info["key_id"], self.client.store.key()
        self.client.sync()
        self.age()
        out = self.client.sync()
        self.assertEqual(out["rotation"], "rotated")
        new_key = self.client.store.key()
        self.assertNotEqual(new_key, old_key)
        new_id = self.client.store.device()["key_id"]
        self.assertNotEqual(new_id, old_id)
        self.assertEqual(self.key_row(old_id)["revoked_by"], "system: rotated")
        self.assertIsNotNone(self.key_row(new_id)["confirmed"])
        # the old key on the real wire: renewed (load the newer key), never "disconnected" (wipe)
        status, body, _ = self.api("GET", "/device/manifest", key=old_key)
        self.assertEqual((status, body.get("code")), (401, "device_key_rotated"), body)
        self.assertEqual(self.api("GET", "/device/manifest", key=new_key)[0], 200)
        self.assertTrue(self.client.signed_in())

    def test_a_call_made_with_the_old_key_picks_up_the_new_one_and_removes_nothing(self):
        self.sign_in()
        old_key = self.client.store.key()
        self.age()
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        self.keep_something_installed()
        new_key = self.client.store.key()
        real, calls = self.client.api, []

        def stale_once():
            api = real()
            if not calls:
                calls.append(1)
                api.key = old_key  # a call that read the key just before the rotation finished
            return api

        self.client.api = stale_once
        self.assertIn("packages", self.client.refresh())
        self.assertEqual(calls, [1])
        self.assertEqual(self.client.store.key(), new_key)
        self.assertTrue(self.client.signed_in())
        self.assertIn("brand-prompts", self.client.store.state()["installed"])

    def test_with_the_new_key_lost_a_refused_old_key_says_reconnect_and_removes_nothing(self):
        info = self.sign_in()
        old_key = self.client.store.key()
        self.keep_something_installed()
        # the server rotates, but the response never reaches the app; then the 10 minutes of grace run out
        status, issued, _ = self.api("POST", "/device/rotate", {}, key=old_key)
        self.assertEqual(status, 200, issued)
        self.gw.db.x("UPDATE keys SET retire_at = ? WHERE id = ?", (time.time() - 1, info["key_id"]))
        with self.assertRaises(core.NeedsReconnect):
            self.client.refresh()
        self.assertTrue(self.client.signed_in())
        self.assertEqual(self.client.store.key(), old_key)
        self.assertIn("brand-prompts", self.client.store.state()["installed"])
        self.assertTrue(self.client.status()["reconnect"])

    def test_a_real_revoke_after_a_rotation_removes_the_app_from_the_device(self):
        (self.home / ".codex").mkdir()
        original = 'model = "o3"\n'
        (self.home / ".codex" / "config.toml").write_text(original)
        self.sign_in()
        self.client.sync()
        self.age()
        self.assertEqual(self.client.sync()["rotation"], "rotated")
        current_id = self.client.store.device()["key_id"]
        self.assertEqual(self.rig.api("POST", f"/keys/{current_id}/revoke")[0], 200)
        with self.assertRaises(core.Revoked):
            self.client.sync()
        self.assertFalse(self.client.signed_in())
        self.assertFalse((self.data / "device.key").exists())
        self.assertFalse((self.data / "packages").exists())
        self.assertEqual((self.home / ".codex" / "config.toml").read_text(), original)

