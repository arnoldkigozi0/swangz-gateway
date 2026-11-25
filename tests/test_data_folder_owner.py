"""D-026, ruling on #353: when the app makes the person the owner of its data folder, and when it never does.
The Windows calls are faked here; the Windows installer journey does the real one."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from swangz_client import cli, core, shell, winacl

ME, OTHER, ADMINS = "S-1-5-21-1-2-3-500", "S-1-5-21-1-2-3-1002", "S-1-5-32-544"
DIRECTORY, REPARSE = 0x10, 0x400


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.profile = Path(tempfile.mkdtemp(prefix="sgw-owner-"))
        self.data = self.profile / "Swangz"
        self.data.mkdir()
        self.owner, self.set_calls = ADMINS, []

    def claim(self, path=None, kind=1, user=ME, attributes=DIRECTORY, fails=False, ignored=False, opened=None):
        def set_owner(fd):
            self.set_calls.append(fd)
            if fails:
                raise OSError(5, "access denied")
            if not ignored:
                self.owner = user

        def open_it(path):
            if opened:
                raise opened
            return os.open(path, os.O_RDONLY)

        with patch.object(winacl, "token_elevation_type", return_value=kind), \
                patch.object(winacl, "current_sid", return_value=user), \
                patch.object(winacl, "local_app_data", return_value=str(self.profile)), \
                patch.object(winacl, "_open_for_owner", side_effect=open_it), \
                patch.object(winacl, "_attributes", return_value=attributes), \
                patch.object(winacl, "_owner_of_open", side_effect=lambda fd: self.owner), \
                patch.object(winacl, "_set_owner_of_open", side_effect=set_owner):
            return winacl.claim_data_folder(str(path or self.data))

    def refusal(self):
        with patch.object(shell.sys, "platform", "win32"), \
                patch.object(winacl, "token_elevation_type", return_value=1), \
                patch.object(winacl, "current_sid", return_value=ME), \
                patch.object(winacl, "owner_sid", return_value=self.owner):
            return shell.cleanup_refusal(self.data)

    def untouched(self, owner, **how):
        self.owner = owner
        self.assertIsNone(self.claim(**how))
        self.assertEqual((self.owner, self.set_calls), (owner, []))

    def test_a_folder_the_administrators_group_owns_becomes_the_persons(self):
        self.assertEqual(self.refusal(), "wrong_account")
        for kind in (1, 3):
            self.owner = ADMINS
            self.assertEqual(self.claim(kind=kind), {"before": ADMINS, "after": ME, "outcome": "claimed"})
            self.assertIsNone(self.refusal())

    def test_another_users_folder_or_any_other_owner_is_never_taken(self):
        for owner in (OTHER, "S-1-5-18", "S-1-5-32-545"):
            with self.subTest(owner=owner):
                self.untouched(owner)
                self.assertEqual(self.refusal(), "wrong_account")
        self.untouched(ME)  # already theirs

    def test_a_reparse_point_or_a_file_is_not_claimed(self):
        self.untouched(ADMINS, attributes=DIRECTORY | REPARSE)
        self.untouched(ADMINS, attributes=0x80)

    def test_a_raised_or_service_token_claims_nothing(self):
        self.untouched(ADMINS, kind=2)
        self.untouched(ADMINS, kind=0)
        for sid in shell.SYSTEM_SIDS:
            self.untouched(ADMINS, user=sid)

    def test_only_the_fixed_folder_in_the_persons_profile_is_claimed(self):
        elsewhere = self.profile / "elsewhere"
        elsewhere.mkdir()
        for path in (elsewhere, self.profile, self.data / "browser-profiles"):
            with self.subTest(path=path):
                self.untouched(ADMINS, path=path)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(elsewhere)}):  # the environment does not choose it
            (elsewhere / "Swangz").mkdir()
            self.untouched(ADMINS, path=elsewhere / "Swangz")

    def test_a_claim_that_fails_leaves_cleanup_refusing(self):
        for how in ({"fails": True}, {"ignored": True}):
            self.owner = ADMINS
            self.assertEqual(self.claim(**how), {"before": ADMINS, "after": ADMINS, "outcome": "failed"})
            self.assertEqual(self.refusal(), "wrong_account")
        self.set_calls.clear()
        self.untouched(ADMINS, opened=OSError(5, "access denied"))


class ClientClaimTests(unittest.TestCase):
    def client(self, data):
        return core.Client(core.Paths(home=data, data=data))

    def test_every_start_and_cleanup_claim_before_the_refusal_rule_and_note_the_change(self):
        data = Path(tempfile.mkdtemp(prefix="sgw-owner-app-"))
        change = {"before": ADMINS, "after": ME, "outcome": "claimed"}
        order = []
        with patch.object(core.sys, "platform", "win32"), \
                patch.object(winacl, "claim_data_folder", side_effect=lambda p: order.append(("claim", p)) or change):
            client = self.client(data)
            self.assertEqual(order, [("claim", str(data))])
            self.assertRegex((data / "ownership.log").read_text(encoding="utf-8"),
                             f"data folder owner {ADMINS} -> {ME} claimed")
            order.clear()
            with patch.object(shell, "cleanup_refusal", side_effect=lambda d: order.append(("rule", str(d))) or "wrong_account"):
                with self.assertRaises(core.CleanupRefused):
                    client.cleanup()
        self.assertEqual(order, [("claim", str(data)), ("rule", str(data))])

    def test_the_command_line_claims_before_it_refuses_and_reports_what_to_do(self):
        data = Path(tempfile.mkdtemp(prefix="sgw-owner-app-"))
        paths, report, order = core.Paths(home=data, data=data), data / "report.txt", []
        with patch.object(core, "claim_data_folder", side_effect=lambda p: order.append(("claim", p))), \
                patch.object(shell, "cleanup_refusal", side_effect=lambda d: order.append(("rule", d)) or "wrong_account"), \
                patch.object(cli, "say"):
            self.assertEqual(cli.main(["cleanup", "--report", str(report)], SimpleNamespace(paths=paths)), 1)
        self.assertEqual(order, [("claim", paths), ("rule", data)])
        self.assertEqual(report.read_text(encoding="utf-8-sig").splitlines(), [cli.DISCONNECT])

    def test_signing_in_claims_the_folder_it_made(self):
        data = Path(tempfile.mkdtemp(prefix="sgw-owner-app-")) / "Swangz"
        seen = []
        answers = {"/device/code": {"device_code": "d", "user_code": "U", "verification_uri": "http://localhost:1/device",
                                    "interval": 0},
                   "/device/token": {"key_id": 1, "key": "sk-swz-test", "owner_kind": "personal", "person": {"name": "A"}}}

        class Api:
            def call(self, method, path, body=None, auth=True):
                return answers[path]
        with patch.object(core.sys, "platform", "win32"), \
                patch.object(winacl, "claim_data_folder", side_effect=lambda p: seen.append(Path(p, "device.json").exists())):
            client = core.Client(core.Paths(home=data.parent, data=data), api_factory=lambda server, key=None: Api(),
                                 sleep=lambda s: None, open_url=lambda url: None)
            client.store.save_device = lambda info, key: (data.mkdir(), (data / "device.json").write_text("{}"))
            client.store.save_state = lambda state: None
            client.store.device = lambda: None
            client.login("http://localhost:1", "laptop")
        self.assertEqual(seen, [False, True])  # at the start, and again once signing in has written the folder

    def test_nothing_is_claimed_elsewhere_and_a_claim_that_raises_stops_nothing(self):
        data = Path(tempfile.mkdtemp(prefix="sgw-owner-app-"))
        with patch.object(winacl, "claim_data_folder", side_effect=RuntimeError) as claim:
            with patch.object(core.sys, "platform", "linux"):
                self.client(data)
            claim.assert_not_called()
            with patch.object(core.sys, "platform", "win32"):
                self.client(data)
            claim.assert_called_once()
        self.assertFalse((data / "ownership.log").exists())


if __name__ == "__main__":
    unittest.main()
