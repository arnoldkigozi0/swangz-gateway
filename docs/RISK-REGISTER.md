# Blocker and risk register

Read at main `13966ba`, 21 Nov 2026. This page collects the open risks already written in the repository into one
list, without restating their detail. Each row names its source; the source holds the detail and wins if the two
disagree. No new risks are claimed without a source.

Sources: `docs/MANAGED-WORKSPACE.md` section 6 (R-1 to R-13), `docs/RELEASE-EVIDENCE.md` "Release-blocking items" and
the owner checklist (O-1 to O-7), `docs/SECURITY.md` "Limits", `docs/PROVIDER-COMPATIBILITY.md` section 7,
`docs/CATALOG-AUDIT.md`, and PRs #306 to #318. What only Arnold can do is listed once in `docs/ARNOLD-ONLY.md`
(the 21 Nov list); this page refers to it by item number.

**Owner** says who can close the row: **Arnold** (a purchase, account, device or decision), **Team** (code or docs),
or **Accepted** (a known limit by design, with the mitigation on offer).

## 1. Release blockers (a production claim needs every one of these)

| # | Blocker | Owner | State | Source |
|---|---|---|---|---|
| B-1 | Code signing: Windows Authenticode certificate, Apple Developer ID and notarization. Until then SmartScreen and Gatekeeper warn or refuse, and desktop auto-update stays off | Arnold | Not bought | RELEASE-EVIDENCE item 1, O-6; ARNOLD-ONLY 6 |
| B-2 | Physical acceptance on a real Windows PC and a real Mac, including a second OS user | Arnold | Not run | RELEASE-EVIDENCE item 2, O-1 to O-4; ARNOLD-ONLY 8 |
| B-3 | Production server, domain, Google OAuth redirect and company identity rules | Arnold | Not set up; code and `preflight` ready | RELEASE-EVIDENCE item 3, O-5; ARNOLD-ONLY 10, 11 |
| B-4 | Provider-seat inventory, and a real provider sign-in that persists in the company browser | Arnold | Not run; the team holds no credentials | RELEASE-EVIDENCE item 4, O-7; ARNOLD-ONLY 7 |
| B-5 | A real release version (`0.2.0`) built, upgraded to and refused on downgrade. The tree is still `0.1.0` | Team | Open | RELEASE-EVIDENCE item 5 |
| B-6 | Row 5 levels B and C: two installed apps at once, two real machines | Team, then Arnold for real machines | Open | RELEASE-EVIDENCE item 6 |
| B-7 | Windows real-token CSRF refusals (macOS has them since #299) | Team | Listed open in RELEASE-EVIDENCE; #302 (merged) made the Windows wrong-code step post a real CSRF token. Not re-read into that page yet | RELEASE-EVIDENCE item 7 |
| B-8 | macOS DMG reproducibility: explain the differing bytes, or document the `.app` as the reproducible unit | Team | Open | RELEASE-EVIDENCE item 8 |
| B-9 | Chrome's own enforcement of the managed policy pack on a company machine (Group Policy or MDM delivery) | Arnold (who administers the machines), then Team | Not installed anywhere | RELEASE-EVIDENCE item 9; ARNOLD-ONLY 12 |
| B-10 | The staff web app on a real Android phone and a real iPhone | Arnold | Mocked tests only | `docs/MOBILE-READINESS.md`; ARNOLD-ONLY 9 |
| B-11 | Extension id, update address and production host for the Chrome pack. Until filled, the pack blocks sites but installs no extension | Arnold | Placeholders | MANAGED-WORKSPACE R-7; `deploy/chrome-policy/README.md`; ARNOLD-ONLY 12 |

## 2. Device and managed-browser risks

| # | Risk | Owner | Mitigation on offer | Source |
|---|---|---|---|---|
| R-1 | A local administrator can remove or change machine policy | Accepted | Staff accounts without admin rights; tamper reported within a minute; `enforce` mode | MANAGED-WORKSPACE R-1 |
| R-2 | Policy stops new profiles in the UI only; another data directory or older profiles still work | Accepted | Machine policy and the forced extension still apply; other browsers need OS or MDM control | MANAGED-WORKSPACE R-2 |
| R-3 | The policy report is self-reported by the client | Accepted | Treated as a tamper signal, not proof | MANAGED-WORKSPACE R-3 |
| R-4 | Revoking in the Hub does not end a session at the provider | Accepted | Admin removes the seat or ends sessions in the provider's console | MANAGED-WORKSPACE R-4 |
| R-5 | URL lists do not control the network; other apps and browsers reach anything | Arnold (firewall or MDM decision) | Out of browser-policy scope | MANAGED-WORKSPACE R-5 |
| R-6 | Windows ACL checks and macOS managed preferences are unproven on real machines | Arnold (devices) | MANAGED-WORKSPACE section 7 | MANAGED-WORKSPACE R-6 |
| R-9 | On a personal device the workspace window checks only the start address; after that the person can go anywhere | Accepted | Company devices get the policy pack; personal devices keep the extension gate | MANAGED-WORKSPACE R-9 |
| R-10 | At Google's sign-in page a person can pick a personal Google account | Accepted | Provider-side seats and organisation controls stay authoritative; `AllowedDomainsForApps` is Arnold's decision | MANAGED-WORKSPACE R-10; ARNOLD-ONLY 12 |
| R-11 | If the app restarts while a workspace window is open, a later suspend cannot close that window | Team (later) | Suspend and revoke ask the person to close it | MANAGED-WORKSPACE R-11 |
| R-12 | After a revoke, the workspace folder and its provider sessions stay on disk | Team (later) | Removing it is the person's action | MANAGED-WORKSPACE R-12 |
| R-13 | `/go/` puts the company browser's Neko sign-in in a redirect address, so it lands in browser history | Team (after 20 Nov) | A single-use launch code replaces it | MANAGED-WORKSPACE R-13; D-022 |
| R-14 | The Swangz app's device key sits in an owner-only file, not yet the OS keychain | Accepted | "Disconnect this device" | SECURITY "Limits" |

R-8 (prompt bodies readable by admins) is closed by D-023 (#249): prompt and reply text are not kept by default, and
only the trust area may read them.

## 3. Server and data risks

| # | Risk | Owner | Mitigation on offer | Source |
|---|---|---|---|---|
| S-1 | Someone with a shell on the server can read provider keys and the database, and edit the audit log | Team | Ship the audit log off the box (not built) | SECURITY "Limits" |
| S-2 | Misconfigured `GATEWAY_TRUST_PROXY` lets a client spoof its address and so its "place" | Arnold (server set-up) | `preflight`; set it only behind the proxy | SECURITY "Limits" |
| S-3 | The production database's schema version is unknown; migrations are tested only on test databases | Arnold (cutover window) | Backup-first plan in `docs/HUB-DELIVERY.md` | ARNOLD-ONLY "Before the Hub can go live" |
| S-4 | Approximate places come from an offline table that can be wrong, stale or VPN-shifted | Accepted | Labelled *approximate*, never a fact | SECURITY "Limits" |

## 4. Provider, billing and catalogue risks

| # | Risk | Owner | Mitigation on offer | Source |
|---|---|---|---|---|
| P-1 | Mode A (one company key behind the gateway) is INFERENCE from vendor terms, not a vendor ruling | Arnold (ask the vendors in writing) | `docs/PROVIDER-SEAT-MATRIX.md` §4 | PROVIDER-COMPATIBILITY 7, decision 3 |
| P-2 | Mode E shared turns: most vendors' terms forbid one login for several people | Arnold (per tool) | Keep E off unless the vendor allows it | PROVIDER-COMPATIBILITY 7, safe path 4; PROVIDER-SEAT-MATRIX §4 |
| P-3 | Per-person cost is an estimate from gateway records; invoice import is not built | Accepted | Costs labelled *estimated* or *unpriced* | SECURITY "Limits"; PROVIDER-COMPATIBILITY 3 |
| P-4 | Vendor prices in `pricing.py` are a dated seed, not re-checked | Team | Re-check against vendor pricing pages | PROVIDER-COMPATIBILITY 3, finding 4 |
| P-5 | Higgsfield's allowlist `POST /*` is broad | Team, after a test credential | Narrow once real endpoints are confirmed | PROVIDER-COMPATIBILITY 3, finding 3 |
| P-6 | `openai.com` is DALL-E's gate host, so ChatGPT's sign-in host `auth.openai.com` is governed as DALL-E | Arnold (archive DALL-E or fold it into ChatGPT) | Pinned in tests until decided | CATALOG-AUDIT defect 3; ARNOLD-ONLY 4 |
| P-7 | `auth.openai.com` and `accounts.google.com` are not yet confirmed as the official sign-in hosts | Arnold | Tests prove consistency and safety only (#307, #313) | ARNOLD-ONLY 5 |
| P-8 | Seedance opens inside Higgsfield AI and is refused on its own | Arnold (archive or keep) | Refused by name on `/go/` and `/device/open` (#308, #312, #314) | ARNOLD-ONLY 1 |
| P-9 | Premiere owns `adobe.com`, so Adobe pages not listed elsewhere count as Premiere | Arnold | Photoshop moved to `photoshop.adobe.com` (#308, #310); Adobe ID sign-in hosts no longer governed as Premiere (#318) | ARNOLD-ONLY 2 |
| P-10 | Notion AI opens a product page; moving it to `notion.com` moves its gate host | Arnold | Unchanged until decided (#310) | ARNOLD-ONLY 3 |
| P-11 | Davinci Resolve and Topaz Video AI open their pricing pages (desktop apps with no web address) | Accepted (desktop only) | Pinned in `tests/test_catalog_checks.py` | CATALOG-AUDIT defect 5 |
| P-12 | No real provider has been tested (no LIVE row exists) | Arnold (capped test keys and accounts) | Fake upstream only | PROVIDER-COMPATIBILITY 1, 7 decision 4 |

## Keeping this page current

When a row closes, strike it with the PR or decision that closed it; do not delete it. New rows need a source.
