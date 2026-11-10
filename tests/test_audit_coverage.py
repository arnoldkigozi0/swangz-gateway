"""Every console route that changes something writes to the audit log (plan v18, item 6).

A source-level sweep: each non-GET route in the control-room API must call audit(...) itself, or be one of the
named routes below that change nothing a person would need accounted for. A new route that forgets the audit
call fails here; a new read-only POST has to be added to the list on purpose, with its reason."""
import inspect
import unittest

from gateway import admin

# POSTs that only compute an answer (simulators, a rule try-out), and marking your own notifications as read.
CHANGES_NOTHING = {
    ("POST", "/purposes/test"): "tries keyword rules against a sample; saves nothing",
    ("POST", "/policies/simulate"): "read-only simulator",
    ("POST", "/simulate/revoke"): "read-only simulator",
    ("POST", "/simulate/seats"): "read-only simulator",
    ("POST", "/notifications/read"): "marks notifications as read for the console; no access or data changes",
}


class AuditCoverageTests(unittest.TestCase):
    def test_every_state_changing_console_route_audits(self):
        missing, seen = [], set()
        for method, rx, fn, _role, _area in admin.ROUTES:
            if method == "GET":
                continue
            key = (method, rx.pattern)
            if "audit(" in inspect.getsource(fn):
                continue
            seen.add(key)
            if key not in CHANGES_NOTHING:
                missing.append(f"{method} {rx.pattern} ({fn.__module__}.{fn.__name__})")
        self.assertEqual(missing, [], "console routes that change state without an audit entry")
        self.assertEqual(set(CHANGES_NOTHING) - seen, set(), "listed as read-only but now audited or gone: remove from the list")

    def test_the_read_only_exceptions_carry_no_area(self):
        # A route that needs a role area changes something; it may not sit on the exceptions list.
        for method, rx, _fn, _role, area in admin.ROUTES:
            if (method, rx.pattern) in CHANGES_NOTHING:
                self.assertIsNone(area, rx.pattern)


if __name__ == "__main__":
    unittest.main()
