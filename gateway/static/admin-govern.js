"use strict";
/* Governing access: people, their devices, the tool catalog and what staff ask for. Every object links
   to the others — a tool to the people using it, a person to their devices, a device to everything
   done from it — so following a thread never loses its place. Viewers see all of it; owners act. */
(() => {
  const { el, icon, fmt, toast } = SUI;
  const A = SWA;
  const { S, api } = A;
  const fact = (k, v, how) => el("div", { class: "fact" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), how ? el("div", { class: "how" }, SUI.evidence(how)) : null);
  const isoDate = (ts) => new Date(ts * 1000).toISOString().slice(0, 10);
  const DEVICE_STATE = { active: ["active", "Active"], idle: ["idle", "Idle"], unused: ["unused", "Never used"], revoked: ["revoked", "Revoked"], suspended: ["suspended", "Owner suspended"] };
  const deviceStatus = (s, plain) => SUI.status(...(DEVICE_STATE[s] || ["info", s]), { plain });
  // a coding tool's user agent often names no operating system; then there is no platform to show
  const platformOf = (d) => (d.platform && d.platform !== d.app ? d.platform : null);

  // ------------------------------------------------------------------ People

  function personState(p) {
    if (p.status !== "active") return ["suspended", "Suspended"];
    if (p.access_until && p.access_until <= Date.now() / 1000) return ["revoked", "Access ended"];
    return ["active", "Active"];
  }
  function signInBadge(state) {
    if (state === "active") return SUI.badge("App sign-in", "ok", "check");
    if (state === "invited") return SUI.badge("Invited", "warn", "send");
    return SUI.badge("No app sign-in", "outline");
  }

  async function pagePeople(params) {
    const data = await api("GET", "/people");
    const items = data.items;
    const st = { q: params.get("q") || "", dept: params.get("dept") || "", status: params.get("status") || "" };
    const now = Date.now() / 1000;
    const kpis = el("div", { class: "kpis five" },
      A.kpi({ label: "People", icon: "people", value: String(items.length), note: `${new Set(items.map((p) => p.department).filter(Boolean)).size} departments` }),
      A.kpi({ label: "Used AI today", icon: "spark", value: String(items.filter((p) => p.today.requests).length), note: "through the gateway" }),
      A.kpi({ label: "Working now", icon: "live", value: String(items.filter((p) => p.live).length), foot: items.some((p) => p.live) ? SUI.status("live", "Live", { breathe: true, plain: true }) : null, href: "#/live" }),
      A.kpi({ label: "Suspended or ended", icon: "lock", value: String(items.filter((p) => p.status !== "active" || (p.access_until && p.access_until <= now)).length) }),
      A.kpi({ label: "No app sign-in yet", icon: "user", value: String(items.filter((p) => p.sign_in === "none").length), note: "send them a sign-in link" }));
    const q = el("input", { type: "search", placeholder: "Search name, email, department…", value: st.q, "aria-label": "Search people" });
    const dept = el("select", { "aria-label": "Department" }, el("option", { value: "" }, "All departments"),
      [...new Set(items.map((p) => p.department).filter(Boolean))].sort().map((d) => el("option", { value: d }, d)));
    dept.value = st.dept;
    const box = el("div");
    function draw() {
      const qq = st.q.toLowerCase();
      const rows = items.filter((p) => (!st.dept || p.department === st.dept)
        && (!st.status || personState(p)[0] === st.status || (st.status === "invite" && p.sign_in !== "active"))
        && (!qq || [p.name, p.email, p.department, p.title].join(" ").toLowerCase().includes(qq)));
      box.replaceChildren(rows.length ? SUI.table({ caption: "People", rows, sort: ["last_seen", "desc"], href: (p) => "#/people/" + p.id, columns: [
        { key: "name", label: "Person", lead: true, render: (p) => el("div", { class: "u-cell" }, SUI.avatar(p.name),
          el("div", null, el("a", { href: "#/people/" + p.id }, el("strong", null, p.name)), el("span", { class: "sub" }, [p.title, p.department].filter(Boolean).join(" · ") || "No department"))) },
        { key: "status", label: "Status", sort: (p) => personState(p)[0], render: (p) => el("div", { class: "row" }, SUI.status(...personState(p), { plain: true }),
          p.live ? SUI.status("live", "Live", { breathe: true, plain: true }) : null) },
        { key: "sign_in", label: "App", render: (p) => signInBadge(p.sign_in), hideSm: true },
        { key: "active_keys", label: "Devices", num: true },
        { key: "today", label: "Today", num: true, sort: (p) => p.today.cost, render: (p) => el("span", null, fmt.money(p.today.cost), el("span", { class: "sub" }, SUI.plural(p.today.requests, "request")),
          p.daily_budget !== null ? A.bar(p.today.cost, p.daily_budget) : null) },
        { key: "month", label: "This month", num: true, sort: (p) => p.month.cost, render: (p) => el("span", null, fmt.money(p.month.cost),
          el("span", { class: "sub" }, p.monthly_budget !== null ? "of " + fmt.money(p.monthly_budget) : "no limit"), p.monthly_budget !== null ? A.bar(p.month.cost, p.monthly_budget) : null) },
        { key: "last_seen", label: "Last used AI", num: true, render: (p) => el("span", { title: p.last_seen ? fmt.stamp(p.last_seen) : null }, fmt.ago(p.last_seen)) },
      ] }) : SUI.stateBox({ icon: "people", title: items.length ? "Nobody matches" : "Nobody yet", text: items.length ? "Try another search or filter." : "Add the first person, then send them a sign-in link or issue a key." }));
    }
    const apply = () => { A.keepParams("#/people", { q: st.q, dept: st.dept, status: st.status }); draw(); };
    q.addEventListener("input", SUI.debounce(() => { st.q = q.value.trim(); apply(); }, 150));
    dept.addEventListener("change", () => { st.dept = dept.value; apply(); });
    draw();
    const add = A.isOwner() ? el("button", { class: "btn primary", onclick: addPerson }, icon("plus"), "Add person") : null;
    A.frame({ title: "People", lede: "Everyone with Swangz AI access — their status, devices, and what they spend.", actions: add }, [
      kpis,
      A.panel(null, null, el("div", { class: "filterbar" }, el("div", { class: "filters" },
        A.field("Search", q), A.field("Department", dept),
        el("div", { class: "field" }, el("span", null, "Status"), A.seg([["", "Everyone"], ["active", "Active"], ["suspended", "Suspended"], ["revoked", "Ended"], ["invite", "Not signed in"]],
          st.status, (v) => { st.status = v; apply(); }, "Status")))), box),
    ]);
    if (params.get("add") && A.isOwner()) addPerson();
  }

  function personForm(p) {
    p = p || {};
    const f = {
      name: el("input", { type: "text", value: p.name || "", required: true }),
      title: el("input", { type: "text", value: p.title || "", placeholder: "e.g. Director" }),
      department: el("input", { type: "text", value: p.department || "", placeholder: "e.g. Production" }),
      email: el("input", { type: "email", value: p.email || "" }),
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
        el("span", { class: "hint" }, "Comma-separated, * works as a wildcard: claude-sonnet-*, gpt-6-*. Empty = any model.")),
      el("label", { class: "field" }, "Allowed services", f.allowed_services,
        el("span", { class: "hint" }, "Comma-separated: " + S.me.providers.map((x) => x.name).join(", ") + ". Empty = every service the company has switched on.")),
      el("label", { class: "field" }, "Notes", f.notes));
    const values = () => Object.fromEntries(Object.entries(f).map(([k, input]) => [k, input.type === "checkbox" ? input.checked : input.value]));
    return { node, values, focus: () => f.name.focus() };
  }

  function addPerson() {
    const form = personForm();
    const err = el("div", { class: "err", role: "alert" });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try {
        const out = await api("POST", "/people", form.values());
        d.close();
        location.hash = "#/people/" + out.id;
      } catch (e) { err.textContent = e.message; }
    } }, "Add person");
    const d = A.dialog("Add a person", [form.node, err], [save]);
    form.focus();
  }

  async function pagePerson(params, id) {
    await A.toolIndex().catch(() => null);
    const p = await api("GET", "/people/" + id);
    const owner = A.isOwner();
    const [state, stateLabel] = personState(p);
    const since30 = Date.now() / 1000 - 30 * 86400;
    const [usage, security, recent] = await Promise.allSettled([
      api("GET", `/usage?person=${p.id}&since=${since30}`), api("GET", "/security?days=30"), api("GET", `/timeline?person=${p.id}&limit=1&since=${Date.now() / 1000 - 365 * 86400}`)]);
    const myEvents = security.status === "fulfilled" ? security.value.events.filter((e) => e.person_id === p.id) : null;
    const used = usage.status === "fulfilled" ? usage.value.rows : null;
    const last = recent.status === "fulfilled" && recent.value.items[0] ? recent.value.items[0] : null;
    const activeKeys = p.keys.filter((k) => !k.revoked);
    const current = activeKeys.filter((k) => k.last_used).sort((a, b) => b.last_used - a.last_used)[0];

    async function suspend(on) {
      if (on) {
        const ok = await A.confirmAction(`Suspend ${p.name}?`, "Every key they hold stops working now, anything streaming is cut, their shared-account turns end, and the portal stops opening tools for them. You can restore access later.", "Suspend", true);
        if (!ok) return;
      }
      try {
        const out = await api("POST", `/people/${p.id}/${on ? "suspend" : "resume"}`);
        toast(on ? `Suspended. ${out.cut} request(s) cut.` : "Access restored.");
        A.render();
      } catch (e) { toast(e.message, true); }
    }

    const kpis = el("div", { class: "kpis six" },
      A.kpi({ label: "Last seen", icon: "clock", value: last ? fmt.ago(last.ts) : "Never", note: last ? (last.type === "request" ? "AI request" : last.type === "launch" ? "opened " + (last.tool || "a tool") : "visited " + (last.tool || "a site")) : "no activity recorded" }),
      A.kpi({ label: "Current device", icon: "device", text: true, value: current ? current.label : "—", note: current ? "used " + fmt.ago(current.last_used) : activeKeys.length ? "not used yet" : "no active key", href: current ? "#/devices/" + current.id : null }),
      A.kpi({ label: "Active sessions", icon: "live", value: String(p.live.length), foot: p.live.length ? SUI.status("live", "In flight", { breathe: true, plain: true }) : SUI.status("idle", "Quiet", { plain: true }) }),
      A.kpi({ label: "Spend · month", icon: "wallet", value: fmt.money(p.month.cost), note: p.monthly_budget !== null ? "of " + fmt.money(p.monthly_budget) : "no monthly limit",
        foot: p.monthly_budget !== null ? A.bar(p.month.cost, p.monthly_budget) : null, tone: "gold" }),
      A.kpi({ label: "Tools · 30 days", icon: "tools", value: used ? String(used.length) : "—", note: `${p.tool_summary.enabled} enabled for them` }),
      A.kpi({ label: "Alerts · 30 days", icon: "shield", value: myEvents ? String(myEvents.filter((e) => e.severity !== "info").length) : "—",
        tone: myEvents && myEvents.some((e) => e.severity === "medium" || e.severity === "high") ? "alert" : null, href: `#/people/${p.id}?tab=security` }));

    async function overviewTab() {
      const live = p.live.length ? A.panel("Working right now", null, el("div", { class: "lv-stream" }, p.live.map((t) => el("article", { class: "lv" },
        el("div", { class: "lv-head" }, SUI.status(t.streaming ? "streaming" : "waiting", t.streaming ? "Streaming" : "Waiting", { breathe: true }), el("span", { class: "grow" }),
          el("span", { class: "elapsed u-num" }, fmt.elapsed(t.started))),
        el("div", { class: "lv-what" }, A.toolLink(null, t.client || "A tool"), el("span", { class: "mono faint" }, t.model || ""), A.deviceLink(t.key_id, t.device)),
        t.prompt ? el("p", { class: "lv-prompt" }, t.prompt) : null)))) : null;
      const tl = await api("GET", `/timeline?person=${p.id}&limit=15&since=${since30}`);
      const tools = used && used.length ? SUI.barList(used.slice().sort((a, b) => (b.requests + b.opens + b.visits) - (a.requests + a.opens + a.visits)).slice(0, 8).map((r) => ({
        label: r.tool, lead: A.toolLogo(r.tool_id, r.tool, "sm"), href: r.tool_id ? `#/tools?open=${r.tool_id}` : null, value: r.requests + r.opens + r.visits,
        display: fmt.compact(r.requests + r.opens + r.visits) + " uses", note: r.requests ? fmt.money(r.cost) : r.seconds ? fmt.dur(r.seconds) + " on site" : null })), { tone: 2 })
        : A.empty("No tool use in the last 30 days.", null, "tools");
      return [live,
        el("div", { class: "grid cols-2" },
          A.panel("Recent activity", el("a", { class: "btn small quiet", href: `#/activity?tab=timeline&person=${p.id}&range=30d` }, "Full timeline", icon("chevronRight")),
            tl.items.length ? A.eventDays(tl.items, { noPerson: true }).node : SUI.stateBox({ icon: "activity", title: "No AI activity yet", text: "Once they use an approved tool, it appears here.", compact: true })),
          el("div", { class: "grid" },
            A.panel("Tools used", "30 days", tools),
            A.panel("Recent sessions", "one conversation each", p.sessions.length ? el("ul", { class: "mini-list" }, p.sessions.slice(0, 6).map((x) => el("li", null,
              el("span", { class: "mini-ic" }, icon("layers")),
              el("a", { class: "grow", href: "#/sessions/" + encodeURIComponent(x.session) }, el("strong", null, x.first_prompt || "(no typed prompt)"),
                el("div", { class: "hint" }, `${x.client || "a tool"} · ${SUI.plural(x.requests, "request")} · ${fmt.when(x.last)}`)),
              el("span", { class: "u-num" }, fmt.money(x.cost)))))
              : A.empty("No sessions yet.")))),
        p.notes ? A.panel("Notes", null, el("div", { class: "body" }, el("pre", { class: "text" }, p.notes))) : null];
    }

    async function activityTab() {
      const st = { range: A.rangeFrom(params, "7d"), type: "" };
      const box = el("div");
      const more = el("button", { class: "btn", hidden: true }, "Load older");
      let next = null, days = null;
      async function load(reset) {
        const q = A.rangeQuery(st.range);
        q.set("person", p.id); q.set("limit", "50");
        if (st.type) q.set("type", st.type);
        if (!reset && next) q.set("before", String(next));
        const data = await api("GET", "/timeline?" + q.toString());
        next = data.next_before; more.hidden = !data.more;
        if (reset) { days = A.eventDays(data.items, { noPerson: true }); box.replaceChildren(data.items.length ? days.node : SUI.stateBox({ icon: "activity", title: "No AI activity in this period", text: "Try a wider range." })); }
        else days.add(data.items);
      }
      more.addEventListener("click", () => load(false).catch((e) => toast(e.message, true)));
      await load(true);
      return A.panel(null, el("a", { class: "btn small", href: A.gadmin(`/export.csv?person=${p.id}`) }, icon("download"), "Export CSV"),
        el("div", { class: "filterbar" }, SUI.rangeControl({ preset: st.range.preset, onChange: (r) => { st.range = r; load(true).catch((e) => box.replaceChildren(SUI.errorBox(e))); } }),
          el("div", { class: "filters" }, el("div", { class: "field" }, el("span", null, "Show"), A.seg([["", "Everything"], ["request", "AI requests"], ["launch", "Tools opened"], ["site", "Websites"]], "",
            (v) => { st.type = v; load(true).catch((e) => box.replaceChildren(SUI.errorBox(e))); }, "Kind of event")))),
        box, el("div", { class: "body center" }, more));
    }

    async function devicesTab() {
      const all = await api("GET", "/devices");
      const mine = all.items.filter((d) => d.person_id === p.id);
      const browsers = all.browsers.filter((b) => b.person_id === p.id);
      const signInState = { active: "Signs in to the Swangz AI app" + (p.last_login ? ` · last signed in ${fmt.ago(p.last_login)}` : ""),
        invited: `Sign-in link sent — valid until ${fmt.stamp(p.invite_expires)}`, none: "No app sign-in yet" }[p.sign_in];
      return [
        el("div", { class: "grid cols-2" },
          A.panel("Devices", SUI.plural(mine.filter((d) => d.state !== "revoked").length, "active key"), mine.length ? el("div", { class: "device-grid" }, mine.map((d) => deviceCard(d, true)))
            : A.empty("No keys yet. Issue one per laptop or coding tool.", "No devices", "device")),
          el("div", { class: "grid" },
            A.panel("Swangz AI app", null, el("div", { class: "body stack" },
              el("div", { class: "row" }, signInBadge(p.sign_in), el("span", { class: "muted" }, signInState)),
              el("div", { class: "hint" }, p.email ? `They sign in at ${S.me.base_url}/ with ${p.email}, or with Continue with Google if that email is their Google account.`
                : "Add their email under Details first — it is what they sign in with."),
              owner && p.email ? el("div", null, el("button", { class: "btn", onclick: () => inviteLink(p) }, icon("send"), p.sign_in === "active" ? "New sign-in link (reset password)" : "Create sign-in link")) : null)),
            A.panel("Browsers", "used to open tools · 90 days", browsers.length ? el("ul", { class: "mini-list" }, browsers.map((b) => el("li", null,
              el("span", { class: "mini-ic" }, icon("monitor")),
              el("div", { class: "grow" }, el("strong", null, [b.browser, b.os].filter(Boolean).join(" on ") || "Unknown browser"),
                el("div", { class: "hint" }, `${SUI.plural(b.opens, "open")} · last ${fmt.ago(b.last)}` + (b.last_ip ? " · " + b.last_ip : ""))))))
              : A.empty("They haven't opened a tool from the portal yet.")))),
      ];
    }

    async function securityTab() {
      if (!myEvents) return SUI.errorBox(security.reason, () => A.render());
      return A.panel("Signals involving " + p.name, "last 30 days", myEvents.length ? el("ul", { class: "sec-list" }, myEvents.map((e) => el("li", { class: "sec sev-" + e.severity },
        el("div", { class: "sec-head" }, el("strong", null, e.title), SUI.status(e.severity, e.severity[0].toUpperCase() + e.severity.slice(1)), el("span", { class: "grow" }), el("time", { class: "hint" }, fmt.ago(e.ts))),
        el("p", { class: "sec-text" }, e.text),
        el("div", { class: "sec-foot" }, e.evidence ? SUI.evidence(e.evidence) : el("span"), e.href ? el("a", { class: "btn small", href: e.href }, "Investigate", icon("chevronRight")) : null))))
        : SUI.stateBox({ tone: "ok", icon: "shield", title: "No security events", text: "Nothing involving them in the last 30 days." }));
    }

    async function detailsTab() {
      if (!owner) return A.panel("Details", null, el("div", { class: "body hint" }, "Only an owner can change someone's details."));
      const form = personForm(p);
      const err = el("div", { class: "err", role: "alert" });
      return A.panel("Details and limits", null, el("div", { class: "body stack" }, form.node, err,
        el("div", null, el("button", { class: "btn primary", onclick: async () => {
          try { await api("PATCH", "/people/" + p.id, form.values()); toast("Saved."); A.render(); } catch (e) { err.textContent = e.message; }
        } }, "Save changes"))));
    }

    const ended = p.access_until && p.access_until <= Date.now() / 1000;
    A.frame({
      title: p.name, lead: SUI.avatar(p.name, "lg"), status: el("span", { class: "row" }, SUI.status(state, stateLabel, { plain: true }), p.live.length ? SUI.status("live", "Live", { breathe: true, plain: true }) : null),
      crumbs: [el("a", { href: "#/people" }, "People")],
      lede: [[p.title, p.department].filter(Boolean).join(" · ") || "No department", p.email].filter(Boolean).join(" — ") +
        (p.access_until ? ` · access ${ended ? "ended" : "until"} ${fmt.date(p.access_until - 86400)}` : ""),
      actions: [owner && p.status === "active" ? el("button", { class: "btn primary", onclick: () => issueKey(p) }, icon("key"), "Issue a key") : null,
        owner ? el("span", { class: "act-gap" }) : null,
        owner ? (p.status === "active" ? el("button", { class: "btn danger", onclick: () => suspend(true) }, icon("lock"), "Suspend access")
          : el("button", { class: "btn", onclick: () => suspend(false) }, "Restore access")) : null],
    }, [kpis, A.pageTabs("#/people/" + p.id, params, [
      ["overview", "Overview", overviewTab],
      ["activity", "Activity", activityTab],
      ["tools", "Tools", async () => personToolsPanel(p, owner), p.tool_summary.enabled],
      ["devices", "Devices & sign-in", devicesTab, activeKeys.length],
      ["security", "Security", securityTab, myEvents ? myEvents.filter((e) => e.severity !== "info").length || null : null],
      ["details", "Details", detailsTab],
    ])]);
  }

  function personToolsPanel(p, owner) {
    const tools = p.tools || [];
    const grid = el("div", { class: "ptools" });
    function cell(t) {
      const can = owner && t.state !== "locked" && t.grant !== "team";
      const on = t.state === "enabled";
      const label = t.grant === "team" ? "Team" : t.state === "locked" ? "Locked" : on ? "On" : "Off";
      const btn = el("button", {
        class: "btn small" + (on && t.grant !== "team" ? " primary" : ""), disabled: !can, "aria-pressed": on ? "true" : "false",
        "aria-label": `${t.name}: ${label}`, title: t.grant === "team" ? "Granted to the whole " + (p.department || "team") : t.reason,
        onclick: can ? async () => {
          const adding = !btn.classList.contains("primary");
          try { await api(adding ? "POST" : "DELETE", `/people/${p.id}/tools/${t.id}`); A.render(); }
          catch (e) { toast(e.message, true); }
        } : null,
      }, label);
      const note = t.state === "locked" ? "not subscribed" : t.ends ? "until " + fmt.date(t.ends - 86400) : t.category;
      return el("div", { class: "ptool" + (on ? " on" : "") }, SUI.logo(t, "sm"), el("div", { class: "pn" }, el("strong", null, t.name), el("div", { class: "hint" }, note)), btn);
    }
    const assigned = tools.filter((t) => t.assigned);
    const rest = tools.filter((t) => !t.assigned && t.state !== "locked");
    grid.replaceChildren(...assigned.map(cell), ...rest.map(cell));
    const removeAll = owner && assigned.some((t) => t.grant === "direct") ? el("button", { class: "btn small danger", onclick: async () => {
      const ok = await A.confirmAction(`Remove every tool from ${p.name}?`, "Their direct tool access is removed now. Team access stays with the team, and their account stays open — suspend it too if they're leaving.", "Remove all tools", true);
      if (!ok) return;
      try { const out = await api("DELETE", `/people/${p.id}/tools`); toast(`Removed ${out.removed} tool(s).`); A.render(); } catch (e) { toast(e.message, true); }
    } }, "Remove all tools") : null;
    return A.panel("Tools", el("div", { class: "row" }, el("span", { class: "sub" }, `${p.tool_summary.enabled} ready · ${p.tool_summary.assigned} assigned`), removeAll),
      tools.length ? grid : A.empty("No tools in the catalog."),
      el("div", { class: "body hint" }, "Locked tools need a company subscription first, and team access is changed — both on the Tools page. To give a tool for a limited time, set an end date there under Who can use it."));
  }

  async function inviteLink(p) {
    try {
      const out = await api("POST", `/people/${p.id}/invite`);
      const text = `Hi ${p.name}, here is your Swangz AI sign-in link (valid ${out.expires_days} days): ${out.link}`;
      A.dialog(`Sign-in link for ${p.name}`, el("div", { class: "stack" },
        el("p", { class: "muted" }, `Send this to ${p.name} privately. It works once, for ${out.expires_days} days, and lets them choose a password for ${out.email}. Any older link stops working.`),
        el("div", { class: "spread" }, el("div", { class: "keybox" }, out.link), el("button", { class: "btn", onclick: () => SUI.copy(out.link) }, icon("copy"), "Copy link"))),
      [el("a", { class: "btn", href: "https://wa.me/?text=" + encodeURIComponent(text), target: "_blank", rel: "noopener noreferrer" }, "Share on WhatsApp"),
        el("button", { class: "btn primary", onclick: (e) => { e.target.closest("dialog").close(); A.render(); } }, "Done")]);
    } catch (e) { toast(e.message, true); }
  }

  function issueKey(p) {
    const label = el("input", { type: "text", placeholder: "e.g. Grace's MacBook — Claude Code", value: "" });
    const err = el("div", { class: "err", role: "alert" });
    const go = el("button", { class: "btn primary", onclick: async () => {
      try {
        const out = await api("POST", `/people/${p.id}/keys`, { label: label.value });
        d.close();
        showNewKey(p, out);
      } catch (e) { err.textContent = e.message; }
    } }, "Issue key");
    const d = A.dialog(`New key for ${p.name}`, el("div", { class: "stack" },
      el("label", { class: "field" }, "Which device or tool is it for?", label, el("span", { class: "hint" }, "One key per device or tool, so you can revoke one without stopping the rest. This name is how the device appears everywhere in the control room.")), err), [go]);
    label.focus();
  }

  function showNewKey(p, out) {
    const blocks = out.tools.map((t) => el("details", { open: t.id === "claude-code" ? true : null },
      el("summary", null, t.name, el("span", { class: "faint" }, " — " + t.kind)),
      t.steps.map((s) => el("div", { class: "stack step-block" },
        el("div", { class: "spread" }, el("strong", null, s.title), el("button", { class: "btn small", onclick: () => SUI.copy(s.code) }, icon("copy"), "Copy")),
        el("div", { class: "hint" }, s.how),
        el("pre", { class: "code" }, s.code)))));
    const done = el("button", { class: "btn primary", onclick: () => { d.close(); A.render(); } }, "I've saved it");
    const d = A.dialog(`Key for ${p.name}`, el("div", { class: "stack" },
      el("div", { class: "notice" }, icon("alert"), "This is the only time the key is shown. Copy it now and give it to them privately."),
      el("div", { class: "spread" }, el("div", { class: "keybox" }, out.key), el("button", { class: "btn", onclick: () => SUI.copy(out.key) }, icon("copy"), "Copy key")),
      el("h3", null, "How to connect their tools"),
      blocks), [done]);
  }

  // ------------------------------------------------------------------ Devices

  async function revokeKey(d) {
    const ok = await A.confirmAction(`Revoke “${d.label}”?`, `${d.hint} stops working immediately, including anything it is streaming right now. This can't be undone — issue a new key instead.`, "Revoke key", true);
    if (!ok) return false;
    try { const out = await api("POST", `/keys/${d.id}/revoke`); toast(`Revoked. ${out.cut} request(s) cut.`); A.render(); return true; }
    catch (e) { toast(e.message, true); return false; }
  }

  function deviceCard(d, noOwner) {
    return el("article", { class: "devcard s-" + d.state },
      el("div", { class: "devcard-head" }, el("span", { class: "dev-ic" }, icon(d.app === "Claude Code" || d.app === "Codex" ? "terminal" : "device")),
        el("div", { class: "grow" }, el("a", { href: "#/devices/" + d.id }, el("strong", null, d.label)), el("div", { class: "hint mono" }, d.hint)),
        deviceStatus(d.state)),
      el("dl", { class: "devcard-facts" },
        noOwner ? null : [el("dt", null, "Owner"), el("dd", null, A.personLink(d.person_id, d.person, { avatar: false }))],
        el("dt", null, "Application"), el("dd", null, d.app || "—"),
        el("dt", null, "Platform"), el("dd", null, platformOf(d) || el("span", { class: "faint" }, "not stated")),
        el("dt", null, "Last seen"), el("dd", null, d.last_used ? fmt.ago(d.last_used) : "never"),
        el("dt", null, "From"), el("dd", null, d.last_ip ? A.where(d.last_ip, d.place) : "—"),
        el("dt", null, "30 days"), el("dd", null, `${SUI.plural(d.requests_30d, "request")} · ${fmt.money(d.cost_30d)}`)),
      el("div", { class: "devcard-foot" }, el("a", { class: "btn small", href: "#/devices/" + d.id }, "Manage", icon("chevronRight")),
        A.isOwner() && d.state !== "revoked" ? el("button", { class: "btn small danger quiet", onclick: () => revokeKey(d) }, "Revoke") : null));
  }

  async function pageDevices(params) {
    const data = await api("GET", "/devices");
    const st = { q: params.get("q") || "", state: params.get("state") || "" };
    const c = data.counts;
    const q = el("input", { type: "search", placeholder: "Search device, owner, app, address…", value: st.q, "aria-label": "Search devices" });
    const box = el("div");
    function draw() {
      const qq = st.q.toLowerCase();
      const rows = data.items.filter((d) => (!st.state || d.state === st.state) && (!qq || [d.label, d.person, d.app, d.platform, d.last_ip, d.hint].join(" ").toLowerCase().includes(qq)));
      box.replaceChildren(rows.length ? SUI.table({ caption: "Devices", rows, sort: ["last_used", "desc"], href: (d) => "#/devices/" + d.id, columns: [
        { key: "label", label: "Device", lead: true, render: (d) => el("div", { class: "u-cell" }, el("span", { class: "dev-ic sm" }, icon(d.app === "Claude Code" || d.app === "Codex" ? "terminal" : "device")),
          el("div", null, el("a", { href: "#/devices/" + d.id }, el("strong", null, d.label)), el("span", { class: "sub mono" }, d.hint))) },
        { key: "person", label: "Owner", render: (d) => A.personLink(d.person_id, d.person) },
        { key: "platform", label: "Platform", render: (d) => platformOf(d) || el("span", { class: "faint" }, "not stated"), hideSm: true },
        { key: "app", label: "Application", render: (d) => d.app || "—" },
        { key: "last_used", label: "Last seen", num: true, render: (d) => el("span", { title: d.last_used ? fmt.stamp(d.last_used) : null }, d.last_used ? fmt.ago(d.last_used) : "never") },
        { key: "last_ip", label: "From", render: (d) => (d.last_ip ? A.where(d.last_ip, d.place) : "—"), hideSm: true },
        { key: "requests_30d", label: "30 days", num: true, render: (d) => el("span", null, fmt.num(d.requests_30d), el("span", { class: "sub" }, fmt.money(d.cost_30d))) },
        { key: "state", label: "Status", render: (d) => deviceStatus(d.state, true) },
      ] }) : SUI.stateBox({ icon: "device", title: data.items.length ? "No devices match" : "No devices yet", text: data.items.length ? "Try another search or status." : "A device appears when someone is issued a key, or connects one themselves in the staff app." }));
    }
    const apply = () => { A.keepParams("#/devices", { q: st.q, state: st.state }); draw(); };
    q.addEventListener("input", SUI.debounce(() => { st.q = q.value.trim(); apply(); }, 150));
    draw();
    A.frame({ title: "Devices", lede: "Every laptop and coding tool holding a gateway key — what it runs, where it connects from, and when it was last used." }, [
      el("div", { class: "kpis four" },
        A.kpi({ label: "Active · 7 days", icon: "device", value: String(c.active) }),
        A.kpi({ label: "Idle", icon: "clock", value: String(c.idle), note: "not used for 7+ days" }),
        A.kpi({ label: "Never used", icon: "key", value: String(c.unused), note: "issued, no requests yet" }),
        A.kpi({ label: "Revoked", icon: "lock", value: String(c.revoked + (c.suspended || 0)), note: c.suspended ? `+ ${c.suspended} with a suspended owner` : "keys that no longer work" })),
      el("div", { class: "notice info" }, icon("info"), "A device is one gateway key — staff use one per laptop or coding tool. Platform comes from the tool's user agent where it says; addresses are shown as recorded, and locations aren't looked up."),
      A.panel(null, null, el("div", { class: "filterbar" }, el("div", { class: "filters" }, A.field("Search", q),
        el("div", { class: "field" }, el("span", null, "Status"), A.seg([["", "All"], ["active", "Active"], ["idle", "Idle"], ["unused", "Never used"], ["revoked", "Revoked"]], st.state, (v) => { st.state = v; apply(); }, "Status")))), box),
      A.panel("Browsers used to open tools", "from the portal's Open button · 90 days", data.browsers.length ? SUI.table({ caption: "Browsers", rows: data.browsers, sort: ["last", "desc"], columns: [
        { key: "person", label: "Person", lead: true, render: (b) => A.personLink(b.person_id, b.person) },
        { key: "browser", label: "Browser", render: (b) => b.browser || "Unknown" },
        { key: "os", label: "System", render: (b) => b.os || "Unknown" },
        { key: "opens", label: "Opens", num: true },
        { key: "last", label: "Last", num: true, render: (b) => fmt.ago(b.last) },
        { key: "last_ip", label: "Last address", render: (b) => (b.last_ip ? el("span", { class: "mono faint" }, b.last_ip) : "—"), hideSm: true }] })
        : A.empty("Nobody has opened a tool from the portal yet.")),
    ]);
  }

  async function pageDevice(params, kid) {
    await A.toolIndex().catch(() => null);
    const d = await api("GET", "/devices/" + kid);
    const recent = await api("GET", `/requests?key=${kid}&limit=20`);
    const ips = d.ips.length ? SUI.table({ caption: "Recent addresses", rows: d.ips, sort: ["last", "desc"], cards: false, columns: [
      { key: "ip", label: "Address", render: (x) => el("span", { class: "mono" }, x.ip || "—") },
      { key: "place", label: "Network", render: (x) => x.place },
      { key: "first", label: "First", num: true, render: (x) => fmt.when(x.first) },
      { key: "last", label: "Last", num: true, render: (x) => fmt.when(x.last) },
      { key: "requests", label: "Requests", num: true }] }) : A.empty("No requests from this device yet.");
    A.frame({
      title: d.label, lead: el("span", { class: "dev-ic lg" }, icon(d.app === "Claude Code" || d.app === "Codex" ? "terminal" : "device")), status: deviceStatus(d.state, true),
      crumbs: [el("a", { href: "#/devices" }, "Devices"), el("a", { href: "#/people/" + d.person_id }, d.person)],
      lede: `${d.person}'s device` + (d.app ? ` · ${d.app}` : "") + (d.platform && d.platform !== d.app ? ` · ${d.platform}` : ""),
      actions: [el("a", { class: "btn", href: `#/activity?tab=ai&person=${d.person_id}` }, icon("activity"), "Their activity"),
        A.isOwner() && d.state !== "revoked" ? [el("span", { class: "act-gap" }), el("button", { class: "btn danger", onclick: () => revokeKey(d) }, icon("lock"), "Revoke device")] : null],
    }, [
      A.panel(null, null, el("div", { class: "facts" },
        fact("Owner", A.personLink(d.person_id, d.person)), fact("Status", deviceStatus(d.state, true)),
        fact("Key", el("span", { class: "mono" }, d.hint), "Only the key's ends are ever shown"),
        fact("Issued", fmt.date(d.created) + (d.created_by ? (d.created_by === "self" ? " · by them in the app" : " · by " + d.created_by) : "")),
        fact("First used", d.first_used ? fmt.stamp(d.first_used) : "never"), fact("Last seen", d.last_used ? fmt.stamp(d.last_used) : "never"),
        fact("Application", d.app || "—", "From the tool's user agent"), fact("Platform", platformOf(d) || "Not stated by the tool", "From the user agent"),
        fact("All-time use", `${SUI.plural(d.totals.requests, "request")} · ${fmt.tokens(d.totals.tokens)} tokens`),
        fact("All-time cost", fmt.money(d.totals.cost), "Estimated from the price table"),
        d.revoked ? fact("Revoked", fmt.stamp(d.revoked) + (d.revoked_by ? (d.revoked_by === "self" ? " · by them" : " · by " + d.revoked_by) : "")) : null)),
      el("div", { class: "grid cols-even" },
        A.panel("Activity", "requests per day · 30 days", el("div", { class: "body" }, SUI.columns({ label: "Requests per day from this device", tone: 2, yName: "Requests",
          data: d.series.map((x) => ({ label: fmt.weekday(x.start), short: fmt.dayMonth(x.start), value: x.requests, note: fmt.money(x.cost) })) }))),
        A.panel("Recent addresses", "locations aren't looked up", ips)),
      el("div", { class: "grid cols-even" },
        A.panel("Applications", null, d.apps.length ? el("ul", { class: "mini-list" }, d.apps.map((a) => el("li", null, el("span", { class: "mini-ic" }, icon("terminal")),
          el("div", { class: "grow" }, el("strong", null, a.client || "Not identified"), el("div", { class: "hint" }, (a.platform || "platform not stated") + " · last " + fmt.ago(a.last))),
          el("span", { class: "u-num" }, fmt.num(a.requests))))) : A.empty("Nothing yet.")),
        A.panel("Models", null, d.models.length ? SUI.barList(d.models.map((m) => ({ label: m.model, value: m.requests, display: fmt.num(m.requests), note: fmt.money(m.cost) })))
          : A.empty("Nothing yet."))),
      el("div", { class: "grid cols-even" },
        A.panel("Sessions", "one conversation each", d.sessions.length ? el("ul", { class: "mini-list" }, d.sessions.map((x) => el("li", null, el("span", { class: "mini-ic" }, icon("layers")),
          el("a", { class: "grow", href: "#/sessions/" + encodeURIComponent(x.session) }, el("strong", null, x.first_prompt || "(no typed prompt)"),
            el("div", { class: "hint" }, `${x.client || "a tool"} · ${SUI.plural(x.requests, "request")} · ${fmt.when(x.last)}`)),
          el("span", { class: "u-num" }, fmt.money(x.cost))))) : A.empty("No sessions yet.")),
        A.panel("Flagged or refused", "from this device", d.flagged.length ? el("ol", { class: "events flat" }, d.flagged.map((r) => el("li", { class: "ev t-request" },
          el("div", { class: "ev-rail" }, el("time", { class: "ev-time" }, fmt.when(r.ts))),
          el("div", { class: "ev-body" }, el("div", { class: "ev-head" }, A.outcomeStatus("request", r.outcome, true), A.flagBadges(r.flags), el("span", { class: "faint" }, r.client || "")),
            r.reason ? el("p", { class: "ev-reason" }, r.reason) : null),
          el("a", { class: "ev-open", href: "#/records/" + r.id, "aria-label": "Open record " + r.id }, el("span", null, "Record"), icon("chevronRight")))))
          : SUI.stateBox({ tone: "ok", icon: "shield", title: "Nothing flagged", text: "No credential detections or refusals from this device.", compact: true }))),
      A.panel("Everything done from this device", "latest 20", recent.items.length ? el("ol", { class: "events flat" }, recent.items.map((r) => A.eventItem(A.reqEvent(r), { noPerson: true })))
        : A.empty("No requests yet.")),
    ]);
  }

  // ------------------------------------------------------------------ Tools

  const SUB_LABEL = { none: "Not subscribed", active: "Active", past_due: "Past due", cancelled: "Cancelled" };
  const SUB_STATE = { active: "ok", past_due: "waiting", cancelled: "blocked", none: "none" };
  const SIGNIN = {
    sso: ["Company sign-in (SSO)", "Staff open it signed in with their Swangz work account. Set up single sign-on in the tool's admin settings and paste its sign-in link under Settings."],
    seat: ["Company seat", "Each person has their own seat on the company plan, invited to their work email. Swangz pays one bill for all seats."],
    shared: ["Shared company account", "One account the whole team uses. The portal hands it out a turn at a time, so whatever credits it burns can be traced to whoever held it, and the browser is signed out when the turn ends."],
    own: ["Own login", "Staff use their own account. Swangz controls access and keeps the record of who opened it."],
    api: ["Company API key", "Runs through this gateway on the company key — there is nothing to sign in to."],
  };
  const KIND = { site: "Website", api: "API + website", dev: "Developer agent" };
  const browserList = (t) => (t.workspace_mode === "agent" ? [] : (t.workspace_url || "").split("\n").map((x) => x.trim()).filter(Boolean));

  function subStatus(t) {
    const sub = t.subscription;
    if ((t.kind === "dev" || t.kind === "api") && sub.state === "none") return SUI.status("info", "On our API key", { plain: true });
    return SUI.status(SUB_STATE[sub.state] || "none", SUB_LABEL[sub.state] || sub.state, { plain: true });
  }

  async function pageTools(params) {
    await A.toolIndex(true);
    const data = S.catalog;
    const state = { q: params.get("q") || "", cat: "all", show: "all" };
    const opens = data.tools.reduce((n, t) => n + t.usage_30d.opens, 0);
    const users = data.tools.filter((t) => t.usage_30d.opens).length;
    const q = el("input", { type: "search", placeholder: "Search by name or category…", value: state.q, "aria-label": "Search tools", oninput: (e) => { state.q = e.target.value; draw(); } });
    const cat = el("select", { "aria-label": "Category" }, el("option", { value: "all" }, "All categories"), data.categories.map((c) => el("option", { value: c }, c)));
    cat.addEventListener("change", () => { state.cat = cat.value; draw(); });
    const show = el("select", { "aria-label": "Show" }, [["all", "All tools"], ["active", "Subscribed"], ["none", "Not subscribed"], ["assigned", "Given to someone"], ["unused", "Given, but not opened in 30 days"]]
      .map(([v, t]) => el("option", { value: v }, t)));
    show.addEventListener("change", () => { state.show = show.value; draw(); });
    const grid = el("div", { class: "toolsadmin" });
    const count = el("div", { class: "hint", role: "status" });
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
      grid.replaceChildren(...(list.length ? list.map(toolAdminCard) : [SUI.stateBox({ icon: "tools", title: "No tools match", text: "Try another search or filter." })]));
      count.textContent = `${SUI.plural(list.length, "tool")} shown`;
    }
    draw();
    const removed = data.removed.length ? A.panel("Removed from the catalog", "staff can't see or open these", el("div", { class: "removed" }, data.removed.map((t) =>
      el("div", null, SUI.logo(t, "sm"), el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.builtin ? "built-in" : "added by an admin")),
        A.isOwner() ? el("button", { class: "btn small", onclick: () => toolAction(t, "restore") }, "Restore") : null,
        A.isOwner() && !t.builtin ? el("button", { class: "btn small danger", onclick: () => deleteTool(t) }, "Delete") : null)))) : null;
    A.frame({ title: "Tools", lede: "What Swangz pays for, how people sign in, and who uses each tool. Open a tool for its full profile.",
      actions: A.isOwner() ? el("button", { class: "btn primary", onclick: () => toolSheet(null) }, icon("plus"), "Add a tool") : null }, [
      el("div", { class: "kpis four" },
        A.kpi({ label: "Tools in the catalog", icon: "tools", value: String(data.summary.total), note: data.removed.length ? `${data.removed.length} removed` : "across " + data.categories.length + " categories" }),
        A.kpi({ label: "Paid subscriptions", icon: "licences", value: String(data.summary.paid), note: "company plans that are active" }),
        A.kpi({ label: "Subscriptions a month", icon: "wallet", value: fmt.money(data.summary.monthly_cost), tone: "gold", href: "#/licences" }),
        A.kpi({ label: "Opens · 30 days", icon: "open", value: fmt.num(opens), note: `${SUI.plural(users, "tool")} opened from the portal` })),
      A.panel(null, null, el("div", { class: "filterbar" }, el("div", { class: "filters" }, A.field("Search", q), A.field("Category", cat), A.field("Show", show))),
        el("div", { class: "body tight" }, count), grid),
      removed,
    ]);
    const open = params.get("open");
    if (open && S.tools[open]) toolSheet(S.tools[open], params.get("tab") || "overview");
    if (params.get("add") && A.isOwner()) toolSheet(null);
  }

  function toolAdminCard(t) {
    const sub = t.subscription;
    const how = SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat;
    const money = sub.state !== "none" ? [sub.plan, sub.monthly_cost != null ? fmt.money(sub.monthly_cost) + "/mo" : null, sub.seats ? sub.seats + " seats" : null].filter(Boolean).join(" · ") : "";
    return el("button", { class: "tooladmin", type: "button", onclick: () => toolSheet(t), "aria-label": `${t.name}, ${t.category}. Open its profile.` },
      el("div", { class: "ta-head" }, SUI.logo(t), el("div", { class: "grow" }, el("strong", null, t.name), el("div", { class: "hint" }, t.category))),
      el("div", { class: "ta-body" },
        el("div", { class: "row" }, subStatus(t), SUI.badge(how[0], "outline")),
        money ? el("div", { class: "hint" }, money) : null),
      el("div", { class: "ta-foot" },
        el("span", null, t.assigned_people + t.assigned_teams === 0 ? "No one assigned"
          : [el("b", null, String(t.assigned_people)), t.assigned_people === 1 ? " person" : " people", t.assigned_teams ? [" · ", el("b", null, String(t.assigned_teams)), " team(s)"] : null]),
        el("span", null, el("b", null, String(t.usage_30d.opens)), " opens · 30d")));
  }

  async function toolAction(t, action) {
    if (action === "archive") {
      const ok = await A.confirmAction(`Remove ${t.name} from the catalog?`, "Staff stop seeing it straight away and can't open it from the portal. Its history stays, and you can restore it from the bottom of the Tools page.", "Remove", true);
      if (!ok) return false;
    }
    try { await api("POST", `/tools/${t.id}/${action}`); toast(action === "archive" ? "Removed from the catalog." : "Restored."); S.tools = null; await A.render(); return true; }
    catch (e) { toast(e.message, true); return false; }
  }

  async function deleteTool(t) {
    const ok = await A.confirmAction(`Delete ${t.name} for good?`, "It's removed from the catalog along with its subscription and every grant. Past launches stay in the log without a tool name. This can't be undone.", "Delete tool", true);
    if (!ok) return;
    try { await api("DELETE", `/tools/${t.id}`); toast("Deleted."); S.tools = null; A.render(); } catch (e) { toast(e.message, true); }
  }

  /* A tool's profile: what it is and how it's used (Overview), who holds it, what Swangz pays, and its settings. */
  function toolSheet(t, tab) {
    const { node, close } = A.sheet(() => { if (location.hash.includes("open=") || location.hash.includes("add=")) history.replaceState(null, "", "#/tools"); }, t ? t.name : "Add a tool");
    const owner = A.isOwner();
    const tabs = t ? [["overview", "Overview"], ["access", "Who can use it"], t.kind === "dev" ? null : ["billing", "Subscription"], ["settings", "Settings"]].filter(Boolean) : [["settings", "New tool"]];
    let current = t ? (tabs.some((x) => x[0] === tab) ? tab : "overview") : "settings";
    const body = el("div", { class: "sheet-body" });
    const tabBar = el("div", { class: "tabs", role: "tablist" });
    function drawTabs() {
      tabBar.replaceChildren(...tabs.map(([id, label]) => el("button", { type: "button", role: "tab", "aria-selected": id === current ? "true" : "false", class: id === current ? "on" : null,
        onclick: () => { current = id; drawTabs(); show(); if (t) history.replaceState(null, "", `#/tools?open=${t.id}&tab=${id}`); } }, label)));
    }
    async function refresh(nextTab) {
      close();
      S.tools = null;
      const next = t ? `#/tools?open=${t.id}&tab=${nextTab || current}` : "#/tools";
      if (location.hash === next) await A.render();
      else location.hash = next;
    }
    function show() {
      SUI.load(body, () => ({ overview: overviewTab, access: accessTab, billing: billingTab, settings: settingsTab })[current](), SUI.skeleton("rows", 4));
    }

    async function overviewTab() {
      const how = SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat;
      const sub = t.subscription;
      const u = await api("GET", `/tools/${t.id}/usage`);
      const uses30 = u.series.reduce((n, d) => n + d.uses, 0);
      const assigned = t.assigned_people + t.assigned_teams;
      return [
        t.description ? el("p", { class: "muted lead-text" }, t.description) : null,
        el("div", { class: "facts" },
          fact("Subscription", sub.state === "none" ? (t.kind === "site" ? "None yet" : "Metered on our API key") : [SUB_LABEL[sub.state], sub.plan].filter(Boolean).join(" · ")),
          fact("Seats", sub.seats ? `${sub.seats} paid` : "—"),
          fact("Assigned", `${SUI.plural(t.assigned_people, "person", "people")}` + (t.assigned_teams ? ` · ${SUI.plural(t.assigned_teams, "team")}` : "")),
          fact("Active this month", SUI.plural(u.active_month, "person", "people")),
          fact(t.kind === "site" ? "Monthly cost" : "API cost · 30 days", t.kind === "site" ? (sub.monthly_cost != null ? fmt.money(sub.monthly_cost) : "—") : fmt.money(u.cost_30d),
            t.kind === "site" ? null : "Estimated from the price table"),
          fact("Use · 30 days", uses30 ? SUI.plural(uses30, "use") : "none", "Opens, website visits and API requests"),
          t.signin === "shared" ? fact("Opens into", t.workspace_mode === "agent" ? "a company browser of their own, already signed in"
            : browserList(t).length ? `the shared workspace — ${SUI.plural(browserList(t).length, "browser")}` : "the tool's own site (they sign in)") : null),
        sub.seats && assigned ? el("div", { class: "seat-meter" }, el("div", { class: "spread" }, el("span", { class: "u-label" }, "Seat utilisation"),
          el("span", { class: "u-num" }, `${u.active_month} active of ${sub.seats} paid`)), A.bar(u.active_month, sub.seats)) : null,
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Use per day · 30 days"),
          SUI.columns({ label: `${t.name} uses per day`, tone: 2, height: 130, yName: "Uses", data: u.series.map((d) => ({ label: fmt.weekday(d.start), short: fmt.dayMonth(d.start), value: d.uses })) })),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Who uses it · 30 days"),
          u.people.length ? SUI.table({ caption: "Who uses " + t.name, rows: u.people, cards: false, sort: ["last", "desc"], columns: [
            { key: "person", label: "Person", render: (r) => A.personLink(r.person_id, r.person) },
            { key: "uses", label: "Uses", num: true, sort: (r) => r.requests + r.opens + r.visits, render: (r) => fmt.num(r.requests + r.opens + r.visits) },
            { key: "seconds", label: "Time", num: true, render: (r) => (r.seconds ? fmt.dur(r.seconds) : "—") },
            { key: "cost", label: "Cost", num: true, render: (r) => (r.requests ? fmt.money(r.cost) : "—") },
            { key: "last", label: "Last", num: true, render: (r) => fmt.ago(r.last) }] }) : A.empty("Nobody has used it in the last 30 days.")),
        u.devices.length ? el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Devices that ran it · 30 days"),
          el("ul", { class: "mini-list boxed" }, u.devices.map((x) => el("li", null, el("span", { class: "mini-ic" }, icon("device")),
            el("div", { class: "grow" }, A.deviceLink(x.key_id, x.label), el("div", { class: "hint" }, x.person + " · last " + fmt.ago(x.last))), el("span", { class: "u-num" }, fmt.num(x.requests)))))) : null,
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Denials · 30 days"),
          u.denials.length ? el("ul", { class: "mini-list boxed" }, u.denials.map((x) => el("li", null, el("span", { class: "mini-ic bad" }, icon("stop")),
            el("div", { class: "grow" }, x.person_id ? A.personLink(x.person_id, x.person, { avatar: false }) : el("span", null, x.person || "An unknown key"), el("div", { class: "hint" }, x.reason)),
            x.id ? el("a", { class: "hint", href: "#/records/" + x.id }, fmt.ago(x.ts)) : el("span", { class: "hint" }, fmt.ago(x.ts)))))
            : el("p", { class: "hint" }, "Nobody was refused.")),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "How people sign in — " + how[0]), el("p", { class: "hint" }, how[1]),
          t.launch_url ? el("div", { class: "hint" }, "Opens: ", el("span", { class: "mono" }, t.launch_url)) : null,
          t.url ? el("a", { class: "btn small", href: t.url, target: "_blank", rel: "noopener noreferrer" }, "Visit website", icon("open")) : null),
        t.hosts.length ? el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Domains the browser extension governs"),
          el("div", { class: "row" }, t.hosts.map((h) => el("span", { class: "u-badge outline mono" }, h)))) : null,
      ];
    }

    async function accessTab() {
      const data = await api("GET", `/tools/${t.id}/access`);
      const teams = data.teams.length ? el("div", { class: "row" }, data.teams.map((team) => {
        const btn = el("button", { class: "btn small" + (team.on ? " primary" : ""), disabled: !owner, "aria-pressed": team.on ? "true" : "false", "aria-label": `${team.name}: ${team.on ? "on" : "off"}`, onclick: async () => {
          const adding = !btn.classList.contains("primary");
          try { await api(adding ? "POST" : "DELETE", `/teams/${encodeURIComponent(team.name)}/tools/${t.id}`); btn.classList.toggle("primary", adding); btn.textContent = adding ? "On" : "Off"; btn.setAttribute("aria-pressed", adding ? "true" : "false"); toast("Saved."); }
          catch (e) { toast(e.message, true); }
        } }, team.on ? "On" : "Off");
        return el("div", { class: "team-toggle" }, el("span", null, team.name), btn);
      })) : el("div", { class: "hint" }, "Give people a department to grant whole teams at once.");
      const rows = data.people.map((p) => {
        const until = el("input", { type: "date", value: p.expires ? isoDate(p.expires - 86400) : "", disabled: !owner, title: "Optional end date", "aria-label": `${p.name}: access ends on` });
        const btn = el("button", { class: "btn small" + (p.granted ? " primary" : ""), disabled: !owner, "aria-pressed": p.granted ? "true" : "false", "aria-label": `${p.name}: ${p.granted ? "on" : "off"}` }, p.granted ? "On" : "Off");
        btn.addEventListener("click", async () => {
          const adding = !btn.classList.contains("primary");
          try {
            if (adding) await api("POST", `/people/${p.id}/tools/${t.id}`, until.value ? { until: until.value } : {});
            else await api("DELETE", `/people/${p.id}/tools/${t.id}`);
            btn.classList.toggle("primary", adding); btn.textContent = adding ? "On" : "Off"; btn.setAttribute("aria-pressed", adding ? "true" : "false");
            toast(adding ? "Turned on." : "Turned off.");
          } catch (e) { toast(e.message, true); }
        });
        until.addEventListener("change", async () => {
          if (!btn.classList.contains("primary")) return;
          try { await api("POST", `/people/${p.id}/tools/${t.id}`, { until: until.value || null }); toast(until.value ? "End date set." : "End date cleared."); }
          catch (e) { toast(e.message, true); }
        });
        return el("div", { class: "assign-row" },
          SUI.avatar(p.name, "sm"),
          el("div", { class: "grow" }, el("a", { href: "#/people/" + p.id }, el("strong", null, p.name)), " ", p.status !== "active" ? SUI.badge("suspended", "bad") : null,
            p.team ? SUI.badge("via team", "info") : null,
            el("div", { class: "hint" }, [p.department || "No department", p.last_opened ? "opened " + fmt.ago(p.last_opened) : "never opened"].join(" · "))),
          until, btn);
      });
      const locked = t.kind === "site" && t.subscription.state !== "active";
      let onItNow = null;
      if (t.signin === "shared") {
        const all = await api("GET", "/turns");
        const here = all.now.filter((x) => x.tool_id === t.id);
        const pool = browserList(t);
        const whereAt = (x) => (x.workspace ? (pool.includes(x.workspace) ? ` · browser ${pool.indexOf(x.workspace) + 1}` : " · a browser no longer listed") : "");
        onItNow = el("div", { class: "stack" }, el("h3", { class: "section-title" }, "On the shared account right now"),
          here.length ? el("div", { class: "assign-list" }, here.map((x) => el("div", { class: "assign-row" },
            SUI.avatar(x.person, "sm"),
            el("div", { class: "grow" }, el("strong", null, x.person), el("div", { class: "hint" }, "until " + fmt.clock(x.expires) + whereAt(x))),
            owner ? el("button", { class: "btn small danger", onclick: async () => {
              try { await api("POST", `/tools/${t.id}/turn/end`, { person_id: x.person_id }); toast("Taken back."); refresh("access"); }
              catch (e) { toast(e.message, true); }
            } }, "Take it back") : null)))
            : el("div", { class: "hint" }, `Nobody is on it. ${pool.length ? Math.min(t.seats_at_once, pool.length) : t.seats_at_once} at a time, ${t.turn_minutes} minutes a turn.`));
      }
      let fromServer = null;
      if (t.signin === "shared" && t.workspace_mode === "agent") {
        const ws = await api("GET", "/workspace");
        const mine = ws.configured && !ws.error ? (ws.browsers || []).filter((b) => b.tool === t.id) : [];
        const STATE = { running: ["ok", "Running"], starting: ["waiting", "Starting"], stopped: ["none", "Stopped"] };
        const openBrowser = async (slot, btn) => {
          btn.disabled = true; btn.textContent = "Starting…";
          try {
            for (let i = 0; i < 45; i++) {
              const out = await api("POST", `/workspace/browsers/${slot}/open`);
              if (out.state === "ready" && out.url) {
                btn.replaceWith(el("a", { class: "btn small primary", href: out.url, target: "_blank", rel: "noopener noreferrer" }, "Open it"));
                toast("Ready. Sign in to the tool inside it, then press Done.");
                return;
              }
              await new Promise((r) => setTimeout(r, 3000));
            }
            toast("The browser is taking too long to start. Try again in a minute.", true);
          } catch (e) { toast(e.message, true); }
          btn.disabled = false; btn.textContent = "Sign in to the tool";
        };
        const closeBrowser = async (slot) => {
          try { await api("POST", `/workspace/browsers/${slot}/close`); toast("Done — the browser is free again."); refresh("access"); }
          catch (e) { toast(e.message, true); }
        };
        const row = (b) => {
          const [tone, label] = STATE[b.state] || ["none", b.state];
          const who = !b.holder ? "Free" : b.holder.kind === "admin" ? `${b.holder.name} is signing it in` : `${b.holder.name} · since ${fmt.clock(b.holder.since)}`;
          let action = null;
          if (owner && b.holder && b.holder.kind === "admin") {
            action = el("span", { class: "row" },
              el("button", { class: "btn small", onclick: (e) => openBrowser(b.slot, e.currentTarget) }, "Open again"),
              el("button", { class: "btn small primary", onclick: () => closeBrowser(b.slot) }, "Done"));
          } else if (owner && !b.holder) {
            action = el("button", { class: "btn small", onclick: (e) => openBrowser(b.slot, e.currentTarget) }, "Sign in to the tool");
          }
          return el("div", { class: "assign-row" }, el("span", { class: "dev-ic sm" }, String(b.n)),
            el("div", { class: "grow" }, el("strong", null, `Browser ${b.n}`), " ", SUI.status(tone, label, { plain: true }), el("div", { class: "hint" }, who)), action);
        };
        fromServer = el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Browsers on the workspace server"),
          !ws.configured ? el("div", { class: "notice" }, "No workspace server is connected yet (GATEWAY_WORKSPACE_AGENT on the gateway).")
            : ws.error ? el("div", { class: "notice" }, "The workspace server isn't answering: " + ws.error)
              : mine.length ? el("div", { class: "assign-list" }, mine.map(row))
                : el("div", { class: "notice" }, `The workspace server has no browsers for this tool yet — add "${t.id}" to its config.`),
          el("p", { class: "hint" }, "Each browser keeps its own sign-in to the tool, so sign each one in once: press Sign in to the tool, open it, sign in to the tool inside it with the company account, then press Done. Nobody can be given that browser meanwhile."));
      }
      return [
        locked ? el("div", { class: "notice" }, "Staff can't open this until the company subscription is active (Subscription tab).") : null,
        onItNow, fromServer,
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Whole teams"), teams),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "People"),
          el("p", { class: "hint" }, "Turn the tool on per person. Add an end date first to give it for a limited time — access stops after that day."),
          rows.length ? el("div", { class: "assign-list" }, rows) : A.empty("No people yet.")),
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
      const err = el("div", { class: "err", role: "alert" });
      const save = owner ? el("button", { class: "btn primary", onclick: async () => {
        try {
          await api("PUT", "/subscriptions/" + t.id, { state: f.state.value, plan: f.plan.value, monthly_cost: f.monthly_cost.value, seats: f.seats.value, renews_on: f.renews_on.value, note: f.note.value });
          toast("Subscription saved."); refresh("billing");
        } catch (e) { err.textContent = e.message; }
      } }, "Save subscription") : null;
      return [
        el("p", { class: "hint" }, "One company account pays for the tool; each person gets their seat through the portal. Staff can only open website tools while this is Active."),
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "Status", f.state), el("label", { class: "field" }, "Plan", f.plan),
          el("label", { class: "field" }, "Monthly cost (USD)", f.monthly_cost), el("label", { class: "field" }, "Seats paid for", f.seats),
          el("label", { class: "field" }, "Renews on", f.renews_on)),
        el("label", { class: "field" }, "Note", f.note),
        t.plans.length ? el("div", { class: "hint" }, "Published plans: " + t.plans.map((p) => `${p.name}${p.monthlyUSD ? " $" + p.monthlyUSD : ""}`).join(" · "),
          t.pricing_url ? [" · ", el("a", { href: t.pricing_url, target: "_blank", rel: "noopener noreferrer" }, "pricing page")] : null) : null,
        sub.updated_by ? el("div", { class: "hint" }, `Last changed ${fmt.ago(sub.updated)} by ${sub.updated_by}.`) : null,
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
        workspace_mode: el("select", null,
          el("option", { value: "agent" }, "From the workspace server — started when needed"),
          el("option", { value: "" }, "The browsers listed below, or none")),
      };
      f.workspace_mode.value = v.workspace_mode === "agent" ? "agent" : "";
      const listField = el("label", { class: "field" }, "Shared workspace browsers", f.workspace_url,
        el("span", { class: "hint" }, "Optional. One address per line — each is a browser on Swangz's own server that an admin has signed in to this tool once. Everyone holding a turn gets a browser to themselves. Leave empty and Open goes to the tool's own site. See deploy/WORKSPACE.md."),
        el("span", { class: "hint" }, S.workspaceManaged ? "The gateway gives each person a sign-in for their turn and removes it the moment the turn ends."
          : "The gateway isn't managing workspace sign-ins yet (GATEWAY_WORKSPACE_TOKEN is not set), so each browser's own login decides who gets in."));
      const agentHint = el("span", { class: "hint" }, S.workspaceAgent
        ? "The workspace server starts a browser of their own for each person on a turn, signs them in, and recycles it when the turn ends. Sign each of its browsers in to the tool under Who can use it, once."
        : "No workspace server is connected yet (GATEWAY_WORKSPACE_AGENT is not set). Until it is, Open can't give anyone a browser for this tool. See deploy/WORKSPACE.md.");
      const drawWhere = () => { listField.hidden = f.workspace_mode.value === "agent"; agentHint.hidden = f.workspace_mode.value !== "agent"; };
      f.workspace_mode.addEventListener("change", drawWhere); drawWhere();
      const sharing = el("div", { class: "share-box" },
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "People on it at a time", f.seats_at_once, el("span", { class: "hint" }, "Usually 1 — one account, one person. With a workspace, never more than its browsers.")),
          el("label", { class: "field" }, "How long a turn lasts (minutes)", f.turn_minutes, el("span", { class: "hint" }, "It ends by itself after this, or when they hand it back."))),
        el("div", { class: "hint" }, "While someone holds the turn, nobody else can open this tool, and the extension signs their browser out when it ends — so the vendor's credit history can be matched to a person."),
        el("label", { class: "field" }, "Company browsers", f.workspace_mode, agentHint),
        listField);
      f.kind.value = v.kind; f.signin.value = v.kind === "dev" ? "api" : (v.signin || "seat");
      const howHint = el("span", { class: "hint" });
      const drawHow = () => { howHint.textContent = (SIGNIN[f.signin.value] || SIGNIN.seat)[1]; sharing.hidden = f.signin.value !== "shared"; };
      f.signin.addEventListener("change", drawHow); drawHow();
      const err = el("div", { class: "err", role: "alert" });
      const values = () => ({ name: f.name.value, category: f.category.value, kind: f.kind.value, description: f.description.value, url: f.url.value,
        signin: f.signin.value, launch_url: f.launch_url.value, hosts: f.hosts.value, color: f.color.value, pricing_url: f.pricing_url.value,
        seats_at_once: f.seats_at_once.value, turn_minutes: f.turn_minutes.value, workspace_url: f.workspace_url.value, workspace_mode: f.workspace_mode.value });
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
        logoBox = el("div", { class: "logo-edit" }, SUI.logo(t, "lg"), el("div", { class: "stack" },
          el("div", { class: "row" },
            owner ? el("button", { class: "btn small", onclick: () => file.click() }, "Upload a logo") : null,
            owner ? el("button", { class: "btn small", onclick: async (e) => {
              const b = e.currentTarget;
              b.disabled = true; b.textContent = "Fetching…";
              try { const out = await api("POST", `/tools/${t.id}/logo/refresh`); toast(out.ok ? "Logo updated from the website." : "Couldn't find a logo on the website — upload one instead.", !out.ok); if (out.ok) refresh("settings"); }
              catch (x) { toast(x.message, true); }
              b.disabled = false; b.textContent = "Fetch from website";
            } }, "Fetch from website") : null, file),
          el("span", { class: "hint" }, "PNG, SVG, WebP or JPEG, under 300 KB. Without a logo, the tile shows initials in the brand colour.")));
      }
      return [
        list, logoBox,
        el("div", { class: "form-grid" }, el("label", { class: "field" }, "Name", f.name), el("label", { class: "field" }, "Category", f.category), el("label", { class: "field" }, "Type", f.kind)),
        el("label", { class: "field" }, "Description", f.description),
        el("div", { class: "form-grid" }, el("label", { class: "field" }, "Website", f.url), el("label", { class: "field" }, "How people sign in", f.signin, howHint)),
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
        el("div", { class: "sheet-id" }, t ? SUI.logo(t, "lg") : el("span", { class: "dev-ic lg" }, icon("plus")),
          el("div", null, el("div", { class: "eyebrow" }, t ? t.category : "Catalog"), el("h2", null, t ? t.name : "Add a tool"),
            t ? el("div", { class: "row" }, subStatus(t), SUI.badge(KIND[t.kind] || t.kind, "outline")) : null)),
        el("button", { class: "btn small quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x"))),
      tabBar);
    node.append(head, body);
    drawTabs();
    show();
  }

  // ------------------------------------------------------------------ Access requests

  async function pageRequests(params) {
    await A.toolIndex().catch(() => null);
    const state = params.get("state") || "open";
    const data = await api("GET", "/access-requests?state=" + encodeURIComponent(state));
    const rows = data.items.map((r) => el("li", { class: "req" },
      SUI.avatar(r.person),
      el("div", { class: "grow" },
        el("div", { class: "req-line" }, A.personLink(r.person_id, r.person, { avatar: false }), el("span", { class: "muted" }, " asked for "), A.toolLink(r.tool_id, r.tool, "xs")),
        el("div", { class: "hint" }, (r.department || "No department") + " · " + fmt.ago(r.created) + (r.decided ? ` · ${r.state} by ${r.decided_by} ${fmt.ago(r.decided)}` : "")),
        r.reason ? el("p", { class: "req-reason" }, r.reason) : null),
      r.state === "open" && A.isOwner() ? el("div", { class: "row" },
        el("button", { class: "btn small primary", onclick: () => decide(r.id, "grant") }, icon("check"), "Grant"),
        el("button", { class: "btn small danger quiet", onclick: () => decide(r.id, "decline") }, "Decline"))
        : SUI.status(r.state === "granted" ? "ok" : r.state === "open" ? "pending" : "blocked", r.state[0].toUpperCase() + r.state.slice(1), { plain: true })));
    A.frame({ title: "Access requests", lede: "Staff asking for tools. Granting turns the tool on for them straight away.",
      actions: A.seg([["open", "Open" + (data.open ? ` (${data.open})` : "")], ["granted", "Granted"], ["declined", "Declined"]], state, (v) => { location.hash = "#/requests?state=" + v; }, "Which requests") },
    A.panel(null, null, rows.length ? el("ul", { class: "reqlist" }, rows)
      : SUI.stateBox({ icon: "requests", tone: state === "open" ? "ok" : null, title: state === "open" ? "No open requests" : "Nothing here", text: state === "open" ? "When staff ask for a tool in Swangz AI, it appears here." : "No requests in this state yet." })));
  }

  async function decide(id, action) {
    try { await api("POST", `/access-requests/${id}/${action}`); toast(action === "grant" ? "Granted." : "Declined."); A.render(); }
    catch (e) { toast(e.message, true); }
  }

  A.page(/^#\/people$/, pagePeople);
  A.page(/^#\/people\/(\d+)$/, pagePerson);
  A.page(/^#\/devices$/, pageDevices);
  A.page(/^#\/devices\/([0-9a-f]{12})$/, pageDevice);
  A.page(/^#\/tools$/, pageTools);
  A.page(/^#\/requests$/, pageRequests);
})();
