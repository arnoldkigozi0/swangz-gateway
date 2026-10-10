"use strict";
/* Money and settings: what Swangz pays for and whether it's used, what the metered AI cost and why,
   and the switches that govern the whole gateway. */
(() => {
  const { el, icon, fmt, toast } = SUI;
  const A = SWA;
  const { S, api } = A;
  const usd = (v) => "$" + (Number.isInteger(v * 100) ? v.toFixed(2) : String(v));

  // ------------------------------------------------------------------ Licences & spend

  async function pageLicences(params) {
    await A.toolIndex().catch(() => null);
    A.frame({ title: "Licences & spend", lede: "What Swangz pays for, whether it's used, and what metered AI cost — with how each number is worked out.",
      actions: el("a", { class: "btn", href: A.gadmin("/export.csv") }, icon("download"), "Export activity CSV") },
    A.pageTabs("#/licences", params, [
      ["licences", "Licences", () => licencesTab()],
      ["spend", "What cost us money?", () => spendTab(params)],
      ["renewals", "Renewals", () => renewalsTab()],
    ]));
  }

  async function licencesTab() {
    const lic = await api("GET", "/licences");
    const s = lic.summary;
    const owner = A.can("money");
    const paid = lic.tools.filter((t) => t.monthly_cost);
    const activeSeats = lic.tools.reduce((n, t) => n + t.active, 0);
    const assignedSeats = lic.tools.reduce((n, t) => n + t.assigned, 0);
    const rows = lic.tools.map((t) => ({ ...t, util: t.assigned ? t.active / t.assigned : null }));
    const table = rows.length ? SUI.table({ caption: "Licence utilisation", rows, sort: ["monthly_cost", "desc"], columns: [
      { key: "name", label: "Tool", lead: true, render: (t) => el("a", { class: "u-cell", href: `#/tools?open=${t.id}&tab=billing` }, A.toolLogo(t.id, t.name, "sm"),
        el("div", null, el("strong", null, t.name), el("span", { class: "sub" }, t.plan || (t.state === "none" ? (t.kind === "site" ? "no plan" : "API key") : t.state)))) },
      { key: "assigned", label: "Given / seats", num: true, render: (t) => el("span", null, String(t.assigned) + (t.seats ? " / " + t.seats : ""),
        t.over_seats ? el("span", { class: "sub" }, SUI.status("blocked", "over-assigned", { plain: true })) : null) },
      { key: "util", label: "Active · 30 days", sort: (t) => (t.util === null ? -1 : t.util), render: (t) => (t.assigned ? el("div", { class: "util" },
        el("span", { class: "u-num" }, `${t.active} of ${t.assigned}`), el("span", { class: "util-pct u-num" }, Math.round(t.util * 100) + "%"), utilBar(t.active, t.assigned))
        : el("span", { class: "hint" }, "no one given it yet")) },
      { key: "monthly_cost", label: "Cost / month", num: true, render: (t) => (t.monthly_cost != null ? fmt.money(t.monthly_cost) : "—") },
      { key: "cost_per_active", label: "Per active user", num: true, render: (t) => (t.cost_per_active != null ? fmt.money(t.cost_per_active) : "—"), hideSm: true },
      { key: "idle", label: "Not used in 30 days", sort: (t) => t.idle.length, render: (t) => (t.idle.length ? el("div", { class: "idle" }, t.idle.map((p) => el("span", { title: p.last ? "last used " + fmt.ago(p.last) : "never used" }, p.name,
        owner ? el("button", { type: "button", "aria-label": `Reclaim ${t.name} from ${p.name}`, onclick: async () => {
          const ok = await A.confirmAction(`Take ${t.name} back from ${p.name}?`, "Their access is removed so the seat can go to someone who needs it. If they have it through their team, change that on the Tools page.", "Take it back", true);
          if (!ok) return;
          try { await api("DELETE", `/people/${p.id}/tools/${t.id}`); toast("Seat freed."); A.render(); } catch (e) { toast(e.message, true); }
        } }, "Reclaim") : null))) : t.assigned ? SUI.status("ok", "All in use", { plain: true }) : el("span", { class: "hint" }, "—")) },
    ] }) : SUI.stateBox({ icon: "licences", title: "No licences yet", text: "Subscribe on the Tools page, then give the tool to people. Seats and their use appear here." });
    return [
      el("div", { class: "kpis four" },
        A.kpi({ label: "Company plans", icon: "licences", value: fmt.money(s.subscriptions_month) + "/mo", tone: "gold hero",
          note: `${SUI.plural(paid.length, "paid plan")} · metered spend is under What cost us money?`,
          tip: "The monthly cost set on each subscription (Tools → a tool → Subscription). Metered API use is separate: What cost us money?" }),
        A.kpi({ label: "Active seats", icon: "people", value: `${activeSeats}`, note: `of ${assignedSeats} given out · used in 30 days` }),
        A.kpi({ label: "Idle seats", icon: "clock", value: String(s.idle_seats), tone: s.idle_seats ? "alert" : null, note: s.idle_seats ? "given, not used in 30 days" : "everyone given a tool is using it" }),
        A.kpi({ label: "Estimated waste", icon: "trendDown", value: fmt.money(s.idle_cost) + "/mo", note: paid.length ? "idle seats × cost per seat" : "set plan costs to estimate",
          tip: "For each paid tool: monthly cost ÷ people given it × people who haven't used it in 30 days. An estimate — vendors bill differently." })),
      A.panel("Utilisation", "seats paid for against real use — reclaim the ones nobody opens", table,
        el("div", { class: "body hint" }, "Used = opened from the portal, visited through the browser extension, or used through the gateway in the last 30 days.")),
    ];
  }

  function utilBar(value, total) {
    const fill = el("i");
    const pct = Math.min(100, (value / (total || 1)) * 100);
    fill.style.width = pct + "%";
    return el("div", { class: "bar use" + (pct < 50 ? " low" : "") }, fill);
  }

  /* What cost us money: metered spend for a window, every way it breaks down, against the window before. */
  async function spendTab(params) {
    const st = { range: A.rangeFrom(params, "30d"), by: params.get("by") || "person" };
    const box = el("div", { class: "stack-lg" });
    const LABEL = { person: "Person", tool: "Tool", department: "Department", model: "Model" };
    async function load() {
      box.classList.add("refreshing");
      const d = await api("GET", "/spend?" + A.rangeQuery(st.range).toString());
      box.classList.remove("refreshing");
      const rows = { person: d.people, tool: d.tools, department: d.departments, model: d.models }[st.by];
      const label = (r) => {
        if (st.by === "person") return r.key ? A.personLink(r.key, r.label) : el("span", { class: "muted" }, r.label);
        if (st.by === "tool") return A.toolLink(r.tool_id, r.label, "sm");
        if (st.by === "model") return el("span", { class: "mono" }, r.label);
        return el("strong", null, r.label);
      };
      const total = d.total || 0;
      // Sharp rises read as one line, not a panel of tiles; the full list opens on demand.
      let rising = null;
      if (d.increases.length) {
        const chip = (x) => el("span", { class: "rise" }, el("strong", null, x.label), el("span", { class: "faint" }, LABEL[x.dimension].toLowerCase()),
          x.new ? SUI.badge("new", "warn") : SUI.delta(x.change));
        const all = el("ul", { class: "mini-list rise-all", hidden: true }, d.increases.map((x) => el("li", null,
          el("span", { class: "mini-ic warn" }, icon("trendUp")),
          el("div", { class: "grow" }, el("strong", null, x.label), el("div", { class: "hint" }, `${LABEL[x.dimension]} · ${fmt.money(x.previous)} → ${fmt.money(x.cost)}`)),
          x.new ? SUI.badge("new", "warn") : SUI.delta(x.change))));
        const more = d.increases.length > 3 ? el("button", { class: "btn link", type: "button", "aria-expanded": "false", onclick: () => {
          all.hidden = !all.hidden; more.setAttribute("aria-expanded", all.hidden ? "false" : "true");
          more.textContent = all.hidden ? `See all ${d.increases.length}` : "Hide the list";
        } }, `See all ${d.increases.length}`) : null;
        rising = el("section", { class: "callout warn" },
          el("div", { class: "callout-row" }, icon("trendUp"), el("span", { class: "callout-k" }, "Rising fast"),
            el("div", { class: "rises" }, d.increases.slice(0, 3).map(chip)), more),
          el("div", { class: "hint" }, "At least half again the period before, and $1 more — worth a look, not necessarily a problem."), all);
      }
      box.replaceChildren(...[
        el("div", { class: "kpis four" },
          A.kpi({ label: "Metered AI spend", icon: "wallet", value: fmt.money(total), tone: "gold hero",
            foot: el("span", { class: "row" }, SUI.delta(d.change), el("span", { class: "note" }, `vs ${fmt.money(d.previous_total)} the period before`)),
            tip: "Each request is priced from the model price table the moment it runs. Vendor invoices aren't imported." }),
          A.kpi({ label: "Requests", icon: "spark", value: fmt.num(d.requests), note: total && d.requests ? `≈ ${fmt.money(total / d.requests)} each` : "in this period" }),
          A.kpi({ label: "Unpriced", icon: "info", value: fmt.num(d.unpriced), href: d.unpriced ? "#/settings?tab=providers&section=prices" : null,
            note: d.unpriced ? "requests with no price — price them" : "every model has a price" }),
          A.kpi({ label: "Company plans", icon: "licences", value: fmt.money(d.subscriptions_month) + "/mo", href: "#/licences?tab=licences",
            note: "fixed monthly, not metered — seats and idle ones under Licences" })),
        rising,
        d.series.length > 1 ? A.panel("Spend per day", "estimated from the price table · " + SUI.tzLabel(true), el("div", { class: "body" },
          SUI.line({ label: "Metered spend per day", format: fmt.money, tick: fmt.moneyShort, yName: "Spend",
            data: d.series.map((x) => ({ label: fmt.weekday(x.start), short: fmt.dayMonth(x.start), value: x.cost, note: SUI.plural(x.requests, "request") })) }))) : null,
        A.panel("Where it went", A.seg([["person", "Person"], ["tool", "Tool"], ["department", "Department"], ["model", "Model"]], st.by, (v) => { st.by = v; apply(); }, "Break down by"),
          rows.length ? SUI.table({ caption: "Spend by " + LABEL[st.by].toLowerCase(), rows, sort: ["cost", "desc"],
            href: st.by === "person" ? (r) => (r.key ? "#/people/" + r.key : null) : st.by === "tool" ? (r) => (r.tool_id ? `#/tools?open=${r.tool_id}` : null) : null,
            columns: [
              { key: "label", label: LABEL[st.by], lead: true, render: label },
              { key: "cost", label: "Spend", num: true, render: (r) => el("span", null, fmt.money(r.cost), el("span", { class: "sub" }, total ? Math.round(r.cost / total * 100) + "% of total" : "")) },
              { key: "previous", label: "Period before", num: true, render: (r) => fmt.money(r.previous), hideSm: true },
              { key: "change", label: "Change", num: true, sort: (r) => (r.change === null ? -Infinity : r.change), render: (r) => SUI.delta(r.change, { none: r.cost ? "new" : "—" }) },
              { key: "requests", label: "Requests", num: true },
              { key: "unpriced", label: "Unpriced", num: true, render: (r) => (r.unpriced ? SUI.status("waiting", String(r.unpriced), { plain: true }) : "—"), hideSm: true }] })
            : SUI.stateBox({ icon: "wallet", title: "No spend in this period", text: "Metered spend appears once requests go through the gateway." })),
        el("details", { class: "explain" },
          el("summary", null, icon("info"), "How spend is worked out", el("span", { class: "hint" }, "estimated, unpriced, plans, and what isn't here")),
          el("div", { class: "method" },
            el("div", null, SUI.status("ok", "Estimated", { plain: true }), el("p", null, "Each request through the gateway is priced from the model price table (Settings → Model prices) the moment it runs, using the tokens the provider reports. Changing a price later doesn't change past requests.")),
            el("div", null, SUI.status("waiting", "Unpriced", { plain: true }), el("p", null, "A model missing from the price table has no cost, so spend is understated until it's priced. Voice, image and video are metered in the service's own units.")),
            el("div", null, SUI.status("info", "Plans", { plain: true }), el("p", null, "Company plans are the fixed monthly cost set on each subscription — not metered here, and not split by person.")),
            el("div", null, SUI.status("none", "Not here", { plain: true }), el("p", null, "Vendor invoices aren't imported, and a shared account's own credit use is matched by turn, not priced."))))].filter(Boolean));
    }
    const apply = () => {
      A.keepParams("#/licences", { tab: "spend", range: st.range.preset, from: st.range.preset === "custom" ? st.range.from : null, to: st.range.preset === "custom" ? st.range.to : null, by: st.by === "person" ? null : st.by });
      load().catch((e) => box.replaceChildren(SUI.errorBox(e, apply)));
    };
    await load();
    return [el("div", { class: "filterbar card" }, SUI.rangeControl({ preset: st.range.preset, from: st.range.from, to: st.range.to, presets: ["today", "7d", "30d", "month", "custom"],
      onChange: (r) => { st.range = r; apply(); } })), box];
  }

  /* Renewals: the commitments coming up. Spend lives under What cost us money?, and each person's budget on their profile. */
  async function renewalsTab() {
    const lic = await api("GET", "/licences");
    const soon = lic.renewals.length ? el("ul", { class: "mini-list" }, lic.renewals.map((t) => el("li", null, A.toolLogo(t.id, t.name, "sm"),
      el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.monthly_cost != null ? fmt.money(t.monthly_cost) + " a month" : "cost not set")),
      SUI.badge("renews " + fmt.date(t.renews_on), "warn", "calendar")))) : SUI.stateBox({ icon: "calendar", compact: true, title: "No renewals soon", text: "Nothing renews in the next 30 days." });
    const plans = lic.tools.filter((t) => t.state !== "none" && t.state !== "cancelled");
    const all = plans.length ? SUI.table({ caption: "Every plan and when it renews", rows: plans, sort: ["renews_on", "asc"], href: (t) => `#/tools?open=${t.id}&tab=billing`, columns: [
      { key: "name", label: "Tool", lead: true, render: (t) => el("a", { class: "u-cell", href: `#/tools?open=${t.id}&tab=billing` }, A.toolLogo(t.id, t.name, "sm"),
        el("div", null, el("strong", null, t.name), el("span", { class: "sub" }, t.plan || "plan not named"))) },
      { key: "seats", label: "Seats", num: true, render: (t) => (t.seats ? String(t.seats) : "—"), hideSm: true },
      { key: "monthly_cost", label: "Cost / month", num: true, render: (t) => (t.monthly_cost != null ? fmt.money(t.monthly_cost) : "—") },
      { key: "renews_on", label: "Renews", num: true, sort: (t) => t.renews_on || Infinity,
        render: (t) => (t.renews_on ? fmt.date(t.renews_on) : el("span", { class: "faint" }, "no date set")) },
    ] }) : SUI.stateBox({ icon: "licences", compact: true, title: "No plans yet", text: "Set a subscription on a tool (Tools → a tool → Subscription) and its renewal shows here." });
    const undated = plans.filter((t) => !t.renews_on).length;
    return [
      el("div", { class: "grid cols-even" },
        A.panel("Renewing in the next 30 days", null, soon),
        A.panel("Before a renewal", null, el("div", { class: "body stack" },
          el("p", { class: "hint" }, "Check the plan is still used: idle seats and what reclaiming them saves are under ", el("a", { href: "#/licences?tab=licences" }, "Licences"), "."),
          el("p", { class: "hint" }, "Metered spend by person, tool and model is under ", el("a", { href: "#/licences?tab=spend" }, "What cost us money?"), "; each person's budget is on their profile."),
          undated ? el("p", { class: "hint" }, SUI.status("waiting", `${SUI.plural(undated, "plan")} with no renewal date`, { plain: true }), " — set it on the tool's Subscription tab so it shows up here in time.") : null))),
      A.panel("Every plan", "soonest first", all),
    ];
  }

  // ------------------------------------------------------------------ Settings

  /* Settings: a grouped rail of categories beside the category. Each category opens with a header — what it is,
     whether this role can change it, and (for the two that have them) its sections, kept in ?section= so a refresh
     or a shared link lands in the same place. Choosing a category by hand opens its first section. Links from before
     the categories (?tab=purposes, ?tab=prices, …) still land where they used to point. */
  const SETTINGS_OLD = { safety: ["access"], security: ["access"], governance: ["purpose"], purposes: ["purpose", "purposes"], locations: ["purpose", "locations"],
    addresses: ["providers", "addresses"], prices: ["providers", "prices"], rates: ["providers", "rates"] };
  // id → label, icon, what it covers, and the areas its controls belong to (for "view only"; null = your own account)
  const SETTINGS_CATS = {
    access: ["Access & privacy", "shield", "How long records are kept, what is kept, the protections on every request, and what staff can do for themselves."],
    purpose: ["Purpose & location", "target", "What requests can be for, and how a place is named — networks Swangz names first, then the offline location table."],
    providers: ["Providers & pricing", "wallet", "Where each provider is reached, and the prices and rates every cost estimate is worked out from."],
    browsers: ["Company browsers", "monitor", "Where shared accounts' company browsers run, and signing each one in to its tool."],
    emergency: ["Emergency", "stop", "The stops: everything at once, one provider, or the company browsers. Each acts the moment it's confirmed, and is written to the audit log."],
    users: ["Console users", "users", "Who can sign in to the control room, and what each role can change. Everyone here can see everything."],
    account: ["Your account", "user", "The console account you're signed in with."],
  };
  // A compact, factual reading of the saved configuration, before its editable controls.
  function settingSummary(items) {
    return el("dl", { class: "set-summary", "aria-label": "Current configuration" }, items.map(([label, value, detail]) =>
      el("div", null, el("dt", null, label), el("dd", { class: "summary-value" }, value), detail ? el("dd", { class: "summary-detail" }, detail) : null)));
  }
  function settingIntro(title, text) {
    return el("div", { class: "set-intro" }, el("h3", null, title), el("p", null, text));
  }
  const SET_SECTIONS = {
    records: ["Keep the records you need", "Set request retention and shorter limits for individual record types. Changes apply when saved; reducing a retention period can delete older records during the next hourly cleanup."],
    safeguards: ["Protect every API request", "Choose how the gateway handles credentials and repeated requests. These controls apply to traffic that passes through the gateway."],
    staff: ["Staff devices, privacy and support", "Control self-service device connections, website-gate logging and the help contact shown to staff."],
    purposes: ["Classify the work", "Manage purpose labels and test the rules that suggest them. Labels describe a request; they do not grant access."],
    locations: ["Understand where requests come from", "Name known networks and review the offline location data. A named network is exact; an address-based city is always approximate."],
    addresses: ["Connect tools to the gateway", "Copy the gateway addresses and check which providers have a company key. Configuration is separate from a provider's live health."],
    prices: ["Price chat and coding requests", "Rates are in US dollars per million tokens. New requests use the saved price; historical records keep their original estimate."],
    rates: ["Price voice, images and video", "Each service uses its own billing unit. Effective dates preserve the rate used for every estimate; these rates are separate from subscription costs."],
  };
  async function pageSettings(params) {
    const old = SETTINGS_OLD[params.get("tab")];
    if (old) {
      params.set("tab", old[0]);
      if (old[1]) params.set("section", old[1]);
      A.S.route = "#/settings?" + params.toString();
      history.replaceState(null, "", A.S.route);
    }
    const st = await api("GET", "/settings");
    const mine = A.S.me.can || (A.isOwner() ? ["admin"] : []);
    const access = [...new Set(["retention_days", "store_bodies", "block_secrets", "rate_per_min", "staff_self_keys", "gate_log_full", "support_contact"]
      .map((k) => (st.areas || {})[k] || "admin"))];
    const areas = { access, purpose: ["govern", "trust", "admin"], providers: ["money"], browsers: ["govern"], emergency: ["emergency"], users: ["admin"], account: null };
    const editable = (id) => !areas[id] || areas[id].some((a) => A.can(a));
    const partly = (id) => areas[id] && editable(id) && !areas[id].every((a) => A.can(a));
    // what the rail can honestly say about a category: a stop in force, or that this role can only look
    const stopped = st.paused ? "AI paused" : st.disabled_providers.length ? `${st.disabled_providers.length} off` : st.workspace_paused ? "Browsers paused" : null;
    const marks = {};
    Object.keys(SETTINGS_CATS).forEach((id) => {
      if (id === "emergency" && stopped) marks[id] = el("span", { class: "pt-mark bad" }, stopped);
      else if (!editable(id)) marks[id] = el("span", { class: "pt-mark lock", title: "View only for your role" }, icon("lock"), el("span", { class: "u-sr" }, "(view only)"));
    });
    // a category's header: where you are, what it covers, what your role can do here, and its sections
    const head = (id, sections) => {
      const [label, ic, about] = SETTINGS_CATS[id];
      const note = !editable(id) ? el("span", { class: "set-chip" }, icon("lock"), "View only")
        : partly(id) ? el("span", { class: "set-chip" }, icon("lock"), "Some of these need another role") : null;
      return el("header", { class: "set-head" + (id === "emergency" ? " danger" : "") + (sections ? " has-sections" : "") },
        el("span", { class: "set-head-ic", "aria-hidden": "true" }, icon(ic)),
        el("div", { class: "set-head-text" }, el("div", { class: "set-head-title" }, el("h2", null, label), note), el("p", null, about)),
        sections || null);
    };
    const category = (id, build) => async () => [head(id), ...[].concat(await build()).filter(Boolean)];
    // a category with sections: one level only, read from the address when it is first shown
    const sectioned = (id, list) => () => {
      const explained = list.map(([key, label, build]) => [key, label, async () => [settingIntro(...SET_SECTIONS[key]), ...[].concat(await build()).filter(Boolean)]]);
      const t = A.pageTabs("#/settings", new URLSearchParams(location.hash.split("?")[1] || ""), explained, { param: "section", label: SETTINGS_CATS[id][0] + " sections", help: false, split: true });
      return [head(id, el("div", { class: "set-sections" }, t.bar)), t.body];
    };
    A.frame({ title: "Settings", actions: el("a", { class: "btn", href: "#/audit" }, icon("audit"), "Review changes"), lede: mine.length ? `Configure access, records and company services. Signed in as ${A.roleLabel()}; changes are recorded in the audit log.`
      : "You're a viewer: you can see every setting, but not change them." },
    el("div", { class: "settings-ws" }, A.pageTabs("#/settings", params, [
      ["access", SETTINGS_CATS.access[0], sectioned("access", [
        ["records", "Records", () => safetyTab("records")],
        ["safeguards", "Safeguards", () => safetyTab("safeguards")],
        ["staff", "Staff controls", () => safetyTab("staff")],
      ])],
      ["purpose", SETTINGS_CATS.purpose[0], sectioned("purpose", [
        ["purposes", "Purposes", () => purposesTab()],
        ["locations", "Locations", () => locationsTab()],
      ])],
      ["providers", SETTINGS_CATS.providers[0], sectioned("providers", [
        ["addresses", "Connections", () => addressesTab()],
        ["prices", "Model prices", () => pricesTab(A.can("money"))],
        ["rates", "Media rates", () => ratesTab()],
      ])],
      ["browsers", SETTINGS_CATS.browsers[0], category("browsers", () => workspaceTab(A.can("govern")))],
      ["emergency", SETTINGS_CATS.emergency[0], category("emergency", emergencyTab)],
      A.can("admin") && ["users", SETTINGS_CATS.users[0], category("users", consoleUsersTab)],
      ["account", SETTINGS_CATS.account[0], category("account", accountTab)],
    ], { vertical: true, clears: ["section"], label: "Settings categories", help: false,
      railDescriptions: { access: "Records, privacy and safeguards", purpose: "Labels, networks and location", providers: "Connections and cost estimates", browsers: "Hosts and shared workspaces", emergency: "Pause access and services", users: "Console access and roles", account: "Profile and password" },
      icons: Object.fromEntries(Object.entries(SETTINGS_CATS).map(([id, c]) => [id, c[1]])), marks,
      groups: [["Gateway", ["access", "purpose", "providers", "browsers"]], [null, ["emergency"]], ["Console access", ["users", "account"]]] })));
  }

  /* Access & records: grouped settings, one row each, and one save bar that appears only when something has
     changed. Each control is open only to the role that owns it (Settings areas come from the server). */
  async function safetyTab(section = "records") {
    const st = await api("GET", "/settings");
    const off = (k) => !(st.areas ? A.can(st.areas[k]) : A.isOwner());
    const retention = el("input", { type: "number", min: "0", step: "1", value: String(st.retention_days), disabled: off("retention_days"), "aria-label": "Keep records for, in days" });
    const ret = {};
    [["retention_bodies_days", "Full bodies"], ["retention_site_days", "Website visits"], ["retention_launch_days", "Tools opened"], ["retention_audit_days", "Audit log"]].forEach(([k, l]) => {
      ret[k] = el("input", { type: "number", min: "0", step: "1", value: String(st[k] || 0), disabled: off(k), "aria-label": l + ", days" });
    });
    const storeBodies = A.switchInput(st.store_bodies, off("store_bodies"), "Keep full request and response bodies");
    const blockSecrets = A.switchInput(st.block_secrets, off("block_secrets"), "Refuse requests that contain credentials");
    const selfKeys = A.switchInput(st.staff_self_keys, off("staff_self_keys"), "Staff can connect their own devices");
    const gateFull = A.switchInput(st.gate_log_full, off("gate_log_full"), "Website gate: full-content logging");
    const rate = el("input", { type: "number", min: "0", step: "1", value: String(st.rate_per_min || 0), disabled: off("rate_per_min"), "aria-label": "Requests per person per minute" });
    const contact = el("input", { type: "text", maxlength: "200", value: st.support_contact || "", placeholder: "e.g. IT desk — it@swangzavenue.com, ext. 204", disabled: off("support_contact"), "aria-label": "Who staff contact for help" });
    const all = () => ({ retention_days: retention.value, ...Object.fromEntries(Object.entries(ret).map(([k, x]) => [k, x.value])),
      store_bodies: storeBodies.checked, block_secrets: blockSecrets.checked, staff_self_keys: selfKeys.checked,
      gate_log_full: gateFull.checked, rate_per_min: rate.value, support_contact: contact.value });
    const first = all();
    // send only what changed, so a role is never refused for a setting it didn't touch
    const values = () => Object.fromEntries(Object.entries(all()).filter(([k, v]) => String(v) !== String(first[k])));
    let saved = JSON.stringify(all());
    const err = el("span", { class: "err", role: "alert" });
    const reason = el("input", { type: "text", maxlength: "200", placeholder: "Why (optional, kept in the audit log)", "aria-label": "Reason for the change" });
    const discard = el("button", { class: "btn quiet", type: "button" }, "Discard");
    const save = el("button", { class: "btn primary", type: "button" }, "Save changes");
    const bar = el("div", { class: "savebar", hidden: true, role: "region", "aria-label": "Unsaved changes" },
      el("span", { class: "msg" }, el("i", { "aria-hidden": "true" }), "You have unsaved changes"), err, reason, discard, save);
    const check = () => { bar.hidden = JSON.stringify(all()) === saved; A.setDirty(() => bar.isConnected && !bar.hidden); };
    A.setDirty(() => bar.isConnected && !bar.hidden);
    // a number's problem is said beside the number, before anything is sent
    const days = { retention_days: retention, rate_per_min: rate, ...ret };
    const fieldErr = {};
    Object.entries(days).forEach(([k, x]) => { fieldErr[k] = el("span", { class: "field-err", role: "alert", id: "err-" + k }); x.setAttribute("aria-describedby", "err-" + k); });
    const problems = () => {
      const out = {};
      Object.entries(days).forEach(([k, x]) => {
        const v = x.value.trim();
        if (!/^\d+$/.test(v)) out[k] = "A whole number, 0 or more.";
        else if (k === "retention_audit_days" && Number(v) > 0 && Number(v) < 365) out[k] = "At least 365 days, or 0 to keep it forever.";
      });
      return out;
    };
    const showProblems = (found) => Object.entries(fieldErr).forEach(([k, node]) => {
      node.textContent = found[k] || "";
      days[k].setAttribute("aria-invalid", found[k] ? "true" : "false");
    });
    [retention, rate, contact, ...Object.values(ret)].forEach((x) => x.addEventListener("input", () => { check(); if (x.getAttribute("aria-invalid") === "true") showProblems(problems()); }));
    Object.values(days).forEach((x) => x.addEventListener("blur", () => showProblems(problems())));
    [storeBodies, blockSecrets, selfKeys, gateFull].forEach((x) => x.addEventListener("change", check));
    discard.addEventListener("click", () => { A.setDirty(null); A.render(); });
    // what deserves a second look before it's saved: shorter keeping (older records go within the hour),
    // fewer bodies kept, wider logging of staff
    function consequences(v) {
      const out = [];
      const shorter = (k) => k in v && Number(v[k]) > 0 && (Number(first[k]) === 0 || Number(v[k]) < Number(first[k]));
      if (shorter("retention_days")) out.push(`Request records older than ${v.retention_days} days are deleted within the hour.`);
      [["retention_bodies_days", "Stored bodies"], ["retention_site_days", "Website visits"], ["retention_launch_days", "Tools-opened records"], ["retention_audit_days", "Audit entries"]]
        .forEach(([k, l]) => { if (shorter(k)) out.push(`${l} older than ${v[k]} days are deleted within the hour.`); });
      if (v.store_bodies === false) out.push("New requests keep only their summary; full bodies are no longer stored.");
      if (v.gate_log_full === true) out.push("The website gate starts recording page content. Staff must be told before this is on.");
      if (v.block_secrets === false) out.push("Requests containing credentials are let through (and flagged) instead of refused.");
      return out;
    }
    save.addEventListener("click", async () => {
      err.textContent = "";
      const found = problems();
      showProblems(found);
      if (Object.keys(found).length) { err.textContent = "Fix the highlighted values first."; days[Object.keys(found)[0]].focus(); return; }
      const v = values();
      const warn = consequences(v);
      if (warn.length && !(await A.confirmAction("Save these changes?", warn.join(" "), "Save changes", true))) return;
      save.disabled = true;
      try { await api("PUT", "/settings", { ...v, reason: reason.value }); A.setDirty(null); toast("Settings saved."); A.render(); }
      catch (e) {
        // the server names the setting it refused: show it beside that control too
        const k = Object.keys(days).find((key) => e.message.startsWith(key)) || (/audit log/.test(e.message) ? "retention_audit_days" : null);
        if (k) {
          const said = e.message.startsWith(k) ? e.message.slice(k.length + 1) : e.message;
          fieldErr[k].textContent = said.charAt(0).toUpperCase() + said.slice(1) + ".";
          days[k].setAttribute("aria-invalid", "true"); days[k].focus();
          err.textContent = "Fix the highlighted value.";
        } else err.textContent = e.message;
      }
      finally { save.disabled = false; }
    });
    const unit = (input, text, key) => el("span", { class: "unit-wrap" }, el("span", { class: "unit" }, input, text), key ? fieldErr[key] : null);
    const anyEditable = st.areas ? Object.values(st.areas).some((a) => A.can(a)) : A.isOwner();
    // a row this role can't change says which area it needs — unless nothing here is theirs (the header says so once)
    const lock = (k) => (anyEditable && off(k) ? { lock: (st.areas || {})[k] || "admin" } : {});
    const row = (k, label, hint, control, o) => A.settingRow(label, hint, control, { ...lock(k), ...(o || {}) });
    const panels = [
      settingSummary([["Request records", fmt.num(st.records), `${(st.db_bytes / 1048576).toFixed(1)} MB on disk`],
        ["Default retention", st.retention_days ? `${st.retention_days} days` : "Keep forever", "Older records are removed hourly"],
        ["Full API bodies", st.store_bodies ? "Stored" : "Summary only", "Applies to new gateway requests"]]),
      A.panel("Request records", `${st.records.toLocaleString()} requests · ${(st.db_bytes / 1048576).toFixed(1)} MB on disk`,
        row("retention_days", "Keep records for", "Older request records are deleted automatically every hour. 0 keeps everything. Staff see this number on their privacy page.", unit(retention, "days", "retention_days")),
        row("store_bodies", "Keep full request and response bodies", "Needed to pull back exactly what was sent. Off keeps only the summary: who, model, prompt, commands, cost.", storeBodies)),
      A.panel("Retention by kind", "days · each row explains what 0 means",
        row("retention_bodies_days", "Full bodies", "Drop bodies sooner; the summary stays. 0 follows request retention. Bodies cannot outlive their request record.", unit(ret.retention_bodies_days, "days", "retention_bodies_days")),
        row("retention_site_days", "Website visits", "Which tool, when and how long, from the browser gate. 0 keeps these records indefinitely.", unit(ret.retention_site_days, "days", "retention_site_days")),
        row("retention_launch_days", "Tools opened from Swangz AI Hub", "Each portal launch, with its browser and address. 0 keeps these records indefinitely.", unit(ret.retention_launch_days, "days", "retention_launch_days")),
        row("retention_audit_days", "Audit log", "At least 365 days, or 0 for forever: the record of what admins did should outlive what it watches. Every purge is itself written to the audit log.",
          unit(ret.retention_audit_days, "days", "retention_audit_days"))),
      A.panel("Protection on every request", null,
        row("block_secrets", "Refuse requests that contain credentials", "API keys, cloud keys, private keys. Off lets them through but flags them. On can interrupt an agent that reads a .env file.", blockSecrets),
        row("rate_per_min", "Rate limit", "Catches a runaway tool. 0 means no limit. A busy agent can make several requests a minute, so keep it generous.", unit(rate, "a minute, per person", "rate_per_min"))),
      A.panel("Staff", null,
        row("staff_self_keys", "Staff can connect their own devices", "In the Swangz AI Hub app they create and disconnect their own keys. Every key still shows up under Devices, and you can revoke any of them.", selfKeys),
        row("gate_log_full", "Website gate: full-content logging", "Off by default, and the honest choice: the browser extension records only which approved site staff open and for how long. Staff are told in the extension's policy.", gateFull, { tone: "warn" }),
        row("support_contact", "Who staff contact for help", "Shown on the staff app's privacy page and wherever access is refused.", contact, { stack: true })),
      anyEditable ? bar : null,
    ];
    const summaries = {
      safeguards: [["Credential handling", st.block_secrets ? "Refuse & flag" : "Flag only", "Detected secrets in API requests"],
        ["Rate limit", st.rate_per_min ? `${st.rate_per_min} / min` : "No limit", "Per person, across their devices"],
        ["Scope", "Gateway requests", "Direct vendor websites are separate"]],
      staff: [["Device connections", st.staff_self_keys ? "Self-service" : "Admin only", "Personal gateway keys per device"],
        ["Website logging", st.gate_log_full ? "Full content" : "Access only", "Browser-extension privacy setting"],
        ["Support contact", st.support_contact ? "Set" : "Not set", "Shown when staff need help"]],
    };
    // Build each section from a fresh server snapshot; only visible controls can contribute edits.
    return section === "safeguards" ? [settingSummary(summaries.safeguards), panels[3], panels[5]]
      : section === "staff" ? [settingSummary(summaries.staff), panels[4], panels[5]]
      : [panels[0], panels[1], panels[2], panels[5]];
  }

  /* The stops. A status board says what is running now and holds the one big stop; below it, one provider at a time
     and the company browsers. Each acts at once — after a deliberate yes — and is written to the audit log. */
  async function emergencyTab() {
    const st = await api("GET", "/settings");
    const can = A.can("emergency");
    const put = async (body, msg) => {
      try { await api("PUT", "/settings", body); toast(msg); A.render(); } catch (e) { toast(e.message, true); A.render(); }
    };
    const off = new Set(st.disabled_providers);
    const providerRows = st.providers.map((p) => {
      const name = p.label || p.name;
      const sw = A.switchInput(!off.has(p.name), !can, `${name}: requests ${off.has(p.name) ? "refused" : "allowed"}`);
      sw.addEventListener("change", async () => {
        const turningOff = !sw.checked;
        if (turningOff && !(await A.confirmAction(`Switch ${name} off?`, "Every new request to it is refused until it is switched back on. Requests already running finish.", "Switch off", true))) { sw.checked = true; return; }
        const next = new Set(off);
        if (turningOff) next.add(p.name); else next.delete(p.name);
        put({ disabled_providers: [...next] }, turningOff ? `${name} is off.` : `${name} is back on.`);
      });
      return A.settingRow(el("span", { class: "row" }, name, off.has(p.name) ? SUI.status("blocked", "Off", { plain: true }) : p.configured ? SUI.status("ok", "On", { plain: true }) : SUI.status("none", "No key", { plain: true })),
        off.has(p.name) ? "Switched off here: every new request to it is refused." : p.configured ? "Requests to it go through as usual." : "No company key on the server yet, so its requests are refused anyway.", sw);
    });
    const ws = A.switchInput(!st.workspace_paused, !can, "Company browsers: " + (st.workspace_paused ? "paused" : "running"));
    ws.addEventListener("change", async () => {
      if (!ws.checked && !(await A.confirmAction("Pause the company browsers?", "Nobody can open a shared tool in a company browser until they are resumed. Turns already running keep their browser until they end.", "Pause", true))) { ws.checked = true; return; }
      put({ workspace_paused: !ws.checked }, ws.checked ? "Company browsers resumed." : "Company browsers paused.");
    });
    const onCount = st.providers.filter((p) => p.configured && !off.has(p.name)).length;
    const board = el("section", { class: "em-board" + (st.paused ? " stopped" : ""), "aria-labelledby": "em-state" },
      el("div", { class: "em-state" },
        el("span", { class: "em-dot", "aria-hidden": "true" }),
        el("div", null,
          el("div", { class: "em-k" }, "Right now"),
          el("h3", { id: "em-state" }, st.paused ? "AI is paused for everyone" : "AI access is enabled"),
          el("p", null, st.paused ? "Every request is refused and the staff app's Open buttons are closed until someone resumes access."
            : `${onCount} of ${SUI.plural(st.providers.length, "provider")} configured and enabled · company-browser access ${st.workspace_paused ? "paused" : "enabled"}. Check Health for live availability.`))),
      el("div", { class: "em-act" },
        can ? (st.paused ? el("button", { class: "btn primary", onclick: () => A.setPaused(false) }, "Resume access")
          : el("button", { class: "btn danger solid", onclick: () => A.setPaused(true) }, icon("stop"), "Stop all AI")) : null,
        el("span", { class: "em-hint" }, st.paused ? "Resuming opens everything again at once." : "Cuts every request in flight and refuses new ones. You'll be asked to confirm.")));
    return [
      board,
      A.panel("One provider at a time", "switch a provider off without stopping everything", providerRows),
      A.panel("Company browsers", null, A.settingRow("Company browsers for shared accounts", "Pause if a workspace server misbehaves; the tools' own sites are unaffected.", ws)),
      el("nav", { class: "em-more", "aria-label": "Smaller stops elsewhere" }, el("span", { class: "em-k" }, "One at a time, elsewhere"),
        el("a", { href: "#/live" }, "Stop a single request", el("span", null, "Live")),
        el("a", { href: "#/people" }, "Suspend a person or revoke a device", el("span", null, "People")),
        el("a", { href: "#/tools" }, "Take back a shared turn", el("span", null, "Tools")),
        el("a", { href: "#/models" }, "Switch a model off", el("span", null, "Models"))),
    ];
  }

  /* The purpose taxonomy: what requests can be for, and the keywords that suggest each. */
  async function purposesTab() {
    const [data, st] = await Promise.all([api("GET", "/purposes"), api("GET", "/settings")]);
    const edit = A.can("govern");
    const inference = A.switchInput(data.inference, !A.can("admin"), "Infer purpose from the prompt");
    inference.addEventListener("change", async () => {
      try { await api("PUT", "/settings", { purpose_inference: inference.checked }); toast(inference.checked ? "Inference on, from the next request." : "Inference off — only declared and derived purposes from now."); }
      catch (e) { inference.checked = !inference.checked; toast(e.message, true); }
    });
    const sample = el("input", { type: "text", placeholder: "Type a sample prompt to see what the rules say — nothing is stored", "aria-label": "Sample prompt" });
    const verdict = el("div", { class: "hint", role: "status" });
    sample.addEventListener("input", SUI.debounce(async () => {
      if (!sample.value.trim()) { verdict.textContent = ""; return; }
      const r = await api("POST", "/purposes/test", { text: sample.value });
      verdict.replaceChildren(r.purpose ? el("span", null, el("strong", null, r.name), ` — ${Math.round(r.confidence * 100)}% sure (${r.strong ? "beats what the tool suggests" : "used only when the tool suggests nothing"}), matched: ${r.evidence.join(", ")}`)
        : r.candidate ? `Too weak to say (${Math.round(r.confidence * 100)}%): would be Unknown.` : "No rule matches: Unknown.", r.note ? " " + r.note : "");
    }, 250));
    const rows = data.items;
    const table = SUI.table({ caption: "Purposes", rows, sort: ["sort", "asc"], columns: [
      { key: "name", label: "Purpose", lead: true, render: (x) => el("div", null, el("strong", null, x.name), x.archived ? SUI.badge("archived", "outline") : null,
        el("span", { class: "sub" }, x.description || "")) },
      { key: "keywords", label: "Keywords", sort: false, render: (x) => el("span", { class: "hint kw-line", title: x.keywords.join(", ") },
        x.keywords.length ? x.keywords.slice(0, 6).join(", ") + (x.keywords.length > 6 ? ` +${x.keywords.length - 6}` : "") : "—"), hideSm: true },
      { key: "requests", label: "Requests · 30 d", num: true },
      { key: "declared", label: "Declared", num: true, hideSm: true }, { key: "derived", label: "From the tool", num: true, hideSm: true },
      { key: "inferred", label: "Inferred", num: true, hideSm: true },
      edit ? { key: "act", label: "", sort: false, srLabel: "Edit", cls: "act", render: (x) => el("button", { class: "btn small quiet", onclick: () => editPurpose(x) }, "Edit") } : null,
    ].filter(Boolean) });
    return [
      settingSummary([["Purpose labels", String(rows.filter((x) => !x.archived).length), "Active labels for new requests"],
        ["Inference", data.inference ? "Enabled" : "Off", "Deterministic keyword rules"],
        ["Unknown · 30 days", fmt.num(data.unknown_30d), "Requests without a reliable purpose"]]),
      A.panel("How purposes are worked out", null,
        A.settingRow("Infer purpose from the prompt", "Keyword rules over what was typed — no model is asked and nothing leaves the gateway. Off: only purposes the person or tool declares (X-Swangz-Purpose, or Studio) and those the tool implies.", inference),
        el("div", { class: "body stack" }, sample, verdict,
          el("p", { class: "hint" }, `Declared beats everything. An inference ${Math.round(data.thresholds.strong * 100)}%+ sure beats what the tool suggests; below ${Math.round(data.thresholds.shown * 100)}% the answer is Unknown. ${fmt.num(data.unknown_30d)} requests in the last 30 days were Unknown.`))),
      A.panel("Purposes", edit ? el("button", { class: "btn small", onclick: () => editPurpose(null) }, icon("plus"), "Add a purpose") : "what a request can be for", table),
    ];
  }

  function editPurpose(x) {
    const name = el("input", { type: "text", maxlength: "60", value: x ? x.name : "" });
    const desc = el("input", { type: "text", maxlength: "200", value: x ? x.description : "" });
    const kw = el("textarea", { rows: "4", placeholder: "comma-separated words or phrases, e.g. venue, guest list, rsvp" }, x ? x.keywords.join(", ") : "");
    const archived = A.switchInput(x ? x.archived : false, false, "Archived");
    const err = el("div", { class: "err", role: "alert" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      const body = { name: name.value, description: desc.value, keywords: kw.value, archived: archived.checked };
      try {
        if (x) await api("PUT", "/purposes/" + x.id, body); else await api("POST", "/purposes", body);
        d.close(); toast("Saved. New requests use it."); A.render();
      } catch (e) { err.textContent = e.message; }
    } }, x ? "Save" : "Add purpose");
    const d = A.dialog(x ? "Edit " + x.name : "Add a purpose", el("div", { class: "stack" },
      el("label", { class: "field" }, "Name", name), el("label", { class: "field" }, "Description", desc),
      el("label", { class: "field" }, "Keywords", kw, el("span", { class: "hint" }, "Whole words only. The purpose with clearly more distinct matches wins; a tie is Unknown.")),
      x ? A.settingRow("Archived", "Hidden from new requests; past records keep it.", archived) : null, err), [save]);
  }

  /* Where requests come from: networks Swangz names (exact), and the offline location table (approximate). */
  async function locationsTab() {
    const g = await api("GET", "/geo");
    const edit = A.can("trust");
    const t = g.table;
    const lookup = el("input", { type: "text", placeholder: "Try an address, e.g. 41.210.145.3", "aria-label": "Address" });
    const said = el("div", { class: "hint", role: "status" });
    lookup.addEventListener("change", async () => {
      try {
        const d = await api("GET", "/geo/lookup?ip=" + encodeURIComponent(lookup.value.trim()));
        said.replaceChildren(el("strong", null, d.label), " — " + d.evidence);
      } catch (e) { said.textContent = e.message; }
    });
    const nets = g.networks.length ? SUI.table({ caption: "Named networks", rows: g.networks, sort: ["label", "asc"], columns: [
      { key: "label", label: "Name", lead: true, render: (n) => el("div", null, el("strong", null, n.label), n.place ? el("span", { class: "sub" }, n.place) : null) },
      { key: "cidr", label: "Addresses", render: (n) => el("span", { class: "mono" }, n.cidr) },
      { key: "kind", label: "Kind", render: (n) => n.kind },
      { key: "created_by", label: "Added by", render: (n) => n.created_by || "—", hideSm: true },
      edit ? { key: "act", label: "", sort: false, srLabel: "Edit", cls: "act", render: (n) => el("button", { class: "btn small quiet", onclick: () => editNetwork(n) }, "Edit") } : null,
    ].filter(Boolean) }) : A.empty("Name the office's address (and any VPN) and requests from it say so exactly, instead of an approximate city.", "No named networks", "pin");
    return [
      settingSummary([["Named networks", String(g.networks.length), "Known office, VPN and other addresses"],
        ["Offline table", t.rows ? "Loaded" : "Not loaded", t.rows ? `${fmt.num(t.rows)} address ranges` : "Public addresses have no city estimate"],
        ["Location evidence", "Approximate", "Named network matches are shown separately"]]),
      A.panel("Named networks", edit ? el("button", { class: "btn small", onclick: () => editNetwork(null) }, icon("plus"), "Name a network") : "exact — Swangz said so", nets),
      A.panel("Location table", t.rows ? `${fmt.num(t.rows)} address ranges` : "not loaded",
        A.settingRow(t.rows ? el("span", { class: "row" }, t.source, SUI.status("ok", "Loaded", { plain: true })) : el("span", { class: "row" }, "None", SUI.status("none", "Not loaded", { plain: true })),
          t.rows ? `Imported ${fmt.date(t.imported)}. Places from it are labelled approximate everywhere — a city from an address, never a GPS position.`
            : "Without one, a public address shows only as \"public internet\". Load a free offline table (DB-IP Lite or IP2Location LITE, CSV) on the server: python3 -m gateway geoip-import FILE --source \"DB-IP Lite 2026-10\". Addresses are never sent to an outside service.", null),
        el("div", { class: "body stack" }, lookup, said)),
    ];
  }

  function editNetwork(n) {
    const cidr = el("input", { type: "text", value: n ? n.cidr : "", placeholder: "e.g. 41.210.145.0/24 or a single address" });
    const label = el("input", { type: "text", maxlength: "80", value: n ? n.label : "", placeholder: "e.g. Swangz office" });
    const place = el("input", { type: "text", maxlength: "80", value: n ? n.place : "", placeholder: "e.g. Kampala, Ntinda" });
    const kind = el("select", null, ["office", "vpn", "home", "cloud", "other"].map((k) => el("option", { value: k }, k)));
    kind.value = n ? n.kind : "office";
    const err = el("div", { class: "err", role: "alert" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      const body = { cidr: cidr.value, label: label.value, place: place.value, kind: kind.value };
      try { if (n) await api("PATCH", "/networks/" + n.id, body); else await api("POST", "/networks", body); d.close(); toast("Saved."); A.render(); }
      catch (e) { err.textContent = e.message; }
    } }, n ? "Save" : "Name it");
    const remove = n ? el("button", { class: "btn danger", onclick: async () => {
      try { await api("DELETE", "/networks/" + n.id); d.close(); toast("Removed."); A.render(); } catch (e) { err.textContent = e.message; }
    } }, "Remove") : null;
    const d = A.dialog(n ? "Edit " + n.label : "Name a network", el("div", { class: "stack" },
      el("label", { class: "field" }, "Addresses", cidr), el("label", { class: "field" }, "Name", label),
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Place", place), el("label", { class: "field" }, "Kind", kind)), err), [remove, save]);
  }

  /* What voice, image and video work costs, by the date each rate takes effect. */
  async function ratesTab() {
    const data = await api("GET", "/media-rates");
    const edit = A.can("money");
    const table = data.items.length ? SUI.table({ caption: "Media rates", rows: data.items, sort: ["effective", "desc"], columns: [
      { key: "provider", label: "Service", lead: true, render: (r) => el("div", null, el("strong", null, r.provider), r.service !== "*" ? el("span", { class: "sub mono" }, r.service) : null) },
      { key: "usd_per_unit", label: "Rate", num: true, render: (r) => `$${r.usd_per_unit} per ${r.unit}` },
      { key: "effective", label: "From", num: true, render: (r) => fmt.date(r.effective) },
      { key: "current", label: "", sort: false, render: (r) => (r.current ? SUI.badge("In force", "ok") : r.scheduled ? SUI.badge("Scheduled", "info") : SUI.badge("Earlier", "outline")) },
      { key: "created_by", label: "Set by", render: (r) => r.created_by || "—", hideSm: true },
      edit ? { key: "act", label: "", sort: false, srLabel: "Remove", cls: "act", render: (r) => el("button", { class: "btn small quiet danger", onclick: async () => {
        try { await api("DELETE", "/media-rates/" + r.id); toast("Removed."); A.render(); } catch (e) { toast(e.message, true); }
      } }, "Remove") } : null,
    ].filter(Boolean) }) : A.empty("Voice, image and video requests stay unpriced until a rate is set.", "No media rates", "wallet");
    const unpriced = data.unpriced.length ? el("section", { class: "callout warn" },
      el("div", { class: "callout-row" }, icon("alert"), el("span", { class: "callout-k" }, "Unpriced in the last 30 days"),
        el("span", { class: "muted" }, data.unpriced.map((u) => `${u.provider} ${u.media_type || ""}: ${fmt.num(u.requests)} requests, ${fmt.num(u.units)} ${u.unit || "units"}`).join(" · ")))) : null;
    return [settingSummary([["Current rates", String(data.items.filter((r) => r.current).length), "In force by service and billing unit"],
      ["Scheduled", String(data.items.filter((r) => r.scheduled).length), "Rates with a future effective date"],
      ["Unpriced · 30 days", fmt.num(data.unpriced.reduce((n, r) => n + r.requests, 0)), "Requests missing a matching rate"]]), unpriced, A.panel("Media rates", edit ? el("button", { class: "btn small", onclick: () => addRate(data) }, icon("plus"), "Add a rate") : "estimated costs for voice, image and video", table,
      el("div", { class: "body hint" }, "A new rate applies from its date on. Costs already recorded keep the rate they were priced with, and a rate that priced anything can't be removed — add a newer one."))];
  }

  function addRate(data) {
    const provider = el("select", null, data.providers.map((p) => el("option", { value: p.name }, p.label || p.name)));
    const unit = el("select", null, data.units.map((u) => el("option", { value: u }, u)));
    const usd = el("input", { type: "number", min: "0", step: "0.000001", placeholder: "e.g. 0.0003" });
    const service = el("input", { type: "text", value: "*", placeholder: "* or a model / kind, e.g. eleven_multilingual_v2" });
    const effective = el("input", { type: "date", value: new Date().toISOString().slice(0, 10) });
    const err = el("div", { class: "err", role: "alert" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try {
        await api("POST", "/media-rates", { provider: provider.value, unit: unit.value, usd_per_unit: usd.value, service: service.value, effective: effective.value });
        d.close(); toast("Rate added."); A.render();
      } catch (e) { err.textContent = e.message; }
    } }, "Add rate");
    const d = A.dialog("Add a media rate", el("div", { class: "stack" },
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Service", provider), el("label", { class: "field" }, "Per", unit)),
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "US dollars per unit", usd), el("label", { class: "field" }, "From", effective)),
      el("label", { class: "field" }, "Which models or kinds", service, el("span", { class: "hint" }, "* for all; the most specific match wins.")), err), [save]);
  }

  async function addressesTab() {
    const st = await api("GET", "/settings");
    const disabled = new Set(st.disabled_providers);
    const available = st.providers.filter((p) => p.configured && !disabled.has(p.name));
    const copyable = (text) => el("div", { class: "row end" }, el("span", { class: "value-mono", title: text }, text),
      el("button", { class: "btn small quiet icon-only", type: "button", "aria-label": "Copy " + text, onclick: () => SUI.copy(text) }, icon("copy")));
    const providers = SUI.table({ caption: "Providers", rows: st.providers, cards: true, columns: [
      { key: "label", label: "Provider", lead: true, render: (p) => el("div", null, el("strong", null, p.label || p.name), el("span", { class: "sub" },
        { anthropic: "chat & coding models", openai: "chat & coding models", elevenlabs: "voice & sound", higgsfield: "image & video" }[p.dialect] || "AI service")) },
      { key: "addr", label: "Address for staff tools", sort: false, render: (p) => el("span", { class: "mono" }, `${st.base_url}/${p.name}` + (p.dialect === "openai" ? "/v1" : "")) },
      { key: "upstream", label: "Forwards to", sort: false, render: (p) => el("span", { class: "mono faint" }, p.upstream), hideSm: true },
      { key: "configured", label: "Configuration", render: (p) => el("div", null,
        p.configured ? SUI.status("ok", "Key set", { plain: true }) : SUI.status("waiting", "Key missing", { plain: true }),
        disabled.has(p.name) ? el("a", { class: "sub", href: "#/settings?tab=emergency" }, "Switched off in Emergency")
          : !p.configured ? el("span", { class: "sub" }, `Set ${p.key_env} on the server`) : el("span", { class: "sub" }, "Enabled in configuration")) }] });
    return [
      settingSummary([["Providers", String(st.providers.length), "Services registered on the gateway"],
        ["Configured & enabled", String(available.length), "Has a key; no provider stop in force"],
        ["Global access", st.paused ? "Paused" : "Enabled", "Live availability is on Health"]]),
      A.panel("This gateway", null,
        A.settingRow("Staff app", "Where staff sign in and open their tools.", copyable(st.base_url + "/")),
        A.settingRow("Control room", "This console. Don't share it with staff.", copyable(st.base_url + "/admin")),
        A.settingRow("Time zone", "Budgets reset at midnight here. Set with GATEWAY_TZ_OFFSET on the server.", el("span", { class: "value-mono" }, SUI.tzLabel()))),
      A.panel("Providers", "staff tools point at these", providers,
        el("div", { class: "body hint" }, "Provider API keys live only in the server's environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, …). They are never shown here and never leave the server.")),
    ];
  }

  /* Company browsers for shared accounts: where they run — the rented server, the Windows PC or the Mac,
     one place at a time — and signing each place's browsers in to their tools. */
  async function workspaceTab(owner) {
    const ws = await api("GET", "/workspace");
    const cap = (x) => x.charAt(0).toUpperCase() + x.slice(1);
    const usable = (h) => (h.kind === "server" ? h.set_up : h.connected);
    const card = (h) => {
      let tone, state, detail;
      if (h.kind === "server") {
        [tone, state] = h.set_up ? ["ok", "Set up"] : ["none", "Not set up"];
        detail = h.set_up ? "A server Swangz rents (GATEWAY_WORKSPACE_AGENT in the gateway's settings). Its browsers are listed in its own config."
          : "Set it up with deploy/setup-workspace-server.sh, then put GATEWAY_WORKSPACE_AGENT and its token in the gateway's settings.";
      } else if (!h.set_up) {
        [tone, state] = ["none", "Not set up"];
        detail = `Run the company browsers on ${h.label} instead of a rented server. It needs Docker Desktop and Python, and has to stay on.`;
      } else if (!h.connected) {
        [tone, state] = ["waiting", "Waiting for it"];
        detail = "It has a key but hasn't checked in yet — run the setup command on it.";
      } else {
        [tone, state] = h.online ? ["ok", "Online"] : ["blocked", "Offline"];
        const i = h.info || {};
        detail = [(h.online ? "checked in " : "last seen ") + fmt.ago(h.seen), i.system, i.memory_gb ? `Docker has ${i.memory_gb} GB` : null,
          i.browsers != null ? `${SUI.plural(i.browsers, "browser")} (${i.running || 0} running)` : null,
          i.max_running ? `at most ${i.max_running} at once` : null].filter(Boolean).join(" · ");
      }
      const buttons = [];
      if (owner && !h.active && usable(h)) buttons.push(el("button", { class: "btn small primary", onclick: () => useHost(h) }, "Use this one"));
      if (owner && h.kind === "computer") {
        buttons.push(el("button", { class: "btn small", onclick: () => connectComputer(h) }, h.set_up ? "New key" : "Connect…"));
        if (h.set_up && !h.active) buttons.push(el("button", { class: "btn small danger quiet", onclick: () => forgetComputer(h) }, "Disconnect"));
      }
      return A.settingRow(el("span", { class: "place-name" }, el("span", { class: "dev-ic sm" }, icon(h.kind === "server" ? "server" : "monitor")),
        cap(h.label), h.active ? SUI.badge("In use", "gold") : null, SUI.status(tone, state, { plain: true })),
      detail, buttons.length ? buttons : null);
    };
    const places = A.panel("Where the company browsers run", "one place at a time — Open uses the one marked In use", ws.hosts.map(card),
      el("div", { class: "body hint" }, "Each place has browsers of its own, and each browser keeps its own sign-in to its tool — so sign a place's browsers in (below) before switching to it. Switching moves anyone in a company browser off the old place: their turn ends, and Open gives them a browser at the new one."));
    const RELAY = { cloudflare: "Cloudflare's video relay", own: "Swangz's own video relay (coturn)" };
    const relay = A.panel("Video from Swangz's own computers", null, A.settingRow(
      el("span", { class: "row" }, "Video relay", ws.relay ? SUI.status("ok", "On", { plain: true }) : SUI.status("waiting", "Not set up", { plain: true })),
      ws.relay ? "Through " + RELAY[ws.relay] + ": staff can work in a computer's browsers from anywhere."
        : "Without one, only people on the same network as the computer can use its browsers. Add a Cloudflare TURN key to the gateway's settings (GATEWAY_TURN_CLOUDFLARE_KEY_ID and GATEWAY_TURN_CLOUDFLARE_TOKEN — see deploy/WORKSPACE.md). The rented server doesn't need one.", null));
    // one place's browsers, to sign them in — before switching to it, too
    const ready = ws.hosts.filter(usable);
    let signing = null;
    if (ready.length) {
      const list = el("div");
      let current = ready.some((h) => h.active) ? ws.active : ready[0].id;
      const pick = el("div", { class: "body" });
      const drawPick = () => pick.replaceChildren(A.seg(ready.map((h) => [h.id, cap(h.label)]), current, (v) => { current = v; show(v); }, "Place"));
      const show = (id) => SUI.load(list, async () => {
        const [one, tools] = await Promise.all([api("GET", "/workspace?host=" + id), A.toolIndex().catch(() => ({}))]);
        if (one.error) return el("div", { class: "body" }, el("div", { class: "notice" }, `${cap(one.label)} isn't answering: ${one.error}`));
        const byTool = {};
        (one.browsers || []).forEach((b) => { (byTool[b.tool] = byTool[b.tool] || []).push(b); });
        const groups = Object.keys(byTool).sort().map((tid) => el("div", { class: "stack" },
          el("h3", { class: "section-title" }, (tools[tid] || {}).name || tid),
          el("div", { class: "assign-list" }, byTool[tid].map((b) => A.browserRow(b, id, owner, () => show(id))))));
        return el("div", { class: "body stack" }, groups.length ? groups : A.empty(one.host === "server"
          ? "No browsers in the rented server's config yet."
          : "No browsers yet. A tool gets them here within a minute once its Settings say Company browsers = Swangz's company browsers — one for each person on it at a time."));
      });
      drawPick();
      signing = A.panel("Signing the browsers in", "once per browser, at each place", pick, list);
      show(current);
    }
    const active = ws.hosts.find((h) => h.active);
    return [settingSummary([["Selected host", active ? cap(active.label) : "None", "Only one host serves shared tools at a time"],
      ["Connected hosts", String(ws.hosts.filter(usable).length), "Configured server or connected computer"],
      ["Computer video relay", ws.relay ? "Configured" : "Not set up", "Needed for remote access to office computers"]]), places, relay, signing];
  }

  async function useHost(h) {
    const ok = await A.confirmAction(`Use ${h.label} for the company browsers?`,
      `From now on Open gives people browsers on ${h.label}. Anyone in a company browser somewhere else is moved off: their turn ends, and Open gives them one here. Sign this place's browsers in to their tools first.`, "Switch", false);
    if (!ok) return;
    try {
      const out = await api("POST", "/workspace/use", { host: h.id });
      toast(out.moved ? `Switched — ${SUI.plural(out.moved, "person", "people")} moved off.` : "Switched.");
      S.tools = null;
      A.render();
    } catch (e) { toast(e.message, true); }
  }

  async function connectComputer(h) {
    if (h.set_up) {
      const ok = await A.confirmAction(`New key for ${h.label}?`, "Its current key stops working at once, and it stays offline until it's set up again with the new one.", "Make a new key", true);
      if (!ok) return;
    }
    let out;
    try { out = await api("POST", `/workspace/hosts/${h.id}/key`); } catch (e) { toast(e.message, true); return; }
    const win = h.id === "windows";
    const steps = el("ol", { class: "setup-steps" },
      el("li", null, el("strong", null, "Docker Desktop: "), win ? "install it (in PowerShell: winget install -e --id Docker.DockerDesktop), open it once and accept its terms."
        : "install it from docker.com (Apple chip or Intel — pick the matching one), open it once and accept its terms."),
      el("li", null, el("strong", null, "Python 3: "), win ? "in PowerShell: winget install -e --id Python.Python.3.13" : "most Macs have it (python3 --version); otherwise brew install python."),
      el("li", null, el("strong", null, "This project: "), "git clone https://github.com/arnoldkigozi0/swangz-gateway.git — or copy the folder across."),
      el("li", null, el("strong", null, "Then, in that folder " + (win ? "(PowerShell)" : "(Terminal)") + ", run the command below.")));
    const done = el("button", { class: "btn primary", onclick: () => { d.close(); A.render(); } }, "I've copied it");
    const d = A.dialog(`Connect ${h.label}`, el("div", { class: "stack" },
      el("div", { class: "notice" }, icon("alert"), "The key is in this command, and this is the only time it's shown. Run it on that computer only."),
      steps,
      el("div", { class: "spread" }, el("strong", null, "The command"), el("button", { class: "btn small", onclick: () => SUI.copy(out.command) }, icon("copy"), "Copy")),
      el("pre", { class: "code" }, out.command),
      el("p", { class: "hint" }, "It checks Docker, works out how many browsers fit in its memory, downloads the tunnel program and the browser (about 1 GB, once), sets itself to start with the computer and keeps it awake, then checks in here. Keep the computer on, plugged in and online: while it's off, nobody gets a company browser unless you switch back to the rented server.")), [done]);
  }

  async function forgetComputer(h) {
    const ok = await A.confirmAction(`Disconnect ${h.label}?`, "Its key stops working and it no longer shows here. The browsers and their sign-ins stay on that computer; run computer.py remove there to stop it starting with the computer.", "Disconnect", true);
    if (!ok) return;
    try { await api("DELETE", `/workspace/hosts/${h.id}`); toast("Disconnected."); A.render(); } catch (e) { toast(e.message, true); }
  }

  async function pricesTab(owner) {
    const prices = await api("GET", "/prices");
    const unpriced = prices.unpriced_models.length ? el("section", { class: "callout warn" },
      el("div", { class: "callout-row" }, icon("alert"), el("span", { class: "callout-k" }, "Used but not priced"),
        el("span", { class: "muted" }, "their cost shows as unpriced, so spend is understated")),
      el("div", { class: "row" }, prices.unpriced_models.map((m) => owner ? el("button", { class: "btn small", onclick: () => editPrice({ model: m }) }, icon("plus"), m) : SUI.badge(m, "warn")))) : null;
    const search = el("input", { type: "search", placeholder: "Find a model or provider…", "aria-label": "Search model prices" });
    const count = el("span", { class: "hint", role: "status", "aria-live": "polite" });
    const tableBox = el("div");
    const draw = () => {
      const term = search.value.trim().toLowerCase();
      const rows = prices.items.filter((x) => `${x.model} ${x.provider || ""}`.toLowerCase().includes(term));
      count.textContent = `${rows.length} of ${prices.items.length} prices`;
      tableBox.replaceChildren(rows.length ? SUI.table({ caption: "Model prices · US dollars per million tokens", rows, sort: ["model", "asc"], cards: true, columns: [
      { key: "model", label: "Model", lead: true, render: (x) => el("span", { class: "mono nowrap" }, x.model) },
      { key: "input", label: "Input", num: true, render: (x) => usd(x.input) },
      { key: "output", label: "Output", num: true, render: (x) => usd(x.output) },
      { key: "cache_write", label: "Cache write · 5 min", num: true, render: (x) => (x.cache_write == null ? "Default" : usd(x.cache_write)) },
      { key: "cache_write_1h", label: "Cache write · 1 hour", num: true, render: (x) => (x.cache_write_1h == null ? "Default" : usd(x.cache_write_1h)) },
      { key: "cache_read", label: "Cache read", num: true, render: (x) => (x.cache_read == null ? "Default" : usd(x.cache_read)) },
      owner ? { key: "edit", label: "", sort: false, srLabel: "Edit", cls: "act", render: (x) => el("button", { class: "btn small quiet", onclick: () => editPrice(x) }, "Edit") } : null].filter(Boolean) }) : SUI.stateBox({ icon: "search", compact: true, title: "No matching prices", text: "Try another model or provider name." }));
    };
    search.addEventListener("input", draw);
    draw();
    return [settingSummary([["Price entries", String(prices.items.length), "Model IDs or matching prefixes"],
      ["Used but unpriced", String(prices.unpriced_models.length), "Models with recorded use and no price"],
      ["Billing basis", "USD / 1M tokens", "Estimates, separate from vendor invoices"]]), unpriced, A.panel("Model prices", owner ? el("div", { class: "row" }, el("span", { class: "sub" }, "US dollars per million tokens"),
      el("button", { class: "btn small", onclick: () => editPrice({}) }, icon("plus"), "Add a price")) : "US dollars per million tokens",
    el("div", { class: "body set-price-search" }, search, count), tableBox,
      el("div", { class: "body hint" }, "Default cache rates: 5-minute writes are 1.25× input, 1-hour writes are 2× input, and reads use the input rate. Exact model IDs take precedence over matching snapshot prefixes."))];
  }

  function editPrice(x) {
    const f = {};
    const fields = [["model", "Model id (or the start of it)"], ["input", "Input"], ["output", "Output"], ["cache_write", "Cache write (5 min)"], ["cache_write_1h", "Cache write (1 hour)"], ["cache_read", "Cache read"]];
    const err = el("div", { class: "err", role: "alert" });
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
        A.render();
      } catch (e) { err.textContent = e.message; }
    } }, "Save price");
    const remove = x.input ? el("button", { class: "btn danger", onclick: async () => {
      try { await api("DELETE", "/prices/" + encodeURIComponent(x.model)); d.close(); A.render(); } catch (e) { err.textContent = e.message; }
    } }, "Remove") : null;
    const d = A.dialog(x.model ? "Price for " + x.model : "Add a model price", el("div", { class: "stack" },
      el("p", { class: "hint" }, "US dollars per million tokens, from the provider's price page. Leave cache fields empty to use the usual multiples of the input price."), grid, err), [remove, save]);
  }

  async function consoleUsersTab() {
    const admins = await api("GET", "/admins");
    const roles = A.S.me.roles || {};
    const areaNames = { govern: "Access & tools", money: "Billing & pricing", trust: "Security", emergency: "Emergency controls", admin: "Console administration" };
    return [settingSummary([["Console users", String(admins.items.length), "Accounts with control-room access"],
      ["Owners", String(admins.items.filter((a) => a.owner).length), "Full administrative authority"],
      ["Your role", A.roleLabel(), "Permissions are enforced by the server"]]), A.panel("Console users", el("button", { class: "btn small", onclick: () => adminDialog(null) }, icon("plus"), "Add a console user"),
      SUI.table({ caption: "Console users", rows: admins.items, sort: ["username", "asc"], columns: [
        { key: "username", label: "User", lead: true, render: (a) => el("span", { class: "u-cell" }, SUI.avatar(a.username, "sm"), el("strong", null, a.username)) },
        { key: "role", label: "Role", render: (a) => el("div", null, SUI.badge(a.role_label, a.owner ? "gold" : "outline"),
          el("span", { class: "sub" }, a.owner ? "All areas" : a.can.length ? a.can.map((x) => areaNames[x] || x).join(" · ") : "View only")) },
        { key: "last_login", label: "Last sign-in", num: true, render: (a) => fmt.ago(a.last_login) },
        { key: "x", label: "", sort: false, srLabel: "Change", cls: "act", render: (a) => (a.username === S.me.username ? el("span", { class: "faint" }, "you")
          : el("div", { class: "row end" }, el("button", { class: "btn small quiet", onclick: () => adminDialog(a) }, "Change role"),
            el("button", { class: "btn small quiet danger", onclick: () => removeAdmin(a) }, "Remove"))) }] }),
      el("div", { class: "body hint" }, "A console user whose username is their Google email can also sign in with Continue with Google.")),
    A.panel("What each role can change", "everyone can see everything", el("ul", { class: "mini-list" }, Object.entries(roles).map(([k, r]) => el("li", null,
      el("strong", null, r.label), el("span", { class: "grow hint" }, r.about))),
    el("li", null, el("strong", null, "Custom"), el("span", { class: "grow hint" }, "Pick the areas yourself."))))];
  }

  async function accountTab() {
    const cur = el("input", { type: "password", autocomplete: "current-password", id: "pw-cur" });
    const nw = el("input", { type: "password", autocomplete: "new-password", id: "pw-new" });
    const again = el("input", { type: "password", autocomplete: "new-password", id: "pw-again" });
    const pwErr = el("span", { class: "err", role: "alert" });
    const go = el("button", { class: "btn primary", type: "submit" }, "Change password");
    const form = el("form", { class: "panel", onsubmit: async (e) => {
      e.preventDefault();
      if (nw.value !== again.value) { pwErr.textContent = "The new passwords don't match."; return; }
      go.disabled = true;
      try { await api("POST", "/password", { current: cur.value, new: nw.value }); toast("Password changed."); form.reset(); pwErr.textContent = ""; }
      catch (err) { pwErr.textContent = err.message; }
      finally { go.disabled = false; }
    } },
      el("header", null, el("h2", null, "Password"), el("div", { class: "sub" }, "10 characters or more")),
      A.settingRow("Current password", null, cur, { forId: "pw-cur" }),
      A.settingRow("New password", null, nw, { forId: "pw-new" }),
      A.settingRow("New password again", null, again, { forId: "pw-again" }),
      A.panelFoot(el("span", { class: "grow" }, pwErr), go));
    return [
      A.panel("Signed in as", null,
        A.settingRow(S.me.username, ((S.me.roles || {})[S.me.role] || {}).about || ((S.me.can || []).length ? "Can change: " + S.me.can.join(", ") + "." : A.isOwner() ? "Can change everything." : "Can see everything, change nothing."),
          SUI.badge(A.roleLabel(), S.me.owner ? "gold" : "outline"))),
      form,
    ];
  }

  function adminDialog(a) {
    const roles = A.S.me.roles || {};
    const areas = A.S.me.areas || {};
    const user = el("input", { type: "text", autocomplete: "off" });
    const pw = el("input", { type: "password", autocomplete: "new-password" });
    const role = el("select", null, Object.entries(roles).map(([k, r]) => el("option", { value: k }, `${r.label} — ${r.about}`)), el("option", { value: "custom" }, "Custom — pick the areas"));
    role.value = a ? (a.owner ? "owner" : Object.keys(roles).find((k) => roles[k].label === a.role_label) || "custom") : "viewer";
    const picks = el("div", { class: "chk-grid" }, Object.entries(areas).map(([k, about]) => el("label", { "data-tip": about }, el("input", { type: "checkbox", value: k, checked: a ? a.can.includes(k) : false }), k)));
    const pickRow = el("label", { class: "field" }, "Areas", picks);
    const sync = () => { pickRow.hidden = role.value !== "custom"; };
    role.addEventListener("change", sync);
    sync();
    const err = el("div", { class: "err", role: "alert" });
    const body = () => ({ role: role.value, areas: role.value === "custom" ? [...picks.querySelectorAll("input:checked")].map((b) => b.value) : undefined });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try {
        if (a) await api("PATCH", "/admins/" + a.id, body()); else await api("POST", "/admins", { username: user.value, password: pw.value, ...body() });
        d.close(); toast(a ? "Role changed. It applies from their next click." : "Added."); A.render();
      } catch (e) { err.textContent = e.message; }
    } }, a ? "Change role" : "Add");
    const d = A.dialog(a ? "Change " + a.username + "'s role" : "Add a console user", el("div", { class: "stack" },
      a ? null : el("label", { class: "field" }, "Username", user, el("span", { class: "hint" }, "Use their Google email (e.g. name@swangzavenue.com) and they can also sign in with Google.")),
      a ? null : el("label", { class: "field" }, "Password (10+ characters)", pw),
      el("label", { class: "field" }, "Role", role), pickRow,
      el("p", { class: "hint" }, "Everyone in the console can see everything. A role decides what they can change; what it refuses is written to the audit log."), err), [save]);
    if (!a) user.focus();
  }

  async function removeAdmin(a) {
    const ok = await A.confirmAction(`Remove ${a.username}?`, "They can no longer sign in to the console.", "Remove", true);
    if (!ok) return;
    try { await api("DELETE", "/admins/" + a.id); toast("Removed."); A.render(); } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ Reports

  /* Reports: a catalogue that says what each one answers, and each report on its own page with its period and
     download. The list of reports comes from the server; the questions are how this page explains them. */
  const REPORT_ABOUT = {
    usage: ["People", "Who used AI, how much, and through which tools?"],
    spend: ["People", "What did each person's use cost, and how sure is each amount?"],
    departments: ["People", "Which departments use AI most, and what does it cost them?"],
    tools: ["Tools and models", "Which tools are used, by how many people, and how often?"],
    models: ["Tools and models", "Which models do requests go to, and what do they cost?"],
    purposes: ["Tools and models", "What is AI being used for — declared, from the tool, or inferred?"],
    licences: ["Licences", "Which seats are paid for, used, or idle?"],
    security: ["Trust", "Which signals came up, with the evidence behind each?"],
    shared: ["Trust", "Who held each shared company account, and for how long?"],
  };
  async function pageReports(params) {
    // links from when each report was a tab of this page
    if (params.get("tab")) {
      const kind = params.get("tab");
      params.delete("tab");
      location.replace(`#/reports/${encodeURIComponent(kind)}` + (params.toString() ? "?" + params.toString() : ""));
      return;
    }
    const list = await api("GET", "/reports");
    const groups = [];
    list.items.forEach((r) => {
      const group = (REPORT_ABOUT[r.kind] || ["Other"])[0];
      let g = groups.find((x) => x[0] === group);
      if (!g) groups.push(g = [group, []]);
      g[1].push(r);
    });
    A.frame({ title: "Reports", lede: "The standard questions, answered for any period and ready to download. Every amount says what it rests on — estimated from prices and rates, allocated from a plan, or unpriced. Downloads are written to the audit log." },
      el("div", { class: "report-groups" }, groups.map(([name, items]) => A.panel(name, null, el("ul", { class: "report-list" }, items.map((r) => el("li", null,
        el("a", { href: "#/reports/" + r.kind }, el("span", { class: "mini-ic" }, icon("report")),
          el("span", { class: "grow" }, el("strong", null, r.title), el("span", { class: "hint" }, (REPORT_ABOUT[r.kind] || [, ""])[1])),
          icon("chevronRight")))))))));
  }

  async function pageReport(params, kind) {
    const list = await api("GET", "/reports");
    const meta = list.items.find((r) => r.kind === kind);
    if (!meta) throw new A.ApiError(404, "There's no report called that.");
    const range = A.rangeFrom(params, "month");
    const holder = el("div");
    const dl = el("a", { class: "btn primary" }, icon("download"), "Download CSV");
    const draw = (r) => {
      const q = A.rangeQuery(r);
      dl.href = A.gadmin(`/reports/${kind}?${q.toString()}&format=csv`);
      SUI.load(holder, async () => {
        const data = await api("GET", `/reports/${kind}?${q.toString()}`);
        const money = (k) => /cost|monthly|per_active/.test(k);
        const when = (k) => k === "time" || k === "last";
        const cols = data.columns.map((c, i) => ({ key: c.key, label: c.label, lead: i === 0, num: typeof (data.rows[0] || {})[c.key] === "number" && !when(c.key),
          render: (x) => {
            const v = x[c.key];
            if (when(c.key)) return v ? el("span", { title: fmt.stamp(v) }, fmt.when(v)) : "—";
            if (money(c.key)) return v === null || v === undefined ? el("span", { class: "basis unpriced" }, "not set") : fmt.money(v);
            return v === null || v === undefined || v === "" ? "—" : typeof v === "number" ? fmt.num(v) : String(v);
          } }));
        return [data.rows.length ? SUI.table({ caption: data.title, rows: data.rows, columns: cols })
          : SUI.stateBox({ icon: "report", title: "Nothing in this period", text: "Try a wider range." }),
        el("div", { class: "body hint" }, data.notes.join(" "))];
      }, SUI.skeleton("rows", 5));
    };
    const ctl = SUI.rangeControl({ preset: range.preset, from: range.from, to: range.to, presets: ["7d", "30d", "month", "custom"], onChange: (r) => {
      A.keepParams("#/reports/" + kind, { range: r.preset, from: r.preset === "custom" ? r.from : null, to: r.preset === "custom" ? r.to : null });
      draw(r);
    } });
    A.frame({ title: meta.title, crumbs: [el("a", { href: "#/reports" }, "Reports")], lede: (REPORT_ABOUT[kind] || [, ""])[1], actions: dl },
      A.panel(null, null, el("div", { class: "filterbar" }, ctl), holder));
    draw(range);
  }

  A.page(/^#\/reports$/, pageReports);
  A.page(/^#\/reports\/([a-z]+)$/, pageReport);
  A.page(/^#\/licences$/, pageLicences);
  A.page(/^#\/settings$/, pageSettings);
})();
