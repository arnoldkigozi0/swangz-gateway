# Directive gap map: deliverables 1 to 12 against main

Read-only audit by Probe on main `13966ba`, 21 Nov 2026. Nothing was installed or run on a real device or with a real
provider login. DONE means the thing exists on main and has a test or a CI job; it does not mean tried by a person.

**Not covered:** the text of deliverables 1, 2, 3, 7, 8 and 10 of the final directive did not reach Probe (the
handoff named only 4, 5, 6, 9, 11 and 12). They are marked NOT MAPPED, not guessed. The 17 Nov sprint list
(`docs/RELEASE-EVIDENCE.md`, deliverables 1 to 10 of that brief) is the nearest evidence and is not the same list.

| # | Deliverable | Status | Evidence on main | Gap and next step |
|---|---|---|---|---|
| 1, 2, 3, 7, 8, 10 | not received | NOT MAPPED | none | Chief to paste the text; Probe maps it in minutes |
| 4 | Separate Open Web / Open Desktop / Run CLI / Use Gateway API for Codex and Claude Code | **PARTIAL** | `catalog.MODES = web, desktop, cli, api, mobile`, column `tools.modes` (schema v29, #304) and an admin checkbox group (`admin-govern.js:1102`) record how a tool is used. CLI exists as `swangz run <tool>` (`swangz_client/cli.py`). The gateway key flow is the "Connect" guide | **No staff-facing split.** A dev tool shows one **Open** (the product page, e.g. `claude.com/claude-code`) and one **Connect**. Nothing reads `modes`: not `/go/`, not `/device/open`, not the staff Tools page, not the app manifest. `modes` is also empty on all 49 seeded rows. Build: seed modes for claude-code and codex, return them in the tool card, and show up to four labelled actions (Open web, Open desktop app, Run in terminal, Use the gateway API), each with its own audit entry (`launch` with `mode`). Needs an official-docs check of each desktop app (Probe) before labelling anything "Open desktop" |
| 5 | Domain configurable, not hardcoded; independent Google OAuth | **PARTIAL** | `GATEWAY_COMPANY_DOMAIN` is read in `gateway/config.py:208`, used for email checks (`:146`, `:160`) and the sign-in hint (`:163`). Google client id, secret and return address are separate env vars (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `GATEWAY_WEB_URL`; `google.py:38-40`), with `GATEWAY_REQUIRE_FIXED_RETURN=1` | Four places still hardcode the domain: (a) `gateway/preflight.py:71-74` **fails** any value other than `swangzavenue.com`, so a different domain cannot pass preflight; (b) `gateway/hub_api.py:387` and `gateway/hub_identity.py:4,21` print "Exact @swangzavenue.com" policy text; (c) `OWNER_EXCEPTIONS` / `email_exceptions` are two fixed Gmail addresses in `config.py:111`, not env or data; (d) UI hints and placeholders in `admin-govern.js:227,1096,1212`, `admin-guide.js:230`, `admin-money.js:396`, `extension/popup.js:33`, and example hosts in `deploy/` and `workspace_agent/*.example.json` (examples, harmless). Forge has the audit task. Add a test that a second domain passes preflight and sign-in |
| 6 | Provider-seat, access and billing matrix for modes A to E | **PARTIAL** | Facts exist but are scattered: sign-in modes `sso/seat/shared/own/api` (`catalog.SIGNIN`), per-tool facts in `docs/PROVIDER-COMPATIBILITY.md` (448 lines, sourced), owner step in `docs/RELEASE-OWNER-CHECKLIST.md` section 5, shared-turn caveat in `docs/SHARED-TURNS-THREAT-NOTE.md` | **No matrix document yet** (`docs/PROVIDER-SEAT-MATRIX.md` does not exist); Anvil is writing it. Probe check on it: every cell cites PROVIDER-COMPATIBILITY or is marked UNVERIFIED, and A to E must be defined in the directive's words (not received) |
| 9 | Linux and PWA readiness evidence | **PARTIAL** | Linux: `build-app.yml` builds and smoke-tests the packaged app under Xvfb on Linux; `docs/CLIENT.md` names Linux keyring (`secret-tool`), autostart and Chrome policy folders; managed-workspace demo ran on Linux headless (#236, `RELEASE-EVIDENCE.md:86`); Chrome pack bypass jobs run on ubuntu with Google Chrome. PWA: `tests/test_pwa_files.py`, `tests/browser/pwa.cjs` (in `checks.yml`), `docs/MOBILE-READINESS.md` with a five-step phone checklist | **No real-device evidence for either.** `MOBILE-READINESS.md` says "Not run by the team: no phone"; Android Chrome install and iPhone Safari are Not run. Linux: no real-desktop run, no `.deb` or AppImage built from a tag (`CLIENT.md:423` says CI builds them "from tags"; none cut), and the Linux keyring path was never run on a real desktop. PWA icon gap: no PNG icons (apple-touch-icon 180, manifest 192/512, maskable) per `MOBILE-READINESS.md:34`. Next: Forge or Prism adds the PNG icons (small PR); Arnold runs the phone checklist (`ARNOLD-ONLY.md` item 9) |
| 11 | Blocker and risk register | **PARTIAL** | Pieces: `ARNOLD-ONLY.md` (the one owner list), `RELEASE-EVIDENCE.md` blockers, `SECURITY.md`, threat notes (`SHARED-TURNS`, `W3`, `W4`), `GO-LIVE-ASKS.md` | **No single register** (`docs/RISK-REGISTER.md` does not exist); Anvil is writing it. Probe check on it: each risk has an owner, a status, and a source link; the unverified ones from PROVIDER-COMPATIBILITY are carried over, not dropped |
| 12 | Owner deploy instructions | **PARTIAL** | `deploy/setup-gateway-server.sh`, `deploy/setup-workspace-server.sh`, `Caddyfile`, `firewall.sh`, service and backup timers, `docs/HUB-DELIVERY.md`, `docs/SERVER-DAY.md`, `docs/SERVER-REHEARSAL.md`, `docs/RELEASE-OWNER-CHECKLIST.md` | Steps are spread over five documents and `preflight` has never run against a real server (`ARNOLD-ONLY.md` item 10: "Nothing has been run on a server"). Build: one short owner runbook, in order (rent server, DNS, setup script, `.env`, preflight, Google client, first admin, health check, backup restore check), each step saying what success looks like. Docs only |

## Smaller findings from the journey checks

- Seedance, claude-code and codex are refused by the app's `check_url` for different reasons: seedance by design (opens
  inside Higgsfield AI), claude-code and codex because they have no website sign-in hosts. If deliverable 4 makes
  "Open web" a real action for them, their hosts must be listed first, or the action will be refused.
- Real-journey run on main (staff sign-in, `/go/` for 49 tools, launch records, revoke on the next request, sign-out) found
  no break. See the thread record of 21 Nov.

## Suggested assignment order

1. Deliverable 4 (largest gap, user-visible): Forge backend (modes in the tool card and audit), Prism UI. Probe checks official docs first.
2. Deliverable 5 (a): preflight accepts a configured domain; test with a second domain. Forge (already assigned).
3. Deliverables 6 and 11: Anvil (already assigned). Probe reviews both.
4. Deliverable 12: one owner runbook (docs only).
5. Deliverable 9: PNG icons; the rest is Arnold's real devices.
