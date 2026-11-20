"""One owner per gate host: no host is claimed by two built-in tools, and old databases are settled without
touching an admin's edit (Probe's catalogue audit, defects 1 and 2)."""
import unittest

from gateway import admin, catalog

from .support import Rig


class GateHostOwnerTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.db = self.rig.gw.db

    def tearDown(self):
        self.rig.close()

    def test_no_built_in_host_has_two_owners_and_every_one_is_a_hostname(self):
        owner = {}
        for row in catalog.SEED:
            tid, hosts = row[0], row[6]
            self.assertEqual(admin._clean_hosts(hosts), list(hosts), tid)  # no paths, schemes or www.
            for h in hosts:
                self.assertNotIn(h, owner, f"{h} is on {owner.get(h)} and {tid}")
                owner[h] = tid

    def test_each_shared_host_now_resolves_to_its_owner(self):
        index = catalog.host_index(self.db)
        for host, tid in (("sora.com", "sora"), ("chatgpt.com", "chatgpt"), ("chat.openai.com", "chatgpt"),
                          ("photoshop.adobe.com", "photoshop"), ("adobe.com", "adobe-premiere"),
                          ("www.adobe.com", "adobe-premiere"), ("firefly.adobe.com", "adobe-firefly"),
                          ("higgsfield.ai", "higgsfield-ai"), ("copilot.microsoft.com", "copilot")):
            self.assertEqual(catalog.match_host(index, host)["id"], tid, host)
        self.assertIsNone(catalog.match_host(index, "github.com"))  # never gated as Copilot, before or now

    def test_an_old_database_is_settled_once_and_an_admins_edit_is_kept(self):
        db = self.db
        for tid, (old, _new) in catalog.HOST_OWNERS.items():
            db.x("UPDATE tools SET hosts = ? WHERE id = ?", (old, tid))
        db.x("UPDATE tools SET hosts = 'adobe.com,photoshop.example.com' WHERE id = 'photoshop'")  # an admin's edit
        grants = [tuple(r) for r in db.q("SELECT * FROM entitlements ORDER BY 1, 2")]
        urls = [tuple(r) for r in db.q("SELECT id, url, launch_url FROM tools ORDER BY id")]
        db.set_setting("catalog_host_owners", "0")
        catalog.settle_hosts(db)
        hosts = {r["id"]: r["hosts"] for r in db.q("SELECT id, hosts FROM tools")}
        self.assertEqual(hosts["chatgpt"], "chat.openai.com,chatgpt.com")
        self.assertEqual(hosts["seedance"], "")
        self.assertEqual(hosts["copilot"], "copilot.microsoft.com")
        self.assertEqual(hosts["photoshop"], "adobe.com,photoshop.example.com")
        self.assertEqual([tuple(r) for r in db.q("SELECT * FROM entitlements ORDER BY 1, 2")], grants)
        self.assertEqual([tuple(r) for r in db.q("SELECT id, url, launch_url FROM tools ORDER BY id")], urls)
        db.x("UPDATE tools SET hosts = 'sora.com,chatgpt.com' WHERE id = 'chatgpt'")
        catalog.settle_hosts(db)  # runs once: a later edit is never touched
        self.assertEqual(db.one("SELECT hosts FROM tools WHERE id = 'chatgpt'")["hosts"], "sora.com,chatgpt.com")

    def test_a_custom_tool_with_an_old_default_is_never_touched(self):
        db = self.db
        db.x("UPDATE tools SET hosts = 'higgsfield.ai', builtin = 0 WHERE id = 'seedance'")
        db.set_setting("catalog_host_owners", "0")
        catalog.settle_hosts(db)
        self.assertEqual(db.one("SELECT hosts FROM tools WHERE id = 'seedance'")["hosts"], "higgsfield.ai")


if __name__ == "__main__":
    unittest.main()
