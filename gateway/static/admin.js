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
    const epoch = rendering;
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
    // A read for a page that has since been left never answers: that page stops where it is instead of
    // drawing itself over the one now showing. Changes (POST, PUT, DELETE) always finish.
    if (method === "GET" && epoch !== rendering) return new Promise(() => {});
    if (!res.ok) throw new ApiError(res.status, (data && data.error) || res.statusText || "Something went wrong");
    return data;
  }
  // `owner` and `can` come from a V2 gateway; an older one only says role, so fall back to it rather than
  // hiding every button while the pages (on Netlify) are newer than the gateway behind them
  const isOwner = () => !!(S.me && (S.me.owner !== undefined ? S.me.owner : S.me.role === "owner"));
  /* What this console user may change (gateway/authz.py decides; this only hides buttons they couldn't use):
     govern (people, tools, access, models, policies), money (prices, budgets, subscriptions, rates),
     trust (security settings, networks, incidents), emergency (the stops), admin (console users, retention). */
  const can = (area) => !!(S.me && (Array.isArray(S.me.can) ? S.me.can.includes(area) : isOwner()));
  const roleLabel = () => (S.me ? S.me.role_label || (S.me.owner ? "Owner" : "Viewer") : "");

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

  /* Unsaved changes. A form registers a check while it has edits; switching tabs, following a link or closing
     the window asks first instead of dropping them. */
  let dirtyCheck = null;
  function setDirty(fn) { dirtyCheck = fn || null; }
  const isDirty = () => !!(dirtyCheck && dirtyCheck());
  async function confirmLeave() {
    if (!isDirty()) return true;
    const ok = await confirmAction("Leave without saving?", "You have changes on this page that haven't been saved. Leave and they are lost.", "Leave without saving", true);
    if (ok) dirtyCheck = null;
    return ok;
  }
  window.addEventListener("beforeunload", (e) => { if (isDirty()) { e.preventDefault(); e.returnValue = ""; } });

  /* One line under a page's tabs, where the view's job isn't obvious from its name. Keyed by page and tab. */
  const TAB_HELP = {
    "#/": {
      now: "The most urgent conditions and who is working right now. The full queue is under Needs attention.",
      trends: "How use and estimated metered spend moved over the last 30 days.",
      leaders: "The tools and people with the most use in 30 days. The full breakdown is Activity → Who used what.",
      licences: "The biggest licence savings and what renews soon. Everything else is under Licences & spend.",
    },
    "#/activity": {
      timeline: "Everything in order of time: AI requests, tools opened, website visits, shared-account turns, sign-ins and access changes.",
      usage: "Totals per person and tool for the period — for comparing, not for reading individual requests.",
      ai: "One row per AI request through the gateway; open one for its full record.",
      opens: "Tools opened from the Swangz AI portal, with the browser and address they were opened from.",
      sites: "Visits to AI websites seen by the browser extension: which site, when and how long — never what was on the page.",
    },
    "#/licences": {
      licences: "Seats paid for against real use, and the idle ones you can reclaim.",
      spend: "Metered AI spend for any period, where it went, and how each amount is worked out.",
      renewals: "Plans that renew soon, so nothing renews by surprise.",
    },
    "#/policies": {
      list: "The rules the gateway enforces now. A change applies to the next request.",
      simulate: "Try a rule against what really happened. Nothing is saved and nobody is affected.",
      explain: "Every check for one person and one tool, in the order the gateway makes them.",
    },
    "#/devices": {
      keys: "One gateway key per laptop or coding tool.",
      browsers: "Browsers staff opened tools from in the portal.",
    },
  };

  /* Tab sets on the page that is showing, so Back and Forward between tabs of the same page switch the view
     instead of rebuilding the page and fetching everything again. */
  let TABSETS = [];

  /* A page split into tabs; each tab builds the first time it is opened and is kept. The chosen tab lives in
     the address under its own parameter (`tab`, or opts.param for a second level such as Settings sections),
     so it can be linked, refreshed, and stepped through with Back and Forward.
       tabs: [id, label, build(), badge?, description?]
       opts: { vertical, param, clears: [params a change here resets], descriptions, help: false } */
  function pageTabs(base, params, tabs, opts) {
    opts = opts || {};
    tabs = tabs.filter(Boolean);
    const paramName = opts.param || "tab";
    const built = new Map();
    const routeKey = base.replace(/\/[^/]+$/, (m) => (/^\/(\d+|[0-9a-f]{12})$/.test(m) ? "" : m));
    const valid = (id) => tabs.some((t) => t[0] === id);
    let current = valid(params.get(paramName)) ? params.get(paramName) : tabs[0][0];
    const uid = "pt" + Math.random().toString(36).slice(2, 7);
    const bar = el("div", { class: "ptabs" + (opts.vertical ? " vertical" : ""), role: "tablist", "aria-orientation": opts.vertical ? "vertical" : "horizontal",
      "aria-label": opts.label || "Views" });
    const panel = el("div", { class: "tab-pane-wrap", role: "tabpanel", id: uid + "-panel", tabindex: "-1" });
    function description(id) {
      if (opts.help === false) return "";
      const tab = tabs.find((t) => t[0] === id);
      return (tab && tab[4]) || (opts.descriptions && opts.descriptions[id]) || ((TAB_HELP[routeKey] || {})[id]) || "";
    }
    const showing = () => ((location.hash || "#/").split("?")[0] || "#/") === base;
    function address(id, how) {
      const keep = new URLSearchParams(location.hash.split("?")[1] || "");
      if (how === "user") (opts.clears || []).forEach((k) => keep.delete(k));  // a different view: its own sections start over
      if (id === tabs[0][0] && opts.defaultless) keep.delete(paramName); else keep.set(paramName, id);
      const q = keep.toString();
      return base + (q ? "?" + q : "");
    }
    // how: "init" (first draw: normalise the address), "user" (a click or key: a new history entry),
    // "history" (Back/Forward already moved the address)
    function show(id, how, focus) {
      current = id;
      bar.querySelectorAll("[role=tab]").forEach((b) => {
        const on = b.dataset.tab === id;
        b.classList.toggle("on", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        if (on) panel.setAttribute("aria-labelledby", b.id);
        if (on && focus) b.focus();
      });
      // the address is only ever written for the page that is showing
      const target = showing() ? address(id, how) : location.hash;
      if (how === "user" && target !== location.hash) { history.pushState(null, "", target); S.route = target; }
      else if (how !== "history" && target !== location.hash) { history.replaceState(null, "", target); S.route = target; }
      const note = description(id);
      if (!built.has(id)) {
        const holder = el("div", { class: "tab-pane" });
        built.set(id, holder);
        SUI.load(holder, () => tabs.find((t) => t[0] === id)[2](), SUI.skeleton("rows", 4));
      }
      panel.replaceChildren(...[note ? el("p", { class: "tab-help" }, note) : null, built.get(id)].filter(Boolean));
      // a view kept from earlier may hold its own tabs: after a click, put their choice back in the address
      if (how === "user") TABSETS.filter((t) => t.bar !== bar && t.bar.isConnected && (opts.clears || []).includes(t.param)).forEach((t) => t.show(t.current, "init"));
    }
    async function choose(id, focus) {
      if (id === current) return;
      const wasDirty = isDirty();
      if (!(await confirmLeave())) { bar.querySelector(`[data-tab="${CSS.escape(current)}"]`)?.focus(); return; }
      if (wasDirty) built.delete(current);  // the changes were dropped: that view starts fresh next time
      show(id, "user", focus);
    }
    bar.replaceChildren(...tabs.map(([id, label, , badge]) => el("button", {
      type: "button", role: "tab", id: uid + "-" + id.replace(/[^a-z0-9-]/gi, ""), "aria-controls": uid + "-panel", "data-tab": id,
      onclick: () => choose(id),
    }, el("span", { class: "pt-l" }, label), badge ? el("span", { class: "tab-count", "aria-label": `(${badge})` }, String(badge)) : null)));
    bar.addEventListener("keydown", (e) => {
      const keys = opts.vertical ? ["ArrowUp", "ArrowDown", "Home", "End"] : ["ArrowLeft", "ArrowRight", "Home", "End"];
      if (!keys.includes(e.key)) return;
      e.preventDefault();
      const i = tabs.findIndex((t) => t[0] === current);
      const next = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + tabs.length) % tabs.length;
      choose(tabs[next][0], true);
    });
    show(current, "init");
    TABSETS.push({ param: paramName, clears: opts.clears || [], bar, get current() { return current; }, first: tabs[0][0], valid, show });
    // On a narrow screen the bar scrolls sideways: fade the edge while more tabs are hidden. The bar starts at its
    // first tab and moves only if the chosen one would otherwise be out of sight — and then just far enough.
    const edge = () => bar.classList.toggle("more", bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 2);
    bar.addEventListener("scroll", edge, { passive: true });
    requestAnimationFrame(() => {
      const on = bar.querySelector("[role=tab].on");
      if (on && bar.scrollWidth > bar.clientWidth) {
        const b = bar.getBoundingClientRect(), r = on.getBoundingClientRect();
        if (r.right > b.right - 24) bar.scrollLeft += r.right - b.right + 40;
        else if (r.left < b.left) bar.scrollLeft -= b.left - r.left + 16;
      }
      edge();
    });
    // a side sheet keeps the bar in its header and the view in its body
    if (opts.split) return { bar, body: el("div", { class: "tab-body" }, panel) };
    return el("div", { class: "tabs-wrap" + (opts.vertical ? " vertical" : "") }, bar, el("div", { class: "tab-body" }, panel));
  }

  /* Settings-style building blocks. A row says what a setting is on the left and holds its control on
     the right; a panel's own actions sit in its footer, at the right, the way out before the action. */
  function settingRow(label, hint, control, o) {
    o = o || {};
    return el("div", { class: "setting" + (o.stack ? " stack" : "") + (o.tone ? " " + o.tone : "") },
      el("div", { class: "setting-text" }, el(o.forId ? "label" : "div", { class: "setting-label", for: o.forId || null }, label), hint ? el("div", { class: "setting-hint" }, hint) : null),
      control ? el("div", { class: "setting-control" }, control) : null);
  }
  function switchInput(checked, disabled, label) {
    return el("input", { type: "checkbox", class: "switch", role: "switch", checked: !!checked, disabled: !!disabled, "aria-label": label || null });
  }
  function panelFoot(...items) { return el("footer", { class: "panel-foot" }, ...items.flat().filter(Boolean)); }

  /* Dialog footers read the same everywhere: the way out on the left of the group, the action last. */
  function withCancel(buttons, close) {
    const hasOut = buttons.some((b) => /^(cancel|close|done|not now|i.ve .*)$/i.test((b.textContent || "").trim()));
    // a destructive side-action (Remove beside Save) stands apart at the far left
    const aside = buttons.filter((b) => b.classList && b.classList.contains("danger") && buttons.some((x) => x !== b && x.classList.contains("primary")));
    aside.forEach((b) => b.classList.add("aside"));
    const rest = buttons.filter((b) => !aside.includes(b));
    return [...aside, hasOut ? null : el("button", { class: "btn quiet", type: "button", onclick: close }, "Cancel"), ...rest].filter(Boolean);
  }
  function dialog(title, body, buttons) {
    const id = "dlg-" + Math.random().toString(36).slice(2, 8);
    const d = el("dialog", { "aria-labelledby": id },
      el("header", null, el("h2", { id }, title), el("button", { class: "btn small quiet icon-only", onclick: () => d.close(), "aria-label": "Close" }, icon("x"))),
      el("div", { class: "body" }, body),
      buttons && buttons.filter(Boolean).length ? el("footer", null, withCancel(buttons.flat().filter(Boolean), () => d.close())) : null);
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
      const no = el("button", { class: "btn quiet", onclick: () => d.close() }, "Cancel");
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
  /* Where a request came from, and how that is known: a network Swangz named (exact), an approximate city from the
     offline location table, or only the kind of address. Never GPS, and never sent to an outside service. */
  function where(ip, place) {
    if (!ip) return null;
    const approx = place && / · approximate$/.test(place);
    const tip = approx ? "Approximate: from the offline location table (Settings → Locations). A city from an address can be wrong, especially on mobile data or a VPN."
      : place && /·/.test(place) ? "A network Swangz named in Settings → Locations."
        : "The address it came from. No location is known for it: name the network in Settings → Locations, or load a location table.";
    return el("span", { class: "obj where", "data-tip": tip, tabindex: "0" },
      icon("pin"), el("span", { class: "mono" }, ip), place && place !== "unknown" ? el("span", { class: "faint" }, " · " + place) : null);
  }

  /* For what: a purpose and how it is known. Declared is the person's word; derived comes from the tool; inferred is a
     guess from keywords, with its confidence — never shown as fact. */
  const PURPOSE_SOURCE = { declared: "Declared", derived: "From the tool", inferred: "Inferred" };
  function purposeChip(name, source, confidence, evidence) {
    if (!name) return null;
    const how = PURPOSE_SOURCE[source] || "";
    const pct = source === "inferred" && confidence != null ? ` · ${Math.round(confidence * 100)}%` : "";
    return el("span", { class: "u-badge purpose p-" + (source || "unknown"), tabindex: "0",
      "data-tip": `${how}${pct}${evidence ? " — " + evidence : ""}` + (source === "inferred" ? ". A guess from keywords, not a fact." : "") },
    icon("target"), name, source === "inferred" ? el("span", { class: "faint" }, "?") : null);
  }
  let purposeNames = null;
  async function purposeIndex() {
    if (!purposeNames) {
      try { purposeNames = Object.fromEntries((await api("GET", "/purposes")).items.map((p) => [p.id, p.name])); } catch (e) { purposeNames = {}; }
    }
    return purposeNames;
  }
  const purposeName = (id) => (id ? (purposeNames && purposeNames[id]) || id.replace(/-/g, " ") : null);

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

  /* One event in two quiet lines: who used what, how it ended and what it cost; then why (the prompt)
     and where from (device, address). The full story is one click away in the record. */
  const EVENT_KIND = { request: ["AI request", "spark"], launch: ["Opened from the portal", "open"], site: ["AI website visit", "globe"],
    turn: ["Shared account turn", "users"], access: ["Sign-in or access change", "key"] };
  function eventItem(e, opts) {
    opts = opts || {};
    if (e.type === "access") return accessItem(e, opts);
    const verb = e.type === "launch" ? (e.outcome === "opened" ? "opened" : "tried to open")
      : e.type === "site" ? (e.outcome === "blocked" ? "was blocked from" : "visited")
        : e.type === "turn" ? "took a turn on"
          : e.kind === "media" ? "generated with" : "used";
    const [kindLabel, kindIcon] = EVENT_KIND[e.type];
    const toolNode = e.tool ? toolLink(e.tool_id, e.tool) : e.app ? el("span", { class: "obj tool" }, toolLogo(null, e.app, "xs"), el("span", null, e.app)) : el("span", { class: "faint" }, "a tool");
    const detail = [];
    if (e.type === "request") {
      if ((e.device || e.key_id) && !opts.noDevice) detail.push(deviceLink(e.key_id, e.device));
      if (e.platform && e.platform !== e.app && e.platform !== e.tool) detail.push(el("span", { class: "obj" }, icon("monitor"), e.platform));
      if (e.ip) detail.push(where(e.ip, e.place));
      if (e.duration_ms) detail.push(el("span", { class: "obj" }, icon("clock"), fmt.ms(e.duration_ms)));
      if (e.actions) detail.push(el("span", { class: "obj" }, icon("layers"), SUI.plural(e.actions, "action")));
    } else if (e.type === "launch") {
      if (e.platform) detail.push(el("span", { class: "obj" }, icon("monitor"), e.platform));
      if (e.ip) detail.push(where(e.ip, e.place));
    } else if (e.type === "turn") {
      const end = e.ended || e.expires;
      detail.push(el("span", { class: "obj" }, icon("clock"), (e.ended ? "held until " : "until ") + fmt.clock(end)));
      if (e.ended_by && e.ended_by !== "system") detail.push(el("span", { class: "faint" }, e.ended_by === "self" ? "handed back" : "ended by " + e.ended_by));
      else if (e.reason) detail.push(el("span", { class: "faint" }, e.reason));
      if (e.where) detail.push(el("span", { class: "obj" }, icon("server"), e.where));
    } else {
      if (e.seconds) detail.push(el("span", { class: "obj" }, icon("clock"), fmt.dur(e.seconds)));
      if (e.host && e.host !== e.tool) detail.push(el("span", { class: "mono faint" }, e.host));
    }
    const lead = e.type !== "turn" && e.outcome && !["ok", "opened", "allowed"].includes(e.outcome) && e.reason ? el("span", { class: "ev-reason" }, e.reason)
      : e.prompt ? el("span", { class: "ev-prompt", title: e.prompt }, e.prompt) : null;
    const money = e.type === "request" && e.outcome === "ok" ? (e.kind === "media" && e.cost === null ? (e.units || null) : fmt.money(e.cost)) : null;
    const href = e.type === "request" && e.id ? "#/records/" + e.id : null;
    return el("li", { class: `ev t-${e.type}` + (opts.fresh ? " u-enter" : "") },
      el("time", { class: "ev-time", datetime: new Date(e.ts * 1000).toISOString(), title: fmt.stamp(e.ts) }, fmt.clock(e.ts)),
      el("div", { class: "ev-body" },
        el("div", { class: "ev-head" },
          el("span", { class: "ev-type", role: "img", "aria-label": kindLabel, "data-tip": kindLabel }, icon(kindIcon)),
          opts.noPerson ? null : personLink(e.person_id, e.person || (e.type === "request" ? "No valid key" : "Someone")),
          opts.noPerson ? null : el("span", { class: "ev-verb" }, verb),
          toolNode,
          e.type === "request" && e.model ? el("span", { class: "ev-model mono" }, e.model) : null,
          e.type === "request" ? agentBadges(e) : null,
          e.type === "request" && e.purpose ? purposeChip(purposeName(e.purpose), e.purpose_source, e.purpose_confidence) : null,
          e.credential ? el("span", { class: "u-badge bad" }, icon("key"), "Credential") : null),
        !opts.compact && (lead || detail.length) ? el("div", { class: "ev-sub" }, lead, detail) : null),
      el("div", { class: "ev-end" }, money ? el("span", { class: "ev-cost u-num" }, money) : null,
        e.type === "turn" ? SUI.status(e.ended ? "idle" : "ok", e.ended ? "Ended" : "Holding", { plain: true }) : outcomeStatus(e.type, e.outcome, true)),
      href ? el("a", { class: "ev-open", href, "aria-label": "Open the full record of request " + e.id }, icon("chevronRight")) : el("span", { class: "ev-open none" }));
  }

  /* A sign-in or an access change, from the audit log: who did it (the person themselves, or an admin) and to whom. */
  function accessItem(e, opts) {
    const negative = /refused|failed|suspended|revoked|turned a tool off|ended/.test(e.action);
    return el("li", { class: "ev t-access" + (opts.fresh ? " u-enter" : "") },
      el("time", { class: "ev-time", datetime: new Date(e.ts * 1000).toISOString(), title: fmt.stamp(e.ts) }, fmt.clock(e.ts)),
      el("div", { class: "ev-body" },
        el("div", { class: "ev-head" },
          el("span", { class: "ev-type", role: "img", "aria-label": EVENT_KIND.access[0], "data-tip": EVENT_KIND.access[0] }, icon("key")),
          e.self ? personLink(e.person_id, e.person) : el("span", { class: "obj" }, SUI.avatar(e.actor, "sm"), el("strong", null, e.actor)),
          el("span", { class: "ev-verb" }, e.action),
          !e.self && !opts.noPerson ? personLink(e.person_id, e.person, { avatar: false }) : null,
          e.target && e.target !== e.person ? el("span", { class: "faint" }, e.target) : null),
        e.detail || e.audit_reason || e.ip ? el("div", { class: "ev-sub" },
          e.audit_reason ? el("span", { class: "ev-prompt" }, "Reason: " + e.audit_reason) : e.detail ? el("span", { class: "faint" }, e.detail) : null,
          e.ip ? where(e.ip, e.place) : null) : null),
      el("div", { class: "ev-end" }, SUI.status(e.outcome === "denied" ? "blocked" : negative ? "waiting" : "info", e.outcome === "denied" ? "Refused" : e.self ? "By them" : "By an admin", { plain: true })),
      el("a", { class: "ev-open", href: "#/audit?q=" + encodeURIComponent(e.action), "aria-label": "Find in the audit log" }, icon("chevronRight")));
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
    ["Monitor", [["#/", "Overview", "overview"], ["#/live", "Live", "live"], ["#/attention", "Needs attention", "attention"], ["#/activity", "Activity", "activity"],
      ["#/health", "Health", "pulse"]], "What's happening"],
    ["Govern", [["#/people", "People", "people"], ["#/requests", "Access requests", "requests"], ["#/tools", "Tools", "tools"], ["#/models", "Models", "chip"],
      ["#/policies", "Policies", "rule"]], "Access and rules"],
    ["Money", [["#/licences", "Licences & spend", "licences"], ["#/reports", "Reports", "report"]], "Spend and licences"],
    ["Trust", [["#/security", "Security", "shield"], ["#/incidents", "Incidents", "flag"], ["#/devices", "Devices", "device"], ["#/audit", "Audit log", "audit"],
      ["#/settings", "Settings", "settings"]], "Risks, records, settings"],
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
    if (href === "#/incidents" && S.notes) {
      const n = S.notes.items.filter((x) => !x.resolved && x.key.startsWith("incident:")).length;
      if (n) return el("span", { class: "count bad", "aria-label": n + " serious incidents open" }, String(n));
    }
    return null;
  }

  // ------------------------------------------------------------------ notifications

  const NOTE_SEV = { critical: ["blocked", "Critical"], high: ["blocked", "High"], warning: ["waiting", "Warning"], notice: ["info", "Notice"], info: ["idle", "Info"] };
  async function refreshNotes() {
    try { S.notes = await api("GET", "/notifications"); } catch (e) { /* the bell just waits */ }
    document.querySelectorAll(".bell").forEach((b) => b.replaceWith(bell()));
    return S.notes;
  }
  function bell() {
    const n = S.notes ? S.notes.unread : 0;
    return el("button", { class: "bell theme-btn" + (n ? " on" : ""), type: "button", onclick: openNotes,
      "aria-label": n ? `Notifications, ${n} unread` : "Notifications", "data-tip": "Notifications" },
    icon("bell"), n ? el("span", { class: "bell-n u-num" }, n > 99 ? "99+" : String(n)) : null);
  }
  async function openNotes() {
    const { node, close } = sheet(null, "Notifications");
    const list = el("div", { class: "sheet-body" });
    let showAll = false;
    const build = async () => {
      const data = await api("GET", "/notifications" + (showAll ? "?all=1" : ""));
      if (!showAll) S.notes = data;
      return data.items.length ? el("ul", { class: "note-list" }, data.items.map((x) => {
        const [state, label] = NOTE_SEV[x.severity] || NOTE_SEV.info;
        return el("li", { class: "note sev-" + x.severity + (x.read || x.resolved ? " read" : "") },
          el("div", { class: "note-head" }, SUI.status(state, label, { plain: true }), el("span", { class: "u-label" }, x.area),
            el("span", { class: "grow" }), el("time", { class: "hint", title: fmt.stamp(x.first_seen) }, x.resolved ? "resolved " + fmt.ago(x.resolved) : "since " + fmt.ago(x.first_seen))),
          el("a", { class: "note-title", href: x.href || "#/attention", onclick: () => close() }, x.title),
          x.text ? el("p", { class: "note-text" }, x.text) : null);
      })) : SUI.stateBox({ tone: "ok", icon: "bell", title: "Nothing new", text: "Conditions that need someone appear here, and clear by themselves once they're dealt with." });
    };
    const reload = () => SUI.load(list, build, SUI.skeleton("rows", 4));
    const markAll = el("button", { class: "btn small", onclick: async () => { await api("POST", "/notifications/read", { all: true }); await refreshNotes(); reload(); } }, "Mark all read");
    const scope = el("button", { class: "btn small quiet", onclick: () => { showAll = !showAll; scope.textContent = showAll ? "Open only" : "Include resolved"; reload(); } }, "Include resolved");
    node.append(el("header", null, el("div", { class: "spread" },
      el("div", { class: "sheet-id" }, el("div", null, el("div", { class: "u-label" }, "Control room"), el("h2", null, "Notifications"))),
      el("button", { class: "btn small quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x"))),
    el("div", { class: "sheet-tools" }, scope, el("span", { class: "grow" }),
      S.notes && S.notes.email ? null : el("span", { class: "hint", "data-tip": "Set GATEWAY_SMTP_HOST and GATEWAY_NOTIFY_TO on the server to email high and critical ones.", tabindex: "0" }, "Email off"),
      markAll)), list);
    reload();
  }

  /* The four areas, each a group that can be folded away. Every group starts open; what someone folds is
     remembered in this browser, but the group holding the page you're on always shows. */
  const NAV_KEY = "swangz-gateway-nav-folded";
  function foldedGroups() {
    try { return new Set(JSON.parse(localStorage.getItem(NAV_KEY) || "[]")); } catch (e) { return new Set(); }
  }
  function sidebar(active, onNavigate) {
    const folded = foldedGroups();
    const nav = el("nav", { class: "nav", "aria-label": "Control room" }, NAV.map(([group, links, about]) => {
      const holdsActive = links.some(([href]) => href === active);
      const open = holdsActive || !folded.has(group);
      const listId = "nav-" + group.toLowerCase();
      const items = el("div", { class: "nav-links", id: listId, hidden: !open },
        links.map(([href, label, ic]) => el("a", { href, class: href === active ? "on" : null, "aria-current": href === active ? "page" : null, onclick: onNavigate || null },
          icon(ic), el("span", { class: "nl" }, label), navCounts(href))));
      const label = [el("span", { class: "gt-l" }, group), el("span", { class: "gt-about" }, about)];
      // the group holding the page you're on stays open, so its heading is a plain label
      const heading = holdsActive ? el("div", { class: "group-toggle static" }, label) : el("button", { class: "group-toggle", type: "button", "aria-expanded": open ? "true" : "false", "aria-controls": listId,
        onclick: () => {
          const opening = items.hidden;
          items.hidden = !opening;
          groupNode.classList.toggle("collapsed", !opening);
          heading.setAttribute("aria-expanded", opening ? "true" : "false");
          const set = foldedGroups();
          if (opening) set.delete(group); else set.add(group);
          try { localStorage.setItem(NAV_KEY, JSON.stringify([...set])); } catch (e) { /* the preference is optional */ }
        } },
      label, icon("chevronDown"));
      const groupNode = el("div", { class: "nav-group" + (open ? "" : " collapsed") + (holdsActive ? " here" : "") }, heading, items);
      return groupNode;
    }));
    const paused = S.overview && S.overview.paused;
    return el("aside", { class: "side" },
      el("a", { class: "brand", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }),
        el("div", null, el("span", { class: "bn" }, "Swangz ", el("b", null, "Gateway")), el("small", null, "Control room"))),
      el("div", { class: "side-tools" },
        el("button", { class: "side-search", type: "button", onclick: () => openCommand(), "aria-label": "Search or jump to a page" }, icon("search"), el("span", null, "Search…"),
          el("span", { class: "u-kbd" }, navigator.platform && /Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K")),
        bell()),
      nav,
      el("div", { class: "side-grow" }),
      can("emergency") ? el("div", { class: "estop" + (paused ? " on" : "") },
        paused ? [el("div", { class: "estop-t" }, SUI.status("blocked", "AI paused"), el("span", null, "for everyone")),
          el("button", { class: "btn small primary", onclick: () => setPaused(false) }, "Resume")]
          : [el("div", { class: "estop-t" }, el("span", { class: "u-label" }, "Emergency"), el("span", null, "Cut every request now")),
            el("button", { class: "btn small danger", onclick: () => setPaused(true) }, icon("stop"), "Stop all AI")]) : null,
      el("div", { class: "who" }, SUI.avatar(S.me.username),
        el("div", { class: "id" }, el("strong", null, S.me.username), el("span", null, roleLabel() + (isOwner() || (S.me.can || []).length ? "" : " · read-only"))),
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
      can("emergency") ? el("button", { class: "btn small primary", onclick: () => setPaused(false) }, "Resume access") : null) : null;
    const appbar = el("div", { class: "appbar" },
      el("button", { class: "btn quiet icon-only", type: "button", "aria-label": "Open navigation", onclick: () => openDrawer(active) }, icon("menu")),
      el("a", { class: "brand mini", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Gateway"),
      el("button", { class: "btn quiet icon-only", type: "button", "aria-label": "Search", onclick: () => openCommand() }, icon("search")), bell());
    // Where you are: the area, then the pages above this one — never the page's own title again.
    const place = NAV.map(([group, links]) => ({ group, item: links.find(([href]) => href === active) })).find((x) => x.item);
    const trail = [place ? el("span", { class: "crumb-area" }, place.group) : null, ...[].concat(o.crumbs || []).filter(Boolean)].filter(Boolean);
    const crumbs = trail.length ? el("nav", { class: "crumbs" + (o.crumbs ? "" : " area-only"), "aria-label": "You are here" },
      trail.map((c, i) => [c, i < trail.length - 1 ? el("span", { class: "sep", "aria-hidden": "true" }, "/") : null])) : null;
    const top = el("header", { class: "top" }, crumbs,
      el("div", { class: "title-row" }, o.lead || null, el("h1", null, o.title), o.status || null),
      o.actions ? el("div", { class: "top-actions" }, o.actions) : null,
      o.lede ? el("p", { class: "lede" }, o.lede) : null);
    const routeSlug = (section === "#/" ? "overview" : section.slice(2)).replace(/[^a-z0-9-]/gi, "-");
    app.replaceChildren(el("div", { class: "shell route-" + routeSlug }, side,
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
      go("Go to", "Why was this allowed or refused?", "#/policies?tab=explain", "rule", "explain trace decision"),
      go("Go to", "What would a policy change?", "#/policies?tab=simulate", "rule", "simulate what-if dry run"),
      go("Go to", "Notifications", "#/attention", "bell", "alerts"),
      can("govern") ? go("Actions", "Add a person", "#/people?add=1", "plus", "new staff user") : null,
      can("govern") ? go("Actions", "Add a tool", "#/tools?add=1", "plus", "new catalog") : null,
      can("govern") ? go("Actions", "Grant or revoke tool access", "#/tools", "tools", "assign entitlement") : null,
      can("govern") ? go("Actions", "Add a policy", "#/policies?add=1", "plus", "rule deny hours cap") : null,
      can("trust") ? go("Actions", "Open an incident", "#/incidents?add=1", "flag", "case investigate") : null,
      { group: "Actions", title: "Switch theme", icon: "sun", keywords: "dark light porcelain obsidian", run: () => { SUI.applyTheme(SUI.theme() === "dark" ? "light" : "dark", true); render(); } },
      can("emergency") && !(S.overview && S.overview.paused) ? { group: "Actions", title: "Stop all AI", sub: "Cuts every request — asks first", icon: "stop", keywords: "pause kill switch emergency", run: () => setPaused(true) } : null,
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
    TABSETS = [];
    setDirty(null);
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
    purposeIndex();
    render().then(() => Promise.all([refreshAttention(), refreshNotes()]).then(() => { const n = document.querySelector(".side"); if (n && S.me) n.replaceWith(sidebar(n.querySelector("a.on")?.getAttribute("href") || "#/")); }));
  }

  /* Moving between tabs of the page that is already showing (Back, Forward, or a link that only changes the
     tab) switches the view in place. Anything else builds the page again. */
  function switchInPlace(from, to) {
    const [fp, fq] = (from || "#/").split("?");
    const [tp, tq] = (to || "#/").split("?");
    if (fp !== tp) return false;
    const a = new URLSearchParams(fq || ""), b = new URLSearchParams(tq || "");
    const changed = new Set([...a.keys(), ...b.keys()].filter((k) => a.get(k) !== b.get(k)));
    if (!changed.size) return true;
    for (const k of changed) {
      const sets = TABSETS.filter((t) => t.param === k);
      // a value no tab set knows (an old link, say) goes to the page itself, which may know what it meant
      if (sets.length) { if (b.get(k) && !sets.some((t) => t.valid(b.get(k)))) return false; continue; }
      if (!TABSETS.some((t) => t.clears.includes(k))) return false;
    }
    // in registration order, so an outer set switches first and a nested set it brings back is then in place
    for (const set of TABSETS.slice()) {
      if (!set.bar.isConnected) continue;
      const want = set.valid(b.get(set.param)) ? b.get(set.param) : set.first;
      if (want !== set.current) set.show(want, "history");
    }
    return true;
  }
  window.addEventListener("hashchange", async () => {
    const to = location.hash;
    if (isDirty()) {
      // put the address back while we ask; go on only if they choose to drop their changes
      const from = S.route || "#/";
      history.replaceState(null, "", from);
      if (!(await confirmLeave())) return;
      location.hash = to;
      return;
    }
    if (S.me && document.querySelector(".shell") && switchInPlace(S.route, to)) { S.route = to; return; }
    render();
  });
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
  setInterval(() => { if (S.me && document.visibilityState === "visible") { refreshAttention(); refreshNotes(); } }, 60000);

  window.SWA = {
    S, api, ApiError, gadmin, gurl, GATEWAY, isOwner, can, roleLabel, every, clearTimers, panel, empty, kpi, pageTabs, settingRow, switchInput, panelFoot, dialog, confirmAction, sheet, bar,
    purposeChip, purposeIndex, purposeName, PURPOSE_SOURCE, refreshNotes, NOTE_SEV,
    toolIndex, toolFor, toolLogo, toolLink, personLink, deviceLink, where, actionsList, ACTION, outcomeStatus, flagBadges, agentBadges,
    totalTokens, units, reqEvent, eventItem, eventDays, launchList, rangeFrom, rangeQuery, keepParams, frame, render, page, setDirty, confirmLeave, isDirty,
    setPaused, refreshOverview, refreshAttention, openCommand,
  };

  document.addEventListener("DOMContentLoaded", () => {
    api("GET", "/me").then((me) => { S.me = me; start(); }).catch(() => { /* the sign-in page is showing */ });
  });
})();
