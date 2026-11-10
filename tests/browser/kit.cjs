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

/* The #/kit page itself, at the acceptance sizes. Findings are gathered, not thrown, so one CI run reports every
   size and theme; the screenshots land in the workflow's /tmp/swangz-hub-* artifact. */
const fs = require('node:fs');
const { AxeBuilder } = require('@axe-core/playwright');
const KIT_OUT = process.env.KIT_PAGE_OUT || '/tmp/swangz-hub-kit-page';
const kitFindings = [];
async function kitPage(page, url, theme, vname) {
  const name = `${vname}-${theme}`, say = (m) => kitFindings.push(`${name}: ${m}`);
  const writes = [], seen = (r) => { if (/\/admin\/api\//.test(r.url()) && r.method() !== 'GET') writes.push(r.method() + ' ' + r.url()); };
  page.on('request', seen);
  try {
    const size = vname === 'desktop' ? { width: 1440, height: 852 } : { width: 390, height: 844 };
    await page.setViewportSize(size);
    await page.goto(url + '/admin#/kit'); await page.reload();
    await page.waitForFunction(() => document.querySelector('main h1')?.textContent === 'Control kit' && document.querySelector('.kit-spec'));
    await page.evaluate(() => document.fonts.ready);
    const m = await page.evaluate(() => ({
      theme: document.documentElement.dataset.theme || 'dark',
      overflow: document.documentElement.scrollWidth - innerWidth,
      panels: document.querySelectorAll('main .panel').length,
      specs: document.querySelectorAll('.kit-spec').length,
      inNav: document.querySelectorAll('a[href="#/kit"]').length,
      empty: [...document.querySelectorAll('.kit-spec')].filter(s => ![...s.querySelector('.kit-stage').children].some(c => { const r = c.getBoundingClientRect(); return r.width > 8 && r.height > 4; })).map(s => s.querySelector('.kit-state').textContent),
      spilled: [...document.querySelectorAll('.kit-stage')].flatMap(st => { const b = st.getBoundingClientRect(); return [...st.children].filter(c => { const r = c.getBoundingClientRect(); return r.right > b.right + 1 || r.left < b.left - 1; }).map(c => c.textContent.trim().slice(0, 40) || c.className); }),
      height: Math.max(document.documentElement.scrollHeight, document.querySelector('main')?.scrollHeight || 0) }));
    if (m.theme !== theme) say(`theme is ${m.theme}`);
    if (m.overflow > 0) say(`page scrolls sideways by ${m.overflow}px`);
    if (m.panels !== 9) say(`${m.panels} panels, expected 9`);
    if (m.specs < 40) say(`only ${m.specs} specimens`);
    if (m.inNav) say('the page is linked from the navigation');
    if (m.empty.length) say('nothing visible in: ' + m.empty.join(', '));
    if (m.spilled.length) say('outside its specimen: ' + m.spilled.join(', '));
    await page.screenshot({ path: path.join(KIT_OUT, `${name}.png`) });
    const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    for (const v of axe.violations) say(`axe ${v.id}: ` + v.nodes.map(n => n.target.join(' ')).join(' | '));

    const spec = (word) => page.locator('.kit-spec', { hasText: word });
    const searches = () => page.locator('input[type=search]:visible').count();
    const before = await searches();
    await spec('Nine options').locator('.u-select').click();
    await page.locator('[role=listbox]:visible').waitFor();
    if (await searches() !== before + 1) say('nine options opened without a search field');
    await page.screenshot({ path: path.join(KIT_OUT, `${name}-select-open.png`) });
    await page.keyboard.press('Escape');
    await spec('Dots').locator('.u-more').click();
    await page.locator('[role=menu]:visible').waitFor();
    await page.keyboard.press('Escape');
    await spec('Clean: closes').locator('.btn').click();
    await page.locator('.u-sheet').waitFor();
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('.u-sheet'));
    await spec('Unsaved changes').locator('.btn').click();
    await page.locator('.u-sheet').waitFor();
    await page.screenshot({ path: path.join(KIT_OUT, `${name}-sheet.png`) });
    await page.keyboard.press('Escape');
    await page.locator('.u-sheet-ask').waitFor();
    await page.getByRole('button', { name: 'Discard', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.u-sheet'));

    await page.setViewportSize({ width: size.width, height: m.height + 200 });
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(KIT_OUT, `${name}-full.png`) });
    if (writes.length) say('changed data: ' + writes.join(', '));
  } catch (e) { say('threw ' + e.message); }
  page.off('request', seen);
}

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
  window.__did = [];
  const more = SUI.menuButton({ label: 'More actions for Amina', items: () => [
    { id: 'remove', label: 'Remove person', danger: true, onSelect: (x) => window.__did.push(x.id) },
    { id: 'edit', label: 'Edit details', icon: 'edit', onSelect: (x) => window.__did.push(x.id) },
    { id: 'pause', label: 'Pause access', sub: 'Until you resume it', onSelect: (x) => window.__did.push(x.id) },
    { id: 'export', label: 'Export record', disabled: true, onSelect: (x) => window.__did.push(x.id) },
    { id: 'reset', label: 'Reset sign-in', onSelect: (x) => window.__did.push(x.id) }] });
  more.dataset.t = 'more';
  const split = SUI.splitButton({ label: 'Export', icon: 'download', menuLabel: 'More export formats', primary: true, onClick: () => window.__did.push('csv'),
    items: [{ id: 'pdf', label: 'Export as PDF', onSelect: (x) => window.__did.push(x.id) }, { id: 'sheet', label: 'Export as a spreadsheet', onSelect: (x) => window.__did.push(x.id) }] });
  split.dataset.t = 'split';
  window.__filt = [];
  const opt = (a) => a.map((x) => ({ id: x.toLowerCase(), label: x }));
  const bar = SUI.filterBar({ label: 'Filter people', search: { placeholder: 'Search people' }, values: { status: 'paused' }, onChange: (v, id) => window.__filt.push(JSON.stringify(v) + '|' + id),
    filters: [{ id: 'team', label: 'Team', options: opt(['Creative', 'Finance', 'Sales']) }, { id: 'role', label: 'Role', options: opt(['Owner', 'Staff']) },
      { id: 'status', label: 'Status', options: opt(['Active', 'Paused']) }, { id: 'tool', label: 'Tool', options: opt(['ChatGPT', 'Claude']) }, { id: 'device', label: 'Device', options: opt(['Laptop', 'Phone']) }] });
  bar.dataset.t = 'bar';
  window.__sheet = [];
  const openSheet = el('button', { type: 'button', class: 'btn' }, 'Add person');
  openSheet.dataset.t = 'sheet';
  openSheet.addEventListener('click', () => {
    const name = el('input', { type: 'text', 'aria-label': 'Name' });
    const filler = el('div'); filler.style.height = '1400px';
    window.__api = SUI.sheet({ title: 'Add a person', purpose: 'They can sign in once you save.', body: el('div', null, name, filler), dirty: () => name.value !== '',
      primary: { label: 'Save person', onClick: (api) => { window.__sheet.push('save:' + name.value); api.close(true); } }, onClose: () => window.__sheet.push('closed') });
  });
  const row = el('div', null, team, ' ', tool, ' ', off, ' ', more, ' ', split, ' ', openSheet);
  row.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;padding:16px 0';
  const foot = el('div', null, low);
  foot.style.cssText = 'position:fixed;left:50%;bottom:16px;z-index:5';
  document.querySelector('main').replaceChildren(el('h1', null, 'Control kit'), row, bar);
  document.body.append(foot);
};

(async () => {
  const demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let browser;
  try {
    const info = await new Promise((res, rej) => { let b = ''; const t = setTimeout(() => rej(new Error('demo timeout')), 30000);
      demo.stdout.on('data', d => { b += d; if (b.includes('\n')) { clearTimeout(t); res(JSON.parse(b.split('\n')[0])); } });
      demo.on('exit', c => c && rej(new Error('demo exit ' + c))); });
    fs.mkdirSync(KIT_OUT, { recursive: true });
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
      {
        const M = T.replace('select', 'menu');
        const ms = () => page.evaluate(() => { const p = document.querySelector('.u-pop-menu'); const a = document.activeElement;
          return { open: !!p, focus: a && (a.dataset.t || a.dataset.id || a.tagName), expanded: document.querySelector('[data-t=more]').getAttribute('aria-expanded') }; });
        const b = await page.evaluate(() => { const x = document.querySelector('[data-t=more]'); const r = x.getBoundingClientRect();
          return { w: r.width, h: r.height, name: x.getAttribute('aria-label'), popup: x.getAttribute('aria-haspopup'), radius: getComputedStyle(x).borderTopLeftRadius }; });
        ok(M + 'the More button is a named square box that says it opens a menu', b.name === 'More actions for Amina' && b.popup === 'menu' && b.radius === '10px' && b.w === b.h && b.h === (vname === 'mobile' ? 44 : 36));
        await page.focus('[data-t=more]'); await page.keyboard.press('Enter');
        let m = await ms();
        ok(M + 'Enter opens it on the first item', m.open && m.focus === 'edit' && m.expanded === 'true');
        const shape = await page.evaluate(() => { const p = document.querySelector('.u-pop-menu'), items = [...p.querySelectorAll('[role=menuitem]')], last = items[items.length - 1];
          const sep = p.querySelector('[role=separator]'); const br = document.querySelector('[data-t=more]').getBoundingClientRect(), pr = p.getBoundingClientRect();
          return { role: p.querySelector('.u-menu').getAttribute('role'), ids: items.map(x => x.dataset.id), sepBeforeLast: sep && sep.nextElementSibling === last, danger: last.classList.contains('danger'),
            dangerColour: getComputedStyle(last).color !== getComputedStyle(items[0]).color, radius: getComputedStyle(items[0]).borderTopLeftRadius, rowH: items[0].getBoundingClientRect().height,
            right: Math.abs(pr.right - br.right), gap: pr.top - br.bottom, bottom: innerHeight - pr.bottom, inside: pr.left >= 0 && pr.right <= innerWidth }; });
        ok(M + 'the destructive item is last, under a rule, in the danger colour', shape.role === 'menu' && shape.ids.join() === 'edit,pause,export,reset,remove' && shape.sepBeforeLast && shape.danger && shape.dangerColour);
        ok(M + 'rows have 8px corners' + (vname === 'mobile' ? ' and 44px targets' : ''), shape.radius === '8px' && shape.rowH >= (vname === 'mobile' ? 44 : 36));
        ok(M + (vname === 'mobile' ? 'on a phone it is a sheet along the bottom' : 'it opens under the button, right edges aligned'), shape.inside && (vname === 'mobile' ? shape.bottom <= 12 : shape.right <= 1 && shape.gap >= 4 && shape.gap <= 8));
        await page.keyboard.press('ArrowDown'); await page.keyboard.press('ArrowDown');
        ok(M + 'arrows move and skip a disabled item', (await ms()).focus === 'reset');
        await page.keyboard.press('ArrowDown'); await page.keyboard.press('ArrowDown');
        ok(M + 'the arrows wrap round', (await ms()).focus === 'edit');
        await page.keyboard.press('End');
        ok(M + 'End goes to the last item', (await ms()).focus === 'remove');
        await page.keyboard.press('p');
        ok(M + 'a letter jumps to the item starting with it', (await ms()).focus === 'pause');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `menu-${vname}-${theme}.png`) });
        await page.keyboard.press('Escape');
        m = await ms();
        ok(M + 'Esc closes it and focus returns to the button', !m.open && m.focus === 'more' && m.expanded === 'false');
        await page.keyboard.press('ArrowUp');
        ok(M + 'ArrowUp opens it on the last item', (await ms()).focus === 'remove');
        await page.keyboard.press('Home'); await page.keyboard.press('Enter');
        m = await ms();
        ok(M + 'Enter runs the item, closes the menu and returns focus', !m.open && m.focus === 'more' && (await page.evaluate(() => window.__did.join())) === 'edit');
        await page.click('[data-t=more]');
        await page.evaluate(() => document.querySelector('.u-pop-menu [data-id=export]').click());
        ok(M + 'a disabled item does nothing and the menu stays', (await ms()).open && (await page.evaluate(() => window.__did.join())) === 'edit');
        await page.click('.u-pop-menu [data-id=pause]');
        ok(M + 'a press runs the item', !(await ms()).open && (await page.evaluate(() => window.__did.join())) === 'edit,pause');
        await page.click('[data-t=more]'); await page.click('main h1');
        ok(M + 'a press outside closes it', !(await ms()).open);
      }
      {
        const S = T.replace('select', 'split button');
        await page.evaluate(() => { window.__did = []; });
        const g = await page.evaluate(() => { const x = document.querySelector('[data-t=split]'), a = x.querySelector('.u-split-main'), b = x.querySelector('.u-split-more');
          const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect(), ca = getComputedStyle(a), cb = getComputedStyle(b);
          return { role: x.getAttribute('role'), group: x.getAttribute('aria-label'), name: b.getAttribute('aria-label'), popup: b.getAttribute('aria-haspopup'), joined: Math.abs(ar.right - br.left) < 0.5,
            sameH: ar.height === br.height, h: ar.height, bw: br.width, left: ca.borderTopLeftRadius, mid: ca.borderTopRightRadius + cb.borderTopLeftRadius, right: cb.borderTopRightRadius, main: a.textContent }; });
        ok(S + 'two joined parts in one 10px box, the chevron part named', g.role === 'group' && g.group === 'Export' && g.name === 'More export formats' && g.popup === 'menu' && g.joined && g.sameH
          && g.left === '10px' && g.right === '10px' && g.mid === '0px0px' && g.main === 'Export' && g.h === (vname === 'mobile' ? 44 : 38) && g.bw >= (vname === 'mobile' ? 44 : 34));
        await page.click('[data-t=split] .u-split-main');
        ok(S + 'the main part does the common action without opening anything', (await page.evaluate(() => window.__did.join())) === 'csv' && !(await page.evaluate(() => !!document.querySelector('.u-pop'))));
        await page.keyboard.press('Tab'); await page.keyboard.press('ArrowDown');
        const o = await page.evaluate(() => { const p = document.querySelector('.u-pop-menu'), a = document.activeElement; const pr = p && p.getBoundingClientRect(), gr = document.querySelector('[data-t=split]').getBoundingClientRect();
          return { open: !!p, focus: a.dataset.id, n: p ? p.querySelectorAll('[role=menuitem]').length : 0, right: p ? Math.abs(pr.right - gr.right) : 99 }; });
        ok(S + 'Tab reaches the chevron part and ArrowDown opens the variants', o.open && o.focus === 'pdf' && o.n === 2 && (vname === 'mobile' || o.right <= 1));
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `split-${vname}-${theme}.png`) });
        await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
        const d = await page.evaluate(() => ({ did: window.__did.join(), open: !!document.querySelector('.u-pop'), back: document.activeElement.classList.contains('u-split-more') }));
        ok(S + 'choosing a variant runs it and focus returns to the chevron part', d.did === 'csv,sheet' && !d.open && d.back);
      }
      {
        const F = T.replace('select', 'filter bar');
        const fs = () => page.evaluate(() => { const b = document.querySelector('[data-t=bar]'), a = document.activeElement;
          return { controls: [...b.querySelectorAll('.u-filter-row > *')].map(x => x.dataset.filter || (x.classList.contains('u-search') ? 'search' : x.classList.contains('u-filter-more') ? 'more' : '?')).join(),
            chips: [...b.querySelectorAll('.u-chip')].map(x => x.textContent).join('|'), names: [...b.querySelectorAll('.u-chip')].map(x => x.getAttribute('aria-label')).join('|'),
            clear: !!b.querySelector('.u-chip-clear'), hidden: b.querySelector('.u-chips').hidden, focus: a.dataset.filter ? (a.classList.contains('u-chip') ? 'chip:' : 'select:') + a.dataset.filter : a.tagName + '.' + a.className,
            last: window.__filt[window.__filt.length - 1], n: window.__filt.length, vals: JSON.stringify(b.values()) }; });
        let f = await fs();
        const look = await page.evaluate(() => { const b = document.querySelector('[data-t=bar]'), c = b.querySelector('.u-chip');
          return { role: b.getAttribute('role'), name: b.getAttribute('aria-label'), chipRadius: getComputedStyle(c).borderTopLeftRadius, chipH: c.getBoundingClientRect().height,
            under: c.getBoundingClientRect().top >= b.querySelector('.u-filter-row').getBoundingClientRect().bottom, status: b.querySelector('[data-filter=status].u-select').textContent }; });
        ok(F + 'search, three dropdown filters and More filters, in that order', f.controls === 'search,team,role,status,more' && look.role === 'search' && look.name === 'Filter people');
        ok(F + 'an active filter is a removable 6px chip under the bar, with Clear all', f.chips === 'Status: Paused' && f.names === 'Remove filter Status: Paused' && f.clear && look.under && look.chipRadius === '6px'
          && look.status === 'Paused' && look.chipH >= (vname === 'mobile' ? 44 : 28));
        await page.click('[data-t=bar] [data-filter=team].u-select');
        await page.click('.u-pop [role=option]:has-text("Finance")');
        f = await fs();
        ok(F + 'choosing a value adds its chip, tells the page and keeps focus on the filter', f.chips === 'Team: Finance|Status: Paused' && f.last === '{"status":"paused","team":"finance"}|team' && f.focus === 'select:team');
        await page.click('[data-t=bar] .u-filter-more');
        const extra = await page.evaluate(() => [...document.querySelectorAll('.u-pop-menu [role=menuitem]')].map(x => x.textContent).join());
        await page.click('.u-pop-menu [data-id=device]');
        const opened = await page.evaluate(() => ({ list: !!document.querySelector('.u-pop-select'), label: document.querySelector('.u-pop-select [role=listbox]').getAttribute('aria-label') }));
        ok(F + 'More filters lists the rest; picking one adds that filter and opens it', extra === 'Tool,Device' && opened.list && opened.label === 'Device');
        await page.click('.u-pop [role=option]:has-text("Phone")');
        f = await fs();
        ok(F + 'the added filter sits in the bar with its chip', f.controls === 'search,team,role,status,device,more' && f.chips === 'Team: Finance|Status: Paused|Device: Phone');
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `filter-${vname}-${theme}.png`) });
        await page.focus('[data-t=bar] .u-chip[data-filter=team]'); await page.keyboard.press('Enter');
        f = await fs();
        ok(F + 'removing a chip clears that filter and moves focus to the next chip', f.chips === 'Status: Paused|Device: Phone' && f.focus === 'chip:status' && f.last === '{"status":"paused","device":"phone"}|team');
        await page.fill('[data-t=bar] input[type=search]', 'ami');
        await page.waitForFunction(() => /"q":"ami"/.test(window.__filt[window.__filt.length - 1]));
        ok(F + 'typing in search tells the page once it settles', /\|q$/.test((await fs()).last));
        await page.click('[data-t=bar] .u-chip-clear');
        f = await fs();
        ok(F + 'Clear all removes every filter and the search text, and hides the chip row', f.vals === '{}' && f.hidden && f.controls === 'search,team,role,status,more' && f.last === '{}|null'
          && (await page.inputValue('[data-t=bar] input[type=search]')) === '');
      }
      {
        const H = T.replace('select', 'side sheet');
        const hs = () => page.evaluate(() => { const n = document.querySelector('.u-sheet'), a = document.activeElement;
          return { open: !!n, scrim: !!document.querySelector('.u-sheet-scrim'), focus: a.dataset.t || a.getAttribute('aria-label') || a.textContent, foot: n ? [...n.querySelectorAll('.u-sheet-foot button')].map(x => x.textContent).join() : '',
            ask: n && n.querySelector('.u-sheet-ask') ? n.querySelector('.u-sheet-ask').textContent : '', log: window.__sheet.join() }; });
        await page.click('[data-t=sheet]');
        await page.waitForFunction(() => { const n = document.querySelector('.u-sheet.in'); return n && Math.abs(n.getBoundingClientRect().right - innerWidth) < 1; });
        const g = await page.evaluate(() => { const n = document.querySelector('.u-sheet'), r = n.getBoundingClientRect(), f = n.querySelector('.u-sheet-foot').getBoundingClientRect(), b = n.querySelector('.u-sheet-body');
          return { w: r.width, top: r.top, h: r.height, role: n.getAttribute('role'), modal: n.getAttribute('aria-modal'), title: document.getElementById(n.getAttribute('aria-labelledby')).textContent,
            purpose: document.getElementById(n.getAttribute('aria-describedby')).textContent, footBottom: Math.abs(f.bottom - innerHeight), scrolls: b.scrollHeight > b.clientHeight,
            btnH: Math.min(...[...n.querySelectorAll('button')].map(x => x.getBoundingClientRect().height)) }; });
        ok(H + (vname === 'mobile' ? 'it fills the phone screen' : 'it is a 480px panel on the right, full height'), g.w === (vname === 'mobile' ? vw : 480) && g.top === 0 && g.h === vh);
        ok(H + 'it is a modal dialog named by its title and described by its purpose', g.role === 'dialog' && g.modal === 'true' && g.title === 'Add a person' && g.purpose === 'They can sign in once you save.');
        ok(H + 'the body scrolls and the footer stays at the bottom with Cancel then the primary', g.scrolls && g.footBottom < 1 && (await hs()).foot === 'Cancel,Save person' && g.btnH >= (vname === 'mobile' ? 44 : 36));
        ok(H + 'focus starts in the first field', (await hs()).focus === 'Name');
        await page.keyboard.press('Shift+Tab');
        const wrapped = await page.evaluate(() => !!document.activeElement.closest('.u-sheet'));
        await page.keyboard.press('Tab');
        ok(H + 'Tab stays inside the sheet', wrapped && (await page.evaluate(() => !!document.activeElement.closest('.u-sheet'))));
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `sheet-${vname}-${theme}.png`) });
        await page.keyboard.press('Escape');
        await page.waitForFunction(() => !document.querySelector('.u-sheet'));
        let h = await hs();
        ok(H + 'Esc closes it and focus returns to where it came from', !h.scrim && h.focus === 'sheet' && h.log === 'closed');
        await page.click('[data-t=sheet]');
        await page.fill('.u-sheet input', 'Amina');
        await page.keyboard.press('Escape');
        h = await hs();
        ok(H + 'with unsaved changes, closing asks first', h.open && h.ask === 'Discard your unsaved changes?' && h.foot === 'Keep editing,Discard' && h.focus === 'Keep editing');
        await page.keyboard.press('Escape');
        h = await hs();
        ok(H + 'Esc on the question keeps editing', h.open && h.foot === 'Cancel,Save person' && (await page.inputValue('.u-sheet input')) === 'Amina');
        await page.click('.u-sheet-x');
        await page.click('.u-sheet-foot .btn.danger');
        await page.waitForFunction(() => !document.querySelector('.u-sheet'));
        ok(H + 'Discard closes it', (await hs()).log === 'closed,closed');
        await page.click('[data-t=sheet]');
        await page.fill('.u-sheet input', 'Brian');
        await page.click('.u-sheet-foot .btn.primary');
        await page.waitForFunction(() => !document.querySelector('.u-sheet'));
        ok(H + 'the primary action runs and can close without asking', (await hs()).log === 'closed,closed,save:Brian,closed');
      }
      ok(T + 'no horizontal page scroll', (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
      await kitPage(page, info.url, theme, vname);
      await ctx.close();
    }
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 852 }, reducedMotion: 'reduce' });
      const r = await ctx.request.post(info.url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'operations@swangzavenue.com', password: 'operations-password' } });
      assert.equal(r.status(), 200);
      const page = await ctx.newPage();
      await page.goto(info.url + '/admin#/kit');
      await page.getByText('Owners only', { exact: true }).waitFor();
      ok('kit page: a non-owner sees no controls', await page.locator('.kit-spec').count() === 0);
      await ctx.close();
    }
    fs.writeFileSync(path.join(KIT_OUT, 'findings.json'), JSON.stringify(kitFindings, null, 1));
    assert.deepEqual(kitFindings, [], 'kit page findings');
    assert.deepEqual(results.errors, [], 'console errors');
    console.log(JSON.stringify({ checks: results.checks.length, errors: results.errors }, null, 1));
  } finally { if (browser) await browser.close(); demo.kill(); }
})().catch(e => { console.error(e); process.exit(1); });
