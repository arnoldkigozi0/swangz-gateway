# What only Arnold can do (10 November 2026)

## 21 November: the one list

As of main on 21 Nov 2026, everything left below is Arnold's: a decision, a purchase, an account, a real device or a real sign-in. The team has done the code side of each item and will not do the rest. The sections further down are the older detail; where they disagree, this list is newer.

| # | Item | What is ready | Arnold's exact step |
|---|---|---|---|
| 1 | **Seedance: archive it, or keep it as part of Higgsfield AI** | Seedance has no gate host since #306. `/go/seedance` and `/device/open` refuse it by name ("opens inside Higgsfield AI") since #308 and #312, and a Seedance-only grant never opens higgsfield.ai (#314) | Say "archive Seedance", or "keep it" (it stays refused on its own, so people need a Higgsfield AI grant) |
| 2 | **Adobe Premiere owning `adobe.com`** | Premiere's gate host is `adobe.com`, so every Adobe page not listed elsewhere counts as Premiere. Photoshop is on `photoshop.adobe.com` (#308, #310), and the Adobe ID sign-in hosts are no longer governed as Premiere (#318) | Confirm Premiere keeps `adobe.com`, or name the host it should have instead (Premiere is a desktop app, so it has no web address) |
| 3 | **Notion AI address** | Open goes to `www.notion.so/product/ai`, a product page. Notion's help names `www.notion.com`, but the gate host is `notion.so`, and changing it moves the gate (#310) | Say whether Notion AI should move to `notion.com` (the gate host moves with it), or stay as it is |
| 4 | **DALL-E** | DALL-E is retired in ChatGPT, and image generation is at `chatgpt.com/images` on ChatGPT's gate. DALL-E's gate host `openai.com` also covers `auth.openai.com`, ChatGPT's sign-in host (audit defect 3, #310) | Say "archive DALL-E" or "fold it into ChatGPT". Either one lets the team move `openai.com` off DALL-E |
| 5 | **Official sign-in hosts** | `auth.openai.com` (ChatGPT) and `accounts.google.com` are listed as sign-in hosts. Tests show the lists are consistent and safe (#307, #313), but nobody has checked them against the providers' own documentation. The Adobe ID hosts were observed in a real browser (#311, #315) | Confirm from OpenAI's and Google's documentation (or a real sign-in, item 7) that these are the hosts, or tell the team which to use |
| 6 | **Code-signing certificates** | CI builds unsigned installers. Desktop auto-update is off (`swangz_client/release_keys.py`, `ENABLED = False`) until builds are signed and you approve the release keys. macOS steps: `docs/MACOS-SIGNING.md` | Buy the Windows code-signing certificate and an Apple Developer ID, then approve the release keys |
| 7 | **Real provider logins** | Sign-ins inside the Swangz workspace window were tested only up to the provider's page, without an account. The team holds no provider credentials and will not | In the workspace window, sign in to one provider yourself, close the window, reopen it and check you are still signed in (`docs/MANAGED-WORKSPACE.md` 9.3 step 2). For Adobe, a test Adobe or Google account is needed (#315) |
| 8 | **Real-device checks: Windows and macOS** | CI builds the installers, and the device enrolment journeys pass on CI runners. Neither has been installed on a real staff computer | On one Windows PC and one Mac: install the RC, connect it at `/device` with your own account, open one tool, then disconnect it in the console and check the tool is removed |
| 9 | **Real-device checks: Android and iPhone** | Mocked tests only; the staff web app has never been installed on a real phone | Follow the five steps in `docs/MOBILE-READINESS.md` on an Android phone and an iPhone, or lend the phones |
| 10 | ~~**Server (VPS) and domain**~~ **Done (Arnold, reported 21 Nov)** | The address is `https://hub.ictconnect.org/` since 25 Nov (the web address; the staff email domain stays `swangzavenue.com`). The team has read its public health page and has not logged in to the server | Install, check and point the apps at it in order: `docs/OWNER-RUNBOOK.md` |
| 11 | **Google sign-in client** | The return address follows `GATEWAY_WEB_URL`. `GATEWAY_REQUIRE_FIXED_RETURN=1` refuses Google sign-in unless the address is fixed | Create the Google web client with the redirect URI `https://hub.ictconnect.org/auth/google/callback` (the one `preflight` prints), and set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` on the server (`docs/OWNER-RUNBOOK.md` step 7) |
| 12 | **Managed Chrome: the rest after the policy pack** | The pack and its README are in `deploy/chrome-policy/`, and `prepare.py` fills the placeholders. It has not been installed on any company computer. Until the extension id is filled in, it blocks sites but installs no extension | (a) Fill the three placeholders with `prepare.py`: `SWANGZ_HUB_HOST` (`51-21-160-193.sslip.io`, item 10), `SWANGZ_EXTENSION_ID` and `SWANGZ_EXTENSION_UPDATE_URL` (approve a Chrome Web Store developer account for an unlisted listing, or a self-hosted update file). (b) Name who installs it on company computers. (c) Decide groups G and H: downloads, and `AllowedDomainsForApps`, which blocks personal Google accounts, and with them the two approved owner exceptions, on company computers |

The rest is the team's, not Arnold's: open reviews, CI and test gaps are in `docs/AGENT-PROGRESS.md`.

## Saturday 15 November: Arnold's order of the day (Kampala time)

Detail for each server step is in `docs/SERVER-DAY.md`. Times are a suggestion; the team does none of this.

| Time | What | Where |
|---|---|---|
| 08:00 | Read the handover (`docs/HANDOVER-14NOV.md`) and decide the items in "Decisions waiting" below. Most of the rest depends on them | this file |
| 08:30 | Decide the managed workspace: the five owner decisions and the final PR #204 (written approval needed before anyone merges it) | `docs/MANAGED-WORKSPACE.md` section 8, PR #204 |
| 09:00 | Confirm or overrule D-022: shared company accounts stay in the staff web app and the extension, not the Swangz workspace window | `docs/DECISIONS.md` D-022, PR #201 |
| 09:15 | Managed workspace step 2 by hand: in the Swangz workspace window sign in to ONE provider yourself, close the window, reopen it and check you are still signed in. The team may not hold credentials, so only you can prove this | `docs/MANAGED-WORKSPACE.md` 9.3 step 2 |
| 09:30 | Get the server details together: login, domain, Google client, provider keys | SERVER-DAY section 0 |
| 10:00 | Rent the server | SERVER-DAY section 1 |
| 10:15 | Point the name at it, then wait for DNS | SERVER-DAY section 2 |
| 11:00 | Run the one command | SERVER-DAY section 3 |
| 11:20 | Health check | SERVER-DAY section 4 |
| 11:30 | Add the first owners | SERVER-DAY section 5 |
| 11:45 | Google sign-in on the fixed address, with `GATEWAY_REQUIRE_FIXED_RETURN=1` | SERVER-DAY section 6 |
| 12:15 | Provider keys | SERVER-DAY section 7 |
| 12:30 | Backups | SERVER-DAY section 8 |
| 13:00 | Point the apps at the new address | SERVER-DAY section 9 |
| 13:30 | Decide whether to carry the data over or start fresh | SERVER-DAY section 10 |
| Afternoon | Real-phone checks (five steps in `docs/MOBILE-READINESS.md`), the scroll check on a normal office computer, and the signing-certificate purchase | below |

Rollback is SERVER-DAY section 11.

## Decisions waiting on Arnold, first (12 Nov 2026)

1. **#150 (managed workspace W1): approved after the fact by Arnold, 12 Nov.** #149 (spec, docs) merged 23:34 and #150 23:35 Kampala time on 11 Nov without prior approval (the merger is not identifiable; shared account). Nothing was deployed, no OS policy installed, nothing bought. Arnold's decision: keep #150. The revert, draft #156, is closed unmerged and is not to be reopened. This approval covers #150 only; W2 to W7 and #160 stay open until Arnold approves each in writing.
2. **R-8, who may read prompts and replies (F-18): decided.** The sprint brief of 17 Nov chose #160's option D, recorded as D-023 in `docs/DECISIONS.md` and built in #249: prompt and reply text are not stored by default, and only the trust area can read them. #160 is closed because D-023 replaces it.
3. **The five owner decisions** in `docs/MANAGED-WORKSPACE.md` section 8. W2 to W7 PRs stay open with `needs-arnold`.
4. **D-022 (shared company accounts).** The Swangz app keeps refusing shared company accounts for the 20 Nov release; turns stay in the staff web app (`/go/`) and the extension. This changes what staff experience, so confirm or overrule it on the 15th. Known risk R-10: the web app's Open puts the turn's company-browser sign-in in a redirect address, so it lands in browser history.
5. **The liquid footer (S4).** It makes every staff page scroll at 1440x852. Keep it everywhere, or only on Home and sign-in with a compact bottom row elsewhere (BRIEF section 15 would narrow).
6. **Chrome policy pack, groups G and H.** Downloads, and limiting Google sign-in to company accounts. Both wait on you.
7. **Commit trailers.** About 14 commits on main since 11 Nov 21:00 carry a Co-Authored-By trailer, against the standing rule. Main history was not rewritten; removing them needs Arnold.

Everything below is waiting on Arnold: a purchase, an account, a decision or a device. The team has not bought, created or changed any of it. Item numbers are those in `docs/GO-LIVE-ASKS.md`, which says where each value goes.

## Before the Hub can go live on its own address

| Ask | State of the code | What Arnold does |
|---|---|---|
| Server and login (1) | Setup script, service files, health check and backup timers are in `deploy/`. Not run on any server | Rent the server; give the login to whoever deploys |
| Domain and DNS (2) | `preflight` checks the address offline | Choose the name; add the DNS record |
| Google sign-in on the fixed address (3) | **Code shipped.** The return address follows `GATEWAY_WEB_URL`. `GATEWAY_REQUIRE_FIXED_RETURN=1` refuses Google sign-in unless the address is fixed; it is off by default so the laptop demo keeps working (lands with PR #93) | Create the web client with the return address `preflight` prints; say when to switch the setting on |
| Provider API keys (4) | Read from the environment only; never stored or logged | Create one key per provider actually used through the gateway |
| Subscriptions and seats (5) | Console pages exist; nothing is entered for production | Supply the list: plan, seats, renewal date, holder |
| First owners (7) | `add-admin` command | Name them |
| Production database move and upgrade (8) | Migrations v23 to v25 (device enrolment, provider-account registry and its repair) run on start-up. They are tested on test databases in the suite, never on production data, and the team does not know which version the production copy is at | Approve the cutover window and the backup-first plan in `docs/HUB-DELIVERY.md` |
| Go-live date and cutover window | | Decide |

## Before the apps are released to staff

| Ask | State of the code | What Arnold does |
|---|---|---|
| Code-signing certificates (6) | Unsigned installers are built by CI. **Desktop auto-update is off (`swangz_client/release_keys.py`: no release keys, `ENABLED = False`) and stays off until builds are signed and Arnold approves the release keys** | Buy the Windows certificate and the Apple Developer ID |
| Android phone and iPhone (9, 10) | Mocked tests only; never installed on a real phone | Follow the five steps in `docs/MOBILE-READINESS.md` on each, or lend the phones |
| Scrolling smoothness on a real graphics card (17) | The 55 frames-per-second target was measured at 28 to 34 on the loaded team laptop with no graphics card, which is not a fair test | Open Tools in the staff app on a normal office computer and scroll; say if it stutters |

## Before company computers are locked down

| Ask | State of the code | What Arnold does |
|---|---|---|
| Extension id and update address (11) | The policy file has placeholders; until they are filled it blocks sites but installs no extension | Approve a Chrome Web Store developer account (unlisted listing), or a self-hosted update file |
| Installing the policy (12) | File and instructions in `deploy/chrome-policy/`. Not installed or tested on any computer | Name who administers the company computers |
| `AllowedDomainsForApps` (13) | Left out on purpose | Decide: adding it blocks personal Google accounts and the two approved owner exceptions on company computers |

## Optional

Off-server backup destination (14), email sending account (15), company-browser server and relay (16), and whether to keep the Netlify site after the move.

## Not asked for

Vendor passwords. The Hub never stores, shares or types a provider password.

## Not on this list

Unfinished team work is not Arnold's to do. The exact-match gaps, the footer scroll rate, the Chrome
policy bypass tests still to build and the pending reviews are listed in `docs/AGENT-PROGRESS.md` under 10 November
("Team work that is not finished") and stay with the team.
