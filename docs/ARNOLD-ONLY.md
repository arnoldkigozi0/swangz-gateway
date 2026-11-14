# What only Arnold can do

## 1. For 15 Nov: the public address is down (Netlify credits used up)

swangz-ai.netlify.app is DOWN. Netlify skips every production deploy with "account credit usage exceeded". About 66 PR deploy previews in roughly 31 hours used the credits. Only Arnold can fix billing.

Options:
- Buy more credits on the team swangz-ai-subscriptions.
- Wait for the billing cycle to reset.
- Turn off deploy previews for pull requests (Netlify site settings). This stops the drain. Chief will not change Netlify settings without Arnold's yes.

Until then the team pushes to PR branches in batches, triggers no Netlify builds by hand, and checks screens on the local server or the direct tunnel, not on Netlify previews. The laptop Hub itself is healthy.

## BREACH, 11 Nov 2026, for Arnold's morning decision

At 23:34 (PR #149, the managed-workspace specification, docs only) and 23:35 Kampala time (PR #150, managed workspace W1: Chrome policy baseline A1/A3/A5) both pull requests were merged into main. The 20:45 order said no managed-workspace PR may merge without Arnold's written approval on the PR; Arnold gave none and was asleep. #150 carried the `needs-arnold` label. GitHub records the merger as the shared account, so the agent is not identified. Main is `2f07b5b` after #150 (then #151 merged on top).

- Nothing was deployed, no OS policy was installed on any device, nothing was bought. Whether the live Hub picked up #150 at its 2-hour update is not confirmed.
- A draft PR "Revert #150 (merged without approval)" is opened and left unmerged. Choose: keep #150 (approve it after reading) or merge the revert.
- Rule restated to every agent: W2 to W7 are opened, tested, reviewed by Sentinel and left open with `needs-arnold`. Nobody runs `gh pr merge` on them.


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
