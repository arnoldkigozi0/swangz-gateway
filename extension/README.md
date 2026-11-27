# Swangz AI Hub Access — browser extension

Some AI tools (ChatGPT, Midjourney, Canva, Runway, …) are used on their own websites and can't be
routed through the gateway. This company extension governs those sites: it opens the ones Swangz has
turned on for a person, shows a clear "not enabled" page for the rest, and keeps an access-level
record of use.

Governed sites require an explicit allow response from the Hub. Signed out, revoked (`401`),
refused (`403`, including `person_paused`), offline, timed out or unable to read a valid
decision: a governed navigation goes to **Sign in to Swangz AI Hub**. Its sign-in button
opens the extension's own sign-in form, so connecting restores the extension token.
Ordinary entitlement/report refusals retain their existing explanation and actions.

The last governed-host list, Hub address and policy stay cached across sign-out and browser
worker restarts. A successful authenticated config refresh can replace that list; a failed
refresh cannot erase it. Other sites remain untouched. A fresh installation needs its first
successful config fetch to know the governed hosts. Checks time out after ten seconds,
including reading the response body. This uses Chrome's tab navigation redirect; it does
not intercept every network request before a page can start loading.

## Your sign-ins to the AI sites stay yours

Since 1.2.0 (27 November 2026) there are no turns on shared company accounts: everyone authorised
works at the same time. The extension **never signs the browser out of a site**. Sign-ins to the AI
tools persist across Chrome restarts, and nothing is ever closed because a turn expired. The extension
no longer has the `browsingData` permission, so it cannot clear any site's cookies or stored data.

On sign-out or any gate endpoint's `401`/`403`, the worker drops its own Hub token and nothing
else. Governed sites are blocked until the person signs in to the extension again; their sign-ins
to the sites themselves are untouched. The first time a 1.2.0 worker starts after an update, it
deletes the `holding` list and the per-minute `turns` alarm that 1.1.x kept; it uses neither.

Sign-out also tells the Hub: after the local token is removed, the worker sends one
`POST /api/logout` with the old token, and the Hub deletes that one extension session
(nothing else: not the person's web sessions, other browsers' extensions or devices).
This is best effort. Nothing waits for it, it gives up after 5 seconds, and if the Hub is
unreachable the extension is signed out all the same and the session ends at its own expiry.

## What it records, and what it doesn't

It records only: **which approved tool, who, when, and for how long.** It never reads page content,
form fields, or anything typed — there is no code that can, and the server has no column to store it.
This keeps it lawful under Uganda's Data Protection and Privacy Act, which expects staff to be told
their use is logged (the extension shows that in its sign-in and its policy panel) but does not permit
covert capture of their work.

An admin can turn on full-content logging (Settings → "Website gate: full-content logging"), which is
**off by default**; when on, staff are told so in the extension's policy. Leave it off unless legal
has signed off.

Only the hosts the gateway lists (the company's AI tools) are ever touched. Every other website is
ignored completely — the extension does nothing on them.

## How it works

1. A staff member installs the extension and signs in with their Swangz AI Hub address and account.
2. The extension fetches the list of governed AI hosts and the usage policy from the gateway.
3. When they open one of those sites, the extension asks the gateway whether that tool is enabled for
   them (the same "paid **and** assigned" rule as everything else). If yes, the site opens normally.
   If not, it shows a page explaining that, with a "Request access" button.
4. It records the open and, when they leave, how long the tab was open.

Authentication is a token the extension stores (same password as the app); it is sent as a bearer
header, so the extension works even though a session cookie can't be sent cross-site. Suspending a
person or pausing all AI invalidates the token immediately.

## Install (Chrome / Edge, developer mode)

1. Open `chrome://extensions`, turn on **Developer mode**.
2. **Load unpacked**, and choose this `extension/` folder.
3. Click the extension, enter the Swangz AI Hub address (e.g. `https://ai.swangz.com`) and sign in.

For a managed rollout, the same folder can be packed and pushed through Chrome Enterprise policy so
staff get it automatically and can't remove it.

## Endpoints it uses (all on the gateway)

- `POST /api/extension/login` — sign in, returns the token and the policy text.
- `GET /api/gate/config` — the governed host list and policy (needs the token).
- `POST /api/gate/open` — decide allow/block for a host, start a usage record.
- `POST /api/gate/close` — end a usage record with the duration.
- `POST /api/logout` — with the token: end this extension session at the Hub.
- `POST /api/tools/<id>/request` — the "Request access" button.

Admins see the log under **Tools → Website access** in the control room.

## Files

| File | Job |
|---|---|
| `manifest.json` | MV3 manifest, permissions |
| `background.js` | the service worker: host matching, the gate decision, open/close logging |
| `popup.html` / `popup.js` | sign in, show status and the policy |
| `blocked.html` / `blocked.js` | sign-in/unavailable blocking, or the entitlement/report refusal and actions |

## Verification

Dependency-free worker and blocked-page regressions:

```sh
node tests/browser/extension.cjs
python3 tests/browser/syntax.py
```

The JavaScript tests execute the shipped worker and page scripts with mocked Chrome APIs
and a minimal DOM; they do not use accounts, provider calls, ports or a browser installation.
`tests/test_extension.py` includes them in the standard Python CI suite when Node is available.
The coverage includes `401`/`403` on open/config/the popup status check, offline and timed-out
responses, preserved caches, ungoverned hosts/domain lookalikes, cold-worker navigation, late
replies after sign-out, the sign-in action and existing report actions. It also proves that
no site data is ever cleared: not at Chrome start (signed in, signed out or offline), not on
extension sign-out or a `401`/`403`, and not on any blocked answer (including an old
`no_turn`); that no `turns` alarm is scheduled and an old one is cleared; that a leftover
`holding` key is removed once and nothing else is; and that the manifest asks for no
`browsingData` permission. Request assertions limit recorded fields to host, access ID and duration.

`tests/browser/extension-chrome.cjs` runs the real unpacked extension in Chromium under
`xvfb-run` in CI: a `401` signs the extension out while the shared site's cookie and
localStorage survive, and closing and reopening Chrome on the same profile keeps the
shared site's sign-in cookie.

Local verification, 27 November 2026 (Node v22.22.1):

```text
1..51
# tests 51
# pass 51
# fail 0
# cancelled 0
# skipped 0
Checked 56 JavaScript files
```

The tests mock Chrome APIs and DOM rendering; real Chrome navigation runs in CI
(`extension-chrome.cjs`), and Edge still needs independent browser verification.
