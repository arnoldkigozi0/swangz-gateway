"""The SBOM of the Windows program: CycloneDX 1.5, lists the runtime, the client code, every bundled native file and the
hash-pinned build tools; flags third-party Python packages; is produced by the release job next to the installer."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sbom", ROOT / "packaging" / "sbom.py")
sbom = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sbom)
REQS = ROOT / "packaging" / "requirements-windows-build.txt"
WORKFLOW = (ROOT / ".github/workflows/release-windows.yml").read_text(encoding="utf-8")


class SbomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.program = Path(self.tmp.name) / "Swangz.exe"
        self.program.write_bytes(b"MZ fake program")

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_tools_come_from_the_hash_pinned_file(self):
        reqs = sbom.read_requirements(REQS)
        names = {n: (v, h) for n, v, h in reqs}
        self.assertIn("pyinstaller", names)
        self.assertEqual(len(reqs), 7)
        for name, (version, hashes) in names.items():
            self.assertTrue(version and hashes, name)
            self.assertTrue(all(len(h) == 64 for h in hashes), name)

    def test_bom_lists_program_runtime_client_native_files_and_tools(self):
        bom, unexpected = sbom.build(self.program, "0.1.9", sbom.read_requirements(REQS),
                                     {"python312.dll": "a" * 64, "_ssl.pyd": "b" * 64},
                                     ["json", "swangz_client", "swangz_client.core", "urllib.request"], "3.12.7", epoch=1700000000)
        self.assertEqual(unexpected, [])
        self.assertEqual((bom["bomFormat"], bom["specVersion"]), ("CycloneDX", "1.5"))
        self.assertEqual(bom["metadata"]["timestamp"], "2023-11-14T22:13:20Z")
        self.assertEqual(bom["metadata"]["component"]["version"], "0.1.9")
        self.assertEqual(bom["metadata"]["component"]["hashes"][0]["content"], sbom.sha256(b"MZ fake program"))
        refs = {c["bom-ref"]: c for c in bom["components"]}
        self.assertEqual(refs["cpython"]["version"], "3.12.7")
        self.assertIn("swangz_client.core", refs["swangz-client"]["properties"][0]["value"])
        self.assertEqual(refs["file:python312.dll"]["hashes"][0]["content"], "a" * 64)
        self.assertEqual(len(bom["metadata"]["tools"]["components"]), 7)
        self.assertEqual(set(bom["dependencies"][0]["dependsOn"]), set(refs))
        json.dumps(bom)

    def test_same_inputs_give_the_same_bom(self):
        args = (self.program, "0.1.9", [], {}, ["json"], "3.12.7")
        self.assertEqual(sbom.build(*args, epoch=1)[0], sbom.build(*args, epoch=1)[0])

    def test_third_party_package_is_flagged(self):
        _, unexpected = sbom.build(self.program, "0.1.9", [], {}, ["json", "requests", "requests.api"], "3.12.7", epoch=1)
        self.assertEqual(unexpected, ["requests"])

    def test_missing_input_exits_2(self):
        self.assertEqual(sbom.main(["--program", "nope.exe", "--version", "1", "--requirements", str(REQS),
                                    "--out", str(Path(self.tmp.name) / "o.json")]), 2)

    def test_the_release_job_ships_the_sbom_with_the_installer(self):
        self.assertIn("python packaging/sbom.py --program dist\\Swangz.exe --version $env:NEW_VERSION", WORKFLOW)
        self.assertIn("--epoch $env:SOURCE_DATE_EPOCH", WORKFLOW)
        self.assertIn("--out artifacts\\Swangz-$env:NEW_VERSION.cdx.json", WORKFLOW)
        step = WORKFLOW.split("- name: SBOM", 1)[1].split("\n      - ", 1)[0]
        self.assertNotIn("continue-on-error", step)
        self.assertLess(WORKFLOW.index("- name: SBOM"), WORKFLOW.index("name: Swangz-Windows-installer-RC-UNSIGNED"))


if __name__ == "__main__":
    unittest.main()
