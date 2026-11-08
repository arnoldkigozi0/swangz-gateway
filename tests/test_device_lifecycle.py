"""Device credential lifecycle (D-002 / G3b): rotation, the 10-minute grace, idle expiry, and the key-storage report."""

import json
import sqlite3
import threading
import time
import unittest

from gateway import credentials
from gateway.db import DB, SCHEMA

from .test_devices import DeviceBase

HOUR, DAY = 3600, 86400
BODY = {"model": "claude-test", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}


class Lifecycle(DeviceBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db
        self.device = self.enrol()
        self.key = self.device["key"]
        self.device_id = self.device["device_id"]

    def manifest(self, key=None):
        return self.api("GET", "/device/manifest", key=key or self.key)

    def rotate(self, key=None):
        return self.api("POST", "/device/rotate", {}, key=key or self.key)

    def code(self, key):
        status, out, _ = self.manifest(key)
        return status, out.get("code") if isinstance(out, dict) else None

    def unrevoked(self):
        return self.db.scalar("SELECT COUNT(*) FROM keys WHERE device_id = ? AND revoked IS NULL", (self.device_id,))

    def audits(self, like):
        return self.db.q("SELECT * FROM audit WHERE action LIKE ?", (like,))


class RotationTests(Lifecycle):
    def test_rotating_gives_a_new_key_for_the_same_device_and_person(self):
        status, out, headers = self.rotate()
        self.assertEqual(status, 200, out)
        self.assertNotEqual(out["key_id"], self.device["key_id"])
        self.assertEqual((out["device_id"], out["rotate_after_days"]), (self.device_id, 30))
        self.assertIn("no-store", headers["cache-control"])
        new = self.db.one("SELECT * FROM keys WHERE id = ?", (out["key_id"],))
        old = self.db.one("SELECT * FROM keys WHERE id = ?", (self.device["key_id"],))
        self.assertEqual((new["person_id"], new["label"], new["created_by"], new["rotated_from"], new["device_id"]),
                         (self.rig.person_id, "Grace's laptop", "device rotation", old["id"], self.device_id))
        self.assertAlmostEqual(old["retire_at"] - new["created"], credentials.GRACE_SECONDS, delta=2)
        self.assertEqual(out["old_key_valid_until"], old["retire_at"])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM devices"), 1)  # one device, not a new one

    def test_the_new_key_is_stored_hashed_and_appears_in_no_audit_record_or_log(self):
        _, out, _ = self.rotate()
        secret = out["key"].split("_", 2)[2]
        rows = json.dumps(self.db.q("SELECT * FROM keys"), default=str) + json.dumps(self.db.q("SELECT * FROM audit"), default=str)
        self.assertNotIn(secret, rows)
        self.assertNotIn(out["key"], rows)
        self.assertEqual(len(self.audits("rotated a device credential")), 1)
        entry = self.audits("rotated a device credential")[0]
        self.assertEqual(entry["correlation"], f"device:{self.device_id}")
        self.assertIn(out["key_id"], entry["after_json"])
        self.assertIn(self.device["key_id"], entry["before_json"])

    def test_the_old_key_still_passes_device_auth_during_the_grace(self):
        _, out, _ = self.rotate()
        self.assertEqual(self.manifest(self.key)[0], 200)
        self.assertEqual(self.manifest(out["key"])[0], 200)

    def test_the_new_keys_first_device_call_ends_the_old_key_which_then_says_rotated_not_revoked(self):
        _, out, _ = self.rotate()
        self.assertEqual(self.manifest(out["key"])[0], 200)
        status, body, _ = self.manifest(self.key)
        self.assertEqual((status, body["code"]), (401, "device_key_rotated"))
        self.assertNotEqual(body["code"], "device_revoked")  # the app must never wipe on this
        old = self.db.one("SELECT * FROM keys WHERE id = ?", (self.device["key_id"],))
        self.assertEqual(old["revoked_by"], "system: rotated")
        device = self.db.one("SELECT * FROM devices WHERE device_id = ?", (self.device_id,))
        self.assertEqual((device["key_id"], device["rotations"]), (out["key_id"], 1))
        self.assertEqual(len(self.audits("confirmed a rotated device credential")), 1)
        self.assertEqual(self.manifest(out["key"])[0], 200)  # idempotent: a second call changes nothing
        self.assertEqual(self.db.scalar("SELECT rotations FROM devices WHERE device_id = ?", (self.device_id,)), 1)

    def test_use_through_the_proxy_does_not_count_as_the_new_keys_first_use(self):
        _, out, _ = self.rotate()
        self.assertEqual(self.rig.anthropic(BODY, key=out["key"])[0], 200)
        self.assertEqual(self.manifest(self.key)[0], 200)  # old key still alive
        self.assertIsNone(self.db.scalar("SELECT revoked FROM keys WHERE id = ?", (self.device["key_id"],)))

    def test_after_the_ten_minutes_the_old_key_is_refused_everywhere_with_a_renewed_message(self):
        _, out, _ = self.rotate()
        self.db.x("UPDATE keys SET retire_at = ? WHERE id = ?", (time.time() - 1, self.device["key_id"]))
        status, body, _ = self.manifest(self.key)
        self.assertEqual((status, body["code"]), (401, "device_key_rotated"))
        old = self.db.one("SELECT * FROM keys WHERE id = ?", (self.device["key_id"],))
        self.assertEqual((old["revoked_by"], old["revoked"]), ("system: rotated", old["retire_at"]))  # at the moment it was due
        status, _, payload = self.rig.anthropic(BODY, key=self.key)
        self.assertEqual(status, 403)
        self.assertIn("renewed", payload.decode())
        self.assertNotIn("revoked by an administrator", payload.decode())
        self.assertEqual(self.manifest(out["key"])[0], 200)  # the new one is unaffected

    def test_the_grace_is_enforced_on_the_proxy_too_even_if_no_device_call_is_made(self):
        self.rotate()
        self.db.x("UPDATE keys SET retire_at = ? WHERE id = ?", (time.time() - 1, self.device["key_id"]))
        self.assertEqual(self.rig.anthropic(BODY, key=self.key)[0], 403)

    def test_a_rotated_key_after_the_whole_device_is_revoked_says_revoked(self):
        _, out, _ = self.rotate()
        self.manifest(out["key"])  # confirms; the old key is now 'system: rotated'
        self.assertEqual(self.rig.api("POST", f"/keys/{out['key_id']}/revoke")[0], 200)
        self.assertEqual(self.code(self.key), (401, "device_revoked"))
        self.assertEqual(self.code(out["key"]), (401, "device_revoked"))

    def test_the_rotated_device_keeps_its_budgets_and_the_kill_switch_applies_to_the_new_key(self):
        _, out, _ = self.rotate()
        self.assertEqual(self.db.scalar("SELECT person_id FROM keys WHERE id = ?", (out["key_id"],)), self.rig.person_id)
        self.db.set_setting("paused", "1")
        self.assertEqual(self.code(out["key"]), (403, "paused"))
        self.assertEqual(self.rig.anthropic(BODY, key=out["key"])[0], 403)
        self.db.set_setting("paused", "0")
        self.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (self.rig.person_id,))
        self.assertEqual(self.code(out["key"]), (403, "person_paused"))

    def test_a_scoped_tool_key_keeps_its_scope(self):
        self.db.x("UPDATE keys SET hub_tool_id = 'claude-code' WHERE id = ?", (self.device["key_id"],))
        _, out, _ = self.rotate()
        self.assertEqual(self.db.scalar("SELECT hub_tool_id FROM keys WHERE id = ?", (out["key_id"],)), "claude-code")


class SingleWinnerTests(Lifecycle):
    def test_a_second_rotation_from_the_same_key_never_leaves_two_pending_keys(self):
        first = self.rotate()[1]
        second = self.rotate()[1]  # the old key asking again in its grace: the unused one is replaced (Q1)
        self.assertNotEqual(first["key_id"], second["key_id"])
        self.assertEqual(self.db.scalar("SELECT revoked_by FROM keys WHERE id = ?", (first["key_id"],)), "system: reissued")
        pending = self.db.scalar("SELECT COUNT(*) FROM keys WHERE rotated_from = ? AND revoked IS NULL", (self.device["key_id"],))
        self.assertEqual(pending, 1)
        self.assertEqual(self.code(first["key"]), (401, "device_key_rotated"))  # reload the key, never wipe
        self.assertEqual(self.manifest(second["key"])[0], 200)
        self.assertEqual(len(self.audits("reissued a device credential")), 1)

    def test_a_reissue_never_extends_the_grace(self):
        self.rotate()
        before = self.db.scalar("SELECT retire_at FROM keys WHERE id = ?", (self.device["key_id"],))
        time.sleep(0.05)
        out = self.rotate()[1]
        self.assertEqual(self.db.scalar("SELECT retire_at FROM keys WHERE id = ?", (self.device["key_id"],)), before)
        self.assertEqual(out["old_key_valid_until"], before)

    def test_no_reissue_once_the_new_key_has_been_used(self):
        out = self.rotate()[1]
        self.rig.anthropic(BODY, key=out["key"])  # proxy use: not a confirmation, but not "never used" either
        status, body, _ = self.rotate()
        self.assertEqual((status, body["code"]), (409, "rotation_pending"))
        self.assertIsNone(self.db.scalar("SELECT revoked FROM keys WHERE id = ?", (out["key_id"],)))

    def test_the_primitive_is_atomic_only_one_update_wins(self):
        sql = "UPDATE keys SET retire_at = ? WHERE id = ? AND revoked IS NULL AND retire_at IS NULL"
        self.assertEqual(self.db.x(sql, (1.0, self.device["key_id"])).rowcount, 1)
        self.assertEqual(self.db.x(sql, (2.0, self.device["key_id"])).rowcount, 0)

    def test_two_requests_at_once_leave_exactly_one_usable_new_key(self):
        results, gate = [], threading.Barrier(2)

        def go():
            gate.wait()
            results.append(self.rotate())

        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertTrue(all(r[0] in (200, 409) for r in results), [r[:2] for r in results])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM keys WHERE rotated_from = ? AND revoked IS NULL", (self.device["key_id"],)), 1)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM keys WHERE device_id = ? AND revoked IS NULL", (self.device_id,)), 2)

    def test_at_most_three_a_hour(self):
        for _ in range(3):
            self.assertEqual(self.rotate()[0], 200)
        status, body, _ = self.rotate()
        self.assertEqual((status, body["code"]), (429, "slow_down"))
        self.db.x("UPDATE keys SET created = created - ? WHERE created_by = 'device rotation'", (2 * HOUR,))
        self.assertEqual(self.rotate()[0], 200)


class WhoMayRotateTests(Lifecycle):
    def test_no_key_a_made_by_hand_key_a_staff_session_and_the_console_cannot_rotate(self):
        self.assertEqual(self.api("POST", "/device/rotate", {})[0], 401)
        status, body, _ = self.api("POST", "/device/rotate", {}, key=self.rig.key)  # a hand-made key
        self.assertEqual((status, body["code"]), (403, "not_enrolled"))
        self.assertEqual(self.api("POST", "/device/rotate", {}, key="sgw_aaaaaaaaaaaa_bad")[0], 401)
        status, _ = self.staff("POST", "/device/rotate", {}, cookie=self.person_cookie)
        self.assertEqual(status, 401)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM keys WHERE created_by = 'device rotation'"), 0)

    def test_a_revoked_paused_or_ended_account_cannot_rotate(self):
        self.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (self.rig.person_id,))
        self.assertEqual(self.rotate()[1]["code"], "person_paused")
        self.db.x("UPDATE people SET status = 'active' WHERE id = ?", (self.rig.person_id,))
        self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")
        self.assertEqual(self.rotate()[1]["code"], "device_revoked")

    def test_a_device_key_is_never_a_staff_or_console_credential(self):
        header = {"authorization": "Bearer " + self.key, "x-swangz-app": "1"}
        for method, path in (("GET", "/api/me"), ("POST", "/api/keys"), ("POST", "/api/keys/aaaaaaaaaaaa/revoke"),
                             ("GET", "/admin/api/devices"), ("GET", "/admin/api/settings"), ("GET", "/admin/api/people")):
            self.assertEqual(self.rig.request(method, path, {} if method == "POST" else None, header)[0], 401, path)
        self.assertEqual(self.rig.request("PUT", "/admin/api/settings", {"device_idle_days": 30},
                                          {**header, "x-gateway-admin": "1"})[0], 401)


class RevokeTests(Lifecycle):
    def test_revoking_mid_grace_ends_both_keys_from_every_path(self):
        out = self.rotate()[1]
        self.assertEqual(self.rig.api("POST", f"/keys/{self.device['key_id']}/revoke")[0], 200)
        self.assertEqual(self.unrevoked(), 0)
        self.assertEqual(self.code(self.key), (401, "device_revoked"))
        self.assertEqual(self.code(out["key"]), (401, "device_revoked"))
        self.assertEqual(self.rig.anthropic(BODY, key=out["key"])[0], 403)

    def test_the_person_disconnecting_in_the_staff_app_mid_grace_ends_both(self):
        out = self.rotate()[1]
        self.assertEqual(self.staff("POST", f"/keys/{self.device['key_id']}/revoke", cookie=self.person_cookie)[0], 200)
        self.assertEqual(self.unrevoked(), 0)
        self.assertEqual(self.code(out["key"]), (401, "device_revoked"))

    def test_signing_out_with_the_new_key_ends_the_old_one_too(self):
        out = self.rotate()[1]
        self.assertEqual(self.api("POST", "/device/signout", key=out["key"])[0], 200)
        self.assertEqual(self.unrevoked(), 0)
        self.assertEqual(self.code(self.key), (401, "device_revoked"))

    def test_the_command_line_revoke_ends_both(self):
        out = self.rotate()[1]
        credentials.revoke_device_keys(self.db, None, out["key_id"], "command line")
        self.assertEqual(self.unrevoked(), 0)

    def test_revoking_cuts_a_request_in_flight_on_each_key(self):
        cuts = []

        class Live:
            def cut(self, reason, *, key_id=None, **_):
                cuts.append(key_id)
                return 1

        out = self.rotate()[1]
        ids, n = credentials.revoke_device_keys(self.db, Live(), out["key_id"], "x")
        self.assertEqual((sorted(ids), sorted(cuts), n), (sorted([out["key_id"], self.device["key_id"]]),) * 2 + (2,))

    def test_the_ten_device_limit_counts_devices_not_keys(self):
        for i in range(7):  # with the rig's own key that is 8 hand-made keys
            self.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,?,?,?,?,?)",
                      (f"{i:012x}", self.rig.person_id, f"old {i}", "x", "h", time.time()))
        self.rotate()  # the device now holds two active keys but is still one device: 8 + 1 = 9
        self.assertEqual(credentials.active_device_count(self.db, self.rig.person_id), 9)
        self.enrol()  # a tenth device is allowed: with 9 the limit is not reached
        self.assertEqual(credentials.active_device_count(self.db, self.rig.person_id), 10)
        second = self.ask()
        self.assertEqual(self.approve(second["user_code"])[0], 400)  # an eleventh is refused


class IdleTests(Lifecycle):
    def long_ago(self, days):
        t = time.time() - days * DAY
        self.db.x("UPDATE devices SET enrolled = ?, last_seen = ? WHERE device_id = ?", (t, t, self.device_id))
        self.db.x("UPDATE keys SET last_used = ?, created = ? WHERE device_id = ?", (t, t, self.device_id))

    def test_the_default_is_sixty_days(self):
        self.assertEqual(credentials.idle_days(self.db), 60)
        self.long_ago(59)
        self.assertEqual(credentials.expire_idle(self.rig.gw), 0)
        self.assertEqual(self.unrevoked(), 1)
        self.long_ago(61)
        self.assertEqual(credentials.expire_idle(self.rig.gw), 1)
        self.assertEqual(self.unrevoked(), 0)
        self.assertEqual(self.code(self.key), (401, "device_revoked"))

    def test_it_is_audited_as_the_system_with_before_and_after(self):
        self.long_ago(90)
        credentials.expire_idle(self.rig.gw)
        entry = self.audits("revoked an idle device")[0]
        self.assertEqual((entry["actor"], entry["area"], entry["correlation"]), ("system", "trust", f"device:{self.device_id}"))
        self.assertIn("system: idle", entry["after_json"])
        self.assertEqual(self.db.scalar("SELECT revoked_by FROM keys WHERE id = ?", (self.device["key_id"],)), "system: idle")

    def test_a_device_that_never_checked_in_counts_from_enrolment(self):
        self.long_ago(90)
        self.db.x("UPDATE devices SET last_seen = NULL WHERE device_id = ?", (self.device_id,))
        self.db.x("UPDATE keys SET last_used = NULL WHERE device_id = ?", (self.device_id,))
        self.assertEqual(credentials.expire_idle(self.rig.gw), 1)

    def test_use_through_the_proxy_alone_counts_as_activity(self):
        self.long_ago(90)
        self.db.x("UPDATE keys SET last_used = ? WHERE device_id = ?", (time.time() - DAY, self.device_id))
        self.assertEqual(credentials.expire_idle(self.rig.gw), 0)
        self.assertEqual(self.unrevoked(), 1)

    def test_activity_on_any_key_of_a_rotating_device_counts_and_revocation_takes_them_all(self):
        out = self.rotate()[1]
        self.long_ago(90)
        self.db.x("UPDATE keys SET last_used = ? WHERE id = ?", (time.time() - DAY, out["key_id"]))
        self.assertEqual(credentials.expire_idle(self.rig.gw), 0)
        self.db.x("UPDATE keys SET last_used = ? WHERE id = ?", (time.time() - 90 * DAY, out["key_id"]))
        self.assertEqual(credentials.expire_idle(self.rig.gw), 1)
        self.assertEqual(self.unrevoked(), 0)

    def test_refused_retries_on_a_rotated_key_are_not_activity_so_an_orphaned_device_still_goes_idle(self):
        # the rotate response is lost: the app keeps the old key, which is retired after the grace
        out = self.rotate()[1]
        start = time.time() - 70 * DAY
        self.db.x("UPDATE devices SET enrolled = ?, last_seen = ? WHERE device_id = ?", (start, start, self.device_id))
        self.db.x("UPDATE keys SET created = ?, last_used = NULL WHERE device_id = ?", (start, self.device_id))
        self.db.x("UPDATE keys SET retire_at = ? WHERE id = ?", (start + credentials.GRACE_SECONDS, self.device["key_id"]))
        # the old key is retried through the proxy every day since, and refused each time (the proxy stamps last_used first)
        self.assertEqual(self.rig.anthropic(BODY, key=self.key)[0], 403)
        old = self.db.one("SELECT * FROM keys WHERE id = ?", (self.device["key_id"],))
        self.assertEqual(old["revoked_by"], "system: rotated")
        self.assertGreater(old["last_used"], old["revoked"])  # the refused attempt is on record
        self.db.x("UPDATE keys SET last_used = ? WHERE id = ?", (time.time() - DAY, self.device["key_id"]))
        self.assertEqual(self.unrevoked(), 1)  # only the unused new key is left
        self.assertEqual(credentials.expire_idle(self.rig.gw), 1)
        self.assertEqual(self.unrevoked(), 0)
        self.assertEqual(self.db.scalar("SELECT revoked_by FROM keys WHERE id = ?", (out["key_id"],)), "system: idle")

    def test_use_made_while_a_key_was_valid_still_counts_after_it_is_revoked(self):
        out = self.rotate()[1]
        self.long_ago(90)
        used = time.time() - 2 * DAY
        # the old key was used two days ago and retired a minute later: real activity, then a clean retirement
        self.db.x("UPDATE keys SET last_used = ?, revoked = ?, revoked_by = 'system: rotated' WHERE id = ?",
                  (used, used + 60, self.device["key_id"]))
        self.assertEqual(self.unrevoked(), 1)
        self.assertEqual(credentials.expire_idle(self.rig.gw), 0)
        self.assertEqual(self.db.scalar("SELECT revoked FROM keys WHERE id = ?", (out["key_id"],)), None)

    def test_the_setting_is_bounded_audited_and_needs_the_admin_area(self):
        for bad in (0, 6, 366, "soon", None):
            self.assertEqual(self.rig.api("PUT", "/settings", {"device_idle_days": bad})[0], 400, bad)
        self.assertEqual(self.rig.api("PUT", "/settings", {"device_idle_days": 30})[0], 200)
        self.assertEqual(credentials.idle_days(self.db), 30)
        self.assertEqual(self.rig.api("GET", "/settings")[1]["device_idle_days"], 30)
        entry = self.db.one("SELECT * FROM audit WHERE action = 'changed settings' ORDER BY id DESC LIMIT 1")
        self.assertIn("device_idle_days", entry["target"])
        self.assertEqual(self.rig.api("PUT", "/settings", {"device_idle_days": 40}, who="viewer")[0], 403)
        self.assertEqual(credentials.idle_days(self.db), 30)
        self.long_ago(31)
        self.assertEqual(credentials.expire_idle(self.rig.gw), 1)

    def test_the_hourly_job_runs_it_and_a_failure_there_does_not_stop_maintenance(self):
        self.long_ago(90)
        self.rig.gw.maintain()
        self.assertEqual(self.unrevoked(), 0)
        original = credentials.expire_idle
        credentials.expire_idle = lambda gw: 1 / 0
        try:
            self.rig.gw.maintain()
        finally:
            credentials.expire_idle = original
        self.assertNotEqual(self.db.get_setting("maintenance_last", "0"), "0")


class KeyStorageTests(Lifecycle):
    def beat(self, **body):
        return self.api("POST", "/device/heartbeat", body, key=self.key)

    def row(self):
        return self.db.one("SELECT * FROM devices WHERE device_id = ?", (self.device_id,))

    def test_the_app_reports_where_it_keeps_the_key_and_the_console_labels_it_as_reported(self):
        self.assertEqual(self.beat(key_storage="keychain", key_backend="secret-service")[0], 200)
        row = self.row()
        self.assertEqual((row["key_storage"], row["key_backend"]), ("keychain", "secret-service"))
        item = next(d for d in self.rig.api("GET", "/devices")[1]["items"] if d["device_id"] == self.device_id)
        self.assertEqual((item["key_storage"], item["key_storage_source"], item["key_storage_flag"]), ("keychain", "reported by the app", False))

    def test_junk_is_stored_as_unknown_and_an_unknown_backend_as_empty(self):
        self.beat(key_storage="<script>", key_backend="rm -rf")
        self.assertEqual((self.row()["key_storage"], self.row()["key_backend"]), ("unknown", ""))

    def test_an_older_app_that_reports_nothing_is_not_reported_and_not_flagged(self):
        self.assertEqual(self.beat(os="Windows 11")[0], 200)
        self.assertEqual(self.row()["key_storage"], "")
        item = next(d for d in self.rig.api("GET", "/devices")[1]["items"] if d["device_id"] == self.device_id)
        self.assertEqual((item["key_storage"], item["key_storage_flag"], item["key_storage_label"]), (None, False, "Not reported (older app)"))

    def test_only_a_move_to_a_file_is_audited_and_a_repeat_is_not(self):
        self.beat(key_storage="keychain")
        self.assertEqual(len(self.audits("device reported its key is kept in a file")), 0)
        self.beat(key_storage="file")
        self.beat(key_storage="file")
        self.assertEqual(len(self.audits("device reported its key is kept in a file")), 1)
        item = next(d for d in self.rig.api("GET", "/devices")[1]["items"] if d["device_id"] == self.device_id)
        self.assertTrue(item["key_storage_flag"])

    def test_the_report_changes_no_access_decision(self):
        self.beat(key_storage="file")
        self.assertEqual(self.manifest()[0], 200)
        self.assertEqual(self.rig.anthropic(BODY, key=self.key)[0], 200)

    def test_the_manifest_tells_the_app_when_to_rotate(self):
        out = self.manifest()[1]
        self.assertEqual(out["credential"]["rotate_after_days"], 30)
        self.assertEqual(out["device"]["id"], self.device_id)


class ListingTests(Lifecycle):
    def test_a_rotating_device_is_listed_once_by_its_current_key(self):
        out = self.rotate()[1]
        items = [d for d in self.rig.api("GET", "/devices")[1]["items"] if d["device_id"] == self.device_id]
        self.assertEqual([d["id"] for d in items], [self.device["key_id"]])  # the new key is not yet taken up
        self.manifest(out["key"])
        items = [d for d in self.rig.api("GET", "/devices")[1]["items"] if d["device_id"] == self.device_id]
        self.assertEqual([d["id"] for d in items], [out["key_id"]])
        self.assertEqual(items[0]["key_rotations"], 1)
        mine = self.staff("GET", "/me", cookie=self.person_cookie)[1]["keys"]
        self.assertEqual([k["id"] for k in mine if k["label"] == "Grace's laptop"], [out["key_id"]])


class MigrationV22Tests(unittest.TestCase):
    def test_a_v21_database_upgrades_and_every_device_keeps_its_identity(self):
        import os
        import tempfile
        from unittest import mock

        import gateway.db as dbmod

        path = os.path.join(tempfile.mkdtemp(prefix="sgw-v22-"), "g.db")
        with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:21]):
            old = DB(path)
            self.assertEqual(old.scalar("SELECT v FROM meta WHERE k = 'schema'"), "21")
            old.x("INSERT INTO people(id, name, email, created) VALUES(1, 'A', 'a@swangzavenue.com', 1)")
            for kid in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
                old.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,1,'k','x','h',1)", (kid,))
            old.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES('cccccccccccc',1,'hand made','x','h',1)")
            for kid in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
                old.x("INSERT INTO devices(key_id, person_id, name, enrolled) VALUES(?,1,'d',5)", (kid,))
            old.close()
        db = DB(path)  # the migration runs on open
        self.assertEqual(db.scalar("SELECT v FROM meta WHERE k = 'schema'"), str(len(SCHEMA)))
        self.assertGreaterEqual(len(SCHEMA), 22)
        self.assertEqual({r["key_id"]: (r["device_id"], r["key_issued"], r["rotations"], r["key_storage"]) for r in db.q("SELECT * FROM devices")},
                         {"aaaaaaaaaaaa": ("aaaaaaaaaaaa", 5.0, 0, ""), "bbbbbbbbbbbb": ("bbbbbbbbbbbb", 5.0, 0, "")})
        self.assertEqual({r["id"]: r["device_id"] for r in db.q("SELECT id, device_id FROM keys")},
                         {"aaaaaaaaaaaa": "aaaaaaaaaaaa", "bbbbbbbbbbbb": "bbbbbbbbbbbb", "cccccccccccc": None})  # a hand-made key is not a device
        self.assertIsNone(db.scalar("SELECT retire_at FROM keys WHERE id = 'aaaaaaaaaaaa'"))
        with self.assertRaises(sqlite3.IntegrityError):  # one device row per device id
            db.x("UPDATE devices SET device_id = 'aaaaaaaaaaaa' WHERE key_id = 'bbbbbbbbbbbb'")
        db.close()
        DB(path).close()  # opening again changes nothing


if __name__ == "__main__":
    unittest.main()
