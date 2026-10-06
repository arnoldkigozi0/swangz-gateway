"""The Swangz Workspace Agent: browsers started when a turn needs one, a sign-in per turn, recycled after."""

import http.client
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from workspace_agent import computer
from workspace_agent.agent import ADMIN, STAFF, Agent, ConfigError, caddy_routes, check_config, make_server

from .fake_docker import FakeDocker
from .fake_neko import FakeNeko

TOKEN = "agent-token-" + "x" * 30
os.environ.setdefault("SWANGZ_WORKSPACE_ACCESS_LOG", "0")


def agent_config(data, **extra):
    return check_config({"token": TOKEN, "public_url": "https://ws.example.test", "public_ip": "203.0.113.7",
                         "data": data, "tools": {"midjourney": {"browsers": [1, 2], "start_url": "https://www.midjourney.com/"}},
                         **extra})


class AgentRig:
    """An agent on a random port, driving a fake Docker whose containers are stand-in Nekos."""

    def __init__(self, boot=0, **extra):
        self.tmp = tempfile.mkdtemp(prefix="sgw-agent-")
        self.cfg = agent_config(self.tmp, **extra)
        self.nekos = {slot: FakeNeko() for slot in self.cfg["browsers"]}
        self.docker = FakeDocker(self.nekos, boot=boot)
        self.start_agent()

    def start_agent(self):
        self.agent = Agent(self.cfg, self.docker, neko_base=lambda slot: self.nekos[slot].url + "/" + slot)
        self.server = make_server(self.agent, "127.0.0.1:0")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop_agent(self):
        self.server.shutdown()
        self.server.server_close()

    def close(self):
        self.stop_agent()
        for neko in self.nekos.values():
            neko.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, token=TOKEN):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def ready(self, lease, user, name="Nansubuga Grace", tool="midjourney"):
        for _ in range(10):
            status, out = self.call("POST", "/allocate", {"tool": tool, "lease": lease, "user": user, "name": name})
            if status != 202:
                return status, out
        raise AssertionError("never became ready")


def signin_in(url):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    return q["usr"], q["pwd"]


class AgentTestCase(unittest.TestCase):
    boot = 0

    def setUp(self):
        self.rig = AgentRig(boot=self.boot)
        self.addCleanup(self.rig.close)
        self.n1, self.n2 = self.rig.nekos["midjourney-1"], self.rig.nekos["midjourney-2"]

    def holder(self, slot):
        return next(b for b in self.rig.call("GET", "/status")[1]["browsers"] if b["slot"] == slot)["holder"]


class AllocateTests(AgentTestCase):
    boot = 1  # the browser fails its first health check, like a real one starting

    def test_the_first_turn_starts_a_browser_then_signs_the_person_in(self):
        body = {"tool": "midjourney", "lease": "t1.1000", "user": "swangz-4", "name": "Nansubuga Grace"}
        self.assertEqual(self.rig.call("POST", "/allocate", body), (202, {"state": "starting", "slot": "midjourney-1"}))
        run = self.rig.docker.containers["swangz-ws-midjourney-1"]
        args = run["args"]
        for expected in (["--pull", "never"], ["-p", "127.0.0.1:8101:8080"], ["-p", "59101:59101/udp"],
                         ["--memory", "2g"], ["--shm-size", "2g"]):
            self.assertIn(expected, [args[i:i + 2] for i in range(len(args) - 1)])
        self.assertIn("swangz-ws-profile-midjourney-1:/home/neko/.config/chromium", args)  # a named volume
        self.assertTrue(any(a.endswith(":/etc/chromium/policies/managed/policies.json:ro") for a in args))
        env = run["env"]
        self.assertEqual((env["NEKO_MEMBER_PROVIDER"], env["NEKO_SERVER_PATH_PREFIX"], env["NEKO_WEBRTC_UDPMUX"]),
                         ("object", "/midjourney-1", "59101"))
        self.assertEqual(len(env["NEKO_SESSION_API_TOKEN"]), 64)
        self.assertNotIn(env["NEKO_SESSION_API_TOKEN"], " ".join(args))  # never on the command line
        self.assertEqual(self.rig.call("POST", "/allocate", body)[0], 202)  # still starting
        status, out = self.rig.call("POST", "/allocate", body)
        self.assertEqual((status, out["state"], out["slot"]), (200, "ready", "midjourney-1"))
        self.assertTrue(out["url"].startswith("https://ws.example.test/midjourney-1/?usr=swangz-4&pwd="))
        usr, pwd = signin_in(out["url"])
        self.assertEqual(self.n1.members[usr]["profile"], {**STAFF, "name": "Nansubuga Grace"})
        self.assertTrue(self.n1.sign_in(usr, pwd))
        self.assertEqual(self.holder("midjourney-1")["name"], "Nansubuga Grace")


class TurnTests(AgentTestCase):
    def test_two_turns_get_two_browsers_and_a_third_is_refused(self):
        self.assertEqual(self.rig.ready("t1.1", "swangz-4")[1]["slot"], "midjourney-1")
        self.assertEqual(self.rig.ready("t2.1", "swangz-5", "Okello Brian")[1]["slot"], "midjourney-2")
        status, out = self.rig.ready("t3.1", "swangz-6", "Akello Joy")
        self.assertEqual(status, 409)
        self.assertIn("in use", out["error"])
        self.assertEqual(self.rig.call("POST", "/allocate", {"tool": "canva", "lease": "t4.1", "user": "swangz-4"})[0], 404)

    def test_the_same_turn_again_gets_a_new_password_and_the_old_tab_lets_go(self):
        usr, first = signin_in(self.rig.ready("t1.1", "swangz-4")[1]["url"])
        self.assertTrue(self.n1.sign_in(usr, first))
        status, out = self.rig.ready("t1.1", "swangz-4")
        usr2, second = signin_in(out["url"])
        self.assertEqual((status, out["slot"], usr2), (200, "midjourney-1", usr))
        self.assertNotEqual(first, second)
        self.assertNotIn(usr, self.n1.sessions)
        self.assertFalse(self.n1.sign_in(usr, first))
        self.assertTrue(self.n1.sign_in(usr, second))

    def test_back_on_a_new_turn_before_the_old_one_is_released_keeps_the_browser(self):
        self.rig.ready("t1.1", "swangz-4")
        status, out = self.rig.ready("t9.1", "swangz-4")
        self.assertEqual((status, out["slot"]), (200, "midjourney-1"))
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"})[0], 404)  # nothing to undo
        self.assertIn("swangz-4", self.n1.members)
        self.assertEqual(self.holder("midjourney-1")["lease"], "t9.1")

    def test_release_removes_the_sign_in_and_recycles_the_browser(self):
        self.rig.ready("t1.1", "swangz-4")
        before = self.rig.docker.containers["swangz-ws-midjourney-1"]["env"]["NEKO_SESSION_API_TOKEN"]
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"}), (200, {"ok": True, "slot": "midjourney-1"}))
        self.assertIn(("DELETE", "/midjourney-1/api/members/swangz-4", None), self.n1.calls)
        self.assertEqual(self.rig.docker.log[-2:], [("rm", "swangz-ws-midjourney-1"), ("run", "swangz-ws-midjourney-1")])
        after = self.rig.docker.containers["swangz-ws-midjourney-1"]["env"]["NEKO_SESSION_API_TOKEN"]
        self.assertNotEqual(before, after)  # every start has its own token
        self.assertIsNone(self.holder("midjourney-1"))
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"})[0], 404)

    def test_when_neko_does_not_answer_the_container_goes_instead(self):
        self.rig.cfg["recycle"] = False
        self.rig.ready("t1.1", "swangz-4")
        self.n1.broken = True
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"})[0], 200)
        self.assertNotIn("swangz-ws-midjourney-1", self.rig.docker.containers)
        self.assertIsNone(self.holder("midjourney-1"))

    def test_when_docker_is_down_too_the_turn_is_not_let_go(self):
        self.rig.ready("t1.1", "swangz-4")
        self.n1.broken = True
        self.rig.docker.down = True
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"})[0], 503)
        self.assertEqual(self.holder("midjourney-1")["lease"], "t1.1")  # the gateway will ask again
        self.rig.docker.down = False
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"})[0], 200)

    def test_a_browser_that_never_starts_is_given_up(self):
        body = {"tool": "midjourney", "lease": "t1.1", "user": "swangz-4", "name": "Grace"}
        self.assertEqual(self.rig.call("POST", "/allocate", body)[0], 202)
        self.n1.booting = 99
        self.rig.agent.slots["midjourney-1"]["started"] -= 1000
        self.assertEqual(self.rig.call("POST", "/allocate", body)[0], 503)
        self.assertNotIn("swangz-ws-midjourney-1", self.rig.docker.containers)
        self.assertIsNone(self.holder("midjourney-1"))


class HousekeepingTests(AgentTestCase):
    def test_idle_browsers_are_stopped(self):
        self.rig.ready("t1.1", "swangz-4")
        self.rig.call("POST", "/release", {"lease": "t1.1"})  # recycled: running, free
        self.rig.agent.sweep()
        self.assertIn("swangz-ws-midjourney-1", self.rig.docker.containers)  # not idle long enough yet
        s = self.rig.agent.slots["midjourney-1"]
        s["last_used"] = s["started"] = time.time() - 3600
        self.rig.agent.sweep()
        self.assertNotIn("swangz-ws-midjourney-1", self.rig.docker.containers)
        self.assertEqual(self.rig.call("GET", "/status")[1]["browsers"][0]["state"], "stopped")

    def test_a_container_that_died_is_noticed_and_started_again(self):
        self.rig.ready("t1.1", "swangz-4")
        self.rig.docker.containers.clear()
        self.rig.agent.sweep()
        self.assertEqual(self.rig.agent.slots["midjourney-1"]["status"], "stopped")
        self.assertEqual(self.rig.ready("t1.1", "swangz-4")[0], 200)

    def test_an_admin_signs_a_browser_in_and_the_session_ends_by_itself(self):
        self.assertEqual(self.rig.call("POST", "/admin-open", {"slot": "midjourney-2", "name": "arnold"})[0], 202)
        status, out = self.rig.call("POST", "/admin-open", {"slot": "midjourney-2", "name": "arnold"})
        self.assertEqual((status, out["state"]), (200, "ready"))
        usr, pwd = signin_in(out["url"])
        self.assertEqual(self.n2.members[usr]["profile"], {**ADMIN, "name": "arnold"})
        self.assertEqual(self.holder("midjourney-2")["kind"], "admin")
        # nobody's turn can be given that browser meanwhile
        self.rig.ready("t1.1", "swangz-4")
        self.assertEqual(self.rig.ready("t2.1", "swangz-5")[0], 409)
        self.rig.agent.slots["midjourney-2"]["since"] -= 3600
        self.rig.agent.sweep()
        self.assertIsNone(self.holder("midjourney-2"))

    def test_admin_close_and_no_taking_a_browser_someone_is_on(self):
        self.rig.ready("t1.1", "swangz-4")
        self.assertEqual(self.rig.call("POST", "/admin-open", {"slot": "midjourney-1", "name": "arnold"})[0], 409)
        self.rig.call("POST", "/admin-open", {"slot": "midjourney-2", "name": "arnold"})
        self.assertEqual(self.rig.call("POST", "/admin-close", {"slot": "midjourney-2"})[0], 200)
        self.assertIsNone(self.holder("midjourney-2"))
        self.assertEqual(self.rig.call("POST", "/admin-open", {"slot": "nope-9", "name": "a"})[0], 404)

    def test_state_survives_an_agent_restart(self):
        self.rig.ready("t1.1", "swangz-4")
        self.rig.stop_agent()
        self.rig.start_agent()
        self.assertEqual(self.holder("midjourney-1")["lease"], "t1.1")
        status, out = self.rig.ready("t1.1", "swangz-4")
        self.assertEqual((status, out["slot"]), (200, "midjourney-1"))
        # a container the agent has no token for is removed rather than trusted
        self.rig.stop_agent()
        self.rig.agent.slots["midjourney-1"]["token"] = ""
        self.rig.agent._save()
        self.rig.start_agent()
        self.assertNotIn("swangz-ws-midjourney-1", self.rig.docker.containers)


class ServerLimitTests(unittest.TestCase):
    """max_running: browsers for many tools listed, only so many running at once on the whole server."""

    def setUp(self):
        self.rig = AgentRig(max_running=2, tools={
            "midjourney": {"browsers": [1, 2], "start_url": "https://www.midjourney.com/"},
            "chatgpt": {"browsers": [3], "start_url": "https://chatgpt.com/"}})
        self.addCleanup(self.rig.close)

    def running(self):
        return sorted(name[len("swangz-ws-"):] for name in self.rig.docker.containers)

    def test_with_every_running_browser_in_use_the_server_is_full(self):
        self.rig.ready("t1.1", "swangz-4")
        self.rig.ready("t2.1", "swangz-5")
        status, out = self.rig.ready("t3.1", "swangz-6", tool="chatgpt")
        self.assertEqual((status, out["full"]), (409, "server"))
        self.assertEqual(self.running(), ["midjourney-1", "midjourney-2"])
        self.assertIsNone(next(b for b in self.rig.call("GET", "/status")[1]["browsers"] if b["slot"] == "chatgpt-3")["holder"])

    def test_a_free_browser_of_another_tool_stops_to_make_room(self):
        self.rig.ready("t1.1", "swangz-4")
        self.rig.ready("t2.1", "swangz-5")
        self.rig.call("POST", "/release", {"lease": "t1.1"})  # recycled: running, free
        self.assertEqual(self.running(), ["midjourney-1", "midjourney-2"])
        status, out = self.rig.ready("t3.1", "swangz-6", tool="chatgpt")
        self.assertEqual((status, out["slot"]), (200, "chatgpt-3"))
        self.assertEqual(self.running(), ["chatgpt-3", "midjourney-2"])

    def test_a_released_browser_is_not_kept_ready_when_there_is_no_room(self):
        self.rig.ready("t1.1", "swangz-4")
        self.rig.docker.containers.pop("swangz-ws-midjourney-1")  # it died; the sweep notices
        self.rig.agent.sweep()
        self.rig.ready("t2.1", "swangz-5")
        self.rig.ready("t3.1", "swangz-6", tool="chatgpt")
        self.assertEqual(self.rig.call("POST", "/release", {"lease": "t1.1"})[0], 200)
        self.assertEqual(self.running(), ["chatgpt-3", "midjourney-2"])
        self.assertEqual(self.rig.call("GET", "/health")[1]["running"], 2)


class ApiTests(AgentTestCase):
    def test_the_token_is_required(self):
        self.assertEqual(self.rig.call("GET", "/status", token="")[0], 401)
        self.assertEqual(self.rig.call("GET", "/status", token="wrong")[0], 401)
        self.assertEqual(self.rig.call("GET", "/health"),
                         (200, {"ok": True, "docker": True, "running": 0, "browsers": 2, "max_running": 0}))

    def test_bad_requests_are_refused(self):
        self.assertEqual(self.rig.call("POST", "/allocate", {"tool": "midjourney", "lease": "t1.1"})[0], 400)
        self.assertEqual(self.rig.call("POST", "/allocate", {"tool": "../x", "lease": "t1", "user": "u"})[0], 400)
        self.assertEqual(self.rig.call("POST", "/release", {})[0], 400)
        self.assertEqual(self.rig.call("POST", "/nothing", {})[0], 404)

    def test_status_lists_every_browser(self):
        status, out = self.rig.call("GET", "/status")
        self.assertEqual(status, 200)
        self.assertEqual([b["slot"] for b in out["browsers"]], ["midjourney-1", "midjourney-2"])
        self.assertEqual(out["capacity"], {"midjourney": 2})


class ConfigTests(unittest.TestCase):
    def test_mistakes_are_caught(self):
        base = {"token": TOKEN, "public_url": "https://ws.example.test", "public_ip": "1.2.3.4", "data": "/tmp/x",
                "tools": {"chatgpt": {"browsers": [1]}}}
        for broken in ({"token": "short"}, {"public_url": "http://ws.example.test"}, {"public_ip": ""},
                       {"tools": {}}, {"tools": {"ChatGPT!": {"browsers": [1]}}},
                       {"tools": {"chatgpt": {"browsers": [1]}, "claude": {"browsers": [1]}}},
                       {"tools": {"chatgpt": {"browsers": [100]}}},
                       {"tools": {"chatgpt": {"browsers": [1], "start_url": "javascript:x"}}},
                       {"max_running": -1}, {"max_running": "20"}):
            with self.subTest(broken=broken), self.assertRaises(ConfigError):
                check_config({**base, **broken})

    def test_caddy_routes_cover_the_agent_and_every_browser(self):
        cfg = check_config({"token": TOKEN, "public_url": "https://workspace.swangzavenue.com", "public_ip": "1.2.3.4",
                            "data": "/tmp/x", "gateway_ip": "198.51.100.9",
                            "tools": {"chatgpt": {"browsers": [1, 2]}, "claude": {"browsers": [3]}}})
        text = caddy_routes(cfg)
        for line in ("workspace.swangzavenue.com {", "handle_path /agent/* {", "@outside not remote_ip 198.51.100.9",
                     "reverse_proxy 127.0.0.1:8790", "handle /chatgpt-2/* {", "reverse_proxy 127.0.0.1:8102",
                     "handle /claude-3/* {", "reverse_proxy 127.0.0.1:8103"):
            self.assertIn(line, text)

    def test_the_browser_policy_keeps_the_sign_in_and_developer_tools_off(self):
        rig = AgentRig()
        self.addCleanup(rig.close)
        rig.ready("t1.1", "swangz-4")
        args = rig.docker.containers["swangz-ws-midjourney-1"]["args"]
        path = next(a for a in args if a.endswith(":/etc/chromium/policies/managed/policies.json:ro")).rsplit(":/etc/", 1)[0]
        with open(path, encoding="utf-8") as f:
            policy = json.load(f)
        self.assertEqual((policy["DeveloperToolsAvailability"], policy["DefaultCookiesSetting"], policy["RestoreOnStartup"]), (2, 1, 1))
        self.assertEqual(policy["NewTabPageLocation"], "https://www.midjourney.com/")
        self.assertIn("file://*", policy["URLBlocklist"])


# ---------------------------------------------------------------- on one of Swangz's own computers

RELAY = [{"urls": ["turn:turn.example.test:3478?transport=udp"], "username": "1760000000:swangz", "credential": "c"}]


class FakeGateway:
    """The gateway's /api/workspace/hello: keeps every check-in, answers with `reply` (or refuses)."""

    def __init__(self, reply):
        self.reply, self.status, self.hellos = reply, 200, []
        gw = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
                gw.hellos.append({"path": self.path, "auth": self.headers.get("authorization"),
                                  "app": self.headers.get("x-swangz-app"), "body": body})
                data = json.dumps(gw.reply if gw.status == 200 else {"error": "that key isn't this computer's"}).encode()
                self.send_response(gw.status)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Nekos(dict):
    """A stand-in browser for whichever slot the gateway's list brings."""

    def __missing__(self, slot):
        self[slot] = FakeNeko()
        return self[slot]


class ComputerRig(AgentRig):
    """An agent in computer mode: no browsers of its own; they, and the relay, come from the gateway."""

    def __init__(self, tools):
        self.gateway = FakeGateway({"ok": True, "active": True, "tools": tools, "ice_servers": RELAY})
        self.tmp = tempfile.mkdtemp(prefix="sgw-agent-")
        self.cfg = check_config({"token": TOKEN, "gateway": "https://ai.example.test", "host": "windows",
                                 "data": self.tmp, "lan_ip": "192.168.1.20"})
        self.cfg.update(gateway=self.gateway.url, public_url="https://quiet-river.trycloudflare.com")
        self.nekos = Nekos()
        self.docker = FakeDocker(self.nekos)
        self.start_agent()

    def close(self):
        super().close()
        self.gateway.close()

    def slots(self):
        return sorted(self.agent.slots)


class ComputerTests(unittest.TestCase):
    TOOLS = {"midjourney": {"start_url": "https://www.midjourney.com/", "browsers": 2},
             "chatgpt": {"start_url": "https://chatgpt.com/", "browsers": 1}}

    def setUp(self):
        self.rig = ComputerRig(self.TOOLS)
        self.addCleanup(self.rig.close)

    def test_a_computer_needs_no_address_or_browser_list_of_its_own(self):
        cfg = check_config({"token": TOKEN, "gateway": "https://ai.example.test/", "host": "mac", "data": "/tmp/x"})
        self.assertEqual((cfg["gateway"], cfg["tools_from_gateway"], cfg["browsers"]), ("https://ai.example.test", True, {}))
        for broken in ({"gateway": "http://ai.example.test"}, {"host": "linux"}, {"token": "short"}, {"ice_servers": "turn:x"}):
            with self.subTest(broken=broken), self.assertRaises(ConfigError):
                check_config({"token": TOKEN, "gateway": "https://ai.example.test", "host": "windows", "data": "/tmp/x", **broken})

    def test_checking_in_brings_the_browsers_and_the_relay(self):
        self.assertEqual(self.rig.slots(), [])
        self.assertTrue(self.rig.agent.say_hello())
        hello = self.rig.gateway.hellos[-1]
        self.assertEqual((hello["path"], hello["auth"], hello["app"]), ("/api/workspace/hello", "Bearer " + TOKEN, "1"))
        self.assertEqual((hello["body"]["host"], hello["body"]["url"]), ("windows", "https://quiet-river.trycloudflare.com/agent"))
        self.assertEqual((hello["body"]["info"]["memory_gb"], hello["body"]["info"]["cpus"]), (31.2, 16))
        # numbers in tool order, each tool's own from now on
        self.assertEqual(self.rig.slots(), ["chatgpt-1", "midjourney-2", "midjourney-3"])
        status, out = self.rig.ready("t1.1", "swangz-4")
        self.assertEqual((status, out["slot"]), (200, "midjourney-2"))
        self.assertTrue(out["url"].startswith("https://quiet-river.trycloudflare.com/midjourney-2/?usr=swangz-4"))
        env = self.rig.docker.containers["swangz-ws-midjourney-2"]["env"]
        self.assertEqual(env["NEKO_WEBRTC_ICELITE"], "false")  # a relay needs full ICE
        self.assertEqual(json.loads(env["NEKO_WEBRTC_ICESERVERS_FRONTEND"]), RELAY)
        self.assertEqual(json.loads(env["NEKO_WEBRTC_ICESERVERS_BACKEND"]), RELAY)
        self.assertEqual(env["NEKO_WEBRTC_NAT1TO1"], "192.168.1.20")  # people in the office connect straight to it
        health = self.rig.call("GET", "/agent/health")[1]
        self.assertEqual((health["relay"], health["gateway"]["ok"], health["gateway"]["active"]), (True, True, True))

    def test_a_tool_keeps_its_browser_numbers_for_good(self):
        agent = self.rig.agent
        agent.apply_tools({"midjourney": {"browsers": 2}})
        self.assertEqual(self.rig.slots(), ["midjourney-1", "midjourney-2"])
        self.rig.ready("t1.1", "swangz-4")  # Grace is on midjourney-1
        agent.apply_tools({"chatgpt": {"browsers": 1}})  # Midjourney no longer needs browsers
        self.assertEqual(self.rig.slots(), ["chatgpt-3", "midjourney-1"])  # hers stays until she's done
        self.rig.call("POST", "/release", {"lease": "t1.1"})
        agent.apply_tools({"chatgpt": {"browsers": 1}})
        self.assertEqual(self.rig.slots(), ["chatgpt-3"])
        self.assertNotIn("swangz-ws-midjourney-1", self.rig.docker.containers)
        agent.apply_tools({"chatgpt": {"browsers": 1}, "midjourney": {"browsers": 2}})
        self.assertEqual(self.rig.slots(), ["chatgpt-3", "midjourney-1", "midjourney-2"])  # the same profiles again
        # and after a restart, before the gateway has answered
        self.rig.stop_agent()
        self.rig.start_agent()
        self.assertEqual(self.rig.slots(), ["chatgpt-3", "midjourney-1", "midjourney-2"])

    def test_a_refused_check_in_is_reported(self):
        self.rig.gateway.status = 401
        self.assertFalse(self.rig.agent.say_hello())
        health = self.rig.call("GET", "/health")[1]
        self.assertIn("that key isn't this computer's", health["gateway"]["error"])
        self.assertEqual(self.rig.slots(), [])

    def test_no_address_yet_means_no_check_in(self):
        self.rig.agent.cfg["public_url"] = ""
        self.assertFalse(self.rig.agent.say_hello())
        self.assertEqual(self.rig.gateway.hellos, [])


class PassOnTests(unittest.TestCase):
    """The agent hands a browser's page — and its WebSocket — on to the browser, as a company computer's
    tunnel brings everything to the agent."""

    def setUp(self):
        self.rig = AgentRig()
        self.addCleanup(self.rig.close)
        self.neko = self.rig.nekos["midjourney-1"]

    def point_browser_1_at(self, port):
        self.rig.agent.cfg["http_port_base"] = port - 1

    def raw(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.rig.server.server_address[1], timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        out = resp.status, resp.read()
        conn.close()
        return out

    def test_pages_and_api_calls_reach_the_browser_without_the_agents_token(self):
        self.point_browser_1_at(self.neko.server.server_address[1])
        self.assertEqual(self.raw("GET", "/midjourney-1/health"), (200, b"{}"))
        status, body = self.raw("POST", "/midjourney-1/api/members?x=1", json.dumps({"username": "u"}),
                                {"Content-Type": "application/json", "Authorization": "Bearer wrong"})
        self.assertEqual((status, json.loads(body)), (401, {"message": "invalid token"}))  # Neko's own answer
        self.assertIn(("POST", "/midjourney-1/api/members", {"username": "u"}), self.neko.calls)
        self.assertEqual(self.raw("GET", "/nobody-7/health")[0], 401)  # not a browser: the agent's API, token needed

    def test_a_browser_that_is_not_running(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free = s.getsockname()[1]
        self.point_browser_1_at(free)
        self.assertEqual(self.raw("GET", "/midjourney-1/")[0], 502)

    def test_the_websocket_goes_both_ways(self):
        seen = []
        upstream = socket.socket()
        upstream.bind(("127.0.0.1", 0))
        upstream.listen(1)
        self.addCleanup(upstream.close)

        def echo():
            conn, _ = upstream.accept()
            with conn:
                head = b""
                while b"\r\n\r\n" not in head:
                    head += conn.recv(4096)
                seen.append(head.decode())
                conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    conn.sendall(data)

        threading.Thread(target=echo, daemon=True).start()
        self.point_browser_1_at(upstream.getsockname()[1])
        with socket.create_connection(("127.0.0.1", self.rig.server.server_address[1]), timeout=10) as c:
            c.sendall(b"GET /midjourney-1/api/ws?token=t HTTP/1.1\r\nHost: quiet-river.trycloudflare.com\r\n"
                      b"Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\n\r\n")
            reply = b""
            while b"\r\n\r\n" not in reply:
                reply += c.recv(4096)
            self.assertTrue(reply.startswith(b"HTTP/1.1 101"))
            for word in (b"ping", b"pong"):
                c.sendall(word)
                self.assertEqual(c.recv(4096), word)
        self.assertIn("GET /midjourney-1/api/ws?token=t HTTP/1.1", seen[0])
        self.assertIn("Connection: Upgrade", seen[0])
        self.assertIn("Host: quiet-river.trycloudflare.com", seen[0])


class ComputerProgramTests(unittest.TestCase):
    def test_how_many_browsers_fit(self):
        self.assertEqual([computer.browsers_that_fit(gb) for gb in (3.8, 7.7, 31.2, 47.0, 62.5)], [1, 2, 14, 20, 20])

    def test_the_settings_keep_what_was_edited_and_hold_the_key(self):
        tmp = tempfile.mkdtemp(prefix="sgw-computer-")
        self.addCleanup(shutil.rmtree, tmp, True)
        p = computer.paths(tmp)
        cfg = computer.write_config(p, "windows", "https://swangz-ai.netlify.app/", "a" * 64, 14)
        self.assertEqual((cfg["gateway"], cfg["host"], cfg["max_running"], cfg["screen"]),
                         ("https://swangz-ai.netlify.app", "windows", 14, "1280x720@25"))
        with open(p["config"], encoding="utf-8") as f:
            saved = json.load(f)
        saved["idle_minutes"] = 30
        with open(p["config"], "w", encoding="utf-8") as f:
            json.dump(saved, f)
        cfg = computer.write_config(p, "windows", "https://swangz-ai.netlify.app", "b" * 64, 20)
        self.assertEqual((cfg["token"], cfg["idle_minutes"], cfg["max_running"]), ("b" * 64, 30, 20))

    def test_the_tunnel_address_is_read_from_cloudflared(self):
        line = "2026-10-06T10:00:00Z INF |  https://quiet-river-sky.trycloudflare.com                 |"
        self.assertEqual(computer.TUNNEL_LINK.search(line).group(0), "https://quiet-river-sky.trycloudflare.com")

    def test_it_starts_without_a_window(self):
        cmd = computer.background_command(computer.paths("/home/x/swangz-workspace"))
        self.assertEqual(cmd[1:], [os.path.abspath(computer.__file__), "run", "--dir", "/home/x/swangz-workspace"])
        if os.name == "nt":
            self.assertTrue(cmd[0].lower().endswith("pythonw.exe"))


if __name__ == "__main__":
    unittest.main()
