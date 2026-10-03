/* Swangz AI Access — service worker.
 *
 * What it does: when you open an AI website that Swangz governs, it asks the gateway whether that
 * tool is turned on for you. If yes, the site opens normally. If not, it shows a page explaining
 * that and offers to request access. It records which tool, when, and for how long — nothing else.
 * It never reads page content or what you type.
 *
 * It also keeps shared company accounts clean. Some tools are one account the whole team shares, and
 * the portal hands them out a turn at a time. This worker signs the browser out of any shared tool
 * you are not currently holding — when your turn ends, and again every time Chrome starts — by
 * clearing that site's cookies and stored data. So re-opening the tool always means going back
 * through Swangz AI first, and the next person never inherits your session.
 *
 * Only the hosts the gateway lists (the company's AI tools) are ever touched. Every other site is
 * ignored completely. */

const S = { base: null, token: null, hosts: {}, policy: "", open: {}, holding: {} };

async function loadConfig() {
  const stored = await chrome.storage.local.get(["base", "token", "hosts", "policy"]);
  Object.assign(S, stored);
  return !!(S.base && S.token);
}

async function refreshHosts() {
  if (!S.base || !S.token) return;
  try {
    const res = await fetch(S.base + "/api/gate/config", {
      headers: { "authorization": "Bearer " + S.token, "x-swangz-app": "1" },
    });
    if (res.status === 401) { await signOut(); return; }
    if (!res.ok) return;
    const data = await res.json();
    S.hosts = data.hosts || {};
    S.policy = data.policy || "";
    await chrome.storage.local.set({ hosts: S.hosts, policy: S.policy });
    updateBadge(true);
  } catch (e) { /* offline; keep the cached host list */ }
}

/* Sign this browser out of a site: cookies and anything it stored. Chrome clears cookies for the
   whole registrable domain, which is what signs the account out. */
async function signOutOf(hosts) {
  const origins = [];
  for (const h of hosts) origins.push("https://" + h, "https://www." + h);
  if (!origins.length) return;
  try {
    await chrome.browsingData.remove({ origins },
      { cookies: true, localStorage: true, indexedDB: true, cacheStorage: true, serviceWorkers: true });
  } catch (e) { /* the browser refused; the turn still ended on the server */ }
}

/* Ask the gateway which shared tools we still hold. When a turn we had has ended, sign this browser
   out of that tool so the next person starts clean and we have to come back through the portal. */
async function syncTurns() {
  if (!S.base || !S.token) return;
  let data;
  try {
    const res = await fetch(S.base + "/api/gate/turns", {
      headers: { "authorization": "Bearer " + S.token, "x-swangz-app": "1" },
    });
    if (res.status === 401) { await signOut(); return; }
    if (!res.ok) return;
    data = await res.json();
  } catch (e) { return; }  // offline: leave things as they are
  const holding = {};
  for (const t of data.holding || []) holding[t.tool_id] = t.expires;
  const lost = Object.keys(S.holding).filter((id) => !(id in holding));
  S.holding = holding;
  await chrome.storage.local.set({ holding });
  if (!lost.length) return;
  for (const t of data.sign_out || []) {
    if (lost.includes(t.tool_id)) await signOutOf(t.hosts);
  }
}

/* Chrome has just started: the previous session is over, so no shared account carries across. */
async function clearSharedOnStartup() {
  if (!S.base || !S.token) { await chrome.storage.local.set({ holding: {} }); return; }
  try {
    const res = await fetch(S.base + "/api/gate/turns", {
      headers: { "authorization": "Bearer " + S.token, "x-swangz-app": "1" },
    });
    if (!res.ok) return;
    const data = await res.json();
    for (const t of [...(data.sign_out || []), ...(data.holding || [])]) await signOutOf(t.hosts);
  } catch (e) { /* offline */ }
  S.holding = {};
  await chrome.storage.local.set({ holding: {} });
}

function hostnameOf(url) {
  try { const u = new URL(url); return u.protocol.startsWith("http") ? u.hostname.toLowerCase() : null; }
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
  const res = await fetch(S.base + "/api/gate/" + path, {
    method: "POST",
    headers: { "authorization": "Bearer " + S.token, "x-swangz-app": "1", "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 401) { await signOut(); return null; }
  return res.ok ? res.json() : null;
}

async function onNavigate(tabId, url) {
  if (!S.base || !S.token) return;
  const host = hostnameOf(url);
  if (!governed(host)) { endTab(tabId); return; }
  let r;
  try { r = await gate("open", { host }); } catch (e) { return; }
  if (!r || !r.known) return;
  if (r.allowed) {
    S.open[tabId] = { id: r.id, since: Date.now() };
    await chrome.storage.session?.set?.({ ["open_" + tabId]: S.open[tabId] }).catch(() => {});
  } else {
    if (r.state === "no_turn") {
      const key = governed(host);
      if (key) await signOutOf([key]);  // they don't hold the turn: leave nothing signed in
    }
    const params = new URLSearchParams({ tool: r.tool || "This tool", reason: r.reason || "",
      app: r.app_url || S.base, tool_id: r.tool_id || "", pending: r.pending ? "1" : "" });
    chrome.tabs.update(tabId, { url: chrome.runtime.getURL("blocked.html") + "#" + params.toString() });
  }
}

async function endTab(tabId) {
  const rec = S.open[tabId];
  if (!rec) return;
  delete S.open[tabId];
  const seconds = Math.round((Date.now() - rec.since) / 1000);
  try { await gate("close", { id: rec.id, seconds }); } catch (e) { /* will be left open-ended */ }
}

async function signOut() {
  S.base = S.token = null; S.hosts = {}; S.open = {}; S.holding = {};
  await chrome.storage.local.remove(["token", "holding"]);
  updateBadge(false);
}

function updateBadge(on) {
  chrome.action.setBadgeText({ text: on ? "" : "!" });
  chrome.action.setBadgeBackgroundColor({ color: on ? "#4E9E6A" : "#B3564E" });
  chrome.action.setTitle({ title: on ? "Swangz AI Access — signed in" : "Swangz AI Access — sign in" });
}

chrome.runtime.onInstalled.addListener(() => { loadConfig().then(refreshHosts); });
// Chrome was closed and reopened: start every shared account signed out.
chrome.runtime.onStartup.addListener(() => { loadConfig().then(clearSharedOnStartup).then(refreshHosts); });
chrome.alarms.create("refresh", { periodInMinutes: 30 });
chrome.alarms.create("turns", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "refresh") loadConfig().then(refreshHosts);
  if (a.name === "turns") loadConfig().then(syncTurns);
});

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "loading" && info.url) onNavigate(tabId, info.url);
  else if (info.url) onNavigate(tabId, info.url);
});
chrome.tabs.onRemoved.addListener((tabId) => endTab(tabId));

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === "status") {
      await loadConfig();
      await syncTurns();
      reply({ signedIn: !!(S.base && S.token), base: S.base, policy: S.policy, count: Object.keys(S.hosts).length,
        holding: Object.keys(S.holding).length });
    }
    else if (msg.type === "signin") { await chrome.storage.local.set({ base: msg.base, token: msg.token, policy: msg.policy || "" }); S.base = msg.base; S.token = msg.token; S.policy = msg.policy || ""; await refreshHosts(); reply({ ok: true }); }
    else if (msg.type === "signout") { await signOut(); reply({ ok: true }); }
    else reply({});
  })();
  return true;
});

loadConfig().then((ok) => { updateBadge(ok); if (ok) syncTurns(); });
