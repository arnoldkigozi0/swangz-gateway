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

    def test_build_times_are_replaced_by_the_source_date(self):
        self.assertIn("SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)", WORKFLOW)
        build = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("SOURCE_DATE_EPOCH")', build)
        self.assertIn("pe.OPTIONAL_HEADER.CheckSum = pe.generate_checksum()", build)
        iss = (ROOT / "packaging" / "windows" / "swangz.iss").read_text(encoding="utf-8")
        self.assertIn("TouchDate=none", iss)
        self.assertIn("TouchTime=none", iss)

    def test_normalizing_a_windows_program_sets_the_stamps_and_keeps_the_archive(self):
        import sys
        if sys.platform != "win32":
            self.skipTest("needs a Windows program to normalize; the Windows job's IDENTICAL/DIFFERENT result covers it")
        try:
            import pefile  # noqa: F401  (PyInstaller's Windows dependency; present on the CI build machine)
        except ImportError:
            self.skipTest("pefile is not installed here; the Windows job's IDENTICAL/DIFFERENT result covers it")
        spec_b = importlib.util.spec_from_file_location("build", ROOT / "packaging" / "build.py")
        build = importlib.util.module_from_spec(spec_b)
        spec_b.loader.exec_module(build)
        program = self.write("Swangz.exe", Path(sys.executable).read_bytes() + b"ARCHIVE-TAIL")
        replaced = build.normalize_windows_program(program, 1700000000)
        self.assertIn("file_header", replaced)
        data = program.read_bytes()
        self.assertTrue(data.endswith(b"ARCHIVE-TAIL"))
        self.assertEqual(repro.pe_header(data)["timestamp"], 1700000000)


if __name__ == "__main__":
    unittest.main()
