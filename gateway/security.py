"""Gateway keys for staff, passwords and sessions for the people who watch.

A gateway key looks like sgw_<12 hex id>_<secret>. Only a SHA-256 of the secret is stored, so the
database alone cannot be used to make requests; the full key is shown once, when it is issued.
"""

import hashlib
import hmac
import secrets
import threading
import time

KEY_PREFIX = "sgw"


def new_key():
    """-> (key_id, full_key, secret_hash, hint)"""
    key_id = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    full = f"{KEY_PREFIX}_{key_id}_{secret}"
    return key_id, full, sha256(secret), f"{KEY_PREFIX}_{key_id}_…{secret[-4:]}"


def split_key(token):
    """-> (key_id, secret) or (None, None) when the token is not shaped like a gateway key."""
    if not token or not token.startswith(KEY_PREFIX + "_"):
        return None, None
    parts = token.split("_", 2)
    if len(parts) != 3 or len(parts[1]) != 12 or not parts[2]:
        return None, None
    try:
        int(parts[1], 16)
    except ValueError:
        return None, None
    return parts[1], parts[2]


def secret_matches(secret, stored_hash):
    return hmac.compare_digest(sha256(secret), stored_hash)


def client_token(headers):
    """The gateway key, however the person's SDK sends it: x-api-key (Anthropic), xi-api-key
    (ElevenLabs), hf-api-key or "Authorization: Key …" (Higgsfield, fal) or "Authorization: Bearer"."""
    for name in ("x-api-key", "xi-api-key", "hf-api-key"):
        token = (headers.get(name) or "").strip()
        if token:
            return token
    auth = (headers.get("authorization") or "").strip()
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    if auth[:4].lower() == "key ":
        return auth[4:].strip().split(":", 1)[0]  # Higgsfield SDKs insist on KEY_ID:KEY_SECRET
    return ""


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def hash_password(password, iterations):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def check_password(password, stored):
    try:
        scheme, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def new_session_token():
    return secrets.token_urlsafe(32)


class LoginThrottle:
    """At most `limit` failed sign-ins per IP in `window` seconds."""

    def __init__(self, limit=8, window=600):
        self.limit = limit
        self.window = window
        self.failures = {}
        self.lock = threading.Lock()

    def blocked(self, ip):
        now = time.time()
        with self.lock:
            recent = [t for t in self.failures.get(ip, []) if now - t < self.window]
            self.failures[ip] = recent
            return len(recent) >= self.limit

    def fail(self, ip):
        with self.lock:
            self.failures.setdefault(ip, []).append(time.time())

    def clear(self, ip):
        with self.lock:
            self.failures.pop(ip, None)
