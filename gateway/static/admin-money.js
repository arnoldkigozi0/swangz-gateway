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
    const owner = A.isOwner();
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
        A.kpi({ label: "AI software spend · this month", icon: "wallet", value: fmt.money(s.total_month), tone: "gold hero",
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
      box.replaceChildren(
        el("div", { class: "spend-hero" },
          el("div", null, el("div", { class: "u-label" }, "Metered AI spend"), el("div", { class: "hero-num" }, fmt.money(total)),
            el("div", { class: "row" }, SUI.delta(d.change, { vs: "vs the period before" }), el("span", { class: "hint" }, `vs ${fmt.money(d.previous_total)} the period before`))),
          el("div", { class: "spend-facts" },
            el("div", null, el("span", { class: "k" }, "Requests"), el("span", { class: "v u-num" }, fmt.num(d.requests))),
            el("div", null, el("span", { class: "k" }, "Unpriced"), el("span", { class: "v u-num" }, fmt.num(d.unpriced)),
              d.unpriced ? el("a", { class: "hint", href: "#/settings?tab=prices" }, "price them") : null),
            el("div", null, el("span", { class: "k" }, "Company plans"), el("span", { class: "v u-num" }, fmt.money(d.subscriptions_month) + "/mo")))),
        d.series.length > 1 ? A.panel("Spend per day", "estimated from the price table · " + SUI.tzLabel(true), el("div", { class: "body" },
          SUI.line({ label: "Metered spend per day", format: fmt.money, tick: fmt.moneyShort, yName: "Spend",
            data: d.series.map((x) => ({ label: fmt.weekday(x.start), short: fmt.dayMonth(x.start), value: x.cost, note: SUI.plural(x.requests, "request") })) }))) : null,
        el("div", { class: "grid cols-even" },
          A.panel("Unexpected increases", "at least half again the period before, and $1 more", d.increases.length ? el("ul", { class: "mini-list" }, d.increases.map((x) => el("li", null,
            el("span", { class: "mini-ic warn" }, icon("trendUp")),
            el("div", { class: "grow" }, el("strong", null, x.label), el("div", { class: "hint" }, `${LABEL[x.dimension]} · ${fmt.money(x.previous)} → ${fmt.money(x.cost)}`)),
            x.new ? SUI.badge("new", "warn") : SUI.delta(x.change)))) : SUI.stateBox({ tone: "ok", icon: "checkCircle", compact: true, title: "No unexpected increases", text: "Nothing grew sharply against the period before." })),
          A.panel("Idle subscriptions", "paid seats not used in 30 days", d.idle.length ? el("ul", { class: "mini-list" }, d.idle.map((x) => el("li", null,
            A.toolLogo(x.tool_id, x.tool, "sm"), el("div", { class: "grow" }, el("strong", null, x.tool), el("div", { class: "hint" }, `${x.idle} of ${x.assigned} seats idle`)),
            el("span", { class: "u-num" }, "≈ " + fmt.money(x.idle_cost) + "/mo")))) : SUI.stateBox({ tone: "ok", icon: "checkCircle", compact: true, title: "No idle subscriptions", text: "Every paid seat was used." }))),
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
        A.panel("How spend is worked out", null, el("div", { class: "body method" },
          el("div", null, SUI.status("ok", "Estimated", { plain: true }), el("p", null, "Each request through the gateway is priced from the model price table (Settings → Model prices) the moment it runs, using the tokens the provider reports. Changing a price later doesn't change past requests.")),
          el("div", null, SUI.status("waiting", "Unpriced", { plain: true }), el("p", null, "A model missing from the price table has no cost, so spend is understated until it's priced. Voice, image and video are metered in the service's own units.")),
          el("div", null, SUI.status("info", "Plans", { plain: true }), el("p", null, "Company plans are the fixed monthly cost set on each subscription — not metered here, and not split by person.")),
          el("div", null, SUI.status("none", "Not here", { plain: true }), el("p", null, "Vendor invoices aren't imported, and a shared account's own credit use is matched by turn, not priced.")))));
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
    const owner = A.isOwner();
    A.frame({ title: "Settings", lede: owner ? "The switches that govern the whole gateway. Every change is written to the audit log." : "You're a viewer: you can see these settings but not change them." },
      A.pageTabs("#/settings", params, [
        ["safety", "Access & records", () => safetyTab(owner)],
        ["addresses", "Addresses", () => addressesTab()],
        ["browsers", "Company browsers", () => workspaceTab(owner)],
        ["prices", "Model prices", () => pricesTab(owner)],
        owner && ["users", "Console users", () => consoleUsersTab()],
        ["account", "Your account", () => accountTab()],
      ]));
  }

  async function safetyTab(owner) {
    const st = await api("GET", "/settings");
    const switchPanel = A.panel("Kill switch", null, el("div", { class: "body spread" },
      el("div", null, el("div", { class: "row" }, st.paused ? SUI.status("blocked", "AI access is paused for everyone") : SUI.status("ok", "AI access is on")),
        el("div", { class: "hint" }, "Stopping cuts every request in flight, refuses new ones, and closes the portal's Open buttons until someone resumes.")),
      owner ? (st.paused ? el("button", { class: "btn primary", onclick: () => A.setPaused(false) }, "Resume access")
        : el("button", { class: "btn danger", onclick: () => A.setPaused(true) }, icon("stop"), "Stop all AI")) : null));
    const retention = el("input", { type: "number", min: "0", step: "1", value: String(st.retention_days), disabled: !owner });
    const storeBodies = el("input", { type: "checkbox", checked: st.store_bodies, disabled: !owner });
    const blockSecrets = el("input", { type: "checkbox", checked: st.block_secrets, disabled: !owner });
    const selfKeys = el("input", { type: "checkbox", checked: st.staff_self_keys, disabled: !owner });
    const gateFull = el("input", { type: "checkbox", checked: st.gate_log_full, disabled: !owner });
    const rate = el("input", { type: "number", min: "0", step: "1", value: String(st.rate_per_min || 0), disabled: !owner });
    const contact = el("input", { type: "text", maxlength: "200", value: st.support_contact || "", placeholder: "e.g. IT desk — it@swangzavenue.com, ext. 204", disabled: !owner });
    const recErr = el("div", { class: "err", role: "alert" });
    const records = A.panel("Records and rules", `${st.records.toLocaleString()} requests · ${(st.db_bytes / 1048576).toFixed(1)} MB on disk`, el("div", { class: "body stack" },
      el("label", { class: "field" }, "Keep records for (days)", retention, el("span", { class: "hint" }, "Older records and their bodies are deleted automatically every hour. 0 keeps everything. Staff see this number on their privacy page.")),
      el("label", { class: "check" }, storeBodies, el("span", null, el("strong", null, "Keep full request and response bodies"), el("div", { class: "hint" }, "Needed to pull back exactly what was sent. Off = only the summary (who, model, prompt, commands, cost)."))),
      el("label", { class: "check" }, selfKeys, el("span", null, el("strong", null, "Staff can connect their own devices"), el("div", { class: "hint" }, "In the Swangz AI app they create and disconnect their own keys. Every key still shows up under Devices, and you can revoke any of them."))),
      el("label", { class: "check" }, blockSecrets, el("span", null, el("strong", null, "Refuse requests that contain credentials"), el("div", { class: "hint" }, "API keys, cloud keys, private keys. Off = let them through but flag them. On can interrupt an agent that reads a .env file."))),
      el("label", { class: "check" }, gateFull, el("span", null, el("strong", null, "Website gate: full-content logging"), el("div", { class: "hint" }, "Off by default, and the honest choice. The browser extension records only which approved site staff open and for how long. Turn this on only with legal sign-off — staff are told in the extension's policy."))),
      el("label", { class: "field" }, "Rate limit (requests per person per minute)", rate, el("span", { class: "hint" }, "Catches a runaway tool. 0 = no limit. A busy agent can make several a minute, so keep it generous.")),
      el("label", { class: "field" }, "Who staff contact for help", contact, el("span", { class: "hint" }, "Shown on the staff app's privacy page and wherever access is refused.")),
      recErr,
      owner ? el("div", null, el("button", { class: "btn primary", onclick: async () => {
        try {
          await api("PUT", "/settings", { retention_days: retention.value, store_bodies: storeBodies.checked, block_secrets: blockSecrets.checked, staff_self_keys: selfKeys.checked,
            gate_log_full: gateFull.checked, rate_per_min: rate.value, support_contact: contact.value });
          recErr.textContent = ""; toast("Saved.");
        } catch (e) { recErr.textContent = e.message; }
      } }, "Save")) : null));
    return [switchPanel, records];
  }

  async function addressesTab() {
    const st = await api("GET", "/settings");
    const providers = SUI.table({ caption: "Providers", rows: st.providers, cards: true, columns: [
      { key: "label", label: "Provider", lead: true, render: (p) => el("div", null, el("strong", null, p.label || p.name), el("span", { class: "sub" },
        { anthropic: "chat & coding models", openai: "chat & coding models", elevenlabs: "voice & sound", higgsfield: "image & video" }[p.dialect] || "AI service")) },
      { key: "addr", label: "Address for staff tools", sort: false, render: (p) => el("span", { class: "mono" }, `${st.base_url}/${p.name}` + (p.dialect === "openai" ? "/v1" : "")) },
      { key: "upstream", label: "Forwards to", sort: false, render: (p) => el("span", { class: "mono faint" }, p.upstream), hideSm: true },
      { key: "configured", label: "API key", render: (p) => (p.configured ? SUI.status("ok", "Key set", { plain: true }) : el("span", null, SUI.status("blocked", "Off", { plain: true }), el("span", { class: "sub" }, `set ${p.key_env} on the server`))) }] });
    return A.panel("Addresses and providers", "staff tools point at these", providers,
      el("div", { class: "body stack" },
        el("div", null, el("span", { class: "u-label" }, "Staff app "), el("span", { class: "mono" }, st.base_url + "/"), el("span", { class: "hint" }, " — where staff sign in and open their tools")),
        el("div", null, el("span", { class: "u-label" }, "Control room "), el("span", { class: "mono" }, st.base_url + "/admin"), el("span", { class: "hint" }, " — this console; don't share it with staff")),
        el("div", null, el("span", { class: "u-label" }, "Time zone "), el("span", { class: "mono" }, SUI.tzLabel()), el("span", { class: "hint" }, " — budgets reset at midnight here (GATEWAY_TZ_OFFSET)"))),
      el("div", { class: "body hint" }, "Provider API keys live only in the server's environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, …). They are never shown here and never leave the server."));
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
      return el("div", { class: "assign-row" },
        el("span", { class: "dev-ic sm" }, icon(h.kind === "server" ? "server" : "monitor")),
        el("div", { class: "grow" }, el("strong", null, cap(h.label)), " ", h.active ? SUI.badge("In use", "gold") : null, " ", SUI.status(tone, state, { plain: true }),
          el("div", { class: "hint" }, detail)),
        buttons.length ? el("span", { class: "row" }, buttons) : null);
    };
    const places = A.panel("Where the company browsers run", "one place at a time — Open uses the one marked In use",
      el("div", { class: "body" }, el("div", { class: "assign-list" }, ws.hosts.map(card))),
      el("div", { class: "body hint" }, "Each place has browsers of its own, and each browser keeps its own sign-in to its tool — so sign a place's browsers in (below) before switching to it. Switching moves anyone in a company browser off the old place: their turn ends, and Open gives them a browser at the new one."));
    const RELAY = { cloudflare: "Cloudflare's video relay", own: "Swangz's own video relay (coturn)" };
    const relay = A.panel("Video from Swangz's own computers", null, el("div", { class: "body row" },
      ws.relay ? [SUI.status("ok", "Relay on", { plain: true }), el("span", null, "Through " + RELAY[ws.relay] + ": staff can work in a computer's browsers from anywhere.")]
        : [SUI.status("waiting", "No relay", { plain: true }), el("span", null, "Without one, only people on the same network as the computer can use its browsers. Add a Cloudflare TURN key to the gateway's settings (GATEWAY_TURN_CLOUDFLARE_KEY_ID and GATEWAY_TURN_CLOUDFLARE_TOKEN — see deploy/WORKSPACE.md). The rented server doesn't need one.")]));
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
    const unpriced = prices.unpriced_models.length ? el("div", { class: "body" }, el("div", { class: "notice" }, icon("alert"), "Used but not priced — their cost shows as “unpriced” and spend is understated:"),
      el("div", { class: "row" }, prices.unpriced_models.map((m) => owner ? el("button", { class: "btn small", onclick: () => editPrice({ model: m }) }, "Price " + m) : SUI.badge(m, "warn")))) : null;
    return A.panel("Model prices", "US dollars per million tokens", unpriced, SUI.table({ caption: "Model prices", rows: prices.items, sort: ["model", "asc"], columns: [
      { key: "model", label: "Model", lead: true, render: (x) => el("span", { class: "mono" }, x.model) },
      { key: "input", label: "Input", num: true, render: (x) => usd(x.input) },
      { key: "output", label: "Output", num: true, render: (x) => usd(x.output) },
      { key: "cache_write", label: "Cache write", num: true, render: (x) => (x.cache_write === null ? "—" : usd(x.cache_write)), hideSm: true },
      { key: "cache_read", label: "Cache read", num: true, render: (x) => (x.cache_read === null ? "—" : usd(x.cache_read)), hideSm: true },
      { key: "edit", label: "", sort: false, srLabel: "Edit", render: (x) => (owner ? el("button", { class: "btn small", onclick: () => editPrice(x) }, "Edit") : "") }] }),
    owner ? el("div", { class: "body" }, el("button", { class: "btn", onclick: () => editPrice({}) }, icon("plus"), "Add a model price")) : null);
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
    return A.panel("Console users", "owners change things; viewers only look", SUI.table({ caption: "Console users", rows: admins.items, sort: ["username", "asc"], columns: [
      { key: "username", label: "User", lead: true, render: (a) => el("span", { class: "u-cell" }, SUI.avatar(a.username, "sm"), el("strong", null, a.username)) },
      { key: "role", label: "Role", render: (a) => SUI.badge(a.role === "owner" ? "Owner" : "Viewer", a.role === "owner" ? "gold" : "outline") },
      { key: "last_login", label: "Last sign-in", num: true, render: (a) => fmt.ago(a.last_login) },
      { key: "x", label: "", sort: false, srLabel: "Remove", render: (a) => (a.username === S.me.username ? el("span", { class: "faint" }, "you") : el("button", { class: "btn danger small", onclick: () => removeAdmin(a) }, "Remove")) }] }),
    el("div", { class: "body" }, el("button", { class: "btn", onclick: addAdmin }, icon("plus"), "Add a console user")),
    el("div", { class: "body hint" }, "A console user whose username is their Google email can also sign in with Continue with Google."));
  }

  async function accountTab() {
    const cur = el("input", { type: "password", autocomplete: "current-password" });
    const nw = el("input", { type: "password", autocomplete: "new-password" });
    const pwErr = el("div", { class: "err", role: "alert" });
    return A.panel("Your password", S.me.username, el("div", { class: "body stack" },
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Current password", cur), el("label", { class: "field" }, "New password (10+ characters)", nw)), pwErr,
      el("div", null, el("button", { class: "btn primary", onclick: async () => {
        try { await api("POST", "/password", { current: cur.value, new: nw.value }); toast("Password changed."); cur.value = nw.value = ""; pwErr.textContent = ""; } catch (e) { pwErr.textContent = e.message; }
      } }, "Change password"))));
  }

  function addAdmin() {
    const user = el("input", { type: "text", autocomplete: "off" });
    const pw = el("input", { type: "password", autocomplete: "new-password" });
    const role = el("select", null, el("option", { value: "viewer" }, "Viewer — can see everything, change nothing"), el("option", { value: "owner" }, "Owner — can change everything"));
    const err = el("div", { class: "err", role: "alert" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try { await api("POST", "/admins", { username: user.value, password: pw.value, role: role.value }); d.close(); toast("Added."); A.render(); } catch (e) { err.textContent = e.message; }
    } }, "Add");
    const d = A.dialog("Add a console user", el("div", { class: "stack" },
      el("label", { class: "field" }, "Username", user, el("span", { class: "hint" }, "Use their Google email (e.g. name@swangzavenue.com) and they can also sign in with Google.")),
      el("label", { class: "field" }, "Password (10+ characters)", pw), el("label", { class: "field" }, "Role", role), err), [save]);
    user.focus();
  }

  async function removeAdmin(a) {
    const ok = await A.confirmAction(`Remove ${a.username}?`, "They can no longer sign in to the console.", "Remove", true);
    if (!ok) return;
    try { await api("DELETE", "/admins/" + a.id); toast("Removed."); A.render(); } catch (e) { toast(e.message, true); }
  }

  A.page(/^#\/licences$/, pageLicences);
  A.page(/^#\/settings$/, pageSettings);
})();
