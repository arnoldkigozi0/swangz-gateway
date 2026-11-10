/* Port-free behavior checks using the shipped ui.js + portal.js and a minimal DOM.
   This is not a browser/layout/accessibility substitute. No network or credentials. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let document;
class Element {
  constructor(tag = '') { this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.events = {}; this.dataset = {}; this.value = ''; this.style = { setProperty() {} }; }
  get className() { return this.attributes.class || ''; }
  set className(v) { this.attributes.class = v; }
  get classList() {
    const n = this;
    return { contains: x => n.className.split(/\s+/).includes(x), add: x => { if (!n.classList.contains(x)) n.className += ' ' + x; },
      remove: x => { n.className = n.className.split(/\s+/).filter(c => c !== x).join(' '); },
      toggle: (x, on) => { on ??= !n.classList.contains(x); n.classList[on ? 'add' : 'remove'](x); return on; } };
  }
  setAttribute(k,v) { this.attributes[k] = String(v); if (k === 'id') this.id = v; if (k === 'hidden') this.hidden = true; }
  getAttribute(k) { return this.attributes[k] ?? null; }
  removeAttribute(k) { delete this.attributes[k]; }
  append(...nodes) { for (let n of nodes) { if (!(n instanceof Element)) n = text(n); n.parentElement = this; this.children.push(n); } }
  replaceChildren(...nodes) { this.children.forEach(n => { n.parentElement = null; }); this.children = []; this.append(...nodes); }
  get textContent() { return this._text || this.children.map(n => n.textContent).join(''); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get previousElementSibling() { const a = this.parentElement?.children || []; return a[a.indexOf(this)-1]; }
  addEventListener(type,fn,capture = false) { (this.events[type] ||= []).push({ fn, capture: capture === true }); }
  removeEventListener(type,fn) { this.events[type] = (this.events[type] || []).filter(x => x.fn !== fn); }
  contains(n) { return n === this || this.children.some(c => c.contains(n)); }
  matches(selector) {
    if (selector.startsWith('.')) return selector.slice(1).split('.').every(x => this.classList.contains(x));
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    const attr = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
    if (attr) return this.getAttribute(attr[1]) !== null && (attr[2] === undefined || this.getAttribute(attr[1]) === attr[2]);
    return this.tagName === selector.toUpperCase();
  }
  querySelectorAll(selector) { const choices = selector.split(',').map(x => x.trim()); return this.children.flatMap(n => [...(choices.some(s => n.matches(s)) ? [n] : []), ...n.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  focus() { const prev = document.activeElement; document.activeElement = this; let p = prev; while (p) { for (const { fn } of p.events.focusout || []) fn({ target: prev, relatedTarget: this }); p = p.parentElement; } }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(n => n !== this); this.parentElement = null; }
  showModal() { this.setAttribute('open',''); }
  close() { this.removeAttribute('open'); emit(this,'close'); }
}
function text(v) { const n = new Element(); n.textContent = v; return n; }
function emit(target,type,props = {}) {
  const e = { target, key: '', preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }, ...props };
  const chain = []; for (let p = target; p; p = p.parentElement) chain.push(p);
  for (const n of [...chain].reverse()) { for (const {fn,capture} of n.events[type] || []) if (capture) fn(e); }
  for (const n of chain) { for (const {fn,capture} of n.events[type] || []) if (!capture) fn(e); if (e.stopped) break; }
  return e;
}
document = new Element('document'); document.documentElement = new Element('html'); document.body = new Element('body');
document.append(document.documentElement); document.documentElement.append(document.body);
document.createElement = document.createElementNS = (...args) => new Element(args.at(-1));
document.createTextNode = text; document.getElementById = id => document.querySelector('#'+id);
document.dispatchEvent = () => {};
const app = new Element('div'); app.setAttribute('id','app'); document.body.append(app);
const context = vm.createContext({ Node: Element, document, location: { hash: '#/', search: '', pathname: '/' }, history: { replaceState() {}, pushState() {} },
  localStorage: { getItem() {}, setItem() {} }, CustomEvent: class {}, URLSearchParams, Date, Intl, console,
  fetch: () => new Promise(() => {}), setTimeout: fn => { fn(); return 0; }, clearTimeout() {}, requestAnimationFrame: fn => fn(), addEventListener() {}, scrollTo() {} });
context.window = context;
const root = path.resolve(__dirname,'../..');
for (const file of ['ui.js','portal.js']) vm.runInContext(fs.readFileSync(path.join(root,'gateway/static',file),'utf8'),context,{filename:file});
const P = context.SWP;
P.S.me = { name: 'Grace <script>', email: 'grace@example.test', active: true, catalog: [], keys: [], hub_unread: 3 };
P.S.studio = { image: true };
let checks = 0;
function check(label,ok) { assert.ok(ok,label); checks++; }
P.frame('Home',document.createElement('section'));
const rail = document.querySelector('.staff-rail-pages');
check('Nine staff destinations when Studio is available',rail.querySelectorAll('a').length === 9);
check('Every rail icon has a name and no visible words',rail.querySelectorAll('a').every(a => a.getAttribute('aria-label') && !a.textContent));
check('Exactly one active page',rail.querySelectorAll('[aria-current="page"]').length === 1);
const links = rail.querySelectorAll('a,button'); links[0].focus();
emit(links[0],'keydown',{key:'End'}); check('End focuses All pages',document.activeElement === links.at(-1));
emit(links.at(-1),'keydown',{key:'ArrowDown'}); check('ArrowDown wraps rail focus',document.activeElement === links[0]);
const account = document.querySelector('.staff-account');
emit(account,'keydown',{key:'ArrowUp'});
check('ArrowUp opens account on last item',document.activeElement.textContent.includes('Sign out') && account.getAttribute('aria-expanded') === 'true');
emit(document.activeElement,'keydown',{key:'Home'}); check('Home focuses Profile',document.activeElement.textContent.includes('Profile'));
emit(document.activeElement,'keydown',{key:'Escape'}); check('Escape restores trigger and state',document.activeElement === account && account.getAttribute('aria-expanded') === 'false');
emit(account,'click');
const menu = document.querySelector('.staff-pop.open');
const theme = menu.querySelectorAll('[role="menuitem"]').find(n => n.textContent.includes('Change theme'));
emit(theme,'click'); check('Theme primitive switches and keeps visible copy',document.documentElement.dataset.theme === 'light' && theme.textContent === 'Change theme');
check('Account name stays literal untrusted text',menu.textContent.includes('Grace <script>'));
emit(document.querySelector('.staff-all'),'click');
let drawer = document.querySelector('.drawer'); const input = drawer.querySelector('input');
check('All pages retains all ten routes',drawer.querySelector('nav').querySelectorAll('a').length === 10);
input.value = 'weekly'; emit(input,'input');
let shown = drawer.querySelector('nav').querySelectorAll('a').filter(a => !a.hidden);
check('Navigation search filters to Weekly reports',shown.length === 1 && shown[0].getAttribute('href') === '#/weekly');
input.value = 'does-not-exist'; emit(input,'input');
check('Search has an explicit empty state',drawer.querySelector('[role="status"]').textContent.includes('No pages match'));
emit(document,'keydown',{key:'Escape'});
check('Escape closes All pages',!document.querySelector('.drawer'));
emit(document,'keydown',{key:'k',ctrlKey:true}); check('Ctrl+K opens search',!!document.querySelector('.drawer'));
emit(document,'keydown',{key:'Escape'});
P.S.studio = null; P.frame('My tools',document.createElement('section'));
check('Unavailable Studio leaves the rail',document.querySelector('.staff-rail-pages').querySelectorAll('a').length === 8);
check('Shell does not invent staff emergency mutation controls',!document.querySelector('.staff-exact').textContent.includes('Stop all AI'));
P.S.me = null; app.replaceChildren();
emit(document,'keydown',{key:'k',ctrlKey:true}); check('Signed-out Ctrl+K does not open navigation',!document.querySelector('.drawer'));
console.log(JSON.stringify({ checks, result: 'PASS', coverage: 'Synthetic DOM behavior only; no rendered layout, contrast, browser or screen-reader claim.' },null,2));
