"use strict";
/* Governing access: people, their devices, the tool catalog and what staff ask for. Every object links
   to the others — a tool to the people using it, a person to their devices, a device to everything
   done from it — so following a thread never loses its place. Viewers see all of it; owners act. */
(() => {
  const { el, icon, fmt, toast } = SUI;
  const A = SWA;
  const { S, api } = A;
  const fact = (k, v, how) => el("div", { class: "fact" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), how ? el("div", { class: "how" }, SUI.evidence(how)) : null);
  function stat(k, v, note, o) {
    o = o || {};
    return el(o.href ? "a" : "div", { class: "stat" + (o.tone ? " " + o.tone : "") + (o.wide ? " wide" : ""), href: o.href || null, title: o.title || null },
      el("span", { class: "k" }, k), el("span", { class: "v" }, v), note ? el("span", { class: "n" }, note) : null, o.bar || null);
  }
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

  // the one line under a person's status: only what needs saying
  function personNote(p) {
    const now = Date.now() / 1000;
    if (p.status === "active" && p.access_until && p.access_until > now) return "until " + fmt.date(p.access_until - 86400);
    if (p.sign_in === "none") return "no app sign-in yet";
    if (p.sign_in === "invited") return "sign-in link sent";
    return null;
  }

  async function pagePeople(params) {
    const data = await api("GET", "/people");
    const items = data.items;
    const st = { q: params.get("q") || "", dept: params.get("dept") || "", status: params.get("status") || "" };
    const mode = A.viewMode("people", "#/people", params);
    // The counts are the filter: one row of tabs instead of a tile per number.
    const STATUS = [
      ["", "Everyone", () => true],
      ["active", "Active", (p) => personState(p)[0] === "active"],
      ["live", "Working now", (p) => p.live],
      ["invite", "Not signed in", (p) => p.sign_in !== "active"],
      ["suspended", "Suspended", (p) => personState(p)[0] === "suspended"],
      ["revoked", "Ended", (p) => personState(p)[0] === "revoked"],
    ];
    if (!STATUS.some(([k]) => k === st.status)) st.status = "";
    const counts = Object.fromEntries(STATUS.map(([k, , f]) => [k, items.filter(f).length]));
    const depts = [...new Set(items.map((p) => p.department).filter(Boolean))].sort();
    const statusOptions = STATUS.filter(([k]) => k && (k === "active" || counts[k] || k === st.status))
      .map(([k, label]) => ({ id: k, label, sub: SUI.plural(counts[k], "person", "people") }));
    const usedToday = items.filter((p) => p.today.requests).length;
    const meta = el("div", { class: "list-meta" },
      el("span", null, SUI.plural(items.length, "person", "people") + " · " + SUI.plural(depts.length, "department")),
      el("span", null, `${usedToday} used AI today`),
      counts.live ? el("a", { href: "#/live" }, SUI.status("live", `${counts.live} working now`, { breathe: true, plain: true })) : el("span", null, "nobody working right now"));
    const box = el("div");
    function draw() {
      const qq = st.q.toLowerCase();
      const want = STATUS.find(([k]) => k === st.status)[2];
      const rows = items.filter((p) => (!st.dept || p.department === st.dept) && want(p)
        && (!qq || [p.name, p.email, p.department, p.title].join(" ").toLowerCase().includes(qq)));
      const person = { key: "name", label: "Person", lead: true, render: (p) => el("div", { class: "u-cell" }, SUI.avatar(p.name),
        el("div", null, el("a", { href: "#/people/" + p.id }, el("strong", null, p.name)), el("span", { class: "sub" }, [p.title, p.department].filter(Boolean).join(" · ") || "No department"))) };
      const status = { key: "status", label: "Status", sort: (p) => personState(p)[0], render: (p) => el("div", null,
        el("div", { class: "row" }, SUI.status(...personState(p), { plain: true }), p.live ? SUI.status("live", "Live", { breathe: true, plain: true }) : null),
        personNote(p) ? el("span", { class: "sub" }, personNote(p)) : null) };
      const month = { key: "month", label: "Spent this month", num: true, sort: (p) => p.month.cost, render: (p) => el("span", null, fmt.money(p.month.cost),
        el("span", { class: "sub" }, p.monthly_budget !== null ? "of " + fmt.money(p.monthly_budget) : "no limit")) };
      const lastSeen = { key: "last_seen", label: "Last used AI", num: true, render: (p) => el("span", { title: p.last_seen ? fmt.stamp(p.last_seen) : null }, fmt.ago(p.last_seen)) };
      /* Simple (BRIEF 10.10.7): five columns, ten rows a page, and every row ends in Open + ⋯ (10.10.6 action column). */
      if (mode.simple) {
        box.replaceChildren(rows.length ? SUI.table({ caption: "People", rows, sort: ["last_seen", "desc"], href: (p) => "#/people/" + p.id,
          pager: { sizes: [10, 25, 50], page: Number(params.get("page")) || 1, onChange: (pg) => A.keepParams("#/people", { page: pg > 1 ? pg : null }) },
          columns: [person, status, month, lastSeen,
            { key: "act", label: "", srLabel: "Actions", sort: false, render: (p) => el("div", { class: "row" },
              el("a", { class: "btn small", href: "#/people/" + p.id, "aria-label": "Open " + p.name }, "Open"),
              SUI.menuButton({ label: "More actions for " + p.name, small: true, items: () => personRowActions(p) })) },
          ] }) : nobody());
        return;
      }
      box.replaceChildren(rows.length ? SUI.table({ caption: "People", rows, sort: ["last_seen", "desc"], href: (p) => "#/people/" + p.id, columns: [
        person, status,
        { key: "active_keys", label: "Devices", num: true, hideSm: true },
        { key: "today", label: "Today", num: true, hideSm: true, sort: (p) => p.today.cost, render: (p) => el("span", null, fmt.money(p.today.cost), el("span", { class: "sub" }, SUI.plural(p.today.requests, "request")),
          p.daily_budget !== null ? A.bar(p.today.cost, p.daily_budget) : null) },
        { key: "month", label: "This month", num: true, sort: (p) => p.month.cost, render: (p) => el("span", null, fmt.money(p.month.cost),
          el("span", { class: "sub" }, p.monthly_budget !== null ? "of " + fmt.money(p.monthly_budget) : "no limit"), p.monthly_budget !== null ? A.bar(p.month.cost, p.monthly_budget) : null) },
        { key: "last_seen", label: "Last used AI", num: true, render: (p) => el("span", { title: p.last_seen ? fmt.stamp(p.last_seen) : null }, fmt.ago(p.last_seen)) },
        { key: "act", label: "", srLabel: "Actions", sort: false, render: (p) => SUI.menuButton({ label: "More actions for " + p.name, small: true, items: () => personRowActions(p) }) },
      ] }) : nobody());
    }
    /* An empty list still ends in one thing to press (BRIEF 10.10.7: no dead ends). */
    function nobody() {
      const clear = el("a", { class: "btn", href: mode.simple ? "#/people" : "#/people?view=detailed" }, "Show everyone");
      const first = A.can("govern") ? el("button", { class: "btn", type: "button", onclick: () => addPerson() }, icon("plus"), "Add a person")
        : el("a", { class: "btn", href: "#/activity" }, "Check who is using what");
      return SUI.stateBox({ icon: "people", title: items.length ? "Nobody matches" : "Nobody yet",
        text: items.length ? "Try another search or filter." : "Add the first person, then send them a sign-in link or issue a key.",
        action: items.length ? clear : first });
    }
    const apply = () => { A.keepParams("#/people", { q: st.q, dept: st.dept, status: st.status, page: null }); params.delete("page"); draw(); };
    const bar = SUI.filterBar({ label: "Filter people", search: { placeholder: "Name, email, department" }, values: st,
      filters: [{ id: "status", label: "Status", any: "Everyone", options: statusOptions }]
        .concat(depts.length > 1 ? [{ id: "dept", label: "Department", any: "All departments", options: depts.map((d) => ({ id: d, label: d })) }] : []),
      onChange: (v) => { st.q = v.q || ""; st.dept = v.dept || ""; st.status = v.status || ""; apply(); } });
    draw();
    const add = A.can("govern") ? SUI.splitButton({ label: "Add person", icon: "plus", primary: true, onClick: () => addPerson(), menuLabel: "More ways to add a person", items: [
      { id: "invite", label: "Add and create sign-in link", icon: "send", onSelect: () => addPerson("invite") },
      { id: "key", label: "Add and issue a key", icon: "key", onSelect: () => addPerson("key") },
    ] }) : null;
    if (mode.simple) {
      /* Simple: the sentence with the real number, one next step, then one panel (filters + the list). */
      const lead = A.peopleLead({ total: items.length, notSignedIn: counts.invite, usedToday, canGovern: A.can("govern"), status: st.status });
      A.frame({ title: "People", trail: [["People"]], sentence: lead.sentence,
        // the header's Add person stays the one primary (its place on every page), so the next step is a plain button
        next: A.leadButton(Object.assign({}, lead.action, { quiet: true })), actions: [mode.switcher, add].filter(Boolean) }, [
        A.panel(null, null, el("div", { class: "filterbar" }, bar), box),
      ]);
    } else {
      A.frame({ title: "People", trail: [["People"]], lede: "Everyone with Swangz AI Hub access — their status, devices, and what they spend.", actions: [mode.switcher, add].filter(Boolean) }, [
        A.panel(null, null, el("div", { class: "filterbar" }, bar), meta, box),
      ]);
    }
    if (params.get("add") && A.can("govern")) addPerson();
    const opened = items.find((p) => String(p.id) === params.get("open"));
    if (opened) previewPerson(opened);
  }

  /* A kit side sheet that belongs to the page under it: leaving the page closes it, and a sheet with edits holds
     Back and links through the console's unsaved-changes question. */
  function pageSheet(o) {
    const leave = () => { if (!A.isDirty()) s.close(true); };
    const s = SUI.sheet(Object.assign({}, o, { onClose: () => {
      window.removeEventListener("hashchange", leave);
      if (o.dirty) A.setDirty(null);
      if (o.onClose) o.onClose();
    } }));
    window.addEventListener("hashchange", leave);
    if (o.dirty) A.setDirty(o.dirty);
    return s;
  }

  /* A row's preview: the facts already on the list, and the ways on into their record. ?open= makes it linkable. */
  function previewPerson(p) {
    A.keepParams("#/people", { open: p.id });
    const none = (x) => el("span", { class: "faint" }, x);
    const record = "#/people/" + p.id;
    const wide = (n) => { n.classList.add("fact-wide"); return n; };
    pageSheet({ title: p.name, purpose: [p.title, p.department].filter(Boolean).join(" · ") || "No department", cancel: "Close",
      body: el("div", { class: "stack" },
        el("div", { class: "facts person-preview" },
          fact("Status", el("span", { class: "row" }, SUI.status(...personState(p), { plain: true }), p.live ? SUI.status("live", "Live", { breathe: true, plain: true }) : null)),
          fact("App sign-in", signInBadge(p.sign_in)),
          wide(fact("Email", p.email || none("none yet"))),
          fact("Devices", SUI.plural(p.active_keys, "active key")),
          fact("Today", `${fmt.money(p.today.cost)} · ${SUI.plural(p.today.requests, "request")}`),
          fact("This month", fmt.money(p.month.cost) + (p.monthly_budget !== null ? " of " + fmt.money(p.monthly_budget) : " · no limit")),
          fact("Last used AI", p.last_seen ? fmt.ago(p.last_seen) : none("never")),
          wide(fact("Access ends", p.access_until ? fmt.date(p.access_until - 86400) : none("no end date")))),
        el("nav", { class: "person-preview-links", "aria-label": "Go to part of their record" },
          [["access", "Tools and access"], ["activity", "Activity"], ["devices", "Devices"], ["security", "Security"]].map(([tab, label]) =>
            el("a", { href: `${record}?tab=${tab}` }, label, icon("chevronRight"))))),
      primary: { label: "Open record", onClick: (sheet) => { sheet.close(true); location.hash = record; } },
      onClose: () => { if (/^#\/people(\?|$)/.test(location.hash)) A.keepParams("#/people", { open: null }); } });
  }

  async function setSuspended(p, on) {
    if (on) {
      const ok = await A.confirmAction(`Suspend ${p.name}?`, "Every key they hold stops working now, anything streaming is cut, their shared-account turns end, and the portal stops opening tools for them. You can restore access later.", "Suspend access", true);
      if (!ok) return;
    }
    try {
      const out = await api("POST", `/people/${p.id}/${on ? "suspend" : "resume"}`);
      toast(on ? `Suspended. ${out.cut} request(s) cut.` : "Access restored.");
      A.render();
    } catch (e) { toast(e.message, true); }
  }
  const mayStop = (p) => (p.status === "active" ? A.can("emergency") : A.can("emergency") || A.can("govern"));
  const signInItem = (p) => (A.can("govern") ? { id: "invite", label: p.sign_in === "active" ? "New sign-in link" : "Create sign-in link", sub: p.email ? null : "Add their email first", icon: "send", disabled: !p.email, onSelect: () => inviteLink(p) } : null);
  const suspendItem = (p) => (mayStop(p) && p.status === "active" ? { id: "suspend", label: "Suspend access", icon: "lock", danger: true, onSelect: () => setSuspended(p, true) } : null);
  function personRowActions(p) {
    return [
      { id: "preview", label: "Preview", icon: "people", onSelect: () => previewPerson(p) },
      A.can("govern") && p.status === "active" ? { id: "key", label: "Create access key", icon: "key", onSelect: () => issueKey(p) } : null,
      signInItem(p),
      mayStop(p) && p.status !== "active" ? { id: "restore", label: "Restore access", icon: "check", onSelect: () => setSuspended(p, false) } : null,
      suspendItem(p),
    ];
  }

  /* o.brief is the add sheet's first step: five fields, with budgets and rules left for their Account tab. */
  function personForm(p, o) {
    p = p || {}; o = o || {};
    const f = {
      name: el("input", { type: "text", value: p.name || "", required: true }),
      title: el("input", { type: "text", value: p.title || "", placeholder: "e.g. Director" }),
      department: el("input", { type: "text", value: p.department || "", placeholder: "e.g. Production" }),
      email: el("input", { type: "email", value: p.email || "", required: !!o.brief }),
      daily_budget: el("input", { type: "number", min: "0", step: "0.01", value: p.daily_budget ?? "", placeholder: "no limit" }),
      monthly_budget: el("input", { type: "number", min: "0", step: "0.01", value: p.monthly_budget ?? "", placeholder: "no limit" }),
      allowed_models: el("input", { type: "text", value: p.allowed_models || "", placeholder: "all models" }),
      allowed_services: el("input", { type: "text", value: p.allowed_services || "", placeholder: "every service" }),
      notes: el("textarea", null, p.notes || ""),
      access_until: el("input", { type: "date", value: p.access_until ? isoDate(p.access_until - 86400) : "" }),
    };
    f.budget_visible = el("input", { type: "checkbox", checked: !!p.budget_visible });
    const nameErr = el("span", { class: "err", role: "alert" }), emailErr = el("span", { class: "err", role: "alert" });
    const accessEnds = el("label", { class: "field" }, "Access ends on", f.access_until,
      el("span", { class: "hint" }, "Optional — for contractors and temporary staff. Every tool and key stops after this day."));
    const node = el("div", { class: "stack" },
      el("div", { class: "form-grid" },
        el("label", { class: "field" }, o.brief ? "Name (required)" : "Name", f.name, nameErr),
        el("label", { class: "field" }, "Role / title", f.title),
        el("label", { class: "field" }, "Department", f.department),
        el("label", { class: "field" }, o.brief ? "Email (required) — they sign in with it" : "Email — they sign in with it", f.email,
          el("span", { class: "hint" }, "Their Swangz email, ending in @swangzavenue.com."), emailErr),
        o.brief ? accessEnds : null),
      o.brief ? null : el("div", { class: "form-grid" },
        el("label", { class: "field" }, "Daily budget (USD)", f.daily_budget),
        el("label", { class: "field" }, "Monthly budget (USD)", f.monthly_budget),
        accessEnds),
      o.brief ? null : el("label", { class: "check" }, f.budget_visible, el("span", null, el("strong", null, "Let this person see their budget"),
        el("div", { class: "hint" }, "Off by default — staff don't see the budget set for them until you turn this on."))),
      o.brief ? null : el("label", { class: "field" }, "Allowed models", f.allowed_models,
        el("span", { class: "hint" }, "Comma-separated, * works as a wildcard: claude-sonnet-*, gpt-6-*. Empty = any model.")),
      o.brief ? null : el("label", { class: "field" }, "Allowed services", f.allowed_services,
        el("span", { class: "hint" }, "Comma-separated: " + S.me.providers.map((x) => x.name).join(", ") + ". Empty = every service the company has switched on.")),
      o.brief ? null : el("label", { class: "field" }, "Notes", f.notes));
    const shown = o.brief ? ["name", "title", "department", "email", "access_until"] : Object.keys(f);
    const values = () => Object.fromEntries(shown.map((k) => [k, f[k].type === "checkbox" ? f[k].checked : f[k].value]));
    /* Says what is missing under the field, and puts focus on the first problem. */
    const mark = (input, node, message) => { node.textContent = message; if (message) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid"); };
    function check() {
      mark(f.name, nameErr, f.name.value.trim() ? "" : "Enter their name.");
      mark(f.email, emailErr, f.email.value.trim() ? "" : "Enter their Swangz email. They sign in with it.");
      const bad = nameErr.textContent ? f.name : emailErr.textContent ? f.email : null;
      if (bad) bad.focus();
      return !bad;
    }
    f.name.addEventListener("blur", () => { if (o.brief && nameErr.textContent) mark(f.name, nameErr, f.name.value.trim() ? "" : "Enter their name."); });
    /* The server refused the address: say so under the field, like any other problem with it. */
    const refuseEmail = (message) => { mark(f.email, emailErr, message); f.email.focus(); };
    return { node, values, check, refuseEmail, focus: () => f.name.focus() };
  }

  /* What to open once the new person's record has drawn. Held here, not in the address: a link must never be able
     to create a sign-in link, which replaces any older one. */
  let afterAdd = null;
  function addPerson(then) {
    const form = personForm(null, { brief: true });
    const first = JSON.stringify(form.values());
    const err = el("div", { class: "err", role: "alert" });
    pageSheet({ title: "Add a person", purpose: "Who they are. Budgets and model rules are on their Account tab once they're added.",
      body: el("div", { class: "stack" }, form.node, err), dirty: () => JSON.stringify(form.values()) !== first,
      primary: { label: { invite: "Add and create link", key: "Add and issue key" }[then] || "Add person", onClick: async (sheet) => {
        err.textContent = "";
        if (!form.check()) return;
        try {
          const v = form.values();
          const out = await api("POST", "/people", v);
          afterAdd = then ? { id: out.id, then } : null;
          sheet.close(true);
          location.hash = "#/people/" + out.id;
        } catch (e) { if (/\b(email|address)\b/i.test(e.message)) form.refuseEmail(e.message); else err.textContent = e.message; }
      } } });
  }

  // links from before the profile's tabs were renamed
  const PERSON_OLD_TABS = { tools: "access", details: "account" };
  async function pagePerson(params, id) {
    if (PERSON_OLD_TABS[params.get("tab")]) {
      params.set("tab", PERSON_OLD_TABS[params.get("tab")]);
      A.S.route = `#/people/${id}?` + params.toString();
      history.replaceState(null, "", A.S.route);
    }
    await A.toolIndex().catch(() => null);
    const p = await api("GET", "/people/" + id);
    const after = afterAdd && afterAdd.id === p.id ? afterAdd.then : null;
    afterAdd = null;
    const owner = A.can("govern");
    const [state, stateLabel] = personState(p);
    const since30 = Date.now() / 1000 - 30 * 86400;
    // "Last seen" counts only what the person did themselves: an AI request, a tool opened, a site visited. Access changes made
    // by an admin, turns and sign-ins are not activity, so one call per kind and the newest wins.
    const lastOf = (type) => api("GET", `/timeline?person=${p.id}&type=${type}&limit=1&since=${Date.now() / 1000 - 365 * 86400}`);
    const [usage, security, ...recent] = await Promise.allSettled([
      api("GET", `/usage?person=${p.id}&since=${since30}`), api("GET", "/security?days=30"), lastOf("request"), lastOf("launch"), lastOf("site")]);
    const myEvents = security.status === "fulfilled" ? security.value.events.filter((e) => e.person_id === p.id) : null;
    const used = usage.status === "fulfilled" ? usage.value.rows : null;
    const own = recent.filter((r) => r.status === "fulfilled" && r.value.items[0]).map((r) => r.value.items[0]).filter((e) => ["request", "launch", "site"].includes(e.type));
    const last = own.sort((a, b) => b.ts - a.ts)[0] || null;
    const activeKeys = p.keys.filter((k) => !k.revoked);
    const current = activeKeys.filter((k) => k.last_used).sort((a, b) => b.last_used - a.last_used)[0];

    // A slim line of facts rather than a tile each: the profile's content lives in the tabs below.
    const alerts = myEvents ? myEvents.filter((e) => e.severity !== "info").length : null;
    const lastNote = !last ? "No activity recorded" : last.type === "request" ? "AI request" : last.type === "launch" ? "opened " + (last.tool || "a tool") : "visited " + (last.tool || "a site");
    const stats = el("div", { class: "statline" },
      stat("Last seen", last ? fmt.ago(last.ts) : "Never", lastNote, { title: last ? fmt.stamp(last.ts) : null }),
      stat("Current device", current ? current.label : "None", current ? "used " + fmt.ago(current.last_used) : activeKeys.length ? "not used yet" : "no active key",
        { href: current ? "#/devices/" + current.id : null, wide: true }),
      stat("Spend this month", fmt.money(p.month.cost), p.monthly_budget !== null ? "of " + fmt.money(p.monthly_budget) : "no monthly limit",
        { bar: p.monthly_budget !== null ? A.bar(p.month.cost, p.monthly_budget) : null }),
      stat("Tools · 30 days", used ? `${used.length} used` : "—", `${p.tool_summary.enabled} enabled for them`, { href: `#/people/${p.id}?tab=access` }),
      stat("Alerts · 30 days", alerts === null ? "—" : alerts ? String(alerts) : "None", alerts ? "worth a look" : "nothing flagged",
        { href: `#/people/${p.id}?tab=security`, tone: myEvents && myEvents.some((e) => e.severity === "medium" || e.severity === "high") ? "alert" : null }));

    async function overviewTab() {
      const live = p.live.length ? A.panel("Working right now", null, el("div", { class: "lv-stream" }, p.live.map((t) => el("article", { class: "lv" },
        el("div", { class: "lv-head" }, SUI.status(t.streaming ? "streaming" : "waiting", t.streaming ? "Streaming" : "Waiting", { breathe: true }), el("span", { class: "grow" }),
          el("span", { class: "elapsed u-num" }, fmt.elapsed(t.started))),
        el("div", { class: "lv-what" }, A.toolLink(null, t.client || "A tool"), el("span", { class: "mono faint" }, t.model || ""), A.deviceLink(t.key_id, t.device)),
        t.prompt ? el("p", { class: "lv-prompt" }, t.prompt) : null)))) : null;
      const tl = await api("GET", `/timeline?person=${p.id}&limit=6&since=${since30}`);
      const tools = used && used.length ? SUI.barList(used.slice().sort((a, b) => (b.requests + b.opens + b.visits) - (a.requests + a.opens + a.visits)).slice(0, 5).map((r) => ({
        label: r.tool, lead: A.toolLogo(r.tool_id, r.tool, "sm"), href: r.tool_id ? `#/tools?open=${r.tool_id}` : null, value: r.requests + r.opens + r.visits,
        display: SUI.plural(r.requests + r.opens + r.visits, "use"), note: r.requests ? fmt.money(r.cost) : r.seconds ? fmt.dur(r.seconds) + " on site" : null })), { tone: 2 })
        : A.empty("No tool use in the last 30 days.", null, "tools");
      return [live,
        el("div", { class: "grid cols-2" },
          A.panel("Recent activity", el("a", { class: "btn small quiet", href: `#/people/${p.id}?tab=activity` }, "All activity", icon("chevronRight")),
            tl.items.length ? A.eventDays(tl.items, { noPerson: true }).node : SUI.stateBox({ icon: "activity", title: "No AI activity yet", text: "Once they use an approved tool, it appears here.", compact: true })),
          A.panel("Tools they use most", el("a", { class: "btn small quiet", href: `#/people/${p.id}?tab=access` }, "Their access", icon("chevronRight")), tools))];
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
    async function activityViews() {
      const sessions = A.panel("Sessions", "one conversation each, most recent first", p.sessions.length ? el("ul", { class: "mini-list" }, p.sessions.slice(0, 12).map((x) => el("li", null,
        el("span", { class: "mini-ic" }, icon("layers")),
        el("a", { class: "grow", href: "#/sessions/" + encodeURIComponent(x.session) }, el("strong", null, x.first_prompt || "(no typed prompt)"),
          el("div", { class: "hint" }, `${x.client || "a tool"} · ${SUI.plural(x.requests, "request")} · ${fmt.when(x.last)}`)),
        el("span", { class: "u-num" }, fmt.money(x.cost)))))
        : A.empty("No sessions yet."));
      return [await activityTab(), sessions];
    }

    async function devicesTab() {
      const all = await api("GET", "/devices");
      const mine = all.items.filter((d) => d.person_id === p.id);
      const browsers = all.browsers.filter((b) => b.person_id === p.id);
      const signInState = { active: "Signs in to the Swangz AI Hub app" + (p.last_login ? ` · last signed in ${fmt.ago(p.last_login)}` : ""),
        invited: `Sign-in link sent — valid until ${fmt.stamp(p.invite_expires)}`, none: "No app sign-in yet" }[p.sign_in];
      return [
        A.panel("Devices", SUI.plural(mine.filter((d) => d.state !== "revoked").length, "active key"), mine.length ? deviceTable(mine, true)
          : A.empty("No keys yet. Issue one per laptop or coding tool.", "No devices", "device")),
        el("div", { class: "grid cols-even" },
          A.panel("Swangz AI Hub app", null, el("div", { class: "body stack" },
            el("div", { class: "row" }, signInBadge(p.sign_in), el("span", { class: "muted" }, signInState)),
            el("div", { class: "hint" }, p.email ? `They sign in at ${S.me.base_url}/ with ${p.email}, or with Continue with Google if that email is their Google account.`
              : "Add their email under Details first — it is what they sign in with."),
            owner && p.email ? el("div", null, el("button", { class: "btn", onclick: () => inviteLink(p) }, icon("send"), p.sign_in === "active" ? "New sign-in link (reset password)" : "Create sign-in link")) : null)),
          A.panel("Browsers", "used to open tools · 90 days", browsers.length ? el("ul", { class: "mini-list" }, browsers.map((b) => el("li", null,
            el("span", { class: "mini-ic" }, icon("monitor")),
            el("div", { class: "grow" }, el("strong", null, [b.browser, b.os].filter(Boolean).join(" on ") || "Unknown browser"),
              el("div", { class: "hint" }, `${SUI.plural(b.opens, "open")} · last ${fmt.ago(b.last)}` + (b.last_ip ? " · " + b.last_ip : ""))))))
            : A.empty("They haven't opened a tool from the portal yet."))),
      ];
    }

    function accessTab() {
      const none = (x) => el("span", { class: "faint" }, x);
      const limits = A.panel("Other limits", el("a", { class: "btn small quiet", href: `#/people/${p.id}?tab=account` }, owner || A.can("money") ? "Change" : "Details", icon("chevronRight")),
        el("div", { class: "facts" },
          fact("Account", p.status === "active" ? (p.access_until ? (ended ? "Ended " : "Open until ") + fmt.date(p.access_until - 86400) : "Open, no end date") : "Suspended"),
          fact("Monthly budget", p.monthly_budget !== null ? `${fmt.money(p.month.cost)} of ${fmt.money(p.monthly_budget)}` : none("no limit")),
          fact("Daily budget", p.daily_budget !== null && p.daily_budget !== undefined ? fmt.money(p.daily_budget) : none("no limit")),
          fact("Models", p.allowed_models || none("any model")),
          fact("Services", p.allowed_services || none("every service switched on"))),
        el("div", { class: "body hint" }, "Policies can take more away for everyone they match — see ", el("a", { href: "#/policies?tab=explain&person=" + p.id }, "Explain a decision"), "."));
      return [personToolsPanel(p, owner, used), limits];
    }

    async function securityTab() {
      if (!myEvents) return SUI.errorBox(security.reason, () => A.render());
      return A.panel("Signals involving " + p.name, "last 30 days", myEvents.length ? el("ul", { class: "sec-list" }, myEvents.map((e) => el("li", { class: "sec sev-" + e.severity },
        el("div", { class: "sec-head" }, el("strong", null, e.title), SUI.status(e.severity, e.severity[0].toUpperCase() + e.severity.slice(1)), el("span", { class: "grow" }), el("time", { class: "hint" }, fmt.ago(e.ts))),
        el("p", { class: "sec-text" }, e.text),
        e.evidence ? el("div", { class: "sec-foot" }, SUI.evidence(e.evidence)) : null,
        e.href ? el("a", { class: "btn small sec-go", href: e.href }, "Investigate", icon("chevronRight")) : null)))
        : SUI.stateBox({ tone: "ok", icon: "shield", title: "No security events", text: "Nothing involving them in the last 30 days." }));
    }

    async function accountTab() {
      if (!owner && !A.can("money")) {
        const none = (x) => el("span", { class: "faint" }, x);
        return [A.panel("Account", null, el("div", { class: "facts" },
            fact("Name", p.name), fact("Role / title", p.title || none("—")), fact("Department", p.department || none("—")), fact("Email", p.email || none("—")),
            fact("Daily budget", p.daily_budget != null ? fmt.money(p.daily_budget) : none("no limit")), fact("Monthly budget", p.monthly_budget != null ? fmt.money(p.monthly_budget) : none("no limit")),
            fact("Access ends", p.access_until ? fmt.date(p.access_until - 86400) : none("no end date"))),
          el("div", { class: "body hint" }, `Your role (${A.roleLabel()}) can see these but not change them.`)),
          p.notes ? A.panel("Notes", null, el("div", { class: "body" }, el("pre", { class: "text" }, p.notes))) : null];
      }
      const form = personForm(p);
      const first = JSON.stringify(form.values());
      A.setDirty(() => form.node.isConnected && JSON.stringify(form.values()) !== first);
      const err = el("span", { class: "err", role: "alert" });
      return A.panel("Details, limits and notes", null, el("div", { class: "body stack" }, form.node),
        A.panelFoot(el("span", { class: "grow" }, err),
          el("button", { class: "btn quiet", type: "button", onclick: () => { A.setDirty(null); A.render(); } }, "Discard"),
          el("button", { class: "btn primary", type: "button", onclick: async () => {
            try { await api("PATCH", "/people/" + p.id, form.values()); A.setDirty(null); toast("Saved."); A.render(); } catch (e) { err.textContent = e.message; }
          } }, "Save changes")));
    }

    const ended = p.access_until && p.access_until <= Date.now() / 1000;
    const step = personStep(p, alerts);
    const stepTab = typeof step === "string" ? "" : step.tab;
    A.frame({
      title: p.name, lead: SUI.avatar(p.name, "lg"), status: el("span", { class: "row" }, SUI.status(state, stateLabel, { plain: true }), p.live.length ? SUI.status("live", "Live", { breathe: true, plain: true }) : null),
      trail: [["People", "#/people"], [p.name]], next: personNext(p, step),
      lede: [[p.title, p.department].filter(Boolean).join(" · ") || "No department", p.email].filter(Boolean).join(" — ") +
        (p.access_until ? ` · access ${ended ? "ended" : "until"} ${fmt.date(p.access_until - 86400)}` : ""),
      actions: [stepTab === "access" && p.status === "active" && A.can("govern") ? el("a", { class: "btn primary", href: `#/people/${p.id}?tab=access` }, icon("plus"), "Give a tool") : null,
        owner && p.status === "active" ? el("button", { class: "btn" + (stepTab === "devices" ? " primary" : ""), type: "button", title: "A key lets one of their devices or coding tools sign in to Swangz AI Hub", onclick: () => issueKey(p) }, icon("key"), "Create access key") : null,
        mayStop(p) && p.status !== "active" ? el("button", { class: "btn primary", onclick: () => setSuspended(p, false) }, "Restore access") : null,
        SUI.menuButton({ label: "More actions for " + p.name, items: () => [
          signInItem(p),
          { id: "details", label: owner || A.can("money") ? "Edit details" : "Details", icon: "settings", href: `#/people/${p.id}?tab=account` },
          { id: "explain", label: "Explain a decision", icon: "shield", href: "#/policies?tab=explain&person=" + p.id },
          { id: "export", label: "Export activity CSV", icon: "download", href: A.gadmin(`/export.csv?person=${p.id}`) },
          suspendItem(p),
        ] })],
    }, [stats, A.pageTabs("#/people/" + p.id, params, [
      ["overview", "Overview", overviewTab],
      ["access", "Access", async () => accessTab(), p.tool_summary.enabled, "The tools they have and why, and the other limits on what they can do."],
      ["activity", "Activity", activityViews, null, "Everything they did, in order, and their AI sessions."],
      ["devices", "Devices", devicesTab, activeKeys.length, "Their keys, how they sign in to the Swangz AI Hub app, and the browsers they open tools in."],
      ["security", "Security", securityTab, alerts || null, "Signals involving them in the last 30 days — what to look into, not a history."],
      ["account", "Account", accountTab],
    ], { label: p.name })]);
    if (after === "key" && owner) issueKey(p);
    if (after === "invite" && owner) inviteLink(p);
  }

  /* The one "Next step" line on a record: the most useful thing to do about this person now, worst first. */
  /* The one thing to do next for a person: a sentence, or { tab, text } when it is a page to go to. The header's
     primary button follows it, so the line and the button never point two ways. */
  function personStep(p, alerts) {
    const state = personState(p)[0];
    if (alerts === null) return "Their security signals couldn't load, so there is no next step to show.";
    if (state === "suspended") return { tab: "security", text: "Check their security signals before restoring access" };
    if (state === "revoked") return { tab: "account", text: "Their access has ended. Extend it, or leave it closed" };
    if (alerts) return { tab: "security", text: `Look at ${SUI.plural(alerts, "security signal")} involving them` };
    if (p.monthly_budget != null && p.month.cost >= p.monthly_budget) return { tab: "account", text: "They have reached their monthly budget. Review it" };
    if (!p.tool_summary.enabled) return { tab: "access", text: p.tool_summary.assigned ? "None of their tools are ready. See why" : "Give them their first tool" };
    if (p.sign_in === "none" && !p.keys.some((k) => !k.revoked)) return { tab: "devices", text: "They can't sign in yet. See how to connect them" };
    return "Nothing needs doing for them right now.";
  }
  function personNext(p, step) {
    return typeof step === "string" ? step : el("a", { href: `#/people/${p.id}?tab=${step.tab}` }, step.text);
  }

  const TOOL_STATE = { enabled: ["ok", "Ready"], past_due: ["waiting", "Payment due"], suspended: ["suspended", "Paused"], locked: ["none", "No subscription"], not_assigned: ["none", "Not given"] };
  /* What a person has, as a table; giving another tool is one picker rather than a tile per tool. */
  function personToolsPanel(p, owner, used) {
    const tools = p.tools || [];
    const use = Object.fromEntries((used || []).filter((r) => r.tool_id).map((r) => [r.tool_id, r]));
    const mine = tools.filter((t) => t.assigned);
    const giveable = tools.filter((t) => !t.assigned && t.state !== "locked");
    async function change(t, give) {
      try { await api(give ? "POST" : "DELETE", `/people/${p.id}/tools/${t.id}`); toast(give ? `${t.name} given to ${p.name}.` : `${t.name} taken back.`); A.render(); }
      catch (e) { toast(e.message, true); }
    }
    const toolItems = (t) => [
      { id: "open", label: "Tool details", icon: "tools", href: `#/tools?open=${t.id}` },
      { id: "explain", label: "Explain a decision", icon: "shield", href: `#/policies?tab=explain&person=${p.id}&tool=${t.id}` },
      owner && t.grant !== "direct" ? { id: "team", label: "Team access", sub: "Changed on the tool", icon: "people", href: `#/tools?open=${t.id}&tab=access` } : null,
      owner && t.grant === "direct" ? { id: "take", label: "Take back", icon: "lock", danger: true, onSelect: () => change(t, false) } : null,
    ].filter(Boolean);
    const table = mine.length ? SUI.table({ caption: "Their tools", rows: mine, sort: ["name", "asc"], columns: [
      { key: "name", label: "Tool", lead: true, render: (t) => el("a", { class: "u-cell", href: `#/tools?open=${t.id}` }, SUI.logo(t, "sm"),
        el("div", null, el("strong", null, t.name), el("span", { class: "sub" }, t.category))) },
      { key: "grant", label: "Access", render: (t) => (t.grant === "team" ? el("span", null, "Through the team", el("span", { class: "sub" }, p.department || "their department")) : "Given directly") },
      { key: "state", label: "State", render: (t) => SUI.status(...(TOOL_STATE[t.state] || ["info", t.state]), { plain: true, title: t.reason }) },
      { key: "ends", label: "Until", num: true, sort: (t) => t.ends || Infinity, render: (t) => (t.ends ? fmt.date(t.ends - 86400) : el("span", { class: "faint" }, "no end date")), hideSm: true },
      { key: "use", label: "Use · 30 days", num: true, sort: (t) => (use[t.id] ? use[t.id].requests + use[t.id].opens + use[t.id].visits : -1), render: (t) => {
        const u = use[t.id];
        if (!u) return el("span", { class: "faint" }, "not used");
        return el("span", null, SUI.plural(u.requests + u.opens + u.visits, "use"), el("span", { class: "sub" }, u.requests ? fmt.money(u.cost) : u.seconds ? fmt.dur(u.seconds) + " on site" : ""));
      } },
      { key: "act", label: "", srLabel: "Actions", sort: false, render: (t) => SUI.menuButton({ label: "More actions for " + t.name, small: true, items: () => toolItems(t) }) },
    ] }) : SUI.stateBox({ icon: "tools", title: "No tools yet", text: owner ? "Give them a tool below." : "An owner gives tools to people.", compact: true });
    let give = null;
    if (owner && giveable.length) {
      let chosen = null;
      const go = el("button", { class: "btn small", type: "button", disabled: true, onclick: () => { if (chosen) change(chosen, true); } }, icon("plus"), "Give");
      const pick = SUI.select({ label: "Tool to give", placeholder: "Choose a tool…", small: true, options: giveable.map((t) => ({ id: t.id, label: t.name, sub: t.category })),
        onChange: (id) => { chosen = giveable.find((x) => x.id === id) || null; go.disabled = !chosen; } });
      give = el("div", { class: "give-row" }, el("span", { class: "u-label" }, "Give another tool"), pick, go,
        el("span", { class: "hint" }, `${giveable.length} subscribed tool${giveable.length === 1 ? "" : "s"} they don't have yet`));
    }
    const removeAll = owner && mine.some((t) => t.grant === "direct") ? el("button", { class: "btn small quiet danger", onclick: async () => {
      const ok = await A.confirmAction(`Remove every tool from ${p.name}?`, "Their direct tool access is removed now. Team access stays with the team, and their account stays open — suspend it too if they're leaving.", "Remove all tools", true);
      if (!ok) return;
      try { const out = await api("DELETE", `/people/${p.id}/tools`); toast(`Removed ${out.removed} tool(s).`); A.render(); } catch (e) { toast(e.message, true); }
    } }, "Remove all") : null;
    return A.panel("Tools", el("div", { class: "row" }, el("span", { class: "sub" }, `${p.tool_summary.enabled} ready · ${p.tool_summary.assigned} given`), removeAll),
      give, table,
      el("div", { class: "body hint" }, "A tool the company isn't subscribed to can't be given yet, and team access is changed on the tool itself — both on the Tools page. To give a tool for a limited time, set an end date there under Who can use it."));
  }

  async function inviteLink(p) {
    try {
      const out = await api("POST", `/people/${p.id}/invite`);
      const text = `Hi ${p.name}, here is your Swangz AI Hub sign-in link (valid ${out.expires_days} days): ${out.link}`;
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
    pageSheet({ title: `New key for ${p.name}`, purpose: "One key per device or tool, so you can revoke one without stopping the rest.",
      body: el("div", { class: "stack" },
        el("label", { class: "field" }, "Which device or tool is it for?", label, el("span", { class: "hint" }, "This name is how the device appears everywhere in the control room.")), err),
      primary: { label: "Issue key", onClick: async (sheet) => {
        try {
          const out = await api("POST", `/people/${p.id}/keys`, { label: label.value });
          sheet.close(true);
          showNewKey(p, out);
        } catch (e) { err.textContent = e.message; }
      } } });
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

  const devIcon = (d) => el("span", { class: "dev-ic sm" }, icon(d.app === "Claude Code" || d.app === "Codex" ? "terminal" : "device"));
  const canRevoke = (d) => (A.can("emergency") || A.can("govern")) && d.state !== "revoked";
  const DEV_ROOT = ["Devices", "#/devices"];
  function deviceTable(rows, noOwner, extra, pager) {
    return SUI.table({ caption: "Devices", rows, pager, sort: ["last_used", "desc"], href: (d) => "#/devices/" + d.id, columns: [
      { key: "label", label: "Device", lead: true, render: (d) => el("div", { class: "u-cell" }, devIcon(d),
        el("div", null, el("a", { href: "#/devices/" + d.id }, el("strong", null, d.label)), el("span", { class: "sub mono" }, d.hint))) },
      noOwner ? null : { key: "person", label: "Owner", render: (d) => A.personLink(d.person_id, d.person) },
      { key: "app", label: "Runs", render: (d) => el("span", null, d.app || "—", platformOf(d) ? el("span", { class: "sub" }, platformOf(d)) : null) },
      { key: "last_used", label: "Last seen", num: true, render: (d) => el("span", { title: d.last_used ? fmt.stamp(d.last_used) : null }, d.last_used ? fmt.ago(d.last_used) : "never") },
      { key: "last_ip", label: "From", render: (d) => (d.last_ip ? A.where(d.last_ip, d.place) : "—"), hideSm: true },
      { key: "requests_30d", label: "30 days", num: true, render: (d) => el("span", null, fmt.num(d.requests_30d), el("span", { class: "sub" }, fmt.money(d.cost_30d))) },
      { key: "state", label: "Status", render: (d) => deviceStatus(d.state, true) },
      extra ? { key: "act", label: "", srLabel: "Actions", sort: false, render: extra } : null,
    ].filter(Boolean) });
  }

  /* One list, one filter row. The tab strip is the only one on the page; each tab has its own filter or none. */
  async function pageDevices(params) {
    const data = await api("GET", "/devices");
    const st = { q: params.get("q") || "", state: params.get("state") || "", page: Number(params.get("page")) || 1, per: Number(params.get("per")) || 25 };
    const STATES = [["active", "Active"], ["idle", "Idle"], ["unused", "Never used"], ["revoked", "Revoked"], ["suspended", "Owner suspended"]];
    const counts = Object.fromEntries(STATES.map(([k]) => [k, data.items.filter((d) => d.state === k).length]));
    const stateOptions = STATES.filter(([k]) => counts[k] || k === st.state).map(([k, label]) => ({ id: k, label, sub: SUI.plural(counts[k], "device") }));
    const box = el("div");
    const pager = { page: st.page, size: st.per, onChange: (page, size) => { st.page = pager.page = page; st.per = pager.size = size; keep(); } };
    const rowActions = (d) => [
      { id: "open", label: "Open the record", icon: "device", href: "#/devices/" + d.id },
      { id: "activity", label: "Their activity", icon: "clock", href: `#/activity?tab=ai&person=${d.person_id}` },
      canRevoke(d) ? { id: "revoke", label: "Revoke device", icon: "lock", danger: true, onSelect: () => revokeKey(d) } : null,
    ];
    function draw() {
      const qq = st.q.trim().toLowerCase();
      const rows = data.items.filter((d) => (!st.state || d.state === st.state) && (!qq || [d.label, d.person, d.app, d.platform, d.last_ip, d.hint].join(" ").toLowerCase().includes(qq)));
      box.replaceChildren(rows.length ? deviceTable(rows, false, (d) => SUI.menuButton({ label: "More actions for " + d.label, small: true, items: () => rowActions(d) }), pager)
        : SUI.stateBox({ icon: "device", title: data.items.length ? "No devices match" : "No devices yet",
          text: data.items.length ? "Try another search or status." : "A device appears when someone is issued a key, or connects one themselves in the staff app." }));
    }
    const keep = () => { A.keepParams("#/devices", { tab: params.get("tab") && params.get("tab") !== "keys" ? params.get("tab") : null, q: st.q, state: st.state, page: st.page > 1 ? st.page : null, per: st.per !== 25 ? st.per : null }); };
    const bar = SUI.filterBar({ label: "Filter devices", search: { placeholder: "Device, owner, app or address" }, values: st, filters: [
      { id: "state", label: "Status", any: "All", options: stateOptions },
    ], onChange: (v) => { st.q = v.q || ""; st.state = v.state || ""; st.page = pager.page = 1; keep(); draw(); } });
    draw();
    const keysTab = () => A.panel(null, null, el("div", { class: "filterbar" }, bar),
      el("div", { class: "list-meta" }, el("span", null, "One gateway key per laptop or coding tool"),
        el("span", null, "places from named networks or the offline table, never an online lookup")), box);
    const browsersTab = () => A.panel(null, "from the portal's Open button · 90 days", data.browsers.length ? SUI.table({ caption: "Browsers", rows: data.browsers, sort: ["last", "desc"], pager: { page: 1, size: 25 }, columns: [
      { key: "person", label: "Person", lead: true, render: (b) => A.personLink(b.person_id, b.person) },
      { key: "browser", label: "Browser", render: (b) => b.browser || "Unknown" },
      { key: "os", label: "System", render: (b) => b.os || "Unknown" },
      { key: "opens", label: "Opens", num: true },
      { key: "last", label: "Last", num: true, render: (b) => fmt.ago(b.last) },
      { key: "last_ip", label: "Last address", render: (b) => (b.last_ip ? el("span", { class: "mono faint" }, b.last_ip) : "—"), hideSm: true }] })
      : A.empty("Nobody has opened a tool from the portal yet."));
    A.frame({ title: "Devices", trail: [["Devices"]], lede: "Every laptop and coding tool holding a gateway key — what it runs, where it connects from, and when it was last used." },
      A.pageTabs("#/devices", params, [
        ["keys", "Gateway keys", keysTab, counts.active || null],
        ["browsers", "Browsers", browsersTab],
      ]));
  }

  /* The one "Next step" line on a device: worst first. */
  function deviceNext(d) {
    const go = (tab, text) => el("a", { href: `#/devices/${d.id}?tab=${tab}` }, text);
    if (d.state === "revoked") return "This key is revoked, so nothing more can be done with it. Issue a new key if the person still needs one.";
    if (d.state === "suspended") return el("a", { href: "#/people/" + d.person_id }, "The owner is suspended, so this device is refused. Review their account");
    if (d.flagged.length) return go("flagged", `Look at ${SUI.plural(d.flagged.length, "flagged or refused request")} from this device`);
    if (d.state === "unused") return "This key has never been used. If nobody needs it, revoke it.";
    if (d.state === "idle") return go("activity", "It has not been used lately. Check the last requests, and revoke the key if the device is gone");
    return "Nothing needs doing for this device.";
  }

  async function pageDevice(params, kid) {
    await A.toolIndex().catch(() => null);
    const d = await api("GET", "/devices/" + kid);
    const recent = await api("GET", `/requests?key=${kid}&limit=20`);
    // where each address is, and how that is known: a named network is exact, the offline table approximate,
    // and otherwise only the kind of address is known
    const placeOf = (x) => (x.location ? x.location.label : x.place);
    const howKnown = (x) => (!x.location ? "Kind of address only" : x.location.kind === "known" ? "Named network — exact"
      : x.location.approximate ? `Approximate — ${x.location.source || "location table"}; not GPS` : x.location.evidence || "Kind of address only");
    const ips = d.ips.length ? SUI.table({ caption: "Recent addresses", rows: d.ips, sort: ["last", "desc"], cards: false, columns: [
      { key: "ip", label: "Address", render: (x) => el("span", { class: "mono" }, x.ip || "—") },
      { key: "place", label: "Place", sort: placeOf, render: (x) => el("div", null, placeOf(x), el("span", { class: "sub" }, howKnown(x))) },
      { key: "first", label: "First", num: true, render: (x) => fmt.when(x.first) },
      { key: "last", label: "Last", num: true, render: (x) => fmt.when(x.last) },
      { key: "requests", label: "Requests", num: true }] }) : A.empty("No requests from this device yet.");
    const total = d.series.reduce((n, x) => n + x.requests, 0), spent = d.series.reduce((n, x) => n + x.cost, 0);
    A.frame({
      title: d.label, trail: [DEV_ROOT, [d.label]], next: deviceNext(d),
      lead: el("span", { class: "dev-ic lg" }, icon(d.app === "Claude Code" || d.app === "Codex" ? "terminal" : "device")), status: deviceStatus(d.state, true),
      actions: [el("a", { class: "btn", href: `#/activity?tab=ai&person=${d.person_id}` }, icon("activity"), "Their activity"),
        canRevoke(d) ? [el("span", { class: "act-gap" }), el("button", { class: "btn danger", onclick: () => revokeKey(d) }, icon("lock"), "Revoke device")] : null],
    }, [
      A.pageTabs("#/devices/" + kid, params, [
        ["overview", "Overview", async () => A.panel(null, null, el("div", { class: "facts" },
          fact("Owner", A.personLink(d.person_id, d.person)), fact("Status", deviceStatus(d.state, true)),
          fact("Runs", d.app || "Not identified", platformOf(d) ? "Platform from the tool's user agent: " + platformOf(d) : "The tool did not state a platform"),
          fact("Last seen", d.last_used ? fmt.stamp(d.last_used) : "never"),
          fact("Last address", d.ips[0] ? el("span", null, el("span", { class: "mono" }, d.ips[0].ip || "—"), " · " + placeOf(d.ips[0])) : "—", d.ips[0] ? howKnown(d.ips[0]) : null),
          fact("Last 30 days", `${SUI.plural(total, "request")} · ${fmt.money(spent)}`, "Estimated from the price table"),
          fact("Key", el("span", { class: "mono" }, d.hint), "Only the key's ends are ever shown"),
          fact("Issued", fmt.date(d.created) + (d.created_by ? (d.created_by === "self" ? " · by them in the app" : " · by " + d.created_by) : "")),
          fact("First used", d.first_used ? fmt.stamp(d.first_used) : "never"),
          fact("All-time use", `${SUI.plural(d.totals.requests, "request")} · ${fmt.tokens(d.totals.tokens)} tokens · ${fmt.money(d.totals.cost)} estimated`),
          d.revoked ? fact("Revoked", fmt.stamp(d.revoked) + (d.revoked_by ? (d.revoked_by === "self" ? " · by them" : " · by " + d.revoked_by) : "")) : null))],
        ["usage", "Usage", async () => el("div", { class: "stack" },
          A.panel("Requests per day", "30 days · " + SUI.tzLabel(true), el("div", { class: "body" }, SUI.columns({ label: "Requests per day from this device", tone: 2, yName: "Requests",
            data: d.series.map((x) => ({ label: fmt.weekday(x.start), short: fmt.dayMonth(x.start), value: x.requests, note: fmt.money(x.cost) })) }))),
          el("div", { class: "grid cols-even" },
            A.panel("Applications", "from the tool's user agent", d.apps.length ? el("ul", { class: "mini-list" }, d.apps.map((a) => el("li", null, el("span", { class: "mini-ic" }, icon("terminal")),
              el("div", { class: "grow" }, el("strong", null, a.client || "Not identified"), el("div", { class: "hint" }, (a.platform || "platform not stated") + " · last " + fmt.ago(a.last))),
              el("span", { class: "u-num" }, fmt.num(a.requests))))) : A.empty("Nothing yet.")),
            A.panel("Models", "requests · estimated cost", d.models.length ? SUI.barList(d.models.map((m) => ({ label: m.model, value: m.requests, display: fmt.num(m.requests), note: fmt.money(m.cost) })))
              : A.empty("Nothing yet."))))],
        ["activity", "Activity", async () => A.panel("Everything done from this device", el("a", { class: "btn small quiet", href: `#/activity?tab=ai&person=${d.person_id}` }, "All their requests", icon("chevronRight")),
          recent.items.length ? A.eventDays(recent.items.map(A.reqEvent), { noPerson: true, noDevice: true }).node : A.empty("No requests yet."))],
        ["flagged", "Flagged", async () => A.panel(null, "credential detections and refusals from this device", d.flagged.length ? el("ol", { class: "events flat" }, d.flagged.map((r) => el("li", { class: "ev t-request" },
          el("time", { class: "ev-time", title: fmt.stamp(r.ts) }, fmt.when(r.ts)),
          el("div", { class: "ev-body" }, el("div", { class: "ev-head" }, A.flagBadges(r.flags), el("span", { class: "muted" }, r.client || "a tool"),
            r.model ? el("span", { class: "ev-model mono" }, r.model) : null),
          r.reason ? el("div", { class: "ev-sub" }, el("span", { class: "ev-reason" }, r.reason)) : null),
          el("div", { class: "ev-end" }, A.outcomeStatus("request", r.outcome, true)),
          el("a", { class: "ev-open", href: "#/records/" + r.id, "aria-label": "Open record " + r.id }, icon("chevronRight")))))
          : SUI.stateBox({ tone: "ok", icon: "shield", title: "Nothing flagged", text: "No credential detections or refusals from this device.", compact: true })), d.flagged.length || null],
        ["sessions", "Sessions", async () => A.panel(null, "one conversation each", d.sessions.length ? el("ul", { class: "mini-list" }, d.sessions.map((x) => el("li", null, el("span", { class: "mini-ic" }, icon("layers")),
          el("a", { class: "grow", href: "#/sessions/" + encodeURIComponent(x.session) }, el("strong", null, x.first_prompt || "(no typed prompt)"),
            el("div", { class: "hint" }, `${x.client || "a tool"} · ${SUI.plural(x.requests, "request")} · ${fmt.when(x.last)}`)),
          el("span", { class: "u-num" }, fmt.money(x.cost))))) : A.empty("No sessions yet.")), d.sessions.length || null],
        ["addresses", "Addresses", async () => A.panel(null, "named networks are exact; the offline table is approximate; nothing is looked up online", ips), d.ips.length || null],
      ], { label: d.label }),
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
    const held = (t) => t.assigned_people + t.assigned_teams > 0;
    const onKey = (t) => (t.kind === "dev" || t.kind === "api") && t.subscription.state === "none";
    // The catalogue is 49 tools; the ones Swangz actually runs come first, the rest are a filter away.
    const SHOW = [
      ["used", "In use", (t) => t.subscription.state !== "none" || onKey(t) || held(t)],
      ["idle", "Given, not opened", (t) => held(t) && !t.usage_30d.opens && t.kind === "site"],
      ["none", "Not subscribed", (t) => t.subscription.state === "none" && !onKey(t) && !held(t)],
      ["all", "All", () => true],
    ];
    // "" is the default view, In use; old links that say show=used land on it too.
    const st = { q: params.get("q") || "", cat: params.get("cat") || "", show: params.get("show") || "",
      page: Number(params.get("page")) || 1, per: Number(params.get("per")) || 25 };
    if (st.show === "used" || (st.show !== "removed" && !SHOW.some(([k]) => k === st.show))) st.show = "";
    const counts = Object.fromEntries(SHOW.map(([k, , f]) => [k, data.tools.filter(f).length]));
    const showOptions = [...SHOW.filter(([k]) => k !== "used" && (k !== "idle" || counts.idle || st.show === "idle")).map(([k, label]) => ({ id: k, label, sub: SUI.plural(counts[k], "tool") })),
      ...(data.removed.length || st.show === "removed" ? [{ id: "removed", label: "Removed", sub: SUI.plural(data.removed.length, "tool") }] : [])];
    const opens = data.tools.reduce((n, t) => n + t.usage_30d.opens, 0);
    const meta = el("div", { class: "list-meta" },
      el("span", null, `${data.summary.total} in the catalogue · ${SUI.plural(data.categories.length, "category", "categories")}`),
      el("a", { href: "#/licences" }, `${SUI.plural(data.summary.paid, "paid plan")} · ${fmt.money(data.summary.monthly_cost)} a month`),
      el("span", null, `${fmt.num(opens)} opens from the portal in 30 days`));
    const box = el("div");
    const sheetHref = (t, tab) => { const p = new URLSearchParams(location.hash.split("?")[1] || ""); p.set("open", t.id); if (tab) p.set("tab", tab); else p.delete("tab"); return "#/tools?" + p.toString(); };
    const pager = { page: st.page, size: st.per, onChange: (page, size) => { st.page = pager.page = page; st.per = pager.size = size; keep(); } };
    const rowActions = (t) => [
      { id: "profile", label: "Open profile", icon: "tools", href: sheetHref(t) },
      { id: "access", label: "Who has access", icon: "people", href: sheetHref(t, "access") },
      t.kind === "dev" ? null : { id: "subscription", label: "Subscription", icon: "wallet", href: sheetHref(t, "billing") },
      { id: "activity", label: "Activity", icon: "clock", href: "#/activity?tab=timeline&tool=" + encodeURIComponent(t.id) },
      A.can("govern") ? { id: "remove", label: "Remove from the catalogue", icon: "x", danger: true, onSelect: () => toolAction(t, "archive") } : null,
    ];
    function draw() {
      const qq = st.q.trim().toLowerCase();
      const match = (t) => (!st.cat || t.category === st.cat) && (!qq || t.name.toLowerCase().includes(qq) || t.category.toLowerCase().includes(qq));
      if (st.show === "removed") {
        const list = data.removed.filter(match);
        box.replaceChildren(list.length ? SUI.table({ caption: "Removed tools", rows: list, sort: ["name", "asc"], pager, columns: [
          { key: "name", label: "Tool", lead: true, render: (t) => el("div", { class: "u-cell" }, SUI.logo(t, "sm"), el("div", null, el("strong", null, t.name), el("span", { class: "sub" }, t.category || ""))) },
          { key: "builtin", label: "Origin", render: (t) => (t.builtin ? "Built in" : "Added by an admin") },
          A.can("govern") ? { key: "act", label: "", srLabel: "Actions", sort: false, render: (t) => SUI.menuButton({ label: "More actions for " + t.name, small: true, items: () => [
            { id: "restore", label: "Restore", icon: "check", onSelect: () => toolAction(t, "restore") },
            t.builtin ? null : { id: "delete", label: "Delete for good", icon: "x", danger: true, onSelect: () => deleteTool(t) },
          ] }) } : null,
        ].filter(Boolean) }) : SUI.stateBox({ icon: "tools", title: "Nothing removed matches", text: "Try another search." }),
        el("div", { class: "body hint" }, "Staff can't see or open removed tools. Restoring one brings back its settings and who could use it."));
        return;
      }
      const want = SHOW.find(([k]) => k === (st.show || "used"))[2];
      const list = data.tools.filter((t) => want(t) && match(t));
      box.replaceChildren(list.length ? SUI.table({ caption: "Tools", rows: list, sort: ["opens", "desc"], href: (t) => sheetHref(t), pager, columns: [
        { key: "name", label: "Tool", lead: true, render: (t) => el("a", { class: "u-cell", href: sheetHref(t) }, SUI.logo(t, "sm"),
          el("div", null, el("strong", null, t.name), el("span", { class: "sub" }, t.category))) },
        { key: "state", label: "Subscription", sort: (t) => (onKey(t) ? "api" : t.subscription.state), render: (t) => {
          const sub = t.subscription;
          const money = sub.state !== "none" ? [sub.plan, sub.monthly_cost != null ? fmt.money(sub.monthly_cost) + "/mo" : null].filter(Boolean).join(" · ") : "";
          return el("div", null, subStatus(t), money ? el("span", { class: "sub" }, money) : null);
        } },
        { key: "signin", label: "Sign-in", sort: (t) => (SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat)[0], render: (t) => (SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat)[0], hideSm: true },
        { key: "people", label: "Given to", num: true, sort: (t) => t.assigned_people, render: (t) => (held(t)
          ? el("span", null, SUI.plural(t.assigned_people, "person", "people"), t.assigned_teams ? el("span", { class: "sub" }, SUI.plural(t.assigned_teams, "team")) : null,
            t.subscription.seats ? el("span", { class: "sub" }, `${t.subscription.seats} seats paid`) : null)
          : el("span", { class: "faint" }, "no one")) },
        { key: "opens", label: "Opens · 30 days", num: true, sort: (t) => t.usage_30d.opens, render: (t) => (t.usage_30d.opens ? fmt.num(t.usage_30d.opens) : el("span", { class: "faint" }, "—")) },
        { key: "act", label: "", srLabel: "Actions", sort: false, render: (t) => SUI.menuButton({ label: "More actions for " + t.name, small: true, items: () => rowActions(t) }) },
      ] }) : SUI.stateBox({ icon: "tools", title: "No tools match", text: !st.show && !st.q && !st.cat ? "Nothing is subscribed or given yet. Set Show to Not subscribed." : "Try another search or filter." }));
    }
    const keep = () => A.keepParams("#/tools", { q: st.q, cat: st.cat, show: st.show, page: st.page > 1 ? st.page : null, per: st.per !== 25 ? st.per : null });
    const bar = SUI.filterBar({ label: "Filter tools", search: { placeholder: "Name or category" }, values: st, filters: [
      { id: "show", label: "Show", any: "In use", options: showOptions },
      { id: "cat", label: "Category", any: "All categories", options: data.categories.map((c) => ({ id: c, label: c })) },
    ], onChange: (v) => { st.q = v.q || ""; st.cat = v.cat || ""; st.show = v.show || ""; st.page = pager.page = 1; keep(); draw(); } });
    draw();
    A.frame({ title: "Tools", trail: [["Tools"]], lede: "What Swangz pays for, how people sign in, and who uses each tool. Open a tool for its full profile.",
      actions: A.can("govern") ? el("button", { class: "btn primary", onclick: () => toolSheet(null) }, icon("plus"), "Add a tool") : null }, [
      A.panel(null, null, el("div", { class: "filterbar" }, bar), meta, box),
    ]);
    const open = params.get("open");
    if (open && S.tools[open]) toolSheet(S.tools[open], params.get("tab") || "overview");
    if (params.get("add") && A.can("govern")) toolSheet(null);
  }

  async function toolAction(t, action) {
    if (action === "archive") {
      const ok = await A.confirmAction(`Remove ${t.name} from the catalogue?`, "Staff stop seeing it straight away and can't open it from the portal. Its history stays, and you can restore it from Show: Removed on the Tools page.", "Remove", true);
      if (!ok) return false;
    }
    try { await api("POST", `/tools/${t.id}/${action}`); toast(action === "archive" ? "Removed from the catalogue." : "Restored."); S.tools = null; await A.render(); return true; }
    catch (e) { toast(e.message, true); return false; }
  }

  async function deleteTool(t) {
    const ok = await A.confirmAction(`Delete ${t.name} for good?`, "It's removed from the catalogue along with its subscription and every grant. Past launches stay in the log without a tool name. This can't be undone.", "Delete tool", true);
    if (!ok) return;
    try { await api("DELETE", `/tools/${t.id}`); toast("Deleted."); S.tools = null; await A.render(); } catch (e) { toast(e.message, true); }
  }

  /* The one thing to do next about a tool, worst first: [what is true, the link's words, the tab it opens]. */
  function toolNext(t) {
    const sub = t.subscription, held = t.assigned_people + t.assigned_teams > 0;
    if (t.kind !== "dev" && sub.state === "past_due") return ["Payment is due.", "Update the subscription", "billing"];
    if (t.kind === "site" && sub.state !== "active") return ["Staff can't open it without an active subscription.", "Add the subscription", "billing"];
    if (!held) return ["Nobody has it yet.", "Give it to someone", "access"];
    if (sub.seats && t.assigned_people > sub.seats) return [`${SUI.plural(t.assigned_people, "person", "people")} have it, with ${SUI.plural(sub.seats, "seat")} paid.`, "Review who has it", "access"];
    if (t.kind === "site" && !t.usage_30d.opens) return ["Nobody has opened it in 30 days.", "Review who has it", "access"];
    return ["Nothing needs doing.", "See how it is used", "usage"];
  }

  /* A tool's profile. Overview says what it is and where it stands; each other tab is one job: how it's used,
     who may use it, what Swangz pays, how it's set up, and — for a shared company account — its turn rules and
     company browsers. The tab is in the address (?open=<tool>&tab=…), so Back steps through the tabs and then
     closes the sheet. Old links to tab=access, tab=billing and tab=settings still work. */
  function toolSheet(t, tab) {
    // the sheet's own place in the address, leaving the list's filters as they were
    const here = (id, tabId) => {
      const p = new URLSearchParams(location.hash.split("?")[1] || "");
      ["open", "tab", "add"].forEach((k) => p.delete(k));
      if (id) { p.set("open", id); p.set("tab", tabId); }
      return "#/tools" + (p.toString() ? "?" + p.toString() : "");
    };
    const { node, close } = A.sheet(() => { if (location.hash.startsWith("#/tools") && (location.hash.includes("open=") || location.hash.includes("add="))) history.replaceState(null, "", here()); }, t ? t.name : "Add a tool");
    const owner = A.can("govern");
    const shared = !!t && t.signin === "shared";
    async function refresh(nextTab) {
      close();
      S.tools = null;
      const next = t ? `#/tools?open=${t.id}&tab=${nextTab || "overview"}` : "#/tools";
      if (location.hash === next) await A.render();
      else location.hash = next;
    }
    // Overview and Usage read the same figures: ask once
    let usage = null;
    const getUsage = () => (usage = usage || api("GET", `/tools/${t.id}/usage`));
    const goTab = (id, label) => el("a", { class: "btn small", href: here(t.id, id) }, label, icon("chevronRight"));
    // The Next step line under the title; a grant or a removal on the Access tab can change it.
    const nextLine = t ? el("p", { class: "next-step sheet-next" }) : null;
    const drawNext = (x) => { const [fact_, words, id] = toolNext(x); nextLine.replaceChildren(el("strong", { class: "next-label" }, "Next step"), fact_ + " ", el("a", { href: here(x.id, id) }, words)); };
    const renewNext = () => A.toolIndex(true).then(() => drawNext(S.tools[t.id])).catch(() => null);

    async function overviewTab() {
      const how = SIGNIN[t.kind === "dev" ? "api" : t.signin] || SIGNIN.seat;
      const sub = t.subscription;
      const u = await getUsage();
      const uses30 = u.series.reduce((n, d) => n + d.uses, 0);
      const assigned = t.assigned_people + t.assigned_teams;
      return [
        t.description ? el("p", { class: "muted lead-text" }, t.description) : null,
        el("div", { class: "facts" },
          fact("Subscription", sub.state === "none" ? (t.kind === "site" ? "None yet" : "Metered on our API key") : [SUB_LABEL[sub.state], sub.plan].filter(Boolean).join(" · ")),
          fact("Seats", sub.seats ? `${sub.seats} paid` : "—"),
          fact("Given to", `${SUI.plural(t.assigned_people, "person", "people")}` + (t.assigned_teams ? ` · ${SUI.plural(t.assigned_teams, "team")}` : "")),
          fact("Active this month", SUI.plural(u.active_month, "person", "people")),
          fact(t.kind === "site" ? "Monthly cost" : "API cost · 30 days", t.kind === "site" ? (sub.monthly_cost != null ? fmt.money(sub.monthly_cost) : "—") : fmt.money(u.cost_30d),
            t.kind === "site" ? null : "Estimated from the price table"),
          fact("Use · 30 days", uses30 ? SUI.plural(uses30, "use") : "none", "Opens, website visits and API requests"),
          shared ? fact("Opens into", t.workspace_mode === "agent" ? "a company browser of their own, already signed in"
            : browserList(t).length ? `the shared workspace — ${SUI.plural(browserList(t).length, "browser")}` : "the tool's own site (they sign in)") : null),
        sub.seats && assigned ? el("div", { class: "seat-meter" }, el("div", { class: "spread" }, el("span", { class: "u-label" }, "Seat utilisation"),
          el("span", { class: "u-num" }, `${u.active_month} active of ${sub.seats} paid`)), A.bar(u.active_month, sub.seats)) : null,
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "How people sign in — " + how[0]), el("p", { class: "hint" }, how[1]),
          t.url ? el("div", null, el("a", { class: "btn small", href: t.url, target: "_blank", rel: "noopener noreferrer" }, "Visit website", icon("open"))) : null),
        el("div", { class: "row wrap" }, goTab("usage", "Use per day"), goTab("access", "Who has it and who uses it"),
          shared ? goTab("workspace", "Turns and company browsers") : null),
      ];
    }

    async function usageTab() {
      const u = await getUsage();
      return [
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Use per day · 30 days"),
          SUI.columns({ label: `${t.name} uses per day`, tone: 2, height: 130, yName: "Uses", data: u.series.map((d) => ({ label: fmt.weekday(d.start), short: fmt.dayMonth(d.start), value: d.uses })) })),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Refused · 30 days"),
          u.denials.length ? el("ul", { class: "mini-list boxed" }, u.denials.map((x) => el("li", null, el("span", { class: "mini-ic bad" }, icon("stop")),
            el("div", { class: "grow" }, x.person_id ? A.personLink(x.person_id, x.person, { avatar: false }) : el("span", null, x.person || "An unknown key"), el("div", { class: "hint" }, x.reason)),
            x.id ? el("a", { class: "hint", href: "#/records/" + x.id }, fmt.ago(x.ts)) : el("span", { class: "hint" }, fmt.ago(x.ts)))))
            : el("p", { class: "hint" }, "Nobody was refused.")),
        el("p", { class: "hint" }, "Each use in order, with who and where: ", el("a", { href: "#/activity?tab=timeline&tool=" + encodeURIComponent(t.id) }, "the Activity timeline for " + t.name), "."),
      ];
    }

    async function accessTab() {
      const [data, u] = await Promise.all([api("GET", `/tools/${t.id}/access`), getUsage()]);
      const teams = data.teams.length ? el("div", { class: "row" }, data.teams.map((team) => {
        const btn = el("button", { class: "btn small" + (team.on ? " primary" : ""), disabled: !owner, "aria-pressed": team.on ? "true" : "false", "aria-label": `${team.name}: ${team.on ? "on" : "off"}`, onclick: async () => {
          const adding = !btn.classList.contains("primary");
          try { await api(adding ? "POST" : "DELETE", `/teams/${encodeURIComponent(team.name)}/tools/${t.id}`); btn.classList.toggle("primary", adding); btn.textContent = adding ? "On" : "Off"; btn.setAttribute("aria-pressed", adding ? "true" : "false"); renewNext(); toast("Saved."); }
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
            renewNext(); toast(adding ? "Turned on." : "Turned off.");
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
      return [
        locked ? el("div", { class: "notice" }, "Staff can't open this until the company subscription is active (Subscription tab).") : null,
        onItNow,
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "Whole teams"), teams),
        el("div", { class: "stack" }, el("h3", { class: "section-title" }, "People"),
          el("p", { class: "hint" }, "Turn the tool on per person. Add an end date first to give it for a limited time — access stops after that day."),
          rows.length ? el("div", { class: "assign-list" }, rows) : A.empty("No people yet.")),
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
      ];
    }

    async function billingTab() {
      const sub = t.subscription;
      const owner = A.can("money");  // subscriptions are money, not access
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
        owner ? el("div", { class: "btn-row end form-actions" }, el("span", { class: "grow" }, err), save) : null,
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
        classification: el("select", { "aria-label": "Data class" }, Object.entries({ public: "Public", internal: "Internal", confidential: "Confidential", restricted: "Restricted" })
          .map(([k, l]) => el("option", { value: k }, l))),
        launch_url: el("input", { type: "url", value: v.launch_url || "", placeholder: "https://… (optional)" }),
        hosts: el("input", { type: "text", value: (v.hosts || []).join(", "), placeholder: "Filled from the website if left empty" }),
        color: el("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(v.color || "") ? v.color : "#3F3F46" }),
        pricing_url: el("input", { type: "url", value: v.pricing_url || "", placeholder: "https://…/pricing" }),
        seats_at_once: el("input", { type: "number", min: "1", max: "50", step: "1", value: String(v.seats_at_once || 1) }),
        turn_minutes: el("input", { type: "number", min: "5", max: "720", step: "5", value: String(v.turn_minutes || 120) }),
        workspace_url: el("textarea", { rows: "3", spellcheck: "false", placeholder: "https://workspace.swangzavenue.com/chatgpt-1/\nhttps://workspace.swangzavenue.com/chatgpt-2/" }, v.workspace_url || ""),
        workspace_mode: el("select", null,
          el("option", { value: "agent" }, "Swangz's company browsers — started when needed"),
          el("option", { value: "" }, "The browsers listed below, or none")),
      };
      f.workspace_mode.value = v.workspace_mode === "agent" ? "agent" : "";
      const listField = el("label", { class: "field" }, "Shared workspace browsers", f.workspace_url,
        el("span", { class: "hint" }, "Optional. One address per line — each is a browser on Swangz's own server that an admin has signed in to this tool once. Everyone holding a turn gets a browser to themselves. Leave empty and Open goes to the tool's own site. See deploy/WORKSPACE.md."),
        el("span", { class: "hint" }, S.workspaceManaged ? "The gateway gives each person a sign-in for their turn and removes it the moment the turn ends."
          : "The gateway isn't managing workspace sign-ins yet (GATEWAY_WORKSPACE_TOKEN is not set), so each browser's own login decides who gets in."));
      const agentHint = el("span", { class: "hint" }, S.workspaceAgent
        ? "Each person on a turn gets a browser of their own, already signed in, recycled when the turn ends — on the rented server or one of Swangz's computers (Settings → Company browsers). Once it is saved, its browsers are listed under Workspace — sign each one in to the tool there, once."
        : "The company browsers aren't connected yet: Settings → Company browsers (the rented server, the Windows PC or the Mac). Until they are, Open can't give anyone a browser for this tool.");
      const drawWhere = () => { listField.hidden = f.workspace_mode.value === "agent"; agentHint.hidden = f.workspace_mode.value !== "agent"; };
      f.workspace_mode.addEventListener("change", drawWhere); drawWhere();
      // a new tool sets its turn rules here; an existing one has them under Workspace
      const sharing = !t ? el("div", { class: "share-box" },
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "People on it at a time", f.seats_at_once, el("span", { class: "hint" }, "Usually 1 — one account, one person. With a workspace, never more than its browsers.")),
          el("label", { class: "field" }, "How long a turn lasts (minutes)", f.turn_minutes, el("span", { class: "hint" }, "It ends by itself after this, or when they hand it back."))),
        el("div", { class: "hint" }, "While someone holds the turn, nobody else can open this tool, and the extension signs their browser out when it ends — so the vendor's credit history can be matched to a person."),
        el("label", { class: "field" }, "Company browsers", f.workspace_mode, agentHint),
        listField)
        : el("div", { class: "notice info" }, icon("info"), el("span", null, "How long a turn lasts, how many people at a time, and the company browsers are under ",
          el("a", { href: here(t.id, "workspace") }, "Workspace"), t.signin === "shared" ? "." : " once this is saved."));
      f.kind.value = v.kind; f.signin.value = v.kind === "dev" ? "api" : (v.signin || "seat");
      f.classification.value = v.classification || "internal";
      const howHint = el("span", { class: "hint" });
      const drawHow = () => { howHint.textContent = (SIGNIN[f.signin.value] || SIGNIN.seat)[1]; sharing.hidden = f.signin.value !== "shared"; };
      f.signin.addEventListener("change", drawHow); drawHow();
      const err = el("div", { class: "err", role: "alert" });
      const values = () => ({ name: f.name.value, category: f.category.value, kind: f.kind.value, description: f.description.value, url: f.url.value,
        signin: f.signin.value, launch_url: f.launch_url.value, hosts: f.hosts.value, color: f.color.value, pricing_url: f.pricing_url.value,
        ...(t ? { classification: f.classification.value } : { seats_at_once: f.seats_at_once.value, turn_minutes: f.turn_minutes.value, workspace_url: f.workspace_url.value, workspace_mode: f.workspace_mode.value }) });
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
        t ? el("label", { class: "field" }, "Data class", f.classification,
          el("span", { class: "hint" }, "What kind of company information may go into it. Policies can refuse tools by class (Govern → Policies).")) : null,
        sharing,
        el("label", { class: "field" }, "Company sign-in link", f.launch_url,
          el("span", { class: "hint" }, "Where Open sends people. For single sign-on, paste the tool's SSO link — or the app's link from Google Admin → Apps → Web and mobile apps. Empty = the website.")),
        el("div", { class: "form-grid" },
          el("label", { class: "field" }, "Domains (for the browser extension)", f.hosts),
          el("label", { class: "field" }, "Pricing page", f.pricing_url),
          el("label", { class: "field" }, "Brand colour", f.color)),
        owner ? el("div", { class: "btn-row end form-actions" }, el("span", { class: "grow" }, err), save) : null,
        t && owner ? el("div", { class: "danger-zone" },
          el("div", null, el("strong", null, t.builtin ? "Remove from the catalog" : "Remove or delete"),
            el("div", { class: "hint" }, t.builtin ? "Hidden from staff and closed to launches. You can restore it any time." : "Remove hides it (restorable). Delete erases it with its grants.")),
          el("div", { class: "row" },
            el("button", { class: "btn danger", onclick: async () => { if (await toolAction(t, "archive")) close(); } }, "Remove"),
            t.builtin ? null : el("button", { class: "btn danger solid", onclick: () => { close(); deleteTool(t); } }, "Delete"))) : null,
      ];
    }

    /* Shared company accounts only: the turn rules, and the company browsers people are given for a turn. */
    async function workspaceTab() {
      const f = {
        seats_at_once: el("input", { type: "number", min: "1", max: "50", step: "1", value: String(t.seats_at_once || 1), disabled: !owner }),
        turn_minutes: el("input", { type: "number", min: "5", max: "720", step: "5", value: String(t.turn_minutes || 120), disabled: !owner }),
        workspace_url: el("textarea", { rows: "3", spellcheck: "false", disabled: !owner, placeholder: "https://workspace.swangzavenue.com/chatgpt-1/\nhttps://workspace.swangzavenue.com/chatgpt-2/" }, t.workspace_url || ""),
        workspace_mode: el("select", { disabled: !owner },
          el("option", { value: "agent" }, "Swangz's company browsers — started when needed"),
          el("option", { value: "" }, "The browsers listed below, or none")),
      };
      f.workspace_mode.value = t.workspace_mode === "agent" ? "agent" : "";
      const listField = el("label", { class: "field" }, "Fixed browsers", f.workspace_url,
        el("span", { class: "hint" }, "One address per line — each a browser on Swangz's own server that an admin has signed in to this tool once. Everyone holding a turn gets a browser to themselves. Empty: Open goes to the tool's own site. See deploy/WORKSPACE.md."),
        el("span", { class: "hint" }, S.workspaceManaged ? "The gateway gives each person a sign-in for their turn and removes it the moment the turn ends."
          : "The gateway isn't managing these browsers' sign-ins (GATEWAY_WORKSPACE_TOKEN is not set), so each browser's own login decides who gets in."));
      const agentHint = el("span", { class: "hint" }, S.workspaceAgent
        ? "Each person on a turn gets a browser of their own, already signed in, recycled when the turn ends — on the rented server or one of Swangz's computers (Settings → Company browsers)."
        : "The company browsers aren't connected yet: Settings → Company browsers (the rented server, the Windows PC or the Mac). Until they are, Open can't give anyone a browser for this tool.");
      const drawWhere = () => { listField.hidden = f.workspace_mode.value === "agent"; agentHint.hidden = f.workspace_mode.value !== "agent"; };
      f.workspace_mode.addEventListener("change", drawWhere); drawWhere();
      const err = el("span", { class: "err", role: "alert" });
      const save = owner ? el("button", { class: "btn primary", onclick: async () => {
        err.textContent = "";
        try {
          await api("PATCH", "/tools/" + t.id, { seats_at_once: f.seats_at_once.value, turn_minutes: f.turn_minutes.value, workspace_mode: f.workspace_mode.value, workspace_url: f.workspace_url.value });
          toast("Saved."); refresh("workspace");
        } catch (e) { err.textContent = e.message; }
      } }, "Save") : null;
      // company browsers: each must be signed in to the tool once, by an admin, here
      let fromServer = null;
      if (t.workspace_mode === "agent") {
        const ws = await api("GET", "/workspace");
        const mine = ws.configured && !ws.error ? (ws.browsers || []).filter((b) => b.tool === t.id) : [];
        const place = ws.label.charAt(0).toUpperCase() + ws.label.slice(1);
        fromServer = A.panel("Company browsers on " + ws.label, null, el("div", { class: "body stack" },
          !ws.configured ? el("div", { class: "notice" }, `${place} isn't connected yet — `, el("a", { href: "#/settings?tab=browsers" }, "Settings → Company browsers"), ".")
            : ws.error ? el("div", { class: "notice" }, `${place} isn't answering: ${ws.error}`)
              : mine.length ? el("div", { class: "assign-list" }, mine.map((b) => browserRow(b, null, owner, () => refresh("workspace"))))
                : el("div", { class: "notice" }, ws.host === "server"
                  ? `The rented server has no browsers for this tool yet — add "${t.id}" to its config.`
                  : `${place} gets its browsers from here within a minute of saving this tool — one for each person on it at a time.`),
          el("p", { class: "hint" }, "Each browser keeps its own sign-in to the tool, so sign each one in once: press Sign in to the tool, open it, sign in to the tool inside it with the company account, then press Done. Nobody can be given that browser meanwhile.")));
      }
      return [
        el("p", { class: "hint" }, "One company account, one person at a time: while someone holds the turn, nobody else can open this tool, and the extension signs their browser out when it ends — so the vendor's credit history can be matched to a person. Who is on it now is under ",
          el("a", { href: here(t.id, "access") }, "Access"), "."),
        A.panel("Turns", null, el("div", { class: "body stack" },
          el("div", { class: "form-grid" },
            el("label", { class: "field" }, "People on it at a time", f.seats_at_once, el("span", { class: "hint" }, "Usually 1 — one account, one person. With company browsers, never more than there are browsers.")),
            el("label", { class: "field" }, "How long a turn lasts (minutes)", f.turn_minutes, el("span", { class: "hint" }, "It ends by itself after this, or when they hand it back."))),
          el("label", { class: "field" }, "Where Open takes them", f.workspace_mode, agentHint),
          listField),
          owner ? A.panelFoot(err, save) : null),
        fromServer,
      ];
    }

    if (t) drawNext(t);
    // the tabs: an existing tool's profile, or the form for a new one
    let tabsUi = null;
    if (t) {
      const params = new URLSearchParams(location.hash.split("?")[1] || "");
      if (!params.get("tab") && tab) params.set("tab", tab);
      tabsUi = A.pageTabs("#/tools", params, [
        ["overview", "Overview", overviewTab],
        ["usage", "Usage", usageTab],
        ["access", "Access", accessTab],
        t.kind === "dev" ? null : ["billing", "Subscription", billingTab],
        ["settings", "Configuration", settingsTab],
        shared ? ["workspace", "Workspace", workspaceTab] : null,
      ], { split: true, help: false, label: t.name + " views" });
    }
    const body = el("div", { class: "sheet-body" }, tabsUi ? tabsUi.body : null);
    if (!t) SUI.load(body, settingsTab, SUI.skeleton("rows", 4));
    const head = el("header", null,
      el("div", { class: "spread" },
        el("div", { class: "sheet-id" }, t ? SUI.logo(t, "lg") : el("span", { class: "dev-ic lg" }, icon("plus")),
          el("div", null, t ? el("nav", { class: "eyebrow sheet-trail", "aria-label": "You are here" }, el("a", { href: here() }, "Tools"), el("span", { "aria-hidden": "true" }, " › "), t.category) : el("div", { class: "eyebrow" }, "Catalog"), el("h2", null, t ? t.name : "Add a tool"),
            t ? el("div", { class: "row" }, subStatus(t), SUI.badge(KIND[t.kind] || t.kind, "outline")) : null)),
        el("div", { class: "row" }, t ? el("a", { class: "btn small primary", href: here(t.id, "access") }, owner ? "Manage access" : "Who has access") : null,
          t ? SUI.menuButton({ label: "More about " + t.name, small: true, items: () => [
            { id: "activity", label: "Activity timeline", icon: "clock", href: "#/activity?tab=timeline&tool=" + encodeURIComponent(t.id) },
            t.kind === "dev" ? null : { id: "licences", label: "Licences and spend", icon: "wallet", href: "#/licences" },
            { id: "requests", label: "Access requests", icon: "people", href: "#/requests?q=" + encodeURIComponent(t.name) },
          ] }) : null,
          el("button", { class: "btn small quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x")))),
      nextLine,
      tabsUi ? tabsUi.bar : null);
    node.append(head, body);
  }

  /* One company browser: running or not, who is on it, and — for owners — signing it in to its tool, once.
     `host` names the place it runs ("server", "windows", "mac"); null = the one Open uses. */
  function browserRow(b, host, owner, after) {
    const STATE = { running: ["ok", "Running"], starting: ["waiting", "Starting"], stopped: ["none", "Stopped"] };
    const q = host ? "?host=" + host : "";
    const openBrowser = async (btn) => {
      btn.disabled = true; btn.textContent = "Starting…";
      try {
        for (let i = 0; i < 45; i++) {  // a cold start takes a few seconds; give it up to ~2 minutes
          const out = await api("POST", `/workspace/browsers/${b.slot}/open${q}`);
          if (out.state === "ready" && out.url) {
            btn.replaceWith(el("a", { class: "btn small primary", href: out.url, target: "_blank", rel: "noopener noreferrer" }, "Open it", icon("open")));
            toast("Ready. Sign in to the tool inside it, then press Done.");
            return;
          }
          await new Promise((r) => setTimeout(r, 3000));
        }
        toast("The browser is taking too long to start. Try again in a minute.", true);
      } catch (e) { toast(e.message, true); }
      btn.disabled = false; btn.textContent = "Sign in to the tool";
    };
    const closeBrowser = async () => {
      try { await api("POST", `/workspace/browsers/${b.slot}/close${q}`); toast("Done — the browser is free again."); after(); }
      catch (e) { toast(e.message, true); }
    };
    const [tone, label] = STATE[b.state] || ["none", b.state];
    const who = !b.holder ? "Free" : b.holder.kind === "admin" ? `${b.holder.name} is signing it in` : `${b.holder.name} · since ${fmt.clock(b.holder.since)}`;
    let action = null;
    if (owner && b.holder && b.holder.kind === "admin") {
      action = el("span", { class: "row" },
        el("button", { class: "btn small", onclick: (e) => openBrowser(e.currentTarget) }, "Open again"),
        el("button", { class: "btn small primary", onclick: closeBrowser }, "Done"));
    } else if (owner && !b.holder) {
      action = el("button", { class: "btn small", onclick: (e) => openBrowser(e.currentTarget) }, "Sign in to the tool");
    }
    return el("div", { class: "assign-row" }, el("span", { class: "dev-ic sm" }, String(b.n)),
      el("div", { class: "grow" }, el("strong", null, `Browser ${b.n}`), " ", SUI.status(tone, label, { plain: true }), el("div", { class: "hint" }, who)), action);
  }
  A.browserRow = browserRow;

  // ------------------------------------------------------------------ Access requests

  /* Access requests on the control kit (BRIEF 10.10): one list, one filter row (Status, with the counts, and a search),
     a pager, and the decision at the right edge of its row — Decline first, Grant last. No primary button: the page has
     no single action, each row has its own. The Next step line names the oldest request that is still waiting. */
  async function pageRequests(params) {
    await A.toolIndex().catch(() => null);
    const owner = A.can("govern");
    const data = await api("GET", "/access-requests?state=any");
    const counts = data.counts || { open: data.open };
    // no ?state= means the open ones; ?state=any is every decision
    const st = { q: params.get("q") || "", state: params.get("state") === "any" ? "" : ["granted", "declined"].includes(params.get("state")) ? params.get("state") : "open",
      page: Number(params.get("page")) || 1, per: Number(params.get("per")) || 25 };
    const STATES = [["open", "Open"], ["granted", "Granted"], ["declined", "Declined"]];
    const box = el("div");
    const meta = el("div", { class: "list-meta" });
    const pager = { page: st.page, size: st.per, onChange: (page, size) => { st.page = pager.page = page; st.per = pager.size = size; keep(); } };
    const keep = () => A.keepParams("#/requests", { q: st.q, state: st.state === "open" ? null : st.state || "any", page: st.page > 1 ? st.page : null, per: st.per !== 25 ? st.per : null });
    const rowMenu = (r) => [
      { id: "person", label: "Their record", icon: "people", href: "#/people/" + r.person_id },
      { id: "tool", label: "The tool", icon: "tools", href: "#/tools?open=" + r.tool_id },
    ];
    const decision = (r) => r.state === "open"
      ? (owner ? el("span", { class: "req-act" },
        el("button", { class: "btn small quiet", type: "button", onclick: () => declineWithNote(r) }, "Decline"),
        el("button", { class: "btn small", type: "button", onclick: () => decide(r, "grant") }, icon("check"), "Grant"))
        : SUI.status("pending", "Waiting for an owner", { plain: true }))
      : el("div", null, SUI.status(r.state === "granted" ? "ok" : "blocked", r.state === "granted" ? "Granted" : "Declined", { plain: true }),
        el("span", { class: "sub", title: r.decided ? fmt.stamp(r.decided) : null }, `by ${r.decided_by || "an owner"} ${fmt.ago(r.decided)}`));
    function table(rows) {
      return SUI.table({ caption: "Access requests", rows, pager, sort: ["created", st.state === "open" ? "asc" : "desc"], columns: [
        { key: "person", label: "Person", lead: true, render: (r) => el("div", { class: "u-cell" }, SUI.avatar(r.person),
          el("div", null, A.personLink(r.person_id, r.person, { avatar: false }), el("span", { class: "sub" }, r.department || "No department"))) },
        { key: "tool", label: "Asked for", render: (r) => A.toolLink(r.tool_id, r.tool, "xs") },
        { key: "reason", label: "Why", sort: false, hideSm: true, render: (r) => el("div", { class: "req-why" }, r.reason || el("span", { class: "faint" }, "No reason given"),
          r.decision_note ? el("span", { class: "sub" }, "Note: " + r.decision_note) : null) },
        { key: "created", label: "Asked", num: true, render: (r) => el("span", { title: fmt.stamp(r.created) }, fmt.ago(r.created)) },
        { key: "state", label: "Decision", sort: false, render: decision },
        { key: "act", label: "", srLabel: "Actions", sort: false, render: (r) => SUI.menuButton({ label: `More actions for ${r.person}'s request`, small: true, items: () => rowMenu(r) }) },
      ] });
    }
    function draw() {
      const qq = st.q.trim().toLowerCase();
      const items = data.items.filter((r) => (!st.state || r.state === st.state) && (!qq || [r.person, r.tool, r.reason, r.department].join(" ").toLowerCase().includes(qq)));
      meta.replaceChildren(el("span", null, st.state === "open" ? "Granting turns the tool on for them at once" : "Decisions are in the audit log too"),
        el("span", null, SUI.plural(items.length, (st.state ? st.state + " " : "") + "request")));
      box.replaceChildren(items.length ? table(items)
        : SUI.stateBox({ icon: "requests", tone: st.state === "open" && !qq ? "ok" : null, title: qq ? "Nothing matches" : st.state === "open" ? "No open requests" : "Nothing here yet",
          text: qq ? "Try another search or status." : st.state === "open" ? "When staff ask for a tool in Swangz AI Hub, it appears here." : "Decided requests appear here." }));
    }
    const bar = SUI.filterBar({ label: "Filter access requests", search: { placeholder: "Person, tool or reason" }, values: st, filters: [
      { id: "state", label: "Status", any: "All", options: STATES.map(([k, label]) => ({ id: k, label, sub: SUI.plural(counts[k] || 0, "request") })) },
    ], onChange: (v) => { st.q = v.q || ""; st.state = v.state || ""; st.page = pager.page = 1; keep(); draw(); } });
    draw();
    const open = data.items.filter((r) => r.state === "open");
    const oldest = open.length ? Math.min(...open.map((r) => r.created)) : null;
    const next = open.length ? `${SUI.plural(open.length, "request")} waiting for a decision. The oldest was asked ${fmt.ago(oldest)}${owner ? "; decide it first." : "; only an owner can decide."}`
      : "Nothing is waiting for a decision.";
    A.frame({ title: "Access requests", trail: [["Access requests"]], next, lede: "Staff asking for tools in Swangz AI Hub. Granting turns the tool on for them straight away." },
      A.panel(null, null, el("div", { class: "filterbar" }, bar), meta, box));
  }

  function declineWithNote(r) {
    const note = el("textarea", { rows: "3", maxlength: "500", placeholder: "Optional — e.g. we're not renewing that tool; try Canva instead." });
    const go = el("button", { class: "btn danger", type: "button", onclick: async () => { await decide(r, "decline", note.value); d.close(); } }, "Decline request");
    const d = A.dialog(`Decline ${r.person}'s request?`, el("div", { class: "stack" },
      el("p", { class: "muted" }, `${r.person} asked for ${r.tool}${r.reason ? ` — “${r.reason}”` : ""}. They'll see it was declined, with your note if you add one.`),
      el("label", { class: "field" }, "Note for them", note)), [go]);
    note.focus();
  }

  async function decide(r, action, note) {
    try {
      await api("POST", `/access-requests/${r.id}/${action}`, note ? { note } : undefined);
      toast(action === "grant" ? `Granted — ${r.tool} is on for ${r.person}.` : "Declined.");
      A.render();
    } catch (e) { toast(e.message, true); }
  }

  A.page(/^#\/people$/, pagePeople);
  A.page(/^#\/people\/(\d+)$/, pagePerson);
  A.page(/^#\/devices$/, pageDevices);
  A.page(/^#\/devices\/([0-9a-f]{12})$/, pageDevice);
  A.page(/^#\/tools$/, pageTools);
  A.page(/^#\/requests$/, pageRequests);
})();
