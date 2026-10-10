# Going live — the checklist, and what it costs

Historical deployment notes below. For the current Hub identity policy, migration and rollout procedure, see [Hub operations](HUB-OPERATIONS.md). The legacy webdev02022007@gmail.com demo identity is no longer allowed to access the Hub; only the two user-approved owner exceptions remain. No public deployment check was performed for this integration.

Last updated: 3 Oct 2026. Swangz uses **paid accounts** (ChatGPT, Claude, Midjourney… subscriptions,
used in the browser), **not provider API keys**. Everything below follows from that.

## Where it stands today

- **Working now:** `https://swangz-ai.netlify.app` (staff) and `/admin` (console), running from Arnold's
  Windows PC through a Cloudflare tunnel. Console owner `arnoldkigozi0@gmail.com`; demo staff
  `webdev02022007@gmail.com`. The PC has to stay on and online — that's why step 2 exists.
- **Signing in to Swangz AI Hub works.** What doesn't happen yet is arriving **already signed in to the AI
  tool**: Open sends people to the tool's own site, where they sign in themselves. That needs one of the
  options below per tool.

## How people get into each tool (set per tool: Tools → the tool → Settings)

| Option | What staff see | What it needs | Fits |
|---|---|---|---|
| **Their own seat** (`seat`) | Open → the tool's site; they sign in once with their work email | A Team/Business plan with a seat per person | Tools used daily by several people — the vendor-approved way |
| **Company SSO** (`sso`) | Open → signed in through Swangz's Google account | A plan that offers SSO; paste its SSO link | Enterprise-tier plans |
| **Shared company account** (`shared`) + workspace | Open → a company browser, **already signed in** | The workspace server (step 4); an admin signs each browser in once | Tools where Swangz pays for one account |

A shared account is handed out **in turns**, so every credit spent has a name against it. One honest
caveat, once: most vendors' terms say a personal plan (ChatGPT Plus, Claude Pro…) is for one person. The
workspace keeps the password safe and records who used it when, but it doesn't change those terms — and
several people on one account *at the same moment* is what vendors spot most easily. Use seats where a
Team plan exists; keep "shared" for the rest, one person at a time.

## The checklist

**You** = something only you can do (it needs your accounts, money, or a decision). **Claude** = can be
done for you from the Windows PC.

### 1. Today — free
- [ ] **You:** for each tool Swangz pays for — Tools → the tool → **Subscription**: set *Active*, the plan
      and monthly cost (this is what Licences & spend adds up). Then **Settings → How people sign in**.
- [ ] **You:** assign tools to people (People → the person → Tools, or the tool → Who can use it).
- [ ] **You:** Google sign-in — Google Cloud console → project `swangz-ai` → Clients → "Swangz Ai" → add a
      client secret. Put `GOOGLE_CLIENT_ID=` and `GOOGLE_CLIENT_SECRET=` in
      `C:\Users\nabul\swangz-gateway-demo\.env`. **Claude:** restart the gateway.
- [ ] **You:** Google consent screen → complete the **Branding** page → **Publish**, so any Swangz Google
      account can sign in (today only the two test users can).

### 2. A server for the gateway — about $5/month — the PC is then no longer needed
- [ ] **You:** open a [Hetzner Cloud](https://www.hetzner.com/cloud) account; create a server: Ubuntu
      24.04, type **CX22**, location Germany (nearest to Kampala they offer). Under **SSH keys** paste the
      key in `C:\Users\nabul\.ssh\swangz_servers.pub`. Send Claude the server's IP address.
- [ ] **You (or whoever runs swangzavenue.com's DNS):** add an **A record** `ai.swangzavenue.com` → that
      IP. (Can't wait for DNS? `<ip-with-dashes>.sslip.io` works meanwhile.)
- [ ] **Claude:** copy the code, run `deploy/setup-gateway-server.sh`, move the database and settings
      across (all accounts and history come along), point Netlify at `https://ai.swangzavenue.com` —
      once, for good — and stop the PC's tunnel.

### 3. Provider API keys — skip
Not needed with paid accounts. (The gateway can still front the APIs later if Swangz ever wants Claude
Code or Codex on company keys.)

### 4. The workspace server — about $9/month — "Open → already signed in"
- [ ] **You:** decide which tools are shared accounts, and how many people need to be on each **at the same
      time** (each needs its own browser, ~2 GB RAM).
- [ ] **You:** create a second Hetzner server: Ubuntu 24.04, **CX32** (8 GB — 3–4 browsers at once; CX42
      for 6–8), same SSH key. DNS: `workspace.swangzavenue.com` → its IP. Send Claude the IP.
- [ ] **Claude:** run `deploy/setup-workspace-server.sh` with your tools and browser counts, connect it to
      the gateway, switch those tools to *Company browsers → From the workspace server*.
- [ ] **You:** console → each shared tool → **Who can use it** → for every browser: **Sign in to the
      tool**, sign in with the company account, **Done**. Once per browser.

### 4b. Or: the company browsers on Swangz's own computer — nothing rented
Instead of the workspace server, a strong Windows PC or Mac that stays on can run the browsers. One place
at a time; switch any time in the console (Settings → Company browsers). See `deploy/WORKSPACE.md` →
"Where the browsers run".
- [ ] **You:** on that computer install Docker Desktop and Python 3, copy the repo across.
- [ ] **You:** console → Settings → Company browsers → the Windows PC (or Mac) → **Connect…**, and run the
      command it shows there. Then sign its browsers in on the same page, and **Use this one**.
- [ ] **You (for staff outside the office):** a free Cloudflare account → Realtime → TURN → create a key;
      put `GATEWAY_TURN_CLOUDFLARE_KEY_ID` and `GATEWAY_TURN_CLOUDFLARE_TOKEN` in the gateway's `.env`.
      **Claude:** restart the gateway. First 1,000 GB a month free, then $0.05/GB.
- Needs: the computer on, awake and signed in; ~2–3 Mbps of *upload* per person in a browser.

### 5. Roll out to staff
- [ ] **You:** add staff (People → Add; `@swangzavenue.com` emails), assign tools, send each their sign-in
      link — or let them use Continue with Google once step 1's Google work is done.
- [ ] **You:** install the browser extension on staff machines (`extension/README.md`) — it keeps shared
      tools to whoever holds the turn and signs browsers out when a turn ends.

### 6. Keep it safe
- [ ] **You:** turn on Hetzner backups for the gateway server (+20%, about $1/month) — `data/gateway.db`
      is the record.
- [ ] **You:** change the shared demo password, and revoke the Netlify token in Netlify → User settings →
      Applications if this PC is ever handed on.

### 7. The V2 control plane — free, a morning's work
- [ ] **You:** Settings → Console users — give each admin the narrowest role that fits (operations,
      security, billing or viewer); keep owners to one or two.
- [ ] **You:** Settings → Locations — name the office network (and any VPN), so requests from it say so exactly.
- [ ] **Claude (or whoever runs the server):** download a free offline location table (DB-IP Lite city, CSV)
      and run `python3 -m gateway geoip-import FILE --source "DB-IP Lite <month>"`; repeat monthly.
- [ ] **You:** Govern → Models — register the models Swangz pays for: approve the everyday ones, restrict the
      most expensive to the teams that need them, disable anything retired.
- [ ] **You:** Settings → Media rates — enter ElevenLabs' per-character and Higgsfield's per-credit price, so
      voice, image and video stop showing as unpriced.
- [ ] **You:** Govern → Policies — write the company's rules only after trying each on **Simulate**; start with
      none, and add them as needs appear.
- [ ] **You:** Settings → Access & records — set retention per category (records, bodies, website visits, opens;
      the audit log at least a year) and tell staff (it shows on their privacy page automatically).
- [ ] **Optional:** an SMTP account for alerts (`GATEWAY_SMTP_HOST`, `GATEWAY_NOTIFY_TO`, … in `.env`) so
      high and critical notifications reach someone when nobody has the console open.
- [ ] **Read** `docs/SECURITY.md` → *Limits*: back up `data/gateway.db` off the server, and keep shell access
      to the server to as few people as possible — the audit log is only as safe as the box it lives on.

## What it costs a month

Infrastructure (approximate, before VAT; Hetzner raised prices in mid-2026 — check when ordering):

| Item | Monthly |
|---|---|
| Gateway server — Hetzner CX22 (2 vCPU, 4 GB) | ~$4.60 |
| Workspace server — Hetzner CX32 (4 vCPU, 8 GB, 3–4 people at once) | ~$8.50 |
| Backups for the gateway server (optional, +20%) | ~$1 |
| Netlify (free plan), Neko, Docker, Caddy, the gateway itself | $0 |
| Domain — swangzavenue.com is already Swangz's; `ai.` and `workspace.` cost nothing | $0 |
| **Infrastructure total** | **about $14** |

Need more people on shared tools at once? A CX42 (16 GB, 6–8 browsers) is ~$16.50 instead of the CX32.
**About 20 at once** (many tools, `max_running: 20`) needs ~64 GB and 16 threads: Contabo Cloud VPS 50
(16 shared vCPU, 64 GB) is ~€37; a Hetzner AX42 dedicated server (8 cores/16 threads, 64 GB) is smoother
under load and costs more, plus a setup fee. The office internet needs ~2–3 Mbps per person on a browser.
Cheaper RAM: Contabo's Cloud VPS 10 (8 GB) is ~$5.50, with a slower network port. Pricier: DigitalOcean
is $6 (1 GB) and $48 (8 GB).

**The AI subscriptions are the real cost**, and they're Swangz's choice of plans. From the catalog's list
prices: ChatGPT Plus $20 or Team $30 a seat; Claude Pro $20; Midjourney $10–60; Canva Pro $15 (Teams
$10 a seat); Suno $10–30; Runway $15–35; Perplexity Pro $20; ElevenLabs $6–99.

Example — one shared account each of ChatGPT Plus, Claude Pro, Midjourney Standard, Canva Pro and Suno
Pro is $95/month in subscriptions, plus ~$14 of servers: **about $110/month**. With seats instead,
subscriptions scale with the number of people (e.g. ChatGPT Team for 5 people is $150 on its own).

Sources for server prices (2026): [Hetzner pricing](https://deployhandbook.com/pricing/hetzner),
[Hetzner review](https://bestusavps.com/reviews/hetzner/), [Contabo pricing](https://onedollarvps.com/pricing/contabo-pricing),
[DigitalOcean pricing](https://www.costbench.com/software/cloud-infrastructure/digitalocean/).
