# What only Arnold can do (10 November 2026)

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

## Decision: who may read what people type to the AI (R-8, finding F-18)

Checked read-only on `main` at `aab785a`, 12 November 2026. Nothing has been changed; the setting stays as it is
until Arnold chooses.

**What happens today.** Every request through the gateway stores the person's prompt (up to 4,000 characters) and
the AI's reply in the request record. The `store_bodies` setting (on by default) adds the full request and response
on top. Every console role, including `viewer`, can read that content on the Timeline, a person's page, the AI
requests list, a session, a single request's full record and the search box. Only the CSV export holds it back from
roles without the `trust` area. Turning `store_bodies` off does **not** stop this, because the prompt and reply are
kept anyway. With it off, the staff Privacy page says "Only a summary is kept — not the full contents of requests",
which is not true. It also contradicts plan v18 item 3 (admins see access and usage metadata only). Details:
`docs/SECURITY-REVIEW.md`, F-18.

| Option | What admins can read | What staff are told | Cost |
|---|---|---|---|
| **A. Leave as is** | Every console role reads prompts and replies | The Privacy page stays wrong when `store_bodies` is off | No build work. Disk keeps holding full bodies until the 90-day request retention removes each record with its bodies |
| **B. Turn `store_bodies` off only** | Unchanged: every role still reads the prompt and the reply | Still wrong | One setting change. Saves disk, does not fix F-18. Not recommended |
| **C. Keep storing, restrict reading** | Only Owner and Security admin (the `trust` area), and every read is recorded in the audit log with a reason. Other roles see who, which tool, model, tokens, cost, outcome and purpose label, with the content marked "withheld" | Corrected: says content is stored and who can read it | One backend PR (about a day) plus Sentinel review. No change in disk use |
| **D. Recommended: stop storing content by default, and restrict reading** | Nothing to read by default. If Arnold turns content capture on for a reason (an incident, an investigation), only Owner and Security admin read it, audited, as in C | Corrected and true: "your prompts and the AI's replies are not kept". If capture is switched on, the Privacy page says so | One backend PR (about a day) plus review. Disk use drops. What admins lose: reading a request's text when debugging a bad answer, and searching by prompt text. What stays: who, what, when, which device, cost, outcome, blocked secrets and the purpose label (worked out before the record is written, then the text is dropped) |

**What D keeps working.** Usage, spend and licence reports; the weekly reports; budgets and policies; Live and
cutting a request; the secret check (it reads the prompt in memory and blocks before anything is sent or stored);
the purpose label.

**Prompts already stored.** Whatever is chosen, the content already in the database stays until Arnold decides.
The choices are: let it age out under the normal 90-day request retention (recommended, deletes nothing early), or
blank it now after a verified backup (this deletes data, so it needs his explicit yes).

**Recommendation: D, and let existing content age out.** It is the only option that matches what staff are told
and plan v18 item 3, it narrows the risk if a console account is misused, and it fits the data-minimisation
principle of Uganda's Data Protection and Privacy Act. Option C is the fallback if Arnold wants prompts kept for
investigations.

**What Arnold does.** Reply with one letter (A, B, C or D) and "age out" or "blank now". The team builds it as one
reviewed PR; the default changes only after that reply.

## Optional

Off-server backup destination (14), email sending account (15), company-browser server and relay (16), and whether to keep the Netlify site after the move.

## Not asked for

Vendor passwords. The Hub never stores, shares or types a provider password.

## Not on this list

Unfinished team work is not Arnold's to do. The exact-match gaps, the footer scroll rate, the Chrome
policy bypass tests still to build and the pending reviews are listed in `docs/AGENT-PROGRESS.md` under 10 November
("Team work that is not finished") and stay with the team.
