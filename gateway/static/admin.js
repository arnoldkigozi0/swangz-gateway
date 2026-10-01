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

  async function api(method, path, body) {
    const opts = { method, credentials: "same-origin", headers: { "x-gateway-admin": "1" } };
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch("/admin/api" + path, opts);
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

  const KIND_LABEL = { command: "ran", edit: "edit", read: "read", web: "web", agent: "agent", other: "tool" };

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
          !r.actions.length && r.reply ? el("div", { class: "reply" }, r.reply) : null,
          failed && r.reason ? el("div", { class: "err" }, r.reason) : null),
        el("div", { class: "side-meta" },
          refused(r) ? el("span", { class: "faint" }, "—") : el("span", null, fmt.money(r.cost)),
          refused(r) ? null : el("span", { class: "faint" }, fmt.tokens(totalTokens(r)) + " tok"),
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

  // ------------------------------------------------------------------ sign-in and frame

  function showSignIn() {
    clearTimers();
    const err = el("div", { class: "err", role: "alert" });
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
    el("div", { class: "row" }, el("img", { src: "/static/icon.svg", alt: "", width: 34, height: 34 }),
      el("div", null, el("div", { class: "eyebrow" }, "Admin"), el("h1", null, "Swangz AI control room"))),
    el("p", { class: "muted", style: null }, "Who is using AI, with which tool, for what — and the switches to stop it."),
    el("label", { class: "field" }, "Username", user),
    el("label", { class: "field" }, "Password", pass),
    err, go);
    app.replaceChildren(el("div", { class: "signin" }, form));
    user.focus();
  }

  const NAV = [
    ["#/", "Live"], ["#/people", "People"], ["#/activity", "Activity"], ["#/settings", "Settings"], ["#/audit", "Audit log"],
  ];

  function frame(title, crumbs, content, actions) {
    const live = S.overview ? S.overview.live.length : 0;
    const paused = S.overview && S.overview.paused;
    const here = (location.hash || "#/").split("?")[0];
    const section = here === "#/" ? "#/" : "#/" + here.split("/")[1];
    const sectionFor = { "#/records": "#/activity", "#/sessions": "#/people" };
    const active = sectionFor[section] || section;
    const nav = el("nav", { class: "nav", "aria-label": "Sections" },
      NAV.map(([href, label]) => el("a", { href, class: href === active ? "on" : null },
        el("span", null, label),
        href === "#/" && live ? el("span", { class: "pill ok" }, el("span", { class: "dot pulse" }), String(live)) : null)));
    const side = el("aside", { class: "side" },
      el("div", { class: "brand" }, el("img", { src: "/static/icon.svg", alt: "" }), el("div", null, "Swangz ", el("b", null, "AI"), el("small", null, "Control room"))),
      nav, el("div", { class: "grow" }),
      el("div", { class: "who" }, el("span", null, S.me.username, el("span", { class: "faint" }, " · " + S.me.role)),
        el("button", { class: "btn small", onclick: signOut }, "Sign out")));
    const stopAll = isOwner() && !paused
      ? el("button", { class: "btn danger", onclick: () => setPaused(true) }, "Stop all AI") : null;
    const banner = paused ? el("div", { class: "banner", role: "alert" },
      el("span", null, "AI access is paused for everyone. Requests are being refused."),
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
    [/^#\/sessions\/(.+)$/, pageSession],
    [/^#\/records\/(\d+)$/, pageRecord],
    [/^#\/activity$/, pageActivity],
    [/^#\/settings$/, pageSettings],
    [/^#\/audit$/, pageAudit],
  ];

  async function render() {
    clearTimers();
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
    app.replaceChildren(frame("Live", null, [
      kpis,
      el("div", { class: "grid cols-2" },
        el("div", { class: "grid" },
          panel("Working right now", "streams in flight", liveBody),
          panel("Activity", el("a", { href: "#/activity", class: "btn small" }, "Search everything"), feed)),
        el("div", { class: "grid" },
          panel("Today by person", "spend", people),
          panel("This month by model", null, models),
          panel("This month by tool", null, tools))),
    ]));

    let maxId = 0;

    function drawOverview(ov) {
      const t = ov.today, m = ov.month;
      kpis.replaceChildren(
        kpi("Spent today", fmt.money(t.cost), `${fmt.money(m.cost)} this month`),
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

    async function tick() {
      const ov = await refreshOverview();
      if (ov) drawOverview(ov);
      await loadFeed();
    }

    drawOverview(S.overview);
    await loadFeed();
    every(2500, tick);
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
      el("td", null, el("a", { href: "#/people/" + p.id }, el("strong", null, p.name)), el("div", { class: "hint" }, [p.title, p.department].filter(Boolean).join(" · ") || "—")),
      el("td", null, p.status === "active" ? el("span", { class: "pill ok" }, "active") : el("span", { class: "pill bad" }, "suspended"),
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
      notes: el("textarea", null, p.notes || ""),
    };
    const node = el("div", { class: "stack" },
      el("div", { class: "form-grid" },
        el("label", { class: "field" }, "Name", f.name),
        el("label", { class: "field" }, "Role / title", f.title),
        el("label", { class: "field" }, "Department", f.department),
        el("label", { class: "field" }, "Email — they sign in with it", f.email)),
      el("div", { class: "form-grid" },
        el("label", { class: "field" }, "Daily budget (USD)", f.daily_budget),
        el("label", { class: "field" }, "Monthly budget (USD)", f.monthly_budget)),
      el("label", { class: "field" }, "Allowed models", f.allowed_models,
        el("span", { class: "hint" }, "Comma-separated, * works as a wildcard: claude-sonnet-*, gpt-6-*. Empty = any model. Through a gateway, Claude Code runs its background tasks on the main model, so allowing that model is enough.")),
      el("label", { class: "field" }, "Notes", f.notes));
    const values = () => Object.fromEntries(Object.entries(f).map(([k, input]) => [k, input.value]));
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
    const statusPill = p.status === "active" ? el("span", { class: "pill ok" }, "active") : el("span", { class: "pill bad" }, "suspended");
    const toggle = owner ? (p.status === "active"
      ? el("button", { class: "btn danger", onclick: () => suspend(true) }, "Suspend access")
      : el("button", { class: "btn primary", onclick: () => suspend(false) }, "Restore access")) : null;

    async function suspend(on) {
      if (on) {
        const ok = await confirmAction(`Suspend ${p.name}?`, "Every key they hold stops working now, and anything they have streaming is cut. You can restore access later.", "Suspend", true);
        if (!ok) return;
      }
      try {
        const out = await api("POST", `/people/${p.id}/${on ? "suspend" : "resume"}`);
        toast(on ? `Suspended. ${out.cut} request(s) cut.` : "Access restored.");
        render();
      } catch (e) { toast(e.message, true); }
    }

    const kpis = el("div", { class: "kpis" },
      el("div", { class: "kpi" }, el("div", { class: "label" }, "Spent today"), el("div", { class: "value" }, fmt.money(p.today.cost)),
        el("div", { class: "note" }, p.daily_budget !== null ? `of ${fmt.money(p.daily_budget)} daily budget` : "no daily limit"), p.daily_budget !== null ? bar(p.today.cost, p.daily_budget) : null),
      el("div", { class: "kpi" }, el("div", { class: "label" }, "Spent this month"), el("div", { class: "value" }, fmt.money(p.month.cost)),
        el("div", { class: "note" }, p.monthly_budget !== null ? `of ${fmt.money(p.monthly_budget)} monthly budget` : "no monthly limit"), p.monthly_budget !== null ? bar(p.month.cost, p.monthly_budget) : null),
      el("div", { class: "kpi" }, el("div", { class: "label" }, "Active keys"), el("div", { class: "value" }, String(p.keys.filter((k) => !k.revoked).length)), el("div", { class: "note" }, `${p.keys.length} issued in total`)),
      el("div", { class: "kpi" }, el("div", { class: "label" }, "Models allowed"), el("div", { class: "value", style: null }, p.allowed_models ? "limited" : "any"), el("div", { class: "note" }, p.allowed_models || "no restriction")));

    // keys
    const keyRows = p.keys.length ? el("ul", { class: "keys" }, p.keys.map((k) => el("li", { class: k.revoked ? "revoked" : null },
      el("div", null,
        el("strong", null, k.label),
        el("div", { class: "hint mono" }, k.hint),
        el("div", { class: "hint" }, (k.created_by === "self" ? `added by them in the app ${fmt.ago(k.created)}` : `issued ${fmt.ago(k.created)}` + (k.created_by ? ` by ${k.created_by}` : "")) + ` · last used ${fmt.ago(k.last_used)}`),
        k.revoked ? el("div", { class: "hint" }, `revoked ${fmt.ago(k.revoked)}` + (k.revoked_by === "self" ? " by them in the app" : k.revoked_by ? ` by ${k.revoked_by}` : "")) : null),
      k.revoked ? el("span", { class: "pill bad" }, "revoked")
        : owner ? el("button", { class: "btn danger small", onclick: () => revoke(k) }, "Revoke") : el("span", { class: "pill ok" }, "active")))) : empty("No keys yet.");

    async function revoke(k) {
      const ok = await confirmAction(`Revoke “${k.label}”?`, `${k.hint} stops working immediately, including anything it is streaming right now. This can't be undone — issue a new key instead.`, "Revoke key", true);
      if (!ok) return;
      try {
        const out = await api("POST", `/keys/${k.id}/revoke`);
        toast(`Revoked. ${out.cut} request(s) cut.`);
        render();
      } catch (e) { toast(e.message, true); }
    }

    // sessions
    const sessions = p.sessions.length ? el("ul", { class: "feed" }, p.sessions.map((s) => el("li", null,
      el("a", { class: "item", href: "#/sessions/" + encodeURIComponent(s.session) },
        el("div", { class: "when", title: fmt.stamp(s.started) }, fmt.when(s.last)),
        el("div", { class: "what" }, el("div", { class: "line1" }, toolPill(s.client), el("span", { class: "model" }, plural(s.requests, "request"))),
          s.first_prompt ? el("div", { class: "prompt" }, s.first_prompt) : el("div", { class: "reply" }, "(no typed prompt recorded)")),
        el("div", { class: "side-meta" }, fmt.money(s.cost)))))) : empty("No sessions yet.");

    const recent = el("ul", { class: "feed" });
    const data = await api("GET", `/requests?person=${p.id}&limit=25`);
    recent.replaceChildren(...(data.items.length ? data.items.map((r) => feedItem(r, { noPerson: true })) : [el("li", null, empty("Nothing yet."))]));

    let controls = null;
    if (owner) {
      const form = personForm(p);
      const err = el("div", { class: "err" });
      controls = panel("Details and limits", null, el("div", { class: "body stack" }, form.node, err,
        el("div", null, el("button", { class: "btn primary", onclick: async () => {
          try { await api("PATCH", "/people/" + p.id, form.values()); toast("Saved."); render(); } catch (e) { err.textContent = e.message; }
        } }, "Save changes"))));
    }

    const live = p.live.length ? panel("Working right now", null, el("div", { class: "live-list" }, p.live.map((t) => el("div", { class: "live-card" },
      el("div", null, el("div", { class: "row" }, el("span", { class: "dot pulse" }), toolPill(t.client), el("span", { class: "faint mono" }, t.model || "")),
        t.prompt ? el("div", { class: "p" }, "“" + t.prompt + "”") : null, el("div", { class: "hint" }, fmt.elapsed(t.started))))))) : null;

    const signInState = { active: "Signs in to the Swangz AI app" + (p.last_login ? ` · last signed in ${fmt.ago(p.last_login)}` : ""),
      invited: `Sign-in link sent — valid until ${fmt.stamp(p.invite_expires)}`, none: "No app sign-in yet" }[p.sign_in];
    const signIn = panel("Swangz AI app", null, el("div", { class: "body stack" },
      el("div", null, signInPill(p.sign_in), " ", el("span", { class: "muted" }, signInState)),
      el("div", { class: "hint" }, p.email ? `They sign in at ${S.me.base_url}/ with ${p.email}. There they connect their own devices and see their allowance — nothing about monitoring.`
        : "Add their email under Details first — it is what they sign in with."),
      owner && p.email ? el("div", null, el("button", { class: "btn", onclick: () => inviteLink(p) }, p.sign_in === "active" ? "New sign-in link (reset password)" : "Create sign-in link")) : null));
    const issue = owner && p.status === "active" ? el("button", { class: "btn primary", onclick: () => issueKey(p) }, "Issue a key") : null;
    app.replaceChildren(frame(p.name, el("a", { href: "#/people" }, "People"), [
      el("div", { class: "row", style: null }, statusPill, el("span", { class: "muted" }, [p.title, p.department, p.email].filter(Boolean).join(" · "))),
      el("div", { style: null, class: "spacer" }),
      kpis,
      el("div", { class: "grid cols-2" },
        el("div", { class: "grid" }, live,
          panel("Sessions", "one conversation each — open one to see everything that happened", sessions),
          panel("Recent activity", el("a", { class: "btn small", href: `#/activity?person=${p.id}` }, "All activity"), recent)),
        el("div", { class: "grid" },
          panel("Keys", "one per device or tool", keyRows),
          signIn,
          controls,
          p.notes && !owner ? panel("Notes", null, el("div", { class: "body" }, longText(p.notes))) : null)),
    ], [el("a", { class: "btn", href: `/admin/api/export.csv?person=${p.id}` }, "Export CSV"), issue, toggle]));
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
      metaCell("Tokens", tokens),
      metaCell("Cost", fmt.money(r.cost)),
      metaCell("Outcome", el("span", null, r.outcome === "ok" ? el("span", { class: "pill ok" }, "ok") : outcomePill(r), " ", r.reason || "", r.status ? el("span", { class: "faint" }, ` HTTP ${r.status}`) : null)),
      metaCell("Session", r.session ? el("a", { class: "mono", href: "#/sessions/" + encodeURIComponent(r.session) }, r.session.slice(0, 18) + (r.session.length > 18 ? "…" : "")) : "—"),
      metaCell("From", el("span", { class: "mono" }, r.client_ip || "—")),
      metaCell("Endpoint", el("span", { class: "mono" }, `${r.provider} ${r.method} ${r.path}`)));

    const summary = panel("In short", flagPills(r.flags), el("div", { class: "body stack" },
      r.prompt ? el("div", null, el("div", { class: "tag" }, "They typed"), el("div", { class: "bubble" }, r.prompt)) : el("div", { class: "hint" }, "Nothing typed in this request — the tool was sending results back to the model on its own."),
      r.actions.length ? el("div", null, el("div", { class: "tag" }, "The model did"), actionsList(r.actions)) : null,
      r.reply ? el("div", null, el("div", { class: "tag" }, "The model said"), longText(r.reply)) : null));

    const download = el("a", { class: "btn", href: `/admin/api/requests/${r.id}?download=1` }, "Download JSON");
    app.replaceChildren(frame(`Record #${r.id}`, el("span", null, el("a", { href: "#/activity" }, "Activity"), r.person_id ? [" · ", el("a", { href: "#/people/" + r.person_id }, r.person)] : null), [
      meta, el("div", { class: "spacer" }), summary, el("div", { class: "spacer" }),
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
    const peopleData = await api("GET", "/people");
    const state = {
      q: params.get("q") || "", person: params.get("person") || "", client: params.get("client") || "",
      outcome: params.get("outcome") || "", only: params.get("only") || "", flag: params.get("flag") || "", all: params.get("all") || "",
    };
    const q = el("input", { type: "search", placeholder: "Search prompts, commands, replies…", value: state.q });
    const person = el("select", null, el("option", { value: "" }, "Everyone"), peopleData.items.map((p) => el("option", { value: String(p.id) }, p.name)));
    person.value = state.person;
    const tool = el("select", null, ["", "Claude Code", "Codex", "Cursor", "OpenAI SDK", "Anthropic SDK", "curl", "unknown"].map((c) => el("option", { value: c }, c || "Any tool")));
    tool.value = state.client;
    const outcome = el("select", null, [["", "Any outcome"], ["ok", "Went through"], ["blocked", "Blocked"], ["denied", "Wrong key"], ["cut", "Cut off"], ["aborted", "Closed by the tool"], ["error", "Errors"]].map(([v, t]) => el("option", { value: v }, t)));
    outcome.value = state.outcome;
    const show = el("select", null, [["", "All requests"], ["prompts", "Only typed prompts"], ["secret", "Credentials flagged"], ["all", "Include token counts & other calls"]].map(([v, t]) => el("option", { value: v }, t)));
    show.value = state.only === "prompts" ? "prompts" : state.flag === "secret" ? "secret" : state.all ? "all" : "";
    const list = el("ul", { class: "feed" });
    const more = el("button", { class: "btn", onclick: () => load(false) }, "Load older");
    const exportLink = el("a", { class: "btn", href: "/admin/api/export.csv" }, "Export CSV");
    let minId = null;

    function query() {
      const p = new URLSearchParams();
      if (q.value.trim()) p.set("q", q.value.trim());
      if (person.value) p.set("person", person.value);
      if (tool.value) p.set("client", tool.value);
      if (outcome.value) p.set("outcome", outcome.value);
      if (show.value === "prompts") p.set("only", "prompts");
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
      exportLink.href = "/admin/api/export.csv" + (person.value ? "?person=" + person.value : "");
    }

    let timer = null;
    const apply = () => {
      minId = null;
      history.replaceState(null, "", "#/activity" + (query().toString() ? "?" + query().toString() : ""));
      load(true).catch((e) => toast(e.message, true));
    };
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(apply, 300); });
    [person, tool, outcome, show].forEach((s) => s.addEventListener("change", apply));

    app.replaceChildren(frame("Activity", null, panel("Every request through the gateway", null,
      el("div", { class: "filters" },
        el("label", { class: "field" }, "Search", q),
        el("label", { class: "field" }, "Person", person),
        el("label", { class: "field" }, "Tool", tool),
        el("label", { class: "field" }, "Outcome", outcome),
        el("label", { class: "field" }, "Show", show),
        el("div", null)),
      list, el("div", { class: "body" }, more)), exportLink));
    await load(true);
  }

  // ------------------------------------------------------------------ Settings

  async function pageSettings() {
    const [st, prices] = await Promise.all([api("GET", "/settings"), api("GET", "/prices")]);
    const owner = isOwner();
    const admins = owner ? await api("GET", "/admins") : null;

    const switchPanel = panel("Kill switch", null, el("div", { class: "body spread" },
      el("div", null, el("strong", null, st.paused ? "AI access is paused for everyone." : "AI access is on."),
        el("div", { class: "hint" }, "Stopping cuts every request in flight and refuses new ones until someone resumes.")),
      owner ? (st.paused ? el("button", { class: "btn primary", onclick: () => setPaused(false) }, "Resume access")
        : el("button", { class: "btn danger", onclick: () => setPaused(true) }, "Stop all AI")) : null));

    const providerRows = st.providers.map((p) => el("tr", null,
      el("td", null, el("strong", null, p.name), el("div", { class: "hint" }, p.dialect + " dialect")),
      el("td", { class: "mono" }, `${st.base_url}/${p.name}` + (p.dialect === "openai" ? "/v1" : "")),
      el("td", { class: "mono muted" }, p.upstream),
      el("td", null, p.configured ? el("span", { class: "pill ok" }, "key set") : el("span", { class: "pill bad", title: "Set the provider's API key in the server environment and restart." }, "no key"))));
    const connections = panel("Addresses and providers", "staff tools point at these", el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Provider"), el("th", null, "Address for staff tools"), el("th", null, "Forwards to"), el("th", null, "API key"))),
      el("tbody", null, providerRows))),
    el("div", { class: "body stack" },
      el("div", null, el("span", { class: "tag" }, "Staff app  "), el("span", { class: "mono" }, st.base_url + "/"), el("span", { class: "hint" }, "  — where staff sign in and connect their tools")),
      el("div", null, el("span", { class: "tag" }, "Admin console  "), el("span", { class: "mono" }, st.base_url + "/admin"), el("span", { class: "hint" }, "  — this console; don't share it with staff"))),
    el("div", { class: "body hint" }, "Provider API keys live only in the server's environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, …). They are never shown here and never leave the server."));

    const retention = el("input", { type: "number", min: "0", step: "1", value: String(st.retention_days), disabled: !owner });
    const storeBodies = el("input", { type: "checkbox", checked: st.store_bodies, disabled: !owner });
    const blockSecrets = el("input", { type: "checkbox", checked: st.block_secrets, disabled: !owner });
    const selfKeys = el("input", { type: "checkbox", checked: st.staff_self_keys, disabled: !owner });
    const recErr = el("div", { class: "err" });
    const records = panel("Records", `${st.records.toLocaleString()} requests · ${(st.db_bytes / 1048576).toFixed(1)} MB on disk`, el("div", { class: "body stack" },
      el("label", { class: "field", style: null }, "Keep records for (days)", retention, el("span", { class: "hint" }, "Older records and their bodies are deleted automatically every hour. 0 keeps everything.")),
      el("label", { class: "check" }, storeBodies, el("span", null, el("strong", null, "Keep full request and response bodies"), el("div", { class: "hint" }, "Needed to pull back exactly what was sent. Off = only the summary (who, model, prompt, commands, cost)."))),
      el("label", { class: "check" }, selfKeys, el("span", null, el("strong", null, "Staff can connect their own devices"), el("div", { class: "hint" }, "In the Swangz AI app they create and disconnect their own keys. Every key still shows up here, and you can revoke any of them."))),
      el("label", { class: "check" }, blockSecrets, el("span", null, el("strong", null, "Refuse requests that contain credentials"), el("div", { class: "hint" }, "API keys, cloud keys, private keys. Off = let them through but flag them. On can interrupt an agent that reads a .env file."))),
      recErr,
      owner ? el("div", null, el("button", { class: "btn primary", onclick: async () => {
        try {
          await api("PUT", "/settings", { retention_days: retention.value, store_bodies: storeBodies.checked, block_secrets: blockSecrets.checked, staff_self_keys: selfKeys.checked });
          toast("Saved.");
        } catch (e) { recErr.textContent = e.message; }
      } }, "Save")) : null));

    const priceRows = prices.items.map((x) => el("tr", null,
      el("td", { class: "mono" }, x.model), el("td", { class: "num" }, usd(x.input)), el("td", { class: "num" }, usd(x.output)),
      el("td", { class: "num" }, x.cache_write === null ? "—" : usd(x.cache_write)), el("td", { class: "num" }, x.cache_read === null ? "—" : usd(x.cache_read)),
      el("td", { class: "num" }, owner ? el("button", { class: "btn small", onclick: () => editPrice(x) }, "Edit") : null)));
    const unpriced = prices.unpriced_models.length ? el("div", { class: "body" }, el("div", { class: "err" }, "Used but not priced (their cost shows as “unpriced”):"),
      el("div", { class: "row", style: null }, prices.unpriced_models.map((m) => owner ? el("button", { class: "btn small", onclick: () => editPrice({ model: m }) }, "Price " + m) : el("span", { class: "pill warn" }, m)))) : null;
    const pricePanel = panel("Model prices", "US dollars per million tokens", unpriced, el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Model"), el("th", { class: "num" }, "Input"), el("th", { class: "num" }, "Output"), el("th", { class: "num" }, "Cache write"), el("th", { class: "num" }, "Cache read"), el("th", null, ""))),
      el("tbody", null, priceRows))),
    owner ? el("div", { class: "body" }, el("button", { class: "btn", onclick: () => editPrice({}) }, "Add a model price")) : null);

    let adminPanel = null;
    if (admins) {
      adminPanel = panel("Console users", "owners change things; viewers only look", el("div", { class: "table-wrap" }, el("table", null,
        el("tbody", null, admins.items.map((a) => el("tr", null,
          el("td", null, el("strong", null, a.username)), el("td", null, el("span", { class: "pill" }, a.role)),
          el("td", { class: "muted" }, "last sign-in " + fmt.ago(a.last_login)),
          el("td", { class: "num" }, a.username === S.me.username ? el("span", { class: "faint" }, "you") : el("button", { class: "btn danger small", onclick: () => removeAdmin(a) }, "Remove"))))))),
      el("div", { class: "body" }, el("button", { class: "btn", onclick: addAdmin }, "Add a console user")));
    }

    const cur = el("input", { type: "password", autocomplete: "current-password" });
    const nw = el("input", { type: "password", autocomplete: "new-password" });
    const pwErr = el("div", { class: "err" });
    const pwPanel = panel("Your password", null, el("div", { class: "body stack" },
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Current password", cur), el("label", { class: "field" }, "New password (10+ characters)", nw)), pwErr,
      el("div", null, el("button", { class: "btn", onclick: async () => {
        try { await api("POST", "/password", { current: cur.value, new: nw.value }); toast("Password changed."); cur.value = nw.value = ""; pwErr.textContent = ""; } catch (e) { pwErr.textContent = e.message; }
      } }, "Change password"))));

    app.replaceChildren(frame("Settings", null, el("div", { class: "grid" },
      el("div", { class: "grid cols-even" }, switchPanel, records), connections, pricePanel,
      el("div", { class: "grid cols-even" }, adminPanel, pwPanel))));
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
      el("label", { class: "field" }, "Username", user), el("label", { class: "field" }, "Password (10+ characters)", pw), el("label", { class: "field" }, "Role", role), err), [save]);
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
