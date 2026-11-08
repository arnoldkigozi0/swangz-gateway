# exact-signin — evidence (feature/exact-signin-v2)

Reference stills: `docs/design/references/stills/login-05.jpg` (Login) and `login-02.jpg` (Get access).
Files per app (`console` = /admin, `staff` = /): `<app>-login|access-<1440|390>-<dark|light>.png`.
`overlay-<app>-login|access-1440.png` = 50% blend of the still and our 1440×852 dark capture, card corner aligned
(the still is 1440×680 with the card at x175/y5; ours is centred in 852px, so the capture is shifted by 30/−101).
`beside-*` puts the still and ours side by side. Overlay captures have Google off (the reference has no Google button).

Measured against the stills (dark, 1440): card edge, seam, headings, fields and ghost pill within ±4px.

Remaining differences, each tagged with its BRIEF §10.1 number:
- 10.1.1 The brand mark and wordmark at top-left (Swangz "S"), and our words (Login, HELLO, FRIEND!, Work email / Console email).
- 10.1.2 Background is our `login-welcome.webp`, not their photo.
- 10.1.3 The alert row under the password is reserved (40px) so an error never moves the button: the button and the links row sit 11px lower than the still.
- 10.1.3 Contrast, focus ring (2px white), 44px hit targets on the eye and links, inert inactive pane, reduced-motion fallback; below 860px the card stacks (greeting under the form).
- 10.1.4 Mode B is "Get access" (the Hub has no self sign-up): a short note (staff: plus a Google link only when the server offers Google, no divider) instead of the three Create Account fields, so its title sits lower.
- 10.1.4 "Forgot Password?" is dropped (an admin resets passwords); "Don't have an account? Sign Up" reads "Get access".
- 10.1.4 The Google button and its "or" divider appear only when the server offers Google (exact href, never clicked by the tests).
- Light theme: the sign-in looks the same as dark by design (the reference has one look).

Checks: `node tests/browser/signin.cjs` (both apps; wrong/correct password, auth_error text and URL removal, Google on/off, eye, inert panes and Tab order, hit targets at both widths, CSP, one h1, reserved alert space, long error at 200% zoom, contrast, mocked valid and expired welcome).
