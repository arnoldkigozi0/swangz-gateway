/* Real unpacked MV3 extension in Actions Chromium. Synthetic pages, isolated gateway, no vendor traffic. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const output = process.env.EXTENSION_OUTPUT || '/tmp/swangz-hub-extension-chrome';
const governedHost = 'governed-fixture.test';
const sharedHost = 'shared-fixture.test';
const ordinaryHost = 'ordinary-fixture.test';
const origins = Object.fromEntries([governedHost, sharedHost, ordinaryHost].map(host => [host, 'https://' + host]));
const results = { checks: [], gateResponses: [], ok: false };
let fixture, context, profile;
fs.mkdirSync(output, { recursive: true });

function pass(message) { results.checks.push(message); console.log('PASS ' + message); }
async function until(predicate, message, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await predicate()) return; await new Promise(r => setTimeout(r, 50)); }
  throw new Error('Timed out: ' + message);
}
async function startFixture() {
  fixture = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'demo.py')], {
    cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, GATEWAY_ACCESS_LOG: '0', GATEWAY_FETCH_ICONS: '0' },
  });
  return new Promise((resolve, reject) => {
    let stdout = '', stderr = '', ready = false;
    const timer = setTimeout(() => reject(new Error('Local gateway startup timeout: ' + stderr)), 30000);
    fixture.stderr.on('data', data => { stderr += data; });
    fixture.stdout.on('data', data => {
      stdout += data;
      if (!ready && stdout.includes('\n')) {
        ready = true; clearTimeout(timer);
        try { resolve(JSON.parse(stdout.split('\n')[0])); } catch (error) { reject(error); }
      }
    });
    fixture.on('exit', code => { clearTimeout(timer); if (!ready) reject(new Error('Local gateway exited: ' + code + ' ' + stderr)); });
  });
}
async function stopFixture() {
  if (!fixture) return;
  const process = fixture; fixture = null;
  if (process.exitCode !== null) return;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { process.kill('SIGKILL'); reject(new Error('Gateway would not stop')); }, 15000);
    process.once('exit', () => { clearTimeout(timer); resolve(); });
    process.kill('SIGTERM');
  });
}
async function navigate(page, url) {
  try { await page.goto(url, { waitUntil: 'domcontentloaded' }); }
  catch (error) { if (!/ERR_ABORTED|interrupted by another navigation/.test(error.message)) throw error; }
}
async function blocked(page, extensionId, name) {
  await page.waitForURL(url => url.protocol === 'chrome-extension:' && url.hostname === extensionId && url.pathname === '/blocked.html');
  await page.getByRole('heading', { name: 'Sign in to Swangz AI Hub', exact: true }).waitFor();
  const link = page.getByRole('link', { name: 'Sign in to Swangz AI Hub', exact: true });
  assert.equal(await link.getAttribute('href'), `chrome-extension://${extensionId}/popup.html`);
  await page.screenshot({ path: path.join(output, name + '.png') });
}

(async () => {
  const rig = await startFixture();
  const base = rig.url;
  async function api(method, pathname, body, cookie) {
    const res = await fetch(base + pathname, { method, redirect: 'manual', headers: {
      'content-type': 'application/json', 'x-swangz-app': '1', 'x-gateway-admin': '1', ...(cookie ? { cookie } : {}),
    }, body: body === undefined ? undefined : JSON.stringify(body) });
    return res;
  }
  const adminLogin = await api('POST', '/admin/api/login', { username: 'owner@swangzavenue.com', password: 'owner-password' });
  assert.equal(adminLogin.status, 200);
  const owner = adminLogin.headers.get('set-cookie').split(';')[0];
  for (const [tool, host, signin] of [['chatgpt', governedHost, 'own'], ['midjourney', sharedHost, 'shared']]) {
    const edited = await api('PATCH', '/admin/api/tools/' + tool, { hosts: [host], signin }, owner);
    assert.equal(edited.status, 200, await edited.text());
  }
  const staffLogin = await api('POST', '/api/login', { email: 'grace@swangzavenue.com', password: 'demo-password' });
  assert.equal(staffLogin.status, 200);
  const staff = staffLogin.headers.get('set-cookie').split(';')[0];
  const turn = await api('GET', '/go/midjourney', undefined, staff);
  assert.equal(turn.status, 302, 'real local gateway grants shared-account turn');

  profile = fs.mkdtempSync(path.join(os.tmpdir(), 'swangz-extension-chrome-'));
  const extension = path.join(root, 'extension');
  context = await chromium.launchPersistentContext(profile, { channel: 'chromium', headless: false,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`] });
  context.setDefaultTimeout(15000);
  // Fulfil synthetic site pages without DNS/vendor access. The worker's own gateway
  // requests use real loopback HTTP and are neither mocked nor fulfilled here.
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname === '127.0.0.1' || url.protocol === 'chrome-extension:') return route.continue();
    if (Object.hasOwn(origins, url.hostname)) return route.fulfill({ status: 200, contentType: 'text/html',
      body: '<!doctype html><html><title>Synthetic site</title><h1>Synthetic site ' + url.hostname + '</h1></html>' });
    return route.abort();
  });
  context.on('response', async res => {
    if (!res.url().startsWith(base + '/api/gate/')) return;
    const record = { endpoint: new URL(res.url()).pathname, status: res.status() };
    if (record.endpoint.endsWith('/open')) {
      try { const data = await res.json(); record.known = data.known; record.allowed = data.allowed; } catch (_) {}
    }
    results.gateResponses.push(record);
  });
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const extensionId = new URL(worker.url()).hostname;
  assert.ok(extensionId);
  results.chromium = context.browser().version();
  pass('unpacked MV3 extension loaded in real Chromium ' + results.chromium);
  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  async function signIn() {
    await popup.getByLabel('Swangz AI Hub address').fill(base);
    await popup.getByLabel('Work email').fill('grace@swangzavenue.com');
    await popup.getByLabel('Password', { exact: true }).fill('demo-password');
    await popup.getByRole('button', { name: 'Connect', exact: true }).click();
    await popup.getByText('Connected to Swangz AI Hub', { exact: true }).waitFor();
  }
  await signIn();
  const state = await worker.evaluate(async () => {
    const data = await chrome.storage.local.get(['hosts', 'holding', 'token']);
    return { hosts: data.hosts, holding: data.holding, signedIn: !!data.token };
  });
  assert.ok(state.signedIn && state.hosts[governedHost] === 'chatgpt' && state.holding.midjourney);
  pass('real extension sign-in fetched governed hosts and the held shared-account turn');

  const ordinary = await context.newPage();
  await ordinary.goto(origins[ordinaryHost]);
  await ordinary.locator('h1').waitFor();
  await ordinary.evaluate(() => localStorage.setItem('unrelated-fixture', 'keep'));
  await context.addCookies([{ name: 'unrelated-fixture', value: 'keep', url: origins[ordinaryHost], secure: true }]);
  const allowed = await context.newPage();
  const beforeAllow = results.gateResponses.length;
  await navigate(allowed, origins[governedHost]);
  await until(() => results.gateResponses.slice(beforeAllow).some(r => r.endpoint.endsWith('/open') && r.allowed === true), 'governed allow decision');
  assert.equal(new URL(allowed.url()).hostname, governedHost);
  pass('governed site loads after an authenticated allow decision');
  const shared = await context.newPage();
  const beforeShared = results.gateResponses.length;
  await navigate(shared, origins[sharedHost]);
  await until(() => results.gateResponses.slice(beforeShared).some(r => r.endpoint.endsWith('/open') && r.allowed === true), 'shared-site allow decision');
  assert.equal(new URL(shared.url()).hostname, sharedHost);
  await shared.evaluate(() => localStorage.setItem('held-fixture', 'synthetic-session'));
  await context.addCookies([{ name: 'held-fixture', value: 'synthetic-session', url: origins[sharedHost], secure: true }]);
  assert.ok((await context.cookies(origins[sharedHost])).some(c => c.name === 'held-fixture'));
  assert.equal(await shared.evaluate(() => localStorage.getItem('held-fixture')), 'synthetic-session');
  pass('held shared site has real Chromium cookie and localStorage fixtures before suspension');

  const suspended = await api('POST', `/admin/api/people/${rig.person}/suspend`, {}, owner);
  assert.equal(suspended.status, 200);
  const beforeSuspend = results.gateResponses.length;
  await navigate(allowed, origins[governedHost] + '/after-suspend');
  await blocked(allowed, extensionId, 'suspended-governed');
  await until(() => results.gateResponses.slice(beforeSuspend).some(r => r.status === 401), 'real gate 401 after admin suspension');
  pass('admin suspend produces a real gate 401 and the governed tab shows Sign in to Swangz AI Hub');
  await until(async () => !(await context.cookies(origins[sharedHost])).some(c => c.name === 'held-fixture'), 'shared-site cookie removal');
  await until(async () => await shared.evaluate(() => localStorage.getItem('held-fixture')) === null, 'shared-site localStorage removal');
  const signedOut = await worker.evaluate(async () => {
    const data = await chrome.storage.local.get(['token', 'holding', 'hosts']);
    return { signedIn: !!data.token, holding: data.holding || {}, hosts: data.hosts };
  });
  assert.equal(signedOut.signedIn, false);
  assert.deepEqual(signedOut.holding, {});
  assert.equal(signedOut.hosts[governedHost], 'chatgpt');
  assert.equal(await ordinary.evaluate(() => localStorage.getItem('unrelated-fixture')), 'keep');
  assert.ok((await context.cookies(origins[ordinaryHost])).some(c => c.name === 'unrelated-fixture'));
  pass('real browsingData.remove cleared the held-site cookie and localStorage on 401; unrelated site data survived');
  await ordinary.goto(origins[ordinaryHost] + '/after-suspend');
  await ordinary.locator('h1').waitFor();
  assert.equal(new URL(ordinary.url()).hostname, ordinaryHost);
  pass('ungoverned site loads while the extension is signed out');

  assert.equal((await api('POST', `/admin/api/people/${rig.person}/resume`, {}, owner)).status, 200);
  await popup.reload();
  await signIn();
  await stopFixture();
  const offline = await context.newPage();
  await navigate(offline, origins[governedHost] + '/gateway-unreachable');
  await blocked(offline, extensionId, 'offline-governed');
  pass('governed site shows Sign in to Swangz AI Hub with the actual local gateway stopped');
  await ordinary.goto(origins[ordinaryHost] + '/gateway-unreachable');
  await ordinary.locator('h1').waitFor();
  assert.equal(new URL(ordinary.url()).hostname, ordinaryHost);
  pass('ungoverned site still loads while the gateway is unreachable');
  results.ok = true;
})().catch(error => { results.error = error.message; console.error(error); process.exitCode = 1; }).finally(async () => {
  try { if (context) await context.close(); } finally {
    try { await stopFixture(); } finally {
      if (profile) fs.rmSync(profile, { recursive: true, force: true });
      fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2) + '\n');
    }
  }
});
