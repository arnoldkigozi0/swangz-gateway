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
