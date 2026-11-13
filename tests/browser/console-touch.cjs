/* Console controls on a phone (Probe's check of main fd69d51, 13 Nov): at 390x844 every visible button, field, select,
   search box and time-range chip on the console's pages has a visible box at least 44px tall, not only a ::before hit
   layer; nothing overflows sideways at 390 or 1440. Also: no page says "Gateway" where it means the product, and the
   clock reads "Hub time". Local fixture only, one browser. Set UI_OUTPUT to keep screenshots. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = process.env.GATEWAY_UI_ROOT || path.resolve(__dirname, '../..');
const out = process.env.UI_OUTPUT || '';
const MIN = 44;
const PAGES = ['#/', '#/?view=detailed', '#/security?view=detailed', '#/attention', '#/activity', '#/activity?tab=requests', '#/people', '#/tools', '#/models', '#/policies',
  '#/licences', '#/requests', '#/devices', '#/audit', '#/incidents', '#/security', '#/settings', '#/settings?section=purpose', '#/health'];
// What a person taps: buttons, links styled as buttons, fields, selects, the search box (its whole label), view and range chips.
const CONTROLS = ['main .btn', 'main select', 'main input:not([type=checkbox]):not([type=radio]):not([type=color]):not([type=range]):not([type=hidden]):not(.u-search input)',
  'main label.u-search', 'main .u-seg button', 'main .u-range button', 'main textarea'];
// The search input fills its label: the label's 44px box less its two 1px borders.
const INNER = { 'main .u-search input': MIN - 2 };
let demo, browser, checks = 0;
(async () => {
  try {
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_UI_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    const { url } = await new Promise((resolve, reject) => {
      let buf = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 60000);
      demo.stdout.on('data', d => { buf += d; if (buf.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(buf.split('\n')[0])); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined, args: ['--no-sandbox'] });
    const failures = [], found = new Set();
    for (const [width, height] of [[390, 844], [1440, 852]]) for (const theme of ['dark', 'light']) {
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      assert.equal((await c.request.post(url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      const p = await c.newPage(); const errors = [];
      p.on('pageerror', e => errors.push(String(e)));
      for (const hash of PAGES) {
        const T = `${width} ${theme} ${hash}: `;
        await p.goto(url + '/admin' + hash); await p.reload();
        await p.locator('main h1').first().waitFor(); await p.waitForLoadState('networkidle'); await p.waitForTimeout(150);
        const seen = await p.evaluate(sels => {
          const shown = n => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(n).visibility !== 'hidden' && !n.closest('[hidden], dialog:not([open])'); };
          const label = n => (n.getAttribute('aria-label') || n.textContent || n.placeholder || n.value || '').trim().replace(/\s+/g, ' ').slice(0, 30);
          return {
            controls: sels.flatMap(sel => [...document.querySelectorAll(sel)].filter(shown).map(n => { const r = n.getBoundingClientRect(); return [sel, Math.round(r.height * 10) / 10, `${Math.round(r.width)}x${Math.round(r.height)} ${sel} "${label(n)}"`]; })),
            overflow: document.documentElement.scrollWidth - innerWidth,
            text: document.querySelector('main').innerText + ' ' + [...document.querySelectorAll('[title], [data-tip], [aria-label]')].map(n => n.getAttribute('title') || n.getAttribute('data-tip') || n.getAttribute('aria-label')).join(' '),
          };
        }, [...CONTROLS, ...Object.keys(INNER)]);
        assert.equal(seen.overflow, 0, T + 'no sideways overflow'); checks++;
        assert.doesNotMatch(seen.text, /through Gateway|Gateway time/, T + 'plain words'); checks++;
        if (width === 390) for (const [sel, h, what] of seen.controls) { found.add(sel); checks++; if (h < (INNER[sel] || MIN)) failures.push(T + what); }
        if (out && theme === 'dark' && ['#/activity?tab=requests', '#/people', '#/audit', '#/settings?section=purpose'].includes(hash))
          await p.screenshot({ path: path.join(out, `console-${hash.replace(/[#/?=&]+/g, '-').replace(/^-|-$/g, '') || 'overview'}-${width}x${height}-${theme}.png`) });
      }
      // The clock in the header says whose time it shows, in plain words.
      const clock = await p.evaluate(() => [...document.querySelectorAll('[title], [data-tip], [aria-label]')].map(n => n.getAttribute('title') || n.getAttribute('data-tip') || n.getAttribute('aria-label')).filter(t => /time/i.test(t)).join(' | '));
      assert.match(clock, /Hub time/, `${width} ${theme}: the clock says Hub time (${clock})`); checks++;
      assert.deepEqual(errors, [], `${width} ${theme}: page errors`);
      await c.close();
    }
    assert.deepEqual(['main .btn', 'main select', 'main label.u-search', 'main .u-search input', 'main .u-seg button', 'main .u-range button'].filter(s => !found.has(s)), [], 'the check found every kind of control');
    assert.deepEqual([...new Set(failures)], [], 'console controls under ' + MIN + 'px at 390');
    console.log(`console-touch.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
