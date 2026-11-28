"""A single company login stays known to whoever has used it (D-028 point 3).

Swangz can block the site where it controls the browser; it cannot end a session the person opened themselves or
make them forget a password. So when an admin's change takes such a tool from someone, Needs attention asks for
that login's password to be changed, until an admin records that it has been. Swangz never sees the password.
"""

import contextlib
import time

from . import entitle

PREFIX = "login_reminder:"  # settings rows, one per (tool, person): login_reminder:<tool id>:<person id> = when


def _single_logins(db):
    return {t["id"]: t for t in db.q("SELECT id, name FROM tools WHERE signin = 'shared' AND archived = 0 ORDER BY name")}


def held(db, people):
    """{(tool id, person id)}: the single company logins these people may use now."""
    shared = set(_single_logins(db))
    out = set()
    if not shared:
        return out
    for pid in people:
        p = db.one("SELECT * FROM people WHERE id = ?", (pid,))
        if p and p["status"] == "active" and not entitle.access_ended(p):
            out |= {(tool_id, pid) for tool_id in entitle.person_grants(db, p) & shared}
    return out


@contextlib.contextmanager
def watching(db, people):
    """Around a change to what these people may use: notes each single company login it takes from one of them."""
    people = list(people)
    before = held(db, people)
    yield
    for tool_id, pid in before - held(db, people):
        db.set_setting(f"{PREFIX}{tool_id}:{pid}", time.time())


def _noted(db):
    """{tool id: {person id}} as noted, whether or not it still matters."""
    out = {}
    for row in db.q("SELECT k FROM settings WHERE substr(k, 1, ?) = ?", (len(PREFIX), PREFIX)):
        tool_id, pid = row["k"][len(PREFIX):].rsplit(":", 1)
        out.setdefault(tool_id, set()).add(int(pid))
    return out


def pending(db):
    """[(tool, [names])]: logins whose password is still to be changed, with who lost access. Someone who has the
    tool again is left out while they have it."""
    noted, out = _noted(db), []
    for tool_id, tool in _single_logins(db).items():
        people = noted.get(tool_id, set())
        now = held(db, people)
        gone = [p for p in people if (tool_id, p) not in now]
        names = sorted(r["name"] for r in (db.one("SELECT name FROM people WHERE id = ?", (p,)) for p in gone) if r)
        if names:
            out.append((tool, names))
    return out


def changed(db, tool_id):
    """The password was changed: nothing is left to do for this tool. -> how many people it was about"""
    people = _noted(db).get(tool_id, set())
    for pid in people:
        db.x("DELETE FROM settings WHERE k = ?", (f"{PREFIX}{tool_id}:{pid}",))
    return len(people)
