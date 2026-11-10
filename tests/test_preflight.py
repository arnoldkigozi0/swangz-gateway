"""The go-live configuration check: environment in, findings out; no network, no database."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from gateway import preflight
from gateway.__main__ import main

GOOD = {
    "GATEWAY_WEB_URL": "https://ai.swangzavenue.example", "GATEWAY_PUBLIC_URL": "https://ai.swangzavenue.example",
    "GATEWAY_TRUST_PROXY": "1", "GATEWAY_FORCE_HTTPS": "1", "GATEWAY_HOST": "127.0.0.1",
    "GOOGLE_CLIENT_ID": "123-abc.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "s3cret-value-never-printed",
    "ANTHROPIC_API_KEY": "sk-never-printed",
}


def levels(env, level):
    return [name for lv, name, _ in preflight.check(env) if lv == level]


class PreflightTests(unittest.TestCase):
    def test_a_complete_first_party_configuration_passes_and_names_the_address_to_register(self):
        findings = preflight.check(GOOD)
        self.assertEqual([f for f in findings if f[0] != "ok"], [])
        self.assertIn(("ok", "Google return address",
                       "register exactly this in the Google client: https://ai.swangzavenue.example/auth/google/callback"), findings)

    def test_the_addresses_must_be_set_https_bare_and_reachable(self):
        for value in ("", "http://ai.swangzavenue.example", "https://ai.swangzavenue.example/hub", "https://localhost:8787",
                      "https://127.0.0.1", "ai.swangzavenue.example", "https://user:pw@ai.swangzavenue.example", "https://ai.example:port"):
            for key in ("GATEWAY_WEB_URL", "GATEWAY_PUBLIC_URL"):
                self.assertIn(key, levels({**GOOD, key: value}, "fail"), (key, value))

    def test_a_hosting_providers_address_is_flagged_for_review_not_refused(self):
        env = {**GOOD, "GATEWAY_WEB_URL": "https://swangz-ai.netlify.app", "GATEWAY_PUBLIC_URL": "https://x.up.railway.app"}
        self.assertEqual(levels(env, "fail"), [])
        self.assertEqual(levels(env, "warn"), ["GATEWAY_WEB_URL", "GATEWAY_PUBLIC_URL", "GATEWAY_CORS_ORIGINS"])
        self.assertNotIn("GATEWAY_CORS_ORIGINS", levels({**env, "GATEWAY_CORS_ORIGINS": "https://swangz-ai.netlify.app"}, "warn"))

    def test_cors_origins_are_exact_https_addresses(self):
        for bad in ("*", "https://*.swangzavenue.example", "http://ai.swangzavenue.example", "https://ai.swangzavenue.example/x"):
            self.assertIn("GATEWAY_CORS_ORIGINS", levels({**GOOD, "GATEWAY_CORS_ORIGINS": bad}, "fail"), bad)

    def test_google_needs_both_values_and_a_fixed_https_return_address_on_the_web_host(self):
        self.assertIn("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET", levels({**GOOD, "GOOGLE_CLIENT_SECRET": ""}, "fail"))
        self.assertIn("Google sign-in", levels({**GOOD, "GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": ""}, "warn"))
        unfixed = {**GOOD, "GATEWAY_WEB_URL": "", "GATEWAY_PUBLIC_URL": ""}
        self.assertIn("Google return address", levels(unfixed, "fail"))
        for bad in ("http://ai.swangzavenue.example/auth/google/callback", "https://ai.swangzavenue.example/callback",
                    "https://ai.swangzavenue.example/auth/google/callback?x=1", "https://ai.swangzavenue.example/auth/google/callback/"):
            self.assertIn("Google return address", levels({**GOOD, "GOOGLE_REDIRECT_URI": bad}, "fail"), bad)
        elsewhere = {**GOOD, "GOOGLE_REDIRECT_URI": "https://other.example/auth/google/callback"}
        self.assertIn("GOOGLE_REDIRECT_URI", levels(elsewhere, "fail"))
        same = {**GOOD, "GOOGLE_REDIRECT_URI": "https://ai.swangzavenue.example/auth/google/callback"}
        self.assertEqual(levels(same, "fail"), [])

    def test_the_return_address_matches_what_the_gateway_would_send(self):
        """The check and gateway/google.py must agree on the address, or the registered one would be wrong."""
        from gateway import google
        from gateway.config import Settings

        class GW:
            settings = Settings.from_env(GOOD)

            def public_url(self, h=None):
                raise AssertionError("the request must not be consulted when the web address is set")

        expected = google.redirect_uri(GW(), None)
        self.assertIn(("ok", "Google return address", "register exactly this in the Google client: " + expected), preflight.check(GOOD))

    def test_the_company_domain_is_swangzavenue_whether_or_not_google_is_on(self):
        no_google = {k: v for k, v in GOOD.items() if not k.startswith("GOOGLE_")}
        for env in (GOOD, no_google):
            self.assertIn("GATEWAY_COMPANY_DOMAIN", levels(env, "ok"))
            self.assertIn("GATEWAY_COMPANY_DOMAIN", levels({**env, "GATEWAY_COMPANY_DOMAIN": "SwangzAvenue.com"}, "ok"))
            for other in ("gmail.com", "swangzavenue.com.example", "evil-swangzavenue.com", "swangzavenue.co"):
                self.assertIn("GATEWAY_COMPANY_DOMAIN", levels({**env, "GATEWAY_COMPANY_DOMAIN": other}, "fail"), other)

    def test_proxy_and_cookie_settings(self):
        self.assertIn("GATEWAY_TRUST_PROXY", levels({**GOOD, "GATEWAY_TRUST_PROXY": ""}, "fail"))
        self.assertIn("GATEWAY_HOST", levels({**GOOD, "GATEWAY_HOST": "0.0.0.0"}, "warn"))
        tls = {**GOOD, "GATEWAY_TLS_CERT": "/c.pem", "GATEWAY_TLS_KEY": "/k.pem"}
        self.assertIn("GATEWAY_TRUST_PROXY", levels(tls, "warn"))
        self.assertEqual(levels({**tls, "GATEWAY_TRUST_PROXY": ""}, "fail"), [])
        insecure = {**GOOD, "GATEWAY_FORCE_HTTPS": "", "GATEWAY_PUBLIC_URL": ""}
        self.assertIn("secure cookies", levels(insecure, "fail"))

    def test_demo_and_bootstrap_leftovers_and_missing_keys(self):
        self.assertIn("DEMO_MODEL", levels({**GOOD, "DEMO_MODEL": "1"}, "fail"))
        self.assertIn("GATEWAY_BOOTSTRAP_PASSWORD", levels({**GOOD, "GATEWAY_BOOTSTRAP_PASSWORD": "x"}, "warn"))
        self.assertIn("provider keys", levels({**GOOD, "ANTHROPIC_API_KEY": ""}, "warn"))

    def test_no_secret_value_is_ever_printed(self):
        env = {**GOOD, "GATEWAY_BOOTSTRAP_PASSWORD": "boot-pw-never-printed", "OPENAI_API_KEY": "sk-open-never-printed",
               "GOOGLE_REDIRECT_URI": "https://other.example/auth/google/callback", "GATEWAY_TRUST_PROXY": ""}
        lines = []
        self.assertEqual(preflight.run(env, lines.append), 1)
        text = "\n".join(lines)
        for secret in ("s3cret-value-never-printed", "sk-never-printed", "boot-pw-never-printed", "sk-open-never-printed"):
            self.assertNotIn(secret, text)
        self.assertIn("Nothing was contacted and nothing was changed.", lines[-1])

    def test_the_command_exits_by_result_and_creates_no_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = os.path.join(tmp, "data")
            for env, code in ((GOOD, 0), ({**GOOD, "GATEWAY_WEB_URL": ""}, 1)):
                with mock.patch.dict(os.environ, {**env, "GATEWAY_DATA": data, "GATEWAY_ENV_FILE": os.path.join(tmp, "none.env")}, clear=True), \
                        mock.patch("socket.socket", side_effect=AssertionError("no network")), redirect_stdout(io.StringIO()) as out:
                    with self.assertRaises(SystemExit) as stop:
                        main(["preflight"])
                    self.assertEqual(stop.exception.code, code)
                self.assertIn("preflight:", out.getvalue())
            self.assertFalse(os.path.exists(data))


if __name__ == "__main__":
    unittest.main()
