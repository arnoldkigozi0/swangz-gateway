/* Models on the control kit (BRIEF 10.10): a trail, one filter row (search, status) with chips, one table with a pager,
   a row menu, one primary (Register a model), and old ?status= links still landing filtered. UI_OUTPUT also writes the
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

      await open('#/models', '.u-filter');
      ok(T + 'trail names the page', (await here()) === 'Models');
      ok(T + 'one table, no chart, no tab strip', await p.locator('main table').count() === 1 && await p.locator('main .u-chart, main [role=tablist]').count() === 0);
      ok(T + 'one primary button', await p.locator('main .btn.primary').count() === 1);
      // Simple (BRIEF 10.10.7, the default): one sentence with the real number, one next step, five columns, no notes line
      const sentence = (await p.locator('.ov-sentence').textContent()).trim();
      ok(T + `Simple's sentence carries a number (${sentence})`, /\d/.test(sentence) && sentence.split(/\s+/).length <= 12);
      ok(T + 'Simple has one next-step button', await p.locator('.next-step .btn').count() === 1);
      ok(T + 'Simple shows five columns', width < 640 || await p.locator('main .u-table thead th').count() === 5);
      ok(T + 'Simple has no notes line', await p.locator('main .list-meta').count() === 0);
      const all = await rows();
      ok(T + `the fixture has models (${all})`, all >= 1);
      if (width <= 640) {
        // Simple on a phone: the five most used, then "See all N" opens the rest (one screen per block)
        const seeAll = p.locator('main .see-all-row .btn');
        ok(T + `phone Simple shows five and See all (${all})`, all === 5 && /^See all \d+$/.test((await seeAll.innerText()).trim()));
        const total = Number((await seeAll.innerText()).match(/\d+/)[0]);
        await small('phone short list'); await seeAll.click();
        ok(T + 'See all shows the rest', await rows() === Math.min(total, 10) && await p.locator('main .see-all-row').count() === 0);
        await open('#/models', '.u-filter');
      }
      await noOverflow('L2'); await axe('L2'); await small('L2'); await shot(p, 'models');
      await p.getByRole('searchbox').first().fill('zzz-no-such-model');
      await p.getByText('No models match').waitFor();
      ok(T + 'a search with no match says so', await rows() === 0);
      ok(T + 'the search is in the address', (await p.evaluate(() => location.hash)).includes('q=zzz-no-such-model'));
      await p.getByRole('searchbox').first().fill('');
      await p.waitForFunction(n => document.querySelectorAll('main .u-table tbody tr').length === n, all);
      checks++;
      // the row menu
      await p.locator('main .u-table tbody tr').first().locator('.u-more').click();
      const items = await p.locator('.u-pop-menu [role=menuitem]').allTextContents();
      ok(T + 'the row menu offers a rule and the requests', items.length >= 2 && items.some(t => /rule/i.test(t)) && items.some(t => t.includes('Requests using it')));
      await p.locator('.u-pop-menu [role=menuitem]', { hasText: /rule/i }).first().click();
      await p.getByRole('dialog').waitFor();
      await p.keyboard.press('Escape'); await p.waitForTimeout(400);
      await open('#/models?view=detailed', '.u-filter');
      ok(T + 'Detailed keeps the notes line and every column', await p.locator('main .list-meta').count() === 1 && (width < 640 || await p.locator('main .u-table thead th').count() === 8));
      await noOverflow('Detailed'); await axe('Detailed');
      // old links arrive as a chip
      await open('#/models?status=unlisted', '.u-filter');
      ok(T + 'the status arrives as a chip', (await p.locator('.u-chips .u-chip').allTextContents()).some(t => t.includes('Unlisted')));
      await open('#/models?status=disabled', '.u-filter');
      ok(T + 'a status with no models shows the chip and an empty list', await rows() === 0 && (await p.locator('.u-chips .u-chip').allTextContents()).some(t => t.includes('Disabled')));
      await noOverflow('L2 filtered'); await axe('L2 filtered'); await shot(p, 'models-filtered');
      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`models.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
