"use strict";
/* Swangz AI Gateway console. Plain DOM, no framework, no inline HTML from data:
   everything a person typed is untrusted text and only ever lands in textContent. */
(() => {
  const app = document.getElementById("app");
  const S = { me: null, timers: [], overview: null, route: "" };

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
        else if (k === "checked") node.checked = !!v;
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  const GATEWAY = (typeof window !== "undefined" && window.SWANGZ_GATEWAY || "").replace(/\/+$/, "");
  const gadmin = (path) => GATEWAY + "/admin/api" + path;

  async function api(method, path, body) {
    const opts = { method, credentials: "include", headers: { "x-gateway-admin": "1" } };
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(GATEWAY + "/admin/api" + path, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (res.status === 401 && path !== "/login") {
      S.me = null;
      showSignIn();
      throw new ApiError(401, "Please sign in again.");
    }
    if (!res.ok) throw new ApiError(res.status, (data && data.error) || res.statusText);
    return data;
  }

  const isOwner = () => S.me && S.me.role === "owner";

  const fmt = {
    money(v) {
      if (v === null || v === undefined) return "unpriced";
      if (v === 0) return "$0.00";
      if (v < 0.01) return "$" + v.toFixed(4);
      if (v < 1000) return "$" + v.toFixed(2);
      return "$" + Math.round(v).toLocaleString();
    },
    tokens(n) {
      n = n || 0;
      if (n < 1000) return String(n);
      if (n < 1e6) return (n / 1e3).toFixed(n < 1e4 ? 1 : 0) + "k";
      return (n / 1e6).toFixed(n < 1e7 ? 2 : 1) + "M";
    },
    when(ts) {
      const d = new Date(ts * 1000);
      const today = new Date();
      if (d.toDateString() === today.toDateString()) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return d.toLocaleDateString([], { month: "short", day: "numeric" });
    },
    stamp(ts) { return ts ? new Date(ts * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" }) : "—"; },
    ago(ts) {
      if (!ts) return "never";
      const s = Date.now() / 1000 - ts;
      if (s < 45) return "just now";
      if (s < 3600) return Math.round(s / 60) + " min ago";
      if (s < 86400) return Math.round(s / 3600) + " h ago";
      return Math.round(s / 86400) + " d ago";
    },
    elapsed(ts) {
      const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
      return s < 60 ? s + "s" : Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s";
    },
    ms(v) { return v === null || v === undefined ? "—" : v < 1000 ? v + " ms" : (v / 1000).toFixed(1) + " s"; },
    dur(s) { s = s || 0; if (s < 60) return s + "s"; if (s < 3600) return Math.round(s / 60) + " min"; return (s / 3600).toFixed(1) + " h"; },
  };

  function toast(message, bad) {
    const t = el("div", { class: "toast" + (bad ? " bad" : ""), role: "status" }, message);
    document.body.append(t);
    setTimeout(() => t.remove(), bad ? 6000 : 3000);
  }

  function every(ms, fn) {
    const id = setInterval(() => { if (document.visibilityState === "visible") fn(); }, ms);
    S.timers.push(id);
  }

  function clearTimers() {
    S.timers.forEach(clearInterval);
    S.timers = [];
  }

  function panel(title, sub, ...body) {
    return el("section", { class: "panel" }, el("header", null, el("h2", null, title), sub ? el("div", { class: "sub" }, sub) : null), ...body);
  }

  function empty(text) { return el("div", { class: "empty" }, text); }

  /* A page split into tabs. Each tab builds its own content the first time it is opened, so a page
     only ever loads what is on screen. The chosen tab lives in the URL (?tab=…) so it can be linked
     and survives a refresh. */
  function pageTabs(base, params, tabs) {
    tabs = tabs.filter(Boolean);
    const body = el("div", { class: "tab-body" });
    const built = new Map();
    let current = tabs.some((t) => t[0] === params.get("tab")) ? params.get("tab") : tabs[0][0];
    const bar = el("div", { class: "ptabs", role: "tablist" });

    function show(id) {
      current = id;
      bar.querySelectorAll("button").forEach((b) => {
        const on = b.dataset.tab === id;
        b.classList.toggle("on", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      const keep = new URLSearchParams(location.hash.split("?")[1] || "");
      keep.set("tab", id);
      history.replaceState(null, "", base + "?" + keep.toString());
      if (built.has(id)) { body.replaceChildren(built.get(id)); return; }
      const holder = el("div");
      built.set(id, holder);
      body.replaceChildren(holder);
      holder.append(el("div", { class: "body hint" }, "Loading…"));
      Promise.resolve(tabs.find((t) => t[0] === id)[2]())
        .then((n) => holder.replaceChildren(...[].concat(n).filter(Boolean)))
        .catch((e) => holder.replaceChildren(el("div", { class: "body err" }, e.message)));
    }

    bar.replaceChildren(...tabs.map(([id, label, , badge]) => el("button", {
      type: "button", role: "tab", "data-tab": id, onclick: () => show(id),
    }, label, badge ? el("span", { class: "tab-count" }, String(badge)) : null)));
    show(current);
    return el("div", null, bar, body);
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied");
    } catch (e) {
      toast("Copy didn't work here — select the text and copy it by hand.", true);
    }
  }

  function dialog(title, body, buttons) {
    const d = el("dialog", null,
      el("header", null, el("h2", null, title), el("button", { class: "btn small", onclick: () => d.close(), "aria-label": "Close" }, "Close")),
      el("div", { class: "body" }, body),
      buttons && buttons.length ? el("footer", null, buttons) : null);
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }

  function confirmAction(title, text, label, danger) {
    return new Promise((resolve) => {
      let ok = false;
      const yes = el("button", { class: "btn " + (danger ? "danger solid" : "primary"), onclick: () => { ok = true; d.close(); } }, label);
      const no = el("button", { class: "btn", onclick: () => d.close() }, "Cancel");
      const d = dialog(title, el("p", { style: null }, text), [no, yes]);
      d.addEventListener("close", () => resolve(ok));
      yes.focus();
    });
  }

  function bar(value, limit) {
    const pct = limit ? Math.min(100, (value / limit) * 100) : 0;
    const fill = el("i");
    fill.style.width = pct + "%";
    return el("div", { class: "bar" + (limit && value >= limit ? " over" : "") }, fill);
  }

  const KIND_LABEL = { command: "ran", edit: "edit", read: "read", web: "web", agent: "agent", other: "tool",
    voice: "voice", image: "image", video: "video", media: "media" };

  function actionsList(actions, limit) {
    if (!actions || !actions.length) return null;
    const shown = limit ? actions.slice(0, limit) : actions;
    return el("ul", { class: "actions" },
      shown.map((a) => el("li", { class: a.kind }, el("span", { class: "k" }, KIND_LABEL[a.kind] || "tool"), el("span", { class: "t" }, a.text))),
      limit && actions.length > limit ? el("li", null, el("span", { class: "k" }), el("span", { class: "t faint" }, `+${actions.length - limit} more`)) : null);
  }

  function toolPill(client) { return client ? el("span", { class: "pill tool" }, client) : null; }

  const CLASS_LABEL = { auxiliary: "background task", compaction: "compaction", workflow: "workflow" };

  function agentPills(r) {
    const out = [];
    if (r.agent) {
      const cut = r.agent.indexOf(":");
      const type = cut < 0 ? r.agent : r.agent.slice(0, cut);
      out.push(el("span", { class: "pill info", title: r.agent }, type === "sub-agent" ? "sub-agent" : "sub-agent · " + type));
    }
    if (r.request_class && CLASS_LABEL[r.request_class]) out.push(el("span", { class: "pill" }, CLASS_LABEL[r.request_class]));
    return out;
  }

  function outcomePill(r) {
    const map = {
      blocked: ["bad", "blocked"], denied: ["bad", "wrong key"], cut: ["bad", "cut off"],
      aborted: ["warn", "closed by the tool"], error: ["warn", "error"],
    };
    const hit = map[r.outcome];
    return hit ? el("span", { class: "pill " + hit[0] }, hit[1]) : null;
  }

  function flagPills(flags) {
    if (!flags) return [];
    return flags.split(",").filter(Boolean).map((f) => {
      if (f.startsWith("secret:")) return el("span", { class: "pill bad", title: f.slice(7) }, "credential");
      if (f.startsWith("attachments:")) return el("span", { class: "pill info" }, f.slice(12) + " file(s)");
      return el("span", { class: "pill" }, f);
    });
  }

  const refused = (r) => r.outcome === "blocked" || r.outcome === "denied";
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const usd = (v) => "$" + (Number.isInteger(v * 100) ? v.toFixed(2) : String(v));

  const units = (r) => (r.units ? `${Number(r.units).toLocaleString()} ${r.unit || ""}`.trim() : "");
  const isVideo = (u) => /\.(mp4|webm|mov)(\?|$)/i.test(u);
  function thumbs(urls) {
    return el("div", { class: "thumbs" }, urls.slice(0, 4).map((u) => isVideo(u)
      ? el("span", { class: "pill info" }, "video")
      : el("img", { src: u, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })));
  }

  const totalTokens = (r) => (r.in_tok || 0) + (r.out_tok || 0) + (r.cache_write_tok || 0) + (r.cache_read_tok || 0);

  function feedItem(r, opts) {
    opts = opts || {};
    const failed = r.outcome !== "ok";
    return el("li", { class: opts.fresh ? "fresh" : null },
      el("a", { class: "item", href: "#/records/" + r.id },
        el("div", { class: "when", title: fmt.stamp(r.ts) }, fmt.when(r.ts)),
        el("div", { class: "what" },
          el("div", { class: "line1" },
            opts.noPerson ? null : el("span", null, r.person || "Unknown key"),
            toolPill(r.client),
            agentPills(r),
            el("span", { class: "model" }, r.model || r.path || ""),
            outcomePill(r)),
          r.prompt ? el("div", { class: "prompt" }, r.prompt) : null,
          actionsList(r.actions, 4),
          (!r.actions.length || r.kind === "media") && r.reply ? el("div", { class: "reply" }, r.reply) : null,
          r.result_urls && r.result_urls.length ? thumbs(r.result_urls) : null,
          failed && r.reason ? el("div", { class: "err" }, r.reason) : null),
        el("div", { class: "side-meta" },
          refused(r) || (r.kind === "media" && r.cost === null) ? el("span", { class: "faint" }, "—") : el("span", null, fmt.money(r.cost)),
          refused(r) ? null : el("span", { class: "faint" }, r.kind === "media" ? units(r) : fmt.tokens(totalTokens(r)) + " tok"),
          el("span", { class: "row" }, flagPills(r.flags)))));
  }

  function longText(text, limit) {
    limit = limit || 2400;
    if (typeof text !== "string") text = JSON.stringify(text, null, 2);
    if (text.length <= limit) return el("pre", { class: "text" }, text);
    const pre = el("pre", { class: "text" }, text.slice(0, limit) + "…");
    const more = el("button", { class: "btn link", onclick: () => { pre.textContent = text; more.remove(); } },
      `Show all (${text.length.toLocaleString()} characters)`);
    return el("div", null, pre, more);
  }

  function code(obj, limit) {
    const text = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
    limit = limit || 6000;
    if (text.length <= limit) return el("pre", { class: "code" }, text);
    const pre = el("pre", { class: "code" }, text.slice(0, limit) + "\n…");
    const more = el("button", { class: "btn link", onclick: () => { pre.textContent = text; more.remove(); } },
      `Show all (${text.length.toLocaleString()} characters)`);
    return el("div", null, pre, more);
  }

  // ------------------------------------------------------------------ icons, theme, logos, side sheet

  function svg(paths) {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.9", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) s.setAttribute(k, v);
    paths.forEach((d) => { const p = document.createElementNS(ns, "path"); p.setAttribute("d", d); s.append(p); });
    return s;
  }
  const ICON = {
    live: ["M3 12h4l3-8l4 16l3-8h4"],
    activity: ["M8 6h13", "M8 12h13", "M8 18h13", "M3.5 6h.01", "M3.5 12h.01", "M3.5 18h.01"],
    people: ["M9 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8z", "M2.5 21v-.5A6.5 6.5 0 0 1 9 14h0a6.5 6.5 0 0 1 6.5 6.5v.5", "M16 3.6a4 4 0 0 1 0 7.3", "M18.5 14.4a6.5 6.5 0 0 1 3 5.6v1"],
    tools: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
    requests: ["M4 13.5L6.2 5h11.6L20 13.5", "M4 13.5V19h16v-5.5", "M4 13.5h5l1.2 2h3.6l1.2-2h5"],
    licences: ["M3 6.5h18v11H3z", "M3 10.5h18", "M7 14.5h4"],
    settings: ["M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z", "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3a1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8a1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"],
    audit: ["M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z", "M14 3v5h5", "M9 13h6", "M9 17h6"],
    sun: ["M12 2.5v2", "M12 19.5v2", "M4.6 4.6L6 6", "M18 18l1.4 1.4", "M2.5 12h2", "M19.5 12h2", "M4.6 19.4L6 18", "M18 6l1.4-1.4", "M12 7.5a4.5 4.5 0 1 0 0 9a4.5 4.5 0 1 0 0-9z"],
    moon: ["M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"],
    plus: ["M12 5v14", "M5 12h14"],
    open: ["M8 16L16 8", "M10 8h6v6"],
    clock: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7.5V12l3 2"],
    wallet: ["M4 7h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z", "M4 7l11-3v3", "M16 13h1.5"],
    stop: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M9 9h6v6H9z"],
    user: ["M12 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8z", "M4 21v-.5A7.5 7.5 0 0 1 11.5 13h1A7.5 7.5 0 0 1 20 20.5v.5"],
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

  const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  const gurl = (path) => GATEWAY + path;
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
  // logos and colours by tool id, for pages that only have a tool's id and name
  async function toolIndex() {
    if (!S.tools) {
      const cat = await api("GET", "/catalog");
      S.tools = Object.fromEntries([...cat.tools, ...cat.removed].map((t) => [t.id, t]));
      S.workspaceManaged = !!cat.workspace_managed;
    }
    return S.tools;
  }
  const toolLogo = (id, name, size) => logo((S.tools && S.tools[id]) || { name: name || "?" }, size);

  const SIGNIN = {
    sso: ["Company sign-in (SSO)", "Staff open it signed in with their Swangz work account. Set up single sign-on in the tool's admin settings and paste its sign-in link under Settings."],
    seat: ["Company seat", "Each person has their own seat on the company plan, invited to their work email. Swangz pays one bill for all seats."],
    shared: ["Shared company account", "One account the whole team uses. The portal hands it out a turn at a time, so whatever credits it burns can be traced to whoever held it, and the browser is signed out when the turn ends."],
    own: ["Own login", "Staff use their own account. Swangz controls access and keeps the record of who opened it."],
    api: ["Company API key", "Runs through this gateway on the company key — there is nothing to sign in to."],
  };
  const KIND = { site: "Website", api: "API + website", dev: "Developer agent" };
  const isoDate = (ts) => new Date(ts * 1000).toISOString().slice(0, 10);
  // a shared tool's workspace browsers, one address per line (gateway/workspace.py)
  const browserList = (t) => (t.workspace_url || "").split("\n").map((s) => s.trim()).filter(Boolean);
  const dateText = (ts) => new Date(ts * 1000).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });

  function sheet(onClose) {
    const scrim = el("div", { class: "scrim" });
    const node = el("aside", { class: "sheet", role: "dialog", "aria-modal": "true" });
    function close() {
      if (onClose) onClose();
      node.classList.remove("in"); scrim.classList.remove("in");
      setTimeout(() => { scrim.remove(); node.remove(); }, 320);
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) { if (e.key === "Escape" && !document.querySelector("dialog[open]")) close(); }
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.append(scrim, node);
    requestAnimationFrame(() => { scrim.classList.add("in"); node.classList.add("in"); });
    return { node, close };
  }

  // ------------------------------------------------------------------ sign-in and frame

  const AUTH_ERRORS = {
    cancelled: "Google sign-in was cancelled.",
    expired: "That sign-in took too long or was started in another browser. Try again.",
    google: "Google couldn't confirm that account. Try again.",
    no_account: "That Google account isn't a console user. An owner can add it under Settings → Console users (use the Google email as the username).",
    off: "Google sign-in isn't set up yet.",
  };
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

  function showSignIn() {
    clearTimers();
    const code = new URLSearchParams(location.search).get("auth_error");
    if (code) history.replaceState(null, "", location.pathname + location.hash);
    const err = el("div", { class: "err", role: "alert" }, code ? (AUTH_ERRORS[code] || "Sign-in didn't work. Try again.") : "");
    const google = el("div", { class: "google-box" });
    if (!GATEWAY) {
      fetch("/auth/options", { credentials: "include" }).then((r) => (r.ok ? r.json() : {})).then((opt) => {
        if (opt.google) google.append(el("a", { class: "btn google", href: "/auth/google/start?app=admin" }, googleMark(), "Continue with Google"),
          el("div", { class: "or" }, el("span", null, "or with a username")));
      }).catch(() => { /* no Google button */ });
    }
    const user = el("input", { type: "text", autocomplete: "username", required: true, autofocus: true });
    const pass = el("input", { type: "password", autocomplete: "current-password", required: true });
    const go = el("button", { class: "btn primary", type: "submit" }, "Sign in");
    const form = el("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        go.disabled = true;
        err.textContent = "";
        try {
          await api("POST", "/login", { username: user.value, password: pass.value });
          S.me = await api("GET", "/me");
          render();
        } catch (x) {
          err.textContent = x.message;
          go.disabled = false;
        }
      },
    },
    el("div", { class: "row" }, el("img", { src: "/static/icon.svg", alt: "", width: 44, height: 44 }),
      el("div", null, el("div", { class: "eyebrow" }, "Swangz AI"), el("h1", null, "Control room"))),
    el("p", { class: "muted", style: null }, "Tools, people, licences and spend — and the switches to stop it all."),
    google,
    el("label", { class: "field" }, "Username", user),
    el("label", { class: "field" }, "Password", pass),
    err, go);
    app.replaceChildren(el("div", { class: "signin" }, form));
    user.focus();
  }

  const NAV = [
    ["Overview", [["#/", "Live", "live"], ["#/activity", "Staff activity", "activity"]]],
    ["Access", [["#/people", "People", "people"], ["#/tools", "Tools", "tools"], ["#/requests", "Tool requests", "requests"]]],
    ["Money", [["#/licences", "Licences & spend", "licences"]]],
    ["System", [["#/settings", "Settings", "settings"], ["#/audit", "Audit log", "audit"]]],
  ];

  function frame(title, crumbs, content, actions) {
    const live = S.overview ? S.overview.live.length : 0;
    const paused = S.overview && S.overview.paused;
    const here = (location.hash || "#/").split("?")[0];
    const section = here === "#/" ? "#/" : "#/" + here.split("/")[1];
    const sectionFor = { "#/records": "#/activity", "#/sessions": "#/people" };
    const active = sectionFor[section] || section;
    const openReqs = S.overview ? (S.overview.open_requests || 0) : 0;
    const nav = el("nav", { class: "nav", "aria-label": "Sections" }, NAV.map(([group, links]) => [
      el("div", { class: "group" }, group),
      links.map(([href, label, icon]) => el("a", { href, class: href === active ? "on" : null, "aria-current": href === active ? "page" : null },
        svg(ICON[icon]), el("span", null, label),
        href === "#/" && live ? el("span", { class: "pill ok" }, el("span", { class: "dot pulse" }), String(live)) : null,
        href === "#/requests" && openReqs ? el("span", { class: "pill warn" }, String(openReqs)) : null))]));
    const side = el("aside", { class: "side" },
      el("div", { class: "brand" }, el("img", { src: "/static/icon.svg", alt: "" }), el("div", null, "Swangz ", el("b", null, "AI"), el("small", null, "Control room"))),
      nav, el("div", { class: "grow" }),
      el("div", { class: "who" }, el("span", { class: "avatar" }, initials(S.me.username)),
        el("div", { class: "id" }, el("strong", null, S.me.username), el("span", null, S.me.role)), themeButton()),
      el("div", { class: "who-actions" }, el("button", { class: "btn small quiet", onclick: signOut }, "Sign out")));
    const stopAll = isOwner() && !paused
      ? el("button", { class: "btn danger", onclick: () => setPaused(true) }, svg(ICON.stop), "Stop all AI") : null;
    const banner = paused ? el("div", { class: "banner", role: "alert" },
      el("span", null, "AI access is paused for everyone. Requests and tool launches are being refused."),
      isOwner() ? el("button", { class: "btn primary", onclick: () => setPaused(false) }, "Resume access") : null) : null;
    const top = el("div", { class: "top" },
      el("div", null, crumbs ? el("div", { class: "crumbs" }, crumbs) : null, el("h1", null, title)),
      el("div", { class: "top-actions" }, actions, stopAll));
    return el("div", { class: "shell" }, side, el("main", { class: "main" }, banner, top, el("div", { class: "page" }, content)));
  }

  async function signOut() {
    try { await api("POST", "/logout"); } catch (e) { /* already out */ }
    S.me = null;
    showSignIn();
  }

  async function setPaused(paused) {
    if (paused) {
      const ok = await confirmAction("Stop all AI?",
        "Every request in flight is cut now, and every new one is refused until you resume. Use this if something is going wrong.",
        "Stop everything", true);
      if (!ok) return;
    }
    try {
      const out = await api("POST", "/pause", { paused });
      toast(paused ? `Paused. ${out.cut} request(s) cut.` : "Access resumed.");
      await refreshOverview();
      render();
    } catch (e) { toast(e.message, true); }
  }

  async function refreshOverview() {
    try { S.overview = await api("GET", "/overview"); } catch (e) { /* shown elsewhere */ }
    return S.overview;
  }

  // ------------------------------------------------------------------ routing

  const ROUTES = [
    [/^#?\/?$/, pageLive],
    [/^#\/people$/, pagePeople],
    [/^#\/people\/(\d+)$/, pagePerson],
    [/^#\/tools$/, pageTools],
    [/^#\/requests$/, pageRequests],
    [/^#\/sessions\/(.+)$/, pageSession],
    [/^#\/records\/(\d+)$/, pageRecord],
    [/^#\/activity$/, pageActivity],
    [/^#\/licences$/, pageLicences],
    [/^#\/settings$/, pageSettings],
    [/^#\/audit$/, pageAudit],
  ];

  async function render() {
    clearTimers();
    document.querySelectorAll(".sheet, .scrim").forEach((n) => n.remove());
    if (!S.me) {
      try { S.me = await api("GET", "/me"); } catch (e) { return; }
    }
    await refreshOverview(); // the live badge and pause banner are never staler than the page
    const [path, query] = (location.hash || "#/").split("?");
    const params = new URLSearchParams(query || "");
    for (const [rx, page] of ROUTES) {
      const m = path.match(rx);
      if (m) {
        S.route = location.hash;
        try {
          await page(params, ...m.slice(1).map(decodeURIComponent));
        } catch (e) {
          if (e.status !== 401) app.replaceChildren(frame("Something went wrong", null, panel("Error", null, el("div", { class: "body err" }, e.message))));
        }
        window.scrollTo(0, 0);
        return;
      }
    }
    location.hash = "#/";
  }

  window.addEventListener("hashchange", render);

  // ------------------------------------------------------------------ Live

  async function pageLive() {
    const kpis = el("div", { class: "kpis" });
    const liveBody = el("div");
    const feed = el("ul", { class: "feed" });
    const people = el("div");
    const models = el("div");
    const tools = el("div");
    const opens = el("div");
    const sharedBody = el("div");
    const sharedPanel = panel("Shared company accounts", "who is on one now", sharedBody);
    await toolIndex().catch(() => null);
    app.replaceChildren(frame("Live", null, [
      kpis,
      el("div", { class: "grid cols-2" },
        el("div", { class: "grid" },
          panel("Working right now", "streams in flight", liveBody),
          panel("Activity", el("a", { href: "#/activity", class: "btn small" }, "Search everything"), feed)),
        el("div", { class: "grid" },
          sharedPanel,
          panel("Opened from the portal", "today", opens),
          panel("Today by person", "spend", people),
          panel("This month by model", null, models),
          panel("This month by tool", null, tools))),
    ]));

    let maxId = 0;

    function drawOverview(ov) {
      const t = ov.today, m = ov.month;
      kpis.replaceChildren(
        kpi("Spent today", fmt.money(t.cost), `${fmt.money(m.cost)} this month`),
        kpi("Tool opens today", String(ov.launches_today || 0), (ov.tools_today || []).length ? "most: " + ov.tools_today[0].name : "from the portal"),
        kpi("Requests today", t.requests.toLocaleString(), `${fmt.tokens(t.tokens)} tokens`),
        kpi("People active today", String(t.people), `${ov.live.length} working right now`),
        kpi("Refused or cut today", String(t.blocked + t.denied + t.cut), `${t.denied} with a wrong key`, t.denied > 0),
        kpi("Credentials in prompts", String(t.secrets), "today", t.secrets > 0));
      liveBody.replaceChildren(ov.live.length ? el("div", { class: "live-list" }, ov.live.map(liveCard)) : empty("Nobody is waiting on a model right now."));
      people.replaceChildren(ov.people_today.length ? spendBars(ov.people_today, (p) => el("a", { href: "#/people/" + p.id }, p.name), (p) => `${p.requests} req · ${fmt.ago(p.last)}`) : empty("No activity yet today."));
      models.replaceChildren(ov.models_month.length ? spendBars(ov.models_month, (x) => x.model, (x) => `${x.requests} req` + (x.unpriced ? ` · ${x.unpriced} unpriced` : "")) : empty("No model calls this month."));
      tools.replaceChildren(ov.clients_month.length ? spendBars(ov.clients_month, (x) => x.client, (x) => `${x.requests} req`) : empty("—"));
    }

    function kpi(label, value, note, alert) {
      return el("div", { class: "kpi" + (alert ? " alert" : "") }, el("div", { class: "label" }, label), el("div", { class: "value" }, value), el("div", { class: "note" }, note));
    }

    function liveCard(t) {
      return el("div", { class: "live-card" },
        el("div", null,
          el("div", { class: "row" }, el("span", { class: "dot pulse" }), el("a", { href: "#/people/" + t.person_id }, el("strong", null, t.person)), toolPill(t.client), el("span", { class: "faint mono" }, t.model || "")),
          t.prompt ? el("div", { class: "p" }, "“" + t.prompt + "”") : el("div", { class: "p faint" }, "agent working on its own"),
          el("div", { class: "hint" }, `${fmt.elapsed(t.started)} · ${t.streaming ? fmt.tokens(t.bytes) + "B streamed" : "waiting for the model"}`)),
        isOwner() ? el("button", { class: "btn danger small", onclick: () => cut(t) }, "Stop") : null);
    }

    async function cut(t) {
      const ok = await confirmAction("Stop this request?", `${t.person}'s ${t.client} request is cut now. Their key keeps working for the next one.`, "Stop it", true);
      if (!ok) return;
      try { await api("POST", `/live/${t.id}/cut`); toast("Stopped."); tick(); } catch (e) { toast(e.message, true); }
    }

    async function loadFeed() {
      const first = maxId === 0;
      const data = await api("GET", first ? "/requests?limit=40" : `/requests?after=${maxId}&limit=100`);
      if (!data.items.length) {
        if (first) feed.replaceChildren(el("li", null, empty("No requests yet. Issue someone a key under People, then point their tool at the gateway.")));
        return;
      }
      if (first) feed.replaceChildren();
      maxId = Math.max(maxId, ...data.items.map((r) => r.id));
      const nodes = data.items.map((r) => feedItem(r, { fresh: !first }));
      feed.prepend(...nodes);
      while (feed.children.length > 80) feed.lastChild.remove();
    }

    async function loadShared() {
      const data = await api("GET", "/turns");
      if (!data.tools.length) { sharedPanel.hidden = true; return; }
      sharedPanel.hidden = false;
      sharedBody.replaceChildren(data.now.length
        ? el("ul", { class: "opens" }, data.now.map((x) => el("li", null,
          toolLogo(x.tool_id, x.tool, "sm"),
          el("div", { class: "who-line" }, el("a", { href: "#/people/" + x.person_id }, el("strong", null, x.person)),
            el("span", { class: "muted" }, " is on "), el("strong", null, x.tool)),
          el("span", { class: "pill warn nowrap" }, "until " + new Date(x.expires * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })))))
        : empty(`Nobody is on a shared account. ${data.tools.length} tool(s) are set up this way.`));
    }

    async function loadOpens() {
      const data = await api("GET", "/launches?since=" + (S.overview ? S.overview.day_start : 0));
      opens.replaceChildren(data.items.length ? opensList(data.items.slice(0, 12)) : empty("Nobody has opened a tool from the portal today."));
    }

    let n = 0;
    async function tick() {
      const ov = await refreshOverview();
      if (ov) drawOverview(ov);
      await loadFeed();
      if (++n % 4 === 0) await Promise.all([loadOpens(), loadShared()]);
    }

    drawOverview(S.overview);
    await Promise.all([loadFeed(), loadOpens(), loadShared()]);
    every(2500, tick);
  }

  function opensList(items, noPerson) {
    return el("ul", { class: "opens" }, items.map((o) => el("li", null,
      toolLogo(o.tool_id, o.tool, "sm"),
      el("div", { class: "who-line" },
        noPerson ? el("strong", null, o.tool || "a removed tool")
          : [el("a", { href: "#/people/" + o.person_id }, el("strong", null, o.person || "Someone")), el("span", { class: "muted" }, " opened "), el("strong", null, o.tool || "a removed tool")]),
      el("span", { class: "row nowrap" },
        o.outcome === "refused" ? el("span", { class: "pill bad" }, "refused") : null,
        el("span", { class: "hint nowrap", title: fmt.stamp(o.ts) }, fmt.ago(o.ts))))));
  }

  function spendBars(rows, name, note) {
    const top = Math.max(...rows.map((r) => r.cost || 0), 0.0000001);
    return el("ul", { class: "bars" }, rows.map((r) => el("li", null,
      el("div", { class: "spread" }, el("span", null, name(r)), el("span", { class: "num" }, fmt.money(r.cost))),
      bar(r.cost || 0, top * 1.0000001),
      el("div", { class: "hint" }, note(r)))));
  }

  // ------------------------------------------------------------------ People

  async function pagePeople() {
    const data = await api("GET", "/people");
    const rows = data.items.map((p) => el("tr", { class: "click", onclick: () => { location.hash = "#/people/" + p.id; } },
      el("td", null, el("div", { class: "person-cell" }, el("span", { class: "avatar" }, initials(p.name)),
        el("div", null, el("a", { href: "#/people/" + p.id }, el("strong", null, p.name)), el("div", { class: "hint" }, [p.title, p.department].filter(Boolean).join(" · ") || "—")))),
      el("td", null, p.status === "active" ? (p.access_until && p.access_until <= Date.now() / 1000 ? el("span", { class: "pill bad" }, "ended")
        : el("span", { class: "pill ok" }, "active")) : el("span", { class: "pill bad" }, "suspended"),
        " ", signInPill(p.sign_in),
        p.live ? el("span", { class: "pill ok" }, el("span", { class: "dot pulse" }), " live") : null),
      el("td", { class: "num" }, String(p.active_keys)),
      el("td", { class: "num" }, fmt.money(p.today.cost), el("div", { class: "hint" }, `${p.today.requests} req`),
        p.daily_budget !== null ? bar(p.today.cost, p.daily_budget) : null),
      el("td", { class: "num" }, fmt.money(p.month.cost), el("div", { class: "hint" }, p.monthly_budget !== null ? `of ${fmt.money(p.monthly_budget)}` : "no limit"),
        p.monthly_budget !== null ? bar(p.month.cost, p.monthly_budget) : null),
      el("td", { class: "nowrap muted" }, fmt.ago(p.last_seen))));
    const table = data.items.length
      ? el("div", { class: "table-wrap" }, el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Person"), el("th", null, "Status"), el("th", { class: "num" }, "Keys"), el("th", { class: "num" }, "Today"), el("th", { class: "num" }, "This month"), el("th", null, "Last used AI"))),
        el("tbody", null, rows)))
      : empty("Nobody yet. Add the first person, then issue them a key.");
    const add = isOwner() ? el("button", { class: "btn primary", onclick: addPerson }, "Add person") : null;
    app.replaceChildren(frame("People", null, panel("Everyone with gateway access", `${data.items.length} people`, table), add));
  }

  function signInPill(state) {
    if (state === "active") return el("span", { class: "pill", title: "Signs in to the Swangz AI app" }, "app ✓");
    if (state === "invited") return el("span", { class: "pill warn", title: "Sign-in link sent, not used yet" }, "invited");
    return el("span", { class: "pill", title: "Has no Swangz AI app sign-in yet" }, "no app sign-in");
  }

  function personForm(p) {
    p = p || {};
    const f = {
      name: el("input", { type: "text", value: p.name || "", required: true }),
      title: el("input", { type: "text", value: p.title || "", placeholder: "e.g. Director" }),
      department: el("input", { type: "text", value: p.department || "", placeholder: "e.g. Production" }),
      email: el("input", { type: "text", value: p.email || "" }),
      daily_budget: el("input", { type: "number", min: "0", step: "0.01", value: p.daily_budget ?? "", placeholder: "no limit" }),
      monthly_budget: el("input", { type: "number", min: "0", step: "0.01", value: p.monthly_budget ?? "", placeholder: "no limit" }),
      allowed_models: el("input", { type: "text", value: p.allowed_models || "", placeholder: "all models" }),
      allowed_services: el("input", { type: "text", value: p.allowed_services || "", placeholder: "every service" }),
      notes: el("textarea", null, p.notes || ""),
      access_until: el("input", { type: "date", value: p.access_until ? isoDate(p.access_until - 86400) : "" }),
    };
    f.budget_visible = el("input", { type: "checkbox", checked: !!p.budget_visible });
    const node = el("div", { class: "stack" },
      el("div", { class: "form-grid" },
        el("label", { class: "field" }, "Name", f.name),
        el("label", { class: "field" }, "Role / title", f.title),
        el("label", { class: "field" }, "Department", f.department),
        el("label", { class: "field" }, "Email — they sign in with it", f.email,
          el("span", { class: "hint" }, "A Swangz email (@swangzavenue.com). The owner and demo accounts are the only exceptions."))),
      el("div", { class: "form-grid" },
        el("label", { class: "field" }, "Daily budget (USD)", f.daily_budget),
        el("label", { class: "field" }, "Monthly budget (USD)", f.monthly_budget),
        el("label", { class: "field" }, "Access ends on", f.access_until,
          el("span", { class: "hint" }, "Optional — for contractors and temporary staff. Every tool and key stops after this day."))),
      el("label", { class: "check" }, f.budget_visible, el("span", null, el("strong", null, "Let this person see their budget"),
        el("div", { class: "hint" }, "Off by default — staff don't see the budget set for them until you turn this on."))),
      el("label", { class: "field" }, "Allowed models", f.allowed_models,
        el("span", { class: "hint" }, "Comma-separated, * works as a wildcard: claude-sonnet-*, gpt-6-*. Empty = any model. Through a gateway, Claude Code runs its background tasks on the main model, so allowing that model is enough.")),
      el("label", { class: "field" }, "Allowed services", f.allowed_services,
        el("span", { class: "hint" }, "Comma-separated: " + S.me.providers.map((x) => x.name).join(", ") + ". Empty = every service the company has switched on.")),
      el("label", { class: "field" }, "Notes", f.notes));
    const values = () => Object.fromEntries(Object.entries(f).map(([k, input]) =>
      [k, input.type === "checkbox" ? input.checked : input.value]));
    return { node, values, focus: () => f.name.focus() };
  }

  function addPerson() {
    const form = personForm();
    const err = el("div", { class: "err" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try {
        const out = await api("POST", "/people", form.values());
        d.close();
        location.hash = "#/people/" + out.id;
      } catch (e) { err.textContent = e.message; }
    } }, "Add person");
    const d = dialog("Add a person", [form.node, err], [save]);
    form.focus();
  }

  async function pagePerson(params, id) {
    const p = await api("GET", "/people/" + id);
    const owner = isOwner();
    const ended = p.access_until && p.access_until <= Date.now() / 1000;
    const statusPill = p.status !== "active" ? el("span", { class: "pill bad" }, "suspended")
      : ended ? el("span", { class: "pill bad" }, "access ended") : el("span", { class: "pill ok" }, "active");
    const toggle = owner ? (p.status === "active"
      ? el("button", { class: "btn danger", onclick: () => suspend(true) }, "Suspend access")
      : el("button", { class: "btn primary", onclick: () => suspend(false) }, "Restore access")) : null;

    async function suspend(on) {
      if (on) {
        const ok = await confirmAction(`Suspend ${p.name}?`, "Every key they hold stops working now, anything they have streaming is cut, and the portal stops opening tools for them. You can restore access later.", "Suspend", true);
        if (!ok) return;
      }
      try {
        const out = await api("POST", `/people/${p.id}/${on ? "suspend" : "resume"}`);
        toast(on ? `Suspended. ${out.cut} request(s) cut.` : "Access restored.");
        render();
      } catch (e) { toast(e.message, true); }
    }

    async function revoke(k) {
      const ok = await confirmAction(`Revoke “${k.label}”?`, `${k.hint} stops working immediately, including anything it is streaming right now. This can't be undone — issue a new key instead.`, "Revoke key", true);
      if (!ok) return;
      try {
        const out = await api("POST", `/keys/${k.id}/revoke`);
        toast(`Revoked. ${out.cut} request(s) cut.`);
        render();
      } catch (e) { toast(e.message, true); }
    }

    await toolIndex().catch(() => null);

    // ---- Overview
    async function overviewTab() {
      const kpis = el("div", { class: "kpis" },
        el("div", { class: "kpi" }, el("div", { class: "label" }, svg(ICON.wallet), "Spent today"), el("div", { class: "value" }, fmt.money(p.today.cost)),
          el("div", { class: "note" }, p.daily_budget !== null ? `of ${fmt.money(p.daily_budget)} daily budget` : "no daily limit"), p.daily_budget !== null ? bar(p.today.cost, p.daily_budget) : null),
        el("div", { class: "kpi" }, el("div", { class: "label" }, svg(ICON.wallet), "Spent this month"), el("div", { class: "value" }, fmt.money(p.month.cost)),
          el("div", { class: "note" }, p.monthly_budget !== null ? `of ${fmt.money(p.monthly_budget)} monthly budget` : "no monthly limit"), p.monthly_budget !== null ? bar(p.month.cost, p.monthly_budget) : null),
        el("div", { class: "kpi" }, el("div", { class: "label" }, svg(ICON.tools), "Tools ready"), el("div", { class: "value" }, String(p.tool_summary.enabled)),
          el("div", { class: "note" }, `${p.tool_summary.assigned} assigned to them`)),
        el("div", { class: "kpi" }, el("div", { class: "label" }, svg(ICON.settings), "Allowed"), el("div", { class: "value", style: null }, p.allowed_models || p.allowed_services ? "limited" : "everything"),
          el("div", { class: "note" }, [p.allowed_services && "services: " + p.allowed_services, p.allowed_models && "models: " + p.allowed_models].filter(Boolean).join(" · ") || "every service and model")));
      const live = p.live.length ? panel("Working right now", null, el("div", { class: "live-list" }, p.live.map((t) => el("div", { class: "live-card" },
        el("div", null, el("div", { class: "row" }, el("span", { class: "dot pulse" }), toolPill(t.client), el("span", { class: "faint mono" }, t.model || "")),
          t.prompt ? el("div", { class: "p" }, "“" + t.prompt + "”") : null, el("div", { class: "hint" }, fmt.elapsed(t.started))))))) : null;
      const launches = await api("GET", `/launches?person=${p.id}`);
      const opensPanel = panel("Tools opened from the portal", "last 30 days",
        launches.items.length ? opensList(launches.items.slice(0, 10), true) : empty("Hasn't opened a tool from the portal yet."));
      const sessions = p.sessions.length ? el("ul", { class: "feed" }, p.sessions.slice(0, 8).map((x) => el("li", null,
        el("a", { class: "item", href: "#/sessions/" + encodeURIComponent(x.session) },
          el("div", { class: "when", title: fmt.stamp(x.started) }, fmt.when(x.last)),
          el("div", { class: "what" }, el("div", { class: "line1" }, toolPill(x.client), el("span", { class: "model" }, plural(x.requests, "request"))),
            x.first_prompt ? el("div", { class: "prompt" }, x.first_prompt) : el("div", { class: "reply" }, "(no typed prompt recorded)")),
          el("div", { class: "side-meta" }, fmt.money(x.cost)))))) : empty("No sessions yet.");
      return [kpis, live, el("div", { class: "grid cols-even" }, opensPanel,
        panel("Recent sessions", "one conversation each", sessions)),
        p.notes ? panel("Notes", null, el("div", { class: "body" }, longText(p.notes))) : null];
    }

    // ---- Tools
    async function toolsTab() {
      return personToolsPanel(p, owner);
    }

    // ---- Activity
    async function activityTab() {
      const recent = el("ul", { class: "feed" });
      const data = await api("GET", `/requests?person=${p.id}&limit=40`);
      recent.replaceChildren(...(data.items.length ? data.items.map((r) => feedItem(r, { noPerson: true })) : [el("li", null, empty("Nothing through the gateway yet."))]));
      const sessions = p.sessions.length ? el("ul", { class: "feed" }, p.sessions.map((x) => el("li", null,
        el("a", { class: "item", href: "#/sessions/" + encodeURIComponent(x.session) },
          el("div", { class: "when", title: fmt.stamp(x.started) }, fmt.when(x.last)),
          el("div", { class: "what" }, el("div", { class: "line1" }, toolPill(x.client), el("span", { class: "model" }, plural(x.requests, "request"))),
            x.first_prompt ? el("div", { class: "prompt" }, x.first_prompt) : el("div", { class: "reply" }, "(no typed prompt recorded)")),
          el("div", { class: "side-meta" }, fmt.money(x.cost)))))) : empty("No sessions yet.");
      return [
        panel("Through the gateway", el("a", { class: "btn small", href: `#/activity?tab=ai&person=${p.id}` }, "Search all"), recent),
        panel("Sessions", "one conversation each — open one to see everything that happened", sessions),
      ];
    }

    // ---- Devices & sign-in
    async function devicesTab() {
      const keyRows = p.keys.length ? el("ul", { class: "keys" }, p.keys.map((k) => el("li", { class: k.revoked ? "revoked" : null },
        el("div", null,
          el("strong", null, k.label),
          el("div", { class: "hint mono" }, k.hint),
          el("div", { class: "hint" }, (k.created_by === "self" ? `added by them in the app ${fmt.ago(k.created)}` : `issued ${fmt.ago(k.created)}` + (k.created_by ? ` by ${k.created_by}` : "")) + ` · last used ${fmt.ago(k.last_used)}`),
          k.revoked ? el("div", { class: "hint" }, `revoked ${fmt.ago(k.revoked)}` + (k.revoked_by === "self" ? " by them in the app" : k.revoked_by ? ` by ${k.revoked_by}` : "")) : null),
        k.revoked ? el("span", { class: "pill bad" }, "revoked")
          : owner ? el("button", { class: "btn danger small", onclick: () => revoke(k) }, "Revoke") : el("span", { class: "pill ok" }, "active")))) : empty("No keys yet.");
      const signInState = { active: "Signs in to the Swangz AI app" + (p.last_login ? ` · last signed in ${fmt.ago(p.last_login)}` : ""),
        invited: `Sign-in link sent — valid until ${fmt.stamp(p.invite_expires)}`, none: "No app sign-in yet" }[p.sign_in];
      const signIn = panel("Swangz AI app", null, el("div", { class: "body stack" },
        el("div", null, signInPill(p.sign_in), " ", el("span", { class: "muted" }, signInState)),
        el("div", { class: "hint" }, p.email ? `They sign in at ${S.me.base_url}/ with ${p.email}, or with Continue with Google if that email is their Google account.`
          : "Add their email under Details first — it is what they sign in with."),
        owner && p.email ? el("div", null, el("button", { class: "btn", onclick: () => inviteLink(p) }, p.sign_in === "active" ? "New sign-in link (reset password)" : "Create sign-in link")) : null));
      return [signIn, panel("Keys", "one per device or coding tool", keyRows)];
    }

    // ---- Details
    async function detailsTab() {
      if (!owner) return panel("Details", null, el("div", { class: "body hint" }, "Only an owner can change someone's details."));
      const form = personForm(p);
      const err = el("div", { class: "err" });
      return panel("Details and limits", null, el("div", { class: "body stack" }, form.node, err,
        el("div", null, el("button", { class: "btn primary", onclick: async () => {
          try { await api("PATCH", "/people/" + p.id, form.values()); toast("Saved."); render(); } catch (e) { err.textContent = e.message; }
        } }, "Save changes"))));
    }

    const issue = owner && p.status === "active" ? el("button", { class: "btn primary", onclick: () => issueKey(p) }, "Issue a key") : null;
    app.replaceChildren(frame(p.name, el("a", { href: "#/people" }, "People"), [
      el("div", { class: "row", style: null }, statusPill, el("span", { class: "muted" }, [p.title, p.department, p.email].filter(Boolean).join(" · ")),
        p.access_until ? el("span", { class: "pill " + (ended ? "bad" : "warn") },
          (ended ? "access ended " : "access until ") + dateText(p.access_until - 86400)) : null),
      el("div", { style: null, class: "spacer" }),
      pageTabs("#/people/" + p.id, params, [
        ["overview", "Overview", overviewTab],
        ["tools", "Tools", toolsTab, p.tool_summary.enabled],
        ["activity", "Activity", activityTab],
        ["devices", "Devices & sign-in", devicesTab],
        ["details", "Details", detailsTab],
      ]),
    ], [el("a", { class: "btn", href: gadmin(`/export.csv?person=${p.id}`) }, "Export CSV"), issue, toggle]));
  }

  function personToolsPanel(p, owner) {
    const tools = p.tools || [];
    const grid = el("div", { class: "ptools" });
    function cell(t) {
      const can = owner && t.state !== "locked" && t.grant !== "team";  // team grants are changed on the Tools page
      const on = t.state === "enabled";
      const label = t.grant === "team" ? "Team" : t.state === "locked" ? "Locked" : on ? "On" : "Off";
      const btn = el("button", {
        class: "btn small" + (on && t.grant !== "team" ? " primary" : ""), disabled: !can,
        title: t.grant === "team" ? "Granted to the whole " + (p.department || "team") : t.reason,
        onclick: can ? async () => {
          const adding = !btn.classList.contains("primary");
          try { await api(adding ? "POST" : "DELETE", `/people/${p.id}/tools/${t.id}`); render(); }
          catch (e) { toast(e.message, true); }
        } : null,
      }, label);
      const note = t.state === "locked" ? "not subscribed" : t.ends ? "until " + dateText(t.ends - 86400) : t.category;
      return el("div", { class: "ptool" + (on ? " on" : "") }, logo(t, "sm"),
        el("div", { class: "pn" }, el("strong", null, t.name), el("div", { class: "hint" }, note)), btn);
    }
    const assigned = tools.filter((t) => t.assigned);
    const rest = tools.filter((t) => !t.assigned && t.state !== "locked");
    grid.replaceChildren(...assigned.map(cell), ...rest.map(cell));
    const removeAll = owner && assigned.some((t) => t.grant === "direct") ? el("button", { class: "btn small danger", onclick: async () => {
      const ok = await confirmAction(`Remove every tool from ${p.name}?`, "Their direct tool access is removed now. Team access stays with the team, and their account stays open — suspend it too if they're leaving.", "Remove all tools", true);
      if (!ok) return;
      try { const out = await api("DELETE", `/people/${p.id}/tools`); toast(`Removed ${out.removed} tool(s).`); render(); } catch (e) { toast(e.message, true); }
    } }, "Remove all tools") : null;
    return panel("Tools", el("div", { class: "row" }, el("span", null, `${p.tool_summary.enabled} ready · ${p.tool_summary.assigned} assigned`), removeAll),
      tools.length ? grid : empty("No tools in the catalog."),
      el("div", { class: "body hint" }, "Locked tools need a company subscription first, and team access is changed — both on the Tools page. To give a tool for a limited time, set an end date there under Who can use it."));
  }

  async function inviteLink(p) {
    try {
      const out = await api("POST", `/people/${p.id}/invite`);
      const text = `Hi ${p.name}, here is your Swangz AI sign-in link (valid ${out.expires_days} days): ${out.link}`;
      dialog(`Sign-in link for ${p.name}`, el("div", { class: "stack" },
        el("p", { class: "muted", style: null }, `Send this to ${p.name} privately. It works once, for ${out.expires_days} days, and lets them choose a password for ${out.email}. Any older link stops working.`),
        el("div", { class: "spread" }, el("div", { class: "keybox" }, out.link), el("button", { class: "btn", onclick: () => copy(out.link) }, "Copy link"))),
      [el("a", { class: "btn", href: "https://wa.me/?text=" + encodeURIComponent(text), target: "_blank", rel: "noopener noreferrer" }, "Share on WhatsApp"),
        el("button", { class: "btn primary", onclick: (e) => { e.target.closest("dialog").close(); render(); } }, "Done")]);
    } catch (e) { toast(e.message, true); }
  }

  function issueKey(p) {
    const label = el("input", { type: "text", placeholder: "e.g. Grace's MacBook — Claude Code", value: "" });
    const err = el("div", { class: "err" });
    const go = el("button", { class: "btn primary", onclick: async () => {
      try {
        const out = await api("POST", `/people/${p.id}/keys`, { label: label.value });
        d.close();
        showNewKey(p, out);
      } catch (e) { err.textContent = e.message; }
    } }, "Issue key");
    const d = dialog(`New key for ${p.name}`, el("div", { class: "stack" },
      el("label", { class: "field" }, "What is it for?", label, el("span", { class: "hint" }, "One key per device or tool, so you can revoke one without stopping the rest.")), err), [go]);
    label.focus();
  }

  function showNewKey(p, out) {
    const blocks = out.tools.map((t) => el("details", { open: t.id === "claude-code" ? true : null },
      el("summary", null, t.name, el("span", { class: "faint" }, " — " + t.kind)),
      t.steps.map((s) => el("div", { class: "stack", style: null },
        el("div", { class: "spread" }, el("strong", null, s.title), el("button", { class: "btn small", onclick: () => copy(s.code) }, "Copy")),
        el("div", { class: "hint" }, s.how),
        el("pre", { class: "code" }, s.code)))));
    const done = el("button", { class: "btn primary", onclick: () => { d.close(); render(); } }, "I've saved it");
    const d = dialog(`Key for ${p.name}`, el("div", { class: "stack" },
      el("p", { class: "err", style: null }, "This is the only time the key is shown. Copy it now and give it to them privately."),
      el("div", { class: "spread" }, el("div", { class: "keybox", style: null }, out.key), el("button", { class: "btn", onclick: () => copy(out.key) }, "Copy key")),
      el("h3", { style: null }, "How to connect their tools"),
      blocks), [done]);
  }

  // ------------------------------------------------------------------ Session

  async function pageSession(params, sid) {
    const s = await api("GET", "/sessions/" + encodeURIComponent(sid));
    const turns = s.items.map((r) => el("div", { class: "turn" },
      el("div", { class: "when", title: fmt.stamp(r.ts) }, fmt.when(r.ts), el("div", { class: "hint" }, new Date(r.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }))),
      el("div", null,
        r.agent || r.request_class ? el("div", { class: "row" }, agentPills(r)) : null,
        r.prompt ? el("div", { class: "bubble" }, r.prompt) : null,
        actionsList(r.actions),
        r.reply ? el("div", { class: "said" }, r.reply) : null,
        r.outcome !== "ok" ? el("div", { class: "err" }, outcomePill(r), " ", r.reason || "") : null,
        el("div", { class: "hint", style: null }, `${r.model || ""} · ${fmt.tokens(totalTokens(r))} tokens · ${fmt.money(r.cost)} · `,
          el("a", { href: "#/records/" + r.id }, "full record")))));
    app.replaceChildren(frame("Session", el("span", null, el("a", { href: "#/people/" + s.person_id }, s.person || "Unknown"), " · ", s.client), [
      el("div", { class: "meta" },
        metaCell("Person", el("a", { href: "#/people/" + s.person_id }, s.person || "—")),
        metaCell("Tool", s.client || "—"),
        metaCell("Started", fmt.stamp(s.started)),
        metaCell("Last request", fmt.stamp(s.last)),
        metaCell("Requests", String(s.items.length)),
        metaCell("Cost", fmt.money(s.cost)),
        metaCell("Session id", el("span", { class: "mono" }, s.session))),
      el("div", { class: "spacer" }),
      panel("Everything that happened", "typed prompts, then every command, edit and reply, in order", turns),
    ]));
  }

  function metaCell(k, v) { return el("div", null, el("div", { class: "k" }, k), el("div", { class: "v" }, v)); }

  // ------------------------------------------------------------------ Record

  async function pageRecord(params, id) {
    const r = await api("GET", "/requests/" + id);
    const tokens = `${fmt.tokens(r.in_tok)} in · ${fmt.tokens(r.out_tok)} out` +
      (r.cache_read_tok ? ` · ${fmt.tokens(r.cache_read_tok)} cache read` : "") + (r.cache_write_tok ? ` · ${fmt.tokens(r.cache_write_tok)} cache write` : "") +
      (r.reasoning_tok ? ` · ${fmt.tokens(r.reasoning_tok)} reasoning` : "");
    const meta = el("div", { class: "meta" },
      metaCell("Person", r.person_id ? el("a", { href: "#/people/" + r.person_id }, r.person) : "— (no valid key)"),
      metaCell("Key", r.key_label ? `${r.key_label}` : r.key_id || "—"),
      metaCell("Tool", el("span", null, r.client || "—", " ", agentPills(r))),
      metaCell("Model", el("span", { class: "mono" }, r.model || "—")),
      metaCell("When", fmt.stamp(r.ts)),
      metaCell("Took", `${fmt.ms(r.duration_ms)}` + (r.ttft_ms ? ` (first byte ${fmt.ms(r.ttft_ms)})` : "")),
      metaCell(r.kind === "media" ? "Size" : "Tokens", r.kind === "media" ? (units(r) || "—") : tokens),
      metaCell("Cost", r.kind === "media" && r.cost === null ? "—" : fmt.money(r.cost)),
      metaCell("Outcome", el("span", null, r.outcome === "ok" ? el("span", { class: "pill ok" }, "ok") : outcomePill(r), " ", r.reason || "", r.status ? el("span", { class: "faint" }, ` HTTP ${r.status}`) : null)),
      metaCell("Session", r.session ? el("a", { class: "mono", href: "#/sessions/" + encodeURIComponent(r.session) }, r.session.slice(0, 18) + (r.session.length > 18 ? "…" : "")) : "—"),
      metaCell("From", el("span", { class: "mono" }, r.client_ip || "—")),
      metaCell("Endpoint", el("span", { class: "mono" }, `${r.provider} ${r.method} ${r.path}`)));

    const summary = panel("In short", flagPills(r.flags), el("div", { class: "body stack" },
      r.prompt ? el("div", null, el("div", { class: "tag" }, r.kind === "media" ? "They asked for" : "They typed"), el("div", { class: "bubble" }, r.prompt)) : el("div", { class: "hint" }, "Nothing typed in this request — the tool was sending results back to the model on its own."),
      r.actions.length ? el("div", null, el("div", { class: "tag" }, r.kind === "media" ? "Request" : "The model did"), actionsList(r.actions)) : null,
      r.reply ? el("div", null, el("div", { class: "tag" }, r.kind === "media" ? "Result" : "The model said"), longText(r.reply)) : null));

    const download = el("a", { class: "btn", href: gadmin(`/requests/${r.id}?download=1`) }, "Download JSON");
    const isAudio = (r.resp_ctype || "").startsWith("audio/");
    const mediaPanel = isAudio || (r.result_urls && r.result_urls.length) ? panel("What was made", null, el("div", { class: "body stack" },
      isAudio ? el("audio", { controls: true, preload: "none", src: gadmin(`/requests/${r.id}/media`), crossorigin: GATEWAY ? "use-credentials" : null }) : null,
      (r.result_urls || []).map((u) => el("div", { class: "stack" },
        isVideo(u) ? el("video", { controls: true, preload: "metadata", src: u, class: "result" }) : el("img", { src: u, alt: "", class: "result", referrerpolicy: "no-referrer" }),
        el("a", { class: "mono faint", href: u, target: "_blank", rel: "noopener noreferrer" }, u))),
      el("div", { class: "hint" }, isAudio ? "Played back from the gateway's own copy. Playing it is written to the audit log." : "Result links come from the service; they can expire."))) : null;
    app.replaceChildren(frame(`Record #${r.id}`, el("span", null, el("a", { href: "#/activity" }, "Activity"), r.person_id ? [" · ", el("a", { href: "#/people/" + r.person_id }, r.person)] : null), [
      meta, el("div", { class: "spacer" }), summary, el("div", { class: "spacer" }),
      mediaPanel, mediaPanel ? el("div", { class: "spacer" }) : null,
      !r.stored ? panel("Full record", null, empty("The request body was not stored (storage was switched off, or retention has removed it). The summary above is all that is left.")) : null,
      r.request !== null && r.request !== undefined ? panel("What was sent", "the whole request, as the tool sent it", renderRequest(r.kind, r.request)) : null,
      el("div", { class: "spacer" }),
      r.response !== null && r.response !== undefined ? panel("What came back", null, renderResponse(r.kind, r.response)) : null,
      el("p", { class: "hint" }, "Opening a full record is written to the audit log."),
    ], download));
  }

  function renderRequest(kind, req) {
    if (typeof req !== "object" || req === null) return el("div", { class: "body" }, code(req));
    const listKey = Array.isArray(req.messages) ? "messages" : Array.isArray(req.input) ? "input" : null;
    const setup = {};
    for (const [k, v] of Object.entries(req)) if (k !== listKey) setup[k] = v;
    const sys = setup.system ?? setup.instructions;
    const tools = Array.isArray(setup.tools) ? setup.tools : null;
    const rest = Object.fromEntries(Object.entries(setup).filter(([k]) => !["system", "instructions", "tools"].includes(k)));
    const parts = [];
    parts.push(el("div", { class: "msg" }, el("details", null,
      el("summary", null, "Setup sent by the tool", el("span", { class: "faint" }, ` — ${sys ? "system prompt, " : ""}${tools ? tools.length + " tool definitions, " : ""}settings`)),
      sys ? [el("div", { class: "tag" }, "System prompt"), longText(typeof sys === "string" ? sys : sys.map((b) => b.text || JSON.stringify(b)).join("\n\n"), 4000)] : null,
      tools ? [el("div", { class: "tag" }, "Tools offered"), el("p", { class: "mono muted" }, tools.map((t) => t.name || t.type).join(", "))] : null,
      el("div", { class: "tag" }, "Settings"), code(rest))));
    if (typeof req.input === "string") parts.push(el("div", { class: "msg user" }, el("div", { class: "role" }, "user"), longText(req.input)));
    const items = listKey ? req[listKey] : [];
    const shown = items.length > 120 ? items.slice(-120) : items;
    if (items.length > shown.length) parts.push(el("div", { class: "msg hint" }, `${items.length - shown.length} earlier messages are not shown here; download the JSON for everything.`));
    shown.forEach((m) => parts.push(messageNode(m)));
    return el("div", null, parts);
  }

  function renderResponse(kind, resp) {
    if (typeof resp !== "object" || resp === null) return el("div", { class: "body" }, code(resp));
    const parts = [];
    if (Array.isArray(resp.content)) parts.push(messageNode({ role: "assistant", content: resp.content }));
    else if (Array.isArray(resp.choices)) resp.choices.forEach((c) => parts.push(messageNode(c.message || c.delta || {})));
    else if (Array.isArray(resp.output)) resp.output.forEach((item) => parts.push(messageNode(item)));
    if (resp.error) parts.push(el("div", { class: "msg" }, el("div", { class: "role" }, "error"), code(resp.error)));
    const extra = Object.fromEntries(Object.entries(resp).filter(([k]) => !["content", "choices", "output"].includes(k)));
    parts.push(el("div", { class: "msg" }, el("details", null, el("summary", null, "Response details (usage, ids, stop reason)"), code(extra))));
    return el("div", null, parts);
  }

  function messageNode(m) {
    if (!m || typeof m !== "object") return el("div", { class: "msg" }, code(m));
    const type = m.type || "message";
    const role = m.role || (type === "message" ? "message" : type.replace(/_/g, " "));
    const cls = "msg " + (m.role === "user" ? "user" : m.role === "assistant" ? "assistant" : "");
    const body = [];
    if (type === "message" || m.role) {
      if (typeof m.content === "string") body.push(longText(m.content));
      else if (Array.isArray(m.content)) m.content.forEach((b) => body.push(blockNode(b)));
      if (Array.isArray(m.tool_calls)) m.tool_calls.forEach((c) => body.push(toolCall((c.function || {}).name, (c.function || {}).arguments)));
      if (m.role === "tool") body.length || body.push(code(m));
    }
    if (type === "function_call") body.push(toolCall(m.name, m.arguments));
    else if (type === "custom_tool_call") body.push(toolCall(m.name, m.input));
    else if (type === "local_shell_call") body.push(toolCall("shell", m.action));
    else if (type.endsWith("_output")) body.push(el("div", { class: "block" }, el("div", { class: "tag" }, "Tool result"), code(typeof m.output === "string" ? m.output : m.output ?? m, 4000)));
    else if (type === "reasoning") body.push(el("div", { class: "hint" }, (m.summary || []).map((s) => s.text).join("\n") || "Reasoning (kept private by the provider)"));
    else if (type === "additional_tools") body.push(el("div", { class: "hint" }, "Tool definitions"));
    else if (!m.role && type !== "message") body.push(code(m));
    return el("div", { class: cls }, el("div", { class: "role" }, role), body);
  }

  function toolCall(name, input) {
    let parsed = input;
    if (typeof input === "string" && input.trim().startsWith("{")) {
      try { parsed = JSON.parse(input); } catch (e) { /* leave as text */ }
    }
    return el("div", { class: "block" }, el("div", { class: "tag" }, "Tool call · " + (name || "?")), code(parsed, 4000));
  }

  function blockNode(b) {
    if (typeof b === "string") return longText(b);
    if (!b || typeof b !== "object") return code(b);
    switch (b.type) {
      case "text": case "input_text": case "output_text":
        return el("div", { class: "block" }, longText(b.text || ""));
      case "tool_use": case "server_tool_use": case "mcp_tool_use":
        return toolCall(b.name, b.input);
      case "tool_result": case "web_search_tool_result": case "mcp_tool_result": {
        const c = b.content;
        const text = typeof c === "string" ? c : Array.isArray(c) ? c.map((x) => (x && x.text) || JSON.stringify(x)).join("\n") : JSON.stringify(c, null, 2);
        return el("div", { class: "block" }, el("div", { class: "tag" }, "Tool result" + (b.is_error ? " · error" : "")), code(text || "", 4000));
      }
      case "thinking": case "redacted_thinking":
        return el("div", { class: "block hint" }, b.thinking ? longText(b.thinking, 1200) : "Thinking (not shown by the provider)");
      case "image": case "input_image": case "image_url":
        return el("div", { class: "block" }, el("span", { class: "pill info" }, "image"), " ", el("span", { class: "faint" }, (b.source && b.source.media_type) || ""));
      case "document": case "input_file": case "file":
        return el("div", { class: "block" }, el("span", { class: "pill info" }, "document"), " ", el("span", { class: "faint" }, (b.title || (b.source && b.source.media_type) || "")));
      default:
        return el("div", { class: "block" }, code(b, 3000));
    }
  }

  // ------------------------------------------------------------------ Activity (search)

  async function pageActivity(params) {
    await toolIndex().catch(() => null);
    const exportLink = el("a", { class: "btn", href: gadmin("/export.csv") }, "Export CSV");
    app.replaceChildren(frame("Staff activity", null, pageTabs("#/activity", params, [
      ["ai", "AI requests", () => aiRequestsTab(params, exportLink)],
      ["opens", "Tools opened", () => toolOpensTab()],
      ["sites", "Websites visited", () => siteVisitsTab()],
    ]), exportLink));
  }

  /* Everything that went through the gateway: typed prompts, the commands an agent ran, replies. */
  async function aiRequestsTab(params, exportLink) {
    const peopleData = await api("GET", "/people");
    const state = {
      q: params.get("q") || "", person: params.get("person") || "", client: params.get("client") || "",
      outcome: params.get("outcome") || "", only: params.get("only") || "", flag: params.get("flag") || "", all: params.get("all") || "",
    };
    const q = el("input", { type: "search", placeholder: "Search prompts, commands, replies…", value: state.q });
    const person = el("select", null, el("option", { value: "" }, "Everyone"), peopleData.items.map((p) => el("option", { value: String(p.id) }, p.name)));
    person.value = state.person;
    const tool = el("select", null, ["", "Claude Code", "Codex", "Swangz AI Studio", "Cursor", "OpenAI SDK", "Anthropic SDK", "curl", "unknown"].map((c) => el("option", { value: c }, c || "Any tool")));
    tool.value = state.client;
    const outcome = el("select", null, [["", "Any outcome"], ["ok", "Went through"], ["blocked", "Blocked"], ["denied", "Wrong key"], ["cut", "Cut off"], ["aborted", "Closed by the tool"], ["error", "Errors"]].map(([v, t]) => el("option", { value: v }, t)));
    outcome.value = state.outcome;
    const show = el("select", null, [["", "All requests"], ["media", "Voice, image & video"], ["prompts", "Only typed prompts"], ["secret", "Credentials flagged"], ["all", "Include token counts & other calls"]].map(([v, t]) => el("option", { value: v }, t)));
    show.value = params.get("kind") === "media" ? "media" : state.only === "prompts" ? "prompts" : state.flag === "secret" ? "secret" : state.all ? "all" : "";
    const list = el("ul", { class: "feed" });
    const more = el("button", { class: "btn", onclick: () => load(false) }, "Load older");
    let minId = null;

    function query() {
      const p = new URLSearchParams();
      if (q.value.trim()) p.set("q", q.value.trim());
      if (person.value) p.set("person", person.value);
      if (tool.value) p.set("client", tool.value);
      if (outcome.value) p.set("outcome", outcome.value);
      if (show.value === "prompts") p.set("only", "prompts");
      if (show.value === "media") p.set("kind", "media");
      if (show.value === "secret") p.set("flag", "secret");
      if (show.value === "all") p.set("all", "1");
      return p;
    }

    async function load(reset) {
      const p = query();
      if (!reset && minId) p.set("before", minId);
      p.set("limit", "60");
      const data = await api("GET", "/requests?" + p.toString());
      if (reset) list.replaceChildren();
      if (reset && !data.items.length) list.append(el("li", null, empty("Nothing matches.")));
      data.items.forEach((r) => list.append(feedItem(r)));
      if (data.items.length) minId = Math.min(...data.items.map((r) => r.id));
      more.hidden = !data.more;
      if (exportLink) exportLink.href = gadmin("/export.csv" + (person.value ? "?person=" + person.value : ""));
    }

    let timer = null;
    const apply = () => {
      minId = null;
      const keep = query();
      keep.set("tab", "ai");
      history.replaceState(null, "", "#/activity?" + keep.toString());
      load(true).catch((e) => toast(e.message, true));
    };
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(apply, 300); });
    [person, tool, outcome, show].forEach((sel) => sel.addEventListener("change", apply));

    const node = panel("Through the gateway", "every API call: who, which tool, the typed prompt, what the agent did, the reply, tokens and cost",
      el("div", { class: "filters" },
        el("label", { class: "field" }, "Search", q),
        el("label", { class: "field" }, "Person", person),
        el("label", { class: "field" }, "Tool", tool),
        el("label", { class: "field" }, "Outcome", outcome),
        el("label", { class: "field" }, "Show", show),
        el("div", null)),
      list, el("div", { class: "body" }, more));
    await load(true);
    return node;
  }

  /* Tools opened from the portal — the Open button on a staff tile. */
  async function toolOpensTab() {
    const peopleData = await api("GET", "/people");
    const person = el("select", null, el("option", { value: "" }, "Everyone"), peopleData.items.map((p) => el("option", { value: String(p.id) }, p.name)));
    const days = el("select", null, [["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"]].map(([v, t]) => el("option", { value: v }, t)));
    days.value = "30";
    const listBox = el("div");
    async function load() {
      const since = Date.now() / 1000 - Number(days.value) * 86400;
      const p = new URLSearchParams({ since: String(since) });
      if (person.value) p.set("person", person.value);
      const data = await api("GET", "/launches?" + p.toString());
      const refused = data.items.filter((o) => o.outcome === "refused").length;
      listBox.replaceChildren(data.items.length
        ? el("div", null, refused ? el("div", { class: "body hint" }, `${refused} refused — the person wasn't entitled at that moment.`) : null,
          opensList(data.items))
        : empty("No tools opened from the portal in this period."));
    }
    [person, days].forEach((sel) => sel.addEventListener("change", () => load().catch((e) => toast(e.message, true))));
    await load();
    return panel("Opened from the portal", "who clicked Open on which tool, and when",
      el("div", { class: "filters filters-3" }, el("label", { class: "field" }, "Person", person), el("label", { class: "field" }, "Period", days), el("div", null)),
      listBox);
  }

  /* AI websites staff opened, as recorded by the company browser extension. */
  async function siteVisitsTab() {
    const usage = await api("GET", "/site-usage");
    const summary = usage.by_tool.length ? el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Tool"), el("th", { class: "num" }, "Opens"), el("th", { class: "num" }, "Blocked"), el("th", { class: "num" }, "Time"))),
      el("tbody", null, usage.by_tool.map((t) => el("tr", null,
        el("td", null, el("div", { class: "tool-cell" }, toolLogo(null, t.tool, "sm"), t.tool || "—")),
        el("td", { class: "num" }, String(t.opens)),
        el("td", { class: "num" }, t.blocked ? el("span", { class: "pill bad" }, String(t.blocked)) : el("span", { class: "faint" }, "—")),
        el("td", { class: "num" }, fmt.dur(t.seconds))))))) : empty("Nothing yet — staff need the browser extension installed.");
    const rows = usage.items.slice(0, 200).map((v) => el("tr", null,
      el("td", { class: "nowrap muted", title: fmt.stamp(v.started) }, fmt.when(v.started)),
      el("td", null, v.person || "—"),
      el("td", null, el("div", { class: "tool-cell" }, toolLogo(null, v.tool || v.host, "sm"), v.tool || v.host)),
      el("td", { class: "num" }, v.seconds ? fmt.dur(v.seconds) : "—"),
      el("td", null, v.outcome === "blocked" ? el("span", { class: "pill bad" }, "blocked") : el("span", { class: "pill ok" }, "allowed"))));
    return [
      panel("By tool", "last 30 days", summary),
      panel("Every visit", "which approved site, who, when, for how long — never page content or anything typed",
        rows.length ? el("div", { class: "table-wrap" }, el("table", null,
          el("thead", null, el("tr", null, el("th", null, "When"), el("th", null, "Person"), el("th", null, "Tool"), el("th", { class: "num" }, "Time"), el("th", null, ""))),
          el("tbody", null, rows))) : empty("No visits recorded yet.")),
    ];
  }

  // ------------------------------------------------------------------ Tools (catalog & subscriptions)

  const SUB_LABEL = { none: "Not subscribed", active: "Active", past_due: "Past due", cancelled: "Cancelled" };
  const SUB_PILL = { active: "ok", past_due: "warn", cancelled: "bad", none: "" };

  function subPill(t) {
    const sub = t.subscription;
    if ((t.kind === "dev" || t.kind === "api") && sub.state === "none") return el("span", { class: "pill info" }, "On our API key");
    return el("span", { class: "pill " + (SUB_PILL[sub.state] || "") }, SUB_LABEL[sub.state] || sub.state);
  }

  async function pageTools(params) {
    const data = await api("GET", "/catalog");
    S.tools = Object.fromEntries([...data.tools, ...data.removed].map((t) => [t.id, t]));
    S.workspaceManaged = !!data.workspace_managed;
    const state = { q: "", cat: "all", show: "all" };
    const opens = data.tools.reduce((n, t) => n + t.usage_30d.opens, 0);
    const users = data.tools.filter((t) => t.usage_30d.opens).length;
    const kpis = el("div", { class: "kpis" },
      kpiCell("Tools in the catalog", String(data.summary.total), data.removed.length ? `${data.removed.length} removed` : "across " + data.categories.length + " categories", ICON.tools),
      kpiCell("Paid subscriptions", String(data.summary.paid), "company plans that are active", ICON.licences),
      kpiCell("Subscriptions a month", fmt.money(data.summary.monthly_cost), "", ICON.wallet, "gold"),
      kpiCell("Opens in 30 days", String(opens), `${users} tool${users === 1 ? "" : "s"} in use`, ICON.open));
    const q = el("input", { type: "search", placeholder: "Search by name or category…", oninput: (e) => { state.q = e.target.value; draw(); } });
    const cat = el("select", null, el("option", { value: "all" }, "All categories"), data.categories.map((c) => el("option", { value: c }, c)));
    cat.addEventListener("change", () => { state.cat = cat.value; draw(); });
    const show = el("select", null, [["all", "All tools"], ["active", "Subscribed"], ["none", "Not subscribed"], ["assigned", "Given to someone"], ["unused", "Given, but not opened in 30 days"]]
      .map(([v, t]) => el("option", { value: v }, t)));
    show.addEventListener("change", () => { state.show = show.value; draw(); });
    const grid = el("div", { class: "toolsadmin" });
    function draw() {
      const qq = state.q.trim().toLowerCase();
      let list = data.tools.filter((t) => (state.cat === "all" || t.category === state.cat));
      const held = (t) => t.assigned_people + t.assigned_teams > 0;
      if (state.show === "active") list = list.filter((t) => t.subscription.state === "active");
      if (state.show === "none") list = list.filter((t) => t.subscription.state === "none");
      if (state.show === "assigned") list = list.filter(held);
      if (state.show === "unused") list = list.filter((t) => held(t) && !t.usage_30d.opens);
      if (qq) list = list.filter((t) => t.name.toLowerCase().includes(qq) || t.category.toLowerCase().includes(qq));
      list.sort((a, b) => (held(b) - held(a)) || ((b.subscription.state === "active") - (a.subscription.state === "active")) || a.name.localeCompare(b.name));
      grid.replaceChildren(...(list.length ? list.map(toolAdminCard) : [empty("No tools match.")]));
    }
    draw();
    const removed = data.removed.length ? panel("Removed from the catalog", "staff can't see or open these", el("div", { class: "removed" }, data.removed.map((t) =>
      el("div", null, logo(t, "sm"), el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.builtin ? "built-in" : "added by an admin")),
        isOwner() ? el("button", { class: "btn small", onclick: () => toolAction(t, "restore") }, "Restore") : null,
        isOwner() && !t.builtin ? el("button", { class: "btn small danger", onclick: () => deleteTool(t) }, "Delete") : null)))) : null;
    const add = isOwner() ? el("button", { class: "btn primary", onclick: () => toolSheet(null) }, svg(ICON.plus), "Add a tool") : null;
    app.replaceChildren(frame("Tools", null, [
      kpis,
      panel("The tool catalog", "what Swangz pays for, how people sign in, and who uses it — click a tool to manage it",
        el("div", { class: "filters filters-3" },
          el("label", { class: "field" }, "Search", q),
          el("label", { class: "field" }, "Category", cat),
          el("label", { class: "field" }, "Show", show)),
        grid),
      removed ? el("div", { class: "spacer" }) : null, removed,
    ], add));
    const open = params && params.get("open");
    if (open && S.tools[open]) toolSheet(S.tools[open], params.get("tab") || "overview");
  }

  function toolAdminCard(t) {
    const sub = t.subscription;
    const how = SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat;
    const money = sub.state !== "none" ? [sub.plan, sub.monthly_cost != null ? fmt.money(sub.monthly_cost) + "/mo" : null, sub.seats ? sub.seats + " seats" : null].filter(Boolean).join(" · ") : "";
    return el("button", { class: "tooladmin", type: "button", onclick: () => toolSheet(t) },
      el("div", { class: "ta-head" }, logo(t), el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.category))),
      el("div", { class: "ta-body" },
        el("div", { class: "row" }, subPill(t), el("span", { class: "pill" }, how[0])),
        money ? el("div", { class: "hint" }, money) : null),
      el("div", { class: "ta-foot" },
        el("span", null, t.assigned_people + t.assigned_teams === 0 ? "No one assigned"
          : [el("b", null, String(t.assigned_people)), t.assigned_people === 1 ? " person" : " people", t.assigned_teams ? [" · ", el("b", null, String(t.assigned_teams)), " team(s)"] : null]),
        el("span", null, el("b", null, String(t.usage_30d.opens)), " opens · 30d")));
  }

  async function toolAction(t, action) {
    if (action === "archive") {
      const ok = await confirmAction(`Remove ${t.name} from the catalog?`, "Staff stop seeing it straight away and can't open it from the portal. Its history stays, and you can restore it from the bottom of the Tools page.", "Remove", true);
      if (!ok) return false;
    }
    try { await api("POST", `/tools/${t.id}/${action}`); toast(action === "archive" ? "Removed from the catalog." : "Restored."); S.tools = null; await render(); return true; }
    catch (e) { toast(e.message, true); return false; }
  }

  async function deleteTool(t) {
    const ok = await confirmAction(`Delete ${t.name} for good?`, "It's removed from the catalog along with its subscription and every grant. Past launches stay in the log without a tool name. This can't be undone.", "Delete tool", true);
    if (!ok) return;
    try { await api("DELETE", `/tools/${t.id}`); toast("Deleted."); S.tools = null; render(); } catch (e) { toast(e.message, true); }
  }

  function toolSheet(t, tab) {
    // closing forgets ?open= so a later refresh of the page doesn't pop the sheet back up
    const { node, close } = sheet(() => { if (location.hash.includes("open=")) history.replaceState(null, "", "#/tools"); });
    const owner = isOwner();
    const tabs = t ? [["overview", "Overview"], ["access", "Who can use it"], t.kind === "dev" ? null : ["billing", "Subscription"], ["settings", "Settings"]].filter(Boolean)
      : [["settings", "New tool"]];
    let current = t ? (tab || "overview") : "settings";
    const body = el("div", { class: "sheet-body" });
    const tabBar = el("div", { class: "tabs", role: "tablist" });
    function drawTabs() {
      tabBar.replaceChildren(...tabs.map(([id, label]) => el("button", { type: "button", role: "tab", class: id === current ? "on" : null,
        onclick: () => { current = id; drawTabs(); show(); } }, label)));
    }
    async function refresh(nextTab) {
      close();
      S.tools = null;
      const next = t ? `#/tools?open=${t.id}&tab=${nextTab || current}` : "#/tools";
      if (location.hash === next) await render();
      else location.hash = next;  // the hashchange renders the page and reopens this tool
    }
    function show() {
      body.replaceChildren(el("div", { class: "hint" }, "Loading…"));
      ({ overview: overviewTab, access: accessTab, billing: billingTab, settings: settingsTab })[current]().then((n) => body.replaceChildren(...[].concat(n).filter(Boolean)))
        .catch((e) => body.replaceChildren(el("div", { class: "err" }, e.message)));
    }

    async function overviewTab() {
      const how = SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat;
      const sub = t.subscription;
      return [
        t.description ? el("p", { class: "muted", style: null }, t.description) : null,
        el("div", { class: "facts" },
          fact("Type", KIND[t.kind] || t.kind),
          fact("Subscription", sub.state === "none" ? (t.kind === "site" ? "None yet" : "Metered on our API key") : [SUB_LABEL[sub.state], sub.plan].filter(Boolean).join(" · ")),
          fact("Monthly cost", sub.monthly_cost != null ? fmt.money(sub.monthly_cost) : "—"),
          fact("Seats", sub.seats ? `${t.assigned_people} given · ${sub.seats} paid` : `${t.assigned_people} given`),
          fact("Opened in 30 days", `${t.usage_30d.opens} times by ${t.usage_30d.people} ${t.usage_30d.people === 1 ? "person" : "people"}`),
          t.signin === "shared" ? fact("Opens into", browserList(t).length
            ? `the shared workspace — ${browserList(t).length} browser${browserList(t).length === 1 ? "" : "s"}, already signed in`
            : "the tool's own site (they sign in)") : null,
          fact("Last opened", t.usage_30d.last ? fmt.ago(t.usage_30d.last) : "not in 30 days")),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "How people sign in — " + how[0]), el("p", { class: "hint", style: null }, how[1]),
          t.launch_url ? el("div", { class: "hint" }, "Opens: ", el("span", { class: "mono" }, t.launch_url)) : null,
          t.url ? el("a", { class: "btn small", href: t.url, target: "_blank", rel: "noopener noreferrer" }, "Visit website", svg(ICON.open)) : null),
        t.hosts.length ? el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Domains the browser extension governs"),
          el("div", { class: "row" }, t.hosts.map((h) => el("span", { class: "pill mono" }, h)))) : null,
      ];
    }

    async function accessTab() {
      const data = await api("GET", `/tools/${t.id}/access`);
      const teams = data.teams.length ? el("div", { class: "row" }, data.teams.map((team) => {
        const btn = el("button", { class: "btn small" + (team.on ? " primary" : ""), disabled: !owner, onclick: async () => {
          const adding = !btn.classList.contains("primary");
          try { await api(adding ? "POST" : "DELETE", `/teams/${encodeURIComponent(team.name)}/tools/${t.id}`); btn.classList.toggle("primary", adding); btn.textContent = adding ? "On" : "Off"; toast("Saved."); }
          catch (e) { toast(e.message, true); }
        } }, team.on ? "On" : "Off");
        return el("div", { class: "team-toggle" }, el("span", null, team.name), btn);
      })) : el("div", { class: "hint" }, "Give people a department to grant whole teams at once.");
      const rows = data.people.map((p) => {
        const until = el("input", { type: "date", value: p.expires ? isoDate(p.expires - 86400) : "", disabled: !owner, title: "Optional end date", "aria-label": "Access ends on" });
        const btn = el("button", { class: "btn small" + (p.granted ? " primary" : ""), disabled: !owner }, p.granted ? "On" : "Off");
        btn.addEventListener("click", async () => {
          const adding = !btn.classList.contains("primary");
          try {
            if (adding) await api("POST", `/people/${p.id}/tools/${t.id}`, until.value ? { until: until.value } : {});
            else await api("DELETE", `/people/${p.id}/tools/${t.id}`);
            btn.classList.toggle("primary", adding); btn.textContent = adding ? "On" : "Off"; toast(adding ? "Turned on." : "Turned off.");
          } catch (e) { toast(e.message, true); }
        });
        until.addEventListener("change", async () => {
          if (!btn.classList.contains("primary")) return;
          try { await api("POST", `/people/${p.id}/tools/${t.id}`, { until: until.value || null }); toast(until.value ? "End date set." : "End date cleared."); }
          catch (e) { toast(e.message, true); }
        });
        return el("div", { class: "assign-row" },
          el("span", { class: "logo sm mono" }, initials(p.name)),
          el("div", { class: "grow" }, el("strong", null, p.name), " ", p.status !== "active" ? el("span", { class: "pill bad" }, "suspended") : null,
            p.team ? el("span", { class: "pill info" }, "via team") : null,
            el("div", { class: "hint" }, [p.department || "No department", p.last_opened ? "opened " + fmt.ago(p.last_opened) : "never opened"].join(" · "))),
          until, btn);
      });
      rows.forEach((r) => { const m = r.querySelector(".logo"); m.style.background = "linear-gradient(140deg, #2B2B31, #141417)"; m.style.color = "#F0C054"; });
      const locked = t.kind === "site" && t.subscription.state !== "active";
      let onItNow = null;
      if (t.signin === "shared") {
        const all = await api("GET", "/turns");
        const here = all.now.filter((x) => x.tool_id === t.id);
        const pool = browserList(t);
        const where = (x) => x.workspace ? (pool.includes(x.workspace) ? ` · browser ${pool.indexOf(x.workspace) + 1}` : " · a browser no longer listed") : "";
        onItNow = el("div", { class: "stack" }, el("h3", { class: "section-title" }, "On the shared account right now"),
          here.length ? el("div", { class: "assign-list" }, here.map((x) => el("div", { class: "assign-row" },
            el("span", { class: "logo sm mono" }, initials(x.person)),
            el("div", { class: "grow" }, el("strong", null, x.person),
              el("div", { class: "hint" }, "until " + new Date(x.expires * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + where(x))),
            owner ? el("button", { class: "btn small danger", onclick: async () => {
              try { await api("POST", `/tools/${t.id}/turn/end`, { person_id: x.person_id }); toast("Taken back."); refresh("access"); }
              catch (e) { toast(e.message, true); }
            } }, "Take it back") : null)))
            : el("div", { class: "hint" }, `Nobody is on it. ${pool.length ? Math.min(t.seats_at_once, pool.length) : t.seats_at_once} at a time, ${t.turn_minutes} minutes a turn.`));
        here.forEach(() => {});
        onItNow.querySelectorAll(".logo").forEach((m) => { m.style.background = "linear-gradient(140deg, #2B2B31, #141417)"; m.style.color = "#F0C054"; });
      }
      return [
        locked ? el("div", { class: "notice" }, "Staff can't open this until the company subscription is active (Subscription tab).") : null,
        onItNow,
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Whole teams"), teams),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "People"),
          el("p", { class: "hint", style: null }, "Turn the tool on per person. Add an end date first to give it for a limited time — access stops after that day."),
          rows.length ? el("div", { class: "assign-list" }, rows) : empty("No people yet.")),
      ];
    }

    async function billingTab() {
      const sub = t.subscription;
      const f = {
        state: el("select", { disabled: !owner }, Object.entries(SUB_LABEL).map(([v, l]) => el("option", { value: v }, l))),
        plan: el("input", { type: "text", value: sub.plan || "", placeholder: (t.plans[0] && t.plans[0].name) || "Plan name", disabled: !owner }),
        monthly_cost: el("input", { type: "number", min: "0", step: "0.01", value: sub.monthly_cost ?? "", placeholder: t.entry_usd ? String(t.entry_usd) : "0", disabled: !owner }),
        seats: el("input", { type: "number", min: "0", step: "1", value: sub.seats ?? "", disabled: !owner }),
        renews_on: el("input", { type: "date", value: sub.renews_on ? isoDate(sub.renews_on) : "", disabled: !owner }),
        note: el("input", { type: "text", value: sub.note || "", placeholder: "Card on file, invoice owner, account email…", disabled: !owner }),
      };
      f.state.value = sub.state || "none";
      const err = el("div", { class: "err" });
      const save = owner ? el("button", { class: "btn primary", onclick: async () => {
        try {
          await api("PUT", "/subscriptions/" + t.id, { state: f.state.value, plan: f.plan.value, monthly_cost: f.monthly_cost.value, seats: f.seats.value, renews_on: f.renews_on.value, note: f.note.value });
          toast("Subscription saved."); refresh("billing");
        } catch (e) { err.textContent = e.message; }
      } }, "Save subscription") : null;
      return [
        el("p", { class: "hint", style: null }, "One company account pays for the tool; each person gets their seat through the portal. Staff can only open website tools while this is Active."),
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "Status", f.state),
          el("label", { class: "field" }, "Plan", f.plan),
          el("label", { class: "field" }, "Monthly cost (USD)", f.monthly_cost),
          el("label", { class: "field" }, "Seats paid for", f.seats),
          el("label", { class: "field" }, "Renews on", f.renews_on)),
        el("label", { class: "field" }, "Note", f.note),
        t.plans.length ? el("div", { class: "hint" }, "Published plans: " + t.plans.map((p) => `${p.name}${p.monthlyUSD ? " $" + p.monthlyUSD : ""}`).join(" · "),
          t.pricing_url ? [" · ", el("a", { href: t.pricing_url, target: "_blank", rel: "noopener noreferrer" }, "pricing page")] : null) : null,
        err, el("div", null, save),
      ];
    }

    async function settingsTab() {
      const v = t || { name: "", category: "", kind: "site", description: "", url: "", signin: "seat", launch_url: "", hosts: [], color: "#3F3F46", pricing_url: "" };
      const cats = Object.values(S.tools || {}).map((x) => x.category);
      const list = el("datalist", { id: "cat-list" }, Array.from(new Set(cats)).sort().map((c) => el("option", { value: c })));
      const f = {
        name: el("input", { type: "text", value: v.name, maxlength: "80", required: true }),
        category: el("input", { type: "text", value: v.category, list: "cat-list", placeholder: "e.g. Image" }),
        kind: el("select", { disabled: t && t.builtin ? true : null }, Object.entries(KIND).map(([k, l]) => el("option", { value: k }, l))),
        description: el("input", { type: "text", value: v.description || "", maxlength: "200", placeholder: "One line staff will read on the tile" }),
        url: el("input", { type: "url", value: v.url || "", placeholder: "https://…" }),
        signin: el("select", null, Object.entries(SIGNIN).map(([k, [l]]) => el("option", { value: k }, l))),
        launch_url: el("input", { type: "url", value: v.launch_url || "", placeholder: "https://… (optional)" }),
        hosts: el("input", { type: "text", value: (v.hosts || []).join(", "), placeholder: "Filled from the website if left empty" }),
        color: el("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(v.color || "") ? v.color : "#3F3F46" }),
        pricing_url: el("input", { type: "url", value: v.pricing_url || "", placeholder: "https://…/pricing" }),
        seats_at_once: el("input", { type: "number", min: "1", max: "50", step: "1", value: String(v.seats_at_once || 1) }),
        turn_minutes: el("input", { type: "number", min: "5", max: "720", step: "5", value: String(v.turn_minutes || 120) }),
        workspace_url: el("textarea", { rows: "3", spellcheck: "false", placeholder: "https://workspace.swangzavenue.com/chatgpt-1/\nhttps://workspace.swangzavenue.com/chatgpt-2/" }, v.workspace_url || ""),
      };
      const sharing = el("div", { class: "share-box" },
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "People on it at a time", f.seats_at_once,
            el("span", { class: "hint" }, "Usually 1 — one account, one person. With a workspace, never more than its browsers.")),
          el("label", { class: "field" }, "How long a turn lasts (minutes)", f.turn_minutes,
            el("span", { class: "hint" }, "It ends by itself after this, or when they hand it back."))),
        el("div", { class: "hint" }, "While someone holds the turn, nobody else can open this tool, and the extension signs their browser out when it ends — so the vendor's credit history can be matched to a person."),
        el("label", { class: "field" }, "Shared workspace browsers", f.workspace_url,
          el("span", { class: "hint" }, "Optional. One address per line — each is a browser on Swangz's own server that an admin has signed in to this tool once. Everyone holding a turn gets a browser to themselves, so as many people can work at once as there are browsers. They arrive signed in and never see the password. Leave empty and Open goes to the tool's own site, where they sign in themselves. See deploy/WORKSPACE.md."),
          el("span", { class: "hint" }, S.workspaceManaged
            ? "The gateway gives each person a sign-in for their turn and removes it the moment the turn ends."
            : "The gateway isn't managing workspace sign-ins yet (GATEWAY_WORKSPACE_TOKEN is not set), so each browser's own login decides who gets in.")));
      f.kind.value = v.kind; f.signin.value = v.kind === "dev" ? "api" : (v.signin || "seat");
      const howHint = el("span", { class: "hint" });
      const drawHow = () => {
        howHint.textContent = (SIGNIN[f.signin.value] || SIGNIN.seat)[1];
        sharing.hidden = f.signin.value !== "shared";
      };
      f.signin.addEventListener("change", drawHow); drawHow();
      const err = el("div", { class: "err" });
      const values = () => ({ name: f.name.value, category: f.category.value, kind: f.kind.value, description: f.description.value, url: f.url.value,
        signin: f.signin.value, launch_url: f.launch_url.value, hosts: f.hosts.value, color: f.color.value, pricing_url: f.pricing_url.value,
        seats_at_once: f.seats_at_once.value, turn_minutes: f.turn_minutes.value, workspace_url: f.workspace_url.value });
      const save = el("button", { class: "btn primary", onclick: async () => {
        err.textContent = "";
        try {
          if (t) { await api("PATCH", "/tools/" + t.id, values()); toast("Saved."); refresh("settings"); }
          else {
            const out = await api("POST", "/tools", values());
            toast("Added — now choose who can use it."); close(); S.tools = null;
            location.hash = `#/tools?open=${out.id}&tab=access`;
          }
        } catch (e) { err.textContent = e.message; }
      } }, t ? "Save changes" : "Add tool");
      if (!owner) Object.values(f).forEach((x) => { x.disabled = true; });

      let logoBox = null;
      if (t) {
        const file = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon,image/gif", hidden: true });
        file.addEventListener("change", () => {
          const pick = file.files[0];
          if (!pick) return;
          if (pick.size > 300 * 1024) { toast("Keep the logo under 300 KB.", true); return; }
          const reader = new FileReader();
          reader.onload = async () => {
            try { await api("PUT", `/tools/${t.id}/logo`, { data: reader.result }); toast("Logo uploaded."); refresh("settings"); } catch (e) { toast(e.message, true); }
          };
          reader.readAsDataURL(pick);
        });
        logoBox = el("div", { class: "logo-edit" }, logo(t, "lg"), el("div", { class: "stack" },
          el("div", { class: "row" },
            owner ? el("button", { class: "btn small", onclick: () => file.click() }, "Upload a logo") : null,
            owner ? el("button", { class: "btn small", onclick: async (e) => {
              e.target.disabled = true; e.target.textContent = "Fetching…";
              try { const out = await api("POST", `/tools/${t.id}/logo/refresh`); toast(out.ok ? "Logo updated from the website." : "Couldn't find a logo on the website — upload one instead.", !out.ok); if (out.ok) refresh("settings"); }
              catch (x) { toast(x.message, true); }
              e.target.disabled = false; e.target.textContent = "Fetch from website";
            } }, "Fetch from website") : null, file),
          el("span", { class: "hint" }, "PNG, SVG, WebP or JPEG, under 300 KB. Without a logo, the tile shows initials in the brand colour.")));
      }
      return [
        list, logoBox,
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "Name", f.name),
          el("label", { class: "field" }, "Category", f.category),
          el("label", { class: "field" }, "Type", f.kind)),
        el("label", { class: "field" }, "Description", f.description),
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "Website", f.url),
          el("label", { class: "field" }, "How people sign in", f.signin, howHint)),
        sharing,
        el("label", { class: "field" }, "Company sign-in link", f.launch_url,
          el("span", { class: "hint" }, "Where Open sends people. For single sign-on, paste the tool's SSO link — or the app's link from Google Admin → Apps → Web and mobile apps. Empty = the website.")),
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "Domains (for the browser extension)", f.hosts),
          el("label", { class: "field" }, "Pricing page", f.pricing_url),
          el("label", { class: "field" }, "Brand colour", f.color)),
        err,
        owner ? el("div", null, save) : null,
        t && owner ? el("div", { class: "danger-zone" },
          el("div", null, el("strong", null, t.builtin ? "Remove from the catalog" : "Remove or delete"),
            el("div", { class: "hint" }, t.builtin ? "Hidden from staff and closed to launches. You can restore it any time." : "Remove hides it (restorable). Delete erases it with its grants.")),
          el("div", { class: "row" },
            el("button", { class: "btn danger", onclick: async () => { if (await toolAction(t, "archive")) close(); } }, "Remove"),
            t.builtin ? null : el("button", { class: "btn danger solid", onclick: () => { close(); deleteTool(t); } }, "Delete"))) : null,
      ];
    }

    const head = el("header", null,
      el("div", { class: "spread" },
        el("div", { class: "sheet-id" }, t ? logo(t, "lg") : el("span", { class: "logo lg mono" }, "+"),
          el("div", null, el("div", { class: "eyebrow" }, t ? t.category : "Catalog"), el("h2", null, t ? t.name : "Add a tool"),
            t ? el("div", { class: "row", style: null }, subPill(t), el("span", { class: "pill" }, KIND[t.kind] || t.kind)) : null)),
        el("button", { class: "btn small quiet", onclick: close, "aria-label": "Close" }, "Close")),
      tabBar);
    if (!t) { const m = head.querySelector(".logo"); m.style.background = "linear-gradient(140deg, #2B2B31, #141417)"; m.style.color = "#F0C054"; }
    node.setAttribute("aria-label", t ? t.name : "Add a tool");
    node.append(head, body);
    drawTabs();
    show();
  }

  function fact(k, v) { return el("div", { class: "fact" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)); }

  // ------------------------------------------------------------------ Licences & spend

  async function pageLicences() {
    const [lic] = await Promise.all([api("GET", "/licences"), toolIndex().catch(() => null)]);
    const s = lic.summary;
    const owner = isOwner();
    const kpis = el("div", { class: "kpis" },
      kpiCell("Spend this month", fmt.money(s.total_month), `${fmt.money(s.subscriptions_month)} plans + ${fmt.money(s.api_month)} API use`, ICON.wallet, "gold"),
      kpiCell("Company plans", fmt.money(s.subscriptions_month), "a month, for the tools below", ICON.licences),
      kpiCell("API use this month", fmt.money(s.api_month), "metered through the gateway", ICON.live),
      kpiCell("Seats not used", String(s.idle_seats), s.idle_cost ? `≈ ${fmt.money(s.idle_cost)} a month going unused` : "everyone given a tool is using it", ICON.clock, s.idle_seats ? "alert" : null));
    const rows = lic.tools.map((t) => el("tr", null,
      el("td", null, el("a", { class: "tool-cell", href: `#/tools?open=${t.id}&tab=billing` }, toolLogo(t.id, t.name, "sm"), el("div", null, el("strong", null, t.name), el("div", { class: "hint" }, t.plan || (t.state === "none" ? (t.kind === "site" ? "no plan" : "API key") : SUB_LABEL[t.state]))))),
      el("td", { class: "num" }, String(t.assigned) + (t.seats ? " / " + t.seats : ""), t.over_seats ? el("div", null, el("span", { class: "pill bad" }, "more people than seats")) : null),
      el("td", null, t.assigned ? [el("span", null, `${t.active} of ${t.assigned}`), usageBar(t.active, t.assigned)] : el("span", { class: "hint" }, "no one given it yet")),
      el("td", { class: "num" }, t.monthly_cost != null ? fmt.money(t.monthly_cost) : "—"),
      el("td", { class: "num" }, t.cost_per_active != null ? fmt.money(t.cost_per_active) : "—"),
      el("td", null, t.idle.length ? el("div", { class: "idle" }, t.idle.map((p) => el("span", { title: p.last ? "last used " + fmt.ago(p.last) : "never used" }, p.name,
        owner ? el("button", { type: "button", onclick: async () => {
          const ok = await confirmAction(`Take ${t.name} back from ${p.name}?`, "Their access is removed so the seat can go to someone who needs it. If they have it through their team, change that on the Tools page.", "Take it back", true);
          if (!ok) return;
          try { await api("DELETE", `/people/${p.id}/tools/${t.id}`); toast("Seat freed."); render(); } catch (e) { toast(e.message, true); }
        } }, "Reclaim") : null))) : t.assigned ? el("span", { class: "pill ok" }, "all in use") : el("span", { class: "hint" }, "—"))));
    const table = lic.tools.length ? el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Tool"), el("th", { class: "num" }, "Given / seats"), el("th", null, "Used in 30 days"),
        el("th", { class: "num" }, "Cost a month"), el("th", { class: "num" }, "Per active user"), el("th", null, "Not used in 30 days"))),
      el("tbody", null, rows))) : empty("No subscriptions or assigned tools yet. Subscribe on the Tools page, then give the tool to people.");
    const renewals = lic.renewals.length ? el("ul", { class: "opens" }, lic.renewals.map((t) => el("li", null, toolLogo(t.id, t.name, "sm"),
      el("div", { class: "who-line" }, el("strong", null, t.name), el("span", { class: "muted" }, " · " + (t.monthly_cost != null ? fmt.money(t.monthly_cost) : "cost not set"))),
      el("span", { class: "pill warn" }, "renews " + dateText(t.renews_on))))) : empty("Nothing renews in the next 30 days.");
    const people = lic.people.filter((p) => p.cost > 0 || p.monthly_budget !== null);
    const spend = people.length ? el("ul", { class: "bars" }, people.map((p) => el("li", null,
      el("div", { class: "spread" }, el("a", { href: "#/people/" + p.id }, p.name), el("span", { class: "num" }, fmt.money(p.cost) + (p.monthly_budget !== null ? " of " + fmt.money(p.monthly_budget) : ""))),
      p.monthly_budget !== null ? bar(p.cost, p.monthly_budget) : bar(p.cost, Math.max(...people.map((x) => x.cost), 0.01)),
      el("div", { class: "hint" }, (p.department || "—") + (p.monthly_budget === null ? " · no monthly budget" : ""))))) : empty("No API spend this month.");
    app.replaceChildren(frame("Licences & spend", null, [
      kpis,
      panel("Licences", "seats paid for against real use — reclaim the ones nobody opens", table,
        el("div", { class: "body hint" }, "Used = opened from the portal, through the browser extension, or used through the gateway in the last 30 days.")),
      el("div", { class: "spacer" }),
      el("div", { class: "grid cols-even" },
        panel("Renewing in the next 30 days", null, renewals),
        panel("API spend by person", "this month, against their budget", spend)),
    ], el("a", { class: "btn", href: gadmin("/export.csv") }, "Export activity CSV")));
  }

  function usageBar(value, total) {
    const fill = el("i");
    fill.style.width = Math.min(100, (value / (total || 1)) * 100) + "%";
    return el("div", { class: "bar use" }, fill);
  }

  function kpiCell(label, value, note, icon, tone) {
    return el("div", { class: "kpi" + (tone ? " " + tone : "") }, el("div", { class: "label" }, icon ? svg(icon) : null, label),
      el("div", { class: "value" }, value), note ? el("div", { class: "note" }, note) : null);
  }

  // ------------------------------------------------------------------ Access requests

  async function pageRequests() {
    const state = location.hash.includes("state=") ? location.hash.split("state=")[1] : "open";
    const data = await api("GET", "/access-requests?state=" + encodeURIComponent(state));
    const tabs = el("div", { class: "row reqtabs" },
      [["open", "Open" + (data.open ? ` (${data.open})` : "")], ["granted", "Granted"], ["declined", "Declined"]].map(([v, t]) =>
        el("button", { class: "btn small" + (state === v ? " primary" : ""), onclick: () => { location.hash = "#/requests?state=" + v; } }, t)));
    const rows = data.items.map((r) => el("div", { class: "req" },
      el("div", null, el("strong", null, r.person), el("span", { class: "muted" }, " wants "), el("strong", null, r.tool),
        el("div", { class: "hint" }, (r.department || "—") + " · " + fmt.ago(r.created) + (r.reason ? " · “" + r.reason + "”" : ""))),
      r.state === "open" && isOwner() ? el("div", { class: "row" },
        el("button", { class: "btn small primary", onclick: () => decideRequest(r.id, "grant") }, "Grant"),
        el("button", { class: "btn small danger", onclick: () => decideRequest(r.id, "decline") }, "Decline"))
        : el("span", { class: "pill " + (r.state === "granted" ? "ok" : "bad") }, r.state)));
    app.replaceChildren(frame("Access requests", null, panel("Staff asking for tools", "grant one and it's turned on for them",
      el("div", { class: "body" }, tabs), rows.length ? el("div", { class: "reqlist" }, rows) : empty("Nothing here."))));
  }

  async function decideRequest(id, action) {
    try { await api("POST", `/access-requests/${id}/${action}`); toast(action === "grant" ? "Granted." : "Declined."); render(); }
    catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ Settings

  async function pageSettings(params) {
    const owner = isOwner();
    app.replaceChildren(frame("Settings", null, pageTabs("#/settings", params, [
      ["safety", "Access & records", () => safetyTab(owner)],
      ["addresses", "Addresses", () => addressesTab()],
      ["prices", "Model prices", () => pricesTab(owner)],
      owner && ["users", "Console users", () => consoleUsersTab()],
      ["account", "Your account", () => accountTab()],
    ])));
  }

  async function safetyTab(owner) {
    const st = await api("GET", "/settings");
    const switchPanel = panel("Kill switch", null, el("div", { class: "body spread" },
      el("div", null, el("strong", null, st.paused ? "AI access is paused for everyone." : "AI access is on."),
        el("div", { class: "hint" }, "Stopping cuts every request in flight, refuses new ones, and closes the portal's Open buttons until someone resumes.")),
      owner ? (st.paused ? el("button", { class: "btn primary", onclick: () => setPaused(false) }, "Resume access")
        : el("button", { class: "btn danger", onclick: () => setPaused(true) }, "Stop all AI")) : null));

    const retention = el("input", { type: "number", min: "0", step: "1", value: String(st.retention_days), disabled: !owner });
    const storeBodies = el("input", { type: "checkbox", checked: st.store_bodies, disabled: !owner });
    const blockSecrets = el("input", { type: "checkbox", checked: st.block_secrets, disabled: !owner });
    const selfKeys = el("input", { type: "checkbox", checked: st.staff_self_keys, disabled: !owner });
    const gateFull = el("input", { type: "checkbox", checked: st.gate_log_full, disabled: !owner });
    const rate = el("input", { type: "number", min: "0", step: "1", value: String(st.rate_per_min || 0), disabled: !owner });
    const recErr = el("div", { class: "err" });
    const records = panel("Records", `${st.records.toLocaleString()} requests · ${(st.db_bytes / 1048576).toFixed(1)} MB on disk`, el("div", { class: "body stack" },
      el("label", { class: "field", style: null }, "Keep records for (days)", retention, el("span", { class: "hint" }, "Older records and their bodies are deleted automatically every hour. 0 keeps everything.")),
      el("label", { class: "check" }, storeBodies, el("span", null, el("strong", null, "Keep full request and response bodies"), el("div", { class: "hint" }, "Needed to pull back exactly what was sent. Off = only the summary (who, model, prompt, commands, cost)."))),
      el("label", { class: "check" }, selfKeys, el("span", null, el("strong", null, "Staff can connect their own devices"), el("div", { class: "hint" }, "In the Swangz AI app they create and disconnect their own keys. Every key still shows up here, and you can revoke any of them."))),
      el("label", { class: "check" }, blockSecrets, el("span", null, el("strong", null, "Refuse requests that contain credentials"), el("div", { class: "hint" }, "API keys, cloud keys, private keys. Off = let them through but flag them. On can interrupt an agent that reads a .env file."))),
      el("label", { class: "check" }, gateFull, el("span", null, el("strong", null, "Website gate: full-content logging"), el("div", { class: "hint" }, "Off by default, and the honest choice. The browser extension records only which approved site staff open and for how long. Turn this on only with legal sign-off — staff are told in the extension's policy."))),
      el("label", { class: "field", style: null }, "Rate limit (requests per person per minute)", rate, el("span", { class: "hint" }, "Catches a runaway tool. 0 = no limit. A busy agent can make several a minute, so keep it generous.")),
      recErr,
      owner ? el("div", null, el("button", { class: "btn primary", onclick: async () => {
        try {
          await api("PUT", "/settings", { retention_days: retention.value, store_bodies: storeBodies.checked, block_secrets: blockSecrets.checked, staff_self_keys: selfKeys.checked, gate_log_full: gateFull.checked, rate_per_min: rate.value });
          toast("Saved.");
        } catch (e) { recErr.textContent = e.message; }
      } }, "Save")) : null));
    return [switchPanel, records];
  }

  async function addressesTab() {
    const st = await api("GET", "/settings");
    const providerRows = st.providers.map((p) => el("tr", null,
      el("td", null, el("strong", null, p.label || p.name), el("div", { class: "hint" }, { anthropic: "chat & coding models", openai: "chat & coding models", elevenlabs: "voice & sound",
        higgsfield: "image & video" }[p.dialect] || "AI service")),
      el("td", { class: "mono" }, `${st.base_url}/${p.name}` + (p.dialect === "openai" ? "/v1" : "")),
      el("td", { class: "mono muted" }, p.upstream),
      el("td", null, p.configured ? el("span", { class: "pill ok" }, "key set")
        : el("span", null, el("span", { class: "pill bad" }, "off"), el("div", { class: "hint" }, `set ${p.key_env} on the server`)))));
    return panel("Addresses and providers", "staff tools point at these", el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Provider"), el("th", null, "Address for staff tools"), el("th", null, "Forwards to"), el("th", null, "API key"))),
      el("tbody", null, providerRows))),
    el("div", { class: "body stack" },
      el("div", null, el("span", { class: "tag" }, "Staff app  "), el("span", { class: "mono" }, st.base_url + "/"), el("span", { class: "hint" }, "  — where staff sign in and open their tools")),
      el("div", null, el("span", { class: "tag" }, "Admin console  "), el("span", { class: "mono" }, st.base_url + "/admin"), el("span", { class: "hint" }, "  — this console; don't share it with staff"))),
    el("div", { class: "body hint" }, "Provider API keys live only in the server's environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, …). They are never shown here and never leave the server."));
  }

  async function pricesTab(owner) {
    const prices = await api("GET", "/prices");
    const priceRows = prices.items.map((x) => el("tr", null,
      el("td", { class: "mono" }, x.model), el("td", { class: "num" }, usd(x.input)), el("td", { class: "num" }, usd(x.output)),
      el("td", { class: "num" }, x.cache_write === null ? "—" : usd(x.cache_write)), el("td", { class: "num" }, x.cache_read === null ? "—" : usd(x.cache_read)),
      el("td", { class: "num" }, owner ? el("button", { class: "btn small", onclick: () => editPrice(x) }, "Edit") : null)));
    const unpriced = prices.unpriced_models.length ? el("div", { class: "body" }, el("div", { class: "err" }, "Used but not priced (their cost shows as “unpriced”):"),
      el("div", { class: "row", style: null }, prices.unpriced_models.map((m) => owner ? el("button", { class: "btn small", onclick: () => editPrice({ model: m }) }, "Price " + m) : el("span", { class: "pill warn" }, m)))) : null;
    return panel("Model prices", "US dollars per million tokens", unpriced, el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Model"), el("th", { class: "num" }, "Input"), el("th", { class: "num" }, "Output"), el("th", { class: "num" }, "Cache write"), el("th", { class: "num" }, "Cache read"), el("th", null, ""))),
      el("tbody", null, priceRows))),
    owner ? el("div", { class: "body" }, el("button", { class: "btn", onclick: () => editPrice({}) }, "Add a model price")) : null);
  }

  async function consoleUsersTab() {
    const admins = await api("GET", "/admins");
    return panel("Console users", "owners change things; viewers only look", el("div", { class: "table-wrap" }, el("table", null,
      el("tbody", null, admins.items.map((a) => el("tr", null,
        el("td", null, el("div", { class: "person-cell" }, el("span", { class: "avatar" }, initials(a.username)), el("strong", null, a.username))),
        el("td", null, el("span", { class: "pill" }, a.role)),
        el("td", { class: "muted" }, "last sign-in " + fmt.ago(a.last_login)),
        el("td", { class: "num" }, a.username === S.me.username ? el("span", { class: "faint" }, "you") : el("button", { class: "btn danger small", onclick: () => removeAdmin(a) }, "Remove"))))))),
    el("div", { class: "body" }, el("button", { class: "btn", onclick: addAdmin }, "Add a console user")),
    el("div", { class: "body hint" }, "A console user whose username is their Google email can also sign in with Continue with Google."));
  }

  async function accountTab() {
    const cur = el("input", { type: "password", autocomplete: "current-password" });
    const nw = el("input", { type: "password", autocomplete: "new-password" });
    const pwErr = el("div", { class: "err" });
    return panel("Your password", S.me.username, el("div", { class: "body stack" },
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Current password", cur), el("label", { class: "field" }, "New password (10+ characters)", nw)), pwErr,
      el("div", null, el("button", { class: "btn primary", onclick: async () => {
        try { await api("POST", "/password", { current: cur.value, new: nw.value }); toast("Password changed."); cur.value = nw.value = ""; pwErr.textContent = ""; } catch (e) { pwErr.textContent = e.message; }
      } }, "Change password"))));
  }

  function editPrice(x) {
    const f = {};
    const fields = [["model", "Model id (or the start of it)"], ["input", "Input"], ["output", "Output"], ["cache_write", "Cache write (5 min)"], ["cache_write_1h", "Cache write (1 hour)"], ["cache_read", "Cache read"]];
    const err = el("div", { class: "err" });
    const grid = el("div", { class: "form-grid" }, fields.map(([k, label]) => {
      f[k] = el("input", { type: k === "model" ? "text" : "number", step: "0.0001", min: "0", value: x[k] ?? "", disabled: k === "model" && !!x.input });
      return el("label", { class: "field" }, label, f[k]);
    }));
    const save = el("button", { class: "btn primary", onclick: async () => {
      const body = {};
      for (const [k] of fields) if (k !== "model") body[k] = f[k].value;
      try {
        await api("PUT", "/prices/" + encodeURIComponent(f.model.value.trim()), body);
        d.close();
        toast("Price saved. New requests use it; past ones keep the cost they had.");
        render();
      } catch (e) { err.textContent = e.message; }
    } }, "Save price");
    const remove = x.input ? el("button", { class: "btn danger", onclick: async () => {
      try { await api("DELETE", "/prices/" + encodeURIComponent(x.model)); d.close(); render(); } catch (e) { err.textContent = e.message; }
    } }, "Remove") : null;
    const d = dialog(x.model ? "Price for " + x.model : "Add a model price", el("div", { class: "stack" },
      el("p", { class: "hint" }, "US dollars per million tokens, from the provider's price page. Leave cache fields empty to use the usual multiples of the input price."), grid, err), [remove, save]);
  }

  function addAdmin() {
    const user = el("input", { type: "text", autocomplete: "off" });
    const pw = el("input", { type: "password", autocomplete: "new-password" });
    const role = el("select", null, el("option", { value: "viewer" }, "Viewer — can see everything, change nothing"), el("option", { value: "owner" }, "Owner — can change everything"));
    const err = el("div", { class: "err" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try { await api("POST", "/admins", { username: user.value, password: pw.value, role: role.value }); d.close(); toast("Added."); render(); } catch (e) { err.textContent = e.message; }
    } }, "Add");
    const d = dialog("Add a console user", el("div", { class: "stack" },
      el("label", { class: "field" }, "Username", user, el("span", { class: "hint" }, "Use their Google email (e.g. name@swangzavenue.com) and they can also sign in with Google.")),
      el("label", { class: "field" }, "Password (10+ characters)", pw), el("label", { class: "field" }, "Role", role), err), [save]);
    user.focus();
  }

  async function removeAdmin(a) {
    const ok = await confirmAction(`Remove ${a.username}?`, "They can no longer sign in to the console.", "Remove", true);
    if (!ok) return;
    try { await api("DELETE", "/admins/" + a.id); toast("Removed."); render(); } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ Audit

  async function pageAudit() {
    const body = el("tbody");
    const more = el("button", { class: "btn" }, "Load older");
    let minId = null;
    async function load() {
      const data = await api("GET", "/audit?limit=100" + (minId ? "&before=" + minId : ""));
      data.items.forEach((a) => body.append(el("tr", null,
        el("td", { class: "nowrap muted", title: fmt.stamp(a.ts) }, fmt.stamp(a.ts)),
        el("td", null, el("strong", null, a.actor)),
        el("td", null, a.action, a.target ? el("span", { class: "muted" }, " — " + a.target) : null, a.detail ? el("div", { class: "hint" }, a.detail) : null),
        el("td", { class: "mono faint" }, a.ip))));
      if (data.items.length) minId = Math.min(...data.items.map((a) => a.id));
      more.hidden = !data.more;
    }
    more.addEventListener("click", load);
    app.replaceChildren(frame("Audit log", null, panel("What the people watching have done", "sign-ins, changes, revokes, and every full record opened",
      el("div", { class: "table-wrap" }, el("table", null, el("thead", null, el("tr", null, el("th", null, "When"), el("th", null, "Who"), el("th", null, "What"), el("th", null, "From"))), body)),
      el("div", { class: "body" }, more))));
    await load();
  }

  // ------------------------------------------------------------------ start

  render();
  // keep the live badge and the pause banner honest on every page
  setInterval(async () => {
    if (!S.me || document.visibilityState !== "visible" || (location.hash || "#/").split("?")[0] === "#/") return;
    const before = S.overview && S.overview.paused;
    await refreshOverview();
    if (S.overview && S.overview.paused !== before) render();
  }, 10000);
})();
