# Swangz AI Hub Access — browser extension

Some AI tools (ChatGPT, Midjourney, Canva, Runway, …) are used on their own websites and can't be
routed through the gateway. This company extension governs those sites: it opens the ones Swangz has
turned on for a person, shows a clear "not enabled" page for the rest, and keeps an access-level
record of use.

## Shared company accounts

Some tools are one account the whole team uses. The portal hands those out **a turn at a time**. This
extension enforces the other half: it lets only the person holding the turn onto the site, and it
**signs the browser out** of a shared tool when their turn ends, when an admin takes it back, and
again every time Chrome starts. It does that by clearing that site's cookies and stored data
(`chrome.browsingData.remove` for the tool's own domains — nothing else is touched).

So re-opening the tool always means going back through Swangz AI Hub, and the next person never inherits
someone else's session. It also means the vendor's credit history lines up with the turn log: whoever
held the account at the time spent what was spent.

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
- `GET /api/gate/turns` — which shared tools this person holds, and which to sign out of.
- `POST /api/gate/close` — end a usage record with the duration.
- `POST /api/tools/<id>/request` — the "Request access" button.

Admins see the log under **Tools → Website access** in the control room.

## Files

| File | Job |
|---|---|
| `manifest.json` | MV3 manifest, permissions |
| `background.js` | the service worker: host matching, the gate decision, open/close logging, shared-account sign-out |
| `popup.html` / `popup.js` | sign in, show status and the policy |
| `blocked.html` / `blocked.js` | the "not enabled for you" page, with Request access |
