/* Phone touch size on the control kit's lists: at 390x844 every control on People and Tools has a hit area at least 44px
   tall (since 13 Nov a .btn on a phone is 44px visible; console-touch.cjs measures that), and a row's More button is
   44px wide too. Local fixture only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = process.env.GATEWAY_UI_ROOT || path.resolve(__dirname, '../..');
const MIN = 44;
let demo, browser, checks = 0;
(async () => {
  try {
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_UI_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    const info = await new Promise((resolve, reject) => {
      let out = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 60000);
      demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    const url = info.url;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined, args: ['--no-sandbox'] });
    const failures = [];
    for (const theme of ['dark', 'light']) {
      const c = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      const p = await c.newPage();
      for (const hash of ['#/people', '#/tools', '#/tools?show=all']) {
        await p.goto(url + '/admin' + hash); await p.reload();
        await p.locator('.u-filter').waitFor(); await p.waitForLoadState('networkidle');
        const seen = await p.evaluate(min => {
          // The skip link is off screen until focused, and a search box's target is its whole label, measured instead.
          const nodes = [...document.querySelectorAll('a:not(.skip), button, select, summary, [role=button], input:not(.u-search input), label.u-search')];
          const named = n => `${n.tagName.toLowerCase()}.${n.className} "${(n.getAttribute('aria-label') || n.textContent || '').trim().slice(0, 30)}"`;
          const shown = nodes.map(n => [n, n.getBoundingClientRect()]).filter(([n, r]) => r.width && r.height && getComputedStyle(n).visibility !== 'hidden');
          return { count: shown.length, more: shown.filter(([n]) => n.matches('.u-more')).length, sort: shown.filter(([n]) => n.matches('th button')).length,
            bar: shown.filter(([n]) => n.matches('.stb-bar a')).length,
            small: shown.filter(([n, r]) => Math.max(r.height, parseFloat(getComputedStyle(n, '::before').height) || 0) < min || (n.matches('.u-more') && r.width < min)).map(([n, r]) => `${Math.round(r.width)}x${Math.round(r.height)} ${named(n)}`) };
        }, MIN);
        const T = `${theme} ${hash}: `;
        assert.ok(seen.more > 0 && seen.sort > 0 && seen.bar >= 4, T + 'the check found no row menus, sort headers or phone bar: ' + JSON.stringify(seen));
        checks++;
        for (const s of new Set(seen.small)) failures.push(T + s);
        checks += seen.count;
      }
      await c.close();
    }
    // The staff app at 390 (Probe's re-test of main, 13 Nov): here the visible box itself reaches 44px, not only a ::before layer.
    const STAFF = ['.stb-bar a', 'main .btn', '.u-seg button', '.p-index button', 'main a.tlink', '.p-more > summary', '.xf-ask input', '.xf-ask button', '.xf-col :is(a, button)', '.sort select'];
    const found = new Set();
    for (const theme of ['dark', 'light']) {
      const c = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } })).status(), 200);
      const p = await c.newPage();
      for (const hash of ['#/', '#/tools', '#/privacy', '#/devices']) {
        await p.goto(url + '/' + hash); await p.locator('main h1, main h2').first().waitFor(); await p.waitForLoadState('networkidle');
        const seen = await p.evaluate(sels => sels.flatMap(sel => [...document.querySelectorAll(sel)].map(n => [sel, n, n.getBoundingClientRect()])
          .filter(([, n, r]) => r.width && r.height && getComputedStyle(n).visibility !== 'hidden')
          .map(([sel, n, r]) => [sel, Math.round(r.height * 10) / 10, `${Math.round(r.width)}x${Math.round(r.height)} ${sel} "${(n.getAttribute('aria-label') || n.textContent || n.placeholder || '').trim().slice(0, 30)}"`])), STAFF);
        for (const [sel, h, label] of seen) { found.add(sel); checks++; if (h < MIN) failures.push(`staff ${theme} ${hash}: ${label}`); }
      }
      await c.close();
    }
    assert.deepEqual(STAFF.filter(s => !found.has(s)), [], 'the staff check found every kind of control');
    assert.deepEqual(failures, [], 'controls under ' + MIN + 'px');
    console.log(`touch.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
