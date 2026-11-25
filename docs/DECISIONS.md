# Swangz AI Hub — architecture decision records

Format: **D-### | date | context | decision | alternatives rejected | consequences.** Builders follow recorded
decisions; changing one needs a new record. Owner: @Sentinel. Findings referenced (F-##) are in
[SECURITY-REVIEW.md](SECURITY-REVIEW.md).

Cross-cutting constraints for every record: Python stdlib at runtime (no new runtime dependency without
Arnold's yes); migrations append-only (one new `SCHEMA` entry, v22, owned by @Forge — see the end);
the device never collects provider passwords, never reads provider credential files, never bypasses MFA;
no credential injection, cookie extraction or unofficial subscription sharing.

---

## D-001 | 2026-11-02 | Device key storage in the OS keychain

**Context.** The device key is a full gateway key. Today it is a 0600 file (`core.py:100`; on Windows the
mode is ignored and the folder roams, `core.py:54`) and is copied into `~/.claude/settings.json`
(`agents.py:106`) and the Windows user environment via `setx` (`agents.py:194`) — F-02.

**Decision.**
1. New module `swangz_client/keystore.py` with one interface: `put(server, key_id, secret)`, `get(...)`,
   `delete(...)`, `backend_name()`. Item identity: service `Swangz AI Hub`, account `<host>/<key_id>`.
2. Backends, chosen by platform, all stdlib:
   - **Windows — Credential Manager** via `ctypes` (`advapi32.CredWriteW/CredReadW/CredDeleteW/CredFree`),
     `CRED_TYPE_GENERIC`, `CRED_PERSIST_LOCAL_MACHINE` (stays on this machine for this user; never
     `ENTERPRISE`, which roams). Protected by DPAPI for the user.
   - **macOS — login Keychain.** v1: `/usr/bin/security` with the secret passed on **stdin** (`security -i`),
     never on the command line. v2 (after Developer ID signing, D-005): `ctypes` to Security.framework
     (`SecItemAdd/SecItemCopyMatching/SecItemDelete`, generic password) so the item's access list is the
     signed app rather than `/usr/bin/security`. ACL behaviour is verified on the macOS CI runner, not assumed.
   - **Linux — Secret Service** via `secret-tool` (libsecret-tools) with the secret on **stdin**
     (`secret-tool store --label … service swangz account <host>/<key_id>`), lookup/clear likewise.
3. **Fallback is visible, never silent.** Only when no backend works (headless Linux, no Secret Service, no
   `secret-tool`): the 0600 file, moved to a non-roaming folder (`%LOCALAPPDATA%` on Windows). The app shows
   "Key kept in a protected file — this device has no keychain" on *This device* and reports
   `key_storage: keychain|file` in every heartbeat; the console shows it as **reported by the app**.
4. **The key is never copied out of the store.**
   - Claude Code (managed): settings get `apiKeyHelper: "<app> key --for claude-code"` and
     `ANTHROPIC_BASE_URL`; **no** `ANTHROPIC_AUTH_TOKEN`. (The gateway already accepts `x-api-key`.)
   - Codex (managed, Unix): the marked profile line becomes `export SWANGZ_AI_KEY="$(<app> key --for codex)"`.
   - Codex (managed, Windows): **no `setx`**; managed Codex uses `swangz run codex` until a command-based
     credential is verified for the deployed Codex version (@Probe to check).
   - Scoped runs (`swangz run …`) put the key only in the child process environment (as today).
   - `swangz key` prints only with `--for <tool>`, refuses when stdout is a terminal, and is logged locally.
5. **Migration on upgrade:** read `device.key` → `put` → read back and compare → overwrite the file with zeros
   and delete it → rewrite managed Claude/Codex settings to the helper form, removing any
   `ANTHROPIC_AUTH_TOKEN` we wrote and `HKCU\Environment\SWANGZ_AI_KEY` → heartbeat reports the backend.
6. `remove_everything()` deletes the keychain item and the fallback file.

**Alternatives rejected.** `keyring` PyPI package (new dependency, pulls `jeepney`/`SecretStorage`; not worth
it for three small backends). Encrypting the file with a key stored beside it (obfuscation). Storing in the
Claude/Codex config (leaks via dotfiles). Raw D-Bus implementation in Python (large, error-prone).

**Consequences.** Any process running as the person can still ask the keychain on Windows/Linux (same trust as
today, but nothing on disk in plaintext, nothing in dotfiles, roaming or backups). Linux devices without a
keychain stay on a file and are visibly labelled. Tests: fake backend in unit tests; real-backend smoke tests on
GitHub Actions (Windows, macOS, Linux with `gnome-keyring` under `dbus-run-session`); abuse test 6 in
SECURITY-REVIEW (scan for the key outside the store after enrol/sync/run).

---

## D-002 | 2026-11-02 | Device credential lifecycle

**Context.** Device keys never expire; revocation is server-side and the app learns of it on next contact.

**Decision.**
1. A device key stays an ordinary gateway key (budgets, policies, kill switch apply unchanged). It is accepted
   by the proxy and `/api/device/*` **only**: never by `current_person` (staff), never by `/admin/api` — keep and
   test this (it is true today because sessions live in other tables).
2. **Inactivity expiry:** a device with no check-in for `device_idle_days` (setting, default 60) is revoked by the
   hourly maintenance, audited as `system`.
3. **Rotation:** `POST /api/device/rotate` (device key) issues a new key for the same `devices` row; the old key is
   revoked when the new one is first used or after 10 minutes. The app rotates every 30 days: put new → verify →
   call → delete old item. Audited.
4. Revocation paths unchanged (staff app, console, app sign-out), plus "This wasn't me" from D-009.
5. The app treats only `device_revoked` as "remove everything"; `device_unknown` asks the person (F-13).

**Alternatives rejected.** Short-lived access tokens + refresh tokens (adds a token service and breaks coding
agents mid-session; rotation + revocation + live cut give most of the benefit). mTLS device certificates (no
stdlib CA tooling on clients; Caddy/tunnel termination complicates it).

**Consequences.** One new endpoint and a maintenance rule (@Forge); rotation logic in the app (@Prism).

**Addendum (G3b, 2026-11-04).**

1. *Lost rotate response.* Reissue only while the old key is in grace and the pending new key has never been used.
   Revoke that new key in the same transaction and keep the original `retire_at`, so a repeat never extends grace.
   Limit 3 per hour; audit every reissue.
2. *Grace is enforced in `identify()`.* When `retire_at <= now`, write `revoked=retire_at, revoked_by='system: rotated'`
   once (`AND revoked IS NULL`) and return the revoked row. No `expires` column.
3. *One stable device row* through `keys.device_id`; `devices.key_id` is only a pointer to the current key.
4. Company devices are revoked when idle too.
5. `key_backend` is optional and from a fixed list; anything else is stored as `''`.
6. Older clients show "not reported (older app)" without a warning; only `file` is flagged.

Required: a rotated key returns 401 `device_key_rotated`, never a wipe, and the proxy refusal says "key renewed". Revoking
a device revokes all its keys and calls `live.cut` for each. The device limit counts devices with an active key. Early
revoke happens only on the new key's first `device_auth`, with a 10-minute hard limit. The new key copies `person_id`,
`label` and `hub_tool_id`, with `created_by='device rotation'`. Single winner:
`UPDATE keys SET retire_at=? WHERE id=? AND revoked IS NULL AND retire_at IS NULL`. The response is
`Cache-Control: no-store`, and the new key appears in no log or audit (hint only). Idle activity is the newest of
`last_seen`, `enrolled` and `last_used` across all the device's keys, and the idle job runs in its own `try`.

Consequence: `swangz run` sessions and Codex shells holding the old key stop 10 minutes after rotation. That is
acceptable for 30-day rotation; the app should rotate at start-up or when idle.

---

## D-003 | 2026-11-02 | Secure client updates

**Context.** The app is unsigned and cannot update itself. Whatever we build must not make the gateway able to
push code (F-03).

**Decision.**
1. **Root of trust is an offline release key held by Arnold**, not the gateway and not CI. Algorithm:
   **RSA-4096, PKCS#1 v1.5, SHA-256**, signed with `openssl dgst -sha256 -sign` on Arnold's machine.
   Verification in the app is ~30 lines of stdlib (`pow(sig, e, n)`, then **build the full expected EMSA
   encoding and compare all bytes** — never parse the padding). Public keys are pinned in
   `swangz_client/release_keys.py` by key id; two slots so a key can be rotated by a release signed with the old.
2. **Signed release manifest** `release.json`:
   `{schema:1, key_id, channel:"stable"|"pilot", version, min_supported, min_server, released, expires,
   artifacts:[{platform, arch, file, sha256, size}], notes}` + detached `release.json.sig`.
3. **The app updates only from a manifest that** verifies with a pinned key; matches its channel; has
   `expires` in the future (90 days; an expired manifest means "no updates", never "stop working"); has a
   `version` strictly greater than the highest version it has ever accepted (stored locally) — this is the
   anti-rollback rule. A deliberate rollback is a **new, higher version** containing the old code.
4. **Distribution:** the gateway serves `release.json`, its signature and artefacts at
   `/api/device/releases/…` (device key required, same origin, no third party at runtime). The gateway can
   withhold updates but cannot forge one. The `client.latest/minimum` hints in the device manifest only trigger
   a check; they never select a file.
5. **Download and verify:** stream to `updates/<version>/` with the size cap from the manifest, check size and
   SHA-256, then on macOS also `codesign --verify --strict` + expected Team ID, on Windows Authenticode via
   `WinVerifyTrust` with the expected publisher; Linux relies on our signature.
6. **Staged install and rollback (no admin rights; per-user install, D-005):**
   - Windows: rename the running `Swangz.exe` → `Swangz.prev.exe`, move the new one in, start it with
     `--post-update`, wait up to 60 s for it to write `update-ok` after its self-test (imports, keychain read,
     state readable); otherwise restore the previous exe and restart it, and record `update_failed`.
   - macOS: the same with the `.app` bundle directory (atomic rename within the same volume); if the install
     location is not writable, offer the download instead of updating.
   - Linux AppImage: the same with the single file.
   - Keep exactly one previous version; delete it after the first successful sync on the new one.
7. **Compatibility:** `min_server` lets the app refuse an update that the current gateway cannot serve;
   `min_supported` lets the gateway's `CLIENT_MINIMUM` force an update (the app says "please update" when no
   signed release satisfies it — today's behaviour).
8. **Managed installs** (per-machine via MDM): self-update is off; updates come through MDM.
9. **CI** produces artefacts + an unsigned `release.json` from a tag; Arnold checks the hashes and signs
   `release.json` offline with `packaging/sign_release.py` (wraps openssl). Platform code-signing certificates
   live in a GitHub *environment* that requires Arnold's approval.

**Alternatives rejected.** Trusting HTTPS + server-provided checksums (gateway compromise = fleet compromise).
Ed25519 (better algorithm, but no stdlib verifier; a hand-written curve implementation is a larger review
surface than RSA verify-by-encoding). Full TUF (correct but heavy for one product; the manifest above takes its
key ideas: offline root, expiry, anti-rollback, two key slots). Release key in CI secrets (a repo or workflow
compromise would then sign releases). GitHub Releases as runtime source (third-party dependency; would need a
second download path without the key).

**Consequences.** Every release needs one offline signing step by Arnold. A lost release key is recovered only
by shipping a manual reinstall — keep an offline backup (two copies, encrypted). Tests (abuse test 4) with
committed fixture keys and fixtures signed at build time; the private test key is test-only and clearly named.

---

## D-004 | 2026-11-02 | Signed packages and the extension

**Context.** Packages and the extension are trusted because the gateway says so (F-03).

**Decision.** A separate **package signing key** (RSA-4096, offline, Arnold or a publisher he names) signs a
canonical JSON statement `{id, version, sha256, size, platforms, signed_at, key_id}`. `package-publish` takes
`--signature FILE` and refuses without it; the server stores the statement and signature; the device manifest
carries both; the app verifies with pinned package keys before checking the sha256 and unpacking. The extension
stops being zipped from the live checkout: it is built from a tag in CI, signed like a package and published as
package `access-gate`. Unpack rules gain F-14. Company devices get the extension by Chrome enterprise
force-install once it is hosted with an update manifest (later; needs Arnold).

**Alternatives rejected.** Signing with the release key (routine publishing would then need the most sensitive
key). Signing on the server (the server is what we are removing from the trust root).

**Consequences.** Publishing needs the signing step; existing packages must be re-published signed before the
app enforces it (one release where unsigned packages are shown as "unsigned — ask your admin" and not installed).

---

## D-005 | 2026-11-02 | Cross-platform installation

**Decision.**
- **Windows:** per-user installer to `%LOCALAPPDATA%\Programs\Swangz` (no admin rights, so self-update works),
  Authenticode-signed (OV/EV certificate or Azure Trusted Signing — Arnold buys). Installer tool (Inno Setup or
  WiX) is a build-time tool; @Prism proposes, Arnold approves. Uninstall runs `Swangz.exe cleanup` (same as
  sign-out without the server call) so nothing is left.
- **macOS:** `.app` with hardened runtime, Developer ID signed, notarised and stapled, in a `.dmg`
  (Apple Developer Program — Arnold). Installs to `/Applications` or `~/Applications`.
- **Linux:** AppImage signed by our release key (D-003) as the primary format; `.deb` later for fleets.
- **Company fleets:** the same installers deployed per-machine by MDM/Intune with self-update disabled.
- **Phones/tablets:** the existing PWA (D-006).
- Every installer embeds the release and package public keys; artefacts are reproducible from a tag with
  pinned build tools (`--require-hashes`, actions pinned by SHA) — F-09.

**Alternatives rejected.** Per-machine by default (needs admin for every update). Unsigned binaries with "allow
anyway" instructions (trains staff to bypass SmartScreen/Gatekeeper). Snap/Flatpak (sandbox blocks editing the
coding agents' settings and running them).

**Consequences.** Certificates cost money and need Arnold. Until signed, builds are pilot-only.

---

## D-006 | 2026-11-02 | Mobile: stay on the PWA

**Context.** Phones cannot run coding agents; staff on phones need Home, Tools, Requests, reports, approvals.
The PWA exists and uses an HttpOnly cookie; the install worker caches no private HTML or APIs.

**Decision.** No native or wrapped mobile app now. Keep one application architecture (the web app). Harden the
PWA against MASVS where it applies: no tokens in `localStorage`/`IndexedDB` (cookie only), no private data in
the service-worker cache, HSTS, CSP, session idle timeout (F-10), sign-out clears caches. Passkeys/WebAuthn,
if wanted later, work in the PWA.

Revisit only when one of these is a real requirement: MDM app-protection policies (Intune MAM) that require a
store app; reliable push on iOS beyond what home-screen web push provides; a capability the web cannot reach.
Then prefer a thin wrapper of the same web app (Android TWA; on iOS only with genuine native value, as App
Store review rejects pure wrappers) over a second codebase.

**Alternatives rejected.** React Native/Flutter apps (second architecture, second auth surface, store reviews,
no capability staff need today). Wrappers now (no benefit without the triggers above).

**Consequences.** G7 tests the PWA on iOS Safari and Android Chrome (install, sign-in, approvals, sign-out
clears caches).

---

## D-007 | 2026-11-02 | Provider authentication patterns

**Decision.** Exactly five patterns, defined in [PROVIDER-AUTH-BOUNDARIES.md](PROVIDER-AUTH-BOUNDARIES.md):
`api` (company key on the gateway), `sso` (vendor SSO with Google Workspace), `seat` (vendor invite to the work
email), `shared` (company account by turns in company browsers, **only where the vendor plan permits
organisational use**, F-12), `own`. Coding agents use the gateway key against the provider API; they never use
a consumer subscription token through the gateway. Prohibited everywhere: collecting provider passwords,
credential injection, reading or exporting vendor cookies/tokens, relaying or bypassing MFA, reading
`~/.claude/.credentials.json`, `~/.codex/auth.json` or browser profiles. Each tool's entry in the matrix is
verified by @Probe before it is marked supported.

**Alternatives rejected.** Proxying consumer subscriptions (ChatGPT Plus, Claude Pro/Max) through the gateway
(against those terms; it is subscription sharing). Password vault with autofill (rejected three times, see
CLAUDE.md).

**Consequences.** Some tools stay `own` or `seat` until the vendor offers SSO or an organisational plan.

---

## D-008 | 2026-11-02 | Desktop-to-web continuity (handoff)

**Context.** "Open" in the app should land the person in the web app signed in, without making the device key a
browser or console credential.

**Decision.**
1. `POST /api/device/handoff` (device key, rate limit 10/hour/device, setting to turn off) with
   `{"next": "/go/<tool>" | "/?view=…"}` — `next` must be a relative path on an allowlist (`/`, `/go/<id>`,
   `/?view=<known>`); anything else is refused.
2. The server stores a **one-time handoff**: 256-bit random, SHA-256 stored, TTL **60 s**, single use, bound to
   `key_id`, person, `next`, and the device's address; audited.
3. The app opens `https://<pinned server>/auth/handoff?h=<secret>` in the default browser.
4. `GET /auth/handoff` **never signs in by itself** (login-CSRF): it shows "Continue as <name> on
   <device name>?" with a same-origin POST form carrying the handoff and a CSRF token; `Cache-Control:
   no-store`, `Referrer-Policy: no-referrer`; the handoff is consumed on POST. If the browser already has a
   session for a **different** person, refuse and say so (no silent account switch).
5. The result is a `staff_sessions` row of kind **`handoff`** (D-010) with `device_key_id`, absolute life 12 h,
   idle 2 h. A handoff session **cannot** approve `/device`, create or reveal keys, change password, start an
   extension session, or mint another handoff. It never reaches `/admin/api` (separate tables, separate
   cookie) — the console always requires its own sign-in.
6. Revoking or rotating the device deletes every session it minted.

**Alternatives rejected.** Device key in a cookie or URL (turns the device credential into a browser
credential). Long-lived "remember me" link. Relying only on Google SSO (fine where Google is used — one click —
but leaves password users and unsigned-in browsers without continuity; kept as the fallback when handoff is off).

**Consequences.** Migration columns (below); @Forge server, @Prism app. Abuse test 2 in SECURITY-REVIEW.
Build after D-010 exists.

---

## D-009 | 2026-11-02 | Device-code phishing hardening

**Decision.** (F-05) The app opens `/device` **without** the code and shows it large; the person types it.
`verification_uri_complete` is no longer used by the app (kept in the response for RFC 8628 compatibility, but
`/device?code=` shows the code page with a warning rather than skipping entry). Codes last 10 minutes. The
device-supplied name is shown as "Name the device gave itself". When the approver's address and the requester's
address differ (and neither is a named company network), a prominent warning is shown and the approve button
needs a second confirmation. After enrolment: an Updates notice (and email when SMTP is configured) with
"This wasn't me" that revokes the device; new devices listed in Needs attention for 24 h. `/device` requires a
`primary` cookie session (D-010).

**Alternatives rejected.** Dropping the device-code flow for a loopback redirect (needs a local HTTP listener and
custom URL schemes per OS; phishing-resistant but much more surface). Requiring a second factor at approval
(right later with passkeys; not available today).

**Consequences.** Small UX cost (typing eight characters).

---

## D-010 | 2026-11-02 | Session kinds and least privilege

**Decision.** `staff_sessions.kind` ∈ `primary` (cookie, from password, invite or Google), `extension` (bearer;
only `/api/gate/*` and `/api/extension/*`), `handoff` (cookie; D-008 limits). `current_person` returns the kind;
routes declare which kinds they accept (default: `primary` and `handoff`; sensitive: `primary` only). Bearer is
accepted only for `extension`. Staff sessions get an idle timeout (3 days) beside the 14-day absolute limit.
Console sessions: password change ends the others (F-15). Console sign-in in production is Google-only with a
server-shell break-glass owner (F-01, D-011).

**Consequences.** Fixes F-04; enables D-008. Permission sweep test like `V2PermissionTests` over kinds.

---

## D-011 | 2026-11-02 | Console authentication

**Decision.** When Google is configured, `console_password_login` defaults to off; console users sign in with
Google (Workspace 2-step), `hd` enforced for domain accounts (F-07; the two owner exceptions unchanged). A
break-glass owner sign-in is available only from the server shell (`python3 -m gateway add-admin` / a one-time
console link printed there, 10 minutes, single use, audited). Per-account failure counting is added to the
per-IP throttle. If Arnold wants password login kept, TOTP (RFC 6238, stdlib) becomes mandatory for it.

**Consequences.** Needs Arnold's agreement before it is switched on in production (it changes how he signs in).

---

## Migration v22 (one entry, owned by @Forge)

`staff_sessions`: `kind TEXT NOT NULL DEFAULT 'primary'`, `device_key_id TEXT`, `last_seen REAL`;
existing extension sessions set to `extension` by `created_by`/expiry heuristics is **not** possible reliably —
instead, existing sessions with expiry > 14 days from creation become `extension`.
`devices`: `key_storage TEXT`, `rotated REAL`. New table `device_handoffs(secret_hash PK, key_id, person_id,
next, ip, created, expires, used)`. `packages`: `statement TEXT`, `signature TEXT`, `signer TEXT`.
`tools`: `shared_terms_ref TEXT` (F-12). One migration; never edit v1–v21.

---

## D-012 | 2026-11-02 | Account ownership: four routes, owner separate from payer

**Context.** Amendment 01 §1: keep existing paid subscriptions and never turn one person's subscription into a
shared login.

**Decision.** Every provider connection record has `route` (`individual_subscription` | `assigned_seat` |
`api_billing` | `enterprise_agreement`), `account_holder` (a person id, or `company`), `payer` (`person` | `company` |
`unknown`) and `credential_location` (`vendor_client_on_device` | `gateway_env` | `none_held`).

1. *Individual subscription* (ChatGPT Plus, Claude Pro/Max, Google AI and similar). Exactly one holder, who is a
   person. Used only through the vendor's own sign-in or command-line tool, on that person's own devices and profile.
   Swangz never stores, reads, relays or sends its tokens through the gateway (D-007). It is never assigned to anyone
   else and never set to `shared`. The company paying for it does not make it a company account. When the person
   leaves it is cancelled, not handed on, unless the vendor officially supports a transfer.
2. *Assigned seat.* The company owns the vendor workspace; one seat belongs to one person's work identity. Seats are
   reassigned only in the vendor's admin. Swangz mirrors that, with source `provider_api` or `manual`.
3. *API billing.* The company key stays on the gateway. Per-person cost comes only from gateway records and is
   labelled estimated.
4. *Enterprise agreement.* The contract that contains seats and/or API use: a contract reference, not a way in.
5. *`shared` (the existing turns feature).* Stays, but only for company-held accounts whose vendor plan permits
   organisational use. The server must refuse, and audit, setting `signin=shared` on a tool whose connection has
   `account_holder` set to a person. No new shared tool without vendor evidence for that tool and Arnold's OK.
6. *One holder, several devices.* Allowed where the vendor permits. Credentials stay in the vendor's own client or the
   operating system's key store on each device; Swangz never copies them between devices.
7. No automatic move to API billing. API and Enterprise remain optional.

**Alternatives rejected.** Treating `payer=company` as company-owned, which would allow reassignment. Mirroring
credentials between devices.

**Consequences.** Holder and payer are separate facts in every record. D-019 builds its visibility rules on them.

---

## D-013 | 2026-11-02 | Small server (VPS): what may run there

**Context.** Amendment 01 small-VPS limits: the server is a control plane, not a place to run people's work.

**Decision.**

1. *Allowed:* identity and authorisation, the backend, SQLite metadata, provider connection records, account sync,
   webhook and callback reception, usage and subscription metadata, device enrolment and manifests, notifications,
   settings, audit, backups and health checks.
2. *Forbidden:* model inference, local language models or GPU work; running employees' agents or automations; storing
   personal workspace content (conversations, files, agent memory); one browser per employee; fleet growth.
3. *Remote browsers on the VPS* need a measured benchmark (RAM, CPU, latency, concurrency per active browser), a
   documented need for a company-held session, and Arnold's OK. Until then no capacity number or monthly total is
   published.
4. *Secrets.* Company admin tokens used for account sync are stored as a `secret_ref` to an environment variable or a
   file only the service user can read (0600), never in ordinary database records.
5. *Per-user provider tokens* may not be stored at all until a follow-up decision settles encryption at rest. The
   standard library has no authenticated encryption, so that needs a new dependency and Arnold's approval.

**Alternatives rejected.** None recorded when this was decided.

**Consequences.** Remote-browser capacity, any spending, and storing per-user tokens each wait for Arnold.

---

## D-014 | 2026-11-02 | Personal workspace isolation

**Context.** Amendment 01 isolated personal workspaces; consistent with `docs/CLIENT.md`, which already forbids reading
a device's content.

**Decision.**

1. *Where things live.* Personal projects, conversations, files, agent settings, memory, automations and preferences
   stay on the person's device or in their own OpenMausBot environment. The server keeps only ownership metadata
   (object id, kind, owner, device, created, last seen), sharing grants and access-level events, never the content.
2. *Server rules.* Every query for a personal object is filtered by `owner = the person in the session`, enforced on
   the server. Console roles see metadata only; no area, including owner, gains read access to content.
3. *Sharing* exists only as a grant record, created by the owner or by a written company sharing policy Arnold
   approved. It names the grantee, scope and expiry, can be revoked, and is audited. A role never grants it implicitly.
4. *Automations* run on the owner's device. The server may hold their schedule and ownership metadata, but never runs
   them.
5. *OpenMausBot environments.* Swangz links to them or launches them only. It does not read, import or migrate their
   bots, memory or workspaces.
6. *On the device,* isolation comes from separate operating-system accounts. Shared company machines need one OS
   account per person. Someone with local administrator rights can read everything on that device; this is accepted
   and documented.

**Alternatives rejected.** None recorded when this was decided.

**Consequences.** Every personal-object route needs a cross-person denial test and a test that a console role cannot
see content.

---

## D-015 | 2026-11-02 | Managed Chrome: three levels of enforcement, never overstated

**Context.** The remote browser's policy in `workspace_agent/agent.py` allowed one local folder and blocked `file://*`
plus four `chrome://` pages, with no block-everything rule and profiles saved per slot (true when this was decided).
Per-slot profiles are acceptable only for company-held `shared` accounts.

**Decision.**

1. *(a) Company-managed devices.* Chrome policy is applied machine-wide through the operating system's management
   (registry or Group Policy, `/etc/opt/chrome/policies/managed`, a macOS configuration profile), installed by an
   admin, on company devices only.
2. *(b) Personal devices.* The app may change nothing outside its own folder, and Chrome policy cannot be applied to
   one profile alone without machine-level changes.
   Option 1: profile-level cloud policy when the profile signs in with a managed @swangzavenue.com account (Chrome
   Enterprise Core). Probe must confirm this from official documentation, and it needs Arnold's OK because it changes
   the Google Workspace admin console.
   Option 2: if Option 1 is not used, the separate Swangz profile (its own data folder, readable only by that OS user)
   plus the access-gate extension is advisory only and the interface must say so.
3. *(c) Remote isolated browser* (the existing Workspace Agent). Only for company-held accounts and seats. A seat's
   saved profile is tied to the person and the seat, not to a slot, and is wiped when the seat moves to someone else.
   Outgoing traffic is restricted to the approved hosts; private address ranges and `169.254.169.254` are blocked.
4. *Ownership.* A profile belongs to exactly one person, or one person plus one seat, and is never reused by anyone
   else. Swangz never reads the profile's cookies or storage and never drives the browser through automation or
   Chrome's debugging interface (CDP).
5. *Records.* Profile ownership, start and end of each session, and access-level events.
6. *Limit to state plainly.* None of this stops a person using the account on another device. The vendor's own identity
   controls, seats and organisation controls are what count.

**Alternatives rejected.** None recorded when this was decided.

**Consequences.** Any Chrome Enterprise Core or Google Workspace admin change, and machine-wide policy on company
devices, need Arnold's OK.

---

## D-016 | 2026-11-02 | Browser restriction baseline (all levels)

**Context.** D-015 needs one baseline that says what a managed browser may reach, and tests that prove it.

**Decision.**

1. *Navigation.* `URLBlocklist: ["*"]` plus `URLAllowlist` containing the approved tool hosts and the identity-provider
   paths needed for approved sign-ins.
2. *Google pages.* Block `mail.google.com`, `drive.google.com`, `myaccount.google.com` and Google's account-security
   and device pages. Do not block the sign-in pages on `accounts.google.com`. Limit account switching with
   `AllowedDomainsForApps=swangzavenue.com`; handle the two approved owner exceptions as recorded, without widening them.
3. *Settings to apply or keep.* `RemoteDebuggingAllowed=false`, `DeveloperToolsAvailability=2`, `SyncDisabled`,
   `BrowserAddPersonEnabled=false`, `BrowserGuestModeEnabled=false`, `IncognitoModeAvailability=1`,
   `ExtensionInstallBlocklist=["*"]` plus an allowlist, `DownloadRestrictions=3` unless Arnold approves downloads,
   `PasswordManagerEnabled=false`, `AutoLaunchProtocolsFromOrigins=[]` plus blocking external protocols. Block
   `file://*`, `chrome://*` and `view-source:*`. Limit access to the local network.
4. *Not settled when decided.* `BrowserSignin=0` conflicts with Option 1 in D-015(b) and must be settled per level.
5. *Bypass tests.* For each level and each supported OS, prove refusal for: redirects, pop-ups and new tabs; alternate
   and lookalike domains, punycode, direct IPv4/IPv6 addresses, and `data:`/`blob:` pages; external protocols, local
   files, local-network and cloud-metadata addresses; opening an extra profile, guest or incognito window; a second
   Google account. The same tests must also show that approved sign-in still works.

**Alternatives rejected.** None recorded when this was decided.

**Consequences.** The company-device policy pack is `deploy/chrome-policy`. `AllowedDomainsForApps` is left out of it
until Arnold decides. The bypass tests above are still owed, so the pack's enforcement is unproven until they run.

---

## D-017 | 2026-11-02 | Google sign-in and return restrictions

**Context.** Without a configured address, the Google return address was built from the request's Host header. Google
only accepts registered addresses, so the risk is low, but production should not depend on the request.

**Decision.**

1. *System browser only.* Sign-ins happen in the system browser or the managed official Chrome, never in an embedded
   window controlled by Swangz. No reading credentials or cookies, and no automated typing or reading of passwords.
2. *The desktop app* keeps using device-code enrolment (D-009) and the desktop-to-web handoff (D-008) and never talks
   to Google directly. Any future native sign-in follows RFC 8252: system browser, PKCE with S256, a loopback address on
   a random port, `state` and `nonce`, and no client secret in the app.
3. *Hub sign-in* stays server-side with scopes `openid email profile` only. Gmail and Drive scopes are never requested.
4. *Production has a fixed return address.* Production refuses to start Google sign-in without one and raises a health
   warning. The page returned to comes only from `APPS`; any `next` uses the D-008 allowlist.
   Updated 2026-11-10: the Host fallback applies only when `GOOGLE_REDIRECT_URI`, `GATEWAY_WEB_URL` and
   `GATEWAY_PUBLIC_URL` are all unset. The refusal is `GATEWAY_REQUIRE_FIXED_RETURN`, off by default and turned on by
   Arnold at go-live; preflight fails if it is off while Google sign-in is on.
5. *Provider-connection sign-ins (account sync).* Server-side confidential client, PKCE and a fixed return address;
   `state` tied to the session, the person and the provider; read-only scopes listed per provider with an official
   source; the consent screen names the account being connected; disconnecting or the person leaving revokes the token
   with the provider and deletes the reference.

**Alternatives rejected.** None recorded when this was decided.

**Consequences.** Setting the fixed return address in production needs Arnold's OK.

---

## D-018 | 2026-11-02 | Account-sync layer

**Context.** Amendment 01 official account-sync hooks: show what a provider actually reports and nothing else.

**Decision.**

1. *Source of each value:* `provider_api` | `webhook` | `manual` (who and when) | `unavailable`, plus how reliable it
   is and when it was last synced. A stale value is shown with its timestamp.
2. *Never invent values.* Balances, quotas and states are never derived from gateway estimates. No scraping private
   pages.
3. *Webhooks* are verified only with each provider's own documented signature scheme, cited from an official source.
   Until Probe cites one for a provider, that provider has no webhook route; there is no generic verifier. Every webhook
   route also needs a timestamp window (at most ±300 s unless the provider documents otherwise), a replay store of
   event ids with idempotent handling, a body size limit and a rate limit, and `@route` with no sign-in but every
   refusal audited.
4. *Polling* is at most hourly per connection by default, backs off on 429 and honours `Retry-After`.
5. *Who sees what.* Owners see their own connections. Metadata for company-paid connections is visible to `money`
   (billing) and `govern` (seats). Connecting an individual subscription is the person's opt-in and can be revoked.
   Every new route has `area=`, `ctx.audit` with before and after, and a test in the permissions sweep.
6. *Provider claims* stay provisional until their official URLs are verified. Unsupported fields default to
   `unavailable` or `manual`. Company admin tokens are a `secret_ref` (D-013); per-user tokens are not stored until a
   decision settles encryption at rest.

**Alternatives rejected.** A generic webhook verifier for all providers: signature schemes differ by provider.

**Consequences.** Webhook and sync work is gated per provider on an official source.

---

## Amendment 01 threat note (covers D-012 to D-018)

**Assets.** Personal workspace content, provider sessions, company keys and admin tokens, seat assignments, audit
integrity.

**Entry points.** Sync and webhook routes, provider sign-in callbacks, the managed browser, the client's local state,
console roles.

**Abuse cases.** One person reading another's objects; an admin reading personal content; turning a personal
subscription into a shared one; spoofed or replayed webhooks; a return address taken from the Host header; escaping the
managed browser (debugging port, extra profile, external protocol, internal address); a second Google account in the
managed profile; invented quota figures; a seat's profile reused after reassignment.

**Proving tests.** Cross-person denial on every personal-object route; a console role cannot see content; `shared`
refused when the holder is a person; webhooks with a bad signature, a stale timestamp or a replay are refused and
duplicates are idempotent; Google sign-in refused without a fixed return address when required; the D-016 bypass suite;
fields marked unavailable when the provider gives nothing; the profile is wiped when a seat is reassigned.

---

## D-019 | 2026-11-06 | Provider-account registry: who sees what, and what the audit log says

**Context.** Amendment 01 task 1 (PR #28, `feature/provider-registry`, approved at `92c97aa`, tree `b8927fe`) lets a
person declare the AI subscriptions they hold (v24 `provider_accounts`, `provider_account_values`; v25 NULL-safe guards).
A personal subscription is the person's own business: the company may need to know *that* it is accounted for, never
which tool a named person pays for privately. Seats on the company plan are company business. The audit log is
readable by every console user, viewers included, so anything written there is visible across the console.

**Decision.**

1. *Visibility through the API.* A console user sees the record kind's field ceiling intersected with the areas they
   hold, then the union across those areas. The ceiling binds the owner too. Console routes are read-only,
   `area=("govern","money")`; viewer, security, emergency-only and admin-only users get 403. The registry tables are
   read only by `gateway/registry.py` (and by the tool-delete check in `admin.py`); no search, Timeline, insight,
   notification, CSV or export reads them.

   | Field | holder (own records, either kind) | govern (seats) | money (seats) |
   |---|---|---|---|
   | id, tool_id, tool, route, status, created, ended | yes | yes | yes |
   | payer, assertion (always `holder_declared`), confirmed (always `false`), label | yes | yes | yes |
   | holder (person id and name) | not returned (it is the caller) | yes | yes |
   | created_by | yes | no | no |
   | values: plan, quota_limit, quota_used, period_end | yes | yes | no |
   | values: credit_balance, monthly_price | yes | no | yes |

   Individual accounts: no console field at all (item 2).
2. *Individual accounts are holder-only (F1).* No console list, read, filter or count returns one. The list filters
   `route = 'seat'` in SQL before `ORDER BY ... LIMIT` (at most 200), so the limit cannot reveal individual rows;
   reading an individual id answers the same 404 as a missing id to every console user allowed to read (govern or
   money, the owner included); every other role gets 403.
3. *Audit (R3).* Each registry change writes one audit row through `server.audit`: actor = the holder's name; action =
   `registered a provider account`, `recorded a provider account value` or `ended a provider account`; time; target and
   correlation = `provider_account:<id>`; before/after = a status or a value id only; outcome `ok`; the network address
   of the request; empty reason, detail and area. The console's Audit log shows the address as a named network, an
   approximate place or the address type. (The Security view groups failed sign-ins only; registry rows are not in
   it.) Never written: tool, route, kind, payer, label or value. These rows are kept out of a person's Timeline (it joins on `person:<id>`), but they are not hidden:
   the Audit log filters by actor, text and correlation and the Ctrl+K menu's audit group finds them.
4. *Accepted residuals (Low).*
   - *Named change.* Every console user can see that a named person changed a provider-account declaration, when, and
     from which network.
   - *Individual or seat.* A govern or money user who reads a `provider_account:<id>` taken from the audit log gets 200
     for a seat and 404 for an individual account. Registry rows are never deleted, so the 404 reliably means
     "individual": the lookup reveals the route. For an individual account it reveals nothing more (no tool or
     contents); for a seat the 200 shows the seat's fields within that user's ceiling, tool included, as intended.
     Viewer and security users get 403 and cannot tell.
     Absence from the seat list alone proves nothing (the list is capped and filterable).
   - *Tool delete.* A govern user deleting an admin-added tool that any registry row points at gets 409
     `has_provider_accounts`. That shows someone has declared an account for the tool, not who, the route, how many or
     when. A probe has three outcomes: 409 when registry rows exist (silent, not audited: the dispatcher audits area
     refusals only); 502 when the tool has no rows but closing a workspace sign-in fails (silent, nothing deleted);
     otherwise the tool is really deleted, and that is audited. So a "yes" is silent and a "no" normally costs a real,
     visible deletion. Accepted because it needs govern, which already decides who may use each tool; it reveals
     existence only; built-in tools are refused earlier with 400; and auditing the refusal would write "someone holds
     an account for tool X" into a log every console user, viewers included, can read, which is wider than the signal
     itself. The answer must be identical across routes *within* each path; the pre-check and
     the foreign-key fallback may word their message differently, because which path answers depends on timing, not
     on the route. Rejected fixes: a seat-only check (moves the 409 to the fallback), silent archive, deleting registry
     rows (breaks the RESTRICT foreign keys and permanent retention), forbidding deletion of every registrable tool.
   - *Legacy id.* Databases first created by the pre-release `48cc003` form of v24 lack `CHECK (id > 0)`, so direct SQL
     can store a non-positive id there. A stored id of -1 was shown to make later automatic inserts fail (fails
     closed, nothing lost); the effect of id 0 was not demonstrated. No HTTP path supplies an id. No v26. If a
     non-fixture database in that form is ever found, the repair is an additive migration: an AFTER INSERT abort on
     `NEW.id <= 0` and `NEW.id > 0 AND` before the `no_replace` id check.
5. *Release condition.* The registry routes go live as soon as the code is deployed, so the staff Privacy notice must
   be in the same release: PR #28 is not merged or deployed without it. The approved notice (PR #29,
   `feature/provider-privacy-notice` at `9354a25`) states: what is declared (tool, personal or seat, who pays, an
   optional label, plan, quota, period end date, price, credit); that it is the person's own declaration, unconfirmed
   and changing no access; that a record can be ended but not deleted, and values cannot be edited (they are
   normalised when stored and then kept unchanged, a new value keeping the earlier one in the history); who sees which
   fields; the audit entry for the three actions (add a record, add a value, end), readable by every control-room
   user including read-only ones; that govern and money users can tell personal from seat from that entry but, for a
   personal subscription, not the tool; that server operators and backups can reach the stored data; and that records
   are kept after ending and audit entries for at least a year. It corrects the "Your personal accounts" line under
   *What is not recorded*, and says "in Swangz AI Hub" rather than an unqualified "only you".

**Alternatives rejected.** Govern seeing individual id, tool, route and times (the earlier draft): re-identifies
personal holdings through the audit log. An opaque or hashed audit reference: adds key management and still leaves the
named actor, time and address. Auditing tool-delete refusals: broadcasts the existence signal to every console user.

**Consequences.** Admin-side review of personal subscriptions is not possible in task 1; any later need (counts,
incident access) needs a new record, Arnold's yes and its own threat note. Tests pinning this:
`tests/test_provider_registry.py` (field matrix, holder-only list and read, `FinalPinTests` limit and 409 parity,
audit leak markers). This record authorises no later Amendment 01 task, and no merge or deploy.

## D-020 | 2026-11-12 | The Swangz workspace window never opens the Hub's own address

**Context.** Managed workspace W3 (PR #186, `feature/w3-launcher`) opens website tools in a separate Swangz workspace
browser profile on contract-2 devices. Its earlier head `a96f905`/`3fc2ead` opened `/go/<tool>?d=<device>` there for
every tool not marked `workspace: true` (shared company accounts, company browsers). The Hub sign-in would then appear
inside the workspace profile and persist there, giving the provider-facing profile a Hub session it does not need.

**Decision.** On a contract-2 device the app opens a website tool in the workspace window **only** through
`POST /api/device/open` (device key; PR #179), at the provider address that call returns, re-checked against the
tool's `hosts`. A tool the manifest does not mark `workspace: true` (on #179's manifest: exactly the company-browser
shared accounts) is **not opened by the app** in this release: the app raises `LaunchError("shared_account")` with
#179's wording ("This is a shared company account. Open it from Swangz AI Hub, where turns are handed out.") before
any window, `/device/open` call or browser start, and never falls back to the default browser. `open_hub` and
`check_hub_url` are removed. Without a contract-2 workspace nothing opens (`no_workspace`).

**Alternatives rejected.** `/go/?d=` in the workspace: puts a Hub session cookie in the provider-facing profile and
widens what a compromised provider page shares a cookie jar with. The default browser for shared tools: breaks the
"never the default browser" rule of section 9.1 and splits one tool across two profiles.

**Consequences.** Shared company accounts are opened from the staff app (turns, company browser) until a later
decision says otherwise; the Swangz app only refuses them with plain words. Tests pinning this:
`tests/test_workspace_launcher.py` `test_contract_2_shared_app_opens_nothing` (no Popen, no `open_url`, no
`webbrowser`, no API call; `check_hub_url`/`open_hub` absent) and
`test_no_tool_ever_reaches_open_url_on_a_contract_2_device`. Approved at #186 head `a3f6806`.

## D-021 | 2026-11-13 | Offline grace before the workspace window closes

**Context.** `docs/MANAGED-WORKSPACE.md` §9.3 reads as "close the workspace window when the Hub cannot confirm the
workspace". Read literally, every failed heartbeat (laptop on a flaky link, a Hub restart, a 5xx) would close the
window and lose unsaved work, while buying no security: the person owns the folder and can reopen it by hand (R-2),
provider sessions continue at the provider (R-4), and Open is an online call the server refuses anyway.

**Decision.** On a network failure, timeout, TLS error, 5xx or non-JSON/`ok`-less answer, the app closes the window it
started only when **both** the last two device check-ins failed **and** the last authenticated answer is at least
`2 × HEARTBEAT_SECONDS` (30 min) old, measured with `time.monotonic()`. Any authenticated answer resets both. It may
warn once, two minutes before. These failures never purge and never latch a refusal of Open: Open stays an online
call (`/api/device/open`) that the Hub decides. A 401/403 is not a network failure: it closes and refuses at once
(`docs/W4-THREAT-NOTE.md` Ruling 2).

**Alternatives rejected.** Close on the first failure (the §9.3 literal reading): data loss on every blip, no gain.
Never close while offline: a suspended person on a disconnected laptop would keep the window indefinitely; 30 min
bounds it. Wall-clock age alone: the clock can be moved; the failure count covers monotonic pauses during sleep.

**Consequences.** A suspension reaches an offline device's window at the latest about 30 min after the link drops, or
at the next authenticated answer. Implemented in PR #191 (`swangz_client/workspace_state.py` `failure()`), test 7 of
the W4 note.

## D-022 | 2026-11-13 | Shared company accounts stay out of the Swangz app for the 20 Nov release

**Context.** Chief's queue item "shared tools through turns" asked whether the Swangz app should hand out turns on
shared company accounts (`signin = 'shared'`, `gateway/turns.py`) and open the Neko company browser in the managed
workspace window. Today the app refuses them (D-020) and `/api/device/open` answers 409 `shared_account`; turns work
through the staff web app's `/go/` and the extension. Full analysis: `docs/SHARED-TURNS-THREAT-NOTE.md`.

**Decision.** Keep refusing in the app and on `/api/device/open`; turns stay in the staff web app, unchanged. Fix the
manifest so every shared tool has `workspace: false` (`gateway/enroll.py`: today a shared tool with no company
browser is marked `true` and only the server refusal stops it). `/device/open` keeps running `launch_checks` and
`managed.launch_refusal` before the `shared_account` refusal and never touches `tool_turns` or `gw.workspaces`. The
staff web app's `/go/` for a shared tool gets no device or enforce-mode gate: the shared session lives in a remote
company browser, not on the device.

**Alternatives rejected.** (b) `/device/open` takes a turn and returns the Neko address for the workspace window:
breaks MANAGED-WORKSPACE §2.2 (no shared provider identity) and §2.6 (no remote browsers for this path), which only
Arnold can change; needs the Neko origin in the workspace allowlist (on Swangz's own computers a random
`*.trycloudflare.com` quick tunnel, so a wildcard or a server-supplied per-turn host); and puts the reusable per-turn
Neko `usr`/`pwd` on the browser command line (W3 A1). Pointing the app at `/go/` in the default browser: rejected in
D-020.

**Consequences.** No migration, no new route. If (b) is reopened after Arnold's yes on §2.2/§2.6: a fixed Neko host
in machine policy (never a wildcard tunnel), a single-use launch code (≥128 bits, ≤60 s, bound to turn + device)
instead of `usr`/`pwd` in the URL, a nullable `device_id` on `tool_turns` in a new migration, and closing on the
existing heartbeat with the agent's release as the real boundary. Existing risk R-13: `/go/` already sends `usr`/`pwd`
in a 302 `Location` into the person's browser history; the single-use code is its fix, after 20 Nov. Tests T1–T6 in
the threat note.

## D-023 | 2026-11-17 | Prompt and reply text: not kept by default, and only the trust area may read it (F-18, R-8)

**Context.** F-18 (SECURITY-REVIEW.md) and #160. `store_bodies` defaults to on (`proxy.py:451`, `admin.py:806`,
`staff.py:404`). Whatever that switch says, every request row keeps the clipped `prompt`, `reply` and `actions`. Any
console role, `viewer` included, can read them through `/timeline`, `/people/<id>`, `/requests`, `/sessions/<sid>`,
`/requests/<id>` and `/search`. Only `/export.csv` checks `ctx.can("trust")`. The release-sprint brief (17 Nov)
directs: default it off, gate it by role, and add a test. This is #160's option D.

**Decision.**
1. **Off by default.** One constant, `STORE_BODIES_DEFAULT = "0"`, read in all three places. An append-only migration
   writes `store_bodies = '0'` only where no row exists. A saved `'1'`, which is an admin's audited choice, stays.
2. **One switch covers all content.** With `store_bodies` off, `prompt`, `reply` and `actions` are written as NULL,
   along with `req_head`, `req_items` and `resp_blob`. There is no second setting. Purpose inference
   (`purpose.classify`) runs on the text in memory and keeps only its label, confidence and rule id. Secret
   blocking is unchanged.
3. **Reading content needs the `trust` area**, the same rule `/export.csv` already uses. Owner has it, and so does
   security. Content means prompt, reply, actions, request and response bodies, and the media prompt.
   - For any other role, the server sets those fields to `null` and adds `"content": "withheld"`. This applies in
     every route above, plus Live, the insight lenses and every CSV.
   - For those roles, `q=` and `/search` match metadata only.
   - The UI only hides; the server decides.
4. **Audit.** Each content read by trust is audited: the existing "opened the full record" event, plus one line per
   content search or session view.
5. **Staff** still see their own requests, unchanged. The staff Privacy page's wording follows the switch: off means
   "no prompt or reply text is kept".
6. **Content already stored** is left alone and ages out under the retention setting. Redacting it means deleting
   data, so that is Arnold's call.

**Rejected.**
- A banner with the default left on, because the default is the privacy promise.
- Encryption at rest, because the key would sit on the same server.
- The `admin` area. In my 17 Nov note to Chief I named `admin`; this decision corrects that to `trust`, which keeps
  the one existing rule and F-18's remediation.

**Consequences.** Pulling back exactly what was sent needs trust to switch storage on first, and that switch is
audited. R-8 closes when the PR merges.

**Tests.**
- A fresh database reads `store_bodies` as off.
- A request through fake_upstream leaves all six content columns NULL.
- A saved `'1'` survives the migration.
- With storage on, a marker is planted in a stored prompt and reply:
  - viewer, billing and operations each call every GET under `/api/admin` (a crawl of the route table, with the
    `export.csv` variants) and never see the marker, and get `content: withheld`;
  - `q=<marker>` returns no rows for them;
  - security and owner do get it, and the read is audited.
- The existing purpose-inference tests still pass with storage off.

## D-024 | 2026-11-17 | Machine-policy integrity: tamper-evident, verified by the app, on company devices only (W6, #160)

**Context.** The parts exist on `feature/managed-workspace`:
- `prepare.py` prints the baseline SHA-256.
- The Hub stores `managed_policy_sha256` and a mode, `warn` or `enforce`.
- The contract-2 block sends `policy: {sha256, mode}`.
- `machine_policy.report()` reads the installed policy and returns `{ok, sha256}`.
- `/api/device/open` and `/go/` apply `enforce` through `managed.launch_refusal`.

Three gaps:
1. `Client.policy_check` is never set (`core.py:538` is the only assignment). No app ever reports, so every device
   shows "has not reported".
2. `launch_refusal` ignores `owner_kind`. In `enforce`, personal devices, which never get the pack, would be refused.
3. The app does not compare what it found with the baseline the Hub sent. Only the server does.

**Decision.**
1. **Company devices only.** At start-up the app sets `policy_check = machine_policy.report` when the enrolment's
   `owner_kind` is `company`. A personal device sends no `policy` field and keeps the extension gate.
2. **When the app checks.** At every heartbeat, and again before each Open. A cached result older than 60 seconds is
   never used. A pack removed or edited is therefore seen within one heartbeat, and always before the next window.
3. **The app also verifies before it opens a window.** It compares its own hash with the block's `policy.sha256` and
   requires `problems_in()` to be empty.
   - In `enforce`, any mismatch is refused on the device, before any browser starts, with the plain
     `workspace_policy` message.
   - In `warn`, the window opens and the result is reported.
   - The server's refusal stays in place on its own.
4. **The server applies `enforce` only to company devices.** `managed.launch_refusal` and `policy_problem` skip
   `owner_kind = personal`.
5. **The hash.** It stays canonical over `BASELINE_KEYS` (sorted keys, compact JSON), so reordering a file or
   changing its whitespace leaves it unchanged, and any change of value changes it. A weakening outside the
   baseline is caught by `problems_in()` and reported as `ok=false`.
6. **Honest labels.** The console says "reported by the app". The docs say tamper-evident, not tamper-proof: a local
   administrator who also patches the app defeats it (R-1, R-3). The default stays `warn` until the release gate
   has the evidence for `enforce`.

**Rejected.**
- Signing the pack: the standard library cannot verify signatures, a new dependency needs Arnold, and HMAC would
  put the key on the device.
- TPM or OS attestation: it needs signed builds and certificates, which are Arnold's purchase.
- Reading other device state: the app never reads device content.

**Tests.**
- A company enrolment sets `policy_check`. A personal one does not, and its heartbeat body has no `policy` key.
- The heartbeat with a report is under 2 KB.
- Tamper cases, on the `machine_policy` fixtures:
  - the pack is removed: `ok=false`;
  - one allowlist entry is edited: the hash differs and the server says "not the baseline";
  - an extra weakening key is added: `ok=false`;
  - the keys are reordered: the hash is unchanged.
- `enforce` with a mismatch:
  - `/api/device/open` returns 409 `workspace_policy`;
  - the app refuses, and the fake `popen` is never called.
- `warn` with a mismatch: the window opens and the console shows "not in force".
- `enforce` on a personal device: not refused for policy.
- A check that raises reports `ok=false` and never skips the heartbeat.

## D-025 | 2026-11-18 | Who decides a device is a company device, before `enforce` (D-024 follow-up, PR #248)

**Context.** The person approving a device code chooses `owner_kind` (`gateway/enroll.py`, default `personal`). D-024
point 4 exempts personal devices from `enforce`, so a staff member who calls a company laptop "personal" skips the
policy check. In `warn`, the default, this changes nothing.

**Decision.**
1. For release, `owner_kind` stays the person's own declaration. The console labels it "declared by the person".
2. Before `managed_policy_mode = enforce` is turned on, an admin must be able to confirm or change a device's kind,
   with the change audited (`before`/`after`, `correlation=device:<id>`, area `govern`). In `enforce`, a device the
   person declared `personal` that an admin has marked `company` is enforced. An admin's mark always wins over the
   person's declaration.
3. Release gate item: `enforce` stays off until (2) is merged and tested.

**Rejected.** Inferring the kind from the device (domain join, MDM, hostname): this reads device state, so CLIENT.md
rules it out, and it is easy to fake. Defaulting to `company`: the Hub would refuse personal devices that never get the
pack.

**Tests (with point 2).** The person declares personal and an admin marks it company: refused in `enforce` with no
report. The admin's change is audited. A viewer or billing role gets 403.

## D-026 | 2026-11-25 | Managed Chrome on Windows and macOS: setup, launch, policy and revocation (issue #333)

**Context.** Issue #333 asks the Windows EXE and macOS DMG to set up genuine Google Chrome, a dedicated browser folder
per employee, and the managed policy and extension, and to open every authorised web tool only in that Chrome. The
pieces exist but are separate: `workspace_launcher.find_browser` (fixed paths, never PATH), `build_argv` (fixed
switches, forbidden switches), `browser_profiles.Profiles` (owner-bound folders), `machine_policy.check` (machine scope,
D-024), `deploy/chrome-policy/` (the pack, never installed by the tool), and the CI tamper tests (#293, #296). This
decision sets the rules for joining them. It changes nothing on the server, the domain or the database.

**Threat note (STRIDE, short).**
- *Assets:* the person's provider sessions in their Chrome folder; the device key; the integrity of the Chrome binary
  and of the machine policy; the person's own browser settings and data on a personal computer.
- *Entry points:* the Chrome download; the elevated install and policy steps; the browser folder on disk; the policy
  key or file; `/device/open` and the launcher; revocation.
- *Abuse cases:*
  1. A fake or modified Chrome, downloaded or already on the disk, reads the sessions (spoofing, tampering).
  2. The elevated step is fed a file or argument the person or malware controls, giving privilege escalation.
  3. A second person on the same OS account, or another program, reads or copies the first person's cookies
     (information disclosure).
  4. A provider link opens in the default browser, outside policy and outside the dedicated folder (control bypass).
  5. An existing GPO or MDM policy, or a user-level policy, quietly overrides the pack while the check says `ok`.
  6. The person's own Chrome settings are changed without their knowledge.
  7. After revocation the folder still holds live provider sessions (lingering access).
  8. Setup reports controls as enforced when Chrome ignores them (false assurance).
- *Controls and tests:* the numbered rules below. Each rule names its proving test.

**Decision.**

**A. Chrome: official source, verified publisher, never redistributed.**
1. Swangz never bundles, mirrors or hosts a Chrome installer: not in the EXE or DMG, not on the Hub, not on Netlify,
   not in GitHub releases. What happens when Chrome is missing depends on the system:
   - **Windows:** the elevated step (B5) downloads the Google Chrome enterprise MSI at that moment,
     `https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi`, over HTTPS with certificate
     checks, into its own admin-only staging folder, never into the app's data folder. A file the person's account
     can write is never handed to an elevated program. (A copy from the user folder was rejected: the "signed by
     Google LLC" check alone also admits an older Google-signed Chrome MSI or another Google product, so a swap
     could still downgrade Chrome.)
   - **macOS: Swangz downloads and installs nothing** (B6). It opens Google's Chrome page,
     `https://www.google.com/chrome/`, in the default browser (allowed by D2: Google's page, not a tool) and says
     which install it will accept. On a company Mac that is a root-owned `/Applications/Google Chrome.app` (A4),
     which in practice means the administrator installs Google's universal enterprise PKG, as Google's Mac
     deployment page recommends. On a personal Mac the person may drag Chrome in from Google's DMG. Either way A2
     and A3 then verify the app before its first use.

   The Windows URL is **observed, not documented**: it returned 200 on 25 Nov 2026, but it is not printed on the
   Google help pages checked (docs/ACCEPTANCE-333.md). If Google moves it, setup stops with a repair message (the
   signature check below still decides) and the constant is updated. Both addresses are constants in the code.
   Redirects are followed only to `https://` URLs, and the download has a size cap (500 MB).
2. **The signature is the authority, not a hash** (no Google-published hash was found; that is unverified, not a
   confirmed absence, and the design does not depend on it):
   - Windows: the Authenticode signature is valid, chains to a trusted root, and the signer certificate's parsed
     `O` (organisation) attribute equals `Google LLC` exactly: compare the attribute value, never search the subject
     string (so `O=Google LLC Ltd` or a `CN` containing `O=Google LLC` fails). Observed on the MSI on 25 Nov:
     `CN=Google LLC, O=Google LLC`; the name is backed by Google's Omaha updater source, not by Chrome product docs.
     Check it through `WinVerifyTrust` or `Get-AuthenticodeSignature`, and check the subject, not a thumbprint,
     because Google rotates certificates.
   - macOS: `codesign --verify --deep` passes on `Google Chrome.app` with the requirement
     `anchor apple generic and identifier "com.google.Chrome" and certificate 1[field.1.2.840.113635.100.6.2.6] and
     certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "EQHXZ8M8AV"`
     (the two `field` clauses require a Developer ID intermediate and a Developer ID Application leaf, so a
     development or other Apple certificate with Google's Team ID fails; the requirement is the one Chromium's own
     source checks, docs/ACCEPTANCE-333.md; `EQHXZ8M8AV` is Google LLC's Team ID), and
     `spctl --assess --type execute` accepts it. The requirement applies to the **app only**, never to the DMG
     (whose identifier is `GoogleChrome-<version>-GGRO`); the DMG is just a carrier. Observed on 25 Nov
     (docs/ACCEPTANCE-333.md): the DMG is signed `Developer ID Application: Google LLC (EQHXZ8M8AV)` and the
     enterprise PKG `Developer ID Installer: Google LLC (EQHXZ8M8AV)` (that certificate expires 1 Feb 2027). If an
     admin checks either carrier, the check pins the Team ID, never a certificate; validity is unverified until
     `codesign` / `pkgutil --check-signature` pass on a Mac.
     *Amendment 25 Nov (#351):* `--strict` is not used. It rejects extended attributes such as
     `com.apple.FinderInfo` and resource forks, which the signature does not cover, and a genuine Chrome copied in
     with them (seen on the GitHub macOS runner) would be refused. The sealed code and resources, nested code
     (`--deep`), the requirement and `spctl` still have to pass. The app never strips attributes from the bundle.
     UNVERIFIED until checked on a real Mac: that `spctl --assess` accepts the installed Chrome offline, and what it
     answers when Gatekeeper assessments are disabled (a local admin can do that; D-024 tamper-evident). Probe checks
     both before release.

   Anything else stops setup with a repair message. The SHA-256 of the checked file goes in the setup log as
   evidence, never as the check.
3. The same publisher check applies to an **already installed** Chrome before its first use, and again whenever the
   binary's size or modification time changes (cache the result keyed on those). An unsigned or foreign `chrome.exe`
   or `Google Chrome.app` at a fixed path is refused with `no_browser`.
4. On a company device, only a per-machine Chrome is used: `%ProgramFiles%` on Windows, or `/Applications` owned by
   root on macOS. A per-user `%LocalAppData%` Chrome, which any program running as the person can replace, is
   accepted only on a personal device, and still has to pass point 3.

*Tests:* missing Chrome leads to a repair state. A wrong signer, an unsigned file and a truncated download each stop
setup and run nothing. A redirect to `http://` is refused. A changed binary is checked again. On a company device a
`%LocalAppData%` Chrome is refused.

**B. Elevation and consent.**
1. Elevation happens only through the operating system's own consent: the UAC prompt on Windows. On macOS Swangz
   itself asks for no elevation in this issue (B6); the only privileged change is the configuration profile the
   administrator installs and approves in System Settings (E1). The person clicks a
   setup step that says exactly what will change; declining leaves everything as it was and shows the repair state.
2. **Never:** store, cache or ask for an administrator password inside Swangz; add a service, scheduled task,
   LaunchDaemon or sudoers rule that runs as SYSTEM or root to avoid later prompts; turn off UAC, Gatekeeper or SIP;
   run `xattr -d com.apple.quarantine`.
3. The elevated step does one fixed thing with **no input the person controls**. Its whole command line is
   `Swangz.exe admin <action>`, where `<action>` is one of `chrome-install`, `policy-write`, `policy-remove`; any other
   argument is refused. It reads no file, pack, script, path or value from a user-writable place, and no environment
   variable: system programs are called by absolute path from `GetSystemDirectory` (`msiexec.exe`), and folders are
   found with `SHGetKnownFolderPath`, never `%TEMP%`, `%ProgramData%` or `PATH`.
4. **Pinned pack values (rules on Forge's gap 3).** The pack needs **three** values, the same three that
   `deploy/chrome-policy/prepare.py` requires (`--hub-host`, `--extension-id`, `--update-url`, i.e. `SWANGZ_HUB_HOST`,
   `SWANGZ_EXTENSION_ID`, `SWANGZ_EXTENSION_UPDATE_URL`). None is taken from the enrolled state (user-writable). All
   three are pinned when the company build is installed with `/ALLUSERS`, by the elevated installer, in
   `HKLM\Software\Swangz\Pinned` (64-bit view): `hub_host`, `extension_id`, `extension_update_url`. The admin passes
   them on the installer's command line, or the release build carries them as constants. `policy-write` reads only
   these and validates each again with `prepare.py`'s own validators (never a second copy of the rules):
   - `hub_host`: the strict hostname pattern;
   - `extension_id`: 32 characters `a-p`;
   - `extension_update_url`: HTTPS on a DNS host, with no credentials, port, query or fragment (`update_address`).
     It must equal either the Chrome Web Store endpoint `https://clients2.google.com/service/update2/crx` or a
     self-hosted address on the pinned `hub_host`. Any other host is refused, because the update URL decides where
     every company Chrome fetches the force-installed extension's code.

   If any of the three is missing or invalid, no policy is written. The elevated step never compares the pinned host
   with the enrolled one: the enrolled state lives in the person's account, which B3 forbids it to read, and an
   admin elevating with their own account would see a different (or no) enrolment. That comparison happens in the
   **unelevated app, before it offers the step**: the app reads `HKLM\Software\Swangz\Pinned` (readable by every
   user) and offers `policy-write` only when the pinned `hub_host` equals the enrolled Hub host. This is a
   usability gate, not a security control; the security control is that the elevated step reads only HKLM.
   An "admin confirmation dialog" in place of pinning was rejected: a prompt inside an elevated step proves only that
   someone clicked, and the values would still come from the person's account.
5. **Only admin-only code is ever elevated (rules on Forge's gaps 1 and 2).**
   - **Windows.** The per-user install (`PrivilegesRequired=lowest`, `%LocalAppData%\Programs\Swangz`) never offers
     an elevated step; it shows "ask your administrator to install the company build". The company build is installed
     with `/ALLUSERS` into `%ProgramFiles%\Swangz` **and is a PyInstaller one-folder build**: today's one-file
     `Swangz.exe` unpacks its Python into the person's `%TEMP%` on every start, where any program running as the
     person can replace it before the elevated process loads it. At its start the elevated process checks, and refuses
     with `admin_install_required` unless: it is frozen and not one-file (`sys._MEIPASS`
     resolves to the `_internal` folder directly beside `sys.executable`, as PyInstaller 6 one-folder builds lay out); its folder
     is under the `ProgramFiles` known folder; the folder and every parent up to `ProgramFiles` is owned by
     Administrators, SYSTEM or TrustedInstaller and grants no write, delete or change-permission right to any other SID
     (including the person's own); the same holds for `Swangz.exe` and the one-folder's `_internal`.
   - **Staging (`chrome-install`).** The elevated process creates `%ProgramData%\Swangz` if missing with a protected
     DACL (SYSTEM and Administrators full control, no inheritance); if it already exists it must pass the same owner and
     DACL check, or the step stops with `staging_unsafe` (ordinary users can create folders in `%ProgramData%`, so a
     pre-made one is untrusted). Inside it, a new folder with a 128-bit random name, created with `CreateDirectory` and
     the same protected DACL, failing if it exists. The MSI is downloaded there (A1), its signature checked there (A2),
     installed with `msiexec.exe /i <that file> /qn /norestart`, and the folder deleted in a `finally`. The installed
     `chrome.exe` under `%ProgramFiles%` is then checked again (A3) before first use.
   - **macOS.** See 6.
6. **macOS has no elevated Swangz step in this issue.** The DMG is drag-installed and owned by the person, so a root
   step started from it would give root to whatever can write the bundle. When Chrome is missing, Swangz opens Google's
   Chrome download page (allowed by D2) and says which install it will accept; then A2/A3 verify the result, and A4
   requires `/Applications/Google Chrome.app` owned by root (Google's enterprise PKG, or Chrome's own "set up updates
   for all users"). Policy is the admin-installed profile (E1). An elevated macOS install comes back only with a new
   decision, after Swangz ships as a root-owned PKG.
7. Installing Chrome or the policy is a separate step that never runs on its own. The Swangz installers stay
   per-user for personal devices (#243). The company `/ALLUSERS` install (M1) needs
   `PrivilegesRequiredOverridesAllowed=commandline` in `swangz.iss`, which it does not have today, and a one-folder
   build; both are Prism's (`packaging/`).

*Tests:* the elevated entry point refuses any argv other than `admin <one of three actions>`. It refuses when: run
one-file (`sys._MEIPASS` under `%TEMP%`, not `<exe folder>\_internal`); it accepts a correct one-folder layout; run from a folder under `%LocalAppData%`; run from a folder whose DACL grants the person write (CI: create
one, grant the runner's SID, expect `admin_install_required`); `%ProgramData%\Swangz` pre-exists with a user-writable
DACL (`staging_unsafe`); any of the three pinned values is missing or malformed; the update URL is on any host other
than `clients2.google.com` or the pinned Hub host. The elevated step opens nothing under the person's profile or the
app data folder (fake filesystem records every read). The unelevated app does not offer `policy-write` when the
pinned host differs from the enrolled one. The staging folder is
gone after success and after a failed signature. `chrome-install` reads nothing from the app data folder (static test:
no path from `paths.data_dir` reaches it). Declining the prompt changes nothing. No code path writes a service, task or
daemon (static test). The macOS client contains no `osascript … with administrator privileges`, `AuthorizationExecute`
or `sudo` (static test).

**C. One browser folder per employee.**
1. Each person gets their own folder under the app's data folder, `browser-profiles/`, bound to (Hub origin, person,
   device, seat) by `browser_profiles.Owner`. On Windows its ACL grants the current OS user only (`verify_folder`). On
   macOS it is mode `0700`. It is checked before every launch.
2. On company devices, each employee has their own OS account. Two people on one OS account are not isolated from
   each other. When a different person signs in on the same OS account, the earlier person's folder is retired
   (deleted) before the new one is made, as R-12 already does for reassignment.
3. Nothing copies, exports, backs up or uploads a folder, its cookies or its tokens, not even between devices of
   the same person. Chrome sync stays off (`SyncDisabled`) and is not required. Provider and Google sign-in happen
   by hand in the window, with the provider's own consent and MFA.
4. A folder survives app restart, computer restart and **signing out of the computer** (so sessions persist). It is
   deleted on revocation (F), when the person changes (C2), and on **uninstall**: `Swangz.exe cleanup` (D-005,
   "nothing is left") closes the window and deletes every folder under **that OS account's** `browser-profiles/`
   (it never reaches another account's folders); a folder it cannot delete is named in the uninstaller's result,
   never silently left. `cleanup` always runs **as the person, unelevated** (it refuses an elevated token), and
   deletes link-safely (a reparse point or symlink is removed itself, never followed; only paths that still resolve
   inside the app's data folder are deleted). **No elevated or all-users uninstall ever deletes inside a
   user-writable folder**: junctions and links could point that delete at system files (see the company-installer
   amendment below). **Signing out of the app** keeps the folder,
   because the same person signs back in to their own sessions; a different person signing in retires it (C2).
   Today `remove_everything` on main keeps the folders in every case (R-12), and folder deletion raises
   `unsupported_platform` on Windows (`browser_profiles._purge`, `retire`); both are Forge's work.
   - **Windows per-user uninstaller** (`packaging/windows/swangz.iss`, `PrivilegesRequired=lowest`, so it runs as the
     person): today `[UninstallRun]` runs `Swangz.exe logout` with `runhidden`, which ignores the exit code, and the
     exe is built `--windowed`, so nothing it prints is seen. It must instead run cleanup from `[Code]`, in
     `CurUninstallStepChanged(usUninstall)`, before any file is removed: stop the person's running copy (the
     existing `taskkill` filter), then `Exec('{app}\Swangz.exe', 'cleanup --report "<{tmp} file>"', …, ResultCode)`.
     `cleanup` runs `logout` itself first, while the key exists, so a separate `logout` entry is dropped. On a
     non-zero `ResultCode` (or `Exec` failing) the uninstaller reads the report, one undeleted folder per line,
     shows it in a message box (skipped when `UninstallSilent`), and always writes it to the uninstall log with
     `Log`. The uninstall continues; it never claims everything was removed (Prism's, `packaging/`).
   - **macOS:** there is no uninstaller; removal is drag-to-Bin (`packaging/macos_dmg.py` README), which runs
     nothing. The removal steps there and in docs/CLIENT.md become: in Swangz choose "Remove Swangz from this
     account" (or run `Swangz.app/Contents/MacOS/Swangz cleanup`, which signs out first), then drag Swangz to the Bin
     (Prism's). Each macOS account that used Swangz does this itself. Dragging without these
     steps leaves the folders (Limitations).
5. Paths go into Chrome as one argv element each, never through a shell. Paths with spaces and non-ASCII characters
   are supported.

*Tests:* two owners produce two folders, and each cannot open the other's. A person switch retires the earlier
folder. A path with spaces and Unicode launches. The folder survives a restart and an app sign-out by the same
person. `cleanup` (uninstall) deletes every folder, and reports one it cannot delete (non-zero exit, named in
`--report`). Static: `swangz.iss` has no `runhidden` entry running `cleanup` or `logout`, and its `[Code]` checks
`ResultCode`; the company `.iss` runs no verb other than `admin policy-remove`. No API returns or uploads folder
content (static test).

**D. Launch: explicit Chrome, fail closed, no default-browser fallback.**
1. **Scope: the Swangz app (EXE, DMG).** In the app, a web tool has exactly two outcomes. Either it opens as
   `[verified chrome, --user-data-dir=<the person's folder>, fixed switches, url]` (`build_argv`), with the address
   coming from the Hub's `/device/open` answer and checked against the tool's own hosts, or it is refused with a
   repair message. Refusals include: no verified Chrome, a failed folder check, a failing policy in `enforce`, the
   Hub refusing, and the tool not being a workspace tool (4).
2. **No fallback.** The app never hands a tool address to `shell.open_url` / `webbrowser`, or to any other browser
   (Edge, Safari, Firefox, a Chromium fork). That covers a provider address, a `/go/<tool>` link and the manifest's
   `open` field. `open_url` stays only for the device code page, the Hub pages in `shell.HUB_PAGES`
   (weekly, devices, admin), and `workspace_launcher.INSTALL_PAGE`, which is Google's Chrome page from A1.
3. Native and CLI tools (Claude Code, Codex) are unchanged and never go through the browser launcher.
4. **Shared company accounts (rules on the #333 gap).** Shared accounts are refused in the app, fail closed, on
   every device. Two owner rules conflict here. #333 asks for every authorised web tool to open in the dedicated
   Chrome. MANAGED-WORKSPACE §2 point 2 says "no shared provider identity" in the workspace, and D-022 applies that
   rule. A shared account is a shared provider identity by definition. Until Arnold chooses between the two, the
   stricter rule holds:
   - `/device/open` keeps answering 409 `shared_account`, and the manifest keeps `workspace: false` for shared tools
     (D-022);
   - **on a company device**, the refusal message no longer sends the person to another browser. It says: "This is
     a shared company account. It does not open on this company computer yet; ask your administrator." The repair
     panel offers no button that opens a tool, `/go/` or the Hub's Tools page;
   - **on a personal device**, the message may still name Swangz AI Hub. That is the personal-device path, governed
     by the extension gate (D-024 point 4), and the app does not open it.

   If Arnold chooses #333 over §2 point 2, a new decision builds it in this shape:
   - a shared account opens in a separate folder for each turn, never the person's own folder, created when the
     turn starts and deleted when the window closes or the turn ends (and at the next start, before any launch);
   - `/device/open` takes the turn with the same checks as `/go/`, and records the device on the turn;
   - a company-browser (Neko) tool opens only under D-022's conditions: a fixed Neko host in machine policy, and a
     single-use launch code instead of `usr`/`pwd` in the address.
5. **The staff web app's `/go/<tool>` is not the app.** It stays the channel for personal devices and phones,
   unchanged, gated by the extension. On a company computer it is a known gap (see Limitations). The person can open
   the staff web app in another Chrome profile or in another browser and use `/go/`. Machine policy limits what any
   Chrome profile on that computer may reach, but it does not govern Edge or Safari. The Hub cannot tell which
   browser a `/go/` request comes from, so it does not refuse `/go/` per person: that would cut off the same
   person's phone. Closing the gap needs the company's own device management, which removes or locks other
   browsers. That is outside Swangz and outside this issue (operating plan v18 point 5: no OS-level enforcement).

*Tests:* with no Chrome present, `open_app` raises `no_browser`, and neither `open_url` nor `webbrowser.open` is called.
The same holds for a shared tool, a tool the Hub denies, an unknown tool and a non-workspace tool. In each case the
fake `open_url` records no call and no process starts. A static test parses `core.py`, `gui.py`, `cli.py`,
`repair.py` and `workspace_launcher.py`. It allows `open_url` / `webbrowser` only in `shell.open_url`, `shell.open_hub`,
the device-code step and the `INSTALL_PAGE` / Chrome-page repair actions, and it fails on any other caller. On a company
device the `shared_account` message names no other browser and the repair panel has no open-tool action. On a personal
device the existing message is kept.

**E. Machine policy: scope and conflicts (closes #194).**
1. **Scope.** Policy is written only on devices an admin has marked `company` (D-025):
   - Windows: `HKLM\Software\Policies\Google\Chrome`, 64-bit view, in the encoding of `packaging/windows/policy.py`
     `registry_values`;
   - macOS: a configuration profile (`.mobileconfig`, payload `com.google.Chrome`) that the admin installs and
     approves in System Settings, which macOS then exposes at `/Library/Managed Preferences/com.google.Chrome.plist`.

   The app never writes `/Library/Managed Preferences` directly on a real Mac; only the CI runner does that.
   **Personal devices never get a policy** and keep the extension gate (D-024 point 4). The only exception, below, is
   an administrator's own manual run of `policy-write` on a computer that is in fact company-owned.
   The `company` mark that matters is the admin's confirmation (D-025 point 2), which is **not built yet**. Until it
   is, the app never offers `policy-write`: the person's own `owner_kind` declaration is not enough to change every
   user's Chrome on a computer. **Except:** an administrator may run `Swangz.exe admin policy-write` by hand only on a
   company-owned computer, even one the Hub still lists as personal; never on a personal computer. The UAC consent
   is that administrator's decision, and the elevated step still applies B3–B5 and E3. Once D-025 point 2 exists, the
   unelevated app offers the step only when the manifest says the admin confirmed `company`.
2. **Setup states the cost plainly.** Machine policy applies to every Chrome window and every OS user on that
   computer, including personal browsing in Chrome, because the pack blocks everything not on the list. The admin
   confirms this before the step runs. Swangz never changes, deletes or hides an existing Chrome profile. Its own
   folder is separate.
3. **Conflicts fail closed; act only on what is still exactly ours (rules on Forge's gap 4).** Swangz's marker is
   `HKLM\Software\Swangz\ChromePolicy` (`sha256`, `written`), outside Chrome's key. `sha256` is taken over the key
   **as read back after writing**, never over the intended values: every subkey path and value under
   `HKLM\Software\Policies\Google\Chrome` (64-bit view), each as (subkey path, value name lowercased, registry type,
   data), sorted, serialised as JSON with `sort_keys`. The same function hashes the key before any change:
   - key absent, marker absent: write, read back, write the marker;
   - key present, marker present, current hash equals the marker: `policy-write` may rewrite, `policy-remove` may
     delete the key tree and then the marker;
   - key present and (no marker, or hash differs): refuse with `conflict`, change nothing, keep the marker. A value a
     GPO, MDM or person added after Swangz wrote is never overwritten or deleted;
   - key absent, marker present: delete the stale marker only.

   A GPO refresh between the hash and the write or delete is a remaining race; it is listed under Limitations.
   It reports the conflict for the admin to resolve and never merges. The check gets stricter in three ways:
   - (a) any policy name in the machine source that is not in the pack fails as `unexpected:<name>`. Examples:
     `ProxySettings`, `CloudManagementEnrollmentToken`, `ExtensionInstallSources`;
   - (b) on Windows, `HKCU\Software\Policies\Google\Chrome` is read too, and any value there fails as
     `user_policy:<name>`, since a user-level value fills gaps the machine key leaves;
   - (c) a non-empty `Recommended` subkey fails.
4. **#194 S1** is done: `ExtensionSettings` is in `FORBIDDEN`, D-024. A regression test should confirm it stays.
   Still to do:
   - **S2:** `check()` catches only `Unreadable` and `OSError`, so a `TypeError` or `RecursionError` from `merge` or
     `problems_in` escapes direct callers. Add a final `except Exception` that returns `unreadable`.
   - **S3:** `read_linux` parses a hidden `.x.json`. Any name starting with `.` should be `Unreadable`.
5. **Unenforced controls are reported, never assumed.** Setup reads whether the machine is domain-joined or
   MDM-managed and lists the pack policies Chrome may ignore on an unmanaged machine. In particular, Chrome may ignore
   force-installing an extension that is not on the Chrome Web Store. The list appears as "not guaranteed on this
   computer". "Enforced" is written only after the physical acceptance check of `chrome://policy` shows **OK** on that
   machine type.
6. **Rollback.**
   - Windows: an administrator runs the elevated `Swangz.exe admin policy-remove` (B5), which acts only under the
     hash rule in 3: it deletes the key tree and then the marker when the key still matches, and otherwise refuses
     with `conflict` and leaves both.
   - macOS: the admin removes the profile in System Settings.
   - The Hub setting `managed_policy_mode = warn` stops refusals at once.
   - Swangz never uninstalls Chrome.

*Tests:* writing over a foreign key is refused. An extra value, an HKCU value or `Recommended` each fail the check.
S1, S2 and S3 each have a regression test. Marker present but one value changed or added after the write: both
`policy-write` and `policy-remove` refuse with `conflict` and the key, the added value and the marker are all unchanged.
Matching key: remove deletes the tree, then the marker. Key absent, marker present: only the marker goes. The hash is
order-independent and changes with any type, name or data change. Personal devices never call the writer.

**F. Revocation: what is cleaned up, and what is not.**
1. **Local, by Swangz.** When the device is revoked or the person's access ends:
   - the Hub refuses further launches at once (server side, already in place);
   - at the next contact the app closes the managed window (`launcher.close`), retires (deletes) the person's browser
     folder (a locked folder becomes `purge_pending` and is deleted at the next start, before any launch), and removes
     the key and the Run, login or autostart item (#281, the macOS and Linux follow-up);
   - it **never touches machine policy or its marker**: the unelevated app cannot write `HKLM`, the policy covers
     every OS user on the computer, and clearing only the marker would make Swangz's own key look foreign and block a
     later setup (E3). The app shows, and reports at that contact, "Machine policy remains on this computer. An
     administrator removes it with `Swangz.exe admin policy-remove` (Windows) or by removing the profile (macOS)."
     The admin runbook lists this step;
   - offline, this waits for the next contact, within the D-021 grace period.
2. **Not by Swangz.** Provider-side sessions and refresh tokens, seats and licences, the person's Google sessions on
   other devices, anything the person already downloaded or copied, sessions in any other browser or Chrome profile,
   and a copy an OS administrator made earlier. The admin's runbook says to remove the seat and sign the person out in
   each provider's admin console, and Google Workspace's "sign out of all sessions". The console must say "access
   ended in Swangz; provider sessions must be ended in the provider", never "revoked everywhere".

*Tests:* after a revoke with the window open, the window closes, the folder is gone (or becomes `purge_pending`
and is gone before the next launch), and `open` is refused. The revoked device has no Run, login or autostart item.
Revocation never opens, writes or deletes anything under `HKLM` or `/Library` (a fake registry records every call; the
list of writes outside the app's data folder and `HKCU\...\Run` is empty), and the "machine policy remains" message is
shown when a marker exists. The console text distinguishes local from provider revocation.

**G. Must NOT be built.**
- Bundling, mirroring or hosting Chrome.
- Typing, storing or auto-filling provider or Google passwords; copying, exporting, backing up or uploading cookies,
  sessions or profiles; one person's session used by another (CLAUDE.md, D-022).
- Remote debugging, CDP or automation flags to drive or read the window; any content capture (CLIENT.md).
- Silent elevation, standing SYSTEM or root helpers, stored admin credentials, or disabling UAC, Gatekeeper, SIP or
  quarantine.
- A default-browser or other-browser fallback for any tool address.
- Policy on personal devices; changing or deleting the person's existing Chrome profiles or settings.
- Chrome Browser Cloud Management enrolment, a cloud or remote browser, or new server infrastructure.
- "Production-ready" or "enforced" claims without the physical acceptance evidence in #333.

**Limitations.**
- Tamper-evident, not tamper-proof (D-024): a local administrator can remove the policy or copy a folder.
- The policy is machine-wide: on a shared or personal computer it blocks the person's own browsing in Chrome.
- Two people on one OS account are separated by Swangz's rules, not by the OS.
- Unsigned RC builds trigger SmartScreen and Gatekeeper warnings until the certificates (Arnold's purchase) exist.
  Until then the UAC prompt for `Swangz.exe admin …` says "Unknown publisher", exactly as it would for any other
  program: the person cannot tell Swangz's prompt from malware's. B5's admin-only install protects what runs after
  "Yes", not the decision to click it. Signed company builds are required before this is called production-ready.
- Anything already running as the person can ask for elevation itself; B5 stops it from *borrowing* Swangz's
  elevated step, not from prompting on its own.
- macOS: no in-app Chrome install in this issue (A1, B6); the person or admin installs Chrome, and Swangz verifies it.
- **Not every authorised web tool opens in the dedicated Chrome yet (D4, D5).** Shared company accounts are refused
  in the app until Arnold chooses between #333 and MANAGED-WORKSPACE §2 point 2. On a company computer, the staff web
  app's `/go/<tool>` still opens tools in whatever browser the person uses there. Machine policy limits Chrome, but
  not Edge or Safari. #333's "every authorised web tool" is not met for these two cases, and the acceptance report
  must say so.
- A GPO refresh can land between E3's hash and the write or delete; the next check reports the mismatch.
- A3 remembers a pass by the main executable's size and modification time, in memory. On macOS a framework
  swapped in while the app runs is not rechecked until the app restarts; on a company Mac the bundle is root-owned,
  so only an administrator can do that. On Windows only `chrome.exe` is checked, not `chrome.dll`; under
  `%ProgramFiles%` the OS's permissions protect it, and on a personal device it is the person's own install (A4).
- After revocation, machine policy stays until an administrator removes it (F1).
- App sign-out keeps the browser folders, with their provider and Google sessions, on disk (C4). Until C4's
  uninstall change is built, uninstall leaves them too. On main, disconnecting the device also keeps them (F1 is not
  built); only an authenticated `retired` or a higher workspace generation deletes them, and not on Windows.
- macOS has no uninstaller: dragging Swangz to the Bin without running `cleanup` first leaves the folders (C4).
- The per-user Windows install (`%LocalAppData%`, personal devices) cannot install Chrome: it never offers an elevated
  step (B5). The person installs Chrome themselves; A3 verifies it, and A4 accepts a per-user Chrome only there.
- `policy-write` is not offered by the app until D-025 point 2 (admin-confirmed `company`) exists (E1), except an
  administrator's manual run on a company-owned computer, even one the Hub still lists as personal.
- Uninstalling the company build removes no person's folders: it is machine-scope only, and `cleanup` reaches only
  the account it runs in. Other OS accounts' folders, with their sessions, stay until F1 runs at that person's next
  contact or the person runs "Remove Swangz from this account". The admin runbook: disconnect the device in the
  console, or run `cleanup` in each account, **before** uninstalling.
- C2 deletes on a person switch when the second person's app next gets an authenticated answer, or opens the
  workspace; approving the sign-in alone deletes nothing. A person is the Hub address plus person ID in a folder's
  marker, so a changed Hub address counts as a different person. A folder whose marker can't be read is left (nothing
  says whose it is, and no owner is given it) until `cleanup`. While an earlier folder can't be deleted (for example
  while its browser is still open), the second person's Open is refused with `purge_pending`. The switch closes no
  browser, and no folder is retired while one runs on it: on macOS and Linux the app reads Chrome's `SingletonLock`
  and leaves the folder whole (deleting under a running Chrome kept its session alive and wrote the folder again with
  no marker); Windows refuses the rename. Limits: a lock left by a crash whose process number another program now has
  holds the folder until that program ends, and a browser started between the check and the rename is not seen.
- A person who signs out and back in gets a new device ID, so a new folder is made. The older one is kept and never
  reused: C4's "back to their own sessions" does not hold today.
- Force-installing the extension on unmanaged Windows or macOS may need the Chrome Web Store listing. Publishing it
  needs Arnold's approval.

**Alternatives rejected.**
- Bundling Chrome: needs Google's permission, and the copy goes stale.
- Accepting any `chrome.exe` on a fixed path: an unsigned binary would get the sessions.
- Writing `/Library/Managed Preferences` directly: Apple doesn't support it, and the system can remove it.
- Merging with an existing GPO or MDM pack: the app cannot tell which source wins.
- Keeping the folder after a revoke (the earlier R-12 reading): it leaves live sessions on a device the company has
  disconnected.

**Amended 2026-11-25 (Forge's review of dc1a607).** Gap 1 (swapped MSI): accepted, stricter than proposed: the
elevated step downloads into its own admin-only folder instead of copying (A1, B5). Gap 2 (elevating a user-writable
exe): accepted, and extended to the one-file build's `%TEMP%` unpacking (B5); unsigned-RC limit stated. Gap 3 (Hub
host): pin at `/ALLUSERS` install in `HKLM\Software\Swangz\Pinned` (B4); the confirmation dialog was rejected. Gap 4
(revocation and marker): accepted as proposed, with the read-back hash rule (E3, E6, F1). macOS gets no elevated step
in this issue (B6), replacing the proposed macOS copy-then-verify.

**Amended 2026-11-25 (Probe's review of #334).** B4 now pins three values (the extension update URL was missing),
with the update URL limited to the Web Store endpoint or the pinned Hub host. A1 and B1 now agree with B6: on macOS,
Swangz downloads, installs and elevates nothing. D1 no longer claims more than the code does: it is scoped to the app,
D4 rules on shared accounts and D5 on the staff web app's `/go/`, and both gaps are listed under Limitations.

**Amended 2026-11-25 (Probe's review of #338).** B4: the pinned-versus-enrolled host comparison moved from the
elevated step to the unelevated app before it offers the step (B3 reads nothing user-writable). C4: "sign-out" split
into computer sign-out and app sign-out (both keep the folder); uninstall deletes the folders; the revocation reference
is F. E1: `policy-write` waits for D-025 point 2. A2: the macOS carriers' Developer ID identities. Limitations: folders
left by sign-out and uninstall until built, per-user Windows Chrome, the D-025 dependency. D4 is unchanged (option A).
Second pass (Probe at 6e7120d): the Limitations line now matches main (disconnect keeps the folders; deletion is
unsupported on Windows); C4 requires the Windows uninstaller to run `cleanup` after `logout` and adds it to the macOS
removal steps; E1 names the manual-run exception; D2/D4 marked done by #339.

**Amended 2026-11-25 (Sentinel's review of #342, the company installer).**
- **B7.** The company install is its own script, `packaging/windows/swangz-company.iss`, with its own AppId. It
  installs only with `/ALLUSERS`, only into `%ProgramFiles%\Swangz`, and only as the one-folder build. `swangz.iss`
  stays per-user and never elevates. This replaces "in `swangz.iss`" in B7: two installer identities cannot
  overwrite or uninstall each other, and the personal installer gains no elevation path.
- **B4 at install time.** The installer checks only that the three values were typed whole, and that all three or
  none were passed. An upgrade with none keeps the recorded values. `prepare.py`'s validators stay the only rule set,
  applied by `policy-write` (B4). The unelevated app's offer check (B4) names a pinned value that fails those
  validators, so a mistyped install is visible before anyone elevates.
- **C4 on the company build.** The company uninstaller is machine-scope only. It stops the program and removes the
  program folder, the shortcuts, the Apps entry and `HKLM\Software\Swangz\Pinned`. It runs no Swangz code over a
  person's profile: no `logout` or `cleanup`, and no elevated delete of anything under any user profile. An
  elevated recursive delete of user-writable folders is an arbitrary-delete primitive (junctions), and it would see
  only the administrator's own profile anyway.
  - **Per-person removal happens as the person, unelevated.** The supported order for retiring a company computer is:
    1. Disconnect the device in the console. At each person's next contact, F1 closes the window, deletes their
       folders and removes their key and Run item. Alternatively, each person runs "Remove from this computer"
       (`Swangz.exe cleanup`) in their own session.
    2. Then the administrator uninstalls.

    "Sign out in the app" alone is not enough, because app sign-out keeps the folders (C4).
  - **Stale Run items are accepted.** A Run item left in a person's `HKCU` points into `%ProgramFiles%\Swangz`, which
    only administrators can recreate, so it cannot be hijacked (Limitations).
  - **Machine policy.** When `policy-write` ships, the company uninstaller's first step is
    `{app}\Swangz.exe admin policy-remove`, run by the administrator from the admin-only folder, reading only `HKLM`,
    under E3's hash rule. On `conflict` it leaves the policy, logs it and says so, and the uninstall continues. Without
    this step no Swangz program would remain to remove the policy.
- **What the cleanup PR builds (Forge).** `Swangz.exe cleanup`:
  - refuses with `elevated_refused` when its token is elevated;
  - closes the managed window, runs `logout` while the key exists, then deletes every folder under
    `browser-profiles/` on every platform, Windows included;
  - deletes a reparse point itself, never its target, and deletes only paths that still resolve inside the app's data
    folder;
  - removes the `HKCU` Run item;
  - names every folder it could not delete and exits non-zero;
  - is idempotent.

  The app's This device page offers it as "Remove Swangz from this account". `cleanup` takes `--report <file>`
  (one undeleted folder per line). The per-user `swangz.iss` runs it from `[Code]` and reports failures (C4); it
  needs no separate `logout`, because `cleanup` runs `logout` first.

  *Tests:*
  - an elevated token is refused;
  - a junction inside `browser-profiles/` pointing outside is removed, and its target is untouched;
  - a locked folder is reported, with a non-zero exit;
  - a second run changes nothing;
  - static: the company `.iss` runs no `Swangz.exe` verb other than `admin policy-remove`.

**Consequences.** Forge builds A–F behind these tests on feature branches. Sentinel reviews each PR before merge.
The elevated Windows steps (`chrome-install`, `policy-write`, `policy-remove`) are not built until Prism has made the
company build one-folder and `/ALLUSERS`-capable with the B4 pinned values (`packaging/`, `swangz.iss`); Forge may build
the launch, folder, verification, conflict-hash and revocation parts (A2–A4, C, D, E3–E5, F) first.
**D2 and D4 build: done** by #339 (merged as `7b95da0`): the shared-account refusal on company devices (message and
repair panel) and the D tests (no `open_url` call for shared, denied, unknown and non-workspace tools; the static
caller allow-list). No server change and no migration.
**C2 build:** `Profiles.retire_other_people` calls `retire_owner` for every other person's marker, on the first
authenticated answer and again before a folder is prepared (`Launcher.ready`); the same person's folders are kept.
**Next for C2, C4 and F1:** `cleanup` and revocation delete the folders on every platform (Forge); the per-user
Windows uninstaller runs `cleanup` from `[Code]` with its result reported, and the macOS removal steps include it (Prism).
`enforce` stays off until D-025 point 2 and E5's acceptance check exist. R-12 changes: a folder is deleted on
revocation, as well as on reassignment.

**Amended 2026-11-25 (Probe's third pass on #338, final).** The per-user Windows uninstaller runs `cleanup` from
`[Code]` with its exit code and `--report` checked, shown unless silent and always logged; `[UninstallRun]` no longer
runs `logout` or `cleanup` hidden (this replaces "after `logout`" in the second pass). `cleanup` reaches only its own
OS account, runs unelevated and deletes link-safely; no elevated uninstall deletes inside a user-writable folder. New
Limitations: the company uninstall leaves other accounts' folders (runbook: disconnect or `cleanup` per account
first), and C2's retirement is not wired on main. E1: the manual run only on a company-owned computer. A2: the two
Developer ID clauses from Chromium's requirement.

## D-027 | 2026-11-25 | Shared company account opened in the Swangz app's own Chrome, on staff computers (option B-local, #333)

**Context.** D-026 D4 refused shared company accounts (`signin = 'shared'`) in the app, because #333 ("every authorised
web tool in the dedicated Chrome") conflicted with MANAGED-WORKSPACE §2 point 2 ("no shared provider identity") and
D-026 C3 (one folder per person, never shared). #339 built that refusal. On 25 Nov 2026 Arnold chose option B, through
Chief: the shared account is the Google account that holds Swangz's AI subscriptions (the Claude and ChatGPT plans the
team uses). **Only Arnold signs it in**; an admin can only issue the setup code (1). Before choosing he was told that a
local administrator or malware on a staff computer can copy the session, and that the turn holder can reach the
account's Gmail, Drive and Google settings and could take it over. This decision is his product choice.

**What it supersedes, for this path only** (a shared tool opened in the app on an admin-confirmed company device):
MANAGED-WORKSPACE §2 point 2; D-026 C3; D-022's refusal; D-026 D4's "a separate folder for each turn, created when the
turn starts and deleted when the window closes" (replaced by one kept folder, 2 and 3); and the D-026 G item "one
person's session used by another". Everywhere else those rules stand. The remote company browser (Neko, D-022) and the
staff web app's `/go/` are unchanged. **Personal computers are excluded entirely**: no shared folder, no setup code,
the 409 stays. **#339's refusal stays on main until the build below is reviewed and the activation PR (task 7) lands.**

**Threat note (STRIDE, short).**
- *Assets:* the shared Google session (refresh cookies) and the provider sessions in the shared folder; the account's
  Gmail, Drive, Gemini and Google settings; the Claude and ChatGPT plans, their billing, history, memory and connectors;
  the plans' usage limits, which the team's own tools also draw on; Arnold's password and 2-step while he types them.
- *Entry points:* the setup code and the setup window; `/device/open` for a shared tool; the shared folder on disk; the
  open window; accounts.google.com, gemini.google.com, claude.ai, chatgpt.com and openai.com, which the pack allows.
- *Abuse cases:* (1) the folder is copied and the account used elsewhere with no turn and no record; (2) the turn
  holder changes the account's password, 2-step or recovery settings and takes the account over; (3) the turn holder
  reads Gmail or Drive, directly or through Gemini or a provider connector; (4) the turn holder reads others' chats,
  cancels a plan, creates API keys, exports data or deletes a provider account; (5) the window outlives the turn
  (app quit, crash, a Chrome already running on the folder); (6) someone signs a different Google account into the
  folder; (7) the account is suspended for sharing and the team's plans stop with it; (8) a revoked person keeps a
  session; (9) a turn for one tool is used to reach the other shared tool in the same folder; (10) a keylogger on the
  computer captures Arnold's password during setup; (11) one turn used from two places (app and `/go/`).

**Decision.**

**1. Sign-in: by hand, by Arnold only, never by Swangz.**
- Swangz never stores, shows, transmits or fills the account's password, 2-step codes or recovery details. The gateway
  keeps no identifier, password or cookie of this account (CLAUDE.md, D-026 G).
- Setup per computer: in the console (Devices, a company device, area `govern`), an admin issues a one-time setup code
  (128 bits or more, valid 10 minutes, bound to that device, single use, stored as a hash, audited). Issuing a code is
  all an admin does; the admin never signs the account in. On that computer the app's "Set up shared account" field
  takes the code; `/device/shared-setup` checks it and the app opens the shared folder at
  `https://accounts.google.com/` with no turn. Arnold types the password and approves 2-step on his own phone.
  **Setup signs in to Google only.** He does not sign in to Claude or ChatGPT during setup: with no turn the extension
  blocks those hosts in both states (3a, task 6). The first turn holder for each tool enters it with "Continue with
  Google" on the Google session Arnold left (3a).
- **The setup window has a deadline and a Done step.** It closes at 10 minutes after the code was accepted (a local
  timer, also offline), when Arnold presses Done in the app, and when a check-in says the device was revoked or
  `shared_browser` was turned off. While the setup window or a shared window is open the app checks in every minute
  (3), so that close takes up to about a minute online; offline only the local timer applies. Done and timeout are
  reported in the next check-in, and the server audits them as `shared setup ended` with the reason (task 2). Without
  a valid code the app never opens the shared folder outside a turn.
- Arnold does setup only on computers he trusts, and prefers a passkey or security key to typing the password (see
  What cannot be enforced).

**2. One shared folder per company device, separate from every person's folder.**
- One folder per enrolled device, a `browser-profiles/` entry bound to (Hub origin, `shared`, device), used only for
  tools with `signin = 'shared'` that the admin has set to open in the app. A person's own folder never opens a shared
  tool, and the app never sends a non-shared tool to the shared folder. Same checks as D-026 C1 and C5 (owner-only
  ACL or `0700`, checked before every launch). The Hub's own address never opens in it (existing rule).
- **One folder holds every shared provider session** (Google, Claude, ChatGPT). The app opens only the turn's tool, but
  a window on the folder can navigate to any host the pack allows. Containment between tools is the extension (3a);
  what stays open is listed under What cannot be enforced.
- **Company devices only, confirmed by an admin:** the device needs `owner_kind = company` confirmed by an admin
  (D-025 point 2, not built yet) **and** a separate per-device switch, `shared_browser`, that an admin turns on
  (area `govern`, audited with before/after). The switch refuses to turn on unless the request records the admin's
  confirmation of the point 5 checklist.
- **Machine policy must pass, in any mode.** `/device/open` for a shared tool and `/device/shared-setup` each carry the
  app's policy report in the request body (`"policy": {"ok", "sha256"}`, as `/device/open` already does,
  device_open.py). The app computes it fresh (`POLICY_MAX_AGE`, 60 seconds, core.py); the server refuses unless that
  request's report is `ok` and its hash equals the Hub's baseline, whatever `managed_policy_mode` is (`warn` too). A
  report from an earlier request is never used. The app also refuses on its own check before the window starts (no
  baseline known = refused). Refusal: 409 `workspace_policy`.
- On a company device each employee has their own OS account (D-026 C2), so the folder belongs to that OS account.
  Arnold signs in once for each such enrolment.

**3. Turns.**
- `/device/open` for a shared tool runs the same checks as `/go/` (`launch_checks`, policy, `managed.launch_refusal`),
  then takes the turn and records the device on the turn (nullable `device_id` on `tool_turns`, new migration). Busy:
  refused with when the turn frees. The answer carries the tool's own start address (checked against its own hosts,
  as today) and the turn's end time.
- **One turn, one place.** Today `turns.take` returns a person's existing turn unchanged from any device or `/go/`
  (turns.py, the `mine` branch). For shared tools that changes: `/device/open` reuses an existing turn only when its
  `device_id` is this device (same end time, never extended); a turn held through `/go/` (`device_id` NULL) or on
  another device is refused with 409 `turn_elsewhere` and its end time. `/go/` refuses a shared tool whose turn is
  bound to a device the same way. The person releases the turn first.
- The app closes the shared window at the turn's end **by a local timer**, also offline, and earlier when a check-in
  says the turn was released, the person was refused, `shared_browser` was turned off or no shared tool is set to open
  in the app (the last two also delete the folder, 4). The normal heartbeat is every 15 minutes (`HEARTBEAT_SECONDS`,
  core.py); **while a shared or setup window is open the app checks in every 60 seconds**, so these closes take up to
  about a minute online. A new window always needs a new `/device/open`.
- **Tracking the window.** Chrome forwards a second launch on the same folder to the running window, so the app may not
  own the process that holds the folder (workspace_launcher `_start` keeps only the PID it started). For the shared
  folder the app records the PID and process start time of the Chrome it started, in its own state, and on every app
  start and before every shared launch it checks the folder's Chrome lock. A recorded process whose PID and start
  time both match is closed at the turn's end, also after an app restart. A Chrome on the folder that the app did not
  start (or whose start time does not match) is never signalled: the app refuses to open (`shared_window_open`,
  "close the shared Swangz window first") and reports it in the next check-in; the server records it as a device
  event and audits it (task 2).
- The folder is **kept** between turns. Deleting it would mean Arnold signs in again for every turn.

**3a. The extension in the shared folder.** The force-installed extension is signed in by the person, with their own
Hub account. What it does today (extension/background.js):
- **Signed in:** a shared tool's host opens only while the person holds that tool's turn. Without one it clears that
  host's site data (`signOutOf`) and shows the blocked page. It checks turns every minute and clears the sites of
  turns that ended, and clears every held shared site when Chrome starts. So a Claude turn cannot open ChatGPT in the
  same folder, and a window left open after the turn loses the provider session within about a minute while online.
  The Google session (accounts.google.com is not a tool host) is kept, so each new turn re-enters the provider with
  "Continue with Google", with no password. This works only if both provider accounts use Google sign-in.
- **No shared tool may live under `google.com`.** Clearing a site's cookies through `chrome.browsingData` clears the
  whole registrable domain, so clearing a `gemini.google.com` tool also clears `accounts.google.com` and ends the
  Google session Arnold left; the next turn could not re-enter without his password. The Hub's `/api/gate/turns`
  lists **every** `signin = 'shared'` tool the person does not hold, not only those that open in the app. So: **while
  any `signin = 'shared'` tool has a host under `google.com` (Gemini included), nothing shared opens in the app**, and
  task 2 refuses with 409 `shared_account`, with a test. Gemini is never a shared tool on this path.
- **Signed out:** today it gates nothing; every allowed host opens. For the shared folder that is fail-open, so task 6
  makes a signed-out extension block the shared providers' hosts on company devices. A never-signed-in extension has
  no host list from the Hub, so the list comes from the pack (task 6), not from the Hub.
- **Setup is Google only** (1): with no turn, both states block claude.ai and chatgpt.com, so no provider sign-in is
  made during setup and no setup exemption is built.
- Probe verifies both states on a test computer before the activation PR.

**4. Removal.** The shared folder is deleted (D-026 F, `cleanup`) when: the device is revoked; `shared_browser` is
turned off; no shared tool is set to open in the app any more; the person on the enrolment changes (C2); the person
runs "Remove Swangz from this account" (`cleanup`, unelevated, in their own OS account, D-026 C4). A locked folder
becomes `purge_pending` and is deleted before any launch. Shared folders exist only on company devices, and **the
company build's uninstaller deletes no person's folders** (D-026 C4, company-installer amendment: no elevated delete
inside user-writable folders). So the shared folder must go **before** the uninstall: disconnect the device in the
console and let F1 run at each account's next contact, or run `cleanup` in each account, then uninstall. An
uninstall alone leaves every account's shared folder, and with it the shared Google session, on disk. **Deleting the
folder does not end a copied session.** That needs the procedure in 6.

**5. Containment Arnold sets on the accounts before the first computer is enabled.** The console shows this list on
the `shared_browser` switch, and the switch's audit entry records that the admin confirmed it.
- *Google account:* 2-Step Verification with Google prompts on his own phone, a security key or a passkey, not SMS
  alone; recovery phone and recovery email are his own and known to no staff member; no app passwords; sign-in alerts
  to his own address; he reviews Security → Your devices weekly. Keep nothing in that Gmail or Drive that staff must
  not read.
- *Gemini:* `gemini.google.com` is on the pack's allowlist, and Gemini can read Gmail and Drive through its Google
  Workspace apps. Gemini is never a shared tool on this path (3a). Turn those apps off for this account, or remove
  `gemini.google.com` from the pack (machine-wide).
- *Claude (claude.ai) and ChatGPT (chatgpt.com):* the turn holder sees **all** history on the account, including
  Arnold's own and every earlier turn holder's, plus Projects, files and memory, and can reach the billing page
  (change or cancel the plan), data export and account deletion. Arnold: disconnect Gmail, Drive and other connectors
  on both; turn memory off; delete or move chats he does not want shared; keep the payment method one that a plan
  cancellation cannot extend to other charges. The plans' usage limits are shared with the team's own tools, so a turn
  holder's heavy use slows them.
- *OpenAI platform:* the pack allows `openai.com` with subdomains, so `platform.openai.com` (API keys, organisation
  billing) is reachable if this account has an API organisation. Arnold confirms it has none, or the pack narrows
  `openai.com` to the hosts ChatGPT's sign-in needs (machine-wide; Probe confirms the list).
- *What the pack already blocks:* everything not on the allowlist, so `mail.google.com`, `drive.google.com`,
  `myaccount.google.com` (password, 2-step, recovery, devices), `pay.google.com` and the Play Store are blocked.
  `accounts.google.com` stays allowed (exact host), because Google sign-in and "Continue with Google" need it. From
  there the turn holder can sign the account out, start "add account" or open account recovery. **UNVERIFIED:** that
  the password, 2-step and recovery settings cannot be changed from `accounts.google.com` alone (Google may serve
  some of those steps there). Probe tests it on a separate test account with the pack applied before the activation
  PR; until then, treat a turn holder as able to take the account over.
- Path blocks on SPA sites (for example `claude.ai/settings/billing`) are **not** a control. They apply to every
  Chrome profile on the computer, and in-page navigation bypasses them. They are not added.

**6. "Sign out of all sessions" procedure** (Arnold, on his own device). Run it when a person with a shared folder
leaves, a computer is lost or sold, a copy is suspected, and once a month:
1. Google: change the password (this signs out other sessions), then check Security → Your devices and sign out any
   that remain.
2. claude.ai and chatgpt.com: use each one's "log out of all devices" where offered (ChatGPT: Settings → Security).
   Provider sessions survive a Google sign-out, so this step is separate.
3. Google: Security → third-party access, remove anything unknown.
4. Console: turn `shared_browser` off on the affected devices, then sign in again on each remaining computer (1).
   Every staff computer needs his sign-in again after step 1.

**7. Hub sign-in: no change.** The account is not `@swangzavenue.com` and not one of the two approved owner
exceptions (`config.OWNER_EXCEPTIONS`), so it cannot sign in to the Hub or the console. It must never be added.

**What cannot be enforced (stated plainly).**
- The person whose OS account holds the shared folder, anything running as them, and any local administrator can copy
  its cookies **at any time, not only during a turn**, or start Chrome on the folder by hand, and use the account with
  no turn and no record. Turns gate the Swangz window, not the session. Preventing this would need Chrome to run as a
  separate OS account, which needs a standing elevated helper (forbidden by D-026 B2). Every person with a shared
  folder effectively holds the account all the time.
- **One folder holds every shared provider session.** A copy of the folder, a hand-started Chrome or a signed-out
  extension (until task 6) exposes Google, Claude and ChatGPT together, not only the turn's tool.
- **Arnold's password and 2-step approval can be captured** when he types them on a staff computer: a keylogger, a
  malicious extension or screen capture running as that OS account or as an administrator sees them. A passkey or
  security key avoids typing the password; a captured 2-step prompt approval still gives one session. Setup only on
  computers he trusts.
- **A window can outlive its turn.** Quitting the app, an app crash, or a Chrome already running on the folder leaves
  Chrome open: the app closes a recorded window at its next start or at the turn's end, and a signed-in extension
  clears the provider site within about a minute while online. Release, revoke and switch-off reach an open window
  only at the next check-in (about a minute while it is open); offline only the local timers apply. Offline, with the
  app not running, the window stays open until someone closes it.
- Which Google account is signed in: anyone in the window can sign out and sign in a different one. Policy cannot
  restrict web sign-in for a consumer Google account.
- What the turn holder does on the provider sites: reading history, cancelling a plan, exporting data, deleting a
  provider account. Recovery is through the provider's support.
- Use of the account outside the window cannot be attributed to a person.
- Vendor terms: one consumer account used by many people from many computers may breach Google's, Anthropic's and
  OpenAI's terms. A suspension stops the team's Claude and ChatGPT plans too. Google may challenge or lock the account
  for sign-ins from many places; recovery depends on Arnold's recovery settings.
- D-024 holds: tamper-evident, not tamper-proof. The server's policy check (2) trusts the app's own report.

**Alternatives rejected.** The remote company browser (Neko) inside the app's Chrome (B-remote) keeps the session on
one server, and no staff computer holds it. Arnold chose B-local. B-remote stays available under D-022's conditions.
A fresh folder per turn (D-026 D4's shape): Arnold would have to sign in for every turn. One folder per shared tool:
each still holds the full Google session, so it separates nothing the extension does not, and doubles Arnold's
sign-ins. One folder for the whole computer, shared by its OS accounts: needs a folder other OS users can read, which
exposes it to every account on the machine.

**Consequences and build (Forge for gateway/ and swangz_client/, Prism for extension/ and the pack; Sentinel
reviews each; the #339 refusal stays until task 7).** Gated on D-025 point 2 (admin-confirmed company) and D-026
C4/F1 folder deletion working on that platform, including Windows. Smallest tasks, each one PR with its tests:
1. **Migration and switches:** in the next `SCHEMA` entry, a nullable `device_id` on `tool_turns`, `devices.shared_browser`
   (default 0) and a per-tool "open in the app" flag (default off). Console routes with `area='govern'` and
   `ctx.audit(before=, after=, correlation='device:<id>' / 'tool:<id>')`, refusing `shared_browser` unless the device's
   company kind is admin-confirmed and the request carries the point 5 confirmation. *Tests:* permission sweep
   (V2PermissionTests); refused for a personal or unconfirmed device; refused without the containment confirmation,
   and the audit row records it when given; viewer cannot change either switch.
2. **`/device/open` for shared tools, the manifest and the heartbeat:** **lands switched off**: a server constant
   (`SHARED_IN_APP = False`) keeps the 409 for every client; its tests switch it on. With it on, both switches on, the
   device confirmed company, the request's own passing policy report with the baseline hash (any mode) and the
   `shared_folder` capability **in that request** (never stored from an earlier one), take the turn with the same
   checks as `/go/`, record `device_id`, return the start address and the end time; otherwise the existing 409
   `shared_account` (or `workspace_policy`, `turn_elsewhere`); also 409 `shared_account` for every shared tool while
   any `signin = 'shared'` tool has a host under `google.com` (3a). The manifest (`GET
   /device/manifest?browser_contract=2`, enroll.py, today `workspace: false` for every shared tool) gives a shared tool
   `workspace: true` only when the switches, the company kind and the `google.com` rule allow it and that GET carries
   the `shared_folder` capability; a GET has no policy report, so the report is checked at open and setup only. An old
   client never calls `/device/open` for a shared tool. The heartbeat answer carries the shared state: the device's
   turn (tool, end) or none, `shared_browser`, and whether any shared tool opens in the app; it accepts the one-minute check-in while a shared
   window is open (rate-limited), and receives and audits setup Done or timeout (`shared setup ended`, with reason) and
   `shared_window_open` (`correlation='device:<id>'`).
   *Tests:* busy turn refused with its end time; a turn from `/go/` or another device refused `turn_elsewhere`, and
   `/go/` refused for a device-bound turn; a same-device repeat returns the same turn, not extended; denied,
   expired-grant, suspended and revoked refused before any turn; missing, failing, stale or wrong-hash policy report
   refused in `warn` and `enforce`; the turn row carries the device; a personal device always 409; the address is the
   tool's own host; any shared tool with a `google.com` host (set to open in the app or not) makes every shared open
   409 and every manifest entry `workspace: false`; the heartbeat reports release, switch off and no shared tool;
   with the constant off every client gets 409 and the manifest says `workspace: false`; a capability sent only on an earlier request is not honoured;
   setup ended and `shared_window_open` produce their audit rows.
3. **Setup code:** console issues a code (≥128 bits, 10 min, single use, device-bound, stored as a hash, audited);
   `/device/shared-setup` accepts it once, under the same policy check (the report in its body), and returns only
   `https://accounts.google.com/`.
   *Tests:* reuse, expiry, wrong device, a code from another device, a missing switch and a failing policy report are
   refused; no route returns or logs the code after issue.
4. **Client:** declares the `shared_folder` capability; the shared folder (bound to (origin, `shared`, device)) used only
   for shared tools; its own fresh policy check before any shared window; the PID and start-time record and the lock
   check (3); the setup window's deadline, Done button and close on revoke or switch off (1); the 60-second check-in
   while a shared or setup window is open; closes the window at the turn's end by a local timer and on the check-in
   signals; reports setup Done or timeout and `shared_window_open`; never opens outside a turn except after a valid setup
   code; deleted in every case in point 4. *Tests:* a person's folder never opens a shared tool and the reverse; the
   window closes at the end time with the network down; a recorded window is closed after an app restart, a PID whose
   start time differs is never signalled, and an untracked Chrome on the folder refuses the open; setup window closes
   at 10 minutes, on Done, on revoke and on switch off; release, switch off and no shared tool close the window (the
   last two delete the folder); no `open_url` call for shared tools (#339's static test stays); folder deleted on
   revoke, switch off, person change and `cleanup`; nothing from the folder is read, uploaded or logged.
5. **Console copy:** the point 5 checklist on the switch, the point 6 procedure in the admin runbook, and the text
   "access ended in Swangz; the shared account's sessions end only with the sign-out procedure".
6. **Extension and pack (Prism; Sentinel reviews it as a D-024 baseline change):** the extension's manifest gets a
   managed-storage schema (`storage.managed_schema`) with `company` (boolean) and `shared_hosts` (list). The company
   pack sets them through Chrome's per-extension policy for the Swangz extension's ID (Windows: the registry key
   `...\Policies\Google\Chrome\3rdparty\extensions\<id>\policy`; macOS: the preference domain
   `com.google.Chrome.extensions.<id>` in the configuration profile), written by the same
   elevated setup from the pinned values (D-026 B3/B4), and the baseline hash covers it, so changing it is a policy
   mismatch. `shared_hosts` is a fixed list in the company build: the own hosts of the shared tools (claude.ai,
   chatgpt.com, chat.openai.com; never a `google.com` host, 3a). Adding a shared tool needs a new
   pack and baseline; task 2 refuses a shared tool whose own hosts are not all in a server copy of the list. With
   `company` true and no Hub sign-in (including never signed in), the extension blocks every `shared_hosts` host. A
   person's own folder never opens a shared tool, so this costs nothing there. *Tests:* signed out (and never signed
   in) with `company` blocks claude.ai and chatgpt.com; without managed config it is unchanged (personal devices);
   signed in without a turn clears the site and blocks; a turn for one shared tool does not open the other; the pack
   writes the per-extension values on both platforms and the baseline changes when they change; the server's list
   equals the pack's.
7. **Activation (last, after Sentinel's review of 1-6 and Probe's checks in 3a and 5):** a separate small PR that sets
   `SHARED_IN_APP = True`. Until it lands, every client gets 409 `shared_account`. *Tests:* an old
   client without the `shared_folder` capability gets 409 even with every switch on; before activation, a new client
   gets 409 too.
