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
  await page.waitForSelector('.xgate:not(.xg-wait) .xgate-card');
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

    // wrong password: a one-line message lands in the reserved row and moves nothing, the password hides again
    const before = { btn: await box(page, `${part('a')} .xg-primary`), card: await box(page, '.xgate-card') };
    await page.locator(`${part('a')} input[type=email]`).fill(app.user);
    await pw.fill(app.wrong);
    await eye.click();
    await page.locator(`${part('a')} .xg-primary`).click();
    const alert = page.locator(`${part('a')} [role=alert]`);
    await page.waitForFunction((s) => document.querySelector(s) && document.querySelector(s).textContent.trim().length > 0, `${part('a')} [role=alert]`);
    ok(V('wrong password shows an error'), (await alert.innerText()).trim().length > 0);
    const after = { btn: await box(page, `${part('a')} .xg-primary`), card: await box(page, '.xgate-card') };
    eq(V('a one-line error moves nothing (button y)'), Math.round(after.btn.y), Math.round(before.btn.y));
    eq(V('a one-line error moves nothing (card height)'), Math.round(after.card.height), Math.round(before.card.height));
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
    // positions against glass-login.mp4 / login-05 (card top y=5): within 4px (BRIEF 10.2). The still's values are relative to the card top.
    const P = await page.evaluate(() => { const c = document.querySelector('.xgate-card').getBoundingClientRect(); const f = document.querySelector('.xg-form-a');
      const r = (s) => f.querySelector(s).getBoundingClientRect(); const fs = f.querySelectorAll('.xfield'); const L = r('.xg-links');
      return { email: fs[0].getBoundingClientRect().bottom - c.top, pass: fs[1].getBoundingClientRect().bottom - c.top, btnTop: r('.xg-primary').top - c.top, btnBottom: r('.xg-primary').bottom - c.top, links: (L.top + L.bottom) / 2 - c.top }; });
    [['email underline', P.email, 286], ['password underline', P.pass, 347], ['Login button top', P.btnTop, 374], ['Login button bottom', P.btnBottom, 432], ['links centre', P.links, 476]]
      .forEach(([n, got, want]) => ok(T(`reference position: ${n} ${got.toFixed(1)} vs ${want} (±4)`), Math.abs(got - want) <= 4));
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
    const g = await page.evaluate(() => { const a = document.querySelector('.xg-form-a [role=alert]'); const b = document.querySelector('.xg-form-a .xg-primary').getBoundingClientRect(); const r = a.getBoundingClientRect();
      return { h: r.height, scroll: a.scrollHeight, client: a.clientHeight, clipped: getComputedStyle(a).overflow, gap: b.top - r.bottom }; });
    ok(T(`${label}: the alert grew past its reserve (${Math.round(g.h)}px) and is not clipped (scroll ${g.scroll} <= client ${g.client})`), g.h > 30 && g.scroll <= g.client + 1 && g.clipped !== 'hidden');
    ok(T(`${label}: the Login button starts below the grown alert (gap ${Math.round(g.gap)}px)`), g.gap >= 0);
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

/* The swap's timing, frame by frame (30fps), against glass-login.mp4: the old words are gone by frame 4-5 (stills 51-52), the glass is bare for a
   beat, the new words begin at frame 6 (still 54) and are in by 12 (still 60). Animations are paused and set to each frame's time, so the laptop's
   slow rendering cannot change the answer. Then reduced motion (everything instant) and a 400ms-late /auth/options (CLS). */
async function motionChecks(browser, info, app) {
  const T = (s) => `${app.name}: ${s}`;
  {
    const { ctx, page } = await newPage(browser, info, app, 1440, 852);
    await page.waitForTimeout(1200);
    const rows = await page.evaluate(async () => {
      const g = (e) => { const s = getComputedStyle(e); return s.visibility === 'hidden' ? 0 : +(+s.opacity).toFixed(2); };
      const ids = ['.xg-form-a', '.xg-hello-a', '.xg-form-b', '.xg-hello-b'].map((s) => document.querySelector(s));
      document.querySelector('.xg-hello-a .xg-ghost').click();
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const an = document.getAnimations(); an.forEach((a) => a.pause());
      const out = [];
      for (let f = 0; f <= 14; f++) { an.forEach((a) => { a.currentTime = f * 1000 / 30; }); out.push(ids.map(g)); }
      return out;
    });
    const at = (f) => rows[f];
    ok(T('swap frame 0: only the old words are showing'), at(0)[0] === 1 && at(0)[1] === 1 && at(0)[2] === 0 && at(0)[3] === 0);
    ok(T('swap frames 1-3: the old words fade while the new are still absent'), [1, 2, 3].every((f) => at(f)[0] < at(f - 1)[0] && at(f)[2] === 0 && at(f)[3] === 0));
    ok(T('swap: the old words are gone by frame 5 (±2 of the still at 3)'), at(5)[0] === 0 && at(5)[1] === 0);
    ok(T('swap: bare glass at frames 4-5 (nothing showing)'), [4, 5].every((f) => at(f).every((v) => v === 0)));
    ok(T('swap: the new words begin at frame 6-7 (still 54 = 6, ±2)'), at(5)[2] === 0 && at(7)[2] > 0 && at(7)[3] > 0 && at(8)[2] > at(7)[2]);
    ok(T('swap: the new words are in by frame 12 (still 60, ±2)'), at(12)[2] >= 0.99 && at(12)[3] >= 0.99 && at(10)[2] < 1);
    ok(T('swap: the old and the new are never both visible (no cross-fade)'), rows.every((r) => !((r[0] > 0 || r[1] > 0) && (r[2] > 0 || r[3] > 0))));
    await ctx.close();
  }
  { // reduced motion: instant
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 852 }, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await page.route('**/auth/options', (r) => r.fulfill({ json: { google: false } }));
    await page.goto(info.url + app.start); await page.waitForSelector('.xgate:not(.xg-wait) .xgate-card');
    await page.locator('.xg-hello-a .xg-ghost').click();
    const d = await page.evaluate(() => [...document.querySelectorAll('.xgate .xg-form, .xgate .xg-hello')].map((e) => getComputedStyle(e).transitionDuration + '/' + getComputedStyle(e).transitionDelay));
    ok(T('reduced motion: every transition is 0s with no delay'), d.every((x) => /^(0s,? ?)+\/(0s,? ?)+$/.test(x)));
    await ctx.close();
  }
  // CLS with a 400ms-late /auth/options: the Google row and divider must not move anything the person can see
  for (const [w, h, vname] of VIEWS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript(() => { window.__cls = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { const src = e.sources || []; if (src.length && src.every((s) => s.node && s.node.parentElement && !s.node.parentElement.closest('.xgate-card'))) continue; window.__cls += e.value; } }).observe({ type: 'layout-shift', buffered: true }); });
    const page = await ctx.newPage();
    await page.route('**/auth/options', async (r) => { await new Promise((x) => setTimeout(x, 400)); r.fulfill({ json: { google: true } }); });
    await page.goto(info.url + app.start);
    await page.waitForSelector('.xgate:not(.xg-wait) .xgate-card');
    const first = await box(page, '.xg-form-a .xg-primary');
    await page.waitForTimeout(1800);
    const last = await box(page, '.xg-form-a .xg-primary');
    ok(T(`${vname}: Google arrives late, the Login button never moves once the card shows (${Math.round(first.y)} -> ${Math.round(last.y)})`), Math.abs(first.y - last.y) < 1);
    ok(T(`${vname}: the Google link is there after the late answer`), (await page.locator('.xg-form-a a[href*="/auth/google/"]').count()) === 1);
    const cls = await page.evaluate(() => window.__cls);
    ok(T(`${vname}: layout shift with a 400ms-late /auth/options is under 0.0001 (${cls.toFixed(6)}); only the brand wordmark outside the card (a web-font swap) is counted out`), cls < 0.0001);
    await ctx.close();
  }
}

/* The reveal matrix (Sentinel G2 ruling, Nov 8): the gate is not painted until Google's answer AND the typeface are in, or 1.2s has passed.
   Inter is latched on once at the reveal only if it was loaded then (a late or missing font is ignored for the view: the system sans stays, a
   documented BRIEF 10.1 (3) performance fallback); the Google row's room is held only if the answer was still outstanding at the reveal.
   Every run records ALL layout-shift entries (text nodes and null nodes included) with the reveal time, from a MutationObserver on the mount and
   on the removal of .xg-wait. After the reveal there must be NO entry inside .xgate (not a threshold: none), the title, the fields and the Login
   button must not move by 1px, and the raw global total is reported with the old threshold. A non-font remainder must be reported with its source,
   never relaxed. */
const FONT_URL = '**/fonts/Inter-latin.woff2';
const MATRIX = [
  // opt: [answer, delay ms] (hung = dropped at 4.5s)           font: [kind, ms]
  { n: 'fast+font-fast',      opt: ['on', 0],     font: ['fast'],      inter: true,  google: 'link' },
  { n: 'font-800ms',          opt: ['on', 0],     font: ['delay', 800], inter: true,  google: 'link' },
  { n: 'font-2.5s',           opt: ['on', 0],     font: ['delay', 2500], inter: false, google: 'link' },
  { n: 'font-404',            opt: ['on', 0],     font: ['404'],       inter: false, google: 'link' },
  { n: 'font-hung',           opt: ['on', 0],     font: ['hung'],      inter: false, google: 'link' },
  { n: 'off+font-2.5s',       opt: ['off', 0],    font: ['delay', 2500], inter: false, google: 'none' },
  { n: 'abort+font-2.5s',     opt: ['abort', 0],  font: ['delay', 2500], inter: false, google: 'none' },
  { n: 'late-on',             opt: ['on', 1500],  font: ['fast'],      inter: true,  google: 'link', late: true },
  { n: 'late-off',            opt: ['off', 1500], font: ['fast'],      inter: true,  google: 'gap', late: true },
  { n: 'late-fail',           opt: ['abort', 1500], font: ['fast'],    inter: true,  google: 'gap', late: true },
  { n: 'hung',                opt: ['hung', 0],   font: ['fast'],      inter: true,  google: 'gap', late: true },
  { n: 'abort',               opt: ['abort', 0],  font: ['fast'],      inter: true,  google: 'none' },
];
async function lateGoogleChecks(browser, info, app) {
  const T = (s) => `${app.name}: ${s}`;
  for (const [w, h, vname] of VIEWS) for (const m of MATRIX) {
    const L = (s) => T(`${vname} ${m.n}: ${s}`);
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript(() => {
      const st = window.__ls = { entries: [], mount: null, reveal: null };
      const inside = (e) => !e.sources || !e.sources.length || e.sources.some((x) => { const n = x.node; if (!n) return true; const el = n.nodeType === 1 ? n : n.parentElement; return !el || !!el.closest('.xgate'); });
      new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) st.entries.push({ t: e.startTime, v: e.value, inside: inside(e),
        src: (e.sources || []).map((x) => (x.node ? (x.node.nodeType === 1 ? x.node.tagName + '.' + x.node.className : '#text in ' + (x.node.parentElement ? x.node.parentElement.tagName + '.' + x.node.parentElement.className : '?')) : 'null')) }); }).observe({ type: 'layout-shift', buffered: true });
      const look = () => { const g = document.querySelector('.xgate'); if (!g) return; const now = performance.now();
        if (st.mount == null) st.mount = now; if (st.reveal == null && !g.classList.contains('xg-wait')) st.reveal = now; };
      new MutationObserver(look).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
    });
    const page = await ctx.newPage();
    const [kind, d] = m.font;
    if (kind === 'delay') await page.route(FONT_URL, async (r) => { await new Promise((x) => setTimeout(x, d)); r.continue().catch(() => {}); });
    if (kind === '404') await page.route(FONT_URL, (r) => r.fulfill({ status: 404, body: 'no' }));
    if (kind === 'hung') await page.route(FONT_URL, async (r) => { await new Promise((x) => setTimeout(x, 6000)); r.abort().catch(() => {}); });
    const [ans, delay] = m.opt;
    await page.route('**/auth/options', async (r) => {
      if (ans === 'hung') { await new Promise((x) => setTimeout(x, 4500)); return r.abort().catch(() => {}); }
      if (delay) await new Promise((x) => setTimeout(x, delay));
      if (ans === 'abort') return r.abort().catch(() => {});
      r.fulfill({ json: { google: ans === 'on' } }).catch(() => {});
    });
    await page.goto(info.url + app.start);
    await page.waitForSelector('.xgate:not(.xg-wait) .xgate-card', { timeout: 6000 });
    const sel = { title: '.xg-form-a .xg-title', email: '.xg-form-a .xfield >> nth=0', pass: '.xg-form-a .xfield >> nth=1', go: '.xg-form-a .xg-primary' };
    const grab = async () => { const o = {}; for (const k of Object.keys(sel)) o[k] = await page.locator(sel[k]).first().boundingBox(); return o; };
    const first = await grab();
    await page.waitForTimeout(3600);                               // past the 2.5s font, the 1.5s answer and the 4.5s drop's first half
    const last = await grab();
    const st = await page.evaluate(() => {
      const g = document.querySelector('.xgate'); const t = document.querySelector('.xg-form-a .xg-title'); const box = document.querySelector('.xg-form-a .google-box');
      return { ...window.__ls, inter: g.classList.contains('xg-inter'), lateCls: g.classList.contains('xg-late'), fam: getComputedStyle(t).fontFamily, boxH: box ? Math.round(box.getBoundingClientRect().height) : 0,
        links: [...document.querySelectorAll('.xg-form-a a[href*="/auth/google/"]')].map((a) => a.getAttribute('href')),
        allLinks: document.querySelectorAll('a[href*="/auth/google/"]').length, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        cardOver: (() => { const c = document.querySelector('.xgate-card'); return c.scrollWidth - c.clientWidth; })() };
    });
    const after = st.entries.filter((e) => st.reveal != null && e.t >= st.reveal - 1);
    const inAfter = after.filter((e) => e.inside);
    const raw = st.entries.reduce((a, e) => a + e.v, 0);
    results.checks.push(L(`entries: ${st.entries.length} total, ${after.length} after reveal (${inAfter.length} inside .xgate); raw ${raw.toFixed(6)}; reveal ${Math.round(st.reveal - st.mount)}ms after mount`));
    ok(L(`reveal within 1200ms + tolerance of the mount (${Math.round(st.reveal - st.mount)}ms)`), st.reveal != null && st.reveal - st.mount <= 1200 + 350);
    eq(L('Inter is latched on exactly when it was loaded at the reveal'), st.inter, m.inter);
    if (!m.inter) ok(L(`the fallback stays for the view even after the font arrives (${st.fam})`), !/Inter/.test(st.fam));
    else ok(L(`Inter is in use (${st.fam})`), /^"?Inter/.test(st.fam));
    ok(L(`zero layout-shift entries inside .xgate after the reveal ${JSON.stringify(inAfter.map((e) => [e.v, e.src]))}`), inAfter.length === 0);
    const insideSum = st.entries.filter((e) => e.inside).reduce((x, e) => x + e.v, 0);
    ok(L(`layout shift inside .xgate across the whole run ${insideSum.toFixed(6)} < 0.0001; raw global ${raw.toFixed(6)} < 0.001 (outside entries: ${JSON.stringify(st.entries.filter((e) => !e.inside).map((e) => [e.v, e.src]))})`), insideSum < 0.0001 && raw < 0.001);
    for (const k of Object.keys(sel)) ok(L(`${k} does not move after the reveal (${Math.round(first[k].y)} -> ${Math.round(last[k].y)}, x ${Math.round(first[k].x)} -> ${Math.round(last[k].x)})`),
      Math.abs(first[k].y - last[k].y) < 1 && Math.abs(first[k].x - last[k].x) < 1 && Math.abs(first[k].height - last[k].height) < 1);
    if (m.google === 'link') {
      eq(L('exactly one Google link, the correct one'), st.links, [app.googleHref]);
    } else {
      eq(L('no Google link'), st.allLinks, 0);
      if (m.google === 'none') eq(L('no room held for Google (the box is 0px tall)'), st.boxH, 0);
      else ok(L(`the room for the unanswered Google row is held as a quiet gap (${st.boxH}px)`), st.boxH >= 90 && st.lateCls);
    }
    if (m.late) ok(L('the reveal held the room for the outstanding answer (xg-late) unless it had already come'), st.lateCls === (m.google !== 'none' || ans === 'hung'));
    else ok(L('no xg-late when the answer was in before the reveal'), !st.lateCls);
    if (m.google === 'gap') { // the gap goes at the next B to A swap, while sign-in A is hidden
      await page.locator('.xg-hello-a .xg-ghost').click(); await page.waitForTimeout(900);
      await page.locator('.xg-hello-b .xg-ghost').click(); await page.waitForTimeout(900);
      const after2 = await page.evaluate(() => { const g = document.querySelector('.xgate'); const b = document.querySelector('.xg-form-a .google-box'); return { late: g.classList.contains('xg-late'), h: b ? Math.round(b.getBoundingClientRect().height) : 0 }; });
      ok(L(`B to A clears the gap once the answer has settled (${after2.h}px, xg-late ${after2.late})`), after2.h === 0 && !after2.late);
    }
    if (vname === 'mobile') ok(L(`no horizontal overflow on a phone (page ${st.overflow}px, card ${st.cardOver}px)`), st.overflow <= 0 && st.cardOver <= 0);
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
    await motionChecks(browser, info, APPS.admin);
    await lateGoogleChecks(browser, info, APPS.admin);
    if (staffPorted) await gateChecks(browser, info, 'staff', APPS.staff);
    if (staffPorted) await motionChecks(browser, info, APPS.staff);
    if (staffPorted) await lateGoogleChecks(browser, info, APPS.staff);
    else results.checks.push('Not run: staff sign-in checks (portal.js showSignIn is not on the split gate yet)');
    await welcomeChecks(browser, info);
    ok('no console or page errors', results.errors.length === 0);
  } finally {
    if (browser) await browser.close();
    demo.kill();
  }
  console.log(JSON.stringify(results, null, 1));
})().catch((e) => { console.error(e); process.exit(1); });
