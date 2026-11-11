/* Tools on the control kit (BRIEF 10.10): filter bar and pages in the address, a More menu on every row, Remove and
   Restore working, and the tool record. UI_OUTPUT also writes the 1440x852 and 390x844 evidence. Local fixture only. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const root = process.env.GATEWAY_UI_ROOT || path.resolve(__dirname, '../..');
const output = process.env.UI_OUTPUT || '';
if (output) fs.mkdirSync(output, { recursive: true });
let demo, browser, checks = 0;
const ok = (name, cond) => { assert.ok(cond, name); checks++; };
(async () => {
  try {
    demo = spawn('python3', [path.join(root, 'tests/browser/demo.py')], { cwd: root, env: { ...process.env, HUB_UI_FIXTURE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    const info = await new Promise((resolve, reject) => {
      let out = ''; const timer = setTimeout(() => reject(Error('Fixture timeout')), 60000);
      demo.stdout.on('data', d => { out += d; if (out.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(out.split('\n')[0])); } });
      demo.on('exit', code => reject(Error('Fixture exited: ' + code)));
    });
    const url = info.url;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME || undefined, args: ['--no-sandbox'] });
    const cells = [['dark', 1440, 852], ['light', 1440, 852], ['dark', 390, 844], ['light', 390, 844]];
    for (const [theme, width, height] of cells) {
      const T = `${theme} ${width}: `;
      const shot = async (p, name) => { if (output) await p.screenshot({ path: path.join(output, `${name}-${width}x${height}-${theme}.png`) }); };
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      await c.addInitScript(t => localStorage.setItem('swangz-theme', t), theme);
      const headers = { 'x-gateway-admin': '1' };
      assert.equal((await c.request.post(url + '/admin/api/login', { headers, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      const axe = async (name) => { const r = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); assert.deepEqual(r.violations.map(v => v.id + ' ' + v.nodes.map(n => n.target).join(',')), [], T + name + ' axe'); checks++; };
      const noOverflow = async (name) => ok(T + name + ' has no sideways page scroll', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const open = async (hash) => { await p.goto(url + '/admin' + hash); await p.reload(); await p.locator('.u-filter').waitFor(); await p.waitForLoadState('networkidle'); };
      const hash = () => p.evaluate(() => location.hash);
      const rowMenu = async (name) => { await p.getByRole('button', { name: 'More actions for ' + name, exact: true }).click(); await p.locator('.u-pop-menu').waitFor(); };

      // the list: kit filter bar, the trail, a More menu on every row
      await open('#/tools');
      ok(T + 'the old tabs and native select are gone', await p.locator('main .fb-select, main .seg').count() === 0);
      if (width > 1200) ok(T + 'the top bar names the page', (await p.locator('.console-trail .crumb-here').textContent()) === 'Tools');
      await noOverflow('list'); await axe('list'); await shot(p, 'tools-list');

      // Show goes in the address, shows as a chip, and the full catalogue pages
      await p.locator('.u-filter .u-select[data-filter=show]').click();
      await p.locator('.u-pop-select [role=option]').filter({ hasText: /^All/ }).click();
      await p.locator('.u-chip[data-filter=show]').waitFor();
      ok(T + 'Show is in the address', (await hash()).includes('show=all'));
      const range = p.locator('.u-pager-range');
      const total = Number((await range.textContent()).split(' of ')[1]);
      ok(T + 'the catalogue is over one page', total > 25 && (await range.textContent()).startsWith('1–25 of'));
      ok(T + 'a page holds 25 rows', await p.locator('.u-table tbody tr').count() === 25);
      ok(T + 'every row ends in one More button', await p.locator('.u-table tbody tr button[aria-label^="More actions for"]').count() === 25);
      await noOverflow('all tools'); await axe('all tools'); await shot(p, 'tools-all');
      const next = p.locator('.u-pager').getByRole('button', { name: 'Next' });
      await next.click();
      ok(T + 'Next turns the page', (await range.textContent()).startsWith('26–') && (await hash()).includes('page=2'));
      await open('#/tools?show=all&page=2');
      ok(T + 'the page survives a reload', (await range.textContent()).startsWith('26–'));
      await p.locator('.u-chip-clear').click();
      ok(T + 'Clear all goes back to In use', !/show=|page=/.test(await hash()));

      // Remove and Restore through the row menu
      await open('#/tools?show=all&q=Suno');
      await rowMenu('Suno');
      ok(T + 'the row menu links to the record', await p.locator('.u-pop-menu [role=menuitem][data-id=access]').getAttribute('href') === '#/tools?show=all&q=Suno&open=suno&tab=access');
      await shot(p, 'tools-row-menu');
      await p.locator('.u-pop-menu [role=menuitem][data-id=remove]').click();
      await p.getByRole('dialog').getByRole('button', { name: 'Remove', exact: true }).click();
      await p.locator('.u-table tbody tr').first().waitFor({ state: 'detached' });
      await open('#/tools?show=removed&q=Suno');
      await rowMenu('Suno');
      ok(T + 'a built-in tool cannot be deleted', await p.locator('.u-pop-menu [data-id=delete]').count() === 0);
      await p.locator('.u-pop-menu [role=menuitem][data-id=restore]').click();
      await p.getByText('Restored.').waitFor();
      ok(T + 'Restore puts it back', (await (await c.request.get(url + '/admin/api/catalog', { headers })).json()).tools.some(t => t.id === 'suno'));

      // Delete, on a tool an admin added
      const name = `Scratch ${theme} ${width}`;
      assert.equal((await c.request.post(url + '/admin/api/tools', { headers, data: { name, url: 'https://scratch.example' } })).status() < 300, true);
      const added = (await (await c.request.get(url + '/admin/api/catalog', { headers })).json()).tools.find(t => t.name === name);
      assert.equal((await c.request.post(url + `/admin/api/tools/${added.id}/archive`, { headers })).status(), 200);
      await open('#/tools?show=removed&q=' + encodeURIComponent(name));
      await rowMenu(name);
      await p.locator('.u-pop-menu [role=menuitem][data-id=delete]').click();
      await p.getByRole('dialog').getByRole('button', { name: 'Delete tool', exact: true }).click();
      await p.getByText('Deleted.').waitFor();
      ok(T + 'Delete erases it', !(await (await c.request.get(url + '/admin/api/catalog', { headers })).json()).removed.some(t => t.id === added.id));

      // the record: state, Next step, six tabs at most, people and devices on Access, a way back with the filter kept
      await open('#/tools?show=all&open=canva');
      const sheet = p.locator('.sheet.in'); await sheet.waitFor(); await p.waitForLoadState('networkidle');
      ok(T + 'the record says what to do next', (await sheet.locator('.sheet-next').textContent()).startsWith('Next step'));
      ok(T + 'at most six tabs', await sheet.locator('[role=tab]').count() <= 6);
      await axe('record'); await shot(p, 'tool-record');
      await sheet.getByRole('button', { name: 'More about Canva', exact: true }).click();
      await p.locator('.u-pop-menu [data-id=requests]').waitFor();
      ok(T + 'the record links on to requests', await p.locator('.u-pop-menu [data-id=requests]').getAttribute('href') === '#/requests?q=Canva');
      await p.keyboard.press('Escape');
      await p.locator('.u-pop-menu').waitFor({ state: 'detached' });
      ok(T + 'Esc closes the menu and leaves the record open', await sheet.isVisible());
      await sheet.getByRole('tab', { name: /^Usage/ }).click();
      await sheet.getByText('Use per day · 30 days').waitFor();
      ok(T + 'Usage no longer lists people', await sheet.getByText('Who uses it · 30 days').count() === 0);
      await sheet.getByRole('link', { name: /Manage access/ }).click();
      await sheet.getByText('Who uses it · 30 days').waitFor();
      await axe('record access'); await shot(p, 'tool-access');
      await p.locator('.sheet.in .sheet-trail a').click();
      await p.locator('.sheet').waitFor({ state: 'detached' });
      await p.locator('.u-chip[data-filter=show]').waitFor();
      ok(T + 'the trail goes back with the filter kept', (await hash()) === '#/tools?show=all');
      assert.deepEqual(errors, [], T + 'no page errors'); checks++;
      await c.close();
    }
    console.log(`tools.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
