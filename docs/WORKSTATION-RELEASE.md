# One workstation — release notes and acceptance (27 Nov 2026)

The owner's directive of 27 Nov 2026 ("Final product correction and delivery") and what was delivered against it.
Decision record: `DECISIONS.md` D-028. Pull request: #370 (branch `correction/one-workstation`).

**Status: unsigned internal test build. Not deployed.** The server at https://hub.ictconnect.org still runs the
earlier version until the owner authorises the update below.

## What changed

| Directive | Delivered |
|---|---|
| 2. Remove timed turns | Gone from every access path: the staff web app's Open (`/go/`), the browser gate and the desktop app. Everyone assigned a tool opens it at the same time; nothing waits, counts down, expires or signs anyone out. A tool set up as one company login is labelled with its limitation (staff tile, app card, console Explain, seat planning, a Needs-attention item) — never a timer. Turn history is kept; migration v31 closes any turn still open. |
| 3. Swangz AI Workstation | The desktop app's window is now a workstation: sidebar Home · Apps (the AI library) · Workspace (the person's Swangz Chrome) · Automations · Usage · Settings. Several apps open at once in the same personal Chrome folder. The first macOS CI screenshot showed Aqua ignoring button colours (white boxes, unreadable text); macOS now draws buttons as styled labels (`gui.LabelButton`, tested). |
| 4. Chrome | Unchanged rules from D-026, now reached by every website tool: genuine Chrome only, publisher-checked; a dedicated persistent folder per person; never the default browser for an AI tool. Windows company installer installs Google's enterprise MSI with consent; macOS and personal Windows open Google's Chrome page and re-check. Extension 1.2.0 keeps sessions across restarts. |
| 5. App manager | `swangz_client/native_apps.py`: a fixed table in the app (never commands from the server) with an official source per entry, checked 27 Nov 2026. Windows installs through `winget` with the exact id, after a consent dialog; command-line tools (Claude Code, Codex) install in a visible terminal; macOS and unverified apps open the vendor's download page. Detect, install, open, repair, state per app. Web-only tools open in Swangz Chrome. |
| 6. Authentication | Unchanged: one Swangz sign-in (device code) for the workspace; providers sign in separately, in the person's own Chrome folder. No password injection, cookie copying or session sharing. |
| 7. Control Room | New **Workstations** page, the console's landing page: employees and departments, computers online/offline with app version, Chrome state and installed AI apps, assigned apps, accounts (seats vs single-login limits), activity labelled *Observed in Swangz* (not provider billing), weekly reports, Suspend and Revoke. |
| 8. Browser security | The company Chrome pack (D-016) now also allows Grok, Google Flow, Antigravity and Grok's sign-in host. Gmail, Drive and Google account pages stay blocked. Controls that cannot be enforced are listed in D-026 and on the Workstations page. |
| 9. Infrastructure | No new server, browser fleet or paid service. The remote company browsers (Neko) are dormant: nothing routes to them. |

New catalogue tools: Grok (grok.com), Google Flow (flow.google.com — Google moved it from labs.google), Antigravity.

## Acceptance tests — results

Automated = unit/integration tests on a stand-in provider (`tests/fake_upstream.py`), run on GitHub CI and/or this
Linux laptop. Real-device = a person on a real Windows PC or Mac. **No real-device test was run today**: there is no
Windows PC or Mac here.

| Required test | Automated | Real device |
|---|---|---|
| Fresh Windows installation | CI installer workflow: silent install, launch, enrol, restart, reconnect, upgrade over a running copy, uninstall (see CI below) | Not run |
| Fresh macOS installation | CI macOS workflow: install from DMG, launch, enrol, restart, upgrade, uninstall; Gatekeeper refusal recorded (unsigned) | Not run |
| Chrome detection and provisioning | `tests/test_chrome_install.py`, `test_chrome_verify.py`, `test_workspace_launcher.py`, GUI Chrome step tests; Linux laptop: Chrome found at `/opt/google/chrome/chrome` | Not run |
| Native app detection and install | `tests/test_native_apps.py` (fake runners; no real install). winget ids checked against microsoft/winget-pkgs on 27 Nov | Not run |
| Two employees at once | `tests/test_turns.py::EveryoneAtOnceTests` — two people open the same single-login tool repeatedly, both 302, no turn rows, each open attributed | Not run |
| One employee, several apps at once | `test_one_person_opens_several_tools_at_once`; launcher tests | Not run |
| No timers, queues or forced expiry | `test_turns.py`, `test_device_open.py`, `test_managed_workspace.py`; extension `tests/browser/extension.cjs` (51 pass: no clearing at Chrome start, no turns alarm, sign-out clears no site data) | Not run |
| Sessions persist after restart | `tests/browser/extension-chrome.cjs` (real Chromium in CI: cookie and storage survive a 401 and a browser restart) | Not run |
| Independent employee workspaces | Existing per-person folder tests (`test_browser_profiles.py`, `test_core_proof.py`) | Not run |
| Admin activity monitoring | `tests/test_workstations.py` (26) — endpoint, permissions, online/offline, apps report, no content leaks; heartbeat app report test in `test_devices.py` | Not run |
| Admin access revocation | `test_workstations.py` suspend/revoke via existing routes; `test_turns.py` suspension still cuts access | Not run |
| Server and database compatibility | Migration v29→v31 on a scratch copy of the 26 Nov server backup: integrity ok, 0 foreign-key problems, every row kept (tools +3, audit +3, settings +1); `gateway backup` + `backup-verify` ok on the migrated copy | Server not updated |
| No provider credentials exposed | `test_workstations.py` no-leak checks; `test_content_privacy.py`; the manifest and app report carry ids and states only | — |
| No regression | Full suite on GitHub CI (Python 3.10 and 3.12, browser, app window) — see CI below | — |

CI on the release commit: _filled in below when the runs finish._

## Installers

_Filled in below: GitHub pre-release with the Windows EXE (personal and company) and the macOS DMG, all labelled
"RC — UNSIGNED — INTERNAL TEST ONLY"._ No signing certificates exist yet (Windows Authenticode, Apple Developer ID),
so Windows SmartScreen and macOS Gatekeeper will warn. The macOS build is Apple Silicon (arm64) only.

## Updating the server (owner's go-ahead needed)

Follow `OWNER-RUNBOOK.md` "Update the server" exactly, with `<new>` = the release commit named in the PR. Differences
for this release:

- The backup-verify check after the update expects **`schema v31`**.
- Migration v31 closes any open turn and adds two device columns; nothing is deleted.
- Extra checks after the update: two staff open the same tool at once (both get in); the console lands on
  Workstations; an app check-in shows its apps on Workstations.
- Company computers with the Chrome pack in `enforce`: the pack changed (4 hosts added), so its baseline hash changed.
  Install the new pack and set the new baseline in Settings before turning `enforce` on (D-024).
- Roll back: the runbook's "Roll back" section, to the commit written down in step 1, with the pre-update backup.

## Owner decisions and outstanding limitations

1. **46 tools are set to "one company login" on the server** (Arnold, 22 Nov). After this release they open for
   everyone at once, with the limitation shown. Most providers' terms allow one person per login: convert each to
   seats or SSO (Tools → the tool → Access) — Swangz does not and will not share passwords or sessions.
2. Unsigned installers; no real Windows or Mac test yet. First real-device run: install, sign in, open two web tools
   and one native app, restart, confirm still signed in.
3. Windows Store and winget-only apps open from the Start menu (no published launch id); several Windows install
   paths are unverified and fall back to `winget export`.
4. Opening vendor download pages in the default browser extends D-026 D2 (download pages only, never AI tools).
5. The dormant remote-browser code (`gateway/workspace.py`, `workspace_agent/`) and its 26 skipped tests should be
   removed in a separate change.
6. Linux and mobile work is frozen per the directive.
