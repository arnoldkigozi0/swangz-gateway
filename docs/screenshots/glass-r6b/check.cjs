/* Glass R6b line chart check. NODE_PATH must point at a tooling dir with playwright (never installed in the repo).
   Starts demo_spend.py (synthetic priced requests over 30 days, test database) and checks the admin "Spend per day" line. */
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
  const demo = spawn('python3', [path.join(__dirname, 'demo_spend.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
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
    await page.waitForSelector('.u-glassline .line');
    return { ctx, page };
  };
  try {
    for (const [w, h] of [[1440, 900], [390, 844]]) for (const theme of ['dark', 'light']) {
      const { ctx, page } = await open(w, h, theme);
      await page.locator('.u-glassline').scrollIntoViewIfNeeded(); await page.waitForTimeout(1700);
      const q = await page.evaluate(() => {
        const svg = document.querySelector('.u-glassline');
        const clip = svg.querySelector('clipPath rect');
        return { d: svg.querySelector('path.line').getAttribute('d'), aria: svg.getAttribute('aria-label'), marks: svg.querySelectorAll('.glass-mark').length,
          fill: getComputedStyle(svg.querySelector('.glass-area')).fill, areaOpacity: getComputedStyle(svg.querySelector('.glass-area')).opacity,
          open: getComputedStyle(clip).transform, endOp: getComputedStyle(svg.querySelector('.end')).opacity,
          overflow: document.documentElement.scrollWidth <= innerWidth, endLabel: svg.querySelector('.end-label').textContent };
      });
      ok(`${w}x${h} ${theme}: smooth curve (C segments)`, /C/.test(q.d));
      ok(`${w}x${h} ${theme}: area uses the gradient, not a flat fill (${q.fill})`, /url\(/.test(q.fill) && q.areaOpacity === '1');
      ok(`${w}x${h} ${theme}: dot markers present (${q.marks})`, q.marks >= 2);
      ok(`${w}x${h} ${theme}: aria-label has latest and highest`, /Latest .*Highest /.test(q.aria));
      ok(`${w}x${h} ${theme}: draw-in finished (clip open, end dot lit)`, (q.open === 'none' || /matrix\(1,/.test(q.open)) && q.endOp === '1');
      ok(`${w}x${h} ${theme}: end label is a real value (${q.endLabel})`, /\d/.test(q.endLabel));
      ok(`${w}x${h} ${theme}: no horizontal overflow`, q.overflow);
      if (w === 1440) {
        const box = await page.locator('.u-glassline').boundingBox();
        await page.mouse.move(box.x + box.width * 0.45, box.y + box.height / 2); await page.waitForTimeout(250);
        ok('hover shows the crosshair and moves the lit dot', await page.evaluate(() => document.querySelector('.u-glassline .cross.on') && Number(document.querySelector('.u-glassline .end').getAttribute('cx')) < Number(document.querySelector('.u-glassline .line').getAttribute('d').split(' ').pop().split(',')[0])));
        await page.screenshot({ path: path.join(out, `line-hover-${theme}-1440x900.png`) });
        await page.mouse.move(5, 5); await page.waitForTimeout(250);
        await page.focus('.u-glassline'); await page.keyboard.press('Home'); await page.waitForTimeout(150);
        ok('keyboard Home reads the first day', await page.evaluate(() => !!document.querySelector('.u-glassline .cross.on')));
        const btn = page.locator('.u-chart-foot button').nth(1);
        await btn.click();
        ok('table view lists 30 days', (await page.locator('.u-chart-table tbody tr').last().count()) === 1 && (await page.locator('.u-chart-table').last().locator('tbody tr').count()) === 30);
        await btn.click(); await page.mouse.move(5, 5);
      }
      await page.locator('.u-glassline').scrollIntoViewIfNeeded(); await page.waitForTimeout(300);
      const f = `line-${theme}-${w}x${h}.png`;
      await page.screenshot({ path: path.join(out, f) }); results.shots.push(f);
      await ctx.close();
    }
    { // mid-draw frame, then reduced motion
      const c2 = await open(1440, 900, 'dark');
      await c2.page.locator('.u-glassline').scrollIntoViewIfNeeded(); await c2.page.waitForTimeout(420);
      await c2.page.screenshot({ path: path.join(out, 'line-drawing-dark-1440x900.png') }); results.shots.push('drawing');
      await c2.ctx.close();
      const rm = await open(1440, 900, 'dark', 'reduce');
      ok('reduced motion: drawn at once, not armed', await rm.page.evaluate(() => { const r = document.querySelector('.u-glassline clipPath rect'); return getComputedStyle(r).transform === 'none' && getComputedStyle(document.querySelector('.u-glassline .end')).opacity === '1'; }));
      await rm.ctx.close();
    }
  } finally { await browser.close(); demo.kill('SIGTERM'); }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 1));
  assert.deepEqual(results.errors, []);
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error('FAIL', e); process.exit(1); });
