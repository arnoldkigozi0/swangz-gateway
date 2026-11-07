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
