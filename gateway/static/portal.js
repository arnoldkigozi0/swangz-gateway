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
    if (me.suspended) out.push({ tone: "bad", icon: "lock", title: "Your access is paused", text: "Talk to your admin to have it restored." });
    else if (me.paused) out.push({ tone: "warn", icon: "stop", title: "AI access is paused for everyone", text: "An admin has paused Swangz AI for now. Tools will open again when it's resumed." });
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
        el("a", { class: "icon-btn", href: "#/requests", "aria-label": count ? `${count} notifications` : "Notifications", "data-tip": count ? `${count} notification${count === 1 ? "" : "s"}` : "No new notifications" },
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
      ? "When you open it from here: the tool, the time, and your browser and address. With the Swangz browser extension: that you visited it and for how long — never what's on the page or what you type."
      : "Requests go through Swangz AI on the company key, so they're recorded: who, which device and app, the model, what you typed, what the AI did and replied, and the cost.";
    const section = (title, ...body) => el("section", { class: "d-sec" }, el("h3", null, title), ...body);
    node.append(
      el("header", null,
        el("div", { class: "d-id" }, SUI.logo(t, "lg"), el("div", null, el("div", { class: "eyebrow" }, t.category), el("h2", null, t.name), tileStatus(t))),
        el("button", { class: "btn btn--quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x"))),
      el("div", { class: "body" },
        section("What it does", el("p", null, t.description || "An AI tool in the Swangz catalog.")),
        section("Why it's available to you", el("p", null, why)),
        section("How sign-in works", el("p", null, el("strong", null, how[0] + ". "), how[1]),
          t.turn ? el("p", { class: "muted" }, `One person at a time${t.turn.seats > 1 ? ` (up to ${t.turn.seats})` : ""}, for up to ${t.turn.minutes} minutes a turn. When your turn ends, the Swangz extension signs your browser out of it.`) : null),
        section("Your recent use", el("dl", { class: "facts" },
          t.kind === "dev" ? [el("dt", null, "Connected on"), el("dd", null, SUI.plural(t.connected || 0, "device"))]
            : [el("dt", null, "Last opened"), el("dd", null, t.last_opened ? fmt.ago(t.last_opened) : "never"),
              el("dt", null, "Opened · 30 days"), el("dd", null, SUI.plural(t.opens_30d || 0, "time"))],
          t.ends ? [el("dt", null, "Access ends"), el("dd", null, fmt.date(t.ends - 1))] : null)),
        section("Who manages access", el("p", null, "Your Swangz administrators decide who has which tool."
          + (me.privacy && me.privacy.support_contact ? " For help: " + me.privacy.support_contact + "." : " Ask your admin if anything's wrong."))),
        section("What's recorded", el("p", { class: "muted" }, recorded), el("a", { class: "tlink", href: "#/privacy", onclick: close }, "How Swangz AI works"))),
      el("footer", null, el("button", { class: "btn btn--quiet", onclick: close }, "Close"), tileActions(t).map((b) => { b.classList.remove("btn--small"); return b; })));
  }

  // ------------------------------------------------------------------ Home

  function pageHome() {
    const me = S.me;
    const catalog = me.catalog;
    const enabled = catalog.filter((t) => t.state === "enabled");
    const weekAgo = Date.now() / 1000 - 7 * 86400;
    const usedWeek = enabled.filter((t) => t.last_opened && t.last_opened >= weekAgo).length;
    const pending = catalog.filter((t) => t.pending).length;
    const recent = enabled.filter((t) => t.last_opened && t.launchable && t.kind !== "dev").sort((a, b) => b.last_opened - a.last_opened).slice(0, 5);
    const statusLine = me.active ? SUI.status("ready", "Access active", { plain: true })
      : me.suspended ? SUI.status("suspended", "Your access is paused", { plain: true }) : SUI.status("waiting", "AI access is paused for everyone", { plain: true });
    const list = notices();
    const hero = el("section", { class: "hero" }, el("div", { class: "shell" },
      el("div", { class: "eyebrow" }, `${greeting()}, ${firstName(me.name)}`),
      el("h1", null, me.active ? "Your AI workspace is ready." : me.suspended ? "Your access is paused." : "AI is paused for now."),
      el("p", { class: "hero-meta" }, statusLine,
        el("span", { class: "sep", "aria-hidden": "true" }), el("span", null, el("b", null, String(enabled.length)), enabled.length === 1 ? " tool available" : " tools available"),
        el("span", { class: "sep", "aria-hidden": "true" }), el("span", null, el("b", null, String(usedWeek)), " used this week"),
        pending ? [el("span", { class: "sep", "aria-hidden": "true" }), el("a", { href: "#/requests" }, el("b", null, String(pending)), pending === 1 ? " request pending" : " requests pending")] : null),
      me.budget ? el("div", { class: "allowance" }, el("span", null, "Allowance this month"), el("strong", null, fmt.money(me.budget.month)),
        el("span", { class: "muted" }, me.budget.monthly !== null ? "of " + fmt.money(me.budget.monthly) : "no limit"),
        me.budget.monthly !== null ? meter(me.budget.month, me.budget.monthly) : null) : null,
      recent.length ? el("div", { class: "recent" }, el("span", { class: "recent-label" }, "Recently opened"),
        recent.map((t) => el("a", { href: gurl("/go/" + t.id), target: "_blank", rel: "noopener", "aria-label": `Open ${t.name} (opens in a new tab)`, onclick: () => opened(t) },
          SUI.logo(t, "sm"), t.name, el("span", { class: "faint" }, fmt.ago(t.last_opened))))) : null));
    const noticeBox = list.length ? el("section", { class: "section tight" }, el("div", { class: "shell" }, el("ul", { class: "notices" }, list.slice(0, 3).map(noticeItem)),
      list.length > 3 ? el("a", { class: "tlink", href: "#/requests" }, `See all ${list.length} notifications`) : null)) : null;
    const mine = enabled.slice().sort((a, b) => (b.last_opened || 0) - (a.last_opened || 0) || a.name.localeCompare(b.name));
    const yours = el("section", { class: "section" }, el("div", { class: "shell" },
      sectionHead("Your tools", enabled.length ? "Your approved AI tools" : "Nothing switched on yet",
        enabled.length ? "Paid for by Swangz and ready for you. Open opens it in a new tab; select a tool for how it works." : "Browse the catalog and request what you need — an admin turns it on.",
        el("a", { class: "btn", href: "#/tools" }, "All tools", icon("chevronRight"))),
      mine.length ? el("div", { class: "grid-tiles" }, mine.map(tile))
        : el("div", { class: "empty" }, el("h3", null, "No tools yet"), el("p", null, "When an admin turns a tool on for you, it appears here."), el("a", { class: "btn btn--solid", href: "#/tools" }, "Browse tools"))));
    const studio = hasStudio() ? el("section", { class: "section" }, el("div", { class: "shell" },
      el("a", { class: "promo", href: "#/studio" }, el("span", { class: "promo-ic" }, icon("spark")),
        el("div", { class: "grow" }, el("strong", null, "Studio — voice, images and video"), el("span", null, "Make a voice-over or an image right here, on the company's account.")), icon("chevronRight")))) : null;
    const activeKeys = me.keys.filter((k) => !k.revoked);
    const more = el("section", { class: "section" }, el("div", { class: "shell" }, el("div", { class: "cards-2" },
      el("a", { class: "info-card", href: "#/devices" }, el("span", { class: "info-ic" }, icon("device")),
        el("div", null, el("h3", null, "My devices"), el("p", null, activeKeys.length ? `${SUI.plural(activeKeys.length, "device")} connected — ${activeKeys.filter((k) => k.last_used && k.last_used > weekAgo).length} used this week.` : "Connect your laptop or coding tools to use the company's AI from them.")),
        icon("chevronRight")),
      el("a", { class: "info-card", href: "#/privacy" }, el("span", { class: "info-ic" }, icon("shield")),
        el("div", null, el("h3", null, "How Swangz AI works"), el("p", null, "What the company records when you use AI, what it doesn't, and how long it's kept.")),
        icon("chevronRight")))));
    frame("Home", [hero, noticeBox, yours, studio, more]);
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

  function pageStudio() {
    if (!hasStudio()) { location.hash = "#/"; return; }
    const st = S.studio;
    const tabs = [["voice", "Voice", st.voice], ["image", "Image", st.image], ["video", "Video", st.video]].filter((t) => t[2]);
    const panel = el("div", { class: "studio-panel", role: "tabpanel" });
    const tabBar = el("div", { class: "tabs", role: "tablist" }, tabs.map(([id, label]) =>
      el("button", { class: "tab", role: "tab", type: "button", "data-tab": id, onclick: () => show(id) }, label)));
    const creations = el("div", { class: "creations" });
    /* What it's for, if they want to say. Optional; it is recorded as their own word (declared), not a guess. */
    function purposeField() {
      const sel = el("select", { class: "input" }, el("option", { value: "" }, "Not saying"), (st.purposes || []).map((p) => el("option", { value: p.id }, p.name)));
      try { sel.value = localStorage.getItem("swangz-studio-purpose") || ""; } catch (e) { /* no storage */ }
      sel.addEventListener("change", () => { try { localStorage.setItem("swangz-studio-purpose", sel.value); } catch (e) { /* no storage */ } });
      return { sel, node: el("label", { class: "field" }, el("span", null, "What it's for (optional)"), sel) };
    }
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
      if (fresh) card.classList.add("fresh");
      creations.prepend(card);
      emptyNote.hidden = true;
      if (c.job && !c.urls.length && c.outcome === "ok") JOBS.set(c.job, card);
      if (fresh) resumeJobs();
    }
    const emptyNote = el("p", { class: "muted" }, "What you make shows up here, so you can play it again or download it.");
    st.recent.slice().reverse().forEach((c) => addCreation(c, false));
    emptyNote.hidden = st.recent.length > 0;
    frame("Studio", el("section", { class: "section first" }, el("div", { class: "shell" },
      sectionHead("Create", "Studio", "Voice-overs, images and video in the browser — on the company's account, nothing to install. What you make here is recorded like any request through Swangz AI."),
      el("div", { class: "studio" }, tabBar, panel),
      el("h3", { class: "sub-head" }, "Recent creations"), emptyNote, creations)));
    show(tabs[0][0]);
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

  function pageDevices() {
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
    frame("Devices", el("section", { class: "section first" }, el("div", { class: "shell" },
      sectionHead("My devices", "Connected devices", "Each laptop or coding tool has its own key, so you can disconnect one without stopping the others. Your admin sees the same list."),
      active.length ? el("div", { class: "grid-devices" }, active.map(card)) : el("div", { class: "empty" }, el("h3", null, "No devices yet"),
        el("p", null, guides.length ? "Connect a coding tool or app below to use the company's AI from your computer." : "When a coding tool is turned on for you, you can connect it here.")),
      guides.length ? [sectionHead(null, "Connect a tool", me.can_add_keys ? "Pick the tool, name the device, and follow three short steps." : "Ask your admin for a key — connecting your own devices is switched off."),
        el("div", { class: "grid-connect" }, guides.map((g) => el("article", { class: "ccard" },
          el("div", { class: "ccard-top" }, el("span", { class: "dcard-ic" }, icon(g.kind === "Coding agent" ? "terminal" : "link")),
            el("div", { class: "grow" }, el("h3", null, g.name), el("div", { class: "faint small" }, g.kind))),
          el("p", null, g.blurb || ""),
          me.can_add_keys ? el("button", { class: "btn btn--small btn--solid", type: "button", onclick: () => connect(g) }, icon("link"), "Connect") : null)))] : null,
      old.length ? el("details", { class: "old-devices" }, el("summary", null, `Disconnected devices (${old.length})`), el("div", { class: "grid-devices" }, old.map(card))) : null)));
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

  function pageRequests() {
    const me = S.me;
    const list = notices();
    const reqs = me.access_requests || [];
    const STATE = { open: ["pending", "Waiting for an admin"], granted: ["ok", "Granted"], declined: ["blocked", "Declined"] };
    const tools = Object.fromEntries(me.catalog.map((t) => [t.id, t]));
    frame("Requests", el("section", { class: "section first" }, el("div", { class: "shell narrow" },
      sectionHead("Notifications", list.length ? "What's new" : "You're all caught up", list.length ? null : "Turned-on tools, decisions on your requests, shared turns and access dates appear here."),
      list.length ? el("ul", { class: "notices" }, list.map(noticeItem)) : null,
      sectionHead("Access requests", "Tools you've asked for", "Ask for any tool in the catalog — an admin grants or declines it.", el("a", { class: "btn", href: "#/tools?q=" }, "Browse tools", icon("chevronRight"))),
      reqs.length ? el("ul", { class: "req-list" }, reqs.map((r) => el("li", null,
        SUI.logo(tools[r.tool_id] || { name: r.tool }, "sm"),
        el("div", { class: "grow" }, el("strong", null, r.tool), el("div", { class: "faint small" }, "Asked " + fmt.ago(r.created) + (r.decided ? " · decided " + fmt.ago(r.decided) : "")),
          r.reason ? el("p", { class: "req-reason" }, r.reason) : null, r.decision_note ? el("p", { class: "muted small" }, "Note from your admin: " + r.decision_note) : null),
        SUI.status(...STATE[r.state], { plain: true }))))
        : el("div", { class: "empty" }, el("h3", null, "No requests yet"), el("p", null, "Find a tool in the catalog and press Request access."), el("a", { class: "btn btn--solid", href: "#/tools" }, "Browse tools")))));
  }

  // ------------------------------------------------------------------ Privacy: how Swangz AI works

  function pagePrivacy() {
    const pv = S.me.privacy || {};
    const item = (ic, title, text) => el("li", null, el("span", { class: "p-ic" }, icon(ic)), el("div", null, el("strong", null, title), el("p", null, text)));
    frame("How Swangz AI works", [
      el("section", { class: "hero hero-plain" }, el("div", { class: "shell narrow" },
        el("div", { class: "eyebrow" }, "Privacy & monitoring"),
        el("h1", null, "How Swangz AI works"),
        el("p", { class: "lede" }, "Your company AI access passes through Swangz Gateway. For security, support and cost management, the company records approved AI use. Here is exactly what that means."))),
      el("section", { class: "section" }, el("div", { class: "shell narrow" },
        el("div", { class: "trust-grid" },
          el("section", { class: "trust-card" }, el("h2", null, icon("eye"), "What is recorded"),
            el("ul", { class: "p-list" },
              item("open", "Tools you open from here", "Which tool, when, and the browser and network address you opened it from."),
              item("globe", "AI websites, with the Swangz browser extension", pv.gate_log_full
                ? "Which approved AI site, when and for how long. Your company has also turned on fuller logging for AI websites — ask your admin what it covers."
                : "Which approved AI site, when and for how long."),
              item("terminal", "AI requests through the gateway", "Coding tools, Studio and apps connected with a Swangz key: who, which device and app, the model, what you typed, what the AI did and replied, and what it cost."),
              item("hand", "Shared company accounts", "Who held the turn and when, so the account's use can be matched to a person."),
              item("target", "What a request was for", pv.purpose_inference
                ? "If you or your tool say (Studio asks), that is recorded as your word. Otherwise the gateway may guess from words in the request — a coding tool is software development, \"Instagram caption\" suggests marketing. A guess is always shown to admins as a guess, with the words it was based on, and can be wrong."
                : "Only if you or your tool say (Studio asks), or the tool itself implies it — a coding tool is software development. The gateway doesn't guess from what you type."),
              item("pin", "Roughly where from", "The network address of each request. Admins see a named network (like the office) or, at most, an approximate town from an offline table" + (pv.location_table ? "" : " (not loaded here yet)") + " — never your exact location, and your address is never sent to an outside service."))),
          el("section", { class: "trust-card" }, el("h2", null, icon("lock"), "What is not recorded"),
            el("ul", { class: "p-list" },
              pv.gate_log_full ? null : item("globe", "Page contents or keystrokes on AI websites", "The extension records the site and the time — never what's on the page or what you type there."),
              item("x", "Anything outside approved AI tools", "Other websites and apps aren't watched by Swangz AI."),
              item("user", "Your personal accounts", "Only access through Swangz AI is recorded."))),
          el("section", { class: "trust-card" }, el("h2", null, icon("clock"), "How long it's kept"),
            el("p", null, pv.retention_days ? `AI request records are deleted automatically after ${pv.retention_days} days.` : "AI request records are kept until an administrator removes them."),
            el("p", { class: "muted" }, !pv.store_bodies ? "Only a summary is kept — not the full contents of requests."
              : pv.bodies_days ? `Full request contents are kept for ${pv.bodies_days} days, then only the summary stays.` : "Full request contents are kept for that time, so the exact request can be checked if something goes wrong."),
            pv.site_days || pv.launch_days ? el("p", { class: "muted" }, [pv.site_days ? `AI website visits: ${pv.site_days} days.` : null, pv.launch_days ? `Tools opened from here: ${pv.launch_days} days.` : null].filter(Boolean).join(" ")) : null),
          el("section", { class: "trust-card" }, el("h2", null, icon("shield"), "Who can see it"),
            el("p", null, "Swangz administrators, in the control room. Every time one opens a full record or exports records, that is itself written to an audit log — and only some admin roles can export what you typed."),
            el("p", { class: "muted" }, pv.block_secrets ? "Requests that contain passwords or API keys are refused, to keep them out of AI tools." : "Requests that look like they contain passwords or API keys are flagged so they can be changed.")),
          el("section", { class: "trust-card wide" }, el("h2", null, icon("info"), "Using it well"),
            el("p", null, "Swangz AI is for your work at Swangz. Don't paste passwords, other people's personal details, or anything you wouldn't put in a work email."),
            el("p", null, el("strong", null, "Questions? "), pv.support_contact ? pv.support_contact : "Ask your admin."),
            el("button", { class: "btn", type: "button", onclick: policy }, "Read the usage policy"))))),
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
