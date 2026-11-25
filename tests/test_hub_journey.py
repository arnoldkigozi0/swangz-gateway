"""packaging/hub_journey.py: the workspace (deliverable 5) and F-18 steps the macOS and Windows packaged-app journeys
run on CI. The packaged app and Chrome only exist on the runners; here the F-18 round trip runs against a real Hub
(tests/support.Rig) with the person's key standing in for the app's, and the workspace step against stand-ins."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
import zlib
from pathlib import Path

from .support import Rig

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("t_hub_journey", ROOT / "packaging" / "hub_journey.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Steps:
    def __init__(self):
        self.seen = []

    def __call__(self, name, ok, detail=""):
        self.seen.append((name, ok, str(detail)))
        if not ok:
            raise AssertionError(f"{name}: {detail}")


class F18Tests(unittest.TestCase):
    def setUp(self):
        self.h = load()
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.base = f"http://127.0.0.1:{self.rig.port}"
        self.h.device_key = lambda *a, **k: (0, self.rig.key)

    def test_round_trip_passes_and_the_key_never_reaches_the_evidence(self):
        steps = Steps()
        self.h.f18(steps, "unused", {}, self.base, self.h.Console(self.base, "owner"), self.rig.person_id, self.rig.tmp)
        names = [n for n, _, _ in steps.seen]
        for want in ("F-18: prompt and reply storage is off by default", "F-18 off: the request is recorded, with no prompt and an empty reply",
                     "F-18 off: the prompt is nowhere in the Hub's database, WAL, stored bodies (orphans too) or logs",
                     "F-18 on: the same scan finds the stored prompt (the scan can see what it looks for)",
                     "F-18 on: a role with the trust area reads the prompt", "F-18: storage is off again"):
            self.assertIn(want, names)
        self.assertTrue(any(n.startswith("F-18 on: a role without it (viewer)") for n in names))
        self.assertNotIn(self.rig.key, json.dumps(steps.seen))
        db = self.rig.gw.db
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM requests WHERE prompt LIKE '%swangz-f18-off-%'"), 0)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM requests WHERE prompt LIKE '%swangz-f18-on-%'"), 1)
        self.assertEqual(db.get_setting("store_bodies"), "0")

    def test_a_hub_that_stores_by_default_fails_the_first_step(self):
        self.rig.gw.db.set_setting("store_bodies", "1")
        with self.assertRaisesRegex(AssertionError, "off by default"):
            self.h.f18(Steps(), "unused", {}, self.base, self.h.Console(self.base, "owner"), self.rig.person_id, self.rig.tmp)

    def test_storage_is_turned_off_again_even_when_a_step_fails(self):
        h, steps = self.h, Steps()
        real, calls = h.record, []

        def record(console, person_id, after, timeout=20):
            calls.append(after)
            return real(console, person_id, after) if len(calls) == 1 else (None, None)  # the second finds nothing
        h.record = record
        with self.assertRaises(AssertionError):
            h.f18(steps, "unused", {}, self.base, h.Console(self.base, "owner"), self.rig.person_id, self.rig.tmp)
        self.assertEqual(self.rig.gw.db.get_setting("store_bodies"), "0")
        self.assertEqual([n for n, ok, _ in steps.seen if not ok], ["F-18 on: a role with the trust area reads the prompt"])
        self.assertEqual(steps.seen[-1][:2], ("F-18: storage is off again", True))


    def test_a_prompt_left_in_a_hub_log_fails_before_storage_is_touched(self):
        h, log = self.h, Path(self.rig.tmp).parent / (Path(self.rig.tmp).name + "-hub.log")
        self.addCleanup(lambda: log.unlink(missing_ok=True))
        real = h.send

        def send(base, key, text):
            with open(log, "a", encoding="utf-8") as f:
                f.write("debug: " + text + "\n")  # a Hub that logs prompts
            return real(base, key, text)
        h.send, steps = send, Steps()
        with self.assertRaisesRegex(AssertionError, "nowhere in the Hub"):
            h.f18(steps, "unused", {}, self.base, h.Console(self.base, "owner"), self.rig.person_id, self.rig.tmp, [log])
        self.assertFalse(steps.seen[-1][1])
        self.assertIn("log " + log.name, steps.seen[-1][2])
        self.assertEqual(self.rig.gw.db.get_setting("store_bodies"), "0")

    def test_a_record_detail_that_is_refused_fails_the_step(self):
        h = self.h
        h.record = lambda *a, **k: (500, {"error": "boom"})
        with self.assertRaisesRegex(AssertionError, "lookup answers"):
            h.f18(Steps(), "unused", {}, self.base, h.Console(self.base, "owner"), self.rig.person_id, self.rig.tmp)

    def test_newest_and_record_raise_when_the_hub_refuses(self):
        class Refused:
            def call(self, *a, **k):
                return 403, {"error": "no"}
        with self.assertRaisesRegex(RuntimeError, "403"):
            self.h.newest(Refused(), 1)
        with self.assertRaisesRegex(RuntimeError, "403"):
            self.h.record(Refused(), 1, 0)
        owner = self.h.Console(self.base, "owner")
        self.assertEqual(self.h.record(owner, self.rig.person_id, 10 ** 9, timeout=0), (None, None))

    def test_the_scan_finds_the_text_in_an_orphan_blob_a_raw_file_and_a_log(self):
        h, db, marker = self.h, self.rig.gw.db, "swangz-f18-off-0123456789abcdef"
        self.assertEqual(h.traces(self.rig.tmp, (), marker), [])
        db.x("INSERT INTO blobs(hash, data, size) VALUES(?, ?, ?)", ("f" * 64, zlib.compress(marker.encode()), len(marker)))
        found = h.traces(self.rig.tmp, (), marker)
        self.assertIn("blob " + "f" * 12, found)  # compressed and pointed at by no request
        (Path(self.rig.tmp) / "stray.txt").write_text(marker)
        log = Path(self.rig.tmp) / "logs" / "hub.log"
        log.parent.mkdir()
        log.write_text("x " + marker)
        found = h.traces(self.rig.tmp, [log], marker)
        self.assertIn("stray.txt", found)
        self.assertIn("log hub.log", found)

    def test_an_unreadable_file_fails_the_scan(self):
        h = self.h
        (Path(self.rig.tmp) / "locked.bin").write_bytes(b"x")
        h.read_bytes = lambda path, tries=20: None if Path(path).name == "locked.bin" else Path(path).read_bytes()
        self.assertIn("unreadable locked.bin", h.traces(self.rig.tmp, (), "anything"))


class SecondPersonTests(unittest.TestCase):
    def setUp(self):
        self.h = load()
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.base = f"http://127.0.0.1:{self.rig.port}"

    def test_the_admin_adds_a_person_who_signs_in_and_approves_a_device_code(self):
        owner = self.h.Console(self.base, "owner")
        pid, staff = self.h.add_person(owner, self.base, "Okello Brian", "brian.okello@swangzavenue.com")
        self.assertNotEqual(pid, self.rig.person_id)
        self.assertTrue(self.h.grant(owner, pid))
        status, _, out = self.rig.request("POST", "/api/device/code", {"name": "CI", "os": "Windows 11", "arch": "x86_64",
                                                                      "app_version": "0.1.0"}, {"x-swangz-app": "1"})
        code = json.loads(out)["user_code"]
        self.assertEqual(staff.approve(code), 200)
        self.assertEqual(self.rig.gw.db.scalar("SELECT person_id FROM device_codes WHERE user_code = ?", (code,)), pid)


class FakeOwner:
    def __init__(self, opened=True):
        self.opened = opened

    def call(self, method, path, body=None):
        if path.startswith("/launches"):
            return 200, {"items": [{"tool_id": "canva", "outcome": "opened"}] if self.opened else []}
        if path == "/people":
            return 200, {"id": 8}
        if path.endswith("/invite"):
            return 200, {"link": "http://hub/#/welcome/" + "t" * 32}
        return 200, {}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.h = load()
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data, True)
        self.closed = []
        self.h.close_chrome = self.closed.append
        (self.data / "manifest.json").write_text(json.dumps({"browser": {"contract": 2, "person_id": "7", "device_id": "dev1"}}))

    def app(self, chrome=True, person="7"):
        def run_app(*args):
            folder = self.data / "browser-profiles" / ("a" * 32)
            folder.mkdir(parents=True)
            (folder / ".swangz-profile.json").write_text(json.dumps({"person_id": person, "device_id": "dev1", "state": "prepared"}))
            if chrome:
                (folder / "Local State").write_text("{}")
            return 0, "Opened in the Swangz workspace window."
        return run_app

    def test_the_window_on_the_persons_folder_passes_and_chrome_is_closed(self):
        steps = Steps()
        folder = self.h.workspace(steps, self.app(), self.data, FakeOwner(), 7)
        self.assertEqual(len(steps.seen), 6)
        self.assertEqual(self.closed, [folder])

    def test_no_chrome_on_the_folder_fails_and_still_closes(self):
        self.h.chrome_wrote = lambda folder, timeout=45: False
        with self.assertRaisesRegex(AssertionError, "Google Chrome started"):
            self.h.workspace(Steps(), self.app(chrome=False), self.data, FakeOwner(), 7)
        self.assertEqual(len(self.closed), 1)

    def test_another_persons_folder_or_no_launch_record_fails(self):
        with self.assertRaisesRegex(AssertionError, "belongs to this person"):
            self.h.workspace(Steps(), self.app(person="8"), self.data, FakeOwner(), 7)
        shutil.rmtree(self.data / "browser-profiles")
        with self.assertRaisesRegex(AssertionError, "records the open"):
            self.h.workspace(Steps(), self.app(), self.data, FakeOwner(opened=False), 7)

    def second(self, person="8", same_folder=False):
        def run_app(*args):
            folder = self.data / "browser-profiles" / (("a" if same_folder else "b") * 32)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / ".swangz-profile.json").write_text(json.dumps({"person_id": person, "device_id": "dev1", "state": "prepared"}))
            (folder / "Local State").write_text("{}")
            return 0, "Opened in the Swangz workspace window."
        return run_app

    def first(self):
        folder = self.h.workspace(Steps(), self.app(), self.data, FakeOwner(), 7)
        return folder, self.h.marker_of(folder)

    def second_person(self, steps, run_app, first, marker):
        self.h.add_person = lambda owner, base, name, email: (8, type("S", (), {"approve": lambda self, code: 200})())
        return self.h.second_person(steps, lambda approve: "dev1", run_app, self.data, FakeOwner(), "http://hub", first, marker)

    def test_kept_passes_for_an_unchanged_folder_and_fails_for_a_changed_or_missing_one(self):
        folder, marker = self.first()
        self.h.kept(Steps(), self.data, folder, marker, "after the upgrade")
        (folder / ".swangz-profile.json").write_text(json.dumps({**marker, "person_id": "9"}))
        with self.assertRaisesRegex(AssertionError, "kept unchanged"):
            self.h.kept(Steps(), self.data, folder, marker, "after the upgrade")
        shutil.rmtree(folder)
        with self.assertRaisesRegex(AssertionError, "kept unchanged"):
            self.h.kept(Steps(), self.data, folder, marker, "after sign out")

    def test_removed_passes_with_only_the_lock_left_and_fails_while_a_folder_stays(self):
        folder, _ = self.first()
        with self.assertRaisesRegex(AssertionError, "every workspace folder is deleted"):
            self.h.removed(Steps(), self.data, "after the uninstall")
        shutil.rmtree(folder)
        (self.data / "browser-profiles" / ".lock").touch()
        self.h.removed(Steps(), self.data, "after the uninstall")
        shutil.rmtree(self.data / "browser-profiles")
        self.h.removed(Steps(), self.data, "after the uninstall")

    def test_a_second_person_gets_a_separate_folder_and_the_first_is_kept(self):
        folder, marker = self.first()
        steps = Steps()
        pid, theirs = self.second_person(steps, self.second(), folder, marker)
        self.assertEqual(pid, 8)
        self.assertNotEqual(theirs, folder)
        self.assertEqual(self.closed[-1], theirs)
        self.assertTrue(steps.seen[-1][0].startswith("workspace: with a second person on this device"))

    def test_a_second_person_reusing_the_first_folder_or_marked_as_the_first_fails(self):
        folder, marker = self.first()
        with self.assertRaisesRegex(AssertionError, "separate workspace folder"):
            self.second_person(Steps(), self.second(same_folder=True), folder, marker)
        folder, marker = folder, self.h.marker_of(folder)
        shutil.rmtree(self.data / "browser-profiles")
        folder, marker = self.first()
        with self.assertRaisesRegex(AssertionError, "marked for them"):
            self.second_person(Steps(), self.second(person="7"), folder, marker)

    def test_close_only_targets_this_folder(self):
        src = (ROOT / "packaging" / "hub_journey.py").read_text(encoding="utf-8")
        self.assertIn('"--user-data-dir=" + needle', src)
        self.assertIn("$_.CommandLine.Contains($env:SWANGZ_WS_FOLDER)", src)
        self.assertNotIn("killall", src)
        self.assertNotIn("taskkill /IM", src)


class FilesHoldingTests(unittest.TestCase):
    def test_finds_the_secret_skips_the_store_and_reports_unreadable_files(self):
        from unittest import mock
        h = load()
        root = Path(tempfile.mkdtemp(prefix="sgw-hold-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "logs").mkdir()
        (root / "logs" / "app.log").write_bytes(b"line sgw_example_secret line")
        (root / "device.key").write_text("sgw_example_secret")
        (root / "clean.txt").write_text("nothing here")
        self.assertEqual(h.files_holding("sgw_example_secret", [root, root / "missing"], skip={"device.key"}),
                         [str(root / "logs" / "app.log")])
        with mock.patch.object(h, "read_bytes", return_value=None):
            hits = h.files_holding("sgw_example_secret", [root], skip={"device.key"})
        self.assertTrue(hits and all(x.startswith("unreadable: ") for x in hits))


class GrantsAfterRestartTests(unittest.TestCase):
    """The offer on the device changes only when the program starts (and syncs); a closed program keeps the old one."""

    def run_helper(self, sync_on_start=True):
        import json
        from unittest import mock
        h = load()
        data = Path(tempfile.mkdtemp(prefix="sgw-grants-"))
        self.addCleanup(shutil.rmtree, data, True)
        hub = {"canva"}

        def save():
            (data / "manifest.json").write_text(json.dumps({"apps": [{"id": t} for t in sorted(hub)]}), encoding="utf-8")

        class Owner:
            def call(self, method, path, body=None):
                tool = path.rsplit("/", 1)[1]
                if method == "POST":
                    hub.add(tool)
                elif method == "DELETE":
                    hub.discard(tool)
                return 200, {}

        save()
        results, starts = [], []
        check = lambda name, ok, detail="": results.append((name, ok))
        start = lambda: starts.append(1) or (save() if sync_on_start else None)
        with mock.patch.object(h, "time", mock.Mock(monotonic=mock.Mock(side_effect=range(0, 10**6, 30)), sleep=lambda s: None)):
            h.grants_after_restart(check, start, lambda proc: None, data, Owner(), 7, timeout=60)
        return results, starts

    def test_a_grant_and_its_removal_show_only_after_the_program_starts(self):
        results, starts = self.run_helper()
        self.assertEqual(len(starts), 2)
        self.assertEqual([ok for _, ok in results], [True, True])

    def test_a_program_that_does_not_sync_on_start_fails_both_steps(self):
        results, _ = self.run_helper(sync_on_start=False)
        self.assertEqual([ok for _, ok in results], [False, False])


class WiringTests(unittest.TestCase):
    def test_both_journeys_run_the_steps_after_reconnect_and_before_the_upgrade(self):
        mac = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        win = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        for text, before, after in ((mac, "Hub back: the server records", "install(j, args.new, apps"),
                                    (win, "network interruption: sync exited 1", "# 6. upgrade")):
            self.assertLess(text.index(before), text.index("hub_journey.workspace("))
            self.assertLess(text.index("hub_journey.workspace("), text.index("hub_journey.f18("))
            self.assertLess(text.index("hub_journey.f18("), text.index(after))
            self.assertLess(text.index(after), text.index('"after the upgrade")'))
            self.assertLess(text.index('"after the upgrade")'), text.index('"after sign out")'))
            self.assertLess(text.index('"after sign out")'), text.index("hub_journey.second_person("))

    def test_both_journeys_run_two_people_at_once_with_separate_data_folders(self):
        mac = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        win = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        for text in (mac, win):
            self.assertIn('"SWANGZ_HOME": str(data_b)', text)
            self.assertLess(text.index("hub_journey.second_person("), text.index("hub_journey.two_at_once("))
        self.assertLess(win.index("hub_journey.two_at_once("), win.rindex('app("autostart", "on")'))

    def test_both_journeys_scan_the_fixture_hubs_data_and_log(self):
        mac = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        win = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        self.assertIn('fixture["data"], [hub_log])', mac)
        self.assertIn("stderr=err", mac)
        self.assertIn("rig.tmp, [hub_log]", win)
        self.assertIn("Tee(sys.stderr, hub_log)", win)

    def test_the_folder_name_and_marker_agree_with_the_app(self):
        from swangz_client import browser_profiles
        h = load()
        self.assertEqual((h.FOLDER.pattern, h.MARKER), (browser_profiles.FOLDER.pattern, browser_profiles.MARKER))

    def test_the_fixture_reports_its_person(self):
        demo = (ROOT / "tests" / "browser" / "demo.py").read_text(encoding="utf-8")
        self.assertIn('"person": rig.person_id', demo)
        self.assertIn('"data": rig.tmp', demo)
