/* Sign-in checks for the split gate (SUI.splitGate): the console sign-in (/admin) and, once ported, the staff sign-in (/).
   NODE_PATH must reach a tooling dir with playwright (never installed in the repo). Starts tests/browser/demo.py (test database).
   Covers the Sentinel G2 list: wrong and correct password, the fixed auth_error text and its removal from the URL, the Google link
   (exact href, on and off, never clicked), the password eye (name, state, autocomplete, reset), inert inactive panes and tab order,
   hit targets at both widths, no CSP violation, one visible h1, reserved alert space, a long error at 200% zoom, contrast, and the
   welcome screens (valid and expired link, mocked). SHOTS=<dir> also saves screenshots. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const results = { checks: [], contrast: [], errors: [], csp: [] };
const ok = (label, v) => { assert.ok(v, label); results.checks.push(label); };
const eq = (label, a, b) => { assert.deepEqual(a, b, label + ': ' + JSON.stringify(a) + ' !== ' + JSON.stringify(b)); results.checks.push(label); };
const SHOTS = process.env.SHOTS;
const staffPorted = /splitGate/.test(fs.readFileSync(path.join(root, 'gateway/static/portal.js'), 'utf8'));

const APPS = {
  admin: { name: 'console', start: '/admin', loginApi: '**/admin/api/login', user: 'owner@swangzavenue.com', pass: 'owner-password', wrong: 'definitely-wrong-password',
    googleHref: '/auth/google/start?app=admin', after: 'main h1:not(.xgate h1)',
    errors: { cancelled: 'Google sign-in was cancelled.', expired: 'That sign-in took too long or was started in another browser. Try again.',
      google: "Google couldn't confirm that account. Try again.", off: "Google sign-in isn't set up yet.",
      no_account: "That Google account isn't a console user. An owner can add it under Settings → Console users (use the Google email as the username)." } },
  staff: { name: 'staff', start: '/', loginApi: '**/api/login', user: 'grace@swangzavenue.com', pass: 'demo-password', wrong: 'definitely-wrong-password',
    googleHref: '/auth/google/start?app=staff', after: 'main h1:not(.xgate h1)',
    errors: { cancelled: 'Google sign-in was cancelled.', expired: 'That sign-in took too long or was started in another browser. Try again.',
      google: "Google couldn't confirm that account. Try again.", not_allowed: 'Only Swangz work accounts can sign in here.',
      no_account: "That Google account isn't set up in Swangz AI Hub yet. Ask your admin to add your email.", paused: 'Your access is paused. Talk to your admin.',
      off: "Google sign-in isn't set up yet. Use your email and password." } },
};
const VIEWS = [[1440, 852, 'desktop'], [390, 844, 'mobile']];

/* Worst contrast of an element's text against the pixels actually painted behind it (see lists.cjs). */
async function contrastOf(page, sel, label, min) {
  const box = await page.evaluate((sel) => {
    const e = document.querySelector(sel); if (!e) return null;
    let r = e.getBoundingClientRect();
    const g = document.createRange(); g.selectNodeContents(e); const q = g.getBoundingClientRect(); if (q.width && q.height) r = q;
    const color = getComputedStyle(e).color;
    const hidden = []; const hide = (n) => { hidden.push([n, n.style.color]); n.style.setProperty('transition', 'none', 'important'); n.style.setProperty('color', 'transparent', 'important'); };
    hide(e); e.querySelectorAll('*').forEach(hide);
    window.__restore = () => hidden.forEach(([n, c]) => { n.style.removeProperty('color'); n.style.removeProperty('transition'); if (c) n.style.color = c; });
    return { x: r.x, y: r.y, w: r.width, h: r.height, color };
  }, sel);
  assert.ok(box, 'missing ' + sel);
  const png = await page.screenshot({ clip: { x: box.x, y: box.y, width: Math.max(2, box.w), height: Math.max(2, box.h) } });
  await page.evaluate(() => window.__restore());
  const worst = await page.evaluate(async ({ b64, color }) => {
    const bmp = await createImageBitmap(new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: 'image/png' }));
    const cv = new OffscreenCanvas(bmp.width, bmp.height); const cx = cv.getContext('2d'); cx.drawImage(bmp, 0, 0);
    const d = cx.getImageData(0, 0, bmp.width, bmp.height).data;
    const lum = (r, g, b) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
    const m = color.match(/[\d.]+/g).map(Number); const t = lum(m[0], m[1], m[2]);
    let lo = 9, hi = -1;
    for (let i = 0; i < d.length; i += 4) { const l = lum(d[i], d[i + 1], d[i + 2]); if (l < lo) lo = l; if (l > hi) hi = l; }
    const c = (a, b) => (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    return Math.min(c(t, lo), c(t, hi));
  }, { b64: png.toString('base64'), color: box.color });
  results.contrast.push({ label, ratio: +worst.toFixed(2), min });
  ok(`${label}: contrast ${worst.toFixed(2)} >= ${min}`, worst >= min);
}

async function newPage(browser, info, app, w, h, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: w < 600 });
  await ctx.addInitScript(() => {
    try { localStorage.setItem('swangz-theme', 'dark'); localStorage.setItem('theme', 'dark'); } catch (e) { /* private mode */ }
    window.__csp = []; document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => results.errors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && !/401|Failed to load resource/.test(m.text()) && results.errors.push(m.text()));
  await page.route('**/auth/options', (r) => r.fulfill({ json: { google: !!o.google } }));
  await page.goto(info.url + app.start + (o.query || ''));
  await page.waitForSelector('.xgate .xgate-card');
  return { ctx, page };
}

const box = (page, sel) => page.locator(sel).first().boundingBox();
const tabbed = async (page, n) => {
  const seen = [];
  for (let i = 0; i < n; i++) {
    await page.keyboard.press('Tab');
    seen.push(await page.evaluate(() => { const a = document.activeElement; if (!a || a === document.body) return null; const p = a.closest('.xg-form-a, .xg-form-b, .xg-hello-a, .xg-hello-b'); return { tag: a.tagName, part: p ? [...p.classList].find((c) => /^xg-(form|hello)-[ab]$/.test(c)) : 'outside' }; }));
  }
  return seen;
};

async function gateChecks(browser, info, key, app) {
  const T = (s) => `${app.name}: ${s}`;
  for (const [w, h, vname] of VIEWS) {
    const V = (s) => `${app.name} ${vname}: ${s}`;
    const { ctx, page } = await newPage(browser, info, app, w, h, { google: true });
    const part = (m) => `.xgate .xg-form-${m}`;

    // structure: one visible h1, both modes
    eq(V('exactly one h1 in mode A'), await page.locator('h1').count(), 1);
    ok(V('the h1 is visible and is the form title'), await page.locator('h1').first().isVisible());
    eq(V('mode A title'), (await page.locator('h1').first().innerText()).trim().toLowerCase(), 'login');
    ok(V('the eye is not inside a label'), (await page.locator('.xg-eye').count()) > 0 && (await page.locator('.xg-eye').evaluateAll((l) => l.every((b) => !b.closest('label')))));
    eq(V('email field autocomplete'), await page.locator(`${part('a')} input[type=email]`).getAttribute('autocomplete'), key === 'admin' ? 'username' : 'email');
    eq(V('password field autocomplete'), await page.locator(`${part('a')} input[autocomplete=current-password]`).count(), 1);
    ok(V('both fields have an accessible label'), await page.locator(`${part('a')} .xfield`).evaluateAll((fs) => fs.every((f) => { const i = f.querySelector('input'); return i.labels && i.labels.length === 1 && i.labels[0].textContent.trim().length > 0; })));

    // focus: the email field is focused straight away, and there is no timer
    ok(V('email field has focus on load'), await page.evaluate(() => document.activeElement && document.activeElement.type === 'email'));

    // Google link: exact href, mode A only, never clicked
    const g = page.locator(`${part('a')} a[href*="/auth/google/"]`);
    eq(V('Google link count in mode A'), await g.count(), 1);
    eq(V('Google link exact href'), await g.getAttribute('href'), app.googleHref);
    eq(V('no divider or Google link in mode B before it is shown'), await page.locator(`${part('b')} .or`).count(), 0);

    // eye
    const pw = page.locator(`${part('a')} input[autocomplete=current-password]`);
    const eye = page.locator(`${part('a')} .xg-eye`);
    eq(V('eye name'), await eye.getAttribute('aria-label'), 'Show password');
    eq(V('eye starts unpressed'), await eye.getAttribute('aria-pressed'), 'false');
    await pw.fill(app.wrong);
    await eye.click();
    eq(V('eye reveals'), await pw.getAttribute('type'), 'text');
    eq(V('eye pressed'), await eye.getAttribute('aria-pressed'), 'true');
    eq(V('eye name while revealed'), await eye.getAttribute('aria-label'), 'Hide password');
    await eye.click();
    eq(V('eye hides again'), await pw.getAttribute('type'), 'password');

    // hit targets
    const hits = { eye: await box(page, `${part('a')} .xg-eye`), link: await box(page, `${part('a')} .xg-link`), primary: await box(page, `${part('a')} .xg-primary`),
      google: await box(page, `${part('a')} a[href*="/auth/google/"]`), hello: await box(page, '.xgate .xg-hello-a .xg-ghost') };
    ['eye', 'link'].forEach((k) => ok(V(`${k} hit target >= 44px (${Math.round(hits[k].width)}x${Math.round(hits[k].height)})`), hits[k].width >= 44 && hits[k].height >= 44));
    ['primary', 'google'].forEach((k) => ok(V(`${k} button >= 52px tall (${Math.round(hits[k].height)})`), hits[k].height >= 52));
    ok(V('hello button >= 44px tall'), hits.hello && hits.hello.height >= 44);

    // inactive pane: inert, hidden from assistive tech, and never reached by Tab
    eq(V('mode B form is inert'), await page.locator(part('b')).evaluate((n) => [n.inert, n.getAttribute('aria-hidden')]), [true, 'true']);
    eq(V('mode B hello is inert'), await page.locator('.xgate .xg-hello-b').evaluate((n) => [n.inert, n.getAttribute('aria-hidden')]), [true, 'true']);
    let seen = await tabbed(page, 14);
    ok(V('Tab never lands in mode B'), seen.every((s) => !s || !/-b$/.test(s.part)));
    ok(V('Tab reaches the form and the hello button'), seen.some((s) => s && s.part === 'xg-form-a') && seen.some((s) => s && s.part === 'xg-hello-a'));
    ok(V('the inactive panes ignore the pointer'), await page.evaluate(() => [...document.querySelectorAll('.xgate-card > .xg-pane-form, .xgate-card > .xg-pane-hello')].every((p) => getComputedStyle(p).pointerEvents === 'none')));

    // wrong password: the message appears, the reserved space does not move anything, the password hides again
    const before = { btn: await box(page, `${part('a')} .xg-primary`), card: await box(page, '.xgate-card') };
    await page.locator(`${part('a')} input[type=email]`).fill(app.user);
    await pw.fill(app.wrong);
    await eye.click();
    await page.locator(`${part('a')} .xg-primary`).click();
    const alert = page.locator(`${part('a')} [role=alert]`);
    await page.waitForFunction((s) => document.querySelector(s) && document.querySelector(s).textContent.trim().length > 0, `${part('a')} [role=alert]`);
    ok(V('wrong password shows an error'), (await alert.innerText()).trim().length > 0);
    const after = { btn: await box(page, `${part('a')} .xg-primary`), card: await box(page, '.xgate-card') };
    eq(V('error appearing moves nothing (button y)'), Math.round(after.btn.y), Math.round(before.btn.y));
    eq(V('error appearing moves nothing (card height)'), Math.round(after.card.height), Math.round(before.card.height));
    eq(V('wrong password: the field is hidden again'), await pw.getAttribute('type'), 'password');
    eq(V('wrong password: the eye is reset'), await eye.getAttribute('aria-pressed'), 'false');
    ok(V('wrong password: the button works again'), await page.locator(`${part('a')} .xg-primary`).isEnabled());
    ok(V('wrong password: still signed out'), (await page.locator('.xgate').count()) === 1);
    await contrastOf(page, `${part('a')} [role=alert]`, V('error text'), 4.5);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${key}-error-${vname}.png`) });

    // swap: resets the password and the eye, moves focus to the other form, and the h1 follows
    await eye.click();
    await page.locator(`${part('a')} .xg-link`).click();
    await page.waitForTimeout(700);
    eq(V('mode B title'), (await page.locator('h1').first().innerText()).trim().toLowerCase(), 'get access');
    eq(V('exactly one h1 in mode B'), await page.locator('h1').count(), 1);
    eq(V('mode B: Google link count'), await page.locator(`${part('b')} a[href*="/auth/google/"]`).count(), key === 'admin' ? 0 : 1);
    eq(V('mode B: no divider'), await page.locator(`${part('b')} .or`).count(), 0);
    eq(V('mode A form is inert in mode B'), await page.locator(part('a')).evaluate((n) => [n.inert, n.getAttribute('aria-hidden')]), [true, 'true']);
    eq(V('swap hides and clears the password'), await pw.evaluate((i) => [i.type, i.value]), ['password', '']);
    eq(V('swap resets the eye'), await eye.evaluate((b) => [b.getAttribute('aria-pressed'), b.getAttribute('aria-label')]), ['false', 'Show password']);
    seen = await tabbed(page, 10);
    ok(V('Tab never lands in mode A while in mode B'), seen.every((s) => !s || !/-a$/.test(s.part)));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${key}-b-${vname}.png`) });
    await contrastOf(page, 'h1', V('mode B title'), 3);
    await contrastOf(page, '.xgate .xg-hello-b p', V('mode B greeting'), 4.5);

    // swap A -> B -> A inside one task: the pending focus of the first swap must not steal focus from the last
    await page.locator('.xgate .xg-hello-b .xg-ghost').click();
    await page.waitForTimeout(700);
    await page.evaluate(() => { document.querySelector('.xg-form-a .xg-link').click(); document.querySelector('.xg-hello-b .xg-ghost').click(); });
    await page.waitForTimeout(700);
    eq(V('back in mode A'), await page.locator('.xgate-card').getAttribute('data-mode'), 'a');
    ok(V('focus is in the mode A form'), await page.evaluate(() => !!(document.activeElement && document.activeElement.closest('.xg-form-a'))));
    await contrastOf(page, 'h1', V('mode A title'), 3);
    await contrastOf(page, `${part('a')} .xg-link`, V('Get access link'), 4.5);
    await contrastOf(page, `${part('a')} .xg-primary`, V('Login button text'), 4.5);
    await contrastOf(page, '.xgate .xg-hello-a p', V('mode A greeting'), 4.5);

    ok(V('no CSP violation'), (await page.evaluate(() => window.__csp)).length === 0);
    await ctx.close();
  }

  // Google off: no link at all
  {
    const { ctx, page } = await newPage(browser, info, app, 1440, 852, { google: false });
    await page.waitForTimeout(300);
    eq(T('Google off: no Google link anywhere'), await page.locator('a[href*="/auth/google/"]').count(), 0);
    eq(T('Google off: no divider'), await page.locator('.xgate .or').count(), 0);
    await ctx.close();
  }

  // auth_error: the fixed text, and the query is gone from the address
  for (const [code, text] of Object.entries(app.errors)) {
    const { ctx, page } = await newPage(browser, info, app, 1440, 852, { query: '?auth_error=' + code });
    eq(T(`auth_error=${code} text`), (await page.locator('.xgate [role=alert]').first().innerText()).trim(), text);
    ok(T(`auth_error=${code} removed from the address`), !/auth_error/.test(page.url()));
    await ctx.close();
  }
  {
    const { ctx, page } = await newPage(browser, info, app, 1440, 852, { query: '?auth_error=%3Cb%3Ex%3C%2Fb%3E' });
    eq(T('unknown auth_error gets the generic text, never the code'), (await page.locator('.xgate [role=alert]').first().innerText()).trim(), "Sign-in didn't work. Try again.");
    eq(T('unknown auth_error injects no markup'), await page.locator('.xgate [role=alert] b').count(), 0);
    await ctx.close();
  }

  // a long error at 200% zoom (1440x852 at 200% is a 720x426 viewport) and on a phone: it wraps inside the card
  for (const [w, h, label] of [[720, 426, '200% zoom'], [390, 844, 'phone']]) {
    const { ctx, page } = await newPage(browser, info, app, w, h);
    const long = 'The gateway refused this sign-in because ' + 'a-very-long-unbroken-reason-'.repeat(8) + ' and then explained itself at some length so the message wraps over several lines.';
    await page.route(app.loginApi, (r) => r.fulfill({ status: 401, json: { error: long } }));
    await page.locator('.xg-form-a input[type=email]').fill(app.user);
    await page.locator('.xg-form-a input[autocomplete=current-password]').fill(app.wrong);
    await page.locator('.xg-form-a .xg-primary').click();
    await page.waitForFunction(() => { const a = document.querySelector('.xg-form-a [role=alert]'); return a && a.textContent.trim().length > 20; });
    const m = await page.evaluate(() => { const a = document.querySelector('.xg-form-a [role=alert]').getBoundingClientRect(); const c = document.querySelector('.xgate-card').getBoundingClientRect();
      const d = document.documentElement; return { aL: a.left, aR: a.right, cL: c.left, cR: c.right, sw: d.scrollWidth, cw: d.clientWidth }; });
    ok(T(`${label}: long error stays inside the card (${Math.round(m.aL)}..${Math.round(m.aR)} in ${Math.round(m.cL)}..${Math.round(m.cR)})`), m.aL >= m.cL - 1 && m.aR <= m.cR + 1);
    ok(T(`${label}: no sideways scrolling (${m.sw} <= ${m.cw})`), m.sw <= m.cw);
    const prim = await box(page, '.xg-form-a .xg-primary');
    ok(T(`${label}: the Login button is still reachable and on screen width`), prim && prim.x >= 0 && prim.x + prim.width <= m.cw + 1);
    await ctx.close();
  }

  // correct password signs in (last: it ends the gate)
  {
    const { ctx, page } = await newPage(browser, info, app, 1440, 852);
    await page.locator('.xg-form-a input[type=email]').fill(app.user);
    await page.locator('.xg-form-a input[autocomplete=current-password]').fill(app.pass);
    await page.locator('.xg-form-a .xg-primary').click();
    await page.waitForFunction(() => !document.querySelector('.xgate') && document.querySelector('main h1'), null, { timeout: 15000 });
    ok(T('correct password leaves the gate'), (await page.locator('.xgate').count()) === 0);
    ok(T('no CSP violation after signing in'), (await page.evaluate(() => window.__csp)).length === 0);
    await ctx.close();
  }
}

async function welcomeChecks(browser, info) {
  const app = APPS.staff;
  for (const mode of ['valid', 'expired']) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 852 } });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => results.errors.push(String(e)));
    await page.route('**/auth/options', (r) => r.fulfill({ json: { google: false } }));
    await page.route('**/api/welcome/tok-test-123', (r) => mode === 'valid'
      ? r.fulfill({ json: { name: 'Test Person', email: 'test.person@example.test', has_password: false } })
      : r.fulfill({ status: 410, json: { error: 'This sign-in link has expired. Ask your admin for a new one.' } }));
    await page.goto(info.url + '/#/welcome/tok-test-123');
    if (mode === 'valid') {
      await page.waitForSelector('#w-pass');
      ok('welcome (valid): the set-password form shows the invited address', (await page.locator('main').innerText()).includes('test.person@example.test'));
      eq('welcome (valid): new-password autocomplete on both fields', await page.locator('#w-pass, #w-again').evaluateAll((l) => l.map((i) => i.autocomplete)), ['new-password', 'new-password']);
      await page.fill('#w-pass', 'long-enough-one'); await page.fill('#w-again', 'long-enough-two');
      await page.locator('form button[type=submit]').click();
      eq('welcome (valid): mismatched passwords are refused in the page', (await page.locator('form [role=alert]').first().innerText()).trim(), "The two passwords don't match.");
    } else {
      await page.waitForFunction(() => /expired/.test(document.body.innerText));
      ok('welcome (expired): the server message is shown', (await page.locator('main').innerText()).includes('This sign-in link has expired.'));
      ok('welcome (expired): a way back to sign in', (await page.locator('a[href="#/"]').count()) >= 1);
    }
    await ctx.close();
  }
}

(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', (d) => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', (c) => c && rej(new Error('demo exit ' + c))); });
    browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
    await gateChecks(browser, info, 'admin', APPS.admin);
    if (staffPorted) await gateChecks(browser, info, 'staff', APPS.staff);
    else results.checks.push('Not run: staff sign-in checks (portal.js showSignIn is not on the split gate yet)');
    await welcomeChecks(browser, info);
    ok('no console or page errors', results.errors.length === 0);
  } finally {
    if (browser) await browser.close();
    demo.kill();
  }
  console.log(JSON.stringify(results, null, 1));
})().catch((e) => { console.error(e); process.exit(1); });
