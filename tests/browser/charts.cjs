/* Focused chart checks for SUI.line: empty data is an honest empty state, real data is unchanged.
   Run like the other browser checks: NODE_PATH must reach a tooling dir with playwright (never installed in the repo).
   Starts tests/browser/demo.py (test database, FakeUpstream), signs in to the console and calls SUI.line in the page. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const results = { checks: [], errors: [] };
const ok = (label, v) => { assert.ok(v, label); results.checks.push(label); };

/* Overview as an L1 (docs/UI.md "Page levels"), at the acceptance sizes: no scroll at 1440x852, and every card opens
   its filtered list. Findings are gathered so one CI run reports all of them; screenshots land in the CI artifact. */
const fs = require('node:fs');
const { AxeBuilder } = require('@axe-core/playwright');
const OVERVIEW_OUT = process.env.OVERVIEW_OUT || '/tmp/swangz-hub-overview-l1';
const CARDS = ['#/licences?tab=spend&range=30d', '#/activity?tab=ai&range=30d', '#/activity?tab=usage&range=today&by=person', '#/security?view=signals&days=7&severity=warnings', '#/attention', '#/live'];
const overviewFindings = [];
async function overviewPass(page, url, theme) {
  for (const [width, height, vname] of [[1440, 852, 'desktop'], [390, 844, 'mobile']]) {
    const name = `${vname}-${theme}`, say = (m) => overviewFindings.push(`${name}: ${m}`);
    try {
      const open = async () => {
        await page.goto(url + '/admin#/?view=detailed'); await page.reload();
        await page.waitForSelector('main h1');
        await page.waitForFunction(() => !document.querySelector('main .u-skel-rows, main .u-skel-cards'));
      };
      await page.setViewportSize({ width, height });
      await open();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(800);
      const m = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - innerWidth, tall: document.documentElement.scrollHeight - innerHeight,
        cards: [...document.querySelectorAll('main a.kpi-link')].map(a => a.getAttribute('href')),
        primaries: [...document.querySelectorAll('main .btn.primary')].filter(b => b.getBoundingClientRect().width).length,
        next: document.querySelector('main .top')?.textContent.includes('Next step'),
        trails: [...document.querySelectorAll('.console-trail, main .top > .crumbs.in-bar')].filter(t => t.getBoundingClientRect().width).length }));
      if (m.trails !== 1) say(`${m.trails} trails showing`);
      if (m.overflow > 0) say(`page scrolls sideways by ${m.overflow}px`);
      if (vname === 'desktop' && m.tall > 0) say(`page scrolls by ${m.tall}px at 1440x852`);
      if (JSON.stringify(m.cards) !== JSON.stringify(CARDS)) say('card links: ' + JSON.stringify(m.cards));
      if (m.primaries !== 1) say(`${m.primaries} primary buttons`);
      if (!m.next) say('no Next step line');
      if (vname === 'mobile') {
        // the kit's touch rule: every control on the page, not only the ones found so far; a link inside a sentence is exempt;
        // a .btn's target is its 44px ::before hit layer (Probe D3), so the larger of the box and that layer is measured
        const small = await page.evaluate(() => [...document.querySelectorAll('main a, main button')].filter(n => !n.closest('p, .hint')).map(n => [n, n.getBoundingClientRect()])
          .filter(([n, r]) => r.width && Math.max(r.height, parseFloat(getComputedStyle(n, '::before').height) || 0) < 44).map(([n, r]) => `${n.className || n.tagName} "${(n.textContent || n.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`));
        for (const s of small) say('under 44px: ' + s);
      }
      await page.screenshot({ path: path.join(OVERVIEW_OUT, `${name}-detailed.png`) });
      const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      for (const v of axe.violations) say(`axe ${v.id}: ` + v.nodes.map(n => n.target.join(' ')).join(' | '));
      // BRIEF 10.10.7: Simple is a sentence, at most three blocks, up to six tiles and one next-step button
      await page.goto(url + '/admin#/?view=simple'); await page.reload();
      await page.waitForSelector('main .task-tile');
      await page.waitForTimeout(500);
      const s = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - innerWidth, tall: document.documentElement.scrollHeight - innerHeight,
        blocks: document.querySelectorAll('main .ov-simple .panel').length, tiles: document.querySelectorAll('main .task-tile').length,
        sentence: document.querySelector('main .ov-sentence')?.textContent, primaries: [...document.querySelectorAll('main .btn.primary')].filter(b => b.getBoundingClientRect().width).length }));
      if (s.overflow > 0) say(`Simple scrolls sideways by ${s.overflow}px`);
      if (vname === 'desktop' && s.tall > 0) say(`Simple scrolls by ${s.tall}px at 1440x852`);
      if (s.blocks > 3) say(`Simple has ${s.blocks} blocks`);
      if (s.tiles < 1 || s.tiles > 6) say(`Simple has ${s.tiles} tiles`);
      if (!s.sentence) say('Simple has no sentence');
      if (s.primaries > 1) say(`Simple has ${s.primaries} primary buttons`);
      if (vname === 'mobile') {
        const small = await page.evaluate(() => [...document.querySelectorAll('main a, main button')].filter(n => !n.closest('p, .hint')).map(n => [n, n.getBoundingClientRect()])
          .filter(([n, r]) => r.width && Math.max(r.height, parseFloat(getComputedStyle(n, '::before').height) || 0) < 44).map(([n, r]) => `${n.className || n.tagName} "${(n.textContent || '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`));
        for (const t of small) say('Simple under 44px: ' + t);
      }
      await page.screenshot({ path: path.join(OVERVIEW_OUT, `${name}.png`) });
      const axeSimple = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      for (const v of axeSimple.violations) say(`Simple axe ${v.id}: ` + v.nodes.map(n => n.target.join(' ')).join(' | '));
      if (vname === 'desktop') for (const href of CARDS) {
        await open();
        await page.locator(`main a.kpi-link[href="${href}"]`).click();
        await page.waitForFunction(() => document.querySelector('main h1') && !/^Hello/.test(document.querySelector('main h1').textContent));
        await page.waitForTimeout(300);
        const at = await page.evaluate(() => location.hash);
        const want = new URLSearchParams(href.split('?')[1] || ''), got = new URLSearchParams(at.split('?')[1] || '');
        if (at.split('?')[0] !== href.split('?')[0]) say(`${href} landed on ${at}`);
        for (const [k, v] of want) if (got.get(k) !== v) say(`${href} lost ${k}: now ${at}`);
      }
    } catch (e) { say('threw ' + e.message); }
  }
}
(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
    fs.mkdirSync(OVERVIEW_OUT, { recursive: true });
    browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
    for (const theme of ['dark', 'light']) {
      const ctx = await browser.newContext({ viewport: { width: 1200, height: 800 } });
      await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, theme);
      const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      assert.equal(r.status(), 200);
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.push(String(e)));
      page.on('console', m => m.type() === 'error' && results.errors.push(m.text()));
      await page.goto(info.url + '/admin');
      await page.waitForSelector('main h1');
      const q = await page.evaluate(async () => {
        const host = document.createElement('div'); host.style.width = '700px'; document.body.append(host);
        const out = {};
        const tryLine = (key, o) => { try { const n = SUI.line({ label: 'Spend', format: v => '$' + v, ...o }); host.append(n); out[key] = { ok: true, state: !!n.matches('.u-state'), text: n.textContent, toggle: !!n.querySelector('.u-chart-foot button'), chart: !!n.matches('.u-chart') || !!n.querySelector('svg[role=img]') }; } catch (e) { out[key] = { ok: false, err: String(e) }; } };
        tryLine('empty', { data: [] });
        tryLine('missing', {});
        tryLine('custom', { data: [], emptyText: 'No spend recorded yet.' });
        tryLine('one', { data: [{ label: 'Mon', short: 'Mon', value: 3 }] });
        tryLine('zeros', { data: [0, 0, 0].map((v, i) => ({ label: 'D' + i, short: 'D' + i, value: v })) });
        tryLine('three', { data: [1, 5, 2].map((v, i) => ({ label: 'D' + i, short: 'D' + i, value: v, note: 'n' + i })), yName: 'Spend' });
        await new Promise(r => setTimeout(r, 400));
        const three = host.children[5];
        out.threeDraw = { path: !!three.querySelector('path.line') && three.querySelector('path.line').getAttribute('d').startsWith('M'), end: three.querySelector('.end-label') && three.querySelector('.end-label').textContent, aria: three.querySelector('svg').getAttribute('aria-label') };
        three.querySelector('.u-chart-foot button').click();
        out.threeRows = three.querySelectorAll('.u-chart-table tbody tr').length;
        out.zerosDraw = !!host.children[4].querySelector('path.line');
        out.oneDraw = !!host.children[3].querySelector('path.line');
        // sparkline with no values is already safe and stays so
        try { out.spark = !!SUI.sparkline([]); } catch (e) { out.spark = false; }
        const tubes = SUI.columns({ label: 'Eight days', showZero: true,
          data: [0, 2, 0, 4, 0, 6, 0, 0].map((value, i) => ({label: 'Day ' + i, value})) });
        host.append(tubes);
        await new Promise(r => setTimeout(r, 400));
        out.tubes = { count: tubes.querySelectorAll('rect.col').length,
          zeros: [...tubes.querySelectorAll('rect.col.zero')].map(n => +n.getAttribute('height')),
          labels: [...tubes.querySelectorAll('.zero-label')].map(n => n.textContent),
          chip: tubes.querySelector('.u-pill:not(.none) .pill-t')?.textContent };
        tubes.querySelector('.u-chart-foot button').click();
        out.tubes.rows = tubes.querySelectorAll('.u-chart-table tbody tr').length;
        return out;
      });
      const t = `${theme}: `;
      // the chart draws on the next frame, so a crash shows up as a page error, not as an exception from SUI.line
      ok(t + 'no page error while any of the charts drew', results.errors.length === 0);
      ok(t + 'empty data does not throw', q.empty.ok);
      ok(t + 'empty data renders a state, no chart and no table toggle', q.empty.state && !q.empty.chart && !q.empty.toggle);
      ok(t + 'empty state says no data, not zero', /No data yet/.test(q.empty.text) && !/\$0/.test(q.empty.text));
      ok(t + 'missing data array does not throw and shows the state', q.missing.ok && q.missing.state);
      ok(t + 'the caller can supply the empty-state wording', q.custom.ok && /No spend recorded yet\./.test(q.custom.text));
      ok(t + 'one point still draws', q.one.ok && !q.one.state && q.oneDraw);
      ok(t + 'all-zero data is real data: a flat line, not the empty state', q.zeros.ok && !q.zeros.state && q.zerosDraw);
      ok(t + 'three days: line, end label and aria text unchanged', q.threeDraw.path && q.threeDraw.end === '$2' && /Use the left and right arrow keys/.test(q.threeDraw.aria));
      ok(t + 'three days: table view lists every day', q.threeRows === 3);
      ok(t + 'sparkline of nothing stays safe', q.spark);
      ok(t + 'eight tubes retain eight truthful table rows', q.tubes.count === 8 && q.tubes.rows === 8);
      ok(t + 'zero days are labelled minimum-height stubs', q.tubes.zeros.length === 5 && q.tubes.zeros.every(h => h === 4) && q.tubes.labels.every(x => x === '0'));
      ok(t + 'selected zero day shows a zero value chip', q.tubes.chip === '0');
      await ctx.close();
    }
    // Deep links render before the asynchronous attention fetch, unlike Overview.
    for (const theme of ['dark', 'light']) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
      await ctx.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.push(String(e)));
      let release;
      const delayed = new Promise(resolve => { release = resolve; });
      let count = 2;
      await page.route('**/admin/api/attention', async route => {
        await delayed;
        await route.fulfill({ json: { items: Array.from({length: count}, (_, i) => ({id: i})), counts: {high: count, medium: 0} } });
      });
      await page.route('**/admin/api/me', async route => {
        const response = await route.fetch();
        await route.fulfill({ response, json: {...await response.json(), display_name: 'Dr Jane Doe'} });
      });
      await page.goto(info.url + '/admin#/people');
      const nav = page.locator('.console-tabbar');
      await nav.waitFor({state: 'visible'});
      ok(theme + ': phone deep link has four links', await nav.locator('a').count() === 4);
      ok(theme + ': People is current', await nav.locator('a[aria-current="page"]').getAttribute('href') === '#/people');
      ok(theme + ': delayed attention has no premature badge', await nav.locator('.stb-badge').count() === 0);
      release();
      await page.waitForFunction(() => document.querySelector('.console-tabbar .stb-badge')?.textContent === '2');
      ok(theme + ': loaded attention updates accessible label', await nav.locator('.stb-round').getAttribute('aria-label') === 'All pages, 2 need attention');
      count = 1;
      await page.evaluate(() => SWA.refreshAttention());
      ok(theme + ': refresh replaces badge count', await nav.locator('.stb-badge').textContent() === '1');
      count = 0;
      await page.evaluate(() => SWA.refreshAttention());
      ok(theme + ': cleared attention removes badge and label', await nav.locator('.stb-badge').count() === 0 && await nav.locator('.stb-round').getAttribute('aria-label') === 'All pages');
      const widths = await nav.locator('.stb-bar').evaluate(n => [n.getBoundingClientRect().width, n.querySelector('a.on').getBoundingClientRect().width]);
      ok(theme + ': bar and active pill match reference geometry', Math.abs(widths[0] - 260) <= 4 && Math.abs(widths[1] - 104) <= 4);
      await nav.locator('.stb-round').click();
      await page.locator('.side.drawer.in').waitFor({state: 'visible'});
      ok(theme + ': All pages opens drawer and hides phone bar', !await nav.isVisible());
      await page.keyboard.press('Escape');
      await page.locator('.side.drawer').waitFor({state: 'detached'});
      await page.evaluate(() => { SUI.phoneLens = undefined; return SWA.render(); });
      await nav.waitFor({state: 'visible'});
      ok(theme + ': missing lens helper preserves console', await nav.locator('a').count() === 4);
      await page.setViewportSize({width: 320, height: 844});
      ok(theme + ': narrow inactive targets retain 44px width', await nav.locator('a:not(.on)').evaluateAll(ns => ns.every(n => n.getBoundingClientRect().width >= 44)));
      await nav.locator('a[href="#/"]').click();
      await page.waitForFunction(() => document.querySelector('main h1')?.textContent.includes('Dr Jane Doe'));
      ok(theme + ': greeting retains full recorded name including title', await page.locator('main h1').textContent() === 'Hello, Dr Jane Doe! 👋');
      await overviewPass(page, info.url, theme);
      await ctx.close();
    }
    ok('no console or page errors', results.errors.length === 0);
    fs.writeFileSync(path.join(OVERVIEW_OUT, 'findings.json'), JSON.stringify(overviewFindings, null, 1));
    assert.deepEqual(overviewFindings, [], 'Overview findings');
  } finally {
    if (browser) await browser.close();
    demo.kill();
  }
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
