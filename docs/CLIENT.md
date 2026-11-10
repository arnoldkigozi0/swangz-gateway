# The Swangz app — Swangz AI Hub on a person's own device

People install the **Swangz app** on their laptop (Windows, macOS, Linux). It is the company's door on that
device: they sign in once, and it brings them what the company has made available — the coding agents
(Claude Code, Codex) pointed at the gateway, the browser access gate, website tools opened through Swangz
(including company browsers for shared accounts), and anything Swangz publishes (templates, scripts,
connectors). Phones and tablets use the installable staff web app (already a PWA); they can't run coding agents.

Code: `swangz_client/` (standard library only, runs from source or as a packaged program). Server side:
`gateway/enroll.py`, schema v21 (`gateway/device_schema.py`). Tests: `tests/test_devices.py` (server),
`tests/test_client.py` (client against a real gateway), `tests/test_client_gui.py` (the window; needs Tk and a
display — `xvfb-run -a python3 -m unittest tests.test_client_gui`).

## How a device joins (the device-code flow)

1. The app asks the gateway for a code (`POST /api/device/code`) and shows it, big, and opens the browser.
2. The person, signed in to Swangz AI Hub in their own browser, opens `/device`, checks what is asking (name,
   system, version, the address it asked from) and presses **Approve**, saying whether the device is *their
   own* or *company-owned*. The page carries a CSRF token and warns that it must only be approved when they
   started it themselves, just now — the one real risk of this flow is being tricked into approving someone
   else's code.
3. The app collects its key once (`POST /api/device/token`). It writes to the native credential store and
   reads it back before committing: Windows Credential Manager (local-machine persistence for this user,
   never roaming), macOS login Keychain through `security -i`, or Linux Secret Service through `secret-tool`.
   The subprocess adapters receive the secret through stdin, never argv. Nothing is typed or pasted.

When the native service cannot store and retrieve the key, the app keeps a protected file and shows
**Key kept in a protected file — this device has no working keychain.** Unix files are mode 0600; Windows
files receive a protected owner/SYSTEM DACL before content is written. Windows defaults to `%LOCALAPPDATA%`,
not roaming `%APPDATA%`. No service is installed or unlocked automatically. A locked existing native item
produces a retryable error; it does not silently create another file or discard the device identity.

On upgrade, `device.key` is imported and compared with a retrieved copy. Only after an atomic metadata
commit does the app overwrite and unlink the old file. A restart can recover either the original file or
the verified native item, including interruption during overwrite. Windows reads the old Swangz roaming
folder for migration; a fallback must be copied to local storage and read back before the roaming key is
removed. Overwrite cannot guarantee removal from SSD history, filesystem journals or backups.

An enrolled device **is** an ordinary gateway key plus a `devices` row, so budgets, policies, the kill
switch, "disconnect this device" (staff app or console) and the console's Devices page all apply unchanged.
Ten devices per person, the same limit as hand-made keys; `staff_self_keys` off means an admin connects them.

## What the device is offered

`GET /api/device/manifest` — computed by the server from the same rule as everywhere (company subscription
active **and** the person assigned): Claude Code and Codex if assigned, the browser access gate for everyone,
published packages the person or their department (or `*`, everyone) is granted for this operating system, and
the website tools they may open (`/go/<tool>`, which checks access, records it and, for a shared account, hands
them a company browser of their own — the credential rules in CLAUDE.md are unchanged). The app installs
exactly this and removes what is no longer offered. The key is never in the manifest.

## Personal and company devices

| | Personal device | Company device |
|---|---|---|
| Claude Code / Codex | `swangz run claude` / `swangz run codex` set the gateway and key only in the child environment; personal tool settings are untouched | Managed Claude is gated on every OS pending verification of the deployed CLI's `/anthropic` prefix. Old managed tokens are removed and the app offers existing scoped runs. Unix Codex uses a marked provider block and a login-profile helper. Windows managed Codex is gated: use `swangz run codex`. Managed Codex also requires Python 3.11+ to validate existing TOML safely. |
| Signing out | removes the Swangz folder | also takes our lines back out of those files — only what we wrote and only if still ours — leaving anything the person changed since |

Managed migration removes the old Claude token only when its fingerprint still matches our recorded write.
It removes the legacy Windows `SWANGZ_AI_KEY` registry value only when it still equals this device's key;
there is no `setx`. Changed or unrelated values survive. Existing conflicting authentication settings are
left alone and reported. New managed text blocks have fingerprints so edited blocks survive removal.
Original settings backups are private; an exact known managed key in an old Claude backup is scrubbed.

`swangz key --for claude-code|codex` is an internal helper: the tool must be installed in the local state,
stdout must be a pipe, and stdout receives only the credential, without a newline. A bounded private
`credential-access.log` records the time and tool, never the key. Do not run it into logs or a file.

The origin entered at enrolment remains pinned even if response metadata supplies another server. Agent
base URLs must remain on that origin and use `/anthropic` or `/openai/v1`; downloads, browser targets and
redirects are checked too. Configuration rejects quotes, backslashes and controls rather than interpolating
server-controlled executable configuration.

## What is recorded — and what is not

The device's name, operating system, app version, which packages are installed, when it last checked in; and
every AI request that goes through the gateway (who, which tool, model, tokens, cost), as for any key. **Never
files, screens, keystrokes or other programs on the device.** The app shows this text on its *This device*
page and in the sign-in approval. This is the same access-level-only rule as the browser extension (Uganda's
Data Protection and Privacy Act). Do not add device-content capture. Note that the gateway sees what the coding
agents send to the AI; it cannot see what they do to files on the device, and this app deliberately doesn't try.

## Publishing packages

```bash
python3 -m gateway package-publish brand-prompts-1.0.zip --id brand-prompts --version 1.0.0 \
    --name "Brand prompts" --description "Shared prompts" --department Creative --department Finance
```

A package is a zip. It is stored under `data/packages/`, its SHA-256 recorded, and offered to whoever it is
granted to (console: `GET /admin/api/packages`, grants, withdraw — `govern` area). Platform-limited packages
(`--platforms windows,macos`) only reach those systems. The app checks the checksum before unpacking, refuses
any file that would land outside the package's folder (`..`, absolute or drive paths, links), caps size and file
count, and unpacks beside the final place before moving it in, so a failure never leaves half a package. It
only downloads from the server it signed in to, so a manifest can never send the key elsewhere.

## Device credentials: rotation, idle expiry, key-storage report (schema v22)

A device is one `devices` row with a stable `device_id` (the id of its first key). Over its life it holds several
gateway keys (`keys.device_id`); `devices.key_id` points at the current one. Device keys are accepted by the proxy and
`/api/device/*` only, never by the staff app or the console.

**Error codes on `/api/device/*`.** `device_revoked`: the device was disconnected (person, admin, app sign-out, idle) —
remove everything. `device_key_rotated`: *this key* was replaced by a newer one on the same device — reload the key
from the keystore and retry; **never wipe**. `device_unknown`: ask the person. The proxy answers a rotated key with 403
"this device key was renewed".

**`POST /api/device/rotate`** (device key; no body needed). Returns `{key, key_id, device_id, old_key_valid_until,
rotate_after_days}`; the response is `no-store` and the key is shown once. The app rotates every `rotate_after_days`
(30; also in the manifest as `credential.rotate_after_days`): put the new key in the keystore, verify it, call any
device endpoint (e.g. a check-in) with it, then delete the old item. The old key works until the new key's first call at a
device endpoint (use through the proxy does not count) or 10 minutes after the rotate call, whichever is first. If the response
is lost, the old key may call rotate again while that grace lasts and the new key was never used: the unused key is revoked
(`device_key_rotated`) and a fresh one issued; the grace is never extended. Errors: `429 slow_down` (3 a
device per hour), `409 rotation_pending` (already being replaced and the new key has been used). If the grace ends
without the new key reaching the app, the app only has a rotated key (see below).

**Lost response, after the grace.** Once the 10 minutes are up the old key answers `device_key_rotated` and cannot
rotate again. So the app must write the new key to its store before it calls any endpoint with it. If the app gets
`device_key_rotated` and its store holds no newer key, it shows "Reconnect this device", never wipes, and retries no
faster than the heartbeat interval. The hourly idle job ends the orphaned device (refused retries do not count as
activity), and the person reconnects with a new code.

**What retirement cuts.** The 10-minute retirement of an old key does not cut requests already in flight on it; it is
routine rotation. If a key is believed compromised, revoke the device (person, administrator or app sign-out): that ends
every key of the device and cuts everything in flight.

**Idle expiry.** A device with no activity for `device_idle_days` (console setting, 7–365, default 60) is revoked by the hourly
job, audited as `system`. Activity is the newest of the app's last check-in, enrolment and any of its keys being used
at the proxy, so a device in daily use through Claude Code is never idle. An attempt refused because the key was already
revoked is not activity.

**Key-storage report.** Heartbeat bodies may carry `key_storage` (`keychain` or `file`) and `key_backend`
(`credential-manager`, `keychain`, `secret-service`; optional). Anything else is stored as `unknown` / empty. The console shows it
as "reported by the app", flags `file`, and shows older apps as "Not reported (older app)". It is a report, never evidence, and
never an input to an access decision. Moving to `file` is audited once.

## Personal browser contract v1 (server side only; nothing in the app uses it yet)

`GET /api/device/manifest?browser_contract=1` adds one block to the manifest. It is **inert**: the server only
describes what the app may prepare; no client, browser launch or UI exists for it.

```json
"browser": {"contract": 1, "person_id": "7", "device_id": "a1b2c3d4e5f6", "profiles": [{"kind": "personal"}]}
```

- **Negotiation is strict.** Exactly one `browser_contract` parameter whose value is exactly `1`. Missing, `2`,
  `01`, `true`, empty or repeated: no `browser` key, and the manifest is byte-for-byte what older apps get.
- **Reading the query.** Percent-escapes are decoded first and the value must then be exactly `1`, so `%31` negotiates but `+`, a space, `%00`, a repeated name (however it is spelled) or a full-width digit does not; `personal` means bound to the person, so a company-owned device gets the same block and still reports `owner_kind: company`.
- **Identity is origin + `person_id` + `device_id`.** `person_id` is `str(people.id)` (`^[1-9][0-9]*$`); person ids
  can be reused by a different database, so the server origin is part of the identity. `device_id` is the stored
  `devices.device_id` (`^[A-Za-z0-9_-]{1,64}$`) and stays the same when the key is rotated. Both come from the
  authenticated key only; anything the request says about them is ignored.
- **No secrets or personal data.** No email, name, key, hint or token. No provider account, registry entry or seat
  inference; the only kind is `personal`.
- **Auth is not changed.** The block is built only after the existing checks pass (revoked or rotated key, paused
  person, ended access, global pause, not enrolled), so every refusal code carries no block. If the account rule
  does not allow the person's email, `profiles` is `[]`; today the existing key check already answers
  `401 device_unknown` for such a person, so the empty list is a second line of defence, not a new refusal.
- **What the app must do with it (lifecycle, for the separate client work):**

| Server says | The app may |
|---|---|
| block with a profile | prepare that personal profile |
| `profiles: []` | retire this owner's browser data |
| no block | do nothing |
| `device_revoked`, `device_unknown` | retire all |
| `device_key_rotated` | never retire; load the newer key |
| `paused` (everyone) or `person_paused` | keep what is on disk; do not prepare or launch |
| `access_ended` | retire all |
| paused and ended together | the server answers `person_paused`: keep what is on disk |

Client integration needs its own review before it is built.

## Disconnecting

If the server says a device was disconnected (`401 device_revoked`), the app removes everything it installed
and the key. `swangz logout` (or the button) tells the server first, so the key stops working everywhere, then
does the same. If the server can't be reached the local removal still happens and the app says to have an admin
disconnect the key.

`device_unknown` keeps local data and asks the person to retry or reconnect. Only explicit
`device_revoked` triggers automatic removal. Failed native deletion keeps a local cleanup marker with the
server and key ID so **Retry local removal**, `swangz logout`, or `swangz cleanup` can finish later. The app
does not claim successful sign-out when cleanup fails. `cleanup` makes no server call.

The device screen and terminal status expose `key_storage: keychain|file`; each heartbeat reports that mode.
Server ingestion, idle expiry and rotation belong to the later G3b change and are not implemented here.

## Key rotation in the app (server contract: schema v22, `POST /api/device/rotate`)

At the end of every sync (start-up and each idle check-in) the app rotates the device key when it is older than the
manifest's `credential.rotate_after_days` (30 if absent). Never while a coding agent started by the app is running: a
run holds the key in its environment, so `swangz run` leaves a marker in `sessions/` (checked against live process
ids) and rotation waits for the next check-in. Steps: call rotate; write the new key to the store and read it back
(native item, or a protected `device.key.next` if the keychain refuses) **before** any use; make one check-in with it;
only then make it current and delete the old item. A failed confirm leaves the old key in place and the new one staged,
and the next check-in confirms it. `device.json` records only identities (`key_id`, `key_issued`, `next_key_id`), never a key.

`device_key_rotated` never removes anything. The app reloads the key from the store (a staged key, or a newer one
written by another window) and tries once more. With nothing newer it keeps everything, shows **Reconnect this device**
(`swangz sync` exits 4), and tries the Hub again no faster than the 15-minute check-in interval; a newer key arriving
clears the wait. Only `device_revoked` removes Swangz from the device, including a staged key. Heartbeats carry
`key_storage` and, when the key is in a native store, `key_backend`.

**One rotation at a time on a device.** The window and `swangz sync` are separate processes, and a second rotation
during the 10-minute grace is reissued by the Hub, which revokes the first new key. So a rotation (finish a staged
key, or rotate, write the new key and confirm it) is done under a lock file, `rotate.lock` in the data folder,
created exclusively and private to the person. A process that finds it held skips rotation until its next check-in.
A lock whose process has ended, or that is older than three minutes, is taken over; it is removed only if it is still
the one that process wrote, and signing out deletes it. Taking over a stale lock is two steps (read, then remove), so
two processes taking over the same stale lock at the same instant could in theory both rotate. That is rare, needs a
crashed holder, and ends in **Reconnect this device** at worst; nothing is removed.

**What a run in progress sees.** Each `sessions/` marker records the process id and when the run started. A marker
older than seven days is ignored and removed even if its process id is live, because the number has been reused by
something else; an older marker without a start time is aged by its file. When the new key is confirmed, requests
still using the old key are cut at once, not after the 10 minutes: grace ends at the new key's first use. Managed
Claude Code and Codex shells opened before the rotation therefore get "key renewed" (`device_key_rotated`) until they
fetch the key again or a new shell is started; the app does not wait for or interrupt them.

## The app

`swangz` opens the window: a dock down the left (Home, Apps, Packages, This device), sign-in, sync every 15
minutes while open, "start when I sign in" (a LaunchAgent on macOS, `~/.config/autostart` on Linux, the `Run`
key on Windows). From a terminal: `swangz login|status|sync|packages|apps|open TOOL|run claude|codex|autostart on|off|logout`.

Build a standalone program for the computer you are on (it carries its own Python):

```bash
pip install pyinstaller && python3 packaging/build.py
```

See `packaging/README.md` for installers and signing.

## Inert browser-profile preparation (tests only)

`swangz_client/browser_profiles.py` prepares empty app-owned directories beneath an explicitly supplied
`<data>/browser-profiles/`. It has no production callers, browser launch, GUI/CLI integration, extension
installation, provider login, policy installation or session data. Forge's ownership/manifest contract
and a separate G2 security approval are required before real use. This is not a managed browser rollout.

Owners use normalized Hub origin, stable person/device identifiers, OS user and an optional seat ID plus
generation. No email, name, token or key is stored. Random folder IDs and versioned markers support exact
owner reuse; duplicates and changed seat generations fail closed. A persistent `.lock` file holds an
OS-managed nonblocking lock: POSIX `flock`, or Windows `msvcrt.locking` over one byte at offset zero.
The file is never written, truncated or removed, and old JSON contents are ignored and preserved.
The noninheritable descriptor is validated for type, permissions, ownership, link count and inode.
The OS releases the lock on process exit; neither PID probing nor file age permits takeover.
Contention reports `busy`; an unavailable locking mechanism reports `lock_unavailable` without cleanup.
Age applies only to interrupted temporary folders: on POSIX those older than 180 seconds are discarded,
not resumed, and structurally safe retired folders are purged on the next locked operation.

`retire(id, owner)` requires a valid matching marker. `retire_owner(owner)` touches only exact owners.
Explicit `retire_all()` removes structurally safe profile folders even if their markers are corrupt or
missing; unsafe and unknown entries remain and are reported in `skipped`, with `complete=False`.
There are no real sign-out/revocation hooks. POSIX purge never follows links into their targets.

POSIX directories are 0700 and markers 0600, owned by the current uid. The supplied data directory must
already exist, be owned by that uid and not be writable by group/others; it is never chmodded. Ancestors
above it are outside the module's checks. Windows rejects reparse points from data downward:
**ACL not verified by the app.** Native Windows behavior: **Not run: needs Actions**.
Windows preparation and locking have mocked coverage only. Retirement and purge refuse with
`unsupported_platform` before renaming or deleting; batch retirement reports candidates as skipped
and incomplete. Temporary/retired folders are retained on Windows, including during preparation.
Windows deletion requires a separately reviewed native handle-based design, Actions evidence and a
new security ruling. The app makes no native safety claim. Advisory locks assume the same OS-user
trust boundary and supported local filesystems; network filesystem locking is unsupported.

Personal-device profiles are advisory (D-015b). A shared OS login is not isolation (D-014), and local
administrators remain outside this boundary. Company policy enforcement is separate (D-015a).
Existing personal browsing, files, histories, agent environments and automations remain untouched.

Port-free checks: `python3 -m unittest tests.test_browser_profiles -v`. Browser and provider checks
are inapplicable to this inert slice; cross-platform behavior still needs independent QA and review.

## Not built yet (in rough priority)

- **Signed installers** for Windows (`.msi`/`.exe`, Authenticode) and macOS (`.dmg`, Developer ID + notarization),
  and a Linux `.deb`/AppImage, built by CI from tags. The TEST-key updater below is not enabled in shipped builds.
- **Installing Claude Code and Codex themselves.** The app configures and runs them; when one isn't installed it
  says how (`npm install -g …`). Installing third-party programs should be an allow-listed, pinned, checked step.
- **A sign-in link that lands the person in the web app already signed in**, so "Open" on an app doesn't ask again.
- **Chrome Enterprise force-install** of the access gate for company devices (needs the extension hosted with an
  update manifest). Today the app unpacks it and says how to load it.
- **Phones and tablets as installed apps** (store apps). They use the installable web app now.
- Codex's config format and `-c` overrides follow the repo's existing guidance (`gateway/guides.py`); check them
  against the Codex version you deploy.

## Credential implementation evidence and remaining gates (G3a)

Probe's corrected direct-read consultation on 2 November 2026 returned official-source evidence, not a live
or independent client test. The implementation's contract was cross-checked against the official
[Claude helper reference](https://code.claude.com/docs/en/settings-reference#apikeyhelper) and
[gateway connection guide](https://code.claude.com/docs/en/llm-gateway-connect#rotate-credentials-with-apikeyhelper):
helpers are shell commands emitting a credential, supplied in both API-key and bearer headers. Unix command
arguments use shell escaping; the token itself never forms part of a command. Probe did not establish
path-prefix handling for our `/anthropic` base URL in the actual CLI or a deployed minimum version.
**Managed Claude is therefore gated in code on every OS** (`CLAUDE_PREFIX_VERIFIED = False`). The helper
implementation is covered with synthetic fixtures that explicitly lift that gate for tests; those tests
do not establish CLI support. Lift it only after a pinned deployed Claude CLI makes a request to a fake
gateway and the observed path preserves `/anthropic`. The old scoped integration is retained, with its
prefix behavior still unverified against a real binary. Windows helper quoting is separately gated.
The documented bare-output rule mentions v2.1.227, and expired-JWT refresh mentions v2.1.246; neither proves
the version that introduced helpers, so neither is presented as a deployed support floor.

The official [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents `model_provider`, provider `base_url`, `env_key` and `wire_api="responses"`;
[CLI configuration overrides](https://learn.chatgpt.com/docs/config-file/config-advanced#one-off-overrides-from-the-cli)
document TOML-valued `-c` arguments. A newer command-auth format exists in the reference, but this change
does not enable it because its Windows/deployed-version boundaries remain unverified.

Native Windows/macOS/Linux credential-service, DACL, macOS ACL and vendor executable smoke checks are
**Not run** until actual native/CI evidence is supplied. Mocked adapter tests do not prove OS behavior.
No provider, real credential, deployment, signing or installer check is claimed. Exact targeted test output
and the artifact checked are recorded in `docs/AGENT-PROGRESS.md` on this feature branch.

## Verified updater development channel (G4 / D-003)

This branch is stacked on PR #11 (`865250c`), without PR #13's rotation code. No gateway routes,
schema, packaging/signing workflows or dependencies change. Integration with PR #13 remains necessary.
`release_keys.py` ships **no public keys** and `ENABLED = False`. With either gate closed, checks
return **Updates unavailable** without reading a device credential, creating update folders or making
a request. Tests alone patch in the public TEST key; its private counterpart is publicly committed at
`tests/fixtures/test_release_rsa4096.json`. It is not a production secret and is never loaded by the app.
The gate stays closed until G8 and Arnold's production-key decision. MDM installs must retain the gate.

The future Forge endpoint contract is same-origin, authenticated GETs at
`/api/device/releases/<channel>/release.json`, `release.json.sig`, and `<file>`.
The detached signature is exactly 512 binary bytes. The release response must provide
`X-Swangz-Gateway-Version` as a strict `major.minor.patch`; absent/invalid version means no update.
The gateway side of this contract is described in "Release distribution (gateway)" below.
`client.latest` only triggers a check after sync; it never selects a URL, key, version or artifact.
HTTPS is required outside the loopback-only fake-server route, regardless of `SWANGZ_ALLOW_HTTP`.
Cross-origin redirects are refused before a redirected request can carry a device credential.

Authentication precedes all release JSON parsing: RSA-4096 / exponent 65537 / PKCS#1 v1.5 / SHA-256,
comparing the entire expected EMSA encoding. The signed `key_id` must identify the pinned key that
verified those bytes. Duplicate JSON fields and non-finite numbers are rejected. The manifest requires
`schema: 1`, matching `channel`, strict three-component `version` and `min_server`, Unix integer
`released`/`expires`, and `artifacts: [{platform, arch, file, size, sha256}]`. Release time permits at
most 300 seconds of future skew; expiry must be future and after release. Platform is
`linux|macos|windows`, architecture uses `x86_64|arm64` (other exact machine strings may match);
there must be exactly one matching artifact. Names are plain ASCII filenames without slashes,
backslashes or `..`. Size is positive and at most 150 MiB; SHA-256 is lowercase hexadecimal.

The candidate must be newer than the running version, the durable highest accepted version and any
failed version. Streaming stops at the signed size cap plus one detection byte and writes no overflow
byte. Exact size and SHA-256 are compared before staging in private `updates/<version>/` (0700
directories / 0500 executable on POSIX, protected DACL on Windows). Release metadata is retained.
Windows staging retains the writable attribute under that DACL. Replace/delete operations clear any
read-only attribute left by older builds, including rollback targets and the previous-version backup.
Installation verifies it again, including expiry, floors and staged bytes. Platform signature status
is **not checked**: `native_signature_status()` is a placeholder for codesign/WinVerifyTrust, not a pass.

`swangz update status|check|apply` exposes the development path. Apply is available only to a frozen
portable executable located at the app's own `data/app/Swangz` (`Swangz.exe` on Windows); source
checkouts and arbitrary installed paths are refused. There is no bundled `.app`/installer unpacking
or bootstrap installer here. Single-file swaps use an OS-held process lock, a durable write-ahead
journal, `current → prev`, then staged → current. The exact checked file is renamed, rehashed and
started with `--post-update`. The probe imports client modules, strictly reads app state and reads
the current keychain/file credential without migrating it. It writes a nonce-bound `update-ok` and
exits. The parent waits no more than 60 seconds for acknowledgement and successful probe exit.
Only then does the highest-accepted version advance. Apply exits after the probe; open Swangz again
to use the new version. A desktop process is not restarted automatically on successful apply.

On failure/timeout the candidate process is stopped and the exact previous binary restored; the
failed version cannot be retried until a newer signed release arrives. At normal startup an
interrupted journal without acknowledgement restores the previous binary and relaunches it.
Startup recovery runs only for GUI, status, sync and update commands. The credential helper never
initializes the updater or relaunches the app: its stdout is exclusively the credential pipe, and
helper failures are reported on stderr. Entry-point relaunches preserve normalized process arguments.
There is exactly one `prev`; it remains until the acknowledged new version completes its first sync
without package or heartbeat failures. The accepted-version ledger survives sign-out. Missing or
modified recovery files fail visibly rather than claiming recovery succeeded. Local administrator
or same-user tampering with the app/state is outside this update trust boundary.

Verification: `tests.test_client_updates` uses a loopback fake server and pure-Python TEST-key signing,
including a signed POSIX script fixture for swap/self-test/restart. No OpenSSL, production keys,
provider calls or certificate checks. Python 3.10 syntax parsing and `git diff --check` passed during
implementation; neither is a test result. Targeted Python results await Probe/CI. Native Windows/macOS
rename/locking/DACL, packaged binaries, `.app` handling, platform signatures and actual GUI update
screens are **Not run**. This work is not a production-update or cross-platform packaging claim.

Sentinel follow-up to `9f505cf`: regression cases emulate Windows read-only replace/unlink failures,
cover staging without the read-only attribute, `main(argv=None)` after recovery, and the credential
helper's isolated stdout/stderr behavior. Tests are added for Probe to run; not executed under Codex.

## Release distribution (gateway)

`gateway/releases.py`. The gateway is a distribution point, never a source of trust: it may withhold an
update, it cannot forge one, because it holds no signing key and the device re-verifies every byte. Releases
are made and signed offline and published from the command line only; there is no HTTP or console upload.

**Publish** (`python3 -m gateway ...`, audited as `command line`, correlation `release:<channel>:<version>`):

- `release-publish DIR --channel stable|pilot` — `DIR` holds `release.json` (at most 64 KiB), `release.json.sig`
  (exactly 512 raw bytes) and the listed artifacts. Refused unless the signature verifies
  (`swangz_client.updater.verify`) against `swangz_client/release_keys.KEYS` (nothing pinned: refused); the
  manifest's channel equals `--channel`; the version is strictly higher than every version already stored in
  that channel (a rollback is a new, higher, signed version; a withdrawn version number is not reused); each
  listed artifact exists, passes the client's filename rule, is at most 150 MiB and matches its size and SHA-256;
  and the disk keeps 1 GiB free after the write. Only listed files are copied.
- `release-withdraw --channel C` — deletes the channel's pointer; devices get 404. Files stay on disk.
- `release-pilot add|remove PERSON` — the pilot list (a setting, `release_pilot`; no schema change).

**Storage:** `data/releases/<channel>/<version>/` (folders 0700, files 0600), written to a temp folder then
renamed; versions are never overwritten; `<channel>/current.json` is replaced atomically, so a crash leaves the
previous release live. The current and one previous version are kept. Serving refuses symlinks and hard links.

**Device routes** (the device's own key, `Authorization: Bearer`; browser and console sessions get 401; the
usual `device_auth` refusals apply): `GET /api/device/releases/<stable|pilot>/<file>`.

| File | Answer |
|---|---|
| `release.json` | `200 application/json`, the stored bytes, plus `X-Swangz-Gateway-Version: x.y.z` (this response only) |
| `release.json.sig` | `200 application/octet-stream`, 512 bytes |
| a name listed in the current `release.json` | `200 application/octet-stream`, streamed in 64 KiB blocks |

All carry `Content-Length`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`; no ranges, no
compression, no redirects. Anything else — no release, withdrawn, `pilot` for someone not on the pilot list,
an unlisted or unsafe name, a missing file, a link — is `404` (`{"error": "No release is available."}`).
Each device may download artifacts three times an hour (`429`, code `slow_down`); the manifest and signature
are not limited. Each artifact download writes one audit record (`downloaded a release file`: person, device,
`<channel> <version>`, file, outcome `ok`/`interrupted`/`failed`/`denied`); polling records nothing.

`client.latest` in `/api/device/manifest` and `latest_client` in the heartbeat are the current version of the
device's channel (`pilot` for people on the list, else `stable`), or `CLIENT_LATEST` when nothing is published.
It is a hint only. The gateway refuses to start unless `gateway.__version__` is strict `x.y.z`.

Verification: `tests.test_device_releases` (fake upstream, the fixture TEST key only).
