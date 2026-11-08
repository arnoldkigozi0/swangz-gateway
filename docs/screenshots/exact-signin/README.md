# exact-signin — evidence (feature/exact-signin-v2)

Reference stills: `docs/design/references/stills/login-05.jpg` (Login) and `login-02.jpg` (Get access).
Files per app (`console` = /admin, `staff` = /): `<app>-login|access-<1440|390>-<dark|light>.png`.
`overlay-<app>-login|access-1440.png` = 50% blend of the still and our 1440×852 dark capture, card corner aligned
(the still is 1440×680 with the card at x175/y5; ours is centred in 852px, so the capture is shifted by 30/−101).
`beside-*` puts the still and ours side by side. Overlay captures have Google off (the reference has no Google button).

Measured against the stills (dark, 1440): card edge, seam, headings, fields and ghost pill within ±4px (text ink rows, Login left heading 185–217 vs 184–216; Get access left heading 221–249 and 275–303 vs 222–253 and 275–307).
Colours (mean of regions, ±16 per channel): left pane 6 and 4 off in Login; the card's top strip and the left pane in Get access sit 17–22 off because our glass is tinted by our own photo (10.1.2); page areas differ by the photo itself (10.1.2).

**The swap** follows `glass-login.mp4` (30fps; stills 48–60): the old words fade out in 4 frames (140ms), the glass is bare for frames 4–5, the new words fade in over frames 6–12 (190ms delay, 200ms), the two planes and the card settle over 570ms. The old and new words are never visible together. Reduced motion: everything instant. `signin.cjs` pauses the animations and reads opacity at each 1/30s frame, so the laptop's slow rendering cannot change the answer.

**Google arriving late.** The card stays invisible (`visibility:hidden`, which layout-shift scoring ignores) until the server's answer to `/auth/options` arrives or 1.2s passes, so the Google button and divider never push visible content. With `/auth/options` delayed 400ms: layout shift 0.000000 inside the card on both apps at 1440×852 and 390×844 and the Login button stays put. The only shift left is the brand wordmark's web-font swap outside the card (≤0.00005, measured on a raw run). The request and its handling are unchanged.

**The grey box on the Netlify Deploy Preview** (x330–1110, y804, 780×48) is not part of the product: it is an iframe Netlify injects into previews (`https://app.netlify.com/cdp/?deployID=…`). The repo has no iframe and no reference to that address, and the box is absent from the local demo captures here.

Remaining differences, each tagged with its BRIEF §10.1 number:
- 10.1.1 The brand mark and wordmark at top-left (Swangz "S"), and our words (Login, HELLO, FRIEND!, Work email / Console email).
- 10.1.2 Background is our `login-welcome.webp`, not their photo.
- 10.1.3 The alert row under the password is reserved (28px, a 30px gap in the still's spacing) so a one-line error moves nothing; a longer error wraps and grows the form, never clipped. Measured (dark, 1440, card-relative, Google off): email underline 286.5 vs 286, password underline 347.5 vs 347, button top 375.5 vs 374 and bottom 431.5 vs 432, links centre 475.5 vs 476 (all within ±4, asserted by `signin.cjs`).
- 10.1.3 Contrast, focus ring (2px white), 44px hit targets on the eye and links, inert inactive pane, reduced-motion fallback; below 860px the card stacks (greeting under the form).
- 10.1.4 Mode B is "Get access" (the Hub has no self sign-up): a short note (staff: plus a Google link only when the server offers Google, no divider) instead of the three Create Account fields, so its title sits lower (ink 228–252 against the still's 167–191) and its button sits 20px higher (427 against 447).
- 10.1.4 "Forgot Password?" is dropped (an admin resets passwords); "Don't have an account? Sign Up" reads "Get access".
- 10.1.4 The Google button and its "or" divider appear only when the server offers Google (exact href, never clicked by the tests).
- Light theme: the sign-in looks the same as dark by design (the reference has one look).

Checks: `node tests/browser/signin.cjs` (both apps; wrong/correct password, auth_error text and URL removal, Google on/off, eye, inert panes and Tab order, hit targets at both widths, CSP, one h1, reserved alert space, reference positions, the frame-by-frame swap, reduced motion, 400ms-late Google options (CLS), a long error growing at 200% zoom and on a phone without clipping, contrast, mocked valid and expired welcome).
