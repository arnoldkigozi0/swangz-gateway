"use strict";
const p = new URLSearchParams(location.hash.slice(1));
const tool = p.get("tool") || "This tool";
const app = p.get("app") || "";
const toolId = p.get("tool_id") || "";
const needsSignIn = p.get("signin") === "1";
document.getElementById("title").textContent = needsSignIn ? "Sign in to Swangz AI Hub" : `${tool} isn't enabled for you`;
document.getElementById("reason").textContent = needsSignIn
  ? "Open the extension sign-in page to connect. If the Hub is offline, try again when it is available. This site stays blocked until access is confirmed."
  : p.get("reason") || "Ask an admin to turn it on for you.";
const actions = document.getElementById("actions");
const done = document.getElementById("done");

function btn(label, cls, onclick, href) {
  if (href) { const a = document.createElement("a"); a.className = "btn " + cls; a.textContent = label; a.href = href; a.target = "_blank"; a.rel = "noopener"; return a; }
  const b = document.createElement("button"); b.className = cls; b.textContent = label; b.onclick = onclick; return b;
}

if (needsSignIn) {
  actions.append(btn("Sign in to Swangz AI Hub", "primary", null, chrome.runtime.getURL("popup.html")));
} else if (p.get("report") && app) {
  actions.append(btn("Complete weekly report", "primary", null, app.replace(/\/+$/, "") + "/#/weekly?report=" + encodeURIComponent(p.get("report"))));
} else if (p.get("pending")) {
  done.innerHTML = '<p class="ok">You\'ve already asked for this — an admin will see it.</p>';
} else if (app && toolId) {
  const ask = btn("Request access", "primary", async () => {
    ask.disabled = true; ask.textContent = "Sending…";
    try {
      const { token } = await chrome.storage.local.get("token");
      const res = await fetch(app.replace(/\/+$/, "") + "/api/tools/" + encodeURIComponent(toolId) + "/request", {
        method: "POST", headers: { "authorization": "Bearer " + token, "x-swangz-app": "1", "content-type": "application/json" },
        body: JSON.stringify({ reason: "" }),
      });
      if (!res.ok) throw new Error();
      done.innerHTML = '<p class="ok">Request sent. An admin will see it.</p>';
      actions.replaceChildren();
    } catch (e) { ask.disabled = false; ask.textContent = "Request access"; }
  });
  actions.append(ask);
}
if (app) actions.append(btn("Open Swangz AI Hub", "ghost", null, app));
actions.append(btn("Go back", "ghost", () => history.length > 1 ? history.back() : window.close()));
