/* Devices on the control kit (BRIEF 10.10): the list (one tab strip, one filter row, a pager and a row menu) and one
   device's record (a trail, a Next step, six tabs at most, Revoke as the only danger). UI_OUTPUT also writes the
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

      // L2: the list
      await open('#/devices', '.u-filter');
      ok(T + 'trail names the page', (await here()) === 'Devices');
      ok(T + 'one tab strip of two', await p.locator('main [role=tablist]').count() === 1 && await p.locator('main [role=tab]').count() === 2);
      ok(T + 'one table, no chart', await p.locator('main table').count() === 1 && await p.locator('main .u-chart').count() === 0);
      ok(T + 'no primary button on the list', await p.locator('main .btn.primary').count() === 0);
      const all = await rows();
      ok(T + 'the fixture has a device', all >= 1);
      await noOverflow('L2'); await axe('L2'); await small('L2'); await shot(p, 'devices');
      await p.getByRole('searchbox').first().fill('zzz-nothing');
      await p.waitForTimeout(400);
      ok(T + 'a search with no match says so', await p.getByText('No devices match').count() === 1);
      await p.getByRole('searchbox').first().fill('');
      await p.waitForTimeout(400);
      ok(T + 'clearing the search brings the rows back', await rows() === all);
      await open('#/devices?state=revoked', '.u-filter');
      ok(T + 'the status filter arrives as a chip', (await chips()).some(t => t.includes('Revoked')));
      ok(T + 'nothing is revoked yet', await rows() === 0);
      await open('#/devices?tab=browsers', '.ptabs');
      await noOverflow('Browsers'); await axe('Browsers');

      // the row menu: open the record, their activity, revoke (not pressed here)
      await open('#/devices', '.u-filter');
      await p.locator('main .u-table tbody tr').first().locator('.u-more').click();
      const items = await p.locator('.u-pop-menu [role=menuitem]').allTextContents();
      ok(T + 'the row menu offers the record, activity and revoke', items.length === 3 && items[0].includes('record') && items[2].includes('Revoke'));
      await p.keyboard.press('Escape');

      // L3: the record
      await open('#/devices/' + info.key, '.ptabs');
      ok(T + 'L3 trail', (await p.locator('.crumbs .crumb-here, .console-trail .crumb-here').first().textContent()).length > 0);
      ok(T + 'L3 has one tab strip, six tabs at most', await p.locator('main [role=tablist]').count() === 1 && await p.locator('main [role=tab]').count() <= 6);
      ok(T + 'L3 has a Next step that links to the flagged tab', await p.locator('.next-step a[href*="tab=flagged"]').count() === 1);
      ok(T + 'L3 has no stat tiles', await p.locator('main .statline, main .stat').count() === 0);
      ok(T + 'L3 has Revoke as its only danger button', await p.locator('main .btn.danger').count() === 1);
      ok(T + 'L3 has no primary button', await p.locator('main .btn.primary').count() === 0);
      ok(T + 'Overview shows the key facts', await p.getByText('Only the key\'s ends are ever shown').count() === 1);
      await noOverflow('L3'); await axe('L3'); await small('L3'); await shot(p, 'device');
      for (const tab of ['usage', 'activity', 'flagged', 'sessions', 'addresses']) {
        await open('#/devices/' + info.key + '?tab=' + tab, '.ptabs');
        ok(T + tab + ' tab opens from the address', await p.locator('main [role=tab][aria-selected=true]').count() === 1);
        await noOverflow(tab);
      }
      await axe('L3 flagged'); await shot(p, 'device-flagged');
      await p.getByRole('button', { name: 'Revoke device' }).click();
      await p.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
      ok(T + 'Cancel leaves the key alone', (await (await c.request.get(url + '/admin/api/devices/' + info.key, { headers })).json()).state !== 'revoked');
      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`devices.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
