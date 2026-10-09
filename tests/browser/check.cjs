/* Optional browser regression checks. Dependencies belong in a temporary tooling directory,
   never in the gateway runtime. See docs/UI.md for the invocation. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const root = path.resolve(__dirname, '../..');
const output = process.env.UI_OUTPUT || '/tmp/swangz-ui-check';
const sizes = [[1440, 900], [1280, 800], [1024, 768], [768, 1024], [430, 932], [390, 844]];
const matrixSizes = sizes.filter(([width]) => !process.env.UI_WIDTH || width === Number(process.env.UI_WIDTH));
const themes = process.env.UI_THEME ? [process.env.UI_THEME] : ['dark', 'light'];
assert.ok(matrixSizes.length && themes.every(t => ['dark', 'light'].includes(t)), 'Valid viewport/theme selection');
fs.mkdirSync(output, { recursive: true });
let browser, demo;
const results = { interactions: [], screens: [], errors: [], failedApi: [] };
const check = (label, value) => { assert.ok(value, label); results.interactions.push(label); };
async function fixture() {
  demo = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  return new Promise((resolve, reject) => {
    let stdout = '', stderr = '';
    const timer = setTimeout(() => reject(new Error('Demo did not start: ' + stderr)), 30000);
    demo.stderr.on('data', d => { stderr += d; });
    demo.stdout.on('data', d => { stdout += d; if (stdout.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(stdout.split('\n')[0])); } });
    demo.on('exit', code => { clearTimeout(timer); if (code) reject(new Error('Demo failed: ' + stderr)); });
  });
}
async function login(c, url, role = 'owner') {
  const r = await c.request.post(url + '/admin/api/login', { headers: { 'x-gateway-admin': '1' }, data: { username: role, password: role + '-password' } });
  assert.equal(r.status(), 200);
}
async function staffLogin(c, url) {
  const r = await c.request.post(url + '/api/login', { headers: { 'x-swangz-app': '1' }, data: { email: 'grace@swangzavenue.com', password: 'demo-password' } });
  assert.equal(r.status(), 200);
}
async function ready(p) { await p.locator('main h1').waitFor(); await p.waitForTimeout(100); }
async function go(p, url, route) {
  await p.goto(url + route);
  if (route.startsWith('/admin')) {
    // A hash navigation can return before its async renderer replaces the prior page.
    await p.waitForFunction(() => window.SWA?.S.route === location.hash);
  }
  await ready(p);
  await p.waitForFunction(() => !document.querySelector('main .u-skel-rows, main .u-skel-cards'));
}
async function screenshot(p, name, fullPage = true) { await p.screenshot({ path: path.join(output, name + '.png'), fullPage }); }
async function layout(p, name, axe = false) {
  const metrics = await p.evaluate(() => ({ width: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1,
    buttons: [...document.querySelectorAll('main button, main .btn')].filter(e => {
      const r = e.getBoundingClientRect();
      if (!r.width || e.closest('.ptabs,.vtabs,.u-seg,.chips-row,.u-table-wrap')) return false;
      return r.right > innerWidth + 1 || r.left < -1 || e.scrollWidth > e.clientWidth + 3;
    }).map(e => e.textContent.trim()),
    clippedValues: [...document.querySelectorAll('.kpi .value:not(.text)')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map(e => e.textContent.trim()) }));
  assert.equal(metrics.overflow, false, name + ': horizontal overflow');
  assert.deepEqual(metrics.buttons, [], name + ': clipped controls');
  assert.deepEqual(metrics.clippedValues, [], name + ': clipped summary values');
  const violations = axe ? (await new AxeBuilder({ page: p }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations : [];
  results.screens.push({ name, ...metrics, violations: violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })) });
  if (axe) assert.deepEqual(violations.map(v => v.id), [], name + ': accessibility findings');
}
(async () => {
  const { url, person, key, session } = await fixture();
  browser = await chromium.launch({ executablePath: process.env.CHROME || undefined, headless: true, args: ['--no-sandbox'] });
  const c = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await login(c, url); await staffLogin(c, url);
  const p = await c.newPage();
  p.on('pageerror', e => results.errors.push(e.message));
  p.on('response', r => { if (r.status() >= 400 && /\/(?:admin\/)?api\//.test(r.url())) results.failedApi.push({ url: r.url(), status: r.status() }); });
  if (process.env.UI_SETTINGS_ONLY === '1') {
    for (const theme of themes) for (const [width, height] of [sizes[0], sizes[3], sizes[5]]) {
      await p.setViewportSize({ width, height });
      for (const category of ['access', 'purpose', 'providers', 'browsers', 'emergency', 'users', 'account']) {
        await go(p, url, '/admin#/settings?tab=' + category);
        await p.locator('.ptabs.vertical [data-tab="' + category + '"][aria-selected="true"]').waitFor();
        await p.waitForFunction(() => !document.querySelector('main .u-skel-rows, main .u-skel-cards'));
        await p.evaluate(t => { document.documentElement.dataset.theme = t; }, theme);
        await layout(p, `owner-${theme}-${width}-settings-${category}`);
        if (width === 390) await screenshot(p, `owner-${theme}-${width}-settings-${category}`);
      }
    }
    assert.deepEqual(results.errors, [], 'Owner Settings browser exceptions');
    assert.deepEqual(results.failedApi, [], 'Owner Settings unexpected API failures');
    console.log('PASS owner Settings', results.screens.length, 'screen checks');
    return;
  }
  if (process.env.UI_AUTH_ONLY === '1') {
    const ac = await browser.newContext(); const ap = await ac.newPage();
    ap.on('pageerror', e => results.errors.push(e.message));
    for (const theme of themes) for (const [width, height] of matrixSizes) {
      await ap.setViewportSize({ width, height });
      for (const route of ['/', '/admin']) {
        await ap.goto(url + route); await ready(ap);
        await ap.evaluate(t => { document.documentElement.dataset.theme = t; localStorage.setItem('swangz-theme', t); }, theme);
        const name = `signin-${theme}-${width}-${route === '/' ? 'staff' : 'admin'}`;
        await layout(ap, name, width === 1440 || width === 390);
        if (width === 1440 || width === 390) await screenshot(ap, name);
      }
    }
    assert.deepEqual(results.errors, [], 'Sign-in browser exceptions');
    await ac.close(); console.log('PASS sign-in views', results.screens.length, 'screen checks');
    return;
  }
  if (process.env.UI_RECORDS_ONLY === '1') {
    const request = await c.request.post(url + '/api/tools/adobe-firefly/request', { headers: { 'x-swangz-app': '1' }, data: { reason: 'Local fixture: artwork for an approved campaign' } });
    assert.equal(request.status(), 200);
    const incident = await c.request.post(url + '/admin/api/incidents', { headers: { 'x-gateway-admin': '1' }, data: {
      title: 'Local fixture: investigate an unexpected request', severity: 'medium', owner: 'owner', summary: 'Test evidence only; no production incident.',
      links: [{ kind: 'person', ref: String(person) }, { kind: 'request', ref: '1' }, { kind: 'device', ref: key }] } });
    assert.equal(incident.status(), 200); const { id } = await incident.json();
    for (const theme of themes) for (const [width, height] of matrixSizes) {
      await p.setViewportSize({ width, height });
      for (const route of ['/#/requests?view=access', '/admin#/requests', '/admin#/incidents/' + id, '/admin#/sessions/' + session]) {
        await go(p, url, route);
        await p.evaluate(t => { document.documentElement.dataset.theme = t; localStorage.setItem('swangz-theme', t); }, theme);
        const name = `records-${theme}-${width}-${route.replace(/[^a-z0-9]/g, '_')}`;
        await layout(p, name, width === 1440 || width === 390);
        if (width === 1440 || width === 390) await screenshot(p, name);
      }
    }
    assert.deepEqual(results.errors, [], 'Record-view browser exceptions');
    assert.deepEqual(results.failedApi, [], 'Record-view unexpected API failures');
    console.log('PASS record views', results.screens.length, 'screen checks');
    return;
  }
  // Optional deep-view pass after the principal page matrix.
  if (process.env.UI_DETAILS_ONLY === '1') {
    await go(p, url, '/#/tools');
    const category = p.getByRole('button', { name: 'Design', exact: true });
    await category.focus(); await p.keyboard.press('Enter');
    check('Category keeps keyboard focus after selection', await category.evaluate(e => e === document.activeElement));
    const filter = p.getByRole('button', { name: 'Available to me', exact: true });
    await filter.focus(); await p.keyboard.press('Enter');
    check('Availability filter keeps keyboard focus', await filter.evaluate(e => e === document.activeElement));
    const menuTrigger = p.getByRole('button', { name: 'Your account', exact: true });
    await menuTrigger.focus(); await p.keyboard.press('ArrowDown'); await p.keyboard.press('Tab');
    check('Tab leaves and closes account menu', await menuTrigger.getAttribute('aria-expanded') === 'false' && await p.locator('.menu.open').count() === 0);
    await go(p, url, '/#/studio');
    await p.getByRole('button', { name: 'Image', exact: true }).click();
    await p.getByRole('textbox', { name: 'What should it show?', exact: true }).fill('Local test job');
    await p.route('**/api/studio/jobs/**', route => route.abort());
    await p.getByRole('button', { name: 'Make the image', exact: true }).click();
    await p.getByRole('button', { name: 'Check again', exact: true }).waitFor({ timeout: 15000 });
    check('Interrupted progress read shows recovery', await p.getByRole('alert').filter({ hasText: "request may still be running" }).isVisible());
    await p.unroute('**/api/studio/jobs/**');
    await p.getByRole('button', { name: 'Check again', exact: true }).click();
    await p.getByRole('link', { name: 'Open full size' }).waitFor({ timeout: 15000 });
    check('Progress recovery reads the existing job', await p.getByRole('link', { name: 'Open full size' }).isVisible());
    let expanded = 0;
    for (const theme of ['dark', 'light']) for (const [width, height] of [sizes[0], sizes[3], sizes[5]]) {
      await p.setViewportSize({ width, height });
      await p.goto(url + '/'); await ready(p);
      await p.evaluate(t => { document.documentElement.dataset.theme = t; localStorage.setItem('swangz-theme', t); }, theme);
      for (const route of ['/#/devices', '/#/requests', '/#/studio', '/admin#/', '/admin#/activity', `/admin#/people/${person}`, `/admin#/devices/${key}`, '/admin#/licences', '/admin#/policies']) {
        await go(p, url, route);
        const tabs = p.locator('main [role="tablist"]').first();
        const ids = await tabs.locator('[role="tab"]').evaluateAll(nodes => nodes.map(n => n.id));
        for (const id of ids) {
          await p.locator('[id="' + id + '"]').click();
          await p.waitForTimeout(200);
          const name = `view-${theme}-${width}-${route.replace(/[^a-z0-9]/g, '_')}-${expanded++}`;
          await layout(p, name); if (width === 390) await screenshot(p, name);
        }
      }
      for (const tab of ['purpose', 'providers']) {
        await go(p, url, '/admin#/settings?tab=' + tab);
        const child = p.locator('.set-sections [role="tab"]');
        const ids = await child.evaluateAll(nodes => nodes.map(n => n.id));
        for (const id of ids) { await p.locator('[id="' + id + '"]').click(); await p.waitForTimeout(200); await layout(p, `section-${theme}-${width}-${tab}-${expanded++}`); }
      }
      await go(p, url, '/admin#/tools?open=canva');
      await p.locator('.sheet.in').waitFor();
      const toolTabs = await p.locator('.sheet [role="tab"]').evaluateAll(nodes => nodes.map(n => n.id));
      for (const id of toolTabs) { await p.locator('[id="' + id + '"]').click(); await p.waitForTimeout(200); await layout(p, `tool-${theme}-${width}-${expanded++}`); }
      await screenshot(p, `tool-profile-${theme}-${width}`, false); await p.keyboard.press('Escape'); await p.waitForTimeout(350);
      await go(p, url, '/admin#/reports');
      const reports = await p.locator('.report-list a').evaluateAll(nodes => nodes.map(n => n.getAttribute('href')));
      for (const report of reports) { await go(p, url, '/admin' + report); await layout(p, `report-${theme}-${width}-${report}`); }
      for (const [route, action] of [['models', 'Register a model'], ['policies', 'Add a policy'], ['incidents', 'Open an incident']]) {
        await go(p, url, '/admin#/' + route); await p.locator('.top-actions').getByRole('button', { name: action, exact: true }).click();
        await p.getByRole('dialog').waitFor();
        await p.getByRole('dialog').evaluate(async e => { await Promise.all(e.getAnimations().map(a => a.finished)); });
        const dialog = await p.getByRole('dialog').boundingBox();
        check(`Dialog fits ${route} ${theme} ${width}`, dialog.x >= 0 && dialog.x + dialog.width <= width + 1);
        await screenshot(p, `dialog-${route}-${theme}-${width}`, false);
        await p.keyboard.press('Escape'); await p.waitForTimeout(350);
      }
    }
    // Home's composition follows actual fixture entitlements and account state.
    const adminHeaders = { 'x-gateway-admin': '1' };
    for (const theme of themes) for (const [width, height] of matrixSizes) {
      await p.setViewportSize({ width, height });
      await c.request.post(url + '/admin/api/pause', { headers: adminHeaders, data: { paused: true } });
      await go(p, url, '/');
      await p.evaluate(t => { document.documentElement.dataset.theme = t; }, theme);
      check(`Paused Home has no launch ${theme} ${width}`, await p.locator('main a[href*="/go/"]').count() === 0);
      await layout(p, `home-paused-${theme}-${width}`); await screenshot(p, `home-paused-${theme}-${width}`);
      await c.request.post(url + '/admin/api/pause', { headers: adminHeaders, data: { paused: false } });
      await c.request.delete(url + '/admin/api/people/' + person + '/tools', { headers: adminHeaders });
      await go(p, url, '/'); await layout(p, `home-no-tools-${theme}-${width}`); await screenshot(p, `home-no-tools-${theme}-${width}`);
      check(`No-tools Home has no launch ${theme} ${width}`, await p.locator('main a[href*="/go/"]').count() === 0);
      await c.request.post(url + '/admin/api/people/' + person + '/tools/canva', { headers: adminHeaders });
      await go(p, url, '/'); await layout(p, `home-one-tool-${theme}-${width}`); await screenshot(p, `home-one-tool-${theme}-${width}`);
      check(`One-tool Home has one launch ${theme} ${width}`, await p.locator('main a[href*="/go/"]').count() === 1);
      await c.request.patch(url + '/admin/api/people/' + person, { headers: adminHeaders, data: { access_until: '2001-01-01' } });
      await go(p, url, '/'); await layout(p, `home-access-ended-${theme}-${width}`); await screenshot(p, `home-access-ended-${theme}-${width}`);
      check(`Ended Home has no launch ${theme} ${width}`, await p.locator('main a[href*="/go/"]').count() === 0);
      await c.request.patch(url + '/admin/api/people/' + person, { headers: adminHeaders, data: { access_until: '' } });
      for (const tool of ['chatgpt', 'claude', 'midjourney', 'codex', 'claude-code']) await c.request.post(url + '/admin/api/people/' + person + '/tools/' + tool, { headers: adminHeaders });
    }
    assert.deepEqual(results.errors, [], 'Deep-view browser exceptions');
    assert.deepEqual(results.failedApi, [], 'Deep-view unexpected API failures');
    console.log('PASS deep views', results.interactions.length, 'interaction assertions;', results.screens.length, 'screen checks');
    return;
  }
  if (process.env.UI_ROLES_ONLY !== '1') {
    // Staff catalogue state, reset, history, secure launch links and drawer focus.
    await go(p, url, '/#/tools');
    check('Staff page has one level-one title', await p.locator('h1').count() === 1);
    await p.getByRole('searchbox', { name: 'Search AI tools' }).fill('does-not-exist');
    await p.getByRole('heading', { name: 'No tools match' }).waitFor();
    check('Catalogue search is in URL', p.url().includes('q=does-not-exist'));
    await p.getByRole('button', { name: 'Clear filters', exact: true }).click();
    check('Clear filters restores catalogue', await p.locator('.tile').count() > 0 && !p.url().includes('?'));
    await p.getByRole('button', { name: 'Design', exact: true }).click();
    await p.getByRole('combobox', { name: 'Sort', exact: true }).selectOption('az');
    await p.reload(); await ready(p);
    check('Catalogue category and sort survive refresh', await p.locator('.chip.on').innerText() === 'Design' && await p.getByRole('combobox', { name: 'Sort', exact: true }).inputValue() === 'az');
    await p.goBack(); await ready(p);
    check('Catalogue Back restores sort', await p.getByRole('combobox', { name: 'Sort', exact: true }).inputValue() === 'recommended');
    await p.goForward(); await ready(p);
    check('Catalogue Forward restores sort', await p.getByRole('combobox', { name: 'Sort', exact: true }).inputValue() === 'az');
    const launch = p.locator('a[href$="/go/canva"]');
    check('Tool launches use the secure gate', await launch.count() === 1 && await launch.getAttribute('rel') === 'noopener');
    await p.getByRole('button', { name: 'Canva — details', exact: true }).click();
    await p.getByRole('dialog', { name: 'Canva' }).waitFor();
    await p.keyboard.press('Escape'); await p.waitForTimeout(350);
    check('Tool drawer restores focus', await p.getByRole('button', { name: 'Canva — details', exact: true }).evaluate(e => e === document.activeElement));
    const account = p.getByRole('button', { name: 'Your account', exact: true });
    await account.focus(); await p.keyboard.press('ArrowDown');
    check('Account menu supports arrow opening', await p.getByRole('menuitem', { name: 'Profile', exact: true }).evaluate(e => e === document.activeElement));
    await p.keyboard.press('End');
    check('Account menu supports End', await p.getByRole('menuitem', { name: 'Sign out', exact: true }).evaluate(e => e === document.activeElement));
    await p.keyboard.press('Escape');
    check('Account menu closes and returns focus', await account.evaluate(e => e === document.activeElement));
    // Retained Studio drafts, validation, real fake-provider success and errors.
    await go(p, url, '/#/studio');
    const script = p.getByRole('textbox', { name: 'Script', exact: true });
    await script.fill('Draft that survives media switches');
    await p.getByRole('button', { name: 'Image', exact: true }).click();
    await p.getByRole('textbox', { name: 'What should it show?', exact: true }).fill('An image draft');
    await p.getByRole('button', { name: 'Voice-over', exact: true }).click();
    check('Studio retains voice draft', await script.inputValue() === 'Draft that survives media switches');
    await p.getByRole('button', { name: 'Image', exact: true }).click();
    check('Studio retains image draft', await p.getByRole('textbox', { name: 'What should it show?', exact: true }).inputValue() === 'An image draft');
    await p.getByRole('button', { name: 'Voice-over', exact: true }).click();
    await p.getByRole('tab', { name: 'Your creations' }).click();
    await p.getByRole('tab', { name: 'Create', exact: true }).click();
    check('Studio retains draft across views', await script.inputValue() === 'Draft that survives media switches');
    await script.fill('please fail');
    await p.getByRole('button', { name: 'Make the voice-over', exact: true }).click();
    await p.locator('.studio-form:not([hidden]) .form-error').filter({ hasText: /./ }).waitFor();
    check('Studio failure keeps input and restores action', await script.inputValue() === 'please fail' && await p.getByRole('button', { name: 'Make the voice-over', exact: true }).isEnabled());
    await script.fill('A local test voice-over');
    await p.getByRole('button', { name: 'Make the voice-over', exact: true }).click();
    await p.locator('.just-made audio').waitFor();
    check('Studio success renders a playable result', await script.inputValue() === '');
    await p.setViewportSize({ width: 390, height: 844 });
    check('Mobile navigation exposes Studio', await p.locator('.tabbar a[href="#/studio"]').isVisible());
    await screenshot(p, 'studio-mobile-result');
    // Settings nested links/history and unsaved changes remain intact.
    await go(p, url, '/admin#/settings?tab=providers&section=prices');
    await p.locator('.set-sections [role="tab"][aria-selected="true"]').waitFor();
    check('Settings deep link restores child section', await p.locator('.set-sections [aria-selected="true"]').innerText() === 'Model prices');
    await p.reload(); await ready(p);
    check('Settings refresh restores section', p.url().includes('section=prices'));
    await p.locator('.set-sections').getByRole('tab', { name: 'Media rates', exact: true }).click();
    await p.goBack(); await p.waitForTimeout(150);
    check('Settings Back restores section', await p.locator('.set-sections [aria-selected="true"]').innerText() === 'Model prices');
    await go(p, url, '/admin#/settings?tab=access');
    const days = p.locator('.setting-control input[type="number"]').first();
    await days.fill('91');
    await p.getByRole('tab', { name: 'Emergency', exact: true }).click();
    await p.getByRole('dialog', { name: 'Leave without saving?' }).waitFor();
    await p.getByRole('button', { name: 'Cancel', exact: true }).click();
    check('Settings unsaved guard keeps changes on Cancel', await days.inputValue() === '91');
    await p.locator('.savebar').getByRole('button', { name: /Discard/ }).click();
    // Matrix: all principal pages, desktop, tablet and phone; dark and light.
    const routes = ['/', '/#/tools', '/#/studio', '/#/devices', '/#/requests', '/#/privacy',
      ...['', 'live', 'attention', 'activity', 'health', 'people', `people/${person}`, 'tools', 'models', 'policies', 'licences', 'reports', 'security', 'incidents', 'devices', 'audit', 'settings', 'records/1', `devices/${key}`].map(r => '/admin#/' + r)];
    for (const theme of themes) for (const [width, height] of matrixSizes) {
      await p.setViewportSize({ width, height });
      for (const route of routes) {
        await go(p, url, route);
        await p.evaluate(t => { document.documentElement.dataset.theme = t; localStorage.setItem('swangz-theme', t); }, theme);
        const name = `${theme}-${width}-${route.replace(/[^a-z0-9]/g, '_')}`;
        await layout(p, name, width === 1440 || width === 390);
        if (width === 1440 || width === 390) await screenshot(p, name);
      }
      console.log('Verified', theme, width);
    }
  }
  // Role restrictions: role-specific pages and every Settings category in two themes/three sizes.
  const categories = ['access', 'purpose', 'providers', 'browsers', 'emergency', 'users', 'account'];
  if (process.env.UI_PAGES_ONLY === '1') {
    assert.deepEqual(results.errors, [], 'Browser exceptions');
    assert.deepEqual(results.failedApi.filter(r => !r.url.endsWith('/studio/voice')), [], 'Unexpected API failures');
    console.log('PASS principal pages', results.interactions.length, 'interaction assertions;', results.screens.length, 'screen checks');
    return;
  }
  for (const role of ['viewer', 'operations', 'security', 'billing']) {
    const rc = await browser.newContext(); await login(rc, url, role); const rp = await rc.newPage();
    rp.on('pageerror', e => results.errors.push(e.message));
    for (const theme of ['dark', 'light']) for (const [width, height] of [sizes[0], sizes[3], sizes[5]]) {
      await rp.setViewportSize({ width, height });
      for (const category of categories) {
        await go(rp, url, '/admin#/settings?tab=' + category);
        const selected = category === 'users' ? 'access' : category; // Console users is restricted to admin.
        await rp.locator('.ptabs.vertical [data-tab="' + selected + '"][aria-selected="true"]').waitFor();
        await rp.waitForFunction(() => !document.querySelector('main .u-skel-rows, main .u-skel-cards'));
        await rp.evaluate(t => { document.documentElement.dataset.theme = t; }, theme);
        await layout(rp, `${role}-${theme}-${width}-settings-${category}`);
        if (role === 'viewer' && category !== 'account') check('Viewer settings are read-only: ' + category + '-' + theme + '-' + width, await rp.locator('.tab-body .setting-control input:not([disabled]):not([readonly]):visible, .tab-body .setting-control textarea:not([disabled]):not([readonly]):visible').count() === 0);
      }
      for (const route of ['people', 'tools', 'models', 'policies', 'incidents']) {
        await go(rp, url, '/admin#/' + route);
        const allowed = ['people', 'tools', 'models', 'policies'].includes(route) ? role === 'operations' : role === 'security';
        const add = rp.locator('.top-actions .btn.primary');
        check(`${role} ${route} action permissions ${theme} ${width}`, (await add.count() > 0) === allowed);
      }
    }
    await rc.close(); console.log('Verified role', role);
  }
  assert.deepEqual(results.errors, [], 'Browser exceptions');
  // The deliberately failed Studio request above is the only expected API failure.
  assert.deepEqual(results.failedApi.filter(r => !r.url.endsWith('/studio/voice')), [], 'Unexpected API failures');
  console.log('PASS', results.interactions.length, 'interaction assertions;', results.screens.length, 'screen checks');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => {
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
  if (browser) await browser.close();
  if (demo) demo.kill('SIGTERM');
});
