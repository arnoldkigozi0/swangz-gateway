"use strict";
/* Forensics: one request's full record, and a whole session. Opening a record is written to the
   audit log. Every fact says how sure it is — from the key, from the tool's user agent, an estimate
   from the price table — so an inference is never presented as a fact. */
(() => {
  const { el, icon, fmt } = SUI;
  const A = SWA;
  const { api } = A;

  function longText(text, limit) {
    limit = limit || 2400;
    if (typeof text !== "string") text = JSON.stringify(text, null, 2);
    if (text.length <= limit) return el("pre", { class: "text" }, text);
    const pre = el("pre", { class: "text" }, text.slice(0, limit) + "…");
    const more = el("button", { class: "btn link", onclick: () => { pre.textContent = text; more.remove(); } }, `Show all (${text.length.toLocaleString()} characters)`);
    return el("div", null, pre, more);
  }
  function code(obj, limit) {
    const text = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
    limit = limit || 6000;
    if (text.length <= limit) return el("pre", { class: "code" }, text);
    const pre = el("pre", { class: "code" }, text.slice(0, limit) + "\n…");
    const more = el("button", { class: "btn link", onclick: () => { pre.textContent = text; more.remove(); } }, `Show all (${text.length.toLocaleString()} characters)`);
    return el("div", null, pre, more);
  }
  const isVideo = (u) => /\.(mp4|webm|mov)(\?|$)/i.test(u);

  /* A fact and how we know it. */
  function fact(k, v, how) {
    return el("div", { class: "fact" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), how ? el("div", { class: "how" }, SUI.evidence(how)) : null);
  }

  // ------------------------------------------------------------------ the record

  async function pageRecord(params, id) {
    await A.toolIndex().catch(() => null);
    const r = await api("GET", "/requests/" + id);
    const tokens = `${fmt.tokens(r.in_tok)} in · ${fmt.tokens(r.out_tok)} out` +
      (r.cache_read_tok ? ` · ${fmt.tokens(r.cache_read_tok)} cache read` : "") + (r.cache_write_tok ? ` · ${fmt.tokens(r.cache_write_tok)} cache write` : "") +
      (r.reasoning_tok ? ` · ${fmt.tokens(r.reasoning_tok)} reasoning` : "");
    const refused = r.outcome === "blocked" || r.outcome === "denied";
    const costText = r.kind === "media" && r.cost === null ? (A.units(r) || "—") : refused ? "Nothing — it was refused" : fmt.money(r.cost);
    const cb = r.cost_basis || {};
    const costHow = refused ? "Refused requests cost nothing" : r.cost === null ? (r.kind === "media" ? "Unpriced: no media rate for this service yet (Settings → Media rates)" : "Unpriced: the model isn't in the price table")
      : cb.from === "media rate" ? `Estimated from the media rate in force then${cb.rate ? ` ($${cb.rate.usd_per_unit} per ${cb.rate.unit})` : ""}${cb.as_of ? ", effective " + fmt.date(cb.as_of) : ""}`
        : `Estimated from the price for ${cb.ref || "this model"}${cb.as_of ? " as of " + fmt.date(cb.as_of) : ""}; never recalculated`;
    const loc = r.location;
    const placeHow = !loc ? null : loc.kind === "known" ? "A network Swangz named — exact" : loc.approximate ? `Approximate — ${loc.source || "location table"}; not GPS`
      : loc.evidence || "Only the kind of address is known";
    const PURPOSE_HOW = { declared: "Declared by the person or their tool", derived: "Derived from the tool itself", inferred: "Inferred from keywords — a guess" };
    const facts = el("div", { class: "facts identity" },
      fact("Person", r.person_id ? A.personLink(r.person_id, r.person) : el("span", { class: "muted" }, "No valid key"), r.person_id ? "Owner of the key used" : "The key wasn't recognised"),
      fact("Device", A.deviceLink(r.key_id, r.key_label) || "—", r.key_id ? "Registered device (its own gateway key)" : null),
      fact("Application", r.client && r.client !== "unknown" ? r.client : "Not identified", "From the tool's user agent"),
      fact("Tool", r.tool ? A.toolLink(r.tool.id, r.tool.name, "sm") : "—", r.tool ? "Catalog tool for this service" : null),
      fact("Model", el("span", { class: "mono" }, r.model || "—"), r.model ? "As requested by the tool" : null),
      fact("Time", fmt.stamp(r.ts), SUI.tzLabel()),
      fact("Took", fmt.ms(r.duration_ms) + (r.ttft_ms ? ` · first word after ${fmt.ms(r.ttft_ms)}` : ""), "Measured by the gateway"),
      fact("From", r.client_ip ? el("span", null, el("span", { class: "mono" }, r.client_ip), r.place ? el("span", { class: "faint" }, " · " + r.place) : null) : "—", placeHow),
      fact("For", r.purpose ? el("span", { class: "row" }, A.purposeChip(r.purpose_name || A.purposeName(r.purpose), r.purpose_source, r.purpose_confidence, r.purpose_evidence),
        r.project ? el("span", { class: "faint" }, "· " + r.project) : null) : el("span", { class: "muted" }, "Unknown"),
      r.purpose ? `${PURPOSE_HOW[r.purpose_source] || ""}${r.purpose_confidence != null && r.purpose_source === "inferred" ? ` (${Math.round(r.purpose_confidence * 100)}% sure)` : ""}${r.purpose_evidence ? " · " + r.purpose_evidence : ""}`
        : "Nothing declared, and no rule was sure enough"),
      r.rule ? fact("Refused by", r.rule.startsWith("policy:") ? el("a", { href: "#/policies" }, r.rule_name || "a policy") : el("a", { href: "#/models" }, "The model registry: " + r.rule.slice(6)),
        "The company rule that refused it") : null,
      fact("Platform", r.platform || "Not stated by the tool", "From the user agent"),
      fact("Cost", el("span", { class: "row" }, costText, !refused && r.cost !== null ? el("span", { class: "basis estimated" }, "estimated") : null), costHow),
      fact(r.kind === "media" ? "Size" : "Tokens", r.kind === "media" ? (A.units(r) || "—") : tokens, r.kind === "media" ? null : "Reported by the provider"),
      fact("Session", r.session ? el("a", { class: "mono", href: "#/sessions/" + encodeURIComponent(r.session) }, r.session.slice(0, 18) + (r.session.length > 18 ? "…" : "")) : "—",
        r.session ? "Sent by the tool" : null));

    // the request, step by step: what was asked, what the model did, how it ended
    const steps = [];
    const step = (cls, at, title, ic, ...body) => steps.push(el("li", { class: "step " + cls },
      el("div", { class: "step-time u-num" }, at ? fmt.clock(at, true) : ""),
      el("div", { class: "step-dot", "aria-hidden": "true" }, icon(ic)),
      el("div", { class: "step-body" }, el("div", { class: "step-title" }, title), ...body)));
    step("start", r.ts, r.prompt ? (r.kind === "media" ? "Asked for" : "Prompt received") : "Request received", "send",
      r.prompt ? el("div", { class: "bubble" }, r.prompt) : el("p", { class: "hint" }, "Nothing typed in this request — the tool was sending results back to the model on its own."),
      A.agentBadges(r).length ? el("div", { class: "row" }, A.agentBadges(r)) : null);
    if (r.ttft_ms) step("think", r.ts + r.ttft_ms / 1000, "Model began responding", "spark", el("p", { class: "hint" }, `${fmt.ms(r.ttft_ms)} after the request arrived`));
    r.actions.forEach((a) => {
      const [label, ic] = A.ACTION[a.kind] || A.ACTION.other;
      step("action a-" + (A.ACTION[a.kind] ? a.kind : "other"), null, el("span", null, el("span", { class: "act-k" }, label)), ic, el("div", { class: "act-t" }, a.text));
    });
    if (r.reply) step("reply", null, r.kind === "media" ? "Result" : "Model replied", "read", longText(r.reply, 1600));
    step("end o-" + r.outcome, r.ts + (r.duration_ms || 0) / 1000, A.outcomeStatus("request", r.outcome), r.outcome === "ok" ? "checkCircle" : "stop",
      r.reason ? el("p", { class: "ev-reason" }, r.reason) : null, r.status ? el("p", { class: "hint" }, `HTTP ${r.status}`) : null);
    const timeline = A.panel("Request timeline", r.actions.length ? SUI.plural(r.actions.length, "action") + " · times in " + SUI.tzLabel(true) : "times in " + SUI.tzLabel(true),
      el("ol", { class: "steps" }, steps),
      r.actions.length ? el("div", { class: "body hint" }, "Actions are listed in the order the model asked for them; the gateway records when the request started and ended, not each action's own time.") : null);

    const isAudio = (r.resp_ctype || "").startsWith("audio/");
    const media = isAudio || (r.result_urls && r.result_urls.length) ? A.panel("What was made", null, el("div", { class: "body stack" },
      isAudio ? el("audio", { controls: true, preload: "none", src: A.gadmin(`/requests/${r.id}/media`), crossorigin: A.GATEWAY ? "use-credentials" : null }) : null,
      (r.result_urls || []).map((u) => el("div", { class: "stack" },
        isVideo(u) ? el("video", { controls: true, preload: "metadata", src: u, class: "result" }) : el("img", { src: u, alt: "", class: "result", referrerpolicy: "no-referrer" }),
        el("a", { class: "mono faint", href: u, target: "_blank", rel: "noopener noreferrer" }, u))),
      el("div", { class: "hint" }, isAudio ? "Played back from the gateway's own copy. Playing it is written to the audit log." : "Result links come from the service; they can expire."))) : null;

    const full = [
      !r.stored ? A.panel("Full record", null, A.empty("The request body was not stored (storage was switched off, or retention has removed it). The summary above is all that is left.", "Body not kept", "file")) : null,
      r.request !== null && r.request !== undefined ? collapsible("What was sent", "the whole request, as the tool sent it", () => renderRequest(r.request)) : null,
      r.response !== null && r.response !== undefined ? collapsible("What came back", "the provider's reply", () => renderResponse(r.response)) : null,
    ];
    A.frame({
      title: `Request #${r.id}`, status: A.outcomeStatus("request", r.outcome),
      crumbs: [el("a", { href: "#/activity" }, "Activity"), r.person_id ? el("a", { href: "#/people/" + r.person_id }, r.person) : null,
        r.session ? el("a", { href: "#/sessions/" + encodeURIComponent(r.session) }, "Session") : null].filter(Boolean),
      lede: [r.person || "An unknown key", r.client && r.client !== "unknown" ? "· " + r.client : "", r.model ? "· " + r.model : "", "· " + fmt.stamp(r.ts)].join(" "),
      actions: [r.session ? el("a", { class: "btn", href: "#/sessions/" + encodeURIComponent(r.session) }, icon("layers"), "Whole session") : null,
        el("a", { class: "btn", href: A.gadmin(`/requests/${r.id}?download=1`) }, icon("download"), "Download JSON")],
    }, [
      A.flagBadges(r.flags).length ? el("div", { class: "row" }, A.flagBadges(r.flags)) : null,
      A.panel("Who, what, when, where", null, facts),
      timeline, media, ...full,
      el("p", { class: "hint" }, icon("audit"), " Opening a full record is written to the audit log."),
    ]);
  }

  function collapsible(title, sub, build) {
    const body = el("div");
    let built = false;
    const btn = el("button", { class: "btn small", type: "button", "aria-expanded": "false" }, "Show");
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "Hide" : "Show";
      if (open && !built) { body.append(build()); built = true; }
      body.hidden = !open;
    });
    body.hidden = true;
    return A.panel(title, el("span", { class: "row" }, el("span", { class: "sub" }, sub), btn), body);
  }

  function renderRequest(req) {
    if (typeof req !== "object" || req === null) return el("div", { class: "body" }, code(req));
    const listKey = Array.isArray(req.messages) ? "messages" : Array.isArray(req.input) ? "input" : null;
    const setup = {};
    for (const [k, v] of Object.entries(req)) if (k !== listKey) setup[k] = v;
    const sys = setup.system ?? setup.instructions;
    const tools = Array.isArray(setup.tools) ? setup.tools : null;
    const rest = Object.fromEntries(Object.entries(setup).filter(([k]) => !["system", "instructions", "tools"].includes(k)));
    const parts = [];
    parts.push(el("div", { class: "msg" }, el("details", null,
      el("summary", null, "Setup sent by the tool", el("span", { class: "faint" }, ` — ${sys ? "system prompt, " : ""}${tools ? tools.length + " tool definitions, " : ""}settings`)),
      sys ? [el("div", { class: "tag" }, "System prompt"), longText(typeof sys === "string" ? sys : sys.map((b) => b.text || JSON.stringify(b)).join("\n\n"), 4000)] : null,
      tools ? [el("div", { class: "tag" }, "Tools offered"), el("p", { class: "mono muted" }, tools.map((t) => t.name || t.type).join(", "))] : null,
      el("div", { class: "tag" }, "Settings"), code(rest))));
    if (typeof req.input === "string") parts.push(el("div", { class: "msg user" }, el("div", { class: "role" }, "user"), longText(req.input)));
    const items = listKey ? req[listKey] : [];
    const shown = items.length > 120 ? items.slice(-120) : items;
    if (items.length > shown.length) parts.push(el("div", { class: "msg hint" }, `${items.length - shown.length} earlier messages are not shown here; download the JSON for everything.`));
    shown.forEach((m) => parts.push(messageNode(m)));
    return el("div", null, parts);
  }

  function renderResponse(resp) {
    if (typeof resp !== "object" || resp === null) return el("div", { class: "body" }, code(resp));
    const parts = [];
    if (Array.isArray(resp.content)) parts.push(messageNode({ role: "assistant", content: resp.content }));
    else if (Array.isArray(resp.choices)) resp.choices.forEach((c) => parts.push(messageNode(c.message || c.delta || {})));
    else if (Array.isArray(resp.output)) resp.output.forEach((item) => parts.push(messageNode(item)));
    if (resp.error) parts.push(el("div", { class: "msg" }, el("div", { class: "role" }, "error"), code(resp.error)));
    const extra = Object.fromEntries(Object.entries(resp).filter(([k]) => !["content", "choices", "output"].includes(k)));
    parts.push(el("div", { class: "msg" }, el("details", null, el("summary", null, "Response details (usage, ids, stop reason)"), code(extra))));
    return el("div", null, parts);
  }

  function messageNode(m) {
    if (!m || typeof m !== "object") return el("div", { class: "msg" }, code(m));
    const type = m.type || "message";
    const role = m.role || (type === "message" ? "message" : type.replace(/_/g, " "));
    const cls = "msg " + (m.role === "user" ? "user" : m.role === "assistant" ? "assistant" : "");
    const body = [];
    if (type === "message" || m.role) {
      if (typeof m.content === "string") body.push(longText(m.content));
      else if (Array.isArray(m.content)) m.content.forEach((b) => body.push(blockNode(b)));
      if (Array.isArray(m.tool_calls)) m.tool_calls.forEach((c) => body.push(toolCall((c.function || {}).name, (c.function || {}).arguments)));
      if (m.role === "tool") body.length || body.push(code(m));
    }
    if (type === "function_call") body.push(toolCall(m.name, m.arguments));
    else if (type === "custom_tool_call") body.push(toolCall(m.name, m.input));
    else if (type === "local_shell_call") body.push(toolCall("shell", m.action));
    else if (type.endsWith("_output")) body.push(el("div", { class: "block" }, el("div", { class: "tag" }, "Tool result"), code(typeof m.output === "string" ? m.output : m.output ?? m, 4000)));
    else if (type === "reasoning") body.push(el("div", { class: "hint" }, (m.summary || []).map((x) => x.text).join("\n") || "Reasoning (kept private by the provider)"));
    else if (type === "additional_tools") body.push(el("div", { class: "hint" }, "Tool definitions"));
    else if (!m.role && type !== "message") body.push(code(m));
    return el("div", { class: cls }, el("div", { class: "role" }, role), body);
  }

  function toolCall(name, input) {
    let parsed = input;
    if (typeof input === "string" && input.trim().startsWith("{")) {
      try { parsed = JSON.parse(input); } catch (e) { /* leave as text */ }
    }
    return el("div", { class: "block" }, el("div", { class: "tag" }, "Tool call · " + (name || "?")), code(parsed, 4000));
  }

  function blockNode(b) {
    if (typeof b === "string") return longText(b);
    if (!b || typeof b !== "object") return code(b);
    switch (b.type) {
      case "text": case "input_text": case "output_text":
        return el("div", { class: "block" }, longText(b.text || ""));
      case "tool_use": case "server_tool_use": case "mcp_tool_use":
        return toolCall(b.name, b.input);
      case "tool_result": case "web_search_tool_result": case "mcp_tool_result": {
        const c = b.content;
        const text = typeof c === "string" ? c : Array.isArray(c) ? c.map((x) => (x && x.text) || JSON.stringify(x)).join("\n") : JSON.stringify(c, null, 2);
        return el("div", { class: "block" }, el("div", { class: "tag" }, "Tool result" + (b.is_error ? " · error" : "")), code(text || "", 4000));
      }
      case "thinking": case "redacted_thinking":
        return el("div", { class: "block hint" }, b.thinking ? longText(b.thinking, 1200) : "Thinking (not shown by the provider)");
      case "image": case "input_image": case "image_url":
        return el("div", { class: "block" }, SUI.badge("image", "info"), " ", el("span", { class: "faint" }, (b.source && b.source.media_type) || ""));
      case "document": case "input_file": case "file":
        return el("div", { class: "block" }, SUI.badge("document", "info"), " ", el("span", { class: "faint" }, (b.title || (b.source && b.source.media_type) || "")));
      default:
        return el("div", { class: "block" }, code(b, 3000));
    }
  }

  // ------------------------------------------------------------------ the session

  async function pageSession(params, sid) {
    await A.toolIndex().catch(() => null);
    const s = await api("GET", "/sessions/" + encodeURIComponent(sid));
    const devices = [...new Map(s.items.filter((r) => r.key_id).map((r) => [r.key_id, r.device])).entries()];
    const turns = s.items.map((r) => el("li", { class: "step session-step o-" + r.outcome },
      el("div", { class: "step-time u-num" }, fmt.clock(r.ts, true)),
      el("div", { class: "step-dot", "aria-hidden": "true" }, icon(r.prompt ? "send" : r.agent ? "bot" : "spark")),
      el("div", { class: "step-body" },
        el("div", { class: "step-title row" }, r.prompt ? "Prompt" : r.agent ? "Sub-agent" : "Agent step", A.agentBadges(r), el("span", { class: "grow" }),
          r.outcome !== "ok" ? A.outcomeStatus("request", r.outcome, true) : null),
        r.prompt ? el("div", { class: "bubble" }, r.prompt) : null,
        A.actionsList(r.actions),
        r.reply ? el("div", { class: "said" }, r.reply) : null,
        r.outcome !== "ok" && r.reason ? el("p", { class: "ev-reason" }, r.reason) : null,
        el("div", { class: "ev-meta" }, el("span", { class: "mono faint" }, r.model || ""), el("span", { class: "faint" }, fmt.tokens(A.totalTokens(r)) + " tokens"),
          el("span", { class: "u-num" }, fmt.money(r.cost)), el("a", { class: "obj", href: "#/records/" + r.id }, "Full record", icon("chevronRight"))))));
    A.frame({
      title: "Session", crumbs: [el("a", { href: "#/activity" }, "Activity"), s.person_id ? el("a", { href: "#/people/" + s.person_id }, s.person) : null].filter(Boolean),
      lede: `${SUI.plural(s.items.length, "request")} in one conversation with ${s.client || "a tool"} — every typed prompt, then everything the agent did, in order.`,
    }, [
      A.panel(null, null, el("div", { class: "facts" },
        fact("Person", A.personLink(s.person_id, s.person)), fact("Application", s.client || "—"),
        fact("Device", devices.length ? el("span", { class: "row" }, devices.map(([k, label]) => A.deviceLink(k, label))) : "—"),
        fact("Started", fmt.stamp(s.started)), fact("Last request", fmt.stamp(s.last)),
        fact("Lasted", fmt.dur(s.last - s.started)), fact("Requests", String(s.items.length)),
        fact("Cost", fmt.money(s.cost), "Estimated from the price table"),
        fact("Session id", el("span", { class: "mono" }, s.session)))),
      A.panel("Everything that happened", "times in " + SUI.tzLabel(true), el("ol", { class: "steps" }, turns)),
    ]);
  }

  A.page(/^#\/records\/(\d+)$/, pageRecord);
  A.page(/^#\/sessions\/(.+)$/, pageSession);
})();
