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

CI on the release code (PR #370 merged with main `643947f`, build ref `9cd08a3`, file tree identical to
`c06f0b1f67800fd55e4bcdf8878a64dcd3406e5f`), all green on 27 Nov 2026:

| Workflow | Run | Result |
|---|---|---|
| Hub checks — Python 3.10 and 3.12 | 46015853704 | 1,977 tests OK each (85 skipped: OS-specific tests and the 26 retired remote-browser tests) |
| Hub checks — app window (xvfb) | 46015853704 | 37 tests OK, including the macOS label-button test |
| Hub checks — browser suites | 46015853704 | pass |
| Windows installer (RC, unsigned), Windows Server 2025 | 46015853735 | 84 steps pass (incl. two people at once, revocation, upgrade 0.1.100 → 0.1.227, uninstall); company installer 10 steps pass |
| macOS app (RC, unsigned), macOS 26 arm64 | 46015853745 | 169 journey steps pass; Gatekeeper refuses the unsigned app, as expected |
| Chrome policy pack checks / W6 step 5 / Inert browser profiles | 46015853833 / 46015853693 / 46015853698 | pass |

The first macOS run (before `7711769`) showed the workstation's buttons drawn white with unreadable text by Aqua;
fixed and re-run. The macOS screenshot also shows a "Allow "Python" to find devices on local networks" prompt: CI's
Hub runs on the runner's local network; the name "Python" in it should become "Swangz" in the bundle (open item).

## Installers

GitHub pre-release **`rc-unsigned-20261127-c06f0b1`**:
https://github.com/arnoldkigozi0/swangz-gateway/releases/tag/rc-unsigned-20261127-c06f0b1 (private repository:
sign in to GitHub to download). Labelled "RC — UNSIGNED — INTERNAL TEST ONLY".

| File | SHA-256 |
|---|---|
| `Swangz-Setup-0.1.227-UNSIGNED.exe` (Windows, one person) | `a05a67a506ac54dfd42b4a1f1146f68601d74fe0f95a3726d813d88b7d696838` |
| `Swangz-Company-Setup-0.1.227-UNSIGNED.exe` (Windows, company computers) | `e4bdca30d0db5c9763baf8a33a4989881c4481781bcd37a4ee818fbdd90f233f` |
| `Swangz-0.1.270-RC-UNSIGNED-macos-arm64.dmg` (macOS, Apple Silicon) | `c644bc2c6321783e67bd571786070fe2aba280477541933826cc0072242e51ae` |

Also attached: `SHA256SUMS`, the CycloneDX SBOMs, and the evidence zips from both install runs. No signing certificates exist yet (Windows Authenticode, Apple Developer ID),
so Windows SmartScreen and macOS Gatekeeper will warn. The macOS build is Apple Silicon (arm64) only.

### Later the same day: Google sign-in build (D-029)

**`rc-unsigned-20261127-2225a66`** — https://github.com/arnoldkigozi0/swangz-gateway/releases/tag/rc-unsigned-20261127-2225a66
— adds "Sign in to Google in Swangz Chrome" (D-029) and includes main up to #371. CI on a tree identical to `2225a66`:
1,991 tests OK on Python 3.10 and 3.12, 40 window tests, Windows 84 + 10 steps, macOS 169 steps. App-only change: the
server stays on `c06f0b1`.

| File | SHA-256 |
|---|---|
| `Swangz-Setup-0.1.231-UNSIGNED.exe` | `2a747e02098ffd5ee53bc5b244a06bcbe66afee600c1d766c66a53bf0d0777e5` |
| `Swangz-Company-Setup-0.1.231-UNSIGNED.exe` | `2a92cff88a1ef9bdaf5680e5e9ef899eb62ba4c1246b9192a3d5ebc8f74c94af` |
| `Swangz-0.1.274-RC-UNSIGNED-macos-arm64.dmg` | `d7bfd05068a97d6bee42e68275861ed2a582d46564a1ece4824ec8ee415a7eca` |

On the server (27 Nov, 15:37 UTC, audited, backup `pre-update/gateway-20261127-153726.db.gz` first): the 46 single-login
tools moved to each person's own account — 38 to Google sign-in (`sso`, confirmed on the vendors' own pages), 8 to a
personal seat (Copilot, Copy.ai, DeepL, DaVinci Resolve, n8n, Socialinsider, Topaz, and Sora, which OpenAI shut down
on 26 Apr 2026 and should be archived).

## Updating the server (owner's go-ahead needed)

Follow `OWNER-RUNBOOK.md` "Update the server" exactly, with **`<new>` = `c06f0b1f67800fd55e4bcdf8878a64dcd3406e5f`**
(the tested code; later commits on the branch change only `docs/`), or the `main` commit PR #370 becomes when merged —
then check `git diff --stat c06f0b1 <main commit> -- gateway deploy swangz_client extension .env.example` lists nothing.
Differences for this release:

- The backup-verify check after the update expects **`schema v31`**.
- Migration v31 closes any open turn and adds two device columns; nothing is deleted.
- Extra checks after the update: two staff open the same tool at once (both get in); the console lands on
  Workstations; an app check-in shows its apps on Workstations.
- Company computers with the Chrome pack in `enforce`: the pack changed (4 hosts added), so its baseline hash changed.
  Install the new pack and set the new baseline in Settings before turning `enforce` on (D-024).
- Roll back: the runbook's "Roll back" section, to the commit written down in step 1, with the pre-update backup.

**Backup and migration, verified 27 Nov 2026** on a scratch copy of the server's 26 Nov pre-update backup (schema 29;
kept on the laptop only, never published): migrated to v31 with integrity ok and 0 foreign-key problems; every table
kept its rows except tools +3 (Grok, Google Flow, Antigravity), audit +3 (their "added a built-in tool" rows) and
settings +1; then `python3 -m gateway backup` and `backup-verify` on the migrated copy: `checksum and integrity ok`.

## Owner decisions and outstanding limitations

1. Done 27 Nov: the 46 single-login tools now use each person's own account (see above). Paid features still need a
   seat per person on each tool's company plan, invited by work email.
2. Unsigned installers; no real Windows or Mac test yet. First real-device run: install, sign in, open two web tools
   and one native app, restart, confirm still signed in.
3. Windows Store and winget-only apps open from the Start menu (no published launch id); several Windows install
   paths are unverified and fall back to `winget export`.
4. Opening vendor download pages in the default browser extends D-026 D2 (download pages only, never AI tools).
5. The dormant remote-browser code (`gateway/workspace.py`, `workspace_agent/`) and its 26 skipped tests should be
   removed in a separate change.
6. Linux and mobile work is frozen per the directive.
