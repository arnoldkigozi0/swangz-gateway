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
    let lens = null, settling = null, pointerNavigation = null;
    const under = x => [...bar.querySelectorAll("a")].find(a => { const r = a.getBoundingClientRect(); return x >= r.left && x <= r.right; });
    const place = x => { const r = bar.getBoundingClientRect(); lens.style.transform = `translate(${Math.max(0, Math.min(r.width, x - r.left))}px, 0)`; };
    const end = () => {
      const old = lens; lens = null;
      if (settling) { settling.cancel(); settling = null; }
      if (old) old.remove();
    };
    bar.addEventListener("pointerdown", e => {
      if (e.button) return;
      pointerNavigation = null;
      end();
      lens = el("i", { class: "stb-lens", "aria-hidden": "true" }); bar.append(lens); place(e.clientX);
      try { bar.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
    });
    bar.addEventListener("pointermove", e => { if (lens && !settling) place(e.clientX); });
    bar.addEventListener("pointerup", e => {
      if (!lens || settling) return;
      const target = under(e.clientX);
      if (!target) { end(); return; }
      pointerNavigation = { target, at: performance.now() };
      const released = lens, from = location.hash;
      const navigate = () => {
        if (lens !== released) return; // A new gesture or keyboard action cancelled this release.
        end();
        if (bar.isConnected && location.hash === from) location.hash = target.getAttribute("href");
      };
      if (!lens.animate || (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches)) { navigate(); return; }
      const links = [...bar.querySelectorAll("a")], active = bar.querySelector("a.on");
      const item = target.getBoundingClientRect(), selected = active ? active.getBoundingClientRect() : item;
      const bounds = bar.getBoundingClientRect(), glass = lens.getBoundingClientRect();
      // The old wide pill collapses when an item to its right becomes active.
      const shift = active && links.indexOf(active) < links.indexOf(target) ? selected.width - item.width : 0;
      const centre = item.left - bounds.left - shift + selected.width / 2;
      try {
        settling = lens.animate([
          { transform: lens.style.transform, opacity: 1 },
          { transform: `translate(${centre}px, 0) scale(${selected.width / glass.width}, ${item.height / glass.height})`, opacity: 0 }
        ], { duration: 200, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards" }); // Six reference frames at 30 fps.
        settling.finished.then(navigate, navigate);
      } catch (err) {
        navigate(); // Navigation remains available without Web Animations support.
      }
    });
    bar.addEventListener("pointercancel", end);
    bar.addEventListener("keydown", end);
    // Suppress the native pointer click while release navigation settles.
    bar.addEventListener("click", e => {
      if (e.detail && pointerNavigation && e.target.closest("a") === pointerNavigation.target && performance.now() - pointerNavigation.at < 500) e.preventDefault();
      if (!e.detail) end();
      pointerNavigation = null;
    });
  }

  SUI.phoneLens = phoneLens;
})();
