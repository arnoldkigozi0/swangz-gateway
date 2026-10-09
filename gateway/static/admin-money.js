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
      ["renewals", "Renewals & budgets", () => renewalsTab()],
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
        A.kpi({ label: "AI spend · this month", icon: "wallet", value: fmt.money(s.total_month), tone: "gold hero",
          note: `${fmt.money(s.subscriptions_month)} plans + ${fmt.money(s.api_month)} metered API`,
          tip: "Plans are what's set on each subscription. Metered API use is estimated from the price table as each request runs." }),
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
      const idleSeats = d.idle.reduce((n, x) => n + x.idle, 0);
      box.replaceChildren(...[
        el("div", { class: "kpis four" },
          A.kpi({ label: "Metered AI spend", icon: "wallet", value: fmt.money(total), tone: "gold hero",
            foot: el("span", { class: "row" }, SUI.delta(d.change), el("span", { class: "note" }, `vs ${fmt.money(d.previous_total)} the period before`)),
            tip: "Each request is priced from the model price table the moment it runs. Vendor invoices aren't imported." }),
          A.kpi({ label: "Requests", icon: "spark", value: fmt.num(d.requests), note: total && d.requests ? `≈ ${fmt.money(total / d.requests)} each` : "in this period" }),
          A.kpi({ label: "Unpriced", icon: "info", value: fmt.num(d.unpriced), href: d.unpriced ? "#/settings?tab=prices" : null,
            note: d.unpriced ? "requests with no price — price them" : "every model has a price" }),
          A.kpi({ label: "Company plans", icon: "licences", value: fmt.money(d.subscriptions_month) + "/mo", href: "#/licences?tab=licences",
            note: idleSeats ? `${SUI.plural(idleSeats, "seat")} idle · ≈ ${fmt.money(d.idle.reduce((n, x) => n + x.idle_cost, 0))}/mo` : "fixed, not metered" })),
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

  async function renewalsTab() {
    const lic = await api("GET", "/licences");
    const renewals = lic.renewals.length ? el("ul", { class: "mini-list" }, lic.renewals.map((t) => el("li", null, A.toolLogo(t.id, t.name, "sm"),
      el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.monthly_cost != null ? fmt.money(t.monthly_cost) + " a month" : "cost not set")),
      SUI.badge("renews " + fmt.date(t.renews_on), "warn", "calendar")))) : SUI.stateBox({ icon: "calendar", compact: true, title: "No renewals soon", text: "Nothing renews in the next 30 days." });
    const people = lic.people.filter((p) => p.cost > 0 || p.monthly_budget !== null);
    const top = Math.max(...people.map((x) => x.cost), 0.01);
    const spend = people.length ? el("ul", { class: "u-bars" }, people.map((p) => el("li", null,
      el("a", { href: "#/people/" + p.id }, SUI.avatar(p.name, "sm"), el("span", null, p.name)),
      el("div", { class: "val" }, fmt.money(p.cost), el("small", null, p.monthly_budget !== null ? "of " + fmt.money(p.monthly_budget) : (p.department || "no budget"))),
      el("div", { class: "track-wrap" }, p.monthly_budget !== null ? A.bar(p.cost, p.monthly_budget) : A.bar(p.cost, top))))) : SUI.stateBox({ icon: "wallet", compact: true, title: "No API spend this month", text: "" });
    return el("div", { class: "grid cols-even" },
      A.panel("Renewing in the next 30 days", null, renewals),
      A.panel("API spend by person", "this month, against their budget", spend));
  }

  // ------------------------------------------------------------------ Settings

  async function pageSettings(params) {
    const mine = A.S.me.can || (A.isOwner() ? ["admin"] : []);
    A.frame({ title: "Settings", lede: mine.length ? `The switches that govern the whole gateway. You can change what your role (${A.roleLabel()}) covers; every change is written to the audit log, with what it was before.`
      : "You're a viewer: you can see these settings but not change them." },
    A.pageTabs("#/settings", params, [
      ["safety", "Access & records", () => safetyTab()],
      ["emergency", "Emergency", () => emergencyTab()],
      ["purposes", "Purposes", () => purposesTab()],
      ["locations", "Locations", () => locationsTab()],
      ["addresses", "Addresses", () => addressesTab()],
      ["browsers", "Company browsers", () => workspaceTab(A.can("govern"))],
      ["prices", "Model prices", () => pricesTab(A.can("money"))],
      ["rates", "Media rates", () => ratesTab()],
      A.isOwner() && ["users", "Console users", () => consoleUsersTab()],
      ["account", "Your account", () => accountTab()],
    ], { vertical: true }));
  }

  /* Access & records: grouped settings, one row each, and one save bar that appears only when something has
     changed. Each control is open only to the role that owns it (Settings areas come from the server). */
  async function safetyTab() {
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
    const check = () => { bar.hidden = JSON.stringify(all()) === saved; };
    [retention, rate, contact, ...Object.values(ret)].forEach((x) => x.addEventListener("input", check));
    [storeBodies, blockSecrets, selfKeys, gateFull].forEach((x) => x.addEventListener("change", check));
    discard.addEventListener("click", () => A.render());
    save.addEventListener("click", async () => {
      save.disabled = true;
      try { await api("PUT", "/settings", { ...values(), reason: reason.value }); toast("Settings saved."); A.render(); }
      catch (e) { err.textContent = e.message; }
      finally { save.disabled = false; }
    });
    const unit = (input, text) => el("span", { class: "unit" }, input, text);
    const anyEditable = st.areas ? Object.values(st.areas).some((a) => A.can(a)) : A.isOwner();
    return [
      A.panel("Records", `${st.records.toLocaleString()} requests · ${(st.db_bytes / 1048576).toFixed(1)} MB on disk`,
        A.settingRow("Keep records for", "Older request records are deleted automatically every hour. 0 keeps everything. Staff see this number on their privacy page.", unit(retention, "days")),
        A.settingRow("Keep full request and response bodies", "Needed to pull back exactly what was sent. Off keeps only the summary: who, model, prompt, commands, cost.", storeBodies),
        A.settingRow("Full bodies", "Drop the stored bodies sooner than the record itself; the summary stays. 0 = as long as the record.", unit(ret.retention_bodies_days, "days")),
        A.settingRow("Website visits", "The browser gate's log: which tool, when, how long. 0 = forever.", unit(ret.retention_site_days, "days")),
        A.settingRow("Tools opened from Swangz AI", "0 = forever.", unit(ret.retention_launch_days, "days")),
        A.settingRow("Audit log", "At least 365 days, or 0 for forever: the record of what admins did should outlive what it watches. Every purge is itself written to the audit log.",
          unit(ret.retention_audit_days, "days"))),
      A.panel("Protection", null,
        A.settingRow("Refuse requests that contain credentials", "API keys, cloud keys, private keys. Off lets them through but flags them. On can interrupt an agent that reads a .env file.", blockSecrets),
        A.settingRow("Rate limit", "Catches a runaway tool. 0 means no limit. A busy agent can make several requests a minute, so keep it generous.", unit(rate, "a minute, per person"))),
      A.panel("Staff", null,
        A.settingRow("Staff can connect their own devices", "In the Swangz AI app they create and disconnect their own keys. Every key still shows up under Devices, and you can revoke any of them.", selfKeys),
        A.settingRow("Website gate: full-content logging", "Off by default, and the honest choice: the browser extension records only which approved site staff open and for how long. Staff are told in the extension's policy.", gateFull, { tone: "warn" }),
        A.settingRow("Who staff contact for help", "Shown on the staff app's privacy page and wherever access is refused.", contact)),
      anyEditable ? bar : el("div", { class: "notice info" }, icon("info"), "Your role can see these but not change them."),
    ];
  }

  /* The stops. Each acts at once — after a deliberate yes — and is written to the audit log. */
  async function emergencyTab() {
    const st = await api("GET", "/settings");
    const can = A.can("emergency");
    const put = async (body, msg) => {
      try { await api("PUT", "/settings", body); toast(msg); A.render(); } catch (e) { toast(e.message, true); A.render(); }
    };
    const off = new Set(st.disabled_providers);
    const providerRows = st.providers.map((p) => {
      const sw = A.switchInput(!off.has(p.name), !can, `${p.label || p.name} on`);
      sw.addEventListener("change", async () => {
        const turningOff = !sw.checked;
        if (turningOff && !(await A.confirmAction(`Switch ${p.label || p.name} off?`, "Every new request to it is refused until it is switched back on. Requests already running finish.", "Switch off", true))) { sw.checked = true; return; }
        const next = new Set(off);
        if (turningOff) next.add(p.name); else next.delete(p.name);
        put({ disabled_providers: [...next] }, turningOff ? `${p.label || p.name} is off.` : `${p.label || p.name} is back on.`);
      });
      return A.settingRow(el("span", { class: "row" }, p.label || p.name, off.has(p.name) ? SUI.status("blocked", "Off", { plain: true }) : null),
        p.configured ? "Requests to it go through as usual." : "No company key on the server yet, so its requests are refused anyway.", sw);
    });
    const ws = A.switchInput(!st.workspace_paused, !can, "Company browsers on");
    ws.addEventListener("change", async () => {
      if (!ws.checked && !(await A.confirmAction("Pause the company browsers?", "Nobody can open a shared tool in a company browser until they are resumed. Turns already running keep their browser until they end.", "Pause", true))) { ws.checked = true; return; }
      put({ workspace_paused: !ws.checked }, ws.checked ? "Company browsers resumed." : "Company browsers paused.");
    });
    return [
      A.panel("Stop everything", null,
        A.settingRow(el("span", { class: "row" }, "Kill switch", st.paused ? SUI.status("blocked", "AI is paused", { plain: true }) : SUI.status("ok", "AI is on", { plain: true })),
          "Cuts every request in flight, refuses new ones, and closes the portal's Open buttons until someone resumes.",
          can ? (st.paused ? el("button", { class: "btn primary", onclick: () => A.setPaused(false) }, "Resume access")
            : el("button", { class: "btn danger", onclick: () => A.setPaused(true) }, icon("stop"), "Stop all AI")) : null)),
      A.panel("One service at a time", "switch a provider off without stopping everything", providerRows),
      A.panel("Company browsers", null, A.settingRow("Company browsers for shared accounts", "Pause if a workspace server misbehaves; the tools' own sites are unaffected.", ws)),
      el("p", { class: "hint" }, "Also here, one at a time: stop a single request (Live), suspend a person or revoke a device (their page), take back a shared turn (the tool), switch a model off (Models). ",
        can ? "" : "Your role can see these but not use them."),
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
    return [unpriced, A.panel("Media rates", edit ? el("button", { class: "btn small", onclick: () => addRate(data) }, icon("plus"), "Add a rate") : "estimated costs for voice, image and video", table,
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
    const copyable = (text) => el("div", { class: "row end" }, el("span", { class: "value-mono", title: text }, text),
      el("button", { class: "btn small quiet icon-only", type: "button", "aria-label": "Copy " + text, onclick: () => SUI.copy(text) }, icon("copy")));
    const providers = SUI.table({ caption: "Providers", rows: st.providers, cards: true, columns: [
      { key: "label", label: "Provider", lead: true, render: (p) => el("div", null, el("strong", null, p.label || p.name), el("span", { class: "sub" },
        { anthropic: "chat & coding models", openai: "chat & coding models", elevenlabs: "voice & sound", higgsfield: "image & video" }[p.dialect] || "AI service")) },
      { key: "addr", label: "Address for staff tools", sort: false, render: (p) => el("span", { class: "mono" }, `${st.base_url}/${p.name}` + (p.dialect === "openai" ? "/v1" : "")) },
      { key: "upstream", label: "Forwards to", sort: false, render: (p) => el("span", { class: "mono faint" }, p.upstream), hideSm: true },
      { key: "configured", label: "API key", render: (p) => (p.configured ? SUI.status("ok", "Key set", { plain: true }) : el("span", null, SUI.status("blocked", "Off", { plain: true }), el("span", { class: "sub" }, `set ${p.key_env} on the server`))) }] });
    return [
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
    return [places, relay, signing];
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
    return [unpriced, A.panel("Model prices", owner ? el("div", { class: "row" }, el("span", { class: "sub" }, "US dollars per million tokens"),
      el("button", { class: "btn small", onclick: () => editPrice({}) }, icon("plus"), "Add a price")) : "US dollars per million tokens",
    SUI.table({ caption: "Model prices", rows: prices.items, sort: ["model", "asc"], columns: [
      { key: "model", label: "Model", lead: true, render: (x) => el("span", { class: "mono" }, x.model) },
      { key: "input", label: "Input", num: true, render: (x) => usd(x.input) },
      { key: "output", label: "Output", num: true, render: (x) => usd(x.output) },
      { key: "cache_write", label: "Cache write", num: true, render: (x) => (x.cache_write === null ? "—" : usd(x.cache_write)), hideSm: true },
      { key: "cache_read", label: "Cache read", num: true, render: (x) => (x.cache_read === null ? "—" : usd(x.cache_read)), hideSm: true },
      owner ? { key: "edit", label: "", sort: false, srLabel: "Edit", cls: "act", render: (x) => el("button", { class: "btn small quiet", onclick: () => editPrice(x) }, "Edit") } : null].filter(Boolean) }))];
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
    return [A.panel("Console users", el("button", { class: "btn small", onclick: () => adminDialog(null) }, icon("plus"), "Add a console user"),
      SUI.table({ caption: "Console users", rows: admins.items, sort: ["username", "asc"], columns: [
        { key: "username", label: "User", lead: true, render: (a) => el("span", { class: "u-cell" }, SUI.avatar(a.username, "sm"), el("strong", null, a.username)) },
        { key: "role", label: "Role", render: (a) => el("div", null, SUI.badge(a.role_label, a.owner ? "gold" : "outline"),
          el("span", { class: "sub" }, a.owner ? "everything" : a.can.length ? a.can.join(", ") : "read-only")) },
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

  async function pageReports(params) {
    const list = await api("GET", "/reports");
    A.frame({ title: "Reports", lede: "The standard questions, answered for any period, ready to download. Every amount says what it rests on: estimated from prices and rates, allocated from a plan, or unpriced. Downloads are written to the audit log." },
      A.pageTabs("#/reports", params, list.items.map((r) => [r.kind, r.title, () => reportTab(r.kind, params)]), { vertical: true }));
  }

  async function reportTab(kind, params) {
    const range = A.rangeFrom(params, "month");
    const holder = el("div");
    const dl = el("a", { class: "btn" }, icon("download"), "Download CSV");
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
      A.keepParams("#/reports", { tab: kind, range: r.preset, from: r.preset === "custom" ? r.from : null, to: r.preset === "custom" ? r.to : null });
      draw(r);
    } });
    draw(range);
    return A.panel(null, el("div", { class: "row" }, ctl, dl), holder);
  }

  A.page(/^#\/reports$/, pageReports);
  A.page(/^#\/licences$/, pageLicences);
  A.page(/^#\/settings$/, pageSettings);
})();
