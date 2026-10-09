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
  async function pageOverview(params) {
    await A.toolIndex().catch(() => null);
    const [trends, attention, security, lic] = await Promise.allSettled([
      api("GET", "/trends?days=30"), A.refreshAttention(), api("GET", "/security?days=7"), api("GET", "/licences")]);
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
      kpis = el("div", { class: "kpis five" },
        A.kpi({ label: "AI spend · 30 days", icon: "wallet", value: fmt.money(tr.current.cost), tone: "gold hero",
          tip: "Metered use through the gateway, priced from the model price table when each request ran. Company plans are a fixed monthly cost on top.",
          foot: SUI.delta(change, { vs: "vs the 30 days before" }), note: subs ? `+ ${fmt.moneyShort(subs)}/mo in plans` : "vs the 30 days before",
          spark: SUI.sparkline(days.map((d) => d.cost)), href: "#/licences?tab=spend&range=30d" }),
        A.kpi({ label: "Active today", icon: "people", value: String(today.people), note: `${tr.current.people} in 30 days`,
          tip: "People who made an AI request, opened a tool from the portal, or visited an approved AI website.", href: "#/activity?tab=usage" }),
        A.kpi({ label: "Live requests", icon: "live", value: String(ov.live.length),
          foot: ov.live.length ? SUI.status("live", "In flight", { breathe: true, plain: true }) : SUI.status("idle", "Quiet", { plain: true }),
          note: `${fmt.num(today.requests)} today`, href: "#/live" }),
        A.kpi({ label: "Tools · 30 days", icon: "tools", value: String(tr.tools_used || 0),
          note: tr.top_tools.length ? "most used: " + tr.top_tools[0].tool : "none yet", href: "#/activity?tab=usage&range=30d&by=tool" }),
        A.kpi({ label: "Security · 7 days", icon: "shield", value: secCount === null ? "—" : String(secCount),
          tone: sec && sec.posture !== "healthy" ? "alert" : null,
          foot: sec ? SUI.status(sec.posture, { healthy: "Healthy", watch: "Worth a look", elevated: "Elevated" }[sec.posture], { plain: true }) : null,
          href: "#/security" }));
    } else kpis = SUI.errorBox(trends.reason, () => A.render(), "The summary couldn't load");

    const liveBox = el("div");
    function drawLive() {
      const live = (S.overview || ov).live;
      liveBox.replaceChildren(live.length ? el("div", { class: "live-strip" }, live.slice(0, 6).map((t) => el("a", { class: "lv-mini", href: "#/live" },
        SUI.status(t.streaming ? "streaming" : "waiting", t.streaming ? "Streaming" : "Waiting", { breathe: true }),
        el("strong", null, t.person || "Unknown key"), el("span", { class: "muted" }, (t.client || "a tool") + (t.device ? " · " + t.device : "")),
        el("span", { class: "elapsed u-num", "data-started": String(t.started) }, fmt.elapsed(t.started)))),
      live.length > 6 ? el("a", { class: "lv-more", href: "#/live" }, `+${live.length - 6} more`) : null)
        : el("div", { class: "live-quiet" }, SUI.status("idle", "Quiet", { plain: true }), el("span", { class: "muted" }, "Nobody is waiting on a model right now.")));
    }
    drawLive();

    const nowTab = () => el("div", { class: "grid cols-2" },
      A.panel("Needs attention", el("a", { class: "btn small quiet", href: "#/attention" }, "See all", icon("chevronRight")),
        att === null ? SUI.errorBox(attention.reason, () => A.render())
          : att.length ? el("ul", { class: "att-list" }, att.slice(0, 6).map(attentionItem))
            : SUI.stateBox({ tone: "ok", icon: "checkCircle", title: "Nothing needs attention", text: "Everything looks normal.", compact: true })),
      A.panel("Live activity", el("a", { class: "btn small quiet", href: "#/live" }, "Open Live", icon("chevronRight")), liveBox));

    const trendsTab = () => {
      if (!tr) return SUI.errorBox(trends.reason, () => A.render());
      const label = (d) => fmt.weekday(d.start);
      return el("div", { class: "grid cols-even" },
        A.panel("Usage per day", "requests, opens and visits · 30 days", el("div", { class: "body" },
          SUI.columns({ label: "Uses per day over the last 30 days", tone: 2, yName: "Uses", caption: "Times in " + SUI.tzLabel(true),
            data: tr.days.map((d) => ({ label: label(d), short: fmt.dayMonth(d.start), value: d.requests + d.opens + d.visits,
              note: `${fmt.num(d.requests)} requests · ${fmt.num(d.opens)} opens · ${fmt.num(d.visits)} visits` })) }))),
        A.panel("Spend per day", "metered API spend · 30 days", el("div", { class: "body" },
          SUI.line({ label: "Metered spend per day over the last 30 days", format: fmt.money, tick: fmt.moneyShort, yName: "Spend",
            caption: "Estimated from the price table", data: tr.days.map((d) => ({ label: label(d), short: fmt.dayMonth(d.start), value: d.cost })) }))));
    };

    const leadersTab = () => {
      if (!tr) return SUI.errorBox(trends.reason, () => A.render());
      return el("div", { class: "grid cols-even" },
        A.panel("Top tools", el("a", { class: "btn small quiet", href: "#/activity?tab=usage&range=30d&by=tool" }, "All tools", icon("chevronRight")),
          tr.top_tools.length ? SUI.barList(tr.top_tools.map((t) => ({
            label: t.tool, lead: A.toolLogo(t.tool_id, t.tool, "sm"), href: t.tool_id ? `#/tools?open=${t.tool_id}` : null,
            value: t.requests + t.opens + t.visits, display: fmt.compact(t.requests + t.opens + t.visits) + " uses",
            note: [t.requests && SUI.plural(t.requests, "request"), t.opens && SUI.plural(t.opens, "open"), t.visits && SUI.plural(t.visits, "visit"), SUI.plural(t.people, "person", "people")].filter(Boolean).join(" · ") })), { tone: 2 })
            : A.empty("Once staff start using approved tools, they'll be ranked here.", "No AI activity yet", "tools")),
        A.panel("Top people", el("a", { class: "btn small quiet", href: "#/activity?tab=usage&range=30d&by=person" }, "Everyone", icon("chevronRight")),
          tr.top_people.length ? SUI.barList(tr.top_people.map((p) => ({
            label: p.person, lead: SUI.avatar(p.person, "sm"), href: "#/people/" + p.person_id,
            value: p.cost || (p.requests + p.opens + p.visits) / 1000, display: fmt.money(p.cost),
            note: `${SUI.plural(p.tools, "tool")} · ${fmt.compact(p.requests + p.opens + p.visits)} uses` })))
            : A.empty("People appear here once they use an approved tool.", "No AI activity yet", "people")));
    };

    const opportunities = licence ? [
      ...licence.tools.filter((t) => t.idle.length && t.monthly_cost).map((t) => ({ t, text: `${SUI.plural(t.idle.length, "seat")} unused for 30 days`,
        cost: t.monthly_cost / Math.max(t.assigned, 1) * t.idle.length })),
      ...licence.tools.filter((t) => t.over_seats).map((t) => ({ t, text: `${t.assigned} people on ${SUI.plural(t.seats, "paid seat")}`, cost: null })),
    ].sort((a, b) => (b.cost || 0) - (a.cost || 0)) : null;
    const licTab = () => el("div", { class: "grid cols-even" },
      A.panel("Licence opportunities", el("a", { class: "btn small quiet", href: "#/licences" }, "Licences", icon("chevronRight")),
        opportunities === null ? SUI.errorBox(lic.reason, () => A.render())
          : opportunities.length ? el("ul", { class: "mini-list" }, opportunities.map((o) => el("li", null, A.toolLogo(o.t.id, o.t.name, "sm"),
            el("div", { class: "grow" }, el("strong", null, o.t.name), el("div", { class: "hint" }, o.text)),
            o.cost ? el("span", { class: "u-num nowrap" }, "≈ " + fmt.money(o.cost) + "/mo") : SUI.badge("over-assigned", "warn"))))
            : SUI.stateBox({ tone: "ok", icon: "checkCircle", title: "No waste found", text: "Every paid seat was used in the last 30 days.", compact: true })),
      A.panel("Renewing soon", "next 30 days", licence && licence.renewals.length ? el("ul", { class: "mini-list" }, licence.renewals.map((t) => el("li", null,
        A.toolLogo(t.id, t.name, "sm"), el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.monthly_cost != null ? fmt.money(t.monthly_cost) + " a month" : "cost not set")),
        SUI.badge(fmt.date(t.renews_on), "warn", "calendar"))))
        : SUI.stateBox({ icon: "calendar", compact: true, title: "No renewals soon", text: "Nothing renews in the next 30 days." })));

    const urgent = att ? att.filter((i) => i.severity === "high" || i.severity === "medium").length : 0;
    A.frame({ title: "Overview", lede: `Swangz AI at a glance — ${fmt.weekday(Date.now() / 1000)}. Times in ${SUI.tzLabel()}.`,
      actions: [el("a", { class: "btn", href: "#/activity" }, icon("activity"), "Activity"), el("a", { class: "btn primary", href: "#/live" }, icon("live"), "Open Live")] },
    [kpis, A.pageTabs("#/", params, [
      ["now", "Right now", nowTab, urgent || null],
      ["trends", "Trends", trendsTab],
      ["leaders", "Top tools & people", leadersTab],
      ["licences", "Licences", licTab, opportunities && opportunities.length ? opportunities.length : null],
    ])]);

    A.every(5000, async () => { await A.refreshOverview().catch(() => null); drawLive(); });
    A.every(1000, () => document.querySelectorAll(".elapsed[data-started]").forEach((n) => { n.textContent = fmt.elapsed(Number(n.dataset.started)); }));
  }

  // ------------------------------------------------------------------ Needs attention

  async function pageAttention() {
    const out = await A.refreshAttention();
    if (!out) throw new A.ApiError(0, "The list of things needing attention couldn't load");
    const groups = ["high", "medium", "low", "info"].map((sev) => [sev, out.items.filter((i) => i.severity === sev)]).filter(([, items]) => items.length);
    const names = { high: "Act now", medium: "Worth a look today", low: "When you have a moment", info: "For your information" };
    A.frame({ title: "Needs attention", lede: "Everything worth a look — security, spend, licences, access and the system — on one page, most urgent first.",
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
    A.frame({ title: "Live", lede: "What is happening across Swangz AI right now.", status: conn }, [
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
    await tick();
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
    A.frame({ title: "Activity", lede: "What staff did through Gateway: AI requests, tools opened from the portal, AI websites visited and shared-account turns — and, on the timeline, each person's sign-ins and the access changes made to them. Every other change admins made is in the Audit log.",
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
      box.replaceChildren(rows.length ? SUI.table({ columns: cols, rows, sort: ["last", "desc"], caption: "Who used what",
        href: st.by === "tool" ? (r) => (r.tool_id ? `#/tools?open=${r.tool_id}` : null) : (r) => `#/people/${r.person_id}` })
        : SUI.stateBox({ icon: "people", title: "No AI activity in this period", text: "Once staff start using approved tools, who used what appears here." }));
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
      client: el("select", { "aria-label": "Application" }, ["", "Claude Code", "Codex", "Swangz AI Studio", "Cursor", "OpenAI SDK", "Anthropic SDK", "curl", "unknown"].map((c) => el("option", { value: c }, c || "Any application"))),
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
        : SUI.stateBox({ icon: "open", title: "No tools opened in this period", text: "When staff press Open in Swangz AI, it appears here with the device and address it came from." }));
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
      : SUI.stateBox({ icon: "globe", title: "No website visits yet", text: "Staff need the Swangz AI Access browser extension installed." });
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
  async function pageSecurity(params) {
    const days = Number(params.get("days")) || 7;
    const type = params.get("type") || "";
    const data = await api("GET", "/security?days=" + days);
    const postureText = {
      healthy: ["healthy", "Healthy", "No medium or high signals in this period. Low and informational events are listed below for completeness."],
      watch: ["watch", "Worth a look", "Something here deserves a check — start with the medium items. Nothing is a finding against anyone until you've looked."],
      elevated: ["elevated", "Elevated", "A high-severity signal is open. Look at it first."],
    }[data.posture];
    // One row of filter chips instead of a tile per kind: only kinds that happened, plus "All".
    const total = Object.values(data.counts).reduce((a, n) => a + (n || 0), 0);
    const chip = (k, label, ic, n) => el("a", { class: "sec-chip" + (type === k ? " on" : ""), href: `#/security?days=${days}` + (k ? "&type=" + k : ""), "aria-current": type === k ? "true" : null },
      ic ? icon(ic) : null, el("span", null, label), el("span", { class: "n u-num" }, String(n)));
    const kinds = Object.entries(SEC_TYPES).filter(([k]) => data.counts[k] || type === k);
    const counts = [chip("", "All", null, total), ...kinds.map(([k, [label, ic]]) => chip(k, label, ic, data.counts[k] || 0))];
    const events = data.events.filter((e) => !type || e.type === type);
    const list = events.length ? el("ul", { class: "sec-list" }, events.map((e) => {
      const [state, label] = SEV[e.severity] || SEV.info;
      return el("li", { class: "sec sev-" + e.severity },
        el("div", { class: "sec-head" }, el("span", { class: "u-label" }, (SEC_TYPES[e.type] || [e.title])[0]), SUI.status(state, label),
          el("span", { class: "grow" }), el("time", { class: "hint", title: fmt.stamp(e.ts) }, fmt.ago(e.ts))),
        el("p", { class: "sec-text" }, e.text),
        el("div", { class: "ev-meta" },
          e.person ? A.personLink(e.person_id, e.person) : null,
          e.tool ? el("span", { class: "obj" }, icon("tools"), e.tool) : null,
          e.device ? el("span", { class: "obj" }, icon("device"), e.device) : null,
          e.ip ? A.where(e.ip, e.place) : null),
        e.evidence ? el("div", { class: "sec-foot" }, SUI.evidence(e.evidence)) : null,
        el("div", { class: "row sec-go" },
          A.can("trust") && ["high", "medium", "low"].includes(e.severity) ? el("button", { class: "btn small quiet", onclick: () => A.openIncident({
            title: e.title + (e.person ? " — " + e.person : ""), severity: e.severity === "high" ? "high" : "medium", source: "security:" + e.type,
            person: e.person_id, request: (e.href || "").startsWith("#/records/") ? e.href.slice(10) : null }) }, icon("flag"), "Open incident") : null,
          e.href ? el("a", { class: "btn small", href: e.href }, "Investigate", icon("chevronRight")) : null));
    })) : SUI.stateBox({ tone: "ok", icon: "shield", title: type ? "None of these" : "No security events", text: type ? "Nothing of this kind in this period." : "Everything looks normal." });
    A.frame({ title: "Security", lede: "Signals worth a look, each with how sure the evidence is. Severity says what to check first — it isn't a judgement on anyone.",
      status: SUI.status(postureText[0], postureText[1], { plain: true }),
      actions: seg([["1", "24 hours"], ["7", "7 days"], ["30", "30 days"]], String(days), (v) => { location.hash = `#/security?days=${v}` + (type ? "&type=" + type : ""); }, "Period") }, [
      el("section", { class: "posture p-" + data.posture },
        el("div", { class: "posture-main" }, el("div", { class: "u-label" }, "Current posture"),
          el("div", { class: "posture-state" }, SUI.status(postureText[0], postureText[1])), el("p", null, postureText[2])),
        el("div", { class: "posture-facts" },
          el("div", null, el("span", { class: "k" }, "Credentials in requests"), el("span", { class: "v" }, data.settings.block_secrets ? "Refused" : "Let through, flagged")),
          el("div", null, el("span", { class: "k" }, "Rate limit"), el("span", { class: "v" }, data.settings.rate_per_min ? data.settings.rate_per_min + " a minute per person" : "Off")),
          el("div", null, el("span", { class: "k" }, "Kill switch"), el("span", { class: "v" }, data.settings.paused ? "AI is paused" : "Ready")),
          el("a", { class: "btn small", href: "#/settings?tab=access" }, "Change in Settings"))),
      el("nav", { class: "sec-chips", "aria-label": "Filter by kind" }, counts,
        kinds.length ? null : el("span", { class: "hint" }, "Nothing of any kind in this period.")),
      A.panel(type ? SEC_TYPES[type][0] : "Events", SUI.plural(events.length, "event") + ` · last ${days === 1 ? "24 hours" : days + " days"}`, list),
    ]);
  }

  // ------------------------------------------------------------------ Audit

  async function pageAudit(params) {
    const st = { range: A.rangeFrom(params, "30d"), actor: params.get("actor") || "", q: params.get("q") || "", outcome: params.get("outcome") || "",
      area: params.get("area") || "", correlation: params.get("correlation") || "" };
    const body = el("div");
    const more = el("button", { class: "btn", hidden: true }, "Load older");
    const q = el("input", { type: "search", placeholder: "Search actions, targets, details…", value: st.q, "aria-label": "Search the audit log" });
    const actor = el("select", { class: "fb-select", "aria-label": "Who" }, el("option", { value: "" }, "Every console user"));
    const summary = el("div", { class: "list-meta", role: "status" });
    let minId = null, rows = [];
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
    async function load(reset) {
      const p = A.rangeQuery(st.range);
      p.set("limit", "100");
      ["actor", "q", "outcome", "area", "correlation"].forEach((k) => { if (st[k]) p.set(k, st[k]); });
      if (!reset && minId) p.set("before", minId);
      const data = await api("GET", "/audit?" + p.toString());
      if (actor.options.length === 1) data.actors.forEach((a) => actor.append(el("option", { value: a }, a)));
      actor.value = st.actor;
      rows = reset ? data.items : rows.concat(data.items);
      if (data.items.length) minId = Math.min(...data.items.map((a) => a.id));
      more.hidden = !data.more;
      summary.replaceChildren(el("span", null, SUI.plural(rows.length, "entry", "entries") + (data.more ? " so far" : "")),
        el("span", null, "can't be edited or cleared from the console"), el("span", null, "times in " + SUI.tzLabel(true)));
      body.replaceChildren(rows.length ? SUI.table({ caption: "Audit log", columns: cols, rows, sort: ["ts", "desc"] })
        : SUI.stateBox({ icon: "audit", title: "No audit entries", text: "Nothing matches in this period." }));
    }
    const apply = () => {
      minId = null;
      A.keepParams("#/audit", { range: st.range.preset, from: st.range.preset === "custom" ? st.range.from : null, to: st.range.preset === "custom" ? st.range.to : null,
        actor: st.actor, q: st.q, outcome: st.outcome, area: st.area, correlation: st.correlation });
      load(true).catch((e) => body.replaceChildren(SUI.errorBox(e, apply)));
    };
    actor.addEventListener("change", () => { st.actor = actor.value; apply(); });
    const outcome = el("select", { "aria-label": "Outcome" }, [["", "Any outcome"], ["ok", "Done"], ["denied", "Refused"], ["no-op", "Changed nothing"]].map(([v, t]) => el("option", { value: v }, t)));
    outcome.value = st.outcome;
    const area = el("select", { "aria-label": "Area" }, [["", "Every area"], ["govern", "Govern"], ["money", "Money"], ["trust", "Trust"], ["emergency", "Emergency"], ["admin", "Administration"]].map(([v, t]) => el("option", { value: v }, t)));
    area.value = st.area;
    const corr = el("input", { type: "text", value: st.correlation, placeholder: "e.g. person:7, policy:2, incident:4", "aria-label": "About" });
    outcome.addEventListener("change", () => { st.outcome = outcome.value; apply(); });
    area.addEventListener("change", () => { st.area = area.value; apply(); });
    corr.addEventListener("change", () => { st.correlation = corr.value.trim(); apply(); });
    q.addEventListener("input", SUI.debounce(() => { st.q = q.value.trim(); apply(); }, 300));
    more.addEventListener("click", () => load(false).catch((e) => toast(e.message, true)));
    await load(true);
    A.frame({ title: "Audit log", lead: el("span", { class: "audit-mark", "aria-hidden": "true" }, icon("audit")),
      lede: "Changes made to Gateway by console users — sign-ins, settings, access changes, revoked keys, every full record opened, and every change someone's role refused — with what it was before and after, and why when they said. What staff did is under Activity." }, [
      A.panel(null, null, (() => {
        const fb = filterBar({ search: q, extra: actor,
          fields: [{ key: "outcome", label: "Outcome", control: outcome }, { key: "area", label: "Area", control: area }, { key: "correlation", label: "About", control: corr }],
          clear: (keys) => { keys.forEach((k) => { st[k] = ""; ({ outcome, area, correlation: corr })[k].value = ""; }); fb.draw(); apply(); },
          range: SUI.rangeControl({ preset: st.range.preset, from: st.range.from, to: st.range.to, presets: ["today", "7d", "30d", "month", "custom"], onChange: (r) => { st.range = r; apply(); } }) });
        [outcome, area, corr].forEach((c) => c.addEventListener("change", () => fb.draw()));
        return fb.node;
      })(),
        summary, body, el("div", { class: "body center" }, more)),
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
