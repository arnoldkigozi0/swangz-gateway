"""Workspace profile folders. Used only by `workspace_launcher.py` (W3); no browser, credentials or lifecycle hooks here.

Directories separate accidental sessions, not people sharing an OS login or administrators.
Windows reparse points are refused; the launcher sets and verifies an owner-only ACL (`winacl.py`) before launch,
and `os_user` is the user's SID on Windows, the uid elsewhere.
"""
import json
import errno
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
_WINDOWS = os.name == "nt"
FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)


KEYS_V1 = frozenset({"version", "profile_id", "origin", "person_id", "device_id", "os_user", "seat", "state", "created"})


def _generation_ok(value):
    """W4 ruling 3: an int >= 1 that is not a bool."""
    return type(value) is int and value >= 1


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
    if _WINDOWS:
        try:
            from .winacl import current_sid
            sid = current_sid()
        except Exception:
            sid = None
        if not isinstance(sid, str) or not re.fullmatch(r"S-1-[0-9-]{1,180}", sid):
            raise ProfileError("os_user_unavailable")
        return sid
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
    if not _WINDOWS:
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != os.getuid() or (mode & 0o022 if data else mode != (0o700 if directory else 0o600)):
            raise ProfileError("unsafe_permissions")
    if not directory and info.st_nlink != 1:
        raise ProfileError("unsafe_hardlink")
    return info


def _same(a, b):
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _before_open(path):
    """Does nothing. Tests replace it to change a checked folder before it is opened."""


def _before_delete(path):
    """Does nothing. Tests replace it to change a listed entry before Windows opens it for deletion."""


def _inside(path, root):
    """True when the path, with every link resolved, is still below the resolved root."""
    real = os.path.normcase(os.path.realpath(path))
    return real.startswith(os.path.join(os.path.normcase(os.path.realpath(root)), ""))


def _purge_fd(fd, path):
    """POSIX removal relative to open directories: never descend through a planted link."""
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            _before_open(os.path.join(path, name))
            try:
                child = os.open(name, FLAGS, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):  # it became a link or a file after the check
                    raise ProfileError("path_changed") from None
                raise
            try:
                if not _same(info, os.fstat(child)):
                    raise ProfileError("path_changed")
                _purge_fd(child, os.path.join(path, name))
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)


def _extended(path):
    r"""The Windows form of an absolute path that is not cut at 260 characters (\\?\)."""
    full = os.path.abspath(path)
    if full.startswith("\\\\?\\"):
        return full
    return "\\\\?\\UNC\\" + full[2:] if full.startswith("\\\\") else "\\\\?\\" + full


def _remove_windows(path, info):
    """Remove one entry, last seen as `info`. It is opened as itself (a link or junction is never followed), then
    checked and deleted through that one handle, so nothing swapped under the name afterwards is acted on."""
    from .winacl import delete_open, open_entry, set_open_attributes
    _before_delete(path)
    fd = open_entry(path)
    try:
        held = os.fstat(fd)
        if stat.S_ISDIR(held.st_mode) and not _reparse(held) and not _same(info, held):
            raise ProfileError("path_changed")  # a real folder goes only if it is the one that was seen
        try:
            delete_open(fd)
        except PermissionError:
            attributes = getattr(held, "st_file_attributes", 0)
            if not attributes & stat.FILE_ATTRIBUTE_READONLY:
                raise
            if _reparse(held):
                # Never change a link's attributes: it stays and is reported.
                raise ProfileError("readonly_link") from None
            # The read-only bit belongs to the file, not to this name: leave a file that also lives somewhere else alone.
            if not stat.S_ISDIR(held.st_mode) and held.st_nlink > 1:
                raise ProfileError("shared_file") from None
            set_open_attributes(fd, attributes & ~stat.FILE_ATTRIBUTE_READONLY)
            delete_open(fd)
    finally:
        os.close(fd)


def _purge_windows(path, info, root):
    """Windows removal, entry by entry. Each folder is held open without delete sharing while its entries go, so it
    cannot be renamed or replaced meanwhile. A reparse point is never entered. An entry that cannot be removed (in
    use) does not stop the others; its error is raised at the end."""
    from .winacl import hold_folder
    _before_open(path)
    fd = hold_folder(path)
    failed = None
    try:
        held = os.fstat(fd)
        if _reparse(held) or not stat.S_ISDIR(held.st_mode) or not _same(info, held) or not _inside(path, root):
            raise ProfileError("path_changed")
        for name in os.listdir(path):
            child = os.path.join(path, name)
            try:
                seen = os.lstat(child)
                if stat.S_ISDIR(seen.st_mode) and not _reparse(seen) and not stat.S_ISLNK(seen.st_mode):
                    _purge_windows(child, seen, root)
                else:
                    _remove_windows(child, seen)
            except FileNotFoundError:
                continue
            except OSError as exc:
                failed = failed or exc
            except ProfileError as exc:
                if exc.code == "path_changed":
                    raise
                failed = failed or exc
    finally:
        os.close(fd)
    if failed:
        raise failed
    _remove_windows(path, info)


def _purge(path):
    """Delete one folder of the profiles root, and nothing that a link inside it points at."""
    _remove_tree(path, _check(path))


def _remove_tree(path, info):
    """Delete the real folder `path`, last seen as `info`, link-safely."""
    if not _inside(path, path.parent):
        raise ProfileError("unsafe_link")
    if _WINDOWS:
        _purge_windows(_extended(path), info, _extended(path.parent))
        return
    _before_open(str(path))
    try:
        fd = os.open(path, FLAGS)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ProfileError("path_changed") from None
        raise
    try:
        if not _same(info, os.fstat(fd)):
            raise ProfileError("path_changed")
        _purge_fd(fd, str(path))
    finally:
        os.close(fd)
    path.rmdir()


def _in_use(folder):
    """True while a running browser holds the folder. On Linux and macOS Chrome keeps the link `SingletonLock` ->
    "<host>-<pid>" in a user-data folder while it runs; only that link's own text is read, and the host is ignored
    (a computer's name can change under a running browser). Only these are not held: no lock, no such process, or
    link text Chrome would never write. A process we may not signal, and any other error, counts as running. Windows
    needs no check: it refuses to rename a folder with open files."""
    if _WINDOWS:
        return False
    try:
        link = os.readlink(os.path.join(folder, "SingletonLock"))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        pid = int(link.rpartition("-")[2])
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError, OverflowError):
        return False
    except OSError:
        return True
    return True


def _lock_os(fd, acquire):
    """The OS owns lock lifetime; the persistent file's contents and age are irrelevant."""
    try:
        if _WINDOWS:
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB if acquire else fcntl.LOCK_UN)
    except (ImportError, AttributeError):
        raise ProfileError("lock_unavailable") from None
    except OSError as exc:
        if acquire and (isinstance(exc, BlockingIOError) or _WINDOWS and exc.errno in (errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK))):
            raise ProfileError("busy") from None
        raise ProfileError("lock_unavailable") from None


def _lock_info(info):
    if stat.S_ISLNK(info.st_mode) or _reparse(info):
        raise ProfileError("unsafe_link")
    if not stat.S_ISREG(info.st_mode):
        raise ProfileError("unsafe_type")
    if info.st_nlink != 1:
        raise ProfileError("unsafe_hardlink")
    if not _WINDOWS and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise ProfileError("unsafe_permissions")


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
            if not isinstance(m, dict) or type(m.get("version")) is not int:
                raise ValueError
            keys = set(m)
            if m["version"] == 1 and keys == KEYS_V1:
                m = {**m, "generation": 1}
            elif m["version"] != 2 or keys != KEYS_V1 | {"generation"} or not _generation_ok(m["generation"]):
                raise ValueError
            if m["profile_id"] != path.name or not FOLDER.fullmatch(path.name):
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
    def _locked(self, strict=True):
        """`strict=False` (cleanup only) neither creates the root nor requires its private mode."""
        if strict:
            self._root()
        path = self.root / ".lock"
        fd, held = None, False
        try:
            try:
                _lock_info(path.lstat())
            except FileNotFoundError:
                pass
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.set_inheritable(fd, False)
            info = os.fstat(fd)
            _lock_info(info)
            named = path.lstat()
            _lock_info(named)
            if not _same(info, named):
                raise ProfileError("path_changed")
            _lock_os(fd, True)
            held = True
            if strict:
                _check(self.data, data=True)
                _check(self.root)
        except OSError as exc:
            if fd is not None:
                os.close(fd)
            raise ProfileError("unsafe_link" if exc.errno == errno.ELOOP else "lock_unavailable") from None
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise
        try:
            yield
        finally:
            try:
                if held:
                    _lock_os(fd, False)
            finally:
                os.close(fd)

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

    @staticmethod
    def _still_retired(skipped):
        """A folder that was retired but could not be deleted yet: it still holds sign-ins."""
        return any(entry["name"].startswith(".retired-") for entry in skipped)

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

    def find(self, owner):
        """-> [(profile_id, generation)] of valid folders whose marker matches this owner exactly. Reads markers only."""
        fields = self._owner(owner)
        with self._locked():
            return self._find(fields)

    def _find(self, fields):
        found = []
        for path in self.root.iterdir():
            if not FOLDER.fullmatch(path.name):
                continue
            try:
                m = self._marker(path)
            except ProfileError:
                continue
            if all(m[k] == v for k, v in fields.items()):
                found.append((path.name, m["generation"]))
        return found

    def prepare(self, owner, generation=1):
        """The owner's folder at this workspace generation (W4). An older-generation folder of the same owner must be
        purged first (`purge_pending`), and so must any retired folder that is still on disk; a newer one means the
        answer went backwards (`generation_rollback`)."""
        fields = self._owner(owner)
        if not _generation_ok(generation):
            raise ProfileError("generation_invalid")
        with self._locked():
            if self._still_retired(self._cleanup()):
                raise ProfileError("purge_pending")
            for _, have in self._find(fields):
                if have < generation:
                    raise ProfileError("purge_pending")
                if have > generation:
                    raise ProfileError("generation_rollback")
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
            marker = {"version": 2, "profile_id": profile_id, **fields, "state": "prepared", "created": time.time(),
                      "generation": generation}
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
        if _in_use(path):  # deleted under a running browser, it would be written again with no marker, and then kept
            raise ProfileError("in_use")
        retired = self.root / (".retired-" + secrets.token_hex(16))
        os.rename(path, retired)
        _purge(retired)

    def retire(self, profile_id, expected_owner):
        if not isinstance(profile_id, str) or not FOLDER.fullmatch(profile_id):
            raise ProfileError("profile_invalid")
        fields = self._owner(expected_owner)
        with self._locked():
            pending = self._still_retired(self._cleanup())
            path = self.root / profile_id
            if pending and not os.path.lexists(path):
                raise ProfileError("purge_pending")  # renamed away earlier, and still not deleted
            m = self._marker(path)
            if any(m[k] != v for k, v in fields.items()):
                raise ProfileError("owner_mismatch")
            self._retire(path)

    def retire_owner(self, expected_owner):
        return self._retire_many(self._owner(expected_owner))

    def retire_other_people(self, owner):
        """A different person signed in on this OS account (D-026 C2): `retire_owner` for every owner found whose
        marker names another person. -> True when none of their folders is left, under its own name or retired. One
        that a running browser holds is left whole until that window is closed.
        The same person's folders from an earlier sign-in of this device are kept (C4). A folder whose marker can't
        be read is left alone: nothing says whose it is, and no owner is ever given it."""
        fields = self._owner(owner)
        with self._locked():
            others = self._other_people(fields)
        for other in others:
            self.retire_owner(other)
        with self._locked():
            return not self._still_retired(self._cleanup()) and not self._other_people(fields)

    def _other_people(self, fields):
        """-> the distinct owners, among valid markers, that are a different (Hub, person) from `fields`."""
        found = []
        for path in self.root.iterdir():
            if not FOLDER.fullmatch(path.name):
                continue
            try:
                m = self._marker(path)
            except ProfileError:
                continue
            if (m["origin"], m["person_id"]) == (fields["origin"], fields["person_id"]):
                continue
            seat = m["seat"] or {"id": None, "generation": None}
            other = Owner(m["origin"], m["person_id"], m["device_id"], seat["id"], seat["generation"])
            if all(other.fields != seen.fields for seen in found):
                found.append(other)
        return found

    def retire_all(self):
        """Explicit app-root cleanup, including safe profile folders with invalid/absent markers."""
        return self._retire_many(None)

    def delete_all(self):
        """`cleanup` (D-026): delete everything under browser-profiles/, whoever it belongs to and whatever state it is
        in. A link or junction is removed itself and its target is never touched. Only the root and its lock stay,
        and a folder a running browser holds, which is listed as `in_use`.
        Creates nothing when there is nothing. -> [(path, reason)] for whatever is still there."""
        try:
            for folder in (self.data, self.root):
                info = folder.lstat()
                if stat.S_ISLNK(info.st_mode) or _reparse(info):
                    return [(str(self.root), "unsafe_link")]  # what it leads to may hold sign-ins: say so, touch nothing
                if not stat.S_ISDIR(info.st_mode):
                    return [(str(folder), "unsafe_type")]
            if not _inside(self.root, self.data):
                return [(str(self.root), "unsafe_link")]
            if not os.listdir(self.root):
                return []
            left = []
            with self._locked(strict=False):
                for path in sorted(self.root.iterdir()):
                    if path.name != ".lock":
                        left.extend(self._delete_entry(path))
            return left
        except FileNotFoundError:
            return []
        except (ProfileError, OSError) as exc:
            return [(str(self.root), getattr(exc, "code", "cleanup_failed"))]

    def _delete_entry(self, path):
        try:
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode) and not _reparse(info):
                if _in_use(path):  # a browser left open would stay signed in and write the folder again
                    return [(str(path), "in_use")]
                if not SPECIAL.fullmatch(path.name):
                    # Renamed first, as every other deletion does: a half-deleted folder is never opened again.
                    retired = self.root / (".retired-" + secrets.token_hex(16))
                    os.rename(path, retired)
                    path = retired
                _remove_tree(path, info)
            elif _WINDOWS:
                _remove_windows(_extended(path), info)
            else:
                path.unlink()
        except FileNotFoundError:
            pass
        except (ProfileError, OSError) as exc:
            return [(str(path), getattr(exc, "code", "cleanup_failed"))]
        return []

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
