/* Port-free behavioral regressions for the actual portal dispatcher and read-only views.
   Minimal element objects exercise state and events; real browser layout is verified separately. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../gateway/static/portal.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const paused = { paused_view: true, name: 'Sam <script>', status: 'paused', reason: 'Talk to your admin.', support_contact: 'help@swangzavenue.com' };
const active = { name: 'Ada', email: 'ada@swangzavenue.com', active: true, catalog: [], keys: [], privacy: {}, hub_unread: 0 };
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const report = { id: 7, tool_name: '<img src=x onerror=alert(1)>', kind: 'weekly', state: 'returned',
  week_start: '2026-10-26', version: 1, currency: 'USD', reason: '<script>do not execute</script>', impact: 'Staff estimate' };
function element(tag, attrs, ...children) {
  const changed = (node, kind) => { while (node) { if (node.observeMutation) node.observeMutation(kind); node = node.parent; } };
  const n = { tag, attrs: attrs || {}, children: [], disabled: false, style: {},
    append(...xs) { for (const x of xs.flat(Infinity).filter(x => x != null)) { if (typeof x === 'object') x.parent = this; this.children.push(x); } changed(this, 'append'); },
    prepend(...xs) { const old = this.children.slice(); this.replaceChildren(...xs, ...old); },
    replaceChildren(...xs) {
      for (const child of this.children) if (typeof child === 'object') child.parent = null;
      this.children = [];
      for (const x of xs.flat(Infinity).filter(x => x != null)) { if (typeof x === 'object') x.parent = this; this.children.push(x); }
      changed(this, 'replaceChildren');
    },
    replaceWith() {}, focus() {},
    setAttribute(k, v) { this.attrs[k] = v; changed(this, 'attribute'); },
    removeAttribute(k) { delete this.attrs[k]; changed(this, 'attribute'); },
    remove() { this.removed = true; if (this.parent) { const p = this.parent; p.children = p.children.filter(c => c !== this); this.parent = null; changed(p, 'remove'); } },
    querySelectorAll(selector) { return nodes(this).slice(1).filter(child => matches(child, selector)); },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }, addEventListener() {}, removeEventListener() {} };
  Object.defineProperty(n, 'parent', { value: null, writable: true });
  Object.defineProperty(n, 'isConnected', { get() { let root = this; while (root.parent) root = root.parent; return root.tag === 'app' || root.tag === 'body'; } });
  Object.defineProperty(n, 'className', { get() { return this.attrs.class || ''; }, set(value) { this.attrs.class = value; } });
  if (tag === 'dialog') {
    n.showModal = () => { n.open = true; n.attrs.open = true; };
    n.close = () => { n.open = false; delete n.attrs.open; };
  }
  Object.defineProperty(n, 'textContent', { get() { return text(this); }, set(value) { this.replaceChildren(String(value)); } });
  const classes = () => new Set((n.attrs.class || '').split(/\s+/).filter(Boolean));
  n.classList = { contains: c => classes().has(c),
    add(c) { n.attrs.class = [...classes().add(c)].join(' '); changed(n, 'attribute'); },
    remove(c) { const cs = classes(); cs.delete(c); n.attrs.class = [...cs].join(' '); changed(n, 'attribute'); },
    toggle(c, on) { if (on === undefined) on = !classes().has(c); this[on ? 'add' : 'remove'](c); } };
  n.dataset = Object.fromEntries(Object.entries(n.attrs).filter(([k]) => k.startsWith('data-')).map(([k, v]) => [k.slice(5), v]));
  n.append(...children);
  return n;
}
const nodes = n => typeof n === 'object' ? [n, ...n.children.flatMap(nodes)] : [];
const text = n => typeof n === 'object' ? n.children.map(text).join(' ') : String(n);
function matches(n, selector) {
  if (selector.startsWith('.')) return (n.attrs.class || '').split(/\s+/).includes(selector.slice(1));
  if (selector === '[role=tab]') return n.attrs.role === 'tab';
  if (selector === 'dialog') return n.tag === 'dialog';
  return selector === 'dialog[open]' && n.tag === 'dialog' && n.attrs.open;
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

async function boot({ hash = '#/', search = '', me = paused, request, sui = {}, storageThrows = false, studio = null } = {}) {
  const app = element('app'), calls = [], listeners = {}, keys = [], replacements = [], pushes = [], overlays = [];
  const body = element('body', null, app), documentElement = element('html');
  const navigations = [], toasts = [], removed = [], store = new Map([['swangz-studio-purpose', 'marketing'], ['swangz-theme', 'light']]);
  // Track only mutations to the attached #app subtree; detached async handlers remain observable separately.
  const mutations = [];
  const dialogs = [];
  Object.defineProperty(app, 'observeMutation', { value: kind => mutations.push({ kind, text: text(app), children: app.children.length }) });
  let guardCalls = 0;
  const c = { URLSearchParams, setTimeout: () => {}, clearTimeout: () => {},
    location: { hash, search, pathname: '/', replace(url) {
      assert.equal(c.SWP.S.me, null); assert.equal(c.SWP.S.studio, null);
      assert.equal(app.children.length, 0, 'attached app cleared before navigation');
      assert.equal(documentElement.style.display, 'none', 'document hidden before navigation');
      assert.deepEqual(removed, ['swangz-studio-purpose']);
      navigations.push(url);
    } },
    localStorage: { getItem: key => store.get(key) || null, setItem: (key, value) => store.set(key, value),
      removeItem(key) { removed.push(key); if (storageThrows) throw Error('Storage unavailable'); store.delete(key); } },
    history: {
      replaceState(_a, _b, url) { replacements.push(url); c.location.hash = url.slice(url.indexOf('#')); c.location.search = ''; },
      pushState(_a, _b, url) { pushes.push(url); c.location.hash = url; } },
    document: { body, documentElement, getElementById: id => id === 'app' ? app : nodes(body).find(n => n.attrs.id === id),
      querySelectorAll: selector => [...new Set([...overlays, ...nodes(body).slice(1)])].filter(n => !n.removed && selector.split(',').some(s => matches(n, s.trim()))), querySelector: () => null,
      createElement: tag => element(tag), createElementNS: (_ns, tag) => element(tag), createTextNode: value => String(value), dispatchEvent() {},
      addEventListener: (type, fn, capture) => { if (type === 'keydown') keys.push({ fn, capture }); }, removeEventListener() {}, activeElement: null },
    SUI: { ICONS: {}, el: (...args) => {
      const n = element(...args); if (n.tag === 'dialog') dialogs.push(n); n.focus = () => { c.document.activeElement = n; }; return n;
    }, icon: name => element('svg', { name }), fmt: { stamp: x => String(x) },
      themeButton: () => element('button', { 'aria-label': 'Theme' }), setGatewayOffset() {},
      avatar: name => element('span', { class: 'avatar' }, name), toast: (...args) => toasts.push(args), ...sui },
    HubUI: { guard() { guardCalls++; return true; } },
    fetch: async (url, opts = {}) => {
      const method = opts.method || 'GET'; calls.push([method, url]);
      const custom = request && await request(url, method);
      if (custom) return custom;
      if (url === '/api/me') return response(me);
      if (url === '/api/studio') return response(studio);
      if (url === '/api/hub/reports?limit=30&offset=0') return response({ items: [report], total: 1 });
      if (url === '/api/hub/reports/7') return response(report);
      if (url === '/api/hub/notifications') return response({ items: [{ title: '<b>Update</b>', href: 'javascript:alert(1)', created: 123 }] });
      if (url === '/auth/options') return response({ google: false });
      throw Error('Unexpected request: ' + method + ' ' + url);
    }, addEventListener: (type, fn) => { listeners[type] = fn; }, removeEventListener() {}, requestAnimationFrame: () => {}, scrollTo() {},
    CustomEvent: class { constructor(type, props) { this.type = type; this.detail = props.detail; } },
    Node: class { static [Symbol.hasInstance](node) { return !!node && typeof node === 'object' && 'tag' in node; } } };
  c.window = c;
  vm.runInNewContext(source, c, { filename: 'gateway/static/portal.js' });
  await flush();
  return { c, app, body, dialogs, calls, overlays, replacements, pushes, navigations, toasts, removed, store, mutations, get guardCalls() { return guardCalls; },
    script(name) { vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../gateway/static', name), 'utf8'), c, { filename: name }); },
    async navigate(hash) { c.location.hash = hash; await listeners.hashchange(); await flush(); },
    key(key, mods = {}) {
      const e = { key, ...mods, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
      for (const listener of [...keys.filter(x => x.capture), ...keys.filter(x => !x.capture)]) { listener.fn(e); if (e.stopped) break; }
      return e;
    } };
}

function signOutButton(t) {
  const button = nodes(t.app).find(n => n.tag === 'button' && text(n).trim() === 'Sign out');
  assert.ok(button, 'actual rendered Sign out button');
  return button;
}
const clickSignOut = t => signOutButton(t).attrs.onclick();
const logoutOptions = (me, extra = {}) => ({ me, hash: me.paused_view ? '#/paused/updates' : '#/privacy', ...extra });
function assertSignedOut(t) {
  assert.equal(t.c.SWP.S.me, null); assert.equal(t.c.SWP.S.studio, null);
  assert.equal(t.app.children.length, 0); assert.equal(text(t.app), '');
  assert.equal(t.c.document.documentElement.style.display, 'none');
  assert.deepEqual(t.navigations, ['/']); assert.deepEqual(t.toasts, []);
  assert.deepEqual(t.calls.filter(([method, url]) => method === 'POST'), [['POST', '/api/logout']]);
  assert.deepEqual(t.removed, ['swangz-studio-purpose']); assert.equal(t.store.get('swangz-theme'), 'light');
}
async function withoutUnhandled(fn) {
  const errors = [], collect = error => errors.push(error);
  process.on('unhandledRejection', collect);
  try { await fn(); await flush(); assert.deepEqual(errors, [], 'no unhandled rejection'); }
  finally { process.removeListener('unhandledRejection', collect); }
}

module.exports = async function run() {
  let count = 0;
  async function check(name, fn) {
    let timer;
    try {
      await Promise.race([fn(), new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Timed out: ' + name)), 10000); })]);
    } finally { clearTimeout(timer); }
    count++; console.log('PASS paused: ' + name);
  }
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
    const settled = Promise.allSettled([a, b]);
    await flush(); assert.equal(meCalls, 2);
    refreshed.resolve(response(paused));
    const result = await settled;
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
  for (const [identity, me] of [['active', active], ['suspended', paused], ['ended', { ...paused, status: 'access_ended', name: 'Ended person' }]]) {
    await check(identity + ' button success clears state and purpose before exactly one clean-page navigation', async () => {
      const t = await boot(logoutOptions(me, { request: url => url === '/api/logout' ? response({ ok: true }) : undefined }));
      if (!me.paused_view) t.c.SWP.S.studio = { private: 'old Studio' };
      const before = t.mutations.length;
      await clickSignOut(t);
      assertSignedOut(t); assert.equal(t.store.has('swangz-studio-purpose'), false);
      assert.deepEqual(t.mutations.slice(before), [{ kind: 'replaceChildren', text: '', children: 0 }], 'one terminal app clear');
    });
    for (const [failure, result] of [
      ['rejected fetch', () => { throw Error('Offline'); }],
      ['503', () => response({ error: 'Unavailable' }, 503)],
      ['500', () => response({ error: 'Failed' }, 500)],
      ['unreadable 200', () => ({ ok: true, status: 200, json: async () => { throw Error('Unreadable body'); } })],
      ['unreadable 500', () => ({ ok: false, status: 500, json: async () => { throw Error('Unreadable body'); } })],
    ]) {
      await check(identity + ' button failure (' + failure + ') retains identity, purpose and view and permits retry', async () => {
        let fail = true;
        const t = await boot(logoutOptions(me, { request: url => url === '/api/logout' ? (fail ? result() : response({ ok: true })) : undefined }));
        const beforeMe = t.c.SWP.S.me, beforeStudio = t.c.SWP.S.studio, dom = JSON.stringify(t.app), hash = t.c.location.hash;
        await clickSignOut(t);
        assert.equal(t.c.SWP.S.me, beforeMe); assert.equal(t.c.SWP.S.studio, beforeStudio);
        assert.equal(JSON.stringify(t.app), dom); assert.equal(t.c.location.hash, hash);
        assert.equal(t.store.get('swangz-studio-purpose'), 'marketing'); assert.deepEqual(t.removed, []);
        assert.deepEqual(t.navigations, []); assert.deepEqual(t.toasts, [["Couldn't sign out. Try again.", true]]);
        fail = false; await clickSignOut(t);
        assert.deepEqual(t.navigations, ['/']); assert.equal(t.c.SWP.S.me, null);
        assert.equal(t.calls.filter(([, url]) => url === '/api/logout').length, 2);
      });
    }
    await check(identity + ' button success navigates even when purpose removal throws', async () => {
      const t = await boot(logoutOptions(me, { storageThrows: true, request: url => url === '/api/logout' ? response({ ok: true }) : undefined }));
      await clickSignOut(t); assertSignedOut(t);
    });
    await check(identity + ' double click shares a pending logout and never navigates or errors twice', async () => {
      const held = deferred();
      const t = await boot(logoutOptions(me, { request: url => url === '/api/logout' ? held.promise : undefined }));
      const button = signOutButton(t);
      const first = button.attrs.onclick(), second = button.attrs.onclick();
      await flush(); assert.equal(t.calls.filter(([, url]) => url === '/api/logout').length, 1);
      held.resolve(response({ ok: true })); await Promise.all([first, second]);
      await button.attrs.onclick(); assertSignedOut(t);
    });
  }
  for (const via of ['refreshPaused', 'load paused /me']) {
    await check('held logout 200 remains authoritative with ' + (via === 'refreshPaused' ? 'automatic pause refresh suppressed' : 'load /me generation change'), async () => {
      const held = deferred(); let meCalls = 0;
      const t = await boot(logoutOptions(active, { request: url => {
        if (url === '/api/me') return response(++meCalls === 1 ? active : paused);
        if (url === '/api/logout') return held.promise;
        if (url === '/api/pause-trigger') return response({ code: 'person_paused', error: 'Paused' }, 403);
      } }));
      const logout = clickSignOut(t); await flush();
      if (via === 'refreshPaused') await assert.rejects(t.c.SWP.api('GET', '/pause-trigger'), e => e.code === 'person_paused');
      else await t.c.SWP.load();
      assert.equal(t.c.SWP.S.me, via === 'refreshPaused' ? active : paused);
      assert.equal(meCalls, via === 'refreshPaused' ? 1 : 2, 'pending logout suppresses automatic pause refresh only');
      held.resolve(response({ ok: true })); await logout; assertSignedOut(t);
    });
  }
  for (const [failure, result] of [
    ['rejected fetch', () => { throw Error('Offline'); }],
    ['503', () => response({ error: 'Unavailable' }, 503)],
    ['500', () => response({ error: 'Failed' }, 500)],
    ['unreadable 200', () => ({ ok: true, status: 200, json: async () => { throw Error('Unreadable body'); } })],
  ]) {
    await check('generation change cannot turn held logout failure (' + failure + ') into success', async () => {
      const held = deferred(); let meCalls = 0;
      const t = await boot(logoutOptions(active, { request: async url => {
        if (url === '/api/me') return response(++meCalls === 1 ? active : paused);
        if (url === '/api/logout') { await held.promise; return result(); }
      } }));
      const logout = clickSignOut(t); await flush(); await t.c.SWP.load();
      const dom = JSON.stringify(t.app);
      held.resolve(); await logout;
      assert.equal(t.c.SWP.S.me, paused); assert.equal(JSON.stringify(t.app), dom);
      assert.deepEqual(t.navigations, []); assert.deepEqual(t.removed, []);
      assert.equal(t.store.get('swangz-studio-purpose'), 'marketing');
      assert.deepEqual(t.toasts, [["Couldn't sign out. Try again.", true]]);
    });
  }
  for (const late of ['me', 'studio', 'reports', 'notifications']) {
    await check('late ' + late + ' response after logout cannot mutate state, DOM, focus or history', async () => {
      const held = deferred(); let armed = false;
      const url = { me: '/api/me', studio: '/api/studio', reports: '/api/hub/reports?limit=30&offset=0', notifications: '/api/hub/notifications' }[late];
      const me = late === 'me' || late === 'studio' ? active : paused;
      const t = await boot(logoutOptions(me, { request: path => {
        if (armed && path === url) return held.promise;
        if (path === '/api/logout') return response({ ok: true });
      } }));
      armed = true;
      const pending = late === 'me' || late === 'studio' ? t.c.SWP.load()
        : t.navigate(late === 'reports' ? '#/paused/reports' : '#/paused/updates');
      await flush(); await clickSignOut(t); assertSignedOut(t);
      const dom = JSON.stringify(t.app), focus = t.c.document.activeElement, calls = t.calls.length;
      const history = JSON.stringify([t.replacements, t.pushes]);
      held.resolve(response(late === 'me' ? { ...active, name: 'OLD PERSON' } : late === 'studio' ? { private: 'OLD PERSON' }
        : { items: [{ ...report, title: 'OLD PERSON' }], total: 1 }));
      await pending; await flush();
      assertSignedOut(t); assert.equal(t.calls.length, calls, 'no retry or follow-up request');
      assert.equal(JSON.stringify(t.app), dom); assert.equal(t.c.document.activeElement, focus);
      assert.equal(JSON.stringify([t.replacements, t.pushes]), history);
    });
  }
  for (const [method, path] of [['GET', '/old'], ['GET', '/logout'], ['POST', '/logout/'], ['POST', '/logout?x=1']]) {
    await check(method + ' ' + path + ' retains stale-generation refusal across logout', async () => {
      const held = deferred();
      const t = await boot(logoutOptions(active, { request: (url, requestedMethod) => {
        if (url === '/api' + path && requestedMethod === method) return held.promise;
        if (url === '/api/logout') return response({ ok: true });
      } }));
      const pending = t.c.SWP.api(method, path);
      const refused = assert.rejects(pending, e => e.code === 'person_paused');
      await flush(); await clickSignOut(t);
      held.resolve(response({ private: 'OLD PERSON' })); await refused;
      assert.deepEqual(t.navigations, ['/']); assert.deepEqual(t.toasts, []);
    });
  }
  await check('paused nonlogout writes and logout path near-misses remain blocked before fetch', async () => {
    const t = await boot(), before = t.calls.length;
    for (const path of ['/hub/reports/7/submit', '/logout/', '/logout?x=1'])
      await assert.rejects(t.c.SWP.api('POST', path, {}), e => e.code === 'person_paused');
    assert.equal(t.calls.length, before);
  });
  for (const [identity, me] of [['active', active], ['suspended', paused]]) {
    for (const read of ['reports', 'notifications']) {
      await check(identity + ' late 403 person_paused from ' + read + ' cannot refresh, fetch or mutate the cleared app', async () => {
        const held = deferred(); let armed = false;
        const url = read === 'reports' ? '/api/hub/reports?limit=30&offset=0' : '/api/hub/notifications';
        const t = await boot(logoutOptions(me, { request: path => {
          if (armed && path === url) return held.promise;
          if (path === '/api/logout') return response({ ok: true });
        } }));
        armed = true;
        const pending = me.paused_view ? t.navigate(read === 'reports' ? '#/paused/reports' : '#/paused/updates')
          : assert.rejects(t.c.SWP.api('GET', url.slice(4)), e => e.code === 'person_paused');
        await flush(); await clickSignOut(t); assertSignedOut(t);
        const calls = t.calls.length, mutations = t.mutations.length;
        held.resolve(response({ code: 'person_paused', error: 'Paused' }, 403));
        await pending; await flush(); assertSignedOut(t);
        assert.equal(t.calls.length, calls, 'no identity refresh or follow-up fetch');
        assert.equal(t.mutations.length, mutations, 'no attached subtree mutation after clear');
      });
    }
  }
  const studio = { image: true, purposes: [], recent: [] };
  for (const endpoint of ['POST /studio/generate', 'GET /studio in load']) {
    for (const order of [['studio', 'logout'], ['logout', 'studio']]) {
      await check(endpoint + ' and logout resolve in one task (' + order.join(' then ') + ') without resurrection', () => withoutUnhandled(async () => {
        const heldStudio = deferred(), heldLogout = deferred(); let armed = false;
        const target = endpoint.startsWith('POST') ? '/api/studio/generate' : '/api/studio';
        const t = await boot({ hash: '#/studio?view=create', me: active, studio,
          sui: { fmt: { stamp: x => String(x), ago: () => 'Just now' } }, request: url => {
            if (url === '/api/logout') return heldLogout.promise;
            if (armed && url === target) return heldStudio.promise;
          } });
        assert.match(text(t.app), /Studio/);
        armed = true;
        const form = nodes(t.app).find(n => n.tag === 'form' && n.attrs.class === 'studio-form');
        assert.ok(form, 'actual Studio form');
        nodes(form).find(n => n.tag === 'textarea').value = 'OLD PERSON PROMPT';
        const pending = endpoint.startsWith('POST') ? form.attrs.onsubmit({ preventDefault() {}, currentTarget: form }) : t.c.SWP.load();
        await flush(); const logout = clickSignOut(t); await flush();
        const made = { id: 99, type: 'image', outcome: 'ok', urls: ['https://fixture.invalid/old-person.png'], prompt: 'OLD PERSON', ts: 123 };
        // No await between resolves: both response orders run in the same JavaScript task.
        for (const name of order) {
          if (name === 'studio') heldStudio.resolve(response(endpoint.startsWith('POST') ? made : studio));
          else heldLogout.resolve(response({ ok: true }));
        }
        await Promise.all([pending, logout]); await flush();
        assert.equal(t.c.SWP.S.me, null); assert.equal(t.c.SWP.S.studio, null);
        assert.equal(text(t.app), ''); assert.equal(t.app.children.length, 0);
        assert.deepEqual(t.navigations, ['/']); assert.deepEqual(t.toasts, []);
        const clear = t.mutations.findLastIndex(m => m.children === 0);
        assert.ok(clear >= 0); assert.equal(clear, t.mutations.length - 1, 'no attached mutation after terminal clear');
        assert.equal(t.calls.filter(([method, url]) => method === 'POST' && url === '/api/logout').length, 1);
        const calls = t.calls.length;
        await form.attrs.onsubmit({ preventDefault() {}, currentTarget: form });
        assert.equal(t.calls.length, calls, 'leftover form handler cannot fetch');
        assert.equal(t.mutations.length, clear + 1, 'leftover handler writes detached nodes only');
      }));
    }
  }
  for (const [identity, me] of [['active', active], ['suspended', paused]]) {
    await check(identity + ' terminal API, dispatchers and leftover buttons cannot fetch or reattach old content', async () => {
      const t = await boot(logoutOptions(me, { hash: me.paused_view ? '#/paused/reports' : '#/privacy', request: url => {
        if (url.includes('/api/hub/reports?')) return response({ error: 'Unavailable' }, 503);
        if (url === '/api/logout') return response({ ok: true });
      } }));
      const button = signOutButton(t);
      const retry = nodes(t.app).find(n => n.tag === 'button' && text(n) === 'Try again');
      await button.attrs.onclick(); assertSignedOut(t);
      const calls = t.calls.length, mutations = t.mutations.length;
      for (const [method, path] of [['GET', '/me'], ['GET', '/hub/notifications'], ['POST', '/studio/generate'], ['POST', '/logout']])
        await assert.rejects(t.c.SWP.api(method, path), e => e.code === 'signed_out');
      await button.attrs.onclick(); if (retry) await retry.attrs.onclick();
      await t.c.SWP.load(); await t.c.SWP.render();
      await assert.doesNotReject(async () => t.c.SWP.frame('Old identity', element('p', null, 'OLD PERSON')));
      await t.navigate('#/paused/reports'); await t.navigate('#/welcome/old-invite'); await t.navigate('#/tools');
      assertSignedOut(t); assert.equal(t.calls.length, calls); assert.equal(t.mutations.length, mutations);
    });
  }
  for (const status of [200, 401, 503]) {
    await check('late welcome response ' + status + ' cannot invoke either signed-out gate writer', () => withoutUnhandled(async () => {
      const held = deferred();
      const t = await boot(logoutOptions(active, { request: url => {
        if (url === '/api/welcome/held') return held.promise;
        if (url === '/api/logout') return response({ ok: true });
      } }));
      const button = signOutButton(t);
      await t.navigate('#/welcome/held'); await button.attrs.onclick(); assertSignedOut(t);
      const mutations = t.mutations.length, calls = t.calls.length;
      held.resolve(response({ name: 'OLD PERSON', email: 'old@swangzavenue.com', error: 'Old response' }, status));
      await flush(); await flush(); assertSignedOut(t);
      assert.equal(t.mutations.length, mutations); assert.equal(t.calls.length, calls);
    }));
  }
  for (const [identity, me] of [['active', active], ['suspended', paused]]) {
    for (const read of ['reports', 'notifications']) {
      await check(identity + ' logout 200 with held JSON suppresses prior ' + read + ' pause error before terminal cleanup', async () => {
        const old = deferred(), logoutBody = deferred(); let armed = false;
        const url = read === 'reports' ? '/api/hub/reports?limit=30&offset=0' : '/api/hub/notifications';
        const t = await boot(logoutOptions(me, { request: path => {
          if (armed && path === url) return old.promise;
          if (path === '/api/logout') return { ok: true, status: 200, json: () => logoutBody.promise };
        } }));
        armed = true;
        const pending = assert.rejects(t.c.SWP.api('GET', url.slice(4)), e => e.code === 'person_paused');
        const logout = clickSignOut(t); await flush();
        const calls = t.calls.length, writes = t.mutations.length, beforeMe = t.c.SWP.S.me;
        old.resolve(response({ code: 'person_paused', error: 'Paused' }, 403)); await pending; await flush();
        assert.equal(t.c.SWP.S.me, beforeMe); assert.equal(t.calls.length, calls, 'no /me refresh during held logout body');
        assert.equal(t.mutations.length, writes); assert.deepEqual(t.navigations, []);
        assert.equal(t.c.document.documentElement.style.display, undefined);
        logoutBody.resolve({ ok: true }); await logout; assertSignedOut(t);
      });
    }
    await check(identity + ' held logout 503 resets pending guard and later pause refusals behave normally', async () => {
      const old = deferred(), logoutBody = deferred(); let armed = false, meCalls = 0, later = false;
      const t = await boot(logoutOptions(me, { request: path => {
        if (path === '/api/me') return response(++meCalls === 1 ? me : paused);
        if (armed && path === '/api/hub/reports?limit=30&offset=0') return later ? response({ code: 'person_paused', error: 'Paused' }, 403) : old.promise;
        if (path === '/api/logout') return { ok: false, status: 503, json: () => logoutBody.promise };
      } }));
      armed = true;
      const pending = assert.rejects(t.c.SWP.api('GET', '/hub/reports?limit=30&offset=0'), e => e.code === 'person_paused');
      const logout = clickSignOut(t); await flush();
      const writes = t.mutations.length, beforeMe = t.c.SWP.S.me;
      old.resolve(response({ code: 'person_paused', error: 'Paused' }, 403)); await pending;
      assert.equal(meCalls, 1); assert.equal(t.mutations.length, writes);
      logoutBody.resolve({ error: 'Unavailable' }); await logout;
      assert.equal(t.c.SWP.S.me, beforeMe); assert.equal(t.c.document.documentElement.style.display, undefined);
      assert.deepEqual(t.navigations, []); assert.equal(t.store.get('swangz-studio-purpose'), 'marketing');
      assert.deepEqual(t.toasts, [["Couldn't sign out. Try again.", true]]);
      later = true;
      await assert.rejects(t.c.SWP.api('GET', '/hub/reports?limit=30&offset=0'), e => e.code === 'person_paused');
      assert.equal(meCalls, me.paused_view ? 1 : 2, 'active refusal can refresh after failed logout');
      assert.equal(t.c.SWP.S.me, paused);
    });
  }
  await check('actual business project consumer, body toast and portal dialog stay hidden and network-blocked after logout', () => withoutUnhandled(async () => {
    const consumer = deferred(); let accepted = false;
    const project = { report_id: 7, position: 0, name: 'OLD PRIVATE PROJECT', description: 'OLD PRIVATE DESCRIPTION', tool_name: 'Fixture', department: 'QA', state: 'submitted' };
    const data = { projects: [project], company: { drive_folder: '' } };
    const t = await boot(logoutOptions(active, { request: path => {
      if (path.startsWith('/api/hub/business?')) return response(data);
      if (path === '/api/logout') return response({ ok: true });
    } }));
    const policy = nodes(t.app).find(n => n.tag === 'button' && text(n) === 'Read the usage policy');
    assert.ok(policy); policy.attrs.onclick();
    assert.equal(t.c.document.querySelectorAll('dialog[open]').length, 1, 'actual portal dialog opens before logout');
    const existingDialog = t.dialogs.at(-1);
    // Load complete unchanged source scripts. Only the native DOM APIs are fixture objects.
    t.script('ui.js'); t.script('hub-ui.js');
    const actualUI = t.c.SUI;
    actualUI.toast('PREEXISTING PRIVATE TOAST');
    const register = t.c.SWP.page, api = t.c.SWP.api, pages = [];
    t.c.SWP.page = (rx, fn) => { pages.push([rx, fn]); register(rx, fn); };
    // Force the accepted API-result/consumer gap while retaining the actual API wrapper and route consumer.
    t.c.SWP.api = async (...args) => { const value = await api(...args); accepted = true; await consumer.promise; return value; };
    t.script('business-ui.js'); t.c.SWP.api = api; t.c.SWP.page = register;
    const projects = pages.find(([rx]) => rx.test('#/projects'))[1];
    const pending = projects(new URLSearchParams('project=7:0')); await flush(); assert.ok(accepted);
    const oldSheet = actualUI.el('aside', { class: 'hub-side-sheet' }, 'PREEXISTING PRIVATE SHEET');
    const oldScrim = actualUI.el('div', { class: 'hub-sheet-scrim' });
    t.body.append(oldSheet, oldScrim);
    assert.equal(t.c.document.querySelectorAll('.toast').length, 1);
    await clickSignOut(t); assertSignedOut(t);
    assert.equal(existingDialog.isConnected, false); assert.equal(oldSheet.isConnected, false); assert.equal(oldScrim.isConnected, false);
    assert.equal(t.c.document.querySelectorAll('dialog, .hub-side-sheet, .hub-sheet-scrim, .toast').length, 0, 'all preexisting overlays removed');
    const calls = t.calls.length;
    consumer.resolve(); await pending; await flush();
    const sheets = t.c.document.querySelectorAll('.hub-side-sheet');
    assert.equal(sheets.length, 1, 'actual late projectDetail/staffSheet body attachment exercised');
    assert.match(text(sheets[0]), /OLD PRIVATE PROJECT/);
    actualUI.toast('LATE PRIVATE TOAST');
    assert.equal(t.c.document.querySelectorAll('.toast').length, 1, 'actual body-level toast exercised');
    assert.doesNotThrow(() => policy.attrs.onclick());
    const lateDialog = t.dialogs.at(-1);
    assert.notEqual(lateDialog, existingDialog); assert.equal(lateDialog.parent, null); assert.ok(!lateDialog.open);
    assert.doesNotThrow(() => lateDialog.close(), 'detached unopened dialog retains native close contract');
    assert.equal(t.c.document.querySelectorAll('dialog[open]').length, 0);
    assert.equal(t.c.document.documentElement.style.display, 'none'); assert.equal(t.calls.length, calls);
    await assert.rejects(api('GET', '/me'), e => e.code === 'signed_out'); assert.equal(t.calls.length, calls);
    assertSignedOut(t);
  }));
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
    more(who, "From that entry, control-room users who manage tools or spending can tell whether the change was to a personal subscription or a company seat; for a personal subscription, they still can't see which tool. As with every record here, the people who run the Swangz server and its backups can reach the stored data.");
    assert.ok(leaf(section('kept'), 'p', 'Subscription records and their values are kept even after you end them. Audit log entries are kept for at least a year.'));
    const page = text(t.app);
    for (const phrase of ['renewal date', 'kept as you entered it', 'add, update or end', 'Any administrator can see that entry', 'kept, even after', 'but not which tool'])
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
