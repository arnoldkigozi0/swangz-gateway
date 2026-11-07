/* Glass R5 tube bars check. NODE_PATH must point at a tooling dir with playwright (never installed in the repo).
   Starts demo_history.py (synthetic opens over 30 days, test database, FakeUpstream) and checks the admin Usage chart. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../../..');
const out = __dirname;
const results = { checks: [], shots: [], errors: [] };
const ok = (label, v) => { assert.ok(v, label); results.checks.push(label); };
(async () => {
  const demo = spawn('python3', [path.join(__dirname, 'demo_history.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
    demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } }); demo.stderr.on('data', d => process.stderr.write(d)); demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
  const open = async (w, h, theme, motion) => {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: motion || 'no-preference' });
    await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, theme);
    const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'operations@swangzavenue.com', password: 'operations-password' } });
    assert.equal(r.status(), 200);
    const page = await ctx.newPage();
    page.on('pageerror', e => results.errors.push(String(e)));
    page.on('console', m => m.type() === 'error' && results.errors.push(m.text()));
    await page.goto(info.url + '/admin#/?tab=trends');
    await page.evaluate(t => { document.documentElement.dataset.theme = t; }, theme);
    await page.waitForSelector('.u-tubes .col');
    return { ctx, page };
  };
  try {
    for (const [w, h] of [[1440, 900], [390, 844]]) for (const theme of ['dark', 'light']) {
      const { ctx, page } = await open(w, h, theme);
      await page.waitForTimeout(1600);
      const q = await page.evaluate(() => {
        const svg = document.querySelector('.u-tubes'); const cols = [...svg.querySelectorAll('.col')];
        return { n: cols.length, on: svg.querySelectorAll('.col.on').length, label: svg.querySelector('.pill-t').textContent, aria: svg.getAttribute('aria-label'),
          rounded: cols.every(c => Number(c.getAttribute('rx')) >= Number(c.getAttribute('width')) / 2 - 0.01), overflow: document.documentElement.scrollWidth <= innerWidth,
          settled: [...svg.querySelectorAll('.tube')].every(t => getComputedStyle(t).opacity === '1' && getComputedStyle(t).transform === 'none') };
      });
      ok(`${w}x${h} ${theme}: 30 tubes, one current`, q.n === 30 && q.on === 1);
      ok(`${w}x${h} ${theme}: tubes fully rounded`, q.rounded);
      ok(`${w}x${h} ${theme}: pill shows a real value (${q.label})`, /^\d/.test(q.label));
      ok(`${w}x${h} ${theme}: aria-label has latest and highest`, /Latest .*Highest /.test(q.aria));
      ok(`${w}x${h} ${theme}: bars settled after growing`, q.settled);
      ok(`${w}x${h} ${theme}: no horizontal overflow`, q.overflow);
      if (w === 1440) { // hover moves the current bar; keyboard reads it; table view lists every day
        const box = await page.locator('.u-tubes .col').nth(5).boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.waitForTimeout(500);
        ok('hover makes the hovered tube current', await page.evaluate(() => [...document.querySelectorAll('.u-tubes .col')].findIndex(c => c.classList.contains('on')) === 5));
        await page.screenshot({ path: path.join(out, `tubes-hover-${theme}-1440x900.png`) });
        await page.mouse.move(5, 5); await page.waitForTimeout(300);
        await page.focus('.u-tubes'); await page.keyboard.press('Home'); await page.waitForTimeout(150);
        ok('keyboard Home selects the first tube', await page.evaluate(() => document.querySelector('.u-tubes .col').classList.contains('on')));
        await page.locator('.u-chart-foot button').first().click();
        ok('table view lists 30 days', (await page.locator('.u-chart-table tbody tr').count()) === 30);
        await page.locator('.u-chart-foot button').first().click();
        await page.mouse.move(5, 5);
      }
      await page.locator('.u-chart').first().scrollIntoViewIfNeeded(); await page.waitForTimeout(300);
      const f = `tubes-${theme}-${w}x${h}.png`;
      await page.screenshot({ path: path.join(out, f) }); results.shots.push(f);
      await ctx.close();
    }
    { // mid-grow frame, then reduced motion
      const { ctx, page } = await open(1440, 900, 'dark');
      await ctx.close();
      const c2 = await open(1440, 900, 'dark');
      await c2.page.waitForTimeout(40);
      await c2.page.screenshot({ path: path.join(out, 'tubes-growing-dark-1440x900.png') }); results.shots.push('growing');
      await c2.ctx.close();
      const rm = await open(1440, 900, 'dark', 'reduce');
      ok('reduced motion: tubes visible at once, not armed', await rm.page.evaluate(() => { const s = document.querySelector('.u-tubes'); return !s.classList.contains('grow') && [...s.querySelectorAll('.tube')].every(t => getComputedStyle(t).opacity === '1' && getComputedStyle(t).transform === 'none'); }));
      await rm.ctx.close();
    }
    results.cls = null;
  } finally { await browser.close(); demo.kill('SIGTERM'); }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 1));
  assert.deepEqual(results.errors, []);
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAIL', e); process.exit(1); });
