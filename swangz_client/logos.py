"""Tool logos for the app window: the same pictures the web staff app shows (the Hub's public /icons/<tool>).

Fetched once from the Hub this device signed in to (never anywhere else), checked, and kept in the app's folder as
PNG, because Tk draws PNG and GIF only. A Windows icon (.ico) is converted here: its PNG entry when it has one,
otherwise its bitmap is decoded and written out as PNG. Anything else (SVG, a broken file, a 404) gets no logo and
the window draws the tool's monogram on its brand colour instead. Standard library only.
"""

import os
import re
import struct
import time
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 512 * 1024   # the Hub caps logos well under this
MAX_SIDE = 512
FRESH_FOR = 7 * 86400    # look again once a week
MISS_FOR = 86400         # a tool with no logo is not asked for again for a day
TOOL_ID = re.compile(r"[a-z0-9-]{1,80}")


def png_size(data):
    """(width, height) of a PNG, or None if it isn't one."""
    if len(data) < 24 or not data.startswith(PNG_SIG) or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def write_png(width, height, rgba):
    """Encode width x height RGBA bytes (top row first) as a PNG."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    return (PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _dib_to_rgba(dib):
    """A Windows icon's bitmap entry (BITMAPINFOHEADER + pixels + AND mask) to (width, height, RGBA)."""
    if len(dib) < 40:
        raise ValueError("short bitmap")
    size, width, height2, planes, bits = struct.unpack("<IiiHH", dib[:16])
    compression = struct.unpack("<I", dib[16:20])[0]
    if size < 40 or compression not in (0, 3) or bits not in (1, 4, 8, 24, 32):
        raise ValueError("unsupported bitmap")
    height = abs(height2) // 2  # the stored height counts the AND mask too
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        raise ValueError("bad size")
    colours = struct.unpack("<I", dib[32:36])[0] or (1 << bits if bits <= 8 else 0)
    pos = size + (12 if compression == 3 and size == 40 else 0)
    palette = []
    for i in range(colours if bits <= 8 else 0):
        b, g, r = dib[pos + i * 4:pos + i * 4 + 3]
        palette.append((r, g, b))
    pos += (colours if bits <= 8 else 0) * 4
    stride = ((width * bits + 31) // 32) * 4
    mask_stride = ((width + 31) // 32) * 4
    pixels = dib[pos:pos + stride * height]
    mask = dib[pos + stride * height:pos + stride * height + mask_stride * height]
    if len(pixels) < stride * height:
        raise ValueError("short pixels")
    out = bytearray(width * height * 4)
    any_alpha = bits == 32 and any(pixels[i] for i in range(3, len(pixels), 4))
    for row in range(height):
        src = height - 1 - row if height2 > 0 else row  # bitmaps are stored bottom row first
        line = pixels[src * stride:(src + 1) * stride]
        mline = mask[src * mask_stride:(src + 1) * mask_stride] if mask else b""
        for x in range(width):
            if bits == 32:
                b, g, r, a = line[x * 4:x * 4 + 4]
                if not any_alpha:
                    a = 255
            elif bits == 24:
                b, g, r = line[x * 3:x * 3 + 3]
                a = 255
            else:
                per = 8 // bits
                byte = line[x // per]
                index = (byte >> (8 - bits * (x % per + 1))) & ((1 << bits) - 1)
                r, g, b = palette[index] if index < len(palette) else (0, 0, 0)
                a = 255
            if bits != 32 or not any_alpha:
                if mline and (mline[x // 8] >> (7 - x % 8)) & 1:
                    a = 0
            o = (row * width + x) * 4
            out[o:o + 4] = bytes((r, g, b, a))
    return width, height, bytes(out)


def ico_to_png(data):
    """The largest picture in a .ico as PNG bytes, or None."""
    if len(data) < 6:
        return None
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or kind != 1 or not 0 < count <= 64:
        return None
    entries = []
    for i in range(count):
        e = data[6 + i * 16:22 + i * 16]
        if len(e) < 16:
            return None
        w, h, _, _, _, bpp, length, offset = struct.unpack("<BBBBHHII", e)
        entries.append(((w or 256) * (h or 256), bpp, length, offset))
    for _, _, length, offset in sorted(entries, reverse=True):
        blob = data[offset:offset + length]
        if len(blob) != length or not blob:
            continue
        if blob.startswith(PNG_SIG):
            size = png_size(blob)
            if size and max(size) <= MAX_SIDE:
                return blob
            continue
        try:
            return write_png(*_dib_to_rgba(blob))
        except (ValueError, struct.error, IndexError):
            continue
    return None


def as_png(data):
    """What the Hub served, as PNG bytes Tk can draw, or None (SVG, unknown, too big, broken)."""
    if not data or len(data) > MAX_BYTES:
        return None
    if data.startswith(PNG_SIG):
        size = png_size(data)
        return data if size and 0 < size[0] <= MAX_SIDE and 0 < size[1] <= MAX_SIDE else None
    if data[:4] == b"\x00\x00\x01\x00":
        return ico_to_png(data)
    return None


class Logos:
    """The logo cache in the app's folder: <data>/logos/<tool>.png, plus a .none marker for tools without one."""

    def __init__(self, data_dir):
        self.folder = Path(data_dir) / "logos"

    def path(self, tool_id):
        """The cached PNG for `tool_id`, or None."""
        if not TOOL_ID.fullmatch(tool_id or ""):
            return None
        p = self.folder / f"{tool_id}.png"
        return p if p.is_file() else None

    def due(self, tool_id, now=None):
        if not TOOL_ID.fullmatch(tool_id or ""):
            return False
        now = time.time() if now is None else now
        for name, age in ((f"{tool_id}.png", FRESH_FOR), (f"{tool_id}.none", MISS_FOR)):
            try:
                if now - (self.folder / name).stat().st_mtime < age:
                    return False
            except OSError:
                pass
        return True

    def refresh(self, tool_ids, fetch, now=None):
        """Fetch the logos that are due through `fetch(tool_id) -> bytes | None`. Returns how many changed. Never raises
        for one tool's failure: a logo is decoration."""
        changed = 0
        for tool_id in tool_ids:
            if not self.due(tool_id, now):
                continue
            try:
                png = as_png(fetch(tool_id))
            except Exception:  # noqa: BLE001 — offline, refused, anything: draw the monogram
                continue  # not marked: try again next time
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                target = self.folder / (f"{tool_id}.png" if png else f"{tool_id}.none")
                tmp = target.with_suffix(".tmp")
                tmp.write_bytes(png or b"")
                os.replace(tmp, target)
                if png:
                    try:
                        (self.folder / f"{tool_id}.none").unlink()
                    except OSError:
                        pass
                    changed += 1
            except OSError:
                continue
        return changed
