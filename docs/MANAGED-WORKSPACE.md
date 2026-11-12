# Managed workspace: one administrator-managed Chromium workspace per enrolled device

Status: **specification. Nothing here is built, deployed or tested on a real staff device.**
Owner request: Arnold, 11 Nov 2026. Builds on PR #146 (policy generator), D-015, D-016, D-019.

## 1. What this is

Each enrolled employee device gets exactly one company-managed Chromium workspace, inside that employee's own OS
account. The person signs in to each AI provider themselves, on the provider's own sign-in page. The Hub decides
remotely whether the workspace may open, and can revoke it. Inference stays on the providers' infrastructure.

## 2. Hard limits (every PR in this stream)

1. No provider password, cookie, token or session is ever read, stored, copied, sent or injected by Swangz code.
2. No shared provider identity. One workspace per person per device; a company seat is assigned to one named person.
3. No production deploy, no install of OS policy on any real device, no purchase of any service.
4. **No merge without Arnold's written approval on the PR.** This overrides the team's merge-on-green rule for this
   stream. Label each PR `needs-arnold`. (PR #146 merged on green while its own description said "draft for review
   only"; that must not repeat.)
5. Every PR description carries the actual test output (command, counts, CI run link). "Should pass" is not evidence.
6. The server stays a light control plane: no remote browsers for this path, no new service, heartbeat at most once
   a minute, under 2 KB.

The existing shared-workspace turns (`gateway/workspace.py`, `gateway/turns.py`) are a separate, already-decided
feature and are not changed here.

## 3. Review of PR #146 (merged at `d26cd82`)

Keep as is: `deploy/chrome-policy/prepare.py`, `swangz-company-chrome.json`, `tests/test_chrome_policy.py`,
`tests/test_managed_chrome_prepare.py`. Re-run on `fa19c0d`: 13 tests, all pass. The generator writes a file only,
refuses overwrite, symlinks and the active Linux/macOS policy folders, and handles no secrets.

Findings to fix in W1 (none is a security hole in the generator itself):

| # | Finding | Fix |
|---|---|---|
| A1 | `REQUIRED` pins 8 settings, but the pack still lacks the D-016 items listed in `docs/CHROME-POLICY-BYPASS-TESTS.md` section 1: `chrome://*`, `view-source:*`, `AutoLaunchProtocolsFromOrigins=[]`, external protocols. "Fail closed" is therefore closed around an incomplete baseline | Add them to the pack and to `REQUIRED`; extend the pinned-names test |
| A2 | `DownloadRestrictions` and `AllowedDomainsForApps` are undecided | Arnold decides (section 8); the generator must refuse to prepare until both are recorded as an explicit choice |
| A3 | `write_new` refuses `policies/managed` but not `policies/recommended`, and has no Windows guard (a `.json` dropped beside a registry import script) | Refuse both Linux folders; on Windows refuse any path under `%ProgramFiles%` and `%WINDIR%` |
| A4 | The PR text says its tests ran against "a matching minimal fixture"; the tests on main do load the real template | No code change; record the real run in the W1 PR |
| A5 | The prepared file has no version or hash, so a device cannot say which baseline it runs | Generator prints the SHA-256 of the output; W2 and W5 use it |

## 4. What already exists and must be reused, not rebuilt

| Need | Existing code |
|---|---|
| Device enrolment, key, rotation, sign-out | `gateway/enroll.py` (`device_code`, `device_token`, `device_rotate`, `device_signout`) |
| Device revocation and idle expiry | `gateway/credentials.py` (`revoke_device_keys`, `expire_idle`) |
| What a device is told | `build_manifest` and the inert `_browser_block` (contract 1) in `gateway/enroll.py` |
| Liveness | `device_heartbeat` |
| Private per-person profile folder | `swangz_client/browser_profiles.py` (`Profiles`, markers, purge, locks), currently inert |
| Who may use which provider, and how they sign in | tool grants, `signin` modes (`sso`, `seat`, `own`), provider registry (D-019) |
| Allowed hosts and forced extension | `deploy/chrome-policy/`, the Swangz extension, the web gate |

## 5. Work items (one small PR each, in this order)

**W1. Complete the baseline.** Fix A1, A3, A5. Tests stay stdlib-only.

**W2. Browser contract 2 (server).** A device that asks for `browser_contract=2` gets, in the manifest's browser
block: `workspace.state` (`active`, `suspended`, `retired`), `workspace.generation` (integer, bumped when a company
seat is reassigned), `policy.sha256` and `policy.mode` (`warn` or `enforce`). Built only from the authenticated
person and device rows, as contract 1 is. Contract 1 answers stay byte-identical. No schema change unless a column
is truly needed; if one is, it is its own migration PR.

**W3. The workspace on the device (client).** Turn on `Profiles` for exactly one `personal` profile per
person + device + OS user. The launcher starts the installed Chrome or Chromium with that folder as its data
directory, and only when all three hold: the manifest says `active`; the OS user matches the profile marker; the
policy check of W5 passes or the mode is `warn`. Storage: folder mode 0700 on Linux and macOS; on Windows the app
verifies an owner-only ACL and refuses to launch if it cannot. The app never opens, reads or copies anything
inside the browser's data folder.

**W4. Revocation.** The heartbeat answer carries the workspace state. On `suspended` or a revoked device key the
client closes the browser process it started and refuses to start it again. On `retired`, or a higher `generation`
for a company seat, it purges that profile with the existing `_purge`. Because 9.1 gives each person one
workspace folder per device, a purge removes everything in it, own-account sign-ins included (the app cannot remove
one provider's data without reading inside the folder, which W3 forbids). The app and the Devices page say so before
an admin retires a device; the person's provider accounts, chats and projects stay with the provider (W7). Purge
happens only on an authenticated answer that says `retired` or a higher `generation`; see 9.1. The Devices page shows state and last policy result. Provider-side sessions
are not ended by any of this; see R-4.

**W5. Policy check beyond the browser's own pages.** The client reads the effective machine policy from where the
OS keeps it (Linux `/etc/opt/chrome/policies/managed`, macOS managed preferences for Chrome, Windows
`HKLM\Software\Policies\Google\Chrome`), checks every `REQUIRED` setting and the default-deny lists, and reports
`policy_ok` plus the hash in the heartbeat. Read-only; it never writes policy. In `enforce` mode the gateway refuses
to open a provider for a device whose last report is missing, stale or failing. Default mode is `warn` until
section 7 evidence exists.

**W6. Cross-platform integration tests.** CI matrix on Linux, Windows and macOS runners:
- stdlib tests: profile creation, permissions and ACL refusal, marker tampering, launcher arguments, purge on
  generation change, refusal after revoke, contract 1 unchanged, heartbeat size.
- Linux with real Chromium and the prepared policy installed inside the CI container only: the bypass cases of
  `docs/CHROME-POLICY-BYPASS-TESTS.md`, plus process-level checks that do not go through page navigation: remote
  debugging port closed when launched with the flag, DevTools unavailable, guest and incognito flags refused, a
  second data directory still under policy and still carrying the forced extension, extension cannot be disabled
  by launch flag, policy file removed → client reports `policy_ok=false` and `enforce` blocks Open.
- An end-to-end run against the fake upstream: enrol, open, revoke, confirm the browser closes and Open is refused.
Windows and macOS runners cannot install real machine policy without admin rights in every case; where a check
cannot run, the test is skipped with a printed reason and listed in the PR as not proven.

**W7. Existing contexts and automations.** Nothing in this stream moves, renames or deletes a person's existing
Chrome profiles, API keys, device keys, n8n, Make or Zapier automations. Tests assert that an existing device key
and an existing gateway API key keep working before and after the workspace is created and after it is revoked
(revoking the workspace alone must not revoke API automations unless the admin revokes the device or the person).
A person's provider chats and projects live with the provider under their account and reappear after sign-in.

## 6. Risks that stay open (do not claim otherwise in any document)

| # | Risk | Why it stays | Mitigation on offer |
|---|---|---|---|
| R-1 | A local administrator can remove or change machine policy | OS design | Staff accounts without admin rights; W5 reports it within a minute; `enforce` mode |
| R-2 | "No additional usable profiles" is not absolute: policy stops adding profiles in the UI, but Chrome can be started with another data directory, and profiles made before rollout remain | Chrome design | Machine policy and the forced extension still apply to those; admin inventories old profiles with the person's consent; another browser must be handled by OS/MDM, not by us |
| R-3 | The policy report is self-reported by client software on the person's machine | No hardware attestation in scope | Treat as a tamper signal, not proof |
| R-4 | Revoking in the Hub does not end a session at the provider | Providers own their sessions | Admin removes the seat or ends sessions in the provider's console; checklist line per provider |
| R-5 | URL lists do not control the network; other apps and browsers reach anything | Out of browser-policy scope | Firewall or MDM, a separate owner decision |
| R-6 | Windows ACL verification and macOS managed preferences are unproven until run on real machines | No such devices in CI with admin rights | Section 7 |
| R-7 | Extension ID, update URL and production host do not exist yet | Owner inputs | `docs/RELEASE-ACCEPTANCE-GATE.md` |
| R-8 | Body storage (`store_bodies`) defaults to on, so admins can read prompt text; this conflicts with the access-level-only logging rule | Found by Probe, 11 Nov | Sentinel to report; owner decision |

## 7. Evidence needed before `enforce` or any rollout

Two non-admin OS accounts on each of Windows, macOS and Linux real machines; the checks listed in
`deploy/chrome-policy/SINGLE-MANAGED-PROFILE.md`; results written into `docs/RELEASE-ACCEPTANCE-GATE.md` with the
commit hash. Until then every screen and document says "not production ready".

## 8. Decisions only Arnold can make

1. Downloads in the workspace: block all (`DownloadRestrictions=3`) or allow (generated media needs them).
2. `AllowedDomainsForApps` and the two owner-address exceptions.
3. `warn` or `enforce` as the default once evidence exists.
4. Whether prompt bodies are stored at all (R-8).
5. Approval of each PR in this stream before merge.

## 9. Owner direction, 12 Nov 2026 (overrides anything above that conflicts)

Arnold, 12 Nov evening: this stream is now the first priority. Team works to the end of 14 Nov; Arnold does his
own items on 15 Nov and wraps up, including the hosted server.

**9.1 Every provider opens inside the Swangz workspace browser. Never in an outside browser.**

Today `swangz_client/shell.py` `open_url` calls `webbrowser.open`, which hands the address to whatever browser the
person has set as default. That stops for provider tools.

- "Open" on any tool (staff app, tray, deep link, a link in a Hub page) starts the workspace browser of W3:
  Google Chrome, or else Chromium installed from the distribution's package (.deb), launched by the app with the
  person's single workspace data folder. Edge, Brave and snap Chromium are never used: they do not read the
  managed policy this stream prepares (`deploy/chrome-policy/`), so a workspace in them would be unmanaged. A
  second "Open" reuses the running workspace (new tab), it does not start another profile.
- The workspace never opens `/go/<tool>`: the workspace folder has no Hub session, so `/go/` would only reach the
  Hub sign-in. Instead the client asks the Hub for the provider address with a device-key call (new in W3; same
  access check and launch record as `/go/`), checks the answer against the tool's allowed hosts, and starts the
  browser on that address. Deep links and links in Hub pages carry a tool id only, never an address or a key. No
  key or token ever goes on the browser's command line (other processes can read it).
- If neither browser is installed, the app says so in plain words with one button to the install page. It does
  **not** fall back to the default browser.
- Links clicked inside the workspace stay inside it. A provider's own sign-in hop (Google, Microsoft, Apple) is
  allowed as part of official sign-in and stays in the same window.
- `open_url` may still use the default browser for exactly three things: the Hub's device approval page
  (`/device`, opened during enrolment at `swangz_client/core.py:599` and again from the app window, where the
  person is signed in to the Hub; enrolment breaks without it), the Hub's own help page and the browser install
  page. A test lists every caller of `open_url` and fails on a new one.
- Why not a web view inside the app window: Google and other providers refuse sign-in inside embedded web
  views, and it would mean shipping a browser engine. The workspace is a real browser window that the app owns,
  starts and closes. Documents say "the Swangz workspace window", not "inside the app window".

**9.2 Downloads are allowed (decision 8.1 is made).** `DownloadRestrictions=0`. Files leave the workspace only
through the browser's normal download. Record the choice in the generator so A2's refusal is satisfied for this
item. `AllowedDomainsForApps` (8.2) is still open; the generator keeps refusing on it until Arnold decides, with
a `--undecided-domains-ok` switch for CI and the laptop demo only.

**9.3 "Working" means this demo passes on the team laptop, on Linux, recorded by Probe:**

1. Enrol the device; press Open on ChatGPT, Claude and Gemini: each opens in the workspace window, on the
   provider's official address, and the default browser's process list is unchanged.
2. Sign in by hand to one provider; close; Open again: still signed in (the folder persisted), no second profile.
3. Suspend the device in the console: within one heartbeat the workspace window closes and Open is refused with
   a plain message. Reactivate: Open works and the sign-in is still there.
4. Retire: the profile folder is gone.
5. With the prepared policy installed in a container only: the bypass cases of W6 pass.
Windows and macOS: the same steps as automated tests on CI runners; anything that cannot run is listed as
not proven, for Arnold to try on a real machine on 15 Nov.

**Device state does not exist yet.** Today a device can only have its keys revoked, sign out or expire idle;
there is no suspend, reactivate or retire for a device, so steps 3 and 4 need it built. W2 therefore starts with
its own migration PR (device workspace state and generation, append-only) before the contract-2 PR. On the client,
only an authenticated manifest or heartbeat answer that says `retired` or a higher `generation` may purge. A bare
401 or 403, a network failure or a server error closes the workspace and refuses Open, but never purges.

**9.4 Order and branches.** W2 (migration PR, then contract 2), then W3 with 9.1, then W4, W5, W6, W7. Each is its own PR **into the branch
`feature/managed-workspace`**, not into main, and may be merged into that branch on green so the pieces can be
tested together. One final PR from `feature/managed-workspace` into main stays open for Arnold's written approval
(hard limit 4 still holds for main). Probe tests on the integration branch.

**9.5 Server ready for 15 Nov.** No purchase by the team. By end of 14 Nov: `deploy/` setup script run end to end
on a fresh local VM or container of the target size (1 vCPU, 1 GB), with timings and memory use written down;
a single page `docs/SERVER-DAY.md` that Arnold follows on the 15th: rent, DNS, one command, Google sign-in
return address, provider keys, first owners, health check, how to point the apps at the new address, rollback.

**9.6 What is left for Arnold on 15 Nov** goes in `docs/ARNOLD-ONLY.md`, in the order he should do it, each with
the time it takes. Nothing else may be parked there: unfinished team work is not Arnold's.
