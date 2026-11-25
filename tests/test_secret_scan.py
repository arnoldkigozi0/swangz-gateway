"""The release secret scan: finds embedded secrets in files and zip entries, masks them in its report, and is wired
into the Windows release job so a hit fails the build."""
import importlib.util
import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("secret_scan", ROOT / "packaging" / "secret_scan.py")
secret_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(secret_scan)
WORKFLOW = (ROOT / ".github/workflows/release-windows.yml").read_text(encoding="utf-8")

# Built at run time so this file itself never holds a secret-shaped string.
FAKE = {
    "Anthropic key": "sk-ant-" + "a1" * 20,
    "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "GitHub token": "ghp_" + "Ab3" * 12,
    "AWS access key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "Swangz Hub key": "sgw_" + "0a1b2c3d4e5f" + "_" + "x" * 43,
    "deployment address": "hub-demo" + ".trycloudflare.com",
}


class SecretScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_scan(self, *paths):
        report = self.dir / "out" / "report.json"
        summary = self.dir / "summary.md"
        with redirect_stdout(io.StringIO()) as out:
            code = secret_scan.main([*map(str, paths), "--report", str(report), "--summary", str(summary)])
        return code, json.loads(report.read_text()), out.getvalue(), summary.read_text()

    def test_clean_input_passes(self):
        (self.dir / "a.txt").write_text("Your Swangz AI Hub address (for example https://ai.swangzavenue.com): ")
        code, rep, out, summary = self.run_scan(self.dir / "a.txt")
        self.assertEqual(code, 0)
        self.assertEqual(rep["hits"], [])
        self.assertIn("CLEAN", out)
        self.assertIn("CLEAN", summary)

    def test_an_aws_shape_inside_a_base64_run_is_not_a_hit(self):
        # The macOS RC's DMG block table (run 45587200151): base64, so "AKIA" sat in the middle of a run of A's.
        table = b"\t\t\t\tReAAAAAAAAAIAAAAAAAAAA" + b"KIA" + b"AAAAAAAQAACAAAAFAAAA\n\t\t\t\tHwAAAAAAAE3gAAAAAAAACAAAAAAAAB2j"
        for prefix in (b"", b"+", b"/", b"7"):
            with self.subTest(prefix=prefix):
                f = self.dir / "blkx.plist"
                f.write_bytes(prefix + table)
                code, rep, _, _ = self.run_scan(f)
                self.assertEqual((code, rep["hits"]), (0, []))

    def test_a_real_shaped_aws_key_is_still_caught_after_any_separator(self):
        key = (FAKE["AWS access key"]).encode()
        for before in (b"", b"\n", b" ", b"=", b"\"", b"'", b":", b"\x00", b"-", b"_", b"\t"):
            with self.subTest(before=before):
                f = self.dir / "cfg.txt"
                f.write_bytes(b"AWS_ACCESS_KEY_ID" + before + key + b"\n" if before else key + b"\n")
                code, rep, _, _ = self.run_scan(f)
                self.assertEqual(code, 1)
                self.assertIn("AWS access key", [h["pattern"] for h in rep["hits"]])
        f = self.dir / "sts.txt"
        f.write_bytes(b'"' + b"ASIA" + b"ABCDEFGHIJKLMNOP" + b'"')
        self.assertIn("AWS access key", [h["pattern"] for h in self.run_scan(f)[1]["hits"]])

    def test_each_pattern_is_found_and_masked(self):
        for name, value in FAKE.items():
            with self.subTest(name):
                f = self.dir / "bin.dat"
                f.write_bytes(b"\x00prefix " + value.encode() + b" suffix\x00")
                code, rep, out, _ = self.run_scan(f)
                self.assertEqual(code, 1)
                self.assertIn(name, [h["pattern"] for h in rep["hits"]])
                if name not in ("deployment address",):
                    # the report never carries the secret itself
                    self.assertNotIn(value, json.dumps(rep))
                    self.assertNotIn(value, out)

    def test_zip_entries_and_env_files_are_searched(self):
        z = self.dir / "lib.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pkg/config.py", "KEY = '" + FAKE["Anthropic key"] + "'")
            zf.writestr("pkg/.env", "nothing")
        code, rep, _, _ = self.run_scan(z)
        self.assertEqual(code, 1)
        where = {(h["pattern"], h["where"].split("!")[-1]) for h in rep["hits"]}
        self.assertIn(("Anthropic key", "pkg/config.py"), where)
        self.assertIn((".env file", "pkg/.env"), where)
        self.assertEqual(rep["inner_entries_scanned"], 2)

    def test_folder_is_walked(self):
        (self.dir / "sub").mkdir()
        (self.dir / "sub" / "log.txt").write_text("device key " + FAKE["Swangz Hub key"])
        code, rep, _, _ = self.run_scan(self.dir / "sub")
        self.assertEqual(code, 1)
        self.assertEqual(len(rep["files"]), 1)

    def test_an_empty_folder_fails(self):
        (self.dir / "empty" / "nested").mkdir(parents=True)  # folders but no files: nothing was scanned
        (self.dir / "a.txt").write_text("clean")
        code, rep, out, summary = self.run_scan(self.dir / "a.txt", self.dir / "empty")
        self.assertEqual(code, 1)
        self.assertEqual(rep["hits"], [])
        self.assertEqual(rep["problems"], [f"{self.dir / 'empty'}: no files to scan"])
        self.assertIn("FAILED", out)
        self.assertIn("**FAILED**", summary)

    def test_min_archives_fails_when_too_few_programs_were_opened(self):
        (self.dir / "a.txt").write_text("clean")
        report = self.dir / "r.json"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(secret_scan.main([str(self.dir / "a.txt"), "--report", str(report), "--min-archives", "1"]), 1)
        self.assertEqual(json.loads(report.read_text())["problems"], ["0 PyInstaller archives opened, at least 1 expected"])
        with redirect_stdout(io.StringIO()), patch.object(secret_scan, "scan_pyinstaller", return_value=None):
            (self.dir / "prog").write_bytes(b"MZ program")  # stands in for a program the reader opened
            self.assertEqual(secret_scan.main([str(self.dir / "prog"), "--report", str(report), "--min-archives", "1"]), 0)
        self.assertEqual(json.loads(report.read_text())["problems"], [])

    def test_the_jobs_require_their_programs_to_be_opened(self):
        mac = (ROOT / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")
        self.assertIn("--min-archives 2 dist evidence", mac)  # dist/Swangz/Swangz and Swangz.app/Contents/MacOS/Swangz
        self.assertIn("--min-archives 1 dist artifacts evidence", WORKFLOW)  # dist\Swangz.exe

    def test_missing_input_exits_2(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(secret_scan.main([str(self.dir / "nope"), "--report", str(self.dir / "r.json")]), 2)

    def test_client_source_is_clean(self):
        """What goes into the program today carries no secret or deployment address."""
        code, rep, out, _ = self.run_scan(ROOT / "swangz_client", ROOT / "packaging" / "windows")
        self.assertEqual(code, 0, out)

    def test_windows_job_runs_the_scan_and_fails_on_hits(self):
        self.assertIn("python packaging/secret_scan.py --report evidence\\secret-scan.json", WORKFLOW)
        self.assertIn("dist artifacts evidence packaging\\windows\\swangz.iss", WORKFLOW)
        step = WORKFLOW.split("- name: Secret scan", 1)[1].split("\n      - ", 1)[0]
        self.assertNotIn("continue-on-error", step)
        # after the acceptance run (so its logs are scanned) and before the release artifact is uploaded
        self.assertLess(WORKFLOW.index("installer_e2e.py"), WORKFLOW.index("- name: Secret scan"))
        self.assertLess(WORKFLOW.index("- name: Secret scan"), WORKFLOW.index("name: Swangz-Windows-installer-RC-UNSIGNED"))


if __name__ == "__main__":
    unittest.main()
