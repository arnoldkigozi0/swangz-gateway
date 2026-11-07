/* Glass R11 footer check: run with NODE_PATH pointing at a tooling dir that has playwright (never installed in the repo).
   Starts tests/browser/demo.py (synthetic data, FakeUpstream), signs in as the demo person and checks the staff footer. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../../..');
const out = __dirname;
const results = { checks: [], shots: [], errors: [] };
const ok = (label, v) => { assert.ok(v, label); results.checks.push(label); };
(async () => {
  const demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
    demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } }); demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
  try {
    for (const [w, h] of [[1440, 900], [390, 844]]) for (const theme of ['dark', 'light']) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'no-preference' });
      await ctx.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      await ctx.addInitScript(t => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
      const r = await ctx.request.post(info.url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
      assert.equal(r.status(), 200);
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.push(String(e)));
      page.on('console', m => m.type() === 'error' && results.errors.push(m.text()));
      await page.goto(info.url + '/#/tools');
      await page.evaluate(t => { document.documentElement.dataset.theme = t; }, theme);
      await page.waitForSelector('.glass-foot');
      const clsBefore = await page.evaluate(() => new Promise(r => { let v = 0; new PerformanceObserver(l => l.getEntries().forEach(e => { if (!e.hadRecentInput) v += e.value; })).observe({ type: 'layout-shift', buffered: true }); setTimeout(() => r(v), 300); }));
      await page.evaluate(() => document.querySelector('.glass-foot').scrollIntoView({ block: 'end' }));
      await page.waitForFunction(() => document.querySelector('.glass-foot').classList.contains('gf-in'));
      await page.waitForTimeout(1800);
      await page.waitForFunction(() => /Gateway (running|not answering)/.test(document.querySelector('.gf-status').textContent));
      if (w === 1440 && theme === 'dark') {
        ok('real health shows the gateway running', /Gateway running/.test(await page.textContent('.gf-status')));
        ok('footer links reuse existing routes', JSON.stringify(await page.$$eval('.gf-card a', a => a.map(x => x.getAttribute('href')))) === JSON.stringify(['#/tools', '#/devices', '#/requests', '#/privacy', '#/privacy']));
        ok('no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        const props = await page.evaluate(() => { const n = document.querySelector('.gf-panel'); const cs = getComputedStyle(n); return [cs.transform, cs.opacity]; });
        ok('settled: no transform, full opacity', props[0] === 'none' && props[1] === '1');
        ok('wordmark is decorative', await page.getAttribute('.gf-word', 'aria-hidden') === 'true');
        // the ask form opens the existing request dialog for a locked tool
        const tool = await page.evaluate(() => document.querySelector('#gf-tools option')?.value);
        if (tool) { await page.fill('.gf-input', tool); await page.click('.gf-btn'); await page.waitForSelector('dialog, [role=dialog]', { timeout: 3000 }); ok('Ask opens the existing request dialog for ' + tool, true); await page.keyboard.press('Escape'); }
        results.cls = clsBefore;
      }
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(300);
      const f = `${theme}-${w}x${h}.png`; await page.screenshot({ path: path.join(out, 'footer-' + f) }); results.shots.push(f);
      if (w === 390) ok(`no horizontal overflow at 390 ${theme}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await ctx.close();
    }
    { // mid-reveal frame: the liquid rising, content still arriving
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await ctx.request.post(info.url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
      const page = await ctx.newPage(); await page.goto(info.url + '/#/tools'); await page.waitForSelector('.glass-foot'); await page.waitForTimeout(600); await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await page.waitForTimeout(230); await page.screenshot({ path: path.join(out, 'footer-reveal-mid-dark-1440x900.png') }); results.shots.push('reveal-mid');
      await ctx.close();
    }
    // reduced motion: footer present and visible with no armed reveal
    const rctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    await rctx.request.post(info.url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
    const rp = await rctx.newPage(); await rp.goto(info.url + '/#/tools'); await rp.waitForSelector('.glass-foot');
    ok('reduced motion: reveal not armed, footer opaque', await rp.evaluate(() => !document.querySelector('.glass-foot').classList.contains('gf-armed') && getComputedStyle(document.querySelector('.gf-panel')).opacity === '1'));
    await rctx.close();
    assert.deepEqual(results.errors.filter(e => !/favicon/.test(e)), [], 'console errors');
  } finally { await browser.close(); demo.kill('SIGTERM'); fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 1)); }
  console.log(JSON.stringify(results, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
