/* Port-free behavioral regressions for the actual portal dispatcher and read-only views.
   Minimal element objects exercise state and events; real browser layout is verified separately. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../gateway/static/portal.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const paused = { paused_view: true, name: 'Sam <script>', status: 'paused', reason: 'Talk to your admin.', support_contact: 'help@swangzavenue.com' };
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const report = { id: 7, tool_name: '<img src=x onerror=alert(1)>', kind: 'weekly', state: 'returned',
  week_start: '2026-10-26', version: 1, currency: 'USD', reason: '<script>do not execute</script>', impact: 'Staff estimate' };
function element(tag, attrs, ...children) {
  return { tag, attrs: attrs || {}, children: children.flat(Infinity).filter(x => x != null), disabled: false,
    append(...xs) { this.children.push(...xs.flat(Infinity).filter(x => x != null)); },
    replaceChildren(...xs) { this.children = xs.flat(Infinity).filter(x => x != null); },
    replaceWith() {}, focus() {}, setAttribute(k, v) { this.attrs[k] = v; }, remove() { this.removed = true; }, addEventListener() {} };
}
const nodes = n => typeof n === 'object' ? [n, ...n.children.flatMap(nodes)] : [];
const text = n => typeof n === 'object' ? n.children.map(text).join(' ') : String(n);
function matches(n, selector) {
  if (selector.startsWith('.')) return (n.attrs.class || '').split(/\s+/).includes(selector.slice(1));
  return selector === 'dialog[open]' && n.tag === 'dialog' && n.attrs.open;
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

async function boot({ hash = '#/', search = '', me = paused, request, sui = {} } = {}) {
  const app = element('app'), calls = [], listeners = {}, keys = [], replacements = [], pushes = [], overlays = [];
  let guardCalls = 0;
  const c = { URLSearchParams, setTimeout: () => {},
    location: { hash, search, pathname: '/' },
    history: {
      replaceState(_a, _b, url) { replacements.push(url); c.location.hash = url.slice(url.indexOf('#')); c.location.search = ''; },
      pushState(_a, _b, url) { pushes.push(url); c.location.hash = url; } },
    document: { getElementById: id => id === 'app' ? app : nodes(app).find(n => n.attrs.id === id),
      querySelectorAll: selector => overlays.filter(n => !n.removed && selector.split(',').some(s => matches(n, s.trim()))), querySelector: () => null,
      addEventListener: (type, fn, capture) => { if (type === 'keydown') keys.push({ fn, capture }); }, activeElement: null },
    SUI: { ICONS: {}, el: (...args) => {
      const n = element(...args); n.focus = () => { c.document.activeElement = n; }; return n;
    }, icon: name => element('svg', { name }), fmt: { stamp: x => String(x) },
      themeButton: () => element('button', { 'aria-label': 'Theme' }), setGatewayOffset() {}, toast() {}, ...sui },
    HubUI: { guard() { guardCalls++; return true; } },
    fetch: async (url, opts = {}) => {
      const method = opts.method || 'GET'; calls.push([method, url]);
      const custom = request && await request(url, method);
      if (custom) return custom;
      if (url === '/api/me') return response(me);
      if (url === '/api/hub/reports?limit=30&offset=0') return response({ items: [report], total: 1 });
      if (url === '/api/hub/reports/7') return response(report);
      if (url === '/api/hub/notifications') return response({ items: [{ title: '<b>Update</b>', href: 'javascript:alert(1)', created: 123 }] });
      if (url === '/auth/options') return response({ google: false });
      throw Error('Unexpected request: ' + method + ' ' + url);
    }, addEventListener: (type, fn) => { listeners[type] = fn; }, scrollTo() {} };
  c.window = c;
  vm.runInNewContext(source, c, { filename: 'gateway/static/portal.js' });
  await flush();
  return { c, app, calls, overlays, replacements, pushes, get guardCalls() { return guardCalls; },
    async navigate(hash) { c.location.hash = hash; await listeners.hashchange(); await flush(); },
    key(key, mods = {}) {
      const e = { key, ...mods, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
      for (const listener of [...keys.filter(x => x.capture), ...keys.filter(x => !x.capture)]) { listener.fn(e); if (e.stopped) break; }
      return e;
    } };
}

module.exports = async function run() {
  let count = 0;
  async function check(name, fn) { await fn(); count++; console.log('PASS paused: ' + name); }
  await check('initial paused deep link uses only /me; own name/contact, no full state', async () => {
    const t = await boot({ hash: '#/tools' });
    assert.match(text(t.app), /Sam <script>, your access is paused/); assert.match(text(t.app), /help@swangzavenue.com/);
    assert.equal(t.c.location.hash, '#/'); assert.deepEqual(t.calls, [['GET', '/api/me']]);
    assert.equal(nodes(t.app).filter(n => n.tag === 'form').length, 0);
  });
  await check('unknown routes, queries, welcome, encoded/invalid IDs replace history with home', async () => {
    const t = await boot();
    for (const hash of ['#/tools', '#/devices', '#/requests', '#/privacy', '#/weekly', '#/studio', '#/business', '#/welcome/abc',
      '#/paused/reports?view=completed', '#/paused/reports/7?amend=1', '#/paused/reports/7?step=2', '#/paused/updates?read=1',
      '#/paused/reports/0', '#/paused/reports/007', '#/paused/reports/9007199254740991', '#/paused/reports/%37', '#/paused/reports/7/../8', '#/?']) {
      await t.navigate(hash); assert.equal(t.c.location.hash, '#/', hash); assert.match(text(t.app), /read-only workspace/);
    }
    assert.equal(t.guardCalls, 0); assert.equal(t.pushes.length, 0); assert.equal(t.calls.length, 1);
    const query = await boot({ hash: '#/paused/reports/7', search: '?amend=1' });
    assert.equal(query.c.location.hash, '#/'); assert.equal(query.c.location.search, ''); assert.equal(query.calls.length, 1);
  });
  await check('guard precedes registered page handlers and HubUI guard, including direct render', async () => {
    const t = await boot();
    t.c.SWP.page(/^#\/probe$/, () => { throw Error('Active extension entered'); });
    t.c.HubUI.guard = () => { throw Error('Dirty active form guard entered'); };
    await t.navigate('#/probe');
    t.c.location.hash = '#/probe'; await t.c.SWP.render();
    await t.c.SWP.frame('Active frame', element('section', null, 'Must stay hidden'));
    assert.equal(t.c.location.hash, '#/');
    assert.doesNotMatch(text(t.app), /Must stay hidden/);
  });
  await check('slash, Ctrl+K and Meta+K are consumed without navigation or requests', async () => {
    const t = await boot();
    for (const [key, mods] of [['/', {}], ['k', { ctrlKey: true }], ['K', { metaKey: true }]]) {
      const e = t.key(key, mods); assert.ok(e.prevented && e.stopped); assert.equal(t.c.location.hash, '#/');
    }
    assert.equal(t.key('Tab').prevented, false); assert.equal(t.calls.length, 1);
  });
  await check('paused API calls cannot invoke active reads or writes', async () => {
    const t = await boot(), before = t.calls.length;
    for (const [method, path] of [['GET', '/keys'], ['GET', '/studio'], ['GET', '/hub/procurement'],
      ['PUT', '/hub/reports/7'], ['POST', '/hub/reports/7/submit'], ['POST', '/hub/notifications/1/read'],
      ['POST', '/tools/chatgpt/request'], ['DELETE', '/keys/1']]) {
      await assert.rejects(t.c.SWP.api(method, path, {}), e => e.code === 'person_paused');
    }
    assert.equal(t.calls.length, before);
  });
  await check('reports, detail and updates use text and bounded links with no write controls', async () => {
    const t = await boot();
    await t.navigate('#/paused/reports'); assert.match(text(t.app), /Showing 1–1 of 1/);
    assert.ok(nodes(t.app).some(n => n.attrs.href === '#/paused/reports/7'));
    await t.navigate('#/paused/reports/7'); assert.match(text(t.app), /<script>do not execute<\/script>/);
    assert.match(text(t.app), /Staff estimate/);
    await t.navigate('#/paused/updates'); assert.match(text(t.app), /<b>Update<\/b>/);
    assert.ok(!nodes(t.app).some(n => /^(form|input|textarea|select|script)$/.test(n.tag)));
    assert.ok(nodes(t.app).filter(n => n.tag === 'a').every(n => ['#/', '#/paused/reports', '#/paused/updates'].includes(n.attrs.href)));
    assert.deepEqual(nodes(t.app).filter(n => n.tag === 'button').map(n => text(n)), ['', 'Sign out']);
    assert.ok(t.calls.every(([method]) => method === 'GET'));
  });
  await check('three-step navigation and repeated history events keep views and data bounded', async () => {
    const t = await boot();
    for (const hash of ['#/paused/reports', '#/paused/reports/7', '#/paused/updates', '#/paused/reports/7', '#/paused/reports', '#/', '#/paused/reports']) {
      await t.navigate(hash); assert.equal(t.c.location.hash, hash);
    }
    assert.equal(t.guardCalls, 0); assert.match(text(t.app), /Your reports/);
  });
  await check('unknown or mismatched report details return home without adding history', async () => {
    for (const res of [response({ error: 'Not found' }, 404), response({ ...report, id: 8 })]) {
      const t = await boot({ hash: '#/paused/reports/123', request: url => url.endsWith('/reports/123') ? res : undefined });
      assert.equal(t.c.location.hash, '#/'); assert.equal(t.pushes.length, 0);
    }
  });
  await check('empty reports and updates are readable', async () => {
    const t = await boot({ request: url => /hub\//.test(url) ? response({ items: [], total: 0 }) : undefined });
    await t.navigate('#/paused/reports'); assert.match(text(t.app), /No reports yet/);
    await t.navigate('#/paused/updates'); assert.match(text(t.app), /No updates yet/);
  });
  await check('long report lists paginate through GET only', async () => {
    const t = await boot({ hash: '#/paused/reports', request: url => url.includes('limit=30') ? response({
      items: url.endsWith('offset=0') ? Array.from({ length: 30 }, (_, i) => ({ ...report, id: i + 1 })) : [report], total: 31 }) : undefined });
    const next = nodes(t.app).find(n => n.tag === 'button' && text(n) === 'Next');
    await next.attrs.onclick({ currentTarget: next });
    assert.match(text(t.app), /Showing 31–31 of 31/);
    const prev = nodes(t.app).find(n => n.tag === 'button' && text(n) === 'Previous');
    await prev.attrs.onclick({ currentTarget: prev }); assert.match(text(t.app), /Showing 1–30 of 31/);
    assert.ok(t.calls.every(([method]) => method === 'GET'));
  });
  await check('loading responses cannot overwrite a later route', async () => {
    const slow = deferred();
    const t = await boot({ hash: '#/paused/reports', request: url => url.includes('limit=30') ? slow.promise : undefined });
    assert.match(text(t.app), /Loading/); await t.navigate('#/paused/updates');
    slow.resolve(response({ items: [report], total: 1 })); await flush();
    assert.match(text(t.app), /Your updates/); assert.doesNotMatch(text(t.app), /Showing 1/);
  });
  await check('read failure exposes retry and never writes', async () => {
    let fail = true;
    const t = await boot({ hash: '#/paused/reports', request: url => url.includes('limit=30') && fail ? response({ error: 'Unavailable' }, 503) : undefined });
    assert.match(text(t.app), /Unavailable/); fail = false;
    await nodes(t.app).find(n => n.tag === 'button' && text(n) === 'Try again').attrs.onclick();
    assert.match(text(t.app), /Showing 1–1 of 1/); assert.ok(t.calls.every(([method]) => method === 'GET'));
  });
  await check('selector-aware paused entry removes Hub sheets, drawers, scrims and open dialogs', async () => {
    const t = await boot(); t.c.SWP.S.studio = { secret: 'old studio' };
    const overlays = ['drawer', 'scrim', 'hub-side-sheet', 'hub-sheet-scrim'].map(className => element('aside', { class: className }));
    const dialog = element('dialog', { open: true }); dialog.close = () => { dialog.closed = true; };
    const unrelated = element('aside', { class: 'unrelated' });
    overlays.push(dialog); t.overlays.push(...overlays, unrelated); await t.navigate('#/');
    assert.equal(t.c.SWP.S.studio, null); assert.ok(overlays.every(n => n.removed));
    assert.ok(dialog.closed); assert.equal(unrelated.removed, undefined);
  });
  await check('mid-session person_paused refreshes /me and replaces the full identity', async () => {
    const slow = deferred(); let meCalls = 0;
    const t = await boot({ request: url => {
      if (url === '/api/me') { meCalls++; return response(paused); }
      if (url === '/api/studio') return response({ code: 'person_paused', error: 'Paused' }, 403);
      if (url === '/api/old') return slow.promise;
    } });
    t.c.SWP.S.me = { name: 'Old', catalog: ['secret'], keys: ['old'], privacy: {} }; t.c.SWP.S.studio = { old: true };
    const stale = t.c.SWP.api('GET', '/old');
    await assert.rejects(t.c.SWP.api('GET', '/studio'), e => e.code === 'person_paused');
    assert.equal(meCalls, 2); assert.equal(t.c.SWP.S.me, paused); assert.equal(t.c.SWP.S.studio, null);
    assert.equal(t.c.SWP.S.me.catalog, undefined); assert.match(text(t.app), /Sam <script>/);
    slow.resolve(response({ old: 'sensitive data' })); await assert.rejects(stale, e => e.code === 'person_paused');
    const before = t.calls.length;
    await assert.rejects(t.c.SWP.api('POST', '/hub/reports/7/submit', {}), e => e.code === 'person_paused');
    assert.equal(t.calls.length, before);
  });
  await check('active routes still dispatch and active unsaved guards still run', async () => {
    const t = await boot(); let called = 0;
    t.c.SWP.S.me = { catalog: [], keys: [] }; t.c.SWP.page(/^#\/probe$/, () => { called++; });
    await t.navigate('#/probe'); assert.equal(called, 1); assert.equal(t.guardCalls, 1);
    t.c.HubUI.guard = () => false; await t.navigate('#/tools'); assert.equal(called, 1); assert.equal(t.pushes.length, 1);
  });
  await check('an older /me response cannot restore a full identity after suspension', async () => {
    const slow = deferred(); let meCalls = 0;
    const t = await boot({ request: url => {
      if (url === '/api/me') return ++meCalls === 2 ? slow.promise : response(paused);
      if (url === '/api/studio') return response({ code: 'person_paused', error: 'Paused' }, 403);
    } });
    t.c.SWP.S.me = { catalog: ['secret'], keys: ['key'] };
    const stale = t.c.SWP.api('GET', '/me');
    await assert.rejects(t.c.SWP.api('GET', '/studio'));
    slow.resolve(response({ catalog: ['secret'], keys: ['key'] }));
    await assert.rejects(stale, e => e.code === 'person_paused');
    assert.equal(t.c.SWP.S.me, paused); assert.equal(meCalls, 3);
  });
  await check('a pause during initial Studio loading replaces state without active rendering', async () => {
    let meCalls = 0;
    const t = await boot({ request: url => {
      if (url === '/api/me') return response(++meCalls === 1 ? { catalog: [], keys: [] } : paused);
      if (url === '/api/studio') return response({ code: 'person_paused', error: 'Paused' }, 403);
    } });
    assert.equal(meCalls, 2); assert.equal(t.c.SWP.S.me, paused); assert.equal(t.c.SWP.S.studio, null);
    assert.match(text(t.app), /read-only workspace/); assert.doesNotMatch(text(t.app), /temporarily unavailable/);
  });
  await check('concurrent pause refusals share one identity refresh', async () => {
    const refreshed = deferred(); let meCalls = 0;
    const t = await boot({ request: url => {
      if (url === '/api/me') return ++meCalls === 1 ? response(paused) : refreshed.promise;
      if (url === '/api/a' || url === '/api/b') return response({ code: 'person_paused', error: 'Paused' }, 403);
    } });
    t.c.SWP.S.me = { catalog: [], keys: [] };
    const a = t.c.SWP.api('GET', '/a'), b = t.c.SWP.api('GET', '/b');
    await flush(); assert.equal(meCalls, 2);
    refreshed.resolve(response(paused));
    const result = await Promise.allSettled([a, b]);
    assert.ok(result.every(r => r.status === 'rejected' && r.reason.code === 'person_paused'));
    assert.equal(meCalls, 2); assert.equal(t.c.SWP.S.me, paused);
  });
  await check('ordinary load entering paused rejects older responses', async () => {
    const slow = deferred();
    const t = await boot({ request: url => url === '/api/old' ? slow.promise : undefined });
    t.c.SWP.S.me = { catalog: ['secret'], keys: ['old'] };
    const stale = t.c.SWP.api('GET', '/old');
    await t.c.SWP.load(); assert.equal(t.c.SWP.S.me, paused);
    slow.resolve(response({ old: 'sensitive data' }));
    await assert.rejects(stale, e => e.code === 'person_paused');
  });
  await check('paused navigation focuses the new read-only region', async () => {
    const t = await boot();
    for (const hash of ['#/', '#/paused/reports', '#/paused/reports/7', '#/paused/updates', '#/']) {
      await t.navigate(hash);
      const focused = t.c.document.activeElement;
      assert.ok(nodes(t.app).includes(focused));
      assert.equal(focused.attrs.class, 'paused-content'); assert.equal(focused.attrs.tabindex, '-1');
    }
  });
  await check('Privacy notice states provider declarations with the approved static copy and no registry call', async () => {
    const active = { name: 'Ada', email: 'ada@swangzavenue.com', active: true, catalog: [], keys: [], privacy: {}, hub_unread: 0 };
    const t = await boot({ hash: '#/privacy', me: active, sui: { avatar: name => element('span', { class: 'avatar' }, name) },
      request: url => url === '/api/studio' ? response(null) : undefined });
    const all = nodes(t.app);
    const sections = all.filter(n => n.tag === 'section' && n.attrs.class === 'trust-card').map(n => n.attrs.id);
    assert.deepEqual(sections, ['p-recorded', 'p-not-recorded', 'p-purpose', 'p-who', 'p-kept', 'p-help'], 'six sections, same order');
    const index = all.find(n => n.tag === 'nav' && n.attrs.class === 'p-index');
    assert.deepEqual(nodes(index).filter(n => n.tag === 'button').map(text),
      ['What is recorded', 'What is not recorded', 'Purpose and location', 'Who can see it', "How long it's kept", 'Using it well, and help']);
    const section = id => all.find(n => n.attrs.id === 'p-' + id);
    // Each approved sentence is one whole text child of an element: static text, never markup.
    const leaf = (root, tag, str) => nodes(root).find(n => n.tag === tag && n.children.length === 1 && n.children[0] === str);
    const more = (root, str) => {
      const p = leaf(root, 'p', str); assert.ok(p, 'More text: ' + str);
      const d = nodes(root).find(n => n.tag === 'details' && n.children.includes(p));
      assert.ok(d, 'inside a disclosure: ' + str);
      assert.ok(d.children.some(c => c.tag === 'summary' && text(c) === 'More about this'));
    };
    const rec = section('recorded');
    assert.ok(leaf(rec, 'strong', 'Subscriptions you tell us about'));
    assert.ok(leaf(rec, 'p', "If you record an AI subscription you hold, Swangz AI Hub keeps what you enter: the tool, whether it's personal or a seat on the company plan, who pays, an optional label, and any plan, quota, period end date, price or credit you add. It's your own declaration: nobody checks it with the provider, and it doesn't change which tools you can use."));
    more(rec, "You can end a record but not delete it. Values can't be edited; adding a new one keeps the earlier one in the record's history.");
    const not = section('not-recorded');
    assert.ok(leaf(not, 'p', 'Only your access through Swangz AI Hub is recorded, plus any subscription you choose to record yourself.'));
    assert.ok(!all.some(n => n.children.includes('Only access through Swangz AI Hub is recorded.')), 'old unqualified sentence gone');
    for (const old of [
      "If you record an AI subscription you hold, Swangz AI Hub keeps what you enter: the tool, whether it's personal or a seat on the company plan, and any plan, quota, renewal date or price you add. It's your own declaration. Nobody checks it with the provider, and it doesn't change which tools you can use.",
      "You can end a record but not delete it, and each value you add is kept as you entered it.",
      "Details of a personal subscription are shown only to you in Swangz AI Hub. For a seat on the company plan, administrators who manage tools also see its plan and quota, and those who manage spending see its price and credit. Whenever you add, update or end a subscription record, the audit log notes your name, the change, the time, your network address and a record number. Any administrator can see that entry, but it never includes the tool, plan, price or anything else you entered.",
      "As with every record here, the people who run the Swangz server and its backups can reach the stored data."])
      assert.ok(!all.some(n => n.children.includes(old)), 'superseded copy gone: ' + old.slice(0, 40));
    const who = section('who');
    assert.ok(leaf(who, 'p', 'Swangz AI Hub shows the details of a personal subscription you record only to you. For a seat on the company plan, control-room users who manage tools or spending see its tool, status, dates, holder, payer and label; those who manage tools also see its plan, quota and period end, and those who manage spending see its price and credit. Whenever you add a subscription record, add a value to it or end it, the audit log notes your name, the change, the time, your network address and a record number. Everyone with control-room access, including read-only users, can see that entry. It never includes the tool, plan, price or anything else you entered.'));
    more(who, 'From that entry, control-room users who manage tools or spending can tell whether the change was to a personal subscription or a company seat, but not which tool. As with every record here, the people who run the Swangz server and its backups can reach the stored data.');
    assert.ok(leaf(section('kept'), 'p', 'Subscription records and their values are kept even after you end them. Audit log entries are kept for at least a year.'));
    const page = text(t.app);
    for (const phrase of ['renewal date', 'kept as you entered it', 'add, update or end', 'Any administrator can see that entry', 'kept, even after'])
      assert.ok(!page.includes(phrase), 'page excludes: ' + phrase);
    assert.ok(nodes(section('recorded')).some(n => n.tag === 'svg' && n.attrs.name === 'wallet'), 'wallet icon on the subscriptions item');
    const whoMore = nodes(who).filter(n => n.tag === 'details');
    assert.equal(whoMore.length, 1, 'one disclosure in Who can see it');
    assert.equal(whoMore[0].children.filter(c => c.tag === 'p').length, 1, 'audience More is one paragraph');
    assert.equal(all.filter(n => ['form', 'input', 'textarea', 'select'].includes(n.tag)).length, 0, 'no form or Save control');
    assert.ok(all.every(n => !('innerHTML' in n.attrs)), 'no innerHTML');
    assert.ok(t.calls.every(([, url]) => !url.includes('provider-accounts') && !url.includes('/hub/registry')), 'no registry request');
  });
  console.log(`PASS paused behavior: ${count} checks; no browser/layout/server-authorization coverage claimed`);
  return count;
};
if (require.main === module) module.exports().catch(e => { console.error(e); process.exitCode = 1; });
