"""Inert, tests-only profile preparation. No browser, credentials or lifecycle hooks.

Directories separate accidental sessions, not people sharing an OS login or administrators.
Windows reparse points are refused; ACL not verified by the app.
"""
import json
import math
import os
import re
import secrets
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from .core import normalise_server

ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
FOLDER = re.compile(r"[0-9a-f]{32}\Z")
SPECIAL = re.compile(r"\.(tmp|retired)-[0-9a-f]{32}\Z")
MARKER = ".swangz-profile.json"
STALE = 180
FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)


class ProfileError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ProfileError("owner_invalid")
    return value


def _origin(value):
    try:
        if not isinstance(value, str) or re.search(r"[\x00-\x20\\]", value.strip()):
            raise ValueError
        u = urlsplit(normalise_server(value))
        host = u.hostname.lower()
        if u.scheme != "https" and host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError
        port = u.port
        host = "[" + host + "]" if ":" in host else host
        if port is not None and port != (443 if u.scheme == "https" else 80):
            host += ":" + str(port)
        return u.scheme + "://" + host
    except (ValueError, AttributeError, TypeError):
        raise ProfileError("origin_invalid") from None


def _os_user():
    if os.name == "nt":
        domain, user = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
        if not domain or not user:
            raise ProfileError("os_user_unavailable")
        return domain + "\\" + user
    return os.getuid()


class Owner:
    def __init__(self, origin, person_id, device_id, seat_id=None, seat_generation=None):
        if seat_id is None:
            if seat_generation is not None:
                raise ProfileError("owner_invalid")
            seat = None
        else:
            if type(seat_generation) is not int or seat_generation < 1:
                raise ProfileError("owner_invalid")
            seat = {"id": _identifier(seat_id), "generation": seat_generation}
        self.fields = {"origin": _origin(origin), "person_id": _identifier(person_id),
                       "device_id": _identifier(device_id), "os_user": _os_user(), "seat": seat}


def _reparse(info):
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _check(path, directory=True, data=False):
    info = Path(path).lstat()
    if stat.S_ISLNK(info.st_mode) or _reparse(info):
        raise ProfileError("unsafe_link")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ProfileError("unsafe_type")
    if os.name != "nt":
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != os.getuid() or (mode & 0o022 if data else mode != (0o700 if directory else 0o600)):
            raise ProfileError("unsafe_permissions")
    if not directory and info.st_nlink != 1:
        raise ProfileError("unsafe_hardlink")
    return info


def _same(a, b):
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _purge_fd(fd):
    """POSIX removal relative to open directories: never descend through a planted link."""
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode) and not _reparse(info):
            child = os.open(name, FLAGS, dir_fd=fd)
            try:
                if not _same(info, os.fstat(child)):
                    raise ProfileError("path_changed")
                _purge_fd(child)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)


def _purge(path):
    info = _check(path)
    if os.name != "nt":
        fd = os.open(path, FLAGS)
        try:
            if not _same(info, os.fstat(fd)):
                raise ProfileError("path_changed")
            _purge_fd(fd)
        finally:
            os.close(fd)
    else:
        # Junctions are removed as entries, never traversed. Native Windows coverage is required.
        for entry in path.iterdir():
            child = entry.lstat()
            if _reparse(child) or stat.S_ISLNK(child.st_mode):
                if stat.S_ISDIR(child.st_mode):
                    entry.rmdir()
                else:
                    entry.unlink()
            elif stat.S_ISDIR(child.st_mode):
                _purge(entry)
            else:
                entry.unlink()
    path.rmdir()


class Profiles:
    def __init__(self, data):
        self.data = Path(data)
        self.root = self.data / "browser-profiles"

    def _root(self):
        _check(self.data, data=True)  # never create/chmod anything outside our root
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _check(self.root)

    def _read_file(self, path):
        info = _check(path, directory=False)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f:
            if not _same(info, os.fstat(f.fileno())):
                raise ProfileError("path_changed")
            raw = f.read(65537)
        if len(raw) > 65536:
            raise ProfileError("marker_invalid")
        return raw

    def _marker(self, path):
        try:
            _check(path)
            m = json.loads(self._read_file(path / MARKER))
            if set(m) != {"version", "profile_id", "origin", "person_id", "device_id", "os_user", "seat", "state", "created"}:
                raise ValueError
            if type(m["version"]) is not int or m["version"] != 1 or m["profile_id"] != path.name or not FOLDER.fullmatch(path.name):
                raise ValueError
            if m["state"] != "prepared" or type(m["created"]) not in (int, float) or not math.isfinite(m["created"]) or m["created"] <= 0:
                raise ValueError
            seat = m["seat"]
            if seat is not None and (not isinstance(seat, dict) or set(seat) != {"id", "generation"}):
                raise ValueError
            owner = Owner(m["origin"], m["person_id"], m["device_id"], seat["id"] if seat else None, seat["generation"] if seat else None)
            if any(m[k] != v or type(m[k]) is not type(v) for k, v in owner.fields.items()):
                raise ValueError
            return m
        except (OSError, ValueError, TypeError, KeyError, ProfileError):
            raise ProfileError("marker_invalid") from None

    @contextmanager
    def _locked(self):
        self._root()
        path = self.root / ".lock"
        mine = json.dumps({"pid": os.getpid(), "at": time.time(), "nonce": secrets.token_hex(16)}).encode()
        for _ in range(3):
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                info = _check(path, directory=False)
                seen = self._read_file(path)
                stale = time.time() - info.st_mtime > STALE
                try:
                    owner = json.loads(seen)
                    if type(owner["pid"]) is int and owner["pid"] > 0 and os.name != "nt":
                        try:
                            os.kill(owner["pid"], 0)
                        except ProcessLookupError:
                            stale = True
                        except PermissionError:
                            pass
                except (ValueError, KeyError, TypeError):
                    pass
                if not stale:
                    raise ProfileError("busy")
                if _same(info, path.lstat()) and self._read_file(path) == seen:
                    path.unlink()
                continue
            with os.fdopen(fd, "wb") as f:
                f.write(mine)
                f.flush()
                os.fsync(f.fileno())
            break
        else:
            raise ProfileError("busy")
        try:
            _check(self.data, data=True)
            _check(self.root)
            yield
        finally:
            try:
                if self._read_file(path) == mine:
                    path.unlink()
            except (OSError, ProfileError):
                pass

    def _cleanup(self):
        skipped = []
        for path in self.root.iterdir():
            match = SPECIAL.fullmatch(path.name)
            if not match:
                continue
            try:
                info = _check(path)
                if match[1] == "retired" or time.time() - info.st_mtime > STALE:
                    _purge(path)
            except (ProfileError, OSError) as exc:
                skipped.append({"name": path.name, "reason": getattr(exc, "code", "cleanup_failed")})
        return skipped

    def _owner(self, owner):
        if not isinstance(owner, Owner):
            raise ProfileError("owner_invalid")
        # Revalidate a caller-mutated owner; no arbitrary marker keys are ever persisted.
        f = owner.fields
        seat = f.get("seat")
        try:
            clean = Owner(f["origin"], f["person_id"], f["device_id"], seat["id"] if seat else None, seat["generation"] if seat else None).fields
            if f != clean or set(f) != set(clean):
                raise ValueError
            return clean
        except (KeyError, TypeError, ValueError):
            raise ProfileError("owner_invalid") from None

    def prepare(self, owner):
        fields = self._owner(owner)
        with self._locked():
            self._cleanup()
            matches = []
            for path in self.root.iterdir():
                if not FOLDER.fullmatch(path.name):
                    continue
                try:
                    m = self._marker(path)
                except ProfileError:
                    continue
                if all(m[k] == v for k, v in fields.items()):
                    matches.append(path)
                elif fields["seat"] and m["seat"] and m["seat"]["id"] == fields["seat"]["id"] and all(m[k] == fields[k] for k in fields if k != "seat"):
                    raise ProfileError("superseded_present" if m["seat"]["generation"] < fields["seat"]["generation"] else "newer_generation_present")
            if len(matches) > 1:
                raise ProfileError("duplicate_profiles")
            if matches:
                return matches[0]
            profile_id = secrets.token_hex(16)
            stage = self.root / (".tmp-" + profile_id)
            stage.mkdir(mode=0o700)
            _check(stage)
            marker = {"version": 1, "profile_id": profile_id, **fields, "state": "prepared", "created": time.time()}
            temp = stage / (".marker-" + secrets.token_hex(16))
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(marker, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, stage / MARKER)
            _check(stage / MARKER, directory=False)
            target = self.root / profile_id
            if target.exists() or target.is_symlink():
                raise ProfileError("profile_collision")
            os.rename(stage, target)
            return target

    def _retire(self, path):
        _check(path)
        retired = self.root / (".retired-" + secrets.token_hex(16))
        os.rename(path, retired)
        _purge(retired)

    def retire(self, profile_id, expected_owner):
        if not isinstance(profile_id, str) or not FOLDER.fullmatch(profile_id):
            raise ProfileError("profile_invalid")
        fields = self._owner(expected_owner)
        with self._locked():
            self._cleanup()
            path = self.root / profile_id
            m = self._marker(path)
            if any(m[k] != v for k, v in fields.items()):
                raise ProfileError("owner_mismatch")
            self._retire(path)

    def retire_owner(self, expected_owner):
        return self._retire_many(self._owner(expected_owner))

    def retire_all(self):
        """Explicit app-root cleanup, including safe profile folders with invalid/absent markers."""
        return self._retire_many(None)

    def _retire_many(self, fields):
        retired, skipped = [], []
        with self._locked():
            skipped.extend(self._cleanup())
            for path in list(self.root.iterdir()):
                if path.name == ".lock" or SPECIAL.fullmatch(path.name):
                    continue
                try:
                    if not FOLDER.fullmatch(path.name):
                        raise ProfileError("unknown_entry")
                    _check(path)
                    if fields is not None:
                        m = self._marker(path)
                        if any(m[k] != v for k, v in fields.items()):
                            continue
                    self._retire(path)
                    retired.append(path.name)
                except (ProfileError, OSError) as exc:
                    skipped.append({"name": path.name, "reason": getattr(exc, "code", "retire_failed")})
        return {"retired": retired, "skipped": skipped, "complete": not skipped}
