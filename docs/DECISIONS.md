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
existing heartbeat with the agent's release as the real boundary. Existing risk R-10: `/go/` already sends `usr`/`pwd`
in a 302 `Location` into the person's browser history; the single-use code is its fix, after 20 Nov. Tests T1–T6 in
the threat note.
