"""Requests in flight right now — what the console shows as "live", and what a revoke can cut.

Cutting works by shutting the upstream socket: the proxy's read returns, it sees why, tells the
client in its own dialect that access was withdrawn, and records the request as cut.
"""

import itertools
import socket
import threading
import time


class Ticket:
    __slots__ = ("id", "person_id", "person", "key_id", "provider", "model", "client", "session",
                 "prompt", "started", "first_byte", "conn", "reason", "out_bytes")

    def __init__(self, tid, **info):
        self.id = tid
        self.started = time.time()
        self.first_byte = None
        self.conn = None
        self.reason = None
        self.out_bytes = 0
        for k in ("person_id", "person", "key_id", "provider", "model", "client", "session", "prompt"):
            setattr(self, k, info.get(k))

    def view(self):
        return {
            "id": self.id, "person_id": self.person_id, "person": self.person, "key_id": self.key_id,
            "provider": self.provider, "model": self.model, "client": self.client, "session": self.session,
            "prompt": (self.prompt or "")[:300], "started": self.started,
            "streaming": self.first_byte is not None, "bytes": self.out_bytes, "cut": self.reason,
        }


class Live:
    def __init__(self):
        self.lock = threading.Lock()
        self.tickets = {}
        self.counter = itertools.count(1)

    def start(self, **info):
        with self.lock:
            t = Ticket(next(self.counter), **info)
            self.tickets[t.id] = t
            return t

    def attach(self, ticket, conn):
        with self.lock:
            ticket.conn = conn
            reason = ticket.reason
        if reason:
            _shut(conn)

    def finish(self, ticket):
        with self.lock:
            self.tickets.pop(ticket.id, None)

    def cut(self, reason, *, ticket_id=None, key_id=None, person_id=None, everything=False):
        """Stop matching requests now. -> how many were cut."""
        hit = []
        with self.lock:
            for t in self.tickets.values():
                if everything or t.id == ticket_id or (key_id and t.key_id == key_id) or (
                        person_id is not None and t.person_id == person_id):
                    if not t.reason:
                        t.reason = reason
                        hit.append(t)
        for t in hit:
            if t.conn is not None:
                _shut(t.conn)
        return len(hit)

    def snapshot(self):
        with self.lock:
            return sorted((t.view() for t in self.tickets.values()), key=lambda v: v["started"])


def _shut(conn):
    sock = getattr(conn, "sock", None)
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
