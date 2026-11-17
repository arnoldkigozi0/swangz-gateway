"""Probe: gaps in the managed-workspace server tests (W2 contract 2, W4 suspend/retire, W5 policy report).
Black-box through HTTP and the console API; the code under test is not changed."""

import time
import unittest

from gateway import security

from .test_managed_workspace import Base, SHA


class ProbeGapTests(Base):
    def other_persons_device(self):
        db = self.db
        pid = db.x("INSERT INTO people(name, email, created) VALUES('Other','other@swangzavenue.com',?)", (time.time(),)).lastrowid
        key_id, _full, secret_hash, hint = security.new_key()
        db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created, device_id) VALUES(?,?,?,?,?,?,?)",
             (key_id, pid, "x", secret_hash, hint, time.time(), key_id))
        db.x("INSERT INTO devices(key_id, device_id, person_id, name, os, owner_kind, enrolled) VALUES(?,?,?,?,?,?,?)",
             (key_id, key_id, pid, "theirs", "linux", "personal", time.time()))
        return key_id

    def test_a_claim_for_another_persons_suspended_device_neither_refuses_nor_leaks(self):
        self.enable_canva()
        other = self.other_persons_device()
        self.assertEqual(self.workspace("suspend", did=other)[0], 200)
        status, _, body = self.go(f"?d={other}")
        self.assertEqual(status, 302)  # not theirs: ignored, indistinguishable from an unknown id
        self.assertNotIn("paused", body)
        self.assertEqual(self.go("?d=dev-unknown-1")[0], 302)

    def test_a_string_two_in_the_heartbeat_does_not_negotiate_contract_2(self):
        for value in ("2", 2.0, True, [2], None):
            status, out = self.beat({"browser_contract": value})
            self.assertEqual(status, 200)
            if value == 2.0:
                continue  # JSON 2.0 is the integer 2 for many clients; accept either answer, record it below
            self.assertNotIn("workspace", out, repr(value))
        status, out = self.beat({"browser_contract": 2})
        self.assertIn("workspace", out)

    def test_reactivate_from_retired_then_reset_keeps_counting_generations(self):
        self.workspace("retire")
        self.workspace("reactivate")
        self.assertEqual(self.state(), {"s": "active", "g": 2})
        self.workspace("reset")
        self.assertEqual(self.state(), {"s": "active", "g": 3})
        self.assertEqual(self.block()["workspace"], {"state": "active", "generation": 3})

    def test_retire_then_suspend_or_reset_is_refused_and_changes_nothing(self):
        self.workspace("retire")
        for action in ("suspend", "reset"):
            self.assertEqual(self.workspace(action)[0], 409, action)
        self.assertEqual(self.state(), {"s": "retired", "g": 1})

    def test_a_policy_report_with_a_non_boolean_ok_is_ignored(self):
        for bad in (1, 0, "true", "false", None, [], {}):
            self.beat({"policy": {"ok": bad, "sha256": SHA}})
        row = self.db.one("SELECT policy_ok AS o, policy_sha AS s, policy_reported AS r FROM devices WHERE device_id = ?", (self.did,))
        self.assertEqual((row["o"], row["r"]), (None, None))  # nothing was recorded (the sha column's default is the empty string)
        self.assertFalse(row["s"])

    def test_a_policy_report_with_a_bad_sha_is_stored_as_no_sha_and_fails_a_baseline(self):
        self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA, "managed_policy_mode": "enforce"})
        self.enable_canva()
        for sha in ("zz", "A" * 63, "a" * 65, 12345, None):
            self.beat({"policy": {"ok": True, "sha256": sha}})
            self.assertEqual(self.go(f"?d={self.did}")[0], 403, repr(sha))
        self.beat({"policy": {"ok": True, "sha256": SHA.upper()}})  # case-insensitive match is fine
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)

    def test_a_suspended_workspace_still_answers_its_heartbeat_and_keeps_its_key(self):
        self.workspace("suspend")
        status, out = self.beat({"browser_contract": 2})
        self.assertEqual(status, 200)
        self.assertEqual(out["workspace"]["state"], "suspended")
        self.assertEqual(self.manifest()["browser"]["workspace"]["state"], "suspended")


if __name__ == "__main__":
    unittest.main()
