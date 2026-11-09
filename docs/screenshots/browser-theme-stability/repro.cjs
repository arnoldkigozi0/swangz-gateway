/* Invoked by tests/browser/check.cjs in the existing CI browser job, using its actual settle/layout helpers.
   Controlled negative cases avoid relying on a natural race or on product-specific colours.
   No product DOM, axe rule or animation is changed by the helper under test. No additional browser/server is started. */
const assert = require('node:assert/strict');

module.exports = async function themeStability({ browser, settle, layout, AxeBuilder }) {
  const checks = [];
  const check = (name, value) => { assert.ok(value, name); checks.push(name); };
  const context = await browser.newContext({ viewport: { width: 800, height: 600 } });
  try {
    const page = await context.newPage();
    await page.setContent('<!doctype html><html lang="en"><head><title>Theme settling regression</title></head><body><main><h1>Theme settling</h1><div id="fixture"><button id="sample">Contrast sample</button><span id="pulse" aria-hidden="true">*</span></div></main></body></html>');
    await page.evaluate(() => {
      const button = document.querySelector('#sample');
      button.style.backgroundColor = '#fff';
      button.style.color = '#111';
      // Exactly 1:1 ink is reported as incomplete by axe; use visible low-contrast ink for the negative control.
      window.themeFinite = button.animate([{ color: '#aaa' }, { color: '#111' }], { duration: 200, fill: 'forwards' });
      window.themeFinite.pause();
      window.themeFinite.currentTime = 0;
      window.themePulse = document.querySelector('#pulse').animate([{ opacity: 1 }, { opacity: .5 }], { duration: 2000, iterations: Infinity });
    });
    const axe = selector => new AxeBuilder({ page }).include(selector).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    check('mid-transition contrast defect is detected', (await axe('#fixture')).violations.some(v => v.id === 'color-contrast'));
    await page.evaluate(() => window.themeFinite.play());
    await settle(page);
    check('settled fixture passes unchanged axe rules', (await axe('#fixture')).violations.length === 0);
    const state = await page.evaluate(() => ({ finite: window.themeFinite.playState, infinite: window.themePulse.playState, colour: getComputedStyle(document.querySelector('#sample')).color }));
    check('finite animation finishes naturally', state.finite === 'finished' && state.colour === 'rgb(17, 17, 17)');
    check('endless animation remains running', state.infinite === 'running');

    await page.evaluate(() => {
      const bad = document.createElement('button');
      bad.id = 'persistent'; bad.textContent = 'Persistent contrast defect';
      bad.style.color = '#aaa'; bad.style.backgroundColor = '#fff';
      document.querySelector('#fixture').append(bad);
    });
    await settle(page);
    check('persistent contrast defect survives settling', (await axe('#persistent')).violations.some(v => v.id === 'color-contrast'));
    await page.evaluate(() => { document.querySelector('#fixture').style.width = '2000px'; });
    await assert.rejects(() => layout(page, 'persistent overflow negative control'), /horizontal overflow/);
    checks.push('persistent layout defect still fails the actual layout assertion');

    await page.evaluate(() => {
      window.themeStalled = document.querySelector('#sample').animate([{ opacity: 1 }, { opacity: .5 }], { duration: 200 });
      window.themeStalled.pause();
      window.themeStalled.currentTime = 0;
    });
    await assert.rejects(() => settle(page), /Timed out waiting for finite animations/);
    check('stalled finite animation fails without being cancelled or advanced', await page.evaluate(() => window.themeStalled.playState === 'paused' && window.themeStalled.currentTime === 0));
    console.log('PASS', checks.length, 'animation/axe regression checks');
    return { checks };
  } finally { await context.close(); }
};
