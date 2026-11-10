"""G4 server side: the gateway is a distribution point, never a source of trust.

Synthetic bytes and the fixture TEST key only. The gateway verifies and serves; nothing here (or in gateway/)
signs for real, and no production key exists.
"""

import contextlib
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import releases, staff
from gateway.config import Settings
from gateway.server import make_server
from swangz_client import core, release_keys, updater

from .test_client_updates import D, N, NOW, TEST_PINS, sign
from .test_devices import DeviceBase

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform]
ARCH = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
PREFIX = "/api/device/releases/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReleaseBase(DeviceBase):
    def setUp(self):
        super().setUp()
        self.key = self.enrol()["key"]
        self.gw, self.data = self.rig.gw, self.rig.settings.data_dir
        self.db = self.gw.db
        pins = patch.dict(release_keys.KEYS, TEST_PINS, clear=True)
        pins.start()
        self.addCleanup(pins.stop)
        self.payload = b"synthetic executable (never executed)"

    # ------------------------------------------------------------ making and publishing releases

    def make(self, version="0.2.0", channel="stable", payload=None, name=None, mutate=None, sign_it=True):
        """A release folder as the offline signer would hand it over."""
        folder = tempfile.mkdtemp(dir=self.tmp)
        payload = self.payload if payload is None else payload
        name = name or f"Swangz-{version}-test"
        artifact = {"platform": SYSTEM, "arch": ARCH, "file": name, "size": len(payload), "sha256": sha(payload)}
        manifest = {"schema": 1, "key_id": "test-only", "channel": channel, "version": version, "min_server": "1.0.0",
                    "released": NOW - 10, "expires": NOW + 3600, "artifacts": [artifact]}
        if mutate:
            mutate(manifest)
        raw = json.dumps(manifest).encode()
        Path(folder, "release.json").write_bytes(raw)
        Path(folder, "release.json.sig").write_bytes(sign(raw) if sign_it else b"\0" * 512)
        if isinstance(name, str) and "/" not in name and name not in ("", ".", "..", "release.json", "release.json.sig"):
            Path(folder, name).write_bytes(payload)
        return folder

    def publish(self, version="0.2.0", channel="stable", **kw):
        folder = self.make(version, channel, **kw)
        out = releases.publish(self.db, self.data, folder, channel)
        return folder, out

    def pilot(self, action="add"):
        return releases.pilot_change(self.db, action, self.rig.person_id)

    def stored(self, channel, *parts):
        return Path(self.data, "releases", channel, *parts)

    # ------------------------------------------------------------ the device's side

    def get(self, channel, name, key="", headers=None, raw_path=None):
        h = {"authorization": "Bearer " + (self.key if key == "" else key)} if key is not None else {}
        h.update(headers or {})
        status, hdrs, body = self.rig.request("GET", raw_path or f"{PREFIX}{channel}/{name}", None, h)
        return status, hdrs, body

    def downloads(self, wait=0):
        """The record is written just after the last byte goes out, so a test that expects `wait` of them waits for it."""
        if wait:
            self.rig.wait_for(lambda: len(self.downloads()) >= wait)
        return self.db.q("SELECT * FROM audit WHERE action = 'downloaded a release file' ORDER BY id")


class WhoMayAskTests(ReleaseBase):
    """Every route uses enroll.device_auth() unchanged."""

    def everything(self):
        return [(c, n) for c in ("stable", "pilot") for n in ("release.json", "release.json.sig", f"Swangz-0.2.0-test")]

    def prepare(self):
        self.publish("0.2.0", "stable")
        self.publish("0.2.0", "pilot")
        self.pilot()

    def test_the_sweep_has_exactly_one_route_and_it_only_reads(self):
        found = [(m, rx.pattern, signed_in) for m, rx, _, signed_in, *_rest in staff.ROUTES if "device/releases" in rx.pattern]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], "GET")
        self.assertIn("(?P<channel>stable|pilot)", found[0][1])
        for method in ("POST", "PUT", "PATCH", "DELETE"):  # no upload, no change through HTTP
            status, _, _ = self.rig.request(method, PREFIX + "stable/release.json", b"x", {"x-swangz-app": "1", "authorization": "Bearer " + self.key})
            self.assertEqual(status, 404, method)
        self.assertEqual(self.get("stable", "release.json", key=None)[0], 401)

    def test_no_credentials_wrong_key_and_not_enrolled_are_refused(self):
        self.prepare()
        for channel, name in self.everything():
            with self.subTest(channel=channel, name=name):
                self.assertEqual(self.get(channel, name, key=None)[0], 401)
                self.gw.throttle.clear("devauth:127.0.0.1")
                status, _, body = self.get(channel, name, key="sgw_nope_nope")
                self.assertEqual((status, json.loads(body)["code"]), (401, "device_unknown"))
                self.gw.throttle.clear("devauth:127.0.0.1")
                # a key the app did not make (no enrolled device) is refused too
                status, _, body = self.get(channel, name, key=self.rig.key)
                self.assertEqual((status, json.loads(body)["code"]), (403, "not_enrolled"))

    def test_revoked_paused_and_ended_are_refused(self):
        self.prepare()
        db, pid = self.db, self.rig.person_id
        for label, setup, undo, expect in (
                ("paused", lambda: db.x("UPDATE people SET status = 'suspended' WHERE id = ?", (pid,)),
                 lambda: db.x("UPDATE people SET status = 'active' WHERE id = ?", (pid,)), (403, "person_paused")),
                ("ended", lambda: db.x("UPDATE people SET access_until = ? WHERE id = ?", (time.time() - 5, pid)),
                 lambda: db.x("UPDATE people SET access_until = NULL WHERE id = ?", (pid,)), (403, "access_ended")),
                ("everyone paused", lambda: db.set_setting("paused", "1"), lambda: db.set_setting("paused", "0"), (403, "paused"))):
            setup()
            for channel, name in self.everything():
                with self.subTest(case=label, channel=channel, name=name):
                    status, _, body = self.get(channel, name)
                    self.assertEqual((status, json.loads(body)["code"]), expect)
            undo()
        self.assertEqual(self.get("stable", "release.json")[0], 200)  # and all of it was reversible
        db.x("UPDATE keys SET revoked = ? WHERE id = ?", (time.time(), db.scalar("SELECT key_id FROM devices LIMIT 1")))
        for channel, name in self.everything():
            with self.subTest(case="revoked", channel=channel, name=name):
                status, _, body = self.get(channel, name)
                self.assertEqual((status, json.loads(body)["code"]), (401, "device_revoked"))

    def test_browser_and_console_sessions_are_not_device_keys(self):
        self.prepare()
        console = self.rig.login("owner")
        for channel, name in self.everything():
            for label, headers in (("staff session cookie", {"cookie": self.person_cookie}), ("console session cookie", {"cookie": console}),
                                   ("session cookie and the x-swangz-app header", {"cookie": self.person_cookie, "x-swangz-app": "1"})):
                with self.subTest(channel=channel, name=name, who=label):
                    status, _, _ = self.get(channel, name, key=None, headers=headers)
                    self.assertEqual(status, 401)
                    self.gw.throttle.clear("devauth:127.0.0.1")
        token = self.person_cookie.split("=", 1)[1]  # a staff session token presented as a bearer is not a device key
        self.assertEqual(self.get("stable", "release.json", key=token)[0], 401)

    def test_pilot_is_only_for_the_pilot_list_and_looks_like_no_release_to_everyone_else(self):
        self.publish("0.2.0", "stable")
        self.publish("0.3.0", "pilot")
        for name in ("release.json", "release.json.sig", "Swangz-0.3.0-test"):
            with self.subTest(name=name):
                status, _, body = self.get("pilot", name)
                self.assertEqual((status, json.loads(body)["error"]), (404, releases.GONE))
        # stable is for every enrolled device, and the pilot refusal is the same as "nothing published there"
        self.assertEqual(self.get("stable", "release.json")[0], 200)
        withdrawn = self.get("stable", "no-such-file")
        self.assertEqual(withdrawn[0], 404)
        self.pilot()
        self.assertEqual([self.get("pilot", n)[0] for n in ("release.json", "release.json.sig", "Swangz-0.3.0-test")], [200, 200, 200])
        self.pilot("remove")
        self.assertEqual(self.get("pilot", "release.json")[0], 404)
        self.assertEqual(self.downloads(wait=1)[-1]["outcome"], "ok")  # the pilot download that did happen was recorded; refusals were not

    def test_only_two_channels_exist(self):
        self.publish("0.2.0", "stable")
        for channel in ("beta", "Stable", "STABLE", "", "stable%2Fpilot", "current"):
            with self.subTest(channel=channel):
                self.assertEqual(self.get(channel, "release.json")[0], 404)
        self.assertEqual(self.stored("stable").name, "stable")


class ServeExactlyTests(ReleaseBase):
    def test_bytes_headers_and_no_tricks(self):
        folder, _ = self.publish("0.2.0", "stable")
        for name, ctype in (("release.json", "application/json"), ("release.json.sig", "application/octet-stream"),
                            ("Swangz-0.2.0-test", "application/octet-stream")):
            with self.subTest(name=name):
                status, h, body = self.get("stable", name)
                self.assertEqual(status, 200)
                self.assertEqual(body, Path(folder, name).read_bytes())  # byte for byte
                self.assertEqual(h["content-type"], ctype)
                self.assertEqual(h["content-length"], str(len(body)))
                self.assertEqual(h["cache-control"], "no-store")
                self.assertEqual(h["x-content-type-options"], "nosniff")
                for forbidden in ("content-encoding", "accept-ranges", "content-range", "location", "set-cookie"):
                    self.assertNotIn(forbidden, h)
        self.assertEqual(len(self.get("stable", "release.json.sig")[2]), 512)

    def test_a_range_request_gets_the_whole_file_not_a_slice(self):
        self.publish("0.2.0", "stable")
        status, h, body = self.get("stable", "Swangz-0.2.0-test", headers={"range": "bytes=5-9", "accept-encoding": "gzip, br"})
        self.assertEqual((status, body), (200, self.payload))
        self.assertNotIn("content-range", h)
        self.assertNotIn("content-encoding", h)

    def test_the_gateway_version_header_is_only_on_release_json_and_only_when_signed_in(self):
        import gateway

        self.publish("0.2.0", "stable")
        status, h, _ = self.get("stable", "release.json")
        self.assertEqual(h["x-swangz-gateway-version"], gateway.__version__)
        self.assertRegex(h["x-swangz-gateway-version"], r"^\d+\.\d+\.\d+$")
        for name in ("release.json.sig", "Swangz-0.2.0-test"):
            self.assertNotIn("x-swangz-gateway-version", self.get("stable", name)[1])
        for status, h, _ in (self.get("stable", "release.json", key=None), self.get("stable", "release.json", key="sgw_bad_key"),
                             self.get("stable", "other.bin"), self.get("pilot", "release.json")):
            self.assertNotEqual(status, 200)
            self.assertNotIn("x-swangz-gateway-version", h)
            self.gw.throttle.clear("devauth:127.0.0.1")
        self.assertNotIn("x-swangz-gateway-version", self.rig.request("GET", "/healthz")[1])

    def test_startup_refuses_a_version_that_is_not_strict_x_y_z(self):
        for bad in ("1.0", "1.0.0-beta", "v1.0.0", "01.0.0", "1.0.0.0", "1.0.0\n", "", None, 1):
            with self.subTest(version=bad), patch.object(releases, "__version__", bad):
                with self.assertRaises(RuntimeError):
                    releases.check_gateway_version()
                with self.assertRaises(RuntimeError):
                    make_server(Settings(host="127.0.0.1", port=0, data_dir=tempfile.mkdtemp(dir=self.tmp)))
        releases.check_gateway_version()

    def test_the_real_client_updater_stages_a_release_from_the_real_route(self):
        self.pilot()
        self.publish("0.2.0", "pilot")
        home = Path(tempfile.mkdtemp(dir=self.tmp))
        client = core.Client(core.Paths(home, home / "swangz"))
        client.api = lambda: core.Api(f"http://127.0.0.1:{self.rig.port}", self.key)
        u = updater.Updater(client, running="0.1.0", now=lambda: NOW)
        with patch.object(release_keys, "ENABLED", True):
            result = u.check()
        self.assertEqual((result["status"], result["version"]), ("staged", "0.2.0"))
        self.assertEqual((u.root / "0.2.0" / "Swangz-0.2.0-test").read_bytes(), self.payload)
        import gateway
        self.assertEqual(u._read("state.json")["gateway_version"], gateway.__version__)
        self.assertEqual([r["detail"].split(";")[0] for r in self.downloads(wait=1)], ["Swangz-0.2.0-test"])

    def test_a_tampered_stored_artifact_cannot_pass_the_clients_own_check(self):
        """The gateway cannot forge an update: flip a byte on its disk and the client refuses it."""
        self.pilot()
        self.publish("0.2.0", "pilot")
        path = self.stored("pilot", "0.2.0", "Swangz-0.2.0-test")
        data = bytearray(path.read_bytes())
        data[0] ^= 1
        path.write_bytes(bytes(data))
        home = Path(tempfile.mkdtemp(dir=self.tmp))
        client = core.Client(core.Paths(home, home / "swangz"))
        client.api = lambda: core.Api(f"http://127.0.0.1:{self.rig.port}", self.key)
        u = updater.Updater(client, running="0.1.0", now=lambda: NOW)
        with patch.object(release_keys, "ENABLED", True), self.assertRaises(updater.UpdateError):
            u.check()
        self.assertFalse((u.root / "0.2.0" / "Swangz-0.2.0-test").exists())

    def test_the_gateway_filename_rule_matches_the_clients(self):
        home = Path(tempfile.mkdtemp(dir=self.tmp))
        u = updater.Updater(core.Client(core.Paths(home, home / "swangz")), running="0.1.0", now=lambda: NOW)
        names = ["Swangz-1.0.0", "a", "a.b", "-bad", ".hid", "a b", "a..b", "end.", "con", "CON.exe", "Lpt1", "nul.txt", "com9.bin",
                 "release.json", "release.json.sig.hex", "x" * 128, "x" * 129, "ünï", "a/b", "a\\b", "a\x00b", "", "9", "A_b-c.d"]
        for name in names:
            raw = json.dumps({"schema": 1, "key_id": "test-only", "channel": "pilot", "version": "0.2.0", "min_server": "1.0.0",
                              "released": NOW - 10, "expires": NOW + 60,
                              "artifacts": [{"platform": SYSTEM, "arch": ARCH, "file": name, "size": 1, "sha256": "0" * 64}]}).encode()
            try:
                u._validate(raw, sign(raw), "1.0.0")
                client_ok = True
            except updater.UpdateError:
                client_ok = False
            with self.subTest(name=name):
                self.assertEqual(releases.valid_name(name), client_ok)
        # the gateway is stricter only about names it owns
        for name in ("release.json.sig", "current.json"):
            self.assertFalse(releases.valid_name(name))


class TraversalTests(ReleaseBase):
    def setUp(self):
        super().setUp()
        self.publish("0.2.0", "stable")
        Path(self.stored("stable", "0.2.0"), "unlisted.bin").write_bytes(b"on disk but not in the signed manifest")
        Path(self.data, "outside.bin").write_bytes(b"outside the channel folder")

    def test_names_that_try_to_leave_or_are_not_listed_are_404_and_leave_no_download_record(self):
        for raw in ("../../gateway.db", "%2e%2e", "%2E%2E%2Fx", "..%5cx", "%5cWindows%5cx", "%2fetc%2fpasswd", "C%3A%5Cx", "unlisted.bin",
                    "release.json.sig.hex", "current.json", "CON", ".lock", "..", ".", "%00", "Swangz-0.2.0-test%00", "x" * 200,
                    "Swangz-0.2.0-test.", "swangz-0.2.0-test", "Swangz-0.2.0-test/"):
            with self.subTest(name=raw):
                status, _, _ = self.get("stable", None, raw_path=f"{PREFIX}stable/{raw}")
                self.assertIn(status, (400, 404))
                self.assertNotEqual(status, 200)
        self.assertEqual(self.downloads(), [])

    def test_a_listed_file_that_is_missing_is_404_and_recorded_as_failed(self):
        self.stored("stable", "0.2.0", "Swangz-0.2.0-test").unlink()
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 404)
        self.assertEqual([r["outcome"] for r in self.downloads()], ["failed"])

    @unittest.skipIf(os.name != "posix", "needs symlinks and hard links")
    def test_symlinks_hard_links_and_swapped_folders_are_refused(self):
        art = self.stored("stable", "0.2.0", "Swangz-0.2.0-test")
        real = art.read_bytes()
        # symlinked file
        art.unlink()
        art.symlink_to(Path(self.data, "outside.bin"))
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 404)
        # a symlink to a file with the right bytes is still a link
        art.unlink()
        Path(self.data, "same.bin").write_bytes(real)
        art.symlink_to(Path(self.data, "same.bin"))
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 404)
        # hard link (a second name for the same inode)
        art.unlink()
        art.write_bytes(real)
        os.link(art, Path(self.data, "second-name.bin"))
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 404)
        os.unlink(Path(self.data, "second-name.bin"))
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 200)
        # symlinked manifest and signature
        for name in ("release.json", "release.json.sig"):
            path = self.stored("stable", "0.2.0", name)
            keep = path.read_bytes()
            path.unlink()
            Path(self.data, "moved-" + name).write_bytes(keep)
            path.symlink_to(Path(self.data, "moved-" + name))
            self.assertEqual(self.get("stable", name)[0], 404, name)
            path.unlink()
            path.write_bytes(keep)
            self.assertEqual(self.get("stable", name)[0], 200, name)
        # the version folder replaced by a link to a copy of itself elsewhere
        folder = self.stored("stable", "0.2.0")
        elsewhere = Path(self.tmp, "elsewhere")
        shutil.copytree(folder, elsewhere)
        shutil.rmtree(folder)
        folder.symlink_to(elsewhere)
        for name in ("release.json", "release.json.sig", "Swangz-0.2.0-test"):
            self.assertEqual(self.get("stable", name)[0], 404, name)
        folder.unlink()
        shutil.copytree(elsewhere, folder)
        # the channel folder replaced by a link
        chan = self.stored("stable")
        moved = Path(self.tmp, "chan-elsewhere")
        shutil.copytree(chan, moved)
        shutil.rmtree(chan)
        chan.symlink_to(moved)
        self.assertEqual(self.get("stable", "release.json")[0], 404)
        chan.unlink()
        shutil.copytree(moved, chan)
        self.assertEqual(self.get("stable", "release.json")[0], 200)
        # a symlinked or hard-linked pointer is no pointer
        pointer = self.stored("stable", "current.json")
        keep = pointer.read_bytes()
        pointer.unlink()
        Path(self.data, "pointer.json").write_bytes(keep)
        pointer.symlink_to(Path(self.data, "pointer.json"))
        self.assertEqual(self.get("stable", "release.json")[0], 404)

    def test_a_signed_manifest_name_that_is_not_a_valid_filename_is_never_served(self):
        """Even if a bad name got into a stored manifest, the route's own rule still refuses it."""
        path = self.stored("stable", "0.2.0", "release.json")
        manifest = json.loads(path.read_bytes())
        manifest["artifacts"][0]["file"] = "../outside.bin"
        path.write_bytes(json.dumps(manifest).encode())
        self.assertIn(self.get("stable", None, raw_path=PREFIX + "stable/..%2Foutside.bin")[0], (400, 404))
        self.assertEqual(self.get("stable", "%2e%2e%2foutside.bin")[0], 404)


class PublishChecksTests(ReleaseBase):
    def refused(self, folder, channel="stable", fragment=None):
        before = (releases.current(self.data, channel), sorted(os.listdir(self.stored(channel))) if self.stored(channel).exists() else [])
        with self.assertRaises(releases.ReleaseError) as caught:
            releases.publish(self.db, self.data, folder, channel)
        if fragment:
            self.assertIn(fragment, str(caught.exception))
        after = (releases.current(self.data, channel), sorted(os.listdir(self.stored(channel))) if self.stored(channel).exists() else [])
        self.assertEqual(before, after)  # a refused publish changes nothing, leaves no temp folder
        return caught.exception

    def test_a_good_release_is_stored_privately_and_made_current(self):
        folder, out = self.publish("0.2.0", "stable")
        self.assertEqual((out["version"], out["previous"]), ("0.2.0", None))
        self.assertEqual(releases.current(self.data, "stable"), "0.2.0")
        if os.name == "posix":
            for d in (self.stored(".."), self.stored("stable"), self.stored("stable", "0.2.0")):
                self.assertEqual(d.resolve().stat().st_mode & 0o777, 0o700, d)
            for f in self.stored("stable", "0.2.0").iterdir():
                self.assertEqual(f.stat().st_mode & 0o777, 0o600, f)
            self.assertEqual(self.stored("stable", "current.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(sorted(p.name for p in self.stored("stable", "0.2.0").iterdir()),
                         ["Swangz-0.2.0-test", "release.json", "release.json.sig"])

    def test_only_listed_files_are_copied(self):
        folder = self.make("0.2.0")
        Path(folder, "notes.txt").write_text("not listed")
        Path(folder, "private.key").write_text("never copied")
        releases.publish(self.db, self.data, folder, "stable")
        self.assertEqual(sorted(p.name for p in self.stored("stable", "0.2.0").iterdir()),
                         ["Swangz-0.2.0-test", "release.json", "release.json.sig"])

    def test_no_pinned_key_means_nothing_can_be_published(self):
        folder = self.make()
        with patch.dict(release_keys.KEYS, {}, clear=True):
            self.refused(folder, fragment="no release key")

    def test_bad_signatures(self):
        good = self.make()
        sig = Path(good, "release.json.sig").read_bytes()
        for label, data in (("flipped", bytes([sig[0] ^ 1]) + sig[1:]), ("short", sig[:-1]), ("long", sig + b"\0"), ("empty", b""),
                            ("zeros", b"\0" * 512), ("modulus", N.to_bytes(512, "big"))):
            folder = self.make()
            Path(folder, "release.json.sig").write_bytes(data)
            with self.subTest(sig=label):
                self.refused(folder)
        # a signature for different bytes
        folder = self.make()
        Path(folder, "release.json").write_bytes(Path(folder, "release.json").read_bytes() + b" ")
        self.refused(folder, fragment="not trusted")
        # a signature that is hex, not raw bytes
        folder = self.make()
        Path(folder, "release.json.sig").write_bytes(sig.hex().encode())
        self.refused(folder)

    def test_oversized_and_missing_metadata(self):
        folder = self.make()
        Path(folder, "release.json").write_bytes(b" " * (64 * 1024 + 1))
        self.refused(folder, fragment="larger")
        folder = self.make()
        os.unlink(Path(folder, "release.json.sig"))
        self.refused(folder, fragment="missing")
        self.refused(os.path.join(self.tmp, "no-such-folder"), fragment="not a folder")

    def test_manifest_rules(self):
        cases = {
            "channel mismatch": (lambda m: m.update(channel="pilot"), "not 'stable'"),
            "wrong schema": (lambda m: m.update(schema=2), "schema"),
            "key id not the signer": (lambda m: m.update(key_id="other"), "key id"),
            "loose version": (lambda m: m.update(version="1.2"), "x.y.z"),
            "no artifacts": (lambda m: m.update(artifacts=[]), "no artifacts"),
            "size zero": (lambda m: m["artifacts"][0].update(size=0), "size"),
            "size is a bool": (lambda m: m["artifacts"][0].update(size=True), "size"),
            "too big": (lambda m: m["artifacts"][0].update(size=releases.MAX_ARTIFACT + 1), "size"),
            "bad hash": (lambda m: m["artifacts"][0].update(sha256="ABC"), "sha256"),
            "upper-case hash": (lambda m: m["artifacts"][0].update(sha256="A" * 64), "sha256"),
            "listed twice": (lambda m: m["artifacts"].append(dict(m["artifacts"][0])), "twice"),
        }
        for label, (mutate, fragment) in cases.items():
            with self.subTest(case=label):
                self.refused(self.make(mutate=mutate), fragment=fragment)

    def test_artifact_names_must_pass_the_client_rule(self):
        for name in ("../escape", "a/b", "a\\b", "CON", "nul.txt", "release.json", "release.json.sig", "release.json.sig.hex", "current.json",
                     ".hidden", "ends.", "has space", "dou..ble", "x" * 129, "ünï"):
            with self.subTest(name=name):
                folder = self.make(name=name)
                self.refused(folder, fragment="artifact name")

    def test_the_files_must_match_the_signed_size_and_hash(self):
        folder = self.make()
        Path(folder, "Swangz-0.2.0-test").write_bytes(self.payload[:-1])  # shorter
        self.refused(folder, fragment="manifest says")
        folder = self.make()
        Path(folder, "Swangz-0.2.0-test").write_bytes(self.payload + b"x")  # longer
        self.refused(folder, fragment="manifest says")
        folder = self.make()
        Path(folder, "Swangz-0.2.0-test").write_bytes(bytes([self.payload[0] ^ 1]) + self.payload[1:])  # same size, wrong bytes
        self.refused(folder, fragment="SHA-256")
        folder = self.make()
        os.unlink(Path(folder, "Swangz-0.2.0-test"))
        self.refused(folder, fragment="missing")

    @unittest.skipIf(os.name != "posix", "needs symlinks")
    def test_a_linked_source_file_is_refused(self):
        folder = self.make()
        art = Path(folder, "Swangz-0.2.0-test")
        art.unlink()
        Path(self.tmp, "real.bin").write_bytes(self.payload)
        art.symlink_to(Path(self.tmp, "real.bin"))
        self.refused(folder, fragment="link")
        folder = self.make()
        sig = Path(folder, "release.json.sig")
        keep = sig.read_bytes()
        sig.unlink()
        Path(self.tmp, "real.sig").write_bytes(keep)
        sig.symlink_to(Path(self.tmp, "real.sig"))
        self.refused(folder, fragment="link")

    def test_versions_only_go_up_and_are_never_overwritten(self):
        self.publish("0.2.0", "stable")
        self.refused(self.make("0.2.0"), fragment="already exists")
        self.refused(self.make("0.1.9"), fragment="not higher")
        self.refused(self.make("0.1.0"), fragment="not higher")
        self.publish("0.10.0", "stable")  # numeric, not text, order
        self.refused(self.make("0.9.0"), fragment="not higher")
        # withdrawing does not free a version, and a rollback is a new higher signed version
        releases.withdraw(self.db, self.data, "stable")
        self.refused(self.make("0.10.0"), fragment="already exists")
        self.refused(self.make("0.2.0"), fragment="already exists")
        self.refused(self.make("0.5.0"), fragment="not higher")
        self.publish("0.10.1", "stable")
        self.assertEqual(releases.current(self.data, "stable"), "0.10.1")
        self.assertEqual(self.stored("stable", "0.2.0").exists(), False)  # only two kept

    def test_channels_are_separate(self):
        self.publish("0.5.0", "pilot")
        self.publish("0.2.0", "stable")  # lower than the pilot, which is fine: separate channels
        self.assertEqual((releases.current(self.data, "stable"), releases.current(self.data, "pilot")), ("0.2.0", "0.5.0"))
        with self.assertRaises(releases.ReleaseError):
            releases.publish(self.db, self.data, self.make("0.6.0", "beta"), "beta")

    def test_free_disk_floor(self):
        folder = self.make()
        real = shutil.disk_usage(self.data)
        with patch.object(releases.shutil, "disk_usage", return_value=type(real)(100, 99, 1)):
            self.refused(folder, fragment="disk space")
        releases.publish(self.db, self.data, folder, "stable")

    def test_a_crash_before_the_pointer_moves_keeps_the_previous_release_live(self):
        first, _ = self.publish("0.2.0", "stable")
        before = self.get("stable", "release.json")[2]
        folder = self.make("0.3.0")
        real_replace = os.replace

        def crash(src, dst, *a, **kw):
            if str(dst).endswith("current.json"):
                raise OSError("simulated crash")
            return real_replace(src, dst, *a, **kw)

        with patch.object(releases.os, "replace", side_effect=crash), self.assertRaises(OSError):
            releases.publish(self.db, self.data, folder, "stable")
        self.assertEqual(releases.current(self.data, "stable"), "0.2.0")
        self.assertEqual(self.get("stable", "release.json")[2], before)
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[2], self.payload)
        self.assertEqual(sorted(os.listdir(self.stored("stable"))), ["0.2.0", "current.json"])
        # a partly written temp folder from a killed publish is cleaned up by the next one
        (self.stored("stable") / ".tmp-deadbeef").mkdir()
        (self.stored("stable") / ".tmp-deadbeef" / "half").write_bytes(b"x")
        releases.publish(self.db, self.data, folder, "stable")
        self.assertEqual(releases.current(self.data, "stable"), "0.3.0")
        self.assertEqual(sorted(os.listdir(self.stored("stable"))), ["0.2.0", "0.3.0", "current.json"])

    def test_a_crash_while_copying_stores_nothing(self):
        self.publish("0.2.0", "stable")
        folder = self.make("0.3.0")
        with patch.object(releases, "_write_new", side_effect=OSError("disk full")), self.assertRaises(OSError):
            releases.publish(self.db, self.data, folder, "stable")
        self.assertEqual(releases.current(self.data, "stable"), "0.2.0")
        self.assertEqual(sorted(os.listdir(self.stored("stable"))), ["0.2.0", "current.json"])

    def test_withdraw_gives_404_and_keeps_the_files(self):
        self.publish("0.2.0", "stable")
        self.assertEqual(self.get("stable", "release.json")[0], 200)
        out = releases.withdraw(self.db, self.data, "stable")
        self.assertEqual(out["version"], "0.2.0")
        for name in ("release.json", "release.json.sig", "Swangz-0.2.0-test"):
            self.assertEqual(self.get("stable", name)[0], 404, name)
        self.assertTrue(self.stored("stable", "0.2.0", "release.json").exists())
        with self.assertRaises(releases.ReleaseError):
            releases.withdraw(self.db, self.data, "stable")

    def test_retention_keeps_exactly_the_current_and_one_previous(self):
        for v in ("0.2.0", "0.3.0", "0.4.0", "0.5.0"):
            self.publish(v, "stable")
        self.assertEqual(sorted(os.listdir(self.stored("stable"))), ["0.4.0", "0.5.0", "current.json"])
        self.assertEqual(releases.current(self.data, "stable"), "0.5.0")


class DownloadLimitTests(ReleaseBase):
    def test_a_device_may_download_artifacts_only_so_often_but_can_always_check(self):
        self.publish("0.2.0", "stable")
        for _ in range(releases.DOWNLOAD_LIMIT):
            self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 200)
        status, _, body = self.get("stable", "Swangz-0.2.0-test")
        self.assertEqual((status, json.loads(body)["code"]), (429, "slow_down"))
        for _ in range(10):  # the manifest and signature are cheap and not counted
            self.assertEqual(self.get("stable", "release.json")[0], 200)
            self.assertEqual(self.get("stable", "release.json.sig")[0], 200)
        self.assertEqual([r["outcome"] for r in self.downloads(wait=releases.DOWNLOAD_LIMIT + 1)], ["ok"] * releases.DOWNLOAD_LIMIT + ["denied"])
        # it is per device: another enrolled device is not held back
        other = self.enrol()["key"]
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test", key=other)[0], 200)


class BigFileTests(ReleaseBase):
    def test_a_150_mib_artifact_is_streamed_with_flat_memory(self):
        size = releases.MAX_ARTIFACT
        chan = self.stored("stable")
        folder = chan / "0.2.0"
        folder.mkdir(parents=True, mode=0o700)
        for d in (chan.parent, chan, folder):
            os.chmod(d, 0o700)
        manifest = {"schema": 1, "channel": "stable", "version": "0.2.0",
                    "artifacts": [{"platform": SYSTEM, "arch": ARCH, "file": "Big-0.2.0", "size": size, "sha256": "0" * 64}]}
        (folder / "release.json").write_bytes(json.dumps(manifest).encode())
        (folder / "release.json.sig").write_bytes(b"\0" * 512)
        with open(folder / "Big-0.2.0", "wb") as f:  # sparse: costs no disk and no time to make
            f.truncate(size)
        (chan / "current.json").write_text('{"version": "0.2.0"}')
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.rig.port, timeout=60)
        tracemalloc.start()
        try:
            conn.request("GET", PREFIX + "stable/Big-0.2.0", headers={"authorization": "Bearer " + self.key})
            resp = conn.getresponse()
            self.assertEqual((resp.status, int(resp.getheader("content-length"))), (200, size))
            total, other = 0, 0
            while True:
                block = resp.read(64 * 1024)
                if not block:
                    break
                total += len(block)
                other |= any(block[:8])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
            conn.close()
        self.assertEqual((total, other), (size, 0))
        self.assertLess(peak, 8 * 1024 * 1024, f"peak {peak} bytes while sending {size}")
        self.assertEqual([r["outcome"] for r in self.downloads(wait=1)], ["ok"])

    def test_a_download_the_device_abandons_is_recorded_as_interrupted(self):
        payload = b"\0" * (40 * 1024 * 1024)
        self.publish("0.2.0", "stable", payload=payload)
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.rig.port, timeout=30)
        conn.request("GET", PREFIX + "stable/Swangz-0.2.0-test", headers={"authorization": "Bearer " + self.key})
        resp = conn.getresponse()
        resp.read(1024)
        resp.close()
        conn.close()
        self.assertEqual(self.downloads(wait=1)[0]["outcome"], "interrupted")


class AuditTests(ReleaseBase):
    def test_publish_withdraw_and_pilot_changes_carry_before_and_after(self):
        self.publish("0.2.0", "stable")
        self.publish("0.3.0", "stable")
        releases.withdraw(self.db, self.data, "stable")
        self.pilot()
        self.pilot("remove")
        rows = {r["action"]: r for r in self.db.q("SELECT * FROM audit WHERE actor = 'command line'")}
        published = self.db.q("SELECT * FROM audit WHERE action = 'published a release' ORDER BY id")
        self.assertEqual([r["correlation"] for r in published], ["release:stable:0.2.0", "release:stable:0.3.0"])
        self.assertEqual(json.loads(published[1]["before_json"]), {"current": "0.2.0"})
        after = json.loads(published[1]["after_json"])
        self.assertEqual((after["current"], after["key_id"], after["artifacts"][0]["file"]), ("0.3.0", "test-only", "Swangz-0.3.0-test"))
        self.assertEqual(after["artifacts"][0]["sha256"], sha(self.payload))
        w = rows["withdrew a release"]
        self.assertEqual((w["correlation"], json.loads(w["before_json"]), json.loads(w["after_json"])),
                         ("release:stable:0.3.0", {"current": "0.3.0"}, {"current": None}))
        added, removed = rows["added to the release pilot"], rows["removed from the release pilot"]
        self.assertEqual(json.loads(added["after_json"]), {"pilot": [self.rig.person_id]})
        self.assertEqual(json.loads(removed["after_json"]), {"pilot": []})
        self.assertTrue(all(r["actor"] == "command line" and r["outcome"] == "ok" for r in self.db.q("SELECT * FROM audit WHERE correlation LIKE 'release:%'")))
        self.assertFalse(self.pilot("remove"))  # nothing changed, so nothing is recorded
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'removed from the release pilot'"), 1)

    def test_a_download_is_one_access_level_record_and_polling_records_nothing(self):
        self.publish("0.2.0", "stable")
        for _ in range(5):
            self.get("stable", "release.json")
            self.get("stable", "release.json.sig")
        self.assertEqual(self.downloads(), [])
        self.assertEqual(self.get("stable", "Swangz-0.2.0-test")[0], 200)
        (row,) = self.downloads(wait=1)
        device = self.db.one("SELECT * FROM devices LIMIT 1")
        self.assertEqual((row["actor"], row["target"], row["outcome"], row["correlation"]),
                         ("Nansubuga Grace", "stable 0.2.0", "ok", "release:stable:0.2.0"))
        self.assertEqual(row["detail"], f"Swangz-0.2.0-test; device {device['key_id']}")

    def test_no_key_and_no_file_contents_in_any_record(self):
        self.publish("0.2.0", "stable")
        self.get("stable", "Swangz-0.2.0-test")
        self.downloads(wait=1)
        self.get("stable", "release.json", key="sgw_bad_key_value")
        secret = self.key.split("_", 1)[-1][-24:]
        for row in self.db.q("SELECT * FROM audit"):
            text = json.dumps(dict(row), default=str)
            self.assertNotIn(self.key, text)
            self.assertNotIn(secret, text)
            self.assertNotIn(self.payload.decode(), text)

    def test_the_manifest_and_heartbeat_hint_follow_the_devices_channel(self):
        import gateway
        from gateway import enroll

        self.assertEqual(self.api("GET", "/device/manifest", key=self.key)[1]["client"]["latest"], enroll.CLIENT_LATEST)  # nothing published
        self.publish("0.2.0", "stable")
        self.publish("0.3.0", "pilot")
        self.assertEqual(self.api("GET", "/device/manifest", key=self.key)[1]["client"]["latest"], "0.2.0")
        self.assertEqual(self.api("POST", "/device/heartbeat", {}, key=self.key)[1]["latest_client"], "0.2.0")
        self.pilot()
        self.assertEqual(self.api("GET", "/device/manifest", key=self.key)[1]["client"]["latest"], "0.3.0")
        self.assertEqual(self.api("POST", "/device/heartbeat", {}, key=self.key)[1]["latest_client"], "0.3.0")
        releases.withdraw(self.db, self.data, "pilot")
        self.assertEqual(self.api("GET", "/device/manifest", key=self.key)[1]["client"]["latest"], enroll.CLIENT_LATEST)
        self.assertEqual(self.api("GET", "/device/manifest", key=self.key)[1]["client"]["minimum"], enroll.CLIENT_MINIMUM)
        self.assertIsNotNone(gateway.__version__)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="sgw-rel-cli-")
        self.addCleanup(shutil.rmtree, self.data, True)
        env = patch.dict(os.environ, {"GATEWAY_DATA": self.data, "GATEWAY_ENV_FILE": os.path.join(self.data, "no.env")})
        env.start()
        self.addCleanup(env.stop)
        pins = patch.dict(release_keys.KEYS, TEST_PINS, clear=True)
        pins.start()
        self.addCleanup(pins.stop)

    def run_cli(self, *argv):
        from gateway.__main__ import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(list(argv))
        return out.getvalue()

    def folder(self, version, channel):
        payload = b"cli synthetic"
        folder = tempfile.mkdtemp(dir=self.data)
        raw = json.dumps({"schema": 1, "key_id": "test-only", "channel": channel, "version": version, "min_server": "1.0.0",
                          "released": NOW - 1, "expires": NOW + 60,
                          "artifacts": [{"platform": SYSTEM, "arch": ARCH, "file": f"S-{version}", "size": len(payload), "sha256": sha(payload)}]}).encode()
        Path(folder, "release.json").write_bytes(raw)
        Path(folder, "release.json.sig").write_bytes(sign(raw))
        Path(folder, f"S-{version}").write_bytes(payload)
        return folder

    def test_publish_withdraw_and_pilot_commands(self):
        from gateway.db import DB

        self.run_cli("add-person", "Ada", "--email", "ada@swangzavenue.com")
        self.assertIn("added to the pilot list", self.run_cli("release-pilot", "add", "1"))
        self.assertIn("no change", self.run_cli("release-pilot", "add", "1"))
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("release-pilot", "add", "99")
        self.assertIn("no such person", str(caught.exception))
        self.assertIn("published stable 0.2.0", self.run_cli("release-publish", self.folder("0.2.0", "stable"), "--channel", "stable"))
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("release-publish", self.folder("0.2.0", "stable"), "--channel", "stable")
        self.assertIn("could not publish", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:  # the manifest says stable
            self.run_cli("release-publish", self.folder("0.3.0", "stable"), "--channel", "pilot")
        self.assertIn("not 'pilot'", str(caught.exception))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_cli("release-publish", self.folder("0.3.0", "stable"), "--channel", "beta")
        self.assertIn("withdrew stable 0.2.0", self.run_cli("release-withdraw", "--channel", "stable"))
        with self.assertRaises(SystemExit):
            self.run_cli("release-withdraw", "--channel", "stable")
        db = DB(os.path.join(self.data, "gateway.db"))
        self.addCleanup(db.close)
        self.assertEqual([r["action"] for r in db.q("SELECT action FROM audit WHERE correlation LIKE 'release:%' ORDER BY id")],
                         ["added to the release pilot", "published a release", "withdrew a release"])
        self.assertEqual(releases.current(self.data, "stable"), None)

    def test_there_is_no_http_way_to_publish(self):
        import gateway.__main__ as cli

        text = Path(cli.__file__).read_text()
        self.assertIn("release-publish", text)
        for method, rx, fn, *_ in staff.ROUTES:
            if "release" in rx.pattern:
                self.assertEqual(method, "GET")


class NoSigningInTheGatewayTests(unittest.TestCase):
    def test_no_private_key_or_signing_code_under_gateway(self):
        patterns = [str(D), str(N), "test_release_rsa4096", r"-----BEGIN (RSA |EC |ENCRYPTED )?PRIVATE KEY-----", r"\bdef sign\w*\(",
                    r"\bimport rsa\b", r"\bcryptography\b", r"\bfrom Crypto\b", r"\bpow\("]
        hits = []
        for path in (ROOT / "gateway").rglob("*"):
            if not path.is_file() or path.suffix in (".woff", ".woff2", ".webp", ".png", ".db", ".pyc"):
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            hits += [(str(path.relative_to(ROOT)), p) for p in patterns if re.search(p, text) and not (p.endswith("pow\\(") and path.suffix != ".py")]
        self.assertEqual(hits, [])
        self.assertEqual(release_keys.KEYS, {})  # nothing pinned and no test key shipped


if __name__ == "__main__":
    unittest.main()
