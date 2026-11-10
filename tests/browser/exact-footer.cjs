/* The staff footer (BRIEF 6, 10.3): geometry at 1440x852 and 390x844 in both themes, the liquid reveal and its
   reduced-motion fallback, the real health word, the Ask pill opening the existing access-request dialog, the
   Evening switch, keyboard reach, and no layout shift or sideways overflow. Local synthetic fixture only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
let demo, browser;
function fixture() {
  demo = spawn('python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  return new Promise((resolve, reject) => {
    let out = '', err = '';
    const timer = setTimeout(() => reject(Error('Fixture timeout: ' + err)), 30000);
    demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
    demo.stderr.on('data', d => { err += d; });
    demo.on('exit', code => { clearTimeout(timer); reject(Error('Fixture exited: ' + code + ' ' + err)); });
  });
}
const box = (p, sel) => p.evaluate(s => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, y: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height }; }, sel);
const near = (actual, expected, tol, label) => assert.ok(Math.abs(actual - expected) <= tol, `${label}: ${actual} not within ${tol} of ${expected}`);
(async () => {
  let checks = 0;
  try {
    const { url } = await fixture();
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined });
    for (const [width, height] of [[1440, 852], [390, 844]]) for (const theme of ['dark', 'light']) for (const motion of ['no-preference', 'reduce']) {
      if (motion === 'reduce' && theme === 'light') continue;
      const label = `${width} ${theme} ${motion}`;
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: motion });
      await c.addInitScript(t => {
        try { localStorage.setItem('swangz-theme', t); } catch (e) { /* none */ }
        window.__shifts = [];
        new PerformanceObserver(l => l.getEntries().forEach(e => { if (!e.hadRecentInput) window.__shifts.push(e.value); })).observe({ type: 'layout-shift', buffered: true });
      }, theme);
      const login = await c.request.post(url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
      assert.equal(login.status(), 200, label + ' login');
      const p = await c.newPage(); const errors = [];
      p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); }); p.on('pageerror', e => errors.push(String(e)));
      await p.goto(url + '/#/tools'); await p.waitForSelector('.xfoot'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(600);

      // Below the first screen until scrolled to; hidden (armed) only when motion is allowed.
      assert.ok((await box(p, '.xfoot')).y >= height, label + ' footer starts below the first screen');
      const armed = await p.evaluate(() => document.querySelector('.xfoot').classList.contains('xf-armed'));
      assert.equal(armed, motion !== 'reduce', label + ' armed only with motion');
      if (armed) assert.equal(await p.evaluate(() => getComputedStyle(document.querySelector('.xf-body')).opacity), '0', label + ' words hidden before the fill');
      await p.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
      await p.waitForFunction(() => getComputedStyle(document.querySelector('.xf-body')).opacity === '1' && getComputedStyle(document.querySelector('.xf-fill')).transform.replace('matrix(1, 0, 0, 1, 0, 0)', 'none') === 'none', null, { timeout: 5000 });
      await p.waitForFunction(() => document.querySelector('.xf-dot').dataset.state !== 'checking', null, { timeout: 5000 });
      assert.equal(await p.textContent('.xf-status'), 'Gateway running', label + ' real health word');

      const panel = await box(p, '.xf-panel'), ask = await box(p, '.xf-ask'), sw = await box(p, '.xf-switch');
      if (width === 1440) {
        const card = await box(p, '.xf-card');
        near(panel.x, 173, 1, label + ' panel left (the shell content column)'); near(panel.r, 1343, 1, label + ' panel right');
        near(ask.w, 380, 1, label + ' ask width'); near(ask.h, 46, 1, label + ' ask height'); near(ask.x - panel.x, 37, 1, label + ' lead inset');
        near(card.y - panel.y, 32, 2, label + ' card top'); near(panel.r - card.r, 35, 1, label + ' card right inset'); near(card.h, 221, 2, label + ' card height');
        near((await box(p, '.xf-col li')).h, 28, 0.5, label + ' link rows'); near(sw.w, 46, 0.5, label + ' switch');
        assert.equal(await p.evaluate(() => getComputedStyle(document.querySelector('.xf-lead h2')).fontSize + ' ' + getComputedStyle(document.querySelector('.xf-lead h2')).fontWeight), '32px 600', label + ' heading');
        assert.equal(await p.evaluate(() => getComputedStyle(document.querySelector('.xf-card')).borderTopLeftRadius), '20px', label + ' card radius');
      } else {
        for (const sel of ['.xf-col a', '.xf-icons a', '.xf-switch', '.xf-ask']) assert.ok((await box(p, sel)).h >= 40, label + ' touch height ' + sel);
      }
      // The wordmark is a hole in the glass: it spans the panel and the whole word, "g" included, is inside it.
      const word = await p.evaluate(() => { const b = document.querySelector('.xf-word').getBBox(); const r = document.querySelector('.xf-glass').getBoundingClientRect(); const fs = parseFloat(getComputedStyle(document.querySelector('.xf-word')).fontSize); return { w: b.width, fs, mask: document.querySelector('rect.xf-milk').getAttribute('mask'), id: document.querySelector('.xf-glass mask').id, glassW: r.width }; });
      assert.equal(word.mask, `url(#${word.id})`, label + ' glass is masked by the word');
      near(word.w, Math.min(panel.w - 80, word.w), 0.5, label + ' word fits');
      assert.ok(word.w >= Math.min(panel.w - 84, 343 * 3), label + ' word spans the panel: ' + word.w + ' of ' + panel.w);
      const meta = await box(p, '.xf-meta'), room = await box(p, '.xf-wordroom');
      assert.ok(room.y >= meta.b - 0.5 && room.h >= word.fs * 0.97, label + ' word has its own room under the bottom row');

      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth), 0, label + ' no sideways overflow');
      assert.deepEqual(await p.evaluate(() => window.__shifts), [], label + ' no layout shift');

      // Evening switch: a real switch, in step with the theme.
      assert.equal(await p.getAttribute('.xf-switch', 'aria-checked'), String(theme === 'dark'), label + ' switch state');
      assert.equal(await p.textContent('.xf-theme-name'), theme === 'dark' ? 'Evening' : 'Daylight');
      await p.click('.xf-switch');
      assert.equal(await p.evaluate(() => document.documentElement.dataset.theme), theme === 'dark' ? 'light' : 'dark', label + ' switch changes the theme');
      assert.equal(await p.getAttribute('.xf-switch', 'aria-checked'), String(theme !== 'dark'));
      await p.click('.xf-switch');

      // Ask: an unknown name explains itself; a known one opens the existing request dialog and sends nothing by itself.
      const posts = []; p.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + new URL(r.url()).pathname); });
      await p.fill('.xf-ask input', 'zzz-not-a-tool'); await p.press('.xf-ask input', 'Enter');
      assert.match(await p.textContent('.xf-note'), /No tool you can ask for matches/, label + ' unknown tool');
      const name = (await p.getAttribute('.xf-ask input', 'placeholder')).replace('Name a tool, e.g. ', '');
      await p.fill('.xf-ask input', name); await p.click('.xf-ask button');
      await p.waitForSelector('dialog[open]', { timeout: 5000 });
      assert.match(await p.textContent('dialog[open]'), new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), label + ' request dialog names the tool');
      assert.deepEqual(posts, [], label + ' nothing is sent until the person confirms');
      await p.keyboard.press('Escape');
      assert.deepEqual(errors, [], label + ' console errors');
      checks++; console.log('PASS footer: ' + label);
      await c.close();
    }
    // Tab reaches the footer before it scrolls into view: focus must reveal it.
    const c = await browser.newContext({ viewport: { width: 1440, height: 852 } });
    assert.equal((await c.request.post(url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } })).status(), 200);
    const p = await c.newPage(); await p.goto(url + '/#/privacy'); await p.waitForSelector('.xfoot.xf-armed');
    await p.evaluate(() => document.querySelector('.xf-col a').focus({ preventScroll: true }));
    assert.ok(await p.evaluate(() => document.querySelector('.xfoot').classList.contains('xf-in')), 'focus reveals the footer');
    console.log(`PASS footer: focus reveal; ${checks + 1} cells`);
  } finally {
    if (browser) await browser.close();
    if (demo) demo.kill('SIGTERM');
  }
})().catch(e => { console.error(e); process.exit(1); });
