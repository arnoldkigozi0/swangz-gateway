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
3. The app collects its key once (`POST /api/device/token`). The key is stored in the app's folder, mode 0600;
   nothing is typed or pasted on the device.

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
| Claude Code / Codex | `swangz run claude` / `swangz run codex` set the gateway for that one command; **nothing outside the Swangz folder is written**, so their own use of those tools is untouched | their settings are pointed at the gateway for good (Claude Code's `~/.claude/settings.json` env; a marked block in Codex's `config.toml` plus `SWANGZ_AI_KEY`), so plain `claude`/`codex` are governed; a copy of the original is kept once |
| Signing out | removes the Swangz folder | also takes our lines back out of those files — only what we wrote and only if still ours — leaving anything the person changed since |

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

## The app

`swangz` opens the window: a dock down the left (Home, Apps, Packages, This device), sign-in, sync every 15
minutes while open, "start when I sign in" (a LaunchAgent on macOS, `~/.config/autostart` on Linux, the `Run`
key on Windows). From a terminal: `swangz login|status|sync|packages|apps|open TOOL|run claude|codex|autostart on|off|logout`.

Build a standalone program for the computer you are on (it carries its own Python):

```bash
pip install pyinstaller && python3 packaging/build.py
```

See `packaging/README.md` for installers and signing.

## Not built yet (in rough priority)

- **Signed installers** for Windows (`.msi`/`.exe`, Authenticode) and macOS (`.dmg`, Developer ID + notarization),
  and a Linux `.deb`/AppImage, built by CI from tags; then in-app self-update (the app already learns the latest
  version from each check-in and says so; it does not replace itself yet).
- **OS keychain** for the key (macOS Keychain, Windows Credential Manager, libsecret). Today: a 0600 file in the
  app's folder, owner-only on Unix and the user profile on Windows.
- **Installing Claude Code and Codex themselves.** The app configures and runs them; when one isn't installed it
  says how (`npm install -g …`). Installing third-party programs should be an allow-listed, pinned, checked step.
- **A sign-in link that lands the person in the web app already signed in**, so "Open" on an app doesn't ask again.
- **Chrome Enterprise force-install** of the access gate for company devices (needs the extension hosted with an
  update manifest). Today the app unpacks it and says how to load it.
- **Phones and tablets as installed apps** (store apps). They use the installable web app now.
- Codex's config format and `-c` overrides follow the repo's existing guidance (`gateway/guides.py`); check them
  against the Codex version you deploy.
