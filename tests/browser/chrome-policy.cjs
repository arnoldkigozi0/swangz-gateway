/* D-016 bypass checks for deploy/chrome-policy (docs/CHROME-POLICY-BYPASS-TESTS.md), step 1: groups A, B and D on
   Google Chrome for Linux, with group C (redirects, script moves, pop-ups, frames, form posts, subresources). CI only: the workflow installs a machine-wide policy file, so this refuses to run anywhere else.

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
const net = require('net');
const os = require('os');
const path = require('path');
const url = require('url');
const { execFileSync, spawn } = require('child_process');

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

/* full: the process step (P cases) installs the pack with RemoteDebuggingAllowed and DeveloperToolsAvailability
   left in, since nothing drives that browser; the extension entries still wait for tier 2. */
function render(full) {
  const pack = JSON.parse(fs.readFileSync(PACK, 'utf8'));
  for (const name of DROPPED) if (!full || name.startsWith('Extension')) delete pack[name];
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
    /* Group C: an approved host that sends the browser somewhere else. `to` gets the case's mark, so a request
       that arrives there is counted against the case; `n` hops stay on approved hosts before the last one. */
    if (at.pathname === '/hop' || at.pathname === '/redirect') {
      const how = at.searchParams.get('how') || '302', left = Number(at.searchParams.get('n') || 1);
      const to = at.searchParams.get('to') || '';
      const next = left > 1
        ? 'https://' + (host === 'claude.ai' ? 'chatgpt.com' : 'claude.ai') + '/hop?how=' + how + '&n=' + (left - 1) + '&to=' + encodeURIComponent(to) + '&swz=' + mark
        : marked(to, mark);
      if (/^30[278]$/.test(how)) { res.writeHead(Number(how), { Location: next, 'Cache-Control': 'no-store' }); return res.end(); }
      const q = JSON.stringify(next).replace(/</g, '\\u003c');
      const href = next.replace(/"/g, '%22');
      /* C-3, C-4, C-6: a pop-up or new tab (the driver clicks #go, so Chrome's pop-up blocker sees a user gesture),
         a frame, and subresources the page loads by itself. */
      /* E-3, E-4: documents made on the approved page (a srcdoc frame, a data: link, a script-made blob:). Each fetches
         the marked `to` when it runs, so a request there means the document loaded and its script ran. */
      const inner = '<script>fetch(' + q + ', { mode: "no-cors" }).catch(() => {})<\/script>';
      const attr = v => v.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
      const made = {
        srcdoc: '<iframe srcdoc="' + attr(inner) + '"></iframe>',
        datalink: '<a id="go" href="data:text/html,' + attr(encodeURIComponent(inner)) + '">go</a>',
        blob: '<script>location.href = URL.createObjectURL(new Blob([' + JSON.stringify(inner).replace(/</g, '\\u003c') + '], { type: "text/html" }))</script>',
        blobframe: '<script>const f = document.createElement("iframe"); f.src = URL.createObjectURL(new Blob([' + JSON.stringify(inner).replace(/</g, '\\u003c') + '], { type: "text/html" })); document.documentElement.appendChild(f)</script>',
      };
      const later = {
        ...made,
        open: '<button id="go" onclick=\'window.open(' + q.replace(/'/g, '&#39;') + ')\'>go</button>',
        blank: '<a id="go" target="_blank" rel="noopener" href="' + href + '">go</a>',
        link: '<a id="go" href="' + href + '">go</a>',
        iframe: '<iframe src="' + href + '"></iframe>',
        script: '<script src="' + href + '"></script>',
        img: '<img src="' + href + '" alt="">',
        fetch: '<script>fetch(' + q + ', { mode: "no-cors" }).catch(() => {})</script>',
        xhr: '<script>const x = new XMLHttpRequest(); x.open("GET", ' + q + '); x.send()</script>',
        ws: '<script>try { new WebSocket(' + q + '.replace(/^http/, "ws")) } catch (e) {}</script>',
      }[how];
      const body = later ? later : how === 'meta' ? '<meta http-equiv="refresh" content="0;url=' + next.replace(/"/g, '%22') + '">'
        : how === 'form' ? '<form id="f" method="post" action="' + next.replace(/"/g, '%22') + '"><input name="a" value="b"></form><script>document.getElementById("f").submit()</script>'
        : '<script>location.' + (how === 'replace' ? 'replace(' + q + ')' : 'href = ' + q) + '</script>';
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      return res.end('<!doctype html><title>hop</title>' + body);
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
/* C-6: a WebSocket arrives as an upgrade, not a request. Log it like one and hang up. */
function logUpgrade(scheme) {
  return (req, socket) => { hits.push({ scheme, host: String(req.headers.host || '').toLowerCase(), url: req.url }); socket.destroy(); };
}
async function fixture(dir) {
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=swangz-fixture',
    '-keyout', path.join(dir, 'key.pem'), '-out', path.join(dir, 'cert.pem')], { stdio: 'ignore' });
  const tls = https.createServer({ key: fs.readFileSync(path.join(dir, 'key.pem')), cert: fs.readFileSync(path.join(dir, 'cert.pem')) }, handler('https'));
  const plain = http.createServer(handler('http'));
  tls.on('upgrade', logUpgrade('https')); plain.on('upgrade', logUpgrade('http'));
  /* F-4: a local user starting Chrome with --proxy-server. The plain server doubles as that proxy and tunnels every
     CONNECT back to the fixture, so the control run still reaches it and the hit log still names the host. */
  plain.on('connect', (req, sock, head) => {
    const up = net.connect(443, '127.0.0.1', () => { sock.write('HTTP/1.1 200 Connection established\r\n\r\n'); up.write(head); up.pipe(sock); sock.pipe(up); });
    up.on('error', () => sock.destroy()); sock.on('error', () => up.destroy());
  });
  await listen(tls, 443); await listen(plain, 80);
  return () => { tls.close(); plain.close(); };
}

/* Each address gets its own mark in the query, so a request Chrome makes by itself to the same host is never
   counted as the case reaching the fixture. Path rules in the pack match on the path, which the mark leaves alone. */
function marked(address, mark) {
  if (!/^https?:/.test(address)) return address;   // data:, chrome:, file: and the like carry no mark
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
const markOf = (c, n) => c.id.replace(/[^A-Za-z0-9]/g, '') + 'n' + n;
async function visit(context, c, address, n) {
  const mark = markOf(c, n);
  const page = await context.newPage();
  const opened = [];   // C-3: pop-ups and new tabs the case opens
  const onPage = p => { if (p !== page) opened.push(p); };
  context.on('page', onPage);
  const failed = [];
  page.on('requestfailed', r => { if (r.isNavigationRequest()) failed.push((r.failure() || {}).errorText || ''); });
  let error = '';
  try { await page.goto(marked(address, mark), { waitUntil: 'domcontentloaded', timeout: 20000 }); }
  catch (e) { error = (String(e.message).match(/net::(ERR_[A-Z_]+)/) || [])[1] || String(e.message).split('\n')[0].slice(0, 120); }
  /* A hop case starts on an approved host, which is meant to answer; what counts is whether the place it sends
     the browser to was reached. A page that moves by script does so after the load, so give it time. */
  const target = c.kind === 'hop' ? c.target || new URL(new URL(address).searchParams.get('to')).host : '';
  const arrived = () => hits.filter(h => h.url.includes('swz=' + mark) && (!target || h.host === target));
  if (target && !error && c.click) {
    const click = { middle: { button: 'middle' }, ctrl: { modifiers: ['Control'] } }[c.click] || {};
    await page.click('#go', { timeout: 5000, ...click }).catch(e => { error = 'click: ' + String(e.message).split('\n')[0].slice(0, 80); });
  }
  if (target && !error) {
    for (let i = 0; i < 16 && !arrived().length; i++) await page.waitForTimeout(250);
    if (!arrived().length && !failed.find(Boolean)) {
      /* A refusal can land in a pop-up or a frame rather than the page itself. */
      const read = f => f.evaluate(() => document.documentElement.innerText).catch(() => '');
      for (const f of [page, ...opened].flatMap(p => p.frames())) if ((await read(f)).includes(BLOCKED)) { error = BLOCKED; break; }
    }
  }
  /* A refused internal page (chrome://, file:, view-source:) can commit Chrome's error page without goto throwing. */
  if (!target && !error && !arrived().length) {
    const text = await page.evaluate(() => document.documentElement.innerText).catch(() => '');
    if (text.includes(BLOCKED)) error = BLOCKED;
  }
  context.off('page', onPage);
  const seen = arrived();
  const out = { id: c.id, expect: c.expect, address, reached: seen.length, hosts: [...new Set(seen.map(h => h.host))],
    error: error || (failed.find(Boolean) || '').replace('net::', ''), final: '' };
  try { out.final = new URL(page.url()).origin + new URL(page.url()).pathname; } catch (e) { out.final = page.url().slice(0, 80); }
  if (c.kind === 'signin') {
    const cookies = await context.cookies('https://' + spec.hub_host + '/');
    out.signin = { back_on_hub: out.final === 'https://' + spec.hub_host + '/auth/google/callback',
      via_google: seen.some(h => h.host === 'accounts.google.com'), cookie: cookies.some(k => k.name === 'swz_fixture_session') };
    await context.clearCookies();
  }
  if (opened.length) out.opened = opened.length;
  for (const p of opened) await p.close().catch(() => {});
  await page.close();
  return out;
}
/* B-5, E-3 typed: text typed into the address bar. Playwright cannot reach Chrome's own UI, so xdotool types it into the
   window (Ctrl+L, the text, Enter), found by a title the harness gives the page. "{mark}" in the text becomes the
   case's mark: a URL carries it as swz=, a bare word is searched for, and a script fetches an approved host with it. */
/* Xvfb has no window manager, so nothing gives Chrome's window the focus the typing needs. openbox runs only while a
   typed case does. */
let wm = null;
async function windowManager() {
  if (wm) return;
  wm = spawn('openbox', [], { stdio: 'ignore' });
  wm.on('error', () => {});
  await pause(1000);
}
async function typed(context, c, address, n) {
  await windowManager();
  const mark = markOf(c, n);
  const text = address.split('{mark}').join(mark);
  const word = !/[:/.]/.test(text);
  const arrived = () => hits.filter(h => word ? h.url.startsWith('/search?') && h.url.includes('q=' + text + '&') : h.url.includes('swz=' + mark));
  const page = await context.newPage();
  const failed = [];
  page.on('requestfailed', r => { if (r.isNavigationRequest()) failed.push(((r.failure() || {}).errorText || '').replace('net::', '')); });
  let error = '';
  try {
    await page.goto('https://claude.ai/?swz=s' + mark, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.evaluate(t => { document.title = t; }, 'swz-type-' + mark);
    await page.bringToFront();
    execFileSync('xdotool', ['search', '--sync', '--limit', '1', '--name', 'swz-type-' + mark, 'windowactivate', '--sync', '%1',
      'key', '--clearmodifiers', 'ctrl+l', 'sleep', '0.3', 'type', '--delay', '15', text], { timeout: 15000, stdio: 'ignore' });
    await pause(700);   // Enter straight after the text was lost: the address bar was still working on it
    execFileSync('xdotool', ['key', '--clearmodifiers', 'Return'], { timeout: 5000, stdio: 'ignore' });
  } catch (e) { error = 'type: ' + String(e.message).split('\n')[0].slice(0, 80); }
  if (!error) {
    for (let i = 0; i < 20 && !arrived().length; i++) await pause(250);
    if (!arrived().length) {
      /* An address-bar navigation is browser-initiated, so Playwright reports no failed request for it, and the
         blocked page's visible text never names the error. Its source does (Chrome embeds the code in the page's
         data); the wording is the fallback. Both were seen on the run's screenshots of the pack's blocked page. */
      const html = await page.content().catch(() => '');
      const body = await page.evaluate(() => document.documentElement.innerText).catch(() => '');
      if (html.includes(BLOCKED) || body.includes(BLOCKED) || failed.includes(BLOCKED) ||
          /organi[sz]ation doesn.t allow you to view this site/i.test(body)) error = BLOCKED;
      else if (failed.find(Boolean)) error = failed.find(Boolean);
    }
  }
  const seen = arrived();
  /* Nothing arrived and nothing was refused: keep a picture, so a typing failure can be told from a policy result. */
  if (!seen.length && !error) {
    try { execFileSync('import', ['-window', 'root', path.join(OUT, 'typed-' + mark + '.png')], { timeout: 10000, stdio: 'ignore' }); } catch (e) { /* no ImageMagick */ }
    try { error = 'nothing arrived; active window: ' + execFileSync('xdotool', ['getactivewindow', 'getwindowname'], { timeout: 5000 }).toString().trim().slice(0, 60); } catch (e) { error = 'nothing arrived; no active window'; }
  }
  const out = { id: c.id, expect: c.expect, address: text, reached: seen.length, hosts: [...new Set(seen.map(h => h.host))], error, final: '' };
  try { out.final = new URL(page.url()).protocol === 'https:' ? new URL(page.url()).origin + new URL(page.url()).pathname : page.url().slice(0, 40); } catch (e) { out.final = ''; }
  await page.close();
  return out;
}
const BASE_ARGS = ['--host-resolver-rules=MAP * 127.0.0.1', '--ignore-certificate-errors', '--no-first-run', '--no-default-browser-check'];
/* F and B-6: a local user starting Chrome with switches. Each address gets a browser of its own, with its own new
   user data directory (F-2: policy must hold in a profile nobody set up), the case's switches added to the harness's.
   "{url}" in the switches puts the marked address on the command line (B-6); the case then never calls goto, and
   counts what Chrome opened by itself. Playwright refuses a bare address among the switches, so a "spawn" case starts
   google-chrome itself, without a driver, and can only count requests (zero is the pass, as for STOP). */
const pause = ms => new Promise(r => setTimeout(r, ms));
/* A Chrome that has already gone (refused a switch, crashed, never started) sends nothing, which would read as a pass
   for STOP. So the exit is watched: if Chrome ended before the harness stopped it, the row says so and fails. */
async function spawned(dir, args, ms, during) {
  const proc = spawn('google-chrome', ['--user-data-dir=' + dir, ...BASE_ARGS, ...args], { stdio: 'ignore' });
  let gone = '';
  proc.on('exit', (code, signal) => { gone = gone || 'Chrome exited early (' + (signal || 'code ' + code) + ')'; });
  proc.on('error', e => { gone = gone || 'Chrome did not start (' + e.code + ')'; });
  await pause(ms);
  const early = gone;
  const seen = during && !early ? await during() : undefined;
  if (!early) proc.kill('SIGTERM');
  await pause(500);
  return { early, seen };
}
/* P-1: Chrome asked for a remote debugging port. The control run proves the port opens without the pack; the process
   step (full pack, RemoteDebuggingAllowed false) must leave it closed. Nothing here speaks CDP; a TCP connect is all. */
const PORT = 9333;
const connects = () => new Promise(resolve => {
  const s = net.connect(PORT, '127.0.0.1');
  s.once('connect', () => { s.destroy(); resolve(true); }); s.once('error', () => resolve(false));
});
async function debugPort(work, c, n) {
  /* A Chrome that had already exited leaves the port closed too, so that must fail, not pass. */
  const { early, seen: open } = await spawned(path.join(work, 'port-' + markOf(c, n)), ['--remote-debugging-port=' + PORT, 'about:blank'], 5000, connects);
  return { id: c.id, expect: c.expect, address: '--remote-debugging-port=' + PORT, reached: open ? 1 : 0, port: open ? 'open' : 'closed',
    early, error: early, final: '' };
}
/* X-1, weak on purpose: an approved page with a link to another program's scheme. xdg-open and xdg-email are shims
   first on PATH that only write a line to a marker file. Chrome normally asks before it starts a program and nobody
   answers, so no start proves little; the row says how many starts and what Chrome reported, and never fails. */
let MARKER = '';
async function protocol(context, c, address, n) {
  const before = fs.existsSync(MARKER) ? fs.readFileSync(MARKER, 'utf8').split('\n').filter(Boolean).length : 0;
  const page = await context.newPage();
  const row = { id: c.id, expect: c.expect, address: decodeURIComponent(new URL(address).searchParams.get('to')), reached: 0, error: '', final: '' };
  page.on('requestfailed', r => { if (r.isNavigationRequest() && !row.error) row.error = ((r.failure() || {}).errorText || '').replace('net::', ''); });
  try {
    await page.goto(marked(address, markOf(c, n)), { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.click('#go', { timeout: 5000 });
    await page.waitForTimeout(2500);
  } catch (e) { row.error = row.error || String(e.message).split('\n')[0].slice(0, 100); }
  const after = fs.existsSync(MARKER) ? fs.readFileSync(MARKER, 'utf8').split('\n').filter(Boolean).length : 0;
  row.launched = after - before;
  await page.close().catch(() => {});
  return row;
}
async function launched(chromium, work, c, address, n) {
  const mark = markOf(c, n), start = marked(address, mark);
  const args = c.launch.map(a => a.replace('{url}', start));
  const row = { id: c.id, expect: c.expect, address: c.launch.join(' ').replace('{url}', address), reached: 0, error: '', final: '' };
  const arrived = () => hits.filter(h => h.url.includes('swz=' + mark));
  if (c.spawn) {
    const { early } = await spawned(path.join(work, 'launch-' + mark), args, 5000);
    row.reached = arrived().length;
    if (early) row.early = row.error = early;
    return row;
  }
  let context;
  try {
    context = await chromium.launchPersistentContext(path.join(work, 'launch-' + mark), { channel: 'chrome', headless: false,
      ignoreHTTPSErrors: true, timeout: 20000, args: BASE_ARGS.concat(args) });
  } catch (e) { row.error = 'launch: ' + String(e.message).split('\n')[0].slice(0, 100); return row; }
  try {
    if (c.launch.some(a => a.includes('{url}'))) {
      for (let i = 0; i < 16 && !arrived().length; i++) await pause(250);
      row.reached = arrived().length;
      row.hosts = [...new Set(arrived().map(h => h.host))];
      for (const p of context.pages()) {
        const text = await p.evaluate(() => document.documentElement.innerText).catch(() => '');
        if (text.includes(BLOCKED)) { row.error = BLOCKED; row.final = p.url().slice(0, 80); }
      }
    } else {
      Object.assign(row, await visit(context, c, address, n), { address: row.address + ' ' + address });
    }
  } catch (e) { row.error = row.error || String(e.message).split('\n')[0].slice(0, 100); }
  finally { await context.close().catch(() => {}); }
  return row;
}
function verdict(mode, r) {
  if (r.early) return 'FAIL: ' + r.early + ', so nothing was tested';
  if (r.launched !== undefined) return 'recorded (weak): ' + r.launched + ' program start' + (r.launched === 1 ? '' : 's') + (r.error ? ', ' + r.error : '');
  if (r.port) return mode === 'control' ? (r.port === 'open' ? 'reached (port open)' : 'FAIL: the port did not open without policy, so this case proves nothing')
    : r.port === 'closed' ? 'refused (port closed)' : 'FAIL: remote debugging port open under the full pack';
  if (r.expect === 'RECORD' && r.error.startsWith('launch:')) return 'recorded: ' + r.error;
  const signedIn = !r.signin || (r.signin.back_on_hub && r.signin.via_google && r.signin.cookie);
  if (mode === 'control') return r.reached > 0 && signedIn ? 'reached' : 'FAIL: did not reach the fixture without policy, so this case proves nothing';
  if (r.expect === 'ALLOW') return r.reached > 0 && signedIn && !r.error ? 'allowed' : 'FAIL: an approved address was refused';
  const refused = r.reached === 0 && r.error === BLOCKED;
  if (r.expect === 'ENFORCE') return refused ? 'refused' : r.reached ? 'FAIL: reached the fixture' : 'FAIL: not refused by policy (' + (r.error || 'no error') + ')';
  /* STOP: the control run reached the fixture and the enforced run sent nothing, but Chrome showed no refusal the
     harness can read (script moves, pop-ups, frames, form posts; first seen on Chrome 156). Zero requests is the pass. */
  if (r.expect === 'STOP') return r.reached === 0 ? 'stopped (no request)' + (r.error ? ', ' + r.error : '') : 'FAIL: reached the fixture';
  /* GAP: the pack does not stop it and the README says so. Reaching is the documented result; anything else means the
     README is out of date. */
  if (r.expect === 'GAP') return r.reached > 0 ? 'gap, as the README says (reached)' : 'FAIL: no longer reaches the fixture; update the README';
  return refused ? 'recorded: refused' : r.reached ? 'recorded: reached' : 'recorded: ' + (r.error || 'no request, no error');
}
function report(mode, version, rows) {
  const lines = ['### Chrome policy pack, ' + mode + ' run', '', version + ' on ' + os.platform() + ' ' + os.release(), '',
    mode === 'enforced' ? 'Driven without: ' + DROPPED.join(', ') + '.' : mode === 'process' ? 'Full pack, not driven; only the extension entries left out (tier 2).'
      : 'No policy file installed.', '',
    '| Case | Expected | Address | Fixture requests | Browser error | Result |', '|---|---|---|---|---|---|',
    ...rows.map(r => `| ${r.id} | ${r.expect} | \`${r.address}\` | ${r.reached} | ${r.error || ''} | ${r.verdict} |`), '',
    'Not run: ' + spec.not_run.map(n => n.id + ' (' + n.reason + ')').join('; ') + '.', ''];
  return lines.join('\n');
}

(async () => {
  const mode = process.argv[2];
  if (mode === 'render') { fs.writeFileSync(process.argv[3], render(process.argv[4] === 'full')); return; }
  assert.ok(['control', 'enforced', 'process'].includes(mode), 'usage: chrome-policy.cjs render OUT [full] | control | enforced | process');
  if (process.env.GITHUB_ACTIONS !== 'true') { console.log('Not run: needs a machine-wide Chrome policy file and ports 80 and 443, CI only'); return; }
  if (mode === 'control') assert.deepEqual(installed(), [], 'a policy file is installed during the control run');
  else {
    assert.deepEqual(installed(), ['swangz-test.json'], 'expected exactly the rendered pack in ' + POLICY_DIR);
    assert.equal(fs.readFileSync(path.join(POLICY_DIR, 'swangz-test.json'), 'utf8'), render(mode === 'process'), 'the installed file is not the rendered pack');
  }
  fs.mkdirSync(OUT, { recursive: true });
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'swz-policy-'));
  const stop = await fixture(work);
  /* X-1's shims: first on PATH for every browser this run starts. */
  const shims = path.join(work, 'shims');
  MARKER = path.join(work, 'program-starts.txt');
  fs.mkdirSync(shims);
  for (const name of ['xdg-open', 'xdg-email']) fs.writeFileSync(path.join(shims, name), '#!/bin/sh\necho "$0 $*" >> ' + JSON.stringify(MARKER) + '\n', { mode: 0o755 });
  process.env.PATH = shims + ':' + process.env.PATH;
  const { chromium } = require('playwright');
  /* The process step drives nothing: the full pack is expected to stop a driver attaching at all. */
  const context = mode === 'process' ? null : await chromium.launchPersistentContext(path.join(work, 'profile'), { channel: 'chrome', headless: false, ignoreHTTPSErrors: true,
    args: BASE_ARGS });
  const version = context && context.browser() ? 'Chrome ' + context.browser().version() : execFileSync('google-chrome', ['--version']).toString().trim();
  const rows = [];
  try {
    for (const c of spec.cases) {
      /* E: some addresses have no fixture behind them (IP literals, other schemes, local network and metadata
         addresses). They get no control run, so nothing is ever sent there without the pack, and the enforced pass
         condition is the policy refusal itself, not a timeout. */
      if (mode === 'control' && c.control === false) {
        for (const address of expand(c)) rows.push({ id: c.id, expect: c.expect, address, reached: 0, error: '', verdict: 'not run without policy (no fixture behind it)' });
        continue;
      }
      /* P cases need the full pack, so they run in the control pass and the process step only; the process step runs
         nothing else. */
      if ((mode === 'process') !== (c.step === 'process') && !(mode === 'control' && c.step === 'process')) {
        if (mode === 'enforced') rows.push({ id: c.id, expect: c.expect, address: '', reached: 0, error: '', verdict: 'runs in the process step, with the full pack' });
        continue;
      }
      let n = 0;
      for (const address of expand(c)) {
        const r = c.step === 'process' ? await debugPort(work, c, ++n) : c.kind === 'protocol' ? await protocol(context, c, address, ++n)
          : c.kind === 'typed' ? await typed(context, c, address, ++n)
          : c.launch ? await launched(chromium, work, c, address, ++n) : await visit(context, c, address, ++n);
        r.verdict = verdict(mode, r); rows.push(r);
      }
    }
  } finally { if (context) await context.close(); stop(); if (wm) wm.kill(); }
  const text = report(mode, version, rows);
  fs.writeFileSync(path.join(OUT, mode + '.json'), JSON.stringify({ mode, version, os: os.platform() + ' ' + os.release(), dropped: mode === 'enforced' ? DROPPED : mode === 'process' ? DROPPED.filter(n => n.startsWith('Extension')) : [], rows, not_run: spec.not_run }, null, 2));
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
