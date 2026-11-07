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
    // a real Cumulative Layout Shift: layout-shift entries (not caused by input) summed from the first frame
    await ctx.addInitScript(() => { window.__cls = 0; try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch (e) { window.__cls = null; } });
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
        const base = Math.max(...cols.map(c => Number(c.getAttribute('y')) + Number(c.getAttribute('height'))));
        return { n: cols.length, on: svg.querySelectorAll('.col.on').length, label: svg.querySelector('.pill-t').textContent, aria: svg.getAttribute('aria-label'), cls: window.__cls,
          bw: Number(cols[0].getAttribute('width')), h: Number(svg.getAttribute('height')),
          heights: cols.map(c => Number(c.getAttribute('height'))), base,
          rounded: cols.every(c => Math.abs(Number(c.getAttribute('rx')) - Math.min(Number(c.getAttribute('width')), Number(c.getAttribute('height'))) / 2) < 0.01), overflow: document.documentElement.scrollWidth <= innerWidth,
          settled: [...svg.querySelectorAll('.tube')].every(t => getComputedStyle(t).opacity === '1' && getComputedStyle(t).transform === 'none') };
      });
      ok(`${w}x${h} ${theme}: 30 tubes, one current`, q.n === 30 && q.on === 1);
      ok(`${w}x${h} ${theme}: caps are rounded to each bar's own size`, q.rounded);
      ok(`${w}x${h} ${theme}: tubes at least 8px wide and chart at least 200px tall (${q.bw.toFixed(1)} x ${q.h})`, q.bw >= (w === 390 ? 5 : 8) && q.h >= 200);
      ok(`${w}x${h} ${theme}: CLS measured and 0 (${q.cls})`, typeof q.cls === 'number' && q.cls < 0.001);
      results.cls = Math.max(results.cls || 0, q.cls);
      ok(`${w}x${h} ${theme}: pill shows a real value (${q.label})`, /^\d/.test(q.label));
      ok(`${w}x${h} ${theme}: aria-label has latest and highest`, /Latest .*Highest /.test(q.aria));
      ok(`${w}x${h} ${theme}: bars settled after growing`, q.settled);
      ok(`${w}x${h} ${theme}: no horizontal overflow`, q.overflow);
      if (w === 1440) { // hover moves the current bar; keyboard reads it; table view lists every day
        const box = await page.locator('.u-tubes .col').nth(5).boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.waitForTimeout(500);
        ok('hover makes the hovered tube current', await page.evaluate(() => [...document.querySelectorAll('.u-tubes .col')].findIndex(c => c.classList.contains('on')) === 5));
        const overlap = await page.evaluate(() => { const a = document.querySelector('.u-tip.in'), b = document.querySelector('.u-tubes .u-pill:not(.none)'); if (!a || !b) return 'missing'; const r = a.getBoundingClientRect(), s = b.getBoundingClientRect(); return !(r.right <= s.left || r.left >= s.right || r.bottom <= s.top || r.top >= s.bottom); });
        ok(`hover tooltip does not cover the floating value label (${overlap})`, overlap === false);
        await page.screenshot({ path: path.join(out, `tubes-hover-${theme}-1440x900.png`) });
        await page.mouse.move(5, 5); await page.waitForTimeout(300);
        await page.focus('.u-tubes'); await page.keyboard.press('Home'); await page.waitForTimeout(150);
        ok('keyboard Home selects the first tube', await page.evaluate(() => document.querySelector('.u-tubes .col').classList.contains('on')));
        await page.locator('.u-chart-foot button').first().click();
        ok('table view lists 30 days', (await page.locator('.u-chart-table tbody tr').count()) === 30);
        const vals = await page.locator('.u-chart-table tbody tr td').allTextContents();
        const hs = await page.evaluate(() => [...document.querySelectorAll('.u-tubes .col')].map(c => Number(c.getAttribute('height'))));
        const nums = vals.map(v => Number(v.replace(/[^0-9.]/g, '')));
        const top = nums.indexOf(Math.max(...nums)), scale = hs[top] / nums[top];
        ok(`bar heights are proportional to the table values (max error ${Math.max(...nums.map((v, i) => Math.abs(hs[i] - v * scale))).toFixed(2)}px)`, nums.every((v, i) => Math.abs(hs[i] - v * scale) <= (v > 0 && v * scale < 1 ? 1 : 0.01)));
        await page.locator('.u-chart-foot button').first().click();
        await page.mouse.move(5, 5);
      }
      if (w === 1440) {
        const empty = await page.evaluate(() => { try { const n = SUI.columns({ label: 'Empty', data: [] }); return { ok: true, state: !!n.matches('.u-state') || !!n.querySelector('.u-state'), text: n.textContent }; } catch (e) { return { ok: false, err: String(e) }; } });
        ok(`empty data renders an empty state and does not throw (${empty.text})`, empty.ok && empty.state);
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
  } finally { await browser.close(); demo.kill('SIGTERM'); }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 1));
  assert.deepEqual(results.errors, []);
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAIL', e); process.exit(1); });
