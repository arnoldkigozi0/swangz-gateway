"""D-026 A2-A4: Chrome's publisher is checked by signature, rechecked when the binary changes, and a company
device accepts only a per-machine install. Stand-ins everywhere; the Native* classes run the real checks on the
Windows and macOS CI runners (which ship Google Chrome) and skip elsewhere."""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swangz_client import chrome_verify as cv
from swangz_client import workspace_launcher as wl


def _len(n):
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag, body):
    return bytes([tag]) + _len(len(body)) + body


OIDS = {"CN": b"\x55\x04\x03", "O": b"\x55\x04\x0a", "L": b"\x55\x04\x07", "C": b"\x55\x04\x06"}


def name(*pairs):
    """[("O", "Google LLC"), ...] -> a DER X.501 Name, one attribute per RDN."""
    rdns = b"".join(_tlv(0x31, _tlv(0x30, _tlv(0x06, OIDS[k]) + _tlv(0x0C, v.encode()))) for k, v in pairs)
    return _tlv(0x30, rdns)


GOOGLE = name(("C", "US"), ("L", "Mountain View"), ("O", "Google LLC"), ("CN", "Google LLC"))
WIN_PF = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
WIN_LOCAL = r"C:\Users\amy\AppData\Local\Google\Chrome\Application\chrome.exe"
WIN_ENV = {"ProgramFiles": r"C:\Program Files", "ProgramFiles(x86)": r"C:\Program Files (x86)",
           "LocalAppData": r"C:\Users\amy\AppData\Local", "SystemRoot": r"C:\Windows"}
MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Run:
    """subprocess.run stand-in: answers by the program's base name and counts the calls."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        out = self.answers[os.path.basename(argv[0].replace("\\", "/"))]
        if isinstance(out, Exception):
            raise out
        code, stdout = out if isinstance(out, tuple) else (0, out)
        return SimpleNamespace(returncode=code, stdout=stdout, stderr=b"")


def authenticode(status="Valid", subject=GOOGLE):
    return json.dumps({"status": status, "subject": base64.b64encode(subject).decode() if subject else ""}).encode()


class Stat:
    def __init__(self, size=100, mtime=1, uid=0):
        self.size, self.mtime, self.uid = size, mtime, uid

    def __call__(self, path):
        return SimpleNamespace(st_size=self.size, st_mtime_ns=self.mtime, st_uid=self.uid)


def windows(run, stat=None):
    return cv.Verifier("win32", run=run, env=WIN_ENV, stat=stat or Stat(), realpath=lambda p: p, digest=lambda p: "ab")


def mac(run, stat=None):
    return cv.Verifier("darwin", run=run, stat=stat or Stat(), realpath=lambda p: p, digest=lambda p: "ab")


class SubjectTests(unittest.TestCase):
    def test_google_llc_exactly(self):
        self.assertTrue(cv.organisation_is_google(GOOGLE))

    def test_lookalike_organisations_fail(self):
        for o in ("Google LLC Ltd", "google llc", "Google LLC ", "Google Inc", "Not Google LLC"):
            with self.subTest(o=o):
                self.assertFalse(cv.organisation_is_google(name(("O", o), ("CN", "x"))))

    def test_a_common_name_that_contains_the_organisation_fails(self):
        self.assertFalse(cv.organisation_is_google(name(("CN", "Evil, O=Google LLC"), ("O", "Evil Corp"))))
        self.assertFalse(cv.organisation_is_google(name(("CN", "O=Google LLC"))))

    def test_two_organisations_fail(self):
        self.assertFalse(cv.organisation_is_google(name(("O", "Google LLC"), ("O", "Evil Corp"))))

    def test_garbage_fails(self):
        for raw in (b"", b"\x30", b"\x30\x05\x31\x03", GOOGLE + b"\x00", GOOGLE[:-1], b"O=Google LLC"):
            with self.subTest(raw=raw):
                self.assertFalse(cv.organisation_is_google(raw))


class WindowsTests(unittest.TestCase):
    def test_google_signed_per_machine_chrome_passes_on_a_company_device(self):
        run = Run(**{"powershell.exe": authenticode()})
        windows(run)(WIN_PF, company=True)
        argv, kw = run.calls[0]
        self.assertEqual(argv[0], os.path.join(r"C:\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe"))
        self.assertEqual(kw["env"]["SWANGZ_CHROME_PATH"], WIN_PF)
        self.assertNotIn(WIN_PF, " ".join(argv))  # the path never becomes script text
        self.assertFalse(kw["shell"])

    def test_wrong_signer_refused(self):
        for subject in (name(("O", "Evil Corp")), name(("O", "Google LLC Ltd")), name(("CN", "O=Google LLC"))):
            with self.subTest(subject=subject), self.assertRaises(cv.Refused):
                windows(Run(**{"powershell.exe": authenticode(subject=subject)}))(WIN_PF, company=False)

    def test_unsigned_or_invalid_refused(self):
        for status in ("NotSigned", "HashMismatch", "NotTrusted", "UnknownError", None):
            with self.subTest(status=status), self.assertRaises(cv.Refused):
                windows(Run(**{"powershell.exe": authenticode(status, subject=None if status == "NotSigned" else GOOGLE)}))(WIN_PF, False)

    def test_unreadable_answers_refused(self):
        for out in ((1, authenticode()), b"", b"not json", b"[]", OSError("gone"), subprocess.TimeoutExpired("ps", 60),
                    json.dumps({"status": "Valid", "subject": "!!"}).encode()):
            with self.subTest(out=out), self.assertRaises(cv.Refused):
                windows(Run(**{"powershell.exe": out}))(WIN_PF, False)

    def test_company_local_app_data_refused_without_running_anything(self):
        run = Run(**{"powershell.exe": authenticode()})
        with self.assertRaises(cv.Refused):
            windows(run)(WIN_LOCAL, company=True)
        self.assertEqual(run.calls, [])

    def test_company_refuses_a_link_out_of_program_files(self):
        v = cv.Verifier("win32", run=Run(**{"powershell.exe": authenticode()}), env=WIN_ENV, stat=Stat(),
                        realpath=lambda p: WIN_LOCAL if p == WIN_PF else p, digest=lambda p: "ab")
        with self.assertRaises(cv.Refused):
            v(WIN_PF, company=True)

    def test_personal_local_app_data_accepted_when_signed_and_still_checked(self):
        run = Run(**{"powershell.exe": authenticode()})
        windows(run)(WIN_LOCAL, company=False)
        self.assertEqual(len(run.calls), 1)
        with self.assertRaises(cv.Refused):
            windows(Run(**{"powershell.exe": authenticode("NotSigned", None)}))(WIN_LOCAL, company=False)


class MacTests(unittest.TestCase):
    def test_codesign_requirement_and_spctl_both_run(self):
        run = Run(codesign=b"", spctl=b"")
        mac(run)(MAC, company=True)
        (cs, _), (sp, _) = run.calls
        app = "/Applications/Google Chrome.app"
        self.assertEqual(cs, ["/usr/bin/codesign", "--verify", "--deep", "--strict", "-R=" + cv.MAC_REQUIREMENT, app])
        self.assertEqual(sp, ["/usr/sbin/spctl", "--assess", "--type", "execute", app])
        self.assertIn('leaf[subject.OU] = "EQHXZ8M8AV"', cv.MAC_REQUIREMENT)
        self.assertIn('identifier "com.google.Chrome"', cv.MAC_REQUIREMENT)

    def test_wrong_signer_or_unsigned_refused(self):
        for answers in ({"codesign": (3, b""), "spctl": b""}, {"codesign": (1, b""), "spctl": b""},
                        {"codesign": b"", "spctl": (3, b"")}, {"codesign": OSError("no"), "spctl": b""}):
            with self.subTest(answers=answers), self.assertRaises(cv.Refused):
                mac(Run(**answers))(MAC, company=False)

    def test_company_needs_root_owned_app_in_applications(self):
        run = Run(codesign=b"", spctl=b"")
        with self.assertRaises(cv.Refused):
            mac(run, Stat(uid=501))(MAC, company=True)
        with self.assertRaises(cv.Refused):
            mac(run)("/Users/amy/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", company=True)
        self.assertEqual(run.calls, [])
        mac(run, Stat(uid=501))(MAC, company=False)  # a personal Mac: the signature still decides


class RecheckTests(unittest.TestCase):
    def test_a_pass_is_cached_until_size_or_mtime_changes(self):
        run, stat = Run(**{"powershell.exe": authenticode()}), Stat()
        v = windows(run, stat)
        v(WIN_PF, False)
        v(WIN_PF, False)
        self.assertEqual(len(run.calls), 1)
        stat.mtime = 2
        v(WIN_PF, False)
        self.assertEqual(len(run.calls), 2)
        stat.size = 99
        v(WIN_PF, False)
        self.assertEqual(len(run.calls), 3)

    def test_a_changed_binary_that_now_fails_is_refused(self):
        run, stat = Run(**{"powershell.exe": authenticode()}), Stat()
        v = windows(run, stat)
        v(WIN_PF, False)
        stat.size, run.answers["powershell.exe"] = 101, authenticode("HashMismatch")
        with self.assertRaises(cv.Refused):
            v(WIN_PF, False)
        with self.assertRaises(cv.Refused):  # a refusal is never remembered as a pass
            v(WIN_PF, False)
        self.assertEqual(len(run.calls), 3)

    def test_a_cached_pass_does_not_excuse_the_company_location(self):
        v = windows(Run(**{"powershell.exe": authenticode()}))
        v(WIN_LOCAL, company=False)
        with self.assertRaises(cv.Refused):
            v(WIN_LOCAL, company=True)

    def test_evidence_records_the_sha256_but_never_decides(self):
        v = windows(Run(**{"powershell.exe": authenticode("NotSigned", None)}))
        with self.assertRaises(cv.Refused):
            v(WIN_PF, False)
        self.assertEqual((v.last["sha256"], v.last["ok"]), ("ab", False))

    def test_linux_is_unchanged(self):
        run = Run()
        cv.Verifier("linux", run=run)("/opt/google/chrome/chrome", company=True)
        self.assertEqual(run.calls, [])


class LauncherHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_find_browser_skips_a_refused_candidate_and_ends_in_no_browser(self):
        seen = []

        def verify(path):
            seen.append(path)
            raise cv.Refused("the signer is not Google LLC")
        env = {n: str(self.tmp / n) for n in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")}
        with self.assertRaises(wl.LaunchError) as caught:
            wl.find_browser("win32", env=env, exists=lambda p: True, verify=verify)
        self.assertEqual((caught.exception.code, caught.exception.install), ("no_browser", True))
        self.assertEqual(caught.exception.detail, "the signer is not Google LLC")
        self.assertEqual(len(seen), 3)

    def test_company_local_app_data_refused_through_the_launcher(self):
        (self.tmp / "device.json").write_text(json.dumps({"owner_kind": "company"}))
        pf, local = str(self.tmp / "pf"), str(self.tmp / "local")
        run = Run(**{"powershell.exe": authenticode()})
        verifier = cv.Verifier("win32", run=run, env={"ProgramFiles": pf}, stat=Stat(), realpath=lambda p: p,
                               digest=lambda p: "ab")
        launcher = wl.Launcher(self.tmp, verifier=verifier)
        env = {"LocalAppData": local}
        company = wl.company_device(self.tmp)
        self.assertTrue(company)
        with self.assertRaises(wl.LaunchError) as caught:
            wl.find_browser("win32", env=env, exists=lambda p: True, verify=lambda p: launcher.verifier(p, company))
        self.assertEqual(caught.exception.code, "no_browser")
        self.assertEqual(run.calls, [])
        personal = wl.find_browser("win32", env=env, exists=lambda p: True, verify=lambda p: launcher.verifier(p, False))
        self.assertTrue(personal.startswith(local))
        self.assertEqual(len(run.calls), 1)
        both = wl.find_browser("win32", env={"ProgramFiles": pf, "LocalAppData": local}, exists=lambda p: True,
                               verify=lambda p: launcher.verifier(p, company))
        self.assertTrue(both.startswith(pf))

    def test_the_default_launcher_verifies(self):
        launcher = wl.Launcher(self.tmp)
        self.assertEqual(launcher.finder, launcher.verified_browser)
        self.assertIsInstance(launcher.verifier, cv.Verifier)

    def test_company_device_reads_either_record_and_fails_closed(self):
        self.assertFalse(wl.company_device(self.tmp))
        (self.tmp / "device.json").write_text(json.dumps({"owner_kind": "personal"}))
        self.assertFalse(wl.company_device(self.tmp))
        (self.tmp / "manifest.json").write_text(json.dumps({"device": {"owner_kind": "company"}}))
        self.assertTrue(wl.company_device(self.tmp))
        (self.tmp / "manifest.json").write_text("{broken")
        self.assertTrue(wl.company_device(self.tmp))
        (self.tmp / "manifest.json").write_text("[]")
        self.assertTrue(wl.company_device(self.tmp))


def _program_files_chrome():
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root and os.path.isfile(os.path.join(root, *wl.WINDOWS_TAIL)):
            return os.path.join(root, *wl.WINDOWS_TAIL)
    return None


@unittest.skipUnless(sys.platform == "win32", "real Authenticode checks run on Windows only")
class NativeWindowsTests(unittest.TestCase):
    """The real Get-AuthenticodeSignature against real files on the CI runner."""

    def test_installed_chrome_passes_as_a_company_device(self):
        chrome = _program_files_chrome()
        if not chrome:
            self.skipTest("no per-machine Google Chrome on this machine")
        v = cv.Verifier()
        v(chrome, company=True)
        self.assertTrue(v.last["ok"])
        self.assertEqual(len(v.last["sha256"]), 64)

    def test_a_binary_signed_by_someone_else_is_refused(self):
        with self.assertRaises(cv.Refused) as caught:
            cv.Verifier()(sys.executable, company=False)  # python.exe: signed, but not by Google
        print("\n  python.exe:", caught.exception)

    def test_an_unsigned_or_damaged_copy_is_refused(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        blank = os.path.join(tmp, "chrome.exe")
        with open(blank, "wb") as f:
            f.write(b"MZ" + b"\0" * 1024)
        with self.assertRaises(cv.Refused):
            cv.Verifier()(blank, company=False)
        chrome = _program_files_chrome()
        if chrome:
            cut = os.path.join(tmp, "cut.exe")
            with open(chrome, "rb") as src, open(cut, "wb") as dst:
                dst.write(src.read(os.path.getsize(chrome) // 2))
            with self.assertRaises(cv.Refused):
                cv.Verifier()(cut, company=False)


@unittest.skipUnless(sys.platform == "darwin", "real codesign and spctl checks run on macOS only")
class NativeMacTests(unittest.TestCase):
    def test_installed_chrome_passes(self):
        if not os.path.isfile(wl.MAC_BROWSERS[0]):
            self.skipTest("no Google Chrome in /Applications on this machine")
        info = os.stat("/Applications/Google Chrome.app")
        v = cv.Verifier()
        v(wl.MAC_BROWSERS[0], company=info.st_uid == 0)
        self.assertTrue(v.last["ok"])
        print("\n  Chrome.app owner uid:", info.st_uid)

    def test_an_app_signed_by_someone_else_is_refused(self):
        safari = "/Applications/Safari.app/Contents/MacOS/Safari"
        if not os.path.isfile(safari):
            self.skipTest("no Safari")
        with self.assertRaises(cv.Refused):
            cv.Verifier()(safari, company=False)


if __name__ == "__main__":
    unittest.main()
