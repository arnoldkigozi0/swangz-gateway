"use strict";
const body = document.getElementById("body");

function el(tag, props, ...kids) {
  const n = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}

function send(msg) { return new Promise((r) => chrome.runtime.sendMessage(msg, r)); }

async function render() {
  const st = await send({ type: "status" });
  body.replaceChildren();
  if (st && st.signedIn) {
    body.append(
      el("div", { class: "status" }, el("span", { class: "dot" }), "Connected to Swangz AI"),
      el("div", { class: "muted" }, st.base),
      el("div", { class: "muted" }, `Guarding ${st.count} AI site${st.count === 1 ? "" : "s"}.`),
      st.policy ? el("div", { class: "policy" }, st.policy) : null,
      el("button", { class: "ghost", onclick: async () => { await send({ type: "signout" }); render(); } }, "Sign out"));
    return;
  }
  const base = el("input", { type: "url", placeholder: "https://ai.swangz.com", value: st && st.base ? st.base : "" });
  const email = el("input", { type: "email", placeholder: "you@swangzavenue.com" });
  const pass = el("input", { type: "password" });
  const err = el("div", { class: "err" });
  const go = el("button", { onclick: async () => {
    err.textContent = ""; go.disabled = true; go.textContent = "Connecting…";
    const url = base.value.trim().replace(/\/+$/, "");
    try {
      const res = await fetch(url + "/api/extension/login", {
        method: "POST", headers: { "content-type": "application/json", "x-swangz-app": "1" },
        body: JSON.stringify({ email: email.value.trim(), password: pass.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Sign-in failed.");
      await send({ type: "signin", base: url, token: data.token, policy: data.policy });
      render();
    } catch (e) { err.textContent = e.message; go.disabled = false; go.textContent = "Connect"; }
  } }, "Connect");
  body.append(
    el("div", { class: "muted" }, "Sign in with your Swangz AI account to use approved AI sites at work."),
    el("label", null, "Swangz AI address", base),
    el("label", null, "Work email", email),
    el("label", null, "Password", pass),
    err, go);
}

render();
