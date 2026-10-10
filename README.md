# Swangz AI Hub

> **New here?** Start with [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md) for the project guide and conventions, then
> [`docs/STATE.md`](docs/STATE.md) for the current status and what's next. On a new machine:
> clone the repository, read [Hub operations](docs/HUB-OPERATIONS.md), and run `python3 -m unittest discover`.

One controlled way into AI for everyone at Swangz. Staff get a personal key and point their tools at
the gateway instead of at Anthropic or OpenAI. The gateway holds the real provider keys, passes each
request through, and keeps a record of **who** used AI, **with which tool**, **what they asked**,
**what the AI did** (every command it ran, every file it edited), and **what it cost**. An admin can
pull any of it back later, or cut someone off — including in the middle of a reply.

Coding agents keep working exactly as before. Claude Code and Codex talk to the gateway in their
providers' own formats, byte for byte, so their full automation (running commands, editing files,
sub-agents) is unchanged — it is simply on the record.

- Python 3.10+ standard library only. Nothing to install.
- One SQLite file holds everything.
- **One platform with staff and admin workspaces.** `/` is **Swangz AI Hub**, the staff app: sign in, connect a tool in about a
  minute, submit weekly and adoption reports, propose purchases, inspect their own recorded activity, and manage devices and allowance. `/admin` is the **control room**, with roles (owner, operations,
  security, billing, viewer) and an audit log of what the watchers themselves did — what changed,
  from what to what, and why.

## Voice, image and video services

ElevenLabs and Higgsfield are built in; any other AI service with an API key (Runway, Replicate,
fal, …) can be added in the providers file. They work exactly like the chat models: the company key
stays on the server, staff use their own gateway key, and every generation is recorded — who, the
text or prompt, the voice/model and settings, characters or images, and the result (generated audio
is kept so an admin can play it back; image and video results are kept as their links).

Staff use them two ways:

- **Studio**, inside the Swangz AI Hub app: voice-overs, images and video in the browser, nothing to set up.
- **Their own scripts and apps**, through the official SDKs pointed at the gateway (the app's "Connect
  a tool" shows the exact lines). The gateway accepts the key however each SDK sends it.

| Service | Key on the server | Built in |
|---|---|---|
| ElevenLabs | `ELEVENLABS_API_KEY` | text-to-speech, speech-to-speech, sound effects, transcription, dialogue, music, voice list |
| Higgsfield | `HIGGSFIELD_CREDENTIALS` (`KEY_ID:KEY_SECRET`) | every generation endpoint and its status |

Account-wide endpoints (ElevenLabs history, for example) are refused: on a shared company account
they would show everyone's work to everyone. Each person can be limited to certain services
("allowed services" on their page) — for example Claude and ElevenLabs, but not video.

Another service, e.g. Runway, in `providers.json`:

```json
[{"name": "runway", "label": "Runway", "base_url": "https://api.dev.runwayml.com", "key_env": "RUNWAY_API_KEY", "dialect": "media"}]
```

`dialect: "media"` forwards the service's whole API with the company key (`auth` can be `bearer`,
`key`, `x-api-key` or `header:<Name>`), and records each request the same way.

**The websites themselves** (higgsfield.ai, elevenlabs.io in a browser) are not put behind the
gateway: they don't survive being proxied, they block automation, and one shared company login
usually breaks their terms. The API route above gives the same tools with the record intact.

## What it records

For every request:

| | |
|---|---|
| Who | the person and which of their keys (one key per device or tool) |
| Tool | Claude Code, Codex, an SDK, curl… — and, for Claude Code and Codex, which sub-agent inside it |
| Session | requests grouped into the conversation they belong to, and the typed prompt each one serves |
| Asked | what the person actually typed, with the context their tool injects stripped off |
| Did | each action in plain words: `$ npm test`, `edited src/login.ts`, `fetched https://…`, `started a sub-agent` |
| Said | the model's reply |
| For | its purpose: declared by the person or tool, derived from the tool, or inferred from keywords (with confidence and the words matched) — or unknown |
| Where | the address, and what is known about it: a network Swangz named, an approximate town from an offline table, or just the address type |
| Cost | input, output, cache and reasoning tokens, and dollars — estimated from the price or media rate in force, which is stored with it, or *unpriced* |
| Flags | credentials (API keys, cloud keys, private keys) seen in what was sent; attachments |
| Full record | the whole request and response, rebuilt on demand, downloadable as JSON |

Agents resend the whole conversation on every turn. The gateway stores each message once (by its
hash), so a long agent session costs about one copy of the conversation, not one per turn.

## What an admin can do

- **Watch live** — who is waiting on a model right now, what they asked, and how long it has run.
- **Stop one request**, **revoke a key**, **suspend a person**, or **stop all AI** with one switch.
  Each of these cuts requests that are already streaming; the tool gets a clear
  "revoked by an administrator" error in its own format, marked as not worth retrying.
- **Set limits** per person: a daily and monthly dollar budget, and which models they may use.
- **Search** everything by text, person, tool or outcome; **export** CSV; run **reports**.
- **Refuse requests that contain credentials** (off by default — when off, they are flagged).
- **Govern** with a **model registry** (approved / experimental / restricted / deprecated / disabled) and
  **policies** — refuse, permitted hours, a monthly cap — for everyone, departments or people, on gateway
  requests, portal opens and website visits. **Simulate** a policy against real history before saving it,
  and **explain** any decision check by check. Policies are data the gateway evaluates the same way every
  time; no AI model decides access.
- **Investigate**: risk signals against each person's own history, **incidents** with evidence and notes,
  **notifications** (optionally by email), and switch one provider off or pause the company browsers.
- **Roles**: owner (everything), operations (people, tools, policies + emergency), security (incidents,
  networks, security settings + emergency), billing (prices, rates, budgets), viewer (look only), or custom.
  Every change and every refused change is written to the audit log with before/after.

## Quick start (on any machine)

```bash
git clone https://github.com/arnoldkigozi0/swangz-gateway.git
cd swangz-gateway
cp .env.example .env            # put the provider keys in it
read -r -p "Verified owner email: " HUB_OWNER_EMAIL
python3 -m gateway add-admin "$HUB_OWNER_EMAIL"
python3 -m gateway serve        # http://localhost:8787
```

Open the control room at `/admin`, add a person under **People** with their work email, and press
**Create sign-in link**. Send them the link (copy it, or share it on WhatsApp). They choose a password,
land in the Swangz AI Hub app, and connect their tools themselves — each device gets its own key, shown
once, with the exact lines to paste. An owner can also issue keys directly from a person's page.

## Connecting tools

Staff normally do this from the Swangz AI Hub app ("Connect a tool"), which fills in the real address and
key. For reference:

**Claude Code** — in `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://ai.example.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "sgw_…",
    "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1"
  }
}
```

`CLAUDE_CODE_GATEWAY_HINT_HEADERS=1` makes Claude Code label each request (main turn, sub-agent,
compaction, background task) and group requests by the prompt they serve, so the record is richer.

**Codex** — in `~/.codex/config.toml`, and the key in the shell profile:

```toml
model_provider = "swangz"

[model_providers.swangz]
name = "Swangz AI Hub"
base_url = "https://ai.example.com/openai/v1"
env_key = "SWANGZ_AI_KEY"
wire_api = "responses"
```

**Anything else** that takes a base URL and an API key (the Anthropic and OpenAI SDKs, most AI
tools): base URL `https://ai.example.com/anthropic` or `https://ai.example.com/openai/v1`, API key
`sgw_…`.

Staff must use the gateway key. A tool signed in with a personal subscription (a Claude Pro/Max
login, Codex with a ChatGPT login) goes straight to the provider and the gateway never sees it.

## Configuration

Environment variables (or a `.env` file next to where you run it):

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | — | the company's provider keys; only the server ever sees them |
| `GATEWAY_PUBLIC_URL` | — | the address staff use, e.g. `https://ai.swangz.com`; https here turns on secure cookies |
| `GATEWAY_HOST`, `GATEWAY_PORT` | `127.0.0.1`, `8787` | where to listen (`PORT` is honoured too) |
| `GATEWAY_DATA` | `data` | folder for `gateway.db` — must be on a persistent disk |
| `GATEWAY_TZ_OFFSET` | `+03:00` | when budget days and months start |
| `GATEWAY_TRUST_PROXY` | off | set to `1` behind a reverse proxy or tunnel: client IPs and the public address come from `X-Forwarded-*` |
| `GATEWAY_FORCE_HTTPS` | off | set to `1` behind a tunnel that serves https but doesn't say so (localhost.run) |
| Identity policy | exact `swangzavenue.com` | enforced for staff and all admin roles; only the two explicitly approved owners are exceptions |
| `GATEWAY_TIMEZONE` | `Africa/Kampala` | Monday-to-Monday weekly reporting periods; budget offset remains separate |
| `GATEWAY_CORS_ORIGINS` | — | web origins allowed to call the API cross-site, e.g. a staff app on Netlify (comma-separated); see [`deploy/NETLIFY.md`](deploy/NETLIFY.md) |
| `GATEWAY_PROVIDERS` | — | path to a JSON list of extra providers (see below) |
| `GATEWAY_WORKSPACE_AGENT`, `GATEWAY_WORKSPACE_AGENT_TOKEN` | — | the Swangz Workspace Agent's address and token: company browsers for shared accounts, one per person on a turn, started when needed; see [`deploy/WORKSPACE.md`](deploy/WORKSPACE.md) |
| `GATEWAY_WORKSPACE_TOKEN` | — | fallback mode only: the Neko API token of fixed browsers listed on a tool, so the gateway makes and removes a sign-in per turn itself |
| `GATEWAY_EXTRA_ENDPOINTS` | — | endpoints to allow beyond the model calls, e.g. `POST /v1/images/generations` |
| `GATEWAY_TLS_CERT`, `GATEWAY_TLS_KEY` | — | serve https directly instead of behind a proxy |
| `GATEWAY_BOOTSTRAP_ADMIN`, `GATEWAY_BOOTSTRAP_PASSWORD` | — | create the first owner on hosts with no shell |
| `GATEWAY_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_FROM`; `GATEWAY_NOTIFY_TO` | — | optional: email high and critical notifications (STARTTLS on 587) |

Settings that change while running — retention per category, storing full bodies, refusing credentials,
model prices, media rates, purposes, named networks, emergency switches, console users and roles — live
in the console under **Settings**.

**Location.** No address is sent anywhere to be located. To show approximate towns, load a free offline
table on the server (DB-IP Lite or IP2Location LITE, CSV) and refresh it monthly:
`python3 -m gateway geoip-import dbip-city-lite-2026-10.csv --source "DB-IP Lite 2026-10"`.

**More providers.** Any service that speaks the Anthropic or OpenAI format can sit behind the
gateway. `providers.json`:

```json
[{"name": "openrouter", "base_url": "https://openrouter.ai/api", "key_env": "OPENROUTER_API_KEY", "dialect": "openai"}]
```

Staff then use `https://ai.example.com/openrouter/v1`.

**Prices.** Claude models come pre-priced from Anthropic's list prices. Other models are recorded
with full token counts and shown as **unpriced** until an owner enters a price under Settings —
the gateway never guesses a price.

## On this laptop, online (demo)

```bash
DEMO_MODEL=1 bash deploy/laptop-demo.sh
```

Starts the gateway and a free https tunnel and prints the staff and admin links. With
`cloudflared` installed (one file from Cloudflare's GitHub releases, in `~/.local/bin`) it uses a
Cloudflare quick tunnel, whose link stays the same while it runs; otherwise it falls back to
localhost.run over plain `ssh`, whose free links change every so often. With `DEMO_MODEL=1` a
stand-in model answers instead of real providers, so nothing is spent. Either way the link goes down
when the laptop sleeps or loses internet — fine for showing it, not for daily use.

## Running it for real

The gateway must be always on, reachable by staff over **https**, with its data folder on a disk
that survives restarts. Free tiers that sleep or wipe the disk are not suitable. A small Linux VPS
(1 GB RAM is plenty) or an always-on office machine behind a tunnel both work.

`deploy/` has a systemd unit and a Caddy config (Caddy gets the https certificate automatically):

```bash
sudo cp -r . /opt/swangz-gateway && sudo cp deploy/swangz-gateway.service /etc/systemd/system/
sudo systemctl enable --now swangz-gateway
```

Back up `data/gateway.db` regularly — it is the record.

## Security model

- Staff keys are `sgw_<id>_<secret>`; only a SHA-256 of the secret is stored, so a copy of the
  database cannot be used to make requests. Keys are shown once.
- Provider keys never leave the server, are never stored in the database, and are stripped from
  everything forwarded.
- Only model endpoints are forwarded. Everyone's traffic shares the company provider key, so
  endpoints that could read other people's data through it (files, batches, stored responses, the
  admin API) are refused unless an owner explicitly allows them.
- The console uses an HttpOnly, SameSite=Strict session cookie, a required header on every change,
  a strict Content-Security-Policy, and never renders anything a person typed as HTML. Sign-in is
  rate limited. CSV exports are protected against spreadsheet formula injection.
- Passwords use PBKDF2-SHA256 (310,000 rounds). Staff sign-in links work once, expire after seven
  days, and are stored only as a hash. Staff and admin sessions use separate cookies; a staff session
  opens nothing in the control room, and the staff API only ever returns the person's own profile,
  allowance and devices.
- The staff app and control room can live on separate subdomains if you prefer (point both at the
  same gateway); it keeps browsers from offering admin passwords on the staff sign-in page.
- Console roles are checked on the server for every change; policies that can't be evaluated refuse
  rather than allow. The full threat model, and its limits, is [`docs/SECURITY.md`](docs/SECURITY.md).

## What it can't see

Being honest about the edges:

- **Only traffic that goes through it.** Web apps used directly in a browser (ChatGPT, claude.ai,
  Higgsfield, Runway…) and tools signed in with personal subscriptions bypass any gateway. Making
  the gateway the only way to get company-paid AI is a policy decision, not a technical one.
- **Commands the agent runs are recorded as the model asked for them.** The output of each
  command comes back in the next request and is in the full record, but the gateway does not run
  on the person's machine and cannot see anything the agent did not report to the model.
- **Budgets are checked before each request**, so one long request can take someone slightly past
  their limit.
- Claude Code's auto mode can ask the API to run its safety checks server-side; the gateway passes
  that through untouched, but it has only been tested against a stand-in provider, not the real API.

The staff app frames itself as a work tool, not as monitoring. Its "Usage policy" note still says,
in one plain line, that use is recorded for security, cost and support — Uganda's Data Protection
and Privacy Act expects people to be told, and that note covers it without making a feature of it.

## Command line

```
python3 -m gateway serve | add-admin EMAIL [--role owner|operations|security|billing|viewer] | add-person NAME --email EMAIL [--department D]
                   issue-key PERSON_ID [--label L] | revoke-key KEY_ID | people | pause | resume | purge
                   geoip-import FILE --source "DB-IP Lite 2026-10"
```

A revoke or pause from the command line applies from the next request; only the console can also
cut requests that are already streaming.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

The suite runs the gateway against a stand-in provider that speaks both formats, streamed and not:
key handling, every refusal, budgets, cutting live streams, record rebuilding, retention, the
console API and its permissions, and (`tests/test_v2.py`) roles, the audit fabric, location, purpose,
the model registry, policies and their simulator, media costs, reports, incidents, notifications, risk
signals and migrations from v12.

Native adoption reporting, weekly accountability, procurement, migration and operating instructions: [Hub operations](docs/HUB-OPERATIONS.md).
