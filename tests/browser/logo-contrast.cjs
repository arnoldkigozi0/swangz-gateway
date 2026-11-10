/* Port-free check of the tile behind a tool's initials (ui.js logoTint): white initials must reach 4.5:1 on the
   lightest part of the tile for every catalogue colour and for arbitrary admin-chosen colours. No browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const ui = fs.readFileSync(path.join(root, 'gateway/static/ui.js'), 'utf8');
const src = ui.match(/const LOGO_INK[\s\S]*?\n  function logoTint[\s\S]*?\n  }\n/);
assert.ok(src, 'logoTint found in ui.js');
assert.ok(ui.includes('const c = logoTint(t.color);'), 'logo() uses logoTint for its tile');
const logoTint = vm.runInNewContext(src[0] + '; logoTint');
const lum = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(x => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
  .reduce((s, x, i) => s + x * [0.2126, 0.7152, 0.0722][i], 0);
const white = hex => 1.05 / (lum(hex) + 0.05);
const catalogue = [...new Set(fs.readFileSync(path.join(root, 'gateway/catalog.py'), 'utf8').match(/#[0-9A-Fa-f]{6}/g))];
assert.ok(catalogue.length >= 30, 'catalogue colours read');
const sweep = []; for (let r = 0; r < 256; r += 51) for (let g = 0; g < 256; g += 51) for (let b = 0; b < 256; b += 51) sweep.push('#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join(''));
let changed = 0;
for (const c of [...catalogue, ...sweep]) {
  const t = logoTint(c);
  assert.match(t, /^#[0-9a-fA-F]{6}$/, c);
  assert.ok(white(t) >= 4.5, `${c} -> ${t} white ${white(t).toFixed(2)}:1`);
  if (white(c) >= 4.5) assert.equal(t, c, c + ' already passes and is unchanged'); else { changed += 1; assert.ok(white(t) < 5.2, `${c} -> ${t} darkened no more than needed`); }
}
assert.ok(changed > 0, 'some colours needed darkening');
for (const bad of ['', null, undefined, 'red', '#fff', 'url(x)']) assert.equal(logoTint(bad), '#3F3F46');
console.log(`logo-contrast: ${catalogue.length} catalogue + ${sweep.length} swept colours OK (${changed} darkened)`);
