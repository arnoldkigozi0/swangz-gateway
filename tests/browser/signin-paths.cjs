/* MANAGED-WORKSPACE 9.3 step 5: with the prepared pack installed, the official sign-in paths of ChatGPT, Claude and
   Gemini still open. Each path starts on the tool's own site and clicks through to the provider's sign-in page
   (Google, Apple, OpenAI, Anthropic), and two challenge widgets (Cloudflare Turnstile, hCaptcha) load on an
   approved page. The pass: no page and no frame ends on Chrome's ERR_BLOCKED_BY_ADMINISTRATOR.

   Real sites, from the CI runner's own network. Nothing is typed, no field is filled, no credential exists here: a
   path stops at the first provider page, and earlier if a password field shows. The challenge page uses the
   providers' public test site keys, which always pass and are documented for exactly this.

   A step that never reached its provider (a vendor changed a button, a site challenged the runner) is not a failure
   of the pack; it is listed as not proven, with its screenshot. Only a refusal by the policy fails the job.
   Only origins, paths and error names are written to the results; no query strings, cookies or page text.

   node signin-paths.cjs          CI only, with the driven copy of the pack installed (chrome-policy.cjs render)
   SIGNIN_LOCAL=1 node ...        no pack, the bundled Chromium: for working on the click paths, never a result */
const assert = require('assert');
const fs = require('fs');
const https = require('https');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const POLICY_DIR = '/etc/opt/chrome/policies/managed';
const OUT = path.join(process.env.CHROME_POLICY_OUT || '/tmp/swangz-chrome-policy', 'signin');
const HUB = process.env.CHROME_POLICY_HUB_HOST || 'hub.swangz-ci.com';
const LOCAL = process.env.SIGNIN_LOCAL === '1';
const BLOCKED = 'ERR_BLOCKED_BY_ADMINISTRATOR';
const BLOCKED_WORDS = /organi[sz]ation doesn.t allow you to view this site/i;
/* Public test keys: Turnstile's "always passes, visible" and hCaptcha's "always passes" (both providers' docs). */
const TURNSTILE_TEST_KEY = '1x00000000000000000000AA';
const HCAPTCHA_TEST_KEY = '10000000-ffff-ffff-ffff-000000000001';

const at = (...hosts) => u => { try { const h = new URL(u).hostname; return hosts.some(x => h === x || h.endsWith('.' + x)); } catch (e) { return false; } };
const button = name => ({ name });
/* Each path: where it starts, then the clicks, each with the page it should reach. A click names the control by its
   words, as a person would find it. */
const PATHS = [
  /* ChatGPT's Log in opens its own dialog on chatgpt.com (Google, Apple, phone, email). OpenAI's own page,
     auth.openai.com, comes only after an email is typed, so it is visited directly instead, and says so. */
  { id: 'chatgpt-login', provider: 'OpenAI (dialog)', start: 'https://chatgpt.com/', steps: [
    { click: button(/^log in$/i), reach: at('chatgpt.com', 'auth.openai.com') }], shows: /continue with google/i },
  { id: 'openai-direct', provider: 'OpenAI', start: 'https://auth.openai.com/log-in', steps: [], reach: at('auth.openai.com', 'chatgpt.com'),
    shows: /continue with google|email address/i, direct: true },
  { id: 'chatgpt-google', provider: 'Google', start: 'https://chatgpt.com/', steps: [
    { click: button(/^log in$/i), reach: at('chatgpt.com', 'auth.openai.com') },
    { click: button(/continue with google/i), reach: at('accounts.google.com') }] },
  { id: 'chatgpt-apple', provider: 'Apple', start: 'https://chatgpt.com/', steps: [
    { click: button(/^log in$/i), reach: at('chatgpt.com', 'auth.openai.com') },
    { click: button(/continue with apple/i), reach: at('appleid.apple.com') }] },
  { id: 'claude-google', provider: 'Google', start: 'https://claude.ai/login', steps: [
    { click: button(/continue with google/i), reach: at('accounts.google.com') }] },
  { id: 'claude-anthropic', provider: 'Anthropic', start: 'https://claude.ai/login', steps: [], reach: at('claude.ai'),
    shows: /continue with google|continue with email/i },
  { id: 'gemini-google', provider: 'Google', start: 'https://gemini.google.com/', steps: [
    { click: button(/^sign in$/i), reach: at('accounts.google.com') }] },
  { id: 'hcaptcha-demo', provider: 'hCaptcha', start: 'https://accounts.hcaptcha.com/demo', steps: [], reach: at('hcaptcha.com'),
    frames: [at('hcaptcha.com')] },
  { id: 'challenges-on-hub', provider: 'Cloudflare and hCaptcha', start: 'https://' + HUB + '/signin-check', steps: [], reach: at(HUB),
    frames: [at('challenges.cloudflare.com'), at('hcaptcha.com')], local: true },
];

/* A challenge in front of a site (Cloudflare's "Just a moment", "Performing security verification") is part of the path
   the pack has to let through: its frames are recorded, and a path waits up to 30 s for it to clear. */
const CHALLENGE_FRAMES = at('challenges.cloudflare.com', 'hcaptcha.com', 'recaptcha.net', 'www.google.com');
const CHALLENGE_WORDS = /just a moment|performing security verification|verify you are human|checking your browser/i;
const pause = ms => new Promise(r => setTimeout(r, ms));
const where = u => { try { const x = new URL(u); return x.protocol === 'chrome-error:' ? 'chrome-error' : x.origin + x.pathname; } catch (e) { return String(u).slice(0, 40); } };

/* The approved page that carries both challenge widgets: the Hub's host, answered here, on 443. */
function hubPage(dir) {
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=' + HUB,
    '-keyout', path.join(dir, 'key.pem'), '-out', path.join(dir, 'cert.pem')], { stdio: 'ignore' });
  const html = '<!doctype html><title>challenges</title>' +
    '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>' +
    '<script src="https://js.hcaptcha.com/1/api.js" async defer></script>' +
    '<div class="cf-turnstile" data-sitekey="' + TURNSTILE_TEST_KEY + '"></div>' +
    '<div class="h-captcha" data-sitekey="' + HCAPTCHA_TEST_KEY + '"></div>';
  const server = https.createServer({ key: fs.readFileSync(path.join(dir, 'key.pem')), cert: fs.readFileSync(path.join(dir, 'cert.pem')) },
    (req, res) => { res.writeHead(req.url.startsWith('/signin-check') ? 200 : 404, { 'content-type': 'text/html' }); res.end(html); });
  return new Promise(resolve => server.listen(LOCAL ? 8443 : 443, '127.0.0.1', () => resolve(() => server.close())));
}

/* Every page and frame the path has open, checked for Chrome's refusal: its URL is chrome-error and its source names
   the error, or its words do. Requests the policy refused are kept too: a frame's own, and (for the record only)
   subresources. */
async function refusals(pages, failed) {
  const found = [];
  for (const p of pages) {
    if (p.isClosed()) continue;
    for (const f of p.frames()) {
      if (!f.url().startsWith('chrome-error:')) continue;
      const html = await f.content().catch(() => '');
      const text = await f.evaluate(() => document.documentElement.innerText).catch(() => '');
      if (html.includes(BLOCKED) || BLOCKED_WORDS.test(text)) found.push({ kind: f === p.mainFrame() ? 'page' : 'frame', url: where(f.url()) });
    }
  }
  for (const r of failed) if (r.nav) found.push({ kind: r.main ? 'page' : 'frame', url: r.url });
  return found;
}

async function run(context, p, n) {
  const page = await context.newPage();
  const pages = [page];
  const onPage = q => { if (!pages.includes(q)) pages.push(q); };
  context.on('page', onPage);
  const failed = [];
  const blockedSub = new Set();
  const onFail = r => {
    const err = (r.failure() || {}).errorText || '';
    if (!err.includes(BLOCKED)) return;
    if (r.isNavigationRequest()) failed.push({ nav: true, main: (() => { try { return r.frame() === r.frame().page().mainFrame(); } catch (e) { return false; } })(), url: where(r.url()) });
    else blockedSub.add(where(r.url()));
  };
  context.on('requestfailed', onFail);
  const row = { id: p.id, provider: p.provider, start: p.start.replace(HUB, '<hub host>'), reached: [], steps: [], blocked: [], blocked_subresources: [],
    password_field: false, final: '', screenshots: [], note: '' };
  const shot = async (q, tag) => {
    const file = path.join(OUT, p.id + '-' + tag + '.png');
    await q.screenshot({ path: file, timeout: 10000 }).then(() => row.screenshots.push(path.basename(file))).catch(() => {});
  };
  const current = () => pages.filter(q => !q.isClosed()).slice(-1)[0] || page;
  const challenged = q => q.evaluate(() => document.title + ' ' + (document.body ? document.body.innerText.slice(0, 400) : '')).then(t => CHALLENGE_WORDS.test(t)).catch(() => false);
  const challenges = new Set();
  const settle = async q => {
    await q.waitForLoadState('load', { timeout: 15000 }).catch(() => {}); await pause(3000);
    for (const f of q.frames()) if (CHALLENGE_FRAMES(f.url()) && (!at('www.google.com')(f.url()) || f.url().includes('/recaptcha/'))) challenges.add(new URL(f.url()).hostname);
    if (await challenged(q)) {
      challenges.add('challenge page on ' + new URL(q.url()).hostname);
      for (let t = 0; t < 30 && await challenged(q); t++) await pause(1000);
      /* One reload if it is still there: a cleared challenge sometimes leaves the page waiting. */
      if (await challenged(q)) { await q.reload({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {}); for (let t = 0; t < 30 && await challenged(q); t++) await pause(1000); }
      await q.waitForLoadState('load', { timeout: 15000 }).catch(() => {}); await pause(1500);
    }
  };
  try {
    try { await page.goto(p.start, { waitUntil: 'domcontentloaded', timeout: 30000 }); }
    catch (e) {
      const m = String(e.message).match(/net::(ERR_[A-Z_]+)/);
      if (m && m[1] === BLOCKED) failed.push({ nav: true, main: true, url: where(p.start) });
      row.note = 'start: ' + (m ? m[1] : String(e.message).split('\n')[0].slice(0, 80));
    }
    await settle(page);
    await shot(page, '0-start');
    if (p.reach && p.reach(page.url())) row.reached.push(where(page.url()));
    let i = 0;
    for (const s of p.steps) {
      i++;
      const q = current();
      /* A password field ends the path: nothing past it is ours to see. */
      if (await q.locator('input[type=password]:visible').count().catch(() => 0)) { row.password_field = true; row.note = 'stopped at a password field'; break; }
      const target = q.getByRole('button', s.click).or(q.getByRole('link', s.click)).first();
      const before = pages.length, was = q.url();
      try { await target.click({ timeout: 20000, noWaitAfter: true }); }
      catch (e) { row.steps.push({ step: i, clicked: false }); row.note = 'step ' + i + ': no control named ' + s.click.name + ' on ' + where(q.url()); break; }
      for (let t = 0; t < 60 && q.url() === was && pages.length === before; t++) await pause(250);
      const now = current();
      await settle(now);
      row.steps.push({ step: i, clicked: true, landed: where(now.url()), popup: pages.length > before });
      await shot(now, i + '-' + (s.click.name.source.replace(/[^a-z]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'step'));
      if (s.reach(now.url())) row.reached.push(where(now.url()));
      else { row.note = 'step ' + i + ': landed on ' + where(now.url()); break; }
    }
    const last = current();
    row.password_field = row.password_field || !!(await last.locator('input[type=password]:visible').count().catch(() => 0));
    if (p.frames) row.frames = p.frames.map(m => [...new Set(last.frames().map(f => f.url()).filter(m).map(f => new URL(f).hostname))]);
    row.challenges = [...challenges];
    row.challenge_stuck = await challenged(last);
    if (p.shows) row.shows = await last.getByText(p.shows).first().isVisible().catch(() => false);
    if (p.direct) row.note = 'visited directly (the clicked route needs an email typed)';
    row.final = where(last.url());
    row.blocked = await refusals(pages, failed);
    row.blocked_subresources = [...blockedSub];
  } finally {
    context.off('page', onPage); context.off('requestfailed', onFail);
    for (const q of pages) await q.close().catch(() => {});
  }
  const wanted = (p.steps.length ? p.steps.length : 0) + (p.reach ? 1 : 0);
  const frameOk = !p.frames || (row.frames || []).every(list => list.length > 0);
  row.verdict = row.blocked.length ? 'FAIL: refused by policy (' + row.blocked.map(b => b.kind + ' ' + b.url).join(', ') + ')'
    : row.challenge_stuck ? 'not proven: a challenge in front of ' + row.final + ' did not clear (nothing refused)'
    : p.shows && !row.shows ? 'not proven: the sign-in controls did not show on ' + row.final + ' (nothing refused)'
    : row.reached.length >= wanted && frameOk ? 'reached' + (p.direct ? ' (direct visit)' : '') + ', nothing refused'
    : 'not proven: ' + (row.note || (frameOk ? 'provider page not reached' : 'no challenge frame loaded'));
  return row;
}

function report(version, rows, pack) {
  const lines = ['## Official sign-in paths, prepared pack installed', '',
    version + '. Pack: ' + pack + '. Real sites from the runner; nothing typed; public test keys on the challenge page.', '',
    '| Path | Provider | Reached | Final page | Challenges seen | Password field | Refused subresources | Result |', '|---|---|---|---|---|---|---|---|'];
  for (const r of rows) lines.push('| ' + [r.id, r.provider, r.reached.join(' → ') || '–', '`' + r.final + '`', (r.challenges || []).join(', ') || '–', r.password_field ? 'yes (stopped)' : 'no',
    r.blocked_subresources.length, r.verdict].join(' | ') + ' |');
  const failing = rows.filter(r => r.verdict.startsWith('FAIL')).length, unproven = rows.filter(r => r.verdict.startsWith('not proven')).length;
  lines.push('', rows.length + ' paths: ' + (rows.length - failing - unproven) + ' reached with nothing refused, ' + failing + ' refused by policy, ' + unproven + ' not proven.');
  lines.push('A refused subresource (a script or image, not a page or frame) is listed for the record; the URL list is not meant to filter those.');
  return lines.join('\n') + '\n';
}

(async () => {
  let pack = 'none (local, not a result)';
  if (!LOCAL) {
    if (process.env.GITHUB_ACTIONS !== 'true') { console.log('Not run: needs the machine-wide pack installed, CI only (SIGNIN_LOCAL=1 for the click paths)'); return; }
    const files = fs.readdirSync(POLICY_DIR);
    assert.deepEqual(files, ['swangz-test.json'], 'expected exactly the driven copy of the pack in ' + POLICY_DIR);
    const installed = JSON.parse(fs.readFileSync(path.join(POLICY_DIR, files[0]), 'utf8'));
    assert.ok(installed.URLBlocklist.includes('*'), 'the installed pack is not default-deny');
    assert.ok(installed.URLAllowlist.includes(HUB), 'the installed pack does not allow the Hub host');
    pack = 'default-deny, ' + installed.URLAllowlist.length + ' allowed entries, process-level keys left out so a driver can attach';
  }
  fs.mkdirSync(OUT, { recursive: true });
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'swz-signin-'));
  const stop = await hubPage(work);
  const { chromium } = require('playwright');
  const context = await chromium.launchPersistentContext(path.join(work, 'profile'), {
    ...(LOCAL ? {} : { channel: 'chrome' }), headless: LOCAL, ignoreHTTPSErrors: true, viewport: { width: 1280, height: 800 },
    args: ['--host-resolver-rules=MAP ' + HUB + ' 127.0.0.1' + (LOCAL ? ':8443' : ''), '--no-first-run', '--no-default-browser-check'] });
  const version = 'Chrome ' + context.browser().version();
  const rows = [];
  try {
    for (const p of PATHS) {
      const r = await run(context, LOCAL && p.local ? { ...p, start: p.start.replace(HUB, HUB + ':8443') } : p);
      console.log(r.id + ': ' + r.verdict);
      rows.push(r);
    }
  } finally { await context.close(); stop(); }
  const text = report(version, rows, pack);
  fs.writeFileSync(path.join(OUT, 'signin.json'), JSON.stringify({ version, pack, local: LOCAL, rows }, null, 2));
  fs.writeFileSync(path.join(OUT, 'signin.md'), text);
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, text + '\n');
  console.log(text);
  const failing = rows.filter(r => r.verdict.startsWith('FAIL'));
  if (failing.length) { console.error(failing.length + ' refused: ' + failing.map(r => r.id).join(', ')); process.exit(1); }
})().catch(e => { console.error(e); process.exit(1); });
