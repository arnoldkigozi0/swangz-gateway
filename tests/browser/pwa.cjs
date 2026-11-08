"use strict";
// Staff web app install/update/logout contract, without a browser: `node tests/browser/pwa.cjs`.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.join(__dirname, "..", "..", "gateway", "static");
const read = (name) => fs.readFileSync(path.join(STATIC, name), "utf8");

// A tiny DOM: elements with classes and children, and the selectors hub-install.js uses.
function makeDom() {
  const all = new Set();
  const node = (classes, parent) => {
    const n = { classes: new Set(classes), children: [], parent: null, attrs: {}, onclick: null,
      classList: { contains: (c) => n.classes.has(c) },
      append(c) { c.parent = n; n.children.push(c); all.add(c); mutate(); },
      prepend(c) { c.parent = n; n.children.unshift(c); all.add(c); mutate(); },
      remove() { if (!n.parent) return; n.parent.children = n.parent.children.filter((x) => x !== n); detach(n); n.parent = null; mutate(); } };
    if (parent) { n.parent = parent; parent.children.push(n); }
    all.add(n);
    return n;
  };
  const detach = (n) => { all.delete(n); n.children.forEach(detach); };
  const has = (n, c) => n.classes.has(c);
  const within = (n, c) => { for (let p = n.parent; p; p = p.parent) if (has(p, c)) return true; return false; };
  const match = (n, sel) => {
    const parts = sel.trim().split(/\s+/);
    const last = parts.pop();
    const [tag, cls] = last.startsWith(".") ? [null, last.slice(1)] : [last, null];
    if (cls && !has(n, cls)) return false;
    if (tag && n.tag !== tag) return false;
    return parts.every((p) => within(n, p.slice(1)));
  };
  const observers = [];
  let mutating = false;
  const mutate = () => { if (mutating) return; mutating = true; try { observers.slice().forEach((o) => o.live && o.fn()); } finally { mutating = false; } };
  const body = node(["body"]);
  const document = { body, querySelector: (sel) => {
    const attached = [];
    const walk = (n) => { attached.push(n); n.children.forEach(walk); };
    walk(body);
    for (const s of sel.split(",")) for (const n of attached) if (match(n, s)) return n;
    return null;
  } };
  class MutationObserver { constructor(fn) { this.fn = fn; this.live = false; observers.push(this); } observe() { this.live = true; } disconnect() { this.live = false; } }
  return { node, body, document, MutationObserver, observers };
}

function load(dom, { secure = true } = {}) {
  const listeners = {};
  const registered = [];
  const SUI = { el: (tag, attrs, text) => { const b = dom.node((attrs.class || "").split(" ")); b.tag = tag; b.attrs = attrs; b.text = text; b.onclick = attrs.onclick; return b; } };
  const ctx = { SUI, document: dom.document, MutationObserver: dom.MutationObserver, isSecureContext: secure,
    navigator: { serviceWorker: { register: (u) => { registered.push(u); return Promise.resolve(); } } },
    addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); } };
  vm.runInNewContext(read("hub-install.js"), ctx);
  const fire = (t, e = {}) => (listeners[t] || []).forEach((fn) => fn(e));
  return { fire, registered };
}

const promptEvent = (outcome) => { const e = { prevented: false, prompted: 0, preventDefault() { this.prevented = true; },
  prompt() { this.prompted++; return Promise.resolve(); }, userChoice: Promise.resolve({ outcome }) }; return e; };
const installButtons = (dom) => dom.document.querySelector(".hub-install-action");

test("worker is registered only in a secure context", () => {
  assert.deepEqual(load(makeDom()).registered, ["/hub-worker.js"]);
  assert.deepEqual(load(makeDom(), { secure: false }).registered, []);
});

test("install offer appears once the app renders, even when the event fires first", () => {
  const dom = makeDom();
  const { fire } = load(dom);
  const e = promptEvent("dismissed");
  fire("beforeinstallprompt", e);
  assert.equal(e.prevented, true);
  assert.equal(installButtons(dom), null, "nothing to attach to yet");
  // /me answers and the sign-in screen renders.
  const form = dom.node(["form"]); form.tag = "form";
  const gate = dom.node(["gate-form"], dom.body); gate.append(form);
  const b = installButtons(dom);
  assert.ok(b, "placed on the sign-in form");
  assert.equal(b.parent, form);
  assert.equal(b.text, "Install app");
  assert.match(b.attrs["aria-label"], /^Install app/, "accessible name contains the visible label");
});

test("install offer follows sign-in into the top bar, ahead of the bell", () => {
  const dom = makeDom();
  const { fire } = load(dom);
  fire("beforeinstallprompt", promptEvent("dismissed"));
  const gate = dom.node(["gate-form"], dom.body); const form = dom.node(["form"]); form.tag = "form"; gate.append(form);
  assert.equal(installButtons(dom).parent, form);
  gate.remove();  // signed in: the app replaces the sign-in screen
  const bar = dom.node(["topbar"], dom.body); const inner = dom.node(["inner"], bar);
  const right = dom.node(["top-right"]); right.append(dom.node(["icon-btn"])); inner.append(right);
  const b = installButtons(dom);
  assert.ok(b);
  assert.equal(b.parent, right);
  assert.equal(right.children[0], b);
});

test("the console gets no install offer (its manifest would install the staff app)", () => {
  const dom = makeDom();
  const { fire } = load(dom);
  fire("beforeinstallprompt", promptEvent("dismissed"));
  dom.node(["signin-card"], dom.body);
  dom.node(["top-actions"], dom.node(["top"], dom.body));
  assert.equal(installButtons(dom), null);
});

test("accepting installs once and removes the offer for good", async () => {
  const dom = makeDom();
  const { fire } = load(dom);
  const e = promptEvent("accepted");
  fire("beforeinstallprompt", e);
  const right = dom.node(["top-right"]); dom.node(["inner"], dom.node(["topbar"], dom.body)).append(right);
  await installButtons(dom).onclick();
  assert.equal(e.prompted, 1);
  assert.equal(installButtons(dom), null);
  right.append(dom.node(["x"]));  // later re-renders do not bring it back
  assert.equal(installButtons(dom), null);
  assert.ok(dom.observers.every((o) => !o.live), "observer disconnected");
});

test("appinstalled from the browser menu removes the offer", () => {
  const dom = makeDom();
  const { fire } = load(dom);
  fire("beforeinstallprompt", promptEvent("dismissed"));
  dom.node(["inner"], dom.node(["topbar"], dom.body)).append(dom.node(["top-right"]));
  assert.ok(installButtons(dom));
  fire("appinstalled");
  assert.equal(installButtons(dom), null);
});

test("worker never intercepts or caches: updates and sign-out always use the network", () => {
  const src = read("hub-worker.js").replace(/\/\/.*$|\/\*[\s\S]*?\*\//gm, "");
  assert.doesNotMatch(src, /addEventListener\(\s*['"]fetch['"]/);
  assert.doesNotMatch(src, /caches\.|indexedDB/);
  assert.match(src, /skipWaiting\(\)/);
  assert.match(src, /clients\.claim\(\)/);
});

test("manifest is installable standalone from /", () => {
  const m = JSON.parse(read("hub.webmanifest"));
  for (const k of ["id", "name", "short_name", "start_url", "scope", "display", "icons"]) assert.ok(m[k], k);
  assert.equal(m.start_url, "/");
  assert.equal(m.scope, "/");
  assert.equal(m.display, "standalone");
  for (const i of m.icons) assert.ok(fs.existsSync(path.join(STATIC, i.src.replace(/^\/static\//, ""))), i.src);
  assert.ok(read("index.html").includes('<link rel="manifest" href="/static/hub.webmanifest">'));
});

test("staff sign-out reloads to a clean page after the server ends the session", () => {
  const src = read("portal.js");
  const body = src.slice(src.indexOf("async function signOut()"), src.indexOf("// ------------------------------------------------------------------ start"));
  assert.match(body, /api\("POST", "\/logout"\)/);
  assert.ok(body.indexOf('"/logout"') < body.indexOf('location.replace("/")'), "logout before reload");
});
