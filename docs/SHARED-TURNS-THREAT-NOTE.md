# Threat note: shared company accounts (turns) and the Swangz app

Written 13 Nov 2026 against `origin/feature/managed-workspace` at `adac542` (merged there: #179, #183, #185, #186, #191):
`swangz_client/core.py` `_open_in_workspace`, `gateway/device_open.py` `device_open`, `gateway/enroll.py` (manifest
`app["workspace"]`), `gateway/managed.py` `launch_refusal`, `gateway/staff.py` `launch`, `gateway/turns.py`,
`gateway/workspace.py` `link()`. It answers @Forge's five questions on Chief's queue item "shared tools through turns".
Recorded as D-022 in `docs/DECISIONS.md`. Builders follow it; a deviation needs a recorded reason.

## Summary

**The app keeps refusing shared tools for the 20 Nov release (option a).** Turns stay in the staff web app (`/go/`)
and the extension, unchanged. The only code work is one manifest fix and pin tests (below).

## Assets

- **S1 The shared provider account.** Its password and session live only in the company browser profile on the
  workspace server. Swangz code never reads, stores or types it (CLAUDE.md, MANAGED-WORKSPACE §2.1).
- **S2 The per-turn Neko sign-in.** `workspace.link()` puts `usr` and `pwd` in the browser address's query. It is a
  reusable credential for the length of the turn. Whoever holds it can watch and drive the shared account.
- **S3 The turn record** (`tool_turns`): who held the shared account when. This is the whole point of turns
  (attribution of vendor spend).
- **S4 The managed workspace profile** on the device and its URL allowlist (D-016, W3).

## Entry points

- `POST /api/device/open` (device key) for a tool with `signin = 'shared'`.
- The manifest's `app.workspace` flag, which decides whether the app calls `/device/open` at all.
- `/go/<tool>` in the person's own browser (cookie session). This path is unchanged.

## Why not (b) now: handing out turns and the Neko browser in the workspace window

1. **It breaks two hard limits of the managed-workspace stream.** MANAGED-WORKSPACE §2.6 says "no remote browsers for
   this path", and §2.2 says "no shared provider identity" in the workspace. Changing either is Arnold's decision, not
   a builder's or mine.
2. **It widens the workspace allowlist.** The Neko origin is not a provider host. On Swangz's own computers it is a
   Cloudflare quick tunnel (`*.trycloudflare.com`, a new random name each start), so the workspace would need either a
   server-supplied per-turn host (the server widening the client's allowlist, the pattern W3 forbids) or a wildcard
   that admits anyone's tunnel. That wildcard is a general way round the D-016 baseline.
3. **It puts S2 on the command line.** The launcher passes the URL as a Chrome argument. Any process of the same user
   can read it, other users can too on Linux without `hidepid`, and it may stay in the profile's history. W3 A1
   forbids tokens on the command line or in a URL. A safe version needs a single-use launch code, which is new code
   in the Workspace Agent or Neko.
4. **It buys little.** The staff web app already hands out turns with attribution, and the Neko page keeps the shared
   session off the device whichever browser shows it. Plan v18 item 8 defers new features until after 20 Nov.

## Rulings

### Q1: Should the app hand out a shared tool? No (option a), for this release

- Keep `LaunchError("shared_account")` before any window, API call or browser start (D-020). The wording stays: "This
  is a shared company account. Open it from Swangz AI Hub, where turns are handed out."
- Keep the server refusal: `/api/device/open` answers **409 `shared_account`**. It never takes, extends or ends a turn
  and never calls `gw.workspaces`. The refusal is recorded in `launches` with `rule = shared_account`.
- **Fix (Low, fail-closed today).** `gateway/enroll.py:330` sets `app["workspace"] = not app["company_browser"]`.
  `company_browser` is `catalog.uses_workspace(tool)`, which is false for a `signin = 'shared'` tool with no company
  browser (turns at the extension gate only). Such a tool is marked `workspace: true`. The app then skips its own
  `shared_account` check and calls `/device/open`, and only the server refusal stops it. Change it to
  `app["workspace"] = not app["company_browser"] and not turns.is_shared(tool)`, so the manifest matches D-020
  ("not `workspace: true` = every shared account").
- **Optional, a UI PR for Prism, not required for 20 Nov.** The Apps list may label a shared tool "Shared: open from
  Swangz AI Hub" instead of offering an Open that fails. If a button is added, it may open only the enrolled origin's
  staff page (`<server>/?view=tools`, built from `device.json`, `same_origin_url` checked) in the default browser.
  Never `/go/`, never with `d=`, a device id or any token, and never in the workspace window (D-020).

### Q2: A Neko address in the workspace window, and the turn token in a URL or on the command line

These rules apply only if (b) is reopened later, with Arnold's yes on §2.2 and §2.6.
- D-020 is about the Hub's own address. It does not by itself forbid a Swangz-hosted Neko address. But the
  allowlist point above does: the Neko origin must be a fixed host declared in the machine policy, **never** a
  wildcard tunnel domain and never a host the server adds per turn.
- **The reusable `usr`/`pwd` pair must never be on a command line or in a URL the app opens.** An acceptable shape is
  a single-use launch code: random, at least 128 bits, consumed on first use, valid for 60 s or less, bound to turn +
  device, and exchanged server-side by the Neko or agent front for the session. A consumed or expired code is
  worthless. The command line otherwise stays as W3 I1 fixed it.
- **Existing risk, recorded, not a blocker.** The staff web app's `/go/` already sends `usr`/`pwd` in a 302
  `Location`, so it reaches the person's own browser history. It is valid only for the turn, and the agent deletes the
  sign-in and recycles the container on release. Record it as risk **R-10** in MANAGED-WORKSPACE §6 (one row, in the same PR as the fix). The single-use code
  above is its fix, after 20 Nov.

### Q3: Turn end and closing the window

Under (a) there is no app window to close.
- If (b) is reopened, the boundary is server-side. The agent deletes the per-turn Neko sign-in and recycles the
  container when the turn ends, so the remote page goes dead whatever the device does.
- The app's close is then a tidy-up, like W4's ("What closing is worth"). It happens on the next authenticated answer,
  at the existing heartbeat (15 min). Add no new polling, and never a heartbeat under 60 s (§2.6).

### Q4: Attribution, and a device_id on the turn

Under (a), no migration. Turns are taken only through `/go/`, and person + tool + time on `tool_turns` plus the
`launches` row is the attribution D-012 needs.
- If (b) is reopened, add a nullable `device_id` to `tool_turns` in a **new** append-only migration. The device is the
  only thing that tells "taken in the app" from "taken in a browser", and an admin needs that when a device is
  revoked mid-turn.

### Q5: Does enforce-mode policy (W5 `launch_refusal`) gate taking a turn from a device?

- **On the device path, yes, and it already does.** `device_open` runs `launch_checks`, then
  `managed.launch_refusal`, and only then the `is_shared` refusal. So a suspended or retired workspace, a failing
  `enforce` policy, a paused Hub or a missing entitlement each answer with their own code before `shared_account`.
  No path from the device reaches `turns.take`. Pin that order.
- **On the staff web app (`/go/` with no `d=`), no, and this is deliberate.** The shared account lives in a remote
  company browser. No provider cookie or session lands on the device, so the device's workspace policy says nothing
  about the risk. Entitlement, the weekly report, the global pause and company policies still apply through
  `launch_checks`. Do not add a device gate to `/go/` for shared tools.

## Abuse cases (STRIDE, short)

| Threat | Case | Control |
|---|---|---|
| S | A stolen device key asks `/device/open` for a shared tool to get a Neko sign-in | 409 `shared_account`, no turn, no `gw.workspaces` call (T1) |
| T | A crafted manifest or old Hub marks a shared tool `workspace: true` | The server refuses anyway (T1). After the fix the manifest never does (T4). |
| R | A refusal leaves no trace | A `launches` row with outcome `refused` and rule `shared_account` (T1) |
| I | The Neko `usr`/`pwd` leaks through argv or history | The app never receives it (T1 body check). R-10 recorded for `/go/`. |
| D | Device calls hold or extend someone's turn | `/device/open` never touches `tool_turns` (T3) |
| E | A workspace-suspended or enforce-failing device reaches a shared account through the app | Order pinned: the workspace or policy code comes first (T2) |

## Tests that prove it (stdlib, `tests/fake_upstream.py`, no real providers)

Server, in `tests/test_device_open.py`:
- **T1.** `POST /api/device/open` for a `signin = 'shared'` tool in each of three modes (`workspace_mode = 'agent'`,
  static `workspace_url`, none). Expect 409 `shared_account`. Expect no `tool_turns` row. `gw.workspaces` is replaced
  by a fake that fails the test if `assign` or `open` is called. The body has no `url` key and no `usr=` or `pwd=`
  anywhere. One `launches` row has outcome `refused` and rule `shared_account`.
- **T2 (order).** For the same shared tool: workspace `suspended` gives 403 `workspace_suspended`; `retired` gives
  `workspace_retired`; `enforce` with a failing policy report gives `workspace_policy`; not assigned gives the
  entitlement code; the global pause is refused. Each leaves no `tool_turns` row.
- **T3.** The person already holds a turn taken through `/go/`. `/device/open` for that tool still answers 409 and
  leaves the turn row unchanged (`expires`, `ended`, `workspace`).

Manifest, in `tests/test_enroll.py` or `tests/test_device_open.py`:
- **T4.** On a contract-2 device, a `signin = 'shared'` tool has `workspace: false` in all three modes, including
  the no-company-browser case that today returns `true`. A `sso`, `seat` or `own` tool keeps `workspace: true`.

Client (`tests/test_workspace_launcher.py` already has most of this; add whatever is missing):
- **T5.** A contract-2 app with `workspace: false` raises `shared_account` with no Popen, no API call, no `open_url`
  and no `webbrowser`. The message contains no URL.
- **T6.** The defence-in-depth case: an app wrongly marked `workspace: true` whose `/device/open` answers 409
  `shared_account`. It raises `LaunchError("shared_account")` (or the server's plain text) and starts no browser.

No new route, so no new permissions test. No state change, so no new audit. The refusal record is the existing
`launches` row. No migration.

## What stays open

- **R-10** (the Neko `usr`/`pwd` in `/go/`'s redirect): the fix is a single-use launch code, after 20 Nov.
- Shared tools in the app (option b): needs Arnold's yes on MANAGED-WORKSPACE §2.2 and §2.6 first, then Q2 to Q4
  above.
