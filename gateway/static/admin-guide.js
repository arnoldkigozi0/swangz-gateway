"use strict";
/* Swangz AI Hub — the app asks, the user answers (BRIEF 10.10.7). The guided tasks behind Overview's "What do you want
   to do?" tiles, and the Simple view of Overview. Each task asks one question per step with the safe answer already
   chosen, shows what will happen, does it through the same routes the full pages use, then suggests the next task.
   The server still decides: tiles only hide what a role cannot do. */
(() => {
  const A = window.SWA;
  const { el, icon, fmt, toast } = SUI;
  const { S, api } = A;

  /* Each period as it reads after a verb: "used AI this week", "used AI in the last 7 days". */
  const PERIODS = { today: "today", week: "this week", "7d": "in the last 7 days", "30d": "in the last 30 days" };
  /* "This week" runs from Monday, in the time the console shows; the other periods are the kit's presets. */
  function weekStart(now) {
    const today = SUI.startOfDay(now);
    const [y, m, d] = SUI.dateInput(today).split("-").map(Number);
    return SUI.startOfDay(today - ((new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7) * 86400 + 7200);
  }
  const rangeOf = (id) => (id === "week" ? { since: weekStart(Date.now() / 1000), until: null } : SUI.presetRange(id));
  const many = (n, one, more) => n.toLocaleString() + " " + (n === 1 ? one : more);

  // ------------------------------------------------------------------ what Overview says first

  /* The one sentence under the title and the one button that follows it, most pressing first. Pure, so it can be tested. */
  function overviewLead(n) {
    const stop = n.canStop ? { label: "Turn AI back on", task: "resume-ai", quiet: true } : { label: "See what is running", href: "#/live", quiet: true };
    if (n.paused) return { sentence: "AI is stopped for everyone.", action: stop };
    if (!n.loaded) return { sentence: "We could not check what needs you.", action: { label: "Try again", retry: true } };
    if (n.urgent) return { sentence: many(n.urgent, "thing needs", "things need") + " you now.", action: { label: "Review " + (n.urgent === 1 ? "it" : "them"), href: "#/attention" } };
    if (n.waiting) return { sentence: many(n.waiting, "person is", "people are") + " waiting for a tool.",
      action: n.canAnswer ? { label: "Answer " + many(n.waiting, "request", "requests"), task: "answer-request" } : { label: "See who is waiting", href: "#/requests" } };
    if (n.secOpen) return { sentence: many(n.secEvents, "security warning", "security warnings") + " in the last 7 days.", action: { label: "Look at the warnings", href: "#/security?days=7" } };
    if (n.items) return { sentence: many(n.items, "small thing", "small things") + " to look at.", action: { label: "See the list", href: "#/attention" } };
    if (n.setupNext) return { sentence: many(n.setupLeft, "setup step", "setup steps") + " left.", action: n.setupNext };
    return { sentence: "Nothing needs you right now.", action: { label: "Check who is using what", task: "check-use" } };
  }

  /* People's sentence and next step (BRIEF 10.10.7). n: { total, notSignedIn, usedToday, canGovern, status }. Pure, so it can be tested.
     The count is the same filter the button opens, so the link shows exactly those people. "Add person" is the page's
     primary in the header, so the next step only repeats it when nobody is on the Hub yet. */
  function peopleLead(n) {
    const onward = n.canGovern ? { label: "Give someone a tool", task: "give-tool" } : { label: "Check who is using what", task: "check-use" };
    if (!n.total) return { sentence: "Nobody has access to the Hub yet.", action: n.canGovern ? { label: "Add a person", task: "add-person" } : onward };
    if (n.notSignedIn) return { sentence: `${n.notSignedIn.toLocaleString()} of ${many(n.total, "person", "people")} ${n.notSignedIn === 1 ? "has" : "have"} not signed in yet.`,
      action: n.status === "invite" ? onward : { label: "See who has not signed in", href: "#/people?status=invite" } };
    return { sentence: `${many(n.total, "person has", "people have")} access; ${n.usedToday.toLocaleString()} used AI today.`, action: onward };
  }

  /* Tools' sentence and next step (BRIEF 10.10.7). n: { inUse, idle, paid, monthly, canGovern, show }. monthly is already
     formatted money. The idle count is the "Given, not opened" filter the button opens. Pure, so it can be tested. */
  function toolsLead(n) {
    const onward = n.canGovern ? { label: "Give someone a tool", task: "give-tool" } : { label: "See what we spent", task: "see-spend" };
    if (!n.inUse) return { sentence: "No tools are in use yet.", action: n.canGovern ? { label: "Give someone a tool", task: "give-tool" } : { label: "See all tools", href: "#/tools?show=all" } };
    if (n.idle) return { sentence: `${many(n.idle, "tool was", "tools were")} given but never opened.`,
      action: n.show === "idle" ? onward : { label: n.idle === 1 ? "See which tool" : "See which tools", href: "#/tools?show=idle" } };
    return { sentence: `${many(n.inUse, "tool is", "tools are")} in use; paid plans cost ${n.monthly} a month.`, action: onward };
  }

  /* Access requests' sentence and next step (BRIEF 10.10.7). n: { open, canDecide, state }. state is the Status filter
     ("open", "granted", "declined" or "" for all). The count is the open requests, and the button answers them one by one
     with each reason shown, or opens the open list when another status is on screen. Pure, so it can be tested. */
  function requestsLead(n) {
    const onward = n.canDecide ? { label: "Give someone a tool", task: "give-tool" } : { label: "Check who is using what", task: "check-use" };
    if (!n.open) return { sentence: "Nothing is waiting for a decision.", action: onward };
    if (!n.canDecide) return { sentence: `${many(n.open, "request is", "requests are")} waiting for an owner.`, action: onward };
    return { sentence: `${many(n.open, "request is", "requests are")} waiting for a decision.`,
      action: n.state === "open" ? { label: "Answer " + many(n.open, "request", "requests"), task: "answer-request" } : { label: "See the open requests", href: "#/requests" } };
  }

  /* Devices' sentence and next step (BRIEF 10.10.7). n: { total, active, idle, unused, requests, state }. A device that was never
     used, or has gone quiet, is a key someone may have lost, so those come first; each count is the Status filter its button
     opens. When that filter is already showing, the next step moves on. Pure, so it can be tested. */
  function devicesLead(n) {
    const onward = { label: "Check who is using what", task: "check-use" };
    if (!n.total) return { sentence: "No devices are connected yet.", action: { label: "See the people", href: "#/people" } };
    if (n.unused) return { sentence: `${many(n.unused, "device has", "devices have")} never been used.`,
      action: n.state === "unused" ? onward : { label: n.unused === 1 ? "See the unused device" : "See the unused devices", href: "#/devices?state=unused" } };
    if (n.idle) return { sentence: `${many(n.idle, "device has", "devices have")} not been used lately.`,
      action: n.state === "idle" ? onward : { label: n.idle === 1 ? "See the quiet device" : "See the quiet devices", href: "#/devices?state=idle" } };
    return { sentence: `${many(n.active, "device is", "devices are")} active; ${many(n.requests, "AI request", "AI requests")} in 30 days.`, action: onward };
  }

  /* "Set up in 4 steps": each step ticks itself from real records. */
  function setupSteps(n) {
    return [
      { id: "people", label: "Add your people", done: n.people > 0, task: n.canGovern ? "add-person" : null, href: "#/people" },
      { id: "tools", label: "Add your tools", done: n.paid > 0 || n.assigned > 0, href: "#/tools" },
      { id: "access", label: "Give people access", done: n.assigned > 0, task: n.canGovern ? "give-tool" : null, href: "#/people" },
      { id: "report", label: "Check the first report", done: n.uses > 0, href: "#/reports" },
    ];
  }

  // ------------------------------------------------------------------ the flow

  /* o: { title, state, steps: [{ q, hint, build(st), check(st), enter(st), when(st) }], review(st) -> { lines, label, danger },
          run(st) -> { title, text, next: { label, href | task, state }, changed } } */
  function guide(o, carried) {
    const st = Object.assign({}, o.state);
    const holder = el("div", { class: "guide" });
    const live = () => o.steps.filter((s) => !s.when || s.when(st));
    let at = 0, touched = false, finished = null, changed = !!carried, leaving = false, sheet = null;
    const err = el("p", { class: "err guide-err", role: "alert" });
    holder.addEventListener("input", () => { touched = true; err.textContent = ""; });
    holder.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.matches("input")) { e.preventDefault(); sheet.node.querySelector(".u-sheet-foot .btn:last-child").click(); }
    });

    function place(question, hint, node) {
      const total = live().length + 1;
      const heading = el("h3", { class: "guide-q", tabindex: "-1" }, question);
      err.textContent = "";
      holder.replaceChildren(SUI.progress(at + 1, { max: total, text: `Step ${at + 1} of ${total}`, label: "Progress through this task" }), heading, ...(hint ? [el("p", { class: "guide-hint" }, hint)] : []), node, err);
      return heading;
    }
    function focusStep(heading) { (holder.querySelector("input[type=search], input[type=text], input[type=email], input:checked") || heading).focus(); }
    function foot() {
      const steps = live();
      if (at < steps.length) sheet.setFoot({ primary: "Next", cancel: "Cancel", back: at > 0 });
      else { const r = o.review(st); sheet.setFoot({ primary: r.label, danger: !!r.danger, cancel: "Cancel", back: true }); }
    }
    function draw() {
      const steps = live();
      let heading;
      if (at < steps.length) heading = place(steps[at].q, steps[at].hint && steps[at].hint(st), steps[at].build(st));
      else { const r = o.review(st); heading = place("Here is what will happen", null, el("ul", { class: "guide-review" }, r.lines.map((l) => el("li", null, l)))); }
      if (sheet) { foot(); focusStep(heading); }
    }
    function result(r) {
      finished = r;
      changed = changed || !!r.changed;
      A.setDirty(null);
      holder.replaceChildren(SUI.stateBox({ tone: r.tone || "ok", icon: r.icon || "checkCircle", title: r.title, text: r.text }));
      if (sheet) { sheet.setFoot({ primary: r.next.label, cancel: "Close", back: false }); sheet.node.querySelector(".u-sheet-foot .btn:last-child").focus(); }
    }
    function follow() {
      const n = finished.next;
      leaving = !!n.task || (!!n.href && location.hash !== n.href);
      sheet.close(true);
      if (n.task) startTask(n.task, n.state, changed); // the next task redraws the page when it closes
      else if (leaving) location.hash = n.href;
      else A.render();
    }
    async function forward() {
      if (finished) return follow();
      const steps = live();
      try {
        if (at < steps.length) {
          const why = steps[at].check && steps[at].check(st);
          if (why) { err.textContent = why; (holder.querySelector("input") || holder).focus(); return undefined; }
          const coming = steps[at + 1];
          if (coming && coming.enter) await coming.enter(st);
          at++;
          draw();
          return undefined;
        }
        result(await o.run(st));
      } catch (e) {
        if (e.status === 401) return undefined;
        err.textContent = (e.message || "That did not work.") + " Try again, or go back and change your answer.";
        if (at >= steps.length) sheet.setFoot({ primary: "Try again", cancel: "Cancel", back: true });
      }
      return undefined;
    }
    function back() { if (!finished && at > 0) { at--; draw(); } }

    if (o.empty) result(o.empty); else draw();
    const leave = () => { if (!A.isDirty()) sheet.close(true); };
    sheet = SUI.sheet({ title: o.title, body: holder, back, primary: { label: "Next", onClick: forward }, dirty: () => !finished && touched,
      onClose: () => { window.removeEventListener("hashchange", leave); A.setDirty(null); if (changed && !leaving) A.render(); } });
    window.addEventListener("hashchange", leave);
    A.setDirty(() => !finished && touched);
    if (finished) sheet.setFoot({ primary: finished.next.label, cancel: "Close", back: false }); else foot();
    return sheet;
  }

  /* One answer out of a few. The radios are native, so arrow keys and screen readers work without help. */
  let groupSeq = 0;
  function choices(options, value, onPick, label) {
    const name = "guide-" + (++groupSeq);
    return el("div", { class: "guide-choices", role: "radiogroup", "aria-label": label }, options.map((x) => {
      const input = el("input", { type: "radio", name, value: x.id });
      input.checked = x.id === value;
      input.addEventListener("change", () => onPick(x.id));
      return el("label", { class: "guide-choice" }, input, x.lead || null, el("span", { class: "guide-choice-text" }, el("strong", null, x.label), x.sub ? el("small", null, x.sub) : null));
    }));
  }
  /* One answer out of many: the same choices, with a search above them. */
  function pickList(options, value, onPick, label, placeholder) {
    const search = el("input", { type: "search", placeholder, "aria-label": placeholder, autocomplete: "off" });
    const list = choices(options, value, onPick, label);
    const none = el("p", { class: "guide-hint", hidden: true }, "No match. Try another search.");
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      let shown = 0;
      [...list.children].forEach((row, i) => { const hit = !q || (options[i].label + " " + (options[i].sub || "")).toLowerCase().includes(q); row.hidden = !hit; shown += hit ? 1 : 0; });
      none.hidden = shown > 0;
    });
    return el("div", { class: "guide-pick" }, el("label", { class: "u-search" }, icon("search"), search), list, none);
  }
  function field(label, type, value, onInput, extra) {
    const input = el("input", Object.assign({ type, value: value || "", autocomplete: "off" }, extra));
    input.addEventListener("input", () => onInput(input.value.trim()));
    return el("label", { class: "field" }, label, input);
  }
  const dateIn = (days) => { const d = new Date(Date.now() + days * 86400000); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
  const periodStep = (q) => ({ q, build: (st) => choices([{ id: "week", label: "This week" }, { id: "7d", label: "The last 7 days" }, { id: "30d", label: "The last 30 days" }], st.range, (v) => { st.range = v; }, q) });

  // ------------------------------------------------------------------ the six tasks

  async function addPerson(state) {
    await A.toolIndex(true);
    const teams = (S.catalog.departments || []).map((t) => ({ id: t, label: t }));
    return { title: "Add a person", state: Object.assign({ name: "", email: "", department: "" }, state), steps: [
      { q: "What is their name?", build: (st) => field("Full name", "text", st.name, (v) => { st.name = v; }, { maxlength: "120" }), check: (st) => (st.name ? null : "Enter their name.") },
      { q: "What is their work email?", hint: () => "They sign in with it.", build: (st) => field("Work email", "email", st.email, (v) => { st.email = v; }),
        check: (st) => (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(st.email) ? null : "Enter an email like name@swangzavenue.com.") },
      { q: "Which team are they in?", hint: () => "You can change this later.", build: (st) => choices([{ id: "", label: "No team yet" }, ...teams], st.department, (v) => { st.department = v; }, "Team") },
    ], review: (st) => ({ label: "Add " + st.name, lines: [`${st.name} joins the Hub as ${st.email}.`, st.department ? `Their team is ${st.department}.` : "They have no team yet.", "They get no tools until you give them one.", "No email is sent."] }),
    run: async (st) => {
      const out = await api("POST", "/people", { name: st.name, email: st.email, department: st.department });
      return { changed: true, title: `${st.name} is added.`, text: "Next, give them a tool.", next: { label: "Give " + st.name + " a tool", task: "give-tool", state: { person: out.id, personName: st.name } } };
    } };
  }

  async function giveTool(state) {
    const [people] = await Promise.all([api("GET", "/people"), A.toolIndex(true)]);
    const active = people.items.filter((p) => p.status === "active");
    const tools = S.catalog.tools;
    return { title: "Give someone a tool", state: Object.assign({ person: null, personName: "", tool: null, days: "30", held: {} }, state), steps: [
      { q: "Who should get the tool?", when: () => !(state && state.person), build: (st) => pickList(active.map((p) => ({ id: p.id, label: p.name, sub: p.department || p.email || "" })), st.person, (v) => { st.person = v; st.personName = active.find((p) => p.id === v).name; }, "Person", "Search people"),
        check: (st) => (st.person ? null : "Choose a person.") },
      { q: "Which tool?", enter: async (st) => { const p = await api("GET", "/people/" + st.person); st.held = Object.fromEntries(p.tools.map((t) => [t.id, t])); },
        build: (st) => pickList(tools.map((t) => ({ id: t.id, label: t.name, sub: st.held[t.id] && st.held[t.id].grant ? "They already have this" : t.category, lead: A.toolLogo(t.id, t.name, "sm") })), st.tool, (v) => { st.tool = v; }, "Tool", "Search tools"),
        check: (st) => (st.tool ? null : "Choose a tool.") },
      { q: "How long should they have it?", hint: (st) => { const h = st.held[st.tool]; return h && h.grant === "direct" ? "They already have this. Your answer replaces the old end date." : "You can take it back at any time."; },
        build: (st) => choices([{ id: "30", label: "30 days" }, { id: "90", label: "90 days" }, { id: "", label: "No end date" }], st.days, (v) => { st.days = v; }, "How long") },
    ], review: (st) => {
      const t = S.tools[st.tool];
      const off = t.kind === "site" && ["none", "cancelled", "past_due"].includes(t.subscription.state);
      return { label: "Give access", lines: [`${st.personName} can use ${t.name}${st.days ? ` for ${st.days} days` : " with no end date"}.`,
        off ? `The company licence for ${t.name} is not active, so it stays locked until it is.` : "It works on their next visit.", "This is written in the audit log."] };
    }, run: async (st) => {
      const t = S.tools[st.tool];
      await api("POST", `/people/${st.person}/tools/${st.tool}`, st.days ? { until: dateIn(Number(st.days)) } : {});
      return { changed: true, title: `${st.personName} now has ${t.name}.`, text: st.days ? `Their access ends in ${st.days} days.` : "Their access has no end date.", next: { label: `See ${st.personName}'s access`, href: `#/people/${st.person}?tab=access` } };
    } };
  }

  async function answerRequest() {
    const data = await api("GET", "/access-requests?state=open");
    const items = data.items.slice().sort((a, b) => a.created - b.created);
    if (!items.length) return { title: "Answer a request", steps: [], empty: { icon: "requests", title: "No requests are waiting.", text: "New requests from staff appear here.", next: { label: "See past requests", href: "#/requests?state=granted" } } };
    const pick = (st) => items.find((r) => r.id === st.request);
    return { title: "Answer a request", state: { request: items[0].id, answer: "later", note: "" }, steps: [
      { q: "Which request?", hint: () => "The oldest is chosen for you.", build: (st) => choices(items.map((r) => ({ id: r.id, label: `${r.person} asks for ${r.tool}`, sub: r.reason || "asked " + fmt.ago(r.created) })), st.request, (v) => { st.request = v; }, "Request") },
      { q: "What is your answer?", build: (st) => {
        const note = el("label", { class: "field", hidden: st.answer !== "no" }, "A note for them (optional)", el("textarea", { rows: "3", maxlength: "500" }));
        const box = note.querySelector("textarea");
        box.value = st.note;
        box.addEventListener("input", () => { st.note = box.value; });
        return el("div", { class: "stack" }, choices([{ id: "later", label: "Decide later", sub: "Nothing changes" }, { id: "give", label: "Give access" }, { id: "no", label: "Say no" }], st.answer, (v) => { st.answer = v; note.hidden = v !== "no"; }, "Answer"), note);
      } },
    ], review: (st) => {
      const r = pick(st);
      if (st.answer === "give") return { label: "Give access", lines: [`${r.person} can use ${r.tool} straight away, with no end date.`, "This is written in the audit log."] };
      if (st.answer === "no") return { label: "Say no", danger: true, lines: [`${r.person} is told the answer is no.`, st.note ? "They see your note." : "No note is added.", "This is written in the audit log."] };
      return { label: "Leave it waiting", lines: ["Nothing changes.", `${r.person}'s request keeps waiting.`] };
    }, run: async (st) => {
      const r = pick(st), more = items.length - 1;
      if (st.answer === "later") return { icon: "clock", tone: null, title: "Nothing changed.", text: `${r.person}'s request is still waiting.`, next: { label: "See all requests", href: "#/requests" } };
      await api("POST", `/access-requests/${r.id}/${st.answer === "give" ? "grant" : "decline"}`, st.note && st.answer === "no" ? { note: st.note } : undefined);
      return { changed: true, title: st.answer === "give" ? `${r.person} now has ${r.tool}.` : `You said no to ${r.person}.`, text: more ? `${many(more, "request is", "requests are")} still waiting.` : "No more requests are waiting.",
        next: more ? { label: "Answer the next request", task: "answer-request" } : { label: `See ${r.person}'s access`, href: `#/people/${r.person_id}?tab=access` } };
    } };
  }

  async function seeSpend() {
    return { title: "See what we spent", state: { range: "7d" }, steps: [periodStep("Which period?")],
      review: (st) => ({ label: "Show the total", lines: [`We add up AI spend ${PERIODS[st.range]}.`, "Nothing changes."] }),
      run: async (st) => {
        const cost = st.range === "week" ? (await api("GET", "/spend?" + A.rangeQuery(rangeOf("week")).toString())).total
          : (await api("GET", "/trends?days=" + (st.range === "7d" ? 7 : 30))).current.cost;
        return { icon: "wallet", title: `${fmt.money(cost)} spent ${PERIODS[st.range]}.`, text: "This is an estimate from our price list. Company plans are billed on top.", next: { label: "See where it went", href: "#/licences?tab=spend&" + (st.range === "week" ? "range=custom&from=" + SUI.dateInput(rangeOf("week").since) : "range=" + st.range) } };
      } };
  }

  async function checkUse() {
    const people = await api("GET", "/people");
    const options = [{ id: 0, label: "Everyone" }, ...people.items.map((p) => ({ id: p.id, label: p.name, sub: p.department || "" }))];
    return { title: "Check who is using what", state: { person: 0, range: "7d" }, steps: [
      { q: "Whose use do you want to see?", build: (st) => pickList(options, st.person, (v) => { st.person = v; }, "Person", "Search people") },
      periodStep("Which period?"),
    ], review: (st) => ({ label: "Show the use", lines: [`We count AI use by ${st.person ? options.find((x) => x.id === st.person).label : "everyone"} ${PERIODS[st.range]}.`, "Nothing changes."] }),
    run: async (st) => {
      const q = A.rangeQuery(rangeOf(st.range));
      if (st.person) q.set("person", String(st.person));
      const out = await api("GET", "/usage?" + q.toString());
      const uses = out.rows.reduce((n, r) => n + r.requests + r.opens + r.visits, 0), when = PERIODS[st.range];
      if (st.person) {
        const name = options.find((x) => x.id === st.person).label;
        return { icon: "activity", title: out.rows.length ? `${name} used ${many(out.tools.length, "tool", "tools")} ${when}.` : `${name} did not use AI ${when}.`, text: uses ? `That is ${many(uses, "use", "uses")} in all.` : "Their record is still there.", next: { label: `See ${name}'s activity`, href: `#/people/${st.person}?tab=activity` } };
      }
      return { icon: "activity", title: out.people.length ? `${many(out.people.length, "person", "people")} used AI ${when}.` : `Nobody used AI ${when}.`, text: uses ? `That is ${many(uses, "use", "uses")} in all.` : "New use shows here as it happens.", next: { label: "See who used what", href: `#/activity?tab=usage&range=${st.range}&by=person` } };
    } };
  }

  function pauseTask(stop) {
    return { title: stop ? "Stop all AI" : "Turn AI back on", state: { go: "no" }, steps: [
      { q: stop ? "Do you want to stop all AI now?" : "Do you want to turn AI back on now?", hint: () => (stop ? "Use this if something is going wrong." : "Check the problem is over first."),
        build: (st) => choices([{ id: "no", label: stop ? "No, keep it running" : "No, keep it stopped" }, { id: "yes", label: stop ? "Yes, stop everything" : "Yes, turn it back on" }], st.go, (v) => { st.go = v; }, "Your answer") },
    ], review: (st) => {
      if (st.go !== "yes") return { label: "Leave it as it is", lines: ["Nothing changes."] };
      return stop ? { label: "Stop all AI", danger: true, lines: ["Every request now running is cut.", "Every new request is refused.", "The Open buttons close for all staff.", "It stays stopped until someone turns it back on."] }
        : { label: "Turn AI back on", lines: ["Requests work again for everyone.", "The Open buttons work again."] };
    }, run: async (st) => {
      if (st.go !== "yes") return { icon: "info", tone: null, title: "Nothing changed.", text: stop ? "AI is still running." : "AI is still stopped.", next: { label: "See what is running", href: "#/live" } };
      const out = await api("POST", "/pause", { paused: stop });
      await A.refreshOverview();
      return stop ? { changed: true, tone: null, icon: "stop", title: "All AI is stopped.", text: `${many(out.cut || 0, "request was", "requests were")} cut.`, next: { label: "Turn AI back on", task: "resume-ai" } }
        : { changed: true, title: "AI is back on.", text: "Requests and tools work again.", next: { label: "See what is running", href: "#/live" } };
    } };
  }

  const TASKS = {
    "add-person": addPerson, "give-tool": giveTool, "answer-request": answerRequest, "see-spend": seeSpend, "check-use": checkUse,
    "stop-ai": async () => pauseTask(true), "resume-ai": async () => pauseTask(false),
  };
  async function startTask(id, state, carried) {
    try { guide(await TASKS[id](state), carried); } catch (e) { if (e.status !== 401) toast(e.message || "That task could not start.", true); }
  }

  // ------------------------------------------------------------------ Overview, Simple

  /* inline: a link inside Detailed's one-line "Next step", which keeps that view at its measured height. */
  function leadButton(a, inline) {
    const cls = inline ? "ov-link" : a.quiet ? "btn" : "btn primary", arrow = inline ? null : icon("chevronRight");
    return a.href && !a.task ? el("a", { class: cls, href: a.href }, a.label, arrow)
      : el("button", { class: cls, type: "button", onclick: a.retry ? () => A.render() : () => startTask(a.task) }, a.label, arrow);
  }

  function tiles(waiting, paused) {
    const list = [
      A.can("govern") && ["add-person", "Add a person", "Put someone new on the Hub", "user"],
      A.can("govern") && ["give-tool", "Give someone a tool", "Choose who, what and how long", "tools"],
      A.can("govern") && ["answer-request", "Answer a request", waiting ? many(waiting, "request is", "requests are") + " waiting" : "None waiting now", "requests"],
      ["see-spend", "See what we spent", "A total for the period you pick", "wallet"],
      ["check-use", "Check who is using what", "One person or everyone", "activity"],
      A.can("emergency") && (paused ? ["resume-ai", "Turn AI back on", "AI is stopped now", "play"] : ["stop-ai", "Stop all AI", "If something is going wrong", "stop"]),
    ].filter(Boolean);
    return el("div", { class: "task-tiles" }, list.map(([id, title, sub, ic]) => el("button", { type: "button", class: "task-tile", "data-task": id, onclick: () => startTask(id) },
      el("span", { class: "task-icon", "aria-hidden": "true" }, icon(ic)), el("strong", null, title), el("small", null, sub))));
  }

  function numberRow(label, value, href) {
    return el("a", { class: "ov-num", href }, el("span", null, label), el("strong", { class: "u-num" }, value), icon("chevronRight"));
  }

  /* At most three blocks: the tiles, the numbers, and either first-visit setup or the short list of what is waiting. */
  function overviewSimple(o) {
    const numbers = A.panel("How it is going", null, o.tr
      ? el("div", { class: "ov-nums" },
        numberRow("Spent", fmt.money(o.tr.current.cost) + " in 30 days", "#/licences?tab=spend&range=30d"),
        numberRow("AI requests", many(o.tr.current.requests, "request", "requests") + " in 30 days", "#/activity?tab=ai&range=30d"),
        numberRow("People using AI", many(o.tr.days[o.tr.days.length - 1].people, "person", "people") + " today", "#/activity?tab=usage&range=today&by=person"))
      : SUI.errorBox(o.trError, () => A.render(), "The numbers could not load"));
    let third = null;
    if (o.setup && o.setup.some((s) => !s.done)) {
      third = A.panel("Set up in 4 steps", null, el("ol", { class: "ov-setup" }, o.setup.map((s) => el("li", { class: s.done ? "done" : "" },
        el("span", { class: "ov-tick", "aria-hidden": "true" }, s.done ? icon("check") : null),
        s.done ? el("span", null, s.label, el("span", { class: "u-sr" }, " (done)"))
          : s.task ? el("button", { type: "button", onclick: () => startTask(s.task) }, s.label) : el("a", { href: s.href }, s.label)))));
    } else if (o.att && o.att.length) {
      third = A.panel("Waiting for you", el("a", { class: "btn small quiet", href: "#/attention" }, "See all", icon("chevronRight")),
        el("ul", { class: "ov-wait" }, o.att.slice(0, 5).map((i) => el("li", null, el("a", { href: i.href || "#/attention", title: i.title }, i.title)))));
    }
    return el("div", { class: "ov-simple" }, A.panel("What do you want to do?", null, tiles(o.waiting, o.paused)), el("div", { class: "ov-side" }, numbers, third));
  }

  Object.assign(A, { startTask, overviewLead, peopleLead, toolsLead, requestsLead, setupSteps, overviewSimple, leadButton, devicesLead });
})();
