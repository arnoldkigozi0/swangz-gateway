"""An older Swangz build never replaces a newer one (swangz_client/core.py check_newest_app). The Windows installer
refuses it; on a Mac the app is dragged in, so the older copy refuses to run while the device is signed in."""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from swangz_client import cli, core


class NewestAppTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.paths = core.Paths(self.root / "home", self.root / "data")
        self.data = self.paths.data
        self.data.mkdir(parents=True)

    def sign_in(self):
        (self.data / "device.json").write_text(json.dumps({"server": "https://hub.example", "key_id": "a" * 12}))

    def floor(self):
        return json.loads((self.data / core.NEWEST_APP).read_text())["version"]

    def test_signed_out_nothing_is_checked_or_written(self):
        (self.data / core.NEWEST_APP).write_text(json.dumps({"version": "9.9.9"}))
        core.check_newest_app(self.paths, running="0.1.0")  # no device: a fresh start with any build
        (self.data / core.NEWEST_APP).unlink()
        core.check_newest_app(self.paths, running="0.1.0")
        self.assertFalse((self.data / core.NEWEST_APP).exists())

    def test_records_the_newest_and_refuses_an_older_copy(self):
        self.sign_in()
        core.check_newest_app(self.paths, running="0.1.0")
        self.assertEqual(self.floor(), "0.1.0")
        core.check_newest_app(self.paths, running="0.1.12")  # 12 > 9: compared as numbers, not text
        self.assertEqual(self.floor(), "0.1.12")
        with self.assertRaises(core.OlderBuild) as caught:
            core.check_newest_app(self.paths, running="0.1.9")
        self.assertIn("Swangz 0.1.12 is already in use", str(caught.exception))
        self.assertEqual(self.floor(), "0.1.12")  # a refusal never lowers the floor
        core.check_newest_app(self.paths, running="0.1.12")

    def test_a_rolled_back_update_does_not_lock_the_restored_build_out(self):
        self.sign_in()
        core.check_newest_app(self.paths, running="0.2.0")
        (self.data / "updates").mkdir()
        (self.data / "updates" / "state.json").write_text(json.dumps({"failed_version": "0.2.0"}))
        core.check_newest_app(self.paths, running="0.1.0")  # the updater restored 0.1.0 after 0.2.0 failed
        self.assertEqual(self.floor(), "0.1.0")

    def test_an_unreadable_record_is_replaced_not_trusted(self):
        self.sign_in()
        (self.data / core.NEWEST_APP).write_text("not json")
        core.check_newest_app(self.paths, running="0.1.0")
        self.assertEqual(self.floor(), "0.1.0")

    def test_sign_out_removes_the_record(self):
        client = core.Client(self.paths, sleep=lambda s: None)
        self.sign_in()
        core.check_newest_app(self.paths, running="0.1.0")
        client.store.wipe()
        self.assertFalse((self.data / core.NEWEST_APP).exists())

    def run_cli(self, *argv):
        client = core.Client(self.paths, sleep=lambda s: None)
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(cli, "alert") as alert:
            code = cli.main(list(argv), client=client)
        return code, out.getvalue(), alert

    def test_the_cli_refuses_with_exit_5_but_still_signs_out(self):
        self.sign_in()
        (self.data / core.NEWEST_APP).write_text(json.dumps({"version": "999.0.0"}))
        for argv in (["status"], ["sync"], ["apps"]):
            code, out, alert = self.run_cli(*argv)
            self.assertEqual(code, 5, argv)
            self.assertIn("Swangz 999.0.0 is already in use", out)
            alert.assert_not_called()
        code, out, alert = self.run_cli()  # the window: opened from Finder, so the refusal is also a dialog
        self.assertEqual(code, 5)
        alert.assert_called_once()
        with mock.patch.object(core.Client, "logout", return_value=True) as logout:
            self.run_cli("logout")
        logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
