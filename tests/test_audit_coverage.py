"""Every console route that changes something writes to the audit log (plan v18, item 6).

A source-level sweep: each non-GET route in the control-room API must call audit(...) itself (or through the one shared
function it hands to), or be one of the
named routes below that change nothing a person would need accounted for. A new route that forgets the audit
call fails here; a new read-only POST has to be added to the list on purpose, with its reason."""
import inspect
import unittest

from gateway import admin, business, reporting
from gateway import server  # noqa: F401  (loading the server registers every module's console routes)

# POSTs that only compute an answer (simulators, a rule try-out), and marking your own notifications as read.
CHANGES_NOTHING = {
    ("POST", "/purposes/test"): "tries keyword rules against a sample; saves nothing",
    ("POST", "/policies/simulate"): "read-only simulator",
    ("POST", "/simulate/revoke"): "read-only simulator",
    ("POST", "/simulate/seats"): "read-only simulator",
    ("POST", "/notifications/read"): "marks notifications as read for the console; no access or data changes",
    ("POST", "/hub/business/calculate"): "a hypothetical calculation; nothing is saved",
}

# Routes that hand straight to a shared function: that function must write the audit entry.
DELEGATES = {
    ("POST", r"/hub/reports/(?P<rid>\d+)/review"): reporting.review,
    ("POST", r"/hub/reports/(?P<rid>\d+)/amend"): business.amend,
    ("POST", r"/hub/reports/(?P<rid>\d+)/pricing"): business.amend,
}


class AuditCoverageTests(unittest.TestCase):
    def test_every_state_changing_console_route_audits(self):
        missing, seen = [], set()
        for method, rx, fn, _role, _area in admin.ROUTES:
            if method == "GET":
                continue
            key = (method, rx.pattern)
            if "audit(" in inspect.getsource(DELEGATES.get(key, fn)):
                continue
            seen.add(key)
            if key not in CHANGES_NOTHING:
                missing.append(f"{method} {rx.pattern} ({fn.__module__}.{fn.__name__})")
        self.assertEqual(missing, [], "console routes that change state without an audit entry")
        self.assertGreater(len(admin.ROUTES), 100)   # the whole console, not one module's routes
        self.assertEqual(set(CHANGES_NOTHING) - seen, set(), "listed as read-only but now audited or gone: remove from the list")

    def test_the_read_only_exceptions_carry_no_area(self):
        # A route that needs a role area changes something; it may not sit on the exceptions list.
        for method, rx, _fn, _role, area in admin.ROUTES:
            if (method, rx.pattern) in CHANGES_NOTHING:
                self.assertIsNone(area, rx.pattern)


if __name__ == "__main__":
    unittest.main()
