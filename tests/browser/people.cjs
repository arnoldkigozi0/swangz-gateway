/* People on the control kit (BRIEF 10.10): filter bar in the address, a More menu on every row, the split Add button,
   and side sheets for preview, add and issue key. UI_OUTPUT also writes the 1440x852 and 390x844 evidence. Local fixture only. */
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
      assert.equal((await c.request.post(url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      const axe = async (name) => { const r = await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); assert.deepEqual(r.violations.map(v => v.id + ' ' + v.nodes.map(n => n.target).join(',')), [], T + name + ' accessibility'); checks++; };
      const noOverflow = async (name) => ok(T + name + ' has no sideways page scroll', await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      const sheet = p.locator('.u-sheet');

      await p.goto(url + '/admin#/people');
      await p.locator('.u-filter').waitFor();
      await p.waitForLoadState('networkidle');
      ok(T + 'the old status tabs are gone', await p.locator('main .fb-select, main .seg').count() === 0);
      ok(T + 'one primary, as a split button', await p.locator('.u-split.primary').count() === 1 && await p.locator('main .btn.primary').count() === 0);
      const rows = p.locator('main tbody tr');
      const total = await rows.count();
      ok(T + 'fixture has people', total > 0);
      ok(T + 'every row ends in one More button', await p.locator('main tbody tr .u-more').count() === total);
      await noOverflow('list'); await axe('list'); await shot(p, 'people');

      // filter: the choice is in the address, shows as a chip, and clearing removes both
      await p.locator('.u-filter .u-select[data-filter=status]').click();
      await p.locator('.u-pop-select [role=option]', { hasText: 'Active' }).first().click();
      await p.waitForFunction(() => location.hash.includes('status=active'));
      ok(T + 'an active filter shows as a chip', await p.locator('.u-chip').count() === 1);
      await shot(p, 'people-filtered');
      await p.locator('.u-chip-clear').click();
      await p.waitForFunction(() => !location.hash.includes('status='));
      ok(T + 'clear all restores the list', await rows.count() === total);
      await p.locator('.u-filter input[type=search]').fill('zzz-nobody');
      await p.waitForFunction(() => location.hash.includes('q=zzz-nobody'));
      await p.locator('main .u-state').waitFor();
      ok(T + 'a search with no match says so', /Nobody matches/.test(await p.locator('main').innerText()));
      await p.locator('.u-filter input[type=search]').fill('');
      await p.waitForFunction(() => !location.hash.includes('q='));

      // row menu: opening it stays on the list; Preview is a sheet with a linkable address
      const more = p.locator('main tbody tr .u-more').first();
      await more.click();
      ok(T + 'the menu did not follow the row link', /#\/people(\?|$)/.test(await p.evaluate(() => location.hash)));
      const items = await p.locator('.u-menu [role=menuitem]').allInnerTexts();
      ok(T + 'row menu offers preview and suspend last', /Preview/.test(items[0]) && /Suspend access/.test(items[items.length - 1]));
      await shot(p, 'people-row-menu');
      await p.locator('.u-menu [data-id=preview]').click();
      await sheet.waitFor();
      await p.waitForFunction(() => /[?&]open=\d+/.test(location.hash));
      const opened = await p.evaluate(() => location.hash.match(/open=(\d+)/)[1]);
      await p.waitForTimeout(350); await noOverflow('preview'); await axe('preview'); await shot(p, 'person-sheet');
      await p.keyboard.press('Escape');
      await sheet.waitFor({ state: 'detached' });
      ok(T + 'closing the preview clears the address', !(await p.evaluate(() => location.hash)).includes('open='));
      await p.goto(url + `/admin#/people?open=${opened}`); await p.reload();
      await sheet.waitFor();
      ok(T + 'the preview reopens from its link', await sheet.locator('.facts .fact').count() === 8);
      await sheet.getByRole('button', { name: 'Open record' }).click();
      await p.waitForFunction((id) => location.hash === '#/people/' + id, opened);
      await sheet.waitFor({ state: 'detached' });

      // record: one primary and a More menu, Suspend last in the danger colour
      await p.locator('main [role=tablist]').first().waitFor();
      await p.waitForLoadState('networkidle');
      ok(T + 'record has one primary', await p.locator('main .btn.primary').count() === 1 && await p.getByRole('button', { name: 'Issue a key' }).count() === 1);
      ok(T + 'suspend moved out of the header', await p.locator('main .btn.danger', { hasText: 'Suspend access' }).count() === 0);
      await noOverflow('record'); await axe('record'); await shot(p, 'person-record');
      await p.getByRole('button', { name: /^More actions for/ }).first().click();
      const head = await p.locator('.u-menu [role=menuitem]').allInnerTexts();
      ok(T + 'record menu ends with suspend', /Suspend access/.test(head[head.length - 1]));
      await shot(p, 'person-record-menu');
      await p.keyboard.press('Escape');
      await p.getByRole('button', { name: 'Issue a key' }).click();
      await sheet.waitFor();
      ok(T + 'issue key is a sheet with its field focused', await p.evaluate(() => document.activeElement.tagName === 'INPUT'));
      await p.waitForTimeout(350); await axe('issue key'); await shot(p, 'person-issue-key');
      await sheet.getByRole('button', { name: 'Cancel' }).click();
      await sheet.waitFor({ state: 'detached' });

      // add: five fields, name checked under the field, edits asked about, then the record
      await p.goto(url + '/admin#/people'); await p.locator('.u-split').waitFor();
      await p.locator('.u-split-main').click();
      await sheet.waitFor();
      ok(T + 'add has at most six fields', await sheet.locator('input, select, textarea').count() <= 6);
      await sheet.getByRole('button', { name: 'Add person' }).click();
      ok(T + 'a missing name is said and focused', /Enter their name/.test(await sheet.innerText()) && await p.evaluate(() => document.activeElement.type === 'text'));
      await p.waitForTimeout(350); await axe('add'); await shot(p, 'people-add');
      await sheet.locator('input[type=text]').first().fill('Kit Test ' + theme + width);
      await p.keyboard.press('Escape');
      ok(T + 'unsaved edits are asked about', /Discard your unsaved changes/.test(await sheet.innerText()));
      await sheet.getByRole('button', { name: 'Keep editing' }).click();
      await sheet.getByRole('button', { name: 'Add person' }).click();
      await p.waitForFunction(() => /#\/people\/\d+/.test(location.hash));
      await sheet.waitFor({ state: 'detached' });
      await p.locator('main h1', { hasText: 'Kit Test' }).waitFor();

      // split variant: add and issue a key lands on the record with the key sheet open
      await p.goto(url + '/admin#/people'); await p.locator('.u-split').waitFor();
      await p.locator('.u-split-more').click();
      await p.locator('.u-menu [data-id=key]').click();
      await sheet.waitFor();
      await sheet.locator('input[type=text]').first().fill('Kit Variant ' + theme + width);
      await sheet.getByRole('button', { name: 'Add and issue key' }).click();
      await p.locator('.u-sheet h2', { hasText: 'New key for Kit Variant' }).waitFor();
      ok(T + 'the variant goes on to its key', /#\/people\/\d+/.test(await p.evaluate(() => location.hash)));

      assert.deepEqual(errors, [], T + 'no page errors'); checks++;
      await c.close();
    }
    console.log(`People kit checks passed: ${checks}`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
