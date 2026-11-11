/* A person's "Last seen" counts only what they did themselves: an AI request, a tool opened, a site visited. An admin
   giving them a tool (an access change) is not activity, so a person who never signed in must not read "visited a site".
   Local fixture only. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
const root = process.env.GATEWAY_UI_ROOT || path.resolve(__dirname, '../..');
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
    const headers = { 'x-gateway-admin': '1' };
    for (const [width, height] of [[1440, 852], [390, 844]]) {
      const T = `${width}: `;
      const c = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
      assert.equal((await c.request.post(url + '/admin/api/login', { headers, data: { username: 'owner@swangzavenue.com', password: 'owner-password' } })).status(), 200);
      const p = await c.newPage(); const errors = []; p.on('pageerror', e => errors.push(e.message));
      const lastSeen = async (id) => {
        await p.goto(url + '/admin#/people/' + id); await p.reload();
        await p.locator('.statline .stat').first().waitFor(); await p.waitForLoadState('networkidle');
        return p.locator('.statline .stat', { hasText: 'Last seen' }).first().innerText();
      };
      // someone added and given a tool, who never did anything
      const made = await c.request.post(url + '/admin/api/people', { headers, data: { name: 'Never Signed In', email: `never${width}@swangzavenue.com`, department: 'Creative' } });
      assert.equal(made.status(), 200);
      const id = (await made.json()).id;
      assert.equal((await c.request.post(url + `/admin/api/people/${id}/tools/canva`, { headers })).status(), 200);
      const none = await lastSeen(id);
      ok(T + 'a person with no activity says so', /Never/.test(none) && /No activity recorded/.test(none));
      ok(T + 'an access change is not a site visit', !/visited/i.test(none));
      // the fixture person has made AI requests: that is the label
      const used = await lastSeen(info.person);
      ok(T + 'a person who used AI is labelled by what they did', /AI request/.test(used) && !/visited/i.test(used) && !/Never/.test(used));
      assert.deepEqual(errors, [], T + 'page errors'); checks++;
      await c.close();
    }
    console.log(`lastseen.cjs: ${checks} checks passed`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (demo) demo.kill();
  }
})().catch(e => { console.error(e); process.exit(1); });
