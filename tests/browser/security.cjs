/* Security on the control kit (BRIEF 10.10): the L1 summary, All signals and Incidents opened already filtered, and one
   incident's record. UI_OUTPUT also writes the 1440x852 and 390x844 evidence. Local fixture only. */
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
    let incident = null;
    for (const [theme, width, height] of cells) {
      const T = `${theme} ${width}: `;
      const shot = async (p, name) => { if (output) await p.screenshot({ path: path.join(output, `${name}-${width}x${height}-${theme}.png`) }); };
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/admin/api/login', { headers, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      if (!incident) {
        const res = await c.request.post(url + '/admin/api/incidents', { headers, data: { title: 'Key found in a request', severity: 'high', summary: 'Fixture case' } });
        assert.ok(res.ok(), 'incident created'); incident = (await res.json()).id;
      }
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

      // L1: four number cards, one short list, no table or tabs, one next step, nothing below the fold on a desktop
      await open('#/security', '.kpis-exact .kpi');
      ok(T + 'L1 has four cards', await p.locator('main .kpis-exact .kpi').count() === 4);
      ok(T + 'L1 has one panel', await p.locator('main .panel').count() === 1);
      ok(T + 'L1 has no table, chart or tab strip', await p.locator('main table, main .u-chart, main [role=tablist]').count() === 0);
      ok(T + 'L1 has at most one primary', await p.locator('main .btn.primary').count() <= 1);
      ok(T + 'L1 has one next step', await p.locator('.next-step').count() === 1);
      ok(T + 'L1 trail names the page', (await here()) === 'Security');
      const listed = await p.locator('main .sec-list li').count();
      ok(T + `L1 list has one to five rows (${listed})`, listed >= 1 && listed <= 5);
      if (width > 1200) {
        const fit = await p.evaluate(() => ({ bottom: document.querySelector('main .panel').getBoundingClientRect().bottom, h: innerHeight }));
        ok(T + `L1 fits above the fold (panel ends at ${fit.bottom} of ${fit.h})`, fit.bottom <= fit.h);
      }
      await noOverflow('L1'); await axe('L1'); await small('L1'); await shot(p, 'security-summary');
      const cards = await p.locator('main .kpis-exact a.kpi, main .kpis-exact .kpi a').evaluateAll(n => n.map(a => a.getAttribute('href')));
      assert.deepEqual(cards, ['#/security?view=signals&days=7&severity=warnings', '#/incidents?status=active', '#/security?view=signals&days=7&type=signin', '#/security?view=signals&days=7&type=credential'], T + 'card links'); checks++;
      const value = async (i) => Number((await p.locator('main .kpis-exact .kpi').nth(i).locator('.value').textContent()).trim());
      const signals = await value(0), incidents = await value(1), signIns = await value(2), credentials = await value(3);
      ok(T + 'the fixture has signals, an incident, a sign-in and a credential', signals > 0 && incidents === 1 && signIns > 0 && credentials > 0);

      await p.getByRole('button', { name: 'Safeguards' }).click();
      await p.locator('.u-sheet, .sheet').filter({ hasText: 'Kill switch' }).first().waitFor();
      ok(T + 'Safeguards shows the settings', await p.getByText('Credentials in requests').count() > 0);
      await p.keyboard.press('Escape');

      // L2: the card's number is the rows the list opens with, as a chip
      await open(cards[0], '.u-filter');
      ok(T + 'L2 trail', (await here()) === 'All signals');
      ok(T + `Signals card ${signals} opens that many rows`, await rows() === signals);
      ok(T + 'L2 shows the severity as a chip', (await chips()).some(t => t.includes('Low and above')));
      ok(T + 'L2 has one table and no chart', await p.locator('main table').count() === 1 && await p.locator('main .u-chart').count() === 0);
      await noOverflow('L2'); await axe('L2'); await small('L2'); await shot(p, 'security-signals');
      await open(cards[2], '.u-filter');
      ok(T + 'Failed sign-ins card count', await rows() === signIns);
      await open(cards[3], '.u-filter');
      ok(T + 'Credentials card count', await rows() === credentials);
      await p.locator('main .u-table tbody tr').first().locator('.u-more').click();
      await p.getByRole('menuitem', { name: 'Details' }).click();
      await p.getByText('Pattern match on the text sent').first().waitFor(); checks++;
      await p.keyboard.press('Escape'); await p.waitForTimeout(400);
      // changing the period fetches again and keeps the address honest
      await open('#/security?days=30&type=signin', '.u-filter');
      ok(T + 'an old link lands on the list, filtered', (await here()) === 'All signals' && (await chips()).some(t => t.includes('30 days')) && (await chips()).some(t => t.includes('Failed sign-ins')));
      await p.locator('.u-chips .u-chip', { hasText: '30 days' }).click();
      await p.waitForLoadState('networkidle');
      ok(T + 'clearing the period updates the address', !(await p.evaluate(() => location.hash)).includes('days=30'));

      // Incidents L2 and L3
      await open(cards[1], '.u-filter');
      ok(T + 'Incidents trail', (await here()) === 'Incidents');
      ok(T + `Open incidents card ${incidents} opens that many rows`, await rows() === incidents);
      await noOverflow('Incidents'); await axe('Incidents'); await small('Incidents'); await shot(p, 'security-incidents');
      await open('#/incidents?status=closed', '.u-filter');
      ok(T + 'the State filter arrives as a chip', (await chips()).some(t => t.includes('Closed')));
      ok(T + 'nothing closed yet', await rows() === 0);
      await open('#/incidents/' + incident, '.ptabs');
      ok(T + 'L3 trail', (await here()) === '#' + incident);
      ok(T + 'L3 has one tab strip of four', await p.locator('main [role=tablist]').count() === 1 && await p.locator('main [role=tab]').count() === 4);
      ok(T + 'L3 has one next step that links on', await p.locator('.next-step a[href*="tab=evidence"]').count() === 1);
      ok(T + 'L3 has at most one primary', await p.locator('main .btn.primary').count() <= 1);
      await noOverflow('L3'); await axe('L3'); await shot(p, 'security-incident');
      await open('#/incidents/' + incident + '?tab=notes', '.ptabs');
      ok(T + 'the Notes tab opens from the address', await p.locator('main textarea').count() === 1);
      ok(T + 'L3 notes tab still has one primary at most', await p.locator('main .btn.primary').count() <= 1);
      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`security.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
