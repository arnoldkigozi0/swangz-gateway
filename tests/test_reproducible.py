"""The reproducible-build check: it reports identical or different honestly and never hides a difference."""

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("reproducible", ROOT / "packaging" / "reproducible.py")
repro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repro)
WORKFLOW = (ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")


def pe(timestamp, checksum, tail=b"payload"):
    data = bytearray(0x200)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<I", data, 0x80 + 8, timestamp)
    struct.pack_into("<I", data, 0x80 + 24 + 64, checksum)
    return bytes(data) + tail


class ReproducibleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def write(self, name, data):
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def run_main(self, a, b, label="program"):
        report, summary = self.tmp / "r.json", self.tmp / "summary.md"
        code = repro.main(["--a", str(a), "--b", str(b), "--label", label, "--report", str(report), "--summary", str(summary)])
        return code, json.loads(report.read_text(encoding="utf-8")) if report.exists() else None, summary

    def test_identical_builds_say_identical(self):
        code, result, summary = self.run_main(self.write("a", b"same"), self.write("b", b"same"))
        self.assertEqual(code, 0)
        self.assertTrue(result["identical"])
        self.assertEqual(result["a"]["sha256"], result["b"]["sha256"])
        self.assertIn("**IDENTICAL**", summary.read_text(encoding="utf-8"))

    def test_a_difference_is_reported_with_where_and_never_fails_the_build(self):
        code, result, summary = self.run_main(self.write("a", pe(1000, 7)), self.write("b", pe(2000, 9)))
        self.assertEqual(code, 0)
        self.assertFalse(result["identical"])
        self.assertNotEqual(result["a"]["sha256"], result["b"]["sha256"])
        self.assertEqual(result["pe"], {"a": {"timestamp": 1000, "checksum": 7}, "b": {"timestamp": 2000, "checksum": 9}})
        self.assertTrue(result["differing_ranges"])
        self.assertIn("unavailable", result["archive_entries_differing"])  # not a PyInstaller archive: said, not guessed
        self.assertIn("**DIFFERENT**", summary.read_text(encoding="utf-8"))

    def test_ranges_cover_changed_and_extra_bytes(self):
        ranges, more = repro.differing_ranges(b"abcdef", b"aXcYefZZ")
        self.assertEqual(ranges, [[1, 2], [3, 4], [6, 8]])
        self.assertFalse(more)

    def test_a_missing_build_is_an_error(self):
        code, result, _ = self.run_main(self.write("a", b"x"), self.tmp / "nope")
        self.assertEqual(code, 2)
        self.assertIsNone(result)

    def test_the_windows_job_builds_twice_and_compares_both_outputs(self):
        self.assertIn("python packaging/build.py --dist dist-b --work build/packaging-b", WORKFLOW)
        self.assertIn("--label program --report evidence\\reproducible-program.json", WORKFLOW)
        self.assertIn("--label installer --report evidence\\reproducible-installer.json", WORKFLOW)
        self.assertEqual(WORKFLOW.count("--summary $env:GITHUB_STEP_SUMMARY"), 2)
        self.assertNotIn("path: repro-b", WORKFLOW)  # the second build is a test input, never uploaded


if __name__ == "__main__":
    unittest.main()
