"use strict";
/* Swangz AI — the staff app. One calm place to open the AI tools Swangz has given you, connect your
   devices, ask for more, and see plainly what the company records. Built on ui.js; anything typed is
   untrusted text and only ever lands in textContent. */
(() => {
  const { el, icon, fmt, toast, copy } = SUI;
  const app = document.getElementById("app");
  const S = { me: null, studio: null, filter: { q: "", cat: "all", sort: "recommended", show: "all" } };

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }
  // Served by the gateway, GATEWAY is "" (same origin). Hosted elsewhere (Netlify), config.js sets it.
  const GATEWAY = (typeof window !== "undefined" && window.SWANGZ_GATEWAY || "").replace(/\/+$/, "");
  const gurl = (path) => GATEWAY + path;

  async function api(method, path, body) {
    const opts = { method, credentials: "include", headers: { "x-swangz-app": "1" } };
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let res;
    try { res = await fetch(GATEWAY + "/api" + path, opts); }
    catch (e) { throw new ApiError(0, "Swangz AI can't be reached. Check your connection and try again."); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) throw new ApiError(res.status, (data && data.error) || "Something went wrong. Try again.");
    return data;
  }

  function greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  }
  const firstName = (name) => (name || "").split(/\s+/)[0] || name;

  function passwordInput(autocomplete, id) {
    const input = el("input", { class: "input", type: "password", autocomplete, required: true, id, minlength: autocomplete === "new-password" ? "10" : null });
    const reveal = el("button", { class: "btn btn--quiet reveal", type: "button", "aria-label": "Show password", "aria-pressed": "false",
      onclick: () => { const shown = input.type === "text"; input.type = shown ? "password" : "text"; reveal.textContent = shown ? "Show" : "Hide"; reveal.setAttribute("aria-pressed", shown ? "false" : "true"); } }, "Show");
    return { input, node: el("div", { class: "input-wrap" }, input, reveal) };
  }

  function codeBlock(text) {
    return el("div", { class: "code" }, el("pre", null, text), el("button", { class: "btn btn--small", type: "button", onclick: () => copy(text) }, icon("copy"), "Copy"));
  }

  function dialog(title, body, actions) {
    const id = "d-" + Math.random().toString(36).slice(2, 7);
    const d = el("dialog", { "aria-labelledby": id }, el("div", { class: "d-body" }, el("h2", { id }, title), typeof body === "string" ? el("p", null, body) : body),
      el("div", { class: "d-actions" }, actions(() => d.close())));
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }

  /* A side drawer: tool details, connecting a device. Focus stays inside; Escape closes it. */
  function drawer(label, onClose) {
    const scrim = el("div", { class: "scrim" });
    const node = el("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": label });
    let release = null;
    function close() {
      node.classList.remove("in"); scrim.classList.remove("in");
      setTimeout(() => { scrim.remove(); node.remove(); }, 320);
      document.removeEventListener("keydown", onKey);
      if (release) release();
      if (onClose) onClose();
    }
    function onKey(e) { if (e.key === "Escape" && !document.querySelector("dialog[open]")) close(); }
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.append(scrim, node);
    requestAnimationFrame(() => {
      scrim.classList.add("in"); node.classList.add("in"); release = SUI.trapFocus(node);
      const first = node.querySelector("input, .btn--solid, button"); if (first) first.focus({ preventScroll: true });
    });
    return { node, close };
  }

  // how a tool lets you in when you open it from here
  const HOW = {
    sso: ["Company sign-in", "Opens with your Swangz work account — no separate password."],
    seat: ["Company seat", "Your own seat on the company plan. Sign in with your work email; Swangz pays one bill."],
    own: ["Your own login", "You use your own account for this one. Swangz still controls access to it."],
    api: ["Company key", "Runs on the company's key through Swangz AI — nothing to sign in to."],
    shared: ["Shared account", "One company account the team takes turns on, so the credits it spends can be traced to whoever held it."],
    workspace: ["Company browser", "Opens a Swangz browser that's already signed in to this tool — your turn, nobody else's. You never see the password."],
  };
  const howOf = (t) => HOW[t.workspace ? "workspace" : t.kind === "dev" ? "api" : (t.signin || "seat")] || HOW.seat;

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
    const svgNode = document.createElementNS(ns, "svg");
    svgNode.setAttribute("viewBox", "0 0 48 48"); svgNode.setAttribute("width", "18"); svgNode.setAttribute("height", "18"); svgNode.setAttribute("aria-hidden", "true");
    [["#EA4335", "M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"],
      ["#4285F4", "M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"],
      ["#FBBC05", "M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"],
      ["#34A853", "M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"]]
      .forEach(([fill, d]) => { const p = document.createElementNS(ns, "path"); p.setAttribute("fill", fill); p.setAttribute("d", d); svgNode.append(p); });
    return svgNode;
  }
  async function googleButton(which, label) {
    const box = el("div", { class: "google-box" });
    if (GATEWAY) return box;
    try {
      const res = await fetch("/auth/options", { credentials: "include" });
      const opt = res.ok ? await res.json() : {};
      if (opt.google) box.append(el("a", { class: "btn btn--google btn--block", href: "/auth/google/start?app=" + which }, googleMark(), label),
        el("div", { class: "or" }, el("span", null, "or use your email")));
    } catch (e) { /* no Google button */ }
    return box;
  }

  // ------------------------------------------------------------------ the gate: sign in, welcome

  function gateArt() {
    return el("section", { class: "gate-art" },
      el("a", { class: "wordmark", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz ", el("b", null, "AI")),
      el("div", null,
        el("h1", { class: "gate-title" }, "Every AI tool. ", el("em", null, "One door.")),
        el("p", { class: "gate-lede" }, "The AI tools Swangz pays for, in one place. Open any of them with your work account — no personal subscriptions, no passwords to juggle."),
        el("ul", { class: "gate-points" },
          el("li", null, icon("tools"), "Your approved tools, ready to open"),
          el("li", null, icon("device"), "Connect your laptop and coding tools safely"),
          el("li", null, icon("shield"), "Clear about what's recorded, and why"))),
      el("div", { class: "gate-foot" }, el("span", null, "Swangz Avenue"), el("span", null, "Company access only")));
  }
  function gateFrame(form) {
    return el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" }, form,
      el("div", { class: "gate-theme" }, SUI.themeButton())));
  }

  function showSignIn() {
    document.title = "Sign in · Swangz AI";
    const email = el("input", { class: "input", type: "email", autocomplete: "email", required: true, placeholder: "you@swangzavenue.com", id: "si-email" });
    const pw = passwordInput("current-password", "si-pass");
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
    el("label", { class: "field", for: "si-email" }, el("span", null, "Work email"), email),
    el("label", { class: "field", for: "si-pass" }, el("span", null, "Password"), pw.node),
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
    const pw = passwordInput("new-password", "w-pass");
    const again = passwordInput("new-password", "w-again");
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
    el("label", { class: "field", for: "w-pass" }, el("span", null, "Choose a password (10+ characters)"), pw.node),
    el("label", { class: "field", for: "w-again" }, el("span", null, "Type it again"), again.node),
    err, go);
    app.replaceChildren(gateFrame(form));
    pw.input.focus();
  }

  // ------------------------------------------------------------------ the frame

  const NAV = [["#/", "Home", "home"], ["#/tools", "Tools", "tools"], ["#/studio", "Studio", "spark"], ["#/devices", "Devices", "device"],
    ["#/requests", "Requests", "inbox"], ["#/privacy", "Privacy", "shield"]];
  SUI.ICONS.inbox = SUI.ICONS.requests;
  const hasStudio = () => !!(S.studio && (S.studio.voice || S.studio.image || S.studio.video) && S.me.active);

  /* What a person should know about, worked out from their own account — never invented. */
  function notices() {
    const me = S.me;
    const out = [];
    const now = Date.now() / 1000;
    // `state` marks the notices that only restate where you stand — Home's hero says that already
    if (me.suspended) out.push({ tone: "bad", icon: "lock", title: "Your access is paused", text: "Talk to your admin to have it restored.", state: true });
    else if (me.paused) out.push({ tone: "warn", icon: "stop", title: "AI access is paused for everyone", text: "An admin has paused Swangz AI for now. Tools will open again when it's resumed.", state: true });
    if (me.access_until && me.access_until - now < 14 * 86400) out.push({ tone: "warn", icon: "calendar", title: "Your access ends " + fmt.date(me.access_until - 1),
      text: "Every tool and key stops working after that day. Ask your admin if you need longer." });
    me.catalog.filter((t) => t.turn && t.turn.mine).forEach((t) => out.push({ tone: "ok", icon: "hand", title: `You have ${t.name} until ${fmt.clock(t.turn.mine.expires)}`,
      text: "Hand it back when you're done so the next person can use the shared account.", tool: t }));
    me.catalog.filter((t) => t.state === "enabled" && t.ends && t.ends - now < 7 * 86400).forEach((t) => out.push({ tone: "warn", icon: "clock",
      title: `${t.name} ends ${fmt.date(t.ends - 1)}`, text: "Your access to this tool was given for a limited time.", tool: t }));
    (me.access_requests || []).filter((r) => r.decided && now - r.decided < 14 * 86400).forEach((r) => out.push(r.state === "granted"
      ? { tone: "ok", icon: "check", title: `${r.tool} was turned on for you`, text: "It's ready under Your tools.", when: r.decided }
      : { tone: "info", icon: "info", title: `Your request for ${r.tool} was declined`, text: r.decision_note || "Ask your admin if you'd like to know more.", when: r.decided }));
    if (me.budget && me.budget.monthly !== null && me.budget.month >= 0.8 * me.budget.monthly) out.push({ tone: "warn", icon: "wallet",
      title: me.budget.month >= me.budget.monthly ? "You've used this month's allowance" : "You're close to this month's allowance",
      text: `${fmt.money(me.budget.month)} of ${fmt.money(me.budget.monthly)}. It resets on the 1st.` });
    return out;
  }

  function frame(title, content, opts) {
    opts = opts || {};
    const me = S.me;
    document.title = (title ? title + " · " : "") + "Swangz AI";
    const section = "#/" + ((location.hash || "#/").split("?")[0].split("/")[1] || "");
    const active = section === "#/" ? "#/" : section;
    const nav = NAV.filter(([href]) => href !== "#/studio" || hasStudio());
    const count = notices().length;
    const menu = el("div", { class: "menu", role: "menu" },
      el("div", { class: "who" }, el("div", null, me.name), el("div", null, me.email)),
      el("button", { onclick: profile, role: "menuitem" }, icon("user"), "Profile"),
      el("button", { onclick: changePassword, role: "menuitem" }, icon("key"), "Change password"),
      el("a", { href: "#/privacy", role: "menuitem" }, icon("shield"), "How Swangz AI works"),
      el("button", { onclick: signOut, role: "menuitem" }, icon("logout"), "Sign out"));
    const meBtn = el("button", { class: "me-btn", "aria-haspopup": "menu", "aria-expanded": "false", "aria-label": "Your account",
      onclick: (e) => { e.stopPropagation(); const open = !menu.classList.contains("open"); menu.classList.toggle("open", open); meBtn.setAttribute("aria-expanded", open ? "true" : "false"); } },
    SUI.avatar(me.name, "sm"), el("span", { class: "me-name" }, firstName(me.name)), icon("chevronDown"));
    const topbar = el("header", { class: "topbar" }, el("div", { class: "inner" },
      el("a", { class: "wordmark", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz ", el("b", null, "AI")),
      el("nav", { class: "topnav", "aria-label": "Swangz AI" }, nav.map(([href, label]) => el("a", { href, class: href === active ? "on" : null, "aria-current": href === active ? "page" : null }, label))),
      el("div", { class: "top-right" },
        el("a", { class: "icon-btn", href: "#/requests?view=updates", "aria-label": count ? `${count} updates` : "Updates", "data-tip": count ? `${count} notification${count === 1 ? "" : "s"}` : "No new notifications" },
          icon("bell"), count ? el("span", { class: "dot-count" }, String(count)) : null),
        SUI.themeButton(), el("div", { class: "me-menu" }, meBtn, menu))));
    const tabbar = el("nav", { class: "tabbar", "aria-label": "Swangz AI" }, nav.filter(([href]) => href !== "#/studio").map(([href, label, ic]) =>
      el("a", { href, class: href === active ? "on" : null, "aria-current": href === active ? "page" : null }, icon(ic), el("span", null, label),
        href === "#/requests" && count ? el("i", { class: "dot-count" }, String(count)) : null)));
    const foot = el("footer", { class: "foot" }, el("div", { class: "inner" },
      el("span", { class: "brandline" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz Avenue · Swangz AI"),
      el("span", { class: "foot-links" }, el("a", { href: "#/privacy" }, "How Swangz AI works"), el("button", { type: "button", onclick: policy }, "Usage policy"))));
    app.replaceChildren(el("a", { class: "skip", href: "#main", onclick: (e) => { e.preventDefault(); document.getElementById("main").focus(); } }, "Skip to content"),
      topbar, el("main", { id: "main", tabindex: "-1", class: opts.cls || null }, content), foot, tabbar);
  }
  document.addEventListener("click", () => { const m = document.querySelector(".menu.open"); if (m) { m.classList.remove("open"); document.querySelector(".me-btn")?.setAttribute("aria-expanded", "false"); } });

  function sectionHead(eyebrow, title, text, action) {
    return el("div", { class: "section-head" }, el("div", null, eyebrow ? el("div", { class: "eyebrow" }, eyebrow) : null, el("h2", null, title), text ? el("p", null, text) : null), action || null);
  }

  /* Views of one page (?view=…): underlined tabs, arrow keys, a history entry per change. Every view is built at
     once and kept in the page, hidden when not chosen, so anything still working in one (a Studio job) carries on.
     views: [id, label, build, count?, onShow?] */
  function viewTabs(base, params, views, label, fallback) {
    views = views.filter(Boolean);
    const valid = (id) => views.some((v) => v[0] === id);
    let current = valid(params.get("view")) ? params.get("view") : valid(fallback) ? fallback : views[0][0];
    const uid = "vt" + Math.random().toString(36).slice(2, 7);
    const bar = el("div", { class: "vtabs", role: "tablist", "aria-label": label || "Views" });
    const body = el("div", { class: "vtab-body" });
    const panes = new Map();
    function show(id, push, focus) {
      current = id;
      bar.querySelectorAll("[role=tab]").forEach((b) => {
        const on = b.dataset.view === id;
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        if (on && focus) b.focus();
      });
      panes.forEach((pane, key) => { pane.hidden = key !== id; });
      const view = views.find((v) => v[0] === id);
      if (view[4]) view[4]();
      const q = new URLSearchParams(location.hash.split("?")[1] || "");
      q.set("view", id);
      const target = base + "?" + q.toString();
      if (target !== location.hash) history[push ? "pushState" : "replaceState"](null, "", target);
    }
    bar.replaceChildren(...views.map(([id, text, , count]) => el("button", { type: "button", role: "tab", id: `${uid}-${id}`, "aria-controls": `${uid}-${id}-panel`, "data-view": id,
      onclick: () => { if (id !== current) show(id, true); } }, el("span", null, text), count ? el("span", { class: "vt-n" }, String(count)) : null)));
    bar.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const i = views.findIndex((v) => v[0] === current);
      const next = e.key === "Home" ? 0 : e.key === "End" ? views.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + views.length) % views.length;
      show(views[next][0], true, true);
    });
    views.forEach(([id, , build]) => {
      const pane = el("div", { class: "vtab-pane", role: "tabpanel", id: `${uid}-${id}-panel`, "aria-labelledby": `${uid}-${id}`, tabindex: "-1" });
      pane.append(...[].concat(build()).filter(Boolean));
      panes.set(id, pane);
      body.append(pane);
    });
    show(current, false);
    return { node: el("div", { class: "vtabs-wrap" }, bar, body), show };
  }

  // ------------------------------------------------------------------ tool tiles

  function tileStatus(t) {
    const me = S.me;
    if (!me.active || t.state === "suspended") return SUI.status("suspended", "Paused", { plain: true });
    if (t.state === "enabled") {
      if (t.turn && t.turn.mine) return SUI.status("live", "Yours until " + fmt.clock(t.turn.mine.expires), { plain: true, breathe: true });
      if (t.turn && !t.turn.free) {
        const soonest = t.turn.others.slice().sort((a, b) => a.expires - b.expires)[0];
        return SUI.status("waiting", `In use — free at ${fmt.clock(soonest.expires)}`, { plain: true });
      }
      return SUI.status("ready", "Ready", { plain: true });
    }
    if (t.pending) return SUI.status("pending", "Requested", { plain: true });
    if (t.state === "not_assigned") return SUI.status("none", "Not assigned", { plain: true });
    if (t.state === "past_due") return SUI.status("waiting", "Renewal due", { plain: true });
    return SUI.status("none", "Not on the company plan", { plain: true });
  }
  function tileNote(t) {
    if (t.state === "enabled") {
      if (t.turn && t.turn.mine) return "Hand it back when you're done.";
      if (t.turn && !t.turn.free) return `${t.turn.others[0].person} has the shared account.`;
      if (t.ends) return "Yours until " + fmt.date(t.ends - 1);
      if (t.kind === "dev") return t.connected ? "Connected on " + SUI.plural(t.connected, "device") : "Set up once on each device";
      return t.last_opened ? "Opened " + fmt.ago(t.last_opened) : "Not opened yet";
    }
    if (t.pending) return "An admin will review your request.";
    if (t.state === "not_assigned") return "Your administrator hasn't enabled this tool for you.";
    if (t.state === "past_due") return "The company subscription needs renewing.";
    if (t.state === "locked") return "Swangz isn't subscribed to it yet — you can still ask.";
    return t.reason || "";
  }

  const TOOL_TO_GUIDE = { "claude-code": "claude-code", codex: "codex", claude: "anthropic-sdk", chatgpt: "openai-compatible", elevenlabs: "elevenlabs", "higgsfield-ai": "higgsfield" };
  const STUDIO_TOOLS = { elevenlabs: "voice", "higgsfield-ai": "image" };
  const guideFor = (t) => { const id = TOOL_TO_GUIDE[t.id]; return id && (S.me.connect || []).find((g) => g.id === id); };

  function openLink(t, label, solid) {
    return el("a", { class: "btn btn--small" + (solid ? " btn--solid" : ""), href: gurl("/go/" + t.id), target: "_blank", rel: "noopener",
      "aria-label": `${label} ${t.name} (opens in a new tab)`, onclick: () => opened(t) }, label, icon("open"));
  }

  function tileActions(t) {
    const me = S.me;
    if (!me.active || t.state === "suspended") return [];
    if (t.state !== "enabled") {
      if (t.pending) return [el("span", { class: "requested" }, icon("check"), "Requested")];
      return [el("button", { class: "btn btn--small", type: "button", onclick: () => requestAccess(t) }, t.state === "past_due" ? "Ask to renew" : "Request access")];
    }
    const guide = guideFor(t);
    if (t.id in STUDIO_TOOLS && S.studio && S.studio[STUDIO_TOOLS[t.id]]) return [el("a", { class: "btn btn--small btn--solid", href: "#/studio" }, icon("spark"), "Open Studio")];
    if (t.kind === "dev") return guide && me.can_add_keys ? [el("button", { class: "btn btn--small btn--solid", type: "button", onclick: () => connect(guide) }, icon("link"), "Connect")] : [];
    if (t.turn) {
      if (t.turn.mine) return [el("button", { class: "btn btn--small btn--quiet", type: "button", onclick: () => handBack(t) }, "Hand back"), openLink(t, "Open", true)];
      if (!t.turn.free) return [el("button", { class: "btn btn--small", disabled: true }, "In use")];
      return [openLink(t, "Take your turn", true)];
    }
    return t.launchable ? [openLink(t, "Open", true)] : guide && me.can_add_keys ? [el("button", { class: "btn btn--small btn--solid", type: "button", onclick: () => connect(guide) }, "Connect")] : [];
  }

  // one line per tool the person doesn't have: what it is, where it stands, and the one thing to do
  function toolRow(t) {
    const act = tileActions(t).map((b) => { if (b.classList.contains("btn")) { b.classList.add("btn--quiet"); if (b.textContent === "Request access") b.textContent = "Request"; } return b; });
    return el("li", { class: "tool-row s-" + t.state },
      el("button", { class: "tr-main", type: "button", onclick: () => details(t), "aria-label": `${t.name} — details` },
        SUI.logo(t, "sm"), el("span", { class: "tr-text" }, el("strong", null, t.name), el("span", { class: "tr-sub" }, t.category, el("span", { class: "dot", "aria-hidden": "true" }),
          t.state === "locked" && !t.pending ? SUI.status("none", "Not on the plan", { plain: true }) : tileStatus(t)))),
      act.length ? el("div", { class: "tr-act" }, act) : null);
  }
  function tile(t) {
    const how = howOf(t);
    const ready = t.state === "enabled";
    const cls = "tile s-" + t.state + (t.turn && t.turn.mine ? " holding" : t.turn && !t.turn.free ? " busy" : "");
    return el("article", { class: cls },
      el("button", { class: "tile-main", type: "button", onclick: () => details(t), "aria-label": `${t.name} — details` },
        el("div", { class: "tile-top" }, SUI.logo(t), el("div", { class: "grow" }, el("h3", null, t.name), el("div", { class: "cat" }, t.category))),
        el("div", { class: "tile-status" }, tileStatus(t)),
        ready ? el("p", { class: "tile-desc" }, t.description || "Ready for you to use at work.") : el("p", { class: "tile-desc" }, tileNote(t))),
      el("div", { class: "tile-foot" },
        ready ? el("div", { class: "tile-meta" }, el("span", { class: "how", "data-tip": how[1], tabindex: "0" }, icon("shield"), how[0]),
          el("span", { class: "when" }, tileNote(t))) : el("span", { class: "tile-meta" }),
        el("div", { class: "tile-actions" }, tileActions(t))));
  }

  function opened(t) {
    t.last_opened = Date.now() / 1000;
    setTimeout(() => { if (!document.querySelector("dialog, .drawer")) load(); }, 900);
  }

  async function handBack(t) {
    try { await api("POST", `/tools/${t.id}/turn/end`); toast("Handed back. Your browser is being signed out of it."); load(); }
    catch (e) { toast(e.message, true); }
  }

  async function requestAccess(t) {
    const reason = el("textarea", { class: "input area", rows: "3", placeholder: "Optional — what do you need it for?", "aria-label": "What do you need it for?" });
    const err = el("div", { class: "form-error", role: "alert" });
    dialog("Request " + t.name, el("div", { class: "fields" },
      el("p", null, t.state === "locked" ? `Swangz isn't subscribed to ${t.name} yet. Your request tells an admin it's needed.` : `An admin will see this and can turn ${t.name} on for you.`),
      reason, err),
    (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
      el("button", { class: "btn btn--solid", onclick: async () => {
        try { await api("POST", `/tools/${t.id}/request`, { reason: reason.value }); close(); toast("Request sent."); load(); }
        catch (e) { err.textContent = e.message; } } }, icon("send"), "Send request")]);
  }

  /* Everything about one tool: what it does, why you have it (or don't), how sign-in works, who
     manages it, your own recent use, and what's recorded when you use it. */
  function details(t) {
    const me = S.me;
    const how = howOf(t);
    const { node, close } = drawer(t.name + " details", () => { if (location.hash.includes("open=")) history.replaceState(null, "", location.hash.split("?")[0]); });
    const why = t.state === "enabled"
      ? (t.grant === "team" ? `Your team${me.department ? " (" + me.department + ")" : ""} has it, so you do too.` : "An administrator turned it on for you.")
        + (t.kind === "site" ? " Swangz pays for a company plan." : " It runs on the company's key — nothing for you to pay.")
      : t.pending ? "You've asked for it — an admin will decide."
        : t.state === "not_assigned" ? "Swangz has it, but your administrator hasn't enabled it for you. You can ask."
          : t.state === "locked" ? "Swangz isn't subscribed to this tool yet. If you need it, ask — your request tells an admin."
            : t.reason;
    const recorded = t.kind === "site"
      ? "That you opened or visited it, when, and for how long — never what's on the page or what you type."
      : "Each request, on the company key: who, which device and app, the model, what you typed and what came back, and the cost.";
    const manages = "Your Swangz administrators decide who has which tool." + (me.privacy && me.privacy.support_contact ? " For help: " + me.privacy.support_contact + "." : "");
    const section = (title, ...body) => el("section", { class: "d-sec" }, el("h3", null, title), ...body);
    node.append(
      el("header", null,
        el("div", { class: "d-id" }, SUI.logo(t, "lg"), el("div", null, el("div", { class: "eyebrow" }, t.category), el("h2", null, t.name), tileStatus(t))),
        el("button", { class: "btn btn--quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x"))),
      el("div", { class: "body" },
        section("What it does", el("p", null, t.description || "An AI tool in the Swangz catalog.")),
        section(t.state === "enabled" ? "Why you have it" : "Why you don't have it yet", el("p", null, why), el("p", { class: "muted" }, manages)),
        section("How you sign in", el("p", null, el("strong", null, how[0] + ". "), how[1]),
          t.turn ? el("p", { class: "muted" }, `One person at a time${t.turn.seats > 1 ? ` (up to ${t.turn.seats})` : ""}, for up to ${t.turn.minutes} minutes a turn. When your turn ends, the Swangz extension signs your browser out of it.`) : null),
        t.state === "enabled" ? section("Your use", el("dl", { class: "facts" },
          t.kind === "dev" ? [el("dt", null, "Connected on"), el("dd", null, SUI.plural(t.connected || 0, "device"))]
            : [el("dt", null, "Last opened"), el("dd", null, t.last_opened ? fmt.ago(t.last_opened) : "never"),
              el("dt", null, "Opened · 30 days"), el("dd", null, SUI.plural(t.opens_30d || 0, "time"))],
          t.ends ? [el("dt", null, "Access ends"), el("dd", null, fmt.date(t.ends - 1))] : null)) : null,
        section("What's recorded", el("p", { class: "muted" }, recorded, " ", el("a", { class: "tlink", href: "#/privacy", onclick: close }, "How Swangz AI works")))),
      el("footer", null, el("button", { class: "btn btn--quiet", onclick: close }, "Close"), tileActions(t).map((b) => { b.classList.remove("btn--small"); return b; })));
  }

  // ------------------------------------------------------------------ Home

  /* Home: a personal launchpad. The hero says where you stand and holds the one thing to do next — usually going
     back to the tool you opened last, through the same /go/ launch as everywhere else. Below it, your other tools;
     beside them, what has changed and the places you need now and then. Every value is real: nothing is guessed or
     padded out, and a tool never appears twice. */
  function pageHome() {
    const me = S.me;
    const catalog = me.catalog;
    const enabled = catalog.filter((t) => t.state === "enabled");
    const pending = catalog.filter((t) => t.pending).length;
    const byRecent = enabled.slice().sort((a, b) => (b.last_opened || 0) - (a.last_opened || 0) || a.name.localeCompare(b.name));
    // the tool to go back to: the one opened most recently from here — or, when it is the only one, that one
    const lead = me.active ? byRecent.find((t) => t.last_opened) || (enabled.length === 1 ? enabled[0] : null) : null;
    const others = byRecent.filter((t) => t !== lead);
    const shown = others.slice(0, lead ? 5 : 6);
    const updates = notices().filter((n) => !n.state);
    const activeKeys = me.keys.filter((k) => !k.revoked);
    const contact = me.privacy && me.privacy.support_contact;
    const toolsBox = el("section", { class: "home-tools", id: "home-tools", tabindex: "-1", "aria-labelledby": "home-tools-h" });

    // --- the hero: where you stand, and the one thing to do next
    let headline, text = null, action = null, extra = null;
    if (me.suspended) {
      headline = "Your access is paused.";
      text = "Your tools and devices can't be used until an admin restores your access. " + (contact ? "For help: " + contact + "." : "Talk to your admin.");
    } else if (me.paused) {
      headline = "AI is paused for now.";
      text = "An admin has paused Swangz AI for everyone. Your tools open again as soon as it's resumed — there's nothing you need to do.";
    } else if (lead) {
      headline = lead.last_opened ? "Pick up where you left off." : "Your AI workspace is ready.";
      const how = howOf(lead);
      action = el("div", { class: "resume" + (lead.turn && lead.turn.mine ? " holding" : "") },
        el("button", { class: "resume-id", type: "button", onclick: () => details(lead), "aria-label": `${lead.name} — details` }, SUI.logo(lead, "lg"),
          el("span", { class: "resume-text" },
            el("span", { class: "resume-k" }, lead.last_opened ? "Opened " + fmt.ago(lead.last_opened) : enabled.length === 1 ? "Your approved tool" : "Ready for you"),
            el("strong", null, lead.name),
            el("span", { class: "resume-sub" }, tileStatus(lead), el("span", { class: "dot", "aria-hidden": "true" }), how[0]))),
        el("div", { class: "resume-act" }, tileActions(lead)));
      if (enabled.length > 1) extra = el("a", { class: "hero-link", href: "#/tools?show=mine" }, "All your tools", icon("chevronRight"));
    } else if (enabled.length) {
      headline = "Your AI workspace is ready.";
      text = "Paid for by Swangz and ready when you are — choose one to start.";
      action = el("button", { class: "btn btn--solid", type: "button", onclick: () => { toolsBox.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); toolsBox.focus({ preventScroll: true }); } },
        "Choose a tool", icon("arrowDown"));
    } else {
      headline = "Nothing is switched on for you yet.";
      text = "Find what you need in the catalogue and ask for it. An admin decides, and the tool appears here when it's on.";
      action = el("a", { class: "btn btn--solid", href: "#/tools" }, "Browse the catalogue", icon("chevronRight"));
      if (pending) extra = el("a", { class: "hero-link", href: "#/requests?view=access" }, SUI.plural(pending, "request") + " waiting for an admin", icon("chevronRight"));
    }
    const standing = me.active ? SUI.status("ready", "Access active", { plain: true })
      : me.suspended ? SUI.status("suspended", "Access paused", { plain: true }) : SUI.status("waiting", "Paused for everyone", { plain: true });
    const hero = el("section", { class: "hero art home-hero" + (me.active ? "" : " blocked") }, el("div", { class: "shell" },
      el("div", { class: "eyebrow" }, `${greeting()}, ${firstName(me.name)}`),
      el("h1", null, headline),
      el("p", { class: "hero-meta" }, standing, me.active && enabled.length ? [el("span", { class: "sep", "aria-hidden": "true" }),
        el("span", null, el("b", null, String(enabled.length)), enabled.length === 1 ? " tool ready" : " tools ready")] : null),
      text ? el("p", { class: "home-lede" }, text) : null,
      action || extra ? el("div", { class: "home-act" }, action, extra) : null));

    // --- your tools: the rest of what is switched on, a bounded few; the catalogue holds everything
    if (me.suspended) toolsBox.remove();
    else if (enabled.length) {
      const more = enabled.length - (lead ? 1 : 0) - shown.length;
      toolsBox.append(...(shown.length ? [
        el("div", { class: "home-h" }, el("h2", { id: "home-tools-h" }, lead ? "Your other tools" : "Your tools"),
          el("a", { class: "tlink", href: more > 0 ? "#/tools?show=mine" : "#/tools" }, more > 0 ? `${more} more in Tools` : "Browse the catalogue", icon("chevronRight"))),
        el("div", { class: "tcards" }, shown.map(toolCard))]
        // only one tool is on: say so once, with the way to ask for another
        : [el("div", { class: "home-h" }, el("h2", { id: "home-tools-h" }, "Need another tool?")),
          el("div", { class: "home-note" }, icon("info"), el("span", null, `${lead.name} is the only tool switched on for you. Everything else Swangz offers is in the catalogue — `,
            el("a", { href: "#/tools?show=others" }, "ask for what you need"), "."))]));
    } else {
      toolsBox.append(el("div", { class: "home-h" }, el("h2", { id: "home-tools-h" }, "How you get a tool")),
        el("ol", { class: "home-steps" },
          el("li", null, el("strong", null, "Find it"), el("span", null, "Everything Swangz offers is in the catalogue, with what each tool is for.")),
          el("li", null, el("strong", null, "Ask for it"), el("span", null, "Say what you need it for — an admin sees your request.")),
          el("li", null, el("strong", null, "Open it here"), el("span", null, "Once it's turned on, it appears on this page, ready to open."))));
    }

    // --- beside the tools: what has changed, your allowance, Studio, and the places you need now and then
    const updatesBox = el("section", { class: "home-card", "aria-labelledby": "home-up-h" },
      el("div", { class: "home-h small" }, el("h2", { id: "home-up-h" }, "Updates"),
        updates.length ? el("a", { class: "tlink", href: "#/requests?view=updates" }, updates.length > 3 ? `All ${updates.length}` : "All updates", icon("chevronRight")) : null),
      updates.length ? el("ul", { class: "home-updates" }, updates.slice(0, 3).map(updateItem))
        : el("div", { class: "home-quiet" }, el("span", { class: "n-ic ok", "aria-hidden": "true" }, icon("check")),
          el("div", null, el("strong", null, "You're all caught up"), el("p", null, "Tools turned on for you, decisions on your requests and access dates appear here."))));
    const allowance = me.budget && me.budget.monthly !== null && me.budget.monthly !== undefined ? el("section", { class: "home-card", "aria-labelledby": "home-al-h" },
      el("div", { class: "home-h small" }, el("h2", { id: "home-al-h" }, "Your allowance")),
      el("div", { class: "home-allow" }, el("strong", null, fmt.money(me.budget.month)), el("span", null, "of " + fmt.money(me.budget.monthly) + " this month")),
      meter(me.budget.month, me.budget.monthly), el("p", { class: "home-fine" }, "AI used through Swangz AI on the company's account. It resets on the 1st.")) : null;
    const studio = hasStudio() ? el("a", { class: "home-studio", href: "#/studio" }, el("span", { class: "home-studio-ic", "aria-hidden": "true" }, icon("spark")),
      el("span", { class: "grow" }, el("strong", null, "Studio"), el("span", null, "Make voice-overs, images and video here, on the company's account.")), icon("chevronRight")) : null;
    const links = el("nav", { class: "home-links", "aria-label": "More in Swangz AI" },
      el("a", { href: "#/devices" }, icon("device"), el("span", null, el("strong", null, "My devices"),
        el("span", null, activeKeys.length ? SUI.plural(activeKeys.length, "device") + " connected" : me.active ? "Connect your laptop or coding tools" : "None connected")), icon("chevronRight")),
      el("a", { href: "#/requests?view=access" }, icon("send"), el("span", null, el("strong", null, "Access requests"),
        el("span", null, pending ? SUI.plural(pending, "request") + " waiting for an admin" : me.active ? "Ask for any tool in the catalogue" : "What you've asked for")), icon("chevronRight")),
      el("a", { href: "#/privacy" }, icon("shield"), el("span", null, el("strong", null, "How Swangz AI works"), el("span", null, "What's recorded, and what isn't")), icon("chevronRight")));
    const aside = el("aside", { class: "home-aside", "aria-label": "Updates and more" }, updatesBox, allowance, studio, links);
    frame("Home", [hero, el("section", { class: "section home-body" }, el("div", { class: "shell home-grid" + (me.suspended ? " solo" : "") }, me.suspended ? null : toolsBox, aside))]);
  }

  /* One of your tools, compact: who it is, where it stands, and its one action. Select it for the details. */
  function toolCard(t) {
    const act = tileActions(t);
    return el("article", { class: "tcard s-" + t.state + (t.turn && t.turn.mine ? " holding" : "") },
      el("button", { class: "tcard-main", type: "button", onclick: () => details(t), "aria-label": `${t.name} — details` },
        SUI.logo(t), el("span", { class: "tcard-text" }, el("strong", null, t.name), el("span", null, t.category))),
      el("p", { class: "tcard-desc" }, t.description || tileNote(t)),
      el("div", { class: "tcard-foot" }, el("span", { class: "tcard-state" }, tileStatus(t), el("span", { class: "tcard-note" }, tileNote(t))),
        act.length ? el("div", { class: "tcard-act" }, act) : null));
  }

  /* An update on Home: short, with its own action when it has one (hand a shared account back). */
  function updateItem(n) {
    return el("li", { class: "home-update n-" + n.tone }, el("span", { class: "n-ic", "aria-hidden": "true" }, icon(n.icon)),
      el("div", { class: "grow" }, el("strong", null, n.title), el("p", null, n.text),
        n.tool && n.tool.turn && n.tool.turn.mine ? el("button", { class: "btn btn--small", type: "button", onclick: () => handBack(n.tool) }, "Hand back") : null),
      n.when ? el("span", { class: "faint small nowrap" }, fmt.ago(n.when)) : null);
  }

  function noticeItem(n) {
    return el("li", { class: "notice-item n-" + n.tone }, el("span", { class: "n-ic" }, icon(n.icon)),
      el("div", { class: "grow" }, el("strong", null, n.title), el("p", null, n.text)),
      n.tool && n.tool.turn && n.tool.turn.mine ? el("button", { class: "btn btn--small", onclick: () => handBack(n.tool) }, "Hand back") : n.when ? el("span", { class: "faint small" }, fmt.ago(n.when)) : null);
  }

  function meter(value, limit) {
    const fill = el("i");
    fill.style.width = Math.min(100, (value / (limit || 1)) * 100) + "%";
    return el("div", { class: "meter" + (value >= limit ? " full" : ""), role: "meter", "aria-valuenow": String(value), "aria-valuemin": "0", "aria-valuemax": String(limit), "aria-label": "Allowance used" }, fill);
  }

  // ------------------------------------------------------------------ All tools

  function pageTools(params) {
    const me = S.me;
    const catalog = me.catalog;
    const f = S.filter;
    if (params.get("q")) f.q = params.get("q");
    if (["all", "mine", "others"].includes(params.get("show"))) f.show = params.get("show");
    const cats = ["all", ...Array.from(new Set(catalog.map((t) => t.category))).sort()];
    const grid = el("div", { class: "cat-parts" });
    const count = el("p", { class: "count", role: "status" });
    const search = el("input", { class: "input search", type: "search", placeholder: "Search AI tools…", value: f.q, "aria-label": "Search AI tools" });
    const chips = el("div", { class: "chips-row", role: "group", "aria-label": "Category" });
    const sort = el("select", { class: "input select", "aria-label": "Sort" }, el("option", { value: "recommended" }, "Recommended"), el("option", { value: "recent" }, "Recently used"), el("option", { value: "az" }, "A–Z"));
    sort.value = f.sort;
    const show = el("div", { class: "u-seg", role: "group", "aria-label": "Show" });
    function drawChips() {
      chips.replaceChildren(...cats.map((c) => el("button", { class: "chip" + (f.cat === c ? " on" : ""), type: "button", "aria-pressed": f.cat === c ? "true" : "false",
        onclick: () => { f.cat = c; drawChips(); draw(); } }, c === "all" ? "All" : c)));
    }
    function drawShow() {
      show.replaceChildren(...[["all", "Everything"], ["mine", "Available to me"], ["others", "Others"]].map(([v, label]) => el("button", { type: "button", "aria-pressed": f.show === v ? "true" : "false",
        onclick: () => { f.show = v; drawShow(); draw(); } }, label)));
    }
    const rank = { enabled: 0, not_assigned: 1, past_due: 2, locked: 3, suspended: 4 };
    function draw() {
      const q = f.q.trim().toLowerCase();
      let list = catalog.filter((t) => (f.cat === "all" || t.category === f.cat) && (!q || [t.name, t.category, t.description].join(" ").toLowerCase().includes(q)));
      if (f.show === "mine") list = list.filter((t) => t.state === "enabled");
      if (f.show === "others") list = list.filter((t) => t.state !== "enabled");
      list.sort(f.sort === "az" ? (a, b) => a.name.localeCompare(b.name)
        : f.sort === "recent" ? (a, b) => (b.last_opened || 0) - (a.last_opened || 0) || a.name.localeCompare(b.name)
          : (a, b) => (rank[a.state] - rank[b.state]) || (b.last_opened || 0) - (a.last_opened || 0) || a.name.localeCompare(b.name));
      // Yours as full cards; everything else as a compact list, so the catalogue isn't a wall of identical cards.
      const ready = list.filter((t) => t.state === "enabled");
      const rest = list.filter((t) => t.state !== "enabled");
      const part = (title, n, sub, body) => el("section", { class: "cat-part" }, el("div", { class: "cat-part-h" }, el("h3", null, title, el("span", { class: "n" }, String(n))), sub ? el("span", { class: "muted small" }, sub) : null), body);
      grid.replaceChildren(...(list.length ? [
        ready.length ? part("Yours", ready.length, "Paid for by Swangz and ready to open.", el("div", { class: "grid-tiles" }, ready.map(tile))) : null,
        rest.length ? part(ready.length ? "Everything else" : "Tools you can ask for", rest.length, "Ask, and an admin can turn it on for you.", el("ul", { class: "tool-rows" }, rest.map(toolRow))) : null,
      ].filter(Boolean) : [el("div", { class: "empty" }, el("h3", null, "No tools match"), el("p", null, "Try another search or category."))]));
      count.textContent = `${SUI.plural(list.length, "tool")}${f.cat !== "all" ? " in " + f.cat : ""}` + (ready.length && rest.length ? ` · ${ready.length} yours` : "");
    }
    search.addEventListener("input", () => { f.q = search.value; draw(); });
    sort.addEventListener("change", () => { f.sort = sort.value; draw(); });
    drawChips(); drawShow(); draw();
    frame("Tools", el("section", { class: "section first" }, el("div", { class: "shell" },
      sectionHead("The catalog", "AI tools at Swangz", "Everything the company offers. Open what's yours; ask for anything else and an admin can turn it on."),
      el("div", { class: "toolbar" }, el("div", { class: "search-wrap" }, icon("search"), search, el("kbd", null, "/")), show, el("label", { class: "sort" }, el("span", { class: "u-sr" }, "Sort"), sort)),
      chips, count, grid)));
    const open = params.get("open");
    const t = open && catalog.find((x) => x.id === open);
    if (t) details(t);
  }

  // ------------------------------------------------------------------ Studio

  const TYPE_LABEL = { voice: "Voice-over", image: "Image", video: "Video", sound: "Sound", music: "Music", transcription: "Transcript" };
  const JOBS = new Map();

  /* Studio: Create (only what's switched on for them) and Your creations. Something just made shows under the form
     until they look at Your creations, where it then joins the rest. */
  function pageStudio(params) {
    if (!hasStudio()) { location.hash = "#/"; return; }
    const st = S.studio;
    const kinds = [["voice", "Voice-over", st.voice], ["image", "Image", st.image], ["video", "Video", st.video]].filter((t) => t[2]);
    const panel = el("div", { class: "studio-panel" });
    let kind = kinds[0][0];
    const kindSeg = el("div", { class: "u-seg", role: "group", "aria-label": "What to make" });
    const drawKinds = () => kindSeg.replaceChildren(...kinds.map(([id, label]) => el("button", { type: "button", "aria-pressed": id === kind ? "true" : "false",
      onclick: () => { kind = id; drawKinds(); show(id); } }, label)));
    const creations = el("div", { class: "creations" });
    const justMade = el("div", { class: "creations just-made" });
    /* What it's for, if they want to say. Optional; it is recorded as their own word (declared), not a guess. */
    function purposeField() {
      const sel = el("select", { class: "input" }, el("option", { value: "" }, "Not saying"), (st.purposes || []).map((p) => el("option", { value: p.id }, p.name)));
      try { sel.value = localStorage.getItem("swangz-studio-purpose") || ""; } catch (e) { /* no storage */ }
      sel.addEventListener("change", () => { try { localStorage.setItem("swangz-studio-purpose", sel.value); } catch (e) { /* no storage */ } });
      return { sel, node: el("label", { class: "field" }, el("span", null, "What it's for (optional)"), sel) };
    }
    function show(id) {
      panel.replaceChildren(id === "voice" ? voiceForm() : visualForm(id));
    }
    function voiceForm() {
      const voice = el("select", { class: "input" }, st.voices.map((v) => el("option", { value: v.id }, v.name + (v.about ? ` — ${v.about}` : ""))));
      const model = el("select", { class: "input" }, st.voice_models.map((m) => el("option", { value: m.id }, m.name)));
      const text = el("textarea", { class: "input area", rows: "5", maxlength: "5000", placeholder: "Type the script — for example: Swangz Avenue presents the December Showcase, live at Serena Kampala." });
      const count = el("span", { class: "muted small" }, "0 / 5,000");
      text.addEventListener("input", () => { count.textContent = `${text.value.length.toLocaleString()} / 5,000`; });
      const err = el("div", { class: "form-error", role: "alert" });
      const purpose = purposeField();
      const go = el("button", { class: "btn btn--solid", type: "submit" }, "Make the voice-over");
      return el("form", { class: "studio-form", onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = ""; go.disabled = true; go.textContent = "Making it…";
        try { const made = await api("POST", "/studio/voice", { text: text.value, voice_id: voice.value, model_id: model.value, purpose: purpose.sel.value }); addCreation(made, true); text.value = ""; count.textContent = "0 / 5,000"; }
        catch (x) { err.textContent = x.message; }
        go.disabled = false; go.textContent = "Make the voice-over";
      } },
      st.voices.length ? null : el("div", { class: "notice" }, "No voices are available yet — ask your admin."),
      el("div", { class: "form-row" }, el("label", { class: "field" }, el("span", null, "Voice"), voice), el("label", { class: "field" }, el("span", null, "Quality"), model)),
      el("label", { class: "field" }, el("span", null, "Script"), text), purpose.node, el("div", { class: "spread" }, count, go), err);
    }
    function visualForm(kind) {
      const prompt = el("textarea", { class: "input area", rows: "4", placeholder: kind === "image"
        ? "Describe the picture — for example: a moody poster of a live band on stage at night, Kampala skyline behind, warm amber lights."
        : "Describe the motion — for example: slow push-in on the singer, haze drifting, lights flicker." });
      const aspect = el("select", { class: "input" }, ["16:9", "9:16", "1:1", "4:5"].map((a) => el("option", { value: a }, a)));
      const image = el("input", { class: "input", type: "url", placeholder: "https://… link to the starting picture" });
      const err = el("div", { class: "form-error", role: "alert" });
      const label = kind === "image" ? "Make the image" : "Make the video";
      const purpose = purposeField();
      const go = el("button", { class: "btn btn--solid", type: "submit" }, label);
      return el("form", { class: "studio-form", onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = ""; go.disabled = true; go.textContent = "Starting…";
        try { const made = await api("POST", "/studio/generate", { kind, prompt: prompt.value, aspect_ratio: aspect.value, image_url: image.value, purpose: purpose.sel.value }); addCreation(made, true); prompt.value = ""; }
        catch (x) { err.textContent = x.message; }
        go.disabled = false; go.textContent = label;
      } },
      kind === "video" ? el("label", { class: "field" }, el("span", null, "Starting picture"), image, el("span", { class: "muted small" }, "Make an image first and copy its link, or use any picture that's online.")) : null,
      el("label", { class: "field" }, el("span", null, kind === "image" ? "What should it show?" : "What should happen?"), prompt), purpose.node,
      el("div", { class: "spread" }, kind === "image" ? el("label", { class: "field inline" }, el("span", null, "Shape"), aspect) : el("span"), go), err);
    }
    function addCreation(c, fresh) {
      const card = creationCard(c);
      if (fresh) { card.classList.add("fresh"); justMade.prepend(card); justHead.hidden = false; }
      else creations.prepend(card);
      emptyNote.hidden = true;
      if (c.job && !c.urls.length && c.outcome === "ok") JOBS.set(c.job, card);
      if (fresh) resumeJobs();
    }
    // looking at Your creations moves what was just made to the top of the list (the same cards, still updating)
    function gather() {
      [...justMade.children].reverse().forEach((card) => { card.classList.remove("fresh"); creations.prepend(card); });
      justHead.hidden = true;
    }
    const emptyNote = el("div", { class: "empty" }, el("h3", null, "Nothing made yet"), el("p", null, "What you make in Create shows up here, so you can play it again or download it."));
    const justHead = el("div", { class: "spread just-head", hidden: true }, el("h3", { class: "sub-head" }, "Just made"),
      el("button", { class: "btn btn--small btn--quiet", type: "button", onclick: () => views.show("mine", true) }, "All your creations", icon("chevronRight")));
    st.recent.slice().reverse().forEach((c) => addCreation(c, false));
    emptyNote.hidden = st.recent.length > 0;
    drawKinds(); show(kind);
    const views = viewTabs("#/studio", params, [
      ["create", "Create", () => [kinds.length > 1 ? kindSeg : null, el("div", { class: "studio" }, panel), justHead, justMade]],
      ["mine", "Your creations", () => [emptyNote, creations], st.recent.length || null, gather],
    ], "Studio");
    frame("Studio", el("section", { class: "section first" }, el("div", { class: "shell" },
      sectionHead("Create", "Studio", "Voice-overs, images and video in the browser — on the company's account, nothing to install. What you make here is recorded like any request through Swangz AI."),
      views.node)));
    resumeJobs();
  }

  function creationCard(c) {
    const body = el("div", { class: "creation-media" });
    fillCreation(body, c);
    return el("article", { class: "creation", "data-id": String(c.id) }, body,
      el("div", { class: "creation-meta" },
        el("div", { class: "spread" }, el("span", { class: "eyebrow" }, TYPE_LABEL[c.type] || "Creation"), el("span", { class: "muted small" }, fmt.ago(c.ts))),
        c.prompt ? el("p", { class: "creation-prompt" }, c.prompt) : null));
  }
  function fillCreation(body, c) {
    if (c.outcome && c.outcome !== "ok") body.replaceChildren(el("div", { class: "creation-state bad" }, c.reason || "This one didn't work."));
    else if (c.audio) body.replaceChildren(el("audio", { controls: true, preload: "none", src: gurl(c.audio), crossorigin: GATEWAY ? "use-credentials" : null }),
      el("a", { class: "btn btn--small", href: gurl(c.audio), download: "swangz-voice-" + c.id + ".mp3" }, icon("download"), "Download"));
    else if (c.urls && c.urls.length) {
      const u = c.urls[0];
      const media = c.type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(u) ? el("video", { controls: true, preload: "metadata", src: u, playsinline: true })
        : el("img", { src: u, alt: c.prompt || "Generated image", loading: "lazy" });
      body.replaceChildren(media, el("a", { class: "btn btn--small", href: u, target: "_blank", rel: "noopener noreferrer" }, "Open full size", icon("open")));
    } else body.replaceChildren(el("div", { class: "creation-state" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Working on it — usually under a minute."));
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
            if (c.state === "nsfw") { c.outcome = "error"; c.reason = "The service turned this one down for its content."; }
            if (c.state === "failed") { c.outcome = "error"; c.reason = "The service couldn't make this one. Try again."; }
            fillCreation(card.querySelector(".creation-media"), c);
            JOBS.delete(job);
          }
        } catch (e) { JOBS.delete(job); }
      }
    }
    polling = false;
  }

  // ------------------------------------------------------------------ Devices

  function deviceState(k) {
    if (k.revoked) return ["revoked", "Disconnected"];
    if (!k.last_used) return ["unused", "Not used yet"];
    return k.last_used > Date.now() / 1000 - 7 * 86400 ? ["active", "Active"] : ["idle", "Idle"];
  }

  /* Devices: the ones connected now, connecting another, and the ones disconnected before. */
  function pageDevices(params) {
    const me = S.me;
    const active = me.keys.filter((k) => !k.revoked);
    const old = me.keys.filter((k) => k.revoked);
    const card = (k) => {
      const [state, label] = deviceState(k);
      return el("article", { class: "dcard s-" + state },
        el("div", { class: "dcard-top" }, el("span", { class: "dcard-ic" }, icon(k.client === "Claude Code" || k.client === "Codex" ? "terminal" : "device")),
          el("div", { class: "grow" }, el("h3", null, k.label), el("div", { class: "mono faint small" }, k.hint)), SUI.status(state, label, { plain: true })),
        el("dl", { class: "facts" },
          el("dt", null, "Application"), el("dd", null, k.client || "Not used yet"),
          el("dt", null, k.revoked ? "Disconnected" : "Last used"), el("dd", null, k.revoked ? fmt.date(k.revoked) : fmt.ago(k.last_used)),
          el("dt", null, "Connected"), el("dd", null, fmt.date(k.created))),
        k.revoked ? null : el("div", { class: "dcard-foot" }, el("button", { class: "btn btn--small btn--danger", type: "button", onclick: () => disconnect(k) }, "Disconnect")));
    };
    const guides = me.connect || [];
    const views = viewTabs("#/devices", params, [
      ["connected", "Connected", () => (active.length ? el("div", { class: "grid-devices" }, active.map(card))
        : el("div", { class: "empty" }, el("h3", null, "No devices yet"),
          el("p", null, guides.length ? "Connect a coding tool or app to use the company's AI from your computer." : "When a coding tool is turned on for you, you can connect it here."),
          guides.length ? el("button", { class: "btn btn--solid", type: "button", onclick: () => views.show("connect", true) }, icon("link"), "Connect a tool") : null)), active.length || null],
      ["connect", "Connect a tool", () => [
        el("p", { class: "muted view-lede" }, me.can_add_keys ? "Pick the tool, name the device, and follow three short steps. Its key is shown once." : "Ask your admin for a key — connecting your own devices is switched off."),
        guides.length ? el("div", { class: "grid-connect" }, guides.map((g) => el("article", { class: "ccard" },
          el("div", { class: "ccard-top" }, el("span", { class: "dcard-ic" }, icon(g.kind === "Coding agent" ? "terminal" : "link")),
            el("div", { class: "grow" }, el("h3", null, g.name), el("div", { class: "faint small" }, g.kind))),
          el("p", null, g.blurb || ""),
          me.can_add_keys ? el("button", { class: "btn btn--small btn--solid", type: "button", onclick: () => connect(g) }, icon("link"), "Connect") : null)))
          : el("div", { class: "empty" }, el("h3", null, "Nothing to connect yet"), el("p", null, "When a coding tool or app is turned on for you, it appears here."))]],
      old.length ? ["old", "Disconnected", () => [el("p", { class: "muted view-lede" }, "Their keys no longer work. They stay listed so you can see what was connected and when."),
        el("div", { class: "grid-devices" }, old.map(card))], old.length] : null,
    ], "Devices", active.length ? "connected" : "connect");
    frame("Devices", el("section", { class: "section first" }, el("div", { class: "shell" },
      sectionHead("My devices", "Devices", "Each laptop or coding tool has its own key, so you can disconnect one without stopping the others. Your admin sees the same list."),
      views.node)));
  }

  /* Connect a tool: name the device, get its own key, follow the steps. The key is shown once. */
  function connect(tool) {
    let created = false;
    const { node, close } = drawer("Connect " + tool.name, () => { if (created) load(); });
    const body = el("div", { class: "body" });
    const foot = el("footer");
    node.append(el("header", null, el("div", { class: "d-id" }, el("span", { class: "dcard-ic lg" }, icon(tool.kind === "Coding agent" ? "terminal" : "link")),
      el("div", null, el("div", { class: "eyebrow" }, tool.kind), el("h2", null, "Connect " + tool.name))),
    el("button", { class: "btn btn--quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x"))), body, foot);
    const label = el("input", { class: "input", type: "text", value: `My laptop — ${tool.name}`, maxlength: "80", id: "c-label" });
    const err = el("div", { class: "form-error", role: "alert" });
    const make = el("button", { class: "btn btn--solid", onclick: async () => {
      make.disabled = true;
      try { const out = await api("POST", "/keys", { label: label.value }); created = true; showSteps(out); }
      catch (e) { err.textContent = e.message; make.disabled = false; }
    } }, icon("key"), "Create my key");
    body.replaceChildren(
      el("ol", { class: "progress", "aria-label": "Steps" }, el("li", { class: "on" }, "Name the device"), el("li", null, "Get your key"), el("li", null, "Set up " + tool.name)),
      el("div", { class: "step" }, el("div", { class: "n" }, "1"), el("div", null,
        el("h3", null, "Name this device"),
        el("p", null, "So you — and your admin — can tell your devices apart. Include the computer and the tool."),
        el("label", { class: "u-sr", for: "c-label" }, "Device name"), label, err)),
      el("p", { class: "muted small" }, "Requests from this device go through Swangz AI on the company key and are recorded — see How Swangz AI works."));
    foot.replaceChildren(el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"), make);
    requestAnimationFrame(() => { label.focus(); label.select(); });

    function showSteps(out) {
      const guide = out.tools.find((t) => t.id === tool.id) || out.tools[0];
      const keyText = el("code", { class: "key-hidden" }, "•".repeat(14) + out.key.slice(-4));
      let shown = false;
      const reveal = el("button", { class: "btn btn--small btn--quiet", type: "button", "aria-pressed": "false", onclick: () => {
        shown = !shown; keyText.textContent = shown ? out.key : "•".repeat(14) + out.key.slice(-4); reveal.textContent = shown ? "Hide" : "Show"; reveal.setAttribute("aria-pressed", shown ? "true" : "false");
      } }, "Show");
      body.replaceChildren(
        el("ol", { class: "progress", "aria-label": "Steps" }, el("li", { class: "done" }, "Name the device"), el("li", { class: "on" }, "Get your key"), el("li", { class: "on" }, "Set up " + tool.name)),
        el("div", { class: "conn-card" },
          el("div", { class: "conn-row" }, el("span", { class: "k" }, "Tool"), el("span", { class: "v" }, tool.name)),
          el("div", { class: "conn-row" }, el("span", { class: "k" }, "Connected device"), el("span", { class: "v" }, out.label)),
          el("div", { class: "conn-row" }, el("span", { class: "k" }, "Gateway address"), el("span", { class: "v mono" }, S.me.base_url),
            el("button", { class: "btn btn--small btn--quiet", type: "button", onclick: () => copy(S.me.base_url, "Address") }, icon("copy"), "Copy")),
          el("div", { class: "conn-row key" }, el("span", { class: "k" }, "Gateway key"), el("span", { class: "v" }, keyText),
            el("span", { class: "row" }, reveal, el("button", { class: "btn btn--small", type: "button", onclick: () => copy(out.key, "Key") }, icon("copy"), "Copy")))),
        el("p", { class: "once" }, icon("alert"), "Shown only this once. It's already filled into the steps below — keep a copy somewhere safe, and never share it."),
        ...guide.steps.map((s, i) => el("div", { class: "step" }, el("div", { class: "n" }, String(i + 1)), el("div", null,
          el("h3", null, s.title), el("p", null, s.how), codeBlock(s.code)))),
        el("div", { class: "notice ok" }, icon("checkCircle"), el("span", null, "Once it's set up, this device shows under My devices with the app it runs and when it was last used.")));
      foot.replaceChildren(el("a", { class: "btn", href: "#/devices", onclick: close }, "My devices"), el("button", { class: "btn btn--solid", onclick: close }, "Done"));
    }
  }

  function disconnect(k) {
    dialog("Disconnect " + k.label + "?", "Its key stops working straight away. Your other devices keep working, and you can connect this one again at any time.",
      (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
        el("button", { class: "btn btn--danger", onclick: async () => {
          try { await api("POST", `/keys/${k.id}/revoke`); close(); toast("Disconnected."); load(); } catch (e) { toast(e.message, true); }
        } }, "Disconnect")]);
  }

  // ------------------------------------------------------------------ Requests & notifications

  /* Requests: Updates (what changed for you) and Access requests (what you asked for). The bell opens Updates. */
  function pageRequests(params) {
    const me = S.me;
    const list = notices();
    const reqs = me.access_requests || [];
    const open = reqs.filter((r) => r.state === "open").length;
    const STATE = { open: ["pending", "Waiting for an admin"], granted: ["ok", "Granted"], declined: ["blocked", "Declined"] };
    const tools = Object.fromEntries(me.catalog.map((t) => [t.id, t]));
    const views = viewTabs("#/requests", params, [
      ["updates", "Updates", () => (list.length ? el("ul", { class: "notices" }, list.map(noticeItem))
        : el("div", { class: "empty" }, el("h3", null, "You're all caught up"), el("p", null, "Turned-on tools, decisions on your requests, shared turns and access dates appear here."))), list.length || null],
      ["access", "Access requests", () => [
        el("div", { class: "spread view-lede" }, el("p", { class: "muted" }, "Ask for any tool in the catalogue — an admin grants or declines it."),
          el("a", { class: "btn btn--small", href: "#/tools?show=others" }, "Browse tools", icon("chevronRight"))),
        reqs.length ? el("ul", { class: "req-list" }, reqs.map((r) => el("li", null,
          SUI.logo(tools[r.tool_id] || { name: r.tool }, "sm"),
          el("div", { class: "grow" }, el("strong", null, r.tool), el("div", { class: "faint small" }, "Asked " + fmt.ago(r.created) + (r.decided ? " · decided " + fmt.ago(r.decided) : "")),
            r.reason ? el("p", { class: "req-reason" }, r.reason) : null, r.decision_note ? el("p", { class: "muted small" }, "Note from your admin: " + r.decision_note) : null),
          SUI.status(...STATE[r.state], { plain: true }))))
          : el("div", { class: "empty" }, el("h3", null, "No requests yet"), el("p", null, "Find a tool in the catalogue and press Request access."), el("a", { class: "btn btn--solid", href: "#/tools?show=others" }, "Browse tools"))], open || null],
    ], "Requests");
    frame("Requests", el("section", { class: "section first" }, el("div", { class: "shell narrow" },
      sectionHead(null, "Requests", "What's changed for you, and the tools you've asked for."), views.node)));
  }

  // ------------------------------------------------------------------ Privacy: how Swangz AI works

  /* How Swangz AI works: six short sections with an index. Each says the plain answer first; the detail is one
     click away rather than in every paragraph. */
  function pagePrivacy() {
    const pv = S.me.privacy || {};
    const item = (ic, title, text, more) => el("li", null, el("span", { class: "p-ic" }, icon(ic)),
      el("div", null, el("strong", null, title), el("p", null, text), more ? el("details", { class: "p-more" }, el("summary", null, "More about this"), el("p", null, more)) : null));
    const sections = [
      ["recorded", "What is recorded", icon("eye"), [
        el("p", { class: "p-lead" }, "Your use of approved AI tools through Swangz AI — for security, support and cost."),
        el("ul", { class: "p-list" },
          item("open", "Tools you open from here", "Which tool, when, and the browser and network address you opened it from."),
          item("globe", "AI websites, with the Swangz browser extension", "Which approved AI site, when and for how long.",
            pv.gate_log_full ? "Your company has also turned on fuller logging for AI websites — ask your admin what it covers." : null),
          item("terminal", "AI requests through the gateway", "Who, which device and app, the model, what you typed, what the AI did and replied, and what it cost.",
            "This covers coding tools, Studio and apps connected with a Swangz key — they run on the company's key, so each request passes through Swangz AI."),
          item("hand", "Shared company accounts", "Who held the turn and when, so the account's use can be matched to a person."))]],
      ["not-recorded", "What is not recorded", icon("lock"), [
        el("ul", { class: "p-list" },
          pv.gate_log_full ? null : item("globe", "Page contents or keystrokes on AI websites", "The extension records the site and the time — never what's on the page or what you type there."),
          item("x", "Anything outside approved AI tools", "Other websites and apps aren't watched by Swangz AI."),
          item("user", "Your personal accounts", "Only access through Swangz AI is recorded."))]],
      ["purpose", "Purpose and location", icon("target"), [
        el("ul", { class: "p-list" },
          item("target", "What a request was for", pv.purpose_inference ? "Your word if you give it (Studio asks); otherwise the tool's, or a labelled guess." : "Only your word (Studio asks) or what the tool itself implies — never a guess from what you type.",
            pv.purpose_inference ? "If you or your tool say what it's for, that is recorded as your word. Otherwise the gateway may guess from words in the request — a coding tool is software development, \"Instagram caption\" suggests marketing. A guess is always shown to admins as a guess, with the words it was based on, and can be wrong."
              : "A coding tool counts as software development. Otherwise a request's purpose stays unknown unless you say."),
          item("pin", "Roughly where from", "A named network (like the office) or, at most, an approximate town — never your exact location.",
            "The gateway sees the network address of each request. Admins see the network's name if Swangz has named it, or an approximate town from an offline table" + (pv.location_table ? "" : " (not loaded here yet)") + ". Your address is never sent to an outside service."))]],
      ["who", "Who can see it", icon("shield"), [
        el("p", null, "Swangz administrators, in the control room. Every time one opens a full record or exports records, that is itself written to an audit log — and only some admin roles can export what you typed."),
        el("p", { class: "muted" }, pv.block_secrets ? "Requests that contain passwords or API keys are refused, to keep them out of AI tools." : "Requests that look like they contain passwords or API keys are flagged so they can be changed.")]],
      ["kept", "How long it's kept", icon("clock"), [
        el("p", null, pv.retention_days ? `AI request records are deleted automatically after ${pv.retention_days} days.` : "AI request records are kept until an administrator removes them."),
        el("p", { class: "muted" }, !pv.store_bodies ? "Only a summary is kept — not the full contents of requests."
          : pv.bodies_days ? `Full request contents are kept for ${pv.bodies_days} days, then only the summary stays.` : "Full request contents are kept for that time, so the exact request can be checked if something goes wrong."),
        pv.site_days || pv.launch_days ? el("p", { class: "muted" }, [pv.site_days ? `AI website visits: ${pv.site_days} days.` : null, pv.launch_days ? `Tools opened from here: ${pv.launch_days} days.` : null].filter(Boolean).join(" ")) : null]],
      ["help", "Using it well, and help", icon("info"), [
        el("p", null, "Swangz AI is for your work at Swangz. Don't paste passwords, other people's personal details, or anything you wouldn't put in a work email."),
        el("p", null, el("strong", null, "Questions? "), pv.support_contact ? pv.support_contact : "Ask your admin."),
        el("div", null, el("button", { class: "btn", type: "button", onclick: policy }, "Read the usage policy"))]],
    ];
    // the index scrolls to a section; it doesn't touch the address, which is the page's route
    const go = (id) => { const n = document.getElementById("p-" + id); if (n) { n.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); n.focus({ preventScroll: true }); } };
    const index = el("nav", { class: "p-index", "aria-label": "On this page" }, el("span", { class: "eyebrow" }, "On this page"),
      el("ul", null, sections.map(([id, title]) => el("li", null, el("button", { type: "button", onclick: () => go(id) }, title)))));
    frame("How Swangz AI works", [
      el("section", { class: "hero hero-plain" }, el("div", { class: "shell" },
        el("div", { class: "eyebrow" }, "Privacy & monitoring"),
        el("h1", null, "How Swangz AI works"),
        el("p", { class: "lede" }, "Your company AI access passes through Swangz Gateway. For security, support and cost management, the company records approved AI use. Here is exactly what that means."))),
      el("section", { class: "section" }, el("div", { class: "shell p-layout" }, index,
        el("div", { class: "p-sections" }, sections.map(([id, title, ic, body]) => el("section", { class: "trust-card", id: "p-" + id, tabindex: "-1", "aria-labelledby": "p-h-" + id },
          el("h2", { id: "p-h-" + id }, ic, title), ...body.filter(Boolean)))))),
    ]);
  }

  function policy() {
    dialog("Using Swangz AI", el("div", { class: "fields" },
      el("p", null, "Swangz AI is provided for your work at Swangz. Your requests are handled by AI providers on the company's behalf."),
      el("p", null, "Like any company system, use is recorded for security, cost and support — the Privacy page lists exactly what. Don't paste passwords, other people's personal details, or anything you wouldn't put in a work email."),
      el("p", null, "Questions? " + ((S.me && S.me.privacy && S.me.privacy.support_contact) || "Ask your admin."))),
    (close) => [el("a", { class: "btn btn--quiet", href: "#/privacy", onclick: close }, "How Swangz AI works"), el("button", { class: "btn btn--solid", onclick: close }, "Got it")]);
  }

  // ------------------------------------------------------------------ profile

  function profile() {
    const me = S.me;
    dialog("Your profile", el("div", { class: "fields" },
      el("div", { class: "profile-id" }, SUI.avatar(me.name, "lg"), el("div", null, el("strong", null, me.name), el("div", { class: "muted" }, me.email),
        el("div", { class: "faint small" }, [me.title, me.department].filter(Boolean).join(" · ") || "Swangz Avenue"))),
      el("dl", { class: "facts" },
        el("dt", null, "Status"), el("dd", null, me.active ? SUI.status("ready", "Active", { plain: true }) : SUI.status("suspended", "Paused", { plain: true })),
        el("dt", null, "Access"), el("dd", null, me.access_until ? "until " + fmt.date(me.access_until - 1) : "no end date"),
        el("dt", null, "Tools"), el("dd", null, SUI.plural(me.catalog.filter((t) => t.state === "enabled").length, "tool") + " enabled"),
        el("dt", null, "Devices"), el("dd", null, SUI.plural(me.keys.filter((k) => !k.revoked).length, "device") + " connected"),
        el("dt", null, "Theme"), el("dd", null, SUI.themeButton()))),
    (close) => [el("button", { class: "btn btn--quiet", onclick: () => { close(); changePassword(); } }, "Change password"), el("button", { class: "btn btn--solid", onclick: close }, "Done")]);
  }

  function changePassword() {
    const cur = passwordInput("current-password", "cp-cur");
    const nw = passwordInput("new-password", "cp-new");
    const err = el("div", { class: "form-error", role: "alert" });
    dialog("Change password", el("div", { class: "fields" },
      el("label", { class: "field", for: "cp-cur" }, el("span", null, "Current password"), cur.node),
      el("label", { class: "field", for: "cp-new" }, el("span", null, "New password (10+ characters)"), nw.node), err),
    (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
      el("button", { class: "btn btn--solid", onclick: async () => {
        try { await api("POST", "/password", { current: cur.input.value, new: nw.input.value }); close(); toast("Password changed."); } catch (e) { err.textContent = e.message; }
      } }, "Save")]);
  }

  async function signOut() {
    try { await api("POST", "/logout"); } catch (e) { /* signed out anyway */ }
    S.me = null;
    showSignIn();
  }

  // ------------------------------------------------------------------ start

  const ROUTES = [[/^#?\/?$/, pageHome], [/^#\/tools$/, pageTools], [/^#\/studio$/, pageStudio], [/^#\/devices$/, pageDevices],
    [/^#\/requests$/, pageRequests], [/^#\/privacy$/, pagePrivacy]];

  function render() {
    document.querySelectorAll(".drawer, .scrim").forEach((n) => n.remove());
    const [path, query] = (location.hash || "#/").split("?");
    const params = new URLSearchParams(query || "");
    const hit = ROUTES.find(([rx]) => rx.test(path));
    if (!hit) { location.hash = "#/"; return; }
    hit[1](params);
    window.scrollTo(0, 0);
  }

  async function load() {
    try {
      const me = await api("GET", "/me");
      S.me = me;
      SUI.setGatewayOffset(180);
      // the device count on each coding tool's tile
      me.catalog.forEach((t) => { if (t.kind === "dev") t.connected = me.keys.filter((k) => !k.revoked && k.client === t.name).length; });
      try { S.studio = await api("GET", "/studio"); } catch (e) { S.studio = null; }
      render();
    } catch (e) {
      if (e.status === 401) showSignIn();
      else app.replaceChildren(el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" },
        el("form", null, el("div", { class: "eyebrow" }, "Connection"), el("h2", null, "Swangz AI is temporarily unavailable"), el("p", { class: "muted" }, e.message),
          el("button", { class: "btn btn--solid", type: "button", onclick: load }, icon("refresh"), "Try again")))));
    }
  }

  function route() {
    const m = (location.hash || "").match(/^#\/welcome\/([A-Za-z0-9_\-]+)$/);
    if (m) return showWelcome(m[1]);
    if (!S.me) return load();
    return render();
  }

  // "/" focuses the tool search wherever there is one
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "")) {
      const box = document.querySelector("input.search");
      if (box) { e.preventDefault(); box.focus(); }
      else if (S.me && !document.querySelector("dialog[open], .drawer")) { e.preventDefault(); location.hash = "#/tools"; setTimeout(() => document.querySelector("input.search")?.focus(), 60); }
    }
  });
  window.addEventListener("hashchange", route);
  route();
})();
