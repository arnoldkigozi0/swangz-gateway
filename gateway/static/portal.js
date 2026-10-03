"use strict";
/* Swangz AI — the staff app: sign in, connect a tool, look after your devices. */
(() => {
  const app = document.getElementById("app");
  const S = { me: null };

  // ------------------------------------------------------------------ helpers

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (k === "value") node.value = v;
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  function svg(paths, size) {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("fill", "none");
    s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", "2");
    s.setAttribute("stroke-linecap", "round");
    s.setAttribute("stroke-linejoin", "round");
    if (size) { s.setAttribute("width", size); s.setAttribute("height", size); }
    paths.forEach((d) => { const p = document.createElementNS(ns, "path"); p.setAttribute("d", d); s.append(p); });
    return s;
  }
  const ICON_DEVICE = ["M4 5h16v11H4z", "M2 20h20", "M9 16v4", "M15 16v4"];

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  // When the app is served by the gateway, GATEWAY is "" (same origin). When it's hosted elsewhere
  // (e.g. Netlify), a config.js sets window.SWANGZ_GATEWAY to the gateway's address.
  const GATEWAY = (typeof window !== "undefined" && window.SWANGZ_GATEWAY || "").replace(/\/+$/, "");
  const gurl = (path) => GATEWAY + path;

  async function api(method, path, body) {
    const opts = { method, credentials: "include", headers: { "x-swangz-app": "1" } };
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(GATEWAY + "/api" + path, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) throw new ApiError(res.status, (data && data.error) || "Something went wrong. Try again.");
    return data;
  }

  function toast(message, bad) {
    const t = el("div", { class: "toast" + (bad ? " bad" : ""), role: "status" }, message);
    document.body.append(t);
    setTimeout(() => t.remove(), bad ? 6000 : 2600);
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied"); }
    catch (e) { toast("Couldn't copy here — select the text and copy it.", true); }
  }

  const money = (v) => (v || 0) < 0.01 && v > 0 ? "<$0.01" : "$" + (v || 0).toFixed(2);
  function ago(ts) {
    if (!ts) return "never";
    const s = Date.now() / 1000 - ts;
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    if (s < 86400 * 30) return Math.round(s / 86400) + " days ago";
    return new Date(ts * 1000).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
  }
  function greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  }
  const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

  function passwordInput(autocomplete) {
    const input = el("input", { class: "input", type: "password", autocomplete, required: true, minlength: autocomplete === "new-password" ? "10" : null });
    const reveal = el("button", { class: "btn btn--quiet reveal", type: "button", "aria-label": "Show password",
      onclick: () => { const shown = input.type === "text"; input.type = shown ? "password" : "text"; reveal.textContent = shown ? "Show" : "Hide"; } }, "Show");
    return { input, node: el("div", { class: "input-wrap" }, input, reveal) };
  }

  function codeBlock(text) {
    return el("div", { class: "code" }, el("pre", null, text), el("button", { class: "btn", type: "button", onclick: () => copy(text) }, "Copy"));
  }

  function dialog(title, text, actions) {
    const d = el("dialog", null, el("div", { class: "d-body" }, el("h2", null, title), typeof text === "string" ? el("p", null, text) : text),
      el("div", { class: "d-actions" }, actions(() => d.close())));
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }

  // ------------------------------------------------------------------ theme, icons, logos

  const ICON = {
    sun: ["M12 2.5v2", "M12 19.5v2", "M4.6 4.6L6 6", "M18 18l1.4 1.4", "M2.5 12h2", "M19.5 12h2", "M4.6 19.4L6 18", "M18 6l1.4-1.4", "M12 7.5a4.5 4.5 0 1 0 0 9a4.5 4.5 0 1 0 0-9z"],
    moon: ["M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"],
    search: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "M20 20l-4-4"],
    shield: ["M12 3l7.5 3v5.5c0 4.6-3.2 7.9-7.5 9.5c-4.3-1.6-7.5-4.9-7.5-9.5V6z", "M9 12l2 2l4-4"],
    grid: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
    clock: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7.5V12l3 2"],
    inbox: ["M4 13.5L6.2 5h11.6L20 13.5", "M4 13.5V19h16v-5.5", "M4 13.5h5l1.2 2h3.6l1.2-2h5"],
    wallet: ["M4 7h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z", "M4 7l11-3v3", "M16 13h1.5"],
    open: ["M8 16L16 8", "M10 8h6v6"],
  };

  const THEME_KEY = "swangz-theme";
  const theme = () => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  function applyTheme(t, remember) {
    document.documentElement.dataset.theme = t;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "dark" ? "#0A0A0B" : "#F4F2ED");
    if (remember) { try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* private window: just this visit */ } }
  }
  (() => { let saved = null; try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* none */ } applyTheme(saved === "light" ? "light" : "dark", false); })();  // dark is the default
  function themeButton() {
    const b = el("button", { class: "theme-btn", type: "button" });
    const draw = () => {
      const dark = theme() === "dark";
      b.replaceChildren(svg(dark ? ICON.sun : ICON.moon));
      b.setAttribute("aria-label", dark ? "Switch to the light theme" : "Switch to the midnight theme");
      b.title = dark ? "Light theme" : "Midnight theme";
    };
    b.addEventListener("click", () => { applyTheme(theme() === "dark" ? "light" : "dark", true); draw(); });
    draw();
    return b;
  }

  function logo(t, size) {
    const cls = "logo" + (size ? " " + size : "");
    const mono = () => {
      const box = el("span", { class: cls + " mono", "aria-hidden": "true" }, initials(t.name));
      const c = /^#[0-9a-f]{6}$/i.test(t.color || "") ? t.color : "#3F3F46";
      box.style.background = `linear-gradient(140deg, ${c}, color-mix(in srgb, ${c} 55%, #0A0A0B))`;
      return box;
    };
    if (!t.icon) return mono();
    const img = el("img", { src: gurl(t.icon), alt: "", loading: "lazy", decoding: "async" });
    const box = el("span", { class: cls, "aria-hidden": "true" }, img);
    img.addEventListener("error", () => box.replaceWith(mono()));
    return box;
  }

  // how a tool signs you in when you open it from here
  const HOW = {
    sso: ["Company sign-in", "Opens with your Swangz work account — no separate password."],
    seat: ["Company seat", "Your seat on the company plan. Sign in with your work email."],
    own: ["Your own login", "Use your own account for this one."],
    api: ["Company key", "Runs on the company's key — nothing to sign in to."],
    shared: ["Shared account", "One company account the team takes turns on, so the credits it spends can be traced."],
  };
  const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateText = (ts) => new Date(ts * 1000).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });

  // ------------------------------------------------------------------ Google sign-in

  const AUTH_ERRORS = {
    cancelled: "Google sign-in was cancelled.",
    expired: "That sign-in took too long or was started in another browser. Try again.",
    google: "Google couldn't confirm that account. Try again.",
    not_allowed: "Only Swangz work accounts can sign in here.",
    no_account: "That Google account isn't set up in Swangz AI yet. Ask your admin to add your email.",
    paused: "Your access is paused. Talk to your admin.",
    off: "Google sign-in isn't set up yet. Use your email and password.",
  };
  function authError() {
    const code = new URLSearchParams(location.search).get("auth_error");
    if (code) history.replaceState(null, "", location.pathname + location.hash);
    return code ? (AUTH_ERRORS[code] || "Sign-in didn't work. Try again.") : "";
  }
  function googleMark() {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    s.setAttribute("viewBox", "0 0 48 48"); s.setAttribute("width", "18"); s.setAttribute("height", "18"); s.setAttribute("aria-hidden", "true");
    [["#EA4335", "M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"],
      ["#4285F4", "M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"],
      ["#FBBC05", "M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"],
      ["#34A853", "M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"]]
      .forEach(([fill, d]) => { const p = document.createElementNS(ns, "path"); p.setAttribute("fill", fill); p.setAttribute("d", d); s.append(p); });
    return s;
  }
  // The Google button appears once the gateway says it's set up. Only when the app and the gateway
  // share an address (served by the gateway, or a Netlify front door that proxies to it).
  async function googleButton(app, label) {
    const box = el("div", { class: "google-box" });
    if (GATEWAY) return box;
    try {
      const res = await fetch("/auth/options", { credentials: "include" });
      const opt = res.ok ? await res.json() : {};
      if (opt.google) box.append(el("a", { class: "btn btn--google btn--block", href: "/auth/google/start?app=" + app }, googleMark(), label),
        el("div", { class: "or" }, el("span", null, "or use your email")));
    } catch (e) { /* no Google button */ }
    return box;
  }

  // ------------------------------------------------------------------ gate (sign in, welcome)

  function gateArt() {
    return el("section", { class: "gate-art" },
      el("a", { class: "wordmark", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz ", el("b", null, "AI")),
      el("div", null,
        el("h1", { class: "gate-title" }, "Every AI tool. ", el("em", null, "One door.")),
        el("p", { class: "gate-lede" }, "The AI tools Swangz pays for, in one place. Open any of them with your work account — no personal subscriptions, no passwords to juggle."),
        el("div", { class: "tool-row" }, ["ChatGPT", "Claude", "Midjourney", "ElevenLabs", "Canva", "Runway", "Claude Code"].map((t) => el("span", null, t)))),
      el("div", { class: "gate-foot" }, el("span", null, "Swangz Avenue"), el("span", null, "Company access only")));
  }

  function gateFrame(form) {
    return el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" }, form));
  }

  function showSignIn() {
    const email = el("input", { class: "input", type: "email", autocomplete: "email", required: true, placeholder: "you@swangzavenue.com" });
    const pw = passwordInput("current-password");
    const err = el("div", { class: "form-error", role: "alert" }, authError());
    const google = el("div");
    googleButton("staff", "Continue with Google").then((b) => google.replaceWith(b));
    const go = el("button", { class: "btn btn--solid btn--block", type: "submit" }, "Sign in");
    const form = el("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        go.disabled = true;
        err.textContent = "";
        try {
          await api("POST", "/login", { email: email.value, password: pw.input.value });
          await load();
        } catch (x) { err.textContent = x.message; go.disabled = false; }
      },
    },
    el("div", null, el("div", { class: "eyebrow" }, "Welcome back"), el("h2", null, "Sign in to Swangz AI")),
    google,
    el("label", { class: "field" }, el("span", null, "Work email"), email),
    el("label", { class: "field" }, el("span", null, "Password"), pw.node),
    err, go,
    el("p", { class: "muted small" }, "First time here? Your admin sends you a sign-in link. Forgot your password? Ask them for a new one."));
    app.replaceChildren(gateFrame(form));
    email.focus();
  }

  async function showWelcome(token) {
    let invite;
    try {
      invite = await api("GET", "/welcome/" + encodeURIComponent(token));
    } catch (e) {
      const form = el("form", null, el("div", { class: "eyebrow" }, "Sign-in link"), el("h2", null, "This link has run out"),
        el("p", { class: "muted" }, e.message), el("a", { class: "btn", href: "#/" }, "Go to sign in"));
      app.replaceChildren(gateFrame(form));
      return;
    }
    const pw = passwordInput("new-password");
    const again = passwordInput("new-password");
    const err = el("div", { class: "form-error", role: "alert" });
    const go = el("button", { class: "btn btn--solid btn--block", type: "submit" }, invite.has_password ? "Set new password" : "Set password and continue");
    const form = el("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        if (pw.input.value.length < 10) { err.textContent = "Use at least 10 characters."; return; }
        if (pw.input.value !== again.input.value) { err.textContent = "The two passwords don't match."; return; }
        go.disabled = true;
        try {
          await api("POST", "/welcome", { token, password: pw.input.value });
          history.replaceState(null, "", location.pathname);
          await load();
          toast("You're in. Your tools are below.");
        } catch (x) { err.textContent = x.message; go.disabled = false; }
      },
    },
    el("div", null, el("div", { class: "eyebrow" }, invite.has_password ? "Reset your password" : "Welcome"),
      el("h2", null, invite.has_password ? "Choose a new password" : `Hi ${invite.name}, let's set you up`)),
    el("p", { class: "muted" }, `You'll sign in with ${invite.email}.`),
    el("label", { class: "field" }, el("span", null, "Choose a password (10+ characters)"), pw.node),
    el("label", { class: "field" }, el("span", null, "Type it again"), again.node),
    err, go);
    app.replaceChildren(gateFrame(form));
    pw.input.focus();
  }

  // ------------------------------------------------------------------ home

  const TOOL_TO_GUIDE = { "claude-code": "claude-code", codex: "codex", claude: "anthropic-sdk",
    chatgpt: "openai-compatible", elevenlabs: "elevenlabs", "higgsfield-ai": "higgsfield" };
  const STUDIO_TOOLS = { elevenlabs: "voice", "higgsfield-ai": "image" };
  const STATE_LABEL = { enabled: "Ready", not_assigned: "Available on request", locked: "Not on the company plan",
    past_due: "Renewal due", suspended: "Paused" };
  const S_FILTER = { q: "", cat: "all" };
  let slashBound = false;

  function render() {
    const me = S.me;
    const catalog = me.catalog || [];
    const menu = el("div", { class: "menu", role: "menu" },
      el("div", { class: "who" }, el("div", null, me.name), el("div", null, me.email)),
      el("button", { onclick: changePassword, role: "menuitem" }, "Change password"),
      el("button", { onclick: policy, role: "menuitem" }, "Usage policy"),
      el("button", { onclick: signOut, role: "menuitem" }, "Sign out"));
    const meBtn = el("button", { class: "me-btn", "aria-haspopup": "menu", onclick: (e) => { e.stopPropagation(); menu.classList.toggle("open"); } },
      el("span", { class: "avatar" }, initials(me.name)), el("span", { class: "me-name" }, me.name));
    document.addEventListener("click", () => menu.classList.remove("open"));

    const searchInput = el("input", { class: "topsearch", type: "search", placeholder: "Search tools", value: S_FILTER.q,
      "aria-label": "Search tools", oninput: (e) => { S_FILTER.q = e.target.value; draw(); } });
    const search = el("div", { class: "search-wrap" }, svg(ICON.search), searchInput, el("kbd", null, "/"));
    if (!slashBound) {
      slashBound = true;
      document.addEventListener("keydown", (e) => {
        if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "")) {
          const box = document.querySelector(".topsearch");
          if (box) { e.preventDefault(); box.focus(); }
        }
      });
    }
    const topbar = el("header", { class: "topbar" }, el("div", { class: "inner" },
      el("a", { class: "wordmark", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz ", el("b", null, "AI")),
      catalog.length ? search : null,
      el("div", { class: "top-right" }, themeButton(), el("div", { class: "me-menu" }, meBtn, menu))));

    const enabled = catalog.filter((t) => t.state === "enabled");
    const weekAgo = Date.now() / 1000 - 7 * 86400;
    const usedWeek = enabled.filter((t) => t.last_opened && t.last_opened >= weekAgo).length;
    const pending = catalog.filter((t) => t.pending).length;
    const statusText = me.active ? "Your tools are ready" : me.suspended ? "Your access is paused — talk to your admin" : "AI access is paused for everyone right now";
    const stat = (icon, label, big, note, extra) => el("div", { class: "stat" },
      el("div", { class: "label" }, svg(icon), label), el("div", { class: "big" }, big), el("div", { class: "note" }, note), extra);
    const stats = el("div", { class: "stats" },
      stat(ICON.grid, "Ready for you", String(enabled.length), `of ${catalog.length} tools in the company catalog`),
      stat(ICON.clock, "Used this week", String(usedWeek), usedWeek === 1 ? "tool you opened" : "tools you opened"),
      stat(ICON.inbox, "Requests waiting", String(pending), pending ? "an admin will review them" : "nothing pending"),
      me.budget ? stat(ICON.wallet, "Allowance this month", money(me.budget.month),
        me.budget.monthly !== null ? `of ${money(me.budget.monthly)}` : "no limit set",
        me.budget.monthly !== null ? meter(me.budget.month, me.budget.monthly) : null) : null);
    const recent = enabled.filter((t) => t.last_opened && t.launchable && t.kind !== "dev")
      .sort((a, b) => b.last_opened - a.last_opened).slice(0, 6);
    const hero = el("section", { class: "hero" }, el("div", { class: "shell" },
      el("div", { class: "status" + (me.active ? "" : " off") }, el("i"), statusText),
      el("h1", null, `${greeting()}, ${me.name}.`),
      el("p", { class: "sub" }, [me.title, me.department].filter(Boolean).join(" · ") || "Swangz Avenue"),
      me.access_until ? el("p", { class: "sub small" }, `Your access runs until ${dateText(me.access_until - 1)}.`) : null,
      stats,
      me.budget && me.budget.monthly !== null && me.budget.month >= me.budget.monthly
        ? el("div", { class: "notice" }, "You've used this month's allowance. It resets on the 1st — or ask your admin for more.") : null,
      recent.length ? el("div", { class: "recent", "aria-label": "Recently opened" },
        recent.map((t) => el("a", { href: gurl("/go/" + t.id), target: "_blank", rel: "noopener", title: "Open " + t.name, onclick: () => opened(t) },
          logo(t, "sm"), t.name))) : null));

    const cats = ["all", ...Array.from(new Set(catalog.map((t) => t.category))).sort()];
    const chips = el("div", { class: "chips-row" }, cats.map((c) => el("button", {
      class: "chip" + (S_FILTER.cat === c ? " on" : ""), type: "button",
      onclick: (e) => { S_FILTER.cat = c; chips.querySelectorAll(".chip").forEach((b) => b.classList.toggle("on", b === e.currentTarget)); draw(); } },
    c === "all" ? "All" : c)));
    const yours = el("div", { class: "launch-grid" });
    const explore = el("div", { class: "explore" });
    const exploreWrap = el("div");

    const yoursSection = el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Your tools"),
        el("h2", null, enabled.length ? "Open a tool" : "Nothing switched on yet"),
        el("p", null, enabled.length
          ? "Everything here is paid for by Swangz and ready for you. Open opens it in a new tab."
          : "Browse the catalog below and request what you need — an admin turns it on."))),
      catalog.length > 8 ? chips : null, yours));
    const exploreSection = el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "The catalog"),
        el("h2", null, "More tools at Swangz"),
        el("p", null, "Ask for any of these and an admin can turn it on for you."))),
      exploreWrap));

    function matches(t) {
      const q = S_FILTER.q.trim().toLowerCase();
      if (S_FILTER.cat !== "all" && t.category !== S_FILTER.cat) return false;
      return !q || t.name.toLowerCase().includes(q) || t.category.toLowerCase().includes(q) || (t.description || "").toLowerCase().includes(q);
    }
    function draw() {
      const mine = enabled.filter(matches).sort((a, b) => (b.last_opened || 0) - (a.last_opened || 0) || a.name.localeCompare(b.name));
      yours.replaceChildren(...(mine.length ? mine.map(launchTile)
        : [el("div", { class: "empty" }, enabled.length ? "None of your tools match that." : el("p", null, "When an admin turns a tool on for you, it appears here."))]));
      const order = { not_assigned: 0, past_due: 1, locked: 2, suspended: 3 };
      const rest = catalog.filter((t) => t.state !== "enabled" && matches(t)).sort((a, b) => (order[a.state] - order[b.state]) || a.name.localeCompare(b.name));
      explore.replaceChildren(...rest.map(exploreRow));
      exploreWrap.replaceChildren(rest.length ? explore : el("div", { class: "empty" }, S_FILTER.q || S_FILTER.cat !== "all" ? "No other tools match." : "You have every tool in the catalog."));
    }
    draw();

    const studio = S.studio && (S.studio.voice || S.studio.image || S.studio.video) && me.active ? studioSection() : null;

    const deviceList = me.keys.length ? el("div", { class: "devices" }, me.keys.map((k) => el("div", { class: "device" + (k.revoked ? " off" : "") },
      el("div", { class: "dot" }, svg(ICON_DEVICE)),
      el("div", null, el("strong", null, k.label), el("div", { class: "meta" },
        el("span", { class: "mono" }, k.hint), " · ", k.revoked ? "disconnected " + ago(k.revoked) : `connected ${ago(k.created)} · last used ${ago(k.last_used)}`)),
      k.revoked ? el("span", { class: "muted" }, "Disconnected") : el("button", { class: "btn btn--danger btn--small", onclick: () => disconnect(k) }, "Disconnect"))))
      : el("div", { class: "empty" }, "No devices yet. Set up a coding tool above to connect your first one.");
    const devices = me.keys.length || enabled.some((t) => t.kind !== "site") ? el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Your devices"), el("h2", null, "Connected devices"),
        el("p", null, "Each laptop or coding tool has its own key. Disconnect one you no longer use — the others keep working."))),
      deviceList)) : null;

    const foot = el("footer", { class: "foot" }, el("div", { class: "inner" },
      el("span", { class: "brandline" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz Avenue · Swangz AI"),
      el("button", { onclick: policy }, "Usage policy")));

    app.replaceChildren(topbar, el("main", null, hero, yoursSection, exploreSection, studio, devices), foot);
    resumeJobs();
  }

  function opened(t) {
    t.last_opened = Date.now() / 1000;
    setTimeout(() => { if (!document.querySelector("dialog, .drawer")) render(); }, 800);
  }

  function launchTile(t) {
    const how = HOW[t.kind === "dev" ? "api" : (t.signin || "seat")] || HOW.seat;
    const busy = t.turn && !t.turn.mine && !t.turn.free;
    return el("article", { class: "ltile" + (t.turn && t.turn.mine ? " holding" : busy ? " busy" : "") },
      el("div", { class: "ltile-top" }, logo(t), el("div", { class: "grow" }, el("h3", null, t.name), el("div", { class: "cat" }, t.category))),
      el("p", null, t.description || "Ready for you to use at work."),
      el("div", { class: "ltile-foot" },
        el("div", { class: "ltile-meta" },
          el("span", { class: "how", title: how[1] }, svg(ICON.shield), how[0]),
          turnLine(t) || (t.ends ? el("span", { class: "ends" }, "Until " + dateText(t.ends - 1))
            : el("span", { class: "when" }, t.kind === "dev" ? "Set up once per device" : t.last_opened ? "Opened " + ago(t.last_opened) : "Not opened yet"))),
        el("div", { class: "ltile-actions" }, launchActions(t))));
  }

  function turnLine(t) {
    const turn = t.turn;
    if (!turn) return null;
    if (turn.mine) return el("span", { class: "turn-on" }, "Yours until " + clock(turn.mine.expires));
    if (turn.others.length) {
      const soonest = turn.others.slice().sort((a, b) => a.expires - b.expires)[0];
      return el("span", { class: "turn-busy" }, `${soonest.person} has it until ${clock(soonest.expires)}`);
    }
    return el("span", { class: "when" }, `Free — your turn lasts ${turn.minutes} min`);
  }

  async function handBack(t) {
    try {
      await api("POST", `/tools/${t.id}/turn/end`);
      toast("Handed back. Your browser is being signed out of it.");
      load();
    } catch (e) { toast(e.message, true); }
  }

  function launchActions(t) {
    const me = S.me;
    const guideId = TOOL_TO_GUIDE[t.id];
    const guide = guideId && (me.connect || []).find((g) => g.id === guideId);
    const openBtn = (label, solid) => el("a", { class: "btn btn--small " + (solid ? "btn--solid" : ""), href: gurl("/go/" + t.id), target: "_blank",
      rel: "noopener", onclick: () => opened(t) }, label, svg(ICON.open));
    if (t.id in STUDIO_TOOLS && S.studio && S.studio[STUDIO_TOOLS[t.id]]) {
      return [t.launchable ? el("a", { class: "tlink", href: gurl("/go/" + t.id), target: "_blank", rel: "noopener", onclick: () => opened(t) }, "Website") : null,
        el("button", { class: "btn btn--solid btn--small", onclick: () => document.querySelector(".studio")?.scrollIntoView({ behavior: "smooth" }) }, "Open Studio")];
    }
    if (t.kind === "dev") {
      return guide ? [el("button", { class: "btn btn--solid btn--small", onclick: () => connect(guide) }, "Set up")] : [el("span", { class: "muted small" }, "Ready")];
    }
    if (t.turn) {
      if (t.turn.mine) {
        return [el("button", { class: "tlink", onclick: () => handBack(t) }, "Hand back"), openBtn("Open", true)];
      }
      if (!t.turn.free) {
        return [el("button", { class: "btn btn--small", disabled: true, title: "Someone else has the shared account" }, "In use")];
      }
      return [openBtn("Take your turn", true)];
    }
    return [guide ? el("button", { class: "tlink", onclick: () => connect(guide) }, "API") : null,
      t.launchable ? openBtn("Open", true) : el("span", { class: "muted small" }, "Ready")];
  }

  function exploreRow(t) {
    const me = S.me;
    let action;
    if (!me.active || t.state === "suspended") action = el("span", { class: "state-chip s-suspended" }, "Paused");
    else if (t.pending) action = el("span", { class: "requested" }, "Requested ✓");
    else action = el("button", { class: "btn btn--small", onclick: () => requestAccess(t) }, t.state === "past_due" ? "Ask to renew" : "Request");
    return el("div", { class: "xrow s-" + t.state },
      logo(t),
      el("div", { class: "grow" }, el("h3", null, t.name),
        el("div", { class: "why", title: t.reason }, t.state === "not_assigned" ? (t.description || t.category) : `${t.category} · ${STATE_LABEL[t.state] || t.reason}`)),
      action);
  }

  async function requestAccess(t) {
    const reason = el("textarea", { class: "input area", rows: "3", placeholder: "Optional — what do you need it for?" });
    const err = el("div", { class: "form-error" });
    dialog("Request " + t.name, el("div", { class: "fields" },
      el("p", null, t.state === "locked"
        ? `Swangz isn't subscribed to ${t.name} yet. Your request tells an admin it's needed.`
        : `An admin will see this and can turn ${t.name} on for you.`), reason, err),
    (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
      el("button", { class: "btn btn--solid", onclick: async () => {
        try { await api("POST", `/tools/${t.id}/request`, { reason: reason.value }); close(); toast("Request sent."); load(); }
        catch (e) { err.textContent = e.message; } } }, "Send request")]);
  }

  // ------------------------------------------------------------------ Studio: voice, image, video

  const TYPE_LABEL = { voice: "Voice-over", image: "Image", video: "Video", sound: "Sound", music: "Music", transcription: "Transcript" };
  const JOBS = new Map();

  function studioSection() {
    const st = S.studio;
    const tabs = [["voice", "Voice", st.voice], ["image", "Image", st.image], ["video", "Video", st.video]].filter((t) => t[2]);
    const panel = el("div", { class: "studio-panel" });
    const tabBar = el("div", { class: "tabs", role: "tablist" }, tabs.map(([id, label]) =>
      el("button", { class: "tab", role: "tab", type: "button", "data-tab": id, onclick: () => show(id) }, label)));
    const creations = el("div", { class: "creations" });

    function show(id) {
      tabBar.querySelectorAll(".tab").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === id ? "true" : "false"));
      panel.replaceChildren(id === "voice" ? voiceForm() : visualForm(id));
    }

    function voiceForm() {
      const voice = el("select", { class: "input" }, st.voices.map((v) => el("option", { value: v.id }, v.name + (v.about ? ` — ${v.about}` : ""))));
      const model = el("select", { class: "input" }, st.voice_models.map((m) => el("option", { value: m.id }, m.name)));
      const text = el("textarea", { class: "input area", rows: "5", maxlength: "5000", placeholder: "Type the script — for example: Swangz Avenue presents the December Showcase, live at Serena Kampala." });
      const count = el("span", { class: "muted small" }, "0 / 5,000");
      text.addEventListener("input", () => { count.textContent = `${text.value.length.toLocaleString()} / 5,000`; });
      const err = el("div", { class: "form-error" });
      const go = el("button", { class: "btn btn--solid", type: "submit" }, "Make the voice-over");
      return el("form", { class: "studio-form", onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        go.disabled = true;
        go.textContent = "Making it…";
        try {
          const made = await api("POST", "/studio/voice", { text: text.value, voice_id: voice.value, model_id: model.value });
          addCreation(made, true);
          text.value = "";
          count.textContent = "0 / 5,000";
        } catch (x) { err.textContent = x.message; }
        go.disabled = false;
        go.textContent = "Make the voice-over";
      } },
      st.voices.length ? null : el("div", { class: "notice" }, "No voices are available yet — ask your admin."),
      el("div", { class: "form-row" }, el("label", { class: "field" }, el("span", null, "Voice"), voice), el("label", { class: "field" }, el("span", null, "Quality"), model)),
      el("label", { class: "field" }, el("span", null, "Script"), text), el("div", { class: "spread" }, count, go), err);
    }

    function visualForm(kind) {
      const prompt = el("textarea", { class: "input area", rows: "4", placeholder: kind === "image"
        ? "Describe the picture — for example: a moody poster of a live band on stage at night, Kampala skyline behind, warm amber lights."
        : "Describe the motion — for example: slow push-in on the singer, haze drifting, lights flicker." });
      const aspect = el("select", { class: "input" }, ["16:9", "9:16", "1:1", "4:5"].map((a) => el("option", { value: a }, a)));
      const image = el("input", { class: "input", type: "url", placeholder: "https://… link to the starting picture" });
      const err = el("div", { class: "form-error" });
      const label = kind === "image" ? "Make the image" : "Make the video";
      const go = el("button", { class: "btn btn--solid", type: "submit" }, label);
      return el("form", { class: "studio-form", onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        go.disabled = true;
        go.textContent = "Starting…";
        try {
          const made = await api("POST", "/studio/generate", { kind, prompt: prompt.value, aspect_ratio: aspect.value, image_url: image.value });
          addCreation(made, true);
          prompt.value = "";
        } catch (x) { err.textContent = x.message; }
        go.disabled = false;
        go.textContent = label;
      } },
      kind === "video" ? el("label", { class: "field" }, el("span", null, "Starting picture"), image,
        el("span", { class: "muted small" }, "Make an image first and copy its link, or use any picture that's online.")) : null,
      el("label", { class: "field" }, el("span", null, kind === "image" ? "What should it show?" : "What should happen?"), prompt),
      el("div", { class: "spread" }, kind === "image" ? el("label", { class: "field inline" }, el("span", null, "Shape"), aspect) : el("span"), go), err);
    }

    function addCreation(c, fresh) {
      const card = creationCard(c);
      if (fresh) card.classList.add("fresh");
      creations.prepend(card);
      empty.hidden = true;
      if (c.job && !c.urls.length && c.outcome === "ok") JOBS.set(c.job, card);
      if (fresh) resumeJobs();
    }

    const empty = el("p", { class: "muted" }, "What you make shows up here, so you can play it again or download it.");
    st.recent.slice().reverse().forEach((c) => addCreation(c, false));
    empty.hidden = st.recent.length > 0;
    setTimeout(() => show(tabs[0][0]), 0);

    return el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Create"), el("h2", null, "Make it here"),
        el("p", null, "Voice-overs, images and video in the browser — nothing to install, nothing to pay."))),
      el("div", { class: "studio" }, tabBar, panel),
      el("h3", { class: "sub-head" }, "Recent creations"), empty, creations));
  }

  function creationCard(c) {
    const body = el("div", { class: "creation-media" });
    fillCreation(body, c);
    return el("article", { class: "creation", "data-id": String(c.id) },
      body,
      el("div", { class: "creation-meta" },
        el("div", { class: "spread" }, el("span", { class: "eyebrow" }, TYPE_LABEL[c.type] || "Creation"), el("span", { class: "muted small" }, ago(c.ts))),
        c.prompt ? el("p", { class: "creation-prompt" }, c.prompt) : null));
  }

  function fillCreation(body, c) {
    if (c.outcome && c.outcome !== "ok") {
      body.replaceChildren(el("div", { class: "creation-state bad" }, c.reason || "This one didn't work."));
    } else if (c.audio) {
      body.replaceChildren(el("audio", { controls: true, preload: "none", src: gurl(c.audio), crossorigin: GATEWAY ? "use-credentials" : null }),
        el("a", { class: "btn btn--small", href: gurl(c.audio), download: "swangz-voice-" + c.id + ".mp3" }, "Download"));
    } else if (c.urls && c.urls.length) {
      const u = c.urls[0];
      const media = c.type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(u)
        ? el("video", { controls: true, preload: "metadata", src: u, playsinline: true })
        : el("img", { src: u, alt: c.prompt || "Generated image", loading: "lazy" });
      body.replaceChildren(media, el("a", { class: "btn btn--small", href: u, target: "_blank", rel: "noopener noreferrer" }, "Open full size"));
    } else {
      body.replaceChildren(el("div", { class: "creation-state" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Working on it — usually under a minute."));
    }
  }

  let polling = false;
  async function resumeJobs() {
    if (polling) return;
    polling = true;
    while (JOBS.size) {
      await new Promise((r) => setTimeout(r, 3000));
      for (const [job, card] of [...JOBS]) {
        if (!card.isConnected) { JOBS.delete(job); continue; }
        try {
          const c = await api("GET", "/studio/jobs/" + encodeURIComponent(job));
          if (c.urls.length || ["failed", "nsfw"].includes(c.state)) {
            if (c.state === "nsfw") c.outcome = "error", c.reason = "The service turned this one down for its content.";
            if (c.state === "failed") c.outcome = "error", c.reason = "The service couldn't make this one. Try again.";
            fillCreation(card.querySelector(".creation-media"), c);
            JOBS.delete(job);
          }
        } catch (e) { JOBS.delete(job); }
      }
    }
    polling = false;
  }

  function meter(value, limit) {
    const fill = el("i");
    fill.style.width = Math.min(100, (value / (limit || 1)) * 100) + "%";
    return el("div", { class: "meter" + (value >= limit ? " full" : "") }, fill);
  }

  function tip(title, text) { return el("div", { class: "tip" }, el("h3", null, title), el("p", null, text)); }

  // ------------------------------------------------------------------ connect a tool

  function connect(tool) {
    const scrim = el("div", { class: "scrim" });
    const body = el("div", { class: "body" });
    const foot = el("footer");
    const drawer = el("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Connect " + tool.name },
      el("header", null, el("div", null, el("div", { class: "eyebrow" }, tool.kind), el("h2", null, "Connect " + tool.name)),
        el("button", { class: "btn btn--quiet", onclick: close, "aria-label": "Close" }, "Close")),
      body, foot);
    let created = false;

    function close() {
      drawer.classList.remove("in");
      scrim.classList.remove("in");
      setTimeout(() => { scrim.remove(); drawer.remove(); }, 320);
      document.removeEventListener("keydown", onKey);
      if (created) load();
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);

    const label = el("input", { class: "input", type: "text", value: `My laptop — ${tool.name}`, maxlength: "80" });
    const err = el("div", { class: "form-error" });
    const make = el("button", { class: "btn btn--solid", onclick: async () => {
      make.disabled = true;
      try {
        const out = await api("POST", "/keys", { label: label.value });
        created = true;
        showSteps(out);
      } catch (e) { err.textContent = e.message; make.disabled = false; }
    } }, "Create my key");
    body.replaceChildren(
      el("div", { class: "step" }, el("div", { class: "n" }, "1"), el("div", null,
        el("h3", null, "Name this device"),
        el("p", null, "So you can tell your devices apart later — for example the laptop and the tool."),
        label, err)));
    foot.replaceChildren(el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"), make);

    function showSteps(out) {
      const guide = out.tools.find((t) => t.id === tool.id) || out.tools[0];
      body.replaceChildren(
        el("div", { class: "step" }, el("div", { class: "n" }, "1"), el("div", null,
          el("h3", null, "Your key for " + out.label),
          el("p", { class: "once" }, "Shown only this once. It's already in the steps below — keep a copy somewhere safe."),
          el("div", { class: "keyline" }, el("code", null, out.key), el("button", { class: "btn", onclick: () => copy(out.key) }, "Copy")))),
        ...guide.steps.map((s, i) => el("div", { class: "step" }, el("div", { class: "n" }, String(i + 2)), el("div", null,
          el("h3", null, s.title), el("p", null, s.how), codeBlock(s.code)))));
      foot.replaceChildren(el("button", { class: "btn btn--solid", onclick: close }, "Done"));
    }

    document.body.append(scrim, drawer);
    requestAnimationFrame(() => { scrim.classList.add("in"); drawer.classList.add("in"); label.focus(); label.select(); });
  }

  function disconnect(k) {
    dialog("Disconnect " + k.label + "?", "Its key stops working straight away. Your other devices keep working, and you can connect this one again at any time.",
      (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
        el("button", { class: "btn btn--danger", onclick: async () => {
          try { await api("POST", `/keys/${k.id}/revoke`); close(); toast("Disconnected."); load(); } catch (e) { toast(e.message, true); }
        } }, "Disconnect")]);
  }

  function changePassword() {
    const cur = passwordInput("current-password");
    const nw = passwordInput("new-password");
    const err = el("div", { class: "form-error" });
    dialog("Change password", el("div", { class: "fields" },
      el("label", { class: "field" }, el("span", null, "Current password"), cur.node),
      el("label", { class: "field" }, el("span", null, "New password (10+ characters)"), nw.node), err),
    (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
      el("button", { class: "btn btn--solid", onclick: async () => {
        try { await api("POST", "/password", { current: cur.input.value, new: nw.input.value }); close(); toast("Password changed."); } catch (e) { err.textContent = e.message; }
      } }, "Save")]);
  }

  function policy() {
    dialog("Using Swangz AI", el("div", { class: "fields" },
      el("p", null, "Swangz AI is provided for your work at Swangz. Your requests are handled by AI providers on the company's behalf."),
      el("p", null, "Like any company system, use is recorded for security, cost and support. Don't paste passwords, other people's personal details, or anything you wouldn't put in a work email."),
      el("p", null, "Questions? Ask your admin.")),
    (close) => [el("button", { class: "btn btn--solid", onclick: close }, "Got it")]);
  }

  async function signOut() {
    try { await api("POST", "/logout"); } catch (e) { /* signed out anyway */ }
    S.me = null;
    showSignIn();
  }

  // ------------------------------------------------------------------ start

  async function load() {
    try {
      S.me = await api("GET", "/me");
      try { S.studio = await api("GET", "/studio"); } catch (e) { S.studio = null; }
      render();
    } catch (e) {
      if (e.status === 401) showSignIn();
      else app.replaceChildren(el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" },
        el("form", null, el("h2", null, "Can't reach Swangz AI"), el("p", { class: "muted" }, e.message), el("button", { class: "btn", type: "button", onclick: load }, "Try again")))));
    }
  }

  function route() {
    const m = (location.hash || "").match(/^#\/welcome\/([A-Za-z0-9_\-]+)$/);
    if (m) return showWelcome(m[1]);
    return load();
  }

  window.addEventListener("hashchange", route);
  route();
})();
