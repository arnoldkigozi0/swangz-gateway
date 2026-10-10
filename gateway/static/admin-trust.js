"use strict";
/* Swangz AI Hub — Trust: incidents (a signal turned into a tracked case with an owner, evidence, notes and
   an ending) and Health (is the gateway itself well: providers, latency, errors, housekeeping). */
(() => {
  const A = window.SWA;
  const { el, icon, fmt, toast } = SUI;
  const { api } = A;

  const SEVERITY = { critical: ["blocked", "Critical"], high: ["blocked", "High"], medium: ["waiting", "Medium"], low: ["info", "Low"] };
  const STATE = { open: ["waiting", "Open"], investigating: ["info", "Investigating"], contained: ["ok", "Contained"], resolved: ["idle", "Resolved"], dismissed: ["idle", "Dismissed"] };
  const LINK_ICON = { person: "user", device: "device", request: "spark", tool: "tools", session: "layers", event: "shield" };

  // ------------------------------------------------------------------ Incidents

  async function pageIncidents(params) {
    const which = ["active", "closed", "all"].includes(params.get("status")) ? params.get("status") : "active";
    const data = await api("GET", "/incidents?status=" + which);
    const c = data.counts || {};
    const active = (c.open || 0) + (c.investigating || 0) + (c.contained || 0);
    const closed = (c.resolved || 0) + (c.dismissed || 0);
    const tabs = el("nav", { class: "sec-chips", "aria-label": "Filter" }, [["active", "Active", active], ["closed", "Closed", closed], ["all", "All", active + closed]].map(([k, t, n]) =>
      el("a", { class: "sec-chip" + (which === k ? " on" : ""), href: "#/incidents?status=" + k, "aria-current": which === k ? "true" : null }, el("span", null, t), el("span", { class: "n u-num" }, String(n)))));
    const table = data.items.length ? SUI.table({ caption: "Incidents", rows: data.items, sort: ["updated", "desc"], href: (i) => "#/incidents/" + i.id, columns: [
      { key: "title", label: "Incident", lead: true, render: (i) => el("div", null, el("strong", null, i.title), el("span", { class: "sub" }, `#${i.id} · opened by ${i.created_by} ${fmt.ago(i.created)}`)) },
      { key: "severity", label: "Severity", sort: (i) => ["low", "medium", "high", "critical"].indexOf(i.severity), render: (i) => SUI.status(...SEVERITY[i.severity], { plain: true }) },
      { key: "status", label: "State", render: (i) => SUI.status(...STATE[i.status], { plain: true }) },
      { key: "owner", label: "Owner", render: (i) => i.owner || "—", hideSm: true },
      { key: "links", label: "Evidence", num: true, hideSm: true },
      { key: "updated", label: "Last change", num: true, render: (i) => fmt.ago(i.updated) }] })
      : SUI.stateBox({ tone: which === "active" ? "ok" : null, icon: "flag", title: which === "active" ? "No open incidents" : "None here",
        text: which === "active" ? "Open one from a security signal, or by hand when something needs following through." : "Nothing in this list." });
    A.frame({ title: "Incidents", lede: "When a signal needs following through: one place for who owns it, the evidence, what was done, and how it ended. Everything here is in the audit log too.",
      actions: A.can("trust") ? el("button", { class: "btn primary", onclick: () => openIncident({}) }, icon("plus"), "Open an incident") : null },
    [tabs, A.panel(null, null, table)]);
    if (params.get("add") && A.can("trust")) {
      openIncident({ title: params.get("title") || "", source: params.get("source") || "", person: params.get("person"), request: params.get("request") });
    }
  }

  /* Opening an incident, optionally from a signal: the person and request come with it as evidence. */
  function openIncident(o) {
    const title = el("input", { type: "text", maxlength: "200", value: o.title || "", placeholder: "e.g. Key shared in a public repository" });
    const sev = el("select", null, ["low", "medium", "high", "critical"].map((s) => el("option", { value: s }, SEVERITY[s][1])));
    sev.value = o.severity || "medium";
    const summary = el("textarea", { rows: "4", maxlength: "4000", placeholder: "What happened, as far as is known. Facts and guesses kept apart." });
    const owner = el("input", { type: "text", maxlength: "80", value: A.S.me.username });
    const err = el("div", { class: "err", role: "alert" });
    const links = [];
    if (o.person) links.push({ kind: "person", ref: String(o.person) });
    if (o.request) links.push({ kind: "request", ref: String(o.request) });
    const save = el("button", { class: "btn primary", onclick: async () => {
      try {
        const out = await api("POST", "/incidents", { title: title.value, severity: sev.value, summary: summary.value, owner: owner.value, source: o.source || "", links });
        d.close();
        location.hash = "#/incidents/" + out.id;
      } catch (e) { err.textContent = e.message; }
    } }, "Open incident");
    const d = A.dialog("Open an incident", el("div", { class: "stack" },
      el("label", { class: "field" }, "Title", title),
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Severity", sev), el("label", { class: "field" }, "Owner", owner)),
      el("label", { class: "field" }, "Summary", summary),
      links.length ? el("p", { class: "hint" }, `Linked as evidence: ${links.map((l) => l.kind + " " + l.ref).join(", ")}.`) : null, err), [save]);
    title.focus();
  }

  async function pageIncident(params, id) {
    const i = await api("GET", "/incidents/" + id);
    const edit = A.can("trust");
    const closed = ["resolved", "dismissed"].includes(i.status);
    const moves = edit ? i.next.map((s) => el("button", { class: "btn" + (s === "resolved" ? " primary" : s === "dismissed" ? " quiet" : ""), onclick: () => move(i, s) },
      { investigating: "Start investigating", contained: "Mark contained", resolved: "Resolve", dismissed: "Dismiss", open: "Reopen" }[s])) : null;
    const facts = el("div", { class: "evidence-grid" },
      [["Severity", SUI.status(...SEVERITY[i.severity])], ["State", SUI.status(...STATE[i.status])], ["Owner", i.owner || "—"],
        ["Opened", `${fmt.stamp(i.created)} by ${i.created_by}`], ["Source", i.source || "By hand"],
        closed ? ["Closed", `${fmt.stamp(i.closed)} by ${i.closed_by}`] : ["Last change", fmt.ago(i.updated)]]
        .map(([k, v]) => el("div", null, el("div", { class: "k" }, k), el("div", { class: "v" }, v))));
    const linkHref = (l) => ({ person: "#/people/" + l.ref, device: "#/devices/" + l.ref, request: "#/records/" + l.ref, tool: "#/tools?open=" + l.ref, session: "#/sessions/" + l.ref }[l.kind] || null);
    const evidence = i.links_list.length ? el("ul", { class: "mini-list" }, i.links_list.map((l) => el("li", null, icon(LINK_ICON[l.kind] || "link"),
      el("div", { class: "grow" }, linkHref(l) ? el("a", { href: linkHref(l) }, l.label) : el("span", null, l.label), el("div", { class: "hint" }, `${l.kind} · added by ${l.added_by} ${fmt.ago(l.added)}`)),
      edit ? el("button", { class: "btn small quiet", onclick: async () => {
        try { await api("DELETE", `/incidents/${i.id}/links/${l.id}`); A.render(); } catch (e) { toast(e.message, true); }
      } }, "Unlink") : null))) : A.empty("Nothing linked yet. Link the people, devices and requests this is about.", null, "link");
    const kind = el("select", { "aria-label": "Kind" }, ["person", "device", "request", "tool", "session"].map((k) => el("option", { value: k }, k)));
    const ref = el("input", { type: "text", placeholder: "Person id, device id, request number…", "aria-label": "Reference" });
    const linkErr = el("span", { class: "err", role: "alert" });
    const addLink = edit ? A.panelFoot(el("span", { class: "grow" }, linkErr), kind, ref, el("button", { class: "btn", onclick: async () => {
      try { await api("POST", `/incidents/${i.id}/links`, { kind: kind.value, ref: ref.value.trim().replace(/^#/, "") }); A.render(); } catch (e) { linkErr.textContent = e.message; }
    } }, icon("plus"), "Link")) : null;
    const note = el("textarea", { rows: "3", maxlength: "4000", placeholder: "What you found or did. Notes can't be edited later." });
    const noteErr = el("span", { class: "err", role: "alert" });
    const notes = el("ol", { class: "incident-notes" }, i.notes_list.map((n) => el("li", { class: n.kind },
      el("div", { class: "meta" }, `${n.author} · ${fmt.stamp(n.ts)}`), el("div", null, n.text))));
    const addNote = edit ? A.panelFoot(el("span", { class: "grow" }, noteErr), el("button", { class: "btn primary", onclick: async () => {
      try { await api("POST", `/incidents/${i.id}/notes`, { text: note.value }); A.render(); } catch (e) { noteErr.textContent = e.message; }
    } }, "Add note")) : null;
    A.frame({ title: i.title, crumbs: [el("a", { href: "#/incidents" }, "Incidents"), "#" + i.id], status: SUI.status(...STATE[i.status], { plain: true }), actions: moves }, [
      facts,
      i.summary ? A.panel("Summary", null, el("div", { class: "body" }, el("p", { class: "pre-wrap" }, i.summary))) : null,
      i.resolution ? A.panel("How it ended", null, el("div", { class: "body" }, el("p", { class: "pre-wrap" }, i.resolution))) : null,
      A.panel("Evidence", SUI.plural(i.links_list.length, "link"), el("div", { class: "body" }, evidence), addLink),
      A.panel("Notes", "in order; nothing here can be edited", el("div", { class: "body stack" }, notes, edit ? note : null), addNote),
      A.panel("Audit trail", null, el("ul", { class: "mini-list" }, i.trail.map((t) => el("li", null,
        el("time", { class: "hint nowrap", title: fmt.stamp(t.ts) }, fmt.when(t.ts)), el("div", { class: "grow" }, el("strong", null, t.actor), " " + t.action), el("span", { class: "hint" }, t.detail || ""))))),
    ]);
  }

  async function move(i, status) {
    let body = { status };
    if (status === "resolved" || status === "dismissed") {
      const text = el("textarea", { rows: "4", maxlength: "4000", placeholder: status === "resolved" ? "What was done, and why it is over." : "Why it needs no action." });
      text.value = i.resolution || "";
      const err = el("div", { class: "err", role: "alert" });
      const ok = await new Promise((resolve) => {
        const go = el("button", { class: "btn primary", onclick: () => { if (!text.value.trim()) { err.textContent = "Say how it ended."; return; } done = true; d.close(); } }, status === "resolved" ? "Resolve" : "Dismiss");
        let done = false;
        const d = A.dialog(status === "resolved" ? "Resolve the incident" : "Dismiss the incident", el("div", { class: "stack" }, el("label", { class: "field" }, "How it ended", text), err), [go]);
        d.addEventListener("close", () => resolve(done));
      });
      if (!ok) return;
      body = { status, resolution: text.value.trim() };
    }
    try { await api("PATCH", "/incidents/" + i.id, body); toast("Updated."); A.render(); } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ Health

  async function pageHealth() {
    const h = await api("GET", "/health");
    const hours = (s) => (s < 3600 ? Math.round(s / 60) + " min" : s < 86400 ? (s / 3600).toFixed(1) + " h" : (s / 86400).toFixed(1) + " days");
    const statline = el("div", { class: "kpis" },
      A.kpi({ label: "Gateway", value: h.ok ? "Running" : "Database error", tone: h.ok ? null : "bad", foot: "up " + hours(h.uptime_seconds) }),
      A.kpi({ label: "In flight", value: String(h.live), href: "#/live" }),
      A.kpi({ label: "Database", value: (h.db_bytes / 1048576).toFixed(1) + " MB", foot: `schema v${h.schema} · ${fmt.num(h.requests_logged)} records` }),
      A.kpi({ label: "Housekeeping", value: h.maintenance_last ? fmt.ago(h.maintenance_last) : "Not yet", foot: "retention and notifications, hourly" }));
    const providers = SUI.table({ caption: "Providers, last hour", rows: h.providers, sort: ["name", "asc"], columns: [
      { key: "label", label: "Provider", lead: true, render: (p) => el("strong", null, p.label || p.name) },
      { key: "state", label: "State", render: (p) => (p.switched_off ? SUI.status("blocked", "Switched off", { plain: true }) : !p.configured ? SUI.status("none", "No key", { plain: true })
        : p.last_hour.error_rate >= 0.25 && p.last_hour.requests >= 5 ? SUI.status("blocked", "Failing", { plain: true }) : SUI.status("ok", "Working", { plain: true })) },
      { key: "requests", label: "Requests", num: true, sort: (p) => p.last_hour.requests, render: (p) => fmt.num(p.last_hour.requests) },
      { key: "errors", label: "Failed", num: true, sort: (p) => p.last_hour.errors, render: (p) => (p.last_hour.errors ? `${p.last_hour.errors} (${Math.round(p.last_hour.error_rate * 100)}%)` : "0") },
      { key: "p50", label: "Typical time", num: true, sort: (p) => p.last_hour.p50_ms || 0, render: (p) => fmt.ms(p.last_hour.p50_ms) },
      { key: "p95", label: "Slowest 5%", num: true, sort: (p) => p.last_hour.p95_ms || 0, render: (p) => fmt.ms(p.last_hour.p95_ms), hideSm: true },
      { key: "ttft", label: "First word", num: true, sort: (p) => p.last_hour.ttft_p50_ms || 0, render: (p) => fmt.ms(p.last_hour.ttft_p50_ms), hideSm: true }] });
    const geo = h.location_table || {};
    const facts = el("div", { class: "evidence-grid" },
      [["Kill switch", h.paused ? SUI.status("blocked", "AI paused") : SUI.status("ok", "Ready"), "Settings → Access & records"],
        ["Company browsers", h.workspace_paused ? SUI.status("waiting", "Paused") : SUI.status("ok", "On"), "Settings → Emergency"],
        ["Policies", `${h.policies_enabled} on`, "Govern → Policies"], ["Models registered", String(h.models_registered), "Govern → Models"],
        ["Open notifications", String(h.notifications_open), "the bell"],
        ["Location table", geo.rows ? `${fmt.num(geo.rows)} ranges` : "Not loaded", geo.rows ? `${geo.source}, imported ${fmt.date(geo.imported)}` : "places show as address types only"],
        ["Rate limit", h.rate_per_min ? `${h.rate_per_min} a minute` : "Off", "per person"], ["Version", h.version, ""]]
        .map(([k, v, how]) => el("div", null, el("div", { class: "k" }, k), el("div", { class: "v" }, v), how ? el("div", { class: "how" }, how) : null)));
    A.frame({ title: "Health", lede: "Is the gateway itself well? Times are measured at the gateway, so they include the network to each provider." }, [
      statline, A.panel("Providers", "the last hour", providers), A.panel("Switches and housekeeping", null, el("div", { class: "body" }, facts))]);
  }

  A.page(/^#\/incidents$/, pageIncidents);
  A.page(/^#\/incidents\/(\d+)$/, pageIncident);
  A.page(/^#\/health$/, pageHealth);
  Object.assign(A, { openIncident });
})();
