"""D-026 A2-A4: is the Chrome this app is about to start really Google's, and installed where this device allows?

The publisher's signature is the authority, never a hash:
- Windows: Authenticode is Valid (WinVerifyTrust, chained to a trusted root, via Get-AuthenticodeSignature) and the
  signer certificate's parsed O attribute is exactly "Google LLC". The subject is read as DER and its attributes
  compared one by one, so "O=Google LLC Ltd" or a CN that merely contains "O=Google LLC" fails.
- macOS: codesign --verify --deep --strict against Google's designated requirement, and spctl accepts it to execute.
The SHA-256 is recorded as evidence only. A binary that passed is not rechecked until its size or mtime changes (A3).
A company device accepts only a per-machine Chrome (A4): under %ProgramFiles% on Windows, a root-owned app in
/Applications on macOS. Every refusal is LaunchError("no_browser"). Nothing is installed, downloaded or elevated.
Linux is unchanged: workspace_launcher's fixed-path ELF and ownership checks stay the rule there.
"""

import base64
import hashlib
import json
import ntpath
import os
import posixpath
import subprocess
import sys

GOOGLE_O = "Google LLC"
MAC_REQUIREMENT = (
    'anchor apple generic and identifier "com.google.Chrome" and certificate 1[field.1.2.840.113635.100.6.2.6] '
    'and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "EQHXZ8M8AV"')
CODESIGN = "/usr/bin/codesign"
SPCTL = "/usr/sbin/spctl"
TIMEOUT = 60
OID_O = "2.5.4.10"
# The path travels in an environment variable, never in the script text, so no file name can become PowerShell.
_PS_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "$s=Get-AuthenticodeSignature -LiteralPath $env:SWANGZ_CHROME_PATH;"
    "$n='';if($s.SignerCertificate){$n=[Convert]::ToBase64String($s.SignerCertificate.SubjectName.RawData)};"
    "[Console]::Out.Write((ConvertTo-Json -Compress @{status=[string]$s.Status;subject=$n}))")


class Refused(Exception):
    """Why a binary was refused, for the log; the person only ever sees no_browser."""


# ------------------------------------------------------------------ DER, just enough to read a Name

def _der(data, i):
    """-> (tag, start of content, end of content) for the element at i."""
    if i + 2 > len(data):
        raise ValueError("short")
    tag, length = data[i], data[i + 1]
    i += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or count > 4 or i + count > len(data):
            raise ValueError("length")
        length = int.from_bytes(data[i:i + count], "big")
        i += count
    if i + length > len(data):
        raise ValueError("overrun")
    return tag, i, i + length


def _children(data, start, end):
    out = []
    while start < end:
        tag, s, e = _der(data, start)
        out.append((tag, s, e))
        start = e
    if start != end:
        raise ValueError("trailing")
    return out


def _oid(raw):
    first = raw[0]
    parts, value = [min(first // 40, 2), first - 40 * min(first // 40, 2)], 0
    for b in raw[1:]:
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            parts.append(value)
            value = 0
    return ".".join(map(str, parts))


_STRINGS = {0x0C: "utf-8", 0x13: "ascii", 0x16: "ascii", 0x14: "latin-1", 0x1E: "utf-16-be"}


def name_attributes(der):
    """X.501 Name (DER) -> [(oid, value), ...] in order. ValueError on anything that is not a well-formed Name."""
    tag, s, e = _der(der, 0)
    if tag != 0x30 or e != len(der):
        raise ValueError("not a Name")
    out = []
    for set_tag, ss, se in _children(der, s, e):
        if set_tag != 0x31:
            raise ValueError("not an RDN")
        for seq_tag, qs, qe in _children(der, ss, se):
            parts = _children(der, qs, qe)
            if seq_tag != 0x30 or len(parts) != 2 or parts[0][0] != 0x06:
                raise ValueError("not an attribute")
            (_, os_, oe), (vtag, vs, ve) = parts
            if vtag not in _STRINGS:
                raise ValueError("value type")
            out.append((_oid(der[os_:oe]), der[vs:ve].decode(_STRINGS[vtag])))
    return out


def organisation_is_google(der):
    """Exactly one O attribute, and it equals "Google LLC" byte for byte."""
    try:
        orgs = [v for oid, v in name_attributes(der) if oid == OID_O]
    except (ValueError, UnicodeDecodeError, IndexError):
        return False
    return orgs == [GOOGLE_O]


# ------------------------------------------------------------------ the platform checks

def _said(done):
    """The tool's own error text, short, for the log (it names the file, never anything secret)."""
    text = (getattr(done, "stderr", b"") or b"").decode("utf-8", "replace").strip()
    return (": " + " ".join(text.split())[:300]) if text else ""


def _powershell(env):
    root = env.get("SystemRoot") or env.get("SYSTEMROOT") or r"C:\Windows"
    return os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def check_windows(binary, run=subprocess.run, env=None):
    env = dict(os.environ if env is None else env)
    env.pop("PSModulePath", None)  # PowerShell 7's module path breaks Windows PowerShell's own Security module
    env["SWANGZ_CHROME_PATH"] = binary
    try:
        done = run([_powershell(env), "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT], capture_output=True,
                   timeout=TIMEOUT, env=env, shell=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        raise Refused("the signature could not be read") from None
    try:
        answer = json.loads(done.stdout.decode("utf-8", "replace") or "null")
    except ValueError:
        raise Refused("the signature could not be read" + _said(done)) from None
    if done.returncode != 0 or not isinstance(answer, dict):
        raise Refused("the signature could not be read" + _said(done))
    if answer.get("status") != "Valid":
        raise Refused("Authenticode status %r" % answer.get("status"))
    try:
        subject = base64.b64decode(answer.get("subject") or "", validate=True)
    except (ValueError, TypeError):
        raise Refused("unreadable signer") from None
    if not organisation_is_google(subject):
        raise Refused("the signer is not Google LLC")


def mac_app(binary):
    """.../Google Chrome.app/Contents/MacOS/Google Chrome -> .../Google Chrome.app"""
    at = binary.find(".app/Contents/MacOS/")
    if at < 0:
        raise Refused("not inside an application bundle")
    return binary[:at + 4]


def check_mac(binary, run=subprocess.run):
    app = mac_app(binary)
    for argv in ([CODESIGN, "--verify", "--deep", "--strict", "-R=" + MAC_REQUIREMENT, app],
                 [SPCTL, "--assess", "--type", "execute", app]):
        try:
            done = run(argv, capture_output=True, timeout=TIMEOUT, shell=False, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            raise Refused(os.path.basename(argv[0]) + " could not run") from None
        if done.returncode != 0:
            raise Refused(os.path.basename(argv[0]) + " refused it" + _said(done))


# ------------------------------------------------------------------ A4: where it may be installed

def _under(path, root, flavour=ntpath):
    try:
        path, root = flavour.normcase(path), flavour.normcase(root)
        return flavour.commonpath([path, root]) == root
    except ValueError:  # different drives
        return False


def _absolute(root):
    # On Windows only a drive-rooted path counts; elsewhere (tests on a Linux or macOS host) a POSIX root does too.
    return ntpath.isabs(root) and (os.name != "nt" or bool(ntpath.splitdrive(root)[0])) or (
        os.name != "nt" and posixpath.isabs(root))


def check_location(binary, platform, company, env=None, stat=os.stat, realpath=os.path.realpath):
    if not company:
        return
    if platform in ("win32", "cygwin"):
        env = os.environ if env is None else env
        real = realpath(binary)
        roots = [env.get(n) for n in ("ProgramFiles", "ProgramFiles(x86)")]
        if not any(r and _absolute(r) and _under(real, realpath(r)) for r in roots):
            raise Refused("a company device uses only a per-machine Chrome")
    elif platform == "darwin":
        app = mac_app(binary)
        if posixpath.dirname(posixpath.normpath(app)) != "/Applications":
            raise Refused("a company device uses only Chrome in /Applications")
        if any(stat(p).st_uid != 0 for p in (app, binary)):
            raise Refused("a company device uses only a root-owned Chrome")


# ------------------------------------------------------------------ A3: verify once per binary version

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class Verifier:
    """Checks a browser binary before first use and again whenever its size or mtime changes. Only a pass is
    remembered; a refusal is checked afresh next time. `last` holds the evidence of the most recent full check."""

    def __init__(self, platform=None, run=subprocess.run, env=None, stat=os.stat, realpath=os.path.realpath,
                 digest=sha256):
        self.platform = platform or sys.platform
        self.run, self.env, self.stat, self.realpath, self.digest = run, env, stat, realpath, digest
        self.passed = {}
        self.last = None

    def applies(self):
        return self.platform in ("win32", "cygwin", "darwin")

    def __call__(self, binary, company):
        """-> None when the binary may start; raises Refused otherwise."""
        if not self.applies():
            return
        check_location(binary, self.platform, company, self.env, self.stat, self.realpath)
        try:
            info = self.stat(binary)
        except OSError:
            raise Refused("missing") from None
        key = (info.st_size, info.st_mtime_ns)
        if self.passed.get(binary) == key:
            return
        self.passed.pop(binary, None)
        evidence = {"path": binary, "size": info.st_size, "mtime_ns": info.st_mtime_ns, "ok": False}
        self.last = evidence
        try:
            evidence["sha256"] = self.digest(binary)
        except OSError:
            raise Refused("unreadable") from None
        if self.platform == "darwin":
            check_mac(binary, self.run)
        else:
            check_windows(binary, self.run, self.env)
        evidence["ok"] = True
        self.passed[binary] = key
