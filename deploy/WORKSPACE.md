# The shared workspace — company browsers on your own server or computer

For tools where Swangz has **one account** and no per-person plan, staff can work in company browsers
that run on Swangz's own server — or one of its own computers — and are signed in to the tool **once**, by an admin. The portal sends
whoever holds a turn into a browser of their own. They arrive signed in, the password never leaves the
server, and several people can be on one tool at once — one browser each.

```
Gateway VPS                                   Workspace VPS
  people, tools, turns, budgets, audit          Swangz Workspace Agent  ── Docker
  "a browser for Grace's turn on ChatGPT"  ──►    ├── chatgpt-1  (Neko + Chromium, signed in)
  "Grace's turn is over"                   ──►    ├── chatgpt-2
                                                  └── claude-3
```

The gateway stays the authority: who may use what, turns, and the record. The workspace server only runs
browsers when the gateway asks. Browsers are **[Neko](https://github.com/m1k1o/neko)** containers:
Apache-2.0 (free for business use), one Chromium each, streamed over WebRTC.

**Why not Kasm?** Kasm's free Community edition is licensed for non-commercial use only, and its
$10/user Starter plan has no developer API. Only Kasm Enterprise has both, on a custom quote — and it
would duplicate the control the gateway already has. (Checked October 2026.)

## Read this before you build it

**It does not make account sharing allowed.** ChatGPT, Midjourney, Canva and most others forbid one
subscription being used by several people, whatever screen they are looking at. Several people on one
account *at the same moment* is the pattern vendors notice most easily, and some sign other sessions
out when a new one starts. Where a tool sells a Team or Business plan, **buy seats**. Use the workspace
for the tools that have none.

**What it does fix:** staff never see or hold the password and can't copy the signed-in session out
(developer tools are off in the browser); each person gets a browser to themselves, only for their
turn; every turn is logged — who, which browser, from when to when.

**What it does not fix:** whoever is in a browser can do anything the account can do *on that site*,
including its settings page — the log says who it was. When several people use one account at once, the
vendor's usage history can't be split between them by time.

**What it costs:** each browser running needs about 1.5–2 GB of RAM; Neko is free. An 8 GB server runs
3–4 at once. Browsers only run while needed, so you can *list* more than fit in RAM — a few for every
tool — and set `max_running` to what the server can carry: when it's reached, a free browser left
running for another tool stops to make room, and when all of them are in use people are told the
workspace is full. Around 20 at once needs about 64 GB of RAM and 16 CPU threads (each browser streams
its screen as video), with `screen` at `1280x720@25`. Keep this server **separate from the gateway's**: a browser that eats the
RAM must not take the gateway down, and a person driving a browser must not be on the machine that holds
the provider keys.

## Where the browsers run: the rented server, the Windows PC or the Mac

The browsers can run on a server Swangz rents (below), or on one of Swangz's own computers — a strong
Windows PC or a Mac — with nothing rented. **One place at a time:** the console's **Settings → Company
browsers** shows all three and which one Open uses, and **Use this one** switches. Switching moves anyone
in a company browser off the old place (their turn ends; Open gives them a browser at the new one), and
their sign-in there is removed as soon as it answers. Each place has browsers of its own, each signed in to
its tool once — sign a place's browsers in on that same page *before* switching to it.

| | Rented server | Swangz's own computer |
|---|---|---|
| Costs | €37/month for ~20 at once (traffic included) | nothing rented; the computer, its power and internet |
| Reachable | public IP, ports open | nothing needs to reach it: a Cloudflare tunnel for the pages, a relay for the video |
| Needs | Ubuntu, set up once by `setup-workspace-server.sh` | Docker Desktop + Python, `computer.py setup` |
| Stays up | in a data centre | only while the computer is on, awake, signed in and online — a UPS helps |
| Upload | the data centre's | **its internet's upload**: ~2–3 Mbps per person in a browser (20 people ≈ 40–60 Mbps) |
| Video for people elsewhere | direct | through the relay (below); people on the computer's own network connect straight to it |

### On a Windows PC or a Mac

1. Install **Docker Desktop** (Windows: `winget install -e --id Docker.DockerDesktop`; Mac: docker.com, the
   Apple-chip or Intel build), open it once and accept its terms. Install **Python 3** (Windows:
   `winget install -e --id Python.Python.3.13`; most Macs have `python3`). Copy this repo onto it.
2. Console → **Settings → Company browsers** → the Windows PC (or the Mac) → **Connect…**. It shows a key —
   once — inside the exact command, e.g.

   ```
   python workspace_agent\computer.py setup --host windows --gateway https://swangz-ai.netlify.app --key <key>
   ```

   Run it in the repo folder on that computer (PowerShell on Windows, Terminal on a Mac). It checks the
   gateway answers, starts Docker Desktop if needed, works out how many browsers fit in Docker's memory
   (`max_running`), downloads Cloudflare's tunnel program and the browser image (~1 GB, once), sets itself to
   start whenever someone signs in to the computer (Windows: the sign-in list in the registry, no window;
   Mac: a LaunchAgent), starts, and checks in. The console then shows the computer **Online**.
3. Sign its browsers in (same page, **Signing the browsers in** → that computer), then **Use this one**.

The computer's browser list comes from the console: every shared tool set to *Company browsers = Swangz's
company browsers* gets one browser per *person on it at a time*, within a minute. A tool keeps the browser
numbers it was given — and so their sign-ins — for good, even when it needs fewer for a while.

Its files are in `~/swangz-workspace` (`agent.json` holds the key; `logs/workspace.log`). On the computer:

```
python workspace_agent/computer.py status   # running? checked in? in use? relay?
python workspace_agent/computer.py stop     # stop it and its browsers (back at the next sign-in, or `start`)
python workspace_agent/computer.py start
python workspace_agent/computer.py remove   # stop it, and no longer start it with the computer
```

**Memory.** Docker Desktop gets only part of the computer's memory: on Windows, half of it by default
(32 GB of 64 → ~15 browsers). Setup says so and how to give it more — on Windows a `.wslconfig` in your user
folder with `[wsl2]` / `memory=52GB`, then `wsl --shutdown`; on a Mac Docker Desktop → Settings →
Resources — then run setup again so `max_running` follows.

**Keep it up.** It keeps the computer from sleeping while it runs, but it can't run while the computer is
off or nobody is signed in to it, or Docker Desktop is closed. If the computer will be off, switch Open
back to the rented server first. Its address is a Cloudflare *quick tunnel*, new each time the tunnel
opens; the computer tells the gateway within seconds. For a fixed address, create a named tunnel in
Cloudflare (needs swangzavenue.com's DNS on Cloudflare), point its hostname at `http://127.0.0.1:8790`, and
put `"tunnel_token"` and `"public_url"` in `agent.json`.

### The video relay

Nothing on the internet can reach a computer in an office or a home, so its browsers' video goes through
a **TURN relay**: both the browser and the person's screen connect *out* to it and meet there. The
gateway keeps the relay's secret and hands the computer credentials that last 48 hours; the console shows
whether one is set. Without one, only people on the same network as the computer can use its browsers.

- **Cloudflare's relay** (recommended — nearest to Kampala, nothing to run): Cloudflare dashboard →
  Realtime → TURN → create a TURN key. In the gateway's `.env`:
  `GATEWAY_TURN_CLOUDFLARE_KEY_ID=…` and `GATEWAY_TURN_CLOUDFLARE_TOKEN=…`, then restart the gateway.
  The first 1,000 GB a month are free, then $0.05 per GB — a person in a browser all day is roughly
  5–10 GB, so ~20 people all day can come to $50–150 a month. At that size the rented server, whose
  traffic is included, costs less.
- **Your own coturn** (free traffic, on a server you rent anyway — e.g. the gateway's, though from there
  the video detours through Germany): run coturn with `use-auth-secret`, and set `GATEWAY_TURN_URLS`
  (e.g. `turn:turn.swangzavenue.com:3478,turns:turn.swangzavenue.com:5349`) and `GATEWAY_TURN_SECRET`.

The rented server doesn't need the relay: its public address is reachable directly.

## How it works

1. **Open** in the staff app takes a turn and asks the agent for a browser for that tool.
2. The agent picks a free browser. If it isn't running it starts it (a fresh container with a new random
   Neko API token that only the agent knows); meanwhile the person sees *Starting your browser…*, which
   checks again every 3 seconds — usually a few seconds, never a hung request.
3. The agent makes a Neko sign-in for that person on that browser — `swangz-<their id>` with a new random
   password — and the gateway sends them in with it. Nobody else has a sign-in there.
4. When the turn ends — handed back, run out (caught within 15 seconds), taken back, suspended — the
   gateway tells the agent, which deletes the sign-in (Neko drops them at once) and **recycles** the
   browser: a fresh container for the next person, still signed in to the tool, because the sign-in
   lives in the browser's profile volume. If Neko doesn't answer, the container is removed instead; if
   Docker itself is down, the gateway keeps asking until it's done.
5. A free browser left unused for `idle_minutes` (15) is stopped, giving its RAM back.

The temporary Neko sign-in lives exactly as long as the turn. The tool's own sign-in, in the profile,
lives on. That separation is the whole design.

## Setting it up

### 1. The server

Ubuntu, 8 GB RAM (4 GB for one or two at once), the region nearest Kampala you can get. Install Docker
and Caddy. Point `workspace.swangzavenue.com` at it. Firewall: 80 and 443, plus each browser's WebRTC port
— `59100 + its number`, UDP **and** TCP (59101 for browser 1, …).

Pull the browser image once, pinned to a version you've tested:

```bash
docker pull ghcr.io/m1k1o/neko/chromium:latest   # then pin, e.g. :3.1.6, in the config
```

### 2. The agent

```bash
sudo useradd --system --create-home --home-dir /var/lib/swangz-workspace --groups docker swangz-ws
sudo mkdir -p /opt/swangz-workspace /etc/swangz-workspace
sudo cp workspace_agent/agent.py /opt/swangz-workspace/
sudo cp workspace_agent/agent.example.json /etc/swangz-workspace/agent.json
sudo nano /etc/swangz-workspace/agent.json      # token, public_ip, gateway_ip, tools and browsers
sudo chown root:swangz-ws /etc/swangz-workspace/agent.json && sudo chmod 640 /etc/swangz-workspace/agent.json
sudo -u swangz-ws python3 /opt/swangz-workspace/agent.py check --config /etc/swangz-workspace/agent.json
```

In the config, each tool lists its browsers by **number**, unique across the whole server; the number
fixes the browser's ports. The tool id must be the gateway's — it's in the console's address bar when
the tool is open (`#/tools?open=chatgpt`); the built-ins include `chatgpt`, `claude`, `midjourney`,
`suno`. `start_url` is the page new tabs open.

```json
"tools": {
  "chatgpt": {"start_url": "https://chatgpt.com/", "browsers": [1, 2]},
  "claude":  {"start_url": "https://claude.ai/",   "browsers": [3]}
}
```

### 3. Caddy

```bash
sudo -u swangz-ws python3 /opt/swangz-workspace/agent.py caddy --config /etc/swangz-workspace/agent.json | sudo tee /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

It routes `/agent/*` to the agent — only from `gateway_ip` — and `/chatgpt-1/…` etc. to each browser.

### 4. Start it

```bash
sudo cp deploy/swangz-workspace-agent.service /etc/systemd/system/
sudo systemctl enable --now swangz-workspace-agent
```

### 5. Connect the gateway

In the gateway's `.env`, then restart the gateway:

```
GATEWAY_WORKSPACE_AGENT=https://workspace.swangzavenue.com/agent
GATEWAY_WORKSPACE_AGENT_TOKEN=<the same token as in agent.json>
```

### 6. Set the tool up, and sign each browser in once

Control room → **Tools → the tool → Settings**: *How people sign in* = **Shared company account**,
*Company browsers* = **Swangz's company browsers**, *People on it at a time* = how many browsers it has
(or fewer).

Then **Who can use it → Browsers on the workspace server**: for each browser press **Sign in to the
tool**, **Open it**, sign in to the tool inside it with the company account, and press **Done**. While
you're in it, nobody can be given that browser. Each browser has its own profile, so each needs this
once. Your admin session ends by itself after 30 minutes.

**Adding a browser later:** add a new number in `agent.json`, open its port in the firewall, run the
Caddy step again, `sudo systemctl restart swangz-workspace-agent`, and sign it in.

## Settings worth knowing

| `agent.json` | Default | |
|---|---|---|
| `idle_minutes` | 15 | a free browser unused this long is stopped |
| `max_running` | 0 (no limit) | browsers running at once on the whole server, all tools together. When reached, the free browser unused longest stops to make room; when every one is in use, people are told it's full |
| `screen` | 1600x900@30 | each browser's screen size and frame rate. `1280x720@25` costs less CPU and less internet per person |
| `recycle` | true | restart the browser after every turn, so the next person starts fresh |
| `fresh_start` | false | open `start_url` on every start instead of restoring the last tabs. Test it per tool: a tool that keeps its sign-in in a *session* cookie loses it when tabs aren't restored. Can be set per tool |
| `memory` / `cpus` / `shm` | 2g / 1.5 / 2g | each browser's limits |
| `start_timeout` | 120 | seconds before a browser that won't start counts as failed |
| `admin_minutes` | 30 | an admin's sign-in session ends by itself after this |

The browser policy the agent writes keeps cookies (`DefaultCookiesSetting: 1`), restores the session
(`RestoreOnStartup: 1`) so the browser stays signed in, and keeps **developer tools off**
(`DeveloperToolsAvailability: 2`) — with them on, anyone in the browser could copy the account's session
cookie to their own laptop. `file://` and `chrome://settings`, `flags` and `inspect` are blocked.

## Security

- **Two secrets, both only on servers:** the agent token (in `agent.json` and the gateway's `.env`) and,
  per browser start, a Neko API token the agent makes and keeps to itself. No fixed Neko password exists.
- The agent listens on `127.0.0.1` only; Caddy lets just the gateway's address reach `/agent/`, and every
  call still needs the token. Browser containers can't reach the agent, the Docker socket, or anything
  of the gateway's.
- The agent's user is in the `docker` group, which is as powerful as root on that server. Keep the
  server for this alone.
- Sign-in profiles are Docker volumes (`swangz-ws-profile-<browser>`). Removing a container never removes
  one; `docker volume rm` does — that signs the browser out for good.

## Checking it works

- Open the tool from the staff app → *Starting your browser…* → you land in it, signed in.
- A second person opens it → they get the other browser. With every browser busy, the next person is told
  so, and keeps no seat.
- Hand it back → within a second or two your tab is disconnected and the old link no longer works.
- Control room → the tool → **Who can use it** shows each browser — running, starting or stopped — and
  who is on it.

## The fallback: fixed browsers

Without the agent, a tool can list browsers you run yourself — *Company browsers* = **The browsers
listed below**, one address per line. Each person on a turn gets one of them. With
`GATEWAY_WORKSPACE_TOKEN` set to the browsers' shared Neko API token, the gateway makes and removes a
sign-in per turn itself; without it, it just sends people to the address. Run each browser with the same
image, the policy above mounted at `/etc/chromium/policies/managed/policies.json`, a profile volume at
`/home/neko/.config/chromium`, and `NEKO_MEMBER_PROVIDER=object`, `NEKO_SESSION_API_TOKEN`,
`NEKO_SERVER_PROXY=true`, `NEKO_SERVER_PATH_PREFIX`, `NEKO_WEBRTC_UDPMUX`/`TCPMUX` and `NEKO_WEBRTC_NAT1TO1`
set. Useful for development and as an emergency fallback; the agent is the way to run it for real.
