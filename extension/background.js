/* Swangz AI Hub Access — service worker.
 *
 * What it does: it governs which AI websites are open to you. When you open an AI site that Swangz
 * governs, it asks the Hub whether that tool is turned on for you. If yes, the site opens normally. If
 * not, it shows a page explaining why and offers to request access. It records which tool, when, and
 * for how long — nothing else.
 *
 * It never reads page content or what you type. It never signs you out of a site either: your sign-ins
 * to the AI tools stay exactly as they are, including when Chrome is closed and reopened. Signing out
 * of this extension ends only its own Hub session.
 *
 * Only the hosts the Hub lists (the company's AI tools) are ever checked. Every other site is ignored
 * completely. */

const S = { base: null, token: null, hosts: {}, policy: "", open: {} };
let signingOut = null;

async function loadConfig() {
  if (signingOut) await signingOut;
  const stored = await chrome.storage.local.get(["base", "token", "hosts", "policy"]);
  Object.assign(S, { base: null, token: null, hosts: {}, policy: "" }, stored);
  return !!(S.base && S.token);
}

async function authenticatedFetch(path, options = {}) {
  if (!S.base || !S.token) return null;
  const base = S.base, token = S.token;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(base + "/api/gate/" + path, {
      ...options, signal: controller.signal,
      headers: { "authorization": "Bearer " + token, "x-swangz-app": "1", ...options.headers },
    });
    if (S.base !== base || S.token !== token) return null;
    if (res.status === 401 || res.status === 403) { await signOut(); return null; }
    if (!res.ok) return null;
    const data = await res.json();
    return S.base === base && S.token === token ? data : null;
  } finally { clearTimeout(timeout); }
}

async function refreshHosts() {
  if (!S.base || !S.token) return;
  try {
    const data = await authenticatedFetch("config");
    if (!data) return;
    if (!data.hosts || typeof data.hosts !== "object" || Array.isArray(data.hosts)) return;
    S.hosts = data.hosts;
    S.policy = data.policy || "";
    await chrome.storage.local.set({ hosts: S.hosts, policy: S.policy });
    updateBadge(true);
  } catch (e) { /* offline; keep the cached host list */ }
}

/* Versions before 1.2.0 handed out shared company accounts a turn at a time: they kept a "holding" list and
   a per-minute "turns" alarm that signed the browser out of a site when a turn ended. Turns are gone, so
   drop what an older version left behind — that list and that alarm, nothing else. */
async function forgetTurns() {
  try {
    const left = await chrome.storage.local.get(["holding"]);
    if ("holding" in left) await chrome.storage.local.remove("holding");
  } catch (e) { /* best effort: nothing reads it any more */ }
  try { await chrome.alarms.clear("turns"); } catch (e) { /* best effort: nothing listens for it */ }
}

function hostnameOf(url) {
  try { const u = new URL(url); return ["http:", "https:"].includes(u.protocol) ? u.hostname.toLowerCase() : null; }
  catch (e) { return null; }
}

function governed(hostname) {
  if (!hostname) return null;
  const h = hostname.startsWith("www.") ? hostname.slice(4) : hostname;
  for (const key of Object.keys(S.hosts)) {
    if (h === key || h.endsWith("." + key)) return key;
  }
  return null;
}

async function gate(path, body) {
  return authenticatedFetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function blockForSignIn(tabId) {
  await endTab(tabId);  // the tab is leaving whatever it had open
  const params = new URLSearchParams({ signin: "1", app: S.base || "" });
  return chrome.tabs.update(tabId, { url: chrome.runtime.getURL("blocked.html") + "#" + params });
}

async function onNavigate(tabId, url) {
  await ready;
  const host = hostnameOf(url);
  const key = governed(host);
  if (!key) { await endTab(tabId); return; }
  // Moving to a different tool closes the previous record first, before anything new is stored or asked.
  if (S.open[tabId] && S.open[tabId].tool !== S.hosts[key]) await endTab(tabId);
  if (!S.base || !S.token) { await blockForSignIn(tabId); return; }
  let r;
  try { r = await gate("open", { host }); } catch (e) { /* unavailable: no allow decision */ }
  if (!S.token || !r) { await blockForSignIn(tabId); return; }
  if (r.known === false) {
    await endTab(tabId);  // the tab left the tool it had open: stop that record before anything else can fail
    await refreshHosts();  // authenticated removal from governance; refresh the stale cache
    if (!S.token) await blockForSignIn(tabId);
    return;
  }
  if (!r.known) { await blockForSignIn(tabId); return; }
  if (r.allowed === true) {
    if (S.open[tabId]) {
      // Same tool, new address in the same tab: keep the record already running. The server started one for this
      // check too, so close that one straight away rather than leave a duplicate open-ended.
      try { await gate("close", { id: r.id, seconds: 0 }); } catch (e) { /* will be left open-ended */ }
      return;
    }
    S.open[tabId] = { id: r.id, since: Date.now(), tool: S.hosts[key] };
    await chrome.storage.session?.set?.({ ["open_" + tabId]: S.open[tabId] }).catch(() => {});
  } else {
    await endTab(tabId);  // refused: the tab is about to show the blocked page, so nothing stays open
    const params = new URLSearchParams({ tool: r.tool || "This tool", reason: r.reason || "",
      app: r.app_url || S.base, tool_id: r.tool_id || "", pending: r.pending ? "1" : "", report: r.report_gate ? String(r.report_gate.report_id) : "" });
    chrome.tabs.update(tabId, { url: chrome.runtime.getURL("blocked.html") + "#" + params.toString() });
  }
}

async function endTab(tabId) {
  const rec = S.open[tabId];
  if (!rec) return;
  delete S.open[tabId];
  try { await chrome.storage.session?.remove?.("open_" + tabId); } catch (e) { /* best effort */ }
  const seconds = Math.round((Date.now() - rec.since) / 1000);
  try { await gate("close", { id: rec.id, seconds }); } catch (e) { /* will be left open-ended */ }
}

// Tell the Hub to end this extension session, so the token is dead there too and not only forgotten here.
// Best effort and never a condition: it starts after the local token is gone, nothing waits for it, it gives up
// after 5 seconds, and its answer (or failure, or a Hub that is unreachable) changes nothing about being signed out.
async function endServerSession(base, token) {
  if (!base || !token) return;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    await fetch(base + "/api/logout", { method: "POST", signal: controller.signal, credentials: "omit",
      headers: { "authorization": "Bearer " + token, "x-swangz-app": "1", "content-type": "application/json" }, body: "{}" });
  } catch (e) { /* the session then ends at its own expiry */ } finally { clearTimeout(timeout); }
}

async function signOut() {
  if (signingOut) return signingOut;
  signingOut = (async () => {
    const base = S.base, token = S.token;
    S.token = null; S.open = {};  // from here every decision is "not signed in", whatever the server answers
    await chrome.storage.local.remove("token");
    endServerSession(base, token);  // not awaited: local sign-out never waits for the Hub
    // Keep base/hosts/policy to guard known sites and offer the correct sign-in. No site data is touched:
    // this ends the extension's Hub session only, never anyone's sign-in to an AI tool.
    updateBadge(false);
  })();
  try { await signingOut; } finally { signingOut = null; }
}

function updateBadge(on) {
  chrome.action.setBadgeText({ text: on ? "" : "!" });
  chrome.action.setBadgeBackgroundColor({ color: on ? "#4E9E6A" : "#B3564E" });
  chrome.action.setTitle({ title: on ? "Swangz AI Hub Access — signed in" : "Swangz AI Hub Access — sign in" });
}

chrome.runtime.onInstalled.addListener(() => { loadConfig().then(refreshHosts); });
// Chrome was closed and reopened: fetch the current list of governed sites. Site sign-ins carry across untouched.
chrome.runtime.onStartup.addListener(() => { loadConfig().then(refreshHosts); });
chrome.alarms.create("refresh", { periodInMinutes: 30 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "refresh") loadConfig().then(refreshHosts);
});

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "loading" && info.url) onNavigate(tabId, info.url);
  else if (info.url) onNavigate(tabId, info.url);
});
chrome.tabs.onRemoved.addListener((tabId) => endTab(tabId));

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    await ready;
    if (msg.type === "status") {
      await loadConfig();
      await refreshHosts();  // asks the Hub, so a revoked or paused account shows as signed out here too
      reply({ signedIn: !!(S.base && S.token), base: S.base, policy: S.policy, count: Object.keys(S.hosts).length });
    }
    else if (msg.type === "signin") { await chrome.storage.local.set({ base: msg.base, token: msg.token, policy: msg.policy || "" }); S.base = msg.base; S.token = msg.token; S.policy = msg.policy || ""; await refreshHosts(); reply({ ok: true }); }
    else if (msg.type === "signout") { await signOut(); reply({ ok: true }); }
    else reply({});
  })();
  return true;
});

const ready = loadConfig();
ready.then(updateBadge);
forgetTurns();
