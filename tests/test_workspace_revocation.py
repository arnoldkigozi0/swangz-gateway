"""W4 client: close, refuse and purge (docs/W4-THREAT-NOTE.md, tests 1-12 and 15).

Temporary folders and stubs only: no real browser starts, no provider is contacted. Test 13 (the server refuses
suspended/retired at /device/open) lives with the endpoint in PR #179 (tests/test_device_open.py); test 14 is W6.
"""
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import browser_profiles as bp
from swangz_client import core
from swangz_client import workspace_launcher as wl
from swangz_client import workspace_state as ws

POSIX = os.name != "nt"
HOSTS = ["chatgpt.com"]
URL = "https://chatgpt.com/"
SERVER = "https://hub.example"


class FakeProc:
    def __init__(self, log, alive=True):
        self.pid, self.alive, self.log = 4242, alive, log

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.log.append("close")
        self.alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.log.append("kill")
        self.alive = False


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        self.data.mkdir(mode=0o700)
        self.log = []
        self.owner = bp.Owner(SERVER, "7", "dev-1")
        self.clock = Clock()
        self.answers = []  # what the next heartbeats return (dict) or raise (exception)
        self.manifest_state = "active"

        def popen(argv, **kw):
            self.log.append("start")
            return FakeProc(self.log)
        self.launcher = wl.Launcher(self.data, popen=popen, finder=lambda: "/opt/google/chrome/chrome", acl=lambda p: True)
        c = core.Client(core.Paths(self.tmp / "home", self.data), sleep=lambda s: None, open_url=mock.Mock())
        c.workspace = ws.WorkspaceState(c, monotonic=self.clock)
        self.manifest = {"apps": [{"id": "chatgpt", "name": "ChatGPT", "open": SERVER + "/go/chatgpt", "hosts": HOSTS, "workspace": True}],
                         "browser": {"contract": 2, "person_id": "7", "device_id": "dev-1",
                                     "workspace": {"state": "active", "generation": 1}}}
        c.store.manifest = lambda: self.manifest
        c.store.device = lambda: {"server": SERVER}
        c.store.state = lambda: {"installed": {}}
        c.store.key = lambda: "k"
        c._reconnect_pending = lambda: False
        api = mock.Mock()

        def call(method, path, body=None, auth=True):
            if path == "/device/heartbeat":
                answer = self.answers.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return answer
            if path == "/device/open":
                return {"ok": True, "url": URL, "workspace": dict(self.manifest["browser"]["workspace"])}
            raise AssertionError(path)
        api.call.side_effect = call
        c.api = lambda: api
        c.launcher = self.launcher
        self.client, self.api = c, api

    # helpers
    def beat(self, state="active", generation=1, **extra):
        self.answers.append({"ok": True, "workspace": {"state": state, "generation": generation}, **extra})
        return self.client.heartbeat()

    def miss(self, exc):
        self.answers.append(exc)
        return self.client.heartbeat()

    def folders(self):
        return sorted(p.name for p in (self.data / "browser-profiles").iterdir() if bp.FOLDER.fullmatch(p.name)) \
            if (self.data / "browser-profiles").exists() else []

    def running(self):
        """The app starts a window; it is the one W4 may close."""
        self.client.open_app("chatgpt")
        self.assertTrue(self.launcher.running())
        self.log.clear()

    def refused(self, code):
        with self.assertRaises(wl.LaunchError) as cm:
            self.client.open_app("chatgpt")
        self.assertEqual(cm.exception.code, code)
        self.client.open_url.assert_not_called()

    def marker(self, name):
        return json.loads((self.data / "browser-profiles" / name / bp.MARKER).read_text())


class SuspendTests(Base):
    def test_1_suspended_closes_once_refuses_and_keeps_the_folder(self):
        self.running()
        before = self.folders()
        self.beat("suspended")
        self.beat("suspended")
        self.assertEqual(self.log, ["close"])  # one window, closed once; a second answer signals nothing
        self.assertEqual(self.folders(), before)
        self.refused("not_active")  # the stored manifest still says active: the Hub's latest answer wins

    def test_2_active_again_with_the_same_generation_reuses_the_folder(self):
        self.running()
        before = self.folders()
        self.beat("suspended")
        self.beat("active", 1)
        self.assertEqual(self.client.open_app("chatgpt"), "workspace")
        self.assertEqual(self.folders(), before)

    def test_suspended_from_the_manifest_and_from_open_use_the_same_reducer(self):
        self.running()
        with mock.patch.object(self.client.workspace, "apply", wraps=self.client.workspace.apply) as apply:
            self.manifest["browser"]["workspace"]["state"] = "suspended"
            self.api.call.side_effect = lambda m, p, b=None, auth=True: self.manifest
            self.client.refresh()
        apply.assert_called_once()
        self.assertEqual(self.log, ["close"])
        self.assertEqual(self.client.workspace.latch()["refused"], "not_active")


@unittest.skipUnless(POSIX, "purging a folder is POSIX-only for now (Windows: test 15)")
class PurgeTests(Base):
    def test_3_retired_latches_then_closes_then_retires(self):
        self.running()
        order = []
        state = self.client.workspace
        save, retire = state._save, bp.Profiles.retire

        def saving(data):
            if data.get("purge_pending"):
                order.append("latch")
            return save(data)

        def retiring(profiles, pid, owner):
            order.append("retire")
            return retire(profiles, pid, owner)
        self.log = order
        self.launcher.process.log = order
        with mock.patch.object(state, "_save", saving), mock.patch.object(bp.Profiles, "retire", retiring):
            self.beat("retired")
        self.assertEqual(order[:3], ["latch", "close", "retire"])
        self.assertEqual(self.folders(), [])
        self.refused("retired")
        self.assertIsNone(state.latch().get("purge_pending"))
        self.assertEqual(state.latch()["notice"], ws.NOTICE_PURGED)

    def test_4_higher_generation_purges_equal_keeps_lower_refuses(self):
        self.running()
        first = self.folders()
        self.beat("active", 1)
        self.assertEqual(self.folders(), first)  # equal: nothing happens
        self.beat("active", 2)
        self.assertEqual(self.folders(), [])
        self.assertIn("close", self.log)
        self.manifest["browser"]["workspace"]["generation"] = 2
        self.client.open_app("chatgpt")
        (new,) = self.folders()
        self.assertNotEqual([new], first)
        self.assertEqual((self.marker(new)["version"], self.marker(new)["generation"]), (2, 2))
        self.log.clear()
        self.beat("active", 1)  # lower than the marker: no close, no purge, refused
        self.assertEqual(self.log, [])
        self.assertEqual(self.folders(), [new])
        self.refused("generation_rollback")
        self.beat("active", 2)
        self.client.open_app("chatgpt")

    def test_a_retired_answer_older_than_the_folder_deletes_nothing(self):
        self.manifest["browser"]["workspace"]["generation"] = 2
        self.beat("active", 2)
        self.running()
        before = self.folders()
        self.assertEqual(self.marker(before[0])["generation"], 2)
        self.beat("retired", 1)  # a Hub restored from an older backup
        self.assertEqual(self.log, [], "no close")
        self.assertEqual(self.folders(), before)
        self.assertIsNone(self.client.workspace.latch().get("purge_pending"))
        self.refused("generation_rollback")

    def test_9_another_owners_folder_survives_a_retired(self):
        other = bp.Profiles(self.data).prepare(bp.Owner(SERVER, "8", "dev-1"))
        other_device = bp.Profiles(self.data).prepare(bp.Owner(SERVER, "7", "dev-2"))
        self.running()
        self.beat("retired")
        self.assertEqual(self.folders(), sorted([other.name, other_device.name]))

    def test_10_a_purge_failure_stays_pending_refuses_and_retries(self):
        self.running()
        with mock.patch.object(bp.Profiles, "retire", side_effect=OSError("busy")):
            self.beat("active", 2)
            self.assertEqual(len(self.folders()), 1)
            latch = self.client.workspace.latch()
            self.assertEqual((latch["refused"], len(latch["purge_pending"])), ("purge_pending", 1))
            self.assertEqual(latch["notice"], ws.NOTICE_PURGE_FAILED)
            self.manifest["browser"]["workspace"]["generation"] = 2
            self.refused("purge_pending")
        self.beat("active", 2)  # the next check-in retries, and this time it works
        self.assertEqual(self.folders(), [])
        self.assertIsNone(self.client.workspace.latch().get("refused"))
        self.client.open_app("chatgpt")

    def test_a_pending_purge_that_completes_keeps_a_later_rollback_refusal(self):
        self.manifest["browser"]["workspace"]["generation"] = 2
        self.beat("active", 2)
        self.running()
        with mock.patch.object(bp.Profiles, "retire", side_effect=OSError("busy")):
            self.beat("active", 3)  # the purge of the generation-2 folder fails and stays pending
            self.assertTrue(self.client.workspace.latch()["purge_pending"])
            self.beat("active", 1)  # then an answer older than that folder: a Hub restored from backup
            self.assertEqual(self.client.workspace.latch()["refused"], "generation_rollback")
        self.assertTrue(self.client.workspace.resume())  # the retry now succeeds
        self.assertEqual(self.folders(), [])
        self.assertEqual(self.client.workspace.latch()["refused"], "generation_rollback")
        self.refused("generation_rollback")
        self.beat("active", 3)  # only a current answer clears it
        self.assertIsNone(self.client.workspace.latch().get("refused"))

    def test_prepare_refuses_while_an_older_generation_folder_exists(self):
        bp.Profiles(self.data).prepare(self.owner, 1)
        with self.assertRaises(bp.ProfileError) as cm:
            bp.Profiles(self.data).prepare(self.owner, 2)
        self.assertEqual(cm.exception.code, "purge_pending")
        with self.assertRaises(bp.ProfileError) as cm:
            bp.Profiles(self.data).prepare(self.owner, True)
        self.assertEqual(cm.exception.code, "generation_invalid")


class RevokeTests(Base):
    def test_5_revoked_closes_before_the_wipe_and_keeps_the_folder(self):
        self.running()
        before = self.folders()
        order = self.log
        real = self.client.remove_everything

        def wipe():
            order.append("wipe")
            return real()
        with mock.patch.object(self.client, "remove_everything", wipe):
            with self.assertRaises(core.Revoked):
                self.miss(core.Revoked(401, "device_revoked", "gone"))
        self.assertEqual(order, ["close", "wipe"])
        self.assertEqual(self.folders(), before)

    def test_6_other_401_and_403_close_and_refuse_key_rotation_does_not(self):
        for exc in (core.ApiFailure(401, "device_unknown", "?"), core.ApiFailure(403, "forbidden", "no")):
            self.beat("active")
            self.running()
            before = self.folders()
            self.miss(exc)
            self.assertEqual(self.log, ["close"], exc.code)
            self.assertEqual(self.folders(), before)
            self.refused("refused_by_hub")
        self.beat("active")
        self.running()
        self.client.workspace.failure(core.KeyRotated(401, "device_key_rotated", "rotated"))
        self.client.workspace.failure(core.NeedsReconnect("reconnect"))
        self.assertEqual(self.log, [])
        self.assertTrue(self.launcher.running())

    def test_a_pending_purge_does_not_follow_the_device_into_a_new_enrolment(self):
        self.running()
        with mock.patch.object(bp.Profiles, "retire", side_effect=OSError("busy")):
            self.beat("retired")
            old = self.folders()
            self.assertTrue(self.client.workspace.latch()["purge_pending"])
            self.client.remove_everything = lambda: None  # the store is stubbed; forget() is checked below
            with self.assertRaises(core.Revoked):
                self.miss(core.Revoked(401, "device_revoked", "gone"))
        self.client.workspace.forget()  # what remove_everything() does after Store.wipe()
        self.assertEqual(self.client.workspace.latch(), {})
        self.manifest["browser"]["device_id"] = "dev-2"  # enrolled again: a new device id
        self.client.open_app("chatgpt")
        self.assertTrue(self.launcher.running())
        self.assertEqual(len(self.folders()), 2)
        self.assertTrue(set(old) < set(self.folders()), "the old folder is not deleted for the new owner")

    def test_a_latch_left_by_another_enrolment_is_dropped_not_purged(self):
        self.running()
        with mock.patch.object(bp.Profiles, "retire", side_effect=OSError("busy")):
            self.beat("retired")
        old = self.folders()
        self.manifest["browser"]["device_id"] = "dev-2"  # the latch file survived (say, a crash before the wipe)
        self.client.open_app("chatgpt")
        latch = self.client.workspace.latch()
        self.assertEqual((latch.get("purge_pending"), latch.get("owner"), latch.get("refused")), (None, None, None))
        self.assertTrue(set(old) < set(self.folders()))

    def test_remove_everything_deletes_the_latch_and_keeps_the_folders(self):
        self.running()
        self.client.workspace.refuse("revoked")
        before = self.folders()
        with mock.patch.object(self.client.store, "wipe"):
            self.client.remove_everything()
        self.assertFalse((self.data / "workspace-state.json").exists())
        self.assertEqual(self.folders(), before)

    def test_revoked_during_rotation_closes_the_window_and_drops_the_latch(self):
        for path in ("/device/rotate", "/device/heartbeat"):  # _rotate, then _confirm_staged
            self.beat("active")
            self.running()
            self.client.workspace.refuse("revoked", close=False)  # a latch on disk to be removed
            api = mock.Mock()
            api.call.side_effect = lambda m, p, b=None, auth=True: (_ for _ in ()).throw(
                core.Revoked(401, "device_revoked", "gone")) if p == path else {"key_id": "k2", "key": "x"}
            self.client.api = lambda: api
            self.client._api_factory = lambda server, key: api
            with mock.patch.object(self.client.store, "wipe"), mock.patch.object(self.client.store, "stage"), \
                    self.assertRaises(core.Revoked):
                self.client._rotate()
            self.assertEqual(self.log, ["close"], path)
            self.assertFalse(self.launcher.running())
            self.assertFalse((self.data / "workspace-state.json").exists(), path)
            self.client.api = lambda: self.api

    def test_signing_out_closes_without_purging(self):
        self.running()
        before = self.folders()
        with mock.patch.object(self.client, "remove_everything"):
            self.api.call.side_effect = lambda *a, **k: {"ok": True}
            self.client.logout()
        self.assertEqual(self.log, ["close"])
        self.assertEqual(self.folders(), before)


class OfflineTests(Base):
    def test_7_one_failure_never_closes_two_spanning_the_grace_do(self):
        for exc in (core.ApiFailure(0, "offline", "x"), core.ApiFailure(503, "", "x"), None):
            self.beat("active")
            self.running()
            failure = exc or {"not": "the hub"}  # a 200 that isn't the Hub's JSON answer
            self.miss(failure)
            self.assertEqual(self.log, [])
            self.clock.now += 2 * core.HEARTBEAT_SECONDS - 1
            self.miss(failure)
            self.assertEqual(self.log, [], "two failures inside 30 minutes keep the window")
            self.clock.now += 1
            self.miss(failure)
            self.assertEqual(self.log, ["close"])
            self.assertIsNone(self.client.workspace.latch().get("refused"), "the offline close is never latched")
            self.beat("active")  # any authenticated answer resets the count
            self.log.clear()

    def test_the_offline_close_does_not_outlive_the_connection_or_a_restart(self):
        self.beat("active")
        self.running()
        self.clock.now += 3 * core.HEARTBEAT_SECONDS
        self.miss(core.ApiFailure(0, "offline", "x"))
        self.miss(core.ApiFailure(0, "offline", "x"))
        self.assertEqual(self.log, ["close"])
        self.client.workspace = ws.WorkspaceState(self.client, monotonic=self.clock)  # the app restarts
        self.client.open_app("chatgpt")  # Open asks the Hub; it answers, so the window opens again
        self.assertTrue(self.launcher.running())

    def test_an_authenticated_answer_resets_the_count(self):
        self.running()
        self.miss(core.ApiFailure(0, "offline", "x"))
        self.beat("active")
        self.clock.now += 3 * core.HEARTBEAT_SECONDS
        self.miss(core.ApiFailure(0, "offline", "x"))
        self.assertEqual(self.log, [])

    def test_an_answer_without_contract_2_changes_nothing(self):
        self.running()
        self.answers.append({"ok": True})
        self.client.heartbeat()
        self.client.workspace.apply({"contract": 1, "workspace": {"state": "retired", "generation": 9}})
        self.client.workspace.apply({"contract": True, "workspace": {"state": "retired", "generation": 9}})
        self.assertEqual(self.log, [])
        self.assertEqual(len(self.folders()), 1)

    def test_heartbeat_asks_for_contract_2(self):
        self.beat("active")
        body = self.api.call.call_args[0][2]
        self.assertEqual(body["browser_contract"], 2)
        self.assertLess(len(json.dumps(body)), 2048)


class MalformedTests(Base):
    def test_8_malformed_answers_close_and_refuse_without_purging(self):
        for workspace in ({"state": "bogus", "generation": 1}, {"state": "retired", "generation": "2"},
                          {"state": "retired", "generation": True}, {"state": "retired", "generation": 0},
                          {"state": "retired"}, "retired", None):
            self.beat("active")
            self.running()
            before = self.folders()
            self.answers.append({"ok": True, "workspace": workspace})
            self.client.heartbeat()
            self.assertEqual(self.log, ["close"], workspace)
            self.assertEqual(self.folders(), before)
            self.refused("workspace_unknown")


class CloseTests(Base):
    def test_11_close_with_no_process_or_an_exited_one_signals_nothing(self):
        self.assertFalse(self.launcher.close())
        self.launcher.process = FakeProc(self.log, alive=False)
        self.assertFalse(self.launcher.close())
        self.assertEqual(self.log, [])
        self.assertIsNone(self.launcher.process)


class MarkerTests(Base):
    def write(self, marker):
        root = self.data / "browser-profiles"
        bp.Profiles(self.data).find(self.owner)  # makes the root safely
        folder = root / marker["profile_id"]
        folder.mkdir(mode=0o700)
        path = folder / bp.MARKER
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(marker, f)
        return folder

    def base(self, **extra):
        return {"version": 1, "profile_id": "a" * 32, **self.owner.fields, "state": "prepared", "created": time.time(), **extra}

    def test_12_marker_v1_reads_as_generation_1_and_v2_keys_are_exact(self):
        profiles = bp.Profiles(self.data)
        folder = self.write(self.base())
        self.assertEqual(profiles._marker(folder)["generation"], 1)
        self.assertEqual(profiles.find(self.owner), [("a" * 32, 1)])
        shutil.rmtree(folder)
        for bad in (self.base(version=2), self.base(version=2, generation=True), self.base(version=2, generation=0),
                    self.base(version=2, generation=2, extra=1), self.base(generation=2)):
            folder = self.write(bad)
            with self.assertRaises(bp.ProfileError, msg=bad):
                profiles._marker(folder)
            shutil.rmtree(folder)
        folder = self.write(self.base(version=2, generation=3))
        self.assertEqual(profiles._marker(folder)["generation"], 3)


class WindowsTests(Base):
    def unsupported(self):
        """On the Windows CI runner this is the real `retire`; elsewhere it stands in for it."""
        if os.name == "nt":
            return mock.patch.object(bp, "_WINDOWS", True)
        return mock.patch.object(bp.Profiles, "retire", side_effect=bp.ProfileError("unsupported_platform"))

    def test_15_retired_on_windows_closes_refuses_and_reports_the_purge_not_done(self):
        self.running()
        before = self.folders()
        with self.unsupported():
            self.beat("retired")
            self.assertEqual(self.log, ["close"])
            self.assertEqual(self.folders(), before)
            latch = self.client.workspace.latch()
            self.assertEqual((latch["purge_error"], latch["notice"]), ("unsupported_platform", ws.NOTICE_PURGE_FAILED))
            self.refused("purge_unsupported")
        self.assertIn("Windows", wl.MESSAGES["purge_unsupported"])


if __name__ == "__main__":
    unittest.main()
