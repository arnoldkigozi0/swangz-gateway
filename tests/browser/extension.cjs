/* Dependency-free worker/blocked-page regressions: no ports, browsers or real accounts. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const workerSource = fs.readFileSync(path.join(root, 'extension/background.js'), 'utf8');
const blockedSource = fs.readFileSync(path.join(root, 'extension/blocked.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const hosts = { 'chatgpt.com': 'chatgpt', 'openai.com': 'chatgpt', 'canva.com': 'canva' };
const storedSession = () => ({ base: 'https://hub.example.test', token: 'fixture-token', hosts: clone(hosts),
  policy: 'Access-level only', holding: { chatgpt: 2000000000 } });
const response = (status = 200, data = {}) => ({ status, ok: status >= 200 && status < 300,
  json: async () => clone(data) });
const settle = () => new Promise(resolve => setImmediate(resolve));

async function worker(initial = storedSession(), options = {}) {
  const stored = clone(initial), requests = [], updates = [], clears = [], trace = [], listeners = {};
  let removeData = async () => {}, fetcher, getBarrier = options.getBarrier;
  const event = name => ({ addListener: fn => { listeners[name] = fn; } });
  const chrome = {
    storage: {
      local: {
        get: async keys => { if (getBarrier) await getBarrier; return Object.fromEntries(keys.filter(k => k in stored).map(k => [k, clone(stored[k])])); },
        set: async values => { Object.assign(stored, clone(values)); trace.push(['set', clone(values)]); },
        remove: async keys => { keys = [].concat(keys); trace.push(['remove', keys]); for (const k of keys) delete stored[k]; },
      },
      session: { set: async values => trace.push(['session', clone(values)]),
        remove: async keys => trace.push(['session-remove', [].concat(keys)]) },
    },
    browsingData: { remove: async (filter, data) => {
      clears.push({ filter: clone(filter), data: clone(data) });
      trace.push(['clear-start', clone(stored.holding || {})]);
      await removeData();
      trace.push(['clear-end']);
    } },
    tabs: { update: async (tab, change) => updates.push({ tab, ...change }),
      onUpdated: event('navigate'), onRemoved: event('removed') },
    runtime: { getURL: name => 'chrome-extension://fixture/' + name,
      onInstalled: event('installed'), onStartup: event('startup'), onMessage: event('message') },
    alarms: { create() {}, onAlarm: event('alarm') },
    action: { setBadgeText() {}, setBadgeBackgroundColor() {}, setTitle() {} },
  };
  fetcher = async url => url.endsWith('/turns') ? response(200, {
    holding: Object.entries(stored.holding || {}).map(([tool_id, expires]) => ({ tool_id, expires,
      hosts: Object.keys(stored.hosts || {}).filter(h => stored.hosts[h] === tool_id) })), sign_out: [],
  }) : response(200, { hosts, policy: 'Access-level only' });
  const context = vm.createContext({ chrome, URL, URLSearchParams, console, AbortController,
    setTimeout: options.setTimeout || setTimeout, clearTimeout,
    fetch: async (url, init) => { requests.push({ url, init }); return fetcher(url, init); } });
  vm.runInContext(workerSource, context, { filename: 'extension/background.js' });
  const run = code => vm.runInContext(code, context);
  if (!options.deferReady) { await run('ready'); await settle(); }
  return { stored, requests, updates, clears, trace, listeners, run,
    state: () => JSON.parse(run('JSON.stringify(S)')),
    fetchWith: fn => { fetcher = fn; }, clearWith: fn => { removeData = fn; } };
}

function blocked(w, tab = 7) {
  const update = w.updates.find(u => u.tab === tab);
  assert.ok(update, 'governed tab redirected');
  assert.equal(update.url.split('#')[0], 'chrome-extension://fixture/blocked.html');
  assert.equal(new URLSearchParams(update.url.split('#')[1]).get('signin'), '1');
}

function blockedPage(hash) {
  const nodes = Object.fromEntries(['title', 'reason', 'actions', 'done'].map(id => [id, {
    textContent: '', children: [], append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
  }]));
  const context = vm.createContext({ location: { hash }, URLSearchParams,
    document: { getElementById: id => nodes[id], createElement: tag => ({ tag }) },
    chrome: { runtime: { getURL: file => 'chrome-extension://fixture/' + file } },
    history: { length: 1 }, window: { close() {} },
  });
  vm.runInContext(blockedSource, context, { filename: 'extension/blocked.js' });
  return nodes;
}

test('signed-out restart retains cached sites and blocks a governed subdomain without a request', async () => {
  const stored = storedSession(); delete stored.token;
  const w = await worker(stored);
  await w.run("onNavigate(7, 'https://chat.chatgpt.com/private?content=not-recorded')");
  blocked(w);
  assert.deepEqual(w.state().hosts, hosts);
  assert.deepEqual(w.stored.hosts, hosts);
  assert.equal(w.requests.length, 0);
});

test('navigation waits for cached configuration on a cold worker', async () => {
  let release;
  const getBarrier = new Promise(resolve => { release = resolve; });
  const stored = storedSession(); delete stored.token;
  const w = await worker(stored, { getBarrier, deferReady: true });
  const navigation = w.run("onNavigate(7, 'https://chatgpt.com/')");
  await settle(); assert.equal(w.updates.length, 0);
  release(); await navigation;
  blocked(w);
});

test('a sign-out message during cold start cannot be undone by initial storage loading', async () => {
  let release;
  const getBarrier = new Promise(resolve => { release = resolve; });
  const w = await worker(storedSession(), { getBarrier, deferReady: true });
  const reply = new Promise(resolve => w.listeners.message({ type: 'signout' }, {}, resolve));
  release(); await reply; await settle();
  assert.equal(w.state().token, null);
  assert.equal(w.stored.token, undefined);
  await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
});

for (const status of [401, 403]) {
  test(`${status} on navigation blocks and clears held sites before dropping their state`, async () => {
    const w = await worker();
    w.fetchWith(async () => response(status, { code: status === 403 ? 'person_paused' : 'unauthorized' }));
    w.clearWith(async () => {
      assert.deepEqual(w.state().holding, { chatgpt: 2000000000 });
      assert.deepEqual(w.stored.holding, { chatgpt: 2000000000 });
      assert.equal(w.state().token, null);
    });
    await w.run("onNavigate(7, 'https://chatgpt.com/')");
    blocked(w);
    assert.equal(w.clears.length, 1);
    assert.deepEqual(w.clears[0].filter.origins, ['https://chatgpt.com', 'https://www.chatgpt.com',
      'https://openai.com', 'https://www.openai.com']);
    assert.deepEqual(w.clears[0].data, { cookies: true, localStorage: true, indexedDB: true,
      cacheStorage: true, serviceWorkers: true });
    const cleared = w.trace.findIndex(e => e[0] === 'clear-end');
    const dropped = w.trace.findIndex(e => e[0] === 'remove' && e[1].includes('holding'));
    assert.ok(cleared >= 0 && dropped > cleared);
    assert.equal(w.stored.token, undefined);
    assert.deepEqual(w.state().holding, {});
    assert.deepEqual(w.stored.hosts, hosts);
    const restarted = await worker(w.stored);
    await restarted.run("onNavigate(7, 'https://chatgpt.com/')");
    blocked(restarted);
  });
  for (const operation of ['refreshHosts()', 'syncTurns()', 'clearSharedOnStartup()']) {
    test(`${status} from ${operation} also removes authentication and retains governed sites`, async () => {
      const w = await worker();
      w.fetchWith(async () => response(status, { code: 'person_paused' }));
      await w.run(operation);
      assert.equal(w.state().token, null);
      assert.deepEqual(w.stored.hosts, hosts);
      assert.ok(w.clears.length);
      await w.run("onNavigate(7, 'https://canva.com/')"); blocked(w);
    });
  }
}

test('offline governed navigation is blocked and preserves host cache', async () => {
  const w = await worker();
  w.fetchWith(async () => { throw new TypeError('offline'); });
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  blocked(w);
  assert.deepEqual(w.stored.hosts, hosts);
  assert.deepEqual(w.state().open, {});
  assert.equal(w.state().token, 'fixture-token');
});

test('a stalled gate times out closed', async () => {
  const w = await worker(storedSession(), { setTimeout: fn => { queueMicrotask(fn); return 0; } });
  w.fetchWith(async (url, init) => {
    if (init.signal.aborted) throw new Error('aborted');
    return new Promise((resolve, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  });
  await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
});

for (const state of ['signed out', 'offline', 'refused']) {
  test(`ungoverned sites and domain lookalikes stay untouched while ${state}`, async () => {
    const initial = storedSession(); if (state === 'signed out') delete initial.token;
    const w = await worker(initial);
    w.requests.length = 0;
    w.fetchWith(async () => { throw new Error('must not contact gateway'); });
    for (const url of ['https://example.org/', 'https://chatgpt.com.example.org/', 'https://notchatgpt.com/',
      'file:///chatgpt.com', 'httpx://chatgpt.com/']) await w.run(`onNavigate(7, ${JSON.stringify(url)})`);
    assert.equal(w.requests.length, 0);
    assert.equal(w.updates.length, 0);
    assert.equal(w.clears.length, 0);
  });
}

for (const decision of [response(500), response(200, {}),
  { ok: true, status: 200, json: async () => { throw new Error('bad JSON'); } }]) {
  test('missing, unavailable or invalid allow decision blocks cached governed site', async () => {
    const w = await worker(); w.fetchWith(async () => decision);
    await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
  });
}

test('authenticated known:false refreshes stale governance and allows the site', async () => {
  const w = await worker(); w.requests.length = 0;
  w.fetchWith(async url => response(200, url.endsWith('/open') ? { known: false } : { hosts: { 'canva.com': 'canva' } }));
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  assert.deepEqual(w.requests.map(r => r.url.split('/').pop()), ['open', 'config']);
  assert.equal(w.updates.length, 0);
  assert.deepEqual(w.stored.hosts, { 'canva.com': 'canva' });
});

test('a tab moving from an allowed governed tool to a known:false host ends the first record', async () => {
  const w = await worker(); w.requests.length = 0;
  w.fetchWith(async url => response(200, url.endsWith('/open') ? { known: true, allowed: true, id: 42 } : {}));
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  assert.deepEqual(Object.keys(w.state().open), ['7']);
  w.fetchWith(async url => response(200, url.endsWith('/open') ? { known: false } : url.endsWith('/close') ? {} : { hosts: { 'canva.com': 'canva' } }));
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  const close = w.requests.filter(r => r.url.endsWith('/close'));
  assert.equal(close.length, 1);
  assert.deepEqual(Object.keys(JSON.parse(close[0].init.body)).sort(), ['id', 'seconds']);
  assert.equal(JSON.parse(close[0].init.body).id, 42);
  assert.deepEqual(w.state().open, {});
  assert.equal(w.updates.length, 0);
});

const openAnswers = (w, ids) => w.fetchWith(async (url, init) => {
  const name = url.split('/').pop();
  if (name === 'open') {
    const host = JSON.parse(init.body).host;
    return response(200, ids[host] === 'blocked' ? { known: true, allowed: false, tool: 'X', reason: 'no' }
      : { known: true, allowed: true, id: ids[host].shift() });
  }
  return response(200, {});
});
const calls = w => w.requests.map(r => r.url.split('/').pop() + (r.init.body ? ':' + r.init.body : ''));

test('moving a tab from one governed tool to another closes the first record before asking about the second', async () => {
  const w = await worker(); w.requests.length = 0;
  openAnswers(w, { 'chatgpt.com': [41], 'canva.com': [42] });
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  await w.run("onNavigate(7, 'https://canva.com/design')");
  const c = calls(w);
  assert.equal(c[0], 'open:{"host":"chatgpt.com"}');
  assert.match(c[1], /^close:\{"id":41,"seconds":\d+\}$/);
  assert.equal(c[2], 'open:{"host":"canva.com"}');
  assert.equal(c.length, 3);
  assert.equal(w.state().open[7].id, 42);
});

test('the first record ends even if the second tool then cannot be checked', async () => {
  const w = await worker();
  openAnswers(w, { 'chatgpt.com': [41] });
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  w.fetchWith(async url => { if (url.endsWith('/close')) return response(200, {}); throw new TypeError('offline'); });
  await w.run("onNavigate(7, 'https://canva.com/')");
  assert.ok(w.requests.some(r => r.url.endsWith('/close') && JSON.parse(r.init.body).id === 41));
  assert.deepEqual(w.state().open, {});
  blocked(w);
});

test('a new address on the same tool keeps the running record and leaves no duplicate open', async () => {
  const w = await worker(); w.requests.length = 0;
  openAnswers(w, { 'chatgpt.com': [41, 43], 'openai.com': [44] });
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  await w.run("onNavigate(7, 'https://chatgpt.com/c/abc')");
  await w.run("onNavigate(7, 'https://openai.com/')");  // another host of the same tool
  assert.equal(w.state().open[7].id, 41);
  const closes = w.requests.filter(r => r.url.endsWith('/close')).map(r => JSON.parse(r.init.body));
  assert.deepEqual(closes, [{ id: 43, seconds: 0 }, { id: 44, seconds: 0 }]);  // the extra server records, not the running one
  assert.equal(w.updates.length, 0);
});

test('a refusal on the same or another tool ends the record the tab had running', async () => {
  for (const next of ['https://chatgpt.com/private', 'https://canva.com/']) {
    const w = await worker();
    openAnswers(w, { 'chatgpt.com': [41, 'blocked'], 'canva.com': 'blocked' });
    await w.run("onNavigate(7, 'https://chatgpt.com/')");
    openAnswers(w, { 'chatgpt.com': 'blocked', 'canva.com': 'blocked' });
    w.requests.length = 0;
    await w.run(`onNavigate(7, '${next}')`);
    assert.ok(w.requests.some(r => r.url.endsWith('/close') && JSON.parse(r.init.body).id === 41), next);
    assert.deepEqual(w.state().open, {}, next);
    assert.ok(w.updates.length >= 1, next);
  }
});

test('ending a record also removes its open_<tab> entry from session storage', async () => {
  const w = await worker();
  openAnswers(w, { 'chatgpt.com': [41] });
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  assert.ok(w.trace.some(t => t[0] === 'session' && 'open_7' in t[1]));
  await w.run('endTab(7)');
  assert.deepEqual(w.trace.filter(t => t[0] === 'session-remove'), [['session-remove', ['open_7']]]);
  await w.run('endTab(7)');  // nothing running: nothing more to remove or send
  assert.equal(w.trace.filter(t => t[0] === 'session-remove').length, 1);
});

test('401 during a known:false config refresh still blocks and signs out', async () => {
  const w = await worker();
  w.fetchWith(async url => url.endsWith('/open') ? response(200, { known: false }) : response(401));
  await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
  assert.equal(w.state().token, null);
});

test('successful config refresh can remove a site from governance', async () => {
  const w = await worker();
  w.fetchWith(async () => response(200, { hosts: { 'canva.com': 'canva' } }));
  await w.run('refreshHosts()'); w.requests.length = 0;
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  assert.equal(w.updates.length, 0); assert.equal(w.requests.length, 0);
});

test('offline or malformed config never erases cached sites', async () => {
  const w = await worker();
  w.fetchWith(async () => { throw new TypeError('offline'); });
  await w.run('refreshHosts()');
  assert.deepEqual(w.stored.hosts, hosts);
  w.fetchWith(async () => response(200, { hosts: null }));
  await w.run('refreshHosts()');
  assert.deepEqual(w.stored.hosts, hosts);
});

test('explicit allow records only host and access duration; sign-out retains base, hosts and policy', async () => {
  const w = await worker(); w.requests.length = 0;
  w.fetchWith(async url => response(200, url.endsWith('/open') ? { known: true, allowed: true, id: 42 } : {}));
  await w.run("onNavigate(7, 'https://chatgpt.com/private?prompt=never-read')");
  assert.equal(w.updates.length, 0);
  assert.deepEqual(JSON.parse(w.requests[0].init.body), { host: 'chatgpt.com' });
  await w.run('endTab(7)');
  assert.deepEqual(Object.keys(JSON.parse(w.requests[1].init.body)).sort(), ['id', 'seconds']);
  await w.run('signOut()');
  assert.deepEqual(w.state().hosts, hosts);
  assert.equal(w.state().base, 'https://hub.example.test');
  assert.equal(w.stored.policy, 'Access-level only');
  assert.deepEqual(w.state().open, {});
});

test('failed shared-site cleanup keeps held state for a signed-out retry', async () => {
  const w = await worker();
  w.fetchWith(async () => response(401));
  w.clearWith(async () => { throw new Error('browser refused'); });
  await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
  assert.equal(w.state().token, null);
  assert.deepEqual(w.stored.holding, { chatgpt: 2000000000 });
  w.clearWith(async () => {});
  await w.run('syncTurns()');
  assert.equal(w.stored.holding, undefined);
});

test('normal turn loss clears held sites before persisting the new holding list', async () => {
  const w = await worker();
  w.fetchWith(async () => response(200, { holding: [], sign_out: [] }));
  w.clearWith(async () => assert.deepEqual(w.state().holding, { chatgpt: 2000000000 }));
  await w.run('syncTurns()');
  assert.equal(w.clears.length, 1);
  assert.deepEqual(w.stored.holding, {});
});

test('signed-out startup clears cached held-site data', async () => {
  const initial = storedSession(); delete initial.token;
  const w = await worker(initial);
  await w.run('clearSharedOnStartup()');
  assert.equal(w.clears.length, 1);
  assert.equal(w.stored.holding, undefined);
});

test('a late allow cannot reopen access after sign-out', async () => {
  const w = await worker(); let complete;
  // the stalled request is the gate's; sign-out's own call to the Hub is answered so it is not mistaken for it
  w.fetchWith(url => url.endsWith('/api/logout') ? response(200, { ok: true }) : new Promise(resolve => { complete = resolve; }));
  const navigating = w.run("onNavigate(7, 'https://chatgpt.com/')");
  await settle(); await w.run('signOut()');
  complete(response(200, { known: true, allowed: true, id: 99 }));
  await navigating; blocked(w);
  assert.deepEqual(w.state().open, {});
});

test('sign-out ends the extension session at the Hub with the old bearer, after the local token is gone', async () => {
  const w = await worker(); let storedAtCall, memoryAtCall;
  w.fetchWith(async url => {
    if (url.endsWith('/api/logout')) { storedAtCall = w.stored.token; memoryAtCall = w.state().token; }
    return response(200, { ok: true });
  });
  await w.run('signOut()'); await settle();
  const calls = w.requests.filter(r => r.url === 'https://hub.example.test/api/logout');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers.authorization, 'Bearer fixture-token');
  assert.equal(calls[0].init.headers['x-swangz-app'], '1');
  assert.equal(calls[0].init.credentials, 'omit');
  assert.equal(storedAtCall, undefined, 'the stored token is removed before the Hub is told');
  assert.equal(memoryAtCall, null);
  await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
  assert.equal(w.requests.filter(r => r.url.endsWith('/api/logout')).length, 1, 'signed out already: nothing to end twice');
});

for (const [name, hub] of [['unreachable', async () => { throw new Error('offline'); }], ['hung', () => new Promise(() => {})],
  ['refusing', async () => response(500)]]) {
  test(`sign-out stays signed out and blocked when the Hub is ${name}`, async () => {
    const w = await worker();
    w.fetchWith(hub);
    await w.run('signOut()'); await settle();
    assert.equal(w.state().token, null);
    assert.equal(w.stored.token, undefined);
    assert.equal(w.clears.length, 1, 'held shared sites are still cleared');
    w.fetchWith(async () => response(200, { known: true, allowed: true, id: 5 }));
    await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
    assert.deepEqual(w.state().open, {});
  });
}

for (const status of [401, 403]) {
  test(`a ${status} from the gate is a block: sign-in page, no open record, and the dead session is ended at the Hub`, async () => {
    const w = await worker();
    w.fetchWith(async url => url.endsWith('/api/logout') ? response(200, { ok: true }) : response(status));
    await w.run("onNavigate(7, 'https://chatgpt.com/')"); await settle();
    blocked(w);
    assert.deepEqual(w.state().open, {});
    const calls = w.requests.filter(r => r.url.endsWith('/api/logout'));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].init.headers.authorization, 'Bearer fixture-token');
  });
}

test('a late refusal for an old token cannot sign out a replacement token', async () => {
  const w = await worker(); let complete;
  w.fetchWith(() => new Promise(resolve => { complete = resolve; }));
  const navigating = w.run("onNavigate(7, 'https://chatgpt.com/')");
  await settle(); w.run("S.token = 'replacement-fixture-token'");
  complete(response(401)); await navigating;
  assert.equal(w.state().token, 'replacement-fixture-token');
});

test('a late JSON allow cannot reopen access after sign-out', async () => {
  const w = await worker(); let complete;
  w.fetchWith(async () => ({ status: 200, ok: true,
    json: () => new Promise(resolve => { complete = resolve; }) }));
  const navigating = w.run("onNavigate(7, 'https://chatgpt.com/')");
  await settle(); await w.run('signOut()');
  complete({ known: true, allowed: true, id: 99 });
  await navigating; blocked(w);
  assert.deepEqual(w.state().open, {});
});

test('a stalled JSON body times out closed', async () => {
  const w = await worker(storedSession(), { setTimeout: fn => { setImmediate(fn); return 0; } });
  w.fetchWith(async (url, init) => ({ status: 200, ok: true,
    json: () => new Promise((resolve, reject) => {
      if (init.signal.aborted) reject(new Error('aborted'));
      else init.signal.addEventListener('abort', () => reject(new Error('aborted')));
    }) }));
  await w.run("onNavigate(7, 'https://chatgpt.com/')"); blocked(w);
});

test('Chrome navigation listener blocks offline governed sites', async () => {
  const w = await worker(); w.fetchWith(async () => { throw new Error('offline'); });
  w.listeners.navigate(7, { status: 'loading', url: 'https://chatgpt.com/' }, {});
  await settle(); blocked(w);
});

test('blocked page offers extension sign-in without an access-request action', () => {
  const page = blockedPage('#signin=1&tool_id=chatgpt&app=https%3A%2F%2Fhub.example.test');
  assert.equal(page.title.textContent, 'Sign in to Swangz AI Hub');
  assert.ok(page.reason.textContent.includes('offline'));
  assert.equal(page.actions.children[0].textContent, 'Sign in to Swangz AI Hub');
  assert.equal(page.actions.children[0].href, 'chrome-extension://fixture/popup.html');
  assert.ok(!page.actions.children.some(n => n.textContent === 'Request access'));
});

test('ordinary access refusal and weekly-report actions remain available', async () => {
  const w = await worker();
  w.fetchWith(async () => response(200, { known: true, allowed: false, tool: 'ChatGPT',
    tool_id: 'chatgpt', reason: 'Complete the report', app_url: 'https://hub.example.test', report_gate: { report_id: 9 } }));
  await w.run("onNavigate(7, 'https://chatgpt.com/')");
  const hash = new URL(w.updates[0].url).hash;
  const page = blockedPage(hash);
  assert.equal(page.title.textContent, "ChatGPT isn't enabled for you");
  assert.equal(page.actions.children[0].textContent, 'Complete weekly report');
  assert.equal(page.actions.children[0].href, 'https://hub.example.test/#/weekly?report=9');
});
