"use strict";
/* Swangz AI Hub — Workstations (#/workstations), the Control Room's first page and its landing after sign-in (owner
   directive, 27 Nov 2026). Swangz AI Hub is one installed AI workstation app per employee plus this Control Room: no
   turns, no queues, no timers. Everyone authorised works at the same time with their own seat or account; where a tool
   is one company login, the page says so plainly and recommends a seat each or company sign-in.

   One read (GET /admin/api/workstations, gateway/workstations.py) answers the owner's list on one screen:
   1 employees and departments, 2 devices (online, app version, Chrome and AI apps, whose computer, Suspend and Revoke on
   the existing routes), 3 who has which app, 4 accounts and subscriptions, 5 activity observed in Swangz (kept apart from
   provider-reported usage and billing, which nobody sends yet), 6 weekly staff reports. Each block links to the page
   that holds the detail. Simple (default) is one sentence, one next step and at most three blocks; Detailed is all six. */
(() => {
  const { el, icon, fmt, toast } = SUI;
  const A = SWA;
  const { api } = A;

  const many = (n, one, more) => Number(n || 0).toLocaleString() + " " + (n === 1 ? one : more);
  const APP_WORD = { installed: "Installed", missing: "Missing", web: "Web", installing: "Installing", failed: "Failed", unknown: "Not readable" };
  const APP_TONE = { installed: "ok", web: "info", installing: "waiting", missing: "waiting", failed: "blocked", unknown: "none" };
  const SIGNIN_WORD = { sso: "Company sign-in", seat: "A seat each", shared: "One company login", own: "Their own account", api: "Company key" };
  const SUB_WORD = { none: "No licence", active: "Active", past_due: "Payment due", cancelled: "Cancelled" };

  /* The one sentence and the one next step, most useful first. Pure: tests run it in Node.
     n: { loaded, people, devices, connected, online, offline, withoutDevice, singleLogins, missing } */
  function workstationsLead(n) {
    if (!n.loaded) return { sentence: "The workstations could not load.", action: { label: "Try again", retry: true } };
    if (!n.people) return { sentence: "Nobody is on the Hub yet.", action: { label: "Add people", href: "#/people?add=1" } };
    if (!n.connected) return { sentence: "No computer has the Swangz app yet.", action: { label: "See who needs it", href: "#/people" } };
    if (n.singleLogins) return { sentence: `${many(n.singleLogins, "tool uses", "tools use")} one company login.`,
      action: { label: n.singleLogins === 1 ? "See the account limit" : "See the account limits", href: "#/workstations?view=detailed&focus=accounts" } };
    if (n.withoutDevice) return { sentence: `${many(n.withoutDevice, "person has", "people have")} no workstation yet.`, action: { label: "See people", href: "#/people" } };
    if (n.missing) return { sentence: `${many(n.missing, "weekly report is", "weekly reports are")} missing.`, action: { label: "Open weekly reports", href: "#/weekly" } };
    if (n.offline) return { sentence: `${n.offline.toLocaleString()} of ${many(n.connected, "computer is", "computers are")} offline.`,
      action: { label: "See the computers", href: "#/workstations?focus=devices" } };
    return { sentence: n.connected === 1 ? "The one computer is online." : `All ${n.connected.toLocaleString()} computers are online.`,
      action: { label: "See the computers", href: "#/workstations?focus=devices" } };
  }

  // ------------------------------------------------------------------ small pieces

  function appCounts(apps) {
    const n = {};
    apps.forEach((a) => { n[a.state] = (n[a.state] || 0) + 1; });
    return n;
  }
  function appsCell(d, detailed) {
    if (!d.apps.length) return el("span", { class: "hint" }, d.apps_reported ? "None reported" : "Not reported yet");
    if (detailed) return el("span", { class: "ws-apps" }, d.apps.map((a) => SUI.badge(`${a.name}: ${APP_WORD[a.state] || a.state}`, APP_TONE[a.state] === "ok" ? "ok" : APP_TONE[a.state] === "blocked" ? "bad" : "outline")));
    const n = appCounts(d.apps);
    const words = ["installed", "missing", "web", "installing", "failed", "unknown"].filter((s) => n[s]).map((s) => `${n[s]} ${APP_WORD[s].toLowerCase()}`);
    return el("span", { class: "ws-apps-sum", title: d.apps.map((a) => `${a.name}: ${APP_WORD[a.state] || a.state}`).join("\n"), tabindex: "0" }, words.join(" · "));
  }
  function chromeCell(d) {
    if (!d.chrome) return el("span", { class: "hint" }, "Not reported");
    return SUI.status(APP_TONE[d.chrome] || "none", APP_WORD[d.chrome] || d.chrome, { plain: true, title: d.chrome_version ? "Chrome " + d.chrome_version : null });
  }
  function stateCell(d) {
    if (!d.connected) return SUI.status("none", "Disconnected", { plain: true });
    if (d.workspace !== "active") return SUI.status("blocked", d.workspace === "retired" ? "Closed" : "Suspended", { plain: true });
    if (d.online) return SUI.status("ok", "Online", { plain: true });
    return SUI.status("idle", d.last_seen ? "Offline · " + fmt.ago(d.last_seen) : "Offline · never seen", { plain: true });
  }

  /* A confirm dialog that asks why, in plain words; the reason goes to the audit log with the change. Resolves with the
     reason, or null when cancelled. Never a browser alert. */
  function askReason(title, text, label, danger) {
    return new Promise((resolve) => {
      let out = null;
      const box = el("textarea", { rows: "3", maxlength: "500", placeholder: "For example: laptop lost, or they left the company" });
      const err = el("div", { class: "err", role: "alert" });
      const yes = el("button", { class: "btn " + (danger ? "danger solid" : "primary"), type: "button", onclick: () => {
        const reason = box.value.trim();
        if (!reason) { err.textContent = "Say why in a few words. It is kept in the audit log."; box.focus(); return; }
        out = reason; d.close();
      } }, label);
      const no = el("button", { class: "btn quiet", type: "button", onclick: () => d.close() }, "Cancel");
      const d = A.dialog(title, el("div", { class: "stack" }, el("p", { class: "confirm-text" }, text),
        el("label", { class: "field" }, "Why are you doing this?", box), err), [no, yes]);
      d.addEventListener("close", () => resolve(out));
      box.focus();
    });
  }

  async function suspend(d) {
    const reason = await askReason(`Suspend ${d.name}?`, `The Swangz workspace on ${d.person || "this person"}'s computer closes within a minute. Nothing is deleted, and you can turn it back on later.`, "Suspend", true);
    if (reason === null) return;
    try { await api("POST", `/devices/${encodeURIComponent(d.device_id)}/workspace`, { action: "suspend", reason }); toast(`${d.name} is suspended.`); A.render(); }
    catch (e) { toast(e.message, true); }
  }
  async function reactivate(d) {
    const reason = await askReason(`Turn ${d.name} back on?`, `The Swangz workspace on ${d.person || "this person"}'s computer opens again at its next check-in.`, "Turn back on", false);
    if (reason === null) return;
    try { await api("POST", `/devices/${encodeURIComponent(d.device_id)}/workspace`, { action: "reactivate", reason }); toast(`${d.name} is back on.`); A.render(); }
    catch (e) { toast(e.message, true); }
  }
  async function revoke(d) {
    const reason = await askReason(`Revoke ${d.name}?`, `${d.name} is signed out of Swangz now: its key stops working, anything running is cut, and the app removes what it set up. ${d.person || "They"} can sign in again later with a new code.`, "Revoke", true);
    if (reason === null) return;
    try { await api("POST", `/keys/${encodeURIComponent(d.key_id)}/revoke`, { reason }); toast(`${d.name} is revoked.`); A.render(); }
    catch (e) { toast(e.message, true); }
  }

  function deviceMenu(d) {
    const stop = A.can("govern") || A.can("emergency");
    return SUI.menuButton({ label: "More for " + d.name, small: true, align: "end", items: () => [
      { id: "person", label: d.person ? `See ${d.person}'s record` : "See their record", icon: "user", href: `#/people/${d.person_id}?tab=devices` },
      d.connected && d.workspace === "active" && stop ? { id: "suspend", label: "Suspend", icon: "stop", onSelect: () => suspend(d) } : null,
      d.connected && d.workspace === "suspended" && A.can("govern") ? { id: "reactivate", label: "Turn back on", icon: "play", onSelect: () => reactivate(d) } : null,
      d.connected && d.key_id && stop ? { id: "revoke", label: "Revoke", icon: "x", danger: true, onSelect: () => revoke(d) } : null,
    ].filter(Boolean) });
  }

  function deviceTable(items, detailed) {
    const cols = [
      { key: "name", label: "Computer", lead: true, sort: (d) => d.name.toLowerCase(), render: (d) => el("div", { class: "ws-who" },
        el("strong", null, d.name), el("span", { class: "hint" }, [d.person || "Unknown person", detailed ? null : d.department].filter(Boolean).join(" · "))) },
      { key: "online", label: "Status", sort: (d) => (d.connected ? (d.online ? 3 : d.workspace === "active" ? 2 : 1) : 0), render: stateCell },
      detailed ? { key: "app_version", label: "App version", render: (d) => d.app_version || "—" } : null,
      { key: "apps", label: "AI apps", sort: (d) => d.apps.filter((a) => a.state === "installed").length, render: (d) => appsCell(d, detailed) },
      { key: "chrome", label: "Chrome", render: chromeCell },
      detailed ? { key: "owner_kind", label: "Whose computer", render: (d) => (d.owner_kind === "company" ? "Company" : "Personal") + (d.owner_confirmed ? "" : " (their word)") } : null,
      detailed ? { key: "os", label: "System", hideSm: true, render: (d) => [d.os, d.arch].filter(Boolean).join(" · ") || "—" } : null,
      detailed ? { key: "last_seen", label: "Last seen", num: true, render: (d) => (d.last_seen ? fmt.ago(d.last_seen) : "never") } : null,
      { key: "more", label: "", srLabel: "Actions", sort: false, render: deviceMenu },
    ].filter(Boolean);
    return SUI.table({ caption: "Computers with the Swangz app", rows: items, columns: cols, sort: ["online", "desc"],
      pager: { page: 1, size: detailed ? 25 : 10, sizes: detailed ? [25, 50, 100] : [10] } });
  }

  function seeAll(label, href) { return el("a", { class: "btn small quiet", href }, label, icon("chevronRight")); }
  function line(label, value, href) {
    return el("a", { class: "ov-num", href }, el("span", null, label), el("strong", { class: "u-num" }, value), icon("chevronRight"));
  }

  // ------------------------------------------------------------------ the six blocks

  function employeesBlock(e) {
    const depts = e.departments.slice(0, 8);
    return A.panel("Employees and departments", seeAll("People", "#/people"), el("div", { class: "body stack" },
      el("p", { class: "ws-big" }, el("strong", { class: "u-num" }, e.active.toLocaleString()), " ", e.active === 1 ? "person can use the Hub" : "people can use the Hub",
        e.suspended ? el("span", { class: "hint" }, ` · ${e.suspended.toLocaleString()} paused`) : null),
      depts.length ? el("div", { class: "row wrap ws-chips" }, depts.map((d) => SUI.badge(`${d.name} · ${d.people}`, "outline")),
        e.departments.length > depts.length ? el("span", { class: "hint" }, `and ${many(e.departments.length - depts.length, "more department", "more departments")}`) : null)
        : el("p", { class: "hint" }, "No departments yet."),
      e.without_device ? el("p", { class: "hint" }, `${many(e.without_device, "person has", "people have")} no computer with the Swangz app yet.`) : null));
  }

  function devicesBlock(dev, detailed, online) {
    const s = dev.summary;
    const head = `${s.online.toLocaleString()} online · ${s.offline.toLocaleString()} offline` + (s.suspended ? ` · ${s.suspended.toLocaleString()} suspended` : "");
    return el("div", { id: "ws-devices" }, A.panel("Computers", seeAll("All devices", "#/devices"), el("div", { class: "body stack" },
      el("p", { class: "hint" }, head + `. Online means it checked in within the last ${online} minutes.`),
      dev.items.length ? deviceTable(dev.items, detailed)
        : SUI.stateBox({ compact: true, icon: "device", title: "No computers yet", text: "When someone installs the Swangz app and signs in, their computer appears here." }),
      s.connected && !s.apps_reported ? el("p", { class: "hint" }, "No computer has reported its apps yet. The newest Swangz app reports Chrome and AI apps at each check-in.") : null)));
  }

  function assignedBlock(assigned) {
    return A.panel("Who has which app", seeAll("Tools", "#/tools"), el("div", { class: "body" },
      assigned.items.length ? SUI.table({ caption: "Apps given to people", rows: assigned.items, sort: ["people", "desc"],
        href: (t) => `#/tools?open=${encodeURIComponent(t.tool_id)}&tab=access`, columns: [
          { key: "name", label: "App", lead: true, render: (t) => el("span", { class: "ws-tool" }, A.toolLogo(t.tool_id, t.name, "xs"), el("span", null, t.name)) },
          { key: "signin", label: "How they sign in", render: (t) => SIGNIN_WORD[t.signin] || t.signin },
          { key: "people", label: "People", num: true, render: (t) => el("span", { title: t.names.join(", ") + (t.people > t.names.length ? ` and ${t.people - t.names.length} more` : "") }, t.people.toLocaleString()) },
          { key: "teams", label: "Through a team", sort: (t) => t.teams.length, render: (t) => t.teams.join(", ") || "—" },
        ], pager: { page: 1, size: 10, sizes: [10, 25, 50] } })
        : SUI.stateBox({ compact: true, icon: "tools", title: "Nobody has an app yet", text: "Give someone a tool and it shows here." })));
  }

  /* A single company login, in plain words: who is on it, the limitation, and the fix. No timer, no queue. */
  function limitNotice(a) {
    return el("div", { class: "notice ws-limit" }, icon("users"), el("span", null,
      el("strong", null, `${a.name}: ${many(a.assigned, "person is", "people are")} given one login. `),
      a.limitation.text + " " + a.limitation.recommendation));
  }

  function accountsBlock(acc) {
    const s = acc.summary;
    return el("div", { id: "ws-accounts" }, A.panel("Accounts and subscriptions", seeAll("Licences", "#/licences"), el("div", { class: "body stack" },
      el("p", { class: "hint" }, `${many(s.seats, "tool gives", "tools give")} a seat each · ${many(s.sso, "uses", "use")} company sign-in · ${many(s.single_logins, "is", "are")} one company login.`),
      acc.items.length ? SUI.table({ caption: "Company accounts and subscriptions", rows: acc.items,
        href: (a) => `#/tools?open=${encodeURIComponent(a.tool_id)}&tab=${a.limitation ? "account" : "billing"}`, columns: [
          { key: "name", label: "Tool", lead: true, render: (a) => el("span", { class: "ws-tool" }, A.toolLogo(a.tool_id, a.name, "xs"), el("span", null, a.name)) },
          { key: "signin", label: "How people get in", render: (a) => (a.limitation ? SUI.badge("One company login", "warn", "users") : SIGNIN_WORD[a.signin] || a.signin) },
          { key: "state", label: "Licence", render: (a) => [SUB_WORD[a.state] || a.state, a.plan].filter(Boolean).join(" · ") },
          { key: "assigned", label: "People / seats", num: true, render: (a) => el("span", { class: a.over_seats ? "ws-over" : null },
            a.seats ? `${a.assigned} of ${a.seats}` : String(a.assigned), a.over_seats ? el("span", { class: "u-sr" }, " (more people than seats)") : null) },
        ], pager: { page: 1, size: 10, sizes: [10, 25, 50] } })
        : SUI.stateBox({ compact: true, icon: "licences", title: "No company accounts yet", text: "Add a subscription to a tool and it shows here." }),
      acc.items.filter((a) => a.limitation).map(limitNotice))));
  }

  function activityBlock(act) {
    const recent = act.recent.map((r) => el("li", null, A.toolLogo(r.tool_id, r.tool, "sm"),
      el("div", { class: "grow" }, r.person_id ? A.personLink(r.person_id, r.person, { avatar: false }) : el("span", null, r.person || "Someone"),
        el("span", { class: "muted" }, r.kind === "open" ? (r.outcome === "opened" ? " opened " : " was refused ") : r.outcome === "allowed" ? " visited " : " was blocked from "),
        el("strong", null, r.tool || "a tool")),
      el("span", { class: "hint nowrap", title: fmt.stamp(r.ts) }, r.seconds ? fmt.dur(r.seconds) + " · " + fmt.ago(r.ts) : fmt.ago(r.ts))));
    return A.panel("Activity", seeAll("Activity", "#/activity?tab=timeline"), el("div", { class: "body ws-activity" },
      el("section", { class: "stack" },
        el("h3", { class: "section-title" }, act.label + " · last " + act.days + " days"),
        el("div", { class: "ov-nums" },
          line("Tools opened", act.opens.toLocaleString() + (act.opens_refused ? ` · ${act.opens_refused} refused` : ""), "#/activity?tab=opens&range=7d"),
          line("AI websites visited", act.visits.toLocaleString() + (act.visits_blocked ? ` · ${act.visits_blocked} blocked` : ""), "#/activity?tab=sites&range=7d"),
          line("AI requests through Swangz", act.requests.toLocaleString(), "#/activity?tab=ai&range=7d"),
          line("People seen", act.people.toLocaleString(), "#/activity?tab=usage&range=7d&by=person")),
        recent.length ? el("ul", { class: "mini-list" }, recent) : el("p", { class: "hint" }, "Nothing observed in the last 7 days.")),
      el("section", { class: "stack ws-provider" },
        el("h3", { class: "section-title" }, act.provider.label),
        el("p", { class: "hint" }, act.provider.available ? "" : act.provider.text))));
  }

  function weeklyBlock(w) {
    const range = `${fmt.date(Date.parse(w.week_start + "T12:00:00") / 1000)} to ${fmt.date(Date.parse(w.week_end + "T12:00:00") / 1000)}`;
    return A.panel("Weekly staff reports", seeAll("Weekly reports", "#/weekly"), el("div", { class: "body stack" },
      el("p", { class: "hint" }, "Last week, " + range + "."),
      el("div", { class: "ov-nums" },
        line("Submitted", w.submitted.toLocaleString(), `#/weekly?week=${encodeURIComponent(w.week_start)}`),
        line("Missing", w.missing.toLocaleString(), `#/weekly?week=${encodeURIComponent(w.week_start)}`)),
      w.outstanding_all > w.missing ? el("p", { class: "hint" }, `${many(w.outstanding_all, "report is", "reports are")} still open across all weeks.`) : null));
  }

  /* Simple: the six answers as one list of plain lines, each opening its page. */
  function sixLines(data) {
    const e = data.employees, s = data.devices.summary, acc = data.accounts.summary, act = data.activity, w = data.weekly;
    return A.panel("Your workstations at a glance", null, el("div", { class: "ov-nums" },
      line("People", `${e.active.toLocaleString()} in ${many(e.departments.length, "department", "departments")}`, "#/people"),
      line("Computers", `${s.online.toLocaleString()} online · ${s.offline.toLocaleString()} offline`, "#/workstations?focus=devices"),
      line("Apps given", many(data.assigned.tools, "app", "apps"), "#/tools"),
      line("One company login", acc.single_logins ? many(acc.single_logins, "tool", "tools") : "None", acc.single_logins ? "#/workstations?view=detailed&focus=accounts" : "#/licences"),
      line("Observed in Swangz", `${(act.opens + act.visits).toLocaleString()} opens and visits this week`, "#/activity"),
      line("Weekly reports", `${w.submitted.toLocaleString()} in · ${w.missing.toLocaleString()} missing`, "#/weekly")));
  }

  function limitsPanel(acc) {
    const shared = acc.items.filter((a) => a.limitation);
    if (!shared.length) return null;
    return A.panel("Account limitations", seeAll("All accounts", "#/workstations?view=detailed&focus=accounts"), el("ul", { class: "ws-limits" },
      shared.slice(0, 5).map((a) => el("li", null, el("a", { href: `#/tools?open=${encodeURIComponent(a.tool_id)}&tab=account` }, a.name),
        el("span", null, ` · ${many(a.assigned, "person", "people")} on one login. `), el("span", { class: "hint" }, a.limitation.recommendation)))));
  }

  // ------------------------------------------------------------------ the page

  async function pageWorkstations(params) {
    await A.toolIndex().catch(() => null);
    const mode = A.viewMode("workstations", "#/workstations", params);
    let data = null, failed = null;
    try { data = await api("GET", "/workstations"); } catch (e) { if (e.status === 401) throw e; failed = e; }
    const s = data ? data.devices.summary : {};
    const lead = workstationsLead(data ? { loaded: true, people: data.employees.active, connected: s.connected, online: s.online, offline: s.offline,
      withoutDevice: data.employees.without_device, singleLogins: data.accounts.summary.single_logins, missing: data.weekly.missing } : { loaded: false });
    const content = !data ? [SUI.errorBox(failed, () => A.render(), "The workstations could not load")]
      : mode.simple ? [el("div", { class: "ws-simple" }, el("div", { class: "ws-main" }, devicesBlock(data.devices, false, data.online_minutes)),
        el("div", { class: "ws-side" }, sixLines(data), limitsPanel(data.accounts)))]
        : [el("div", { class: "ws-grid" }, employeesBlock(data.employees), weeklyBlock(data.weekly)),
          devicesBlock(data.devices, true, data.online_minutes),
          el("div", { class: "ws-grid" }, assignedBlock(data.assigned), accountsBlock(data.accounts)),
          activityBlock(data.activity)];
    A.frame({ title: "Workstations", trail: [["Workstations"]], sentence: mode.simple ? lead.sentence : null,
      next: mode.simple ? A.leadButton(lead.action) : el("span", null, lead.sentence + " ", A.leadButton(lead.action, true)),
      actions: [mode.switcher], lede: mode.simple ? null : "Every person's Swangz app, the apps they have, and how they sign in. Everyone works at the same time, each with their own access." },
    content);
    const focus = params.get("focus");
    if (focus && ["devices", "accounts"].includes(focus)) setTimeout(() => document.getElementById("ws-" + focus)?.scrollIntoView({ block: "start" }), 60);
  }

  A.workstationsLead = workstationsLead;
  A.page(/^#\/workstations$/, pageWorkstations);
})();
