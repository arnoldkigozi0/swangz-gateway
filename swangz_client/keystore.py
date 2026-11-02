"""Native device credentials. Errors deliberately contain no command output or secret.

No backend is installed or unlocked for the user. The caller owns the visible file fallback.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

SERVICE = "Swangz AI Hub"


class KeyStoreError(Exception):
    pass


class Unavailable(KeyStoreError):
    """The backend could not be started; no credential was written."""


def account(server, key_id):
    u = urlsplit(server)
    if (u.scheme not in ("https", "http") or not u.hostname or u.username or u.password
            or u.path or u.query or u.fragment or not re.fullmatch(r"[A-Za-z0-9_-]+", str(key_id))
            or any(ord(c) < 33 or c in '\\"' for c in server)):
        raise KeyStoreError("Invalid credential identity.")
    return u.netloc.lower() + "/" + str(key_id)


def check_secret(secret):
    if not isinstance(secret, str) or not secret or len(secret) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in secret):
        raise KeyStoreError("Invalid device credential.")
    return secret


def _run(argv, secret_input=None, run=None):
    try:
        return (run or subprocess.run)(argv, input=secret_input, capture_output=True, text=True,
                                       timeout=15, check=False)
    except FileNotFoundError:
        raise Unavailable("This device has no keychain service.") from None
    except (OSError, subprocess.SubprocessError):
        raise KeyStoreError("The device keychain could not complete the operation.") from None


class SecretService:
    name = "secret-service"

    def __init__(self, run=None):
        self.run = run

    def _call(self, action, server, key_id, secret=None):
        args = ["secret-tool", action]
        if action == "store":
            args += ["--label", SERVICE]
        return _run(args + ["service", "swangz", "account", account(server, key_id)], secret, self.run)

    def put(self, server, key_id, secret):
        if self._call("store", server, key_id, check_secret(secret)).returncode:
            raise KeyStoreError("Secret Service did not store the device credential.")

    def get(self, server, key_id):
        out = self._call("lookup", server, key_id)
        if out.returncode == 1 and not out.stdout and not out.stderr:
            return None
        if out.returncode:
            raise KeyStoreError("Secret Service could not read the device credential.")
        return check_secret(out.stdout.rstrip("\r\n"))

    def delete(self, server, key_id):
        out = self._call("clear", server, key_id)
        if out.returncode and not (out.returncode == 1 and not out.stdout and not out.stderr):
            raise KeyStoreError("Secret Service could not delete the device credential.")


class Keychain:
    name = "keychain"

    def __init__(self, run=None):
        self.run = run

    @staticmethod
    def _quote(value):
        # security's interactive command parser, not a shell. No command separators or controls.
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def put(self, server, key_id, secret):
        command = "add-generic-password -U -s {} -a {} -w {}\n".format(
            self._quote(SERVICE), self._quote(account(server, key_id)), self._quote(check_secret(secret)))
        out = _run(["/usr/bin/security", "-i"], command, self.run)
        if out.returncode:
            raise KeyStoreError("Keychain did not store the device credential.")
        # Interactive security can exit successfully after an individual command failed.
        # The caller MUST retrieve and compare before committing or deleting the legacy file.

    def get(self, server, key_id):
        out = _run(["/usr/bin/security", "find-generic-password", "-s", SERVICE,
                    "-a", account(server, key_id), "-w"], run=self.run)
        if out.returncode == 44:  # errSecItemNotFound, truncated to a process exit code
            return None
        if out.returncode:
            raise KeyStoreError("Keychain could not read the device credential.")
        return check_secret(out.stdout.rstrip("\r\n"))

    def delete(self, server, key_id):
        out = _run(["/usr/bin/security", "delete-generic-password", "-s", SERVICE,
                    "-a", account(server, key_id)], run=self.run)
        if out.returncode not in (0, 44):
            raise KeyStoreError("Keychain could not delete the device credential.")


class CREDENTIALW(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


class CredentialManager:
    name = "credential-manager"

    def __init__(self, library=None, last_error=None):
        try:
            self.lib = library if library is not None else ctypes.WinDLL("advapi32", use_last_error=True)
        except (AttributeError, OSError):
            raise Unavailable("Windows Credential Manager is unavailable.") from None
        self.last_error = last_error or ctypes.get_last_error
        pointer = ctypes.POINTER(CREDENTIALW)
        for name, args in (("CredWriteW", [pointer, wintypes.DWORD]),
                           ("CredReadW", [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]),
                           ("CredDeleteW", [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD])):
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, wintypes.BOOL
        self.lib.CredFree.argtypes, self.lib.CredFree.restype = [ctypes.c_void_p], None

    def _target(self, server, key_id):
        return SERVICE + ":" + account(server, key_id)

    def put(self, server, key_id, secret):
        raw = check_secret(secret).encode("utf-8")
        blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        cred = CREDENTIALW(Type=1, TargetName=self._target(server, key_id),
                           UserName=account(server, key_id), CredentialBlobSize=len(raw),
                           CredentialBlob=blob, Persist=2)  # LOCAL_MACHINE, never ENTERPRISE (roaming)
        try:
            if not self.lib.CredWriteW(ctypes.byref(cred), 0):
                raise KeyStoreError("Windows Credential Manager did not store the device credential.")
        finally:
            ctypes.memset(blob, 0, len(raw))

    def get(self, server, key_id):
        ptr = ctypes.POINTER(CREDENTIALW)()
        if not self.lib.CredReadW(self._target(server, key_id), 1, 0, ctypes.byref(ptr)):
            if self.last_error() == 1168:
                return None
            raise KeyStoreError("Windows Credential Manager could not read the device credential.")
        try:
            cred = ptr.contents
            if not 0 < cred.CredentialBlobSize <= 4096:
                raise KeyStoreError("Invalid stored device credential.")
            try:
                return check_secret(ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode("utf-8"))
            except UnicodeError:
                raise KeyStoreError("Invalid stored device credential.") from None
        finally:
            self.lib.CredFree(ptr)

    def delete(self, server, key_id):
        if not self.lib.CredDeleteW(self._target(server, key_id), 1, 0) and self.last_error() != 1168:
            raise KeyStoreError("Windows Credential Manager could not delete the device credential.")


def backend():
    if sys.platform == "win32":
        return CredentialManager()
    return Keychain() if sys.platform == "darwin" else SecretService()


def put(server, key_id, secret):
    return backend().put(server, key_id, secret)


def get(server, key_id):
    return backend().get(server, key_id)


def delete(server, key_id):
    return backend().delete(server, key_id)


def backend_name():
    return {"win32": "credential-manager", "darwin": "keychain"}.get(sys.platform, "secret-service")


def protect_windows_file(path):
    """Protected DACL: owner and SYSTEM only. Apply to the empty temporary file before writing."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                                                        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    adv.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    adv.SetFileSecurityW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW("D:P(A;;FA;;;OW)(A;;FA;;;SY)", 1,
                                                                  ctypes.byref(descriptor), None):
        raise KeyStoreError("Could not protect the local credential file.")
    try:
        if not adv.SetFileSecurityW(str(path), 0x80000004, descriptor):  # protected DACL
            raise KeyStoreError("Could not protect the local credential file.")
    finally:
        kernel.LocalFree(descriptor)


def write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".swangz-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            if os.name == "nt":
                protect_windows_file(name)
            else:
                os.fchmod(f.fileno(), 0o600)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def erase_file(path):
    """Best effort overwrite followed by unlink. SSDs, backups and journaling can retain old bytes."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return
    with os.fdopen(fd, "r+b") as f:
        if path.is_symlink() or not stat.S_ISREG(os.fstat(f.fileno()).st_mode) or os.fstat(f.fileno()).st_nlink != 1:
            raise KeyStoreError("Refused to erase a linked credential file.")
        size = os.fstat(f.fileno()).st_size
        if size > 64 * 1024:
            raise KeyStoreError("Unexpected credential file size.")
        f.write(b"\0" * size)
        f.flush()
        os.fsync(f.fileno())
    path.unlink()
