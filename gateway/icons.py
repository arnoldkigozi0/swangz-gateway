"""Tool logos for the catalog tiles.

The gateway fetches each tool's own icon once from its website (the apple-touch-icon or favicon the
site publishes), keeps it in the database and serves it from /icons/<tool id> — so a staff browser
never contacts a tool's site just to draw a tile. An admin can also upload a logo. When no logo can
be found the apps draw a monogram in the tool's brand colour instead.
"""

import base64
import ipaddress
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_BYTES = 300 * 1024      # a logo bigger than this is not a logo
HTML_BYTES = 256 * 1024     # the <head> is all we need from a home page
RETRY_AFTER = 7 * 86400     # a site that refused us is asked again a week later
TIMEOUT = 8
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 "
      "SwangzAI-logo-fetch")


def sniff(data):
    """The real image type from the first bytes — never trust the server's Content-Type."""
    if not data:
        return None
    head = data[:256]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    text = head.lstrip().lower()
    if text.startswith(b"<svg") or (text.startswith(b"<?xml") and b"<svg" in data[:2048].lower()):
        return "image/svg+xml"
    return None


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower().split()
        if a.get("href") and ("icon" in rel or "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel):
            self.found.append((rel, a["href"], a.get("sizes", ""), a.get("type", "").lower()))


def _size(sizes):
    best = 0
    for part in sizes.lower().split():
        w, _, _ = part.partition("x")
        if w.isdigit():
            best = max(best, int(w))
    return best


def candidates(page_url, html_text):
    """Icon addresses a page declares, best first: apple-touch-icon, then the largest raster icon,
    then an SVG icon, then /favicon.ico at the site root."""
    p = _Links()
    try:
        p.feed(html_text)
    except Exception:
        pass
    ranked = []
    for rel, href, sizes, ctype in p.found:
        url = urllib.parse.urljoin(page_url, href.strip())
        if not url.startswith(("https://", "http://")):
            continue
        svg = ctype == "image/svg+xml" or url.lower().split("?")[0].endswith(".svg")
        if any(r.startswith("apple-touch-icon") for r in rel):
            score = 3000 + (_size(sizes) or 180)
        elif svg:
            score = 1000
        else:
            score = 2000 + (_size(sizes) or 16)
        ranked.append((score, url))
    ranked.sort(key=lambda x: -x[0])
    out = []
    for _, url in ranked:
        if url not in out:
            out.append(url)
    root = urllib.parse.urlsplit(page_url)
    fav = f"{root.scheme}://{root.netloc}/favicon.ico"
    if fav not in out:
        out.append(fav)
    return out


def _public(host):
    """Only fetch from the public internet — never from this machine or the office network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def _get(url, limit):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or not _public(parts.hostname):
        return None, None
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,image/*;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            final = resp.geturl()
            host = urllib.parse.urlsplit(final).hostname
            if not host or not _public(host):
                return None, None
            return final, resp.read(limit + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None, None


def fetch(tool):
    """-> (ctype, bytes, source url) for this tool's logo, or None."""
    url = (tool.get("url") or "").strip()
    if not url.startswith(("https://", "http://")):
        return None
    final, page = _get(url, HTML_BYTES)
    tried = candidates(final or url, page.decode("utf-8", "replace") if page else "")
    for icon_url in tried[:5]:
        _, data = _get(icon_url, MAX_BYTES)
        if not data or len(data) > MAX_BYTES:
            continue
        ctype = sniff(data)
        if ctype:
            return ctype, data, icon_url
    return None


def save(db, tool_id, result, source=""):
    if result:
        ctype, data, source = result
        db.x("INSERT OR REPLACE INTO tool_icons(tool_id, data, ctype, source, fetched, ok) VALUES(?,?,?,?,?,1)",
             (tool_id, data, ctype, source, time.time()))
    else:
        db.x("INSERT OR REPLACE INTO tool_icons(tool_id, data, ctype, source, fetched, ok) VALUES(?,NULL,'',?,?,0)",
             (tool_id, source, time.time()))


def from_data_url(text):
    """An uploaded logo, as a data: URL -> (ctype, bytes). Raises ValueError if it isn't a small image."""
    text = str(text or "")
    if not text.startswith("data:") or ";base64," not in text[:100]:
        raise ValueError("send the logo as a data: URL")
    try:
        data = base64.b64decode(text.split(";base64,", 1)[1], validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("that logo isn't valid base64")
    if len(data) > MAX_BYTES:
        raise ValueError("keep the logo under 300 KB")
    ctype = sniff(data)
    if not ctype:
        raise ValueError("use a PNG, JPEG, WebP, GIF, ICO or SVG image")
    return ctype, data


def missing(db):
    cutoff = time.time() - RETRY_AFTER
    return db.q("SELECT t.* FROM tools t LEFT JOIN tool_icons i ON i.tool_id = t.id"
                " WHERE t.url != '' AND (i.tool_id IS NULL OR (i.ok = 0 AND i.fetched < ?))", (cutoff,))


def refresh_missing(db, log=None):
    done = 0
    for tool in missing(db):
        save(db, tool["id"], fetch(tool), tool["url"])
        done += 1
        time.sleep(0.2)
    if log and done:
        have = db.scalar("SELECT COUNT(*) FROM tool_icons WHERE ok = 1") or 0
        log(f"logos: checked {done} tool(s); {have} logo(s) on file")
    return done


def enabled():
    return os.environ.get("GATEWAY_FETCH_ICONS", "1") not in ("0", "false", "no")


def fetch_soon(db, tool_id, log=None):
    """Fetch one tool's logo in the background (after an admin adds or edits it)."""
    if not enabled():
        return

    def run():
        tool = db.one("SELECT * FROM tools WHERE id = ?", (tool_id,))
        if tool:
            try:
                save(db, tool_id, fetch(tool), tool["url"])
            except Exception as exc:
                if log:
                    log(f"logo fetch for {tool_id} failed: {exc!r}")

    threading.Thread(target=run, name="logo-" + tool_id, daemon=True).start()


def start(db, log=None):
    if not enabled():
        return

    def run():
        try:
            refresh_missing(db, log)
        except Exception as exc:
            if log:
                log(f"logo fetch failed: {exc!r}")

    threading.Thread(target=run, name="logos", daemon=True).start()
