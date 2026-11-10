/* Port-free check of the staff Updates list copy, using the shipped portal-hub.js with stubs.
   A notice says "Emailed" only when the email was sent; internal delivery states are never shown. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const text = n => (n == null || n === false ? '' : typeof n === 'object' ? n.text : String(n));
const el = (tag, attrs, ...kids) => ({ tag, attrs: attrs || {}, text: kids.flat(Infinity).map(text).join('') });
const items = ['not_configured', 'pending', 'failed', 'sent'].map((email_state, i) => ({ id: i + 1, title: 'Report returned ' + email_state, href: '#/weekly', created: 0, read: 0, email_state }));
const SWP = { api: async () => ({ items }), page() {} };
const sandbox = { SWP, HubUI: {}, SUI: { el, icon: () => '', fmt: { ago: () => '2h ago' }, toast() {} }, URLSearchParams, location: { hash: '#/requests' } };
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../gateway/static/portal-hub.js'), 'utf8'), sandbox);
(async () => {
  const list = await SWP.hubNotes();
  for (const state of ['not_configured', 'pending', 'failed']) {
    assert.ok(list.text.includes('Report returned ' + state + ' · 2h ago'), state + ' notice is listed');
    assert.ok(!list.text.includes('Report returned ' + state + ' · 2h ago ·'), state + ' notice shows nothing about email');
  }
  assert.ok(list.text.includes('Report returned sent · 2h ago · Emailed'), 'a sent notice says Emailed');
  assert.ok(!/email (not_configured|pending|failed|sent)/.test(list.text), 'no raw delivery state: ' + list.text);
  console.log('updates-copy: OK');
})().catch(e => { console.error(e); process.exitCode = 1; });
