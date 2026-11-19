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
