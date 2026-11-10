"""Go-live configuration check: reads the environment only, never the network or the database.

`python3 -m gateway preflight` prints one line per finding and exits non-zero when anything would stop
people signing in at the first-party address. Secrets are never printed, only whether they are set.
"""

import re
from urllib.parse import urlsplit

CALLBACK = "/auth/google/callback"
ON = ("1", "true", "yes")
LOCAL = re.compile(r"localhost$|127\.|\[?::1\]?$|0\.0\.0\.0$")
BORROWED = (".netlify.app", ".trycloudflare.com", ".up.railway.app", ".ngrok.io", ".ngrok-free.app")


def _origin(value):
    """(scheme, host, problem) for an address that must be a bare origin like https://ai.example.com."""
    try:
        u = urlsplit(value)
        u.port  # raises on a port that is not a number
    except ValueError:
        return "", "", "is not a valid address"
    if u.scheme not in ("http", "https") or not u.hostname:
        return "", "", "must start with https:// and name a host"
    if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?|\[[0-9a-f:]+\]", u.netloc.rpartition("@")[2].lower().split(":")[0] if "[" not in u.netloc else "[" + u.hostname.lower() + "]"):
        return u.scheme, u.hostname, "must name one exact host (no wildcard)"
    if u.username or u.password:
        return u.scheme, u.hostname, "must not contain a user name or password"
    if u.path not in ("", "/") or u.query or u.fragment:
        return u.scheme, u.hostname, "must be the address only, with no path, query or #"
    return u.scheme, u.hostname.lower(), ""


def check(env):
    """Return [(level, name, message)], level one of 'ok', 'warn', 'fail'."""
    out = []
    add = lambda level, name, message: out.append((level, name, message))
    get = lambda k: (env.get(k) or "").strip()
    web, public = get("GATEWAY_WEB_URL").rstrip("/"), get("GATEWAY_PUBLIC_URL").rstrip("/")

    hosts = {}
    for name, value in (("GATEWAY_WEB_URL", web), ("GATEWAY_PUBLIC_URL", public)):
        if not value:
            add("fail", name, "is not set; production needs the verified first-party https address")
            continue
        scheme, host, problem = _origin(value)
        if problem:
            add("fail", name, problem)
        elif scheme != "https":
            add("fail", name, "must be https")
        elif LOCAL.match(host):
            add("fail", name, "points at this computer, not an address people can open")
        elif host.endswith(BORROWED):
            add("warn", name, f"{host} is a hosting provider's address, not a first-party one")
            hosts[name] = host
        else:
            add("ok", name, value)
            hosts[name] = host
    if len(hosts) == 2 and hosts["GATEWAY_WEB_URL"] != hosts["GATEWAY_PUBLIC_URL"]:
        cors = {o.strip().rstrip("/").lower() for o in get("GATEWAY_CORS_ORIGINS").split(",") if o.strip()}
        level = "ok" if web.lower() in cors else "warn"
        add(level, "GATEWAY_CORS_ORIGINS", "the web and gateway addresses differ; " + (
            "the web address is allowed" if level == "ok" else "the web address must be listed unless it proxies every request"))
    for origin in [o.strip() for o in get("GATEWAY_CORS_ORIGINS").split(",") if o.strip()]:
        scheme, _, problem = _origin(origin)
        if problem or scheme != "https":
            add("fail", "GATEWAY_CORS_ORIGINS", f"{origin!r} must be one exact https address (no wildcard, no path)")

    # Whoever signs in, by password or Google: the account rule is this one domain (plus the approved exceptions).
    domain = get("GATEWAY_COMPANY_DOMAIN").strip().lower().lstrip("@")
    if domain and domain != "swangzavenue.com":
        add("fail", "GATEWAY_COMPANY_DOMAIN", "must be swangzavenue.com (or unset); another domain would let its accounts sign in")
    else:
        add("ok", "GATEWAY_COMPANY_DOMAIN", "swangzavenue.com" + ("" if domain else " (default)"))

    cid, secret, fixed = get("GOOGLE_CLIENT_ID"), get("GOOGLE_CLIENT_SECRET"), get("GOOGLE_REDIRECT_URI")
    if bool(cid) != bool(secret):
        add("fail", "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET", "set both or neither; with one missing the Google button is hidden")
    elif not cid:
        add("warn", "Google sign-in", "is off (no client id and secret); people sign in with a password or link only")
    else:
        if not cid.endswith(".apps.googleusercontent.com"):
            add("warn", "GOOGLE_CLIENT_ID", "does not look like a Google web client id (….apps.googleusercontent.com)")
        base = web or public
        redirect = fixed or (base + CALLBACK if base else "")
        if not redirect:
            add("fail", "Google return address", "is not fixed: set GATEWAY_WEB_URL, otherwise it is taken from each request's Host header")
        else:
            try:
                u = urlsplit(redirect)
                host = (u.hostname or "").lower()
            except ValueError:
                u, host = None, ""
            if not u or u.scheme != "https" or not host:
                add("fail", "Google return address", f"{redirect} must be https")
            elif u.path != CALLBACK or u.query or u.fragment:
                add("fail", "Google return address", f"{redirect} must end with exactly {CALLBACK}")
            elif hosts.get("GATEWAY_WEB_URL") and host != hosts["GATEWAY_WEB_URL"]:
                add("fail", "GOOGLE_REDIRECT_URI", f"is on {host}, but people open {hosts['GATEWAY_WEB_URL']}; the sign-in cookie would be set on the wrong site")
            else:
                add("ok", "Google return address", f"register exactly this in the Google client: {redirect}")

    tls = bool(get("GATEWAY_TLS_CERT") and get("GATEWAY_TLS_KEY"))
    trust, force = get("GATEWAY_TRUST_PROXY") in ON, get("GATEWAY_FORCE_HTTPS") in ON
    bind = get("GATEWAY_HOST") or "127.0.0.1"
    if tls and trust:
        add("warn", "GATEWAY_TRUST_PROXY", "is on while the gateway serves TLS itself; forwarded headers from the internet would be believed")
    elif not tls and not trust:
        add("fail", "GATEWAY_TRUST_PROXY", "is off and there is no TLS certificate; behind Caddy or a platform proxy it must be 1 so addresses and https are read correctly")
    elif trust and not re.match(r"localhost$|127\.|\[?::1\]?$", bind):
        add("warn", "GATEWAY_HOST", f"listens on {bind} while trusting forwarded headers; only the proxy may be able to reach this port")
    else:
        add("ok", "proxy", "TLS here" if tls else "behind a proxy on this computer, forwarded headers trusted")
    secure = tls or force or get("GATEWAY_SECURE_COOKIES") in ON or public.startswith("https://")
    add("ok" if secure else "fail", "secure cookies", "on" if secure else "off: set GATEWAY_FORCE_HTTPS=1 or an https GATEWAY_PUBLIC_URL")

    if get("DEMO_MODEL") in ON:
        add("fail", "DEMO_MODEL", "is on; a stand-in model would answer instead of the providers")
    if get("GATEWAY_BOOTSTRAP_PASSWORD"):
        add("warn", "GATEWAY_BOOTSTRAP_PASSWORD", "is set; remove it from the environment once the first owner exists")
    keys = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "HIGGSFIELD_CREDENTIALS") if get(k)]
    add("ok" if keys else "warn", "provider keys", ("set: " + ", ".join(keys)) if keys else "none set; API and developer tools cannot reach a provider (website tools do not need one)")
    return out


def run(env, write=print):
    findings = check(env)
    for level, name, message in findings:
        write(f"{level.upper():4}  {name}: {message}")
    fails = sum(1 for f in findings if f[0] == "fail")
    warns = sum(1 for f in findings if f[0] == "warn")
    write(f"preflight: {fails} to fix, {warns} to review. Nothing was contacted and nothing was changed.")
    return 1 if fails else 0
