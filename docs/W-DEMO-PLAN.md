# Recording the managed-workspace demo (MANAGED-WORKSPACE.md section 9.3)

Who: Probe runs it and writes the result; one builder stays on call to fix breaks. Where: the team laptop, Linux,
real Google Chrome (stable, from the .deb) or .deb Chromium. Never snap Chromium, Edge or Brave. Not on the live Hub:
`~/swangz-gateway` and `~/swangz-gateway-demo` are never touched. Everything below uses a throwaway data folder and
the fake provider. No real key, no real provider account, no deploy.

This is the plan for recording the steps in 9.3. The result of a run goes in `docs/MANAGED-WORKSPACE.md` section 9.3 (or
a dated note next to it), with the commit hash of `feature/managed-workspace` that was tested.

## 0. Before you start (about 10 minutes)

1. Check the browser slot: nothing else running Chrome or a demo server (`ps -eo pid,args | grep -E 'demo\.py|chrome'`).
2. Check out `feature/managed-workspace` in a scratch worktree under `.worktrees/`. Write down `git log -1 --format=%h`.
3. Start a throwaway Hub: a fresh empty data folder (`GATEWAY_DATA=<new folder>`), `GATEWAY_PUBLIC_URL=http://localhost:<port>`,
   `python3 -m gateway add-admin <owner email>` and a staff person with a password (`tests/browser/demo.py` builds
   exactly this with `grace@swangzavenue.com` and `demo-password`; use it if you do not want to build one by hand).
4. Give the staff person Gemini, Perplexity and Canva in the console (People, open the person, Access, give a tool).
   Each needs an active subscription. ChatGPT and Claude are seeded as `api` tools; they only appear as workspace
   apps if an admin makes them website tools (see PR #213).
5. A second, separate app folder for the client: `SWANGZ_HOME=<new folder>` for every `swangz` command below.
6. Record (screen capture or terminal log): the Chrome version (`google-chrome --version`), the commit, the date.

## 1. Steps, who does what, what to capture

Each step lists the exact action, the expected result and what to save. A step that does not match is a FAIL: write
the exact element or message, do not repair the code.

**Step 1: enrol, then Open three tools.**
- Staff (person): `swangz login --server http://localhost:<port> --name "Demo laptop"`. The terminal prints a link and a
  code. Open `/device` in a browser where the staff person is signed in, check the code matches, press Approve.
- Capture first: `ps -eo pid,args | grep -iE 'chrome|chromium|firefox' | grep -v grep` into `before.txt`, and the
  default browser's name (`xdg-settings get default-web-browser`).
- Staff: `swangz apps`, then `swangz open gemini`, `swangz open perplexity`, `swangz open canva` (or press Open in the
  app window or the staff app on the same device).
- Expect: "Opened in the Swangz workspace window." Each opens in one Chrome window whose command line has
  `--user-data-dir=<SWANGZ_HOME>/browser-profiles/...`, on the provider's official address (gemini.google.com,
  perplexity.ai, canva.com). A second Open adds a tab, it does not start a second profile.
- Capture: the address bar of each tab, the window's process list (`after.txt`), and a diff against `before.txt`: the
  default browser must have no new process. In the console, Activity, Tools opened: three launches for this device.

**Step 2: sign-in persists.**
- Staff: sign in by hand to one provider in the workspace window. With the fake provider there is no real sign-in;
  use any site cookie the demo page sets, or sign in to a throwaway account the team owns. Never a staff or owner
  account. Close the window, run `swangz open <same tool>` again.
- Expect: still signed in; `ls <SWANGZ_HOME>/browser-profiles` shows one folder, not two.
- Capture: the page after reopening, the folder listing before and after.

**Step 3: suspend, then reactivate.**
- Admin: there is no console button yet. Use the device workspace route, signed in as the owner:
  `POST /admin/api/devices/<device_id>/workspace` with `{"action": "suspend"}` (header `x-gateway-admin: 1`; the
  the device id is the `device_id` field of `GET /admin/api/devices`: neither the Devices page nor `swangz status` shows it, checked 14 Nov at `9260034`). Expect an audit entry.
- The app checks in every 15 minutes. To avoid waiting, run `swangz sync` on the device and say so in the record.
- Expect: the workspace window closes; `swangz open <tool>` is refused with the plain "paused" message from
  `swangz_client/workspace_launcher.py`; an Open sent before the app has checked in is refused by the Hub and recorded (Activity, Tools opened, outcome refused, rule `workspace_suspended`); once the app knows the workspace is paused it refuses on the device and the Hub records nothing.
- Then `{"action": "reactivate"}`, `swangz sync`, `swangz open <tool>`: Open works and the earlier sign-in is still there.
- Capture: the refusal text, the three console records, and the time between the API call and the window closing.

**Step 4: retire.**
- Admin: `{"action": "retire"}`, then on the device `swangz sync`.
- Expect: the profile folder under `<SWANGZ_HOME>/browser-profiles/` is gone; `swangz open <tool>` says the
  workspace was removed (not "paused").
- Capture: the folder listing after, and the refusal text.
- Extra check: reactivate after retire starts a new folder with a higher generation; the old sign-in must not come back.

**Step 5: prepared policy, in a container only.**
- The laptop has no container runtime, so this runs as the GitHub Actions job "W6 step 5, prepared pack"
  (`.github/workflows/w6-step5.yml`, PR #214). It makes the pack with `deploy/chrome-policy/prepare.py` using CI
  placeholders, runs the bypass cases against Chrome with and without the pack, and checks the client reports the same
  baseline hash.
- Capture: the run URL, the Chrome version in its log, the line "enforced: N addresses checked, none failing", and the
  client `ok=true` with the baseline hash. Never install a policy on the laptop's own Chrome.

## 2. Windows and macOS

Not run by hand. Whatever the CI runners cover is cited by run URL; everything else is written as "not proven" for
Arnold to try on a real machine on 15 Nov (two non-admin OS accounts per machine, see `docs/MANAGED-WORKSPACE.md`
section 7).

## 3. What this demo does NOT check

- That the forced extension installs, or that a second data folder carries it (needs a signed extension and a real
  update address).
- Windows ACLs and macOS managed preferences.
- A real provider's sign-in, terms or two-factor behaviour. Sign-in hops for ChatGPT, Claude and Gemini stay as
  documented in PROVIDER-COMPATIBILITY.md, with the two UNVERIFIED hosts still marked.
- Whether a person can open a second Chrome on the same machine outside the workspace. The workspace is one managed
  window; it does not stop other browsers.
- Behaviour when the Hub is unreachable for a long time (only a 401, 403 or network failure closes the window and
  refuses Open, and never deletes the folder; this is covered by unit tests, not by this recording).
- Load, long runs, and anything on the live Hub.

## 4. Cleanup (end of the run)

Close the workspace window, stop the throwaway Hub and the fake provider, remove nothing outside the scratch folders you
made, and list what is still running (`ps`) in the report. Leave nothing running.
