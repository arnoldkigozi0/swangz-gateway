"""The manual provider-account registry (Amendment 01, task 1; schema v24).

A person records which AI subscription they hold and may add what they know about it: plan, quota, period end,
credit balance, monthly price. Everything here is a declaration by the holder. Nothing is fetched from a provider,
nothing is confirmed, and nothing here feeds entitlements, policies, turns, subscriptions, licences, spend,
notifications or search: a declaration is shown as a declaration and counted nowhere.

Staff routes (own accounts only, ordinary signed-in web session, never paused, never the extension or a device key):
  GET  /api/provider-accounts            POST /api/provider-accounts
  GET  /api/provider-accounts/<id>       POST /api/provider-accounts/<id>/values      POST /api/provider-accounts/<id>/end
Console routes (read only; the field ceiling below applies to every console user, owners included):
  GET /admin/api/provider-accounts       GET /admin/api/provider-accounts/<id>

What the console may see is the record kind's field ceiling intersected with the actor's areas (govern, money), then
the union across those areas. `FIELD_CEILING` below is that table; it is the only place visibility is decided.
"""

import math
import re
import sqlite3
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from . import admin, authz, staff
from .admin import ApiError

ROUTES_OPEN = ("individual", "seat")  # api / enterprise exist as enums only: no route can write them
KINDS = ("plan", "quota_limit", "quota_used", "period_end", "credit_balance", "monthly_price")
FINANCIAL = ("credit_balance", "monthly_price")
MAX_ACTIVE_ACCOUNTS = 20
MAX_VALUES_PER_ACCOUNT = 200
WRITES_PER_MINUTE = 20
READS_PER_MINUTE = 120
LABEL_MAX, PLAN_MAX = 80, 60
LIST_LIMIT = 200
MAX_AMOUNT = Decimal(10) ** 12
DECIMAL_PLACES = Decimal("0.000001")

# ---------------------------------------------------------------- who sees what (Sentinel D-019)
# Per record kind, per audience: the account fields and the value kinds visible. A console user sees the union over the
# areas they hold. An audience with no entry for a kind sees no such record at all (it is 404, as if it did not exist).
CORE = frozenset({"id", "tool_id", "tool", "route", "status", "created", "ended"})
SEAT_EXTRA = frozenset({"holder", "payer", "assertion", "confirmed", "label"})
HOLDER_FIELDS = CORE | {"payer", "assertion", "confirmed", "label", "created_by"}
FIELD_CEILING = {
    ("individual", "holder"): (HOLDER_FIELDS, frozenset(KINDS)),
    ("seat", "holder"): (HOLDER_FIELDS, frozenset(KINDS)),
    ("individual", "govern"): (CORE, frozenset()),
    ("seat", "govern"): (CORE | SEAT_EXTRA, frozenset({"plan", "quota_limit", "quota_used", "period_end"})),
    ("seat", "money"): (CORE | SEAT_EXTRA, frozenset({"credit_balance", "monthly_price"})),
}
CONSOLE_AREAS = ("govern", "money")

# Active ISO 4217 currency codes.
CURRENCIES = frozenset("""
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY
COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR
IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR
MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD
SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED VES VND VUV WST XAF XCD
XOF XPF YER ZAR ZMW ZWL""".split())

# ---------------------------------------------------------------- bounded, secret-resistant input

_KEY_LIKE = re.compile(r"[A-Za-z0-9_\-+/=.]{32,}")
_SECRET_PREFIXES = ("sk-", "AKIA", "ghp_", "xox")


def _bad(message, code="bad_request"):
    return ApiError(400, message, code)


def _text(value, name, limit, *, required):
    """NFC, trimmed, bounded, and refused when it carries a control or bidi-override character or looks like a secret.
    The refusal never repeats the text."""
    if not isinstance(value, str):
        raise _bad(f"{name} must be text", "bad_text")
    s = unicodedata.normalize("NFC", value)
    for ch in s:
        if unicodedata.category(ch) in ("Cc", "Zl", "Zp") or "‪" <= ch <= "‮" or "⁦" <= ch <= "⁩":
            raise _bad(f"{name} has a character that is not allowed", "bad_text")
    s = s.strip()
    if not s:
        if required:
            raise _bad(f"{name} is required", "bad_text")
        return ""
    if len(s) > limit:
        raise _bad(f"{name} is longer than {limit} characters", "too_long")
    if s.startswith(_SECRET_PREFIXES) or s[:7].lower() == "bearer " or _KEY_LIKE.search(s):
        raise _bad(f"{name} looks like a key or a token. Don't put secrets here.", "looks_like_secret")
    return s


def _amount(value, name):
    """A finite decimal from 0 to 1e12, as a canonical string (at most six decimal places)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _bad(f"{name} must be a number", "bad_number")
    try:
        if isinstance(value, str):
            if not re.fullmatch(r"[0-9]{1,13}(\.[0-9]{1,6})?", value):
                raise ValueError
            number = Decimal(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError
            number = Decimal(repr(value))
        else:
            number = Decimal(value)
        if number < 0 or number > MAX_AMOUNT:
            raise ValueError
        number = number.quantize(DECIMAL_PLACES)
    except (ValueError, ArithmeticError):
        raise _bad(f"{name} must be a number from 0 to 1000000000000", "bad_number")
    if number == 0:
        number = Decimal(0)
    out = format(number, "f")
    return out.rstrip("0").rstrip(".") if "." in out else out


def _day(value, name, last):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise _bad(f"{name} must be a date like 2026-12-31", "bad_date")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise _bad(f"{name} must be a real date", "bad_date")
    if day < date(2000, 1, 1) or day > last:
        raise _bad(f"{name} is outside the dates this accepts", "bad_date")
    return value


def _strict(body, allowed):
    if set(body) - set(allowed):
        raise _bad("That request has a field this form does not take.", "unknown_field")


def _today():
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------- reading

SELECT_ACCOUNT = ("SELECT a.*, t.name AS tool_name, p.name AS holder_name FROM provider_accounts a"
                  " JOIN tools t ON t.id = a.tool_id LEFT JOIN people p ON p.id = a.holder_person_id")


def _declared(row):
    out = {"state": "declared", "id": row["id"], "value": row["value"], "as_of": row["as_of"], "recorded": row["recorded"],
           "source": "holder_declared", "confirmed": False}
    if row["currency"]:
        out["currency"] = row["currency"]
    return out


def _current_values(db, ids):
    """{account_id: {kind: latest value row}}: the newest row of each kind is the current one."""
    out = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        marks = ",".join("?" * len(chunk))
        for v in db.q(f"SELECT v.* FROM provider_account_values v WHERE v.account_id IN ({marks}) AND v.id = ("
                      "SELECT MAX(id) FROM provider_account_values WHERE account_id = v.account_id AND kind = v.kind)", chunk):
            out.setdefault(v["account_id"], {})[v["kind"]] = v
    return out


def _shape(row, current, audiences):
    """The account as the given audiences ('holder', 'govern', 'money') may see it, or None when none of them sees this
    kind of record at all. A value kind outside the ceiling is left out entirely; one inside it that nobody has
    recorded is {state: unavailable}, never a zero."""
    fields, kinds = set(), set()
    for audience in audiences:
        ceiling = FIELD_CEILING.get((row["route"], audience))
        if ceiling:
            fields |= ceiling[0]
            kinds |= ceiling[1]
    if not fields:
        return None
    out = {}
    for name in sorted(fields):
        if name == "tool":
            out[name] = row["tool_name"]
        elif name == "holder":
            out[name] = {"person_id": row["holder_person_id"], "name": row["holder_name"]}
        elif name == "confirmed":
            out[name] = False
        elif name == "created_by":
            out[name] = row["created_by"]
        else:
            out[name] = row[name]
    if kinds:
        out["values"] = {k: (_declared(current[k]) if k in current else {"state": "unavailable"}) for k in KINDS if k in kinds}
    return out


def _history(db, account_id):
    return [dict(_declared(v), kind=v["kind"]) for v in
            db.q("SELECT * FROM provider_account_values WHERE account_id = ? ORDER BY id DESC", (account_id,))]


def _id(raw):
    try:
        n = int(raw)
    except ValueError:
        raise ApiError(404, "no such account", "no_such_account")
    if n > 2 ** 62:
        raise ApiError(404, "no such account", "no_such_account")
    return n


def _throttle(ctx, kind, limit):
    if ctx.gw.ratelimit.over(("registry", kind, ctx.person["id"]), limit):
        raise ApiError(429, "Too many requests in a minute. Wait a little and try again.", "rate_limited")


def _own(ctx, account_id):
    """The signed-in person's own account, or the same 404 whether it is missing or someone else's."""
    row = ctx.db.one(SELECT_ACCOUNT + " WHERE a.id = ? AND a.holder_person_id = ? AND a.account_holder_kind = 'person'",
                     (account_id, ctx.person["id"]))
    if not row:
        raise ApiError(404, "no such account", "no_such_account")
    return row


def _audit(ctx, action, account_id, before, after):
    """Ids, route, status and value kinds only: a label or a value is never written to the audit log."""
    ctx.gw.audit(ctx.person["name"], action, f"provider_account:{account_id}", "", ctx.ip, before=before, after=after,
                 correlation=f"person:{ctx.person['id']}")


# ---------------------------------------------------------------- staff routes (the holder's own accounts)


@staff.route("GET", r"/provider-accounts")
def list_own(ctx):
    _throttle(ctx, "read", READS_PER_MINUTE)
    status = ctx.arg("status", "all")
    if status not in ("all", "active", "ended"):
        raise _bad("status is active, ended or all", "bad_filter")
    where, args = "a.holder_person_id = ? AND a.account_holder_kind = 'person'", [ctx.person["id"]]
    if status != "all":
        where += " AND a.status = ?"
        args.append(status)
    rows = ctx.db.q(f"{SELECT_ACCOUNT} WHERE {where} ORDER BY a.id DESC LIMIT {LIST_LIMIT}", args)
    current = _current_values(ctx.db, [r["id"] for r in rows])
    return {"items": [_shape(r, current.get(r["id"], {}), ("holder",)) for r in rows],
            "limits": {"active_accounts": MAX_ACTIVE_ACCOUNTS, "values_per_account": MAX_VALUES_PER_ACCOUNT},
            "routes": list(ROUTES_OPEN), "value_kinds": list(KINDS),
            "note": "Declared by you. Swangz does not check these with the provider."}


@staff.route("GET", r"/provider-accounts/(?P<aid>[0-9]+)")
def read_own(ctx, aid):
    _throttle(ctx, "read", READS_PER_MINUTE)
    row = _own(ctx, _id(aid))
    out = _shape(row, _current_values(ctx.db, [row["id"]]).get(row["id"], {}), ("holder",))
    out["history"] = _history(ctx.db, row["id"])
    return out


@staff.route("POST", r"/provider-accounts")
def register(ctx):
    _throttle(ctx, "write", WRITES_PER_MINUTE)
    body = ctx.body
    _strict(body, ("tool_id", "route", "payer", "label"))
    tool_id, route = body.get("tool_id"), body.get("route")
    if not isinstance(tool_id, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", tool_id):
        raise _bad("tool_id is required", "bad_tool")
    if route in ("api", "enterprise"):
        raise _bad("That route can't be registered here.", "route_unavailable")
    if route not in ROUTES_OPEN:
        raise _bad("route is individual or seat", "bad_route")
    payer = body.get("payer")
    if route == "individual":
        if payer not in ("person", "none"):
            raise _bad("payer is person or none for an individual subscription", "bad_payer")
    else:
        if payer not in (None, "company"):
            raise _bad("a company seat is paid by the company", "bad_payer")
        payer = "company"
    label = _text(body["label"], "label", LABEL_MAX, required=False) if "label" in body else ""
    tool = ctx.db.one("SELECT id, signin, archived FROM tools WHERE id = ?", (tool_id,))
    if not tool or tool["archived"]:
        raise _bad("no such tool", "bad_tool")
    if tool["signin"] in ("shared", "api"):
        raise _bad("This tool can't be registered here.", "tool_not_allowed")
    person_id, now = ctx.person["id"], time.time()
    with ctx.db.tx():
        if ctx.db.scalar("SELECT COUNT(*) FROM provider_accounts WHERE holder_person_id = ? AND status = 'active'",
                         (person_id,)) >= MAX_ACTIVE_ACCOUNTS:
            raise ApiError(409, f"You can have {MAX_ACTIVE_ACCOUNTS} active accounts. End one first.", "account_limit")
        try:
            account_id = ctx.db.x(
                "INSERT INTO provider_accounts(account_holder_kind, holder_person_id, tool_id, route, payer, assertion, label,"
                " status, created, created_by) VALUES('person', ?, ?, ?, ?, 'holder_declared', ?, 'active', ?, ?)",
                (person_id, tool_id, route, payer, label, now, person_id)).lastrowid
        except sqlite3.IntegrityError:
            raise ApiError(409, "You already have this account registered.", "already_registered")
        _audit(ctx, "registered a provider account", account_id, None, {"status": "active", "route": route, "tool_id": tool_id})
    row = _own(ctx, account_id)
    return 201, _shape(row, {}, ("holder",))


@staff.route("POST", r"/provider-accounts/(?P<aid>[0-9]+)/values")
def add_value(ctx, aid):
    _throttle(ctx, "write", WRITES_PER_MINUTE)
    row = _own(ctx, _id(aid))
    body = ctx.body
    _strict(body, ("kind", "value", "currency", "as_of"))
    kind = body.get("kind")
    if kind not in KINDS:
        raise _bad("kind is not one of the kinds this records", "bad_kind")
    if "value" not in body:
        raise _bad("value is required", "bad_value")
    currency = body.get("currency")
    if kind in FINANCIAL:
        if not isinstance(currency, str) or currency not in CURRENCIES:
            raise _bad("currency is a three-letter code like UGX or USD", "bad_currency")
    elif "currency" in body:
        raise _bad("currency only goes with a balance or a price", "bad_currency")
    else:
        currency = ""
    if kind == "plan":
        value = _text(body["value"], "plan", PLAN_MAX, required=True)
    elif kind == "period_end":
        value = _day(body["value"], "period_end", date(2100, 12, 31))
    else:
        value = _amount(body["value"], kind)
    today = _today()
    as_of = _day(body["as_of"], "as_of", today + timedelta(days=1)) if "as_of" in body else today.isoformat()
    if row["status"] != "active":
        raise ApiError(409, "This account has ended, so it takes no more values.", "account_ended")
    with ctx.db.tx():
        if ctx.db.scalar("SELECT COUNT(*) FROM provider_account_values WHERE account_id = ?", (row["id"],)) >= MAX_VALUES_PER_ACCOUNT:
            raise ApiError(409, f"An account keeps {MAX_VALUES_PER_ACCOUNT} values. End it and register it again.", "value_limit")
        try:
            value_id = ctx.db.x(
                "INSERT INTO provider_account_values(account_id, kind, value, currency, as_of, recorded, recorded_by)"
                " VALUES(?,?,?,?,?,?,?)", (row["id"], kind, value, currency, as_of, time.time(), ctx.person["id"])).lastrowid
        except sqlite3.IntegrityError:
            raise ApiError(409, "This account has ended, so it takes no more values.", "account_ended")
        _audit(ctx, "recorded a provider account value", row["id"], None, {"kind": kind, "value_id": value_id})
    return 201, _shape(row, _current_values(ctx.db, [row["id"]]).get(row["id"], {}), ("holder",))


@staff.route("POST", r"/provider-accounts/(?P<aid>[0-9]+)/end")
def end(ctx, aid):
    _throttle(ctx, "write", WRITES_PER_MINUTE)
    _own(ctx, _id(aid))
    _strict(ctx.body, ())
    with ctx.db.tx():
        row = _own(ctx, int(aid))
        if row["status"] == "active":
            ctx.db.x("UPDATE provider_accounts SET status = 'ended', ended = ? WHERE id = ? AND status = 'active'",
                     (time.time(), row["id"]))
            _audit(ctx, "ended a provider account", row["id"], {"status": "active"}, {"status": "ended"})
    row = _own(ctx, int(aid))
    return _shape(row, _current_values(ctx.db, [row["id"]]).get(row["id"], {}), ("holder",))


# ---------------------------------------------------------------- console routes (read only, field-filtered)


def _audiences(ctx):
    return tuple(a for a in CONSOLE_AREAS if authz.can(ctx.admin, a))


@admin.route("GET", r"/provider-accounts", area=CONSOLE_AREAS)
def console_list(ctx):
    audiences = _audiences(ctx)
    if not audiences:  # the dispatcher already refuses these; kept so the handler is safe on its own
        raise ApiError(403, "your role can't see that")
    status = ctx.arg("status", "all")
    if status not in ("all", "active", "ended"):
        raise ApiError(400, "status is active, ended or all")
    where, args = [], []
    if "govern" not in audiences:  # money alone sees seats only
        where.append("a.route = 'seat'")
    else:
        where.append("a.route IN ('individual', 'seat')")
    if status != "all":
        where.append("a.status = ?")
        args.append(status)
    tool = ctx.arg("tool")
    if tool:
        where.append("a.tool_id = ?")
        args.append(tool)
    limit = min(max(ctx.arg("limit", LIST_LIMIT, int), 1), LIST_LIMIT)
    rows = ctx.db.q(f"{SELECT_ACCOUNT} WHERE {' AND '.join(where)} ORDER BY a.id DESC LIMIT {limit}", args)
    current = _current_values(ctx.db, [r["id"] for r in rows])
    items = [s for s in (_shape(r, current.get(r["id"], {}), audiences) for r in rows) if s is not None]
    return {"items": items, "note": "Declared by the holder and not confirmed with the provider."}


@admin.route("GET", r"/provider-accounts/(?P<aid>[0-9]+)", area=CONSOLE_AREAS)
def console_read(ctx, aid):
    audiences = _audiences(ctx)
    row = ctx.db.one(SELECT_ACCOUNT + " WHERE a.id = ?", (_id(aid),)) if audiences else None
    out = _shape(row, _current_values(ctx.db, [row["id"]]).get(row["id"], {}), audiences) if row else None
    if out is None:
        raise ApiError(404, "no such account", "no_such_account")
    return out
