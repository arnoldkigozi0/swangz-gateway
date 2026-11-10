/* The staff footer, BRIEF 6 and 10.3: one milky glass panel that fills like liquid when it scrolls into
   view, a nested link card, the real gateway health, the "Ask for a tool" pill (the existing access-request
   dialog, nothing new on the server), an Evening / Daylight switch and the cut-out "Swangz" wordmark.
   The panel's glass is one SVG rectangle with the word masked out of it, so the letters are real holes
   onto the room behind: no second copy of the photo, nothing to line up, nothing repainted on scroll.
   portal.js calls SWFooter.build() from the signed-in frame; the paused view and sign-in never do. */
(() => {
  "use strict";
  const { el, icon } = SUI;
  const NS = "http://www.w3.org/2000/svg";
  const svg = (tag, attrs, ...kids) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
    n.append(...kids);
    return n;
  };
  const WORDS = { checking: "Checking the gateway", up: "Gateway running", db: "Gateway up, database not responding", down: "Gateway not answering" };
  let health = null, current = null, serial = 0;

  /* "up" = healthy; "db" = the gateway answered but says its database does not; "down" = no usable answer. */
  function gatewayHealth(gurl, set) {
    if (health && Date.now() - health.at < 60000) return set(health.state);
    fetch(gurl("/healthz"), { cache: "no-store" })
      .then(r => r.json().then(j => (r.ok && j && j.ok ? "up" : j && j.ok === false ? "db" : "down"), () => "down"))
      .catch(() => "down")
      .then(state => { health = { state, at: Date.now() }; set(state); });
  }

  function askForTool(me, requestAccess) {
    const open = ((me && me.catalog) || []).filter(t => t.state !== "enabled" && t.state !== "suspended" && !t.pending);
    if (!(me && me.active && open.length && requestAccess)) {
      return [el("a", { class: "xf-ask xf-ask-link", href: "#/requests?view=access" }, el("span", null, "See your access requests"), el("b", null, "Open")),
        el("p", { class: "xf-note" }, "Your tools and requests are on the Requests page.")];
    }
    const quiet = "An admin sees your request. Nothing is turned on until they agree.";
    const list = "xf-tools-" + serial;
    const input = el("input", { type: "text", list, autocomplete: "off", placeholder: "Name a tool, e.g. " + open[0].name, "aria-label": "Ask for a tool: type its name" });
    const note = el("p", { class: "xf-note", role: "status" }, quiet);
    const send = e => {
      e.preventDefault();
      const typed = input.value.trim(), q = typed.toLowerCase();
      if (!q) { note.textContent = "Type the name of a tool you do not have yet."; return; }
      const t = open.find(x => x.name.toLowerCase() === q) || open.find(x => x.name.toLowerCase().includes(q));
      if (t) { input.value = ""; note.textContent = quiet; return requestAccess(t); }
      note.replaceChildren("No tool you can ask for matches that. ", el("a", { href: "#/tools?q=" + encodeURIComponent(typed) }, "Search every tool"), ".");
    };
    return [el("form", { class: "xf-ask", onsubmit: send }, input, el("datalist", { id: list }, open.map(t => el("option", { value: t.name }))),
      el("button", { type: "submit" }, "Ask")), note];
  }

  function glass(id) {
    const word = svg("text", { class: "xf-word", x: "50%", y: "0", "text-anchor": "middle", fill: "#000" }, "Swangz");
    const art = svg("svg", { class: "xf-glass", "aria-hidden": "true", focusable: "false", width: "100%", height: "100%" },
      svg("defs", null, svg("mask", { id, maskUnits: "userSpaceOnUse", x: "0", y: "0", width: "100%", height: "100%" },
        svg("rect", { width: "100%", height: "100%", fill: "#fff" }),
        svg("svg", { x: "0", y: "100%", width: "100%", height: "1", overflow: "visible" }, word))),
      svg("rect", { class: "xf-milk", width: "100%", height: "100%", rx: "28", mask: `url(#${id})` }));
    return { art, word };
  }

  function build(ctx) {
    const { me, requestAccess, policy, gurl } = ctx || {};
    serial += 1;
    const link = (href, text) => el("a", { href }, text);
    // Column titles are labels, not headings: "Requests" must stay the one heading of the Requests page.
    const col = (title, items) => el("div", { class: "xf-col" }, el("p", { class: "xf-col-title", "aria-hidden": "true" }, title),
      el("ul", { "aria-label": title }, items.map(i => el("li", null, i))));
    const dot = el("i", { class: "xf-dot", "data-state": "checking", "aria-hidden": "true" });
    const word = el("span", null, WORDS.checking);
    if (gurl) gatewayHealth(gurl, state => { dot.dataset.state = state; word.textContent = WORDS[state]; });

    const knob = el("button", { class: "xf-switch", type: "button", role: "switch" }, el("i", { "aria-hidden": "true" }));
    const label = el("span", { class: "xf-theme-name", "aria-hidden": "true" });
    const drawTheme = () => {
      const dark = SUI.theme() === "dark";
      label.textContent = dark ? "Evening" : "Daylight";
      knob.setAttribute("aria-checked", String(dark));
      knob.setAttribute("aria-label", "Evening theme (dark). Off is Daylight (light)");
    };
    knob.addEventListener("click", () => SUI.applyTheme(SUI.theme() === "dark" ? "light" : "dark", true));
    drawTheme();

    const { art, word: mark } = glass("xf-cut-" + serial);
    const wave = svg("svg", { class: "xf-wave", "aria-hidden": "true", focusable: "false", viewBox: "0 0 1200 14", preserveAspectRatio: "none" },
      svg("path", { class: "xf-milk", d: "M0 14V8C60 2 120 2 190 7s130 6 200 1 120-7 200-2 140 7 210 2 130-6 200-1 140 6 200 1V14Z" }));
    const body = el("div", { class: "xf-body" },
      el("div", { class: "xf-top" },
        el("div", { class: "xf-lead" },
          el("div", { class: "xf-brand" }, el("img", { src: "/static/icon.svg", alt: "", width: "36", height: "36" }), "Swangz AI Hub"),
          el("h2", null, "Need another tool?", el("br"), "Ask for it."),
          askForTool(me, requestAccess)),
        el("nav", { class: "xf-card", "aria-label": "Footer" },
          col("Workspace", [link("#/", "Home"), link("#/tools", "My tools"), link("#/devices", "Devices"), link("#/activity", "Activity")]),
          col("Reporting", [link("#/weekly", "Weekly reports"), link("#/business", "Adoption & impact"), link("#/projects", "Projects")]),
          col("Requests", [link("#/requests?view=updates", "Updates"), link("#/requests?view=access", "Access requests"), link("#/requests?view=procurement", "Procurement")]),
          col("Trust", [link("#/privacy", "How the Hub works"), policy ? el("button", { type: "button", onclick: policy }, "Usage policy") : null].filter(Boolean)))),
      el("div", { class: "xf-meta" },
        el("p", { class: "xf-copy" }, "© " + new Date().getFullYear() + " Swangz Avenue"),
        el("p", { class: "xf-status", role: "status" }, dot, word),
        el("div", { class: "xf-icons" },
          el("a", { href: "#/requests?view=updates", "aria-label": "Updates", "data-tip": "Updates" }, icon("bell")),
          el("a", { href: "#/tools", "aria-label": "My tools", "data-tip": "My tools" }, icon("tools")),
          el("a", { href: "#/weekly", "aria-label": "Weekly reports", "data-tip": "Weekly reports" }, icon("report")),
          el("a", { href: "#/privacy", "aria-label": "Privacy and help", "data-tip": "Privacy and help" }, icon("shield"))),
        el("div", { class: "xf-theme" }, label, knob)),
      el("div", { class: "xf-wordroom", "aria-hidden": "true" }));
    const panel = el("div", { class: "xf-panel" }, el("div", { class: "xf-fill" }, wave, art, el("i", { class: "xf-rim", "aria-hidden": "true" })), body);
    const f = el("footer", { class: "foot xfoot" }, panel);

    /* The word spans the panel (40px each side), capped at the reference's 240px capital height. Measured from
       the rendered glyphs, so it is right for Poppins and for the fallback face alike. */
    let frame = 0;
    const fit = () => {
      frame = 0;
      if (!f.isConnected) return;
      const width = panel.clientWidth;
      if (!width) return;
      f.style.setProperty("--xf-fs", "100px");
      let em = 3.4;
      try { const w = mark.getComputedTextLength(); if (w > 50) em = w / 100; } catch (e) { /* not rendered yet: keep the estimate */ }
      f.style.setProperty("--xf-fs", Math.max(48, Math.min(343, (width - 80) / em)).toFixed(1) + "px");
    };
    const queue = () => { if (!frame) frame = requestAnimationFrame(fit); };
    current = { f, drawTheme, queue };
    if ("ResizeObserver" in window) new ResizeObserver(queue).observe(panel);
    else requestAnimationFrame(queue);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(queue);

    if ("IntersectionObserver" in window && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      f.classList.add("xf-armed");
      const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) show(); }, { threshold: 0.12 });
      const show = () => { f.classList.add("xf-in"); io.disconnect(); };
      f.addEventListener("focusin", show, { once: true });   // Tab can reach the footer before it scrolls into view
      requestAnimationFrame(() => { if (f.isConnected) io.observe(f); });
    }
    return f;
  }

  document.addEventListener("swangz:theme", () => { if (current && current.f.isConnected) current.drawTheme(); });
  window.SWFooter = { build };
})();
