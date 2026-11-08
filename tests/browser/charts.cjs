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
(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
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
      await ctx.close();
    }
    ok('no console or page errors', results.errors.length === 0);
  } finally {
    if (browser) await browser.close();
    demo.kill();
  }
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
