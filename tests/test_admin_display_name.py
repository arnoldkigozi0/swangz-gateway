import json
import time
import unittest

from .support import Rig

OWNER = "owner@swangzavenue.com"


class AdminDisplayNameTests(unittest.TestCase):
    """GET /admin/api/me carries display_name: the name on the one person whose email is the console username."""

    def setUp(self):
        self.rig = Rig()
        self.db = self.rig.gw.db
        self.cookie = self.rig.login()

    def tearDown(self):
        self.rig.close()

    def me(self):
        status, _, payload = self.rig.request("GET", "/admin/api/me", headers={"cookie": self.cookie})
        self.assertEqual(status, 200)
        return json.loads(payload)

    def person(self, name, email):
        return self.db.x("INSERT INTO people(name, email, department, created) VALUES(?,?,?,?)", (name, email, "Ops", time.time())).lastrowid

    def test_no_matching_person_is_null_and_never_the_username_or_role(self):
        me = self.me()
        self.assertIn("display_name", me)
        self.assertIsNone(me["display_name"])
        self.assertEqual(me["username"], OWNER)  # the rest of the answer is unchanged

    def test_matching_person_gives_their_recorded_name(self):
        self.person("  Kato  Brian ", "Owner@SwangzAvenue.com")  # case-insensitive match, name trimmed at the ends only
        self.assertEqual(self.me()["display_name"], "Kato  Brian")

    def test_another_persons_name_is_never_used(self):
        self.assertEqual(self.db.scalar("SELECT name FROM people WHERE id = ?", (self.rig.person_id,)), "Nansubuga Grace")
        self.person("Someone Else", "owner@swangzavenue.com.example")
        self.person("Prefix Match", "the-owner@swangzavenue.com")
        self.assertIsNone(self.me()["display_name"])

    def test_blank_name_is_null(self):
        self.person("   ", OWNER)
        self.assertIsNone(self.me()["display_name"])

    def test_duplicate_emails_are_null_not_a_guess(self):
        self.person("Kato Brian", OWNER)
        self.person("Kato Brenda", OWNER.upper())
        self.assertIsNone(self.me()["display_name"])

    def test_people_without_an_email_never_match(self):
        self.person("No Email", "")
        self.person("Blank Email", "   ")
        self.assertIsNone(self.me()["display_name"])
        self.person("Kato Brian", f"  {OWNER} ")  # stray spaces around a stored email still identify the one person
        self.assertEqual(self.me()["display_name"], "Kato Brian")

    def test_signed_out_gets_nothing(self):
        status, _, payload = self.rig.request("GET", "/admin/api/me")
        self.assertEqual(status, 401)
        self.assertNotIn("display_name", payload if isinstance(payload, str) else payload.decode())


if __name__ == "__main__":
    unittest.main()
