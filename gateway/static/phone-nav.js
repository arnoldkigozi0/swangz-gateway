"use strict";
/* Shared bar C pointer decoration, from the staff component (#70). */
(() => {
  const { el } = SUI;
  function phoneLens(bar) {
    if (!bar.addEventListener) return;
    bar.addEventListener("keydown", e => {
      const links = [...bar.querySelectorAll("a")], at = links.indexOf(document.activeElement);
      if (at < 0) return;
      const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (step) { e.preventDefault(); links[(at + step + links.length) % links.length].focus(); }
    });
    if ( (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
    let lens = null;
    const under = x => [...bar.querySelectorAll("a")].find(a => { const r = a.getBoundingClientRect(); return x >= r.left && x <= r.right; });
    const place = x => { const r = bar.getBoundingClientRect(); lens.style.transform = `translate(${Math.max(0, Math.min(r.width, x - r.left))}px, 0)`; };
    const end = () => { if (lens) { lens.remove(); lens = null; } };
    bar.addEventListener("pointerdown", e => {
      if (e.button) return;
      end();
      lens = el("i", { class: "stb-lens", "aria-hidden": "true" }); bar.append(lens); place(e.clientX);
      try { bar.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
    });
    bar.addEventListener("pointermove", e => { if (lens) place(e.clientX); });
    bar.addEventListener("pointerup", e => {
      if (!lens) return;
      const target = under(e.clientX); end();
      if (target) location.hash = target.getAttribute("href");
    });
    bar.addEventListener("pointercancel", end);
    // The pointer handler has already navigated; a click on a link would do it twice.
    bar.addEventListener("click", e => { if (e.detail) e.preventDefault(); });
  }

  SUI.phoneLens = phoneLens;
})();
