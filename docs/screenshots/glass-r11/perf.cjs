/* Footer reveal frame-time trace (R11). Software rendering (headless Chrome, --disable-gpu): meaningful for comparing two states on one
   machine, not for absolute numbers. OLDWORD=1 puts the previous wordmark (scene photo, fixed attachment, drop-shadow filter) back with an
   injected rule, so the same build is measured both ways. Each run loads Tools, scrolls to the footer in steps and records requestAnimationFrame
   intervals from the first step until 1.6 s after the footer reaches the bottom. NODE_PATH must reach a tooling dir with playwright.
   SAME DISTANCE: ROOT=<other checkout> runs that checkout's server and page (for example current main, whose footer is the plain .foot with no
   reveal), and DISTANCE=<px> makes every arm scroll exactly that far: a spacer is added above the footer when the page is shorter, so the footer
   ends at the bottom of the viewport in every arm. Steps (24, 30 ms apart) and the 1.6 s rest after the last step are the same in every arm.
   EXTRACSS=<css> injects a rule, to switch one part off and see what it costs (for example the reveal, or the letters' photo).
   Usage: [EXTRACSS=css] [ROOT=dir] [DISTANCE=845] [OLDWORD=1] [RUNS=4] [THEME=dark|light] node docs/screenshots/glass-r11/perf.cjs */
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(process.env.ROOT || path.join(__dirname, '../../..')), DISTANCE = Number(process.env.DISTANCE || 0);
const RUNS = Number(process.env.RUNS || 4), OLD = process.env.OLDWORD === '1', THEME = process.env.THEME || 'dark';
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
const OLDCSS = '.gf-word{background:linear-gradient(180deg,rgba(255,246,232,.46),rgba(255,246,232,.24)),var(--scene-image) center / cover fixed no-repeat!important;-webkit-background-clip:text!important;background-clip:text!important;filter:drop-shadow(0 1px 0 rgba(255,255,255,.34))!important}';
(async () => {
  const demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
    demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } }); demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--disable-gpu'] });
  const out = [], fs = require('node:fs');
  try {
    for (let run = 0; run < RUNS; run++) {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, bypassCSP: true });
      await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, THEME);
      const r = await ctx.request.post(info.url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
      if (r.status() !== 200) throw new Error('login ' + r.status());
      const page = await ctx.newPage();
      await page.goto(info.url + '/#/tools'); await page.waitForSelector('.glass-foot, footer.foot'); await page.waitForTimeout(900);
      if (DISTANCE) await page.evaluate(d => { const have = document.documentElement.scrollHeight - innerHeight; if (have < d) { const sp = document.createElement('div'); sp.style.height = (d - have) + 'px'; sp.setAttribute('data-spacer', '1'); const foot = document.querySelector('.glass-foot, footer.foot'); foot.parentNode.insertBefore(sp, foot); } }, DISTANCE);
      if (OLD) await page.addStyleTag({ content: OLDCSS });
      if (process.env.EXTRACSS) await page.addStyleTag({ content: process.env.EXTRACSS });
      const cdp = await ctx.newCDPSession(page); await cdp.send('Performance.enable'); const metric = async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(m => [m.name, m.value]));
      const m0 = await metric();
      await page.evaluate(() => { window.__f = []; let last = performance.now(); const tick = (n) => { window.__f.push(n - last); last = n; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick); });
      const max = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
      if (DISTANCE && Math.abs(max - DISTANCE) > 1) throw new Error('distance ' + max + ' != ' + DISTANCE);
      for (let y = 0; y <= max; y += Math.max(60, Math.ceil(max / 24))) { await page.evaluate(v => window.scrollTo(0, v), y); await page.waitForTimeout(30); }
      await page.evaluate(v => window.scrollTo(0, v), max); await page.waitForTimeout(1600);
      const f = (await page.evaluate(() => { cancelAnimationFrame(window.__raf); return window.__f; })).slice(2);
      const m1 = await metric(); const ms = k => Math.round((m1[k] - m0[k]) * 1000);
      out.push({ run: run + 1, taskMs: ms('TaskDuration'), layoutMs: ms('LayoutDuration'), scriptMs: ms('ScriptDuration'), frames: f.length, p50: +pct(f, .5).toFixed(1), p95: +pct(f, .95).toFixed(1), max: +Math.max(...f).toFixed(1), over50: f.filter(x => x > 50).length });
      console.log(JSON.stringify(out[out.length - 1]));
      await ctx.close();
    }
    if (process.env.SAVE) fs.appendFileSync(process.env.SAVE, JSON.stringify({ arm: process.env.ARM || null, root: path.basename(root), theme: THEME, distance: DISTANCE || 'natural', extra: process.env.EXTRACSS || null, runs: out }) + '\n');
    console.log(JSON.stringify({ root: path.basename(root), distance: DISTANCE || 'natural', oldWordmark: OLD, extra: process.env.EXTRACSS || null, theme: THEME, p95: out.map(o => o.p95), over50: out.map(o => o.over50) }));
  } finally { await browser.close(); demo.kill(); }
})().catch(e => { console.error(e); process.exit(1); });
