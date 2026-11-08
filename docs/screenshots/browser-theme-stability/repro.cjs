/* Why check.cjs waits for finite animations before axe. Staff Home, theme flipped to light, then axe:
   1. "frozen mid-transition": every finite animation is held at 0% (what a slow CI runner shows axe) -> axe reports color-contrast;
   2. after the same wait check.cjs now does (play, then await finished) -> no violations.
   Axe and its rules are unchanged. NODE_PATH must reach a tooling dir with playwright and @axe-core/playwright. Starts tests/browser/demo.py. */
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const root = path.resolve(__dirname, '../../..');
const finite = `document.getAnimations().filter(a => { const t = a.effect && a.effect.getComputedTiming(); return t && Number.isFinite(t.iterations); })`;
(async () => {
  const demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  const info = await new Promise(r => { let b = ''; demo.stdout.on('data', d => { b += d; if (b.includes('\n')) r(JSON.parse(b.split('\n')[0])); }); });
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
  const axe = async p => (await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations.map(v => v.id);
  const out = { frozen: [], settled: [] };
  try {
    for (let i = 0; i < 3; i++) {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await ctx.request.post(info.url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
      const p = await ctx.newPage(); await p.goto(info.url + '/'); await p.locator('main h1').waitFor(); await p.waitForTimeout(100);
      await p.evaluate(() => { document.documentElement.dataset.theme = 'light'; localStorage.setItem('swangz-theme', 'light'); });
      await p.evaluate(`${finite}.forEach(a => { a.pause(); a.currentTime = 0; })`);
      out.frozen.push(await axe(p));
      await p.evaluate(`${finite}.forEach(a => a.play())`);
      await p.evaluate(async () => { // the wait added to check.cjs
        const finite = () => document.getAnimations().filter(a => { const t = a.effect && a.effect.getComputedTiming(); return t && Number.isFinite(t.iterations); });
        for (let k = 0; k < 5 && finite().length; k++) await Promise.all(finite().map(a => a.finished.catch(() => {})));
      });
      out.settled.push(await axe(p));
      await ctx.close();
    }
  } finally { await browser.close(); demo.kill(); }
  console.log(JSON.stringify(out));
  if (!out.frozen.every(v => v.includes('color-contrast')) || out.settled.some(v => v.length)) process.exit(1);
})();
