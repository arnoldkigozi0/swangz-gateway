# Chrome policy pack: bypass-test plan (D-016 item 5)

Owner: Probe (plan). Builder: Forge (`.github/workflows/chrome-policy.yml` and `tests/browser/chrome-policy.cjs`).
Status: **plan only. Nothing here has been run.** Where a browser behaviour is a prediction it says UNVERIFIED; the first CI
run decides it, and the result goes into the README, not into this plan.

Target: `deploy/chrome-policy/swangz-company-chrome.json` (D-015 level (a), company devices). The same case list
should later run against the Workspace Agent's own policy (`workspace_agent/agent.py` `POLICY`, level (c)) as a second
target, so keep the cases as data (`tests/browser/chrome-policy-cases.json`), not code.

## 1. Pack versus D-016, found while planning (fix or record before the tests can pass)

D-016 item 3 lists settings the pack does not contain. `tests/test_chrome_policy.py` pins the pack to exactly 13 names,
so it cannot notice.

| D-016 asks for | In the pack? | What to do |
|---|---|---|
| Block `chrome://*` | No: only `chrome://flags`, `chrome://inspect` (README explains the Chrome 147 change) | Add `chrome://*` as its own entry (needed from 147). Check it does not break the sign-in pages |
| Block `view-source:*` | No | Add, then test |
| `DownloadRestrictions=3` | No | **Product decision for Arnold**: it blocks every download, including generated media from Midjourney, ElevenLabs and others. Pick: block all, or leave open and say so |
| `AutoLaunchProtocolsFromOrigins=[]` and block external protocols | No | Add; test with the shim in case X-1 |
| Limit access to the local network | No | Not a URL-list job; see N-9 and the "cannot do" list. Do not claim it |
| `AllowedDomainsForApps` | No, by decision | Arnold's decision, with the owner-exception problem. Case G-2 makes it testable offline when decided |
| `BrowserSignin=0` conflict with D-015(b) option 1 | n/a on level (a) | Leave to Sentinel |

A case expected to ENFORCE for one of these items stays red until the pack is fixed. That is the point of the test.

## 2. Harness design (the parts that are easy to get wrong)

**Hermetic.** No real provider, no real DNS, nothing leaves the machine. Chrome runs with
`--host-resolver-rules="MAP * 127.0.0.1"` and `--ignore-certificate-errors`. One fixture server (plain Node `https` and
`http`, self-signed certificate from `openssl` in the workflow, no new dependency) listens on 443 and 80 and **logs every
request: Host, path, headers.** On Linux set `sudo sysctl net.ipv4.ip_unprivileged_port_start=0` first. If Chrome's
rules accept a port (`MAP * 127.0.0.1:8443`), use that instead (UNVERIFIED). Literal IP addresses are not affected by
the resolver rules, see N-9.

**Ground truth is the server's hit log, not the browser's error page.** A case is REFUSED only if the fixture saw **zero**
requests for that Host *and* the browser reported `net::ERR_BLOCKED_BY_ADMINISTRATOR` (from `goto` or the
`requestfailed` event). The error name matters: a lookalike that merely fails to resolve must not count as a pass.

**Every case runs twice.**
1. *Control, no policy file installed:* the request must reach the fixture. This proves the case can fail.
2. *Enforced, pack installed:* the case's expected result (below).

A pack that was never loaded (wrong directory, wrong Chrome flavour) shows up as "control and enforced both reached the
fixture" and fails the whole job loudly, before any case is reported. The job also deletes any old policy directory at
start and removes it again at the end (`if: always()`), so a stale file cannot give a false pass.

**Render, never edit, the pack.** The test copies the shipped JSON, replaces `SWANGZ_HUB_HOST` with `hub.swangz.test`,
and replaces the extension placeholders with a test id (tier 2) or drops the three extension-force entries (tier 1).
It asserts no other `SWANGZ_` placeholder is left.

**Two policies must be left out of the driven copy, and tested on their own.** `RemoteDebuggingAllowed=false` (UNVERIFIED,
but probably) stops Playwright from attaching, because Playwright drives Chrome over the same remote-debugging pipe.
`DeveloperToolsAvailability=2` hides DevTools. So:
- The driven suite uses the rendered pack minus those two names and prints that it did.
- Case P-1: full pack, launch with `--remote-debugging-port=9333`, wait 5 s, a TCP connect to 9333 must be refused.
- Case P-2: full pack, launch with `--auto-open-devtools-for-tabs` on a fixture page; the process must not expose a
  `devtools://` target. If that cannot be observed without CDP, mark P-2 "Not run: no way to observe" in the report
  and say so in the README, rather than skipping silently.

**The harness must refuse to run outside CI.** It writes to `/etc/...`, the Windows registry or `/Library/...`. Guard:
`if (process.env.GITHUB_ACTIONS !== 'true') { print "Not run: installs machine-wide policy, CI only"; exit 0 }`.
Nobody runs this on the team laptop.

**Output.** `/tmp/swangz-chrome-policy/results.json` and a Markdown table in the job summary: id, expected, observed, fixture
hits, Chrome version (`--version`), OS. Uploaded as a 7-day artifact. Secrets, headers beyond the ones named in the cases,
and page content are never written.

**Result classes.** `ENFORCE` (must be refused), `ALLOW` (must reach the fixture), `GAP` (the pack cannot or does not stop
it: run it, record what happened, and fail only if the README stops listing it or the observed result changes from the
README's). A GAP that turns out to be refused is good news and gets the README updated, not ignored.

## 3. Matrix

| Cell | Chrome | Policy location | Phase |
|---|---|---|---|
| ubuntu-latest, Playwright Chromium | bundled | `/etc/chromium/policies/managed/` (UNVERIFIED for Playwright's build; the control/enforced pair catches it) | 1 (build first) |
| ubuntu-latest, `channel: 'chrome'` | the runner's Google Chrome | `/etc/opt/chrome/policies/managed/` | 1 |
| windows-latest, Chrome | runner's Chrome | `HKLM\Software\Policies\Google\Chrome`, list policies as numbered subkeys `1`,`2`,… (this also proves or disproves the UNCONFIRMED note in the README) | 2 |
| macos-latest, Chrome | runner's Chrome | `/Library/Managed Preferences/com.google.Chrome.plist` (UNVERIFIED that Chrome honours it on an unmanaged runner) | 3, `continue-on-error: true`, shown as a visible warning, never hidden |

`fail-fast: false`. Record each cell's Chrome version in the artifact: behaviour changes at Chrome 147 (`*` and `chrome://`).
Windows and macOS are "supported" in the docs only after their cell passes; until then the README says "Linux only checked".
Trigger on `deploy/chrome-policy/**`, `tests/browser/chrome-policy*`, the workflow itself, and `workflow_dispatch`.
Heavy jobs run on Actions only.

## 4. Cases (fixture host names are synthetic; "allowed page" = `https://claude.ai/` served by the fixture)

### A. Approved access still works (ALLOW)
| Id | Case |
|---|---|
| A-1 | Hub host, `claude.ai`, `chatgpt.com`, `gemini.google.com`, `github.com/copilot` load |
| A-2 | Sign-in round trip: Hub page, redirect to `accounts.google.com`, redirect back to `hub.swangz.test/auth/google/callback?code=x`, cookie is set |
| A-3 | `login.microsoftonline.com`, `appleid.apple.com`, `github.com/login/oauth/authorize`, `www.google.com/recaptcha/api.js`, `challenges.cloudflare.com` load |
| A-4 | A subdomain of an allowed provider (`app.claude.ai`, `platform.openai.com`) loads |

### B. Navigation to hosts off the list (ENFORCE)
| Id | Case |
|---|---|
| B-1 | `https://evil.test/`, and the same over `http://` |
| B-2 | `mail.google.com`, `drive.google.com`, `myaccount.google.com`, `google.com`, `www.google.com/search?q=x` (what the omnibox sends), `youtube.com`, `gmail.com` |
| B-3 | `evil.accounts.google.com` (the leading-dot entry must match the exact host only) |
| B-4 | `github.com/` and `github.com/someuser/repo` (only `/login`, `/session`, `/sessions`, `/copilot` allowed) |
| B-5 | Omnibox typing of a bare word or a blocked host ends on the blocked page, not on a search result |
| B-6 | `--app=https://evil.test` and `--new-window https://evil.test` launch flags |

### C. Redirects, pop-ups, new tabs, frames, forms (ENFORCE unless marked)
| Id | Case |
|---|---|
| C-1 | Allowed page answers 302 to `https://evil.test/`; 307/308; a chain of three hops ending off-list |
| C-2 | Meta refresh, `location.href`, `location.replace` from an allowed page |
| C-3 | `window.open('https://evil.test')`; `<a target=_blank rel=noopener>`; middle-click and Ctrl+click; a pop-up that opens an allowed page and then redirects off-list |
| C-4 | `<iframe src="https://evil.test">` on an allowed page (README says "not tested": result is recorded, then pinned) |
| C-5 | `<form method=post action="https://evil.test">` submitted from an allowed page |
| C-6 | **GAP:** subresources from an allowed page (`<script>`, `<img>`, `fetch`, XHR, WebSocket to `evil.test`). Expected: not governed (README). Pin it |
| C-7 | **GAP:** an open redirector on an allowed host (`https://claude.ai/redirect?to=https://evil.test` where the fixture redirects) is refused at the second hop; a redirector that *stays* on an allowed host is not stoppable. Pin the first, document the second |

### D. Lookalikes and URL tricks (ENFORCE)
| Id | Case |
|---|---|
| D-1 | `claude.ai.evil.test`, `evil.test/claude.ai`, `evil.test/?u=claude.ai`, `claude-ai.test`, `claudeai.test`, `cIaude.ai` |
| D-2 | Punycode lookalike: `xn--` form of `clаude.ai` (Cyrillic a, built in the test with `url.domainToASCII`) and the Unicode form typed in the address bar |
| D-3 | Userinfo trick: `https://claude.ai@evil.test/` and `https://claude.ai:pw@evil.test/` (host is `evil.test`) |
| D-4 | Trailing dot `https://claude.ai./` and `chatgpt.com.`, upper case, a double slash path, `%2e` encodings. Prediction UNVERIFIED either way: record it. If the trailing-dot form is allowed it is a finding, not a pass |
| D-5 | Path-prefix over-match: `github.com/login-anything`, `github.com/copilot-anything`. Predicted allowed because path entries are prefixes (UNVERIFIED). Record; if allowed it is a low-severity GAP to list in the README |

### E. Direct addresses and special schemes (ENFORCE)
| Id | Case |
|---|---|
| E-1 | `http://127.0.0.1:PORT/` (fixture listens, so the hit log works), `http://[::1]:PORT/`, `http://localhost:PORT/`, `http://0.0.0.0:PORT/` |
| E-2 | Encoded loopback: `http://2130706433/`, `http://0x7f000001/`, `http://0177.0.0.1/`, `http://[::ffff:127.0.0.1]/` |
| E-3 | `data:text/html,<h1>x</h1>` typed, and clicked from an allowed page; `javascript:` typed; `about:srcdoc` |
| E-4 | `blob:` created by script on an allowed page and then navigated; `filesystem:`; `blob:https://claude.ai/<id>` is the dangerous one (inherits the allowed origin). Record the result for each |
| E-5 | `file:///etc/hostname` (Windows: `file:///C:/Windows/win.ini`) typed and clicked from an allowed page |
| E-6 | `view-source:https://claude.ai/` (D-016 wants it blocked; the pack does not list it yet) |
| E-7 | `chrome://settings`, `chrome://extensions`, `chrome://version`, `chrome://newtab`, `chrome://flags`, `chrome://inspect`, `chrome://policy`, `chrome-extension://<some id>/`, `devtools://devtools/` (Chrome 147 changes the result; fails until `chrome://*` is added) |
| E-8 | `ftp://`, `ws://evil.test` as a top-level navigation |
| E-9 | Local network and metadata: `http://169.254.169.254/`, `http://[fd00:ec2::254]/`, `http://10.0.0.1/`, `http://172.16.0.1/`, `http://192.168.1.1/`, `http://metadata.google.internal/`. These are IP literals or unresolved, so **no control run and no network call**: the pass condition is `ERR_BLOCKED_BY_ADMINISTRATOR` specifically, not a timeout. (The GitHub runner can reach a real metadata address, so never send the control request there.) |
| E-10 | **GAP:** an allowed host name that resolves to a private address (DNS rebinding). A URL list cannot see it. State it in the README, do not claim "local network limited" |

### F. Profiles, windows and launch flags
| Id | Case |
|---|---|
| F-1 | `--incognito`, Ctrl+Shift+N and `--guest` give no incognito or guest window. Observe with CDP `Target.getTargets` and compare `browserContextId` counts (UNVERIFIED that this works; if not observable say "Not run") |
| F-2 | A second profile: launch with a different `--user-data-dir` and with `--profile-directory="Profile 2"`; the blocked-host case is still refused there. `BrowserAddPersonEnabled=false` only hides the UI, so this is the real test that policy is machine-wide |
| F-3 | `--disable-extensions`: the allowed provider pages **still load**, which means the extension gate is off while the URL list is on. Expected GAP, matches README check 8; the README must say so |
| F-4 | `--kiosk`, `--disable-web-security`, `--proxy-server=...`, `--host-resolver-rules` given by a local user: policy still refuses `evil.test` (Linux only; these flags are the local-user attack, not the test's own) |

### G. Accounts
| Id | Case |
|---|---|
| G-1 | **GAP, pinned:** with the pack as is, a second (non-company) Google account can be typed on the fixture sign-in page. The fixture cannot tell real accounts apart, so the test only checks that `accounts.google.com` is reachable and says so |
| G-2 | Offline test for the decision that is Arnold's: Chrome adds `X-GoogApps-Allowed-Domains` to requests it sends to Google sign-in hosts when `AllowedDomainsForApps` is set. The fixture's hit log reads that header. Today: assert **absent** (pins that the decision is open). When enabled: assert the header equals the approved list. Note for the decision: the header names domains only, so allowing the two owner exceptions means allowing their whole mail domains, which defeats the restriction. Tell Arnold that before he chooses |
| G-3 | Sign-in to a provider with a personal Google account is the provider's own control (seats), not Chrome's. The README states it; no test |

### H. Chrome-managed settings (ENFORCE)
| Id | Case |
|---|---|
| H-1 | Password manager: the save prompt does not appear after a fixture form login (pref read: `PasswordManagerEnabled` policy shows as locked in the profile's preferences file after exit) |
| H-2 | `BrowserSignin=0`, `SyncDisabled`: the profile preferences show sync off and no sign-in entry point; do not drive the UI |
| H-3 | `DownloadRestrictions` : the fixture serves `Content-Disposition: attachment` from an allowed page. Fails until the pack has the policy and Arnold has decided (section 1) |
| H-4 | `chrome://policy` listing (when reachable) shows every one of the pack's names with status OK and none as unknown. Export through the page's own JSON export is not available headless, so read the rendered rows, or call it "Not run" |

### I. Extension (tier 2, time-box one shift, Playwright Chromium only)
Force-install of an off-store extension needs a signed CRX and an update manifest served by the fixture
(`chromium --pack-extension` makes the CRX: UNVERIFIED headless). Playwright's `--load-extension` is not accepted by
current branded Chrome (UNVERIFIED), so this tier does not run in the `channel: 'chrome'` cell.

| Id | Case |
|---|---|
| I-1 | The Swangz extension appears with `chrome.management` `installType: "admin"` and `mayDisable: false` |
| I-2 | Layering: with policy on and the extension installed, a tool the person has **no grant** for (allowed by the URL list) is still blocked by the extension, and a granted tool opens. Reuse the `extension-chrome.cjs` fixture |
| I-3 | An extension other than the Swangz one cannot be installed (`ExtensionInstallBlocklist=*`) |
| I-4 | An extension id mentioned in the README (`SWANGZ_EXTENSION_ID`) is not left as a placeholder when rendered for the test |

### X. External protocols (weak on purpose)
| Id | Case |
|---|---|
| X-1 | Put an `xdg-open` shim first on `PATH` that appends to a marker file. Click `mailto:`, `zoommtg:`, `ms-word:` links on an allowed page. Chrome normally shows a prompt that needs a click, so "no launch" proves little. Report both the prompt (if observable) and the marker, and label the case **weak**. It does not prove the pack blocks the protocols |

### P. Process-level (see section 2): P-1 remote debugging port closed, P-2 DevTools unavailable.

## 5. Pass bar for the verdict I will give
- Phase 1 cells green with every ENFORCE refused (zero fixture hits, error is `ERR_BLOCKED_BY_ADMINISTRATOR`), every ALLOW reached, every GAP matching the README, control runs all reached, Chrome versions recorded: **VERIFIED for that OS and version only.**
- Any ENFORCE case that reaches the fixture is a defect to Forge with the case id, and the README "What it cannot do" list is updated in the same PR.
- Windows and macOS stay "Not run" in the docs until their cell is green. No claim for them from the Linux result.
- Anything listed UNVERIFIED above is settled by the first CI run, and I will record the real behaviour in `docs/PROVIDER-COMPATIBILITY.md` with the Chrome version and date.

## 6. Suggested build order for Forge (small PRs, each mergeable alone)
1. Fixture server and the control/enforced engine, Linux Chromium cell, cases A, B, D only. Proves the pack loads at all.
2. Cases C, E, F, X, P; the README "checked" section filled with what actually happened.
3. Pack fixes from section 1 (after Arnold's call on downloads and `AllowedDomainsForApps`), then cases G, H.
4. Windows cell, then macOS cell (non-blocking), then tier 2 extension cases.
