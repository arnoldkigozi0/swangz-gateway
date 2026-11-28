"""The model rules, company policies, budgets and the rate limit apply to a chat provider's requests whatever the
endpoint; following a media job and a chat provider's bodyless reads are not new use."""

import json
import time
import unittest

from tests.support import Rig

PATHS = (("/openai/v1/completions", "gpt-6.1"), ("/openai/v1/embeddings", "gpt-6.1"),
         ("/openai/v1/responses/compact", "gpt-6.1"), ("/anthropic/v1/messages/count_tokens", "claude-opus-5-5"))
READS = ("/openai/v1/models", "/openai/v1/models/gpt-6.1", "/anthropic/v1/models")


class CompanyCheckTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db = self.rig.gw.db

    def admin(self, method, path, body):
        status, out = self.rig.api(method, path, body)
        self.assertEqual(status, 200, out)
        return out

    def deny(self, provider=None):
        body = {"name": "Not today", "effect": "deny", "subjects": {"everyone": True}}
        if provider:
            body["scope"] = {"providers": [provider]}
        return self.admin("POST", "/policies", body)["id"]

    def spent(self, cost):
        self.db.x("INSERT INTO requests(ts, person_id, provider, method, path, kind, outcome, cost)"
                  " VALUES(?, ?, 'openai', 'POST', '/v1/responses', 'responses', 'ok', ?)",
                  (time.time(), self.rig.person_id, cost))

    def send(self, path, body=None, method="POST", key=None):
        """-> (status, the request's record, how many requests reached the provider)"""
        sent = len(self.rig.fake.seen)
        status, _, _ = self.rig.request(method, path, body, {"authorization": f"Bearer {key or self.rig.key}",
                                                             "user-agent": "python-requests/2.32"})
        return status, self.rig.last_record(), len(self.rig.fake.seen) - sent

    def ask(self, path, model):
        return self.send(path, {"model": model, "input": "hi", "prompt": "hi",
                                "messages": [{"role": "user", "content": "hi"}]})

    def refused(self, answer, status, reason, rule=None):
        got, row, reached = answer
        self.assertEqual((got, row["outcome"], row["reason"], row["rule"], reached), (status, "blocked", reason, rule, 0))

    def passed(self, answer):
        """It reached the provider (the stand-in answers 404 for a path it doesn't play)."""
        status, row, reached = answer
        self.assertEqual((reached, row["outcome"] != "blocked"), (1, True), (status, row["reason"]))

    def every_path(self, status, reason, rule=None):
        for path, model in PATHS:
            with self.subTest(path=path, reason=reason):
                self.refused(self.ask(path, model), status, reason, rule)

    def all_pass(self):
        for path, model in PATHS:
            with self.subTest(path=path):
                self.passed(self.ask(path, model))

    def test_allowed_requests_pass(self):
        self.all_pass()
        # also with rules in place that don't cover them
        self.admin("PUT", "/models/some-other-model", {"status": "disabled"})
        self.deny("elevenlabs")
        self.admin("PATCH", f"/people/{self.rig.person_id}", {"daily_budget": "100", "monthly_budget": "100"})
        self.admin("PUT", "/settings", {"rate_per_min": 100})
        self.all_pass()

    def test_a_switched_off_model(self):
        for path, model in PATHS:
            self.admin("PUT", f"/models/{model}", {"status": "disabled"})
            with self.subTest(path=path):
                self.refused(self.ask(path, model), 403, "model disabled", f"model:{model}")
                self.passed(self.ask(path, "another-model"))

    def test_a_department_restricted_model(self):
        for model in {m for _, m in PATHS}:
            self.admin("PUT", f"/models/{model}", {"status": "restricted", "allowed_departments": ["Engineering"]})
        for path, model in PATHS:
            with self.subTest(path=path):
                self.refused(self.ask(path, model), 403, "model restricted", f"model:{model}")
        for model in {m for _, m in PATHS}:
            self.admin("PUT", f"/models/{model}", {"allowed_departments": ["Engineering", "Creative"]})
        self.all_pass()

    def test_a_deny_policy(self):
        pid = self.deny()
        self.every_path(403, "policy: Not today", f"policy:{pid}")

    def test_a_monthly_cap(self):
        pid = self.admin("POST", "/policies", {"name": "Small cap", "effect": "cap", "subjects": {"everyone": True},
                                               "params": {"limit_usd": 1}})["id"]
        self.all_pass()
        self.spent(2.0)
        self.every_path(403, "policy: Small cap", f"policy:{pid}")

    def test_used_up_personal_budgets(self):
        self.spent(2.0)
        for field, reason in (("daily_budget", "daily budget"), ("monthly_budget", "monthly budget")):
            self.admin("PATCH", f"/people/{self.rig.person_id}", {"daily_budget": "", "monthly_budget": "", field: "1"})
            self.every_path(403, reason)

    def test_the_rate_limit(self):
        self.admin("PUT", "/settings", {"rate_per_min": 1})
        self.passed(self.ask(*PATHS[0]))
        self.every_path(429, "rate limited")

    def test_each_endpoint_counts_towards_the_rate_limit(self):
        self.admin("PUT", "/settings", {"rate_per_min": 1})
        for path, model in PATHS:
            with self.subTest(path=path):
                self.rig.gw.ratelimit.hits.clear()
                self.passed(self.ask(path, model))
                self.refused(self.ask(path, model), 429, "rate limited")

    def test_a_policy_that_cannot_be_read_refuses(self):
        self.deny()
        self.db.x("UPDATE policies SET params = 'not json', effect = 'hours'")
        self.rig.gw.reload_governance()
        self.every_path(503, "policy check failed", "policy:error")

    def test_an_added_endpoint_taking_a_file(self):
        self.rig.gw.extra_endpoints = "POST /v1/audio/*"
        pid = self.deny()
        sent = len(self.rig.fake.seen)
        status, _, _ = self.rig.request("POST", "/openai/v1/audio/transcriptions", b"--b--\r\n",
                                        {"authorization": f"Bearer {self.rig.key}",
                                         "content-type": "multipart/form-data; boundary=b"})
        self.refused((status, self.rig.last_record(), len(self.rig.fake.seen) - sent), 403, "policy: Not today",
                     f"policy:{pid}")

    def test_bodyless_reads_are_not_new_use(self):
        self.deny()
        self.spent(2.0)
        self.admin("PATCH", f"/people/{self.rig.person_id}", {"daily_budget": "1"})
        self.admin("PUT", "/settings", {"rate_per_min": 1})
        self.rig.gw.ratelimit.over(self.rig.person_id, 1)  # the minute's one request is taken
        for path in READS:
            with self.subTest(path=path):
                self.passed(self.send(path, method="GET"))

    def test_a_media_job_is_still_followed(self):
        status, _, payload = self.rig.request("POST", "/higgsfield/flux-pro/image", {"prompt": "a poster"},
                                              {"authorization": f"Bearer {self.rig.key}"})
        self.assertEqual(status, 200, payload)
        job = json.loads(payload)["request_id"]
        pid = self.deny()
        self.passed(self.send(f"/higgsfield/requests/{job}/status", method="GET"))
        # anything else on a media provider is checked
        for method, path in (("POST", f"/higgsfield/requests/{job}/cancel"), ("GET", "/elevenlabs/v1/voices"),
                             ("GET", "/higgsfield/v1/motions")):
            with self.subTest(path=path):
                self.refused(self.send(path, method=method), 403, "policy: Not today", f"policy:{pid}")


if __name__ == "__main__":
    unittest.main()
