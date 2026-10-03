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
                              "nonce": q["nonce"], "email": email, "email_verified": True, "name": "Test", **over}
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

    def test_suspended_people_are_refused(self):
        self.rig.gw.db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (self.rig.person_id,))
        q, cookie = self.begin()
        self.assertEqual(self.finish(q, cookie)[0], "/?auth_error=paused")

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

    def test_sign_in_links_use_the_web_address(self):
        status, out = self.rig.api("POST", f"/people/{self.rig.person_id}/invite")
        self.assertTrue(out["link"].startswith("https://swangz-ai.example.test/#/welcome/"))


if __name__ == "__main__":
    unittest.main()
