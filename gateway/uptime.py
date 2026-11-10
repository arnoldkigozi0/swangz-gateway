"""The uptime check: ask a running gateway's /healthz whether it is up, and say so with an exit code.

`python3 -m gateway health-check` is what `deploy/swangz-gateway-health.timer` runs every five minutes on the server.
It reads nothing but that one address, opens no database and changes nothing. A check on the same machine cannot
notice the machine itself being off or unreachable from outside: that still needs a monitor somewhere else pointed at
https://<domain>/healthz (docs/HUB-DELIVERY.md).
"""

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

TIMEOUT = 5
MAX_BYTES = 4096


def default_url(env):
    host = env.get("GATEWAY_HOST") or "127.0.0.1"
    host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    return f"http://{host}:{int(env.get('GATEWAY_PORT') or env.get('PORT') or 8787)}/healthz"


def check(url, expect_commit="", timeout=TIMEOUT):
    """(ok, message). Up means: HTTP 200, a JSON object with "ok": true and, when asked, the expected commit."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False, "the address must start with http:// or https://"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "swangz-health-check"}),
                                    timeout=timeout) as response:
            status, raw = response.status, response.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        e.close()
        return False, f"down: {url} answered {e.code}"
    except (OSError, ValueError) as e:
        return False, f"down: {url} did not answer ({getattr(e, 'reason', e)})"
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
        return False, f"down: {url} answered {status} without \"ok\": true"
    commit = str(body.get("commit") or "")
    if expect_commit and not (commit and (commit.startswith(expect_commit) or expect_commit.startswith(commit))):
        return False, f"wrong build: running {commit or 'an unrecorded commit'}, expected {expect_commit}"
    return True, (f"up: version {body.get('version') or '?'}, commit {commit or 'not recorded'},"
                  f" running {int(body.get('uptime_seconds') or 0)} seconds")


def run(args, env, write=print):
    ok, message = check(args.url or default_url(env), args.expect_commit or "", args.timeout)
    write(message)
    return 0 if ok else 1
