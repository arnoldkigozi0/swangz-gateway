/* The Audit log on the control kit (BRIEF 10.10): a trail under Security, one filter row (search, period, who, outcome,
   area) with chips, one table with a pager, and old links still landing filtered. UI_OUTPUT also writes the
   1440x852 and 390x844 evidence. Local fixture only. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const root = process.env.GATEWAY_UI_ROOT || path.resolve(__dirname, '../..');
const output = process.env.UI_OUTPUT || '';
if (output) fs.mkdirSync(output, { recursive: true });
let demo, browser, checks = 0;
const ok = (name, cond) => { assert.ok(cond, name); checks++; };
(async () => {
  try {
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_UI_FIXTURE: '1', HUB_SECURITY_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    const info = await new Promise((resolve, reject) => {
      let out = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 60000);
      demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    const url = info.url;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined, args: ['--no-sandbox'] });
    const headers = { 'x-gateway-admin': '1' };
    const cells = [['dark', 1440, 852], ['light', 1440, 852], ['dark', 390, 844], ['light', 390, 844]];
    for (const [theme, width, height] of cells) {
      const T = `${theme} ${width}: `;
      const shot = async (p, name) => { if (output) await p.screenshot({ path: path.join(output, `${name}-${width}x${height}-${theme}.png`) }); };
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/admin/api/login', { headers, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      const axe = async (name) => { const r = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); assert.deepEqual(r.violations.map(v => v.id + ' ' + v.nodes.map(n => n.target).join(',')), [], T + name + ' axe'); checks++; };
      const noOverflow = async (name) => ok(T + name + ' has no sideways page scroll', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const open = async (hash, wait) => { await p.goto(url + '/admin' + hash); await p.reload(); await p.locator(wait).first().waitFor(); await p.waitForLoadState('networkidle'); };
      const here = async () => (await p.locator('.crumb-here').first().textContent());
      const rows = () => p.locator('main .u-table tbody tr').count();
      const chips = () => p.locator('.u-chips .u-chip').allTextContents();
      const small = async (name) => {
        if (width > 640) return;
        const bad = await p.evaluate(() => [...document.querySelectorAll('main .btn, main .u-more, main .sec-link, main .u-table th button')].filter(n => { const r = n.getBoundingClientRect(); return r.height && r.height < 44; }).map(n => n.textContent));
        assert.deepEqual(bad, [], T + name + ' touch size'); checks++;
      };

      await open('#/audit', '.u-filter');
      ok(T + 'trail names the page', (await here()) === 'Audit log');
      ok(T + 'the trail starts at Security', await p.locator('.crumbs a[href="#/security"], .console-trail a[href="#/security"]').count() >= 1);
      ok(T + 'one table, no chart, no tab strip', await p.locator('main table').count() === 1 && await p.locator('main .u-chart, main [role=tablist]').count() === 0);
      ok(T + 'no primary button', await p.locator('main .btn.primary').count() === 0);
      const all = await rows();
      ok(T + `the fixture has audit entries (${all})`, all >= 1);
      ok(T + 'the old Load older button waits until there are more', await p.getByRole('button', { name: 'Load older' }).isHidden());
      await noOverflow('L2'); await axe('L2'); await small('L2'); await shot(p, 'audit');
      if (width >= 1440) {
        // a long list scrolls inside its panel and the page itself does not: one vertical scrollbar at 1440x852
        await p.evaluate(() => { const b = document.querySelector('main .u-table tbody'); const r = b.querySelector('tr'); for (let i = 0; i < 80; i++) b.append(r.cloneNode(true)); });
        const m = await p.evaluate(() => { const w = document.querySelector('main .u-table-wrap'); return { inner: w.scrollHeight > w.clientHeight + 1, page: document.documentElement.scrollHeight - innerHeight }; });
        ok(T + `a long list scrolls inside its panel (${JSON.stringify(m)})`, m.inner);
        ok(T + 'and the page itself does not scroll', m.page <= 1);
        await open('#/audit', '.u-filter');
      }
      await p.getByRole('searchbox').first().fill('zzz-nothing-like-this');
      await p.getByText('No audit entries').waitFor();
      ok(T + 'a search with no match says so', await rows() === 0);
      ok(T + 'the search is in the address', (await p.evaluate(() => location.hash)).includes('q=zzz-nothing-like-this'));
      await p.getByRole('searchbox').first().fill('');
      await p.waitForFunction(n => document.querySelectorAll('main .u-table tbody tr').length === n, all);
      checks++;

      // old links and filters arrive as chips
      await open('#/audit?outcome=denied&area=govern&range=7d', '.u-filter');
      const chip = await p.locator('.u-chips .u-chip').allTextContents();
      ok(T + 'outcome, area and period arrive as chips', ['Refused', 'Govern', '7 days'].every(w => chip.some(t => t.includes(w))));
      await open('#/audit?correlation=person:1', '.u-filter');
      ok(T + 'an About link arrives as a chip', (await p.locator('.u-chips .u-chip').allTextContents()).some(t => t.includes('person:1')));
      await p.locator('.u-chips .u-chip', { hasText: 'person:1' }).click();
      await p.waitForLoadState('networkidle');
      ok(T + 'removing the chip drops it from the address', !(await p.evaluate(() => location.hash)).includes('correlation'));
      await open('#/audit?q=signed', '.u-filter');
      ok(T + 'a link from the timeline lands searched', await p.getByRole('searchbox').first().inputValue() === 'signed');
      await noOverflow('L2 filtered'); await axe('L2 filtered'); await shot(p, 'audit-filtered');
      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`audit.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
