"""Recovery and deployment safety without calling Netlify or starting real processes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("laptop_service", Path(__file__).parents[1] / "deploy/laptop-service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class LaptopRecoveryTests(unittest.TestCase):
    def test_crashed_child_restarts_without_interrupting_other_children(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = service.Supervisor.__new__(service.Supervisor)
            supervisor.logs = Path(directory)
            crashed = Mock()
            crashed.poll.return_value = 1
            other = Mock()
            other.poll.return_value = None
            replacement = Mock()
            replacement.poll.return_value = None
            supervisor.children = {"gateway": crashed, "tunnel": other}
            supervisor.files = {}
            with patch.object(service.subprocess, "Popen", return_value=replacement) as spawn:
                supervisor.ensure("gateway", ["python3", "-m", "gateway", "serve"])
                supervisor.ensure("gateway", ["python3", "-m", "gateway", "serve"])
            spawn.assert_called_once()
            other.terminate.assert_not_called()
            supervisor.terminate("gateway")
            replacement.terminate.assert_called_once()
            replacement.wait.assert_called_once()

    def test_only_current_https_tunnel_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tunnel.log"
            path.write_text("https://first-link.trycloudflare.com\nhttp://unsafe.trycloudflare.com\n"
                            "https://latest-link.trycloudflare.com\n")
            self.assertEqual(service.latest_url(path), "https://latest-link.trycloudflare.com")

    def test_new_tunnel_updates_all_contexts_then_builds(self):
        client = service.Netlify("private-test-token")
        client.api = Mock(side_effect=[{}, {"deploy_id": "new-deploy"}])
        site = {"id": "site", "account_id": "account"}
        url = "https://new-link.trycloudflare.com"
        self.assertEqual(client.begin(site, url), "new-deploy")
        self.assertEqual(client.api.call_args_list[0].args,
            ("PUT", "/accounts/account/env/SWANGZ_GATEWAY?site_id=site",
             {"key": "SWANGZ_GATEWAY", "values": [{"context": "all", "value": url}]}))
        self.assertEqual(client.api.call_args_list[1].args[0], "POST")
        with self.assertRaises(ValueError):
            client.begin(site, "http://untrusted.example")

    def test_resume_pending_deploy_without_triggering_another_build(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            url = "https://existing-link.trycloudflare.com"
            service.save_json(state_file, {"pending_url": url, "deploy_id": "running"})
            client = Mock()
            client.site.return_value = {"name": "swangz-ai", "ssl_url": "https://swangz-ai.netlify.app"}
            client.api.return_value = {"state": "ready"}
            with patch.object(service, "Netlify", return_value=client), patch.object(service, "netlify_token", return_value="test"), patch.object(service, "healthy", return_value=True):
                service.sync_netlify(url, state_file, threading.Event())
            client.begin.assert_not_called()
            state = service.read_json(state_file)
            self.assertEqual(state["published_url"], url)
            self.assertNotIn("deploy_id", state)
            self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

    def test_ready_deploy_with_broken_proxy_is_not_marked_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            url = "https://existing-link.trycloudflare.com"
            service.save_json(state_file, {"pending_url": url, "deploy_id": "running"})
            client = Mock()
            client.site.return_value = {"name": "swangz-ai"}
            client.api.return_value = {"state": "ready"}
            with patch.object(service, "Netlify", return_value=client), patch.object(service, "netlify_token", return_value="test"), patch.object(service, "healthy", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "has not recovered"):
                    service.sync_netlify(url, state_file, threading.Event())
            self.assertNotIn("published_url", service.read_json(state_file))

    def test_failed_build_clears_pending_id_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            url = "https://existing-link.trycloudflare.com"
            service.save_json(state_file, {"pending_url": url, "deploy_id": "broken"})
            client = Mock()
            client.site.return_value = {"name": "swangz-ai"}
            client.api.return_value = {"state": "error"}
            with patch.object(service, "Netlify", return_value=client), patch.object(service, "netlify_token", return_value="test"):
                with self.assertRaisesRegex(RuntimeError, "did not finish"):
                    service.sync_netlify(url, state_file, threading.Event())
            self.assertNotIn("deploy_id", service.read_json(state_file))

    def test_healthy_same_address_does_not_redeploy(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            url = "https://existing-link.trycloudflare.com"
            service.save_json(state_file, {"published_url": url})
            client = Mock()
            client.site.return_value = {"name": "swangz-ai"}
            with patch.object(service, "Netlify", return_value=client), patch.object(service, "netlify_token", return_value="test"), patch.object(service, "healthy", return_value=True):
                service.sync_netlify(url, state_file, threading.Event())
            client.begin.assert_not_called()
            client.api.assert_not_called()
