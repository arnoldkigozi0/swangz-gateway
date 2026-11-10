/* D-016 bypass checks for deploy/chrome-policy (docs/CHROME-POLICY-BYPASS-TESTS.md), step 1: groups A, B and D on
   Google Chrome for Linux. CI only: the workflow installs a machine-wide policy file, so this refuses to run anywhere else.

   node chrome-policy.cjs render OUT    writes the pack as the driven browser gets it (see render())
   node chrome-policy.cjs control       no policy installed: every case must reach the fixture, proving it can fail
   node chrome-policy.cjs enforced      pack installed: ALLOW reaches the fixture, ENFORCE is refused by policy

   Ground truth is the fixture's own request log, not the browser's error page. Nothing leaves the machine: Chrome
   resolves every name to 127.0.0.1, where one fixture answers on 443 and 80. Only hosts, paths and error names are
   written to the results; no headers, cookies or page content. */
const assert = require('assert');
const fs = require('fs');
const http = require('http');
const https = require('https');
const os = require('os');
const path = require('path');
const url = require('url');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '../..');
const PACK = path.join(root, 'deploy/chrome-policy/swangz-company-chrome.json');
const POLICY_DIR = '/etc/opt/chrome/policies/managed';
const OUT = process.env.CHROME_POLICY_OUT || '/tmp/swangz-chrome-policy';
const spec = JSON.parse(fs.readFileSync(path.join(__dirname, 'chrome-policy-cases.json'), 'utf8'));
/* Left out of the driven copy and owed their own process-level cases (P-1, P-2): the first is expected to stop the
   test driver from attaching at all, the second hides DevTools. The three extension entries need a signed extension
   and an update address (tier 2). */
const DROPPED = ['RemoteDebuggingAllowed', 'DeveloperToolsAvailability', 'ExtensionInstallBlocklist', 'ExtensionInstallAllowlist', 'ExtensionInstallForcelist'];
const BLOCKED = 'ERR_BLOCKED_BY_ADMINISTRATOR';

function render() {
  const pack = JSON.parse(fs.readFileSync(PACK, 'utf8'));
  for (const name of DROPPED) delete pack[name];
  const text = JSON.stringify(pack, null, 2).split('SWANGZ_HUB_HOST').join(spec.hub_host);
  assert.ok(!/SWANGZ_/.test(text), 'a placeholder is left in the rendered pack');
  assert.ok(JSON.parse(text).URLBlocklist.includes('*'), 'the rendered pack is not default-deny');
  return text + '\n';
}
function installed() {
  return fs.existsSync(POLICY_DIR) ? fs.readdirSync(POLICY_DIR).filter(n => n.endsWith('.json')) : [];
}

/* One fixture for every host. It logs host + path for each request and answers a small page; the three sign-in
   routes play the Hub -> Google -> Hub round trip of case A-2. */
const hits = [];
function handler(scheme) {
  return (req, res) => {
    const host = String(req.headers.host || '').toLowerCase();
    hits.push({ scheme, host, url: req.url });
    const at = new URL(req.url, 'https://' + (host || 'unknown.test'));
    const mark = at.searchParams.get('swz') || '';
    if (at.pathname === '/favicon.ico') { res.writeHead(204); return res.end(); }
    if (host === spec.hub_host && at.pathname === '/auth/google/start') {
      res.writeHead(302, { Location: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=fixture&swz=' + mark }); return res.end();
    }
    if (host === 'accounts.google.com' && at.pathname === '/o/oauth2/v2/auth') {
      res.writeHead(302, { Location: 'https://' + spec.hub_host + '/auth/google/callback?code=x&swz=' + mark }); return res.end();
    }
    const headers = { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' };
    if (host === spec.hub_host && at.pathname === '/auth/google/callback') headers['Set-Cookie'] = 'swz_fixture_session=1; Path=/; Secure; HttpOnly';
    res.writeHead(200, headers);
    res.end('<!doctype html><title>fixture</title><p id="host"></p><script>document.getElementById("host").textContent = location.host</script>');
  };
}
function listen(server, port) {
  return new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
}
async function fixture(dir) {
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=swangz-fixture',
    '-keyout', path.join(dir, 'key.pem'), '-out', path.join(dir, 'cert.pem')], { stdio: 'ignore' });
  const tls = https.createServer({ key: fs.readFileSync(path.join(dir, 'key.pem')), cert: fs.readFileSync(path.join(dir, 'cert.pem')) }, handler('https'));
  const plain = http.createServer(handler('http'));
  await listen(tls, 443); await listen(plain, 80);
  return () => { tls.close(); plain.close(); };
}

/* Each address gets its own mark in the query, so a request Chrome makes by itself to the same host is never
   counted as the case reaching the fixture. Path rules in the pack match on the path, which the mark leaves alone. */
function marked(address, mark) {
  return address + (address.includes('?') ? '&' : '?') + 'swz=' + mark;
}
function expand(c) {
  const list = c.urls.slice();
  if (c.unicode_host) {
    const ascii = url.domainToASCII(c.unicode_host);
    assert.ok(ascii.startsWith('xn--'), c.id + ': the lookalike did not become punycode');
    list.push('https://' + ascii + '/');
  }
  return list;
}
async function visit(context, c, address, n) {
  const mark = c.id.replace(/[^A-Za-z0-9]/g, '') + 'n' + n;
  const page = await context.newPage();
  const failed = [];
  page.on('requestfailed', r => { if (r.isNavigationRequest()) failed.push((r.failure() || {}).errorText || ''); });
  let error = '';
  try { await page.goto(marked(address, mark), { waitUntil: 'domcontentloaded', timeout: 20000 }); }
  catch (e) { error = (String(e.message).match(/net::(ERR_[A-Z_]+)/) || [])[1] || String(e.message).split('\n')[0].slice(0, 120); }
  const seen = hits.filter(h => h.url.includes('swz=' + mark));
  const out = { id: c.id, expect: c.expect, address, reached: seen.length, hosts: [...new Set(seen.map(h => h.host))],
    error: error || (failed.find(Boolean) || '').replace('net::', ''), final: '' };
  try { out.final = new URL(page.url()).origin + new URL(page.url()).pathname; } catch (e) { out.final = page.url().slice(0, 80); }
  if (c.kind === 'signin') {
    const cookies = await context.cookies('https://' + spec.hub_host + '/');
    out.signin = { back_on_hub: out.final === 'https://' + spec.hub_host + '/auth/google/callback',
      via_google: seen.some(h => h.host === 'accounts.google.com'), cookie: cookies.some(k => k.name === 'swz_fixture_session') };
    await context.clearCookies();
  }
  await page.close();
  return out;
}
function verdict(mode, r) {
  const signedIn = !r.signin || (r.signin.back_on_hub && r.signin.via_google && r.signin.cookie);
  if (mode === 'control') return r.reached > 0 && signedIn ? 'reached' : 'FAIL: did not reach the fixture without policy, so this case proves nothing';
  if (r.expect === 'ALLOW') return r.reached > 0 && signedIn && !r.error ? 'allowed' : 'FAIL: an approved address was refused';
  const refused = r.reached === 0 && r.error === BLOCKED;
  if (r.expect === 'ENFORCE') return refused ? 'refused' : r.reached ? 'FAIL: reached the fixture' : 'FAIL: not refused by policy (' + (r.error || 'no error') + ')';
  return refused ? 'recorded: refused' : r.reached ? 'recorded: reached' : 'recorded: ' + (r.error || 'no request, no error');
}
function report(mode, version, rows) {
  const lines = ['### Chrome policy pack, ' + mode + ' run', '', version + ' on ' + os.platform() + ' ' + os.release(), '',
    mode === 'enforced' ? 'Driven without: ' + DROPPED.join(', ') + '.' : 'No policy file installed.', '',
    '| Case | Expected | Address | Fixture requests | Browser error | Result |', '|---|---|---|---|---|---|',
    ...rows.map(r => `| ${r.id} | ${r.expect} | \`${r.address}\` | ${r.reached} | ${r.error || ''} | ${r.verdict} |`), '',
    'Not run: ' + spec.not_run.map(n => n.id + ' (' + n.reason + ')').join('; ') + '.', ''];
  return lines.join('\n');
}

(async () => {
  const mode = process.argv[2];
  if (mode === 'render') { fs.writeFileSync(process.argv[3], render()); return; }
  assert.ok(['control', 'enforced'].includes(mode), 'usage: chrome-policy.cjs render OUT | control | enforced');
  if (process.env.GITHUB_ACTIONS !== 'true') { console.log('Not run: needs a machine-wide Chrome policy file and ports 80 and 443, CI only'); return; }
  if (mode === 'control') assert.deepEqual(installed(), [], 'a policy file is installed during the control run');
  else {
    assert.deepEqual(installed(), ['swangz-test.json'], 'expected exactly the rendered pack in ' + POLICY_DIR);
    assert.equal(fs.readFileSync(path.join(POLICY_DIR, 'swangz-test.json'), 'utf8'), render(), 'the installed file is not the rendered pack');
  }
  fs.mkdirSync(OUT, { recursive: true });
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'swz-policy-'));
  const stop = await fixture(work);
  const { chromium } = require('playwright');
  const context = await chromium.launchPersistentContext(path.join(work, 'profile'), { channel: 'chrome', headless: false, ignoreHTTPSErrors: true,
    args: ['--host-resolver-rules=MAP * 127.0.0.1', '--ignore-certificate-errors', '--no-first-run', '--no-default-browser-check'] });
  const version = context.browser() ? 'Chrome ' + context.browser().version() : execFileSync('google-chrome', ['--version']).toString().trim();
  const rows = [];
  try {
    for (const c of spec.cases) {
      let n = 0;
      for (const address of expand(c)) { const r = await visit(context, c, address, ++n); r.verdict = verdict(mode, r); rows.push(r); }
    }
  } finally { await context.close(); stop(); }
  const text = report(mode, version, rows);
  fs.writeFileSync(path.join(OUT, mode + '.json'), JSON.stringify({ mode, version, os: os.platform() + ' ' + os.release(), dropped: mode === 'enforced' ? DROPPED : [], rows, not_run: spec.not_run }, null, 2));
  fs.writeFileSync(path.join(OUT, mode + '.md'), text);
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, text + '\n');
  console.log(text);
  const failures = rows.filter(r => r.verdict.startsWith('FAIL'));
  /* A pack Chrome never read looks like every refusal failing at once. Say that, rather than list forty symptoms. */
  const enforce = rows.filter(r => r.expect === 'ENFORCE');
  if (mode === 'enforced' && enforce.length && enforce.every(r => r.reached > 0)) {
    console.error('\nThe pack was not loaded: every address it should refuse reached the fixture. Check the policy location for this Chrome.');
    process.exit(2);
  }
  if (failures.length) { console.error('\n' + failures.length + ' failing: ' + failures.map(r => r.id + ' ' + r.address).join(', ')); process.exit(1); }
  console.log(mode + ': ' + rows.length + ' addresses checked, none failing');
})().catch(e => { console.error(e); process.exit(1); });
