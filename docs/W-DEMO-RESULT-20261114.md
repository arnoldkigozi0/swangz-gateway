# Managed-workspace demo, MANAGED-WORKSPACE.md section 9.3: result of the run on 14 Nov 2026

Tested: `feature/managed-workspace` at `9260034` (PR #204, includes #224-#229 and the W PRs). Google Chrome 156.0.8078.47
(stable .deb) on the team Linux laptop. Plan followed: `docs/W-DEMO-PLAN.md`. Run by Probe.
Harness and raw output: `docs/w-demo-20261114/` (`demo93.py` runs the real app core, `swangz_client`, against the in-process
fake Hub with a real Chrome; `results.json` is what it printed; the run takes 18 seconds).

How this differs from the plan, so nobody reads more into it than is there:
- **Headless Chrome through a wrapper** (`chrome-headless.sh`: `--headless=new`, and every name except 127.0.0.1 fails to
  resolve). The app starts exactly the command line it builds; the wrapper only adds those switches. No provider page loaded,
  no sign-in happened, nothing left the laptop. There was no window to look at, so there are no screenshots.
- **The app core was driven from Python** (`Client.login`, `refresh`, `open_app`, `heartbeat`), not the `swangz` command or
  the app window. Same code paths as the commands; the window and the command-line wrapper were not exercised.
- **A marker file stands in for a sign-in cookie** (step 2): there is no real sign-in with the fake provider.
- **Heartbeat run by hand** instead of waiting 15 minutes.
- Throwaway data folder under /tmp and the in-process Hub. `~/swangz-gateway` and `~/swangz-gateway-demo` were not touched.

## Result per step

| Step | Result | Evidence |
|---|---|---|
| 1. Enrol, Open Gemini, Perplexity, Canva | **PASS** | `open_app` returned `workspace` for all three. The manifest marked each as `workspace: true` with its own hosts. One Chrome main process, command line `--user-data-dir=<data>/browser-profiles/<id> --no-first-run --no-default-browser-check https://gemini.google.com/`; the 2nd and 3rd Open created no second process and no second folder (one folder). Hub recorded 3 launches, outcome `opened`, all with this device's id. The only new Chrome processes outside the profile folder were two `chrome_crashpad_handler` processes of the headless run; they exited with it. The user's own Chrome (the default browser, `google-chrome.desktop`) got no new process. |
| 2. Sign-in persists | **PASS for the folder, not for a sign-in** | Close, then Open again: same folder name, same inode, one folder, marker file still there, one new Chrome process on the same folder. **Not run:** a real cookie surviving (no network, no sign-in); counting tabs (headless). |
| 3. Suspend, reactivate | **PASS** | Owner route `suspend` returned 200 and wrote audit entry "suspend the workspace on a device". Open *before* the next check-in: the Hub refused it, launch row `refused`, rule `workspace_suspended`, "Your Swangz workspace on this device is paused by an administrator." After `heartbeat` (0.2 s): the window process was gone, the folder stayed, and Open is refused on the device with "This device's workspace is paused. Close any open workspace window, and ask your admin." Reactivate (audited), `heartbeat`, Open: works, marker still in the folder. |
| 4. Retire | **PASS** | Close, `retire` (audited), `heartbeat`: the profile folder is gone (`browser-profiles` empty), no process; Open says "Your admin removed the Swangz workspace from this device, so nothing was opened." (not "paused"); server state `retired`, generation 1. Reactivate: state `active`, generation **2**, a **new** folder with a different name, and the marker from before is gone. |
| 5. Prepared policy in a container | **PASS by CI, not run locally** | The laptop has no container runtime. GitHub Actions "W6 step 5, prepared pack" at `9260034`: run 43548912860 (job "Prepared pack bypass checks (ubuntu, Google Chrome)", pass, 9m49s) and re-run 43550429075 (pass); "Chrome policy pack checks" run 43548912909 pass. I did not read those logs for the "enforced: N addresses checked, none failing" line or the baseline hash, so this row cites the job result only. |

## Things the run showed that are not step failures

1. **The plan expected a Hub record for the refusal after the check-in, and there is none.** Once the app has learned the
   workspace is paused, it refuses locally before asking the Hub, so Activity shows no `refused` row for that attempt. A row
   exists only for an Open sent to the Hub before the check-in. That is consistent with the code's rule that the device checks what it can
   before asking the Hub. Not a defect; the plan's step 3 wording should say so. Probe fixes the plan wording in a docs PR if Chief agrees.
2. **The console has no button for suspend, retire or reactivate** (known, in the plan). The admin route was used.
3. **Suspend needs a check-in.** The window closed within the heartbeat call (0.2 s); in production that is up to 15 minutes after the admin acts.
   Until then the person can keep working in an open window and any new Open is refused by the Hub. State this to the admin when the button lands.

## CI on the branch (not part of 9.3)

`feature/managed-workspace` at `9260034`: workflow "Hub checks", job **browser**, step "Control kit (select, More menu, split
button, filter bar, side sheet)" fails: `dark desktop select: with no room below, the list opens above its trigger`
`{"gap":2,"top":616,"bTop":848,"bBottom":884,"pBottom":846,"ih":900}` (run 43548912924, job 132306584295). python (3.10), python (3.12)
and app-window pass; the policy and inert-profile workflows pass. `main` Hub checks pass at `9407c10`. A browser UI failure,
not a workspace one, but PR #204 cannot merge with it red. Owner: Prism (select popover placement in the dark desktop case).

## Not checked (as the plan says)

Forced extension install, Windows ACLs and macOS managed preferences, a real provider sign-in, other browsers on the machine,
a long Hub outage, load, and the live Hub.

## Still open from the same task

- Post-merge verification of #231, #233 and #234: not run, all three were still OPEN into `main` at 08:05 on 14 Nov.
- Re-test of Hub sign-in, light theme, phone bar and staff shell against the fix lists: not run in this task; it follows the post-merge check.
