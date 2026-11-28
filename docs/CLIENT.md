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

Sign-in starts with `https://hub.ictconnect.org` in the address box (`swangz_client/core.py` `DEFAULT_SERVER`; the
browser extension's popup does the same). The person can type another address, `swangz login --server URL` still works,
and `SWANGZ_SERVER` still overrides the window's box. Nothing is sent to the address before they press Sign in. Which
accounts may sign in is the Hub's rule and is unchanged (`swangzavenue.com`). A device that is already connected keeps
the address it was connected with.

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
Sign out, revocation and `swangz cleanup` erase `device.key` and `device.key.next` before they touch the
keychain, so an unreachable one (for example a locked or stopped Secret Service) never leaves a usable key on disk.
If a keychain entry then can't be confirmed removed, the app says so ("The key file on this device was removed, but
its keychain entry could not be confirmed removed. Retry signing out.") and keeps the identity so a retry finishes it.
On Linux, `secret-tool lookup` answers a locked keyring exactly as it answers a missing item, so the app counts an
entry as gone only when `secret-tool search` also finds nothing; a search that lists it or fails keeps the cleanup
pending. Limit: this relies on the Secret Service provider listing locked items to `search` (gnome-keyring does);
a provider that hides them could still report a locked entry as removed.

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

**An older build never replaces a newer one.** The Windows installer refuses it. On a Mac the app is dragged into
Applications, so the app itself refuses: while the device is signed in, `newest-app.json` in the app's data folder
records the newest version that ran, and an older copy exits 5 (with a dialog when opened from Finder) without
touching the sign-in. `swangz logout` still works; sign out and revocation remove the record. A version the updater
rolled back from (`updates/state.json` `failed_version`) does not count (`core.check_newest_app`).
On a Mac `swangz` is not on PATH, so the refusal dialog offers **Sign out** (the same path as `swangz logout`), and
the terminal message prints the full command (`/Applications/Swangz.app/Contents/MacOS/Swangz logout`).

**Version numbers: the first real release is 0.2.0.** Test (RC) builds from CI are numbered `0.1.<PATCH + run
number>` (for example 0.1.400), so a later official 0.1.x could sort below a test build a tester already ran and be
refused. The first non-RC release therefore raises MINOR to **0.2.0**, which sorts above every 0.1.<run> test build;
later releases keep going up from there. The credential helper (`swangz key`) is deliberately not covered by this
floor, so Claude Code and Codex keep working; the server's minimum client version is the control for agent use.

## Personal and company devices

| | Personal device | Company device |
|---|---|---|
| Claude Code / Codex | `swangz run claude` / `swangz run codex` set the gateway and key only in the child environment; personal tool settings are untouched | Managed Claude is gated on every OS pending verification of the deployed CLI's `/anthropic` prefix. Old managed tokens are removed and the app offers existing scoped runs. Unix Codex uses a marked provider block and a login-profile helper. Windows managed Codex is gated: use `swangz run codex`. Managed Codex also requires Python 3.11+ to validate existing TOML safely. |
| Signing out | removes the key and what Swangz installed; browser folders stay (see *Disconnecting*) | also takes our lines back out of those files — only what we wrote and only if still ours — leaving anything the person changed since |

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

**Company build on Windows.** A company computer can have the app installed for all users into `%ProgramFiles%\Swangz`
by an administrator, with the company's pinned values recorded in `HKLM` (`packaging/README.md`, "Company installer").
The install does not make a device a company device: enrolment still decides that. Before uninstalling the company
build, disconnect the device in the console. The uninstaller closes every `Swangz.exe` on the computer and removes the
program, but disconnects nothing itself. Neither signs anyone out of a provider or Google: the Swangz browser folders
that hold those sign-ins stay on the computer. A person deletes their own with **Remove Swangz from this account**
in the app, before the uninstall.

## What is recorded — and what is not

The device's name, operating system, app version, which packages are installed, when it last checked in; and
every AI request that goes through the gateway (who, which tool, model, tokens, cost), as for any key. Since 27 Nov
2026 the check-in also says, for **the person's own assigned AI tools only** and Google Chrome, whether each is
installed here (and its version), from the fixed list in `native_apps.py` (see *Desktop and command-line apps*). It
never lists, opens or reads anything else on the computer. **Never files, screens, keystrokes or other programs on the
device.** The app shows this text on its *This device*
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

## Managed workspace contract 2 (server side: W2, W4, W5; schema v26)

`GET /api/device/manifest?browser_contract=2` returns contract 1's block plus the workspace state and the policy baseline.
Negotiation is exactly as strict as for 1 (one parameter, value exactly `2`, after percent-decoding). Contract 1 answers are unchanged
byte for byte; `apps[].open` links carry `?d=<device_id>` **only** under contract 2.

```json
"browser": {"contract": 2, "person_id": "7", "device_id": "a1b2c3d4e5f6", "profiles": [{"kind": "personal"}],
            "workspace": {"state": "active", "generation": 1},
            "policy": {"sha256": null, "mode": "warn"}}
```

- `workspace.state`: `active` | `suspended` | `retired`, stored per device (`devices.workspace_state`), separate from the device key.
  `generation` starts at 1.
- `policy.sha256`: the baseline hash the admin pinned (Settings `managed_policy_sha256`, 64 hex or `null`); `policy.mode`: `warn`
  (default) or `enforce` (Settings `managed_policy_mode`). Both are "trust" area settings.
- **Heartbeat.** `POST /api/device/heartbeat` with `{"browser_contract": 2, "policy": {"ok": true, "sha256": "<64 hex>"}, ...}`.
  The answer then also carries `workspace` and `policy` (the same two objects). Without an integer `browser_contract` of 2 the answer is
  unchanged. The whole answer stays well under 2 KB; **one heartbeat a minute at most is a client rule**, the server does not
  throttle it. A malformed `policy` report is ignored; a bad hash is dropped.
- **Where the app's `policy` report comes from (W5, `swangz_client/machine_policy.py`).** Read-only and **machine scope only**:
  Linux every file in `/etc/opt/chrome/policies/managed` (Debian Chromium `/etc/chromium/policies/managed`, Ubuntu
  `chromium-browser` `/etc/chromium-browser/policies/managed`; Chrome applies every file there, so any file that is not
  valid `*.json` policy, hidden files included, fails the check), macOS
  `/Library/Managed Preferences/com.google.Chrome.plist` (Chromium `org.chromium.Chromium`), Windows
  `HKLM\Software\Policies\Google\Chrome` (Chromium `...\Chromium`) in the 64-bit registry view (DWORD 0/1 read as
  true/false, list subkeys in number order). Per-user copies (macOS `/Library/Managed Preferences/<user>/`, HKCU), Linux's
  `recommended` folder and Windows' `Recommended` key are never read. The family checked is the one the workspace launcher
  starts (`machine_policy.report()` asks `find_browser` and looks its exact path up in `machine_policy.BROWSERS`); no
  browser found, or a path with no known policy folder, is `ok: false`.
  Fails closed (`ok: false`): an unreadable, invalid or oversized (> 1 MB) file, a symlink in place of a policy file or of the
  Linux folder, a key given twice in one JSON file, or two sources that disagree. `ok` is true only if every `REQUIRED` setting of the policy pack holds, `URLBlocklist` carries `*`, `file://*`, `chrome://*`
  and `view-source:*`, `URLAllowlist` is not open (`*`, `*://*`, `http://*`, `https://*`), `ExtensionInstallBlocklist` is `["*"]`,
  the allow and force lists are filled in, no two policy sources disagree, and none of the policies that would quietly undo
  the pack is set at all (`machine_policy.FORBIDDEN`: `ExtensionSettings`, the two `...MultipleSourceMergeList` policies,
  `CloudPolicyOverridesPlatformPolicy`; they are reported as `forbidden:<key>` and never change the hash). Missing or unreadable policy is `ok: false`; the check
  never raises. `sha256` is the **baseline hash**: canonical JSON (sorted, compact) of the policies the pack sets, the same on all
  three systems; `deploy/chrome-policy/prepare.py` prints it as "Baseline SHA-256" and that is the value to pin. The report is sent
  by **company devices only** (D-024): a company enrolment sets `Client.policy_check = machine_policy.report`; a personal one sends
  no `policy` field and keeps the extension gate, and the Hub never refuses it for policy. The app checks at every heartbeat and
  before every Open, never reusing a result older than 60 s. Before a window starts it compares its own hash with the baseline the
  Hub sent (`policy.sha256`) and requires `ok`: in `enforce` a mismatch is refused on the device (`workspace_policy`, no browser is
  started, no open is recorded); in `warn` the window opens and the result goes in the next heartbeat. The Hub's own refusal
  (`/device/open` 409 `workspace_policy`, `/go/` 403) stays in place. This is tamper-evident, not tamper-proof: a local
  administrator who also patches the app defeats it.
- **What the report cannot prove (W5 limits).** It reads where the OS keeps policy, not `chrome://policy`, so it says the policy is
  *installed*, not that the running browser applied it. On **Windows computers that are not joined to a domain (Active Directory or
  Microsoft Entra ID) or enrolled in Chrome Browser Cloud Management**, Chrome ignores some policies set in the registry (for example
  force-installing an extension that is not from the Chrome Web Store), so the report can say `ok: true` for settings Chrome does not
  apply: company Windows devices must be joined or enrolled, and an admin checks `chrome://policy` once per device. A person with
  administrator rights on the computer can change both the policy and the app; the report is a tamper signal, not a lock. Duplicate
  keys are detected in JSON files only (Python's plist reader keeps the last one). The server only ever uses the report to refuse.
- **What the app does** (for Prism, W3/W6/W7): `suspended` closes the workspace at the next heartbeat and keeps the profile folder
  (reactivating keeps the sign-in); `retired`, or a `generation` higher than the one on disk, means close it and delete the profile
  folder. The server says `retired` only after an administrator's explicit `retire`; a person the account rule no longer
  allows, or an unreadable stored state, is told `suspended` (closed, nothing deleted). A suspended or retired workspace does not revoke the device key, the device, any gateway API key or any automation (W7).
- **Admin.** `POST /admin/api/devices/<device_id>/workspace` with `{"action": "suspend" | "reactivate" | "retire" | "reset"}`
  (`suspend`: govern or emergency, so the security role can stop a workspace; `reactivate`, `retire` and `reset`: govern only,
  because `retire` purges the folder; a refusal is `403` and audited as denied). Answer: `{"ok": true, "workspace": {"state", "generation"}, "changed": bool}`. `reactivate` from
  `retired` starts a new generation; `reset` bumps the generation (a seat changed hands; no automatic trigger exists yet);
  `suspend`/`reset` on a retired workspace is `409 workspace_retired`; unknown device `404`; repeating an action changes and audits
  nothing. Every change is audited with before/after and `correlation=device:<id>`. The console devices list
  (`GET /admin/api/devices`) now carries `workspace_state`, `workspace_generation`, `policy_ok`, `policy_reported`, `policy_source`.
- **Open is refused, in plain words.** `/go/<tool>?d=<device_id>` returns 403 and logs a `refused` launch (rule `workspace_suspended`,
  `workspace_retired` or `workspace_policy`) when that device (it must be the signed-in person's own) is suspended or retired, or, in
  `enforce` mode, has no fresh (10 minutes) passing policy report for the pinned baseline. **Honest limit:** `d` is an advisory claim
  the app adds; a request with no `d` is not refused by this check. Real enforcement is the app closing the workspace plus the
  machine policy on the managed browser. The policy report is `reported by the app`, a tamper signal and never proof, and it only
  ever takes access away.
- No provider password, cookie, token or session is read, stored or sent by any of this.

### Opening a provider in the workspace window (W3, `POST /api/device/open`)

The workspace browser never opens `/go/<tool>` (it has no Hub session). The app asks for the provider address with its device key:

```
POST /api/device/open
Authorization: Bearer <device key>      X-Swangz-App: 1      Content-Type: application/json
{"tool": "chatgpt"}

200 {"ok": true, "tool": {"id": "chatgpt", "name": "ChatGPT"}, "url": "https://chatgpt.com/",
     "allowed_hosts": ["chat.openai.com", "chatgpt.com", "sora.com"], "workspace": {"state": "active", "generation": 1}}
```

- Checks, in order: the device key (`401 device_unknown | device_revoked | device_key_rotated`, `403 person_paused | access_ended |
  paused | not_enrolled`), the tool (`404 unknown_tool`), then exactly `/go/`'s checks (`staff.launch_checks`: `403 locked |
  not_assigned | past_due | suspended | weekly_report_required` with `details.report`, or `policy` for a company rule), then this
  device's workspace (`403 workspace_suspended | workspace_retired | workspace_policy`), then the address (`409 no_address |
  host_not_allowed | unsafe_address | shared_account`). Errors are `{"error": "<plain words>", "code", "details"}`.
- Every answer after the key check is recorded as a launch, `opened` or `refused` with its rule, exactly as `/go/` records it.
- The address is https only, port 443, no user name or password, a DNS name (no IP, not `localhost`, not the Hub), no query or fragment
  field named like a credential (`token`, `access_token`, `api_key`, `password`, ...), at most 2048 characters, and on one of the tool's
  `hosts` (exact or a subdomain). A tool with no hosts is refused (`host_not_allowed`): the admin sets them.
- **The app must still** check `url` against `allowed_hosts` itself before starting the browser, pass `url` and nothing else on the
  command line (never the key), and treat any non-200 as "do not open". Modern manifests route authorized shared-login tools
  through the same dedicated Chrome profile as any other site (D-028). If an older manifest or gateway refuses the tool, the
  client offers sync or admin guidance without suggesting another browser.
- Not `GET`: the call records a launch. The answer is `Cache-Control: no-store` and carries no key, token or Hub session.

#### When Open is refused in the app (#333)

A refused Open opens nothing, in any browser. `swangz_client/repair.py` turns the refusal (made on the device or answered by
the Hub) into a title, the plain reason, numbered next steps and at most these buttons: **Try again** (asks the Hub again,
then retries the same tool or Google sign-in), **Get Google Chrome** (guided official setup on Windows, Google's download
page for macOS, only when no usable Chrome is found) and
**Open weekly reports** (the Hub's page). No button carries a tool or provider address. The window shows this as a panel on
Home and Apps until it is dismissed, the page changes or the tool opens; `swangz open TOOL` prints the same steps and exits
1. A disconnected or signed-out device goes back to sign-in instead. Command-line coding agents are separate and unchanged.

Under **Sign-ins** or **Workspace**, use **Choose another Google account** to open Google's fixed account chooser without
prefilling the Hub email. Staff must authenticate on Google's page and use only an approved account. This is Google website
sign-in, not Chrome Sync, and is independent of the Workstation's Hub login. It neither changes whose tools the Hub assigns nor
signs in to provider websites for staff. Google keeps its own session in the same local profile used for approved tool launches;
the app neither detects the Google account nor reads or copies cookies. Google's reauthentication, MFA and company policy still
apply. On company macOS, an administrator installs Google's official enterprise package before Workstation verifies Chrome.

This covers Open in the app only. Open in the Hub's web pages (`/go/<tool>`, including shared company accounts) still opens in
the browser the person is using.

## Disconnecting

If the server says a device was disconnected (`401 device_revoked`), the app removes everything it installed
and the key. `swangz logout` (or the button) tells the server first, so the key stops working everywhere, then
does the same. If the server can't be reached the local removal still happens and the app says to have an admin
disconnect the key.

Disconnecting a device (the person's button, an admin, or `swangz logout`) ends **every** key of that device, including both
keys during a rotation grace, and cuts its requests in flight. It never touches web or extension sessions, and signing out of
the web app ends only that one session. A device key is never a web session and a web session or extension token is never a
device key: each is refused on the other's endpoints. Each action is one audit entry with `before` (key ids) / `after`
(counts), correlated `device:<id>` or `person:<id>`, and no token.

Sessions have a kind (schema v23, `staff_sessions.kind`): `web` rows are accepted only as the `sgw_staff` cookie, `extension`
rows only as a bearer token, and an extension session reaches only `/api/extension/*`, the gate (`/api/gate/*`), sign-out and `POST /api/tools/<id>/request` (the blocked page's "Request access");
anywhere else it answers `403 {"code": "session_kind"}`. A row that existed before v23 became an `extension` row: nothing was
deleted, the old cookies simply stop working, and the old bearer tokens keep working on the gate. `last_seen` is recorded at most
once a minute.

A session is checked against the person on every request. A person whose email is no longer an approved account gets `401` from
every signed-in endpoint. A suspended person's, or one whose `access_until` has passed, **web** session keeps a read-only paused view
(`paused_ok` routes, which refuse to register for anything but a GET and sign-out): `GET /api/me` trimmed to `{paused_view, name,
status, reason, support_contact}`, `GET /api/hub/reports` and `/api/hub/reports/<id>` (their own), `GET /api/hub/notifications`
and `POST /api/logout`. Every other signed-in route, `/go/<tool>` and `/device` answer `403 {"code": "person_paused"}`; an
extension session of such a person gets `401`; the proxy, `/device` and device keys refuse them as before. `POST /api/login` for such a person starts a web session
(`{"ok": true, "paused": true}`); `POST /api/extension/login` and invites still answer `403 person_paused`, and a wrong password is
still the same `401` whatever the status. Suspending someone through the console still deletes their sessions. Google sign-in
applies the same rule, and for everyone but the two approved owner addresses it requires the ID token's own `hd` claim to equal
the company domain (`GATEWAY_COMPANY_DOMAIN`, default `swangzavenue.com`) as well as the email suffix. Any domain other than the default must be confirmed by name (`GATEWAY_COMPANY_DOMAIN_CONFIRM=<the same domain>`), or `preflight` fails: accounts on another domain are not moved and lose sign-in. Only `preflight` checks the confirmation; the gateway does not check it at start-up and accepts any valid `GATEWAY_COMPANY_DOMAIN`, so run `preflight` before starting a deployment with a new domain.

`device_unknown` keeps local data and asks the person to retry or reconnect. Only explicit
`device_revoked` triggers automatic removal. Failed native deletion keeps a local cleanup marker with the
server and key ID so **Retry local removal**, `swangz logout`, or `swangz cleanup` can finish later. The app
does not claim successful sign-out when cleanup fails.

Signing out of the app, being disconnected and signing out of the computer all **keep** the browser folders that
hold a person's provider and Google sign-ins. The app says where they are.

## Removing Swangz from an account (`cleanup`)

**Remove Swangz from this account** on *This device*, or `swangz cleanup` (`Swangz.exe cleanup`), takes Swangz off
one person's account. It:

1. refuses where it must not run. Nothing changes, the exit code is 1 and the message carries the reason:
   - `elevated_refused`: rights raised by Windows' prompt ("Run as administrator"), a Windows service account, root
     on macOS and Linux, or rights that can't be read. An account that always has full rights because that prompt is
     off, the built-in Administrator included, is not refused for it;
   - `wrong_account`: the account running it does not own the app's data folder, or the owner can't be read
     (D-026, "Amendment 25 Nov (cleanup tokens)"). Before this rule the app tries the one owner change below;
2. closes the workspace window;
3. signs out while the key still exists, which removes the key and what Swangz installed. If the server can't be
   reached it carries on and says **Have this device disconnected from the Hub: ask your Swangz administrator to do
   it in the console.**;
4. deletes every folder under `browser-profiles/` in the app's data folder, whoever it was made for. A link or
   junction is removed itself and what it points at is never touched. A folder that a running browser holds is left
   whole and named (`in_use`): `cleanup` closes only a window this running app started, so close the window and run
   it again;
5. turns off start at sign-in.

A step that fails does not stop the later ones. Everything left is named and the exit code is then 1;
`--report FILE` writes the folders that could not be deleted, one per line (UTF-8 with a byte order mark). Where the
server could not be told, and where the run was refused, the first line is the one asking for the device to be
disconnected. The file is empty when nothing is left to do. Running it again is safe. The app itself stays installed.

**Windows: the owner of the app's data folder.** Windows can make `BUILTIN\Administrators` the owner of a folder an
administrator's process creates (the built-in Administrator), and `cleanup` accepts only the person as owner. So the
app makes the person the owner, at every start, after signing in and at the start of `cleanup`, only when all of
these hold: the rights are not raised by Windows' prompt (Default or Limited token) and are not a service account's;
the folder is `Swangz` under the local app data folder Windows itself names for the person (no environment variable
is read); opened without following a link, it is a real folder; and its owner is exactly `BUILTIN\Administrators`
(`S-1-5-32-544`). Only the owner is set, on that open folder; its permissions are not changed and no special
privilege is used. Each attempt is noted in `ownership.log` in the folder (owner before, owner after, `claimed` or
`failed`). Where it fails, or any condition does not hold, `cleanup` refuses with `wrong_account`.

- **Windows, per-person install:** uninstalling closes the person's running copy and runs `cleanup` as that person
  before the program files go. If it fails, the uninstaller shows what was not deleted (not in a silent uninstall,
  where it is only in the log) and carries on. If everything was removed but the server could not be told, it shows
  the line asking for the device to be disconnected (the same way). An uninstaller started as administrator, or by an account that does not
  own the data folder, gets the refusal: the program is removed and nothing in the account is cleaned. The message
  names the two ways to finish: install again and choose **Remove Swangz from this account** without administrator
  rights, or have the device disconnected in the console. The uninstaller never retries with more rights.
- **Windows, company build:** its elevated installer and uninstaller never run `cleanup`. Each person chooses
  **Remove Swangz from this account** first.
- **macOS:** choose **Remove Swangz from this account** (or run
  `/Applications/Swangz.app/Contents/MacOS/Swangz cleanup`, which signs out first), then drag Swangz to the Bin.
  Dragging it to the Bin alone leaves the key and the browser folders on the Mac.

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

`swangz` opens the window, an **AI workstation** (owner directive, 27 Nov 2026: one installed app where every
authorised employee works at the same time, with their own seat or account; no turns). A sidebar down the left:

- **Home**: a greeting with the person's whole name as the Hub stores it (Ugandan names are often surname-first, so the
  app never picks a "first name"); Google Chrome, sync and device status; quick launch of pinned and recent tools
  (pins live in `workstation.json` in the data folder); what is open (the Swangz Chrome window, and what was opened from
  Swangz since it started; Swangz does not look at other running programs).
- **Apps**: every tool assigned to the person (the manifest's `tools`, falling back to `apps` and agent packages on an
  older Hub) as a card with **Web / Desktop / CLI** badges and *Open in Swangz Chrome*, *Open desktop app*, *Install*,
  *Repair*, *Pin*. A manifest app's `account_note` (single-login company accounts) shows as a quiet line; it never
  blocks anything.
- **Workspace**: the person's Swangz Chrome profile. Chrome found and publisher-checked (`Client.chrome_status`, off
  the window's thread), or the guided step: *Install Google Chrome* (Windows company build: the elevated Google-only
  install of D-026 B5, after a yes on the window's own dialog; everywhere else Google's page `INSTALL_PAGE`), then a
  re-check when the window gets focus again or on *Re-check*. The profile folder, whether the window is open, and
  *Open Swangz AI Hub* (the Hub's devices page through `shell.open_hub`; the Hub's tool pages are deliberately not
  offered, because they would open tools outside Swangz Chrome).
- **Automations**: coding agents (Claude Code, Codex through `swangz run`) and published packages.
- **Usage**: what was opened from Swangz on this computer (`workspace-open.log` and `apps-open.log`, both
  `<time> <open|desktop> <tool id>`, 100 lines each, local only) and the weekly report button.
- **Settings**: start at login, sync, device facts, company browser settings (company computers only), what Swangz
  records, Hub account pages, sign out, *Remove Swangz from this account*.

**Several tools at once.** Each Open starts Chrome on the same per-person folder with the same fixed switches; a
running Chrome takes the address into its window and the new process exits. The launcher remembers only the window it
started and never closes it for a later Open (`tests/test_native_apps.py` `SeveralToolsAtOnceTests`). Chrome
`--app=<url>` windows were considered and **not** adopted in this change: D-026 D1 fixes the argument list as
`[chrome, --user-data-dir, fixed switches, url]`, pinned by `test_workspace_launcher`, `test_open_repair` and
`test_w6_matrix`; changing it needs a D-026 amendment first.

Sync every 15 minutes while open, "start when I sign in" (a LaunchAgent on macOS, `~/.config/autostart` on Linux, the
`Run` key on Windows; signing out turns it off). From a terminal: `swangz login|status|sync|packages|apps|open TOOL|run claude|codex|autostart on|off|logout|cleanup [--report FILE]`
(`swangz apps` lists every assigned tool with its badges and whether it is installed here).

## Desktop and command-line apps (`swangz_client/native_apps.py`)

A **fixed, code-reviewed table** keyed by the Hub's tool id. The Hub only names tools; it never sends a command, path,
package id or address for the app to run, so a compromised Hub cannot make a device run anything. Every id, path and
page has its source URL and the date it was read (27 Nov 2026) in the table; anything not verified is left out, and
the entry's note says so. Linux is source-only and frozen: every tool is web there.

| Tool | Windows | macOS |
|---|---|---|
| chatgpt | winget `OpenAI.ChatGPT` (MSIX family `OpenAI.Codex_2p2nqsd0c76g0`: the app now includes Codex) | page; `ChatGPT.app`, `com.openai.codex` |
| claude | winget `Anthropic.Claude` (MSIX family `Claude_pzs8sxrjxfjjc`) | page; `Claude.app`, `com.anthropic.claudefordesktop` |
| gemini | winget `Google.GeminiDesktop` | page; `Gemini.app`, `com.google.GeminiMacOS` (cask `google-gemini`, not `gemini`) |
| perplexity | Store `9P9XG917PWCJ` (no winget-community id) | found only (`ai.perplexity.macv3`); download page unverified |
| copilot | Store `9NHT9RB2F4HD` (family `Microsoft.Copilot_8wekyb3d8bbwe`) | page only; app name/bundle unpublished, not checkable |
| cursor / notion-ai / figma-ai / deepl / grammarly / capcut / descript / loom-ai | winget `Anysphere.Cursor`, `Notion.Notion`, `Figma.Figma`, `DeepL.DeepL`, `Grammarly.Grammarly`, `ByteDance.CapCut`, `Descript.Descript`, `Loom.Loom` | page; bundle ids from Homebrew casks (DeepL and Grammarly by app name only) |
| canva | winget `Canva.Canva`, `%LocalAppData%\Programs\Canva\Canva.exe` (from the manifest) | page; `com.canva.CanvaDesktop` |
| antigravity | winget `Google.Antigravity` (Google also ships `Google.AntigravityIDE`: confirm which the catalogue means) | page; `com.google.antigravity` |
| claude-code | winget `Anthropic.ClaudeCode` in a visible window | Anthropic's `install.sh` in Terminal |
| codex | winget `OpenAI.Codex` in a visible window | OpenAI's `chatgpt.com/codex/install.sh` in Terminal |
| adobe-premiere, photoshop | winget `Adobe.CreativeCloud` (machine-wide, so Windows asks), then the app from Creative Cloud; not checkable | Creative Cloud page; not checkable |
| davinci-resolve, topaz-video-ai, airtable-ai (Windows) | vendor page only, not checkable | page (Airtable checkable: `com.FormaGrid.Airtable`) |
| grok, google-flow, adobe-firefly, elevenlabs, higgsfield-ai, everything else | web | web |

- **Finding an app**: fixed install paths only (Program Files from HKLM, never the environment; `%LocalAppData%`;
  /Applications and ~/Applications, where the app's `Info.plist` must name the table's bundle id); a Store/MSIX app by its
  `%LocalAppData%\Packages\<family>` folder; on Windows `winget export` (a read: what winget knows is installed, with
  versions), run at most every five minutes from the check-in thread or *Re-check*, written to a private file and
  deleted; a CLI's PATH entry only as a labelled fallback. A tool with no honest way to look is **unknown**: the window
  says "Swangz can't check", and the check-in leaves it out rather than calling it missing.
- **Installing**: only after the person presses Install and says yes to a dialog naming the app, publisher and source.
  Windows: `winget install --id <exact id> --exact --source <winget|msstore> --accept-source-agreements
  --accept-package-agreements` (hidden, 30-minute timeout, no Swangz or provider keys in its environment); a CLI the
  same, in a terminal window; no winget: the vendor's page. macOS: the vendor's page in the default browser (the person
  runs the installer) or, for a CLI, the vendor's install script in Terminal. Swangz never elevates; an installer that
  needs administrator rights asks Windows itself.
- **Repair**: re-detect, then `winget upgrade` (installed) or `winget install` (missing) with consent; elsewhere the
  vendor's page. *Update check* (`Manager.check_update`): a dry `winget list --id <id> --exact --upgrade-available`,
  otherwise what the table says ("updates itself" from the Homebrew cask's `auto_updates`).
- **Opening**: Windows `os.startfile` on the detected program file; a Store app through `explorer.exe
  shell:AppsFolder\<AUMID>` only when the table has a published AUMID (none do yet, so those say "Open it from the Start
  menu"); macOS `/usr/bin/open -a <detected app>`. Claude Code and Codex open through `swangz run` in a terminal, still
  pointed at the gateway. Each open adds `<time> desktop <tool>` to `apps-open.log`.
- **Check-in** (`core._heartbeat_body`): `"apps": [{"id": "chrome"|<tool id>, "state":
  "installed"|"missing"|"installing"|"failed"|"web", "version": "<= 40 chars or ''"}]`, Chrome first, at most 60.
  An older Hub ignores the key.
- **Static allow-list**: `tests/test_no_fallback.py` lists the three new places that can start something
  (`_startfile`, `Manager.launch`, `_open_page`) and the two terminal callers; `tests/test_native_apps.py` pins their
  exact arguments. Vendor download pages extend D-026 D2's list of what may open in the default browser: they are
  installer pages from the fixed table, never a tool address or anything from the manifest. **Needs Sentinel's review.**

**Verified where.** Unit-tested on Linux with fake runners and filesystems (`python3 -m unittest tests.test_native_apps`).
Not yet run on a real Windows or Mac: winget's behaviour and exit codes, the Store family folders, the version reader,
`explorer.exe`/`open -a`, the terminal windows and the Chrome install step all need a check on each system.

Build a standalone program for the computer you are on (it carries its own Python):

```bash
pip install pyinstaller && python3 packaging/build.py
```

The manual `build-app.yml` Actions workflow builds Linux, Windows and macOS standalone apps,
smokes each packaged executable against an isolated local gateway, and uploads archives named
**UNSIGNED-TEST** with SHA-256 sidecars and per-OS smoke reports (seven-day retention). The smoke
covers frozen imports and a hidden sign-in window, device-code sign-in, sync, credential read and
sign-out. Windows' windowed executable reports its offline check through
`Swangz.exe --self-check REPORT.json`; it has no console output. Updates remain disabled with no
production keys. These artifacts have no trusted publisher signature; installers, code signing
and notarization need separate decisions. See `packaging/README.md` for the build procedure,
verification limits and pending tooling decisions.

## Inert browser-profile preparation (tests only)

`swangz_client/browser_profiles.py` prepares empty app-owned directories beneath an explicitly supplied
`<data>/browser-profiles/`. The workspace launcher and `cleanup` use it. It does no browser launch, extension
installation, provider login or policy installation of its own. Forge's ownership/manifest contract
and a separate G2 security approval are required before real use. This is not a managed browser rollout.

Owners use normalized Hub origin, stable person/device identifiers, OS user and an optional seat ID plus
generation. No email, name, token or key is stored. Random folder IDs and versioned markers support exact
owner reuse; duplicates and changed seat generations fail closed. A persistent `.lock` file holds an
OS-managed nonblocking lock: POSIX `flock`, or Windows `msvcrt.locking` over one byte at offset zero.
The file is never written, truncated or removed, and old JSON contents are ignored and preserved.
The noninheritable descriptor is validated for type, permissions, ownership, link count and inode.
The OS releases the lock on process exit; neither PID probing nor file age permits takeover.
Contention reports `busy`; an unavailable locking mechanism reports `lock_unavailable` without cleanup.
Age applies only to interrupted temporary folders: those older than 180 seconds are discarded,
not resumed, and structurally safe retired folders are purged on the next locked operation.

`retire(id, owner)` requires a valid matching marker. `retire_owner(owner)` touches only exact owners.
Explicit `retire_all()` removes structurally safe profile folders even if their markers are corrupt or
missing; unsafe and unknown entries remain and are reported in `skipped`, with `complete=False`.
A revocation does not delete a folder yet; an authenticated `retired` answer or a newer generation does.

**Deletion, on every system.** A folder that a running browser holds is not touched (Linux and macOS: Chrome's
`SingletonLock` names a live process, and only that link's text is read; Windows refuses the rename itself).
A folder is taken as free only when there is no `SingletonLock`, no process has the number it names, or its text
holds no usable process number. A process this account may not signal, a lock that cannot be read as a link and any
other error count as a running browser.
Any other folder is first renamed to `.retired-<random>`, then deleted. A link
(symbolic link, junction or other reparse point) is removed itself and never entered, so what it points at
is untouched. A linked `browser-profiles/` root is refused (`unsafe_link`) and never retargeted. A folder
is compared by file ID before and after it is opened; a swap in between is `path_changed` and the folder is
reported. Nothing outside the resolved root is deleted. On Windows each folder is held open, without delete
sharing, while its entries are removed, so it cannot be renamed or replaced meanwhile; paths longer than
260 characters are handled; a read-only attribute is cleared only on an entry already checked, never through a
link (`readonly_link`) and never on a file that also has a name elsewhere (`shared_file`). `delete_all()`, used
only by `cleanup`, removes every entry under the root except `.lock`, whatever its marker, name or permissions.

**When deleting fails** (an open file, a permission), the folder is reported as not deleted and stays. While
a retired folder remains, preparing and opening any workspace on this account is refused with
`purge_pending`; deletion is tried again before the next launch and at the next check-in.

**A different person on the same account.** When someone else signs in, the earlier person's folders are deleted
at the first check-in or sync, and again before a folder is prepared; until they are gone, Open is refused with
`purge_pending`. A folder that a running browser holds is not touched: it stays whole until that window is closed
(Linux and macOS: Chrome's `SingletonLock` names a live process, and only that link's text is read; Windows refuses
the rename itself). The app closes only a window it started and still remembers, so the person may have to close it.
"Someone else" means another Hub address or person ID in the folder's marker. The same person's
folders are kept. A folder whose marker can't be read stays until Swangz is removed from the account.

POSIX directories are 0700 and markers 0600, owned by the current uid. The supplied data directory must
already exist, be owned by that uid and not be writable by group/others; it is never chmodded. Ancestors
above it are outside the module's checks. Windows rejects reparse points from data downward:
**ACL not verified by the app.** Native Windows behavior: **Not run: needs Actions**.
Windows deletion, links and junctions are tested on the GitHub Windows runner, not on a physical
Swangz computer. These checks and the locks assume the same OS-user trust boundary and a supported local
filesystem; network filesystem locking is unsupported. In particular, holding a folder open does not stop a
program running as the same user from turning an emptied folder into a junction.

Personal-device profiles are advisory (D-015b). A shared OS login is not isolation (D-014), and local
administrators remain outside this boundary. Company policy enforcement is separate (D-015a).
Existing personal browsing, files, histories, agent environments and automations remain untouched.

Port-free checks: `python3 -m unittest tests.test_browser_profiles -v`. Browser and provider checks
are inapplicable to this inert slice; cross-platform behavior still needs independent QA and review.

## Not built yet (in rough priority)

- **Signed installers** for Windows (`.msi`/`.exe`, Authenticode) and macOS (`.dmg`, Developer ID + notarization),
  and a Linux `.deb`/AppImage, built by CI from tags. The TEST-key updater below is not enabled in shipped builds.
- **Desktop apps on real Windows and Mac computers.** The allow-listed install step exists (`native_apps.py`, above) but
  has only run against fakes. Published AUMIDs for Store apps, and install paths for most winget apps, are still missing,
  so those are found through winget and opened from the Start menu.
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
