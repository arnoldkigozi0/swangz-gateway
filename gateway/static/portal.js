"use strict";
/* Swangz AI — the staff app: sign in, connect a tool, look after your devices. */
(() => {
  const app = document.getElementById("app");
  const S = { me: null };

  // ------------------------------------------------------------------ helpers

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (k === "value") node.value = v;
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  function svg(paths, size) {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("fill", "none");
    s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", "2");
    s.setAttribute("stroke-linecap", "round");
    s.setAttribute("stroke-linejoin", "round");
    if (size) { s.setAttribute("width", size); s.setAttribute("height", size); }
    paths.forEach((d) => { const p = document.createElementNS(ns, "path"); p.setAttribute("d", d); s.append(p); });
    return s;
  }
  const GLYPHS = { "claude-code": "CC", codex: "CX", "anthropic-sdk": "{ }", "openai-compatible": "AI" };
  const ICON_DEVICE = ["M4 5h16v11H4z", "M2 20h20", "M9 16v4", "M15 16v4"];

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  async function api(method, path, body) {
    const opts = { method, credentials: "same-origin", headers: { "x-swangz-app": "1" } };
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch("/api" + path, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) throw new ApiError(res.status, (data && data.error) || "Something went wrong. Try again.");
    return data;
  }

  function toast(message, bad) {
    const t = el("div", { class: "toast" + (bad ? " bad" : ""), role: "status" }, message);
    document.body.append(t);
    setTimeout(() => t.remove(), bad ? 6000 : 2600);
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied"); }
    catch (e) { toast("Couldn't copy here — select the text and copy it.", true); }
  }

  const money = (v) => (v || 0) < 0.01 && v > 0 ? "<$0.01" : "$" + (v || 0).toFixed(2);
  function ago(ts) {
    if (!ts) return "never";
    const s = Date.now() / 1000 - ts;
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    if (s < 86400 * 30) return Math.round(s / 86400) + " days ago";
    return new Date(ts * 1000).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
  }
  function greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  }
  const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

  function passwordInput(autocomplete) {
    const input = el("input", { class: "input", type: "password", autocomplete, required: true, minlength: autocomplete === "new-password" ? "10" : null });
    const reveal = el("button", { class: "btn btn--quiet reveal", type: "button", "aria-label": "Show password",
      onclick: () => { const shown = input.type === "text"; input.type = shown ? "password" : "text"; reveal.textContent = shown ? "Show" : "Hide"; } }, "Show");
    return { input, node: el("div", { class: "input-wrap" }, input, reveal) };
  }

  function codeBlock(text) {
    return el("div", { class: "code" }, el("pre", null, text), el("button", { class: "btn", type: "button", onclick: () => copy(text) }, "Copy"));
  }

  function dialog(title, text, actions) {
    const d = el("dialog", null, el("div", { class: "d-body" }, el("h2", null, title), typeof text === "string" ? el("p", null, text) : text),
      el("div", { class: "d-actions" }, actions(() => d.close())));
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    return d;
  }

  // ------------------------------------------------------------------ gate (sign in, welcome)

  function gateArt() {
    return el("section", { class: "gate-art" },
      el("a", { class: "wordmark", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz ", el("b", null, "AI")),
      el("div", null,
        el("h1", { class: "gate-title" }, "Every AI tool. ", el("em", null, "One sign-in.")),
        el("p", { class: "gate-lede" }, "Claude, Codex and the rest — set up for your work at Swangz. No personal subscriptions, no accounts to juggle."),
        el("div", { class: "tool-row" }, ["Claude Code", "Codex", "Cursor", "Your scripts"].map((t) => el("span", null, t)))),
      el("div", { class: "gate-foot" }, "Swangz Avenue"));
  }

  function showSignIn() {
    const email = el("input", { class: "input", type: "email", autocomplete: "email", required: true });
    const pw = passwordInput("current-password");
    const err = el("div", { class: "form-error", role: "alert" });
    const go = el("button", { class: "btn btn--solid btn--block", type: "submit" }, "Sign in");
    const form = el("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        go.disabled = true;
        err.textContent = "";
        try {
          await api("POST", "/login", { email: email.value, password: pw.input.value });
          await load();
        } catch (x) { err.textContent = x.message; go.disabled = false; }
      },
    },
    el("div", null, el("div", { class: "eyebrow" }, "Welcome back"), el("h2", null, "Sign in to Swangz AI")),
    el("label", { class: "field" }, el("span", null, "Work email"), email),
    el("label", { class: "field" }, el("span", null, "Password"), pw.node),
    err, go,
    el("p", { class: "muted" }, "First time? Your admin sends you a sign-in link. Forgot your password? Ask them for a new link."));
    app.replaceChildren(el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" }, form)));
    email.focus();
  }

  async function showWelcome(token) {
    let invite;
    try {
      invite = await api("GET", "/welcome/" + encodeURIComponent(token));
    } catch (e) {
      const form = el("form", null, el("div", { class: "eyebrow" }, "Sign-in link"), el("h2", null, "This link has run out"),
        el("p", { class: "muted" }, e.message), el("a", { class: "btn", href: "#/" }, "Go to sign in"));
      app.replaceChildren(el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" }, form)));
      return;
    }
    const pw = passwordInput("new-password");
    const again = passwordInput("new-password");
    const err = el("div", { class: "form-error", role: "alert" });
    const go = el("button", { class: "btn btn--solid btn--block", type: "submit" }, invite.has_password ? "Set new password" : "Set password and continue");
    const form = el("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        if (pw.input.value.length < 10) { err.textContent = "Use at least 10 characters."; return; }
        if (pw.input.value !== again.input.value) { err.textContent = "The two passwords don't match."; return; }
        go.disabled = true;
        try {
          await api("POST", "/welcome", { token, password: pw.input.value });
          history.replaceState(null, "", location.pathname);
          await load();
          toast("You're in. Connect your first tool below.");
        } catch (x) { err.textContent = x.message; go.disabled = false; }
      },
    },
    el("div", null, el("div", { class: "eyebrow" }, invite.has_password ? "Reset your password" : "Welcome"),
      el("h2", null, invite.has_password ? "Choose a new password" : `Hi ${invite.name}, let's set you up`)),
    el("p", { class: "muted" }, `You'll sign in with ${invite.email}.`),
    el("label", { class: "field" }, el("span", null, "Choose a password (10+ characters)"), pw.node),
    el("label", { class: "field" }, el("span", null, "Type it again"), again.node),
    err, go);
    app.replaceChildren(el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" }, form)));
    pw.input.focus();
  }

  // ------------------------------------------------------------------ home

  function render() {
    const me = S.me;
    const menu = el("div", { class: "menu", role: "menu" },
      el("div", { class: "who" }, el("div", null, me.name), el("div", null, me.email)),
      el("button", { onclick: changePassword, role: "menuitem" }, "Change password"),
      el("button", { onclick: signOut, role: "menuitem" }, "Sign out"));
    const meBtn = el("button", { class: "me-btn", "aria-haspopup": "menu", onclick: (e) => { e.stopPropagation(); menu.classList.toggle("open"); } },
      el("span", { class: "avatar" }, initials(me.name)), el("span", { class: "me-name" }, me.name));
    document.addEventListener("click", () => menu.classList.remove("open"));

    const topbar = el("header", { class: "topbar" }, el("div", { class: "inner" },
      el("a", { class: "wordmark", href: "#/" }, el("img", { src: "/static/icon.svg", alt: "" }), "Swangz ", el("b", null, "AI")),
      el("div", { class: "me-menu" }, meBtn, menu)));

    const statusText = me.active ? "Your AI access is on" : me.suspended ? "Your access is paused — talk to your admin" : "AI access is paused for everyone right now";
    const b = me.budget;
    const monthStat = el("div", { class: "stat" }, el("div", { class: "eyebrow" }, "This month"),
      el("div", { class: "big" }, money(b.month)),
      el("div", { class: "note" }, b.monthly !== null ? `of your ${money(b.monthly)} monthly allowance` : "No monthly limit"),
      b.monthly !== null ? meter(b.month, b.monthly) : null);
    const todayStat = el("div", { class: "stat" }, el("div", { class: "eyebrow" }, "Today"),
      el("div", { class: "big" }, money(b.today)),
      el("div", { class: "note" }, b.daily !== null ? `of ${money(b.daily)} a day` : "No daily limit"),
      b.daily !== null ? meter(b.today, b.daily) : null);
    const live = me.keys.filter((k) => !k.revoked);
    const devStat = el("div", { class: "stat" }, el("div", { class: "eyebrow" }, "Devices connected"),
      el("div", { class: "big" }, String(live.length)),
      el("div", { class: "note" }, live.length ? "last used " + ago(Math.max(...live.map((k) => k.last_used || 0)) || null) : "Connect a tool to get started"));

    const hero = el("section", { class: "hero" }, el("div", { class: "shell" },
      el("div", { class: "status" + (me.active ? "" : " off") }, el("i"), statusText),
      el("h1", null, `${greeting()}, ${me.name}.`),
      el("p", { class: "muted", style: null }, [me.title, me.department].filter(Boolean).join(" · ") || "Swangz Avenue"),
      el("div", { class: "stats" }, monthStat, todayStat, devStat),
      b.monthly !== null && b.month >= b.monthly ? el("div", { class: "notice" }, "You've used this month's allowance. It resets on the 1st — or ask your admin for more.") : null));

    const tools = el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Step 1"), el("h2", null, "Connect a tool"),
        el("p", null, "Pick the tool you want to use. You get a key for that device and the exact lines to paste — about a minute."))),
      el("div", { class: "tools" }, me.tools.map((t) => el("article", { class: "tool" },
        el("div", { class: "glyph" }, GLYPHS[t.id] || initials(t.name)),
        el("div", null, el("div", { class: "kind" }, t.kind), el("h3", null, t.name)),
        el("p", null, t.blurb),
        el("div", null, me.can_add_keys
          ? el("button", { class: "btn btn--small", onclick: () => connect(t) }, "Connect")
          : el("span", { class: "muted", style: null }, me.active ? "Ask your admin to connect this for you" : "Unavailable while access is paused")))))));

    const deviceList = me.keys.length ? el("div", { class: "devices" }, me.keys.map((k) => el("div", { class: "device" + (k.revoked ? " off" : "") },
      el("div", { class: "dot" }, svg(ICON_DEVICE)),
      el("div", null, el("strong", null, k.label), el("div", { class: "meta" },
        el("span", { class: "mono" }, k.hint), " · ", k.revoked ? "disconnected " + ago(k.revoked) : `connected ${ago(k.created)} · last used ${ago(k.last_used)}`)),
      k.revoked ? el("span", { class: "muted" }, "Disconnected") : el("button", { class: "btn btn--danger btn--small", onclick: () => disconnect(k) }, "Disconnect"))))
      : el("div", { class: "empty" }, "No devices yet. Connect a tool above and it will show up here.");

    const devices = el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Step 2"), el("h2", null, "Your devices"),
        el("p", null, "Each laptop or tool has its own key. Lost a laptop, or stopped using a tool? Disconnect it here — the others keep working."))),
      deviceList));

    const models = el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Models"), el("h2", null, "What you can use"))),
      me.models.length ? el("div", { class: "chips" }, me.models.map((m) => el("span", { class: "chip" }, m)))
        : el("p", { class: "muted", style: null }, "Every model Swangz offers — Claude and OpenAI models included.")));

    const tips = el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Good to know"), el("h2", null, "Keep it simple"))),
      el("div", { class: "tips" },
        tip("One key per device", "Connect your laptop and your work PC separately. Each gets its own key."),
        tip("Your key is yours", "Don't share it or paste it into chats. If it leaks, disconnect that device and connect it again."),
        tip("Stuck?", "If a tool says your key isn't valid or access is paused, your admin can sort it out in a minute."))));

    const foot = el("footer", { class: "foot" }, el("div", { class: "inner" },
      el("span", null, "Swangz Avenue · Swangz AI"),
      el("button", { onclick: policy }, "Usage policy")));

    const studio = S.studio && (S.studio.voice || S.studio.image || S.studio.video) && me.active ? studioSection() : null;
    app.replaceChildren(topbar, el("main", null, hero, studio, tools, devices, models, tips), foot);
    resumeJobs();
  }

  // ------------------------------------------------------------------ Studio: voice, image, video

  const TYPE_LABEL = { voice: "Voice-over", image: "Image", video: "Video", sound: "Sound", music: "Music", transcription: "Transcript" };
  const JOBS = new Map();

  function studioSection() {
    const st = S.studio;
    const tabs = [["voice", "Voice", st.voice], ["image", "Image", st.image], ["video", "Video", st.video]].filter((t) => t[2]);
    const panel = el("div", { class: "studio-panel" });
    const tabBar = el("div", { class: "tabs", role: "tablist" }, tabs.map(([id, label]) =>
      el("button", { class: "tab", role: "tab", type: "button", "data-tab": id, onclick: () => show(id) }, label)));
    const creations = el("div", { class: "creations" });

    function show(id) {
      tabBar.querySelectorAll(".tab").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === id ? "true" : "false"));
      panel.replaceChildren(id === "voice" ? voiceForm() : visualForm(id));
    }

    function voiceForm() {
      const voice = el("select", { class: "input" }, st.voices.map((v) => el("option", { value: v.id }, v.name + (v.about ? ` — ${v.about}` : ""))));
      const model = el("select", { class: "input" }, st.voice_models.map((m) => el("option", { value: m.id }, m.name)));
      const text = el("textarea", { class: "input area", rows: "5", maxlength: "5000", placeholder: "Type the script — for example: Swangz Avenue presents the December Showcase, live at Serena Kampala." });
      const count = el("span", { class: "muted small" }, "0 / 5,000");
      text.addEventListener("input", () => { count.textContent = `${text.value.length.toLocaleString()} / 5,000`; });
      const err = el("div", { class: "form-error" });
      const go = el("button", { class: "btn btn--solid", type: "submit" }, "Make the voice-over");
      return el("form", { class: "studio-form", onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        go.disabled = true;
        go.textContent = "Making it…";
        try {
          const made = await api("POST", "/studio/voice", { text: text.value, voice_id: voice.value, model_id: model.value });
          addCreation(made, true);
          text.value = "";
          count.textContent = "0 / 5,000";
        } catch (x) { err.textContent = x.message; }
        go.disabled = false;
        go.textContent = "Make the voice-over";
      } },
      st.voices.length ? null : el("div", { class: "notice" }, "No voices are available yet — ask your admin."),
      el("div", { class: "form-row" }, el("label", { class: "field" }, el("span", null, "Voice"), voice), el("label", { class: "field" }, el("span", null, "Quality"), model)),
      el("label", { class: "field" }, el("span", null, "Script"), text), el("div", { class: "spread" }, count, go), err);
    }

    function visualForm(kind) {
      const prompt = el("textarea", { class: "input area", rows: "4", placeholder: kind === "image"
        ? "Describe the picture — for example: a moody poster of a live band on stage at night, Kampala skyline behind, warm amber lights."
        : "Describe the motion — for example: slow push-in on the singer, haze drifting, lights flicker." });
      const aspect = el("select", { class: "input" }, ["16:9", "9:16", "1:1", "4:5"].map((a) => el("option", { value: a }, a)));
      const image = el("input", { class: "input", type: "url", placeholder: "https://… link to the starting picture" });
      const err = el("div", { class: "form-error" });
      const label = kind === "image" ? "Make the image" : "Make the video";
      const go = el("button", { class: "btn btn--solid", type: "submit" }, label);
      return el("form", { class: "studio-form", onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        go.disabled = true;
        go.textContent = "Starting…";
        try {
          const made = await api("POST", "/studio/generate", { kind, prompt: prompt.value, aspect_ratio: aspect.value, image_url: image.value });
          addCreation(made, true);
          prompt.value = "";
        } catch (x) { err.textContent = x.message; }
        go.disabled = false;
        go.textContent = label;
      } },
      kind === "video" ? el("label", { class: "field" }, el("span", null, "Starting picture"), image,
        el("span", { class: "muted small" }, "Make an image first and copy its link, or use any picture that's online.")) : null,
      el("label", { class: "field" }, el("span", null, kind === "image" ? "What should it show?" : "What should happen?"), prompt),
      el("div", { class: "spread" }, kind === "image" ? el("label", { class: "field inline" }, el("span", null, "Shape"), aspect) : el("span"), go), err);
    }

    function addCreation(c, fresh) {
      const card = creationCard(c);
      if (fresh) card.classList.add("fresh");
      creations.prepend(card);
      empty.hidden = true;
      if (c.job && !c.urls.length && c.outcome === "ok") JOBS.set(c.job, card);
      if (fresh) resumeJobs();
    }

    const empty = el("p", { class: "muted" }, "What you make shows up here, so you can play it again or download it.");
    st.recent.slice().reverse().forEach((c) => addCreation(c, false));
    empty.hidden = st.recent.length > 0;
    setTimeout(() => show(tabs[0][0]), 0);

    return el("section", { class: "section" }, el("div", { class: "shell" },
      el("div", { class: "section-head" }, el("div", null, el("div", { class: "eyebrow" }, "Create"), el("h2", null, "Make it here"),
        el("p", null, "Voice-overs, images and video in the browser — nothing to install, nothing to pay."))),
      el("div", { class: "studio" }, tabBar, panel),
      el("h3", { class: "sub-head" }, "Recent creations"), empty, creations));
  }

  function creationCard(c) {
    const body = el("div", { class: "creation-media" });
    fillCreation(body, c);
    return el("article", { class: "creation", "data-id": String(c.id) },
      body,
      el("div", { class: "creation-meta" },
        el("div", { class: "spread" }, el("span", { class: "eyebrow" }, TYPE_LABEL[c.type] || "Creation"), el("span", { class: "muted small" }, ago(c.ts))),
        c.prompt ? el("p", { class: "creation-prompt" }, c.prompt) : null));
  }

  function fillCreation(body, c) {
    if (c.outcome && c.outcome !== "ok") {
      body.replaceChildren(el("div", { class: "creation-state bad" }, c.reason || "This one didn't work."));
    } else if (c.audio) {
      body.replaceChildren(el("audio", { controls: true, preload: "none", src: c.audio }),
        el("a", { class: "btn btn--small", href: c.audio, download: "swangz-voice-" + c.id + ".mp3" }, "Download"));
    } else if (c.urls && c.urls.length) {
      const u = c.urls[0];
      const media = c.type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(u)
        ? el("video", { controls: true, preload: "metadata", src: u, playsinline: true })
        : el("img", { src: u, alt: c.prompt || "Generated image", loading: "lazy" });
      body.replaceChildren(media, el("a", { class: "btn btn--small", href: u, target: "_blank", rel: "noopener noreferrer" }, "Open full size"));
    } else {
      body.replaceChildren(el("div", { class: "creation-state" }, el("span", { class: "spinner", "aria-hidden": "true" }), "Working on it — usually under a minute."));
    }
  }

  let polling = false;
  async function resumeJobs() {
    if (polling) return;
    polling = true;
    while (JOBS.size) {
      await new Promise((r) => setTimeout(r, 3000));
      for (const [job, card] of [...JOBS]) {
        if (!card.isConnected) { JOBS.delete(job); continue; }
        try {
          const c = await api("GET", "/studio/jobs/" + encodeURIComponent(job));
          if (c.urls.length || ["failed", "nsfw"].includes(c.state)) {
            if (c.state === "nsfw") c.outcome = "error", c.reason = "The service turned this one down for its content.";
            if (c.state === "failed") c.outcome = "error", c.reason = "The service couldn't make this one. Try again.";
            fillCreation(card.querySelector(".creation-media"), c);
            JOBS.delete(job);
          }
        } catch (e) { JOBS.delete(job); }
      }
    }
    polling = false;
  }

  function meter(value, limit) {
    const fill = el("i");
    fill.style.width = Math.min(100, (value / (limit || 1)) * 100) + "%";
    return el("div", { class: "meter" + (value >= limit ? " full" : "") }, fill);
  }

  function tip(title, text) { return el("div", { class: "tip" }, el("h3", null, title), el("p", null, text)); }

  // ------------------------------------------------------------------ connect a tool

  function connect(tool) {
    const scrim = el("div", { class: "scrim" });
    const body = el("div", { class: "body" });
    const foot = el("footer");
    const drawer = el("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Connect " + tool.name },
      el("header", null, el("div", null, el("div", { class: "eyebrow" }, tool.kind), el("h2", null, "Connect " + tool.name)),
        el("button", { class: "btn btn--quiet", onclick: close, "aria-label": "Close" }, "Close")),
      body, foot);
    let created = false;

    function close() {
      drawer.classList.remove("in");
      scrim.classList.remove("in");
      setTimeout(() => { scrim.remove(); drawer.remove(); }, 320);
      document.removeEventListener("keydown", onKey);
      if (created) load();
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);

    const label = el("input", { class: "input", type: "text", value: `My laptop — ${tool.name}`, maxlength: "80" });
    const err = el("div", { class: "form-error" });
    const make = el("button", { class: "btn btn--solid", onclick: async () => {
      make.disabled = true;
      try {
        const out = await api("POST", "/keys", { label: label.value });
        created = true;
        showSteps(out);
      } catch (e) { err.textContent = e.message; make.disabled = false; }
    } }, "Create my key");
    body.replaceChildren(
      el("div", { class: "step" }, el("div", { class: "n" }, "1"), el("div", null,
        el("h3", null, "Name this device"),
        el("p", null, "So you can tell your devices apart later — for example the laptop and the tool."),
        label, err)));
    foot.replaceChildren(el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"), make);

    function showSteps(out) {
      const guide = out.tools.find((t) => t.id === tool.id) || out.tools[0];
      body.replaceChildren(
        el("div", { class: "step" }, el("div", { class: "n" }, "1"), el("div", null,
          el("h3", null, "Your key for " + out.label),
          el("p", { class: "once" }, "Shown only this once. It's already in the steps below — keep a copy somewhere safe."),
          el("div", { class: "keyline" }, el("code", null, out.key), el("button", { class: "btn", onclick: () => copy(out.key) }, "Copy")))),
        ...guide.steps.map((s, i) => el("div", { class: "step" }, el("div", { class: "n" }, String(i + 2)), el("div", null,
          el("h3", null, s.title), el("p", null, s.how), codeBlock(s.code)))));
      foot.replaceChildren(el("button", { class: "btn btn--solid", onclick: close }, "Done"));
    }

    document.body.append(scrim, drawer);
    requestAnimationFrame(() => { scrim.classList.add("in"); drawer.classList.add("in"); label.focus(); label.select(); });
  }

  function disconnect(k) {
    dialog("Disconnect " + k.label + "?", "Its key stops working straight away. Your other devices keep working, and you can connect this one again at any time.",
      (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
        el("button", { class: "btn btn--danger", onclick: async () => {
          try { await api("POST", `/keys/${k.id}/revoke`); close(); toast("Disconnected."); load(); } catch (e) { toast(e.message, true); }
        } }, "Disconnect")]);
  }

  function changePassword() {
    const cur = passwordInput("current-password");
    const nw = passwordInput("new-password");
    const err = el("div", { class: "form-error" });
    dialog("Change password", el("div", { class: "fields" },
      el("label", { class: "field" }, el("span", null, "Current password"), cur.node),
      el("label", { class: "field" }, el("span", null, "New password (10+ characters)"), nw.node), err),
    (close) => [el("button", { class: "btn btn--quiet", onclick: close }, "Cancel"),
      el("button", { class: "btn btn--solid", onclick: async () => {
        try { await api("POST", "/password", { current: cur.input.value, new: nw.input.value }); close(); toast("Password changed."); } catch (e) { err.textContent = e.message; }
      } }, "Save")]);
  }

  function policy() {
    dialog("Using Swangz AI", el("div", { class: "fields" },
      el("p", null, "Swangz AI is provided for your work at Swangz. Your requests are handled by AI providers on the company's behalf."),
      el("p", null, "Like any company system, use is recorded for security, cost and support. Don't paste passwords, other people's personal details, or anything you wouldn't put in a work email."),
      el("p", null, "Questions? Ask your admin.")),
    (close) => [el("button", { class: "btn btn--solid", onclick: close }, "Got it")]);
  }

  async function signOut() {
    try { await api("POST", "/logout"); } catch (e) { /* signed out anyway */ }
    S.me = null;
    showSignIn();
  }

  // ------------------------------------------------------------------ start

  async function load() {
    try {
      S.me = await api("GET", "/me");
      try { S.studio = await api("GET", "/studio"); } catch (e) { S.studio = null; }
      render();
    } catch (e) {
      if (e.status === 401) showSignIn();
      else app.replaceChildren(el("main", { class: "gate" }, gateArt(), el("section", { class: "gate-form" },
        el("form", null, el("h2", null, "Can't reach Swangz AI"), el("p", { class: "muted" }, e.message), el("button", { class: "btn", type: "button", onclick: load }, "Try again")))));
    }
  }

  function route() {
    const m = (location.hash || "").match(/^#\/welcome\/([A-Za-z0-9_\-]+)$/);
    if (m) return showWelcome(m[1]);
    return load();
  }

  window.addEventListener("hashchange", route);
  route();
})();
