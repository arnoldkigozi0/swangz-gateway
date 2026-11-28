"""Tool logos for the app window (swangz_client/logos.py): what the Hub serves becomes a PNG Tk can draw, or nothing."""

import os
import struct
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

from swangz_client import core, logos


def png(w=2, h=2, rgba=b"\xff\x00\x00\xff"):
    return logos.write_png(w, h, rgba * (w * h))


def ico(entries):
    """A .ico holding `entries` (each raw bytes, with its nominal width)."""
    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    table, blobs = b"", b""
    for width, blob in entries:
        table += struct.pack("<BBBBHHII", width % 256, width % 256, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    return head + table + blobs


def dib32(w, h, pixel=b"\x00\x80\xff\xff"):
    """A 32-bit BITMAPINFOHEADER icon bitmap: BGRA pixels, bottom row first, then an all-clear AND mask."""
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)
    return header + pixel * (w * h) + mask


def decode(data):
    """(width, height, first pixel RGBA) of a PNG this module wrote."""
    w, h = logos.png_size(data)
    idat = b"".join(data[i + 8:i + 8 + struct.unpack(">I", data[i:i + 4])[0]]
                    for i in range(8, len(data)) if data[i + 4:i + 8] == b"IDAT")
    raw = zlib.decompress(idat)
    return w, h, raw[1:5]


class ConvertTests(unittest.TestCase):
    def test_a_png_passes_through_and_a_huge_one_does_not(self):
        data = png()
        self.assertEqual(logos.as_png(data), data)
        self.assertIsNone(logos.as_png(logos.write_png(600, 1, b"\x00" * 2400)))  # over 512 px across
        self.assertIsNone(logos.as_png(b"x" * (logos.MAX_BYTES + 1)))

    def test_svg_text_and_nothing_get_no_logo(self):
        for data in (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"no logo", b"", None):
            self.assertIsNone(logos.as_png(data))

    def test_an_ico_with_a_png_inside_gives_that_png(self):
        inner = png(4, 4)
        self.assertEqual(logos.as_png(ico([(4, inner)])), inner)

    def test_an_ico_bitmap_is_decoded_to_png_with_its_colours(self):
        out = logos.as_png(ico([(16, dib32(16, 16))]))
        w, h, first = decode(out)
        self.assertEqual((w, h), (16, 16))
        self.assertEqual(first, b"\xff\x80\x00\xff")  # BGRA 00 80 ff ff -> RGBA ff 80 00 ff

    def test_the_largest_picture_in_the_ico_wins(self):
        out = logos.as_png(ico([(16, dib32(16, 16)), (32, dib32(32, 32))]))
        self.assertEqual(logos.png_size(out), (32, 32))

    def test_a_broken_ico_gets_no_logo(self):
        for data in (b"\x00\x00\x01\x00", b"\x00\x00\x01\x00\x01\x00" + b"\x00" * 16, ico([(16, b"\x28" + b"\x00" * 10)])):
            self.assertIsNone(logos.as_png(data))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = logos.Logos(self.tmp.name)

    def test_fetched_once_kept_and_not_asked_again_until_due(self):
        asked = []

        def fetch(tool):
            asked.append(tool)
            return png() if tool == "canva" else b"no logo"

        self.assertEqual(self.cache.refresh(["canva", "udio"], fetch), 1)
        self.assertEqual(self.cache.path("canva").read_bytes()[:8], logos.PNG_SIG)
        self.assertIsNone(self.cache.path("udio"))  # no logo: the monogram is drawn
        self.cache.refresh(["canva", "udio"], fetch)
        self.assertEqual(asked, ["canva", "udio"])  # neither is asked for again yet
        later = time.time() + logos.MISS_FOR + 60
        self.cache.refresh(["canva", "udio"], fetch, now=later)
        self.assertEqual(asked, ["canva", "udio", "udio"])  # a missing logo is asked for again after a day

    def test_a_failed_fetch_is_not_remembered_and_odd_ids_are_never_used(self):
        def fetch(tool):
            raise core.ApiFailure(0, "offline", "no network")

        self.assertEqual(self.cache.refresh(["canva"], fetch), 0)
        self.assertTrue(self.cache.due("canva"))
        for odd in ("../x", "A", "", "a" * 81):
            self.assertFalse(self.cache.due(odd))
            self.assertIsNone(self.cache.path(odd))


class ClientTests(unittest.TestCase):
    def test_logos_come_from_the_signed_in_hub_without_the_device_key(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = core.Client(paths=core.Paths(home=tmp.name, data=os.path.join(tmp.name, "data")))
        client.store.device = lambda: {"server": "https://hub.example"}
        client.store.manifest = lambda: {"tools": [{"id": "canva", "name": "Canva"}, {"id": "udio", "name": "Udio"}]}
        seen = []

        def opened(api, req, limit):
            seen.append((req.full_url, req.get_header("Authorization")))
            return (200, png(), {}) if req.full_url.endswith("/canva") else (404, b"no logo", {})

        with mock.patch.object(core.Api, "_open", opened):
            self.assertEqual(client.refresh_logos(), 1)
        self.assertEqual(seen, [("https://hub.example/icons/canva", None), ("https://hub.example/icons/udio", None)])
        self.assertIsNotNone(client.logos.path("canva"))

    def test_one_unreachable_hub_stops_the_round(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = core.Client(paths=core.Paths(home=tmp.name, data=os.path.join(tmp.name, "data")))
        client.store.device = lambda: {"server": "https://hub.example"}
        client.store.manifest = lambda: {"tools": [{"id": f"t{i}", "name": "T"} for i in range(5)]}
        calls = []

        def opened(api, req, limit):
            calls.append(req.full_url)
            raise core.ApiFailure(0, "offline", "no network")

        with mock.patch.object(core.Api, "_open", opened):
            self.assertEqual(client.refresh_logos(), 0)
        self.assertEqual(len(calls), 1)

    def test_tools_carry_how_you_sign_in_a_description_and_a_checked_colour(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        client = core.Client(paths=core.Paths(home=tmp.name, data=os.path.join(tmp.name, "data")))
        client.store.manifest = lambda: {"tools": [
            {"id": "canva", "name": "Canva", "kind": "site", "category": "Design", "signin": "sso",
             "description": "Design anything.", "color": "#00C4CC"},
            {"id": "odd", "name": "Odd", "kind": "site", "signin": "magic", "color": "red; x", "description": 5}]}
        tools = {t["id"]: t for t in client.tools()}
        self.assertEqual(tools["canva"], {"id": "canva", "name": "Canva", "kind": "site", "category": "Design",
                                          "signin": "sso", "description": "Design anything.", "color": "#00C4CC"})
        self.assertEqual(tools["odd"], {"id": "odd", "name": "Odd", "kind": "site", "category": ""})


if __name__ == "__main__":
    unittest.main()
