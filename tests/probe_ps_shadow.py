"""Probe experiment (not for merge): can a module in the person's Documents folder answer Chrome's signature check?"""
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())
from swangz_client import chrome_verify as cv


def der(tag, body):
    return bytes([tag, len(body)]) + body


NAME = der(0x30, der(0x31, der(0x30, der(0x06, bytes([0x55, 4, 10])) + der(0x13, b"Google LLC"))))
assert cv.organisation_is_google(NAME)
import base64
B64 = base64.b64encode(NAME).decode()
FOLDERS = cv.windows_folders()
SHELL = cv._powershell(FOLDERS)
CHROME = os.path.join(FOLDERS["ProgramFiles"], "Google", "Chrome", "Application", "chrome.exe")
ORIGINAL = cv._PS_SCRIPT


def attempt(label, target):
    try:
        cv.check_windows(target)
        print(label, os.path.basename(target), "-> ACCEPTED as Google")
    except cv.Refused as exc:
        print(label, os.path.basename(target), "-> refused:", exc)


def run(stage):
    attempt(stage, sys.executable)
    attempt(stage, CHROME)


run("[head, clean]")
docs = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-Command",
                       "[Environment]::GetFolderPath('MyDocuments')"], capture_output=True, text=True).stdout.strip()
mod = Path(docs) / "WindowsPowerShell" / "Modules" / "ZzProbe"
print("user module folder existed before:", mod.parent.exists())
mod.mkdir(parents=True)
try:
    (mod / "ZzProbe.psm1").write_text(
        "function Get-AuthenticodeSignature { param($LiteralPath) [pscustomobject]@{Status='Valid';"
        "SignerCertificate=[pscustomobject]@{SubjectName=[pscustomobject]@{RawData="
        "[Convert]::FromBase64String('%s')}}} }\n" % B64, encoding="ascii")
    (mod / "ZzProbe.psd1").write_text(
        "@{ ModuleVersion='99.0'; RootModule='ZzProbe.psm1'; FunctionsToExport=@('Get-AuthenticodeSignature') }\n",
        encoding="ascii")
    run("[head, module planted in Documents]")
    cv._PS_SCRIPT = "$env:PSModulePath=\"$PSHOME\\Modules\";" + ORIGINAL
    run("[suggested fix, module still planted]")
finally:
    shutil.rmtree(mod)
cv._PS_SCRIPT = ORIGINAL
run("[head, module removed]")
