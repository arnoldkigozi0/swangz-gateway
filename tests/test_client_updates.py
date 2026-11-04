"""D-003 abuse tests. Pure Python TEST-key signing; never live providers or keys."""

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from swangz_client import cli, core, keystore, release_keys, updater
from tests.fake_releases import FakeReleases

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = json.loads((Path(__file__).parent / "fixtures" / "test_release_rsa4096.json").read_text())
N, D, E = int(TEST_KEY["n"]), int(TEST_KEY["d"]), TEST_KEY["e"]
TEST_PINS = {"test-only": (N, E)}
NOW = 1800000000
PREFIX = "/api/device/releases/pilot/"
DEVICE_KEY = "swangz_test_device_only"


def encoded(raw):
    tail = updater.SHA256_DER + hashlib.sha256(raw).digest()
    return b"\x00\x01" + b"\xff" * (512 - len(tail) - 3) + b"\x00" + tail


def sign(raw=None, block=None):
    block = encoded(raw) if block is None else block
    return pow(int.from_bytes(block, "big"), D, N).to_bytes(512, "big")


class ReleaseVerificationTests(unittest.TestCase):
    def test_valid_signature_and_exact_bytes(self):
        raw = b'{"signed":"exact bytes, including whitespace"}\n'
        self.assertEqual(updater.verify(raw, sign(raw), TEST_PINS), "test-only")
        for bad in (raw + b" ", bytes([raw[0] ^ 1]) + raw[1:]):
            with self.assertRaises(updater.UpdateError):
                updater.verify(bad, sign(raw), TEST_PINS)

    def test_flipped_signature_wrong_length_and_noncanonical_encoding(self):
        raw = b"synthetic release"
        signature = sign(raw)
        block = encoded(raw)
        bad_oid = bytearray(block)
        bad_oid[-40] ^= 1
        bad_blocks = [bytes(bad_oid), block[:-1] + b"\x00", block[:8] + b"\x00" + block[9:],
                      block[:2] + block[3:] + b"\x00"]
        bad_signatures = [signature[:-1], signature + b"\x00", bytes([signature[0] ^ 1]) + signature[1:],
                          N.to_bytes(512, "big")]
        bad_signatures.extend(sign(block=b) for b in bad_blocks)
        for bad in bad_signatures:
            with self.subTest(signature=bad[:6]), self.assertRaises(updater.UpdateError):
                updater.verify(raw, bad, TEST_PINS)

    def test_strict_versions(self):
        for value in (None, 1, True, "1", "1.0", "01.0.0", "1.2.3-beta", "1.2.3.4", "-1.0.0", " 1.2.3", "1.2.3\n", "9999999999.0.0"):
            with self.subTest(value=value), self.assertRaises(updater.UpdateError):
                updater.version(value)

    def test_signature_cannot_introduce_a_new_pinned_key(self):
        raw = b"test release"
        for pins in ({}, {"other": (N - 2, E)}, {"test-only": (N, 3)}, {"test-only": (N >> 1, E)}):
            with self.subTest(pins=list(pins)), self.assertRaises(updater.UpdateError):
                updater.verify(raw, sign(raw), pins)

    def test_no_test_key_or_private_key_in_shipped_client(self):
        self.assertEqual(release_keys.KEYS, {})
        self.assertFalse(release_keys.ENABLED)
        for path in (ROOT / "swangz_client").rglob("*.py"):
            text = path.read_text()
            self.assertNotIn(str(D), text)
            self.assertNotIn(str(N), text)
            self.assertNotIn("BEGIN PRIVATE KEY", text)
            self.assertNotIn("test_release_rsa4096", text)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name)
        self.paths = core.Paths(home, home / "swangz")
        self.client = core.Client(self.paths)
        self.server = FakeReleases()
        self.addCleanup(self.server.close)
        self.client.api = lambda: core.Api(self.server.url, DEVICE_KEY)
        self.u = updater.Updater(self.client, running="0.1.0", now=lambda: NOW)
        self.pins = patch.dict(release_keys.KEYS, TEST_PINS, clear=True)
        self.pins.start()
        self.addCleanup(self.pins.stop)
        self.enable = patch.object(release_keys, "ENABLED", True)
        self.enable.start()
        self.addCleanup(self.enable.stop)
        self.payload = b"synthetic executable (never executed)"
        self.manifest = {
            "schema": 1, "key_id": "test-only", "channel": "pilot", "version": "0.2.0",
            "min_server": "1.0.0", "released": NOW - 10, "expires": NOW + 3600,
            "artifacts": [{"platform": {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform],
                           "arch": {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower()),
                           "file": "Swangz-test", "size": len(self.payload), "sha256": hashlib.sha256(self.payload).hexdigest()}]}

    def publish(self, payload=None):
        raw = json.dumps(self.manifest).encode()
        self.server.routes[PREFIX + "release.json"] = (200, raw, {"X-Swangz-Gateway-Version": "1.0.0"})
        self.server.routes[PREFIX + "release.json.sig"] = (200, sign(raw), {})
        for artifact in self.manifest["artifacts"]:
            self.server.routes[PREFIX + artifact["file"]] = (200, self.payload if payload is None else payload, {})

    def stage(self):
        self.publish()
        result = self.u.check()
        self.assertEqual(result["status"], "staged")
        self.assertEqual(result["platform_signature"], "not checked")
        self.u.target.write_bytes(b"original application")
        self.u.target.chmod(0o700)

    def test_no_pinned_key_or_closed_gate_means_zero_requests_and_no_credential_read(self):
        self.client.api = Mock(side_effect=AssertionError("credentials must not be read"))
        with patch.dict(release_keys.KEYS, {}, clear=True):
            self.assertEqual(self.u.check()["status"], "unavailable")
            self.assertEqual(self.u.install()["status"], "unavailable")
        with patch.object(release_keys, "ENABLED", False):
            self.assertEqual(self.u.check()["status"], "unavailable")
        self.assertEqual(self.server.seen, [])
        self.assertFalse(self.u.root.exists())

    def test_valid_download_is_private_and_has_no_acceptance_until_self_test(self):
        self.publish()
        self.u.check()
        path = self.u.root / "0.2.0" / "Swangz-test"
        self.assertEqual(path.read_bytes(), self.payload)
        self.assertNotIn("highest", self.u._read("state.json"))
        self.assertTrue(all(auth == "Bearer " + DEVICE_KEY for _, auth in self.server.seen))
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o500)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_unsigned_latest_hint_does_not_claim_a_verified_update_or_enable_downloads(self):
        self.client.store.device = Mock(return_value={"server": self.server.url, "key_storage": "file"})
        self.client.store.key = Mock(return_value=DEVICE_KEY)
        self.client._upgrade_agents = Mock()
        manifest = {"client": {"latest": "999.0.0", "minimum": "0.1.0"}, "packages": [], "apps": [], "recording": "test"}
        api = Mock()
        api.call.side_effect = [manifest, {}]
        self.client.api = Mock(return_value=api)
        with patch.dict(release_keys.KEYS, {}, clear=True):
            self.client.sync()
            self.assertFalse(self.client.status()["update_available"])
        self.assertEqual(self.server.seen, [])

    def test_expired_update_check_does_not_stop_ordinary_sync(self):
        self.client.store.device = Mock(return_value={"server": self.server.url, "key_storage": "file"})
        self.client.store.key = Mock(return_value=DEVICE_KEY)
        self.client._upgrade_agents = Mock()
        manifest = {"client": {"latest": "0.2.0", "minimum": "0.1.0"}, "packages": [], "apps": [], "recording": "test"}
        api = Mock()
        api.call.side_effect = [manifest, {}]
        self.client.api = Mock(return_value=api)
        with patch.object(updater.Updater, "check", side_effect=updater.UpdateError("Expired release")):
            self.assertEqual(self.client.sync()["manifest"], manifest)

    def test_manifest_and_signature_bit_flips_rejected_before_json_parse(self):
        for which in ("release.json", "release.json.sig"):
            self.publish()
            status, raw, headers = self.server.routes[PREFIX + which]
            self.server.routes[PREFIX + which] = (status, bytes([raw[0] ^ 1]) + raw[1:], headers)
            # Journal parsing uses decode too, so only assert on the manifest argument.
            original = updater.decode
            def decode_checked(value):
                if b'"schema"' in value:
                    self.fail("unauthenticated manifest was parsed")
                return original(value)
            with patch.object(updater, "decode", side_effect=decode_checked), self.assertRaises(updater.UpdateError):
                self.u.check()

    def test_manifest_policy_rejections_do_not_download_artifact(self):
        cases = [{"key_id": "unpinned"}, {"schema": True}, {"channel": "stable"},
                 {"expires": NOW}, {"released": NOW + updater.SKEW + 1}, {"released": True},
                 {"min_server": "2.0.0"}, {"version": "0.1.0"}, {"version": "0.0.9"},
                 {"version": "0.2.0-beta"}, {"artifacts": []}]
        original = json.loads(json.dumps(self.manifest))
        for changes in cases:
            self.manifest = {**original, **changes}
            self.server.seen.clear()
            self.publish()
            with self.subTest(changes=changes), self.assertRaises(updater.UpdateError):
                self.u.check()
            self.assertEqual([p for p, _ in self.server.seen], [PREFIX + "release.json", PREFIX + "release.json.sig"])

    def test_replayed_or_older_than_highest_accepted_is_refused(self):
        self.u._paths()
        self.u._state(highest="0.3.0")
        for value in ("0.2.0", "0.3.0", "0.1.9"):
            self.manifest["version"] = value
            self.publish()
            with self.assertRaises(updater.UpdateError):
                self.u.check()
        self.assertEqual(self.u._read("state.json")["highest"], "0.3.0")

    def test_unsafe_filenames_platform_and_arch_refused(self):
        for name in ("../escape", "/tmp/escape", "C:\\escape", "a\\b", "a..b", "https://evil.test/a", "a/b",
                     "CON", "nul.exe", "COM1", "trailing.", "release.json", "release.json.sig.hex"):
            self.manifest["artifacts"][0]["file"] = name
            self.publish()
            with self.subTest(name=name), self.assertRaises(updater.UpdateError):
                self.u.check()
        self.manifest["artifacts"][0]["file"] = "safe"
        self.manifest["artifacts"][0]["arch"] = "wrong-arch"
        self.publish()
        with self.assertRaises(updater.UpdateError):
            self.u.check()

    def test_hash_oversize_undersize_leave_no_staged_executable(self):
        for payload in (b"X" * len(self.payload), self.payload + b"extra", self.payload[:-1]):
            self.publish(payload)
            with self.subTest(size=len(payload)), self.assertRaises(updater.UpdateError):
                self.u.check()
            self.assertFalse((self.u.root / "0.2.0" / "Swangz-test").exists())

    def test_stream_stops_reading_at_cap_plus_one_and_never_writes_the_extra_byte(self):
        class Response(io.BytesIO):
            status, headers = 200, {}
            def geturl(inner):
                return self.server.url + "/oversize"
            def close(inner):
                inner.consumed = inner.tell()
                super().close()
        response = Response(b"x" * 100000)
        opener = Mock()
        opener.open.return_value = response
        output = io.BytesIO()
        with patch.object(updater.urllib.request, "build_opener", return_value=opener), self.assertRaises(updater.UpdateError):
            self.u._fetch(self.client.api(), "/oversize", 100, output)
        self.assertEqual(response.consumed, 101)
        self.assertLessEqual(len(output.getvalue()), 100)

    def test_cross_origin_redirects_never_send_device_key_to_destination(self):
        destination = FakeReleases()
        self.addCleanup(destination.close)
        for file in ("release.json", "release.json.sig", "Swangz-test"):
            self.publish()
            self.server.routes[PREFIX + file] = (302, b"", {"Location": destination.url + "/stolen"})
            with self.subTest(file=file), self.assertRaises(core.ApiFailure):
                self.u.check()
            self.assertEqual(destination.seen, [])

    def test_missing_gateway_version_and_non_https_non_loopback_are_refused(self):
        self.publish()
        status, raw, _ = self.server.routes[PREFIX + "release.json"]
        self.server.routes[PREFIX + "release.json"] = (status, raw, {})
        with self.assertRaises(updater.UpdateError):
            self.u.check()
        api = core.Api("https://gateway.example.test", DEVICE_KEY)
        api.server = "http://gateway.example.test"
        with self.assertRaises(updater.UpdateError):
            self.u._fetch(api, "/release.json", 100)

    def test_duplicate_json_and_nonfinite_values_are_refused_after_signature_verifies(self):
        self.u._paths()
        for raw in (b'{"schema":1,"schema":1}', b'{"schema":NaN}', b'{"schema":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(updater.UpdateError):
                self.u._validate(raw, sign(raw), "1.0.0")

    def test_tampered_stage_and_expired_before_install_never_launch(self):
        self.stage()
        launch = Mock()
        path = self.u.root / "0.2.0" / "Swangz-test"
        path.chmod(0o600)
        path.write_bytes(b"changed")
        with self.assertRaises(updater.UpdateError):
            self.u.install(launch=launch)
        launch.assert_not_called()
        self.publish()
        self.u.check()
        self.u.now = lambda: NOW + 4000
        with self.assertRaises(updater.UpdateError):
            self.u.install(launch=launch)
        launch.assert_not_called()

    def test_post_update_read_only_self_test_checks_state_and_keychain(self):
        self.stage()
        digest = hashlib.sha256(self.payload).hexdigest()
        self.u.target.write_bytes(self.payload)
        self.u._journal({"phase": "new_moved", "version": "0.2.0", "sha256": digest, "nonce": "test-nonce"})
        new = updater.Updater(self.client, running="0.2.0")
        keystore.write_private(self.paths.data / "state.json", "not json")
        with self.assertRaises(updater.UpdateError):
            new.post_update()
        self.assertFalse((self.u.root / "update-ok").exists())
        keystore.write_private(self.paths.data / "state.json", '{}')
        keystore.write_private(self.paths.data / "device.json", json.dumps({"server": self.server.url, "key_id": "test", "key_storage": "keychain"}))
        self.client.store.credentials = Mock()
        self.client.store.credentials.get.return_value = None
        with self.assertRaises(keystore.KeyStoreError):
            new.post_update()
        self.client.store.credentials.get.return_value = DEVICE_KEY
        new.post_update()
        self.client.store.credentials.get.assert_called_with(self.server.url, "test")
        self.client.store.credentials.put.assert_not_called()
        self.assertTrue((self.u.root / "update-ok").exists())

    def test_failed_self_test_or_timeout_rolls_back_and_suppresses_retry(self):
        self.stage()
        for timeout in (False, True):
            process = Mock()
            process.poll.return_value = None if timeout else 1
            ticks = iter((0, 1, 61))
            with self.subTest(timeout=timeout), self.assertRaises(updater.UpdateError):
                self.u.install(launch=Mock(return_value=process), monotonic=lambda: next(ticks), sleep=lambda _: None)
            self.assertEqual(self.u.target.read_bytes(), b"original application")
            self.assertFalse(self.u.prev.exists())
            self.assertEqual(self.u._read("state.json")["status"], "update_failed")
            self.assertNotIn("highest", self.u._read("state.json"))
            if timeout:
                process.kill.assert_called_once()
                process.wait.assert_called_once()
            self.publish()
            with self.assertRaises(updater.UpdateError):
                self.u.check()
            # Reset only between the two independent failure scenarios.
            (self.u.root / "state.json").unlink()
            self.stage()

    def test_crash_at_each_swap_boundary_recovers_on_next_start(self):
        self.stage()
        for phase in ("prepared", "old_moved", "new_moved"):
            pending = {"phase": phase, "version": "0.2.0", "nonce": "test", "sha256": hashlib.sha256(self.payload).hexdigest(),
                       "old_sha256": hashlib.sha256(b"original application").hexdigest()}
            self.u._journal(pending)
            if phase != "prepared":
                os.replace(self.u.target, self.u.prev)
            if phase == "new_moved":
                self.u.target.write_bytes(self.payload)
            fresh = updater.Updater(self.client)
            with self.subTest(phase=phase):
                self.assertTrue(fresh.recover())
                self.assertEqual(fresh.target.read_bytes(), b"original application")
                self.assertEqual(fresh._read("state.json")["failed_version"], "0.2.0")
                self.assertFalse(fresh.recover())

    @unittest.skipUnless(os.name == "posix", "portable script fixture requires a POSIX shebang; native builds await CI")
    def test_valid_end_to_end_launch_self_test_accept_restart_then_sync_removes_one_prev(self):
        # This is a signed TEST executable, not downloaded/third-party program content.
        self.payload = (f'#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(ROOT)!r})\n'
                        'from swangz_client import core, cli, updater\n'
                        'core.Client.updater = lambda c: updater.Updater(c, running="0.2.0")\n'
                        'sys.exit(cli.main())\n').encode()
        self.manifest["artifacts"][0].update(size=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())
        self.stage()
        result = self.u.install()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.u.target.read_bytes(), self.payload)
        self.assertEqual(self.u.prev.read_bytes(), b"original application")
        self.assertEqual(self.u._read("state.json")["highest"], "0.2.0")
        new = updater.Updater(self.client, running="0.2.0")
        self.assertFalse(new.recover())
        self.u.synced()  # old process cannot retire the previous version
        self.assertTrue(self.u.prev.exists())
        new.synced()
        self.assertFalse(self.u.prev.exists())
        self.assertFalse((self.u.root / "pending.json").exists())
        self.assertEqual(new._read("state.json")["highest"], "0.2.0")
        with self.assertRaises(updater.UpdateError):
            new.check()  # signed replay of accepted version

    def test_newer_manifest_clears_failed_version_restriction(self):
        self.u._paths()
        self.u._state(failed_version="0.2.0", highest="0.1.0")
        self.manifest["version"] = "0.3.0"
        self.publish()
        self.assertEqual(self.u.check()["status"], "staged")
        self.assertEqual(self.u._read("state.json")["highest"], "0.1.0")

    def test_symlink_escape_and_concurrent_updaters_are_refused(self):
        self.u._paths()
        with self.u.locked(), self.assertRaises(OSError):
            with updater.Updater(self.client).locked():
                self.fail("second updater acquired the lock")
        if os.name == "posix":
            external = self.paths.home / "external"
            external.mkdir()
            (self.u.root / "0.2.0").symlink_to(external, target_is_directory=True)
            self.publish()
            with self.assertRaises(updater.UpdateError):
                self.u.check()
            self.assertEqual(list(external.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
