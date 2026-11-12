/* Money on the control kit (BRIEF 10.10): the L1 summary, the three L2 lists its cards open already filtered, Spend
   reports and one report. UI_OUTPUT also writes the 1440x852 and 390x844 evidence. Local fixture only. */
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
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_UI_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    const info = await new Promise((resolve, reject) => {
      let out = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 60000);
      demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    const url = info.url;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined, args: ['--no-sandbox'] });
    const headers = { 'x-gateway-admin': '1' };
    const cells = [['dark', 1440, 852], ['light', 1440, 852], ['dark', 390, 844], ['light', 390, 844]];
    let seeded = false;
    for (const [theme, width, height] of cells) {
      const T = `${theme} ${width}: `;
      const shot = async (p, name) => { if (output) await p.screenshot({ path: path.join(output, `${name}-${width}x${height}-${theme}.png`) }); };
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/admin/api/login', { headers, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      if (!seeded) {
        // one plan that renews in ten days, so the Renewing card has something to count
        const res = await c.request.put(url + '/admin/api/subscriptions/claude', { headers, data: { state: 'active', monthly_cost: 30, seats: 5, renews_on: new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10) } });
        assert.equal(res.status(), 200); seeded = true;
      }
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      const axe = async (name) => { const r = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); assert.deepEqual(r.violations.map(v => v.id + ' ' + v.nodes.map(n => n.target).join(',')), [], T + name + ' axe'); checks++; };
      const noOverflow = async (name) => ok(T + name + ' has no sideways page scroll', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const open = async (hash, wait) => { await p.goto(url + '/admin' + hash); await p.reload(); await p.locator(wait).first().waitFor(); await p.waitForLoadState('networkidle'); };
      const hash = () => p.evaluate(() => location.hash);
      const here = async () => (await p.locator('.crumb-here').first().textContent());
      const unclipped = async (name) => { if (width > 1200) ok(T + name + ' shows the current page in full', await p.locator('.console-trail .crumb-here').evaluate(n => n.scrollWidth <= n.clientWidth + 1)); };
      const small = async (name) => {
        if (width > 640) return;
        const bad = await p.evaluate(() => [...document.querySelectorAll('.top-actions .btn, .panel-actions .btn, .list-meta .btn')].filter(b => b.getBoundingClientRect().height < 44).map(b => b.textContent));
        assert.deepEqual(bad, [], T + name + ' touch size'); checks++;
      };

      // Simple (BRIEF 10.10.7, the default): one sentence with the real number, one next-step button, two blocks, no cards
      await open('#/licences', '.ov-sentence');
      ok(T + 'Simple is the default (no number cards)', await p.locator('main .kpis-exact').count() === 0);
      const sentence = (await p.locator('.ov-sentence').textContent()).trim();
      ok(T + `Simple's sentence carries a number (${sentence})`, /\d/.test(sentence) && sentence.split(/\s+/).length <= 14);
      ok(T + 'Simple has one next-step button', await p.locator('.next-step .btn').count() === 1);
      ok(T + 'Simple has at most three blocks', await p.locator('main .page > .panel, main .page > .kpis').count() <= 3);
      ok(T + 'Simple has at most one primary', await p.locator('main .btn.primary').count() <= 1);
      ok(T + 'Simple has no table', await p.locator('main table').count() === 0);
      const nums = await p.locator('main .ov-num').evaluateAll(n => n.map(a => a.getAttribute('href')));
      assert.deepEqual(nums, ['#/licences?tab=spend&range=30d', '#/licences?tab=licences&show=paid', '#/licences?tab=licences&show=idle', '#/licences?tab=renewals&show=soon'], T + 'Simple number links'); checks++;
      if (width > 1200) {
        const bottom = await p.evaluate(() => Math.max(...[...document.querySelectorAll('main .page > .panel')].map(n => n.getBoundingClientRect().bottom)));
        ok(T + `Simple fits above the fold (ends at ${bottom} of ${height})`, bottom <= height);
      }
      await noOverflow('Simple'); await axe('Simple'); await small('Simple'); await shot(p, 'money-simple');

      // Detailed (L1): four number cards, one chart, no table, one next step, and nothing below the fold on a desktop
      await open('#/licences?view=detailed', '.kpis-exact .kpi');
      ok(T + 'L1 has four cards', await p.locator('main .kpis-exact .kpi').count() === 4);
      ok(T + 'L1 has one panel and one chart', await p.locator('main .panel').count() === 1 && await p.locator('main .u-chart').count() === 1);
      ok(T + 'L1 has no table or tab strip', await p.locator('main table, main [role=tablist]').count() === 0);
      ok(T + 'L1 has at most one primary', await p.locator('main .btn.primary').count() <= 1);
      ok(T + 'L1 has one next step', await p.locator('.next-step').count() === 1);
      ok(T + 'L1 trail names the page', (await here()) === 'Licences & spend');
      if (width > 1200) {
        const fit = await p.evaluate(() => { const m = document.querySelector('.page').getBoundingClientRect(); const last = document.querySelector('main .panel').getBoundingClientRect(); return { bottom: last.bottom, h: innerHeight, top: m.top }; });
        ok(T + `L1 fits above the fold (panel ends at ${fit.bottom} of ${fit.h})`, fit.bottom <= fit.h);
      }
      await noOverflow('L1'); await axe('L1'); await small('L1'); await shot(p, 'money-summary');
      const cards = await p.locator('main .kpis-exact a.kpi, main .kpis-exact .kpi a').evaluateAll(n => n.map(a => a.getAttribute('href')));
      assert.deepEqual(cards, ['#/licences?tab=spend&range=30d', '#/licences?tab=licences&show=paid', '#/licences?tab=licences&show=idle', '#/licences?tab=renewals&show=soon'], T + 'card links'); checks++;
      const value = async (i) => (await p.locator('main .kpis-exact .kpi').nth(i).locator('.value').textContent()).trim();
      const idleSeats = Number(await value(2)), renewing = Number(await value(3));
      ok(T + 'the fixture has an idle seat and a renewal', idleSeats > 0 && renewing === 1);

      // Licences: kit filter bar, one table, and the card's filter arrives as a chip
      await open('#/licences?tab=licences&show=idle', '.u-filter');
      ok(T + 'Licences is one table with no tabs or charts', await p.locator('main table').count() === 1 && await p.locator('main [role=tablist], main .u-chart, main .seg').count() === 0);
      ok(T + 'the card filter shows as a chip', await p.locator('.u-chip[data-filter=show]').count() === 1);
      ok(T + 'Licences trail', (await here()) === 'Licences');
      const shownIdle = await p.locator('.idle > span').count();
      ok(T + `the list holds the seats the card counted (${shownIdle} of ${idleSeats})`, shownIdle === idleSeats);
      ok(T + 'every row has one More button', await p.locator('main tbody button[aria-label^="More actions for"]').count() === await p.locator('main tbody tr').count());
      await noOverflow('Licences'); await axe('Licences'); await small('Licences'); await shot(p, 'money-licences');
      const search = p.locator('.u-filter input[type=search]');
      await search.fill('zzz-no-such-tool');
      await p.getByText('No licences match').waitFor();
      ok(T + 'search goes in the address', (await hash()).includes('q=zzz'));
      await search.fill('');
      await p.locator('main table').waitFor();

      // What cost us money: one table; By is a kit filter; the chart stays on the L1
      await open('#/licences?tab=spend&range=30d', '.u-filter');
      ok(T + 'Spend is one table with no chart or segmented control', await p.locator('main table').count() === 1 && await p.locator('main .u-chart, main .seg, main details').count() === 0);
      ok(T + 'Spend trail', (await here()) === 'What cost us money?');
      await unclipped('Spend');
      await noOverflow('Spend'); await axe('Spend'); await small('Spend'); await shot(p, 'money-spend');
      await p.locator('.u-filter .u-select[data-filter=by]').click();
      await p.locator('.u-pop-select [role=option]').filter({ hasText: /^Model/ }).click();
      await p.locator('.u-chip[data-filter=by]').waitFor();
      ok(T + 'By goes in the address and keeps the range', (await hash()).includes('by=model') && (await hash()).includes('range=30d'));
      ok(T + 'the table is by model', (await p.locator('main thead th').first().textContent()).includes('Model'));
      await open('#/licences?tab=spend&range=30d&by=model', '.u-chip[data-filter=by]');
      ok(T + 'By survives a reload', (await p.locator('main thead th').first().textContent()).includes('Model'));
      await p.getByRole('button', { name: 'How spend is worked out' }).click();
      await p.locator('.u-sheet .method').waitFor();
      ok(T + 'the method sheet keeps its four notes', await p.locator('.u-sheet .method > div').count() === 4);
      await axe('method sheet'); await shot(p, 'money-spend-method');
      await p.locator('.u-sheet-foot .btn').first().click();
      await p.locator('.u-sheet').waitFor({ state: 'detached' });

      // Renewals: the card's count is the filtered list
      await open('#/licences?tab=renewals&show=soon', '.u-filter');
      ok(T + `Renewals lists what the card counted (${renewing})`, await p.locator('main tbody tr').count() === renewing);
      ok(T + 'Renewals is one table', await p.locator('main table').count() === 1);
      ok(T + 'Renewals trail', (await here()) === 'Renewals');
      await noOverflow('Renewals'); await axe('Renewals'); await small('Renewals'); await shot(p, 'money-renewals');

      // Spend reports: one card list; a report sits under it in the trail
      await open('#/reports', '.report-list a');
      const total = await p.locator('.report-list a').count();
      ok(T + 'Reports is one list', total >= 9 && await p.locator('main .report-list').count() === 1 && await p.locator('main table').count() === 0);
      ok(T + 'Reports trail', (await here()) === 'Spend reports');
      await noOverflow('Reports'); await axe('Reports'); await small('Reports'); await shot(p, 'money-reports');
      await p.locator('.u-filter .u-select[data-filter=group]').click();
      await p.locator('.u-pop-select [role=option]').filter({ hasText: /^Trust/ }).click();
      await p.locator('.u-chip[data-filter=group]').waitFor();
      ok(T + 'Group narrows the list and goes in the address', await p.locator('.report-list a').count() === 2 && (await hash()).includes('group=Trust'));
      await p.locator('.report-list a').first().click();
      await p.locator('main .u-range').waitFor();
      ok(T + 'a report has one primary', await p.locator('main .btn.primary, .top-actions .btn.primary').count() === 1);
      await unclipped('report');
      await noOverflow('report'); await axe('report'); await small('report'); await shot(p, 'money-report');
      await p.goBack();
      await p.locator('.u-chip[data-filter=group]').waitFor();
      ok(T + 'Back returns with the filter kept', (await hash()).includes('group=Trust') && await p.locator('.report-list a').count() === 2);

      // links from when these were tabs still land on the same content
      await open('#/licences?tab=spend', '.u-filter');
      ok(T + 'the old spend link opens the list', (await here()) === 'What cost us money?');

      if (theme === 'light' && width === 390) {
        // Reclaim still works from the list, and the count drops
        await open('#/licences?tab=licences&show=idle', '.idle button');
        await p.locator('.idle button').first().click();
        await p.getByRole('button', { name: 'Take it back' }).click();
        await p.waitForFunction(n => document.querySelectorAll('.idle > span').length === n - 1, idleSeats);
        ok(T + 'Reclaim frees the seat and keeps the filter', (await hash()).includes('show=idle'));
      }
      assert.deepEqual(errors, [], T + 'no page errors'); checks++;
      await c.close();
    }
    console.log(`money.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
