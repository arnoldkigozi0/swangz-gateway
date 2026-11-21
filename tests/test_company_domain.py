"""The company domain comes from GATEWAY_COMPANY_DOMAIN everywhere: no code path quietly falls back to the built-in
default (staff invites, the console, the hub identity and import tools)."""
import os
import time
import unittest
from unittest import mock

from gateway import hub_identity, security, staff
from gateway.config import COMPANY_DOMAIN

from .support import Rig

BOSS = "boss@example.org"


class CompanyDomainTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.db = self.rig.gw.db
        self.rig.gw.settings.company_domain = "example.org"  # the fixture owners are on the built-in domain
        self.db.x("INSERT INTO admins(username, pw_hash, role, created) VALUES(?,?,?,?)",
                  ("boss@example.org", security.hash_password("boss@example.org-password", 1000), "owner", time.time()))

    def tearDown(self):
        self.rig.close()

    def person(self, email):
        return self.db.x("INSERT INTO people(name, email, created) VALUES(?, ?, ?)", ("P " + email, email, time.time())).lastrowid

    def test_an_invite_follows_the_configured_domain(self):
        ours, built_in = self.person("ann@example.org"), self.person("bob@" + COMPANY_DOMAIN)
        self.assertEqual(self.rig.api("POST", f"/people/{ours}/invite", who=BOSS)[0], 200)
        status, out = self.rig.api("POST", f"/people/{built_in}/invite", who=BOSS)
        self.assertEqual(status, 400, out)

    def test_new_invite_without_settings_reads_the_environment(self):
        pid = self.person("cat@example.org")
        with mock.patch.dict(os.environ, {"GATEWAY_COMPANY_DOMAIN": "example.org"}):
            self.assertTrue(staff.new_invite(self.db, pid))
        with mock.patch.dict(os.environ, {"GATEWAY_COMPANY_DOMAIN": ""}):
            with self.assertRaises(ValueError):
                staff.new_invite(self.db, pid)

    def test_the_console_and_hub_settings_name_the_configured_domain(self):
        self.assertEqual(self.rig.api("GET", "/me", who=BOSS)[1]["company_domain"], "example.org")
        self.assertIn("@example.org", self.rig.api("GET", "/hub/settings", who=BOSS)[1]["identity_policy"])

    def test_hub_identity_preflight_uses_the_configured_domain(self):
        self.person("dan@example.org")
        with mock.patch.dict(os.environ, {"GATEWAY_COMPANY_DOMAIN": "example.org"}):
            out = hub_identity.preflight(self.rig.gw.settings.data_dir + "/gateway.db")
        self.assertIn("@example.org", out["policy"])
        self.assertTrue([p for p in out["staff"] if p["email"] == "dan@example.org"][0]["allowed"])


if __name__ == "__main__":
    unittest.main()
