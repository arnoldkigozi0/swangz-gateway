"""The files a phone needs to install the staff app are present and well-formed (no browser; a real phone is still
needed for the checklist in docs/MOBILE-READINESS.md)."""
import json
import os
import re
import unittest

STATIC = os.path.join(os.path.dirname(__file__), "..", "gateway", "static")


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


class PwaFileTests(unittest.TestCase):
    def test_the_manifest_can_be_installed_from_the_root(self):
        m = json.loads(read("hub.webmanifest"))
        self.assertEqual((m["id"], m["start_url"], m["scope"], m["display"]), ("/", "/", "/", "standalone"))
        self.assertTrue(m["name"] and m["short_name"] and len(m["short_name"]) <= 12)
        for colour in (m["background_color"], m["theme_color"]):
            self.assertRegex(colour, r"^#[0-9a-fA-F]{6}$")
        self.assertTrue(m["icons"])
        for icon in m["icons"]:
            self.assertTrue(icon["src"].startswith("/static/"), icon)
            self.assertTrue(os.path.isfile(os.path.join(STATIC, icon["src"][len("/static/"):])), icon)

    def test_the_staff_page_links_the_manifest(self):
        self.assertRegex(read("index.html"), r'<link rel="manifest" href="/static/hub\.webmanifest">')

    def test_the_worker_keeps_nothing_offline(self):
        worker = re.sub(r"/\*.*?\*/|//[^\n]*", "", read("hub-worker.js"), flags=re.S)
        self.assertIn("'install'", worker)
        self.assertIn("'activate'", worker)
        for forbidden in ("'fetch'", '"fetch"', "caches.", "indexedDB"):
            self.assertNotIn(forbidden, worker)


if __name__ == "__main__":
    unittest.main()
