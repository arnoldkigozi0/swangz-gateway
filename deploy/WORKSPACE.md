# The shared workspace — company browsers on your own server

For tools where Swangz has **one account** and no per-person plan, you can run browsers on the
company's own server, sign each one in to that tool **once**, and have the portal send whoever holds a
turn straight into one. They arrive already signed in, and the password never leaves the server.

```
staff browser → Swangz AI (turn, log, sign-in for this turn) → a company browser on your server → the tool
```

This is a real, mainstream category — **remote browser isolation**. It is what Island and Cloudflare
Browser Isolation sell. Self-hosted, the gateway is built for **[Neko](https://github.com/m1k1o/neko)**:
Apache-2.0 (free for business use), one Chromium per container, streamed over WebRTC — which copes
with a MiFi better than desktop streaming does.

**Why not Kasm?** Kasm's free Community edition is licensed for testing and non-commercial use only,
and its $10/user Starter plan has no developer API, which the gateway needs to hand out and take back
sign-ins. Only Kasm Enterprise has both, on a custom quote. (Checked October 2026.)

## Read this before you build it

**It does not make account sharing allowed.** ChatGPT, Midjourney, Canva and most others forbid one
subscription being used by several people, whatever screen they are looking at. Several people on one
account *at the same moment* is the pattern vendors notice most easily, and some vendors sign the other
sessions out when a new one starts. Where a tool sells a Team or Business plan, **buy seats** — it is
cheaper than losing the account, and nobody queues.

**What it does fix,** and these are real:
- staff never see or hold the shared password, and can't copy the signed-in session out (developer
  tools are switched off in the browser);
- each person gets a browser of their own, and only for their turn — the gateway makes them a sign-in
  when they open it and deletes it the moment the turn ends;
- every turn is logged: who, which browser, from when to when.

**What it does not fix:** whoever is in a browser can do anything the account can do *on that site* —
including its settings page. The log tells you who it was. And when several people work on one account
at once, the vendor's usage history can't be split between them by time; one person at a time can.

**What it costs:**
- **RAM.** Each browser is one person at a time and needs roughly 1.5–2 GB. A 4 GB server runs 1–2
  browsers; 8 GB runs 3–4. The $5 VPS that runs the gateway cannot also run browsers — this is a
  **separate machine**, about **$12–30/month**.
- **Speed.** You are streaming a screen. Pick the region nearest Kampala you can get.
- **Bot checks.** Some AI sites challenge sign-ins from datacentre addresses. Expect to answer a
  verification the first time on each browser, and occasionally again.

## How it works

- In the console, a shared tool lists its **browsers**, one address per line. The pool size caps how
  many people can be on it at once (together with *People on it at a time*).
- **Open** takes a turn, gives the person a free browser for the whole turn, and — when
  `GATEWAY_WORKSPACE_TOKEN` is set on the gateway — creates a Neko sign-in just for them on that
  browser (`swangz-<their id>`, a new random password every time), then sends them there with it.
  Nobody else has a sign-in on that browser.
- When the turn ends — they hand it back, it runs out, an admin takes it back, they're suspended — the
  gateway deletes that sign-in, and Neko disconnects them on the spot. A turn that runs out is caught
  within 15 seconds. If the browser's server is down, the gateway keeps trying until it's gone.
- The gateway never stores the password it made; it's only in the link the person opened.

Without `GATEWAY_WORKSPACE_TOKEN`, Open still gives each person a browser of their own, but sends them
to the plain address and Neko's own login decides who gets in. Fine for a first test, not for real use.

## Setting it up

### 1. A server

4 GB RAM minimum (8 GB for three or four people at once), nearest region to Kampala, separate from
the gateway. Install Docker. Point `workspace.swangzavenue.com` at it. Open the WebRTC ports below
(UDP and TCP) in its firewall, and 80/443 for Caddy.

### 2. Shared settings for every browser

Make two secrets: `openssl rand -hex 32` for the API token, and a long password for the Neko admin.

`neko.yaml` — the same file for every browser:

```yaml
server:
  proxy: true                      # behind Caddy
member:
  provider: object                 # sign-ins the gateway makes live in memory: a restart clears them
  object:
    users:
      - username: admin            # only for signing each browser in to the tool, by hand
        password: "<the long admin password>"
        profile: {name: Swangz admin, is_admin: true, can_login: true, can_connect: true, can_watch: true,
                  can_host: true, can_share_media: false, can_access_clipboard: true,
                  sends_inactive_cursor: true, can_see_inactive_cursors: true}
session:
  api_token: "<the API token — the same value goes in the gateway's GATEWAY_WORKSPACE_TOKEN>"
webrtc:
  icelite: true
  nat1to1: "<this server's public IP>"
```

`policies.json` — Neko's own Chromium policy (copy `apps/chromium/policies.json` from the Neko repo)
with these changes, so the browser **stays signed in** and staff can't lift the session out of it:

```json
  "DefaultCookiesSetting": 1,
  "RestoreOnStartup": 1,
  "DeveloperToolsAvailability": 2,
  "URLBlocklist": ["file://*", "chrome://policy", "chrome://settings", "chrome://flags", "chrome://inspect"]
```

(`DeveloperToolsAvailability: 2` is already Neko's default — keep it. With developer tools on, anyone
in the browser could copy the account's session cookie and use it from their own laptop.)

### 3. One container per browser

`docker-compose.yml` — two ChatGPT browsers here; add more the same way, each with its **own profile
folder, path and WebRTC port**:

```yaml
x-browser: &browser
  image: ghcr.io/m1k1o/neko/chromium:latest   # pin a version tag once it works
  restart: unless-stopped
  shm_size: 2gb

services:
  chatgpt-1:
    <<: *browser
    ports: ["127.0.0.1:8101:8080", "59101:59101/udp", "59101:59101/tcp"]
    volumes:
      - ./neko.yaml:/etc/neko/neko.yaml:ro
      - ./policies.json:/etc/chromium/policies/managed/policies.json:ro
      - ./profiles/chatgpt-1:/home/neko/.config/chromium    # where the signed-in session lives
    environment:
      NEKO_CONFIG: /etc/neko/neko.yaml
      NEKO_SERVER_PATH_PREFIX: /chatgpt-1
      NEKO_WEBRTC_UDPMUX: "59101"
      NEKO_WEBRTC_TCPMUX: "59101"

  chatgpt-2:
    <<: *browser
    ports: ["127.0.0.1:8102:8080", "59102:59102/udp", "59102:59102/tcp"]
    volumes:
      - ./neko.yaml:/etc/neko/neko.yaml:ro
      - ./policies.json:/etc/chromium/policies/managed/policies.json:ro
      - ./profiles/chatgpt-2:/home/neko/.config/chromium
    environment:
      NEKO_CONFIG: /etc/neko/neko.yaml
      NEKO_SERVER_PATH_PREFIX: /chatgpt-2
      NEKO_WEBRTC_UDPMUX: "59102"
      NEKO_WEBRTC_TCPMUX: "59102"
```

Create each profile folder before the first start and give it to Neko's user:
`mkdir -p profiles/chatgpt-1 profiles/chatgpt-2 && sudo chown -R 1000:1000 profiles`.

### 4. Caddy in front

```
workspace.swangzavenue.com {
    handle /chatgpt-1* {
        reverse_proxy 127.0.0.1:8101
    }
    handle /chatgpt-2* {
        reverse_proxy 127.0.0.1:8102
    }
}
```

`handle` (not `handle_path`): Neko expects its path prefix to arrive intact.

### 5. Sign each browser in, once, by hand

Open `https://workspace.swangzavenue.com/chatgpt-1/`, log in to Neko as **admin**, go to the tool in
that browser and sign in with the Swangz subscription account. Do the same in every browser — each has
its own profile. Nobody else ever types that password. Restart the container once and check it is
still signed in.

### 6. Connect the gateway

On the gateway's machine, add to its `.env` and restart it:

```
GATEWAY_WORKSPACE_TOKEN=<the same API token as in neko.yaml>
```

Then in the control room: **Tools → the tool → Settings** → *How people sign in* = **Shared company
account** → **Shared workspace browsers**, one per line:

```
https://workspace.swangzavenue.com/chatgpt-1/
https://workspace.swangzavenue.com/chatgpt-2/
```

Set *People on it at a time* to the number of browsers (or fewer), and how long a turn lasts.

**Keep the API token secret.** It can make and remove sign-ins on every browser. It lives only in
`neko.yaml` and the gateway's `.env` — never in the console, never in git.

## Checking it works

- Open the tool from the staff app → you land in a browser, signed in to Neko and to the tool.
- A second person presses Open → they get the other browser. A third → told who has them, until when.
- Hand it back in the staff app → within a second or two your browser tab is disconnected, and the old
  link no longer works.
- Control room → the tool → **Who can use it** shows who is on which browser; **Live** shows who is on a
  shared account; **Staff activity → Tools opened** has the history.
