# Swangz AI Hub — security review (G2, initial)

Reviewed: 2 Nov 2026, `main` at `ba82a2a`. Method: source reading (read-only) against OWASP ASVS 4.0.3 L2,
MASVS (for the PWA and the desktop app where it applies), STRIDE per trust boundary
([ARCHITECTURE-REVIEW.md §4](ARCHITECTURE-REVIEW.md)). Nothing was executed against a live system.
Test suite: **Not run** by this review; no baseline recorded yet in `docs/AGENT-PROGRESS.md`.

Severity: Critical / High / Medium / Low / Info. "Blocks" says which gate the fix must land before.

## What is already sound (keep it)

- Provider keys exist only server-side; client auth headers are stripped before forwarding (`proxy.py:20`);
  endpoint allowlist per dialect.
- Staff keys, sessions, device codes stored as SHA-256 of 256-bit secrets; constant-time compares.
- Deterministic policies that only remove access and fail closed; area-based console authorisation enforced
  in one dispatcher (`admin.py:81`) with refusals audited.
- Console cookie SameSite=Strict + custom header; strict CSP, `frame-ancestors 'none'`; output built with
  `textContent`; CSV formula guard.
- Device code flow: single-use, 15 min, hashed poll secret, CSRF bound to session+code, approver sees the
  requesting address, ten-device cap, audited.
- Package unpack: checksum, no `..`/absolute/drive/backslash names, no links, size/count caps, header-lie
  check, staging then rename (`bundles.py:29-91`).
- Company browsers: no vendor password stored by the gateway; per-turn Neko sign-ins; Chromium policy disables
  devtools, password manager and `chrome://settings` (`workspace_agent/agent.py:86-97`).
- The client never reads Claude/Codex credential files (`~/.claude/.credentials.json`, `~/.codex/auth.json`).
- Exact identity rule in one place (`config.py:127`).

## Findings

| ID | Sev | Area | Affected | Blocks |
|---|---|---|---|---|
| F-01 | High | Console authentication | `gateway/admin.py:154-179` | G8 |
| F-02 | High | Device credential exposure | `swangz_client/agents.py:106,194`, `core.py:54,100` | G3 |
| F-03 | High | Supply chain / distribution | `gateway/enroll.py:234-249,463-499`, `core.py:323-337` | G4 |
| F-04 | High | Session scope / privilege escalation | `gateway/staff.py:66-79,463-480`, `enroll.py:376-445` | G8 |
| F-05 | Medium | Device-code phishing | `gateway/enroll.py:128,134-135,402-418`; `core.py:244` | G8 |
| F-06 | Medium | Key redirection / config injection | `swangz_client/core.py:266,328`; `agents.py:139-149`; `enroll.py:179` | G3 |
| F-07 | Medium | Federated identity | `gateway/google.py:118-131` | G8 |
| F-08 | Medium | Backup confidentiality | `gateway/backup.py:94-102` | G9 |
| F-09 | Medium | Build supply chain | `.github/workflows/build-app.yml` | G5 |
| F-10 | Medium | Token lifecycle | `staff.py:20,460`; `enroll.py` (device keys) | G8 |
| F-11 | Medium | Workspace host trust | `gateway/workspace.py:218-233` | G8 |
| F-12 | Medium (policy) | Shared-account exposure | `gateway/turns.py`, `catalog` `signin='shared'` | G9 |
| F-13 | Low | Device auth availability | `enroll.py:189-196`; `core.py:193` | — |
| F-14 | Low | Windows unpack names | `swangz_client/bundles.py:29-33` | G4 |
| F-15 | Low | Session revocation | `gateway/admin.py:200-210` | G8 |
| F-16 | Low | Credential in URL | `workspace_agent/agent.py:414-422` | — |
| F-17 | Info | OIDC hardening | `gateway/google.py:85-86` | — |

### F-01 High — console sign-in has no second factor
**Evidence.** `admin.login` accepts username + password and issues a 12-hour owner-capable session
(`admin.py:154-179`). Throttle is per IP only (`security.LoginThrottle`, in memory, reset on restart), so
distributed guessing against one account is not limited; ASVS 2.2.1/2.2.3, 2.8.
**Failure scenario.** An owner reuses a password breached elsewhere; an attacker signs in from many addresses
and holds every area (keys revoke, policies, packages grants, exports with prompts).
**Remediation.** In production, console sign-in **must** go through Google (Workspace enforces 2-step) — add a
setting `console_password_login` default off when Google is configured, with a break-glass owner path from the
server shell (`python3 -m gateway add-admin`) only. If password login stays, add TOTP (stdlib HMAC, RFC 6238)
for every console role. Add a per-account failure counter alongside per-IP. Tests: password login refused when
disabled; break-glass works; per-account lockout.

### F-02 High — the device key is copied out of its protected store
**Evidence.** Managed Claude Code: `agents.py:106` writes `ANTHROPIC_AUTH_TOKEN: <key>` into
`~/.claude/settings.json`, contrary to `agents.py:11`. Managed Codex on Windows: `persist_env` runs
`setx SWANGZ_AI_KEY <key>` (`agents.py:194`) — the key is on a process command line, stored plaintext in
`HKCU\Environment` and inherited by every process the person starts. Storage: `device.key` 0600
(`core.py:100`); on Windows `os.open` mode is ignored and the folder is `%APPDATA%` **Roaming**
(`core.py:54`), which roams to profile servers. On Unix the profile line re-reads the file (acceptable but
puts the key into every login shell's environment).
**Failure scenario.** A developer commits or syncs dotfiles (common for `~/.claude`), or a crash dump/telemetry
of any process captures the environment → a working company key with the person's name on the bill.
**Remediation.** D-001 + D-002: OS keychain; Claude Code via `apiKeyHelper` → `swangz key`; no `setx`; data in
`%LOCALAPPDATA%`; migrate and scrub existing copies. Tests in D-001.

### F-03 High — every distributed artefact is trusted only because the gateway says so
**Evidence.** Package sha256 is computed at publish on the server and delivered by the same server in the
manifest (`enroll.py:279,491`); the app checks bytes against it (`core.py:330`). The extension zip is built
live from the server's working tree (`enroll.py:236`). No signature independent of the gateway exists; the app
itself is unsigned and has no update path yet.
**Failure scenario.** Anyone who can write to the gateway host (or its `extension/` checkout, or `data/packages`
plus a DB row) ships executable files to every granted device and a modified extension to every browser that
loads it; with self-update built the same way it would ship a new app.
**Remediation.** D-003 (signed releases, offline key) and D-004 (signed packages and extension). The gateway
stays a distributor, never the signer. Tests: wrong key, tampered byte, stale manifest, downgrade — all refused.

### F-04 High — the extension token is a full staff session and can approve devices
**Evidence.** `extension_login` (`staff.py:463-480`) mints a 30-day row in `staff_sessions`. `current_person`
(`staff.py:66-79`) accepts that token as `Bearer` on every `/api` route. `/device` (`enroll.page`, `server.py:366`)
also calls `current_person`; with no cookie, the CSRF value is `HMAC(sha256(""), code)` (`enroll.py:354-356,405`),
which the bearer holder receives from the GET and replays on the POST. The same token can call `POST /api/keys`
(`staff.py:581`).
**Failure scenario.** Token copied from a shared Chrome profile or a malicious extension → attacker approves
their own device code as the victim (or creates a key) → durable gateway key that survives the token's expiry
and a password change.
**Remediation.** Session kinds (D-008/D-010): `primary` (cookie, password/Google), `extension` (only
`/api/gate/*`, `/api/extension/*`), `handoff` (no device approval, no key creation, no password change).
`/device` and `/api/keys` require a primary cookie session; refuse bearer there. Migration: new column on
`staff_sessions` (append-only). Tests: extension token on `/device`, `/api/keys`, `/api/password` → 401/403.

### F-05 Medium — device-code phishing is easier than it needs to be
**Evidence.** The app opens `verification_uri_complete` (`core.py:244`, `enroll.py:135`), so a link alone
pre-fills an attacker's code; the "Device name" shown to the approver is attacker-chosen free text
(`enroll.py:128,402`); there is no warning when the approver's address differs from the requester's, and no
notice to the person after a device joins. Existing controls (warning text, address shown, 15 min, single use)
are good but rely on the person reading carefully.
**Failure scenario.** "IT here — approve your laptop: https://hub/device?code=…" with the device named
"Swangz IT – your laptop" → victim clicks Approve → attacker holds a key.
**Remediation.** D-009: no prefilled code from links (type it); label prefixed "Name it gave itself:"; prominent
mismatch banner when approver and requester addresses differ; 10-minute codes; post-enrolment notice in Updates
(+ email when SMTP is set) with a one-click "This wasn't me" that revokes; new devices appear in Needs attention
for 24 h.

### F-06 Medium — a manifest can redirect the key or inject Codex configuration
**Evidence.** The app stores `out["server"]` from the token response over what the person typed (`core.py:266`),
and writes `install["base_url"]` with the key into tool config without checking its origin (`core.py:328`,
`agents.py:106`). `codex_block`/`codex_overrides` interpolate `base_url` into TOML unescaped (`agents.py:139-149`),
so a crafted value can add tables such as an MCP server `command` (code execution when Codex starts).
The server side derives `server` from the Host header when `GATEWAY_PUBLIC_URL` is unset (`server.py:212-224`).
**Failure scenario.** Misconfigured proxy or a compromised gateway turns every enrolled laptop into a key
exfiltration or code-execution point.
**Remediation.** Pin the origin the person entered; ignore a differing `server`; require
`base_url` to be same scheme+host+port as the pinned server and match `^https://host(:port)?/[a-z0-9-]+(/v1)?$`;
emit TOML strings with proper escaping (or refuse any `"`, `\`, newline). Make `GATEWAY_PUBLIC_URL` mandatory
when `GATEWAY_FORCE_HTTPS` is on. Tests: foreign `base_url`, quote/newline injection, differing `server`.

### F-07 Medium — Google sign-in accepts any verified Google account on the work address
**Evidence.** `_valid` checks `iss`, `aud`, `exp`, `nonce`, `email_verified` (`google.py:118-131`) but not `hd`.
A consumer Google account can be registered on an `@swangzavenue.com` address and keeps working after the
mailbox is removed, outside Workspace 2-step and offboarding.
**Remediation.** For `@swangzavenue.com` identities require `hd == "swangzavenue.com"`; the two approved owner
exceptions (gmail.com) have no `hd` and stay as they are — do not widen the rule. Tests: domain email without
`hd` refused; owner exceptions unchanged.

### F-08 Medium — off-server backups are plaintext
**Evidence.** `backup.py:94-102` rsyncs the compressed database (prompts, bodies, audit, hashes) as is.
**Remediation.** Encrypt before it leaves the host to a public key whose private half is offline (age or
`openssl cms`/`smime` with a recipient cert — `openssl` is already on the server, so no new dependency).
Needs Arnold's approval (deploy change). Test: restore drill from an encrypted copy.

### F-09 Medium — the build chain is not pinned and artefacts are unsigned
**Evidence.** `build-app.yml`: `pip install pyinstaller` with no version or hashes; actions pinned by tag, not
commit SHA; artefacts unsigned, no provenance.
**Remediation.** `pip install --require-hashes -r packaging/requirements-build.txt`; pin actions to SHAs; build
on tags; produce SHA-256 list + build attestation; sign per D-003/D-005 in a protected environment.

### F-10 Medium — long-lived credentials without idle expiry or rotation
**Evidence.** Staff sessions 14 days absolute, no idle timeout, no rotation (`staff.py:20,101-107`); extension
sessions 30 days (`staff.py:460`); device keys never expire.
**Remediation.** Staff: idle timeout (e.g. 3 days) + absolute 14 days. Devices: revoke after 60 days without a
check-in; rotation endpoint (D-002). "Sign out everywhere" for staff.

### F-11 Medium — a computer key can choose where staff are sent
**Evidence.** `workspace.hello` stores any `https://` URL the computer reports (`workspace.py:218-233`); turn
holders are redirected to it.
**Remediation.** Restrict to an allowlisted suffix set by an admin (e.g. `*.trycloudflare.com` or a named host),
show the URL in Settings with last change audited, alert on change.

### F-12 Medium (policy) — shared accounts depend on vendor terms
**Evidence.** `signin='shared'` hands one vendor account to many people by turns. The implementation is sound
(no password held, attribution by turns), but if a tool's plan is a single-person licence this is the
"unofficial subscription sharing" the mission excludes, and vendors suspend accounts for it.
**Remediation.** Per-tool admin attestation "plan permits organisational/shared use" with a reference, required
before `shared` can be selected; otherwise `seat`. See PROVIDER-AUTH-BOUNDARIES.md.

### F-13 Low — device authentication can be denied for a whole office; unknown key wipes
`devauth` throttle is per IP (`enroll.py:189-196`), so garbage from one NAT address blocks colleagues; `401
device_unknown` (e.g. after restoring an older database) makes every app remove everything (`core.py:193`).
Remediation: throttle by key id + IP; treat `device_unknown` as "ask the person" and remove only on
`device_revoked`.

### F-14 Low — Windows-specific unsafe names are accepted
`check_name` does not refuse `:` (NTFS alternate streams), reserved names (`CON`, `NUL`, …) or trailing dots/
spaces. Remediation: refuse them on every platform (packages must be portable). Tests with each.

### F-15 Low — changing a console password leaves other sessions alive
`change_password` (`admin.py:200-210`) does not delete other `admin_sessions`. Remediation: delete all except
the current one; audit the count. ASVS 3.3.3.

### F-16 Low — per-turn Neko password travels in a URL
`agent.py:414-422` builds `?usr=…&pwd=…`; it lands in browser history. Mitigated: per turn, deleted on release,
`Referrer-Policy: no-referrer`. Remediation if Neko allows: a short-lived one-time login token instead.

### F-17 Info — OIDC defence in depth
No PKCE (confidential client, acceptable); ID token not signature-checked but received directly from Google
over TLS (acceptable per OIDC Core 3.1.3.7). Add PKCE (S256) — stdlib only.

## STRIDE summary of the areas under G2

| Threat | Credential storage | Self-update | Provider auth |
|---|---|---|---|
| Spoofing | phished device code (F-05) | fake update server | consumer Google account (F-07) |
| Tampering | settings file edits | swapped binary/manifest (F-03) | manifest base_url (F-06) |
| Repudiation | key used from copied file — still attributed to the person | — | shared accounts without turns |
| Information disclosure | key in dotfiles/env (F-02) | — | provider key on server only (sound) |
| Denial of service | `device_unknown` wipe (F-13) | bad update bricks app → rollback (D-003) | provider switch-off (exists) |
| Elevation | extension token → device approval (F-04) | update runs as user, never as admin | device key ≠ browser/console session (D-008) |

## Required abuse-case tests (to be written by the builders, reviewed at G8)

1. Extension bearer token cannot approve `/device`, create keys, or change password.
2. Handoff session cannot approve devices or reach `/admin/api`; revoking the device ends it.
3. Manifest with foreign `base_url`, TOML-breaking `base_url`, or differing `server` → refused, key unchanged.
4. Update: bad signature, unknown key id, expired manifest, lower version, size mismatch, hash mismatch,
   artefact URL without auth header → all refused; failed self-test → rollback to previous version.
5. Package: unsigned / wrong signer / ADS name / reserved name → refused.
6. Keychain: key never written to disk outside the keychain (scan the data folder, `~/.claude`, profiles,
   `HKCU\Environment`) after enrol, sync, and run.
7. Google: domain email without `hd` refused; owner exceptions unchanged; nothing else widened.
