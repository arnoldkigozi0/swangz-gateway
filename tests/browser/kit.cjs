/* The shared control kit (BRIEF 10.10 point 5), one control at a time: here the dropdown select (SUI.select).
   NODE_PATH must reach a tooling dir with playwright (never installed in the repo). Starts tests/browser/demo.py (test database).
   The page is the real console with fixture controls mounted by SUI in main. SHOTS=<dir> also saves screenshots. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const results = { checks: [], errors: [] };
const ok = (label, v) => { assert.ok(v, label); results.checks.push(label); };
const SHOTS = process.env.SHOTS;

const mount = () => {
  const { el } = SUI;
  window.__picked = [];
  const teams = ['Creative', 'Finance', 'Operations', 'Sales', 'Strategy', 'Studio'].map((x) => ({ id: x.toLowerCase(), label: x }));
  const tools = ['Canva', 'ChatGPT', 'Claude', 'Cursor', 'ElevenLabs', 'Gemini', 'Higgsfield', 'Midjourney', 'Notion AI', 'Perplexity', 'Runway', 'Suno']
    .map((x) => ({ id: x.toLowerCase(), label: x, sub: x === 'Claude' ? 'Assistant' : null }));
  const team = SUI.select({ label: 'Team', options: teams, value: 'finance', onChange: (id) => window.__picked.push(id) });
  const tool = SUI.select({ label: 'Tool', options: tools, placeholder: 'Any tool', onChange: (id) => window.__picked.push(id) });
  const off = SUI.select({ label: 'Role', options: teams, value: 'sales', disabled: true });
  const low = SUI.select({ label: 'Period', options: teams, value: 'studio' });
  team.dataset.t = 'team'; tool.dataset.t = 'tool'; off.dataset.t = 'off'; low.dataset.t = 'low';
  const row = el('div', null, team, ' ', tool, ' ', off);
  row.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;padding:16px 0';
  const foot = el('div', null, low);
  foot.style.cssText = 'position:fixed;left:50%;bottom:16px;z-index:5';
  document.querySelector('main').replaceChildren(el('h1', null, 'Control kit'), row);
  document.body.append(foot);
};

(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
    browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome' });
    for (const theme of ['dark', 'light']) for (const [vw, vh, vname] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
      const T = `${theme} ${vname} select: `;
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: 1, hasTouch: vname === 'mobile', reducedMotion: 'reduce' });
      await ctx.addInitScript(t => { try { localStorage.setItem('swangz-theme', t); localStorage.setItem('theme', t); } catch (e) {} }, theme);
      const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } });
      assert.equal(r.status(), 200);
      const page = await ctx.newPage();
      page.on('pageerror', e => results.errors.push(String(e)));
      page.on('console', m => m.type() === 'error' && results.errors.push(m.text()));
      await page.goto(info.url + '/admin');
      await page.waitForSelector('main h1');
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(mount);
      const team = '[data-t=team]', tool = '[data-t=tool]';
      const state = () => page.evaluate(() => {
        const p = document.querySelector('.u-pop'); const a = document.activeElement;
        const act = p && p.querySelector('li.on');
        return { open: !!p, focus: a && (a.dataset.t || a.getAttribute('role') || a.tagName), active: act && act.textContent, described: a && a.getAttribute('aria-activedescendant'), actId: act && act.id,
          options: p ? p.querySelectorAll('[role=option]').length : 0, selected: p ? [...p.querySelectorAll('[aria-selected=true]')].map(x => x.textContent) : [] };
      });

      const closed = await page.evaluate(() => { const b = document.querySelector('[data-t=team]'); const cs = getComputedStyle(b);
        return { radius: cs.borderTopLeftRadius, h: b.getBoundingClientRect().height, popup: b.getAttribute('aria-haspopup'), expanded: b.getAttribute('aria-expanded'), name: b.getAttribute('aria-label'), text: b.textContent,
          off: document.querySelector('[data-t=off]').disabled, offOpacity: getComputedStyle(document.querySelector('[data-t=off]')).opacity, ph: document.querySelector('[data-t=tool]').textContent }; });
      ok(T + 'the trigger is a 10px box that names itself and its value', closed.radius === '10px' && closed.popup === 'listbox' && closed.expanded === 'false' && closed.name === 'Team: Finance' && closed.text === 'Finance');
      ok(T + 'trigger height (38 on desktop, 44 on phones)', vname === 'mobile' ? closed.h >= 44 : Math.abs(closed.h - 38) <= 1);
      ok(T + 'disabled is disabled and dimmed; an empty one shows its placeholder', closed.off && closed.offOpacity === '0.45' && closed.ph === 'Any tool');

      await page.click(team);
      let s = await state();
      const geo = await page.evaluate(() => { const b = document.querySelector('[data-t=team]').getBoundingClientRect(), p = document.querySelector('.u-pop').getBoundingClientRect(), li = document.querySelector('.u-pop li');
        return { under: p.top - b.bottom, left: p.left - b.left, right: p.right, bottom: p.bottom, vw: innerWidth, vh: innerHeight, rowH: li.getBoundingClientRect().height, rowR: getComputedStyle(li).borderTopLeftRadius,
          expanded: document.querySelector('[data-t=team]').getAttribute('aria-expanded'), tick: !!document.querySelector('.u-pop [aria-selected=true] .tick'), search: !!document.querySelector('.u-pop input') }; });
      ok(T + 'a click opens a listbox with every option, the current one ticked, focus inside', s.open && s.options === 6 && s.selected.join() === 'Finance' && geo.tick && geo.expanded === 'true' && s.focus === 'listbox' && s.active === 'Finance' && s.described === s.actId);
      ok(T + 'rows are 8px boxes; six options get no search field', geo.rowR === '8px' && !geo.search);
      if (vname === 'mobile') ok(T + 'on a phone the list is a sheet along the bottom with 44px rows', geo.rowH >= 44 && geo.vh - geo.bottom <= 12 && geo.right <= geo.vw);
      else ok(T + 'the list opens just under its trigger, inside the window', geo.under >= 4 && geo.under <= 8 && Math.abs(geo.left) <= 1 && geo.right <= geo.vw && geo.bottom <= geo.vh);
      if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `select-${vname}-${theme}.png`) });

      await page.keyboard.press('ArrowDown');
      ok(T + 'arrow down moves to the next option', (await state()).active === 'Operations');
      await page.keyboard.press('End');
      ok(T + 'End goes to the last option', (await state()).active === 'Studio');
      await page.keyboard.press('s');
      ok(T + 'typing a letter jumps to the next match', (await state()).active === 'Sales');
      await page.keyboard.press('Enter');
      s = await state();
      const after = await page.evaluate(() => ({ text: document.querySelector('[data-t=team]').textContent, name: document.querySelector('[data-t=team]').getAttribute('aria-label'), picked: window.__picked.slice(), value: document.querySelector('[data-t=team]').value }));
      ok(T + 'Enter chooses: the list closes, focus returns, the value and its name change, onChange fires once', !s.open && s.focus === 'team' && after.text === 'Sales' && after.name === 'Team: Sales' && after.picked.join() === 'sales' && after.value === 'sales');

      await page.keyboard.press('ArrowDown');
      ok(T + 'arrow down on the trigger opens it', (await state()).open);
      await page.keyboard.press('ArrowUp'); await page.keyboard.press('Space');
      s = await state();
      ok(T + 'Space chooses too, and its key-up does not reopen the list', !s.open && s.focus === 'team' && (await page.evaluate(() => document.querySelector('[data-t=team]').textContent)) === 'Operations');
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('Escape');
      s = await state();
      ok(T + 'Esc closes it, returns focus and changes nothing', !s.open && s.focus === 'team' && (await page.evaluate(() => window.__picked.length)) === 2);
      await page.keyboard.press('Enter');
      ok(T + 'Enter on the trigger opens it', (await state()).open);
      await page.click('main h1');
      ok(T + 'a press outside closes it', !(await state()).open);

      await page.click(tool);
      s = await state();
      ok(T + 'twelve options get a search field, which takes focus', s.open && s.options === 12 && s.focus === 'combobox');
      await page.keyboard.type('cl');
      s = await state();
      ok(T + 'typing in the field narrows the list', s.options === 1 && /^Claude/.test(s.active));
      await page.keyboard.type('zz');
      const none = await page.evaluate(() => { const e = document.querySelector('.u-pop-empty'); return e.hidden ? '' : e.textContent; });
      ok(T + 'no match says so in words', (await state()).options === 0 && /Nothing matches/.test(none));
      await page.keyboard.press('Backspace'); await page.keyboard.press('Backspace');
      await page.keyboard.press('Enter');
      ok(T + 'Enter in the field chooses the match', (await page.evaluate(() => document.querySelector('[data-t=tool]').textContent)) === 'Claude' && !(await state()).open);

      if (vname === 'desktop') {
        await page.click('[data-t=low]');
        await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
        const flip = await page.evaluate(() => { const b = document.querySelector('[data-t=low]').getBoundingClientRect(), p = document.querySelector('.u-pop').getBoundingClientRect(); return { gap: b.top - p.bottom, top: p.top, bTop: b.top, bBottom: b.bottom, pBottom: p.bottom, ih: innerHeight, up: document.querySelector('.u-pop').className }; });
        ok(T + 'with no room below, the list opens above its trigger ' + JSON.stringify(flip), flip.gap >= 4 && flip.gap <= 8 && flip.top >= 8);
        await page.click(team);
        ok(T + 'opening another closes the first: one list at a time', (await page.evaluate(() => document.querySelectorAll('.u-pop').length)) === 1);
        await page.keyboard.press('Escape');
      }
      ok(T + 'no horizontal page scroll', (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
      await ctx.close();
    }
    assert.deepEqual(results.errors, [], 'console errors');
    console.log(JSON.stringify({ checks: results.checks.length, errors: results.errors }, null, 1));
  } finally { if (browser) await browser.close(); demo.kill(); }
})().catch(e => { console.error(e); process.exit(1); });
