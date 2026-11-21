# Provider seat, access and billing matrix (modes A to E)

Read at main `13966ba`, 21 Nov 2026. This page brings together facts that are already in the repository. It adds
no new vendor research. Sources: `docs/PROVIDER-COMPATIBILITY.md` (sections 1, 3, 4, 6.3, 7), the Amendment 01
section of `CLAUDE.md`, `docs/DECISIONS.md` D-012 to D-018, `gateway/registry.py` and `docs/SECURITY.md` "Limits".
Where those disagree with this page, they win.

Labels are the ones in `docs/PROVIDER-COMPATIBILITY.md` section 1: **REPO** (read from code), **DOC-V** (Probe read
the vendor page), **DOC-R** (a reviewer read it), **INFERENCE**, **UNVERIFIED**. No row is **LIVE**: no mode has been
tested against a real provider.

## 1. The five modes

| Mode | What it is | `tools.signin` | Who pays | Who holds the account |
|---|---|---|---|---|
| **A** | Company API credential through the gateway | `api` (and the `dev` tools) | Swangz, one bill per provider key | Swangz. The key lives only in the server environment (REPO) |
| **B** | Vendor SSO with the company identity | `sso` | Swangz (vendor business plan) | The person, through the company identity provider |
| **C** | An assigned company subscription seat | `seat` | Swangz, one bill | The person: one seat, one person, invited to the work email |
| **D** | The person's own provider account | `own` | The person (holder and payer are recorded separately, D-012) | The person |
| **E** | A company-held shared account, handed out in turns | `shared` | Swangz | Swangz. The turn holder works in a company browser and never sees the password |

The provider-account registry (`gateway/registry.py`) records only individual accounts and seats today
(`ROUTES_OPEN = ("individual", "seat")`). Its `api` and `enterprise` kinds exist as enum values only, and no route
can write them (REPO). An individual account has no console entry at all (Sentinel F1).

## 2. Mode by tool category

The catalogue's seed carries no sign-in mode per tool. A new install gives every tool `signin = seat`, and an admin
sets the real mode. Which tools are set to `shared` in live data is **UNVERIFIED**, because the live database is out
of bounds (`docs/PROVIDER-COMPATIBILITY.md` 6.3).

| Category (catalogue `kind`) | Tools | Modes (code support, limited by vendor terms) | Notes |
|---|---|---|---|
| `api`: the four provider routes | chatgpt, claude, higgsfield-ai, elevenlabs | A through the gateway, plus B, C or D for the web side. E: not allowed per vendor terms (`docs/PROVIDER-COMPATIBILITY.md` §5; DOC-V for Claude) | Mode A is a proposal until the vendor confirms it in writing (§4) |
| `dev`: coding agents | claude-code, codex | A only (assignment-only, no host to gate) | Never route a consumer plan (Claude Pro/Max, ChatGPT plan) through the gateway. The Claude Code legal page forbids it (DOC-V). Codex's plan sign-in rule is UNVERIFIED |
| `site`: website tools with a company route | the 38 `site` IDs listed in `docs/PROVIDER-COMPATIBILITY.md` 6.3 | B, C or D at the launch level. E only where the vendor allows it; otherwise UNVERIFIED, not allowed | B needs the vendor's SSO set up in the vendor's admin console, and C needs the seat assigned there. **Neither is verified for any tool** |
| `site`: no company sign-in route confirmed | midjourney, suno, udio | D | Midjourney documents no SSO and no seats. Suno and Udio are UNVERIFIED |
| `site`: retired at the vendor | sora, dall-e | none to rely on | Launch records continue while the entry is active. Archiving is Arnold's call (DALL-E: `docs/ARNOLD-ONLY.md` item 4; Sora: `docs/PROVIDER-COMPATIBILITY.md` §7 decision 1) |

## 3. What Swangz can legitimately observe

Observation profiles from `docs/PROVIDER-COMPATIBILITY.md` 6.3 (REPO, tested against the fake upstream only):

| Mode | Profile | Recorded | Never recorded |
|---|---|---|---|
| A | P-API | person, key, provider, path, client name from the User-Agent, model, status, outcome, duration, tokens, and cost labelled *estimated* or *unpriced* | Prompt and reply text: not stored by default, and only the trust area can read it (D-023, #249) |
| B, C | P-L | the launch (`/go/<tool>`: tool, person, time, outcome, address, user agent) and access-level gate events (which tool, when, how long) | Anything inside the vendor product: prompts, files, spend, credits. Only the vendor's admin reports show that, and none is imported |
| D | P-D | the launch only | Spend, content and the identity used inside the vendor account. Spend cannot be attributed |
| E | P-E | turn holder, turn window, turn id, plus the launch | Vendor-side activity. It is matched to a person by time window only |

Rules that apply to all modes:
- The Hub's Google sign-in signs people in to the Hub only. `/go/` records the launch and redirects; it does not sign
  the person in to the vendor (REPO).
- Website monitoring is an access gate plus access-level logging, never page content or keystrokes (`CLAUDE.md`).
- The gateway never stores, shares or types a provider password. Credential injection is ruled out (`CLAUDE.md`).
- Revoking access in the Hub does not end a session at the provider (risk R-4 in `docs/RISK-REGISTER.md`).
- Per-person cost exists only in gateway records, labelled estimated or unpriced. Invoice import is not built
  (`docs/SECURITY.md` "Limits").

## 4. Caveats

**The shared-turn caveat (mode E).** Turns make attribution real in our records (REPO), but most vendors' terms
forbid one login used by several people. Claude's seat policy, read by Probe, says: "Users can't share login
credentials or let others use their account" and the seat "isn't designed for rotating one seat among several active
users" (DOC-V). Keep E off for a tool unless Arnold approves that tool **and** the vendor's plan or written permission
allows it. Where no rule is confirmed (Suno, Udio, Copy.ai, HeyEddie, Make, Zapier, n8n, Social Insider, CapCut,
Loom), the answer is UNVERIFIED, not "allowed". Amendment 01 also says: never turn an individual's subscription into a
shared company login.

**Mode A is a proposal.** That one company key behind an internal gateway is allowed for employees is INFERENCE from
the Anthropic, OpenAI and ElevenLabs terms. Whether it counts as "intermediating" for Claude Code is not settled by
Anthropic's page. Written confirmation from each vendor is Arnold's to request (`docs/PROVIDER-COMPATIBILITY.md` 7,
decision 3).

**No usage or quota API is assumed** for modes B to E. Values that a vendor does not document stay unavailable or
manually entered, with their source and time (D-018).

**Existing subscriptions stay.** API and Business/Enterprise plans are optional. Nothing here moves anyone to API
billing (Amendment 01, section 7).
