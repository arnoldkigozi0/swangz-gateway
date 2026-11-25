"""Windows only: the current user's SID, an owner-only ACL on the workspace folder (W3 threat note, T1), and the file
calls that deleting a profile folder safely needs.

Standard library `ctypes` over advapi32. Every failure is reported as "not verified", and the launcher refuses.
"""
import ctypes
import os
import uuid
from ctypes import wintypes

from .shell import SYSTEM_SIDS, USER_TOKENS

SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 0x1
DACL_SECURITY_INFORMATION = 0x4
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
ADMINISTRATORS_SID = "S-1-5-32-544"  # the group every administrator on the computer shares
READ_CONTROL, WRITE_OWNER = 0x20000, 0x80000
FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT = 0x10, 0x400
FOLDERID_LOCAL_APP_DATA = "f1b32785-6fba-4fcf-9d55-7b8e7f157091"
TOKEN_QUERY = 0x8
TOKEN_USER = 1
TOKEN_ELEVATION_TYPE = 18  # TOKEN_INFORMATION_CLASS: 1 default, 2 full, 3 limited
ACL_REVISION = 2
ACL_SIZE_INFORMATION = 2
ACCESS_ALLOWED_ACE_TYPE = 0
OBJECT_INHERIT_ACE, CONTAINER_INHERIT_ACE = 0x1, 0x2
FILE_ALL_ACCESS = 0x1F01FF
FILE_LIST_DIRECTORY, FILE_READ_ATTRIBUTES = 0x1, 0x80
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2  # no FILE_SHARE_DELETE: a held folder cannot be renamed or replaced
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT = 0x02000000, 0x00200000
DELETE, FILE_WRITE_ATTRIBUTES = 0x10000, 0x100
# FILE_INFO_BY_HANDLE_CLASS
FILE_BASIC_INFO_CLASS, FILE_DISPOSITION_INFO_CLASS, FILE_DISPOSITION_INFO_EX_CLASS = 0, 4, 21
FILE_DISPOSITION_DELETE, FILE_DISPOSITION_POSIX_SEMANTICS = 0x1, 0x2
SETTABLE_ATTRIBUTES = 0x1 | 0x2 | 0x4 | 0x20 | 0x100 | 0x1000 | 0x2000  # read-only … not content indexed


class ACL_SIZE(ctypes.Structure):
    _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD), ("AclBytesFree", wintypes.DWORD)]


class ACE_HEADER(ctypes.Structure):
    _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte), ("AceSize", wintypes.WORD)]


class FILE_BASIC_INFO(ctypes.Structure):
    _fields_ = [("Times", ctypes.c_longlong * 4), ("FileAttributes", wintypes.DWORD)]  # a time of 0 stays as it is


class ACCESS_ACE(ctypes.Structure):
    _fields_ = [("Header", ACE_HEADER), ("Mask", wintypes.DWORD), ("SidStart", wintypes.DWORD)]


def _libs():
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                                             ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
                                             ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    advapi.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
                                             ctypes.c_void_p, ctypes.c_void_p]
    advapi.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]
    advapi.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi.AddAccessAllowedAceEx.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return advapi, kernel


def _user_sid(advapi, kernel):
    """-> a ctypes buffer holding TOKEN_USER; its first pointer is the SID."""
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise OSError("token")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, TOKEN_USER, buf, size, ctypes.byref(size)):
            raise OSError("token information")
        return buf, ctypes.c_void_p.from_buffer(buf).value
    finally:
        kernel.CloseHandle(token)


def token_elevation_type():
    """-> 1 default (no split token: UAC off, built-in Administrator, or a plain user), 2 full (raised by UAC),
    3 limited. Raises OSError when Windows will not say."""
    advapi, kernel = _libs()
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise OSError("token")
    try:
        kind, size = wintypes.DWORD(), wintypes.DWORD()
        if not advapi.GetTokenInformation(token, TOKEN_ELEVATION_TYPE, ctypes.byref(kind), ctypes.sizeof(kind),
                                          ctypes.byref(size)):
            raise OSError("token information")
        return kind.value
    finally:
        kernel.CloseHandle(token)


def current_sid():
    """-> the current user's SID as text ("S-1-5-21-…")."""
    advapi, kernel = _libs()
    buf, sid = _user_sid(advapi, kernel)
    text = wintypes.LPWSTR()
    if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise OSError("sid")
    try:
        return text.value
    finally:
        kernel.LocalFree(text)


def owner_sid(path):
    """-> the SID, as text, of the file or folder's owner. Raises FileNotFoundError when it is not there and OSError
    when Windows will not say."""
    advapi, kernel = _libs()
    owner, sd, text = ctypes.c_void_p(), ctypes.c_void_p(), wintypes.LPWSTR()
    err = advapi.GetNamedSecurityInfoW(path, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION, ctypes.byref(owner),
                                       None, None, None, ctypes.byref(sd))
    if err in (2, 3):  # file or path not found
        raise FileNotFoundError(path)
    if err:
        raise OSError(err, "owner")
    try:
        if not owner.value or not advapi.ConvertSidToStringSidW(owner, ctypes.byref(text)):
            raise OSError("owner sid")
        try:
            return text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.LocalFree(sd)


class GUID(ctypes.Structure):
    _fields_ = [("Data", ctypes.c_ubyte * 16)]


def local_app_data():
    """-> this person's own AppData\\Local as Windows has it (SHGetKnownFolderPath), never an environment variable."""
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    folder = GUID.from_buffer_copy(uuid.UUID(FOLDERID_LOCAL_APP_DATA).bytes_le)
    found = ctypes.c_void_p()
    try:
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(found)) or not found.value:
            raise OSError("known folder")
        return ctypes.wstring_at(found.value)
    finally:
        ole32.CoTaskMemFree(found)


def _open_for_owner(path):
    return _open_itself(path, READ_CONTROL | WRITE_OWNER | FILE_READ_ATTRIBUTES)


def _attributes(fd):
    return os.fstat(fd).st_file_attributes


def _owner_of_open(fd):
    """-> the owner SID, as text, of what `fd` is open on."""
    import msvcrt
    advapi, kernel = _libs()
    advapi.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD] + [ctypes.POINTER(ctypes.c_void_p)] * 5
    advapi.GetSecurityInfo.restype = wintypes.DWORD
    owner, sd, text = ctypes.c_void_p(), ctypes.c_void_p(), wintypes.LPWSTR()
    err = advapi.GetSecurityInfo(msvcrt.get_osfhandle(fd), SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION,
                                 ctypes.byref(owner), None, None, None, ctypes.byref(sd))
    if err:
        raise OSError(err, "owner")
    try:
        if not owner.value or not advapi.ConvertSidToStringSidW(owner, ctypes.byref(text)):
            raise OSError("owner sid")
        try:
            return text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.LocalFree(sd)


def _set_owner_of_open(fd):
    """Make the current user the owner of what `fd` is open on. The DACL is not touched, no privilege is enabled."""
    import msvcrt
    advapi, kernel = _libs()
    advapi.SetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD] + [ctypes.c_void_p] * 4
    advapi.SetSecurityInfo.restype = wintypes.DWORD
    buf, sid = _user_sid(advapi, kernel)
    err = advapi.SetSecurityInfo(msvcrt.get_osfhandle(fd), SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION, sid, None, None, None)
    if err:
        raise OSError(err, "set owner")


def claim_data_folder(path):
    """Make the person the owner of the app's data folder when it is owned by the Administrators group, as a folder
    made with an administrator's token is (docs/DECISIONS.md D-026, 25 Nov ruling on #353). Only the app's fixed folder
    under the person's own profile, a real folder, a token `cleanup` would accept, and that one owner: any other is
    never taken. -> None when nothing was to be changed, else {"before", "after", "outcome": "claimed" or "failed"}.
    Whatever this does not manage, `shell.cleanup_refusal` then refuses."""
    try:
        user = current_sid()
        if token_elevation_type() not in USER_TOKENS or not user or user in SYSTEM_SIDS:
            return None
        fixed = os.path.join(local_app_data(), "Swangz")
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(fixed)):
            return None
        fd = _open_for_owner(str(path))
    except OSError:
        return None
    try:
        attributes = _attributes(fd)
        if not attributes & FILE_ATTRIBUTE_DIRECTORY or attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            return None
        before = _owner_of_open(fd)
        if before != ADMINISTRATORS_SID:
            return None
        try:
            _set_owner_of_open(fd)  # on the checked handle: the path cannot be swapped between check and change
            after = _owner_of_open(fd)
        except OSError:
            after = before
        return {"before": before, "after": after, "outcome": "claimed" if after == user else "failed"}
    except OSError:
        return None
    finally:
        os.close(fd)


def restrict(path):
    """Make the current user the folder's owner and give it a protected DACL with one entry: the current user, full
    control, inherited by children. Setting the owner matters for administrators: a folder an elevated (or
    administrator-group) process creates is owned by BUILTIN\\Administrators, not by the user, and owner_only
    would then refuse it for good."""
    advapi, kernel = _libs()
    buf, sid = _user_sid(advapi, kernel)
    size = ctypes.sizeof(ACL_SIZE) + 64 + advapi.GetLengthSid(sid)
    acl = ctypes.create_string_buffer(size)
    if not advapi.InitializeAcl(acl, size, ACL_REVISION):
        raise OSError("acl")
    if not advapi.AddAccessAllowedAceEx(acl, ACL_REVISION, OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE, FILE_ALL_ACCESS, sid):
        raise OSError("ace")
    err = advapi.SetNamedSecurityInfoW(path, SE_FILE_OBJECT,
                                       OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                                       sid, None, acl, None)
    if err:
        raise OSError(err, "set security")


def owner_only(path):
    """True only when the folder's owner is the current user and every DACL entry is an allow entry for that user.
    A NULL DACL (everyone), any other SID, any deny entry or anything unreadable -> False."""
    try:
        advapi, kernel = _libs()
        buf, me = _user_sid(advapi, kernel)
        owner, dacl, sd = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        if advapi.GetNamedSecurityInfoW(path, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                                        ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(sd)):
            return False
        try:
            if not dacl.value or not owner.value or not advapi.EqualSid(owner, me):
                return False
            info = ACL_SIZE()
            if not advapi.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), ACL_SIZE_INFORMATION) or info.AceCount < 1:
                return False
            for i in range(info.AceCount):
                ace = ctypes.c_void_p()
                if not advapi.GetAce(dacl, i, ctypes.byref(ace)):
                    return False
                entry = ACCESS_ACE.from_address(ace.value)
                if entry.Header.AceType != ACCESS_ALLOWED_ACE_TYPE:
                    return False
                if not advapi.EqualSid(ace.value + ACCESS_ACE.SidStart.offset, me):
                    return False
            return True
        finally:
            kernel.LocalFree(sd)
    except Exception:
        return False


def _open_itself(path, access):
    """-> a file descriptor on the entry `path` names: a junction or link is opened, not followed. While it is open
    nobody else can rename or delete that entry. Raises OSError, also when someone else holds it against this."""
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING,
                                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except OSError:
        kernel.CloseHandle(handle)
        raise


def hold_folder(path):
    """-> a file descriptor that holds the folder while its entries are listed and removed."""
    return _open_itself(path, FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES)


def open_entry(path):
    """-> a file descriptor through which one entry is checked, changed and deleted."""
    return _open_itself(path, DELETE | FILE_READ_ATTRIBUTES | FILE_WRITE_ATTRIBUTES)


def _set_information(fd, kind, info):
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(fd), kind, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())


def delete_open(fd):
    """Delete what `fd` (from open_entry) is open on. A folder must be empty; a read-only entry raises
    PermissionError. The name goes when the descriptor is closed."""
    try:  # POSIX semantics, as os.unlink has: the name goes even while someone else still has the file open
        _set_information(fd, FILE_DISPOSITION_INFO_EX_CLASS,
                         wintypes.DWORD(FILE_DISPOSITION_DELETE | FILE_DISPOSITION_POSIX_SEMANTICS))
    except OSError as exc:
        if exc.winerror not in (1, 50, 87):  # a file system that has no such call
            raise
        _set_information(fd, FILE_DISPOSITION_INFO_CLASS, ctypes.c_ubyte(1))


def set_open_attributes(fd, attributes):
    """Set the attributes of what `fd` (from open_entry) is open on."""
    info = FILE_BASIC_INFO()
    info.FileAttributes = attributes & SETTABLE_ATTRIBUTES or 0x80  # 0x80 = FILE_ATTRIBUTE_NORMAL; 0 means "keep"
    _set_information(fd, FILE_BASIC_INFO_CLASS, info)
