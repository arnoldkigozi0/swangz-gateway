"use strict";
/* Swangz AI Hub — Govern: the model registry and company policies, with the two read-only tools that make
   rules safe to change: the simulator (what a draft would have refused over recent history) and explain
   (why one person may or may not use one thing right now, check by check). The server decides every
   one of these; this page only asks it and shows the answer with its reasons. */
(() => {
  const A = window.SWA;
  const { el, icon, fmt, toast } = SUI;
  const { api, S } = A;

  const STATUS = { approved: ["ok", "Approved"], experimental: ["info", "Experimental"], restricted: ["waiting", "Restricted"],
    deprecated: ["idle", "Deprecated"], disabled: ["blocked", "Disabled"], unlisted: ["none", "Unlisted"] };
  const CLASS = { public: "Public", internal: "Internal", confidential: "Confidential", restricted: "Restricted" };
  const EFFECT = { deny: ["Refuse", "stop"], hours: ["Permitted hours", "clock"], cap: ["Monthly cap", "wallet"] };
  const CHANNEL = { request: "Requests through the gateway", launch: "Opening from Swangz AI Hub", site: "Website visits" };
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function countTabs(base, counts, current, order, labels) {
    return el("nav", { class: "sec-chips", "aria-label": "Filter" }, order.filter((k) => k === "" || counts[k]).map((k) =>
      el("a", { class: "sec-chip" + (current === k ? " on" : ""), href: base + (k ? (base.includes("?") ? "&" : "?") + "status=" + k : ""), "aria-current": current === k ? "true" : null },
        el("span", null, labels[k]), el("span", { class: "n u-num" }, String(k ? counts[k] || 0 : Object.values(counts).reduce((a, n) => a + n, 0))))));
  }

  // ------------------------------------------------------------------ Models

  async function pageModels(params) {
    const data = await api("GET", "/models");
    const status = params.get("status") || "";
    const counts = {};
    data.items.forEach((m) => { counts[m.status] = (counts[m.status] || 0) + 1; });
    const rows = data.items.filter((m) => !status || m.status === status);
    const edit = A.can("govern");
    const table = rows.length ? SUI.table({ caption: "Models", rows, sort: ["requests", "desc"], columns: [
      { key: "id", label: "Model", lead: true, render: (m) => el("div", { class: "model-cell" }, el("span", { class: "mono strong nowrap" }, m.id),
        el("span", { class: "sub" }, [m.provider, m.label || (m.governed_by ? "by the rule for " + m.governed_by : "")].filter(Boolean).join(" · "))) },
      { key: "status", label: "Status", render: (m) => el("div", null, SUI.status(...(STATUS[m.status] || STATUS.unlisted), { plain: true }),
        m.status === "restricted" && m.allowed_departments.length ? el("span", { class: "sub" }, "Only " + m.allowed_departments.join(", ")) : null) },
      { key: "classification", label: "Data class", render: (m) => (m.classification ? CLASS[m.classification] : el("span", { class: "faint" }, "—")), hideSm: true },
      { key: "requests", label: "Requests · 30 d", num: true, render: (m) => fmt.num(m.requests) },

      { key: "cost", label: "Est. cost", num: true, render: (m) => el("span", { class: "row end nowrap" }, fmt.money(m.cost),
        m.unpriced ? el("span", { class: "basis unpriced", "data-tip": `${m.unpriced} request(s) with no price${m.priced ? " when they ran" : " — add one in Settings → Model prices"}`, tabindex: "0" }, `${fmt.num(m.unpriced)} unpriced`) : null) },
      { key: "refused", label: "Refused", num: true, render: (m) => (m.refused ? el("span", { class: "neg" }, fmt.num(m.refused)) : "0"), hideSm: true },
      { key: "last", label: "Last used", num: true, render: (m) => el("span", { class: "nowrap", title: m.people ? SUI.plural(m.people, "person", "people") + " in 30 days" : null }, fmt.ago(m.last)), hideSm: true },
      edit ? { key: "act", label: "", sort: false, srLabel: "Edit", cls: "act", render: (m) => el("button", { class: "btn small quiet", onclick: () => editModel(m, data) }, m.registered ? "Edit" : "Rules") } : null,
    ].filter(Boolean) }) : SUI.stateBox({ icon: "chip", title: "No models here", text: status ? "None with this status." : "Models appear once they are used through the gateway, priced, or registered." });
    A.frame({ title: "Models", lede: "Every chat model the gateway has seen, priced or registered, and the rule on each. A model nobody registered is unlisted: allowed, as before the registry. A rule for claude-opus-4 also covers claude-opus-4-1 and later versions of it.",
      actions: edit ? el("button", { class: "btn primary", onclick: () => editModel(null, data) }, icon("plus"), "Register a model") : null }, [
      countTabs("#/models", counts, status, ["", "approved", "experimental", "restricted", "deprecated", "disabled", "unlisted"],
        { "": "All", approved: "Approved", experimental: "Experimental", restricted: "Restricted", deprecated: "Deprecated", disabled: "Disabled", unlisted: "Unlisted" }),
      A.panel(null, null, table,
        el("div", { class: "body hint" }, "Disabled: refused for everyone. Restricted: only the departments named. Experimental and deprecated are allowed and marked. Costs are estimated from the price table."))]);
  }

  function editModel(m, data) {
    const id = el("input", { type: "text", value: m ? m.id : "", disabled: !!m, placeholder: "e.g. claude-opus-4 or gpt-5", "aria-label": "Model id" });
    const label = el("input", { type: "text", value: m ? m.label : "", maxlength: "80", placeholder: "Optional, e.g. Opus 4 (top tier)" });
    const status = el("select", null, data.statuses.map((x) => el("option", { value: x }, STATUS[x][1])));
    status.value = m && m.registered ? m.status : "approved";
    const cls = el("select", null, data.classifications.map((x) => el("option", { value: x }, CLASS[x])));
    cls.value = (m && m.classification) || "internal";
    const chosen = new Set(m ? m.allowed_departments : []);
    const depts = el("div", { class: "chk-grid" }, data.departments.length ? data.departments.map((d) => {
      const box = el("input", { type: "checkbox", checked: chosen.has(d), value: d });
      return el("label", null, box, d);
    }) : el("span", { class: "hint" }, "No departments yet — set them on people first."));
    const deptRow = el("label", { class: "field" }, "Departments that may use it", depts);
    const note = el("input", { type: "text", value: m ? m.note : "", maxlength: "300", placeholder: "Why — shown to other admins" });
    const err = el("div", { class: "err", role: "alert" });
    const sync = () => { deptRow.hidden = status.value !== "restricted"; };
    status.addEventListener("change", sync);
    sync();
    const save = el("button", { class: "btn primary", onclick: async () => {
      const mid = (m ? m.id : id.value).trim();
      if (!mid) { err.textContent = "Give the model id."; return; }
      try {
        await api("PUT", "/models/" + encodeURIComponent(mid), { label: label.value, status: status.value, classification: cls.value, note: note.value,
          provider: m ? m.provider : "", allowed_departments: [...depts.querySelectorAll("input:checked")].map((b) => b.value) });
        d.close();
        toast("Saved. It applies from the next request.");
        A.render();
      } catch (e) { err.textContent = e.message; }
    } }, "Save");
    const remove = m && m.registered ? el("button", { class: "btn danger", onclick: async () => {
      try { await api("DELETE", "/models/" + encodeURIComponent(m.id)); d.close(); toast("Removed from the registry: unlisted, so allowed."); A.render(); } catch (e) { err.textContent = e.message; }
    } }, "Remove") : null;
    const d = A.dialog(m ? "Rules for " + m.id : "Register a model", el("div", { class: "stack" },
      m ? null : el("label", { class: "field" }, "Model id", id, el("span", { class: "hint" }, "The id or the start of it: a rule for claude-opus-4 covers claude-opus-4-1-20250805 too.")),
      el("label", { class: "field" }, "Name", label),
      el("div", { class: "form-grid" }, el("label", { class: "field" }, "Status", status), el("label", { class: "field" }, "Data class", cls)),
      deptRow, el("label", { class: "field" }, "Note", note), err), [remove, save]);
  }

  // ------------------------------------------------------------------ Policies

  async function pagePolicies(params) {
    const [data, people, settings] = await Promise.all([api("GET", "/policies"), A.people(), api("GET", "/settings"), A.toolIndex().catch(() => null)]);
    const ctx = { data, people, providers: settings.providers || [] };
    A.frame({ title: "Policies", lede: "Company rules, decided by the gateway the same way every time. A policy only takes access away — refusing, limiting hours, or capping a month's spend — and every refusal names the rule. Try a change on the Simulate tab before you make it.",
      actions: A.can("govern") ? el("button", { class: "btn primary", onclick: () => policySheet(null, ctx) }, icon("plus"), "Add a policy") : null },
    A.pageTabs("#/policies", params, [
      ["list", "Policies", () => policyList(ctx), data.items.length || null],
      ["simulate", "Simulate", () => simulateTab(ctx)],
      ["explain", "Explain a decision", () => explainTab(ctx, params)],
    ]));
    if (params.get("add") && A.can("govern")) policySheet(null, ctx);
  }

  function policyList(ctx) {
    const items = ctx.data.items;
    const edit = A.can("govern");
    if (!items.length) {
      return A.panel(null, null, SUI.stateBox({ icon: "rule", title: "No policies yet",
        text: "With no policies, access works exactly as assigned: entitlements, budgets and model rules. Add one to refuse something, limit it to working hours, or cap a team's monthly spend.",
        action: edit ? el("button", { class: "btn primary", onclick: () => policySheet(null, ctx) }, icon("plus"), "Add a policy") : null }));
    }
    return A.panel(null, null, SUI.table({ caption: "Policies", rows: items, sort: ["name", "asc"], columns: [
      { key: "name", label: "Policy", lead: true, render: (p) => el("div", null, el("strong", null, p.name), el("div", { class: "policy-sum" }, p.summary)) },
      { key: "effect", label: "Effect", render: (p) => SUI.badge(EFFECT[p.effect][0], p.effect === "deny" ? "bad" : "info", EFFECT[p.effect][1]) },
      { key: "enabled", label: "On", render: (p) => {
        const sw = A.switchInput(p.enabled, !edit, (p.enabled ? "Switch off " : "Switch on ") + p.name);
        sw.addEventListener("change", async () => {
          try { await api("PATCH", "/policies/" + p.id, { enabled: sw.checked }); toast(sw.checked ? "On — it applies from now." : "Off."); p.enabled = sw.checked ? 1 : 0; }
          catch (e) { sw.checked = !sw.checked; toast(e.message, true); }
        });
        return sw;
      } },
      { key: "refused_30d", label: "Refused · 30 d", num: true, render: (p) => fmt.num(p.refused_30d) },
      { key: "updated", label: "Changed", num: true, render: (p) => el("span", { title: fmt.stamp(p.updated) }, fmt.ago(p.updated), el("span", { class: "sub" }, p.updated_by)), hideSm: true },
      edit ? { key: "act", label: "", sort: false, srLabel: "Edit", cls: "act", render: (p) => el("button", { class: "btn small quiet", onclick: () => policySheet(p, ctx) }, "Edit") } : null,
    ].filter(Boolean) }));
  }

  /* The policy form, shared by the editor and the simulator. -> { node, value() } */
  function policyForm(p, ctx) {
    p = p || { effect: "deny", subjects: { everyone: true }, scope: {}, params: {} };
    const f = {};
    f.name = el("input", { type: "text", maxlength: "120", value: p.name || "", placeholder: "e.g. No video tools outside working hours" });
    let effect = p.effect;
    const effectSeg = A.seg(Object.entries(EFFECT).map(([k, [t]]) => [k, t]), effect, (v) => { effect = v; sync(); }, "Effect");
    // who
    const s = p.subjects || {};
    let who = s.everyone ? "everyone" : (s.departments || []).length ? "departments" : "people";
    const whoSeg = A.seg([["everyone", "Everyone"], ["departments", "Departments"], ["people", "People"]], who, (v) => { who = v; sync(); }, "Who");
    const depts = el("div", { class: "chk-grid" }, ctx.data.departments.map((d) => el("label", null, el("input", { type: "checkbox", value: d, checked: (s.departments || []).includes(d) }), d)));
    const ppl = el("select", { multiple: true, size: "6", "aria-label": "People" }, ctx.people.map((x) => el("option", { value: String(x.id), selected: (s.people || []).includes(x.id) }, x.name)));
    // what
    const sc = p.scope || {};
    const tools = Object.values(S.tools || {}).filter((t) => !t.archived).sort((a, b) => a.name.localeCompare(b.name));
    const toolSel = el("select", { multiple: true, size: "6", "aria-label": "Tools" }, tools.map((t) => el("option", { value: t.id, selected: (sc.tools || []).includes(t.id) }, t.name)));
    f.models = el("input", { type: "text", value: (sc.models || []).join(", "), placeholder: "e.g. claude-opus-*, gpt-5*" });
    const provs = el("div", { class: "chk-grid" }, ctx.providers.map((x) => el("label", null, el("input", { type: "checkbox", value: x.name, checked: (sc.providers || []).includes(x.name) }), x.label || x.name)));
    const classes = el("div", { class: "chk-grid" }, Object.entries(CLASS).map(([k, t]) => el("label", null, el("input", { type: "checkbox", value: k, checked: (sc.classifications || []).includes(k) }), t)));
    const chans = el("div", { class: "chk-grid" }, Object.entries(CHANNEL).map(([k, t]) => el("label", null, el("input", { type: "checkbox", value: k, checked: (sc.channels || []).includes(k) }), t)));
    // effect parameters
    const pr = p.params || {};
    const days = el("div", { class: "chk-grid" }, DAYS.map((d, i) => el("label", null, el("input", { type: "checkbox", value: String(i), checked: (pr.days || [0, 1, 2, 3, 4]).includes(i) }), d)));
    f.start = el("input", { type: "time", value: pr.start || "08:00", "aria-label": "From" });
    f.end = el("input", { type: "time", value: pr.end || "19:00", "aria-label": "Until" });
    f.limit = el("input", { type: "number", min: "0", step: "1", value: pr.limit_usd != null ? String(pr.limit_usd) : "", placeholder: "e.g. 200", "aria-label": "Monthly limit in dollars" });
    f.message = el("input", { type: "text", maxlength: "200", value: pr.message || "", placeholder: "Optional: what the person is told, e.g. Ask Arnold for an exception." });
    f.note = el("input", { type: "text", maxlength: "500", value: p.note || "", placeholder: "Why this rule exists — for other admins" });
    const rows = {
      depts: el("label", { class: "field" }, "Departments", depts),
      people: el("label", { class: "field" }, "People (Ctrl or ⌘ to pick several)", ppl),
      hours: el("div", { class: "stack" }, el("label", { class: "field" }, "Allowed on", days),
        el("div", { class: "form-grid" }, el("label", { class: "field" }, "From (gateway time)", f.start), el("label", { class: "field" }, "Until", f.end))),
      cap: el("label", { class: "field" }, "Monthly limit (US dollars, estimated spend)", f.limit,
        el("span", { class: "hint" }, "Counts the subjects' estimated spend this month on what the policy covers. Only requests through the gateway cost metered money, so a cap governs those.")),
      chans: el("label", { class: "field" }, "Where it applies (none ticked = everywhere)", chans),
    };
    // called after every change of effect or of who; the groups and the read-back below exist by then
    function sync() {
      rows.depts.hidden = who !== "departments";
      rows.people.hidden = who !== "people";
      rows.hours.hidden = effect !== "hours";
      rows.cap.hidden = effect !== "cap";
      rows.chans.hidden = effect === "cap";
      limits.hidden = effect === "deny";
      readBack();
    }
    const picked = (box) => [...box.querySelectorAll("input:checked")].map((b) => b.value);
    const value = () => ({
      name: f.name.value, effect, note: f.note.value,
      subjects: { everyone: who === "everyone", departments: who === "departments" ? picked(depts) : [],
        people: who === "people" ? [...ppl.selectedOptions].map((o) => Number(o.value)) : [] },
      scope: { tools: [...toolSel.selectedOptions].map((o) => o.value), models: f.models.value.split(",").map((x) => x.trim()).filter(Boolean),
        providers: picked(provs), classifications: picked(classes), channels: effect === "cap" ? ["request"] : picked(chans) },
      params: { days: picked(days).map(Number), start: f.start.value, end: f.end.value, limit_usd: f.limit.value === "" ? null : Number(f.limit.value), message: f.message.value },
    });
    // In order: what it is and does, who, what, the effect's own limits, what people are told, then a sentence that
    // reads the whole rule back before it's saved. Fields for one effect only appear when that effect is picked.
    const EFFECT_SAYS = { deny: "Refuses what it covers, for the people it names.", hours: "Allows what it covers only on the days and hours below; refuses it outside them.",
      cap: "Refuses requests once the people it names have spent the limit below this month." };
    const effectSays = el("span", { class: "hint" });
    const review = el("p", { class: "pf-review", role: "status", "aria-live": "polite" });
    // numbered by CSS, so a group hidden for this effect leaves no gap in the numbers
    const group = (n, title, hint, ...kids) => el("fieldset", { class: "pf-group" },
      el("legend", null, el("span", { class: "pf-n", "aria-hidden": "true" }), title), hint ? el("p", { class: "hint pf-hint" }, hint) : null, ...kids);
    const limits = group(4, "Days, hours and spend", null, rows.hours, rows.cap);
    const list = (xs, none) => (xs.length ? xs.join(", ") : none);
    function readBack() {
      const v = value();
      const subj = v.subjects.everyone ? "everyone" : v.subjects.departments.length ? "the " + list(v.subjects.departments) + " department" + (v.subjects.departments.length > 1 ? "s" : "")
        : v.subjects.people.length ? SUI.plural(v.subjects.people.length, "named person", "named people") : "nobody yet (pick who)";
      const toolNames = v.scope.tools.map((id) => (S.tools && S.tools[id] ? S.tools[id].name : id));
      const what = [toolNames.length ? list(toolNames) : null, v.scope.models.length ? "models " + list(v.scope.models) : null,
        v.scope.providers.length ? "services " + list(v.scope.providers) : null, v.scope.classifications.length ? list(v.scope.classifications.map((c) => CLASS[c].toLowerCase())) + " tools" : null]
        .filter(Boolean).join("; ") || "every tool and model";
      const where = effect === "cap" ? "requests through the gateway" : v.scope.channels.length ? list(v.scope.channels.map((c) => CHANNEL[c].toLowerCase())) : "everywhere";
      const days = v.params.days.map((d) => DAYS[d]).join(", ");
      const how = effect === "deny" ? "Refuses" : effect === "hours" ? `Allows only on ${days || "no days"}, ${v.params.start}–${v.params.end} (gateway time),`
        : `Stops after ${v.params.limit_usd != null ? fmt.money(v.params.limit_usd) : "a limit not yet set"} of estimated spend this month on`;
      review.textContent = `${how} ${what}, for ${subj} — ${where}.` + (v.params.message ? ` They are told: “${v.params.message}”` : " They see the standard refusal message.");
      effectSays.textContent = EFFECT_SAYS[effect] || "";
    }
    const node = el("div", { class: "pf" },
      group(1, "Basics", null,
        el("label", { class: "field" }, "Name", f.name),
        el("div", { class: "field", role: "group", "aria-label": "What it does" }, "What it does", effectSeg, effectSays)),
      group(2, "Who it is about", null, whoSeg, rows.depts, rows.people),
      group(3, "What it covers", "Leave a list empty to mean any.",
        el("label", { class: "field" }, "Tools", toolSel),
        el("label", { class: "field" }, "Models (patterns)", f.models),
        el("div", { class: "form-grid" }, el("label", { class: "field" }, "Services", provs), el("label", { class: "field" }, "Data class of the tool or model", classes)),
        rows.chans),
      limits,
      group(5, "What people are told, and why", null,
        el("label", { class: "field" }, "Message to the person refused", f.message),
        el("label", { class: "field" }, "Reason, for other admins", f.note, el("span", { class: "hint" }, "Kept with the policy and in the audit log; staff don't see it."))),
      group(6, "Review", null, review));
    node.addEventListener("input", readBack);
    node.addEventListener("change", readBack);
    sync();
    return { node, value };
  }

  function policySheet(p, ctx) {
    const { node, close } = A.sheet(null, p ? p.name : "Add a policy");
    const form = policyForm(p, ctx);
    const err = el("div", { class: "err", role: "alert" });
    const preview = el("div", { class: "sim-out" });
    const run = el("button", { class: "btn", onclick: async () => {
      err.textContent = "";
      SUI.load(preview, async () => simResult(await api("POST", "/policies/simulate", { policy: form.value(), replacing: p ? p.id : null })), SUI.skeleton("rows", 3));
    } }, icon("play"), "Preview impact");
    const save = el("button", { class: "btn primary", onclick: async () => {
      try {
        if (p) await api("PUT", "/policies/" + p.id, form.value()); else await api("POST", "/policies", form.value());
        close();
        toast(p ? "Saved. It applies from the next request." : "Added. It applies from the next request.");
        A.render();
      } catch (e) { err.textContent = e.message; }
    } }, p ? "Save" : "Add policy");
    const remove = p ? el("button", { class: "btn danger", onclick: async () => {
      const ok = await A.confirmAction(`Remove ${p.name}?`, "It stops applying at once. Its past refusals keep naming it in their records.", "Remove", true);
      if (!ok) return;
      try { await api("DELETE", "/policies/" + p.id); close(); toast("Removed."); A.render(); } catch (e) { err.textContent = e.message; }
    } }, "Remove") : null;
    node.append(el("header", null, el("div", { class: "spread" },
      el("div", { class: "sheet-id" }, el("div", null, el("div", { class: "u-label" }, "Policy"), el("h2", null, p ? p.name : "Add a policy"))),
      el("button", { class: "btn small quiet icon-only", onclick: close, "aria-label": "Close" }, icon("x")))),
    el("div", { class: "sheet-body" }, form.node, preview),
    el("footer", { class: "panel-foot" }, remove ? Object.assign(remove, { className: "btn danger aside" }) : null, el("span", { class: "grow" }, err), run,
      el("button", { class: "btn quiet", onclick: close }, "Cancel"), save));
  }

  function simResult(r) {
    const total = r.refused.total;
    const head = el("div", { class: "verdict " + (total ? "no" : "yes") }, icon(total ? "stop" : "check"),
      el("div", null, total ? `Over the last ${r.window.days} days this would have refused ${SUI.plural(total, "thing")} for ${SUI.plural(r.people_count, "person", "people")}.`
        : `Over the last ${r.window.days} days this would have refused nothing.`,
      el("div", { class: "hint" }, r.summary || "")));
    const facts = el("div", { class: "evidence-grid" },
      ...[["Requests", r.refused.request, r.checked.request], ["Opens", r.refused.launch, r.checked.launch], ["Website visits", r.refused.site, r.checked.site]]
        .map(([k, n, of]) => el("div", null, el("div", { class: "k" }, k), el("div", { class: "v u-num" }, `${fmt.num(n)} of ${fmt.num(of)}`), el("div", { class: "how" }, "would have been refused"))),
      el("div", null, el("div", { class: "k" }, "Devices"), el("div", { class: "v u-num" }, fmt.num(r.devices)), el("div", { class: "how" }, "keys whose requests it covers")),
      el("div", null, el("div", { class: "k" }, "Spend it covers"), el("div", { class: "v u-num" }, fmt.money(r.spend)),
        el("div", { class: "how" }, el("span", { class: "basis estimated" }, "estimated"), r.unpriced ? ` + ${r.unpriced} unpriced` : "")));
    const people = r.people.length ? SUI.table({ caption: "People affected", rows: r.people, sort: ["refused", "desc"], columns: [
      { key: "person", label: "Person", lead: true, render: (x) => A.personLink(x.person_id, x.person) },
      { key: "department", label: "Department", render: (x) => x.department || "—" },
      { key: "refused", label: "Refused", num: true }, { key: "request", label: "Requests", num: true, hideSm: true },
      { key: "launch", label: "Opens", num: true, hideSm: true }, { key: "site", label: "Visits", num: true, hideSm: true }] }) : null;
    const overlap = r.already_refused.length ? el("div", { class: "notice info" }, icon("info"),
      "Already refused by: " + r.already_refused.map((x) => `${x.name} (${x.events})`).join(", ") + ".") : null;
    const conflicts = r.conflicts.length ? el("div", { class: "notice" }, icon("alert"),
      el("div", null, r.conflicts.map((c) => el("div", null, el("strong", null, c.name), " " + c.text + ".")))) : null;
    const examples = r.examples.length ? el("ul", { class: "mini-list" }, r.examples.map((x) => el("li", null,
      el("time", { class: "hint nowrap", title: fmt.stamp(x.ts) }, fmt.when(x.ts)), el("div", { class: "grow" }, el("strong", null, x.person), " · " + x.tool + (x.model ? " · " + x.model : "")),
      el("span", { class: "hint" }, x.why)))) : null;
    return [head, facts, conflicts, overlap, people ? A.panel("Who it would have stopped", null, people) : null,
      examples ? A.panel("Examples", "the first few it would have refused", examples) : null,
      el("div", { class: "hint" }, r.notes.join(" "))];
  }

  function simulateTab(ctx) {
    const form = policyForm(null, ctx);
    const out = el("div", { class: "sim-out" });
    const daysSel = el("select", { "aria-label": "Replay" }, [7, 30, 90].map((n) => el("option", { value: String(n) }, `Last ${n} days`)));
    daysSel.value = "30";
    const err = el("div", { class: "err", role: "alert" });
    const run = el("button", { class: "btn primary", onclick: () => {
      err.textContent = "";
      SUI.load(out, async () => simResult(await api("POST", "/policies/simulate", { policy: form.value(), days: Number(daysSel.value) })), SUI.skeleton("rows", 3));
    } }, icon("play"), "Run simulation");
    return [A.panel("Try a policy against what really happened", "read-only — nothing is saved, nobody is told", el("div", { class: "body" }, form.node),
      A.panelFoot(el("span", { class: "grow" }, err), daysSel, run)), out];
  }

  async function explainTab(ctx, params) {
    const person = A.personSelect(ctx.people, params.get("person") || "");
    person.options[0].textContent = "Pick a person";
    const tool = A.toolSelect(params.get("tool") || "");
    tool.options[0].textContent = "Pick a tool";
    const model = el("input", { type: "text", placeholder: "e.g. claude-sonnet-4-6 (for requests)", value: params.get("model") || "", "aria-label": "Model" });
    const channel = el("select", { "aria-label": "How" }, el("option", { value: "" }, "Work it out from the tool"), Object.entries(CHANNEL).map(([k, t]) => el("option", { value: k }, t)));
    channel.value = params.get("channel") || "";
    const out = el("div", { class: "sim-out" });
    const err = el("div", { class: "err", role: "alert" });
    const go = el("button", { class: "btn primary", onclick: () => {
      err.textContent = "";
      if (!person.value || !tool.value) { err.textContent = "Pick a person and a tool."; return; }
      const q = new URLSearchParams({ person: person.value, tool: tool.value });
      if (model.value.trim()) q.set("model", model.value.trim());
      if (channel.value) q.set("channel", channel.value);
      A.keepParams("#/policies", { tab: "explain", person: person.value, tool: tool.value, model: model.value.trim(), channel: channel.value });
      SUI.load(out, async () => explainResult(await api("GET", "/policies/explain?" + q.toString())), SUI.skeleton("rows", 4));
    } }, "Explain");
    if (person.value && tool.value) setTimeout(() => go.click());
    return [A.panel("Why is this allowed — or refused?", "every check, in the order the gateway makes them",
      el("div", { class: "body form-grid" }, A.field("Person", person), A.field("Tool", tool), A.field("Model", model), A.field("How", channel)),
      A.panelFoot(el("span", { class: "grow" }, err), go)), out];
  }

  function explainResult(r) {
    const MARK = { pass: "check", fail: "x", skip: "dot", info: "info" };
    return [
      el("div", { class: "verdict " + (r.allowed ? "yes" : "no") }, icon(r.allowed ? "checkCircle" : "stop"),
        el("div", null, r.allowed ? `${r.person.name} may use ${r.tool ? r.tool.name : r.provider}${r.model ? " with " + r.model : ""} right now.`
          : `${r.person.name} is refused: ${r.decided_by}.`, el("div", { class: "hint" }, CHANNEL[r.channel] + " · as of " + fmt.stamp(r.as_of)))),
      el("ol", { class: "trace" }, r.steps.map((s) => el("li", { class: s.result },
        el("span", { class: "mark", "aria-label": s.result }, icon(MARK[s.result] || "dot")),
        el("div", null, el("div", { class: "t" }, s.check), el("div", { class: "d" }, s.detail))))),
      r.policy_trace.length ? A.panel("Each policy", null, el("ul", { class: "mini-list" }, r.policy_trace.map((t) => el("li", null,
        el("strong", null, t.name), el("span", { class: "grow hint" }, t.why),
        t.applies ? SUI.status(t.refuses ? "blocked" : "ok", t.refuses ? "Refuses" : "Allows", { plain: true }) : SUI.status("idle", "Doesn't apply", { plain: true }))))) : null,
      el("div", { class: "hint" }, r.notes.join(" ")),
    ];
  }

  A.page(/^#\/models$/, pageModels);
  A.page(/^#\/policies$/, pagePolicies);
  Object.assign(A, { CLASS });
})();
