"""Open goes to the app, not a marketing page, where the provider's own site confirms the app address
(Probe's catalogue audit). Old databases move once; an admin's edit, grants and gate hosts are kept."""
import unittest

from gateway import catalog

from .support import Rig


class AppUrlTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.db = self.rig.gw.db

    def tearDown(self):
        self.rig.close()

    def tool(self, tid):
        return self.db.one("SELECT url, info_url, hosts FROM tools WHERE id = ?", (tid,))

    def test_a_fresh_catalogue_opens_the_app_and_keeps_the_product_page(self):
        for tid, (old, new) in catalog.APP_URLS.items():
            row = self.tool(tid)
            self.assertEqual((row["url"], row["info_url"]), (new, old), tid)
            # the app address is governed by the tool's own gate host
            self.assertEqual(catalog.match_host(catalog.host_index(self.db), new.split("/")[2])["id"], tid)
            self.assertEqual(catalog.launch_target(dict(self.db.one("SELECT * FROM tools WHERE id = ?", (tid,)))), new)

    def test_an_old_database_moves_once_and_an_admins_edit_is_kept(self):
        db = self.db
        for tid, (old, _new) in catalog.APP_URLS.items():
            db.x("UPDATE tools SET url = ?, info_url = '' WHERE id = ?", (old, tid))
        db.x("UPDATE tools SET url = 'https://airtable.example/', info_url = '' WHERE id = 'airtable-ai'")  # an admin's edit
        grants = [tuple(r.values()) for r in db.q("SELECT * FROM entitlements ORDER BY 1, 2")]
        hosts = [tuple(r.values()) for r in db.q("SELECT id, hosts FROM tools ORDER BY id")]
        db.set_setting("catalog_app_urls", "0")
        catalog.settle_app_urls(db)
        self.assertEqual(dict(self.tool("photoshop")),
                         {"url": "https://photoshop.adobe.com/", "info_url": "https://www.adobe.com/products/photoshop.html",
                          "hosts": "photoshop.adobe.com"})
        self.assertEqual((self.tool("airtable-ai")["url"], self.tool("airtable-ai")["info_url"]), ("https://airtable.example/", ""))
        self.assertEqual([tuple(r.values()) for r in db.q("SELECT * FROM entitlements ORDER BY 1, 2")], grants)
        self.assertEqual([tuple(r.values()) for r in db.q("SELECT id, hosts FROM tools ORDER BY id")], hosts)
        moved = db.q("SELECT target, correlation, actor FROM audit WHERE action = 'moved a tool''s website to its app'")
        self.assertEqual([(r["target"], r["correlation"], r["actor"]) for r in moved], [("photoshop", "tool:photoshop", "system")])
        db.x("UPDATE tools SET url = 'https://www.adobe.com/products/photoshop.html' WHERE id = 'photoshop'")
        catalog.settle_app_urls(db)  # runs once: a later edit is never touched
        self.assertEqual(self.tool("photoshop")["url"], "https://www.adobe.com/products/photoshop.html")

    def test_an_admins_product_page_is_never_replaced(self):
        db = self.db
        db.x("UPDATE tools SET url = ?, info_url = 'https://example.com/ps' WHERE id = 'photoshop'",
             (catalog.APP_URLS["photoshop"][0],))
        db.set_setting("catalog_app_urls", "0")
        catalog.settle_app_urls(db)
        self.assertEqual(dict(self.tool("photoshop"))["info_url"], "https://example.com/ps")

    def test_a_custom_tool_is_never_touched(self):
        db = self.db
        db.x("UPDATE tools SET url = ?, info_url = '', builtin = 0 WHERE id = 'photoshop'", (catalog.APP_URLS["photoshop"][0],))
        db.set_setting("catalog_app_urls", "0")
        catalog.settle_app_urls(db)
        self.assertEqual(self.tool("photoshop")["url"], catalog.APP_URLS["photoshop"][0])


if __name__ == "__main__":
    unittest.main()
