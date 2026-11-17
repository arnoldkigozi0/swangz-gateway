/* Staff app at 390x844 with long names and a long history (Probe, Nov 13): a purchase card whose tool name is ~50
   characters wraps inside the card instead of widening it; Your creations counts every creation and reaches the older
   ones with Show older; the Tools Show control keeps its three options on one row. 1440 is checked for the same pages
   to stay unchanged in kind (no sideways scroll). Local fixture only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const root = process.env.GATEWAY_UI_ROOT || path.resolve(__dirname, '../..');
let demo, browser, checks = 0;
const ok = (name, cond) => { assert.ok(cond, name); checks++; };
(async () => {
  try {
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_STAFF_PHONE_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    const info = await new Promise((resolve, reject) => {
      let out = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 60000);
      demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    const url = info.url;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined, args: ['--no-sandbox'] });
    for (const [theme, width, height] of [['dark', 390, 844], ['light', 390, 844], ['dark', 640, 900], ['light', 640, 900], ['dark', 1440, 852]]) {
      const T = `${theme} ${width}: `;
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } })).status(), 200);
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      const axe = async (name) => { const r = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); assert.deepEqual(r.violations.map(v => v.id + ' ' + v.nodes.map(n => n.target).join(',')), [], T + name + ' axe'); checks++; };
      const noOverflow = async (name) => ok(T + name + ' has no sideways page scroll', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const open = async (hash, wait) => { await p.goto(url + '/' + hash); await p.locator(wait).first().waitFor(); await p.waitForLoadState('networkidle'); };
      const targets = async (name, locator) => {
        const short = await locator.evaluateAll(nodes => nodes.filter(n => {
          const r = n.getBoundingClientRect(); return r.height && (r.height < 44 || r.width < 44);
        }).map(n => n.getAttribute('aria-label') || n.textContent.trim()));
        assert.deepEqual(short, [], T + name + ' has 44px targets'); checks++;
      };

      // 1. Requests > Tool & subscription purchases: the long tool name wraps and the card never scrolls sideways
      await open('#/requests?view=procurement', '.hub-pagination');
      if (width <= 640) {
        await p.keyboard.press('Tab');
        ok(T + 'the skip link is the first keyboard stop', await p.locator('.skip').evaluate(n => document.activeElement === n));
        await targets('skip link', p.locator('.skip'));
        await p.keyboard.press('Enter');
        ok(T + 'the skip link focuses the page', await p.locator('main').evaluate(n => document.activeElement === n));
      }
      const card = await p.evaluate(() => {
        const wrap = document.querySelector('main .u-table-wrap'), td = document.querySelector('main .u-table td.lead'), btn = td.querySelector('.btn');
        const label = document.querySelector('main .u-table td[data-label]');
        return { sw: wrap.scrollWidth, cw: wrap.clientWidth, name: btn.textContent, fits: btn.scrollWidth <= btn.clientWidth + 1, btnLeft: btn.getBoundingClientRect().left,
          labelLeft: label.getBoundingClientRect().left, h: btn.getBoundingClientRect().height, pager: document.querySelector('.hub-pagination span').textContent };
      });
      ok(T + 'the purchase table does not scroll sideways', card.sw <= card.cw + 1);
      ok(T + 'the long tool name is shown whole', card.name.includes('long name for wrapping checks') && card.fits);
      if (width <= 640) ok(T + 'the name sits flush with the labels below it, at least 44px tall', Math.abs(card.btnLeft - card.labelLeft) <= 2 && card.h >= 44);
      ok(T + 'one purchase reads as 1 record', card.pager.startsWith('1 record ·'));
      await noOverflow('Purchases'); await axe('Purchases');

      // 2. Studio > Your creations: the count is all 40, and Show older reaches every one, once
      await open('#/studio?view=mine', '.creation');
      ok(T + 'the count is every creation, not the first page', (await p.locator('.vt-n').allTextContents()).includes('40'));
      ok(T + 'the first page shows 12', await p.locator('.creations .creation').count() === 12);
      while (await p.locator('.creations-more:not([hidden]) button').count()) {
        const before = await p.locator('.creations .creation').count();
        await p.locator('.creations-more button').click();
        await p.waitForFunction(n => document.querySelectorAll('.creations .creation').length > n, before);
      }
      const ids = await p.locator('.creations .creation').evaluateAll(n => n.map(x => Number(x.dataset.id)));
      ok(T + 'Show older reaches all 40, newest first, none twice', ids.length === 40 && new Set(ids).size === 40 && ids.every((v, i) => !i || ids[i - 1] > v));
      ok(T + 'Show older goes away after the oldest', await p.locator('.creations-more').isHidden());
      ok(T + 'a failed creation says so', (await p.locator('.creation-state.bad').count()) === 40);
      await noOverflow('Your creations'); await axe('Your creations');

      // 3. Tools: Everything / Available to me / Others share one row
      await open('#/tools', '.toolbar .u-seg button');
      const tops = await p.locator('.toolbar .u-seg button').evaluateAll(n => n.map(x => Math.round(x.getBoundingClientRect().top)));
      ok(T + 'the three Show options share one row', tops.length === 3 && new Set(tops).size === 1);
      if (width <= 640) ok(T + 'each Show option is at least 44px tall', (await p.locator('.toolbar .u-seg button').evaluateAll(n => n.map(x => x.getBoundingClientRect().height))).every(h => h >= 44));
      await noOverflow('Tools'); await axe('Tools');

      if (width <= 640) {
        // Tool details live outside the shell; both Close controls and Open still need phone targets.
        const trigger = p.getByRole('button', { name: 'Canva — details', exact: true });
        await trigger.click();
        const drawer = p.getByRole('dialog', { name: 'Canva details', exact: true });
        await drawer.waitFor();
        await targets('tool drawer actions', drawer.locator('header .btn, footer .btn'));
        await p.keyboard.press('Tab');
        ok(T + 'drawer keyboard focus stays inside', await drawer.evaluate(n => n.contains(document.activeElement)));
        await p.keyboard.press('Escape');
        await drawer.waitFor({ state: 'detached' });
        ok(T + 'Escape returns focus to the tool', await trigger.evaluate(n => document.activeElement === n));

        for (const route of ['#/requests', '#/devices', '#/weekly']) {
          await open(route, '.vtabs [role=tab], .ptabs [role=tab]');
          await targets(route + ' tabs', p.locator('main :is(.vtabs, .ptabs) [role=tab]'));
          await noOverflow(route);
        }
        await open('#/privacy', '.p-sections summary');
        await targets('Privacy summaries', p.locator('.p-sections summary'));
        const summary = p.locator('.p-sections summary').filter({ hasText: 'Weekly reporting and your declarations' });
        await summary.focus();
        await p.keyboard.press('Enter');
        ok(T + 'the Privacy disclosure opens with the keyboard', await summary.evaluate(n => n.parentElement.open));
        await p.keyboard.press('Enter');
        ok(T + 'the Privacy disclosure closes with the keyboard', await summary.evaluate(n => !n.parentElement.open));
        await noOverflow('Privacy'); await axe('Privacy');
      }

      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`staff phone: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close();
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
