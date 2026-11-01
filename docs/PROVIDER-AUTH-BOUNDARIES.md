# Provider authentication boundaries

What Swangz AI Hub may and may not do to get a person into an AI provider. Decision: D-007 in
[DECISIONS.md](DECISIONS.md). Owner: @Sentinel; the per-tool verification column is maintained by @Probe in
`docs/PROVIDER-COMPATIBILITY.md`. Product principle: one Swangz login unlocks the person's authorised Swangz
workspace; it does **not** pretend every vendor shares one login or one bill.

## The five patterns (`tools.signin`)

| Pattern | Who authenticates the person to the vendor | What the Hub holds | What the Hub does | Attribution |
|---|---|---|---|---|
| `api` | nobody — the gateway authenticates to the provider | company provider key, server env only | proxies allow-listed endpoints, adds the key, records | the person's gateway key |
| `sso` | the vendor, via Google Workspace (SAML/OIDC) | nothing from the vendor | `/go/<tool>` checks access, logs, redirects to the vendor's SSO link | vendor's own logs + launch record |
| `seat` | the vendor, with the person's own invited seat on the work email (vendor MFA) | nothing | access gate + launch log | vendor seat = the person |
| `shared` | an admin, by hand, once, inside a company browser (Neko) | per-turn Neko sign-in only; never the vendor password | one turn per person; company browser per turn; extension signs out at turn end | turns matched to vendor history |
| `own` | the person, with their own account | nothing | access gate + launch log | the person |

## Hard boundaries (all components: gateway, app, extension, Workspace Agent)

Never, for any provider:
1. Ask for, receive, store, log or type a vendor password (no credential injection — CLAUDE.md, three refusals).
2. Read, copy or export vendor cookies, session tokens or OAuth tokens — from staff browsers, company browsers
   or devices. The Neko Chromium policy keeps devtools, password manager and `chrome://` pages off
   (`workspace_agent/agent.py:86-97`); keep it that way.
3. Read coding-agent credential stores: `~/.claude/.credentials.json`, macOS Keychain items of Claude Code,
   `~/.codex/auth.json`, or any browser profile. The app edits only `~/.claude/settings.json` and
   `~/.codex/config.toml` (managed devices, marked lines) — and after D-001 no secret goes into them.
4. Relay, prompt for, or bypass MFA/2-step codes, captchas or bot checks.
5. Route a consumer subscription (ChatGPT Plus/Pro, Claude Pro/Max, Midjourney personal, …) through the gateway
   or hand one person's subscription to others. Coding agents on the gateway use the **company API key**, never a
   subscription login.
6. Use `shared` on a plan whose terms are for a single person. `shared` requires an admin attestation that the
   plan permits organisational/multi-user use (`tools.shared_terms_ref`, F-12); otherwise use `seat`.
7. Send a provider key to any client. Provider keys exist only in the gateway's environment.

## Provider API integrations (gateway-held keys)

| Provider | Dialect / header the gateway adds | Client presents | Key scoping recommended (Arnold) | Never allowed through the gateway |
|---|---|---|---|---|
| Anthropic | `x-api-key` | gateway key as `x-api-key` / Bearer (`apiKeyHelper` after D-001) | a dedicated workspace key with a spend limit | Admin API (`/v1/organizations/*`), files/batches unless allow-listed |
| OpenAI | `Authorization: Bearer` | gateway key | a project key with only the needed model permissions | admin/org endpoints, fine-tuning, files unless allow-listed |
| ElevenLabs | `xi-api-key` | gateway key as `xi-api-key` | a key restricted to the needed endpoints/quota | voice cloning/admin endpoints unless allow-listed |
| Higgsfield | `Authorization: Key id:secret` | gateway key | per-environment credentials | account management |

The endpoint allowlist (`proxy.ALLOWED_ENDPOINTS`) is the enforcement; any widening is critical work (G2 note
from @Sentinel + test). Leak response for a provider key: rotate at the vendor, update env, restart; the
gateway's per-provider switch-off (Settings → Emergency) stops traffic meanwhile.

## Coding agents

| Agent | Supported | How it authenticates | Not supported |
|---|---|---|---|
| Claude Code | yes | `ANTHROPIC_BASE_URL` = gateway; key via `apiKeyHelper` → `swangz key --for claude-code` (managed) or child env (scoped run) | signing Claude Code in with a Claude.ai subscription and pointing it at the gateway; reading its OAuth credentials |
| Codex | yes | `model_providers.swangz` with `env_key = SWANGZ_AI_KEY`; key from the keychain at shell start (Unix managed) or child env (`swangz run codex`) | ChatGPT sign-in (`auth.json`) through the gateway |

@Probe verifies against the deployed versions: Claude Code `apiKeyHelper` semantics (headers sent, refresh
TTL) and whether Codex offers a command-based credential (would remove the environment variable).

## Website tools (`sso` / `seat` / `shared` / `own`)

The catalog (`gateway/catalog.py`) gives each tool a default `signin`; admins change it per tool. For each website tool @Probe records in `PROVIDER-COMPATIBILITY.md`: whether the
vendor offers SSO on Swangz's plan, whether seats are invitable by email, whether the plan permits shared
organisational use, whether the vendor enforces MFA, and the date checked. A tool is marked **supported** only
with that row filled; until then it stays `own` or `seat`. Do not record vendor capabilities from memory.

## Desktop app rules (G2 requirements for @Prism)

- The app never shows a vendor login form, never embeds a vendor site in a web view, and never handles vendor
  passwords. "Open" goes through `/go/<tool>` in the person's default browser (or, after D-008, a handoff into
  the web app first).
- The app sends its key only to the pinned server origin (F-06) and only in `Authorization`/`x-api-key` to the
  gateway; never in URLs, never to artefact hosts.
- The only provider-facing traffic from the device is the coding agents' own, aimed at the gateway.
