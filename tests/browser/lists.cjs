/* Focused checks for the glass list primitives (R7): SUI.listPanel, segmented, searchPill, progress, star and the table inside.
   NODE_PATH must reach a tooling dir with playwright (never installed in the repo). Starts tests/browser/demo.py (test database).
   The page is the real console with a fixture list mounted by SUI in main: the first row is the demo database's real person,
   the other rows are placeholders (example.test addresses, invented percentages). SHOTS=<dir> also saves screenshots. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const results = { checks: [], contrast: [], errors: [] };
const ok = (label, v) => { assert.ok(v, label); results.checks.push(label); };
const SHOTS = process.env.SHOTS;

/* Runs in the page: builds the fixture list and returns nothing. */
const mount = (people) => {
  const { el } = SUI;
  const main = document.querySelector('main');
  const fixtures = [
    { name: 'Achieng Olivia', email: 'achieng@example.test', dept: 'Finance', state: 'active', used: 82, fav: true },
    { name: 'Bukenya Daniel', email: 'bukenya@example.test', dept: 'Creative', state: 'active', used: 47, fav: false },
    { name: 'Kintu Sarah', email: 'kintu@example.test', dept: 'Operations', state: 'paused', used: 12, fav: false },
    { name: 'Mugisha Peter', email: 'mugisha@example.test', dept: 'Sales', state: 'active', used: 100, fav: false },
  ];
  const rows = people.map((p) => ({ name: p.name, email: p.email, dept: p.department || 'Not set', state: p.status, used: 23, fav: false })).concat(fixtures);
  let filter = 'all', q = '';
  const body = el('div');
  const draw = () => {
    const shown = rows.filter((r) => (filter === 'all' || r.state === filter) && (!q || (r.name + r.email).toLowerCase().includes(q.toLowerCase())));
    body.replaceChildren(SUI.table({ caption: 'People', rows: shown, sort: ['name', 'asc'], columns: [
      { key: 'fav', label: '', srLabel: 'Favourite', sort: false, render: (r) => SUI.star(r.fav, r.name) },
      { key: 'name', label: 'Person', lead: true, render: (r) => el('div', { class: 'u-cell' }, SUI.avatar(r.name), el('div', null, el('strong', null, r.name), el('span', { class: 'sub' }, r.email))) },
      { key: 'dept', label: 'Department', hideSm: true },
      { key: 'state', label: 'Status', render: (r) => SUI.status(r.state === 'active' ? 'active' : 'paused', r.state === 'active' ? 'Active' : 'Paused') },
      { key: 'used', label: 'Budget used', num: false, render: (r) => SUI.progress(r.used, { label: 'Budget used by ' + r.name }) },
    ] }));
  };
  const count = (s) => rows.filter((r) => s === 'all' || r.state === s).length;
  main.replaceChildren(SUI.el('h1', null, 'People'), SUI.listPanel({ title: 'All people', sub: 'Who can use what', body,
    filters: { label: 'Show', value: 'all', options: [{ id: 'all', label: 'All', count: count('all') }, { id: 'active', label: 'Active', count: count('active') }, { id: 'paused', label: 'Paused', count: count('paused') }], onChange: (v) => { filter = v; draw(); } },
    search: { label: 'Search people', placeholder: 'Search people', onInput: (v) => { q = v; draw(); } } }));
  draw();
};

/* Worst contrast of an element's text (or a non-text part) against the pixels actually painted behind it. */
async function contrastOf(page, sel, label, min, nonText) {
  const box = await page.evaluate(({ sel, nonText }) => {
    const e = document.querySelector(sel); if (!e) return null;
    let r = e.getBoundingClientRect();
    if (!nonText) { const g = document.createRange(); g.selectNodeContents(e); const q = g.getBoundingClientRect(); if (q.width && q.height) r = q; } // just where the glyphs sit, not a pill's curved border
    const color = getComputedStyle(e).color;
    const hidden = []; const hide = (n) => { hidden.push([n, n.style.color]); n.style.setProperty('transition', 'none', 'important'); n.style.setProperty('color', 'transparent', 'important'); };
    hide(e); e.querySelectorAll("*").forEach(hide); const dots = [...e.querySelectorAll("i")]; dots.forEach((n) => n.style.setProperty("background", "transparent", "important")); // a status dot is not text
    window.__restore = () => { dots.forEach((n) => n.style.removeProperty('background')); hidden.forEach(([n, c]) => { n.style.removeProperty('color'); n.style.removeProperty('transition'); if (c) n.style.color = c; }); };
    return { x: r.x, y: r.y, w: r.width, h: r.height, color };
  }, { sel, nonText });
  assert.ok(box, 'missing ' + sel);
  const inset = nonText ? 3 : 0;
  const png = await page.screenshot({ clip: { x: box.x + inset, y: box.y + inset, width: Math.max(2, box.w - 2 * inset), height: Math.max(2, box.h - 2 * inset) } });
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

(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
    browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
    for (const theme of ['dark', 'light']) for (const [vw, vh, vname] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
      const T = `${theme} ${vname}: `;
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: 1, hasTouch: vname === 'mobile' });
      await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, theme);
      const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      assert.equal(r.status(), 200);
      const people = (await (await ctx.request.get(info.url + '/admin/api/people')).json()).items;
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.push(String(e)));
      page.on('console', m => m.type() === 'error' && results.errors.push(m.text()));
      await page.goto(info.url + '/admin');
      await page.waitForSelector('main h1');
      await page.evaluate(mount, people);
      await page.waitForTimeout(700); // let the bars finish growing
      const s = await page.evaluate(() => {
        const list = document.querySelector('.u-list'); const cs = (e, p) => getComputedStyle(e)[p];
        const bar = document.querySelector('.u-progress .bar i');
        return {
          panelBlur: cs(list, 'backdropFilter'), rowBlur: cs(document.querySelector('.u-list tbody tr'), 'backdropFilter'), segBlur: cs(document.querySelector('.u-seg'), 'backdropFilter'),
          radius: cs(list, 'borderTopLeftRadius'), segRadius: cs(document.querySelector('.u-seg'), 'borderTopLeftRadius'), searchRadius: cs(document.querySelector('.u-search'), 'borderTopLeftRadius'),
          pressed: document.querySelectorAll('.u-seg [aria-pressed="true"]').length, group: document.querySelector('.u-seg').getAttribute('role'),
          bars: [...document.querySelectorAll('.u-progress .bar')].map(b => [b.getAttribute('role'), b.getAttribute('aria-valuenow'), !!b.getAttribute('aria-label')]),
          firstTransform: cs(bar, 'transform'), firstP: bar.style.getPropertyValue('--p'),
          overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          cards: cs(document.querySelector('.u-table'), 'display'),
          starLabel: document.querySelector('.u-star').getAttribute('aria-label'),
          searchLabel: document.querySelector('.u-search input').getAttribute('aria-label'),
          segMinH: document.querySelector('.u-seg button').getBoundingClientRect().height,
          starSize: document.querySelector('.u-star').getBoundingClientRect().width,
        };
      });
      ok(T + 'one blur layer: the panel blurs, rows, pills and search do not', s.panelBlur !== 'none' && s.rowBlur === 'none' && s.segBlur === 'none');
      ok(T + 'panel uses the card radius, pills and search are fully round', s.radius === '22px' && parseFloat(s.segRadius) >= 100 && parseFloat(s.searchRadius) >= 100);
      ok(T + 'filter pills are a labelled group with exactly one pressed', s.group === 'group' && s.pressed === 1);
      ok(T + 'every progress bar has role, value and a name', s.bars.length >= 5 && s.bars.every(b => b[0] === 'progressbar' && b[1] !== null && b[2]));
      const m = s.firstTransform.match(/matrix\(([^)]+)\)/); const sx = m ? parseFloat(m[1].split(',')[0]) : NaN;
      ok(T + 'progress fill is a transform scale equal to its value', Math.abs(sx - parseFloat(s.firstP)) < 0.01);
      ok(T + 'no horizontal page scroll', s.overflowX <= 0);
      ok(T + 'star and search have accessible names', /^Favourite /.test(s.starLabel) && s.searchLabel === 'Search people');
      if (vname === 'mobile') {
        ok(T + 'table becomes cards on phones', s.cards === 'block');
        ok(T + 'touch targets: pills >= 36px tall, stars >= 44px wide', s.segMinH >= 36 && s.starSize >= 44);
      } else {
        ok(T + 'table stays a table on desktop', s.cards === 'table');
        // behaviour (once per theme)
        if (true) {
          await page.click('.u-seg button[data-id="paused"]');
          const afterFilter = await page.evaluate(() => ({ rows: document.querySelectorAll('.u-list tbody tr').length, pressed: document.querySelector('.u-seg [aria-pressed="true"]').dataset.id }));
          ok(T + 'a filter pill narrows the rows and takes the pressed state', afterFilter.pressed === 'paused' && afterFilter.rows >= 1 && afterFilter.rows < 6);
          await page.click('.u-seg button[data-id="all"]');
          await page.fill('.u-search input', 'kintu');
          ok(T + 'the search pill filters rows', (await page.locator('.u-list tbody tr').count()) === 1);
          await page.fill('.u-search input', '');
          await page.focus('.u-seg button[data-id="all"]');
          await page.keyboard.press('ArrowRight');
          ok(T + 'arrow keys move focus between pills', (await page.evaluate(() => document.activeElement.dataset.id)) === 'active');
          await page.keyboard.press('End');
          ok(T + 'End goes to the last pill', (await page.evaluate(() => document.activeElement.dataset.id)) === 'paused');
          await page.keyboard.press('Home');
          ok(T + 'Home goes to the first pill', (await page.evaluate(() => document.activeElement.dataset.id)) === 'all');
          const before = await page.getAttribute('.u-star', 'aria-pressed');
          await page.click('.u-star');
          ok(T + 'a star toggles its pressed state', (await page.getAttribute('.u-star', 'aria-pressed')) === (before === 'true' ? 'false' : 'true'));
          await page.click('.u-star');
          // contrast on what is really painted
          await contrastOf(page, '.u-list-title h2', T + 'panel title', 4.5);
          await contrastOf(page, '.u-list-title p', T + 'panel subtitle', 4.5);
          await contrastOf(page, '.u-seg button[aria-pressed="true"]', T + 'pressed pill text', 4.5);
          await contrastOf(page, '.u-seg button[aria-pressed="false"]', T + 'unpressed pill text', 4.5);
          await contrastOf(page, '.u-seg button[aria-pressed="false"] .n', T + 'pill count', 4.5);
          await contrastOf(page, '.u-search svg', T + 'search icon', 3, true);
          await contrastOf(page, '.u-list thead th button', T + 'column heading', 4.5);
          await contrastOf(page, '.u-list tbody td .u-cell strong', T + 'row name', 4.5);
          await contrastOf(page, '.u-list tbody td .sub', T + 'row email', 4.5);
          await contrastOf(page, '.u-list tbody td:nth-child(3)', T + 'department', 4.5);
          await contrastOf(page, '.u-list tbody .u-status', T + 'status word', 4.5);
          await contrastOf(page, '.u-progress .v', T + 'progress value', 4.5);
          await contrastOf(page, '.u-star', T + 'star icon', 3, true);
          // the fill against what the bar sits on: sample a strip of the track beside the fill
          const track = await page.evaluate(() => { const b = document.querySelectorAll('.u-progress .bar')[1]; const r = b.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
          const png = await page.screenshot({ clip: { x: track.x, y: track.y, width: track.w, height: track.h } });
          const ratio = await page.evaluate(async ({ b64, p }) => {
            const bmp = await createImageBitmap(new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: 'image/png' }));
            const cv = new OffscreenCanvas(bmp.width, bmp.height); const cx = cv.getContext('2d'); cx.drawImage(bmp, 0, 0);
            const at = (fx) => cx.getImageData(Math.floor(bmp.width * fx), Math.floor(bmp.height / 2), 1, 1).data;
            const lum = (d) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(d[0]) + .7152 * f(d[1]) + .0722 * f(d[2]); };
            const a = lum(at(Math.max(0.03, p / 2))), b = lum(at(Math.min(0.97, p + (1 - p) / 2)));
            return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
          }, { b64: png.toString('base64'), p: 0.47 });
          results.contrast.push({ label: T + 'progress fill vs track', ratio: +ratio.toFixed(2), min: 3 });
          ok(T + `progress fill vs track ${ratio.toFixed(2)} >= 3`, ratio >= 3);
        }
      }
      if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `list-${vname}-${theme}.png`) }); }
      await ctx.close();
    }
    // reduced motion stops the bars growing; reduced transparency drops the blur (where the browser can emulate it)
    const rctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    const rr = await rctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
    assert.equal(rr.status(), 200);
    const rp = await rctx.newPage();
    rp.on('pageerror', e => results.errors.push(String(e)));
    await rp.goto(info.url + '/admin'); await rp.waitForSelector('main h1');
    await rp.evaluate(mount, []);
    const rm = await rp.evaluate(() => ({ anim: getComputedStyle(document.querySelector('.u-progress .bar i')).animationName, tr: getComputedStyle(document.querySelector('.u-seg button')).transitionDuration }));
    ok('reduced motion: bars do not animate and pills do not transition', rm.anim === 'none' && parseFloat(rm.tr) <= 0.01);
    await rctx.close();
    // a plain context: Playwright re-sends its own media overrides when reducedMotion is set, which would drop this one
    const tctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const tr = await tctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
    assert.equal(tr.status(), 200);
    const tp = await tctx.newPage();
    tp.on('pageerror', e => results.errors.push(String(e)));
    await tp.goto(info.url + '/admin'); await tp.waitForSelector('main h1');
    await tp.evaluate(mount, []);
    let cdp = null;
    try { cdp = await tctx.newCDPSession(tp); await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }] }); }
    catch (e) { results.checks.push('Not run: reduced-transparency emulation failed: ' + e.message); }
    if (cdp) {
      await tp.waitForTimeout(300);
      const rt = await tp.evaluate(() => { const l = document.querySelector('.u-list'); return { match: matchMedia('(prefers-reduced-transparency: reduce)').matches, blur: getComputedStyle(l).backdropFilter, bg: getComputedStyle(l).backgroundColor, seg: getComputedStyle(document.querySelector('.u-seg')).backgroundColor }; });
      if (rt.match) ok('reduced transparency: the panel drops its blur and the panel and pills go solid', rt.blur === 'none' && /^rgb\(/.test(rt.bg) && /^rgb\(/.test(rt.seg));
      else results.checks.push('Not run: this Chrome did not apply prefers-reduced-transparency emulation');
    }
    await tctx.close();
    ok('no console or page errors', results.errors.length === 0);
  } finally {
    if (browser) await browser.close();
    demo.kill();
  }
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
