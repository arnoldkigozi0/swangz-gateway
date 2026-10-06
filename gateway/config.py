"""Settings come from the environment (and an optional .env file), never from the database.

Provider API keys live only here. Staff never see them: they hold a personal gateway key,
and the gateway swaps it for the provider key on the way out.
"""

import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

RESERVED_NAMES = {"admin", "api", "static", "healthz", "favicon.ico", "auth", "go", "icons"}


DIALECTS = ("anthropic", "openai", "elevenlabs", "higgsfield", "media")
CHAT_DIALECTS = ("anthropic", "openai")

# How each dialect presents the company key upstream. "media" is any other AI service with an API.
DEFAULT_AUTH = {"anthropic": "x-api-key", "openai": "bearer", "elevenlabs": "header:xi-api-key",
                "higgsfield": "key", "media": "bearer"}


@dataclass
class Provider:
    name: str  # first path segment clients use: https://gateway/<name>/v1/...
    base_url: str  # upstream root, e.g. https://api.anthropic.com
    key_env: str  # environment variable holding the provider key
    dialect: str  # anthropic | openai | elevenlabs | higgsfield | media
    auth: str = ""  # x-api-key | bearer | key (Authorization: Key …) | header:<Name>
    label: str = ""  # how the apps name it, e.g. "ElevenLabs"

    def __post_init__(self):
        if self.dialect not in DIALECTS:
            raise ValueError(f"provider {self.name}: dialect must be one of {', '.join(DIALECTS)}")
        if not self.auth:
            self.auth = DEFAULT_AUTH[self.dialect]
        if not (self.auth in ("x-api-key", "bearer", "key") or self.auth.startswith("header:")):
            raise ValueError(f"provider {self.name}: auth must be x-api-key, bearer, key or header:<Name>")
        self.label = self.label or self.name.capitalize()
        parts = urlsplit(self.base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"provider {self.name}: base_url must be http(s)://host[/path]")
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self.base_path = parts.path.rstrip("/")

    @property
    def is_chat(self):
        return self.dialect in CHAT_DIALECTS

    def api_key(self):
        return os.environ.get(self.key_env, "")

    def auth_headers(self):
        key = self.api_key()
        if not key:
            return {}
        if self.auth == "x-api-key":
            return {"x-api-key": key}
        if self.auth == "key":
            return {"authorization": f"Key {key}"}
        if self.auth.startswith("header:"):
            return {self.auth.split(":", 1)[1]: key}
        return {"authorization": f"Bearer {key}"}


def default_providers():
    return [
        Provider("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", "anthropic", label="Claude"),
        Provider("openai", "https://api.openai.com", "OPENAI_API_KEY", "openai", label="OpenAI"),
        Provider("elevenlabs", "https://api.elevenlabs.io", "ELEVENLABS_API_KEY", "elevenlabs", label="ElevenLabs"),
        # Higgsfield keys come as KEY_ID:KEY_SECRET, sent as "Authorization: Key KEY_ID:KEY_SECRET"
        Provider("higgsfield", "https://api.higgsfield.ai", "HIGGSFIELD_CREDENTIALS", "higgsfield", label="Higgsfield"),
    ]


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8787
    data_dir: str = "data"
    public_url: str = ""  # what staff type into their tools, e.g. https://ai.swangz.com
    secure_cookies: bool = False  # true whenever the console is served over https
    tz_offset_minutes: int = 180  # budget days and months follow Kampala time (UTC+3)
    tls_cert: str = ""
    tls_key: str = ""
    pbkdf2_iterations: int = 310_000
    max_body_bytes: int = 64 * 1024 * 1024
    upstream_timeout: float = 900.0  # long agent turns stream for many minutes
    bootstrap_admin: str = ""
    bootstrap_password: str = ""
    providers: dict = field(default_factory=dict)
    # Who may be given an account: a Swangz-domain email, or one of the named exceptions (the owner
    # and the demo user). Configurable; these are the defaults.
    email_domains: tuple = ("swangzavenue.com",)
    email_exceptions: frozenset = frozenset({"arnoldkigozi0@gmail.com", "webdev02022007@gmail.com"})
    # The address people open the apps at, when it differs from the gateway's own (e.g. a Netlify site
    # that proxies to the gateway). Used for sign-in links and the Google sign-in return address.
    web_url: str = ""
    # Sign in with Google (OpenID Connect). Both empty = the Google button is hidden.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""  # optional; default <web address>/auth/google/callback
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    # The shared workspace's API token (Neko's session.api_token, the same on every company browser).
    # Set = the gateway makes a sign-in per turn and removes it when the turn ends. Empty = plain links.
    workspace_token: str = ""
    # The Swangz Workspace Agent on the workspace server (workspace_agent/agent.py): its address, e.g.
    # https://workspace.swangzavenue.com/agent, and its token. Tools in 'agent' mode get browsers from it.
    workspace_agent_url: str = ""
    workspace_agent_token: str = ""
    # The video relay (TURN) for company browsers on Swangz's own computers, which nothing on the
    # internet can reach directly. Cloudflare's (a TURN key: its id and API token), or your own coturn
    # (its turn: addresses and static-auth-secret). The gateway hands out short-lived credentials only.
    turn_cloudflare_key_id: str = ""
    turn_cloudflare_token: str = ""
    turn_urls: tuple = ()
    turn_secret: str = ""

    @property
    def google_enabled(self):
        return bool(self.google_client_id and self.google_client_secret)

    def email_allowed(self, email):
        """True when this email may be used for an account: a Swangz domain, or a named exception."""
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            return False
        if email in self.email_exceptions:
            return True
        domain = email.rsplit("@", 1)[1]
        return any(domain == d or domain.endswith("." + d) for d in self.email_domains)

    def email_rule(self):
        doms = " or ".join("@" + d for d in self.email_domains)
        return f"Accounts use a Swangz email ({doms})."

    def __post_init__(self):
        if not self.providers:
            self.providers = {p.name: p for p in default_providers()}
        for name in self.providers:
            if name in RESERVED_NAMES or "/" in name or not name:
                raise ValueError(f"provider name {name!r} is reserved or invalid")

    @property
    def db_path(self):
        return os.path.join(self.data_dir, "gateway.db")

    def base_url(self):
        if self.public_url:
            return self.public_url.rstrip("/")
        scheme = "https" if self.tls_cert else "http"
        host = "localhost" if self.host in ("0.0.0.0", "::", "127.0.0.1") else self.host
        return f"{scheme}://{host}:{self.port}"

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        providers = {p.name: p for p in default_providers()}
        extra = env.get("GATEWAY_PROVIDERS", "")
        if extra:
            for entry in load_provider_file(extra):
                providers[entry.name] = entry
        return cls(
            host=env.get("GATEWAY_HOST", "127.0.0.1"),
            port=int(env.get("GATEWAY_PORT") or env.get("PORT") or 8787),
            data_dir=env.get("GATEWAY_DATA", "data"),
            public_url=env.get("GATEWAY_PUBLIC_URL", ""),
            secure_cookies=env.get("GATEWAY_SECURE_COOKIES", "") in ("1", "true", "yes")
            or env.get("GATEWAY_PUBLIC_URL", "").startswith("https://"),
            tz_offset_minutes=parse_offset(env.get("GATEWAY_TZ_OFFSET", "+03:00")),
            tls_cert=env.get("GATEWAY_TLS_CERT", ""),
            tls_key=env.get("GATEWAY_TLS_KEY", ""),
            pbkdf2_iterations=int(env.get("GATEWAY_PBKDF2_ITERATIONS") or 310_000),
            bootstrap_admin=env.get("GATEWAY_BOOTSTRAP_ADMIN", ""),
            bootstrap_password=env.get("GATEWAY_BOOTSTRAP_PASSWORD", ""),
            providers=providers,
            email_domains=tuple(d.strip().lower().lstrip("@") for d in
                                env.get("SWANGZ_EMAIL_DOMAINS", "swangzavenue.com").split(",") if d.strip()),
            email_exceptions=frozenset({"arnoldkigozi0@gmail.com", "webdev02022007@gmail.com"}
                                       | {e.strip().lower() for e in env.get("SWANGZ_EMAIL_EXCEPTIONS", "").split(",") if e.strip()}),
            web_url=env.get("GATEWAY_WEB_URL", "").strip().rstrip("/"),
            google_client_id=env.get("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=env.get("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=env.get("GOOGLE_REDIRECT_URI", "").strip(),
            workspace_token=env.get("GATEWAY_WORKSPACE_TOKEN", "").strip(),
            workspace_agent_url=env.get("GATEWAY_WORKSPACE_AGENT", "").strip().rstrip("/"),
            workspace_agent_token=env.get("GATEWAY_WORKSPACE_AGENT_TOKEN", "").strip(),
            turn_cloudflare_key_id=env.get("GATEWAY_TURN_CLOUDFLARE_KEY_ID", "").strip(),
            turn_cloudflare_token=env.get("GATEWAY_TURN_CLOUDFLARE_TOKEN", "").strip(),
            turn_urls=tuple(u.strip() for u in env.get("GATEWAY_TURN_URLS", "").split(",") if u.strip()),
            turn_secret=env.get("GATEWAY_TURN_SECRET", "").strip(),
        )


def load_provider_file(path):
    """A JSON list of {name, base_url, key_env, dialect[, auth, label]} — extra providers, or overrides."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [Provider(**{k: v for k, v in item.items() if k in ("name", "base_url", "key_env", "dialect", "auth", "label")}) for item in raw]


def parse_offset(text):
    """'+03:00' -> 180, '-05:30' -> -330."""
    text = (text or "").strip()
    if not text:
        return 0
    sign = -1 if text.startswith("-") else 1
    hours, _, minutes = text.lstrip("+-").partition(":")
    return sign * (int(hours or 0) * 60 + int(minutes or 0))


def load_dotenv(path=".env"):
    """KEY=VALUE lines into os.environ. Values already in the environment win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            else:  # KEY=value   # a comment — the comment is not part of the value
                value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
                if value.startswith("#"):  # KEY=   # only a comment
                    value = ""
            os.environ.setdefault(key, value)
