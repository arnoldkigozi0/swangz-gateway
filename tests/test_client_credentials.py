"""Synthetic credential and hostile-input tests. Never contact a provider or a real OS keychain."""

import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request

from swangz_client import agents, cli, core, keystore


SECRET = "sgw_synthetic_test_credential"
SERVER = "https://hub.example"
INFO = {"server": SERVER, "key_id": "device-1", "owner_kind": "company", "name": "Fixture",
        "person": {"name": "Fixture", "email": "fixture@swangzavenue.com"}}


class MemoryCredentials:
    def __init__(self):
        self.items = {}

    def put(self, server, key_id, secret):
        self.items[(server, key_id)] = secret

    def get(self, server, key_id):
        return self.items.get((server, key_id))

    def delete(self, server, key_id):
        self.items.pop((server, key_id), None)


class CredentialTests(unittest.TestCase):
    def setUp(self):
        # Exercise helper mechanics against fixtures; this does not lift the CLI-prefix rollout gate.
        gate = patch.object(agents, "CLAUDE_PREFIX_VERIFIED", True)
        gate.start()
        self.addCleanup(gate.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="swangz-credentials-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = core.Paths(self.root / "home", self.root / "data")
        self.credentials = MemoryCredentials()
        self.store = core.Store(self.paths, self.credentials)

    def legacy(self):
        core.write_private(self.paths.data / "device.json", json.dumps(INFO))
        core.write_private(self.paths.data / "device.key", SECRET)

    def test_native_enrolment_restart_and_exact_cleanup(self):
        self.credentials.put(SERVER, "other", "unrelated")
        self.store.save_device(INFO, SECRET)
        self.assertFalse((self.paths.data / "device.key").exists())
        restart = core.Store(self.paths, self.credentials)
        self.assertEqual(restart.key(), SECRET)
        self.assertEqual(restart.device()["key_storage"], "keychain")
        restart.wipe()
        self.assertEqual(self.credentials.items, {(SERVER, "other"): "unrelated"})
        self.assertIsNone(restart.device())

    def test_migration_put_get_compare_precedes_removal(self):
        self.legacy()
        seen = []
        put = self.credentials.put
        get = self.credentials.get
        def record_put(*args):
            seen.append("put")
            self.assertEqual((self.paths.data / "device.key").read_text(), SECRET)
            put(*args)
        def record_get(*args):
            seen.append("get")
            self.assertEqual((self.paths.data / "device.key").read_text(), SECRET)
            return get(*args)
        with patch.object(self.credentials, "put", side_effect=record_put), patch.object(self.credentials, "get", side_effect=record_get):
            self.assertEqual(self.store.key(), SECRET)
        self.assertEqual(seen, ["put", "get"])
        self.assertFalse((self.paths.data / "device.key").exists())

    def test_unavailable_write_error_and_mismatched_read_preserve_usable_fallback(self):
        for failure in ("unavailable", "write", "read", "mismatch"):
            with self.subTest(failure=failure):
                self.legacy()
                credentials = MemoryCredentials()
                if failure == "mismatch":
                    credentials.get = Mock(return_value="wrong")
                elif failure == "read":
                    credentials.get = Mock(side_effect=keystore.KeyStoreError("read failed"))
                else:
                    exc = keystore.Unavailable if failure == "unavailable" else keystore.KeyStoreError
                    credentials.put = Mock(side_effect=exc("write failed"))
                store = core.Store(self.paths, credentials)
                self.assertEqual(store.key(), SECRET)
                self.assertEqual((self.paths.data / "device.key").read_text(), SECRET)
                self.assertEqual(store.device()["key_storage"], "file")
                self.assertIn("protected file", store.device()["credential_warning"])
                if os.name == "posix":
                    self.assertEqual((self.paths.data / "device.key").stat().st_mode & 0o777, 0o600)

    def test_interruption_before_commit_preserves_original_and_recovers(self):
        self.legacy()
        save = self.store._save_info
        def interrupt(info):
            if info.get("key_storage") == "keychain":
                raise OSError("simulated interruption")
            save(info)
        with patch.object(self.store, "_save_info", side_effect=interrupt):
            with self.assertRaises(OSError):
                self.store.key()
        self.assertEqual((self.paths.data / "device.key").read_text(), SECRET)
        self.assertEqual(core.Store(self.paths, self.credentials).key(), SECRET)
        self.assertFalse((self.paths.data / "device.key").exists())

    def test_interruption_during_erase_uses_committed_native_item_on_restart(self):
        self.legacy()
        def interrupt(path):
            Path(path).write_bytes(b"\0" * len(SECRET))
            raise KeyboardInterrupt
        with patch.object(keystore, "erase_file", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.store.key()
        self.assertEqual(self.store.device()["key_storage"], "keychain")
        self.assertEqual(core.Store(self.paths, self.credentials).key(), SECRET)
        self.assertFalse((self.paths.data / "device.key").exists())

    def test_interrupted_initial_put_can_recover_without_a_legacy_file(self):
        self.store._save_info({**INFO, "keychain_pending": True, "key_storage": "file"})
        self.credentials.put(SERVER, INFO["key_id"], SECRET)
        self.assertEqual(core.Store(self.paths, self.credentials).key(), SECRET)
        self.assertEqual(self.store.device()["key_storage"], "keychain")

    def test_locked_native_store_does_not_fall_back_or_destroy_identity(self):
        self.store.save_device(INFO, SECRET)
        with patch.object(self.credentials, "get", side_effect=keystore.KeyStoreError("locked")):
            with self.assertRaises(keystore.KeyStoreError):
                core.Store(self.paths, self.credentials).key()
        self.assertEqual(self.store.device()["key_storage"], "keychain")
        self.assertFalse((self.paths.data / "device.key").exists())

    def test_cleanup_failure_retains_tombstone_then_retries(self):
        self.store.save_device(INFO, SECRET)
        with patch.object(self.credentials, "delete", side_effect=keystore.KeyStoreError("locked")):
            with self.assertRaises(keystore.KeyStoreError):
                self.store.wipe()
        self.assertTrue(self.store.device()["cleanup_pending"])
        self.assertIsNone(self.store.key())
        core.Store(self.paths, self.credentials).wipe()
        self.assertIsNone(self.store.device())
        self.assertEqual(self.credentials.items, {})

    def test_windows_default_is_local_and_legacy_fallback_moves_only_after_readback(self):
        env = {"APPDATA": str(self.root / "Roaming"), "LOCALAPPDATA": str(self.root / "Local")}
        with patch.dict(os.environ, env), patch("swangz_client.core.sys.platform", "win32"):
            with patch.dict(os.environ, {"SWANGZ_HOME": ""}):
                paths = core.Paths(self.paths.home)
        self.assertEqual(paths.data, self.root / "Local" / "Swangz")
        core.write_private(paths.legacy_data / "device.json", json.dumps(INFO))
        core.write_private(paths.legacy_data / "device.key", SECRET)
        store = core.Store(paths, self.credentials)
        with patch.object(self.credentials, "put", side_effect=keystore.Unavailable("none")):
            self.assertEqual(store.key(), SECRET)
        self.assertEqual((paths.data / "device.key").read_text(), SECRET)
        self.assertFalse((paths.legacy_data / "device.key").exists())
        self.assertEqual(core.Store(paths, self.credentials).key(), SECRET)

    def test_legacy_managed_copies_upgrade_on_restart_without_changing_unrelated_settings(self):
        self.legacy()
        path = agents.claude_settings(self.paths)
        original = {"theme": "mine", "env": {"EDITOR": "vim", "ANTHROPIC_AUTH_TOKEN": SECRET,
                    "ANTHROPIC_BASE_URL": SERVER + "/anthropic", "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1"}}
        core.write_private(path, json.dumps(original))
        record = {"mode": "managed", "base_url": SERVER + "/anthropic", "file": str(path),
                  "wrote": {k: agents.digest(v) for k, v in original["env"].items() if k != "EDITOR"}}
        self.store.save_state({"installed": {"claude-code": record}})
        client = core.Client(self.paths, credentials=self.credentials)
        client.status()
        result = json.loads(path.read_text())
        self.assertEqual(result["theme"], "mine")
        self.assertEqual(result["env"]["EDITOR"], "vim")
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", result["env"])
        self.assertIn("key --for claude-code", result["apiKeyHelper"])
        self.assertEqual(client.store.state()["installed"]["claude-code"]["credential_config"], 2)
        for file in self.root.rglob("*"):
            if file.is_file():
                self.assertNotIn(SECRET.encode(), file.read_bytes(), str(file))

    def test_helper_requires_pipe_and_prints_bare_secret_with_separate_bounded_log(self):
        self.store.save_device(INFO, SECRET)
        self.store.save_state({"installed": {"claude-code": {"credential_config": 2}}})
        client = core.Client(self.paths, credentials=self.credentials)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["key", "--for", "claude-code"], client), 0)
        self.assertEqual(out.getvalue(), SECRET)
        self.assertNotIn(SECRET, (self.paths.data / "credential-access.log").read_text())
        terminal = io.StringIO()
        terminal.isatty = lambda: True
        with contextlib.redirect_stdout(terminal), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["key", "--for", "claude-code"], client), 1)
        self.assertEqual(terminal.getvalue(), "")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit):
                cli.main(["key"], client)

    def test_scoped_child_environment_and_windows_managed_gates(self):
        self.store.save_device(INFO, SECRET)
        record = agents.install_claude(self.paths, SERVER + "/anthropic", SECRET, "scoped")
        self.store.save_state({"installed": {"claude-code": record}})
        client = core.Client(self.paths, credentials=self.credentials)
        before = dict(os.environ)
        argv, env = client.agent_command("claude-code")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], SECRET)
        self.assertEqual(dict(os.environ), before)
        self.assertNotIn(SECRET, str(argv))
        with patch("swangz_client.agents.sys.platform", "win32"):
            for fn, base in ((agents.install_claude, SERVER + "/anthropic"), (agents.install_codex, SERVER + "/openai/v1")):
                result = fn(self.paths, base, SECRET, "managed")
                self.assertEqual(result["mode"], "scoped")
                self.assertTrue(result["gated"])
        self.assertFalse(self.paths.home.exists())

    def test_managed_helper_write_interruption_is_repeatable(self):
        first = agents.install_claude(self.paths, SERVER + "/anthropic", SECRET, "managed")
        second = agents.install_claude(self.paths, SERVER + "/anthropic", SECRET, "managed")
        self.assertEqual(first, second)
        agents.remove_claude(self.paths, second)
        self.assertNotIn("apiKeyHelper", agents.claude_settings(self.paths).read_text())

    def test_unverified_claude_prefix_gates_managed_setup_and_scrubs_old_copy(self):
        self.legacy()
        path = agents.claude_settings(self.paths)
        core.write_private(path, json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": SECRET}}))
        old = {"mode": "managed", "base_url": SERVER + "/anthropic", "file": str(path),
               "wrote": {"ANTHROPIC_AUTH_TOKEN": agents.digest(SECRET)}}
        self.store.save_state({"installed": {"claude-code": old}})
        with patch.object(agents, "CLAUDE_PREFIX_VERIFIED", False):
            client = core.Client(self.paths, credentials=self.credentials)
            self.assertIsNone(client.status()["credential_warning"])
            record = client.store.state()["installed"]["claude-code"]
            self.assertEqual(record["mode"], "scoped")
            self.assertTrue(record["gated"])
            self.assertIn("/anthropic", record["detail"])
        self.assertNotIn(SECRET, path.read_text())
        self.assertNotIn("apiKeyHelper", path.read_text())

    def test_changed_managed_blocks_and_conflicting_personal_auth_are_preserved(self):
        path = agents.claude_settings(self.paths)
        core.write_private(path, '{"apiKeyHelper":"my-existing-helper", "env":{"EDITOR":"vim"}}')
        before = path.read_text()
        with self.assertRaises(agents.AgentConfigError):
            agents.install_claude(self.paths, SERVER + "/anthropic", SECRET, "managed")
        self.assertEqual(path.read_text(), before)
        record = agents.install_codex(self.paths, SERVER + "/openai/v1", SECRET, "managed")
        config = agents.codex_config(self.paths)
        config.write_text(config.read_text().replace('name = "Swangz AI Hub"', 'name = "changed-by-person"'))
        profile = self.paths.home / ".profile"
        profile.write_text(profile.read_text().replace("export SWANGZ_AI_KEY", "export MY_OWN_KEY"))
        config_before, profile_before = config.read_text(), profile.read_text()
        agents.remove_codex(self.paths, record)
        self.assertEqual(config.read_text(), config_before)
        self.assertEqual(profile.read_text(), profile_before)

    def test_erase_failure_keeps_a_visible_warning_and_retry_clears_it(self):
        self.legacy()
        with patch.object(keystore, "erase_file", side_effect=OSError("disk unavailable")):
            self.assertEqual(self.store.key(), SECRET)
        self.assertIn("old key file", self.store.device()["credential_warning"])
        self.assertEqual(core.Store(self.paths, self.credentials).key(), SECRET)
        self.assertNotIn("credential_warning", self.store.device())

    def test_login_ignores_response_origin_and_manifest_foreign_target_is_not_saved(self):
        api = Mock()
        api.call.side_effect = [{"verification_uri": SERVER + "/device", "user_code": "ABCD-EFGH", "device_code": "fixture"},
                                {**INFO, "key": SECRET, "server": "https://evil.example"}]
        client = core.Client(self.paths, credentials=self.credentials, api_factory=lambda *args: api,
                             sleep=lambda s: None, open_url=lambda url: None)
        self.assertEqual(client.login(SERVER)["server"], SERVER)
        manifest = {"packages": [{"id": "claude-code", "install": {"type": "agent", "base_url": "https://evil.example/anthropic"}}]}
        api.call.side_effect = None
        api.call.return_value = manifest
        with self.assertRaises(core.ApiFailure):
            client.refresh()
        self.assertIsNone(client.store.manifest())
        self.assertEqual(client.store.key(), SECRET)

    def test_legacy_helper_rewrite_interruption_retries_from_the_old_record(self):
        self.legacy()
        path = agents.claude_settings(self.paths)
        core.write_private(path, "{}")
        record = {"mode": "managed", "base_url": SERVER + "/anthropic", "file": str(path), "wrote": {}}
        self.store.save_state({"installed": {"claude-code": record}})
        client = core.Client(self.paths, credentials=self.credentials)
        with patch.object(client.store, "save_state", side_effect=OSError("interrupted after settings write")):
            client.status()
        self.assertIn("apiKeyHelper", path.read_text())
        restarted = core.Client(self.paths, credentials=self.credentials)
        self.assertIsNone(restarted.status()["credential_warning"])
        self.assertEqual(restarted.store.state()["installed"]["claude-code"]["credential_config"], 2)


class AdapterTests(unittest.TestCase):
    def test_subprocess_backends_send_secrets_only_on_stdin(self):
        for backend in (keystore.SecretService, keystore.Keychain):
            with self.subTest(backend=backend.__name__):
                run = Mock(return_value=SimpleNamespace(returncode=0, stdout=SECRET + "\n", stderr=""))
                adapter = backend(run)
                adapter.put(SERVER, "id", SECRET)
                self.assertNotIn(SECRET, str(run.call_args.args))
                self.assertIn(SECRET, run.call_args.kwargs["input"])
                self.assertEqual(adapter.get(SERVER, "id"), SECRET)
                adapter.delete(SERVER, "id")
                self.assertNotIn(SECRET, str(run.call_args.args))
                run.return_value = SimpleNamespace(returncode=5, stdout=SECRET, stderr=SECRET)
                with self.assertRaises(keystore.KeyStoreError) as caught:
                    adapter.get(SERVER, "id")
                self.assertNotIn(SECRET, str(caught.exception))
                run.side_effect = FileNotFoundError
                with self.assertRaises(keystore.Unavailable):
                    adapter.put(SERVER, "id", SECRET)

    def test_windows_ctypes_write_read_free_delete_and_local_persistence(self):
        lib = SimpleNamespace(**{name: Mock() for name in ("CredWriteW", "CredReadW", "CredDeleteW", "CredFree")})
        blob = (ctypes.c_ubyte * len(SECRET)).from_buffer_copy(SECRET.encode())
        stored = keystore.CREDENTIALW(CredentialBlob=blob, CredentialBlobSize=len(SECRET))
        def write(ptr, flags):
            cred = ctypes.cast(ptr, ctypes.POINTER(keystore.CREDENTIALW)).contents
            self.assertEqual((cred.Type, cred.Persist), (1, 2))
            self.assertEqual(cred.TargetName, "Swangz AI Hub:hub.example/id")
            self.assertEqual(ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize), SECRET.encode())
            return True
        def read(target, kind, flags, out):
            ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(keystore.CREDENTIALW)))[0] = ctypes.pointer(stored)
            return True
        lib.CredWriteW.side_effect, lib.CredReadW.side_effect = write, read
        adapter = keystore.CredentialManager(lib, last_error=lambda: 1168)
        adapter.put(SERVER, "id", SECRET)
        self.assertEqual(adapter.get(SERVER, "id"), SECRET)
        lib.CredFree.assert_called_once()
        lib.CredReadW.side_effect = None
        lib.CredReadW.return_value = False
        self.assertIsNone(adapter.get(SERVER, "id"))
        adapter.delete(SERVER, "id")
        lib.CredDeleteW.assert_called_once_with("Swangz AI Hub:hub.example/id", 1, 0)
        lib.CredWriteW.side_effect = None
        lib.CredWriteW.return_value = False
        with self.assertRaises(keystore.KeyStoreError):
            adapter.put(SERVER, "id", SECRET)
        adapter.last_error = lambda: 5
        with self.assertRaises(keystore.KeyStoreError):
            adapter.get(SERVER, "id")
        lib.CredDeleteW.return_value = False
        with self.assertRaises(keystore.KeyStoreError):
            adapter.delete(SERVER, "id")

    def test_legacy_windows_registry_removal_preserves_changed_value(self):
        registry = SimpleNamespace(HKEY_CURRENT_USER=1, KEY_QUERY_VALUE=1, KEY_SET_VALUE=2,
                                   OpenKey=Mock(), QueryValueEx=Mock(), DeleteValue=Mock())
        registry.OpenKey.return_value.__enter__ = Mock(return_value="handle")
        registry.OpenKey.return_value.__exit__ = Mock(return_value=False)
        record = {"kind": "windows-user-env"}
        registry.QueryValueEx.return_value = ("their-own-key", 1)
        agents.forget_env(None, "SWANGZ_AI_KEY", record, key=SECRET, registry=registry)
        registry.DeleteValue.assert_not_called()
        registry.QueryValueEx.return_value = (SECRET, 1)
        agents.forget_env(None, "SWANGZ_AI_KEY", record, key=SECRET, registry=registry)
        registry.DeleteValue.assert_called_once_with("handle", "SWANGZ_AI_KEY")


class OriginTests(unittest.TestCase):
    def test_origin_config_and_redirect_injection_refused_before_auth_or_write(self):
        for bad in ("https://evil.example/anthropic", SERVER + '/anthropic"\n[mcp_servers.bad]',
                    SERVER + "/anthropic?steal=1", SERVER + "/../anthropic", SERVER + "\\@evil.example/anthropic"):
            with self.subTest(bad=bad):
                with self.assertRaises((core.ApiFailure, agents.AgentConfigError)):
                    core.Client._agent_url(bad, "claude-code", SERVER)
        for bad in (SERVER + '/openai/v1"', SERVER + "/openai/v1\nfoo=1", SERVER + "/openai\\v1"):
            with self.assertRaises(agents.AgentConfigError):
                agents.codex_block(bad)
            with self.assertRaises(agents.AgentConfigError):
                agents.codex_overrides(bad)
        req = urllib.request.Request(SERVER + "/api/device/manifest", headers={"Authorization": "Bearer " + SECRET})
        with self.assertRaises(core.ApiFailure):
            core.PinnedRedirect(SERVER).redirect_request(req, None, 302, "", {}, "https://evil.example/steal")

    def test_unknown_is_preserved_but_explicit_revocation_triggers_cleanup(self):
        api = core.Api(SERVER, SECRET)
        for code, kind in (("device_unknown", core.ApiFailure), ("device_revoked", core.Revoked)):
            with patch.object(api, "_open", return_value=(401, json.dumps({"code": code}).encode(), {})):
                with self.assertRaises(kind) as caught:
                    api.call("GET", "/device/manifest")
                self.assertEqual(isinstance(caught.exception, core.Revoked), code == "device_revoked")
        client = core.Client()
        client.remove_everything = Mock()
        def unknown():
            raise core.ApiFailure(401, "device_unknown", "unknown")
        with self.assertRaises(core.ApiFailure):
            client._guard(unknown)
        client.remove_everything.assert_not_called()


if __name__ == "__main__":
    unittest.main()
