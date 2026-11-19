# OWNER ONLY - not done by the team

**Every item below is Arnold's to provide or decide.** The team does not buy, create, sign up for,
configure or hold any of it, and does not assume an approval or a credential that has not been given.
Until an item is provided, the release stays a release candidate (RC) for internal testing, never
production.

No secret goes in this file, in chat or in git. Where a value is secret (a key, a password, a
certificate), Arnold puts it straight where it is used (the server's `.env` with mode 600, or a GitHub
repository secret) and tells the team only that it is done.

Related: [RELEASE-EVIDENCE.md](RELEASE-EVIDENCE.md) rows O-1 to O-7 (where results are recorded),
[SERVER-DAY.md](SERVER-DAY.md) (the server-day runbook), [GO-LIVE-ASKS.md](GO-LIVE-ASKS.md) (where
each value goes), [MACOS-SIGNING.md](MACOS-SIGNING.md), [ARNOLD-ONLY.md](ARNOLD-ONLY.md),
[HUB-DELIVERY.md](HUB-DELIVERY.md).

## Status

| # | Item | Evidence row | Status |
|---|---|---|---|
| 1 | Production server address and approval | O-5 | Waiting on Arnold |
| 2 | Domain and DNS | O-5 | Waiting on Arnold |
| 3 | Google Cloud OAuth consent and redirect | O-5 | Waiting on Arnold |
| 4 | Company email and authorized identities | O-5 | Waiting on Arnold |
| 5 | Provider-seat inventory and authorization | O-7 | Waiting on Arnold |
| 6 | Windows and Mac physical-device acceptance | O-1 to O-4 | Waiting on Arnold |
| 7 | Application signing and deployment authorization | O-6 | Waiting on Arnold |

## 1. Production server address and approval

- **Arnold provides:** a rented server (Ubuntu 24.04, 1 vCPU, 1 GB RAM, 25 GB disk or more, public
  IPv4, SSH key login, firewall open for TCP 22/80/443 and UDP 443), paid for on his card; its
  address; and an explicit "yes, deploy commit X to it" for the commit Chief names.
- **Why:** the Hub must run on a first-party host that is always on. The laptop demo sleeps, moves
  networks and is not a production host. Spending money and deploying are Arnold's decisions only.
- **The team, once he has:** follows [SERVER-DAY.md](SERVER-DAY.md) sections 3-5 with whoever holds
  the login (one install command, preflight, first owner), runs the health and backup checks, and
  records the result in RELEASE-EVIDENCE O-5. The team never logs into the server without being given
  access for that session.

## 2. Domain and DNS

- **Arnold provides:** an A record `ai.swangzavenue.com` pointing at the server's IP, set in the
  swangzavenue.com DNS account (DNS only, not proxied, if the host is Cloudflare).
- **Why:** staff need one stable company address, and Caddy needs the name to reach the server to get
  its HTTPS certificate. Only the owner of the DNS account can change it.
- **The team, once he has:** checks the name resolves, confirms Caddy issued the certificate, sets
  `GATEWAY_PUBLIC_URL` / `GATEWAY_WEB_URL` to the new address, and checks both apps load over HTTPS
  ([SERVER-DAY.md](SERVER-DAY.md) section 2).

## 3. Google Cloud OAuth consent and redirect

- **Arnold provides:** in the Google Cloud console that owns the existing OAuth client: the redirect
  URI `https://ai.swangzavenue.com/auth/google/callback` added exactly (old addresses kept until the
  cutover is finished), the consent screen set for the company, and the client ID and secret placed in
  the server's `.env` himself.
- **Why:** "Continue with Google" only works for redirect addresses Google has been told about, and
  only the owner of the Google Cloud project can change it. The client secret must never pass through
  the team.
- **The team, once he has:** confirms `GATEWAY_REQUIRE_FIXED_RETURN=1` is set, runs `preflight` until
  it says `ok`, and tests sign-in for staff and admin on the new address
  ([SERVER-DAY.md](SERVER-DAY.md) section 6).

## 4. Company email and authorized identities

- **Arnold provides:** the work email addresses for the first owners and admins, confirmation of which
  staff accounts exist on the company domain, and any change to the identity rule. The only accepted
  accounts are company-domain addresses plus the two already-approved owner exceptions; nothing wider.
- **Why:** who may sign in is a security decision. The team cannot create company mailboxes and must
  not widen the allowed-account rule on its own.
- **The team, once he has:** adds the first owner with `add-admin`, checks that a non-company email is
  refused, and records the result in RELEASE-EVIDENCE O-5.

## 5. Provider-seat inventory and authorization

- **Arnold provides:** the list of AI subscriptions the company actually holds (provider, plan, seat
  count, who holds each seat, renewal date), which people are authorized for which provider, and,
  only for providers used through the gateway, the provider keys placed in the server's `.env`
  himself.
- **Why:** a tool is enabled only when the company subscription is active AND the person is assigned
  it. The team cannot know what Swangz pays for. Existing subscriptions stay as they are (no move to API
  billing), and the Hub never stores or fills in a provider password.
- **The team, once he has:** enters the tools, subscriptions and grants in the control room (or helps
  Arnold do so), checks that each person sees exactly their tools, and records the inventory check in
  RELEASE-EVIDENCE O-7.

## 6. Windows and Mac physical-device acceptance

- **Arnold provides:** a Windows 11 PC and a Mac (Apple silicon) that he controls, a real company
  account, and the time to run the steps himself (or with a team member watching):
  - **O-1 Windows:** install the unsigned installer (note the SmartScreen warning), sign in, open an
    AI site in the workspace, reboot, check it starts on login, uninstall.
  - **O-2 Mac:** open the DMG, note the first-open Gatekeeper behaviour (expected: blocked until
    signed) and the Keychain prompt, sign in, open the workspace, remove the app.
  - **O-3:** a second OS user on each machine cannot read the first user's profile folder or app data.
  - **O-4:** sleep, Wi-Fi off and on, and a VPN switch: the app reconnects with no new code.
  - Real phones (one Android, one iPhone) for the staff web app: [MOBILE-READINESS.md](MOBILE-READINESS.md).
- **Why:** CI runners and the laptop prove the code, not the experience on a real staff machine
  (installer warnings, Keychain, start on login, a second user, flaky networks). The team has no
  physical Windows PC or Mac.
- **The team, once he has:** turns every failure into a fix PR the same shift, then asks for a re-run
  of only the failed step, and records results in RELEASE-EVIDENCE O-1 to O-4.

## 7. Application signing and deployment authorization

- **Arnold provides:**
  - **Windows:** a code-signing certificate for Swangz Avenue (bought by the company).
  - **macOS:** Apple Developer Program membership as an organization (D-U-N-S number, a person with
    legal authority, yearly fee), a Developer ID Application certificate, notarization credentials,
    and confirmation of the bundle id `com.swangzavenue.swangz` (full list:
    [MACOS-SIGNING.md](MACOS-SIGNING.md)).
  - The certificates and credentials entered as GitHub repository secrets by Arnold himself (names in
    MACOS-SIGNING.md), never sent to the team.
  - A release signing key decision, and the explicit decision to turn desktop updates on.
  - The explicit authorization to publish a signed release and to deploy it.
- **Why:** signing proves the app comes from Swangz. Without it Windows warns "unknown publisher" and
  macOS Gatekeeper blocks the app. Buying certificates, holding signing keys and publishing a release
  are Arnold's decisions only.
- **The team, once he has:** turns on the signing and notarization steps in CI, builds signed
  installers, checks the signatures, asks for a physical-device re-run of O-1 and O-2 on the signed
  builds, and enables updates only after the app verifies signatures against a pinned release key.

## Signing and Gatekeeper note (applies until item 7 is done)

- **Installers stay UNSIGNED.** Every build is labelled "RC — UNSIGNED — INTERNAL TEST ONLY". None is
  production-ready, and none is published as a release.
- **macOS:** Gatekeeper blocks the unsigned app on first open. That is expected. The team does not
  tell staff to bypass it, and does not ship a workaround. Testers install an RC by hand from its DMG
  on Arnold's say-so.
- **Windows:** SmartScreen warns "unknown publisher". That is expected until the app is signed with the
  company's own certificate.
- **Desktop auto-update stays OFF.** The app reports "Updates unavailable: no pinned release key". It
  is turned on only after signed builds exist, the app verifies signatures, and Arnold decides to turn
  it on.
