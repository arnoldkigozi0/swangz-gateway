"""A voice, image or video job is followed or cancelled only by the person who started it, from any of their keys;
a tool-scoped key must also be for the job's tool. Anything the gateway cannot tie to that person is refused."""

import json
import os
import sqlite3
import time
import unittest
from unittest.mock import patch

from gateway import proxy, security
from gateway.config import Provider
from tests.support import Rig

SECOND = "second-video"
REFUSAL = (403, "blocked", "job ownership")


class MediaJobOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db, self.a = self.rig.gw.db, self.rig.person_id
        self.db.set_setting("store_bodies", "1")  # so a poll copies the reply onto the job's record
        os.environ["FAKE_CUSTOM_KEY"] = "custom-provider-secret"
        self.rig.settings.providers["custom"] = Provider("custom", self.rig.fake.url, "FAKE_CUSTOM_KEY", "media", label="Custom")
        self.b = self.db.x("INSERT INTO people(name, email, department, created) VALUES(?,?,?,?)",
                           ("Okello Sam", "sam@swangzavenue.com", "Creative", time.time())).lastrowid
        self.a_key, self.b_key = self.rig.key, self.key_for(self.b)

    def key_for(self, person):
        key_id, key, secret_hash, hint = security.new_key()
        self.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,?,?,?,?,?)",
                  (key_id, person, "another device", secret_hash, hint, time.time()))
        return key

    def scoped_key(self, tool_id):
        self.db.x("INSERT OR IGNORE INTO entitlements(tool_id, person_id, granted) VALUES(?,?,1)", (tool_id, self.a))
        status, out = self.rig.api("POST", f"/people/{self.a}/keys", {"label": tool_id, "tool_id": tool_id})
        self.assertEqual(status, 200, out)
        return out["key"]

    def send(self, method, path, key, body=None, extra=None):
        """-> (status, body, the request's record)"""
        headers = {"authorization": f"Bearer {key}", "user-agent": "python-requests/2.32", **(extra or {})}
        status, _, payload = self.rig.request(method, path, body, headers)
        return status, payload, self.rig.last_record()

    def start(self, key=None, provider="higgsfield"):
        status, payload, row = self.send("POST", f"/{provider}/flux-pro/image", key or self.a_key, {"prompt": "a poster"})
        self.assertEqual(status, 200, payload)
        job = json.loads(payload)["request_id"]
        self.assertEqual((row["turn_id"], row["outcome"]), (job, "ok"))
        return job, row["id"]

    def record(self, rid):
        return self.db.one("SELECT * FROM requests WHERE id = ?", (rid,))

    def refused(self, method, path, key, body=None):
        sent = len(self.rig.fake.seen)
        status, payload, row = self.send(method, path, key, body)
        self.assertEqual((status, row["outcome"], row["reason"]), REFUSAL, payload)
        self.assertEqual(len(self.rig.fake.seen), sent)  # nothing reached the provider
        return row

    def passed(self, method, path, key, body=None):
        sent = len(self.rig.fake.seen)
        status, payload, row = self.send(method, path, key, body)
        self.assertLess(status, 300, payload)
        self.assertEqual((len(self.rig.fake.seen), row["outcome"]), (sent + 1, "ok"), row["reason"])
        return row

    # ------------------------------------------------------------ whose job

    def test_the_owners_poll_still_copies_the_result_onto_the_job(self):
        job, rid = self.start()
        for _ in range(2):
            self.passed("GET", f"/higgsfield/requests/{job}/status", self.a_key)
        self.assertEqual(self.record(rid)["reply"], "completed · 1 result")
        self.assertTrue(self.record(rid)["result_urls"])

    def test_another_person_cannot_poll_it_and_the_record_is_untouched(self):
        job, rid = self.start()
        self.rig.fake.jobs[job]["polls"] = 5  # the provider would hand over the result now
        before = self.record(rid)
        row = self.refused("GET", f"/higgsfield/requests/{job}/status", self.b_key)
        self.assertEqual(row["person_id"], self.b)
        self.assertEqual(self.record(rid), before)

    def test_another_person_cannot_cancel_it(self):
        job, _ = self.start()
        row = self.refused("POST", f"/higgsfield/requests/{job}/cancel", self.b_key)
        self.assertEqual((row["person_id"], row["kind"]), (self.b, "other"))

    def test_the_owner_cancels_and_polls_from_a_second_key(self):
        job, _ = self.start()
        second = self.key_for(self.a)
        self.passed("GET", f"/higgsfield/requests/{job}/status", second)
        self.passed("POST", f"/higgsfield/requests/{job}/cancel", second)

    def test_no_other_way_of_writing_the_path_gets_round_it(self):
        job, _ = self.start()
        cases = (("POST", f"/higgsfield/requests/{job}/status"), ("GET", f"/higgsfield/requests/{job}"),
                 ("GET", f"/higgsfield/requests/{job}/status/"), ("GET", f"/higgsfield/requests//{job}/status"),
                 ("POST", f"/higgsfield/%72equests/{job}/status"), ("POST", f"/higgsfield/requests/{job}/%63ancel"),
                 ("POST", f"/higgsfield/Requests/{job}/cancel"), ("POST", f"/higgsfield/v1/requests/{job}/cancel"),
                 ("POST", f"/higgsfield/requests;x/{job}/status"))
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.refused(method, path, self.b_key)

    def test_a_path_that_cannot_be_read_as_one_job_is_refused_even_for_the_owner(self):
        job, _ = self.start()
        for method, path in (("GET", f"/higgsfield/requests//{job}/status"), ("GET", f"/higgsfield/requests/{job}/more"),
                             ("POST", f"/higgsfield/requests/{job}/requests/other/cancel"),
                             ("POST", f"/higgsfield/requests/{job}/%63ancel")):
            with self.subTest(method=method, path=path):
                self.refused(method, path, self.a_key)

    def test_an_unknown_or_purged_job_is_refused_and_recorded(self):
        row = self.refused("GET", "/higgsfield/requests/job9999-unknown/status", self.a_key)
        self.assertEqual((row["person_id"], row["kind"]), (self.a, "media-status"))
        job, rid = self.start()
        self.db.x("DELETE FROM requests WHERE id = ?", (rid,))
        self.refused("GET", f"/higgsfield/requests/{job}/status", self.a_key)
        self.refused("POST", f"/higgsfield/requests/{job}/cancel", self.a_key)

    def test_a_failed_or_refused_start_does_not_make_an_owner(self):
        job, rid = self.start()
        for outcome in ("error", "blocked", "cut"):
            self.db.x("UPDATE requests SET outcome = ? WHERE id = ?", (outcome, rid))
            with self.subTest(outcome=outcome):
                self.refused("GET", f"/higgsfield/requests/{job}/status", self.a_key)

    def test_a_job_on_one_provider_is_not_a_job_on_another(self):
        job, _ = self.start()
        self.refused("GET", f"/custom/requests/{job}/status", self.a_key)

    # ------------------------------------------------------------ Higgsfield job sets

    def start_set(self, key=None):
        status, payload, row = self.send("POST", "/higgsfield/v1/text2image/soul", key or self.a_key, {"prompt": "a poster"})
        self.assertEqual(status, 200, payload)
        job = json.loads(payload)["id"]
        self.assertEqual((row["turn_id"], row["kind"], row["outcome"]), (job, "media", "ok"))
        return job, row["id"]

    def test_a_job_set_is_read_only_by_whoever_started_it(self):
        job, rid = self.start_set()
        before = self.record(rid)
        row = self.refused("GET", f"/higgsfield/v1/job-sets/{job}", self.b_key)
        self.assertEqual((row["person_id"], row["kind"]), (self.b, "other"))
        self.assertEqual(self.record(rid), before)
        for key in (self.a_key, self.key_for(self.a)):
            self.passed("GET", f"/higgsfield/v1/job-sets/{job}", key)
        self.refused("GET", "/higgsfield/v1/job-sets/set9999-unknown", self.a_key)
        self.db.x("DELETE FROM requests WHERE id = ?", (rid,))
        self.refused("GET", f"/higgsfield/v1/job-sets/{job}", self.a_key)

    def test_no_other_way_of_writing_a_job_set_path_gets_round_it(self):
        job, _ = self.start_set()
        mine, _ = self.start_set(self.b_key)
        for method, path in (("GET", f"/higgsfield/v1/job-sets/{job}/"), ("GET", f"/higgsfield/v1/job-sets//{job}"),
                             ("GET", f"/higgsfield/v1/job-sets/{job}/{mine}"), ("GET", f"/higgsfield/v1/job-sets/{mine}/{job}"),
                             ("GET", f"/higgsfield/v1/job-sets/{mine};/{job}"), ("GET", f"/higgsfield/requests/{job}"),
                             ("GET", f"/higgsfield/v1/job-sets/%73{job[1:]}"), ("POST", f"/higgsfield/v1/job-sets/{job}"),
                             ("POST", f"/higgsfield/v1/%6Aob-sets/{job}"), ("POST", f"/higgsfield/v1/Job-Sets/{job}")):
            with self.subTest(method=method, path=path):
                self.refused(method, path, self.b_key)

    # ------------------------------------------------------------ nobody can claim a job

    def test_a_tool_cannot_name_the_job_of_its_own_request(self):
        job, rid = self.start()
        for name, value in (("x-claude-code-prompt-id", job), ("x-codex-turn-metadata", json.dumps({"turn_id": job}))):
            with self.subTest(header=name):
                status, payload, row = self.send("POST", "/higgsfield/v1/text-to-speech/voice01", self.b_key,
                                                 {"text": "hello"}, {name: value})
                self.assertEqual((status, row["kind"], row["turn_id"]), (200, "media", None), payload)
        self.db.x("DELETE FROM requests WHERE id = ?", (rid,))  # even once the real record is gone
        self.refused("GET", f"/higgsfield/requests/{job}/status", self.b_key)

    def test_an_answer_naming_someone_elses_job_does_not_hand_it_over(self):
        job, rid = self.start()
        row = self.passed("POST", "/higgsfield/v1/echo-job", self.b_key, {"job": job})
        self.assertIsNone(row["turn_id"])
        self.db.x("DELETE FROM requests WHERE id = ?", (rid,))
        self.refused("GET", f"/higgsfield/requests/{job}/status", self.b_key)

    def test_a_later_record_naming_the_job_neither_takes_it_nor_receives_the_result(self):
        job, rid = self.start()
        later = self.db.x("INSERT INTO requests(ts, person_id, provider, method, path, kind, client, outcome, turn_id)"
                          " VALUES(?,?,'higgsfield','POST','/x','media','x','ok',?)", (time.time(), self.b, job)).lastrowid
        self.refused("GET", f"/higgsfield/requests/{job}/status", self.b_key)
        for _ in range(2):
            self.passed("GET", f"/higgsfield/requests/{job}/status", self.a_key)
        self.assertTrue(self.record(rid)["result_urls"])
        self.assertEqual((self.record(later)["result_urls"], self.record(later)["reply"]), (None, None))

    # ------------------------------------------------------------ tool-scoped keys

    def test_a_scoped_key_follows_only_its_own_tools_jobs(self):
        row = dict(self.db.one("SELECT * FROM tools WHERE id = 'higgsfield-ai'"), id=SECOND, name="Second video")
        self.db.x(f"INSERT INTO tools({', '.join(row)}) VALUES({', '.join('?' * len(row))})", tuple(row.values()))
        own, other = self.scoped_key("higgsfield-ai"), self.scoped_key(SECOND)
        job, rid = self.start(own)
        self.assertEqual(self.record(rid)["hub_tool_id"], "higgsfield-ai")
        for method, path in (("GET", f"/higgsfield/requests/{job}/status"), ("POST", f"/higgsfield/requests/{job}/cancel")):
            with self.subTest(method=method):
                self.refused(method, path, other)
                self.passed(method, path, own)
                self.passed(method, path, self.a_key)  # the person's unscoped key

    # ------------------------------------------------------------ custom media providers

    def test_a_custom_providers_get_needs_one_of_the_persons_jobs_as_a_whole_path_segment(self):
        job, rid = self.start(provider="custom")
        for path in ("/custom/v1/models", "/custom", "/custom/requests/job9999-unknown/status",
                     f"/custom/requests/x{job}/status", f"/custom/requests/{job}.json", f"/custom/requests/%6A{job[1:]}/status",
                     f"/custom/requests//{job}/status", f"/custom/other/%2e%2e/{job}"):
            with self.subTest(path=path):
                self.refused("GET", path, self.a_key)
        self.refused("GET", f"/custom/requests/{job}/status", self.b_key)
        for _ in range(2):
            self.passed("GET", f"/custom/requests/{job}/status", self.a_key)
        self.assertTrue(self.record(rid)["result_urls"])

    def test_a_custom_providers_path_naming_two_peoples_jobs_is_refused(self):
        mine, _ = self.start(provider="custom")
        theirs, _ = self.start(self.b_key, provider="custom")
        for first, second in ((mine, theirs), (theirs, mine)):
            with self.subTest(first=first):
                self.refused("GET", f"/custom/jobs/{first}/compare/{second}", self.a_key)
                self.refused("GET", f"/custom/jobs/{first}/requests/{second}/cancel", self.a_key)

    def test_a_custom_providers_cancel_is_the_owners_only(self):
        job, _ = self.start(provider="custom")
        for path in (f"/custom/requests/{job}/cancel", f"/custom/requests/{job}/%63ancel",
                     f"/custom/requests/{job}//cancel", f"/custom/v1/Requests/{job}/cancel"):
            with self.subTest(path=path):
                self.refused("POST", path, self.b_key)
        self.passed("POST", f"/custom/requests/{job}/cancel", self.a_key)

    # ------------------------------------------------------------ failure and timing

    def test_when_the_owner_cannot_be_read_the_request_is_refused(self):
        job, _ = self.start()
        for method, path in (("GET", f"/higgsfield/requests/{job}/status"), ("POST", f"/higgsfield/requests/{job}/cancel")):
            with self.subTest(method=method), patch.object(proxy, "media_owner", side_effect=sqlite3.OperationalError("disk")):
                sent = len(self.rig.fake.seen)
                status, payload, row = self.send(method, path, self.a_key)
                self.assertEqual((status, row["outcome"], row["reason"]),
                                 (503, "blocked", "job ownership check failed"), payload)
                self.assertEqual(len(self.rig.fake.seen), sent)

    def test_a_poll_sent_before_the_job_is_written_down_waits_for_it(self):
        real = proxy.purpose.classify

        def slow(db, rec, *args, **kwargs):
            if rec["kind"] == "media":
                time.sleep(0.5)  # the record is written just after the answer has gone back
            return real(db, rec, *args, **kwargs)

        headers = {"authorization": f"Bearer {self.a_key}"}
        with patch.object(proxy.purpose, "classify", side_effect=slow):
            status, _, payload = self.rig._request("POST", "/higgsfield/flux-pro/image", {"prompt": "a poster"}, headers)
            self.assertEqual(status, 200, payload)
            job = json.loads(payload)["request_id"]
            status, _, payload = self.rig._request("GET", f"/higgsfield/requests/{job}/status", None, headers)
            self.assertEqual(status, 200, payload)
            self.rig.wait_for(lambda: self.db.scalar("SELECT COUNT(*) FROM requests WHERE turn_id = ?", (job,)) == 2)


if __name__ == "__main__":
    unittest.main()
