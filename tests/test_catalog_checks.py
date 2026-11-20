"""Directive section 13, checks 1 and 5, across all 49 built-in tools (docs/CATALOG-AUDIT.md, last section).

Check 1, catalogue metadata correct: every built-in row is well formed on a fresh database, opens on a safe https address
that the gate governs as that same tool, and (once the v29 catalogue-facts columns exist) carries only valid modes, hosts
and dates. Whether an address is the provider's *official* app cannot be decided from the file; that needs the
provider's documentation and stays with the per-tool `last_verified` work.

Check 5, approved auth redirect behaviour: the official sign-in hosts (catalog.SIGNIN_HOSTS) are well formed, belong to
built-ins only, never become a tool's governed host or start address, widen only their own tool's workspace window, and
are reachable under the company Chrome pack.

The KNOWN_* sets name the audit's open defects. A test asserts that what it finds is a subset of them, so fixing a defect
never breaks a test, and a new defect always does. Shrink a set when its defect is fixed.
"""

import json
import os
import re
import unittest
from datetime import date
from urllib.parse import urlsplit

from gateway import catalog, device_open
from gateway.db import DB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME_PACK = os.path.join(ROOT, "deploy", "chrome-policy", "swangz-company-chrome.json")

ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
KINDS = {"api", "dev", "site"}
API_PROVIDERS = {"anthropic", "openai", "elevenlabs", "higgsfield"}  # the providers the gateway routes on the company key
DEV_TOOLS = {"claude-code": "anthropic", "codex": "openai"}

# Audit defect 5: desktop applications whose "address" is the product/pricing page (no web app to open).
KNOWN_URL_IS_PRICING = {"davinci-resolve", "topaz-video-ai"}
# Audit defect 1, what is left after PR #308: seedance's higgsfield.ai/seedance is higgsfield-ai's host (Open refuses
# it as inside_other_tool). Photoshop now opens on photoshop.adobe.com, so it may not come back.
KNOWN_OPENS_ON_ANOTHER_TOOLS_HOST = {"seedance"}
# Audit defect 1, shared gate hosts as (tool, host) pairs: PR #306 settled them all, so none may come back.
KNOWN_SHARED_HOSTS = set()
# Audit defect 2: a path where a hostname belongs. PR #306 removed github.com/copilot, so none may come back.
KNOWN_NOT_A_HOSTNAME = set()
# Audit defect 3: openai.com is DALL-E's gate host, so ChatGPT's sign-in host auth.openai.com is governed as DALL-E
# (pinned on purpose in tests/test_device_open.py, "as before: openai.com is DALL-E").
# PR #311: adobe.com is Premiere's gate host, so Adobe ID's sign-in hosts under it are governed as Premiere too. The
# workspace window may still follow them (SIGNIN_HOSTS); on personal devices the extension counts them as Premiere.
KNOWN_SIGN_IN_HOST_GOVERNED = {"auth.openai.com": "dall-e",
                               "auth.services.adobe.com": "adobe-premiere",
                               "auth-light.identity.adobe.com": "adobe-premiere",
                               "federatedid-na1.services.adobe.com": "adobe-premiere"}


def fresh():
    """The 49 built-ins as a new install holds them, through the same catalogue steps the gateway runs at start-up."""
    db = DB(":memory:")
    catalog.seed(db)
    catalog.refine(db)
    if hasattr(catalog, "settle_hosts"):  # PR #306: one owner per gate host
        catalog.settle_hosts(db)
    return db


def hosts_of(row):
    return [h.strip() for h in (row["hosts"] or "").split(",") if h.strip()]


def is_hostname(h):
    return bool(device_open.HOST.fullmatch(h)) and h == h.lower() and not h.startswith("www.")


def safe_https(url):
    """None when `url` is a plain https address on a named host, else why not."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        return "not https"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "userinfo"
    if parts.port not in (None, 443):
        return "port"
    if not device_open.HOST.fullmatch(parts.hostname or ""):
        return "host"
    if parts.query or parts.fragment:
        return "query or fragment"
    return None


class SeedShapeTests(unittest.TestCase):
    """Check 1 on the source of truth (catalog.SEED / DETAILS), before any database."""

    def setUp(self):
        self.rows = [dict(zip(catalog.FIELDS, row)) for row in catalog.SEED]

    def test_49_rows_with_unique_ids_and_names(self):
        for row in catalog.SEED:
            self.assertEqual(len(row), len(catalog.FIELDS), row[0])
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), 49)
        self.assertEqual(len(set(ids)), 49, "duplicate tool id")
        self.assertEqual(len({r["name"].casefold() for r in self.rows}), 49, "duplicate tool name")
        for r in self.rows:
            with self.subTest(r["id"]):
                self.assertRegex(r["id"], ID)
                self.assertTrue(r["name"].strip() and r["name"] == r["name"].strip())
                self.assertTrue(r["category"].strip())

    def test_kind_and_provider_agree(self):
        for r in self.rows:
            with self.subTest(r["id"]):
                self.assertIn(r["kind"], KINDS)
                if r["kind"] == "api":
                    self.assertIn(r["provider"], API_PROVIDERS)
                elif r["kind"] == "dev":
                    self.assertEqual(DEV_TOOLS.get(r["id"]), r["provider"])
                    self.assertEqual(r["hosts"], [], "a command-line agent is not a website the gate governs")
                else:
                    self.assertEqual(r["provider"], "", "a website tool is never routed on a company key")
        self.assertEqual({r["id"] for r in self.rows if r["kind"] == "dev"}, set(DEV_TOOLS))
        for provider in API_PROVIDERS:  # the proxy finds its tool by provider (catalog.provider_tool)
            self.assertEqual(sum(r["kind"] == "api" and r["provider"] == provider for r in self.rows), 1, provider)

    def test_addresses_are_safe_https_and_the_open_address_is_not_the_pricing_page(self):
        same = set()
        for r in self.rows:
            with self.subTest(r["id"]):
                self.assertIsNone(safe_https(r["url"]), r["url"])
                if r["pricing_url"]:
                    self.assertIsNone(safe_https(r["pricing_url"]), r["pricing_url"])
                if r["url"] == r["pricing_url"]:
                    same.add(r["id"])
        self.assertLessEqual(same, KNOWN_URL_IS_PRICING, "the address people open is a pricing page")

    def test_gate_hosts_are_bare_lowercase_hostnames(self):
        bad = set()
        for r in self.rows:
            self.assertEqual(len(r["hosts"]), len(set(r["hosts"])), r["id"])
            bad |= {(r["id"], h) for h in r["hosts"] if not is_hostname(h)}
        self.assertLessEqual(bad, KNOWN_NOT_A_HOSTNAME)

    def test_plans_and_entry_price(self):
        for r in self.rows:
            with self.subTest(r["id"]):
                self.assertIsInstance(r["plans"], list)
                self.assertIsInstance(r["entry_usd"], (int, float))
                self.assertGreaterEqual(r["entry_usd"], 0)
                for plan in r["plans"]:
                    self.assertTrue(isinstance(plan.get("name"), str) and plan["name"].strip(), plan)
                    self.assertIsInstance(plan.get("monthlyUSD"), (int, float), plan)
                    self.assertGreaterEqual(plan["monthlyUSD"], 0, plan)
                    for field in ("included", "unitCostUSD"):
                        if plan.get(field) is not None:
                            self.assertGreaterEqual(plan[field], 0, plan)
                paid = [p["monthlyUSD"] for p in r["plans"] if p["monthlyUSD"]]
                self.assertEqual(r["entry_usd"], min(paid) if paid else 0, "the entry price is the cheapest paid plan")

    def test_every_tool_has_exactly_one_description_and_colour(self):
        self.assertEqual(set(catalog.DETAILS), {r["id"] for r in self.rows})
        for tid, (description, colour) in catalog.DETAILS.items():
            with self.subTest(tid):
                self.assertTrue(description.strip() and description.rstrip().endswith("."), description)
                self.assertRegex(colour, COLOUR)


class FreshDatabaseTests(unittest.TestCase):
    """Check 1 on what a new install actually holds, and where Open sends people."""

    def setUp(self):
        self.db = fresh()
        self.addCleanup(self.db.close)
        self.rows = {r["id"]: dict(r) for r in self.db.q("SELECT * FROM tools")}
        self.seed = {row[0]: dict(zip(catalog.FIELDS, row)) for row in catalog.SEED}
        self.columns = {r["name"] for r in self.db.q("PRAGMA table_info(tools)")}

    def test_the_built_ins_arrive_as_seeded_enabled_and_described(self):
        self.assertEqual(set(self.rows), set(self.seed))
        for tid, row in self.rows.items():
            with self.subTest(tid):
                want = self.seed[tid]
                for field in ("name", "category", "kind", "provider", "pricing_url", "entry_usd"):
                    self.assertEqual(row[field], want[field], field)
                self.assertEqual(json.loads(row["plans"]), want["plans"])
                self.assertEqual((row["builtin"], row["archived"]), (1, 0))
                self.assertEqual((row["description"], row["color"]), catalog.DETAILS[tid])
                self.assertIn(row["signin"], catalog.SIGNIN)
                self.assertEqual(row["launch_url"], "", "no company sign-in link is invented for a new install")

    def test_open_goes_to_a_safe_address_the_gate_counts_as_the_same_tool(self):
        index = catalog.host_index(self.db)
        elsewhere = {}
        for tid, row in self.rows.items():
            with self.subTest(tid):
                target = catalog.launch_target(row)
                self.assertEqual(target, row["url"])
                self.assertTrue(target.startswith("https://"), target)
                if row["kind"] == "dev":
                    continue  # a command-line agent: the address is its documentation, not a governed site
                owner = catalog.match_host(index, urlsplit(target).hostname)
                self.assertIsNotNone(owner, f"{target} is not governed by the access gate at all")
                if owner["id"] != tid:
                    elsewhere[tid] = owner["id"]
        self.assertLessEqual(set(elsewhere), KNOWN_OPENS_ON_ANOTHER_TOOLS_HOST, elsewhere)

    def test_every_governed_host_resolves_to_exactly_its_tool(self):
        index = catalog.host_index(self.db)
        for tid, row in self.rows.items():
            for h in hosts_of(row):
                if not is_hostname(h) or (tid, h) in KNOWN_NOT_A_HOSTNAME:
                    continue
                owner = catalog.match_host(index, h)
                if owner["id"] != tid:
                    self.assertIn((tid, h), KNOWN_SHARED_HOSTS, f"{h} of {tid} is governed as {owner['id']}")

    def test_catalogue_facts_are_valid_when_the_columns_exist(self):
        """PR #304 (v29): info_url, modes, oauth_hosts, last_verified. Empty means not verified, never a guess."""
        needed = {"info_url", "modes", "oauth_hosts", "last_verified"}
        self.assertLessEqual(needed, self.columns, "catalogue-facts columns (v29) are missing or renamed")
        modes = set(getattr(catalog, "MODES", ()))
        self.assertTrue(modes)
        gate = {h for row in self.rows.values() for h in hosts_of(row)}
        for tid, row in self.rows.items():
            with self.subTest(tid):
                if row["info_url"]:
                    self.assertIsNone(safe_https(row["info_url"]), row["info_url"])
                for mode in filter(None, (m.strip() for m in row["modes"].split(","))):
                    self.assertIn(mode, modes)
                for h in filter(None, (h.strip() for h in row["oauth_hosts"].split(","))):
                    self.assertTrue(is_hostname(h), h)
                    self.assertNotIn(h, gate, "a sign-in host is never a gate host")
                if row["last_verified"]:
                    self.assertLessEqual(date.fromisoformat(row["last_verified"]), date.today())
                    self.assertTrue(row["info_url"] or row["url"], "a verified row says where it was checked")


class SignInHostTests(unittest.TestCase):
    """Check 5: approved auth redirect behaviour, for all 49 tools rather than the three that have sign-in hosts."""

    @classmethod
    def setUpClass(cls):
        cls.db = fresh()
        cls.rows = {r["id"]: dict(r) for r in cls.db.q("SELECT * FROM tools")}
        cls.sign_in = {h for hosts in catalog.SIGNIN_HOSTS.values() for h in hosts}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_sign_in_hosts_are_well_formed_and_for_built_ins_only(self):
        self.assertTrue(catalog.SIGNIN_HOSTS)
        for tid, hosts in catalog.SIGNIN_HOSTS.items():
            with self.subTest(tid):
                self.assertIn(tid, self.rows, "sign-in hosts for a tool that is not a built-in")
                self.assertIsInstance(hosts, tuple)
                self.assertTrue(hosts)
                self.assertEqual(len(hosts), len(set(hosts)))
                for h in hosts:
                    self.assertTrue(is_hostname(h), h)

    def test_a_sign_in_host_is_never_a_gate_host_and_the_gate_governs_none_but_the_known_one(self):
        gate = {h for row in self.rows.values() for h in hosts_of(row)}
        self.assertFalse(self.sign_in & gate, "a sign-in host would be governed as a tool")
        index = catalog.host_index(self.db)
        governed = {h: catalog.match_host(index, h)["id"] for h in self.sign_in if catalog.match_host(index, h)}
        self.assertLessEqual(governed.items(), KNOWN_SIGN_IN_HOST_GOVERNED.items(), governed)
        self.assertIsNone(catalog.match_host(index, "accounts.google.com"))

    def test_only_a_tools_own_sign_in_hosts_widen_its_workspace_window(self):
        for tid, row in self.rows.items():
            with self.subTest(tid):
                own = device_open.own_hosts(row)
                allowed = device_open.allowed_hosts(row)
                extra = [h for h in catalog.SIGNIN_HOSTS.get(tid, ()) if h not in own]
                self.assertEqual(allowed, own + extra)
                self.assertFalse(set(own) & self.sign_in, "own hosts never include a sign-in host")
                # the same row added by an admin (not a built-in) gets no sign-in hosts at all
                self.assertEqual(device_open.allowed_hosts(dict(row, builtin=0)), own)

    def test_no_tool_may_start_on_a_sign_in_host_and_only_its_own_may_follow_one(self):
        for tid, row in self.rows.items():
            own, allowed = device_open.own_hosts(row), device_open.allowed_hosts(row)
            mine = set(catalog.SIGNIN_HOSTS.get(tid, ()))
            for h in sorted(self.sign_in):
                url = f"https://{h}/signin"
                with self.subTest(tool=tid, host=h):
                    governed_by_own = any(h == o or h.endswith("." + o) for o in own)
                    if not governed_by_own:  # dall-e's openai.com covers auth.openai.com (KNOWN_SIGN_IN_HOST_GOVERNED)
                        self.assertEqual(device_open.check_url(url, own), "host_not_allowed", "a start address")
                    if h in mine or governed_by_own:
                        self.assertIsNone(device_open.check_url(url, allowed))
                    else:
                        self.assertEqual(device_open.check_url(url, allowed), "host_not_allowed", "another tool's sign-in")

    def test_sign_in_hosts_with_credentials_or_tricks_are_still_refused(self):
        allowed = device_open.allowed_hosts(self.rows["chatgpt"])
        for url in ("https://accounts.google.com/o?access_token=x", "https://accounts.google.com/o#id_token=x",
                    "https://user:pw@accounts.google.com/", "https://accounts.google.com:8443/",
                    "http://accounts.google.com/", "https://accounts.google.com.evil.example/",
                    "https://evilaccounts.google.com/"):
            with self.subTest(url):
                self.assertIsNotNone(device_open.check_url(url, allowed))

    def test_every_sign_in_host_is_reachable_under_the_company_chrome_pack(self):
        """Chrome URLAllowlist: "host" covers the host and its subdomains, ".host" the exact host only."""
        with open(CHROME_PACK, encoding="utf-8") as f:
            allow = json.load(f)["URLAllowlist"]

        def allowed(host):
            for entry in allow:
                if "/" in entry:
                    continue
                if entry.startswith("."):
                    if host == entry[1:]:
                        return True
                elif host == entry or host.endswith("." + entry):
                    return True
            return False

        for h in sorted(self.sign_in):
            with self.subTest(h):
                self.assertTrue(allowed(h), f"{h} is blocked by the company Chrome pack")


if __name__ == "__main__":
    unittest.main()
