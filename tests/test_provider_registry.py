"""Amendment 01 task 1: the manual provider-account registry (schema v24). Synthetic data only; no outbound calls.

The eleven groups follow Sentinel's task 1 security gate: ownership, the console field ceiling, the database rules,
strict bodies, input limits, session kinds and CSRF, no effect on entitlements or spend, retained ends, private data in
no log, the migration, and the permission sweep."""

import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import gateway.db as dbmod
from gateway import registry, security, staff, store
from gateway.admin import ROUTES as ADMIN_ROUTES
from gateway.db import DB, SCHEMA

from .test_devices import DeviceBase

EMAIL = "grace@swangzavenue.com"
LABEL_MARK, PLAN_MARK = "Zq7LabelMarkerQx", "Zq7PlanMarkerQx"
CORE = {"id", "tool_id", "tool", "route", "status", "created", "ended"}
SEAT_EXTRA = {"holder", "payer", "assertion", "confirmed", "label"}
GOVERN_KINDS = {"plan", "quota_limit", "quota_used", "period_end"}
MONEY_KINDS = {"credit_balance", "monthly_price"}
ALL_KINDS = GOVERN_KINDS | MONEY_KINDS
SCHEMA_23_SHA256 = "02070d74ad6d1743d2adcdebbb106f83ca2a753c4c2f6cfafa600baa0ba68928"
OTHER_PASSWORD = "another-long-pw"

VALUES = [("plan", "Max 20x", None), ("quota_limit", 900, None), ("quota_used", "123.5", None), ("period_end", "2026-12-31", None),
          ("credit_balance", "42.10", "USD"), ("monthly_price", 200000, "UGX")]


class Base(DeviceBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db
        self.pid = self.rig.person_id
        self.db.x("UPDATE tools SET signin = 'api' WHERE id = 'claude-code'")
        self.db.x("UPDATE tools SET signin = 'shared' WHERE id = 'midjourney'")
        self.other_pid = self.db.x("INSERT INTO people(name, email, department, status, created, pw_hash) VALUES(?,?,?,?,?,?)",
                                   ("Okello Brian", "brian@swangzavenue.com", "Creative", "active", time.time(),
                                    security.hash_password(OTHER_PASSWORD, 1000))).lastrowid
        status, h, _ = self.rig.request("POST", "/api/login", {"email": "brian@swangzavenue.com", "password": OTHER_PASSWORD},
                                        {"x-swangz-app": "1"})
        self.assertEqual(status, 200)
        self.other_cookie = h["set-cookie"].split(";")[0]

    # ------------------------------------------------------------ calls
    autoclear = True  # the per-person limiter counts refusals too; only the limiter tests turn this off

    def call(self, method, path, body=None, cookie=None, bearer=None, header=True):
        if self.autoclear:
            self.clear_rate()
        headers = {"x-swangz-app": "1"} if header else {}
        cookie = self.person_cookie if cookie is None and bearer is None else cookie
        if cookie:
            headers["cookie"] = cookie
        if bearer:
            headers["authorization"] = "Bearer " + bearer
        status, h, payload = self.rig.request(method, "/api" + path, body, headers)
        try:
            return status, json.loads(payload) if payload else None
        except ValueError:
            return status, payload

    def console(self, path, who="owner", method="GET"):
        return self.rig.api(method, path, None if method == "GET" else {}, who=who)

    def make_admin(self, name, role="viewer", areas=""):
        self.db.x("INSERT INTO admins(username, pw_hash, role, areas, created) VALUES(?,?,?,?,?)",
                  (f"{name}@swangzavenue.com", security.hash_password(f"{name}-password", 1000), role, areas, time.time()))

    def clear_rate(self):
        self.rig.gw.ratelimit.hits.clear()

    # ------------------------------------------------------------ fixtures
    def account(self, tool="canva", route="individual", payer=None, label="", cookie=None, expect=201):
        payer = payer or ("company" if route == "seat" else "person")
        body = {"tool_id": tool, "route": route, "payer": payer}
        if label:
            body["label"] = label
        status, out = self.call("POST", "/provider-accounts", body, cookie=cookie)
        self.assertEqual(status, expect, out)
        return out

    def value(self, aid, kind, value, currency=None, cookie=None, expect=201, **extra):
        body = {"kind": kind, "value": value, **extra}
        if currency:
            body["currency"] = currency
        status, out = self.call("POST", f"/provider-accounts/{aid}/values", body, cookie=cookie)
        self.assertEqual(status, expect, out)
        return out

    def fill(self, aid):
        for kind, value, currency in VALUES:
            self.value(aid, kind, value, currency)

    def refused(self, body, code, path="/provider-accounts", status=400):
        got, out = self.call("POST", path, body)
        self.assertEqual((got, out.get("code")), (status, code), (body, out))
        return out


# ------------------------------------------------------------------ 1. ownership


class OwnershipTests(Base):
    def test_another_person_s_account_is_a_404_indistinguishable_from_a_missing_one(self):
        mine = self.account(label=LABEL_MARK)["id"]
        self.value(mine, "plan", PLAN_MARK)
        missing = max(mine + 100, 999)
        for method, tail, body in (("GET", "", None), ("GET", "", None), ("POST", "/values", {"kind": "plan", "value": "x"}),
                                   ("POST", "/end", {})):
            other = self.call(method, f"/provider-accounts/{mine}{tail}", body, cookie=self.other_cookie)
            gone = self.call(method, f"/provider-accounts/{missing}{tail}", body, cookie=self.other_cookie)
            self.assertEqual(other, gone, (method, tail))
            self.assertEqual(other[0], 404)
            self.assertNotIn(LABEL_MARK, json.dumps(other))
        for huge in ("9" * 40, "9" * 5000):
            self.assertEqual(self.call("GET", f"/provider-accounts/{huge}")[0], 404)
        self.assertEqual(self.db.scalar("SELECT status FROM provider_accounts WHERE id = ?", (mine,)), "active")
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_account_values"), 1)

    def test_lists_hold_only_the_signed_in_person_s_accounts(self):
        mine = self.account(label=LABEL_MARK)["id"]
        theirs = self.account(tool="chatgpt", cookie=self.other_cookie)["id"]
        _, mine_list = self.call("GET", "/provider-accounts")
        _, theirs_list = self.call("GET", "/provider-accounts", cookie=self.other_cookie)
        self.assertEqual([i["id"] for i in mine_list["items"]], [mine])
        self.assertEqual([i["id"] for i in theirs_list["items"]], [theirs])
        self.assertNotIn(LABEL_MARK, json.dumps(theirs_list))

    def test_the_holder_is_the_session_never_the_body(self):
        out = self.account()
        row = self.db.one("SELECT * FROM provider_accounts WHERE id = ?", (out["id"],))
        self.assertEqual((row["holder_person_id"], row["account_holder_kind"], row["assertion"], row["created_by"]),
                         (self.pid, "person", "holder_declared", self.pid))
        self.assertEqual((out["assertion"], out["confirmed"], out["created_by"]), ("holder_declared", False, self.pid))


# ------------------------------------------------------------------ 2. the console field ceiling


class ConsoleCeilingTests(Base):
    def setUp(self):
        super().setUp()
        self.ind = self.account(tool="canva", route="individual", payer="person", label=LABEL_MARK)["id"]
        self.seat = self.account(tool="chatgpt", route="seat", payer="company", label="Team seat")["id"]
        self.clear_rate()
        self.fill(self.ind)
        self.fill(self.seat)
        self.make_admin("ops", areas="govern,emergency")
        self.make_admin("bill", areas="money")
        self.make_admin("both", areas="govern,money")
        self.make_admin("sec", areas="trust,emergency")
        self.make_admin("adm", areas="admin")
        self.make_admin("emerg", areas="emergency")

    def items(self, who):
        status, out = self.console("/provider-accounts", who)
        self.assertEqual(status, 200, out)
        return {i["id"]: i for i in out["items"]}

    def test_the_holder_sees_everything_about_their_own_accounts(self):
        status, out = self.call("GET", f"/provider-accounts/{self.ind}")
        self.assertEqual(status, 200)
        self.assertEqual(set(out), CORE | SEAT_EXTRA - {"holder"} | {"created_by", "values", "history"})
        self.assertEqual(set(out["values"]), ALL_KINDS)
        self.assertEqual(len(out["history"]), 6)
        self.assertEqual((out["values"]["credit_balance"]["value"], out["values"]["credit_balance"]["currency"]), ("42.1", "USD"))
        self.assertEqual((out["values"]["plan"]["source"], out["values"]["plan"]["confirmed"]), ("holder_declared", False))

    def test_individual_accounts_show_the_console_only_that_they_exist(self):
        for who in ("owner", "ops", "both"):
            item = self.items(who)[self.ind]
            self.assertEqual(set(item), CORE, who)
            self.assertEqual(item["route"], "individual")
            status, detail = self.console(f"/provider-accounts/{self.ind}", who)
            self.assertEqual((status, set(detail)), (200, CORE), who)
            self.assertNotIn(LABEL_MARK, json.dumps(detail))
            self.assertNotIn("Max 20x", json.dumps(detail))
            self.assertNotIn("holder", detail)  # the ceiling names no holder for an individual account

    def test_money_alone_does_not_see_individual_accounts_at_all(self):
        self.assertNotIn(self.ind, self.items("bill"))
        self.assertEqual(self.console(f"/provider-accounts/{self.ind}", "bill")[0], 404)
        missing = self.console("/provider-accounts/999999", "bill")
        self.assertEqual(self.console(f"/provider-accounts/{self.ind}", "bill"), missing)

    def test_seat_accounts_split_between_govern_and_money_and_the_owner_gets_the_union(self):
        want = {"govern": (CORE | SEAT_EXTRA, GOVERN_KINDS), "ops": (CORE | SEAT_EXTRA, GOVERN_KINDS),
                "bill": (CORE | SEAT_EXTRA, MONEY_KINDS), "owner": (CORE | SEAT_EXTRA, ALL_KINDS), "both": (CORE | SEAT_EXTRA, ALL_KINDS)}
        for who, (fields, kinds) in want.items():
            who = "ops" if who == "govern" else who
            item = self.items(who)[self.seat]
            self.assertEqual(set(item), fields | {"values"}, who)
            self.assertEqual(set(item["values"]), kinds, who)
            status, detail = self.console(f"/provider-accounts/{self.seat}", who)
            self.assertEqual((status, set(detail), set(detail["values"])), (200, fields | {"values"}, kinds), who)
            self.assertEqual((detail["payer"], detail["assertion"], detail["confirmed"], detail["label"]),
                             ("company", "holder_declared", False, "Team seat"))
            self.assertEqual(detail["holder"], {"person_id": self.pid, "name": "Nansubuga Grace"})

    def test_a_kind_nobody_recorded_is_unavailable_never_zero(self):
        empty = self.account(tool="canva", route="seat", payer="company")["id"]
        item = self.console(f"/provider-accounts/{empty}", "owner")[1]
        self.assertEqual(set(item["values"]), ALL_KINDS)
        self.assertTrue(all(v == {"state": "unavailable"} for v in item["values"].values()))
        self.assertEqual(self.console(f"/provider-accounts/{empty}", "ops")[1]["values"]["plan"], {"state": "unavailable"})

    def test_roles_without_govern_or_money_and_viewers_are_refused(self):
        for who in ("viewer", "sec", "adm", "emerg"):
            self.assertEqual(self.console("/provider-accounts", who)[0], 403, who)
            self.assertEqual(self.console(f"/provider-accounts/{self.seat}", who)[0], 403, who)
        for path in ("/provider-accounts", f"/provider-accounts/{self.seat}"):
            self.assertEqual(self.rig.request("GET", "/admin/api" + path)[0], 401)

    def test_the_console_has_no_write_routes_here(self):
        for method, path in (("POST", "/provider-accounts"), ("POST", f"/provider-accounts/{self.seat}/end"),
                             ("PUT", f"/provider-accounts/{self.seat}"), ("DELETE", f"/provider-accounts/{self.seat}")):
            self.assertEqual(self.console(path, "owner", method)[0], 404, (method, path))

    def test_ended_accounts_stay_readable_with_the_same_ceiling(self):
        self.assertEqual(self.call("POST", f"/provider-accounts/{self.ind}/end", {})[0], 200)
        item = self.console(f"/provider-accounts/{self.ind}", "ops")[1]
        self.assertEqual((item["status"], set(item)), ("ended", CORE))
        self.assertIsNotNone(item["ended"])


# ------------------------------------------------------------------ 3. database rules


class DatabaseRuleTests(Base):
    BASE = ("INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created, created_by{extra})"
            " VALUES({vals}, 1, ?{more})")

    def insert(self, kind="person", holder=None, tool="canva", route="individual", payer="person", **extra):
        holder = self.pid if holder is None else holder
        cols = "".join(f", {k}" for k in extra)
        marks = "".join(", ?" for _ in extra)
        sql = (f"INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created, created_by{cols})"
               f" VALUES(?,?,?,?,?,1,?{marks})")
        return self.db.x(sql, (kind, None if kind == "company" else holder, tool, route, payer, self.pid, *extra.values())).lastrowid

    def rejects(self, fn, *a, **k):
        with self.assertRaises(sqlite3.IntegrityError):
            fn(*a, **k)

    def test_enums_holder_route_payer_and_status_are_enforced(self):
        self.insert()  # a good row
        self.rejects(self.insert, route="gateway", tool="chatgpt")
        self.rejects(self.insert, payer="bank", tool="chatgpt")
        self.rejects(self.insert, assertion="staff", tool="chatgpt")
        self.rejects(self.insert, status="paused", tool="chatgpt")
        self.rejects(self.insert, kind="robot", tool="chatgpt")
        # holder_person_id is set if and only if the holder is a person, in both directions
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.x("INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created)"
                      " VALUES('person', NULL, 'chatgpt', 'api', 'company', 1)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.x("INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created)"
                      " VALUES('company', ?, 'chatgpt', 'api', 'company', 1)", (self.pid,))
        self.db.x("INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created)"
                  " VALUES('company', NULL, 'chatgpt', 'enterprise', 'company', 1)")  # a company holder is allowed by the schema only
        with self.assertRaises(sqlite3.IntegrityError):  # individual and seat are always person-held
            self.db.x("INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created)"
                      " VALUES('company', NULL, 'chatgpt', 'seat', 'company', 1)")
        self.rejects(self.insert, route="individual", payer="company", tool="chatgpt")
        self.rejects(self.insert, route="seat", payer="person", tool="chatgpt")
        self.rejects(self.insert, route="seat", payer="none", tool="chatgpt")
        self.rejects(self.insert, label="x" * 81, tool="chatgpt")

    def test_status_and_timestamp_must_agree(self):
        self.rejects(self.insert, status="ended", tool="chatgpt")
        self.rejects(self.insert, status="active", ended=5, tool="chatgpt")
        self.assertTrue(self.insert(status="ended", ended=5, tool="chatgpt"))

    def test_one_active_account_per_holder_tool_and_route_but_an_ended_one_can_be_registered_again(self):
        first = self.insert()
        self.rejects(self.insert)
        self.insert(route="seat", payer="company")  # a different route
        self.insert(kind="person", holder=self.other_pid)  # a different person
        self.db.x("UPDATE provider_accounts SET status = 'ended', ended = 9 WHERE id = ?", (first,))
        self.assertTrue(self.insert())

    def test_values_are_immutable_and_an_account_can_only_be_ended(self):
        aid = self.insert()
        vid = self.db.x("INSERT INTO provider_account_values(account_id, kind, value, as_of, recorded, recorded_by)"
                        " VALUES(?, 'plan', 'Pro', '2026-11-06', 1, ?)", (aid, self.pid)).lastrowid
        self.rejects(self.db.x, "UPDATE provider_account_values SET value = 'Free' WHERE id = ?", (vid,))
        self.rejects(self.db.x, "DELETE FROM provider_account_values WHERE id = ?", (vid,))
        self.rejects(self.db.x, "DELETE FROM provider_accounts WHERE id = ?", (aid,))
        for column, value in (("label", "'renamed'"), ("tool_id", "'chatgpt'"), ("payer", "'none'"), ("holder_person_id", str(self.other_pid)),
                              ("route", "'seat'"), ("created", "5"), ("assertion", "'admin_declared'")):
            self.rejects(self.db.x, f"UPDATE provider_accounts SET {column} = {value} WHERE id = ?", (aid,))
        self.rejects(self.db.x, "UPDATE provider_accounts SET status = 'ended' WHERE id = ?", (aid,))  # needs the timestamp
        self.db.x("UPDATE provider_accounts SET status = 'ended', ended = 7 WHERE id = ?", (aid,))
        self.rejects(self.db.x, "UPDATE provider_accounts SET ended = 8 WHERE id = ?", (aid,))
        self.rejects(self.db.x, "UPDATE provider_accounts SET status = 'active', ended = NULL WHERE id = ?", (aid,))
        self.rejects(self.db.x, "INSERT INTO provider_account_values(account_id, kind, value, as_of, recorded, recorded_by)"
                                " VALUES(?, 'plan', 'Late', '2026-11-06', 1, ?)", (aid, self.pid))

    def test_value_rules(self):
        aid = self.insert()
        ok = "INSERT INTO provider_account_values(account_id, kind, value, currency, as_of, recorded, recorded_by) VALUES(?,?,?,?,?,1,?)"
        self.rejects(self.db.x, ok, (aid, "secret", "x", "", "2026-11-06", self.pid))
        self.rejects(self.db.x, ok, (aid, "credit_balance", "5", "", "2026-11-06", self.pid))  # a balance needs a currency
        self.rejects(self.db.x, ok, (aid, "plan", "Pro", "USD", "2026-11-06", self.pid))
        self.rejects(self.db.x, ok, (aid, "plan", "", "", "2026-11-06", self.pid))
        self.rejects(self.db.x, ok, (aid, "plan", "p" * 61, "", "2026-11-06", self.pid))
        self.rejects(self.db.x, ok, (999, "plan", "Pro", "", "2026-11-06", self.pid))

    def test_a_person_or_tool_with_a_registry_row_cannot_be_deleted(self):
        self.insert()
        self.rejects(self.db.x, "DELETE FROM tools WHERE id = 'canva'")
        self.rejects(self.db.x, "DELETE FROM people WHERE id = ?", (self.pid,))


# ------------------------------------------------------------------ 4. strict bodies


class StrictBodyTests(Base):
    def test_unknown_fields_and_every_holder_or_company_assertion_are_refused(self):
        base = {"tool_id": "canva", "route": "individual", "payer": "person"}
        for extra in ({"holder_person_id": self.other_pid}, {"person_id": self.other_pid}, {"account_holder_kind": "company"},
                      {"assertion": "admin_declared"}, {"company": True}, {"email": "x@swangzavenue.com"}, {"identity": "x"},
                      {"status": "ended"}, {"secret_ref": "env"}, {"created_by": 1}, {"token": "abc"}, {"id": 1}, {"anything": 1}):
            self.refused({**base, **extra}, "unknown_field")
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 0)
        aid = self.account()["id"]
        for extra in ({"holder_person_id": 1}, {"account_holder_kind": "company"}, {"assertion": "admin_declared"}, {"payer": "company"},
                      {"reason": "because"}, {"confirmed": True}, {"source": "official_api"}):
            self.refused({"kind": "plan", "value": "Pro", **extra}, "unknown_field", f"/provider-accounts/{aid}/values")
        self.refused({"anything": 1}, "unknown_field", f"/provider-accounts/{aid}/end")
        self.assertEqual(self.db.scalar("SELECT status FROM provider_accounts WHERE id = ?", (aid,)), "active")

    def test_api_enterprise_and_unknown_routes_cannot_be_written(self):
        for route, code in (("api", "route_unavailable"), ("enterprise", "route_unavailable"), ("company", "bad_route"),
                            ("", "bad_route"), (None, "bad_route"), (["seat"], "bad_route")):
            self.refused({"tool_id": "canva", "route": route, "payer": "company"}, code)
        self.refused({"tool_id": "canva"}, "bad_route")
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 0)

    def test_payer_rules_per_route(self):
        self.refused({"tool_id": "canva", "route": "individual"}, "bad_payer")
        self.refused({"tool_id": "canva", "route": "individual", "payer": "company"}, "bad_payer")
        self.refused({"tool_id": "canva", "route": "seat", "payer": "person"}, "bad_payer")
        self.refused({"tool_id": "canva", "route": "seat", "payer": "none"}, "bad_payer")
        seat = self.account(route="seat", payer="company")
        self.assertEqual((seat["payer"], seat["assertion"], seat["confirmed"]), ("company", "holder_declared", False))
        none = self.account(tool="chatgpt", route="individual", payer="none")
        self.assertEqual(none["payer"], "none")
        status, out = self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat"})  # seat payer is implied
        self.assertEqual((status, out["payer"]), (201, "company"))

    def test_shared_api_unknown_and_archived_tools_are_refused(self):
        for tool, code in (("midjourney", "tool_not_allowed"), ("claude-code", "tool_not_allowed"), ("no-such-tool", "bad_tool"),
                           ("Canva", "bad_tool"), ("../x", "bad_tool"), (7, "bad_tool"), (None, "bad_tool")):
            self.refused({"tool_id": tool, "route": "individual", "payer": "none"}, code)
        self.db.x("UPDATE tools SET archived = 1 WHERE id = 'canva'")
        self.refused({"tool_id": "canva", "route": "individual", "payer": "none"}, "bad_tool")

    def test_value_kinds_and_currency_pairing(self):
        aid = self.account()["id"]
        path = f"/provider-accounts/{aid}/values"
        self.refused({"kind": "email", "value": "x"}, "bad_kind", path)
        self.refused({"kind": "plan"}, "bad_value", path)
        self.refused({"value": "x"}, "bad_kind", path)
        self.refused({"kind": "plan", "value": "Pro", "currency": "USD"}, "bad_currency", path)
        self.refused({"kind": "credit_balance", "value": "5"}, "bad_currency", path)
        self.refused({"kind": "monthly_price", "value": "5", "currency": "usd"}, "bad_currency", path)
        self.refused({"kind": "monthly_price", "value": "5", "currency": "ABC"}, "bad_currency", path)
        self.refused({"kind": "monthly_price", "value": "5", "currency": 7}, "bad_currency", path)
        self.value(aid, "monthly_price", "5", "EUR")

    def test_bodies_must_be_json_objects(self):
        self.assertEqual(self.call("POST", "/provider-accounts", [1])[0], 400)
        status, h, _ = self.rig.request("POST", "/api/provider-accounts", b"{nope", {"x-swangz-app": "1", "cookie": self.person_cookie})
        self.assertEqual(status, 400)


# ------------------------------------------------------------------ 5. input, count and rate limits


class LimitTests(Base):
    def setUp(self):
        super().setUp()
        self.aid = self.account()["id"]
        self.path = f"/provider-accounts/{self.aid}/values"

    def test_label_and_plan_length_normalisation_and_trimming(self):
        self.assertEqual(self.account(tool="chatgpt", label="  " + "ab " * 26 + "ab" + "  ")["label"], "ab " * 26 + "ab")
        self.refused({"tool_id": "codex", "route": "seat", "label": "ab " * 27 + "ab"}, "too_long")
        self.assertEqual(self.account(tool="gemini", label="Café")["label"], "Café")  # NFC
        self.assertEqual(self.account(tool="perplexity", label="   ")["label"], "")
        self.refused({"tool_id": "grok", "route": "seat", "label": 7}, "bad_text")
        self.assertEqual(self.value(self.aid, "plan", "pq " * 19 + "pq")["values"]["plan"]["value"], "pq " * 19 + "pq")
        self.refused({"kind": "plan", "value": "pq " * 20 + "p"}, "too_long", self.path)
        self.refused({"kind": "plan", "value": "   "}, "bad_text", self.path)

    def test_control_and_bidi_characters_are_refused_everywhere_in_the_text(self):
        bad = ["\x00", "\x07", "\n", "\t", "\x7f", "\u0085", " ", " ", *map(chr, range(0x202A, 0x202F)), *map(chr, range(0x2066, 0x206A))]
        for ch in bad:
            for text in (f"a{ch}b", ch + "ab", "ab" + ch):
                self.refused({"tool_id": "codex", "route": "seat", "label": text}, "bad_text")
                self.refused({"kind": "plan", "value": text}, "bad_text", self.path)
        self.refused({"tool_id": "codex", "route": "seat", "label": "a\u200db"}, "bad_text")  # a zero-width joiner is a format character

    def test_text_that_looks_like_a_secret_is_refused_without_being_repeated(self):
        samples = ["sk-ant-api03-abc", "sk-", "AKIAIOSFODNN7EXAMPLE", "ghp_abcdefghij", "xoxb-1234", "Bearer abc", "bearer abc",
                   "my key " + "A" * 32, "k" * 32, "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "a" * 16 + "/" + "b" * 15 + "=", "x.y" * 11]
        for text in samples:
            status, out = self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat", "label": text})
            self.assertEqual((status, out["code"]), (400, "looks_like_secret"), text)
            self.assertNotIn(text, json.dumps(out))
            self.refused({"kind": "plan", "value": text}, "looks_like_secret", self.path)
        for text in ("sk", "ghp", "Bearer", "xo", "my key " + "A" * 31, "Max 20x plan, billed yearly", "Okello's team seat"):
            self.assertTrue(self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat", "label": text})[0] in (201, 409), text)
            self.clear_rate()

    def test_numbers_are_finite_decimals_from_zero_to_a_trillion(self):
        good = [(0, "0"), (-0.0, "0"), ("0", "0"), (7, "7"), (12.5, "12.5"), ("12.50", "12.5"), ("0.000001", "0.000001"),
                (1000000000000, "1000000000000"), ("1000000000000", "1000000000000"), (999999999999.5, "999999999999.5"),
                (0.000001, "0.000001"), (1e-06, "0.000001"), (0.123456, "0.123456")]
        for given, stored in good:
            self.assertEqual(self.value(self.aid, "quota_limit", given)["values"]["quota_limit"]["value"], stored, given)
            self.clear_rate()
        for given in (-1, -0.01, "-1", 1000000000001, "1000000000000.000001", 1000000000000.5, float("nan"), float("inf"), float("-inf"),
                      "nan", "inf", "1e3", "1E3", " 5", "5 ", "5.", ".5", "1,000", "0x10", "5.0000001", 0.1 + 0.2, "", True, False, None, [1], {"v": 1},
                      10 ** 400, "٣"):
            status, out = self.call("POST", self.path, {"kind": "quota_used", "value": given})
            self.assertEqual((status, out.get("code")), (400, "bad_number"), repr(given))
            self.clear_rate()
        self.assertEqual(self.value(self.aid, "credit_balance", "1000000000000", "UGX")["values"]["credit_balance"]["value"], "1000000000000")
        self.refused({"kind": "credit_balance", "value": "1000000000001", "currency": "UGX"}, "bad_number", self.path)

    def test_nan_in_the_raw_body_is_refused_too(self):
        raw = b'{"kind": "quota_limit", "value": NaN}'
        status, _, payload = self.rig.request("POST", "/api" + self.path, raw, {"x-swangz-app": "1", "cookie": self.person_cookie})
        self.assertEqual(status, 400, payload)

    def test_dates_run_from_2000_to_2100_and_as_of_not_past_tomorrow(self):
        for good in ("2000-01-01", "2026-02-28", "2100-12-31", "2024-02-29"):
            self.assertEqual(self.value(self.aid, "period_end", good)["values"]["period_end"]["value"], good)
            self.clear_rate()
        for bad in ("1999-12-31", "2101-01-01", "2026-02-30", "2026-13-01", "2026-1-1", "26-01-01", "2026/01/01", "2026-01-01T00:00", " 2026-01-01",
                    "2026-01-01\n", "٢٠٢٦-٠١-٠١", 20260101, None, True, "tomorrow"):
            status, out = self.call("POST", self.path, {"kind": "period_end", "value": bad})
            self.assertEqual((status, out.get("code")), (400, "bad_date"), repr(bad))
            self.clear_rate()
        today = registry._today(types.SimpleNamespace(gw=self.rig.gw))
        self.assertEqual(self.value(self.aid, "plan", "Pro", as_of=(today + timedelta(days=1)).isoformat())["values"]["plan"]["as_of"],
                         (today + timedelta(days=1)).isoformat())
        self.refused({"kind": "plan", "value": "Pro", "as_of": (today + timedelta(days=2)).isoformat()}, "bad_date", self.path)
        self.refused({"kind": "plan", "value": "Pro", "as_of": "1999-12-31"}, "bad_date", self.path)
        self.assertEqual(self.value(self.aid, "plan", "Pro")["values"]["plan"]["as_of"], today.isoformat())

    def test_currency_must_be_an_iso_4217_code(self):
        for code in ("UGX", "USD", "EUR", "GBP", "KES", "JPY"):
            self.value(self.aid, "monthly_price", "5", code)
            self.clear_rate()
        for code in ("XXX", "ABC", "US", "USDD", "usd", "Usd", "", " USD", "U$D", "١٢٣"):
            status, out = self.call("POST", self.path, {"kind": "monthly_price", "value": "5", "currency": code})
            self.assertEqual((status, out.get("code")), (400, "bad_currency"), code)

    def test_twenty_active_accounts_per_person_and_ending_one_makes_room(self):
        tools = [r["id"] for r in self.db.q("SELECT id FROM tools WHERE signin IN ('seat','own','sso') AND archived = 0 AND id != 'canva' ORDER BY id")]
        made = [self.aid]
        for tool in tools[:19]:
            self.clear_rate()
            made.append(self.account(tool=tool)["id"])
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts WHERE status = 'active'"), 20)
        self.clear_rate()
        status, out = self.call("POST", "/provider-accounts", {"tool_id": tools[19], "route": "individual", "payer": "none"})
        self.assertEqual((status, out["code"]), (409, "account_limit"))
        self.assertEqual(self.account(tool=tools[19], cookie=self.other_cookie)["route"], "individual")  # the limit is per person
        self.assertEqual(self.call("POST", f"/provider-accounts/{made[3]}/end", {})[0], 200)
        self.clear_rate()
        self.assertEqual(self.account(tool=tools[19])["status"], "active")

    def test_two_hundred_values_per_account(self):
        for i in range(registry.MAX_VALUES_PER_ACCOUNT - 1):
            self.db.x("INSERT INTO provider_account_values(account_id, kind, value, as_of, recorded, recorded_by) VALUES(?, 'plan', ?, '2026-11-06', ?, ?)",
                      (self.aid, f"p{i}", i, self.pid))
        self.assertEqual(self.value(self.aid, "plan", "last")["values"]["plan"]["value"], "last")
        self.clear_rate()
        status, out = self.call("POST", self.path, {"kind": "plan", "value": "one more"})
        self.assertEqual((status, out["code"]), (409, "value_limit"))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_account_values WHERE account_id = ?", (self.aid,)), 200)

    def test_the_per_person_limiter_slows_writes_and_reads(self):
        self.autoclear = False
        self.clear_rate()
        codes = [self.call("POST", self.path, {"kind": "quota_used", "value": i})[0] for i in range(registry.WRITES_PER_MINUTE + 2)]
        self.assertEqual(codes[:registry.WRITES_PER_MINUTE], [201] * registry.WRITES_PER_MINUTE)
        self.assertEqual(codes[registry.WRITES_PER_MINUTE:], [429, 429])
        self.assertEqual(self.call("POST", self.path, {"kind": "quota_used", "value": 1}, cookie=self.other_cookie)[0], 404)  # not their limiter
        self.clear_rate()
        reads = [self.call("GET", "/provider-accounts")[0] for _ in range(registry.READS_PER_MINUTE + 1)]
        self.assertEqual((reads[:-1] == [200] * registry.READS_PER_MINUTE, reads[-1]), (True, 429))


# ------------------------------------------------------------------ 6. sessions, kinds and CSRF


class SessionTests(Base):
    PATHS = (("GET", "/provider-accounts", None), ("POST", "/provider-accounts", {"tool_id": "canva", "route": "individual", "payer": "none"}),
             ("GET", "/provider-accounts/1", None), ("POST", "/provider-accounts/1/values", {"kind": "plan", "value": "Pro"}),
             ("POST", "/provider-accounts/1/end", {}))

    def test_paused_and_ended_people_are_refused_on_every_route(self):
        aid = self.account()["id"]
        for fields in ({"status": "suspended"}, {"access_until": time.time() - 5}):
            self.db.x(f"UPDATE people SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ?", [*fields.values(), self.pid])
            for method, path, body in self.PATHS:
                status, out = self.call(method, path.replace("/1", f"/{aid}"), body)
                self.assertEqual((status, out.get("code")), (403, "person_paused"), (fields, method, path))
            self.db.x("UPDATE people SET status = 'active', access_until = NULL WHERE id = ?", (self.pid,))
        self.assertEqual(self.call("GET", "/provider-accounts")[0], 200)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_account_values"), 0)

    def test_an_address_outside_the_approved_accounts_is_refused(self):
        self.db.x("UPDATE people SET email = 'grace@gmail.com' WHERE id = ?", (self.pid,))
        for method, path, body in self.PATHS:
            self.assertEqual(self.call(method, path, body)[0], 401, (method, path))

    def test_extension_sessions_device_keys_and_signed_out_callers_are_refused(self):
        aid = self.account()["id"]
        token = self.call("POST", "/extension/login", {"email": EMAIL, "password": "a-good-password-1"}, cookie="")[1]["token"]
        device = self.enrol()
        for method, path, body in self.PATHS:
            path = path.replace("/1", f"/{aid}")
            status, out = self.call(method, path, body, bearer=token)
            self.assertEqual((status, out.get("code")), (403, "session_kind"), (method, path))
            self.assertEqual(self.call(method, path, body, bearer=device["key"])[0], 401, (method, path))
            self.assertEqual(self.call(method, path, body, cookie="")[0], 401, (method, path))
            self.assertEqual(self.call(method, path, body, cookie="sgw_staff=" + token)[0], 401, (method, path))  # a bearer is not a cookie
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 1)

    def test_writes_without_the_app_header_are_refused(self):
        aid = self.account()["id"]
        for method, path, body in self.PATHS:
            if method == "POST":
                self.assertEqual(self.call(method, path.replace("/1", f"/{aid}"), body, header=False)[0], 403, path)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 1)
        self.assertEqual(self.db.scalar("SELECT status FROM provider_accounts"), "active")

    def test_the_pinned_route_sets_did_not_change(self):
        paused_ok = {(m, rx.pattern) for m, rx, fn, signed_in, ok in staff.ROUTES if ok}
        self.assertEqual(paused_ok, {("GET", r"/me"), ("GET", r"/hub/reports"), ("GET", r"/hub/reports/(?P<rid>\d+)"),
                                     ("GET", r"/hub/notifications"), ("POST", r"/logout")})
        self.assertEqual(staff.EXTENSION_PATHS.pattern, r"/(?:extension|gate)/.+|/logout|/tools/[a-z0-9-]+/request")
        for method, path, body in self.PATHS:
            self.assertIsNone(staff.EXTENSION_PATHS.fullmatch(path))

    def test_the_global_ai_pause_alone_does_not_block_the_registry(self):
        self.db.set_setting("paused", "1")
        aid = self.account()["id"]
        self.value(aid, "plan", "Pro")
        self.assertEqual(self.call("POST", f"/provider-accounts/{aid}/end", {})[0], 200)


# ------------------------------------------------------------------ 7. nothing else reads declarations


class NoEffectTests(Base):
    TABLES = ("entitlements", "subscriptions", "tool_turns", "launches", "site_usage", "notifications", "requests", "keys", "devices",
              "policies", "people", "tools", "budgets")

    def counts(self):
        out = {}
        for table in self.TABLES:
            if self.db.one("SELECT 1 AS x FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)):
                out[table] = self.db.q(f"SELECT * FROM {table}")
        return out

    def views(self):
        out = {}
        for path in ("/licences", "/reports", "/reports/usage", "/notifications", "/health", "/search?q=canva", "/search?q=" + LABEL_MARK[:8]):
            status, body = self.rig.api("GET", path)
            if isinstance(body, dict):  # the report stamps the moment it was made
                body = {k: v for k, v in body.items() if k not in ("generated", "until")}
            out[path] = (status, json.dumps(body, sort_keys=True))
        me = self.call("GET", "/me")[1]
        out["/me"] = json.dumps({"catalog": me.get("catalog"), "budget": me.get("budget")}, sort_keys=True, default=str)
        return out

    def test_declarations_change_no_entitlement_subscription_licence_spend_search_or_notification(self):
        self.rig.api("PUT", "/subscriptions/canva", {"state": "active", "monthly_cost": 30, "seats": 5})
        self.views()  # the first read of a view can raise its own notifications; compare after that
        before_tables, before_views = self.counts(), self.views()
        seat = self.account(tool="canva", route="seat", payer="company", label=LABEL_MARK)["id"]
        ind = self.account(tool="chatgpt", route="individual", payer="person")["id"]
        self.clear_rate()
        self.fill(seat)
        self.fill(ind)
        self.call("POST", f"/provider-accounts/{ind}/end", {})
        after_tables = self.counts()
        self.assertEqual(before_tables, after_tables)
        after_views = self.views()
        for path in before_views:
            if path.startswith("/search?q=canva"):
                continue  # the audit rows are searchable by action; compared below without them
            self.assertEqual(before_views[path], after_views[path], path)
        self.assertNotIn(LABEL_MARK, json.dumps(after_views))
        # a seat declaration does not give the person the tool, nor spend
        self.assertIsNone(self.db.one("SELECT 1 AS x FROM entitlements WHERE person_id = ? AND tool_id = 'canva'", (self.pid,)))
        launch = self.rig.request("GET", "/go/canva", None, {"cookie": self.person_cookie})[0]
        self.assertEqual(launch, 403)  # still refused: assignment decides, not a declaration

    def test_no_other_module_reads_the_registry_tables(self):
        here = os.path.dirname(os.path.abspath(registry.__file__))
        readers = []
        for name in sorted(os.listdir(here)):
            if name.endswith(".py") and name not in ("registry.py", "registry_schema.py", "db.py"):
                text = open(os.path.join(here, name), encoding="utf-8").read()
                if "provider_account" in text:
                    readers.append(name)
        self.assertEqual(readers, ["admin.py"])  # only the tool-delete guard


# ------------------------------------------------------------------ 8. ends are retained


class EndTests(Base):
    def test_ending_is_idempotent_keeps_every_row_and_takes_no_more_values(self):
        aid = self.account(label=LABEL_MARK)["id"]
        self.value(aid, "plan", "Pro")
        status, first = self.call("POST", f"/provider-accounts/{aid}/end", {})
        self.assertEqual((status, first["status"]), (200, "ended"))
        self.assertIsNotNone(first["ended"])
        audits = self.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'ended a provider account'")
        time.sleep(0.02)
        status, again = self.call("POST", f"/provider-accounts/{aid}/end", {})
        self.assertEqual((status, again["ended"]), (200, first["ended"]))  # the same timestamp
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'ended a provider account'"), audits)  # no second entry
        status, out = self.call("POST", f"/provider-accounts/{aid}/values", {"kind": "plan", "value": "Free"})
        self.assertEqual((status, out["code"]), (409, "account_ended"))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_account_values WHERE account_id = ?", (aid,)), 1)
        detail = self.call("GET", f"/provider-accounts/{aid}")[1]  # still readable, values and history kept
        self.assertEqual((detail["status"], detail["values"]["plan"]["value"], len(detail["history"])), ("ended", "Pro", 1))
        self.assertEqual(self.db.scalar("SELECT label FROM provider_accounts WHERE id = ?", (aid,)), LABEL_MARK)

    def test_an_ended_registration_can_be_made_again_as_a_new_row(self):
        first = self.account()["id"]
        again = self.call("POST", "/provider-accounts", {"tool_id": "canva", "route": "individual", "payer": "person"})
        self.assertEqual((again[0], again[1]["code"]), (409, "already_registered"))
        self.call("POST", f"/provider-accounts/{first}/end", {})
        second = self.account()["id"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 2)
        listed = self.call("GET", "/provider-accounts?status=ended")[1]["items"]
        self.assertEqual([i["id"] for i in listed], [first])
        self.assertEqual(self.call("GET", "/provider-accounts?status=nope")[0], 400)

    def test_deleting_a_tool_with_registry_rows_is_a_409_not_a_500_and_changes_nothing(self):
        self.rig.api("POST", "/tools", {"name": "Home grown", "kind": "site", "url": "https://example.test/"})
        self.assertIsNotNone(self.db.one("SELECT 1 AS x FROM tools WHERE id = 'home-grown'"))
        self.account(tool="home-grown")
        status, out = self.rig.api("DELETE", "/tools/home-grown")
        self.assertEqual((status, out.get("code")), (409, "has_provider_accounts"))
        self.assertIsNotNone(self.db.one("SELECT 1 AS x FROM tools WHERE id = 'home-grown'"))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 1)
        self.rig.api("POST", "/tools", {"name": "Unused one", "kind": "site", "url": "https://example.test/"})
        self.assertEqual(self.rig.api("DELETE", "/tools/unused-one")[0], 200)  # an unrelated delete still works

    def test_store_purge_and_retention_leave_the_registry_alone(self):
        aid = self.account(label=LABEL_MARK)["id"]
        self.value(aid, "plan", "Pro")
        self.call("POST", f"/provider-accounts/{aid}/end", {})
        settings = {key: 1 for key in store.CATEGORIES}
        store.purge_categories(self.db, settings, now=time.time() + 400 * 86400)
        store.purge(self.db, 1, now=time.time() + 400 * 86400)
        self.rig.gw.maintain()
        self.assertEqual((self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), self.db.scalar("SELECT COUNT(*) FROM provider_account_values")), (1, 1))


# ------------------------------------------------------------------ 9. private data stays out of every log


class PrivacyTests(Base):
    def test_labels_and_values_are_in_no_audit_row_log_error_or_console_response_for_an_individual_account(self):
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            aid = self.account(label=LABEL_MARK)["id"]
            self.value(aid, "plan", PLAN_MARK)
            self.value(aid, "quota_used", "7391.4725")
            self.value(aid, "credit_balance", "5150.25", "UGX")
            self.call("POST", f"/provider-accounts/{aid}/values", {"kind": "plan", "value": "sk-" + "Z" * 40})
            self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat", "label": LABEL_MARK + "\n"})
            self.call("GET", f"/provider-accounts/{aid}")
            self.make_admin("both", areas="govern,money")
            console = [self.console("/provider-accounts", who) for who in ("owner", "both")]
            console += [self.console(f"/provider-accounts/{aid}", who) for who in ("owner", "both")]
            self.call("POST", f"/provider-accounts/{aid}/end", {})
        markers = (LABEL_MARK, PLAN_MARK, "7391.4725", "5150.25", "sk-ZZZZ")
        audit = json.dumps(self.db.q("SELECT * FROM audit"), default=str)
        for marker in markers:
            self.assertNotIn(marker, audit)
            self.assertNotIn(marker, stderr.getvalue())
            self.assertNotIn(marker, json.dumps(console))
        # the audit says what happened, with ids and kinds only
        rows = self.db.q("SELECT * FROM audit WHERE target = ? ORDER BY id", (f"provider_account:{aid}",))
        self.assertEqual([r["action"] for r in rows], ["registered a provider account", "recorded a provider account value",
                                                       "recorded a provider account value", "recorded a provider account value",
                                                       "ended a provider account"])
        self.assertTrue(all(r["correlation"] == f"provider_account:{aid}" and r["detail"] == "" and r["outcome"] == "ok"
                            and r["actor"] == "Nansubuga Grace" for r in rows))
        self.assertEqual(json.loads(rows[0]["after_json"]), {"status": "active"})
        self.assertEqual(set(json.loads(rows[1]["after_json"])), {"value_id"})
        self.assertEqual((json.loads(rows[4]["before_json"]), json.loads(rows[4]["after_json"])), ({"status": "active"}, {"status": "ended"}))

    def test_an_ended_or_refused_call_leaves_no_secret_in_an_error_body(self):
        aid = self.account()["id"]
        secret = "ghp_" + "Q" * 36
        status, out = self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat", "label": secret})
        self.assertEqual(status, 400)
        self.assertNotIn(secret, json.dumps(out))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE detail LIKE ? OR before_json LIKE ? OR after_json LIKE ?",
                                        ("%ghp_%", "%ghp_%", "%ghp_%")), 0)


# ------------------------------------------------------------------ 10. the migration


class MigrationTests(unittest.TestCase):
    def test_the_schema_has_24_entries_and_the_first_23_are_byte_for_byte_the_base(self):
        self.assertEqual(len(SCHEMA), 24)
        self.assertEqual(hashlib.sha256("\x00".join(SCHEMA[:23]).encode()).hexdigest(), SCHEMA_23_SHA256)

    def test_older_entries_are_still_strings_and_v24_is_a_tuple_of_single_statements(self):
        self.assertTrue(all(isinstance(entry, str) for entry in SCHEMA[:23]))
        self.assertIsInstance(SCHEMA[23], tuple)
        for element in SCHEMA[23]:
            self.assertTrue(sqlite3.complete_statement(element + ";"), element[:60])
            self.assertIsNone(re.search(r"\bEND\s*;\s*\S", element))  # nothing follows a trigger's END
        self.assertEqual(sum(e.lstrip().startswith("CREATE TRIGGER") for e in SCHEMA[23]), 7)
        with self.assertRaises((sqlite3.Warning, sqlite3.ProgrammingError)):  # sqlite itself refuses an element that holds two statements
            sqlite3.connect(":memory:").execute("SELECT 1; SELECT 2")
        self.assertFalse(hasattr(dbmod, "statements"))  # no parser: a str entry is split on semicolons, as it always was

    def test_a_fresh_database_gets_the_registry_and_its_rules(self):
        db = DB(":memory:")
        self.assertEqual(db.scalar("SELECT v FROM meta WHERE k = 'schema'"), "24")
        names = {r["name"] for r in db.q("SELECT name FROM sqlite_master")}
        self.assertTrue({"provider_accounts", "provider_account_values", "provider_accounts_one_active", "provider_account_values_no_update",
                         "provider_accounts_only_end", "provider_accounts_no_replace", "provider_account_values_no_replace"} <= names)
        self.assertEqual(db.scalar("PRAGMA recursive_triggers"), 0)  # the guards do not rely on it
        db.close()

    def test_a_failing_statement_rolls_the_whole_tuple_back_to_v23(self):
        for broken in (("CREATE TABLE zz_a(x)", "CREATE TRIGGER zz_t BEFORE INSERT ON zz_a BEGIN SELECT 1; END", "CREATE TABLE zz_a(x)"),
                       ("CREATE TABLE zz_a(x)", "CREATE TABLE zz_b(x); CREATE TABLE zz_c(x)"),  # two statements in one element
                       ("CREATE TABLE zz_a(x)", "CREATE TRIGGER zz_t BEFORE INSERT ON zz_a BEGIN SELECT RAISE(ABORT, 'x'); END",
                        "INSERT INTO no_such_table VALUES(1)")):
            path = os.path.join(tempfile.mkdtemp(prefix="sgw-v24-"), "g.db")
            with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:23]):
                DB(path).close()
            with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:23] + [broken]):
                with self.assertRaises(sqlite3.Error):
                    DB(path)
            raw = sqlite3.connect(path)
            self.assertEqual(raw.execute("SELECT v FROM meta WHERE k = 'schema'").fetchone()[0], "23")
            self.assertEqual(raw.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'zz_%'").fetchone()[0], 0)
            raw.close()
            with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:23]):  # and the v23 database still opens
                reopened = DB(path)
                self.assertEqual(reopened.scalar("SELECT v FROM meta WHERE k = 'schema'"), "23")
                reopened.close()

    def test_the_real_v24_failing_part_way_leaves_v23_untouched(self):
        path = os.path.join(tempfile.mkdtemp(prefix="sgw-v24-"), "g.db")
        with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:23]):
            DB(path).close()
        broken = SCHEMA[23] + ("CREATE TABLE provider_accounts(x)",)  # the last element fails: the table exists by then
        with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:23] + [broken]):
            with self.assertRaises(sqlite3.Error):
                DB(path)
        raw = sqlite3.connect(path)
        self.assertEqual(raw.execute("SELECT v FROM meta WHERE k = 'schema'").fetchone()[0], "23")
        self.assertEqual(raw.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'provider_account%'").fetchone()[0], 0)
        raw.close()
        DB(path).close()  # the real upgrade then succeeds from the untouched v23 file

    def test_a_populated_v23_database_upgrades_with_every_existing_row_unchanged(self):
        path = os.path.join(tempfile.mkdtemp(prefix="sgw-v24-"), "g.db")
        with mock.patch.object(dbmod, "SCHEMA", SCHEMA[:23]):
            old = DB(path)
            self.assertEqual(old.scalar("SELECT v FROM meta WHERE k = 'schema'"), "23")
            old.x("INSERT INTO people(id, name, email, created) VALUES(1, 'A', 'a@swangzavenue.com', 1), (2, 'B', 'b@swangzavenue.com', 2)")
            old.x("INSERT INTO tools(id, name, created) VALUES('t1', 'Tool one', 1)")
            old.x("INSERT INTO entitlements(tool_id, person_id, granted) VALUES('t1', 1, 5)")
            old.x("INSERT INTO staff_sessions(token_hash, person_id, created, expires, kind) VALUES('h', 1, 1, ?, 'web')", (time.time() + 99,))
            old.x("INSERT INTO audit(ts, actor, action) VALUES(1, 'x', 'y')")
            tables = [r["name"] for r in old.q("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            before = {t: old.q(f"SELECT * FROM {t}") for t in tables}
            old.close()
        db = DB(path)
        self.assertEqual(db.scalar("SELECT v FROM meta WHERE k = 'schema'"), "24")
        for table, rows in before.items():
            if table == "meta":
                continue  # only the schema number moves
            self.assertEqual(db.q(f"SELECT * FROM {table}"), rows, table)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM provider_accounts") + db.scalar("SELECT COUNT(*) FROM provider_account_values"), 0)
        db.x("INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, created) VALUES('person', 1, 't1', 'seat', 'company', 1)")
        db.close()
        again = DB(path)  # opening again changes nothing
        self.assertEqual(again.scalar("SELECT COUNT(*) FROM provider_accounts"), 1)
        again.close()


# ------------------------------------------------------------------ 11. the permission sweep


class SweepTests(Base):
    STAFF = {("GET", r"/provider-accounts"), ("POST", r"/provider-accounts"), ("GET", r"/provider-accounts/(?P<aid>[0-9]+)"),
             ("POST", r"/provider-accounts/(?P<aid>[0-9]+)/values"), ("POST", r"/provider-accounts/(?P<aid>[0-9]+)/end")}
    CONSOLE = {("GET", r"/provider-accounts"), ("GET", r"/provider-accounts/(?P<aid>[0-9]+)")}

    def test_every_registry_route_is_known_and_none_is_paused_ok(self):
        staff_found = {(m, rx.pattern) for m, rx, fn, s, ok in staff.ROUTES if "provider-accounts" in rx.pattern}
        self.assertEqual(staff_found, self.STAFF)
        self.assertTrue(all(s and not ok for m, rx, fn, s, ok in staff.ROUTES if "provider-accounts" in rx.pattern))
        console_found = {(m, rx.pattern, area) for m, rx, fn, role, area in ADMIN_ROUTES if "provider-accounts" in rx.pattern}
        self.assertEqual({(m, p) for m, p, a in console_found}, self.CONSOLE)
        self.assertTrue(all(a == ("govern", "money") for m, p, a in console_found))
        self.assertEqual(sum("provider-accounts" in rx.pattern for m, rx, fn, role, area in ADMIN_ROUTES if m != "GET"), 0)

    def test_staff_sweep_signed_out_wrong_session_and_other_person(self):
        aid = self.account()["id"]
        for method, pattern in sorted(self.STAFF):
            path = re.sub(r"\(\?P<aid>\[0-9\]\+\)", str(aid), pattern)
            body = {"tool_id": "chatgpt", "route": "seat"} if path == "/provider-accounts" else {"kind": "plan", "value": "x"} if path.endswith("values") else {}
            self.assertEqual(self.call(method, path, body, cookie="")[0], 401, (method, path))
            self.assertEqual(self.call(method, path, body, cookie="sgw_staff=nonsense")[0], 401, (method, path))
            if str(aid) in path:
                self.assertEqual(self.call(method, path, body, cookie=self.other_cookie)[0], 404, (method, path))

    def test_console_sweep_signed_out_and_by_role(self):
        aid = self.account(route="seat", payer="company")["id"]
        self.make_admin("ops", areas="govern,emergency")
        self.make_admin("bill", areas="money")
        self.make_admin("sec", areas="trust")
        for path in ("/provider-accounts", f"/provider-accounts/{aid}"):
            self.assertEqual(self.rig.request("GET", "/admin/api" + path)[0], 401)
            expected = {"owner": 200, "ops": 200, "bill": 200, "sec": 403, "viewer": 403}
            for who, code in expected.items():
                self.assertEqual(self.console(path, who)[0], code, (path, who))
        denied = self.db.scalar("SELECT COUNT(*) FROM audit WHERE outcome = 'denied'")
        self.assertEqual(denied, 4)  # each refusal is recorded by the dispatcher


# ------------------------------------------------------------------ correction R1-R5 (Sentinel, 6 November 02:27)


class ReplaceGuardTests(Base):
    """R1: INSERT OR REPLACE and REPLACE INTO delete the row they replace without firing DELETE triggers."""

    def seed(self, with_values=True):
        aid = self.account(label=LABEL_MARK)["id"]
        if with_values:
            self.value(aid, "plan", "Pro")
            self.value(aid, "quota_used", "5")
        return aid

    def snapshot(self):
        return (self.db.q("SELECT * FROM provider_accounts ORDER BY id"), self.db.q("SELECT * FROM provider_account_values ORDER BY id"),
                self.db.scalar("SELECT COUNT(*) FROM audit"))

    def refuses(self, sql, args=()):
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.x(sql, args)
        self.assertEqual(self.snapshot(), before)

    VALUE = "INSERT OR REPLACE INTO provider_account_values(id, account_id, kind, value, as_of, recorded, recorded_by) VALUES(?,?,'plan','Free','2026-11-06',1,?)"

    def test_replacing_a_value_row_is_refused_and_nothing_changes(self):
        aid = self.seed()
        vid = self.db.scalar("SELECT MIN(id) FROM provider_account_values")
        self.refuses(self.VALUE, (vid, aid, self.pid))
        self.refuses(self.VALUE.replace("INSERT OR REPLACE", "REPLACE"), (vid, aid, self.pid))
        self.refuses(self.VALUE.replace("INSERT OR REPLACE", "INSERT"), (vid, aid, self.pid))
        self.assertEqual(self.db.scalar("SELECT value FROM provider_account_values WHERE id = ?", (vid,)), "Pro")

    def test_replacing_an_account_row_is_refused_with_and_without_values(self):
        for with_values in (True, False):
            aid = self.seed(with_values)
            sql = ("INSERT OR REPLACE INTO provider_accounts(id, account_holder_kind, holder_person_id, tool_id, route, payer, label, created,"
                   " created_by) VALUES(?, 'person', ?, 'gemini', 'seat', 'company', 'taken over', 1, ?)")
            self.refuses(sql, (aid, self.other_pid, self.pid))
            self.refuses(sql.replace("INSERT OR REPLACE", "REPLACE"), (aid, self.other_pid, self.pid))
            self.assertEqual(self.db.scalar("SELECT label FROM provider_accounts WHERE id = ?", (aid,)), LABEL_MARK)
            self.call("POST", f"/provider-accounts/{aid}/end", {})

    def test_replacing_through_the_partial_index_under_a_new_id_is_refused(self):
        for with_values in (False, True):  # without values nothing else would stop the replace
            self.partial_index_replace(with_values)
            aid = self.db.scalar("SELECT MAX(id) FROM provider_accounts")
            self.call("POST", f"/provider-accounts/{aid}/end", {})

    def partial_index_replace(self, with_values):
        aid = self.seed(with_values)
        for verb in ("INSERT OR REPLACE", "REPLACE", "INSERT OR IGNORE"):
            sql = (f"{verb} INTO provider_accounts(id, account_holder_kind, holder_person_id, tool_id, route, payer, label, created,"
                   " created_by) VALUES(?, 'person', ?, 'canva', 'individual', 'none', 'new row', 1, ?)")
            before = self.snapshot()
            try:
                self.db.x(sql, (aid + 50, self.pid, self.pid))
            except sqlite3.IntegrityError:
                pass
            self.assertEqual(self.snapshot(), before, verb)
        self.assertEqual(self.db.scalar("SELECT status FROM provider_accounts WHERE id = ?", (aid,)), "active")

    def test_an_ended_account_may_be_registered_again_and_a_replace_cannot_touch_the_ended_one(self):
        aid = self.seed()
        self.call("POST", f"/provider-accounts/{aid}/end", {})
        again = self.account()["id"]
        self.assertNotEqual(aid, again)
        self.refuses("REPLACE INTO provider_accounts(id, account_holder_kind, holder_person_id, tool_id, route, payer, created, created_by,"
                     " status, ended) VALUES(?, 'person', ?, 'canva', 'individual', 'none', 1, ?, 'ended', 2)", (aid, self.pid, self.pid))

    def test_ids_must_be_positive_so_the_guards_stay_exact_and_normal_use_still_works(self):
        self.refuses("INSERT INTO provider_accounts(id, account_holder_kind, holder_person_id, tool_id, route, payer, created, created_by)"
                     " VALUES(-1, 'person', ?, 'gemini', 'seat', 'company', 1, ?)", (self.pid, self.pid))
        self.refuses("INSERT INTO provider_accounts(id, account_holder_kind, holder_person_id, tool_id, route, payer, created, created_by)"
                     " VALUES(0, 'person', ?, 'gemini', 'seat', 'company', 1, ?)", (self.pid, self.pid))
        aid = self.seed()
        self.assertEqual(self.call("POST", f"/provider-accounts/{aid}/end", {})[0], 200)
        self.assertEqual(self.db.scalar("PRAGMA recursive_triggers"), 0)


# ------------------------------------------------------------------ R2: text categories and the write boundary


class TextCategoryTests(Base):
    def setUp(self):
        super().setUp()
        self.aid = self.account()["id"]
        self.path = f"/provider-accounts/{self.aid}/values"

    def test_lone_surrogates_are_a_400_not_a_traceback(self):
        for ch in ("\ud800", "\udbff", "\udc00", "\udfff"):
            for text in (ch, "a" + ch + "b"):
                got, out = self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat", "label": text})
                self.assertEqual((got, out["code"]), (400, "bad_text"), repr(text))
                self.refused({"kind": "plan", "value": text}, "bad_text", self.path)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 1)

    def test_a_surrogate_that_reaches_the_database_is_still_a_400(self):
        with mock.patch.object(registry, "_text", lambda value, name, limit, required: "\ud800"):
            got, out = self.call("POST", "/provider-accounts", {"tool_id": "codex", "route": "seat", "label": "x"})
            self.assertEqual((got, out["code"]), (400, "bad_text"))
            got, out = self.call("POST", self.path, {"kind": "plan", "value": "x"})
            self.assertEqual((got, out["code"]), (400, "bad_text"))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_accounts"), 1)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_account_values"), 0)

    def test_every_other_category_is_refused_and_ordinary_text_is_not(self):
        for ch in ("\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\ufeff", "\u2065", "\u206a", "\u00ad", "\ue000", "\u0378",
                   "\U000f0000", "\U0010ffff", "\u061c", "\u2060", "\u180e", "\U000e0001"):
            self.refused({"tool_id": "codex", "route": "seat", "label": "a" + ch + "b"}, "bad_text")
            self.refused({"kind": "plan", "value": ch + "Pro"}, "bad_text", self.path)
        for text in ("Jos\u00e9", "Zo\u00eb's team", "Cafe\u0301", "\u65e5\u672c\u8a9e plan", "\U0001f44d", "Max 20x \U0001f680"):
            self.clear_rate()
            self.assertTrue(self.value(self.aid, "plan", text)["values"]["plan"]["value"])
        for sequence in ("\U0001f468\u200d\U0001f469\u200d\U0001f467", "\U0001f3f3\ufe0f\u200d\U0001f308"):  # ZWJ sequences: refused
            self.refused({"kind": "plan", "value": sequence}, "bad_text", self.path)

    def test_a_lone_surrogate_in_the_raw_body_does_not_break_the_server(self):
        raw = b'{"tool_id": "codex", "route": "seat", "label": "\\ud800"}'
        status, _, payload = self.rig.request("POST", "/api/provider-accounts", raw, {"x-swangz-app": "1", "cookie": self.person_cookie})
        self.assertEqual(status, 400, payload)
        self.assertEqual(json.loads(payload)["code"], "bad_text")
        self.assertEqual(self.call("GET", "/provider-accounts")[0], 200)


# ------------------------------------------------------------------ R3: the audit log is readable by every console user


class AuditPrivacyTests(Base):
    def setUp(self):
        super().setUp()
        self.make_admin("bill", areas="money")
        self.make_admin("sec", areas="trust,emergency")
        self.aid = self.account(tool="canva", route="individual", payer="person", label=LABEL_MARK)["id"]
        self.value(self.aid, "monthly_price", "30", "USD")
        self.value(self.aid, "plan", PLAN_MARK)
        self.call("POST", f"/provider-accounts/{self.aid}/end", {})

    def test_the_three_audit_entries_name_the_holder_and_the_record_and_nothing_else(self):
        rows = self.db.q("SELECT * FROM audit WHERE target = ? ORDER BY id", (f"provider_account:{self.aid}",))
        self.assertEqual([r["action"] for r in rows], ["registered a provider account", "recorded a provider account value",
                                                       "recorded a provider account value", "ended a provider account"])
        ref = f"provider_account:{self.aid}"
        for r in rows:
            self.assertEqual((r["actor"], r["correlation"], r["detail"], r["reason"], r["outcome"]), ("Nansubuga Grace", ref, "", "", "ok"))
        shapes = [(json.loads(r["before_json"]) if r["before_json"] else None, json.loads(r["after_json"])) for r in rows]
        self.assertEqual(shapes[0], (None, {"status": "active"}))
        self.assertEqual([set(a) for b, a in shapes[1:3]], [{"value_id"}, {"value_id"}])
        self.assertEqual(shapes[3], ({"status": "active"}, {"status": "ended"}))
        text = json.dumps(rows, default=str)
        for word in ("canva", "Canva", "individual", "seat", "monthly_price", "plan\"", "USD", "payer", LABEL_MARK, PLAN_MARK):
            self.assertNotIn(word, text.replace("recorded a provider account value", "").replace("a provider account", ""), word)

    def test_no_console_audit_view_search_or_timeline_shows_a_tool_route_kind_or_content(self):
        private = (LABEL_MARK, PLAN_MARK, "monthly_price", "individual", '"USD"', "canva", "Canva")
        for who in ("viewer", "bill", "sec", "owner"):
            audit = [self.console(path, who) for path in ("/audit?limit=500", "/audit?q=provider&limit=500")]
            search = [self.console("/search?q=" + q, who) for q in ("provider", str(self.aid), "Grace", "canva", LABEL_MARK)]
            for status, body in audit + search:
                self.assertEqual(status, 200, who)
            entries = [i for status, body in audit for i in body["items"] if "provider account" in i["action"]]
            self.assertEqual(len(entries), 8, who)  # four entries, seen in both listings
            for item in entries:
                self.assertEqual((item["target"], item["actor"]), (f"provider_account:{self.aid}", "Nansubuga Grace"), who)
            for marker in private:
                self.assertNotIn(marker, json.dumps(entries), (who, marker))
            for status, body in search[3:]:  # a search for the tool or the content finds no registry entry
                self.assertNotIn("provider_account", json.dumps(body), who)
                self.assertNotIn("provider account", json.dumps(body), who)

    def test_the_person_timeline_has_no_registry_rows(self):
        for query in ("/timeline", f"/timeline?person={self.pid}", f"/timeline?kind=access&person={self.pid}",
                      f"/people/{self.pid}/timeline"):
            status, body = self.console(query, "owner")
            if status == 404:
                continue
            self.assertEqual(status, 200, query)
            text = json.dumps(body)
            self.assertNotIn("provider account", text, query)
            self.assertNotIn("provider_account", text, query)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE correlation LIKE 'person:%' AND action LIKE '%provider account%'"), 0)


# ------------------------------------------------------------------ R5: local day, six places, case, currencies


class LocalDayTests(Base):
    def setUp(self):
        super().setUp()
        self.aid = self.account()["id"]
        self.path = f"/provider-accounts/{self.aid}/values"
        # 21:30 UTC on 5 November is 00:30 on 6 November in Kampala (UTC+3)
        self.at = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()

    def test_the_default_day_and_the_tomorrow_limit_follow_the_gateway_not_utc(self):
        self.assertEqual(self.rig.gw.settings.tz_offset_minutes, 180)
        with mock.patch.object(registry, "_now", lambda: self.at):
            self.assertEqual(self.value(self.aid, "plan", "Pro")["values"]["plan"]["as_of"], "2026-11-06")  # not 2026-11-05
            self.clear_rate()
            self.assertEqual(self.value(self.aid, "plan", "Pro", as_of="2026-11-07")["values"]["plan"]["as_of"], "2026-11-07")
            self.clear_rate()
            self.refused({"kind": "plan", "value": "Pro", "as_of": "2026-11-08"}, "bad_date", self.path)
        with mock.patch.object(registry, "_now", lambda: self.at - 3600):  # 20:30 UTC, 23:30 in Kampala: still 5 November
            self.clear_rate()
            self.assertEqual(self.value(self.aid, "plan", "Pro")["values"]["plan"]["as_of"], "2026-11-05")
            self.clear_rate()
            self.refused({"kind": "plan", "value": "Pro", "as_of": "2026-11-07"}, "bad_date", self.path)

    def test_the_offset_is_the_gateway_setting(self):
        ctx = types.SimpleNamespace(gw=types.SimpleNamespace(settings=types.SimpleNamespace(tz_offset_minutes=-300)))
        with mock.patch.object(registry, "_now", lambda: self.at):
            self.assertEqual(registry._today(ctx).isoformat(), "2026-11-05")  # 16:30 in UTC-5
            ctx.gw.settings.tz_offset_minutes = 180
            self.assertEqual(registry._today(ctx).isoformat(), "2026-11-06")


class SixPlacesTests(Base):
    def setUp(self):
        super().setUp()
        self.aid = self.account()["id"]
        self.path = f"/provider-accounts/{self.aid}/values"

    def test_more_than_six_decimal_places_are_refused_as_number_and_as_text_never_rounded(self):
        pairs = [(1e-7, "1e-7"), (0.0000001, "0.0000001"), (1.0000001, "1.0000001"), (0.1234567, "0.1234567"), (12.3456789, "12.3456789"),
                 (5e-324, "5e-324"), (0.1 + 0.2, "0.30000000000000004"), (1e-10, "0.0000000001")]
        for number, text in pairs:
            for given in (number, text):
                self.clear_rate()
                got, out = self.call("POST", self.path, {"kind": "quota_used", "value": given})
                self.assertEqual((got, out.get("code")), (400, "bad_number"), repr(given))
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM provider_account_values"), 0)
        for number, text in ((1e-06, "0.000001"), (0.5, "0.5"), (123456.123456, "123456.123456"), (2.5e-05, "0.000025"), (3, "3")):
            self.clear_rate()
            self.assertEqual(self.value(self.aid, "quota_used", number)["values"]["quota_used"]["value"], text)
            self.clear_rate()
            self.assertEqual(self.value(self.aid, "quota_used", text)["values"]["quota_used"]["value"], text)

    def test_amount_unit_boundaries(self):
        for given, stored in ((0, "0"), (0.0, "0"), (-0.0, "0"), ("0", "0"), ("0.000000", "0"), (1e-06, "0.000001"), (1e12, "1000000000000"),
                               ("999999999999.999999", "999999999999.999999")):
            self.assertEqual(registry._amount(given, "x"), stored, given)
        for given in ("1000000000000.000001", "1000000000000.5", -1e-06, "-0.000001"):
            with self.assertRaises(registry.ApiError, msg=given):
                registry._amount(given, "x")


class SecretCaseTests(Base):
    def test_secret_prefixes_are_matched_without_regard_to_case(self):
        aid = self.account()["id"]
        for text in ("SK-abc", "Sk-ant-123", "akia1234", "Akia team", "AKIAXXXX", "GHP_abc", "Ghp_abc", "XOXB-1", "Xoxp-1", "BEARER x",
                     "Bearer abc", "bEaReR token", "sk-"):
            self.clear_rate()
            for body, path in (({"tool_id": "codex", "route": "seat", "label": text}, "/provider-accounts"),
                               ({"kind": "plan", "value": text}, f"/provider-accounts/{aid}/values")):
                got, out = self.call("POST", path, body)
                self.assertEqual((got, out["code"]), (400, "looks_like_secret"), text)
                self.assertNotIn(text, json.dumps(out))
        for text in ("Skate plan", "Bearers club", "Ghpx", "akin", "xo plan", "Skip"):
            self.clear_rate()
            self.assertEqual(self.call("POST", f"/provider-accounts/{aid}/values", {"kind": "plan", "value": text})[0], 201, text)

    def test_a_required_plan_of_only_whitespace_is_refused_and_an_optional_blank_label_is_empty(self):
        aid = self.account()["id"]
        self.refused({"kind": "plan", "value": " \u00a0\u3000 "}, "bad_text", f"/provider-accounts/{aid}/values")
        self.assertEqual(self.account(tool="chatgpt", label="  \u00a0 ")["label"], "")


class CurrencySourceTests(unittest.TestCase):
    SIX_FILE = os.environ.get("SIX_LIST_ONE", "/tmp/probe_six/l1.xml")
    EXCLUDED = set("BOV CHE CHW CLF COU MXV USN UYI UYW XAD XAG XAU XBA XBB XBC XBD XDR XPD XPT XSU XTS XUA XXX".split())

    def test_the_set_is_the_documented_derivation_of_list_one(self):
        codes = registry.CURRENCIES
        self.assertEqual(len(codes), 155)
        self.assertTrue({"UGX", "USD", "EUR", "GBP", "KES", "XCG", "ZWG", "SLE", "VED", "XOF", "XAF", "XCD", "XPF"} <= codes)
        self.assertFalse({"ANG", "BGN", "ZWL", "XXX", "XTS", "XAU", "XAG", "XDR", "USN", "CHE", "CHW", "CLF", "UYI", "UYW", "BOV", "MXV",
                          "COU", "XAD", "XSU", "XUA", "usd", "AAA"} & codes)
        self.assertTrue(all(len(c) == 3 and c.isalpha() and c.isupper() for c in codes))
        source = open(registry.__file__, encoding="utf-8").read()
        self.assertIn("2026-09-17", source)
        self.assertIn("33139b438657d1cee116ba737807ea71d19d6de4b90f799a09c56f0cc6a1b0ff", source)

    def test_the_set_matches_the_published_file_when_it_is_present(self):
        if not os.path.exists(self.SIX_FILE):
            self.skipTest(f"Not run: the SIX List One file is not at {self.SIX_FILE} (set SIX_LIST_ONE)")
        import xml.etree.ElementTree as ET
        raw = open(self.SIX_FILE, "rb").read()
        if hashlib.sha256(raw).hexdigest() != "33139b438657d1cee116ba737807ea71d19d6de4b90f799a09c56f0cc6a1b0ff":
            self.skipTest("Not run: that file is not the 2026-09-17 List One the set was derived from")
        root = ET.fromstring(raw)
        listed = {e.findtext("Ccy") for e in root.iter("CcyNtry") if e.findtext("Ccy")}
        self.assertEqual(root.attrib["Pblshd"], "2026-09-17")
        self.assertEqual(registry.CURRENCIES, listed - self.EXCLUDED)


if __name__ == "__main__":
    unittest.main()
