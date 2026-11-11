/* Access requests on the control kit (BRIEF 10.10): one list, one filter row (Status + search), a pager, a row menu,
   the decision at the edge of the row, and the Next step line. UI_OUTPUT also writes the 1440x852 and 390x844
   evidence. Local fixture only. */
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
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_UI_FIXTURE: '1', HUB_REQUESTS_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
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

      // Simple (BRIEF 10.10.7), the default: one sentence with the real number, one next step, five columns, ten rows
      await p.goto(url + '/admin'); await p.evaluate(() => localStorage.clear());
      await open('#/requests', '.u-filter');
      const sentence = (await p.locator('main .ov-sentence').first().innerText()).trim();
      ok(T + 'Simple: the sentence carries the real number', sentence === '2 requests are waiting for a decision.' && sentence.split(/\s+/).length <= 12);
      ok(T + 'Simple: one next step, and it answers the two requests', await p.locator('main .next-step').count() === 1 && await p.locator('main .next-step').getByRole('button', { name: 'Answer 2 requests' }).count() === 1);
      ok(T + 'Simple: one primary, the next step', await p.locator('main .btn.primary').count() === 1);
      ok(T + 'Simple: one panel, one table, no tab strip or chart', await p.locator('main .panel').count() === 1 && await p.locator('main table').count() === 1 && await p.locator('main [role=tablist]').count() === 0 && await p.locator('main .u-chart').count() === 0);
      const heads = (await p.locator('main .u-table thead th').allTextContents()).map(t => t.trim()).filter(Boolean);
      ok(T + 'Simple: five columns, no Why', heads.length <= 5 && !heads.some(t => /^Why/.test(t)));
      ok(T + 'Simple: the two open requests, each with its decision', await rows() === 2 && await p.getByRole('button', { name: 'Grant' }).count() === 2);
      ok(T + 'Simple: a way to Detailed', await p.getByRole('radio', { name: 'Detailed' }).count() + await p.getByRole('button', { name: 'Detailed' }).count() >= 1);
      await noOverflow('Simple'); await axe('Simple'); await small('Simple'); await shot(p, 'requests-simple');
      await p.locator('main .next-step').getByRole('button', { name: 'Answer 2 requests' }).click();
      await p.locator('.guide').first().waitFor();
      ok(T + 'Simple: answering shows each reason', await p.locator('.guide').getByText(/illustrations/).count() >= 1);
      await p.keyboard.press('Escape');

      // L2 (Detailed): the list opens on the open requests
      await open('#/requests?view=detailed', '.u-filter');
      ok(T + 'trail names the page', (await here()) === 'Access requests');
      ok(T + 'no tab strip, one table, no chart', await p.locator('main [role=tablist]').count() === 0 && await p.locator('main table').count() === 1 && await p.locator('main .u-chart').count() === 0);
      ok(T + 'no primary button on the list', await p.locator('main .btn.primary').count() === 0);
      ok(T + 'the open filter is a chip', (await chips()).some(t => t.includes('Open')));
      ok(T + 'two requests are open', await rows() === 2);
      ok(T + 'the Next step names the waiting requests', /2 requests waiting/.test(await p.locator('main .next-step').first().innerText()) && await p.locator('main .next-step').count() === 1);
      ok(T + 'each open row can be declined or granted', await p.getByRole('button', { name: 'Grant' }).count() === 2 && await p.getByRole('button', { name: 'Decline' }).count() === 2);
      await noOverflow('L2'); await axe('L2'); await small('L2'); await shot(p, 'requests');
      // all statuses
      await open('#/requests?view=detailed&state=any', '.u-filter');
      ok(T + 'state=any shows all four with no chip', await rows() === 4 && (await chips()).length === 0);
      ok(T + 'a decided row says who decided', await p.getByText('Approved for the campaign.').count() === 1 || await p.getByText(/by owner@swangzavenue\.com/).count() >= 1);
      await axe('L2 all'); await shot(p, 'requests-all');
      await open('#/requests?view=detailed&state=declined', '.u-filter');
      ok(T + 'declined has one row and the note', await rows() === 1 && await p.getByText(/not renewing that tool/).count() === 1);
      ok(T + 'nothing to decide on a declined row', await p.getByRole('button', { name: 'Grant' }).count() === 0);
      // search and chips
      await open('#/requests?view=detailed', '.u-filter');
      await p.getByRole('searchbox').first().fill('zzz-nothing');
      await p.waitForTimeout(400);
      ok(T + 'a search with no match says so', await p.getByText('Nothing matches').count() === 1);
      await p.getByRole('searchbox').first().fill('illustrations');
      await p.waitForTimeout(400);
      ok(T + 'search finds the reason', await rows() === 1);
      await p.getByRole('searchbox').first().fill('');
      await p.waitForTimeout(400);
      await p.getByRole('button', { name: /Remove filter Status/ }).click();
      ok(T + 'removing the chip shows every status and keeps the address', await rows() === 4 && (await p.evaluate(() => location.hash)).includes('state=any'));
      // row menu
      await p.locator('main .u-table tbody tr').first().getByRole('button', { name: /More actions for/ }).click();
      ok(T + 'the row menu links the record and the tool', await p.locator('.u-menu [role=menuitem]').count() === 2);
      await p.keyboard.press('Escape');
      // decline asks first, and Cancel changes nothing
      await open('#/requests?view=detailed', '.u-filter');
      await p.getByRole('button', { name: 'Decline' }).first().click();
      await p.getByRole('dialog').waitFor();
      await axe('decline dialog'); await shot(p, 'requests-decline');
      await p.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
      const state = async () => (await (await c.request.get(url + '/admin/api/access-requests?state=open', { headers })).json()).open;
      ok(T + 'Cancel leaves both requests open', await state() === 2);
      // grant: the row leaves the open list
      if (theme === 'light' && width === 390) {
        await p.getByRole('button', { name: 'Grant' }).first().click();
        await p.waitForFunction(() => document.querySelectorAll('main .u-table tbody tr').length === 1);
        ok(T + 'granting removes the row from the open list', await state() === 1);
      }
      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`requests.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
