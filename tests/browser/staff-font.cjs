/* Cold-load font behaviour of the staff shell (BRIEF 10.1(3), 7): Poppins is latched once at the reveal.
   Every cell loads the signed-in staff app cold with the Poppins files fast, slow, missing or hung and asserts
   that the shell is revealed within the cap, that NO layout shift is recorded at any time, and that a late
   font never swaps in afterwards. Local synthetic fixture only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const FONT = '**/static/fonts/Poppins-*.woff2';
const CELLS = [
  { name: 'fast', mode: 'fast', poppins: true },
  { name: 'font 800ms', mode: 800, poppins: true },
  { name: 'font 2.5s', mode: 2500, poppins: false },
  { name: 'font 404', mode: 'missing', poppins: false },
  { name: 'font hung', mode: 'hung', poppins: false },
];
const ROUTES = ['/#/', '/#/tools', '/#/weekly'];
const SIZES = [[390, 844], [1440, 852]];
let demo, browser;
async function fixture() {
  demo = spawn('python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  return new Promise((resolve, reject) => {
    let out = '', err = '';
    const timer = setTimeout(() => reject(Error('Fixture timeout: ' + err)), 30000);
    demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
    demo.stderr.on('data', d => { err += d; });
    demo.on('exit', code => { clearTimeout(timer); reject(Error('Fixture exited: ' + code + ' ' + err)); });
  });
}
(async () => {
  const log = [];
  try {
    const { url } = await fixture();
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined });
    for (const [width, height] of SIZES) for (const cell of CELLS) for (const route of ROUTES) {
      const label = `${width} ${cell.name} ${route}`;
      const c = await browser.newContext({ viewport: { width, height } });
      await c.addInitScript(() => {
        window.__shifts = []; window.__t = {};
        new PerformanceObserver(l => l.getEntries().forEach(e => window.__shifts.push({
          t: Math.round(e.startTime), v: e.value, hadInput: e.hadRecentInput,
          s: (e.sources || []).map(s => (s.node ? (s.node.nodeName + '.' + (s.node.className && s.node.className.baseVal === undefined ? s.node.className : '')) : 'null')) })))
          .observe({ type: 'layout-shift', buffered: true });
        new MutationObserver(() => {
          const now = performance.now();
          if (!window.__t.mount && document.querySelector('.staff-exact')) window.__t.mount = now;
          if (window.__t.mount && !window.__t.reveal && !document.documentElement.classList.contains('staff-hold')) window.__t.reveal = now;
        }).observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
      });
      const hung = [];
      await c.route(FONT, async r => {
        if (cell.mode === 'fast') return r.fallback();
        if (cell.mode === 'missing') return r.fulfill({ status: 404, body: 'gone' });
        if (cell.mode === 'hung') { hung.push(r); return; }
        await new Promise(res => setTimeout(res, cell.mode)); try { await r.fallback(); } catch (e) { /* page closed */ }
      });
      const login = await c.request.post(url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
      assert.equal(login.status(), 200, label + ' login');
      const p = await c.newPage();
      const errors = []; p.on('pageerror', e => errors.push(e.message));
      await p.goto(url + route, { waitUntil: 'commit' }); // preloads of a hung font hold the load event itself
      await p.locator('.staff-exact').waitFor({ state: 'attached' });
      await p.waitForFunction(() => window.__t.reveal, null, { timeout: 20000 });
      const before = await p.evaluate(() => ({ t: window.__t, ff: getComputedStyle(document.querySelector('.staff-exact')).fontFamily,
        latched: document.documentElement.classList.contains('staff-poppins') }));
      
      await p.waitForTimeout(cell.mode === 2500 ? 3200 : 1800);
      const after = await p.evaluate(() => ({ shifts: window.__shifts, ff: getComputedStyle(document.querySelector('.staff-exact')).fontFamily,
        latched: document.documentElement.classList.contains('staff-poppins'), held: document.documentElement.classList.contains('staff-hold'),
        vis: getComputedStyle(document.querySelector('.staff-exact')).visibility, over: document.documentElement.scrollWidth - innerWidth }));
      const wait = before.t.reveal - before.t.mount;
      assert.ok(wait <= 1550, `${label} revealed ${Math.round(wait)}ms after mount`);
      assert.equal(before.latched, cell.poppins, `${label} Poppins latch expectation`);
      assert.equal(after.latched, before.latched, `${label} latch never changes after the reveal`);
      assert.equal(after.ff, before.ff, `${label} font stack unchanged after the reveal`);
      assert.equal(after.ff.includes('Swangz Staff Poppins'), cell.poppins, `${label} stack`);
      assert.equal(after.held, false, `${label} hold released`);
      assert.equal(after.vis, 'visible', `${label} shell visible`);
      assert.ok(after.over <= 0, `${label} horizontal overflow ${after.over}`);
      assert.deepEqual(after.shifts, [], `${label} layout shifts: ${JSON.stringify(after.shifts)}`);
      assert.deepEqual(errors, [], label + ' page errors');
      log.push(`${label}: reveal ${Math.round(wait)}ms, poppins ${before.latched}, shifts 0`);
      await c.close();
    }
    console.log(log.join('\n'));
    console.log(`staff-font: ${log.length} cells OK`);
  } finally {
    if (browser) await browser.close();
    if (demo && demo.exitCode === null) { const ended = new Promise(r => demo.once('exit', r)); demo.kill('SIGTERM'); await ended; }
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
