"""packaging/macos.py: the parts that do not need a Mac (the rest runs on macos-latest in release-macos.yml)."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("swangz_macos", ROOT / "packaging" / "macos.py")
macos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macos)


class MacPackagingTests(unittest.TestCase):
    def test_plist_carries_version_identifier_and_unsigned_label(self):
        out = macos.stamp_plist({"CFBundleShortVersionString": "0.0.0", "LSBackgroundOnly": True, "Keep": 1},
                                "1.2.3", "456")
        self.assertEqual(out["CFBundleShortVersionString"], "1.2.3")
        self.assertEqual(out["CFBundleVersion"], "456")
        self.assertEqual(out["CFBundleIdentifier"], "com.swangzavenue.swangz")
        self.assertIn("UNSIGNED", out["NSHumanReadableCopyright"])
        self.assertNotIn("LSBackgroundOnly", out)
        self.assertEqual(out["Keep"], 1)

    def test_artifact_names_say_unsigned(self):
        self.assertEqual(macos.artifact_name("0.1.0", "arm64", "dmg"), "Swangz-0.1.0-macOS-arm64-UNSIGNED.dmg")

    def test_dmg_is_compressed_read_only(self):
        cmd = macos.dmg_command("/s", "/o.dmg", "Swangz 0.1.0")
        self.assertEqual(cmd[:2], ["hdiutil", "create"])
        self.assertEqual(cmd[cmd.index("-format") + 1], "UDZO")

    def test_never_bypasses_gatekeeper(self):
        src = (ROOT / "packaging" / "macos.py").read_text(encoding="utf-8")
        flow = (ROOT / ".github" / "workflows" / "release-macos.yml").read_text(encoding="utf-8")
        for text in (src, flow):
            for bad in ("xattr -d", "xattr -c", "com.apple.quarantine", "spctl --master-disable",
                        "spctl --add", "--global-disable"):
                self.assertNotIn(bad, text)
        self.assertIn("spctl", src)  # Gatekeeper's verdict is recorded and must be a refusal


if __name__ == "__main__":
    unittest.main()
