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
        grants = [tuple(r.values()) for r in db.q("SELECT * FROM entitlements ORDER BY 1, 2")]
        urls = [tuple(r.values()) for r in db.q("SELECT id, url, launch_url FROM tools ORDER BY id")]
        db.set_setting("catalog_host_owners", "0")
        catalog.settle_hosts(db)
        hosts = {r["id"]: r["hosts"] for r in db.q("SELECT id, hosts FROM tools")}
        self.assertEqual(hosts["chatgpt"], "chat.openai.com,chatgpt.com")
        self.assertEqual(hosts["seedance"], "")
        self.assertEqual(hosts["copilot"], "copilot.microsoft.com")
        self.assertEqual(hosts["photoshop"], "adobe.com,photoshop.example.com")
        self.assertEqual([tuple(r.values()) for r in db.q("SELECT * FROM entitlements ORDER BY 1, 2")], grants)
        self.assertEqual([tuple(r.values()) for r in db.q("SELECT id, url, launch_url FROM tools ORDER BY id")], urls)
        moved = {r["target"]: r for r in db.q("SELECT * FROM audit WHERE action = 'moved a tool''s gate hosts'")}
        self.assertEqual(set(moved), {"chatgpt", "seedance", "copilot"})  # the admin-edited Photoshop row is not logged
        self.assertEqual(moved["seedance"]["correlation"], "tool:seedance")
        self.assertIn("higgsfield.ai", moved["seedance"]["before_json"])
        self.assertEqual(moved["seedance"]["actor"], "system")
        db.x("UPDATE tools SET hosts = 'sora.com,chatgpt.com' WHERE id = 'chatgpt'")
        catalog.settle_hosts(db)  # runs once: a later edit is never touched
        self.assertEqual(db.one("SELECT hosts FROM tools WHERE id = 'chatgpt'")["hosts"], "sora.com,chatgpt.com")
        self.assertEqual(db.one("SELECT COUNT(*) AS n FROM audit WHERE action = 'moved a tool''s gate hosts'")["n"], 3)

    def test_a_custom_tool_with_an_old_default_is_never_touched(self):
        db = self.db
        db.x("UPDATE tools SET hosts = 'higgsfield.ai', builtin = 0 WHERE id = 'seedance'")
        db.set_setting("catalog_host_owners", "0")
        catalog.settle_hosts(db)
        self.assertEqual(db.one("SELECT hosts FROM tools WHERE id = 'seedance'")["hosts"], "higgsfield.ai")

    def test_an_admin_cannot_give_one_host_to_two_tools(self):
        api = self.rig.api
        status, out = api("PATCH", "/tools/midjourney", {"hosts": "midjourney.com,chatgpt.com"})
        self.assertEqual(status, 409, out)
        self.assertIn("chatgpt.com", str(out))
        self.assertEqual(self.db.one("SELECT hosts FROM tools WHERE id = 'midjourney'")["hosts"], "midjourney.com")
        self.assertEqual(api("PATCH", "/tools/midjourney", {"hosts": "midjourney.com,alpha.midjourney.com"})[0], 200)
        self.assertEqual(api("PATCH", "/tools/midjourney", {"hosts": "midjourney.com,sora.com"})[0], 409)
        self.db.x("UPDATE tools SET archived = 1 WHERE id = 'sora'")  # an archived tool owns nothing
        self.assertEqual(api("PATCH", "/tools/midjourney", {"hosts": "midjourney.com,sora.com"})[0], 200)

    def test_tools_that_already_share_a_host_stay_editable_and_adding_one_warns(self):
        api = self.rig.api
        status, out = api("POST", "/tools", {"name": "Suno Team", "url": "https://suno.com", "signin": "shared"})
        self.assertEqual(status, 200, out)
        self.assertIn("suno.com (already on Suno)", out["warning"])
        added = self.db.one("SELECT detail FROM audit WHERE action = 'added a tool to the catalog' ORDER BY id DESC LIMIT 1")
        self.assertIn("suno.com", added["detail"])
        for tid in ("suno", out["id"]):  # the console sends hosts on every save
            self.assertEqual(api("PATCH", f"/tools/{tid}", {"hosts": "suno.com", "description": "edited"})[0], 200, tid)
        self.assertEqual(api("PATCH", "/tools/suno", {"hosts": "suno.com,chatgpt.com"})[0], 409)
        self.assertEqual(api("PATCH", "/tools/suno", {"hosts": ""})[0], 200)  # dropping a host is always allowed
        self.assertNotIn("warning", api("POST", "/tools", {"name": "Home grown", "url": "https://example.test/"})[1])


if __name__ == "__main__":
    unittest.main()
