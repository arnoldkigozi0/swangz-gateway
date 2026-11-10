# Go-live: what only Arnold can provide

The code can be made ready without these, but the Hub cannot go live until each required one exists. Nothing here has been bought, created or changed by the team. Values go into the server's environment file, never into Git or chat. The same list with the current state of each item is `docs/ARNOLD-ONLY.md`.

## Required

| # | What | Why it is needed | Where it goes |
|---|---|---|---|
| 1 | **A server (VPS) and its login** | The laptop only serves while it is awake and online. | `deploy/setup-gateway-server.sh` on that server |
| 2 | **A domain name and a DNS record** pointing at the server (for example `ai.swangzavenue.com`) | People need one permanent https address; Google sign-in needs a fixed one. | `GATEWAY_WEB_URL` and `GATEWAY_PUBLIC_URL` |
| 3 | **A Google OAuth web client** in the Swangz Google Cloud project, with the return address the check prints (`https://<domain>/auth/google/callback`) | "Continue with Google" for staff and admins. | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| 4 | **Provider API keys, one per provider Swangz actually uses through the gateway** (Anthropic, OpenAI, ElevenLabs, Higgsfield). None is needed for a provider nobody uses that way | Only tools that run through the gateway on the company key (API and developer tools, Studio) need one, and each key is billed by usage on top of any subscription. Website tools need no key. | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `HIGGSFIELD_CREDENTIALS` |
| 5 | **The list of vendor subscriptions and seats**: which plans Swangz pays for, how many seats, the renewal date, and which person holds each seat. Existing subscriptions stay as they are | A tool opens only when its subscription is marked active and the person is assigned. The Hub does not buy, renew or check a subscription with the vendor; it records what is entered. | Entered in the console (Tools, People, AI providers). No vendor passwords are stored |
| 6 | **Code-signing certificates**: a Windows publisher certificate and an Apple Developer ID with notarization | Unsigned installers show a warning, and desktop auto-update stays off until builds are signed. | `packaging/README.md` |
| 7 | **The first owners**: the names and work emails of the people who get the owner role | Someone must be able to sign in to the control room on the new server. | `python3 -m gateway add-admin` on the server |
| 8 | **Approval to move the production database** to the new server and upgrade it (schema v23 to v25 were added this month; the upgrade runs by itself on first start) | Migrations run on start-up and cannot be undone except from a backup. | `docs/HUB-DELIVERY.md` (backup, rehearsal, cutover) |
| 9 | **An Android phone for 30 minutes** | The installable staff app must be tried on a real device before release. | `docs/MOBILE-READINESS.md` |
| 10 | **An iPhone for 30 minutes** | Same; iPhone installs differently (Share, Add to Home Screen) and has no install button. | `docs/MOBILE-READINESS.md` |

## Required only for company computers (managed Chrome)

| # | What | Why it is needed | Where it goes |
|---|---|---|---|
| 11 | **A fixed extension id and update address**: an unlisted Chrome Web Store listing (needs a Chrome Web Store developer account, which has a registration fee) or a signing key and a hosted update file | Chrome cannot force-install an extension that has no fixed id. | `deploy/chrome-policy/` placeholders |
| 12 | **An administrator of each company computer** (or the device-management tool) to install the policy file, and staff accounts that are not administrators | The policy is installed by hand per computer and a local administrator can remove it. | `deploy/chrome-policy/README.md` |
| 13 | **A decision on `AllowedDomainsForApps`** (limit Google sign-in in company Chrome to `swangzavenue.com`) | It stops personal Google accounts, but also locks out the two approved owner exceptions on those computers. | `deploy/chrome-policy/` |

## Optional

| # | What | Why | Where it goes |
|---|---|---|---|
| 14 | **Backup destination**: a second machine or storage account reachable over SSH (rsync), with its address and key | Without it the nightly backup stays on the same server and is lost with the server. Recommended. | `GATEWAY_BACKUP_REMOTE` |
| 15 | **Email sending account**: SMTP host, port, user, password, a from-address, and who receives alerts | Emails high and critical notifications; without it they appear only in the console. | `GATEWAY_SMTP_*`, `GATEWAY_NOTIFY_TO` |
| 16 | **A server and video relay for company browsers** (shared accounts only) | Only if a shared company account is used with a company browser. | `deploy/WORKSPACE.md` |
| 17 | **A computer with a real graphics card for 10 minutes** | The 55 frames-per-second scrolling target could not be measured fairly on the team laptop. | `docs/ARNOLD-ONLY.md` |

Decisions only Arnold makes: the go-live date and cutover window, switching Google sign-in to the fixed address (item 3 plus `GATEWAY_REQUIRE_FIXED_RETURN=1`), whether to keep the Netlify site after the move, and approval of each purchase above (prices need current vendor quotations; none is quoted here).

Once items 1 to 3 exist, run `python3 -m gateway preflight` against the server's environment file (see `docs/HUB-DELIVERY.md`); it says exactly what is still missing without contacting anything.
