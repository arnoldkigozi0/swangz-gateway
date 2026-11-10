"""Run the dependency-free extension regressions from the standard CI suite."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node is required for extension JavaScript regressions")
class ExtensionTests(unittest.TestCase):
    def test_fail_closed_worker_and_blocked_page(self):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run([shutil.which("node"), "tests/browser/extension.cjs"],
                                cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
