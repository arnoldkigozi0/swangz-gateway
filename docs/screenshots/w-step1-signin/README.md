# 9.3 step 1: Open and sign in, ChatGPT, Claude, Gemini (Probe, 13 Nov 2026, feature/managed-workspace 84a15d9)

Nothing was typed on any page: no email, no password, no code. Every flow stops at the provider's own sign-in form.

**Two parts, because I cannot drive the workspace window itself** (the app forbids remote debugging, and a desktop screenshot of it comes out black under Wayland):
1. `workspace-open-run.txt`: the real app (`open_app`) started the real Chrome 156 workspace window (`--user-data-dir=<folder> --no-first-run --no-default-browser-check`) for chatgpt, claude, gemini. History: `chatgpt.com`, `claude.ai` (redirected to `/login`), `gemini.google.com`. No default-browser call.
2. `signin-probe.cjs`: the same Chrome 156 binary, driven by Playwright with a throwaway profile, clicked the sign-in buttons. **No policy pack was installed** (installing machine policy on this laptop is out of bounds), so the pack was checked by `packmatch.py`, my emulation of Chrome's URL-filter format against `deploy/chrome-policy/swangz-company-chrome.json` `URLAllowlist`. It is not Chrome's own policy engine. `pack-allowlist-check.txt` is its output. The CI bypass harness (`tests/browser/chrome-policy.cjs`) is what enforces for real.

| Flow | Result | Screenshot | Pack allows every host seen? |
|---|---|---|---|
| ChatGPT Log in | modal: Google, Apple, phone, e-mail | chatgpt-login-modal.png | yes |
| ChatGPT Continue with Google | chatgpt.com -> auth.openai.com -> accounts.google.com sign-in page loads | chatgpt-google.png | yes (`openai.com`, `.accounts.google.com`, `.accounts.youtube.com`) |
| ChatGPT Continue with Apple | -> appleid.apple.com "Apple Account" page loads | chatgpt-apple.png | yes (`appleid.apple.com`) |
| ChatGPT Continue with Microsoft | **not offered**: the button exists in the page but is `display:none` for this visitor (Uganda, signed out), so it cannot be clicked | none | `login.microsoftonline.com` and `login.live.com` are on the list; which one ChatGPT uses is UNVERIFIED |
| Claude Continue with Google | opens a Google pop-up window: "Sign in to continue to Claude" | claude-google-popup.png | main hosts yes; **a frame to `newassets.hcaptcha.com` loaded and is NOT on the list** |
| Gemini Sign in | gemini.google.com -> accounts.google.com ServiceLogin -> sign-in page loads | gemini-signin.png | yes |

Not allowed by the pack, and not needed in anything I observed: `claude.com`, `sso.claude.com`, `platform.claude.com` (named in Anthropic's network docs for other sign-in routes; UNVERIFIED for claude.ai web sign-in).

## Demo note: ChatGPT "Continue with Microsoft" (final, 13 Nov 2026)

ChatGPT's Microsoft button was hidden for the visitor on the test run (`display:none`, signed out, Uganda), so it could not be clicked and no Microsoft sign-in page was reached. Whether the policy pack would allow it is therefore not tested. Per Chief's instruction of 13 Nov 2026 no further work is planned on it; for the demo, use Continue with Google. Apple was not offered either.
