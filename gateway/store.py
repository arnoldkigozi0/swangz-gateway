"""The record of every request, kept so it can be pulled back later.

Coding agents resend the whole conversation on every turn, so storing each request body whole
would grow with the square of the conversation length. Instead each message is stored once, by
the hash of its content, and a request is a short list of hashes. A 200-turn agent session costs
roughly one copy of the conversation, not two hundred.

What is stored is the meaning of the request, not its exact bytes: keys are sorted and prompt
cache markers (`cache_control`, which tools move from turn to turn) are dropped before hashing.
"""

import hashlib
import json
import time
import zlib

MAX_STORED_RAW = 16 * 1024 * 1024


def _strip_cache_markers(obj):
    if isinstance(obj, dict):
        return {k: _strip_cache_markers(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_strip_cache_markers(v) for v in obj]
    return obj


def canonical(obj):
    return json.dumps(_strip_cache_markers(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def put_blob(db, data):
    digest = hashlib.sha256(data).hexdigest()
    if digest in db.blob_cache:
        return digest
    db.x("INSERT OR IGNORE INTO blobs(hash, data, size) VALUES(?, ?, ?)", (digest, zlib.compress(data, 6), len(data)))
    if len(db.blob_cache) > 200_000:
        db.blob_cache.clear()
    db.blob_cache.add(digest)
    return digest


def get_blob(db, digest):
    row = db.one("SELECT data FROM blobs WHERE hash=?", (digest,))
    return zlib.decompress(row["data"]) if row else None


def store_request_body(db, body_json, raw, field):
    """-> (head_hash, item_hashes_json). field names the conversation list, or None."""
    if body_json is None:
        if not raw:
            return None, None
        return put_blob(db, raw[:MAX_STORED_RAW]), None
    if field:
        head = {k: v for k, v in body_json.items() if k != field}
        items = [put_blob(db, canonical(item)) for item in body_json.get(field) or []]
        return put_blob(db, canonical(head)), json.dumps(items)
    return put_blob(db, canonical(body_json)), None


def load_request_body(db, row):
    """Rebuild the request as sent (minus cache markers). -> (dict | str | None)"""
    if not row.get("req_head"):
        return None
    head = get_blob(db, row["req_head"])
    if head is None:
        return None
    try:
        body = json.loads(head)
    except ValueError:
        return head.decode("utf-8", "replace")
    if row.get("req_list_field") and row.get("req_items"):
        items = []
        for digest in json.loads(row["req_items"]):
            data = get_blob(db, digest)
            items.append(json.loads(data) if data is not None else {"missing": digest})
        body[row["req_list_field"]] = items
    return body


def store_response(db, final_obj, raw):
    """-> (hash, format). The rebuilt final response when we could read it, else the raw bytes."""
    if final_obj is not None:
        return put_blob(db, canonical(final_obj)), "json"
    if raw:
        return put_blob(db, raw[:MAX_STORED_RAW]), "raw"
    return None, None


def load_response_bytes(db, row):
    """The stored response exactly as received — audio and other binary results."""
    return get_blob(db, row["resp_blob"]) if row.get("resp_blob") else None


def load_response(db, row):
    if not row.get("resp_blob"):
        return None
    data = get_blob(db, row["resp_blob"])
    if data is None:
        return None
    if row.get("resp_format") == "json":
        try:
            return json.loads(data)
        except ValueError:
            pass
    return data.decode("utf-8", "replace")


CATEGORIES = {
    # setting: (what it removes, the SQL that removes it)
    "retention_bodies_days": ("stored request and response bodies (the record itself stays)",
                              "UPDATE requests SET req_head = NULL, req_items = NULL, resp_blob = NULL, resp_format = NULL"
                              " WHERE ts < ? AND (req_head IS NOT NULL OR resp_blob IS NOT NULL)"),
    "retention_site_days": ("website visits", "DELETE FROM site_usage WHERE started < ?"),
    "retention_launch_days": ("tools opened from the portal", "DELETE FROM launches WHERE ts < ?"),
    "retention_audit_days": ("audit log entries", "DELETE FROM audit WHERE ts < ?"),
}
AUDIT_MIN_DAYS = 365


def purge_categories(db, days_by_setting, now=None):
    """Apply each category's own retention (0 = keep forever). -> {setting: rows affected}. The audit log is
    never trimmed to less than a year, whatever the setting says."""
    now = now or time.time()
    out = {}
    for key, (_, sql) in CATEGORIES.items():
        days = int(days_by_setting.get(key) or 0)
        if key == "retention_audit_days" and days:
            days = max(days, AUDIT_MIN_DAYS)
        if days > 0:
            n = db.x(sql, (now - days * 86400,)).rowcount
            if n:
                out[key] = n
    return out


def purge(db, retention_days, now=None):
    """Delete request records older than the retention window, then any bodies nothing points at."""
    now = now or time.time()
    removed = 0
    if retention_days and retention_days > 0:
        cutoff = now - retention_days * 86400
        removed = db.x("DELETE FROM requests WHERE ts < ?", (cutoff,)).rowcount
    db.blob_cache.clear()
    with db.tx():
        db.x("CREATE TEMP TABLE IF NOT EXISTS live_blobs(hash TEXT PRIMARY KEY)")
        db.x("DELETE FROM live_blobs")
        for row in db.q("SELECT req_head, req_items, resp_blob FROM requests"):
            refs = [row["req_head"], row["resp_blob"]]
            if row["req_items"]:
                refs += json.loads(row["req_items"])
            for ref in refs:
                if ref:
                    db.x("INSERT OR IGNORE INTO live_blobs(hash) VALUES(?)", (ref,))
        orphans = db.x("DELETE FROM blobs WHERE hash NOT IN (SELECT hash FROM live_blobs)").rowcount
        db.x("DELETE FROM live_blobs")
    db.x("DELETE FROM admin_sessions WHERE expires < ?", (now,))
    return removed, orphans
