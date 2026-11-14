# W4 threat note: closing, refusing and purging the workspace (with a W5 checklist)

Written against `docs/MANAGED-WORKSPACE.md` §5 W4 and §9.3 (PR #175 head `d1d4df9`), the server side in
`gateway/managed.py` (v26 `workspace_state` / `workspace_generation`, actions `suspend | reactivate | retire | reset`)
and the client at PR #186 head `3fc2ead`: `swangz_client/core.py` `heartbeat()` and `_guard()`
(`HEARTBEAT_SECONDS` = 15 min), `workspace_launcher.Launcher`, `browser_profiles.Profiles`. It answers the parts of
`docs/W3-THREAT-NOTE.md` that were marked W4. Builders follow it; a deviation needs a recorded reason.

## What closing is worth (read first)

Closing the window is a tidy-up and a deterrent, **not a security boundary**. The person still owns the folder and
can start Chrome on it by hand (R-2), and provider sessions carry on at the provider (R-4). The real refusals are on
the server: `/api/device/open` and `/go/?d=` refuse a workspace that is not `active`; the extension gate; the
provider's console. So W4 never trades safety for a stronger-looking close: it does not signal a process it cannot
prove it started, and it does not delete a folder it cannot prove is the one the server meant.

## Assets

- **A2 The workspace folder.** A purge cannot be undone. It deletes local sign-ins, history and bookmarks in the
  workspace. Provider chats stay with the provider (W7).
- **A6 The person's other processes.** They are never signalled.
- **A7 Other folders on the same OS user.** This covers a previous enrolment's workspace and the person's own Chrome
  profiles (W3 A3). Nothing in W4 touches them.
- **A8 The latch.** This is the client's record of the last authenticated workspace answer: state, generation, when
  it was received and any pending purge.

## Entry points

- The heartbeat answer (every 15 min).
- The manifest sync.
- The `/device/open` answer.
- App start.
- On the server: an administrator's `suspend`, `reactivate`, `retire` or `reset`, which is audited with before and
  after.

## Ruling 1: keep the PID in memory only for W4

The launcher keeps the `Popen` handle in memory, as W3 D1 says. Persisting the PID is not part of W4. The gap is open
risk **R-11**: if the app restarts while an earlier window is still running, a later suspend cannot close that window.

Why:
- The value is low (see above).
- The risk is real. A reused PID would make the app signal an unrelated process.
- A sound identity check needs ctypes code on three operating systems, and Windows and macOS cannot be proven on CI
  before 14 Nov.

Behaviour in the gap: when the app starts and its latch says `suspended` or `retired`, it refuses Open and tells the
person in plain words to close the Swangz workspace window. For `retired`, it still purges (Ruling 4).

If a later PR persists the PID, **all** of these are required:
- **Where it is stored.** In the app's own state through `write_private`. Never inside `browser-profiles/`.
- **What is recorded.** The PID, plus the process creation time read from the OS for the child **before any
  `poll()`/`wait()`**. Until then the zombie (POSIX) or the open handle (Windows) keeps the PID reserved. Also record
  the boot identity: `/proc/sys/kernel/random/boot_id` on Linux, the boot time elsewhere.
- **When it may signal.** Only when the PID is alive **and** the creation time is exactly equal **and** the boot is
  the same **and** the process owner is the current uid or SID. If any of these cannot be read, it does not signal.
- **What it must not do.** No executable-path or command-line matching: the Chrome and Chromium wrapper scripts
  `exec`, so the executable differs, and reading another process's command line is fragile on Windows and macOS.
  Never read Chrome's lock files (§2: nothing inside the folder is read).

## Ruling 2: close and refuse triggers

| Event | Close the window we started | Refuse Open | Purge |
|---|---|---|---|
| Authenticated contract-2 answer: `state = suspended` | yes | until an authenticated `active` | **no** |
| Authenticated: `state = retired` | yes | yes | yes (Ruling 3) |
| Authenticated: `generation` > the folder marker's generation | yes | until the purge is done | yes (Ruling 3) |
| Authenticated: `generation` < the marker's (server rolled back) | no | yes, `generation_rollback`; an admin `reset` fixes it | **no** |
| 200 contract-2 answer with an unknown or malformed `state` or `generation` | yes | yes | **no** |
| `Revoked` (401 `device_revoked`) | yes, **before** `remove_everything()` wipes the store | yes (no device left) | **no** |
| Any other 401 or 403 (`device_unknown`, forbidden) | yes | yes | **no** |
| `KeyRotated` leading to `NeedsReconnect` | no | yes, until reconnected (device calls fail anyway) | no |
| Sign-out (the person's own action; also runs `remove_everything`) | yes | yes | **no** |
| Network failure, timeout, TLS error, 5xx, non-JSON | after the grace below | Open needs the Hub anyway | **no** |
| Answer without contract 2 (older Hub) | no change | as W3 (`no_workspace`) | no |

**Grace on network failure and server errors.** This is a recorded deviation from the literal §9.3 text, D-021 (to be entered in `docs/DECISIONS.md`).
- The app closes the window only when the last authenticated answer is older than `2 × HEARTBEAT_SECONDS` (30 min)
  **and** the last two heartbeats both failed.
- Measure the age with `time.monotonic()`, because the wall clock can be moved. Also require the consecutive-failure
  count, because the monotonic clock pauses during sleep.
- Any authenticated answer resets the count.
- Before closing, the app may warn the person once: "Can't reach Swangz: your workspace window will close in
  2 minutes. Save your work."

Why: on a flaky link, closing on every failure loses unsaved work and buys no security. Blocking the Hub to keep the
window open gains nothing when the folder can be reopened by hand (R-2), and the server refuses Open regardless.
Refusing Open needs no client latch on network failure, because Open is an online call (`/device/open`, or `/go/`
through the Hub).

**Implementation notes:**
- `heartbeat()` today folds every `ApiFailure` into `return None`. W4 must separate 401/403 (close at once) from
  transport errors and 5xx (grace).
- In `_guard()`, the `Revoked` branch closes the launcher first and then calls `remove_everything()`.
  `remove_everything()` must keep leaving `browser-profiles/` alone; it does today.
- One reducer function applies the workspace block from the heartbeat, the manifest and `/device/open` alike. Open
  checks that latch first, for a fast plain message, but the server stays the authority.
- `close()` stays as it is: `terminate`, wait up to 10 s, then `kill`. On Windows that is a hard stop, and Chrome may
  offer to restore pages next time, which is acceptable. Do not enumerate or message windows.
- Only the app process that started the window can close it. Say so in `docs/CLIENT.md` if the tray and the window
  are separate processes.

## Ruling 3: when a purge is allowed, and own account versus retire

**The only source for a purge** is an HTTP 200 JSON answer that meets all of these:
- it comes from the enrolled origin in `device.json`, with no redirect to another origin;
- it answers a device-key call;
- `contract == 2`;
- `workspace.state` is one of `active`, `suspended` or `retired`;
- `generation` is an `int ≥ 1`, and not a `bool`.

**Triggers:** `state == retired`, or `generation` greater than the generation recorded **in the folder's marker**.

**Where the generation is kept: in the marker, not in `state.json`.**
- The marker moves to version 2 with one added key, `generation` (`int ≥ 1`), and its strict key check is extended
  explicitly.
- A version-1 marker (W3 test builds only) reads as generation 1, the server's default. A device reactivated from
  `retired` gets generation 2 or higher, so its old folder is correctly replaced.
- A new folder is created with the generation from the authenticated answer that allowed the Open.
- Why: `state.json` is wiped on revoke and sign-out and is not tied to any folder. The marker travels with the folder
  it describes.
- `prepare()` refuses to create a folder while an older-generation folder of the same owner still exists, with the
  error `purge_pending`.

**Scope of a purge:**
- Only `Profiles.retire(profile_id, owner)` or `retire_owner(owner)`, with origin, person, device and OS user all
  matching.
- **Never `retire_all()` from a server answer**: it also deletes folders with invalid markers and is for explicit
  app-root cleanup only.
- A previous enrolment's folder on the same OS user is never touched.

**Own account versus retire (§5 W4 against §9.3).** §9 overrides any conflict, as its header says.
- **What is purged.** The device's one managed workspace folder, the `personal` kind and today the only kind. It is
  purged on an authenticated `retired` or a higher generation. Both come only from explicit, audited administrator
  actions: `retire`, `reset`, and `reactivate` from `retired`.
- **"Never purged without the person's action" covers everything implicit.** That is suspend, revoke, any 401 or 403,
  network failure, a marker mismatch, the account rule (`effective_state` answers `suspended`), sign-out, and app
  update or uninstall. The person's own Chrome profiles and default browser are never touched by anything.
- **Required alongside it:**
  - The console's confirmation for `retire` and `reset` says the workspace folder on the device will be deleted:
    sign-ins, history and bookmarks in it. Chats stay with the provider.
  - After a purge, the app tells the person in plain words.
  - When #175 is next updated, replace the W4 sentence with: "...is never purged except by an administrator's
    explicit retire or reset."

**What stays open:**
- **R-12.** After a revoke, the folder and its sessions stay on disk, because nothing authenticated can retire it any
  more. Removing it is the person's action. A later, optional addition: after re-enrolment, offer "Remove the old
  workspace".
- **Windows.** `Profiles._retire` raises `unsupported_platform` today. On Windows, W4 closes the window, refuses Open
  and reports the purge as not done. It never reports it as done.
- **Hand-rolled Windows delete.** Not in W4, unless a Windows CI test proves that a junction or symlink inside the
  folder pointing outside is not followed and its target survives. §9.3 step 4 is proven on Linux only; Windows is
  listed as not proven for 15 Nov.

## Ruling 4: a purge while the browser is running

The steps, in one function and in this order:

1. Persist the latch with `write_private` (`{state, generation, purge_pending: profile_id}`) **before anything
   else**, so a crash mid-way finishes at the next start.
2. Refuse Open from this point on.
3. `Launcher.close()`: `terminate`, wait up to 10 s, then `kill`.
4. `Profiles.retire(profile_id, owner)`: rename to `.retired-*`, then `_purge`, under the Profiles lock. This
   already exists.
5. On success, clear `purge_pending`. On failure, keep it, retry at app start and at every heartbeat, and show it
   in the app.

- **Close failing does not defer the purge.** On POSIX, rename and unlink work while a browser runs: it loses its
  folder and fails. That is also true for a Chrome the app did not start (R-2).
- **On Windows,** open handles make the delete fail, so it stays pending and is retried.
- **Never** kill a process the app did not start in order to make a purge succeed.

## Abuse cases (STRIDE, short)

- **S. A forged `retired` answer.** It is accepted only over TLS from the enrolled origin, on a device-key call.
  Someone who has put a rogue CA on the device could delete the local workspace. That is denial of service only, and
  accepted.
- **T. The person edits the latch or the marker.**
  - Editing `state.json` to "un-suspend" only affects the client. The server still refuses `/device/open` and
    `/go/?d=`.
  - Raising the marker's generation gives `generation_rollback`, so they only refuse their own Open.
  - Any other marker change gives `owner_mismatch`: Open is refused and nothing is purged.
- **R. Repudiation.** Administrator actions are audited in `managed.py`. The client's log stays access-level and
  bounded: `<time> close <reason>`, `<time> purge done|pending`. No paths, no addresses.
- **I. Information disclosure.** Nothing new is read or sent.
- **D. Denial of service.** A flaky link is handled by the grace. A misused `retire` is audited, and the console
  confirms it first.
- **E. Elevation.** Signalling the wrong process cannot happen: only the in-memory `Popen` handle is ever signalled.

## Server requirement (check in #179 or a small W4 server PR)

`/api/device/open` and `/go/<tool>?d=<device>` call `managed.effective_state` and refuse anything but `active`, using
the `PLAIN` message. Test both with `suspended` and `retired`, and with a person the account rule no longer allows.

## Tests that prove it (stdlib, fake `popen`, fake API, fake monotonic clock)

1. `suspended` calls `close()` once, Open raises `not_active`, `retire` is never called, and the folder is intact.
2. `active` again with the same generation: Open works and uses the same folder (the marker is unchanged).
3. `retired`: the call order is latch persisted, then `close`, then `retire`. The folder is gone and Open is refused.
   With a crash injected after the latch, the next start finishes the purge.
4. Generation G greater than the marker's purges; equal does nothing; lower refuses Open with no purge.
5. `Revoked`: `close` comes before `remove_everything`, and the folder still exists after the wipe.
6. 401 `device_unknown` and 403: close and refuse, folder intact. `KeyRotated`: no close.
7. Network error, timeout, 5xx, non-JSON: one failure does not close. Two consecutive failures spanning 30 min or
   more do close. The folder is intact in every case, and an authenticated answer resets the count.
8. Malformed 200 answers (`state` "bogus"; `generation` "2", `True`, 0, or missing): close and refuse, no purge.
9. A folder whose marker has a different `person_id` or `device_id` on the same OS user survives a `retired`
   answer.
10. When the purge fails (injected `OSError`), `purge_pending` is kept, Open is refused, the purge is retried at the
    next heartbeat and at app start, and `prepare()` refuses while it is pending.
11. `close()` with no process, or with an exited one, signals nothing. The fake `popen` records every signal, and
    none goes to a process the launcher did not start.
12. Marker version 2: an extra or missing key is refused, and a version-1 marker reads as generation 1.
13. Server: `/api/device/open` and `/go/?d=` refuse `suspended` and `retired`.
14. W6 end-to-end against the fake upstream: enrol, open, suspend through the console API, heartbeat; the window is
    closed and Open is refused. Then retire: the folder is gone (Linux).
15. Windows CI: `retired` closes and refuses, and the purge is reported as not done, never silently as done.

## W5 checklist (PR #185 exists; use this when reviewing it)

1. The report covers the browser the launcher will actually start: Chrome or .deb Chromium, with the matching
   directory, macOS domain or registry key. It does not always report Chrome.
2. Only machine scope counts: HKLM in the 64-bit view, `.../policies/managed`, and `/Library/Managed Preferences`.
   The per-user managed copy counts only if it is owned by root. HKCU and the `recommended` folders never satisfy a
   `REQUIRED` setting.
3. Fail closed: an unreadable, invalid, oversized or symlinked file, a duplicate JSON key, or a value that conflicts
   across files gives `ok=false`. It never raises an exception.
4. The report is `{ok, sha256}` only. Problem names stay on the device, and no values are ever sent.
5. Server:
   - Staleness is measured from the time the server received the report, never from a time the client supplies.
   - In `enforce` mode, `/device/open` and `/go/?d=` are refused when the last report is missing, older than two
     heartbeats, failing, or carries a SHA that is not the expected one.
   - In `warn` mode the report is only recorded.
   - The console labels it "reported by the app" (R-3).
6. On Windows, Chrome ignores some policies on machines that are neither domain-joined nor MDM-managed, for example
   forcing an extension from outside the Web Store. A registry value being present is not the same as it being
   applied. W5 must not claim the policy is applied, and R-6 stays open.
7. Tests: one for each of 1–5, plus "policy file removed gives `ok=false` and `enforce` blocks Open" (W6 list).
