"""Private workspaces on the Workspace Agent: a browser that belongs to one person at a time, keeps their
own profile, is stopped gracefully when they're done, and sends its traffic through the egress proxy."""

import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from workspace_agent import egress
from workspace_agent.agent import AgentError, ConfigError, check_config, policy_for

from .test_workspace_agent import TOKEN, AgentRig, signin_in

os.environ.setdefault("SWANGZ_WORKSPACE_ACCESS_LOG", "0")
PERSONAL = {"browsers": [21, 22]}


class PersonalRig(AgentRig):
    def __init__(self, **extra):
        extra.setdefault("personal", dict(PERSONAL))
        super().__init__(**extra)
        self.p1, self.p2 = self.nekos["personal-21"], self.nekos["personal-22"]

    def open(self, user, name="Nansubuga Grace"):
        return self.ready("p" + user.split("-")[-1], user, name, tool="personal")


class PersonalConfigTests(unittest.TestCase):
    base = {"token": TOKEN, "public_url": "https://ws.example.test", "public_ip": "203.0.113.7", "data": "/tmp/x"}

    def test_private_browsers_join_the_pool_with_their_own_numbers(self):
        cfg = check_config({**self.base, "tools": {"claude": {"browsers": [1]}}, "personal": {"browsers": [21, 22]}})
        self.assertEqual(sorted(cfg["browsers"]), ["claude-1", "personal-21", "personal-22"])
        self.assertTrue(cfg["browsers"]["personal-21"]["personal"])
        self.assertFalse(cfg["browsers"]["claude-1"]["personal"])
        self.assertEqual((cfg["personal"]["idle_minutes"], cfg["personal"]["max_hours"], cfg["personal"]["egress"]), (20, 12, True))

    def test_private_browsers_alone_are_a_valid_server(self):
        self.assertEqual(list(check_config({**self.base, "personal": {"browsers": [5]}})["browsers"]), ["personal-5"])

    def test_the_name_is_reserved_and_bad_values_are_refused(self):
        with self.assertRaisesRegex(ConfigError, "reserved"):
            check_config({**self.base, "tools": {"personal": {"browsers": [1]}}})
        with self.assertRaises(ConfigError):  # a number used by a tool as well
            check_config({**self.base, "tools": {"claude": {"browsers": [21]}}, "personal": {"browsers": [21]}})
        for bad in ({"browsers": "21"}, {"browsers": [21], "idle_minutes": 0}, {"browsers": [21], "max_hours": "x"},
                    {"browsers": [21], "start_url": "ftp://x"}, {"browsers": [100]}, "yes"):
            with self.assertRaises(ConfigError, msg=bad):
                check_config({**self.base, "personal": bad})

    def test_without_the_block_nothing_changes(self):
        cfg = check_config({**self.base, "tools": {"claude": {"browsers": [1]}}})
        self.assertEqual(list(cfg["browsers"]), ["claude-1"])
        self.assertEqual(cfg["personal"]["browsers"], [])


class PolicyTests(unittest.TestCase):
    def test_a_private_browser_is_forced_through_the_proxy_and_has_no_side_door(self):
        b = {"start_url": "https://www.google.com/", "fresh_start": False}
        p = policy_for(b, "host.docker.internal:8821")
        self.assertEqual(p["ProxySettings"], {"ProxyMode": "fixed_servers", "ProxyServer": "host.docker.internal:8821"})
        self.assertEqual((p["DnsOverHttpsMode"], p["QuicAllowed"], p["WebRtcIPHandling"]),
                         ("off", False, "disable_non_proxied_udp"))
        self.assertEqual(p["DeveloperToolsAvailability"], 2)
        self.assertEqual(p["ExtensionInstallBlocklist"], ["*"])
        self.assertIn("chrome://net-internals", p["URLBlocklist"])
        self.assertEqual(p["RestoreOnStartup"], 1)  # tabs come back where they were
        self.assertNotIn("ProxySettings", policy_for(b))  # a shared browser is unchanged


class PersonalBrowserTests(unittest.TestCase):
    def setUp(self):
        self.rig = PersonalRig()
        self.addCleanup(self.rig.close)
        self.agent, self.docker = self.rig.agent, self.rig.docker

    def args(self, slot):
        return self.docker.containers["swangz-ws-" + slot]["args"]

    def holder(self, slot):
        return next(b for b in self.rig.call("GET", "/status")[1]["personal"] if b["slot"] == slot)["holder"]

    def test_a_person_gets_a_browser_with_their_own_profile_and_a_proxy(self):
        status, out = self.rig.open("swangz-4")
        self.assertEqual((status, out["state"], out["slot"]), (200, "ready", "personal-21"))
        self.assertTrue(out["url"].startswith("https://ws.example.test/personal-21/?usr=swangz-4&pwd="))
        args = self.args("personal-21")
        self.assertIn("swangz-ws-profile-me-swangz-4:/home/neko/.config/chromium", args)  # theirs, not the slot's
        self.assertNotIn("swangz-ws-profile-personal-21:/home/neko/.config/chromium", args)
        self.assertIn(["--add-host", "host.docker.internal:host-gateway"], [args[i:i + 2] for i in range(len(args) - 1)])
        with open(next(a.split(":")[0] for a in args if a.endswith("policies.json:ro")), encoding="utf-8") as f:
            policy = json.load(f)
        self.assertEqual(policy["ProxySettings"]["ProxyServer"], "host.docker.internal:8821")
        self.assertEqual(self.holder("personal-21")["user"], "swangz-4")

    def test_opening_again_is_the_same_browser_and_a_second_person_gets_another(self):
        self.assertEqual(self.rig.open("swangz-4")[1]["slot"], "personal-21")
        self.assertEqual(self.rig.open("swangz-4")[1]["slot"], "personal-21")
        self.assertEqual(self.rig.open("swangz-5", "Okello Brian")[1]["slot"], "personal-22")
        status, out = self.rig.open("swangz-6", "Akello Joy")
        self.assertEqual(status, 409)
        self.assertIn("in use", out["error"])
        runs = [n for c, n in self.docker.log if c == "run"]
        self.assertEqual(sorted(runs), ["swangz-ws-personal-21", "swangz-ws-personal-22"])  # not restarted by re-opening

    def test_letting_go_saves_the_profile_then_stops_and_never_recycles(self):
        self.rig.open("swangz-4")
        status, out = self.rig.call("POST", "/release", {"lease": "p4"})
        self.assertEqual((status, out["slot"]), (200, "personal-21"))
        steps = [(c, n) for c, n in self.docker.log if n == "swangz-ws-personal-21"]
        self.assertLess(steps.index(("stop", "swangz-ws-personal-21")), len(steps) - 1 - steps[::-1].index(("rm", "swangz-ws-personal-21")))
        self.assertEqual(sum(1 for c, _ in steps if c == "run"), 1)  # no fresh browser started for the next person
        self.assertNotIn("swangz-ws-personal-21", self.docker.containers)
        self.assertIsNone(self.holder("personal-21"))

    def test_the_profile_follows_the_person_to_whichever_browser_they_get(self):
        self.rig.open("swangz-4")
        self.rig.open("swangz-5", "Okello Brian")
        self.rig.call("POST", "/release", {"lease": "p4"})
        self.assertEqual(self.rig.open("swangz-6", "Akello Joy")[1]["slot"], "personal-21")  # the slot, a new person
        self.assertIn("swangz-ws-profile-me-swangz-6:/home/neko/.config/chromium", self.args("personal-21"))
        self.assertNotIn("swangz-ws-profile-me-swangz-4:/home/neko/.config/chromium", self.args("personal-21"))
        self.rig.call("POST", "/release", {"lease": "p5"})
        self.assertEqual(self.rig.open("swangz-4")[1]["slot"], "personal-22")  # swangz-4 back, in the other slot
        self.assertIn("swangz-ws-profile-me-swangz-4:/home/neko/.config/chromium", self.args("personal-22"))

    def test_private_browsers_are_listed_apart_and_admins_cannot_sign_in_to_them(self):
        self.rig.open("swangz-4")
        status = self.rig.call("GET", "/status")[1]
        self.assertEqual([b["slot"] for b in status["browsers"]], ["midjourney-1", "midjourney-2"])
        self.assertEqual(status["capacity"], {"midjourney": 2})
        self.assertEqual((status["personal_capacity"], len(status["personal"])), (2, 2))
        status, out = self.rig.call("POST", "/admin-open", {"slot": "personal-21", "name": "Admin"})
        self.assertEqual(status, 409)
        self.assertIn("belong to the people", out["error"])
        health = self.rig.call("GET", "/health")[1]
        self.assertEqual((health["personal"], health["egress"]), (1, False))

    def test_they_have_their_own_cap_so_they_cannot_starve_the_shared_browsers(self):
        self.rig.close()
        self.rig = PersonalRig(personal={"browsers": [21, 22], "max_running": 1})
        self.addCleanup(self.rig.close)
        self.assertEqual(self.rig.open("swangz-4")[0], 200)
        status, out = self.rig.open("swangz-5", "Okello Brian")
        self.assertEqual((status, out.get("full")), (409, "personal"))
        self.assertEqual(self.rig.ready("t1.1", "swangz-5", tool="midjourney")[0], 200)  # shared tools unaffected

    def test_without_a_personal_block_there_are_no_private_workspaces(self):
        rig = AgentRig()
        self.addCleanup(rig.close)
        status, out = rig.call("POST", "/allocate", {"tool": "personal", "lease": "p4", "user": "swangz-4", "name": "A"})
        self.assertEqual(status, 404)


class IdleTests(unittest.TestCase):
    def setUp(self):
        self.rig = PersonalRig()
        self.addCleanup(self.rig.close)
        self.agent = self.rig.agent
        url = self.rig.open("swangz-4")[1]["url"]
        self.user, self.password = signin_in(url)
        self.slot = self.agent.slots["personal-21"]

    def idle(self, minutes):
        self.slot["last_used"] = self.slot["started"] = self.slot["since"] = time.time() - minutes * 60
        self.agent.sweep()

    def test_a_disconnected_browser_is_let_go_after_the_idle_time(self):
        self.idle(5)
        self.assertEqual(self.slot["lease"], "p4")  # not yet
        self.idle(21)
        self.assertIsNone(self.slot["lease"])
        self.assertNotIn("swangz-ws-personal-21", self.rig.docker.containers)

    def test_a_connected_tab_keeps_it_alive(self):
        self.assertTrue(self.rig.p1.sign_in(self.user, self.password))
        self.idle(60)
        self.assertEqual(self.slot["lease"], "p4")
        self.assertGreater(time.time() - self.slot["last_used"], -1)
        self.assertLess(time.time() - self.slot["last_used"], 5)  # the connection counted as use

    def test_when_neko_cannot_say_recent_traffic_keeps_it_and_silence_does_not(self):
        self.rig.p1.sessions_unreadable = True
        self.agent.visits.record("swangz-4", "example.com", 443)
        self.idle(60)
        self.assertEqual(self.slot["lease"], "p4")
        self.agent.visits.active["swangz-4"] = time.time() - 600
        self.idle(60)
        self.assertIsNone(self.slot["lease"])

    def test_the_time_limit_applies_even_while_connected(self):
        self.assertTrue(self.rig.p1.sign_in(self.user, self.password))
        self.slot["since"] = time.time() - 13 * 3600
        self.agent.sweep()
        self.assertIsNone(self.slot["lease"])

    def test_a_container_that_died_frees_the_lease_and_opening_again_starts_one(self):
        self.rig.docker.containers.pop("swangz-ws-personal-21")
        self.agent.sweep()
        self.assertIsNone(self.slot["lease"])
        status, out = self.rig.open("swangz-4")
        self.assertEqual((status, out["state"]), (200, "ready"))
        self.assertIn("swangz-ws-personal-21", self.rig.docker.containers)


class ApiTests(unittest.TestCase):
    def test_visits_need_the_token_and_page_forward(self):
        rig = PersonalRig()
        self.addCleanup(rig.close)
        self.assertEqual(rig.call("GET", "/visits", token="wrong")[0], 401)
        log = rig.agent.visits
        log.window = 0
        log.record("swangz-4", "example.com", 443, up=10, down=20)
        log.record("swangz-4", "news.test", 443)
        status, out = rig.call("GET", "/visits?after=0")
        self.assertEqual((status, [e["host"] for e in out["entries"]], out["last"], out["reset"]),
                         (200, ["example.com", "news.test"], 2, False))
        self.assertEqual(rig.call("GET", "/visits?after=1")[1]["entries"][0]["host"], "news.test")
        self.assertEqual(rig.call("GET", "/visits?after=2")[1]["entries"], [])
        self.assertTrue(rig.call("GET", "/visits?after=99")[1]["reset"])  # the reader is ahead: this log was lost
        self.assertEqual(rig.call("GET", "/visits?after=x")[0], 400)


# ---------------------------------------------------------------- the egress proxy


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"hello {self.headers.get('Host')} {self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class EgressTests(unittest.TestCase):
    def setUp(self):
        self.up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        self.addCleanup(self.up.shutdown)
        self.port = self.up.server_address[1]
        self.log = egress.VisitLog(window=0)
        self.user = "swangz-4"
        # "site.test" stands in for a public website: it resolves to the local upstream, which the test rule allows
        self.proxy = egress.EgressProxy(
            self.log, lambda slot: self.user, allow_ip=lambda ip: ip.is_loopback,
            resolve=lambda host, port: ["127.0.0.1"] if host.endswith(".test") else egress.EgressProxy._resolve(host, port))
        self.addCleanup(self.proxy.close)
        self.pport = self.proxy.listen("personal-21", "127.0.0.1", 0)
        self.strict = egress.EgressProxy(self.log, lambda slot: self.user)  # the real rule: public addresses only
        self.addCleanup(self.strict.close)
        self.sport = self.strict.listen("personal-21", "127.0.0.1", 0)

    def raw(self, port, payload, read=400):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(payload)
            time.sleep(0.2)
            return s.recv(read)

    def entries(self):
        return self.log.since(0)["entries"]

    def test_https_tunnels_and_only_the_host_is_logged(self):
        with socket.create_connection(("127.0.0.1", self.pport), timeout=5) as s:
            s.sendall(f"CONNECT site.test:{self.port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
            self.assertTrue(s.recv(200).startswith(b"HTTP/1.1 200"))
            s.sendall(b"GET /private/page?token=abc HTTP/1.1\r\nHost: site.test\r\nConnection: close\r\n\r\n")
            time.sleep(0.3)
            self.assertIn(b"hello site.test /private/page", s.recv(500))
        time.sleep(0.3)
        (entry,) = self.entries()
        self.assertEqual((entry["user"], entry["host"], entry["port"], entry["outcome"]), ("swangz-4", "site.test", self.port, "allowed"))
        self.assertGreater(entry["down"], 0)
        self.assertNotIn("private", json.dumps(self.entries()))

    def test_plain_http_is_relayed_and_the_path_is_never_logged(self):
        req = urllib.request.Request(f"http://site.test:{self.port}/secret/path?token=abc")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{self.pport}"}))
        with opener.open(req, timeout=5) as resp:
            self.assertEqual(resp.read(), f"hello site.test:{self.port} /secret/path?token=abc".encode())
        time.sleep(0.3)
        text = json.dumps(self.entries())
        self.assertIn("site.test", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("token", text)

    def test_the_browser_cannot_reach_the_servers_own_network(self):
        for target in ("127.0.0.1:8790", "169.254.169.254:80", "10.0.0.5:443", "192.168.1.1:80", "localhost:80", "[::1]:80"):
            reply = self.raw(self.sport, f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())
            self.assertTrue(reply.startswith(b"HTTP/1.1 403"), target)
        self.assertEqual({e["outcome"] for e in self.entries()}, {"blocked"})
        self.assertEqual({e["reason"] for e in self.entries()}, {"internal or private address"})

    def test_abuse_ports_are_refused_before_anything_is_looked_up(self):
        looked_up = []
        proxy = egress.EgressProxy(self.log, lambda slot: self.user, resolve=lambda h, p: looked_up.append(h) or ["93.184.216.34"])
        self.addCleanup(proxy.close)
        port = proxy.listen("personal-21", "127.0.0.1", 0)
        for dest in ("mail.example.com:25", "db.example.com:5432", "box.example.com:22"):
            self.assertTrue(self.raw(port, f"CONNECT {dest} HTTP/1.1\r\n\r\n".encode()).startswith(b"HTTP/1.1 403"), dest)
        self.assertEqual(looked_up, [])
        self.assertTrue(all("not allowed" in e["reason"] for e in self.entries()))

    def test_a_name_with_any_private_address_is_refused_whole(self):
        proxy = egress.EgressProxy(self.log, lambda slot: self.user, resolve=lambda h, p: ["93.184.216.34", "10.0.0.7"])
        self.addCleanup(proxy.close)
        port = proxy.listen("personal-21", "127.0.0.1", 0)
        self.assertTrue(self.raw(port, b"CONNECT rebind.example.com:443 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"))

    def test_it_connects_to_the_address_it_checked(self):
        asked = []
        proxy = egress.EgressProxy(self.log, lambda slot: self.user, allow_ip=lambda ip: ip.is_loopback,
                                   resolve=lambda h, p: asked.append(h) or ["127.0.0.1"])
        self.addCleanup(proxy.close)
        port = proxy.listen("personal-21", "127.0.0.1", 0)
        self.assertTrue(self.raw(port, f"CONNECT site.test:{self.port} HTTP/1.1\r\n\r\n".encode()).startswith(b"HTTP/1.1 200"))
        self.assertEqual(asked, ["site.test"])  # resolved once

    def test_nobodys_browser_and_malformed_requests_are_refused(self):
        self.user = ""
        self.assertTrue(self.raw(self.pport, b"CONNECT site.test:443 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"))
        self.user = "swangz-4"
        for bad in (b"GET / HTTP/1.1\r\n\r\n", b"CONNECT nonsense HTTP/1.1\r\n\r\n", b"CONNECT a b:443 HTTP/1.1\r\n\r\n",
                    b"CONNECT site.test:0 HTTP/1.1\r\n\r\n", b"CONNECT site.test:99999 HTTP/1.1\r\n\r\n", b"junk\r\n\r\n"):
            self.assertTrue(self.raw(self.pport, bad).startswith(b"HTTP/1.1 400"), bad)

    def test_only_private_network_peers_are_served(self):
        self.assertTrue(egress.private_peer("172.17.0.2"))
        self.assertTrue(egress.private_peer("10.1.2.3"))
        for outside in ("8.8.8.8", "203.0.113.7", "100.64.0.1", "169.254.169.254", "172.32.0.1", "2001:4860:4860::8888", "garbage"):
            self.assertFalse(egress.private_peer(outside), outside)
        proxy = egress.EgressProxy(self.log, lambda slot: self.user, allow_peer=lambda ip: False)
        self.addCleanup(proxy.close)
        port = proxy.listen("personal-21", "127.0.0.1", 0)
        self.assertEqual(self.raw(port, b"CONNECT site.test:443 HTTP/1.1\r\n\r\n"), b"")  # dropped without an answer

    def test_host_names_are_normalised_and_odd_ones_refused(self):
        self.assertEqual(egress.parse_host("Example.COM."), "example.com")
        self.assertEqual(egress.parse_host("[2001:DB8::1]"), "2001:db8::1")
        self.assertEqual(egress.parse_host("203.0.113.9"), "203.0.113.9")
        for odd in ("", "a b", "evil.com@good.com", "a/b", "-x.com", "x" * 300):
            self.assertIsNone(egress.parse_host(odd), odd)


class VisitLogTests(unittest.TestCase):
    def test_a_minute_of_visits_to_one_site_is_one_entry(self):
        now = [1000.0]
        log = egress.VisitLog(window=60, clock=lambda: now[0])
        for _ in range(5):
            log.record("swangz-4", "example.com", 443)
            now[0] += 5
        log.record("swangz-4", "example.com", 443, conns=0, up=100, down=900)
        self.assertEqual(log.since(0)["entries"], [])  # the minute is still open
        now[0] += 60
        (entry,) = log.since(0)["entries"]
        self.assertEqual((entry["conns"], entry["up"], entry["down"], entry["seq"]), (5, 100, 900, 1))
        self.assertEqual((entry["ts"], entry["last"]), (1000.0, 1025.0))

    def test_entries_survive_a_restart_and_keep_counting(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "visits.jsonl")
            log = egress.VisitLog(path, window=0)
            log.record("swangz-4", "a.test", 443)
            log.record("swangz-5", "b.test", 443, "blocked", "internal or private address")
            log.flush()
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
            again = egress.VisitLog(path, window=0)
            self.assertEqual([e["host"] for e in again.since(0)["entries"]], ["a.test", "b.test"])
            again.record("swangz-4", "c.test", 443)
            self.assertEqual(again.since(2)["entries"][0]["seq"], 3)

    def test_a_reader_ahead_of_a_lost_log_is_told_to_start_again(self):
        log = egress.VisitLog(window=0)
        log.record("swangz-4", "a.test", 443)
        out = log.since(500)
        self.assertEqual((out["reset"], out["last"], [e["seq"] for e in out["entries"]]), (True, 1, [1]))

    def test_it_keeps_only_so_many(self):
        log = egress.VisitLog(window=0, keep=3)
        for i in range(6):
            log.record("swangz-4", f"s{i}.test", 443)
            log.flush()
        self.assertEqual([e["seq"] for e in log.since(0)["entries"]], [4, 5, 6])


if __name__ == "__main__":
    unittest.main()
