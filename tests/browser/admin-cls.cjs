/* Cold loads of the console must not shift: the version line at the foot of the page sits under content that
   arrives late (Activity, Settings). Every layout-shift entry is recorded with its source; none is allowed.
   Also checks the line is shown once the page is still. Local synthetic fixture only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
let demo, browser;
(async () => {
  try {
    demo = spawn('python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
    const url = await new Promise((resolve, reject) => {
      let out = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 30000);
      demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0]).url); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined });
    let cells = 0;
    for (const [width, height] of [[1440, 852], [390, 844]]) for (const hash of ['#/', '#/activity', '#/settings', '#/people', '#/health']) {
      const c = await browser.newContext({ viewport: { width, height } });
      await c.addInitScript(() => {
        window.__shifts = [];
        new PerformanceObserver(l => l.getEntries().forEach(e => window.__shifts.push({ v: e.value,
          s: (e.sources || []).map(s => (s.node ? s.node.nodeName + '.' + (s.node.className && s.node.className.baseVal === undefined ? s.node.className : '') : 'null')) })))
          .observe({ type: 'layout-shift', buffered: true });
      });
      const login = await c.request.post(url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      assert.equal(login.status(), 200);
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      await p.goto(url + '/admin' + hash);
      await p.waitForLoadState('networkidle');
      await p.waitForTimeout(2500);
      const got = await p.evaluate(() => { const f = document.querySelector('.build-foot');
        return { shifts: window.__shifts, text: f && f.textContent, shown: f && getComputedStyle(f).visibility }; });
      const label = `${width} ${hash}`;
      assert.deepEqual(got.shifts, [], `${label} layout shifts: ${JSON.stringify(got.shifts)}`);
      assert.match(got.text || '', /^Swangz AI Hub \d+\.\d+\.\d+ · /, label + ' version line');
      assert.equal(got.shown, 'visible', label + ' version line shown once the page is still');
      assert.deepEqual(errors, [], label + ' page errors');
      cells += 1; await c.close();
    }
    console.log(`admin-cls: ${cells} cells OK`);
  } finally {
    if (browser) await browser.close();
    if (demo && demo.exitCode === null) { const ended = new Promise(r => demo.once('exit', r)); demo.kill('SIGTERM'); await ended; }
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
