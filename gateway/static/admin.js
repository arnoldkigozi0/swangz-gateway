"use strict";
/* Swangz Gateway — the control room. This file is the core: sign-in, the frame and navigation, the
   command menu (Ctrl+K), routing, and the pieces every page shares. The pages themselves live in
   admin-*.js and register their routes here. Built on ui.js; plain DOM, no framework — everything a
   person typed is untrusted text and only ever lands in textContent. */
(() => {
  const { el, icon, fmt, toast } = SUI;
  const app = document.getElementById("app");
  const S = { me: null, timers: [], overview: null, route: "", tools: null, toolsByName: null, attention: null };

  // ------------------------------------------------------------------ the API

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }
  const GATEWAY = (typeof window !== "undefined" && window.SWANGZ_GATEWAY || "").replace(/\/+$/, "");
  const gadmin = (path) => GATEWAY + "/admin/api" + path;
  const gurl = (path) => GATEWAY + path;

  async function api(method, path, body) {
    const opts = { method, credentials: "include", headers: { "x-gateway-admin": "1" } };
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let res;
    try { res = await fetch(GATEWAY + "/admin/api" + path, opts); }
    catch (e) { throw new ApiError(0, "The gateway can't be reached"); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (res.status === 401 && path !== "/login") {
      S.me = null;
      showSignIn();
      throw new ApiError(401, "Please sign in again.");
    }
    if (!res.ok) throw new ApiError(res.status, (data && data.error) || res.statusText || "Something went wrong");
    return data;
  }
  const isOwner = () => S.me && S.me.role === "owner";

  function every(ms, fn) {
    const id = setInterval(() => { if (document.visibilityState === "visible") fn(); }, ms);
    S.timers.push(id);
    return id;
  }
  function clearTimers() { S.timers.forEach(clearInterval); S.timers = []; }

  // ------------------------------------------------------------------ building blocks

  /* A panel: a titled card. `sub` is a line of context, or a node of actions on the right. */
  function panel(title, sub, ...body) {
    const right = sub instanceof Node || Array.isArray(sub) ? el("div", { class: "panel-actions" }, sub) : sub ? el("div", { class: "sub" }, sub) : null;
    return el("section", { class: "panel" }, title ? el("header", null, el("h2", null, title), right) : null, ...body);
  }
  function empty(text, title, iconName) { return SUI.stateBox({ compact: true, icon: iconName || "info", title, text }); }
  function kpi(o) {
    return el("div", { class: "kpi" + (o.tone ? " " + o.tone : "") + (o.href ? " link" : "") },
      o.href ? el("a", { class: "kpi-link", href: o.href, "aria-label": o.label + ": " + o.value }) : null,
      el("div", { class: "label" }, o.icon ? icon(o.icon) : null, o.label, o.tip ? SUI.infoTip(o.tip) : null),
      el("div", { class: "value" + (o.text ? " text" : "") }, o.value),
      o.foot || o.note ? el("div", { class: "foot" }, o.foot || null, o.note ? el("span", { class: "note" }, o.note) : null) : null,
      o.spark ? el("div", { class: "spark" }, o.spark) : null);
  }

  /* A page split into tabs; each tab builds the first time it is opened. The tab lives in ?tab=. */
  function pageTabs(base, params, tabs) {
    tabs = tabs.filter(Boolean);
    const body = el("div", { class: "tab-body" });
    const built = new Map();
    let current = tabs.some((t) => t[0] === params.get("tab")) ? params.get("tab") : tabs[0][0];
    const bar = el("div", { class: "ptabs", role: "tablist" });
    function show(id, focus) {
      current = id;
      bar.querySelectorAll("button").forEach((b) => {
        const on = b.dataset.tab === id;
        b.classList.toggle("on", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        if (on && focus) b.focus();
      });
      const keep = new URLSearchParams(location.hash.split("?")[1] || "");
      keep.set("tab", id);
      history.replaceState(null, "", base + "?" + keep.toString());
      if (built.has(id)) { body.replaceChildren(built.get(id)); return; }
      const holder = el("div", { class: "tab-pane", role: "tabpanel" });
      built.set(id, holder);
      body.replaceChildren(holder);
      SUI.load(holder, () => tabs.find((t) => t[0] === id)[2](), SUI.skeleton("rows", 4));
    }
    bar.replaceChildren(...tabs.map(([id, label, , badge]) => el("button", {
      type: "button", role: "tab", "data-tab": id, onclick: () => show(id),
    }, label, badge ? el("span", { class: "tab-count" }, String(badge)) : null)));
    bar.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      const i = tabs.findIndex((t) => t[0] === current);
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length][0];
      show(next, true);
    });
    show(current);
    return el("div", { class: "tabs-wrap" }, bar, body);
  }

  function dialog(title, body, buttons) {
    const id = "dlg-" + Math.random().toString(36).slice(2, 8);
    const d = el("dialog", { "aria-labelledby": id },
      el("header", null, el("h2", { id }, title), el("button", { class: "btn small quiet icon-only", onclick: () => d.close(), "aria-label": "Close" }, icon("x"))),
      el("div", { class: "body" }, body),
      buttons && buttons.filter(Boolean).length ? el("footer", null, buttons) : null);
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }

  /* Destructive actions say exactly what will happen and wait for a deliberate yes. */
  function confirmAction(title, text, label, danger) {
    return new Promise((resolve) => {
      let ok = false;
      const yes = el("button", { class: "btn " + (danger ? "danger solid" : "primary"), onclick: () => { ok = true; d.close(); } }, label);
      const no = el("button", { class: "btn", onclick: () => d.close() }, "Cancel");
      const d = dialog(title, el("p", { class: "confirm-text" }, text), [no, yes]);
      d.addEventListener("close", () => resolve(ok));
      no.focus();
    });
  }

  /* A side sheet over the page, for drilling into one thing without losing your place. */
  function sheet(onClose, label) {
    const scrim = el("div", { class: "scrim" });
    const node = el("aside", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": label || "Details" });
    let release = null;
    function close() {
      if (onClose) onClose();
      node.classList.remove("in"); scrim.classList.remove("in");
      setTimeout(() => { scrim.remove(); node.remove(); }, 320);
      document.removeEventListener("keydown", onKey);
      if (release) release();
    }
    function onKey(e) { if (e.key === "Escape" && !document.querySelector("dialog[open]") && !document.querySelector(".u-cmd-scrim")) close(); }
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.append(scrim, node);
    requestAnimationFrame(() => {
      scrim.classList.add("in"); node.classList.add("in");
      release = SUI.trapFocus(node);
      const first = node.querySelector("button, a[href], input, select");
      if (first) first.focus({ preventScroll: true });
    });
    return { node, close };
  }

  function bar(value, limit) {
    const pct = limit ? Math.min(100, (value / limit) * 100) : 0;
    const fill = el("i");
    fill.style.width = pct + "%";
    return el("div", { class: "bar" + (limit && value >= limit ? " over" : limit && value >= 0.8 * limit ? " near" : ""), role: "meter",
      "aria-valuemin": "0", "aria-valuemax": String(limit || 0), "aria-valuenow": String(value || 0), "aria-label": "Used" }, fill);
  }

  // ------------------------------------------------------------------ tools, people, devices: the threads between objects

  async function toolIndex(force) {
    if (!S.tools || force) {
      const cat = await api("GET", "/catalog");
      S.tools = Object.fromEntries([...cat.tools, ...cat.removed].map((t) => [t.id, t]));
      S.toolsByName = Object.fromEntries(Object.values(S.tools).map((t) => [t.name.toLowerCase(), t]));
      S.catalog = cat;
      S.workspaceManaged = !!cat.workspace_managed;
      S.workspaceAgent = !!cat.workspace_agent;
    }
    return S.tools;
  }
  function toolFor(id, name) {
    return (S.tools && id && S.tools[id]) || (S.toolsByName && name && S.toolsByName[String(name).toLowerCase()]) || { name: name || "?" };
  }
  const toolLogo = (id, name, size) => SUI.logo(toolFor(id, name), size);
  function toolLink(id, name, size) {
    const t = toolFor(id, name);
    const inner = [toolLogo(id, name, size || "xs"), el("span", null, t.name || name || "Unknown tool")];
    return t.id ? el("a", { class: "obj tool", href: `#/tools?open=${t.id}` }, inner) : el("span", { class: "obj tool" }, inner);
  }
  function personLink(id, name, opts) {
    opts = opts || {};
    const inner = [opts.avatar === false ? null : id ? SUI.avatar(name || "?", "sm") : el("span", { class: "u-avatar sm unknown", "aria-hidden": "true" }, icon("lock")),
      el("span", null, name || "Unknown key")];
    return id ? el("a", { class: "obj person", href: "#/people/" + id }, inner) : el("span", { class: "obj person unknown" }, inner);
  }
  function deviceLink(keyId, label) {
    if (!label && !keyId) return null;
    const inner = [icon("device"), el("span", null, label || "a device")];
    return keyId ? el("a", { class: "obj device", href: "#/devices/" + keyId }, inner) : el("span", { class: "obj device" }, inner);
  }
  function where(ip, place) {
    if (!ip) return null;
    return el("span", { class: "obj where", "data-tip": "The address it came from. Location isn't looked up — no IP location database is used.", tabindex: "0" },
      icon("pin"), el("span", { class: "mono" }, ip), place && place !== "unknown" ? el("span", { class: "faint" }, " · " + place) : null);
  }

  // ------------------------------------------------------------------ requests and events

  /* What an agent did, in recognisable categories rather than a log wall. */
  const ACTION = {
    command: ["Command", "terminal"], edit: ["Edit", "edit"], read: ["Read", "read"], web: ["Web", "globe"], agent: ["Agent", "bot"],
    voice: ["Media", "mic"], image: ["Media", "image"], video: ["Media", "video"], media: ["Media", "image"], other: ["System", "chip"],
  };
  function actionsList(actions, limit) {
    if (!actions || !actions.length) return null;
    const shown = limit ? actions.slice(0, limit) : actions;
    return el("ul", { class: "actions" },
      shown.map((a) => {
        const [label, ic] = ACTION[a.kind] || ACTION.other;
        return el("li", { class: "a-" + (ACTION[a.kind] ? a.kind : "other") }, el("span", { class: "k" }, icon(ic), label), el("span", { class: "t" }, a.text));
      }),
      limit && actions.length > limit ? el("li", { class: "more" }, el("span", { class: "k" }), el("span", { class: "t faint" }, `+${actions.length - limit} more`)) : null);
  }

  const OUTCOME = {
    request: { ok: ["ok", "Completed"], blocked: ["blocked", "Blocked"], denied: ["blocked", "Wrong key"], cut: ["failed", "Stopped"],
      aborted: ["idle", "Closed by the tool"], error: ["failed", "Failed"] },
    launch: { opened: ["ok", "Opened"], refused: ["blocked", "Refused"] },
    site: { allowed: ["ok", "Visited"], blocked: ["blocked", "Blocked"] },
  };
  function outcomeStatus(type, outcome, plain) {
    const [state, label] = (OUTCOME[type] || {})[outcome] || ["info", outcome || "—"];
    return SUI.status(state, label, { plain });
  }

  function flagBadges(flags) {
    if (!flags) return [];
    return flags.split(",").filter(Boolean).map((f) => {
      if (f.startsWith("secret:")) return el("span", { class: "u-badge bad", "data-tip": "Looks like " + f.slice(7) + " — matched by pattern; could be a test key.", tabindex: "0" }, icon("key"), "Credential");
      if (f.startsWith("attachments:")) return SUI.badge(f.slice(12) + " file(s)", "info");
      return SUI.badge(f);
    });
  }
  const CLASS_LABEL = { auxiliary: "background task", compaction: "compaction", workflow: "workflow" };
  function agentBadges(r) {
    const out = [];
    if (r.agent) {
      const cut = r.agent.indexOf(":");
      const type = cut < 0 ? r.agent : r.agent.slice(0, cut);
      out.push(el("span", { class: "u-badge agent", "data-tip": r.agent, tabindex: "0" }, icon("bot"), type === "sub-agent" ? "Sub-agent" : "Sub-agent · " + type));
    }
    if (r.request_class && CLASS_LABEL[r.request_class]) out.push(SUI.badge(CLASS_LABEL[r.request_class]));
    return out;
  }
  const totalTokens = (r) => (r.in_tok || 0) + (r.out_tok || 0) + (r.cache_write_tok || 0) + (r.cache_read_tok || 0);
  const units = (r) => (r.units ? `${Number(r.units).toLocaleString()} ${r.unit || ""}`.trim() : "");

  /* A request from /requests, in the timeline's event shape. */
  function reqEvent(r) {
    const t = toolFor(r.client === "Claude Code" ? "claude-code" : r.client === "Codex" ? "codex" : null, r.client);
    return { type: "request", id: r.id, ts: r.ts, person_id: r.person_id, person: r.person, tool_id: t.id || null, tool: t.id ? t.name : null,
      app: r.client || null, model: r.model, kind: r.kind, outcome: r.outcome, reason: r.reason, cost: r.cost, tokens: totalTokens(r),
      duration_ms: r.duration_ms, session: r.session, prompt: r.prompt, actions: (r.actions || []).length, actionList: r.actions,
      reply: r.reply, credential: (r.flags || "").includes("secret:"), device: r.device, key_id: r.key_id, ip: r.client_ip, flags: r.flags,
      agent: r.agent, request_class: r.request_class, units: units(r), result_urls: r.result_urls };
  }

  /* One event: who, what, why (the prompt), when, where from, on which device, and how it ended. */
  function eventItem(e, opts) {
    opts = opts || {};
    const verb = e.type === "launch" ? (e.outcome === "opened" ? "opened" : "tried to open")
      : e.type === "site" ? (e.outcome === "blocked" ? "was blocked from" : "visited")
        : e.kind === "media" ? "generated with" : "used";
    const toolNode = e.tool ? toolLink(e.tool_id, e.tool) : e.app ? el("span", { class: "obj tool" }, toolLogo(null, e.app, "xs"), el("span", null, e.app)) : el("span", { class: "faint" }, "a tool");
    const meta = [];
    if (e.type === "request") {
      if (e.app && e.tool && e.app !== e.tool) meta.push(el("span", { class: "obj" }, icon("terminal"), e.app));
      if (e.model) meta.push(el("span", { class: "mono faint" }, e.model));
      if (e.device || e.key_id) meta.push(deviceLink(e.key_id, e.device));
      if (e.platform && e.platform !== e.app && e.platform !== e.tool) meta.push(el("span", { class: "obj" }, icon("monitor"), e.platform));
      if (e.ip) meta.push(where(e.ip, e.place));
      if (e.duration_ms) meta.push(el("span", { class: "obj" }, icon("clock"), fmt.ms(e.duration_ms)));
      if (e.actions) meta.push(el("span", { class: "obj" }, icon("layers"), SUI.plural(e.actions, "action")));
    } else if (e.type === "launch") {
      meta.push(el("span", { class: "obj" }, icon("open"), "from the Swangz AI portal"));
      if (e.platform) meta.push(el("span", { class: "obj" }, icon("monitor"), e.platform));
      if (e.ip) meta.push(where(e.ip, e.place));
    } else {
      meta.push(el("span", { class: "obj" }, icon("globe"), "browser extension"));
      if (e.seconds) meta.push(el("span", { class: "obj" }, icon("clock"), fmt.dur(e.seconds)));
      if (e.host && e.host !== e.tool) meta.push(el("span", { class: "mono faint" }, e.host));
    }
    const money = e.type === "request" && e.outcome === "ok" ? (e.kind === "media" && e.cost === null ? (e.units || null) : fmt.money(e.cost)) : null;
    const href = e.type === "request" && e.id ? "#/records/" + e.id : null;
    return el("li", { class: `ev t-${e.type}` + (opts.fresh ? " u-enter" : "") },
      el("div", { class: "ev-rail" }, el("time", { class: "ev-time", datetime: new Date(e.ts * 1000).toISOString(), title: fmt.stamp(e.ts) }, fmt.clock(e.ts)),
        el("span", { class: "ev-dot", "aria-hidden": "true" }, icon(e.type === "request" ? (e.kind === "media" ? "image" : "spark") : e.type === "launch" ? "open" : "globe"))),
      el("div", { class: "ev-body" },
        el("div", { class: "ev-head" },
          opts.noPerson ? null : personLink(e.person_id, e.person || (e.type === "request" ? "No valid key" : "Someone")),
          opts.noPerson ? null : el("span", { class: "ev-verb" }, verb),
          toolNode,
          e.type === "request" ? agentBadges(e) : null,
          e.credential ? el("span", { class: "u-badge bad" }, icon("key"), "Credential") : null,
          el("span", { class: "ev-grow" }),
          money ? el("span", { class: "ev-cost u-num" }, money) : null,
          outcomeStatus(e.type, e.outcome)),
        e.prompt ? el("p", { class: "ev-prompt" }, e.prompt) : e.type === "request" && e.outcome === "ok" && !opts.compact
          ? el("p", { class: "ev-prompt none" }, "No typed prompt — the tool was working on its own.") : null,
        e.type === "request" && e.outcome !== "ok" && e.reason ? el("p", { class: "ev-reason" }, e.reason) : null,
        opts.compact ? null : el("div", { class: "ev-meta" }, meta)),
      href ? el("a", { class: "ev-open", href, "aria-label": "Open the full record of request " + e.id }, el("span", null, "Record"), icon("chevronRight")) : el("span"));
  }

  /* Events grouped under day headings (in the chosen time zone). */
  function eventDays(events, opts) {
    const wrap = el("div", { class: "days" });
    let day = null, list = null;
    function add(evs, fresh) {
      evs.forEach((e) => {
        const d = SUI.startOfDay(e.ts);
        if (d !== day) {
          day = d;
          list = el("ol", { class: "events" });
          wrap.append(el("section", { class: "day" }, el("h3", { class: "day-h" }, el("span", null, fmt.day(e.ts)), el("span", { class: "faint" }, fmt.date(e.ts))), list));
        }
        list.append(eventItem(e, { ...opts, fresh }));
      });
    }
    add(events);
    return { node: wrap, add };
  }

  function launchList(items, noPerson) {
    return el("ul", { class: "mini-list" }, items.map((o) => el("li", null,
      toolLogo(o.tool_id, o.tool, "sm"),
      el("div", { class: "grow" },
        noPerson ? el("strong", null, o.tool || "a removed tool")
          : [personLink(o.person_id, o.person || "Someone", { avatar: false }), el("span", { class: "muted" }, " opened "), el("strong", null, o.tool || "a removed tool")]),
      el("span", { class: "row nowrap" }, o.outcome === "refused" ? SUI.status("blocked", "Refused", { plain: true }) : null,
        el("time", { class: "hint nowrap", title: fmt.stamp(o.ts) }, fmt.ago(o.ts))))));
  }

  // ------------------------------------------------------------------ ranges in the address bar

  /* A page's time range lives in its address (?range=7d or ?from=&to=), so a view can be linked. */
  function rangeFrom(params, fallback) {
    const preset = params.get("range") || fallback || "today";
    const r = SUI.presetRange(preset, { from: params.get("from"), to: params.get("to") });
    return { preset, from: params.get("from") || "", to: params.get("to") || "", ...r };
  }
  function rangeQuery(r) {
    const p = new URLSearchParams();
    if (r.since) p.set("since", String(r.since));
    if (r.until) p.set("until", String(r.until));
    return p;
  }
  function keepParams(base, values) {
    const keep = new URLSearchParams(location.hash.split("?")[1] || "");
    for (const [k, v] of Object.entries(values)) { if (v === null || v === undefined || v === "") keep.delete(k); else keep.set(k, v); }
    history.replaceState(null, "", base + (keep.toString() ? "?" + keep.toString() : ""));
  }

  // ------------------------------------------------------------------ sign-in

  const AUTH_ERRORS = {
    cancelled: "Google sign-in was cancelled.",
    expired: "That sign-in took too long or was started in another browser. Try again.",
    google: "Google couldn't confirm that account. Try again.",
    no_account: "That Google account isn't a console user. An owner can add it under Settings → Console users (use the Google email as the username).",
    off: "Google sign-in isn't set up yet.",
  };
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

  function showSignIn() {
    clearTimers();
    document.title = "Sign in · Swangz Gateway";
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
    const user = el("input", { type: "text", autocomplete: "username", required: true, id: "si-user" });
    const pass = el("input", { type: "password", autocomplete: "current-password", required: true, id: "si-pass" });
    const go = el("button", { class: "btn primary block", type: "submit" }, "Sign in");
    const form = el("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        go.disabled = true;
        err.textContent = "";
        try {
          await api("POST", "/login", { username: user.value, password: pass.value });
          S.me = await api("GET", "/me");
          start();
        } catch (x) {
          err.textContent = x.message;
          go.disabled = false;
        }
      },
    },
    el("div", { class: "signin-brand" }, el("img", { src: "/static/icon.svg", alt: "", width: 40, height: 40 }),
      el("div", null, el("div", { class: "eyebrow" }, "Swangz Gateway"), el("h1", null, "Control room"))),
    el("p", { class: "muted" }, "Mission control for company AI: who is using what, what it costs, and the switches to govern it."),
    google,
    el("label", { class: "field", for: "si-user" }, "Username", user),
    el("label", { class: "field", for: "si-pass" }, "Password", pass),
    err, go,
    el("p", { class: "hint" }, "Console users only. Staff sign in to Swangz AI at the main address."));
    app.replaceChildren(el("main", { class: "signin" }, el("div", { class: "signin-card" }, form),
      el("div", { class: "signin-foot" }, SUI.themeButton())));
    user.focus();
  }

  async function signOut() {
    try { await api("POST", "/logout"); } catch (e) { /* already out */ }
    S.me = null;
    showSignIn();
  }

  async function setPaused(paused) {
    if (paused) {
      const ok = await confirmAction("Stop all AI for everyone?",
        "Every request in flight is cut now, every new one is refused, and the portal's Open buttons close — until an owner resumes access. Use this if something is going wrong.",
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
    try { S.overview = await api("GET", "/overview"); } catch (e) { if (e.status === 401) throw e; }
    return S.overview;
  }
  async function refreshAttention() {
    try { S.attention = await api("GET", "/attention"); } catch (e) { /* the badge just waits */ }
    return S.attention;
  }

  // ------------------------------------------------------------------ the frame

  const NAV = [
    ["Monitor", [["#/", "Overview", "overview"], ["#/live", "Live", "live"], ["#/attention", "Needs attention", "attention"], ["#/activity", "Activity", "activity"]]],
    ["Govern", [["#/people", "People", "people"], ["#/devices", "Devices", "device"], ["#/tools", "Tools", "tools"], ["#/requests", "Access requests", "requests"]]],
    ["Money", [["#/licences", "Licences & spend", "licences"]]],
    ["Trust", [["#/security", "Security", "shield"], ["#/audit", "Audit log", "audit"], ["#/settings", "Settings", "settings"]]],
  ];
  const SECTION_OF = { "#/records": "#/activity", "#/sessions": "#/activity" };

  function navCounts(href) {
    const ov = S.overview;
    if (href === "#/live" && ov && ov.live.length) return el("span", { class: "count live", "aria-label": ov.live.length + " live" }, el("i", { class: "u-breathe" }), String(ov.live.length));
    if (href === "#/requests" && ov && ov.open_requests) return el("span", { class: "count warn", "aria-label": ov.open_requests + " open" }, String(ov.open_requests));
    if (href === "#/attention" && S.attention) {
      const n = (S.attention.counts.high || 0) + (S.attention.counts.medium || 0);
      if (n) return el("span", { class: "count bad", "aria-label": n + " need attention" }, String(n));
    }
    return null;
  }

  function sidebar(active, onNavigate) {
    const nav = el("nav", { class: "nav", "aria-label": "Control room" }, NAV.map(([group, links]) => el("div", { class: "nav-group" },
      el("div", { class: "group", "aria-hidden": "true" }, group),
      links.map(([href, label, ic]) => el("a", { href, class: href === active ? "on" : null, "aria-current": href === active ? "page" : null, onclick: onNavigate || null },
        icon(ic), el("span", { class: "nl" }, label), navCounts(href))))));
    const paused = S.overview && S.overview.paused;
    return el("aside", { class: "side" },
      el("a", { class: "brand", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }),
        el("div", null, el("span", { class: "bn" }, "Swangz ", el("b", null, "Gateway")), el("small", null, "Control room"))),
      el("button", { class: "side-search", type: "button", onclick: () => openCommand() }, icon("search"), el("span", null, "Search or jump to…"),
        el("span", { class: "u-kbd" }, navigator.platform && /Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K")),
      nav,
      el("div", { class: "side-grow" }),
      isOwner() ? el("div", { class: "estop" + (paused ? " on" : "") },
        paused ? [el("div", { class: "estop-t" }, SUI.status("blocked", "AI paused"), el("span", null, "for everyone")),
          el("button", { class: "btn small primary", onclick: () => setPaused(false) }, "Resume")]
          : [el("div", { class: "estop-t" }, el("span", { class: "u-label" }, "Emergency"), el("span", null, "Cut every request now")),
            el("button", { class: "btn small danger", onclick: () => setPaused(true) }, icon("stop"), "Stop all AI")]) : null,
      el("div", { class: "who" }, SUI.avatar(S.me.username),
        el("div", { class: "id" }, el("strong", null, S.me.username), el("span", null, S.me.role === "owner" ? "Owner · can change things" : "Viewer · read-only")),
        SUI.themeButton(),
        el("button", { class: "theme-btn", type: "button", onclick: signOut, "aria-label": "Sign out", "data-tip": "Sign out" }, icon("logout"))));
  }

  /* Every page sits in the same frame: the sidebar (a drawer on phones), then a header saying where
     you are, why the page exists, and what you can do here. */
  function frame(o, content) {
    const here = (location.hash || "#/").split("?")[0];
    const section = here === "#/" || here === "" ? "#/" : "#/" + here.split("/")[1];
    const active = SECTION_OF[section] || section;
    document.title = (o.title ? o.title + " · " : "") + "Swangz Gateway";
    const side = sidebar(active);
    const paused = S.overview && S.overview.paused;
    const banner = paused ? el("div", { class: "banner", role: "alert" }, icon("stop"),
      el("span", null, el("strong", null, "AI access is paused for everyone. "), "Requests and tool launches are refused until an owner resumes."),
      isOwner() ? el("button", { class: "btn small primary", onclick: () => setPaused(false) }, "Resume access") : null) : null;
    const appbar = el("div", { class: "appbar" },
      el("button", { class: "btn quiet icon-only", type: "button", "aria-label": "Open navigation", onclick: () => openDrawer(active) }, icon("menu")),
      el("a", { class: "brand mini", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Gateway"),
      el("button", { class: "btn quiet icon-only", type: "button", "aria-label": "Search", onclick: () => openCommand() }, icon("search")));
    const crumbs = o.crumbs ? el("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, [].concat(o.crumbs).map((c, i, all) =>
      [c, i < all.length - 1 ? el("span", { class: "sep", "aria-hidden": "true" }, "/") : null])) : null;
    const top = el("header", { class: "top" },
      el("div", { class: "top-id" }, crumbs, el("div", { class: "title-row" }, o.lead || null, el("h1", null, o.title), o.status || null),
        o.lede ? el("p", { class: "lede" }, o.lede) : null),
      o.actions ? el("div", { class: "top-actions" }, o.actions) : null);
    app.replaceChildren(el("div", { class: "shell" }, side,
      el("div", { class: "main" }, appbar, banner, el("main", { id: "main", tabindex: "-1" }, top, el("div", { class: "page" + (o.wide ? " wide" : "") }, content)))));
  }

  function openDrawer(active) {
    const scrim = el("div", { class: "scrim" });
    const side = sidebar(active, () => close());
    side.classList.add("drawer");
    side.setAttribute("role", "dialog");
    side.setAttribute("aria-modal", "true");
    side.setAttribute("aria-label", "Navigation");
    const closeBtn = el("button", { class: "btn quiet icon-only drawer-close", type: "button", "aria-label": "Close navigation", onclick: () => close() }, icon("x"));
    side.prepend(closeBtn);
    let release = null;
    function close() {
      side.classList.remove("in"); scrim.classList.remove("in");
      document.removeEventListener("keydown", onKey);
      setTimeout(() => { side.remove(); scrim.remove(); }, 260);
      if (release) release();
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.append(scrim, side);
    requestAnimationFrame(() => { scrim.classList.add("in"); side.classList.add("in"); release = SUI.trapFocus(side); closeBtn.focus(); });
  }

  // ------------------------------------------------------------------ the command menu

  let commandOpen = null;
  function openCommand() { if (commandOpen) commandOpen(); }
  function setupCommand() {
    const go = (group, title, href, ic, keywords, sub) => ({ group, title, href, icon: ic, keywords, sub });
    const actions = [
      ...NAV.flatMap(([, links]) => links.map(([href, label, ic]) => go("Go to", label, href, ic, "page open"))),
      go("Go to", "Who used what", "#/activity?tab=usage", "people", "usage lens"),
      go("Go to", "Who did what, when, where", "#/activity?tab=timeline", "activity", "timeline investigate"),
      go("Go to", "What cost us money?", "#/licences?tab=spend", "wallet", "spend cost report"),
      go("Actions", "Search AI requests", "#/activity?tab=ai", "search", "prompt find"),
      go("Actions", "Review security", "#/security", "shield", "alerts"),
      { group: "Actions", title: "Export activity (CSV)", icon: "download", keywords: "report download", run: () => { location.href = gadmin("/export.csv"); } },
      isOwner() ? go("Actions", "Add a person", "#/people?add=1", "plus", "new staff user") : null,
      isOwner() ? go("Actions", "Add a tool", "#/tools?add=1", "plus", "new catalog") : null,
      isOwner() ? go("Actions", "Grant or revoke tool access", "#/tools", "tools", "assign entitlement") : null,
      { group: "Actions", title: "Switch theme", icon: "sun", keywords: "dark light porcelain obsidian", run: () => { SUI.applyTheme(SUI.theme() === "dark" ? "light" : "dark", true); render(); } },
      isOwner() && !(S.overview && S.overview.paused) ? { group: "Actions", title: "Stop all AI", sub: "Cuts every request — asks first", icon: "stop", keywords: "pause kill switch emergency", run: () => setPaused(true) } : null,
    ].filter(Boolean);
    commandOpen = SUI.commandMenu({
      actions, placeholder: "Search people, tools, devices, requests — or type a page",
      search: async (q) => {
        const out = await api("GET", "/search?q=" + encodeURIComponent(q));
        await toolIndex().catch(() => null);
        const ICON_OF = { People: "user", Tools: "tools", Devices: "device", Requests: "spark", Sessions: "layers", Audit: "audit" };
        return out.groups.map((g) => ({ group: g.group, items: g.items.map((it) => ({ title: it.title, sub: it.sub, href: it.href,
          icon: ICON_OF[g.group], lead: g.group === "Tools" ? toolLogo(it.tool_id, it.title, "sm") : g.group === "People" ? SUI.avatar(it.title, "sm") : null,
          hint: it.ts ? fmt.when(it.ts) : null })) }));
      },
    });
  }

  // ------------------------------------------------------------------ routing

  const ROUTES = [];
  function page(rx, fn) { ROUTES.push([rx, fn]); }

  let rendering = 0;
  async function render() {
    const mine = ++rendering;
    clearTimers();
    SUI.hideTip();
    document.querySelectorAll(".sheet, .scrim, .side.drawer").forEach((n) => n.remove());
    if (!S.me) {
      try { S.me = await api("GET", "/me"); } catch (e) { return; }
      SUI.setGatewayOffset(S.me.tz_offset_minutes);
    }
    try { await refreshOverview(); } catch (e) { return; }  // the live badge and the pause banner are never staler than the page
    if (mine !== rendering) return;
    const [path, query] = (location.hash || "#/").split("?");
    const params = new URLSearchParams(query || "");
    for (const [rx, fn] of ROUTES) {
      const m = path.match(rx);
      if (!m) continue;
      S.route = location.hash;
      // show the frame straight away with a skeleton, so a slow page never looks blank
      frame({ title: "" }, SUI.skeleton("cards", 4));
      try {
        await fn(params, ...m.slice(1).map(decodeURIComponent));
      } catch (e) {
        if (e.status !== 401 && mine === rendering) {
          frame({ title: e.status === 404 ? "Not found" : "Something went wrong" },
            SUI.errorBox(e, () => render(), e.status === 404 ? "This isn't here any more" : "This page couldn't load"));
        }
      }
      if (!params.get("keep-scroll")) window.scrollTo(0, 0);
      return;
    }
    location.hash = "#/";
  }

  function start() {
    SUI.setGatewayOffset(S.me ? S.me.tz_offset_minutes : 180);
    setupCommand();
    render().then(() => refreshAttention().then(() => { const n = document.querySelector(".side"); if (n && S.me) n.replaceWith(sidebar(n.querySelector("a.on")?.getAttribute("href") || "#/")); }));
  }

  window.addEventListener("hashchange", render);
  // the skip link focuses the page without touching the address (the address is the route)
  document.addEventListener("click", (e) => {
    const skip = e.target.closest && e.target.closest("a.skip");
    if (skip) { e.preventDefault(); const m = document.getElementById("main"); if (m) m.focus(); }
  });
  document.addEventListener("swangz:tz", () => render());

  // keep the live badge, the attention count and the pause banner honest on every page
  setInterval(async () => {
    if (!S.me || document.visibilityState !== "visible") return;
    const before = S.overview && S.overview.paused;
    try { await refreshOverview(); } catch (e) { return; }
    if (S.overview && S.overview.paused !== before) { render(); return; }
    const side = document.querySelector(".shell > .side");
    if (side) {
      const active = side.querySelector("a.on");
      side.replaceWith(sidebar(active ? active.getAttribute("href") : "#/"));
    }
  }, 15000);
  setInterval(() => { if (S.me && document.visibilityState === "visible") refreshAttention(); }, 60000);

  window.SWA = {
    S, api, ApiError, gadmin, gurl, GATEWAY, isOwner, every, clearTimers, panel, empty, kpi, pageTabs, dialog, confirmAction, sheet, bar,
    toolIndex, toolFor, toolLogo, toolLink, personLink, deviceLink, where, actionsList, ACTION, outcomeStatus, flagBadges, agentBadges,
    totalTokens, units, reqEvent, eventItem, eventDays, launchList, rangeFrom, rangeQuery, keepParams, frame, render, page,
    setPaused, refreshOverview, refreshAttention, openCommand,
  };

  document.addEventListener("DOMContentLoaded", () => {
    api("GET", "/me").then((me) => { S.me = me; start(); }).catch(() => { /* the sign-in page is showing */ });
  });
})();
