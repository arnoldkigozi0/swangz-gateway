"use strict";
/* Swangz AI Hub — the control kit page (#/kit, owners only): every shared control in every state, built from the
   same SUI functions the pages use, so a change to a control is seen here first. Nothing on it reads or changes
   data: every action only says what it would have done. It is not in the navigation. */
(() => {
  const A = window.SWA;
  const { el, toast } = SUI;

  const said = (what) => () => toast(what + " (kit page: nothing changed)");
  const TEAMS = ["Creative", "Production", "Finance", "Legal", "People", "Technology", "Sales", "Events", "Studio"]
    .map((t) => ({ id: t.toLowerCase(), label: t }));
  const ACTIONS = () => [
    { id: "open", label: "Open profile", icon: "user", onSelect: said("Open profile") },
    { id: "export", label: "Export activity", sub: "CSV, this month", onSelect: said("Export activity") },
    { id: "locked", label: "Change role", disabled: true },
    { id: "remove", label: "Remove access", danger: true, onSelect: said("Remove access") }];

  /* One specimen: the state's name over the control. */
  function spec(state, ...nodes) {
    return el("div", { class: "kit-spec" }, el("div", { class: "kit-state" }, state), el("div", { class: "kit-stage" }, ...nodes));
  }
  function group(title, call, ...specs) {
    return A.panel(title, call, el("div", { class: "body kit-grid" }, ...specs));
  }
  function btn(cls, label, o) {
    return el("button", Object.assign({ type: "button", class: "btn " + cls, onclick: said(label) }, o || {}), label);
  }

  function pageKit() {
    if (!A.isOwner()) {
      A.frame({ title: "Control kit" }, SUI.stateBox({ icon: "lock", title: "Owners only", text: "The control kit is a reference page for the people who look after the console." }));
      return;
    }
    const buttons = group("Buttons", ".btn",
      spec("Outline (default)", btn("", "Export")), spec("Primary", btn("primary", "Save changes")),
      spec("Quiet", btn("quiet", "Cancel")), spec("Danger", btn("danger", "Remove access")),
      spec("Small", btn("small", "Edit")), spec("Disabled", btn("", "Export", { disabled: true }), btn("primary", "Save changes", { disabled: true })));

    const menus = group("Menu and More button", "SUI.menuButton",
      spec("Dots", SUI.menuButton({ label: "More actions for Amina", items: ACTIONS })),
      spec("Small, in a row", SUI.menuButton({ label: "More actions for Brian", items: ACTIONS, small: true })),
      spec("With a word", SUI.menuButton({ label: "More actions", text: "More", items: ACTIONS })),
      spec("Aligned to the end", SUI.menuButton({ label: "More actions for Carol", items: ACTIONS, align: "end" })),
      spec("Disabled", SUI.menuButton({ label: "More actions for Dan", items: ACTIONS, disabled: true })));

    const formats = () => [{ id: "csv", label: "CSV", onSelect: said("Export CSV") }, { id: "pdf", label: "PDF", onSelect: said("Export PDF") }];
    const splits = group("Split button", "SUI.splitButton",
      spec("Default", SUI.splitButton({ label: "Export", onClick: said("Export"), items: formats, menuLabel: "More export formats" })),
      spec("Primary", SUI.splitButton({ label: "Export", onClick: said("Export"), items: formats, menuLabel: "More export formats", primary: true })),
      spec("Small", SUI.splitButton({ label: "Export", onClick: said("Export"), items: formats, menuLabel: "More export formats", small: true })),
      spec("With an icon", SUI.splitButton({ label: "Add person", icon: "plus", onClick: said("Add person"), items: () => [{ id: "many", label: "Add several", onSelect: said("Add several") }], menuLabel: "More ways to add" })),
      spec("Disabled", SUI.splitButton({ label: "Export", items: formats, menuLabel: "More export formats", disabled: true })));

    const five = TEAMS.slice(0, 5);
    const selects = group("Dropdown select", "SUI.select",
      spec("Empty, with a placeholder", SUI.select({ label: "Team", options: five, placeholder: "Choose a team", onChange: (id) => toast("Team: " + id) })),
      spec("With a value", SUI.select({ label: "Team", options: five, value: "finance" })),
      spec("Nine options: search appears", SUI.select({ label: "Team", options: TEAMS, value: "studio" })),
      spec("Second lines and a disabled row", SUI.select({ label: "Role", value: "ops", options: [
        { id: "owner", label: "Owner", sub: "Every area" }, { id: "ops", label: "Operations", sub: "Govern and emergency" },
        { id: "sec", label: "Security", sub: "Trust and emergency" }, { id: "bill", label: "Billing", sub: "Money" },
        { id: "view", label: "Viewer", sub: "Read-only", disabled: true }] })),
      spec("Small", SUI.select({ label: "Team", options: five, value: "legal", small: true })),
      spec("Disabled", SUI.select({ label: "Team", options: five, value: "people", disabled: true })));

    const filterDefs = [
      { id: "team", label: "Team", any: "Any team", options: TEAMS },
      { id: "state", label: "State", any: "Any state", options: [{ id: "active", label: "Active" }, { id: "paused", label: "Paused" }, { id: "ended", label: "Ended" }] },
      { id: "role", label: "Role", any: "Any role", options: [{ id: "staff", label: "Staff" }, { id: "lead", label: "Team lead" }] },
      { id: "device", label: "Device", any: "Any device", options: [{ id: "company", label: "Company" }, { id: "personal", label: "Personal" }] }];
    const bar = (label, values) => SUI.filterBar({ label, search: { placeholder: "Search people", param: "q" }, filters: filterDefs, values, onChange() {} });
    const filters = A.panel("Filter bar", "SUI.filterBar", el("div", { class: "body kit-stack" },
      spec("Nothing chosen", bar("Filter people, empty", {})),
      spec("Search and two filters active: chips and Clear all", bar("Filter people, active", { q: "amina", team: "creative", state: "paused" })),
      spec("A filter behind More filters is active", bar("Filter people, more", { device: "company" }))));

    function openSheet(o) {
      let touched = !!o.dirty;
      const name = el("input", { type: "text", value: "Amina Nakato", oninput: () => { touched = true; } });
      SUI.sheet({ title: "Edit person", purpose: "Change how this person appears in the console.",
        body: el("label", { class: "field" }, "Name", name),
        primary: { label: "Save changes", onClick: (s) => (o.slow ? new Promise((done) => setTimeout(() => { s.close(true); done(); }, 1500)) : s.close(true)) },
        dirty: () => touched });
    }
    const sheets = group("Side sheet", "SUI.sheet",
      spec("Clean: closes at once", btn("", "Open sheet", { onclick: () => openSheet({}) })),
      spec("Unsaved changes: asks first", btn("", "Open dirty sheet", { onclick: () => openSheet({ dirty: true }) })),
      spec("Primary waits on a slow save", btn("", "Open slow sheet", { onclick: () => openSheet({ slow: true }) })));

    const small = group("Pills, search and switches", "SUI.segmented · SUI.searchPill · A.switchInput",
      spec("Segmented, with counts", SUI.segmented({ label: "State", value: "all", options: [{ id: "all", label: "All", count: 24 }, { id: "active", label: "Active", count: 19 }, { id: "paused", label: "Paused", count: 5 }], onChange() {} })),
      spec("Search, empty", SUI.searchPill({ label: "Search tools", placeholder: "Search tools" })),
      spec("Search, filled", SUI.searchPill({ label: "Search tools, filled", value: "midjourney" })),
      spec("Switch: off, on", A.switchInput(false, false, "Example off"), A.switchInput(true, false, "Example on")),
      spec("Switch: disabled off, on", A.switchInput(false, true, "Example disabled off"), A.switchInput(true, true, "Example disabled on")));

    const states = group("Status, badges and progress", "SUI.status · SUI.badge · SUI.progress",
      spec("Status: every state", ...[["ok", "Working"], ["waiting", "Waiting"], ["blocked", "Blocked"], ["info", "Investigating"], ["idle", "Resolved"], ["none", "No key"]].map(([s, w]) => SUI.status(s, w))),
      spec("Status: plain", SUI.status("ok", "Working", { plain: true }), SUI.status("blocked", "Failing", { plain: true })),
      spec("Badge", SUI.badge("Owner"), SUI.badge("Shared account", null, "users")),
      spec("Progress: none, part, full", SUI.progress(0), SUI.progress(42), SUI.progress(100)));

    const boxes = A.panel("Loading, empty and error", "SUI.skeleton · SUI.stateBox · SUI.errorBox", el("div", { class: "body kit-grid wide" },
      spec("Loading", SUI.skeleton("cards", 2)),
      spec("Empty", SUI.stateBox({ compact: true, icon: "info", title: "Nothing here yet", text: "People you add appear in this list." })),
      spec("Empty, with an action", SUI.stateBox({ compact: true, icon: "user", title: "No people yet", text: "Add the first person to give them a tool.", action: btn("primary", "Add person") })),
      spec("Error, with retry", SUI.errorBox(new Error("The gateway did not answer"), said("Try again"), "This list couldn't load"))));

    A.frame({ title: "Control kit", lede: "Every shared control in every state. Nothing on this page reads or changes data." },
      [buttons, menus, splits, selects, filters, sheets, small, states, boxes]);
  }

  A.page(/^#\/?kit$/, pageKit);
})();
