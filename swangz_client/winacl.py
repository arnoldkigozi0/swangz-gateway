"""Windows only: the current user's SID, and an owner-only ACL on the workspace folder (W3 threat note, T1).

Standard library `ctypes` over advapi32. Every failure is reported as "not verified", and the launcher refuses.
"""
import ctypes
from ctypes import wintypes

SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 0x1
DACL_SECURITY_INFORMATION = 0x4
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
TOKEN_QUERY = 0x8
TOKEN_USER = 1
ACL_REVISION = 2
ACL_SIZE_INFORMATION = 2
ACCESS_ALLOWED_ACE_TYPE = 0
OBJECT_INHERIT_ACE, CONTAINER_INHERIT_ACE = 0x1, 0x2
FILE_ALL_ACCESS = 0x1F01FF


class ACL_SIZE(ctypes.Structure):
    _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD), ("AclBytesFree", wintypes.DWORD)]


class ACE_HEADER(ctypes.Structure):
    _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte), ("AceSize", wintypes.WORD)]


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


def restrict(path):
    """Give the folder a protected DACL with one entry: the current user, full control, inherited by children."""
    advapi, kernel = _libs()
    buf, sid = _user_sid(advapi, kernel)
    size = ctypes.sizeof(ACL_SIZE) + 64 + advapi.GetLengthSid(sid)
    acl = ctypes.create_string_buffer(size)
    if not advapi.InitializeAcl(acl, size, ACL_REVISION):
        raise OSError("acl")
    if not advapi.AddAccessAllowedAceEx(acl, ACL_REVISION, OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE, FILE_ALL_ACCESS, sid):
        raise OSError("ace")
    err = advapi.SetNamedSecurityInfoW(path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                                       None, None, acl, None)
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
