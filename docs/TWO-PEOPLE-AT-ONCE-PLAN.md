# Deliverable 5: two people signed in at once (test plan)

Status: PLAN ONLY. Nothing here has been run. Drafted 19 Nov 2026 against main `9313eaa`.
Release label for any result: `RC - UNSIGNED - INTERNAL TEST ONLY`.

## What is open

`RELEASE-EVIDENCE.md` row 5 lists "two people signed in at the same time" as open. Today's second-person step
(`packaging/hub_journey.py: second_person`, #272) signs person 1 out, signs person 2 in on the same app, and shows a
second folder beside the first. It never has two people signed in together. "At once" means three different things,
and each needs different evidence:

| Level | What "at once" means | Where it can be tested |
|---|---|---|
| A | Two people hold a shared-account turn together (`seats_at_once` = 2) | Hub, fake upstream, CI |
| B | Two signed-in app instances with separate data folders, both with a workspace window open | CI runner, one OS user |
| C | Two real OS users on one machine, or two devices, each with its own person | Arnold's machines (OWNER) |

## A. Shared turns, server side (CI, no new code)

Existing: `tests/test_turns.py::test_two_seats_let_two_people_in` (two 302s, two open turns). It does not show that a
third person is refused, that ending one turn frees exactly one seat, or that one person's release leaves the other's
browser alone. Add, when a builder has time (small, Hub-only):

1. `seats_at_once` = 2: persons 1 and 2 get a turn; person 3 is refused with the "in use" message.
2. Person 1 releases: person 3 can now enter; person 2's turn is unchanged (same `tool_turns` row, `ended` NULL).
3. With `workspace_mode = 'agent'` against the fake agent: two turns get two different browser slots and two
   different Neko sign-ins; releasing one deletes only that sign-in and recycles only that container.
4. The audit trail shows two overlapping turns, each under its own person.

Not provable here: a real Neko session, real provider sign-in, real video relay (OWNER).

## B. Two signed-in app instances at once (CI, small journey change)

Feasible without app changes. `Paths` reads `SWANGZ_HOME` (`swangz_client/core.py:88`), so one runner can host two
installed-app instances with two data folders. The keychain entry is named by server and key id (`keystore.account`),
so two devices should not collide, and step B3 checks that rather than assuming it.

Journey steps (macOS `macos_journey.py` and Windows `installer_e2e.py`, after `second_person`; the first person's
app instance keeps its own `SWANGZ_HOME`, the second gets another):

| Step | Assert | How |
|---|---|---|
| B1 | Both are signed in together: `status` for each instance exits 0 and names its own person | two `app("status")` calls with different `SWANGZ_HOME`, no sign-out between them |
| B2 | Both open the same granted tool and both windows are alive together | two opens; two Chrome processes whose command lines carry two different `--user-data-dir` folders, both running at the same time (list processes before closing either) |
| B3 | Two different device ids, two different keychain accounts, two different keys | read both manifests and both stored key hashes; never print a key |
| B4 | Neither folder holds the other person's marker, and neither data folder holds the other's key | `marker_of` on each; `files_holding` for each key over both data folders |
| B5 | The Hub shows two devices and two recorded opens, each under its own person | admin devices and activity as the admin |
| B6 | Revoking person 1's device leaves person 2 signed in and syncing | revoke 1, `sync` for 2 exits 0, `sync` for 1 exits 3, person 2's folder untouched |
| B7 | Signing person 1 out removes only their login item and key, not person 2's | file and process checks after sign-out |
| B8 | Cleanup: both Chrome processes ended by folder, nothing left | the existing `close_chrome(folder)` once per folder |

Limits that stay stated in the evidence row: same OS user, so it does not prove OS-level separation (no ACL or
second-user check); the windows are Google Chrome opened on a fixture tool, not a real provider sign-in.

Risk to check first: whether two instances running together contend on something global (a lock file under the home
folder, one login item name, the same Keychain service). If so, record it as a finding for Forge; do not work around it
in the test.

## C. Real machine (OWNER, Arnold)

Needs two company accounts and either two OS users on one computer or two computers. Checklist for the owner
sheet (`RELEASE-EVIDENCE.md` owner-only list):

1. Windows with two Windows users: user A signs in and opens a tool; user B (fast user switching) signs in as another
   person and opens a tool. Neither can open the other's `browser-profiles` folder (File Explorer reports access
   denied) or read the other's `device.key` / Credential Manager entry.
2. Same on macOS with two macOS users (fast user switching).
3. Two computers, two people, the same shared-account tool with `seats_at_once` = 2 and a workspace on the server:
   both open it together; each sees their own browser; neither sees a password; releasing one does not disturb the
   other.
4. A third person is refused with a clear message while both seats are held.
5. The admin's Live and Activity pages show both people, each with their own device and tool, at the same time.

Result words: PASS / FAIL / NOT TESTED, with the screenshot or the exact message seen.

## Order and cost

1. A (Hub-only tests, no browser, minutes of CI) first.
2. B after Forge's pkg-enrol-negative and Anvil's mac-policy-tamper heads merge, because all three edit the journey
   files; one journey owner at a time.
3. C is Arnold's, after the release candidate artifacts exist.

Until A and B pass on both runners, row 5 keeps "two people signed in at the same time" as open.
