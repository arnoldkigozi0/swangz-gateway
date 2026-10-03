"""The Swangz Workspace Agent: browsers started when a turn needs one, a sign-in per turn, recycled after."""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

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
        self.nekos = {"midjourney-1": FakeNeko(), "midjourney-2": FakeNeko()}
        self.docker = FakeDocker(self.nekos, boot=boot)
        self.cfg = agent_config(self.tmp, **extra)
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


class ApiTests(AgentTestCase):
    def test_the_token_is_required(self):
        self.assertEqual(self.rig.call("GET", "/status", token="")[0], 401)
        self.assertEqual(self.rig.call("GET", "/status", token="wrong")[0], 401)
        self.assertEqual(self.rig.call("GET", "/health"), (200, {"ok": True, "docker": True, "running": 0, "browsers": 2}))

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
                       {"tools": {"chatgpt": {"browsers": [1], "start_url": "javascript:x"}}}):
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


if __name__ == "__main__":
    unittest.main()
