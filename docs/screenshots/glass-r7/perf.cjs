/* Hover and filter frame-time trace for the glass list panel (R7). Software rendering (headless Chrome, no GPU): good for comparing two
   states on the same machine, not for absolute numbers. BLUR=1 puts the panel's live backdrop blur back (the old behaviour), so the same
   build is measured both ways. NODE_PATH must reach a tooling dir with playwright. Starts tests/browser/demo.py (test database).
   Usage: [BLUR=1] [RUNS=4] node docs/screenshots/glass-r7/perf.cjs   -> one JSON line per run, then a summary. */
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../../..');
const RUNS = Number(process.env.RUNS || 4), BLUR = process.env.BLUR === '1', THEME = process.env.THEME || 'dark';
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
(async () => {
  const demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
    demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } }); demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--disable-gpu'] });
  const out = [];
  try {
    for (let run = 0; run < RUNS; run++) {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, bypassCSP: true });
      await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, THEME);
      const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      if (r.status() !== 200) throw new Error('login ' + r.status());
      const page = await ctx.newPage();
      await page.goto(info.url + '/admin'); await page.waitForSelector('main h1');
      if (BLUR) await page.addStyleTag({ content: '.u-list{-webkit-backdrop-filter:var(--glass-blur)!important;backdrop-filter:var(--glass-blur)!important}' });
      await page.evaluate(() => {
        const { el } = SUI; const rows = Array.from({ length: 14 }, (_, i) => ({ name: 'Person ' + i, email: 'p' + i + '@example.test', state: i % 3 ? 'active' : 'paused', used: (i * 7) % 100 }));
        let filter = 'all'; const body = el('div');
        const draw = () => body.replaceChildren(SUI.table({ caption: 'People', rows: rows.filter(x => filter === 'all' || x.state === filter), sort: ['name', 'asc'], columns: [
          { key: 'name', label: 'Person', lead: true, render: (x) => el('div', { class: 'u-cell' }, SUI.avatar(x.name), el('div', null, el('strong', null, x.name), el('span', { class: 'sub' }, x.email))) },
          { key: 'state', label: 'Status', render: (x) => SUI.status(x.state === 'active' ? 'active' : 'paused', x.state) },
          { key: 'used', label: 'Used', render: (x) => SUI.progress(x.used, { label: 'Used by ' + x.name }) }] }));
        document.querySelector('main').replaceChildren(el('h1', null, 'People'), SUI.listPanel({ title: 'All people', body,
          filters: { label: 'Show', value: 'all', options: [{ id: 'all', label: 'All' }, { id: 'active', label: 'Active' }, { id: 'paused', label: 'Paused' }], onChange: (v) => { filter = v; draw(); } } }));
        draw();
      });
      await page.waitForTimeout(900);
      await page.evaluate(() => { window.__f = []; let last = performance.now(); const tick = (n) => { window.__f.push(n - last); last = n; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick); });
      const box = await page.locator('.u-list tbody').boundingBox();
      for (let pass = 0; pass < 3; pass++) for (let i = 0; i <= 40; i++) await page.mouse.move(box.x + 60 + i * 20, box.y + 10 + ((i * 17 + pass * 31) % Math.max(20, box.height - 20)));
      for (const id of ['active', 'paused', 'all', 'active', 'paused', 'all']) { await page.click(`.u-seg button[data-id="${id}"]`); await page.waitForTimeout(120); }
      const f = (await page.evaluate(() => { cancelAnimationFrame(window.__raf); return window.__f; })).slice(2);
      out.push({ run: run + 1, frames: f.length, p50: +pct(f, .5).toFixed(1), p95: +pct(f, .95).toFixed(1), max: +Math.max(...f).toFixed(1), slow: f.filter(x => x > 33.4).length });
      console.log(JSON.stringify(out[out.length - 1]));
      await ctx.close();
    }
    const p95s = out.map(o => o.p95);
    console.log(JSON.stringify({ blur: BLUR, theme: THEME, p95Range: [Math.min(...p95s), Math.max(...p95s)], slowFrames: out.map(o => o.slow) }));
  } finally { await browser.close(); demo.kill(); }
})().catch(e => { console.error(e); process.exit(1); });
