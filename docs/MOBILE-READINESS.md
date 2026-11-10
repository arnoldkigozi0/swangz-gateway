# Staff web app: install, update and sign-out readiness (G7)

Review of the staff web app as an installable app on phones and desktops: `gateway/static/hub.webmanifest`,
`hub-install.js`, `hub-worker.js`, how `gateway/server.py` serves them, and staff sign-out in `portal.js`.
Branch `feature/mobile-readiness` from `main` at `ba82a2a`, 2026-11-04.

## How it works

- **Install.** `hub.webmanifest` sets `id`, `name`, `start_url` and `scope` to `/`, with `display: standalone`
  and one SVG icon. `hub-install.js` registers `/hub-worker.js` (only in a secure context) and turns Chromium's
  `beforeinstallprompt` into an **Install app** button.
- **Update.** The worker has no `fetch` handler and uses no cache. Every page, script and API response comes
  from the network: static files are `no-cache`, and API responses are `no-store`. A new release reaches an
  installed app on its next load. Nothing private is stored offline.
- **Sign-out.** `POST /logout` deletes the session row and expires the cookie (`gateway/staff.py`).

## Fixed on this branch

1. **The install button never appeared.** It targeted `.login-card` / `.auth-card`, which no page has, and it
   tried to place the button only when the event fired. That is usually before the app has rendered.
   It now targets the staff sign-in form and the signed-in top bar (before the bell). It re-places itself
   whenever the app re-renders. It is removed after an install or `appinstalled`, and after a dismissal
   (Chromium offers the prompt again later). Its accessible name contains its visible label.
2. **Sign-out left the previous person's data in the page.** That data was unsaved report drafts, the
   catalogue and Studio. Staff sign-out now reloads `/` after the server ends the session. On a shared
   phone or an installed window, the next person starts from a clean page running the newest release.

Tests: `node tests/browser/pwa.cjs` (mocked DOM; 9 tests). Four of them fail against main's `hub-install.js`.

## Gaps, not fixed here

| Gap | Effect | Needs |
|---|---|---|
| No PNG icons (`apple-touch-icon` 180, manifest 192/512, maskable) | iOS uses a page screenshot as the home-screen icon. Android may show the SVG on a white circle | A PNG export of `icon.svg` from Arnold's artwork. There is no rasteriser in the stdlib, and adding one is a dependency decision |
| No install hint on iOS or Firefox | Those browsers have no `beforeinstallprompt`, so no button shows. Users need Share → Add to Home Screen | A small copy decision: where to show the hint, and whether to show it at all |
| The console (`/admin`) links the staff manifest | Installing from the console opens the staff app, not the console. The console shows no install button | A decision on whether the console should be installable (it would need its own manifest, `id` and `start_url`) |
| Console sign-out still re-renders in place | The same leftover-memory issue as fix 2, for console users | The same one-line change in `admin.js`, if wanted |
| An open installed window updates only when reloaded | Someone who leaves it open all day runs the old release until the next load | Acceptable for now; a "new version, reload" notice is possible later |

## Checks run, and where

- Mocked contract tests, run with Node 22 on the team laptop: worker registration, install placement and
  removal, the no-fetch/no-cache worker, the manifest fields and icon file, and sign-out ordering.
- Static review of the server headers and routes, done by reading the code.

## Real-phone checklist (five steps, about ten minutes per phone)

Do this once on an Android phone (Chrome) and once on an iPhone (Safari), on the Hub's real https address, with a
staff account that has at least one tool. Write down pass or fail for each step and the phone model and system version.

1. **Open and sign in.** Open the Hub address in the browser and sign in. Pass: Home appears, nothing is cut off at
   the sides, and the page does not scroll sideways.
2. **Install.** Android: tap **Install app** (or the browser menu, *Add to Home screen* / *Install app*). iPhone: tap
   Share, then *Add to Home Screen* (there is no Install button on iPhone). Pass: an AI Hub icon is on the home screen.
   Note what the icon looks like; a blank or screenshot icon is a known gap (no PNG icons yet).
3. **Open from the icon.** Close the browser and open the Hub from its icon. Pass: it opens full screen with no
   address bar. Note whether you are still signed in or had to sign in again (an iPhone may ask again).
4. **Use it.** Open Tools, open one tool with **Open**, come back, and open Weekly reports. Pass: the tool opens, the
   back gesture returns to the Hub, and text and buttons are readable and tappable with a thumb.
5. **Sign out and reopen.** Sign out from the avatar menu, close the app, open it from the icon again. Pass: it shows
   the sign-in page and nothing from the previous person. Then turn on aeroplane mode and open it: it should show the
   phone's own "no connection" page, not old Hub content (nothing is kept offline).

Not run by the team: no phone was available. `tests/test_pwa_files.py` checks only that the files a phone needs are
present and well-formed.

## Device checks

- Android Chrome, install from the sign-in page and from Home: **Not run.** No device or emulator here, and
  no headed browser on this laptop.
- iOS Safari, Add to Home Screen, standalone launch and sign-in: **Not run.** No iOS device.
- Desktop Chrome/Edge install and the installed window: **Not run.** No headed browser on this laptop.
- Update reaching an installed app after a release: **Not run.** It needs a real install.
- Sign-out in an installed app, then a second person signing in: **Not run.** It needs a real install.
  This is covered only by the mocked test.
- Lighthouse/installability audit: **Not run.** It needs a real browser; it could run on Actions with the
  pinned Playwright Chromium.
- Phone-width layout of the top bar with the button present: **Not run.** It needs a real browser; it
  belongs in the existing responsive matrix on Actions.
