/* Chart and list contrast on the glass panel (R14a), measured on what is painted. Light "Porcelain" is the target; dark is asserted too (the sparkline stroke was 1.40:1 there).
   Mounts SUI.columns / line / sparkline / barList and a SUI.listPanel inside .u-glass-strong in the real console (tests/browser/demo.py).
   The numbers are fixtures (invented values, example.test names): this checks colour, not data. SHOTS=<dir> saves screenshots.
   NODE_PATH must reach a tooling dir with playwright. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const results = { checks: [], measured: [], errors: [] };
const SHOTS = process.env.SHOTS;
const REPORT_ONLY = (process.env.REPORT_ONLY || '') === '1';
const fails = [];

const mount = () => {
  const { el } = SUI;
  const main = document.querySelector('main');
  const days = [3, 5, 4, 8, 6, 9, 7, 12, 10, 11].map((v, i) => ({ label: 'Day ' + (i + 1), short: 'D' + (i + 1), value: v, note: 'n' }));
  const pane = (title, ...kids) => { const n = el('section', { class: 'u-glass-strong', 'aria-label': title }, el('h2', { class: 'pt' }, title), ...kids); n.style.setProperty('padding', '16px 18px'); n.style.setProperty('margin-bottom', '16px'); return n; }; // CSSOM, not a style attribute: the CSP forbids those
  const wrap = el('div', { class: 'pcl-grid' },
    pane('Requests per day', SUI.columns({ label: 'Requests', data: days, yName: 'Requests' })),
    pane('Spend', SUI.line({ label: 'Spend', data: days, format: (v) => '$' + v, yName: 'Spend' })),
    pane('Activity', SUI.columns({ label: 'Activity', data: days, tone: 2 }), SUI.line({ label: 'Activity line', data: days, tone: 2 })),
    pane('Top tools', SUI.barList([
      { label: 'Claude Code', value: 90, display: '90', note: 'requests' }, { label: 'Codex', value: 55, display: '55', note: 'requests' }, { label: 'ElevenLabs', value: 20, display: '20', note: 'requests' }]),
      SUI.barList([{ label: 'Second tone', value: 40, display: '40', note: 'requests' }], { tone: 2 })),
    pane('Spark', el('div', { class: 'pcl-spark' }, SUI.sparkline([2, 4, 3, 7, 5, 9]), SUI.sparkline([2, 4, 3, 7, 5, 9], 2))),
    SUI.listPanel({ title: 'People', sub: 'Fixture rows', filters: { label: 'Show', value: 'all', options: [{ id: 'all', label: 'All', count: 2 }, { id: 'on', label: 'On', count: 1 }] }, search: { label: 'Search', placeholder: 'Search people' },
      body: SUI.table({ caption: 'People', rows: [{ n: 'Achieng Olivia', e: 'a@example.test', u: 82 }, { n: 'Kintu Sarah', e: 'k@example.test', u: 12 }], columns: [
        { key: 'n', label: 'Person', lead: true, render: (r) => el('div', { class: 'u-cell' }, SUI.avatar(r.n), el('div', null, el('strong', null, r.n), el('span', { class: 'sub' }, r.e))) },
        { key: 'u', label: 'Budget used', render: (r) => SUI.progress(r.u, { label: 'Budget used by ' + r.n }) }] }) }));
  wrap.querySelectorAll('.pt').forEach((h) => { h.style.setProperty('margin', '0 0 10px'); h.style.setProperty('font-size', '15px'); });
  main.replaceChildren(el('h1', null, 'Charts'), wrap);
};

const lumOf = (r, g, b) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };

/* Hide the element, photograph what is behind it, then compare the element's own colour (composited at its opacity) with the worst pixel. */
async function measure(page, sel, label, min, kind, nth = 0) {
  const info = await page.evaluate(({ sel, kind, nth }) => {
    const e = document.querySelectorAll(sel)[nth]; if (!e) return null;
    const cs = getComputedStyle(e);
    let color = kind === 'stroke' ? cs.stroke : kind === 'fill' ? cs.fill : kind === 'bg' ? cs.backgroundColor : cs.color;
    let op = parseFloat(cs.opacity) || 1;
    for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) { const o = parseFloat(getComputedStyle(p).opacity); if (!isNaN(o)) op *= o; }
    let r = e.getBoundingClientRect();
    if (kind === 'text') { const g = document.createRange(); g.selectNodeContents(e); const q = g.getBoundingClientRect(); if (q.width && q.height) r = q; }
    e.scrollIntoView({ block: 'center' });
    r = e.getBoundingClientRect();
    if (kind === 'text') { const g = document.createRange(); g.selectNodeContents(e); const q = g.getBoundingClientRect(); if (q.width && q.height) r = q; }
    window.__hid = [e, e.style.visibility]; e.style.setProperty('visibility', 'hidden', 'important');
    if (kind === 'text') e.querySelectorAll('*').forEach((n) => n.style.setProperty('visibility', 'hidden', 'important'));
    return { x: r.x, y: r.y, w: Math.max(2, r.width), h: Math.max(2, r.height), color, op };
  }, { sel, kind, nth });
  assert.ok(info, 'missing ' + sel);
  const png = await page.screenshot({ clip: { x: Math.max(0, info.x), y: Math.max(0, info.y), width: info.w, height: info.h } });
  await page.evaluate(() => { const [e, v] = window.__hid; e.style.visibility = v; e.querySelectorAll('*').forEach((n) => n.style.removeProperty('visibility')); });
  const ratio = await page.evaluate(async ({ b64, color, op }) => {
    const bmp = await createImageBitmap(new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: 'image/png' }));
    const cv = new OffscreenCanvas(bmp.width, bmp.height); const cx = cv.getContext('2d'); cx.drawImage(bmp, 0, 0);
    const d = cx.getImageData(0, 0, bmp.width, bmp.height).data;
    const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
    const L = (r, g, b) => .2126 * f(r) + .7152 * f(g) + .0722 * f(b);
    const m = color.match(/[\d.]+/g).map(Number); const a = (m[3] === undefined ? 1 : m[3]) * op;
    let worst = 99;
    // sample at most ~400 pixels; the worst case is whichever background pixel is closest in luminance to the ink
    const step = Math.max(1, Math.floor(d.length / 4 / 400));
    for (let i = 0; i < d.length; i += 4 * step) {
      const rr = m[0] * a + d[i] * (1 - a), gg = m[1] * a + d[i + 1] * (1 - a), bb = m[2] * a + d[i + 2] * (1 - a);
      const l1 = L(rr, gg, bb), l2 = L(d[i], d[i + 1], d[i + 2]);
      worst = Math.min(worst, (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05));
    }
    return worst;
  }, { b64: png.toString('base64'), color: info.color, op: info.op });
  const row = { label, ratio: +ratio.toFixed(2), min }; results.measured.push(row);
  if (ratio < min) fails.push(`${label}: ${ratio.toFixed(2)} < ${min}`);
}

(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
    browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
    for (const theme of ['light', 'dark']) for (const [vw, vh, vname] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
      const T = `${theme} ${vname}: `;
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: 1 });
      await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, theme);
      const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      assert.equal(r.status(), 200);
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.push(String(e)));
      page.on('console', m => m.type() === 'error' && results.errors.push(m.text()));
      await page.goto(info.url + '/admin'); await page.waitForSelector('main h1');
      await page.evaluate(mount);
      await page.waitForTimeout(900);
      if (vname === 'desktop') {
        const M = (sel, l, min, kind, nth) => measure(page, sel, T + l, min, kind, nth);
        await M('.u-chart .axis text', 'axis label text', 4.5, 'fill');
        await M('.u-chart .col', 'column fill (spend tone)', 3, 'fill');
        await M('.u-chart.tone-2 .col', 'column fill (tone 2)', 3, 'fill');
        await M('.u-chart .line', 'line stroke', 3, 'stroke');
        await M('.u-chart.tone-2 .line', 'line stroke tone 2', 3, 'stroke');
        await M('.u-chart .end-label', 'end label text', 4.5, 'fill');
        await M('.u-chart-foot button', 'show-as-table link', 4.5, 'text');
        await M('.u-spark .line', 'sparkline stroke', 3, 'stroke');
        await M('.u-bars li > .nm span', 'bar list name', 4.5, 'text');
        await M('.u-bars .val', 'bar list value', 4.5, 'text');
        await M('.u-bars .val small', 'bar list note', 4.5, 'text');
        await M('.u-bars .track i', 'bar list fill', 3, 'bg');
        await M('.u-list-title h2', 'list title', 4.5, 'text');
        await M('.u-seg button[aria-pressed="false"]', 'filter pill text', 4.5, 'text');
        await M('.u-progress .v', 'progress value', 4.5, 'text');
        await M('.pt', 'panel heading', 4.5, 'text');
        // report-only: decorative parts that a number or table repeats
        const dec = { 'grid line': ['.u-chart .grid line', 'stroke'], 'bar list track': ['.u-bars .track', 'bg'] };
        for (const [k, [sel, kind]] of Object.entries(dec)) await measure(page, sel, T + k + ' (decorative, not asserted)', 0, kind);
      }
      if (SHOTS) { await page.evaluate(() => window.scrollTo(0, 0)); fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `charts-${vname}-${theme}.png`) }); }
      await ctx.close();
    }
    results.checks.push(`${results.measured.filter(m => m.min).length} contrast measurements`);
  } finally {
    if (browser) await browser.close();
    demo.kill();
  }
  console.log(JSON.stringify(results, null, 1));
  if (fails.length && !REPORT_ONLY) { console.error('FAILURES:\n' + fails.join('\n')); process.exit(1); }
  if (results.errors.length) { console.error('ERRORS', results.errors); process.exit(1); }
})().catch(e => { console.error(e); process.exit(1); });
