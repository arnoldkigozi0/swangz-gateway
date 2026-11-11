"use strict";
/* The control room's monitoring pages: Overview, Needs attention, Live, Activity, Security and the
   Audit log. Each answers one question: what matters now, what is happening, what did staff do,
   what looks wrong, and what did the people watching do. */
(() => {
  const { el, icon, fmt, toast } = SUI;
  const A = SWA;
  const { S, api } = A;

  const SEV = { high: ["high", "High"], medium: ["medium", "Medium"], low: ["low", "Low"], info: ["info", "Info"] };

  function attentionItem(i) {
    const [state, label] = SEV[i.severity] || SEV.info;
    return el("li", { class: "att sev-" + i.severity },
      el("div", { class: "att-sev" }, SUI.status(state, label)),
      el("div", { class: "att-body" },
        el("div", { class: "att-title" }, el("span", { class: "u-badge outline" }, i.area), el("strong", null, i.title)),
        el("p", null, i.text)),
      i.href ? el("a", { class: "btn small", href: i.href }, "Open", icon("chevronRight")) : null);
  }

  // ------------------------------------------------------------------ Overview

  /* The overview leads with one summary strip; the detail sits in tabs, one question each:
     what's happening now, how use and spend are moving, who and what lead, where licences leak. */
  /* BRIEF 10.9(2): a count of 0 says "0" with one line on why. Each line states only what the numbers on the card
     show; a value that is not zero returns null and the card keeps its usual note. */
  function zeroReason(card, n) {
    if (card === "spend") return n.cost ? null : n.requests ? "Requests ran, none carried a cost" : "No metered requests in 30 days";
    if (card === "requests") return n.requests ? null : n.before ? "No requests in 30 days · " + n.before.toLocaleString() + " in the 30 before" : "No requests in 30 days";
    if (card === "people") return n.today ? null : n.month ? "Nobody has used AI today · " + n.month.toLocaleString() + " in 30 days" : "Nobody has used AI in 30 days";
    if (card === "security") return n.events ? null : "No warnings in 7 days";
    if (card === "attention") return n.items ? null : "Nothing is flagged right now";
    if (card === "live") return n.live ? null : "No requests in flight";
    return null;
  }

  async function pageOverview(params) {
    await A.toolIndex().catch(() => null);
    const [trends, attention, security, lic, requests, staff] = await Promise.allSettled([
      api("GET", "/trends?days=30"), A.refreshAttention(), api("GET", "/security?days=7"), api("GET", "/licences"),
      api("GET", "/access-requests?state=open"), api("GET", "/people")]);
    const ov = S.overview;
    const tr = trends.status === "fulfilled" ? trends.value : null;
    const sec = security.status === "fulfilled" ? security.value : null;
    const att = attention.status === "fulfilled" && attention.value ? attention.value.items : null;
    const licence = lic.status === "fulfilled" ? lic.value : null;

    let kpis;
    if (tr) {
      const days = tr.days;
      const today = days[days.length - 1];
      const change = tr.previous.cost ? (tr.current.cost - tr.previous.cost) / tr.previous.cost : null;
      const secCount = sec ? sec.events.filter((e) => e.severity !== "info").length : null;
      const subs = licence ? licence.summary.subscriptions_month : 0;
      const reqChange = tr.previous.requests ? (tr.current.requests - tr.previous.requests) / tr.previous.requests : null;
      const spendWhy = zeroReason("spend", { cost: tr.current.cost, requests: tr.current.requests });
      const reqWhy = zeroReason("requests", { requests: tr.current.requests, before: tr.previous.requests });
      /* BRIEF 10.3 / 10.7: four separate cards, the first in accent glass. Each opens the page that holds its detail. */
      kpis = el("div", { class: "kpis four kpis-exact" }, [
        A.kpi({ label: "AI spend · 30 days", value: fmt.money(tr.current.cost), tone: "gold",
          tip: "Metered use through the gateway, priced from the model price table when each request ran. Company plans are a fixed monthly cost on top." + (subs ? ` Plans: ${fmt.moneyShort(subs)}/month.` : ""),
          foot: spendWhy ? null : SUI.delta(change),
          note: spendWhy || "vs the 30 days before",
          href: "#/licences?tab=spend&range=30d" }),
        A.kpi({ label: "AI requests · 30 days", value: fmt.num(tr.current.requests),
          foot: reqWhy ? null : SUI.delta(reqChange, { upIsGood: true }), note: reqWhy || "vs the 30 days before", href: "#/activity?tab=ai&range=30d" }),
        A.kpi({ label: "Active people · today", value: String(today.people), note: zeroReason("people", { today: today.people, month: tr.current.people }) || `${tr.current.people} in 30 days`,
          tip: "People who made an AI request, opened a tool from the portal, or visited an approved AI website.", href: "#/activity?tab=usage&range=today&by=person" }),
        A.kpi({ label: "Security events · 7 days", value: secCount === null ? "—" : String(secCount),
          tone: sec && sec.posture !== "healthy" ? "alert" : null,
          foot: sec ? SUI.status(sec.posture, { healthy: "Healthy", watch: "Worth a look", elevated: "Elevated" }[sec.posture], { plain: true }) : null,
          note: sec ? zeroReason("security", { events: secCount }) || "warnings and above" : "couldn't load", href: "#/security?view=signals&days=7&severity=warnings" }),
      ].map((card) => { card.append(el("span", { class: "kpi-go", "aria-hidden": "true" }, icon("arrowUp"))); return card; }));
    } else kpis = SUI.errorBox(trends.reason, () => A.render(), "The summary couldn't load");

    /* BRIEF 10.10.1, an L1: four number cards, the one chart and two counts, seven blocks in all. Uses by tool lives
       on Activity > Who used what (grouped by tool); trends, leaders and licences live on their own pages. */
    const week = tr ? tr.days.slice(-8) : [];
    const usage = A.panel("AI usage", el("a", { class: "btn small quiet", href: "#/activity?tab=usage&range=30d" }, "Who used what", icon("chevronRight")),
      tr ? el("div", { class: "body" }, SUI.columns({ label: "Uses per day over the last 8 days", showZero: true, yName: "Uses", height: window.matchMedia("(min-width: 1001px)").matches ? 350 : 250, caption: "Requests, tool opens and website visits · times in " + SUI.tzLabel(true),
        data: week.map((d) => ({ label: fmt.weekday(d.start), short: fmt.dayMonth(d.start), value: d.requests + d.opens + d.visits,
          note: `${fmt.num(d.requests)} requests · ${fmt.num(d.opens)} opens · ${fmt.num(d.visits)} visits` })) }))
        : SUI.errorBox(trends.reason, () => A.render()));

    const urgent = att ? att.filter((i) => i.severity === "high" || i.severity === "medium").length : 0;
    const counts = el("div", { class: "kpis kpis-exact two" });
    function drawCounts() {
      const live = (S.overview || ov).live;
      const streaming = live.filter((t) => t.streaming).length;
      counts.replaceChildren(...[
        A.kpi({ label: "Need attention", icon: "attention", value: att === null ? "—" : String(att.length), tone: urgent ? "alert" : null,
          note: att === null ? "couldn't load" : att.length ? (urgent ? `${urgent} high or medium` : "none high or medium") : zeroReason("attention", { items: 0 }), href: "#/attention" }),
        A.kpi({ label: "Live requests", icon: "live", value: String(live.length),
          foot: live.length ? SUI.status("live", "Live", { breathe: true, plain: true }) : SUI.status("idle", "Quiet", { plain: true }),
          note: live.length ? `${streaming} streaming · ${live.length - streaming} waiting` : zeroReason("live", { live: 0 }), href: "#/live" }),
      ].map((card) => { card.append(el("span", { class: "kpi-go", "aria-hidden": "true" }, icon("arrowUp"))); return card; }));
    }
    drawCounts();

    /* BRIEF 10.10.7: one sentence with the real number, then one button for the most useful thing to do now. */
    const secOpen = sec && sec.posture !== "healthy";
    const waiting = requests.status === "fulfilled" ? requests.value.open : 0;
    const tools = S.catalog ? S.catalog.tools : [];
    const setup = staff.status === "fulfilled" && S.catalog ? A.setupSteps({ canGovern: A.can("govern"), people: staff.value.items.length, paid: S.catalog.summary.paid,
      assigned: tools.reduce((n, t) => n + t.assigned_people + t.assigned_teams, 0), uses: tr ? tr.current.requests + tr.days.reduce((n, d) => n + d.opens + d.visits, 0) : 0 }) : null;
    const left = setup ? setup.filter((s) => !s.done) : [];
    const lead = A.overviewLead({ paused: !!(S.overview && S.overview.paused), canStop: A.can("emergency"), loaded: att !== null, urgent, waiting, canAnswer: A.can("govern"),
      secOpen, secEvents: sec ? sec.events.filter((e) => e.severity !== "info").length : 0, items: att ? att.length : 0, setupLeft: left.length, setupNext: left[0] ? { label: left[0].label, task: left[0].task, href: left[0].href } : null });

    /* Simple by default for everyone; the choice is kept per console user and carried in the address. */
    const remembered = "swa-overview-view:" + S.me.username;
    let saved = null;
    try { saved = localStorage.getItem(remembered); } catch (e) { saved = null; }
    const view = (params.get("view") || saved) === "detailed" ? "detailed" : "simple";
    const switcher = SUI.segmented({ label: "How much to show", value: view, options: [{ id: "simple", label: "Simple" }, { id: "detailed", label: "Detailed" }],
      onChange: (v) => { try { localStorage.setItem(remembered, v); } catch (e) { /* private window: the address still carries it */ } location.hash = "#/?view=" + v; } });

    const who = String(S.me.display_name || "").trim();
    A.frame({ title: who ? `Hello, ${who}! 👋` : "Hello! 👋", sentence: view === "simple" ? lead.sentence : null,
      trail: [["Overview"]], next: view === "simple" ? A.leadButton(lead.action) : el("span", null, lead.sentence + " ", A.leadButton(lead.action, true)),
      actions: view === "simple" ? [switcher] : [switcher, el("a", { class: "btn", href: "#/activity" }, icon("activity"), "Activity"), el("a", { class: "btn primary", href: "#/live" }, icon("live"), "Open Live")] },
    view === "simple" ? [A.overviewSimple({ tr, trError: trends.reason, att, waiting, setup, paused: !!(S.overview && S.overview.paused) })]
      : [kpis, el("div", { class: "overview-exact" }, usage, el("div", { class: "overview-side" }, counts))]);

    if (view === "detailed") A.every(5000, async () => { await A.refreshOverview().catch(() => null); drawCounts(); });
  }

  // ------------------------------------------------------------------ Needs attention

  async function pageAttention() {
    const out = await A.refreshAttention();
    if (!out) throw new A.ApiError(0, "The list of things needing attention couldn't load");
    const groups = ["high", "medium", "low", "info"].map((sev) => [sev, out.items.filter((i) => i.severity === sev)]).filter(([, items]) => items.length);
    const names = { high: "Act now", medium: "Worth a look today", low: "When you have a moment", info: "For your information" };
    A.frame({ title: "Needs attention", trail: [["Overview", "#/"], ["Needs attention"]], lede: "Everything worth a look — security, spend, licences, access and the system — on one page, most urgent first.",
      actions: el("button", { class: "btn", onclick: () => A.render() }, icon("refresh"), "Refresh") },
    out.items.length ? groups.map(([sev, items]) => A.panel(names[sev], SUI.plural(items.length, "item"), el("ul", { class: "att-list" }, items.map(attentionItem))))
      : A.panel(null, null, SUI.stateBox({ tone: "ok", icon: "checkCircle", title: "Nothing needs attention", text: "Everything looks normal. This page lists security signals, budgets, idle or over-assigned seats, renewals, waiting tool requests and missing provider keys as soon as they appear." })));
  }

  // ------------------------------------------------------------------ Live

  async function pageLive() {
    await A.toolIndex().catch(() => null);
    const conn = el("span", { class: "u-connecting", role: "status", "aria-live": "polite" }, SUI.status("waiting", "Connecting to live activity…", { plain: true }));
    const kpis = el("div", { class: "kpis four" });
    const stream = el("div", { class: "lv-stream", "aria-live": "off" });
    const finished = el("ol", { class: "events flat" });
    const shared = el("div"), opens = el("div"), sites = el("div");
    const sharedPanel = A.panel("Shared company accounts", "who holds a turn now", shared);
    const cards = new Map();
    function drawKpis(live, turnsNow) {
      const streaming = live.filter((t) => t.streaming).length;
      kpis.replaceChildren(
        A.kpi({ label: "Working right now", icon: "live", value: String(live.length), foot: live.length ? SUI.status("live", "Live", { breathe: true, plain: true }) : SUI.status("idle", "Quiet", { plain: true }) }),
        A.kpi({ label: "Streaming", icon: "activity", value: String(streaming), note: "replies arriving" }),
        A.kpi({ label: "Waiting", icon: "clock", value: String(live.length - streaming), note: "for the model's first word" }),
        A.kpi({ label: "Shared accounts in use", icon: "hand", value: turnsNow === null ? "—" : String(turnsNow), note: "turns held now" }));
    }
    function liveCard(t) {
      const stop = A.can("emergency") ? el("button", { class: "btn small danger", onclick: () => cut(t) }, icon("stop"), "Stop") : null;
      const node = el("article", { class: "lv u-enter", "data-id": String(t.id) },
        el("div", { class: "lv-head" }, el("span", { class: "lv-state" }), el("span", { class: "grow" }),
          el("span", { class: "elapsed u-num", "data-started": String(t.started) }, fmt.elapsed(t.started))),
        el("div", { class: "lv-who" }, A.personLink(t.person_id, t.person), t.department ? el("span", { class: "faint" }, t.department) : null),
        el("div", { class: "lv-what" }, A.toolLink(t.client === "Claude Code" ? "claude-code" : t.client === "Codex" ? "codex" : null, t.client || "A tool"),
          t.model ? el("span", { class: "mono faint" }, t.model) : null, A.deviceLink(t.key_id, t.device)),
        t.prompt ? el("p", { class: "lv-prompt" }, t.prompt) : el("p", { class: "lv-prompt none" }, "The agent is working on its own — no new typed prompt."),
        el("div", { class: "lv-foot" }, el("span", { class: "lv-bytes hint u-num" }), el("span", { class: "grow" }),
          el("button", { class: "btn small", onclick: () => inspectLive(t) }, icon("eye"), "Inspect"), stop ? el("span", { class: "lv-gap" }) : null, stop));
      update(node, t);
      return node;
    }
    function update(node, t) {
      node.querySelector(".lv-state").replaceChildren(SUI.status(t.streaming ? "streaming" : "waiting", t.streaming ? "Streaming" : "Waiting", { breathe: true }));
      node.querySelector(".lv-bytes").textContent = t.streaming ? `${fmt.tokens(t.bytes)}B streamed · cost known when it finishes` : "waiting for the model";
      node.classList.toggle("streaming", !!t.streaming);
    }
    function drawStream(live) {
      const ids = new Set(live.map((t) => t.id));
      for (const [id, node] of cards) if (!ids.has(id)) { node.classList.add("gone"); setTimeout(() => node.remove(), 300); cards.delete(id); }
      live.forEach((t) => { if (cards.has(t.id)) update(cards.get(t.id), t); else { const n = liveCard(t); cards.set(t.id, n); stream.append(n); } });
      const quiet = stream.querySelector(".lv-quiet");
      if (!live.length && !quiet) stream.append(el("div", { class: "lv-quiet" }, SUI.stateBox({ icon: "live", compact: true, title: "All quiet", text: "Nobody is waiting on a model right now. New requests appear here the moment they start." })));
      if (live.length && quiet) quiet.remove();
    }
    async function cut(t) {
      const ok = await A.confirmAction("Stop this request?", `${t.person || "This"}'s ${t.client || "tool"} request is cut now. Their key keeps working for the next one.`, "Stop it", true);
      if (!ok) return;
      try { await api("POST", `/live/${t.id}/cut`); toast("Stopped."); tick(); } catch (e) { toast(e.message, true); }
    }

    let maxId = 0;
    async function loadFinished() {
      const first = maxId === 0;
      const data = await api("GET", first ? "/requests?limit=25" : `/requests?after=${maxId}&limit=50`);
      if (!data.items.length) {
        if (first) finished.replaceChildren(el("li", { class: "plain" }, A.empty("Nothing has gone through the gateway yet. Issue someone a key under People, then point their tool at the gateway.", "No AI activity yet", "spark")));
        return;
      }
      if (first || finished.querySelector(".plain")) finished.replaceChildren();
      maxId = Math.max(maxId, ...data.items.map((r) => r.id));
      finished.prepend(...data.items.map((r) => A.eventItem(A.reqEvent(r), { fresh: !first, compact: false })));
      while (finished.children.length > 40) finished.lastChild.remove();
    }
    async function loadSide() {
      const [turns, launches, visits] = await Promise.all([
        api("GET", "/turns"), api("GET", "/launches?since=" + (S.overview ? S.overview.day_start : 0)),
        api("GET", `/timeline?type=site&since=${Date.now() / 1000 - 3600}&limit=12`)]);
      sharedPanel.hidden = !turns.tools.length;
      shared.replaceChildren(turns.now.length ? el("ul", { class: "mini-list" }, turns.now.map((x) => el("li", null,
        A.toolLogo(x.tool_id, x.tool, "sm"),
        el("div", { class: "grow" }, A.personLink(x.person_id, x.person, { avatar: false }), el("span", { class: "muted" }, " holds "), el("strong", null, x.tool)),
        el("span", { class: "u-badge warn" }, "until " + fmt.clock(x.expires)))))
        : A.empty(`Nobody is on a shared account. ${SUI.plural(turns.tools.length, "tool")} work this way.`));
      opens.replaceChildren(launches.items.length ? A.launchList(launches.items.slice(0, 10)) : A.empty("Nobody has opened a tool from the portal today."));
      sites.replaceChildren(visits.items.length ? el("ul", { class: "mini-list" }, visits.items.map((v) => el("li", null, A.toolLogo(v.tool_id, v.tool, "sm"),
        el("div", { class: "grow" }, A.personLink(v.person_id, v.person, { avatar: false }), el("span", { class: "muted" }, v.outcome === "blocked" ? " was blocked from " : " on "), el("strong", null, v.tool)),
        v.outcome === "blocked" ? SUI.status("blocked", "Blocked", { plain: true }) : el("span", { class: "hint nowrap" }, v.seconds ? fmt.dur(v.seconds) : fmt.ago(v.ts)))))
        : A.empty("No approved AI websites opened in the last hour (needs the browser extension)."));
      return turns.now.length;
    }

    let n = 0, turnsNow = null, failures = 0, lastOk = 0;
    async function tick() {
      try {
        await A.refreshOverview();
        if (!S.overview) throw new Error("no data");
        drawStream(S.overview.live);
        await loadFinished();
        if (n++ % 5 === 0) turnsNow = await loadSide();
        drawKpis(S.overview.live, turnsNow);
        failures = 0; lastOk = Date.now();
        document.querySelector(".page")?.classList.remove("stale");
        conn.replaceChildren(SUI.status("live", "Live", { breathe: true, plain: true }), el("span", { class: "hint" }, " · updated just now"));
      } catch (e) {
        if (e.status === 401) return;
        failures++;
        document.querySelector(".page")?.classList.add("stale");
        conn.replaceChildren(SUI.status("failed", "Live data temporarily unavailable", { plain: true }),
          el("button", { class: "btn small", onclick: () => tick() }, icon("refresh"), "Retry"));
      }
    }
    // The first load is drawn into these nodes before the page is shown, so nothing fills in (and moves
    // what is below it) after the first paint. BRIEF 10.9.4: a cold load must not shift.
    await tick();
    A.frame({ title: "Live", trail: [["Overview", "#/"], ["Live"]], lede: "What is happening across Swangz AI Hub right now.", status: conn }, [
      kpis,
      el("div", { class: "grid cols-2" },
        el("div", { class: "grid" },
          A.panel("In flight", "requests waiting on a model or streaming back", stream),
          A.panel("Just finished", el("a", { class: "btn small quiet", href: "#/activity?tab=ai" }, "Search everything", icon("chevronRight")), finished)),
        el("div", { class: "grid" },
          sharedPanel,
          A.panel("Opened from the portal", "today", opens),
          A.panel("AI websites", "last hour · browser extension", sites))),
    ]);
    document.querySelector(".page")?.classList.toggle("stale", failures > 0);
    A.every(2500, tick);
    A.every(1000, () => {
      document.querySelectorAll(".elapsed[data-started]").forEach((x) => { x.textContent = fmt.elapsed(Number(x.dataset.started)); });
      if (lastOk && !failures) { const ago = Math.round((Date.now() - lastOk) / 1000); const h = conn.querySelector(".hint"); if (h) h.textContent = ago < 2 ? " · updated just now" : ` · updated ${ago}s ago`; }
    });
  }

  /* Inspect a request in flight, then follow it straight into its record when it finishes. */
  function inspectLive(t) {
    let timer = null;
    const { node, close } = sheet(() => clearInterval(timer), "Request in flight");
    const state = el("div", { class: "row" });
    const facts = el("div", { class: "facts" });
    const after = el("div");
    const history = el("div");
    node.append(
      el("header", null, el("div", { class: "spread" },
        el("div", { class: "sheet-id" }, A.toolLogo(t.client === "Claude Code" ? "claude-code" : t.client === "Codex" ? "codex" : null, t.client || "Tool", "lg"),
          el("div", null, el("div", { class: "eyebrow" }, "Request in flight"), el("h2", null, (t.person || "Unknown key") + " · " + (t.client || "a tool")), state)),
        el("button", { class: "btn small quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x")))),
      el("div", { class: "sheet-body" }, facts, after,
        t.prompt ? el("div", { class: "stack" }, el("div", { class: "u-label" }, "What they typed"), el("div", { class: "bubble" }, t.prompt)) : null,
        el("div", { class: "stack" }, el("div", { class: "u-label" }, "Earlier in this session"), history)));
    function draw(live) {
      state.replaceChildren(live ? SUI.status(live.streaming ? "streaming" : "waiting", live.streaming ? "Streaming" : "Waiting", { breathe: true })
        : SUI.status("finished", "Finished"));
      facts.replaceChildren(
        fact("Person", A.personLink(t.person_id, t.person)), fact("Device", A.deviceLink(t.key_id, t.device) || "—"),
        fact("Application", t.client || "—"), fact("Model", el("span", { class: "mono" }, t.model || "—")),
        fact("Started", fmt.clock(t.started, true)), fact("Elapsed", live ? el("span", { class: "elapsed u-num", "data-started": String(t.started) }, fmt.elapsed(t.started)) : "—"),
        fact("Streamed", live ? fmt.tokens(live.bytes) + "B" : "—"),
        fact("Session", t.session ? el("a", { class: "mono", href: "#/sessions/" + encodeURIComponent(t.session) }, t.session.slice(0, 14) + "…") : "—"));
    }
    async function poll() {
      await A.refreshOverview().catch(() => null);
      const live = S.overview && S.overview.live.find((x) => x.id === t.id);
      draw(live);
      if (!live) {
        clearInterval(timer);
        after.replaceChildren(el("div", { class: "notice ok" }, "This request has finished. Looking for its record…"));
        for (let i = 0; i < 6; i++) {
          const data = await api("GET", `/requests?${t.key_id ? "key=" + t.key_id : "person=" + t.person_id}&limit=6`).catch(() => ({ items: [] }));
          const rec = data.items.find((r) => r.ts >= t.started - 2);
          if (rec) {
            after.replaceChildren(el("div", { class: "notice ok spread" }, el("span", null, "Finished — ", A.outcomeStatus("request", rec.outcome, true), " · ", fmt.money(rec.cost)),
              el("a", { class: "btn small primary", href: "#/records/" + rec.id, onclick: () => close() }, "Open the full record", icon("chevronRight"))));
            return;
          }
          await new Promise((r) => setTimeout(r, 1000));
        }
        after.replaceChildren(el("div", { class: "notice" }, "It finished, but its record hasn't appeared yet — find it under Activity."));
      }
    }
    draw(S.overview && S.overview.live.find((x) => x.id === t.id));
    timer = setInterval(poll, 2000);
    if (t.session) {
      api("GET", `/requests?session=${encodeURIComponent(t.session)}&limit=8`).then((d) => {
        history.replaceChildren(d.items.length ? el("ol", { class: "events flat" }, d.items.map((r) => A.eventItem(A.reqEvent(r), { noPerson: true })))
          : A.empty("This is the first request of the session."));
      }).catch((e) => history.replaceChildren(SUI.errorBox(e)));
    } else history.replaceChildren(A.empty("The tool didn't send a session id, so earlier requests can't be linked."));
  }
  const sheet = (onClose, label) => A.sheet(onClose, label);
  function fact(k, v) { return el("div", { class: "fact" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)); }

  // ------------------------------------------------------------------ Activity

  async function pageActivity(params) {
    await A.toolIndex().catch(() => null);
    const exportLink = el("a", { class: "btn", href: A.gadmin("/export.csv") }, icon("download"), "Export CSV");
    A.frame({ title: "Activity", trail: [["Overview", "#/"], ["Activity"]], lede: ["What staff did through Gateway — AI requests, tools opened, AI websites visited, shared-account turns, and each person's sign-ins and access changes. Signals worth investigating are under ",
      el("a", { href: "#/security" }, "Security"), "; what admins changed is in the ", el("a", { href: "#/audit" }, "Audit log"), "."],
      actions: exportLink },
    A.pageTabs("#/activity", params, [
      ["timeline", "Timeline", () => timelineTab(params)],
      ["usage", "Who used what", () => usageTab(params)],
      ["ai", "AI requests", () => aiTab(params, exportLink)],
      ["opens", "Tools opened", () => opensTab(params)],
      ["sites", "Websites visited", () => sitesTab(params)],
    ]));
  }

  let peopleCache = null;
  async function people() {
    if (!peopleCache || Date.now() - peopleCache.at > 60000) peopleCache = { at: Date.now(), items: (await api("GET", "/people")).items };
    return peopleCache.items;
  }
  function personSelect(list, value) {
    const sel = el("select", { "aria-label": "Person" }, el("option", { value: "" }, "Everyone"), list.map((p) => el("option", { value: String(p.id) }, p.name)));
    sel.value = value || "";
    return sel;
  }
  function deptSelect(list, value) {
    const depts = [...new Set(list.map((p) => p.department).filter(Boolean))].sort();
    const sel = el("select", { "aria-label": "Department" }, el("option", { value: "" }, "All departments"), depts.map((d) => el("option", { value: d }, d)));
    sel.value = value || "";
    return sel;
  }
  function toolSelect(value) {
    const tools = Object.values(S.tools || {}).filter((t) => !t.archived).sort((a, b) => a.name.localeCompare(b.name));
    const sel = el("select", { "aria-label": "Tool" }, el("option", { value: "" }, "Every tool"), tools.map((t) => el("option", { value: t.id }, t.name)));
    sel.value = value || "";
    return sel;
  }
  function seg(options, value, onChange, label) {
    const box = el("div", { class: "u-seg", role: "group", "aria-label": label });
    const draw = () => box.replaceChildren(...options.map(([v, t]) => el("button", { type: "button", "aria-pressed": v === value ? "true" : "false",
      onclick: () => { value = v; draw(); onChange(v); } }, t)));
    draw();
    return box;
  }
  function field(label, control) { return el("label", { class: "field" }, el("span", null, label), control); }
  const optText = (sel) => (sel.value ? (sel.tagName === "SELECT" ? sel.options[sel.selectedIndex].text : sel.value) : "");

  /* Filters without the clutter: search, the Filters button and the time range share one row; the rest
     fold away until wanted, and whatever is set shows as a chip you can clear.
     fields: [{key, label, control}] — clear(keys) resets them and reloads. */
  let fbSeq = 0;
  function filterBar(o) {
    const fields = o.fields || [];
    const more = el("div", { class: "fb-more", id: "fb-more-" + (++fbSeq), hidden: true }, fields.map((f) => field(f.label, f.control)));
    const count = el("span", { class: "fb-count", hidden: true });
    const toggle = el("button", { class: "btn small fb-toggle", type: "button", "aria-expanded": "false", "aria-controls": more.id }, icon("filter"), "Filters", count);
    toggle.addEventListener("click", () => {
      const open = more.hidden;
      more.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.classList.toggle("on", open);
      if (open) { const first = more.querySelector("select, input"); if (first) first.focus(); }
    });
    const chips = el("div", { class: "fb-chips", hidden: true });
    function draw() {
      const active = fields.filter((f) => optText(f.control));
      count.textContent = String(active.length);
      count.hidden = !active.length;
      chips.hidden = !active.length;
      chips.replaceChildren(...active.map((f) => el("button", { class: "fb-chip", type: "button", "aria-label": `Remove filter ${f.label}: ${optText(f.control)}`,
        onclick: () => o.clear([f.key]) }, el("span", { class: "k" }, f.label), optText(f.control), icon("x"))),
      active.length > 1 ? el("button", { class: "btn link fb-clear", type: "button", onclick: () => o.clear(active.map((f) => f.key)) }, "Clear all") : null);
    }
    draw();
    const node = el("div", { class: "filterbar" },
      el("div", { class: "fb-row" },
        o.search ? el("label", { class: "fb-search" }, icon("search"), el("span", { class: "u-sr" }, "Search"), o.search) : null,
        fields.length ? toggle : null, o.extra || null, o.range || null),
      more, chips);
    return { node, draw };
  }

  /* Who did what, when, where — every record in one stream, grouped by day. */
  async function timelineTab(params) {
    const list = await people();
    const st = { range: A.rangeFrom(params, "7d"), person: params.get("person") || "", tool: params.get("tool") || "", type: params.get("type") || "", q: params.get("q") || "", dept: params.get("dept") || "" };
    const ctl = { person: personSelect(list, st.person), dept: deptSelect(list, st.dept), tool: toolSelect(st.tool),
      type: el("select", { "aria-label": "Kind of event" }, [["", "Everything"], ["request", "AI requests"], ["launch", "Tools opened"], ["site", "AI websites"],
        ["turn", "Shared account turns"], ["access", "Sign-ins and access changes"]].map(([v, t]) => el("option", { value: v }, t))) };
    ctl.type.value = st.type;
    const q = el("input", { type: "search", placeholder: "Search prompts, people, tools…", value: st.q });
    const results = el("div", { class: "results" });
    const summary = el("div", { class: "hint", role: "status" });
    const more = el("button", { class: "btn", hidden: true }, "Load older");
    let next = null, days = null;
    const query = () => {
      const p = A.rangeQuery(st.range);
      ["person", "tool", "type", "q", "dept"].forEach((k) => { if (st[k]) p.set(k, st[k]); });
      return p;
    };
    async function load(reset) {
      const p = query();
      p.set("limit", "50");
      if (!reset && next) p.set("before", String(next));
      if (reset) results.classList.add("refreshing");
      const data = await api("GET", "/timeline?" + p.toString());
      results.classList.remove("refreshing");
      next = data.next_before;
      more.hidden = !data.more;
      if (reset) {
        days = A.eventDays(data.items);
        results.replaceChildren(data.items.length ? days.node : SUI.stateBox({ icon: "activity", title: "No AI activity in this period",
          text: "Once staff use approved tools, their requests, opens and visits appear here. Try a wider range or fewer filters." }));
      } else days.add(data.items);
      summary.textContent = `${results.querySelectorAll(".ev").length.toLocaleString()} events${data.more ? " so far" : ""} · times in ${SUI.tzLabel()}`;
    }
    const apply = () => {
      fb.draw();
      A.keepParams("#/activity", { tab: "timeline", range: st.range.preset, from: st.range.preset === "custom" ? st.range.from : null,
        to: st.range.preset === "custom" ? st.range.to : null, person: st.person, tool: st.tool, type: st.type, q: st.q, dept: st.dept });
      load(true).catch((e) => results.replaceChildren(SUI.errorBox(e, apply)));
    };
    const fb = filterBar({ search: q,
      range: SUI.rangeControl({ preset: st.range.preset, from: st.range.from, to: st.range.to, presets: ["today", "yesterday", "7d", "30d", "month", "custom"], onChange: (r) => { st.range = r; apply(); } }),
      fields: [{ key: "person", label: "Person", control: ctl.person }, { key: "dept", label: "Department", control: ctl.dept },
        { key: "tool", label: "Tool", control: ctl.tool }, { key: "type", label: "Show", control: ctl.type }],
      clear: (keys) => { keys.forEach((k) => { st[k] = ""; ctl[k].value = ""; }); apply(); } });
    Object.entries(ctl).forEach(([k, c]) => c.addEventListener("change", () => { st[k] = c.value; apply(); }));
    q.addEventListener("input", SUI.debounce(() => { st.q = q.value.trim(); apply(); }, 300));
    more.addEventListener("click", () => load(false).catch((e) => toast(e.message, true)));
    await load(true);
    return A.panel(null, null, fb.node, el("div", { class: "body tight" }, summary), results, el("div", { class: "body center" }, more));
  }

  /* Who used what: one row per person and tool, across every record. */
  async function usageTab(params) {
    const st = { range: A.rangeFrom(params, "today"), by: params.get("by") || "both" };
    const box = el("div");
    async function load() {
      box.classList.add("refreshing");
      const data = await api("GET", "/usage?" + A.rangeQuery(st.range).toString());
      box.classList.remove("refreshing");
      const uses = (r) => r.requests + r.opens + r.visits;
      const useCell = (r) => el("span", null, [r.requests && SUI.plural(r.requests, "request"), r.generations && SUI.plural(r.generations, "generation"),
        r.opens && SUI.plural(r.opens, "open"), r.visits && SUI.plural(r.visits, "visit")].filter(Boolean).join(" · ") || "—",
      r.refused ? el("span", { class: "sub" }, SUI.plural(r.refused, "refusal")) : null);
      const common = [
        { key: "uses", label: "Use", sort: uses, render: useCell },
        { key: "seconds", label: "Time on site", num: true, render: (r) => (r.seconds ? fmt.dur(r.seconds) : "—"), hideSm: true },
        { key: "cost", label: "Cost", num: true, render: (r) => (r.requests ? fmt.money(r.cost) : "—") },
        { key: "last", label: "Last", num: true, render: (r) => el("span", { title: fmt.stamp(r.last) }, fmt.when(r.last)) },
      ];
      let rows, cols;
      if (st.by === "person") {
        rows = data.people;
        cols = [{ key: "person", label: "Person", lead: true, render: (r) => A.personLink(r.person_id, r.person) },
          { key: "tools", label: "Tools", num: true }, ...common];
      } else if (st.by === "tool") {
        rows = data.tools;
        cols = [{ key: "tool", label: "Tool", lead: true, render: (r) => A.toolLink(r.tool_id, r.tool, "sm") },
          { key: "people", label: "People", num: true }, ...common];
      } else {
        rows = data.rows;
        cols = [{ key: "person", label: "Person", lead: true, render: (r) => A.personLink(r.person_id, r.person) },
          { key: "tool", label: "Tool", render: (r) => [A.toolLink(r.tool_id, r.tool, "sm"), r.apps.length && !(r.apps.length === 1 && r.apps[0] === r.tool) ? el("span", { class: "sub" }, "via " + r.apps.join(", ")) : null] },
          ...common];
      }
      /* Uses by tool, moved here from Overview (BRIEF 10.10.1): shown when the list is grouped by tool. */
      const byTool = st.by === "tool" && rows.length ? el("div", { class: "body usage-by-tool" }, SUI.donut({ label: "Uses by tool in this period", unit: "Uses", centre: "Uses", other: "Other tools",
        total: rows.reduce((n, t) => n + uses(t), 0),
        rows: rows.slice().sort((x, y) => uses(y) - uses(x)).map((t) => ({ label: t.tool, href: t.tool_id ? `#/tools?open=${t.tool_id}` : null, value: uses(t), display: SUI.plural(uses(t), "use") })) })) : null;
      box.replaceChildren(...[byTool, rows.length ? SUI.table({ columns: cols, rows, sort: ["last", "desc"], caption: "Who used what",
        href: st.by === "tool" ? (r) => (r.tool_id ? `#/tools?open=${r.tool_id}` : null) : (r) => `#/people/${r.person_id}` })
        : SUI.stateBox({ icon: "people", title: "No AI activity in this period", text: "Once staff start using approved tools, who used what appears here." })].filter(Boolean));
      const total = data.people.length;
      summary.textContent = `${SUI.plural(total, "person", "people")} · ${SUI.plural(data.tools.length, "tool")} · ${fmt.money(data.people.reduce((n, p) => n + p.cost, 0))} metered`;
    }
    const summary = el("div", { class: "hint", role: "status" });
    const apply = () => {
      A.keepParams("#/activity", { tab: "usage", range: st.range.preset, from: st.range.preset === "custom" ? st.range.from : null, to: st.range.preset === "custom" ? st.range.to : null, by: st.by === "both" ? null : st.by });
      load().catch((e) => box.replaceChildren(SUI.errorBox(e, apply)));
    };
    await load();
    return A.panel(null, null,
      filterBar({ extra: el("span", { class: "fb-group" }, el("span", { class: "u-label" }, "Group by"),
        seg([["both", "Person & tool"], ["person", "Person"], ["tool", "Tool"]], st.by, (v) => { st.by = v; apply(); }, "Group by")),
      range: SUI.rangeControl({ preset: st.range.preset, from: st.range.from, to: st.range.to, onChange: (r) => { st.range = r; apply(); } }) }).node,
      el("div", { class: "body tight" }, summary), box);
  }

  /* Every API call through the gateway: the typed prompt, what the agent did, the reply, tokens, cost. */
  async function aiTab(params, exportLink) {
    const list = await people();
    const st = { range: A.rangeFrom(params, "30d"), q: params.get("q") || "", person: params.get("person") || "", client: params.get("client") || "",
      outcome: params.get("outcome") || "", show: params.get("kind") === "media" ? "media" : params.get("only") === "prompts" ? "prompts" : params.get("flag") === "secret" ? "secret" : params.get("all") ? "all" : "",
      model: params.get("model") || "", dept: params.get("dept") || "" };
    const q = el("input", { type: "search", placeholder: "Search prompts, commands, replies…", value: st.q });
    const ctl = { person: personSelect(list, st.person), dept: deptSelect(list, st.dept),
      client: el("select", { "aria-label": "Application" }, ["", "Claude Code", "Codex", "Swangz AI Hub Studio", "Cursor", "OpenAI SDK", "Anthropic SDK", "curl", "unknown"].map((c) => el("option", { value: c }, c || "Any application"))),
      model: el("input", { type: "text", placeholder: "e.g. claude-sonnet-4-5", value: st.model, "aria-label": "Model" }),
      outcome: el("select", { "aria-label": "Outcome" }, [["", "Any outcome"], ["ok", "Completed"], ["blocked", "Blocked"], ["denied", "Wrong key"], ["cut", "Stopped"], ["aborted", "Closed by the tool"], ["error", "Failed"]].map(([v, t]) => el("option", { value: v }, t))),
      show: el("select", { "aria-label": "Show" }, [["", "All requests"], ["media", "Voice, image & video"], ["prompts", "Only typed prompts"], ["secret", "Credentials flagged"], ["all", "Include token counts & other calls"]].map(([v, t]) => el("option", { value: v }, t))) };
    ctl.client.value = st.client; ctl.outcome.value = st.outcome; ctl.show.value = st.show;
    const listBox = el("ol", { class: "events flat" });
    const more = el("button", { class: "btn", hidden: true }, "Load older");
    let minId = null;
    function query() {
      const p = A.rangeQuery(st.range);
      if (st.q) p.set("q", st.q);
      if (st.person) p.set("person", st.person);
      if (st.dept) p.set("dept", st.dept);
      if (st.client) p.set("client", st.client);
      if (st.outcome) p.set("outcome", st.outcome);
      if (st.model) p.set("model", st.model);
      if (st.show === "prompts") p.set("only", "prompts");
      if (st.show === "media") p.set("kind", "media");
      if (st.show === "secret") p.set("flag", "secret");
      if (st.show === "all") p.set("all", "1");
      return p;
    }
    async function load(reset) {
      const p = query();
      if (!reset && minId) p.set("before", minId);
      p.set("limit", "60");
      const data = await api("GET", "/requests?" + p.toString());
      if (reset) listBox.replaceChildren();
      if (reset && !data.items.length) listBox.append(el("li", { class: "plain" }, SUI.stateBox({ icon: "search", title: "Nothing matches", text: "Try a wider time range or fewer filters." })));
      data.items.forEach((r) => listBox.append(A.eventItem(A.reqEvent(r))));
      if (data.items.length) minId = Math.min(...data.items.map((r) => r.id));
      more.hidden = !data.more;
      if (exportLink) exportLink.href = A.gadmin("/export.csv?" + new URLSearchParams([...A.rangeQuery(st.range)].concat(st.person ? [["person", st.person]] : [])).toString());
    }
    const apply = () => {
      minId = null;
      fb.draw();
      const keep = query();
      keep.delete("since"); keep.delete("until");
      keep.set("tab", "ai");
      keep.set("range", st.range.preset);
      if (st.range.preset === "custom") { keep.set("from", st.range.from); keep.set("to", st.range.to); }
      history.replaceState(null, "", "#/activity?" + keep.toString());
      load(true).catch((e) => listBox.replaceChildren(el("li", { class: "plain" }, SUI.errorBox(e, apply))));
    };
    const fb = filterBar({ search: q,
      range: SUI.rangeControl({ preset: st.range.preset, from: st.range.from, to: st.range.to, onChange: (r) => { st.range = r; apply(); } }),
      fields: [{ key: "person", label: "Person", control: ctl.person }, { key: "dept", label: "Department", control: ctl.dept },
        { key: "client", label: "Application", control: ctl.client }, { key: "model", label: "Model", control: ctl.model },
        { key: "outcome", label: "Outcome", control: ctl.outcome }, { key: "show", label: "Show", control: ctl.show }],
      clear: (keys) => { keys.forEach((k) => { st[k] = ""; ctl[k].value = ""; }); apply(); } });
    q.addEventListener("input", SUI.debounce(() => { st.q = q.value.trim(); apply(); }, 300));
    ctl.model.addEventListener("input", SUI.debounce(() => { st.model = ctl.model.value.trim(); apply(); }, 400));
    ["person", "dept", "client", "outcome", "show"].forEach((k) => ctl[k].addEventListener("change", () => { st[k] = ctl[k].value; apply(); }));
    more.addEventListener("click", () => load(false).catch((e) => toast(e.message, true)));
    await load(true);
    return A.panel(null, null, fb.node, listBox, el("div", { class: "body center" }, more));
  }

  async function opensTab(params) {
    const list = await people();
    const st = { range: A.rangeFrom(params, "30d"), person: params.get("person") || "" };
    const person = personSelect(list, st.person);
    const box = el("div");
    let fb = null;
    async function load() {
      const p = A.rangeQuery(st.range);
      if (st.person) p.set("person", st.person);
      p.set("type", "launch");
      p.set("limit", "200");
      const data = await api("GET", "/timeline?" + p.toString());
      const refused = data.items.filter((o) => o.outcome !== "opened").length;
      box.replaceChildren(data.items.length ? el("div", null,
        refused ? el("div", { class: "body" }, el("div", { class: "notice" }, `${SUI.plural(refused, "open")} refused — the person wasn't entitled at that moment.`)) : null,
        A.eventDays(data.items).node)
        : SUI.stateBox({ icon: "open", title: "No tools opened in this period", text: "When staff press Open in Swangz AI Hub, it appears here with the device and address it came from." }));
    }
    const apply = () => {
      fb.draw();
      A.keepParams("#/activity", { tab: "opens", range: st.range.preset, from: st.range.preset === "custom" ? st.range.from : null, to: st.range.preset === "custom" ? st.range.to : null, person: st.person });
      load().catch((e) => box.replaceChildren(SUI.errorBox(e, apply)));
    };
    fb = filterBar({ range: SUI.rangeControl({ preset: st.range.preset, from: st.range.from, to: st.range.to, onChange: (r) => { st.range = r; apply(); } }),
      fields: [{ key: "person", label: "Person", control: person }], clear: () => { st.person = ""; person.value = ""; apply(); } });
    person.addEventListener("change", () => { st.person = person.value; apply(); });
    await load();
    return A.panel(null, null, fb.node, box);
  }

  async function sitesTab() {
    const usage = await api("GET", "/site-usage");
    const byTool = usage.by_tool.length ? SUI.table({ caption: "AI websites by tool", rows: usage.by_tool, sort: ["opens", "desc"], columns: [
      { key: "tool", label: "Tool", lead: true, render: (t) => A.toolLink(null, t.tool || "—", "sm") },
      { key: "opens", label: "Visits", num: true },
      { key: "blocked", label: "Blocked", num: true, render: (t) => (t.blocked ? SUI.status("blocked", String(t.blocked), { plain: true }) : "—") },
      { key: "seconds", label: "Time", num: true, render: (t) => fmt.dur(t.seconds) }] })
      : SUI.stateBox({ icon: "globe", title: "No website visits yet", text: "Staff need the Swangz AI Hub Access browser extension installed." });
    const visits = usage.items.slice(0, 300);
    return [
      el("div", { class: "notice info" }, icon("shield"), "The browser extension records which approved AI site was opened, by whom, when and for how long — never page content or anything typed."),
      A.panel("By tool", "last 30 days", byTool),
      A.panel("Every visit", "newest first", visits.length ? SUI.table({ caption: "Every website visit", rows: visits, sort: ["started", "desc"], columns: [
        { key: "started", label: "When", lead: true, render: (v) => el("span", { title: fmt.stamp(v.started) }, fmt.day(v.started) + " · " + fmt.clock(v.started)) },
        { key: "person", label: "Person", render: (v) => v.person || "—" },
        { key: "tool", label: "Tool", render: (v) => A.toolLink(null, v.tool || v.host, "sm") },
        { key: "seconds", label: "Time", num: true, render: (v) => (v.seconds ? fmt.dur(v.seconds) : "—") },
        { key: "outcome", label: "Outcome", render: (v) => A.outcomeStatus("site", v.outcome, true) }] }) : A.empty("No visits recorded yet.")),
    ];
  }

  // ------------------------------------------------------------------ Security

  const SEC_TYPES = {
    credential: ["Credential detections", "key"], unusual: ["Unusual usage", "activity"], wrong_key: ["Unknown keys", "lock"], signin: ["Failed sign-ins", "user"],
    blocked: ["Rule refusals", "stop"], denied_open: ["Opened without access", "open"], site_blocked: ["Websites blocked", "globe"], revoked: ["Keys revoked", "key"],
    suspended: ["Access suspended", "user"], denials: ["Repeated refusals", "stop"], new_place: ["New places", "pin"], new_device: ["New devices", "device"],
    off_hours: ["Unusual hours", "clock"], new_model: ["New models", "chip"],
  };
  /* BRIEF 10.10: Security is an L1 (four number cards and one short list). All signals is the L2 under it, and every
     card opens that list already filtered to what the card counts. ?days= or ?type= still land on the list, so links
     from when this was one page keep working. */
  const SEC_ROOT = ["Security", "#/security"];
  const SEC_RANK = { high: 3, medium: 2, low: 1, info: 0 };
  const SEC_DAYS = [["1", "24 hours"], ["30", "30 days"]];
  const SEC_LEVELS = [["warnings", "Low and above", (e) => e.severity !== "info"], ["high", "High", (e) => e.severity === "high"],
    ["medium", "Medium", (e) => e.severity === "medium"], ["low", "Low", (e) => e.severity === "low"], ["info", "Info", (e) => e.severity === "info"]];
  const secSignals = (extra) => "#/security?view=signals&days=7" + (extra ? "&" + extra : "");

  function pageSecurity(params) {
    return params.get("view") === "signals" || params.has("days") || params.has("type") ? signalsList(params) : securitySummary();
  }

  function safeguardsSheet(data) {
    const [state, label, text] = {
      healthy: ["healthy", "Healthy", "No medium or high signals in this period. Low and informational events are in All signals for completeness."],
      watch: ["watch", "Worth a look", "Something here deserves a check, so start with the medium items. Nothing is a finding against anyone until you've looked."],
      elevated: ["elevated", "Elevated", "A high-severity signal is open. Look at it first."],
    }[data.posture];
    const fact = (k, v) => el("div", null, el("div", { class: "k" }, k), el("div", { class: "v" }, v));
    SUI.sheet({ title: "Safeguards", cancel: "Close", purpose: "How the gateway is set to protect itself right now.", body: el("div", { class: "stack" },
      el("div", null, SUI.status(state, label), el("p", null, text)),
      el("div", { class: "evidence-grid" },
        fact("Credentials in requests", data.settings.block_secrets ? "Refused" : "Let through, flagged"),
        fact("Rate limit", data.settings.rate_per_min ? data.settings.rate_per_min + " a minute per person" : "Off"),
        fact("Kill switch", data.settings.paused ? "AI is paused" : "Ready")),
      el("a", { class: "btn small", href: "#/settings?tab=access" }, "Change in Settings")) });
  }

  async function securitySummary() {
    const [secR, incR] = await Promise.allSettled([api("GET", "/security?days=7"), api("GET", "/incidents?status=active")]);
    const data = secR.status === "fulfilled" ? secR.value : null;
    const inc = incR.status === "fulfilled" ? incR.value : null;
    const failed = "couldn't load";
    const of = (f) => (data ? data.events.filter(f) : []);
    const warnings = of((e) => e.severity !== "info"), high = of((e) => e.severity === "high"), medium = of((e) => e.severity === "medium");
    const signIns = of((e) => e.type === "signin"), credentials = of((e) => e.type === "credential");
    const active = inc ? inc.items.length : 0;
    const cards = el("div", { class: "kpis four kpis-exact" }, [
      A.kpi({ label: "Signals · 7 days", value: data ? String(warnings.length) : "—", tone: high.length ? "alert" : null, href: secSignals("severity=warnings"),
        tip: "Everything rated low or above. Severity says what to check first; it isn't a judgement on anyone.",
        note: !data ? failed : warnings.length ? `${high.length} high, ${medium.length} medium` : "nothing to check" }),
      A.kpi({ label: "Open incidents", value: inc ? String(active) : "—", tone: active ? "alert" : null, href: "#/incidents?status=active",
        note: !inc ? failed : active ? "being followed through" : "none open" }),
      A.kpi({ label: "Failed sign-ins · 7 days", value: data ? String(signIns.length) : "—", href: secSignals("type=signin"),
        tip: "Grouped: one signal for each address and kind of sign-in, however many attempts it made.",
        note: !data ? failed : signIns.length ? "grouped by address" : "none failed" }),
      A.kpi({ label: "Credentials · 7 days", value: data ? String(credentials.length) : "—", tone: credentials.length ? "alert" : null, href: secSignals("type=credential"),
        tip: "Requests whose text looked like a key or password. It can be a test or example key.",
        note: !data ? failed : credentials.length ? "found in requests" : "none found in requests" }),
    ].map((card) => { card.append(el("span", { class: "kpi-go", "aria-hidden": "true" }, icon("arrowUp"))); return card; }));

    const first = warnings.slice().sort((a, b) => SEC_RANK[b.severity] - SEC_RANK[a.severity] || b.ts - a.ts).slice(0, 5);
    const list = !data ? SUI.errorBox(secR.reason, () => A.render())
      : first.length ? el("ul", { class: "sec-list sec-short" }, first.map((e) => { const [state, label] = SEV[e.severity] || SEV.info;
        return el("li", { class: "sec sev-" + e.severity }, el("a", { class: "sec-link", href: e.href },
          el("div", { class: "sec-head" }, el("span", { class: "u-label" }, (SEC_TYPES[e.type] || [e.title])[0]), SUI.status(state, label),
            el("span", { class: "grow" }), el("time", { class: "hint", title: fmt.stamp(e.ts) }, fmt.ago(e.ts))),
          el("p", { class: "sec-text", title: e.text }, e.text))); }))
        : SUI.stateBox({ tone: "ok", icon: "shield", title: "Nothing to check", text: "No signals rated low or above in the last 7 days." });

    /* The one "Next step" line: high signals first, then cases already open, then what is worth a look. */
    const next = !data || !inc ? "Some of the figures couldn't load, so there is no next step to show."
      : high.length ? el("a", { href: secSignals("severity=high") }, `Check ${SUI.plural(high.length, "high signal")}`)
        : active ? el("a", { href: "#/incidents?status=active" }, `Follow through on ${SUI.plural(active, "open incident")}`)
          : medium.length ? el("a", { href: secSignals("severity=medium") }, `Check ${SUI.plural(medium.length, "medium signal")}`)
            : "Nothing needs doing right now.";

    A.frame({ title: "Security", trail: [[SEC_ROOT[0]]], next, actions: [
      data ? el("button", { class: "btn", type: "button", onclick: () => safeguardsSheet(data) }, icon("shield"), "Safeguards") : null,
      el("a", { class: "btn", href: "#/devices" }, icon("device"), "Devices"),
      el("a", { class: "btn", href: "#/audit" }, icon("audit"), "Audit log"),
    ].filter(Boolean) }, [cards, A.panel("Check these first", el("a", { class: "btn small quiet", href: secSignals() }, "See all", icon("chevronRight")), list)]);
  }

  async function signalsList(params) {
    const days = SEC_DAYS.some(([k]) => k === params.get("days")) ? params.get("days") : "";
    const st = { q: params.get("q") || "", days, type: SEC_TYPES[params.get("type")] ? params.get("type") : "",
      severity: SEC_LEVELS.some(([k]) => k === params.get("severity")) ? params.get("severity") : "",
      page: Number(params.get("page")) || 1, per: Number(params.get("per")) || 25 };
    let data = await api("GET", "/security?days=" + (st.days || 7)), asked = 0;
    const box = el("div"), meta = el("div", { class: "list-meta", role: "status" });
    const pager = { page: st.page, size: st.per, onChange: (page, size) => { st.page = pager.page = page; st.per = pager.size = size; keep(); } };
    const details = (e) => SUI.sheet({ title: e.title, cancel: "Close", purpose: (SEC_TYPES[e.type] || [e.title])[0], body: el("div", { class: "stack" },
      el("p", null, e.text), e.evidence ? SUI.evidence(e.evidence) : null, e.href ? el("a", { class: "btn small", href: e.href }, "Investigate", icon("chevronRight")) : null) });
    function draw() {
      const qq = st.q.trim().toLowerCase();
      const want = (SEC_LEVELS.find(([k]) => k === st.severity) || [, , () => true])[2];
      const rows = data.events.filter((e) => (!st.type || e.type === st.type) && want(e)
        && (!qq || [e.title, e.text, e.person, e.tool, e.device, e.ip].join(" ").toLowerCase().includes(qq)));
      const span = SEC_DAYS.find(([k]) => k === st.days);
      meta.replaceChildren(el("span", null, SUI.plural(rows.length, "signal") + " · last " + (span ? span[1] : "7 days")));
      box.replaceChildren(rows.length ? SUI.table({ caption: "All signals", rows, sort: ["ts", "desc"], href: (e) => e.href || null, pager, columns: [
        { key: "title", label: "Signal", lead: true, render: (e) => el("div", null, el("strong", null, (SEC_TYPES[e.type] || [e.title])[0]), el("span", { class: "sub sec-cut", title: e.text }, e.text)) },
        { key: "severity", label: "Severity", sort: (e) => SEC_RANK[e.severity], render: (e) => SUI.status(...(SEV[e.severity] || SEV.info), { plain: true }) },
        { key: "person", label: "Who", render: (e) => (e.person ? A.personLink(e.person_id, e.person) : "—") },
        { key: "where", label: "Where", sort: false, hideSm: true, render: (e) => (e.ip ? A.where(e.ip, e.place) : e.device || e.tool || "—") },
        { key: "ts", label: "When", num: true, render: (e) => el("time", { title: fmt.stamp(e.ts) }, fmt.ago(e.ts)) },
        { key: "act", label: "", srLabel: "Actions", sort: false, render: (e) => SUI.menuButton({ label: "More actions for " + e.title, small: true, items: () => [
          { id: "details", label: "Details", icon: "info", onSelect: () => details(e) },
          e.href ? { id: "investigate", label: "Investigate", icon: "chevronRight", href: e.href } : null,
          A.can("trust") && e.severity !== "info" ? { id: "incident", label: "Open incident", icon: "flag", onSelect: () => A.openIncident({
            title: e.title + (e.person ? " — " + e.person : ""), severity: e.severity === "high" ? "high" : "medium", source: "security:" + e.type,
            person: e.person_id, request: (e.href || "").startsWith("#/records/") ? e.href.slice(10) : null }) } : null,
        ].filter(Boolean) }) },
      ] }) : SUI.stateBox({ tone: data.events.length ? null : "ok", icon: "shield", title: data.events.length ? "No signals match" : "No security signals",
        text: data.events.length ? "Try another search or filter." : "Nothing in this period." }));
    }
    const keep = () => A.keepParams("#/security", { view: "signals", days: st.days, type: st.type, severity: st.severity, q: st.q, page: st.page > 1 ? st.page : null, per: st.per !== 25 ? st.per : null });
    const reload = async () => {
      const mine = ++asked;
      try { const got = await api("GET", "/security?days=" + (st.days || 7)); if (mine !== asked) return; data = got; draw(); }
      catch (e) { if (mine === asked) box.replaceChildren(SUI.errorBox(e, reload)); }
    };
    const bar = SUI.filterBar({ label: "Filter signals", search: { placeholder: "Person, tool, device or address" }, values: st, filters: [
      { id: "days", label: "Period", any: "7 days", options: SEC_DAYS.map(([id, label]) => ({ id, label })) },
      { id: "type", label: "Kind", any: "Every kind", options: Object.entries(SEC_TYPES).map(([id, [label]]) => ({ id, label })) },
      { id: "severity", label: "Severity", any: "Any severity", options: SEC_LEVELS.map(([id, label]) => ({ id, label })) },
    ], onChange: (v, id) => { st.q = v.q || ""; st.days = v.days || ""; st.type = v.type || ""; st.severity = v.severity || ""; st.page = pager.page = 1; keep();
      if (id === "days" || id === null) reload(); else draw(); } });
    draw();
    A.frame({ title: "All signals", trail: [SEC_ROOT, ["All signals"]], lede: ["Signals that may need investigating, each with its evidence. Severity says what to check first; it isn't a judgement on anyone. What people did is under ",
      el("a", { href: "#/activity" }, "Activity"), "."] }, A.panel(null, null, el("div", { class: "filterbar" }, bar), meta, box));
  }

  // ------------------------------------------------------------------ Audit

  const AUDIT_RANGES = [["today", "Today"], ["7d", "7 days"], ["month", "This month"]];
  const AUDIT_AREAS = [["govern", "Govern"], ["money", "Money"], ["trust", "Trust"], ["emergency", "Emergency"], ["admin", "Administration"]];
  const AUDIT_OUTCOMES = [["ok", "Done"], ["denied", "Refused"], ["no-op", "Changed nothing"]];

  /* L2: one filter row (search, period, who, outcome, area), one table. The server filters and hands back 100 at a time;
     the pager steps through what has loaded and "Load older" fetches the next 100. */
  async function pageAudit(params) {
    const range = A.rangeFrom(params, "30d");
    const st = { range: range.preset === "30d" ? "" : range.preset, actor: params.get("actor") || "", q: params.get("q") || "", outcome: params.get("outcome") || "",
      area: params.get("area") || "", correlation: params.get("correlation") || "", page: Number(params.get("page")) || 1, per: Number(params.get("per")) || 25 };
    let from = params.get("from") || "", to = params.get("to") || "";
    const box = el("div"), summary = el("div", { class: "list-meta", role: "status" });
    const more = el("button", { class: "btn", type: "button", hidden: true }, "Load older");
    const pager = { page: st.page, size: st.per, onChange: (page, size) => { st.page = pager.page = page; st.per = pager.size = size; keep(); } };
    let minId = null, rows = [], actors = [], asked = 0, hasMore = false;
    const cols = [
      { key: "ts", label: "When", lead: true, render: (a) => el("time", { title: fmt.stamp(a.ts), class: "u-num nowrap" }, fmt.clock(a.ts, true), el("span", { class: "sub" }, fmt.day(a.ts))) },
      { key: "actor", label: "Who", render: (a) => el("span", { class: "u-cell" }, SUI.avatar(a.actor, "sm"), el("strong", null, a.actor)) },
      { key: "action", label: "Action", render: (a) => el("div", null,
        el("span", { class: "audit-action" + (a.outcome === "denied" || /failed|revoked|suspended|deleted|removed|paused|stopped/.test(a.action) ? " neg" : "") }, a.action),
        a.outcome && a.outcome !== "ok" ? el("span", { class: "sub" }, a.outcome === "denied" ? "refused: outside their role" : a.outcome === "no-op" ? "changed nothing" : a.outcome) : null) },
      { key: "target", label: "Target", render: (a) => a.target || "—" },
      { key: "detail", label: "Detail", sort: false, render: (a) => auditDetail(a), hideSm: true },
      { key: "ip", label: "From", render: (a) => (a.ip ? A.where(a.ip, a.place) : el("span", { class: "faint" }, "—")), hideSm: true },
    ];
    function auditDetail(a) {
      const show = (v) => JSON.stringify(v, null, 1).replace(/^\{\n|\n\}$/g, "").replace(/"([^"]+)":/g, "$1:");
      const changed = a.before || a.after;
      return el("div", { class: "audit-detail-box" },
        a.detail ? el("span", { class: "audit-detail", title: a.detail }, a.detail) : null,
        a.reason ? el("div", { class: "hint" }, "Reason: " + a.reason) : null,
        changed ? el("details", null, el("summary", null, "What changed"),
          el("div", { class: "json-diff" }, el("pre", { class: "was" }, a.before ? show(a.before) : "—"), el("pre", { class: "now" }, a.after ? show(a.after) : "—"))) : null,
        !a.detail && !a.reason && !changed ? "—" : null);
    }
    function draw() {
      summary.replaceChildren(el("span", null, SUI.plural(rows.length, "entry", "entries") + (hasMore ? " so far" : "")),
        el("span", null, "can't be edited or cleared from the console"), el("span", null, "times in " + SUI.tzLabel(true)));
      box.replaceChildren(rows.length ? SUI.table({ caption: "Audit log", columns: cols, rows, sort: ["ts", "desc"], pager })
        : SUI.stateBox({ icon: "audit", title: "No audit entries", text: "Nothing matches. Try another period or filter." }));
      more.hidden = !hasMore;
    }
    // "person:7" is the way a change names what it is about, so typing one searches that exactly
    const aboutQuery = (q) => (/^[a-z_]+:\d+$/i.test(q) ? ["correlation", q] : ["q", q]);
    async function load(reset) {
      const mine = ++asked;
      const p = A.rangeQuery(A.rangeFrom(new URLSearchParams({ range: st.range || "30d", from, to }), "30d"));
      p.set("limit", "100");
      ["actor", "outcome", "area"].forEach((k) => { if (st[k]) p.set(k, st[k]); });
      if (st.correlation) p.set("correlation", st.correlation);
      if (st.q.trim()) { const [k, v] = aboutQuery(st.q.trim()); p.set(k, v); }
      if (!reset && minId) p.set("before", minId);
      const data = await api("GET", "/audit?" + p.toString());
      if (mine !== asked) return;
      actors = data.actors;
      rows = reset ? data.items : rows.concat(data.items);
      if (data.items.length) minId = Math.min(...data.items.map((a) => a.id));
      hasMore = data.more;
      draw();
    }
    const keep = () => A.keepParams("#/audit", { range: st.range, from: st.range === "custom" ? from : null, to: st.range === "custom" ? to : null,
      actor: st.actor, q: st.q, outcome: st.outcome, area: st.area, correlation: st.correlation, page: st.page > 1 ? st.page : null, per: st.per !== 25 ? st.per : null });
    const reload = () => { minId = null; load(true).catch((e) => box.replaceChildren(SUI.errorBox(e, reload))); };
    more.addEventListener("click", () => load(false).catch((e) => toast(e.message, true)));
    await load(true);
    const periods = [...AUDIT_RANGES, ...(st.range === "custom" ? [["custom", "Custom dates"]] : [])].map(([id, label]) => ({ id, label }));
    const bar = SUI.filterBar({ label: "Filter the audit log", search: { placeholder: "Action, target, detail, or person:7" }, values: st, filters: [
      { id: "range", label: "Period", any: "30 days", options: periods },
      { id: "actor", label: "Who", any: "Every console user", options: actors.map((a) => ({ id: a, label: a })) },
      { id: "outcome", label: "Outcome", any: "Any outcome", options: AUDIT_OUTCOMES.map(([id, label]) => ({ id, label })) },
      { id: "area", label: "Area", any: "Every area", options: AUDIT_AREAS.map(([id, label]) => ({ id, label })) },
      { id: "correlation", label: "About", any: "Anything", options: st.correlation ? [{ id: st.correlation, label: st.correlation }] : [] },
    ], onChange: (v) => { Object.assign(st, { q: v.q || "", range: v.range || "", actor: v.actor || "", outcome: v.outcome || "", area: v.area || "", correlation: v.correlation || "" });
      if (st.range !== "custom") { from = ""; to = ""; }
      st.page = pager.page = 1; keep(); reload(); } });
    draw();
    A.frame({ title: "Audit log", trail: [SEC_ROOT, ["Audit log"]],
      lede: ["What console users and the system changed, or tried to — sign-ins, settings, access, keys, every full record opened, every change a role refused — with before and after, the reason given, and the outcome. What staff did is under ",
        el("a", { href: "#/activity" }, "Activity"), "."] }, [
      A.panel(null, null, el("div", { class: "filterbar" }, bar), summary, box, el("div", { class: "body center" }, more)),
    ]);
  }

  A.page(/^#?\/?$/, pageOverview);
  A.page(/^#\/attention$/, pageAttention);
  A.page(/^#\/live$/, pageLive);
  A.page(/^#\/activity$/, pageActivity);
  A.page(/^#\/security$/, pageSecurity);
  A.page(/^#\/audit$/, pageAudit);
  Object.assign(A, { attentionItem, seg, field, fact, people, personSelect, toolSelect, filterBar });
})();
