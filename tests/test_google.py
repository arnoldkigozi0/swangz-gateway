"""Sign in with Google: the whole round trip against a stand-in for Google's token endpoint."""

import base64
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from gateway import security

from .support import Rig

CLIENT = "123-test.apps.googleusercontent.com"


def jwt(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256', 'typ': 'JWT'})}.{enc(claims)}.c2lnbmF0dXJl"


class FakeGoogle:
    """Answers the token exchange with whatever ID token claims the test sets."""

    def __init__(self):
        self.claims = {}
        self.posted = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("content-length") or 0)).decode()
                fake.posted.append({k: v[-1] for k, v in parse_qs(body).items()})
                data = json.dumps({"access_token": "x", "id_token": jwt(fake.claims), "token_type": "Bearer"}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/token"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class GoogleSignInTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.google = FakeGoogle()
        s = self.rig.settings
        s.google_client_id, s.google_client_secret, s.google_token_url = CLIENT, "secret-xyz", self.google.url
        s.web_url = "https://swangz-ai.example.test"
        db = self.rig.gw.db
        db.x("UPDATE people SET email = 'grace@swangzavenue.com' WHERE id = ?", (self.rig.person_id,))
        db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
             ("arnoldkigozi0@gmail.com", security.hash_password("x" * 12, 1000), "owner", time.time()))

    def tearDown(self):
        self.google.close()
        self.rig.close()

    def begin(self, app="staff"):
        status, h, _ = self.rig.request("GET", f"/auth/google/start?app={app}")
        self.assertEqual(status, 302)
        loc = urlsplit(h["location"])
        q = {k: v[-1] for k, v in parse_qs(loc.query).items()}
        cookie = h["set-cookie"].split(";")[0]
        return q, cookie

    def finish(self, q, cookie, email="grace@swangzavenue.com", **over):
        self.google.claims = {"iss": "https://accounts.google.com", "aud": CLIENT, "exp": time.time() + 600,
                              "nonce": q["nonce"], "email": email, "email_verified": True, "name": "Test", "hd": "swangzavenue.com", **over}
        for k in [k for k, v in over.items() if v is None]:
            del self.google.claims[k]  # a test passes hd=None to send a token with no hd claim at all
        status, h, _ = self.rig.request("GET", f"/auth/google/callback?state={q['state']}&code=one-time-code", None, {"cookie": cookie})
        self.assertEqual(status, 302)
        cookies = h.get("set-cookie", "")
        return h["location"], cookies

    def test_the_button_only_shows_when_configured(self):
        self.assertEqual(json.loads(self.rig.request("GET", "/auth/options")[2]), {"google": True})
        self.rig.settings.google_client_secret = ""
        self.assertEqual(json.loads(self.rig.request("GET", "/auth/options")[2]), {"google": False})
        status, h, _ = self.rig.request("GET", "/auth/google/start?app=staff")
        self.assertEqual((status, h["location"]), (302, "/?auth_error=off"))

    def test_start_sends_people_to_google_with_our_return_address(self):
        q, cookie = self.begin()
        self.assertEqual(q["client_id"], CLIENT)
        self.assertEqual(q["redirect_uri"], "https://swangz-ai.example.test/auth/google/callback")
        self.assertEqual(q["scope"], "openid email profile")
        self.assertTrue(q["state"] and q["nonce"])
        self.assertEqual(cookie, "sgw_oauth=" + q["state"])

    def test_staff_round_trip(self):
        q, cookie = self.begin()
        where, cookies = self.finish(q, cookie)
        self.assertEqual(where, "/")
        session = next(c.split(";")[0] for c in cookies.split(", ") if c.startswith("sgw_staff="))
        # the code was swapped with our secret and the same return address
        sent = self.google.posted[-1]
        self.assertEqual((sent["code"], sent["client_secret"], sent["grant_type"]), ("one-time-code", "secret-xyz", "authorization_code"))
        self.assertEqual(sent["redirect_uri"], q["redirect_uri"])
        status, _, body = self.rig.request("GET", "/api/me", None, {"cookie": session})
        self.assertEqual((status, json.loads(body)["email"]), (200, "grace@swangzavenue.com"))
        self.assertTrue(self.rig.gw.db.one("SELECT 1 FROM audit WHERE action = 'signed in with Google'"))

    def test_admin_round_trip(self):
        q, cookie = self.begin("admin")
        where, cookies = self.finish(q, cookie, email="ArnoldKigozi0@gmail.com")
        self.assertEqual(where, "/admin")
        session = next(c.split(";")[0] for c in cookies.split(", ") if c.startswith("sgw_admin="))
        status, _, body = self.rig.request("GET", "/admin/api/me", None, {"cookie": session})
        self.assertEqual((status, json.loads(body)["role"]), (200, "owner"))

    def test_admin_needs_a_console_user_with_that_email(self):
        q, cookie = self.begin("admin")
        self.assertEqual(self.finish(q, cookie, email="grace@swangzavenue.com")[0], "/admin?auth_error=no_account")

    def test_refusals(self):
        cases = [
            ({"email": "someone@gmail.com"}, "/?auth_error=not_allowed"),           # not a Swangz email
            ({"email": "nobody@swangzavenue.com"}, "/?auth_error=no_account"),      # no account here
            ({"email_verified": False}, "/?auth_error=google"),                     # Google hasn't verified it
            ({"aud": "someone-elses-client"}, "/?auth_error=google"),                # a token meant for another app
            ({"iss": "https://evil.example"}, "/?auth_error=google"),
            ({"exp": time.time() - 5}, "/?auth_error=google"),
            ({"nonce": "replayed"}, "/?auth_error=google"),
        ]
        for over, expected in cases:
            q, cookie = self.begin()
            where, cookies = self.finish(q, cookie, **{k: v for k, v in over.items() if k == "email"},
                                         **{k: v for k, v in over.items() if k != "email"})
            self.assertEqual(where, expected, over)
            self.assertNotIn("sgw_staff=", cookies.replace("sgw_staff=;", ""))

    def test_a_suspended_or_ended_person_gets_the_read_only_paused_view_and_an_unapproved_email_is_refused(self):
        self.rig.gw.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (self.rig.person_id,))
        q, cookie = self.begin()
        where, cookies = self.finish(q, cookie)
        self.assertEqual(where, "/")
        session = next(c.split(";")[0] for c in cookies.split(", ") if c.startswith("sgw_staff="))
        status, _, body = self.rig.request("GET", "/api/me", None, {"cookie": session})
        self.assertEqual((status, json.loads(body)["paused_view"]), (200, True))
        self.assertEqual(self.rig.request("GET", "/api/studio", None, {"cookie": session})[0], 403)
        self.assertTrue(self.rig.gw.db.one("SELECT 1 FROM audit WHERE action = 'signed in with Google (access paused: read-only view)'"))
        self.rig.gw.db.x("UPDATE people SET status = 'active', access_until = ? WHERE id = ?", (time.time() - 5, self.rig.person_id))
        q, cookie = self.begin()  # ended access: the same read-only view
        where, cookies = self.finish(q, cookie)
        self.assertEqual(where, "/")
        session = next(c.split(";")[0] for c in cookies.split(", ") if c.startswith("sgw_staff="))
        status, _, body = self.rig.request("GET", "/api/me", None, {"cookie": session})
        self.assertEqual((status, json.loads(body)["paused_view"]), (200, True))
        self.rig.gw.db.x("UPDATE people SET email = 'grace@gmail.com' WHERE id = ?", (self.rig.person_id,))
        q, cookie = self.begin()  # an address outside the approved accounts is still refused
        self.assertEqual(self.finish(q, cookie, email="grace@gmail.com")[0], "/?auth_error=not_allowed")

    def test_the_company_account_check_uses_the_hd_claim_in_the_id_token(self):
        cases = [  # (email, hd claim or None, where it should land for the staff app)
            ("grace@swangzavenue.com", "swangzavenue.com", "/"),                     # right hd
            ("grace@swangzavenue.com", None, "/?auth_error=not_allowed"),             # no hd claim
            ("grace@swangzavenue.com", "evil.example", "/?auth_error=not_allowed"),   # wrong hd
            ("grace@swangzavenue.com", "SwangzAvenue.com", "/"),                      # hd is compared without case
            ("grace@swangzavenue.com.evil.example", "swangzavenue.com", "/?auth_error=not_allowed"),  # right hd, wrong suffix
            ("grace@evil.swangzavenue.com", "swangzavenue.com", "/?auth_error=not_allowed"),
            ("someone@gmail.com", None, "/?auth_error=not_allowed"),                  # an hd-less Gmail
            ("someone@gmail.com", "swangzavenue.com", "/?auth_error=not_allowed"),
        ]
        for email, hd, expected in cases:  # refusals come before any account lookup, so only grace needs an account
            q, cookie = self.begin()
            where, cookies = self.finish(q, cookie, email=email, hd=hd)
            self.assertEqual(where, expected, (email, hd))
            if expected != "/":
                self.assertNotIn("sgw_staff=", cookies.replace("sgw_staff=;", ""))

    def test_the_url_hint_is_never_trusted(self):
        q, cookie = self.begin()
        self.assertNotIn("hd", q)  # we send no hd hint; and the callback only ever reads the token's claim
        where, _ = self.finish(q, cookie, hd=None)
        self.assertEqual(where, "/?auth_error=not_allowed")
        q, cookie = self.begin()
        status, h, _ = self.rig.request("GET", f"/auth/google/callback?state={q['state']}&code=c&hd=swangzavenue.com",
                                        None, {"cookie": cookie})
        self.assertEqual(status, 302)  # the hint in the address changes nothing

    def test_the_two_owner_exceptions_need_only_a_verified_exact_match_and_no_hd(self):
        db = self.rig.gw.db
        for email in ("arnoldkigozi0@gmail.com", "marvinmusokessekatawa@gmail.com", "ArnoldKigozi0@Gmail.com"):
            q, cookie = self.begin("admin")
            if email.lower() == "marvinmusokessekatawa@gmail.com":
                db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
                     (email, security.hash_password("x" * 12, 1000), "viewer", time.time()))
            where, cookies = self.finish(q, cookie, email=email, hd=None)
            self.assertEqual(where, "/admin", email)
            self.assertIn("sgw_admin=", cookies)
        q, cookie = self.begin("admin")  # unverified: refused even for an exception
        self.assertEqual(self.finish(q, cookie, email="arnoldkigozi0@gmail.com", hd=None, email_verified=False)[0], "/admin?auth_error=google")
        for lookalike in ("arnoldkigozi0+x@gmail.com", "arnold.kigozi0@gmail.com", "arnoldkigozi0@gmail.com.evil.example"):
            q, cookie = self.begin("admin")
            self.assertEqual(self.finish(q, cookie, email=lookalike, hd=None)[0], "/admin?auth_error=not_allowed", lookalike)

    def test_a_refusal_is_audited_without_a_token(self):
        q, cookie = self.begin()
        self.finish(q, cookie, email="grace@swangzavenue.com", hd="evil.example")
        row = self.rig.gw.db.one("SELECT * FROM audit WHERE action = 'Google sign-in refused'")
        self.assertEqual(row["detail"], "not a company Google account")
        dump = json.dumps(self.rig.gw.db.q("SELECT * FROM audit"), default=str)
        for secret in ("one-time-code", "secret-xyz", self.google.claims["nonce"]):
            self.assertNotIn(secret, dump)

    def test_the_domain_is_one_environment_value_with_an_unchanged_default(self):
        from gateway.config import Settings
        self.assertEqual(Settings().company_domain, "swangzavenue.com")
        self.assertEqual(Settings.from_env({"GATEWAY_COMPANY_DOMAIN": "Example.org"}).company_domain, "example.org")
        with self.assertRaises(ValueError):
            Settings.from_env({"GATEWAY_COMPANY_DOMAIN": "bad domain/x"})

    def test_state_must_match_this_browser_and_is_single_use(self):
        q, cookie = self.begin()
        self.google.claims = {}
        status, h, _ = self.rig.request("GET", f"/auth/google/callback?state={q['state']}&code=c", None, {"cookie": "sgw_oauth=other"})
        self.assertEqual(h["location"], "/?auth_error=expired")
        # the state was used up by that attempt
        self.assertEqual(self.finish(q, cookie)[0], "/?auth_error=expired")
        status, h, _ = self.rig.request("GET", "/auth/google/callback?state=made-up&code=c", None, {"cookie": "sgw_oauth=made-up"})
        self.assertEqual(h["location"], "/?auth_error=expired")
        self.assertEqual(len(self.google.posted), 0)  # nothing was ever sent to Google

    def test_cancelling_at_google(self):
        q, cookie = self.begin()
        status, h, _ = self.rig.request("GET", f"/auth/google/callback?state={q['state']}&error=access_denied", None, {"cookie": cookie})
        self.assertEqual(h["location"], "/?auth_error=cancelled")

    def test_the_return_address_is_the_first_party_address_whatever_host_the_request_names(self):
        """GATEWAY_WEB_URL fixes the return address at the start and again at the code exchange (Google
        compares the two), and the browser is sent back to a path on the same site."""
        hostile = {"host": "evil.example.test", "x-forwarded-host": "evil.example.test", "x-forwarded-proto": "http"}
        self.rig.gw.trust_proxy = True
        status, h, _ = self.rig.request("GET", "/auth/google/start?app=staff", None, hostile)
        self.assertEqual(status, 302)
        q = {k: v[-1] for k, v in parse_qs(urlsplit(h["location"]).query).items()}
        self.assertEqual(q["redirect_uri"], "https://swangz-ai.example.test/auth/google/callback")
        cookie = h["set-cookie"].split(";")[0]
        self.google.claims = {"iss": "https://accounts.google.com", "aud": CLIENT, "exp": time.time() + 600, "nonce": q["nonce"],
                              "email": "grace@swangzavenue.com", "email_verified": True, "hd": "swangzavenue.com"}
        status, h, _ = self.rig.request("GET", f"/auth/google/callback?state={q['state']}&code=one-time-code", None, {**hostile, "cookie": cookie})
        self.assertEqual((status, h["location"]), (302, "/"))
        self.assertEqual(self.google.posted[-1]["redirect_uri"], "https://swangz-ai.example.test/auth/google/callback")
        self.assertNotIn("evil", json.dumps(self.google.posted))

    def test_with_a_fixed_return_required_and_none_set_a_hostile_host_gets_no_redirect_to_google(self):
        """D-017. GATEWAY_REQUIRE_FIXED_RETURN: with no address in the settings the return address would be built from
        the request's Host header, so sign-in is refused instead and the button is hidden."""
        s = self.rig.settings
        s.web_url = s.public_url = s.google_redirect_uri = ""
        hostile = {"host": "evil.example.test", "x-forwarded-host": "evil.example.test", "x-forwarded-proto": "https"}
        self.rig.gw.trust_proxy = True
        status, h, _ = self.rig.request("GET", "/auth/google/start?app=admin", None, hostile)
        self.assertIn("evil.example.test", h["location"])  # the gap: off by default, the Host header reaches Google
        self.assertEqual(json.loads(self.rig.request("GET", "/auth/options")[2]), {"google": True})

        s.require_fixed_return = True
        status, h, _ = self.rig.request("GET", "/auth/google/start?app=admin", None, hostile)
        self.assertEqual((status, h["location"]), (302, "/admin?auth_error=off"))
        self.assertNotIn("accounts.google.com", h["location"])
        self.assertEqual(json.loads(self.rig.request("GET", "/auth/options", None, hostile)[2]), {"google": False})

    def test_with_a_fixed_return_required_and_an_address_set_the_flow_is_unchanged(self):
        s = self.rig.settings
        s.require_fixed_return = True
        for name, value, expected in (("web_url", "https://swangz-ai.example.test", "https://swangz-ai.example.test"),
                                      ("public_url", "https://gw.example.test", "https://gw.example.test"),
                                      ("google_redirect_uri", "https://hub.example.test/auth/google/callback", "https://hub.example.test")):
            s.web_url = s.public_url = s.google_redirect_uri = ""
            setattr(s, name, value)
            self.assertEqual(json.loads(self.rig.request("GET", "/auth/options")[2]), {"google": True}, name)
            status, h, _ = self.rig.request("GET", "/auth/google/start?app=staff", None, {"host": "evil.example.test"})
            q = {k: v[-1] for k, v in parse_qs(urlsplit(h["location"]).query).items()}
            self.assertEqual(q["redirect_uri"], expected + "/auth/google/callback", name)
        s.public_url = s.google_redirect_uri = ""
        s.web_url = "https://swangz-ai.example.test"
        location, cookies = self.finish(*self.begin())
        self.assertEqual(location, "/")
        self.assertIn("HttpOnly", cookies)

    def test_an_explicit_redirect_uri_wins_at_both_steps(self):
        self.rig.settings.google_redirect_uri = "https://hub.example.test/auth/google/callback"
        q, cookie = self.begin()
        self.assertEqual(q["redirect_uri"], "https://hub.example.test/auth/google/callback")
        self.finish(q, cookie)
        self.assertEqual(self.google.posted[-1]["redirect_uri"], "https://hub.example.test/auth/google/callback")

    def test_sign_in_links_use_the_web_address(self):
        status, out = self.rig.api("POST", f"/people/{self.rig.person_id}/invite")
        self.assertTrue(out["link"].startswith("https://swangz-ai.example.test/#/welcome/"))


if __name__ == "__main__":
    unittest.main()
