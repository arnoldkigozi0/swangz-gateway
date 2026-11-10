# Real Chromium extension continuity check

The existing Actions browser job runs `xvfb-run -a node tests/browser/extension-chrome.cjs`
with the already-pinned Playwright and its bundled Chromium. No local browser installation
or new dependency is needed. Extension loading uses a persistent Chromium context as
specified in https://playwright.dev/docs/chrome-extensions.

The shipped `extension/` directory is loaded unpacked. Its Chrome APIs, service worker,
network requests and tab redirects are real. `tests/browser/demo.py` runs the isolated
Gateway plus fake upstream. Admin API calls configure synthetic `.test` hostnames and suspend/resume the fixture
person; the staff portal grants the shared-account turn. The extension signs in
through its own form and the real local `/api/extension/login` route. Site HTML is fulfilled
by Playwright at synthetic origins, so there is no vendor traffic or real account data.

The check proves an authenticated allow, a governed tab blocked after suspension/401,
real held-site cookie/localStorage removal, retained unrelated-site data, ungoverned
navigation while signed out, and governed blocking plus ungoverned navigation after
actually stopping the gateway. It reads safe extension state for assertions, but does
not replace Chrome APIs or call the worker's navigation/gate functions directly.

The browser job first runs `python -m unittest tests.test_extension -v` with Node required,
so the workflow log must show the test executed successfully rather than skipped.
That wrapper runs the separate dependency-free mocked regressions.

Results and blocked-page screenshots are written to `/tmp/swangz-hub-extension-chrome/`
and included in the existing seven-day browser artifact. The JSON result is the execution
record, including safe gate status/allow metadata and any failure. It excludes tokens,
passwords, request headers and site content. Run this check on Actions, not headed on the
team laptop. It verifies Chromium; Edge, managed installation and live vendor behavior
remain separate checks. No production service, credentials or signing keys are used.
