"""The macOS RC build (packaging/macos_dmg.py, .github/workflows/build-macos.yml): labelled unsigned, checksummed,
pinned, and never bypassing Gatekeeper. The build itself runs on macos-latest; these checks run anywhere."""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("t_" + name, ROOT / "packaging" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MacBuildTests(unittest.TestCase):
    def setUp(self):
        self.m = load("macos_dmg")

    def test_every_name_says_rc_unsigned(self):
        self.assertEqual(self.m.dmg_name("0.1.0", "arm64"), "Swangz-0.1.0-RC-UNSIGNED-macos-arm64.dmg")
        self.assertIn("RC UNSIGNED", self.m.volume_name("0.1.0"))
        self.assertEqual(self.m.LABEL, "RC — UNSIGNED — INTERNAL TEST ONLY")
        self.assertIn(self.m.LABEL, self.m.README)
        self.assertIn(self.m.LABEL, self.m.plist_values("0.1.0")["NSHumanReadableCopyright"])

    def test_the_bundle_carries_the_app_version_and_identifier(self):
        v = self.m.plist_values("1.2.3")
        self.assertEqual((v["CFBundleShortVersionString"], v["CFBundleVersion"], v["CFBundleIdentifier"]),
                         ("1.2.3", "1.2.3", "com.swangzavenue.swangz"))
        self.assertEqual(self.m.app_version(), load("macos_dmg").app_version())

    def test_steps_sign_ad_hoc_only_and_never_touch_gatekeeper(self):
        commands, dmg = self.m.steps(Path("/d"), Path("/w"), "0.1.0", "arm64")
        flat = [" ".join(c) for c in commands]
        sign = [c for c in commands if c[0] == "codesign" and "--sign" in c]
        self.assertEqual(len(sign), 1)
        self.assertEqual(sign[0][sign[0].index("--sign") + 1], "-")  # ad hoc: identifies nobody
        for bad in ("xattr", "quarantine", "spctl", "master-disable", "--no-strict"):
            self.assertFalse([c for c in flat if bad in c], bad)
        self.assertTrue(any(c.startswith("hdiutil create") for c in flat))
        self.assertTrue(any(c.startswith("hdiutil verify") for c in flat))
        self.assertEqual(dmg.name, "Swangz-0.1.0-RC-UNSIGNED-macos-arm64.dmg")

    def test_workflow_pins_its_tools_and_keeps_evidence(self):
        wf = (ROOT / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: macos-latest", wf)
        self.assertRegex(wf, r"PYINSTALLER_VERSION: '\d+\.\d+\.\d+'")
        self.assertIn('--require-hashes --only-binary :all: -r packaging/requirements-macos-build.txt', wf)
        version = re.search(r"PYINSTALLER_VERSION: '([\d.]+)'", wf).group(1)
        reqs = (ROOT / "packaging" / "requirements-macos-build.txt").read_text()
        pins = re.findall(r"^([a-z0-9-]+)==(\S+) \\\n\s+--hash=sha256:[0-9a-f]{64}$", reqs, re.M)
        self.assertIn(("pyinstaller", version), pins)  # the workflow's version and the hashed pin agree
        self.assertEqual(len(pins), len(re.findall(r"^[a-z0-9-]+==", reqs, re.M)))  # every pin carries a hash
        self.assertNotIn("brew install", wf)  # no unpinned DMG tools
        self.assertIn("shasum -a 256 -c", wf)
        self.assertIn("macos_journey.py", wf)
        self.assertIn("evidence/", wf)
        self.assertNotIn("secrets.", wf)  # signing is not wired until Arnold provides the account
        for bad in ("xattr", "master-disable", "spctl --add"):
            self.assertNotIn(bad, wf)

    def test_journey_expects_gatekeeper_to_refuse_and_checks_the_uninstall(self):
        text = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        self.assertIn('"spctl", "--assess"', text)
        self.assertIn("code != 0", text)
        for step in ("upgraded in place", "server shows the device disconnected", "no Swangz item left in the login keychain",
                     "app removed from Applications", "after restart"):
            self.assertIn(step, text)
        self.assertNotIn("xattr", text)

    def test_journey_cuts_the_hub_and_reconnects_on_the_same_address(self):
        text = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        # the app signs in through the relay, never straight to the fixture server
        self.assertIn('"login", "--server", app_url', text)
        self.assertNotIn('"login", "--server", url', text)
        cut = text.split("relay.stop()", 1)[1].split("relay.start()", 1)[0]
        for needle in ("Hub unreachable: sync fails", "code != 0", "no sync is claimed", 'device.json").is_file()'):
            self.assertIn(needle, cut)
        back = text.split("relay.start()", 2)[2].split("# keep", 1)[0]
        for needle in ("Hub back: the next sync succeeds with no new sign-in", 'not device.get("reconnect")',
                       "the server records the device's check-in"):
            self.assertIn(needle, back)
        self.assertLess(text.index("after restart: still signed in"), text.index("Hub unreachable"))
        self.assertLess(text.index("Hub back: the server records"), text.index("install(j, args.new, apps"))

        from importlib.util import module_from_spec, spec_from_file_location
        spec = spec_from_file_location("macos_journey", ROOT / "packaging" / "macos_journey.py")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module.relay_class(), "stop"))  # the Windows relay loads on any OS (no winreg at import)

    def test_the_signing_doc_lists_what_only_arnold_can_provide(self):
        doc = (ROOT / "docs" / "MACOS-SIGNING.md").read_text(encoding="utf-8")
        for item in ("Apple Developer Program", "Developer ID Application", "notarytool", "stapler staple",
                     "D-U-N-S", "physical-Mac acceptance", "RC — UNSIGNED — INTERNAL TEST ONLY", "MACOS_TEAM_ID"):
            self.assertIn(item, doc)
        self.assertIn("No `xattr -d com.apple.quarantine`", doc)


if __name__ == "__main__":
    unittest.main()


class MacSummaryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.m = load("macos_summary")
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "dist").mkdir()
        (self.dir / "ev").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir)

    def render(self):
        return self.m.render(self.dir / "dist", self.dir / "ev", "6.22.3", env={"GITHUB_SHA": "abc"}, macos="15.0")

    def test_summary_is_labelled_and_carries_the_checksums_and_steps(self):
        (self.dir / "dist" / "SHA256SUMS").write_text("ff  Swangz-0.1.3-RC-UNSIGNED-macos-arm64.dmg\n")
        (self.dir / "ev" / "journey.json").write_text(json.dumps([{"step": "a", "result": "pass", "detail": "x|y"}]))
        text = self.render()
        self.assertIn("RC — UNSIGNED — INTERNAL TEST ONLY", text)
        self.assertIn("Not production-ready", text)
        self.assertIn("ff  Swangz-0.1.3-RC-UNSIGNED-macos-arm64.dmg", text)
        self.assertIn("passed, 1 steps", text)
        self.assertIn("| pass | a | x/y |", text)

    def test_a_failure_or_missing_build_is_said_plainly(self):
        (self.dir / "ev" / "journey.json").write_text(json.dumps([{"step": "a", "result": "pass"}, {"step": "b", "result": "FAIL"}]))
        text = self.render()
        self.assertIn("FAILED at: b", text)
        self.assertIn("no SHA256SUMS (build failed)", text)
        (self.dir / "ev" / "journey.json").unlink()
        self.assertIn("no journey ran", self.render())

    def test_workflow_builds_main_and_publishes_the_summary(self):
        wf = (ROOT / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [main]", wf)
        self.assertIn("macos_summary.py", wf)
        self.assertIn("GITHUB_STEP_SUMMARY", wf)
        self.assertNotIn("release create", wf)  # building an artifact is not publishing a release


class JourneyGapTests(unittest.TestCase):
    """PR #269's macOS gaps: the fresh-install address rule (row 4), Hub down at app start and revoked while away
    (row 7), the reconnect check comparing the key and counting sign-in codes, and the older build refused (row 9)."""

    def setUp(self):
        self.text = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        self.main = self.text.split("def main(", 1)[1]

    def test_a_fresh_install_has_no_address_and_refuses_plain_http_before_any_code(self):
        fresh = self.text.split("def fresh_install(", 1)[1].split("def main(", 1)[0]
        for needle in ('"status"', "code == 2", 'check.get("window") == "signin"', 'check.get("hub_address") == ""',
                       '"http://hub.example.com"', '"http://192.0.2.10:8787"', "only connects over https",
                       "sign_in_codes(db) == before", "shutil.rmtree(apps)"):
            self.assertIn(needle, fresh)
        self.assertLess(self.main.index("fresh_install(j, args.new"), self.main.index("install(j, args.old, apps)"))
        self.assertIn('"SWANGZ_SERVER", "SWANGZ_ALLOW_HTTP"', self.main)  # nothing in the runner's env supplies one
        app = (ROOT / "packaging" / "swangz_app.py").read_text(encoding="utf-8")
        self.assertIn('"hub_address": app.server_var.get() if app.page == "signin" else None', app)
        self.assertIn('"data": rig.tmp', (ROOT / "tests" / "browser" / "demo.py").read_text(encoding="utf-8"))

    def test_the_outage_opens_the_window_and_compares_the_key_and_the_codes(self):
        cut = self.main.split("relay.stop()", 1)[1].split("relay.start()", 1)[0]
        self.assertIn("Hub down at app start: the window still opens", cut)
        self.assertIn("Couldn't reach", cut)
        back = self.main.split("relay.start()", 2)[2].split("keep = sorted", 1)[0]
        for needle in ("after == secret", 'device.get("key_id") == key_id', "sign_in_codes(db) == codes",
                       "files_holding(secret, [data, j.evidence]"):
            self.assertIn(needle, back)
        # the key itself is never written: only a 12-character SHA-256 prefix is
        self.assertNotIn("j.note(secret", self.text)
        self.assertNotIn("{secret}", self.text)

    def test_a_real_hub_process_restart_on_the_same_address_and_data(self):
        restart = self.main.split("# a real Hub process restart", 1)[1].split("# deliverable 5", 1)[0]
        steps = ["stop_server(server)", "server.returncode is not None", "Couldn't reach",
                 'start_server(app_url, hub_log, data=fixture["data"], port=fixture["port"])', "server.pid != old_pid",
                 'not device.get("reconnect")', "after == secret", "sign_in_codes(db) == codes", "now != used"]
        at = [restart.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the restart steps are out of order")
        self.assertNotIn("relay.stop()", restart)  # the process stops, not the relay
        self.assertIn('"HUB_FIXTURE_KEEP": "1"', self.text)
        self.assertIn('shutil.rmtree(fixture["data"]', self.main.split("finally:")[-1])

    def test_the_hub_address_survives_the_upgrade_as_its_own_step(self):
        upgrade = self.main.split("keep = sorted", 1)[1].split("# 5b (row 9)", 1)[0]
        self.assertLess(upgrade.index('.get("server")'), upgrade.index("install(j, args.new, apps, args.new_app)"))
        self.assertIn("after upgrade: the Hub address is unchanged", upgrade)
        self.assertIn("address == moved == app_url and code == 0", upgrade)

    def test_the_older_build_over_the_newer_refuses_and_changes_nothing(self):
        older = self.main.split("# 5b (row 9)", 1)[1].split("sign out", 1)[0]
        for needle in ("install(j, args.old, apps)", '("status", "sync")', "code == 5",
                       'f"Swangz {args.new_version} is already in use"', "kept == device",
                       "install(j, args.new, apps)"):
            self.assertIn(needle, older)
        self.assertLess(self.main.index("upgraded in place"), self.main.index("# 5b (row 9)"))

    def test_revoked_while_away_is_refused_on_return_and_cleans_up(self):
        away = self.main.split("# 7 (row 7d)", 1)[1].split("shutil.rmtree(app)", 1)[0]
        steps = ["enrol(j, app", '"autostart", "on"', "login_item.exists()", "relay.stop()",
                 "direct.revoke(key_id) == 200", "code == 1", "relay.start()", "code == 3", "KEPT_AFTER_SIGNOUT",
                 "not login_item.exists()", "keychain_secret(app_url, key_id) is None", "code == 2"]
        at = [away.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the revocation steps are out of order")
        self.assertIn('Browser(f"http://127.0.0.1:{relay.target}")', away)  # the other browser reaches the Hub directly

    def test_sign_in_codes_and_files_holding(self):
        import sqlite3
        import tempfile
        j = load("macos_journey")
        d = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, d, True)
        db = d / "gateway.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE device_codes (id INTEGER PRIMARY KEY, user_code TEXT)")
        con.commit()
        self.assertEqual(j.sign_in_codes(db), (0, 0))
        con.execute("INSERT INTO device_codes(user_code) VALUES ('BCDF-GHJK')")
        con.commit()
        con.close()
        self.assertEqual(j.sign_in_codes(db), (1, 1))
        (d / "logs").mkdir()
        (d / "logs" / "app.log").write_text("ok sgw_secret_value here")
        (d / "device.key").write_text("sgw_secret_value")
        self.assertEqual(j.files_holding("sgw_secret_value", [d], skip={"device.key"}), [str(d / "logs" / "app.log")])
        self.assertEqual(j.files_holding("sgw_secret_value", [d / "missing"]), [])
        self.assertEqual(j.fingerprint(None), "none")
        self.assertEqual(len(j.fingerprint("x")), 12)


class RefusedCodeTests(unittest.TestCase):
    """Row 3a/3b and the grants check on macOS, the same as packaging/windows/installer_e2e.py: a wrong code, an expired
    code and a reused code are refused through the installed app; grants reach it only after it starts again."""

    def setUp(self):
        self.text = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")
        self.main = self.text.split("def main(", 1)[1]

    def test_the_steps_run_in_order_around_the_first_sign_in(self):
        steps = ["fresh_install(j, args.new", "install(j, args.old, apps)",
                 "refused_codes(j, app, browser, env, app_url, data, db)", "enrol(j, app, browser, env, app_url)",
                 "reused_code(j, app, browser, env, app_url, data, db)", "hub_journey.f18(",
                 "hub_journey.grants_after_restart(", "install(j, args.new, apps, args.new_app)"]
        at = [self.main.index(s) for s in steps]
        self.assertEqual(at, sorted(at), "the refused-code or grants steps are out of order")

    def test_each_refusal_checks_what_the_windows_run_checks(self):
        refused = self.text.split("def refused_codes(", 1)[1].split("def reused_code(", 1)[0]
        steps = ["status = 'pending' AND id > ?", "hub_enroll._new_user_code()", "That code isn't right",
                 '"csrf": "0" * 64', "posted == 400", 'waiting == "pending" and login.poll() is None',
                 "real_token_refusals(j, browser, app_url, db, row)",
                 "UPDATE device_codes SET expires = ?", "login.returncode == 1", '"expired" in out.lower()',
                 "keys() == issued", "unusable(browser, row[1])"]
        at = [refused.index(s) for s in steps]
        self.assertEqual(at, sorted(at))
        reused = self.text.split("def reused_code(", 1)[1].split("def start_window(", 1)[0]
        for needle in ("WHERE key_id = ?", "unusable(browser, used[0][0])", "stdin=subprocess.DEVNULL", "code == 1",
                       "sign_in_codes(db) == codes", "keys() == issued", 'again.get("key_id") == device.get("key_id")'):
            self.assertIn(needle, reused)
        for words in ("That code isn't right", "already used or has expired"):  # the Hub really says these
            self.assertTrue(any(words in f.read_text(encoding="utf-8") for f in (ROOT / "gateway").glob("*.py")), words)

    def test_unusable_and_hub_rows(self):
        import sqlite3
        import tempfile
        j = load("macos_journey")
        d = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, d, True)
        db = d / "gateway.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE keys (id INTEGER PRIMARY KEY)")
        con.execute("INSERT INTO keys DEFAULT VALUES")
        con.commit()
        con.close()
        self.assertEqual(j.hub_rows(db, "SELECT COUNT(*) FROM keys"), [(1,)])
        with self.assertRaises(sqlite3.OperationalError):  # read-only: the journey never writes through it
            j.hub_rows(db, "DELETE FROM keys")

        class Page:
            def __init__(self, status, text):
                self.answer = (status, text)

            def call(self, method, path):
                return self.answer

        self.assertTrue(j.unusable(Page(200, "That code was already used or has expired."), "BCDF-GHJK"))
        self.assertFalse(j.unusable(Page(200, "already used or has expired <input name=csrf value='ab'>"), "X"))
        self.assertFalse(j.unusable(Page(500, "already used or has expired"), "X"))
        self.assertFalse(j.unusable(Page(200, "Approve this device"), "X"))

    def test_the_grants_check_starts_the_window_not_background(self):
        start = self.text.split("def start_window(", 1)[1].split("def close_app(", 1)[0]
        self.assertNotIn('"--background"', start)
        self.assertIn("start_window(app, env, starts)", self.main)
        self.assertIn("starts == [True, True]", self.main)

    def test_close_app_stops_the_program(self):
        import subprocess
        import sys
        j = load("macos_journey")
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        j.close_app(proc)
        self.assertIsNotNone(proc.poll())
        j.close_app(proc)  # already closed: nothing to do


class RealTokenCsrfTests(unittest.TestCase):
    """macos_journey.real_token_refusals against a real Hub (tests/support.Rig): a real pending code posted with an
    altered, missing, empty, other-code or other-session token is refused and stays pending."""

    def setUp(self):
        from gateway import security
        from .support import Rig
        self.j = load("macos_journey")
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.rig.gw.db.x("UPDATE people SET pw_hash = ? WHERE id = ?",
                         (security.hash_password(self.j.PASSWORD, 1000), self.rig.person_id))
        self.base = f"http://127.0.0.1:{self.rig.port}"
        self.db = Path(self.rig.tmp) / "gateway.db"
        self.browser = self.j.Browser(self.base)
        self.assertEqual(self.browser.sign_in(), 200)
        status, text = self.browser.call("POST", "/api/device/code", {"name": "CI Mac", "os": "macos"},
                                           headers={"x-swangz-app": "1"})
        code = json.loads(text)["user_code"]
        self.row = (self.rig.gw.db.scalar("SELECT id FROM device_codes WHERE user_code = ?", (code,)), code)

    def steps(self):
        class J:
            results = []

            def step(self, name, ok, detail=""):
                self.results.append((name, ok, detail))
        return J()

    def test_every_real_token_variant_is_refused_and_both_codes_stay_pending(self):
        keys = lambda: self.rig.gw.db.scalar("SELECT COUNT(*) FROM keys")  # noqa: E731
        before, j = keys(), self.steps()
        self.j.real_token_refusals(j, self.browser, self.base, self.db, self.row)
        self.assertEqual(keys(), before)
        self.assertEqual(len(j.results), 8, j.results)
        self.assertTrue(all(ok for _, ok, _ in j.results), [r for r in j.results if not r[1]])
        self.assertEqual(self.rig.gw.db.scalar("SELECT status FROM device_codes WHERE id = ?", (self.row[0],)), "pending")
        # the real token itself still works, so the refusals above were about the token, not the code
        self.assertEqual(self.browser.approve(self.row[1]), 200)
        self.assertEqual(self.rig.gw.db.scalar("SELECT status FROM device_codes WHERE id = ?", (self.row[0],)), "approved")

    def test_the_check_fails_if_the_hub_accepted_a_bad_token(self):
        from gateway import enroll
        real = enroll._csrf
        enroll._csrf = lambda gw, token, code: real(gw, "", code)  # a broken Hub: the token ignores the session
        self.addCleanup(setattr, enroll, "_csrf", real)
        j = self.steps()
        self.j.real_token_refusals(j, self.browser, self.base, self.db, self.row)
        failed = [name for name, ok, _ in j.results if not ok]
        self.assertTrue(any("another session" in n for n in failed), j.results)


class MountedDmgTests(unittest.TestCase):
    """macos_journey.check_mounted: the mounted DMG's app must equal the scanned build, and the whole volume
    (READ ME FIRST.txt included) is secret-scanned. Runs on any OS against a folder laid out like a mounted DMG."""

    def setUp(self):
        import os
        import tempfile
        self.os = os
        self.j_mod = load("macos_journey")
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.dir, True)
        self.build = self.dir / "dist" / "Swangz.app"
        (self.build / "Contents" / "MacOS").mkdir(parents=True)
        (self.build / "Contents" / "MacOS" / "Swangz").write_bytes(b"\xcf\xfa\xed\xfe program")
        (self.build / "Contents" / "Info.plist").write_text("<plist/>")
        os.symlink("MacOS/Swangz", self.build / "Contents" / "current")
        self.mount = self.dir / "mount"
        self.mount.mkdir()
        __import__("shutil").copytree(self.build, self.mount / "Swangz.app", symlinks=True)
        (self.mount / "READ ME FIRST.txt").write_text("RC — UNSIGNED — INTERNAL TEST ONLY")
        os.symlink("/Applications", self.mount / "Applications")
        (self.mount / ".fseventsd").mkdir()
        self.journey = self.j_mod.Journey(self.dir / "ev")
        # the fixture's program is a stand-in: let the scan count it as an opened PyInstaller archive
        opened = __import__("unittest.mock").mock.patch.object(self.j_mod.secret_scan, "scan_pyinstaller", return_value=None)
        opened.start()
        self.addCleanup(opened.stop)

    def check(self):
        self.j_mod.check_mounted(self.journey, self.mount, self.build, self.dir / "ev" / "secret-scan-dmg.json")
        return self.journey.results

    def test_identical_clean_volume_passes_and_the_report_lists_the_notice(self):
        results = self.check()
        self.assertEqual([r["result"] for r in results], ["pass", "pass", "pass"])
        report = json.loads((self.dir / "ev" / "secret-scan-dmg.json").read_text())
        self.assertTrue(any(f.endswith("READ ME FIRST.txt") for f in report["files"]))
        self.assertFalse(any("Applications" in f or ".fseventsd" in f for f in report["files"]))
        scan = load("secret_scan")
        self.assertEqual(scan.scan([self.dir / "ev"])["hits"], [])  # the later workflow scan of evidence/ stays clean

    def test_a_changed_file_in_the_dmg_fails(self):
        (self.mount / "Swangz.app" / "Contents" / "Info.plist").write_text("<plist>other</plist>")
        with self.assertRaises(SystemExit):
            self.check()
        self.assertIn("Contents/Info.plist", self.journey.results[-1]["detail"])

    def test_an_extra_file_or_a_retargeted_link_fails(self):
        (self.mount / "Swangz.app" / "Contents" / "extra.py").write_text("x")
        with self.assertRaises(SystemExit):
            self.check()
        (self.mount / "Swangz.app" / "Contents" / "extra.py").unlink()
        self.os.remove(self.mount / "Swangz.app" / "Contents" / "current")
        self.os.symlink("Info.plist", self.mount / "Swangz.app" / "Contents" / "current")
        self.journey.results.clear()
        with self.assertRaises(SystemExit):
            self.check()

    def test_a_secret_in_the_rc_notice_fails(self):
        (self.mount / "READ ME FIRST.txt").write_text("key sk-ant-" + "a1" * 20)
        with self.assertRaises(SystemExit):
            self.check()
        self.assertEqual(self.journey.results[-1]["result"], "FAIL")
        self.assertIn("Anthropic key", self.journey.results[-1]["detail"])

    def test_a_hidden_or_unexpected_entry_on_the_volume_fails(self):
        (self.mount / ".hidden").write_text("sk-ant-" + "a1" * 20)
        with self.assertRaises(SystemExit):
            self.check()
        self.assertIn("unexpected: .hidden", self.journey.results[-1]["detail"])

    def test_an_applications_link_pointing_elsewhere_fails(self):
        self.os.remove(self.mount / "Applications")
        self.os.symlink("/tmp", self.mount / "Applications")
        with self.assertRaises(SystemExit):
            self.check()
        self.assertEqual(self.journey.results[-1]["result"], "FAIL")

    def test_a_volume_whose_program_could_not_be_opened_fails(self):
        with __import__("unittest.mock").mock.patch.object(self.j_mod.secret_scan, "scan_pyinstaller", return_value="not a PyInstaller program"):
            with self.assertRaises(SystemExit):
                self.check()
        self.assertEqual(self.journey.results[-1]["result"], "FAIL")
        self.assertIn("0 PyInstaller archives opened", self.journey.results[-1]["detail"])


class FixtureRestartTests(unittest.TestCase):
    """tests/browser/demo.py restart mode: a new process reopens the same data folder on the same port, seeds nothing."""

    def start(self, env):
        import os
        import subprocess
        import sys
        proc = subprocess.Popen([sys.executable, str(ROOT / "tests" / "browser" / "demo.py")], cwd=ROOT,
                                env={**os.environ, "HUB_FIXTURE_KEEP": "1", **env}, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(), proc.wait()))
        return proc, json.loads(proc.stdout.readline())

    def stop(self, proc):
        proc.terminate()
        proc.wait(timeout=20)
        proc.stdout.close()

    def test_restart_reopens_the_same_data_and_port_without_seeding(self):
        import shutil
        import sqlite3
        import urllib.request
        first, a = self.start({})
        self.addCleanup(shutil.rmtree, a["data"], True)
        db = Path(a["data"]) / "gateway.db"
        count = lambda: sqlite3.connect(db).execute(
            "SELECT (SELECT COUNT(*) FROM people), (SELECT COUNT(*) FROM keys), (SELECT COUNT(*) FROM admins)").fetchone()
        self.stop(first)
        self.assertTrue(db.is_file(), "HUB_FIXTURE_KEEP leaves the data folder behind")
        before = count()
        second, b = self.start({"HUB_FIXTURE_DATA": a["data"], "HUB_FIXTURE_PORT": str(a["port"])})
        self.assertNotEqual(a["pid"], b["pid"])
        self.assertEqual((a["port"], a["data"], a["person"], a["key"]), (b["port"], b["data"], b["person"], b["key"]))
        with urllib.request.urlopen(f"http://127.0.0.1:{b['port']}/healthz", timeout=10) as r:
            self.assertEqual(r.status, 200)
        self.assertEqual(count(), before, "a restart seeds nothing again")
        self.stop(second)
        self.assertTrue(db.is_file())


class PolicyTamperTests(unittest.TestCase):
    """Deliverable 6 (packaging/macos_policy.py): the machine policy pack tampered with, through the packaged app."""

    def setUp(self):
        self.p = load("macos_policy")
        self.journey = (ROOT / "packaging" / "macos_journey.py").read_text(encoding="utf-8")

    def test_the_journey_runs_it_on_a_company_device_before_the_disconnect_rows(self):
        call = self.journey.index("macos_policy.run(")
        self.assertLess(call, self.journey.index("# 7 (row 7d)"))
        self.assertIn('browser.approve(code, "company")', self.journey[call:call + 600])
        self.assertIn('"owner": kind', self.journey)

    def test_the_messages_it_looks_for_are_the_ones_the_app_and_the_hub_write(self):
        launcher = (ROOT / "swangz_client" / "workspace_launcher.py").read_text(encoding="utf-8")
        self.assertIn(self.p.REFUSED, launcher.replace("\\'", "'"))
        self.assertIn(self.p.AUDIT, (ROOT / "gateway" / "managed.py").read_text(encoding="utf-8"))
        self.assertIn(str(self.p.PLIST), (ROOT / "swangz_client" / "machine_policy.py").read_text(encoding="utf-8"))

    def test_the_tampered_packs(self):
        policy = {"URLBlocklist": ["*", "file://*"], "URLAllowlist": ["hub.swangz-ci.com"]}
        self.assertEqual(self.p.without_default_deny(policy)["URLBlocklist"], ["file://*"])
        self.assertEqual(self.p.extra_block(policy)["URLBlocklist"], ["*", "file://*", self.p.EXTRA_BLOCK])
        self.assertEqual(policy["URLBlocklist"], ["*", "file://*"], "the original pack is not changed")

    def test_prepare_returns_the_pack_and_its_printed_baseline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            policy, baseline = self.p.prepare(work)
        self.assertRegex(baseline, r"^[0-9a-f]{64}$")
        self.assertIn("*", policy["URLBlocklist"])
        from swangz_client import machine_policy
        self.assertEqual(machine_policy.problems_in(policy), [])
        self.assertEqual(machine_policy.problems_in(self.p.extra_block(policy)), [], "case 3 still passes every rule")
        self.assertNotEqual(machine_policy.problems_in(self.p.without_default_deny(policy)), [])
        self.assertEqual(machine_policy.baseline_sha(policy), baseline, "the app computes the hash prepare.py printed")
        self.assertNotEqual(machine_policy.baseline_sha(self.p.extra_block(policy)), baseline)

    def test_it_always_restores_the_runner_and_writes_its_evidence(self):
        src = (ROOT / "packaging" / "macos_policy.py").read_text(encoding="utf-8")
        tail = src[src.index("    finally:"):]
        for needed in ("remove()", '"managed_policy_mode": "warn"', "policy-tamper.json"):
            self.assertIn(needed, tail)


class MacReproducibleTests(unittest.TestCase):
    def setUp(self):
        self.r = load("macos_reproducible")
        self.workflow = (ROOT / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")

    def make(self, root, files):
        import os
        for rel, data in files.items():
            p = Path(root) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        os.symlink("Contents/MacOS/Swangz", Path(root) / "link")

    def test_identical_and_different_trees_and_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            a, b, c = Path(t, "a.app"), Path(t, "b.app"), Path(t, "c.app")
            base = {"Contents/MacOS/Swangz": b"prog", "Contents/Info.plist": b"<plist/>"}
            self.make(a, base)
            self.make(b, base)
            self.make(c, {**base, "Contents/MacOS/Swangz": b"prog2"})
            same = self.r.compare_apps(a, b)
            self.assertTrue(same["identical"])
            self.assertEqual(same["a"]["tree_sha256"], same["b"]["tree_sha256"])
            diff = self.r.compare_apps(a, c)
            self.assertFalse(diff["identical"])
            self.assertEqual([d["path"] for d in diff["differing"]], ["Contents/MacOS/Swangz"])
            report = Path(t, "out", "r.json")
            summary = Path(t, "summary.md")
            (Path(t) / "x.dmg").write_bytes(b"1")
            (Path(t) / "y.dmg").write_bytes(b"2")
            code = self.r.main(["--app-a", str(a), "--app-b", str(c), "--dmg-a", str(Path(t, "x.dmg")),
                                "--dmg-b", str(Path(t, "y.dmg")), "--report", str(report), "--summary", str(summary)])
            self.assertEqual(code, 0, "a difference is reported, never a failure")
            data = json.loads(report.read_text())
            self.assertFalse(data["app"]["identical"] or data["dmg"]["identical"])
            self.assertEqual(summary.read_text().count("**DIFFERENT**"), 2)
            self.assertEqual(self.r.main(["--app-a", str(a), "--app-b", str(Path(t, "nope")), "--dmg-a", "x",
                                          "--dmg-b", "y", "--report", str(report)]), 2)

    def test_the_workflow_builds_twice_with_the_same_version_and_keeps_the_report(self):
        step = self.workflow[self.workflow.index("Reproducibility"):self.workflow.index("- name: Checksums")]
        self.assertIn("--dist dist-b", step)
        self.assertIn("${NEW_VERSION}", step)
        self.assertIn("git checkout -- swangz_client/__init__.py", step)
        self.assertIn("evidence/reproducible-macos.json", step)
        self.assertIn("SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)", self.workflow)
        self.assertIn("evidence/", self.workflow[self.workflow.index("upload-artifact"):])


class BumpVersionTests(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        self.b = load("bump_version")
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        for rel in ("swangz_client/__init__.py", "gateway/enroll.py"):
            (self.root / rel).parent.mkdir(parents=True)
            (self.root / rel).write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")

    def test_the_real_tree_has_each_value_once(self):
        now = self.b.read()
        self.assertEqual(set(now), {"__version__", "CLIENT_LATEST", "CLIENT_MINIMUM"})
        for v in now.values():
            self.b.parse(v)

    def test_bump_changes_the_app_and_latest_but_not_the_minimum(self):
        before = self.b.read(self.root)
        changed = self.b.bump("0.2.0", root=self.root)
        after = self.b.read(self.root)
        self.assertEqual((after["__version__"], after["CLIENT_LATEST"]), ("0.2.0", "0.2.0"))
        self.assertEqual(after["CLIENT_MINIMUM"], before["CLIENT_MINIMUM"])
        self.assertIn("__version__", changed)

    def test_minimum_only_when_asked_and_refusals(self):
        self.b.bump("0.2.0", minimum="0.2.0", root=self.root)
        self.assertEqual(self.b.read(self.root)["CLIENT_MINIMUM"], "0.2.0")
        for bad in (("0.2.0", None), ("0.1.9", None), ("0.3.0", "0.4.0"), ("0.3.0", "0.1.0")):
            with self.assertRaises(SystemExit):
                self.b.bump(*bad, root=self.root)
        with self.assertRaises(ValueError):
            self.b.bump("0.3", root=self.root)
