"""packaging/hub_journey.py: the workspace (deliverable 5) and F-18 steps the macOS and Windows packaged-app journeys
run on CI. The packaged app and Chrome only exist on the runners; here the F-18 round trip runs against a real Hub
(tests/support.Rig) with the person's key standing in for the app's, and the workspace step against stand-ins."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
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
        self.h.f18(steps, "unused", {}, self.base, self.h.Console(self.base, "owner"), self.rig.person_id)
        names = [n for n, _, _ in steps.seen]
        for want in ("F-18: prompt and reply storage is off by default", "F-18 off: the request is recorded, with no prompt or reply stored",
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
            self.h.f18(Steps(), "unused", {}, self.base, self.h.Console(self.base, "owner"), self.rig.person_id)

    def test_storage_is_turned_off_again_even_when_a_step_fails(self):
        h, steps = self.h, Steps()
        real, calls = h.record, []

        def record(console, person_id, after, timeout=20):
            calls.append(after)
            return real(console, person_id, after) if len(calls) == 1 else None  # the second lookup finds nothing
        h.record = record
        with self.assertRaises(AssertionError):
            h.f18(steps, "unused", {}, self.base, h.Console(self.base, "owner"), self.rig.person_id)
        self.assertEqual(self.rig.gw.db.get_setting("store_bodies"), "0")
        self.assertEqual([n for n, ok, _ in steps.seen if not ok], ["F-18 on: a role with the trust area reads the prompt"])
        self.assertEqual(steps.seen[-1][:2], ("F-18: storage is off again", True))


class FakeOwner:
    def __init__(self, opened=True):
        self.opened = opened

    def call(self, method, path, body=None):
        if path.startswith("/launches"):
            return 200, {"items": [{"tool_id": "canva", "outcome": "opened"}] if self.opened else []}
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

    def test_close_only_targets_this_folder(self):
        src = (ROOT / "packaging" / "hub_journey.py").read_text(encoding="utf-8")
        self.assertIn('"--user-data-dir=" + needle', src)
        self.assertIn("$_.CommandLine.Contains($env:SWANGZ_WS_FOLDER)", src)
        self.assertNotIn("killall", src)
        self.assertNotIn("taskkill /IM", src)


class WiringTests(unittest.TestCase):
    def test_both_journeys_run_the_steps_after_reconnect_and_before_the_upgrade(self):
        mac = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        win = (ROOT / "packaging" / "windows" / "installer_e2e.py").read_text(encoding="utf-8")
        for text, before, after in ((mac, "Hub back: the server records", "install(j, args.new, apps"),
                                    (win, "network interruption: sync exited 1", "# 6. upgrade")):
            self.assertLess(text.index(before), text.index("hub_journey.workspace("))
            self.assertLess(text.index("hub_journey.workspace("), text.index("hub_journey.f18("))
            self.assertLess(text.index("hub_journey.f18("), text.index(after))

    def test_the_folder_name_and_marker_agree_with_the_app(self):
        from swangz_client import browser_profiles
        h = load()
        self.assertEqual((h.FOLDER.pattern, h.MARKER), (browser_profiles.FOLDER.pattern, browser_profiles.MARKER))

    def test_the_fixture_reports_its_person(self):
        self.assertIn('"person": rig.person_id', (ROOT / "tests" / "browser" / "demo.py").read_text(encoding="utf-8"))
