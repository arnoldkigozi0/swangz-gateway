"use strict";
/* Swangz UI — the primitives both apps build their pages from (styles in ui.css).
   Plain DOM, no framework. Anything a person typed or a tool sent is untrusted text, and only
   ever lands in textContent — never in markup. */
(() => {
  // ------------------------------------------------------------------ elements

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else if (k === "value") node.value = v;
        else if (k === "checked") node.checked = !!v;
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  const NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) node.setAttribute(k, v);
    return node;
  }

  // ------------------------------------------------------------------ icons: one system, 24px grid, round strokes

  const C = (cx, cy, r) => `M${cx} ${cy - r}a${r} ${r} 0 1 0 0 ${2 * r}a${r} ${r} 0 1 0 0-${2 * r}z`;
  const ICONS = {
    overview: ["M4 4h7v9H4z", "M13 4h7v5h-7z", "M13 11h7v9h-7z", "M4 15h7v5H4z"],
    live: ["M3 12h4l3-8l4 16l3-8h4"],
    activity: ["M8 6h13", "M8 12h13", "M8 18h13", "M3.5 6h.01", "M3.5 12h.01", "M3.5 18h.01"],
    attention: ["M12 3.5l9.5 16.5h-19z", "M12 10v4", "M12 17.2v.01"],
    people: ["M9 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8z", "M2.5 21v-.5A6.5 6.5 0 0 1 9 14a6.5 6.5 0 0 1 6.5 6.5v.5", "M16 3.6a4 4 0 0 1 0 7.3", "M18.5 14.4a6.5 6.5 0 0 1 3 5.6v1"],
    user: ["M12 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8z", "M4 21v-.5A7.5 7.5 0 0 1 11.5 13h1A7.5 7.5 0 0 1 20 20.5v.5"],
    device: ["M5 5h14a1 1 0 0 1 1 1v9.5H4V6a1 1 0 0 1 1-1z", "M2.5 18.5h19"],
    monitor: ["M3 4h18v12H3z", "M8 20h8", "M12 16v4"],
    terminal: ["M4 4h16v16H4z", "M8 9.5l3 2.5l-3 2.5", "M13 15h3"],
    tools: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
    requests: ["M4 13.5L6.2 5h11.6L20 13.5", "M4 13.5V19h16v-5.5", "M4 13.5h5l1.2 2h3.6l1.2-2h5"],
    licences: ["M3 6.5h18v11H3z", "M3 10.5h18", "M7 14.5h4"],
    shield: ["M12 3l7.5 3v5.5c0 4.6-3.2 7.9-7.5 9.5c-4.3-1.6-7.5-4.9-7.5-9.5V6z", "M9 12l2 2l4-4"],
    audit: ["M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z", "M14 3v5h5", "M9 13h6", "M9 17h6"],
    settings: ["M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z", "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3a1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8a1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"],
    clock: [C(12, 12, 9), "M12 7.5V12l3 2"],
    pin: ["M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z", C(12, 9.5, 2.5)],
    wallet: ["M4 7h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z", "M4 7l11-3v3", "M16 13h1.5"],
    lock: ["M6 11h12v10H6z", "M8.5 11V7.5a3.5 3.5 0 0 1 7 0V11"],
    alert: ["M12 3.5l9.5 16.5h-19z", "M12 10v4", "M12 17.2v.01"],
    check: ["M5 12.5l4.5 4.5L19 7.5"],
    checkCircle: [C(12, 12, 9), "M8.5 12.5l2.5 2.5l4.5-5"],
    x: ["M6 6l12 12", "M18 6L6 18"],
    search: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "M20 20l-4-4"],
    command: ["M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"],
    bot: ["M5 8h14v11H5z", "M12 4v4", "M9 13v1.5", "M15 13v1.5", "M2.5 12v4", "M21.5 12v4"],
    server: ["M4 4h16v6H4z", "M4 14h16v6H4z", "M8 7h.01", "M8 17h.01"],
    spark: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M19 16l.7 1.8l1.8.7l-1.8.7L19 21l-.7-1.8l-1.8-.7l1.8-.7z"],
    key: [C(7.5, 15.5, 3.5), "M10 13l10-10", "M16 7l3 3", "M13.5 9.5l2 2"],
    globe: [C(12, 12, 9), "M3 12h18", "M12 3a14 14 0 0 1 0 18", "M12 3a14 14 0 0 0 0 18"],
    eye: ["M2 12s3.5-7 10-7s10 7 10 7s-3.5 7-10 7S2 12 2 12z", C(12, 12, 3)],
    edit: ["M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z", "M13.5 7.5l3 3"],
    read: ["M3 5h6a3 3 0 0 1 3 3v12a2.5 2.5 0 0 0-2.5-2.5H3z", "M21 5h-6a3 3 0 0 0-3 3v12a2.5 2.5 0 0 1 2.5-2.5H21z"],
    image: ["M4 5h16v14H4z", "M4 16l5-5l4 4l2-2l5 5", "M15.5 9.5h.01"],
    video: ["M3 6h12v12H3z", "M15 10l6-3v10l-6-3"],
    mic: ["M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z", "M5.5 11a6.5 6.5 0 0 0 13 0", "M12 17.5V21"],
    chip: ["M7 7h10v10H7z", "M10 3v4", "M14 3v4", "M10 17v4", "M14 17v4", "M3 10h4", "M3 14h4", "M17 10h4", "M17 14h4"],
    building: ["M4 21V5l8-2v18", "M12 9h8v12", "M3 21h18", "M7 8h2", "M7 12h2", "M7 16h2", "M15 13h2", "M15 17h2"],
    link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
    copy: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
    open: ["M8 16L16 8", "M10 8h6v6"],
    refresh: ["M20 11a8 8 0 0 0-14.6-4.5L4 8", "M4 4v4h4", "M4 13a8 8 0 0 0 14.6 4.5L20 16", "M20 20v-4h-4"],
    logout: ["M15 4h4v16h-4", "M10 8l-4 4l4 4", "M6 12h11"],
    menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
    plus: ["M12 5v14", "M5 12h14"],
    stop: [C(12, 12, 9), "M9 9h6v6H9z"],
    sun: ["M12 2.5v2", "M12 19.5v2", "M4.6 4.6L6 6", "M18 18l1.4 1.4", "M2.5 12h2", "M19.5 12h2", "M4.6 19.4L6 18", "M18 6l1.4-1.4", "M12 7.5a4.5 4.5 0 1 0 0 9a4.5 4.5 0 1 0 0-9z"],
    moon: ["M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"],
    info: [C(12, 12, 9), "M12 11v5", "M12 7.8v.01"],
    trendUp: ["M3 17l6-6l4 4l8-8", "M15 7h6v6"],
    trendDown: ["M3 7l6 6l4-4l8 8", "M15 17h6v-6"],
    arrowUp: ["M12 19V5", "M6 11l6-6l6 6"],
    arrowDown: ["M12 5v14", "M6 13l6 6l6-6"],
    chevronRight: ["M9 6l6 6l-6 6"],
    chevronLeft: ["M15 6l-6 6l6 6"],
    chevronDown: ["M6 9l6 6l6-6"],
    sortUp: ["M7 14l5-5l5 5"],
    filter: ["M4 5h16l-6.5 8v5.5l-3 1.5v-7z"],
    calendar: ["M4 6h16v15H4z", "M4 10h16", "M8 3v5", "M16 3v5"],
    download: ["M12 4v11", "M7 10l5 5l5-5", "M5 20h14"],
    layers: ["M12 3l9 5l-9 5l-9-5z", "M3 13l9 5l9-5"],
    bell: ["M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z", "M10 20.5a2 2 0 0 0 4 0"],
    home: ["M4 11l8-7l8 7", "M6 9.5V20h12V9.5"],
    play: ["M7 5l12 7l-12 7z"],
    send: ["M4 12l16-8l-6 16l-3-7z"],
    hand: ["M8 13V5.5a1.5 1.5 0 0 1 3 0V12", "M11 11V4.5a1.5 1.5 0 0 1 3 0V11", "M14 11V6.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-7 7h-.5a6 6 0 0 1-5-2.7L3 15.5a1.5 1.5 0 0 1 2.5-1.7L8 16"],
    dot: [C(12, 12, 3)],
    pulse: ["M3 12h3.5l2-5l4 10l2.5-7l1.5 2H21"],
    rule: ["M5 4h14v16H5z", "M8.5 9l1.5 1.5L13 7.5", "M8.5 15h7", "M15 10h1.5"],
    report: ["M5 3h10l4 4v14H5z", "M9 17v-4", "M12 17v-7", "M15 17v-2"],
    flag: ["M5 21V4", "M5 4h11l-2 4l2 4H5"],
    target: [C(12, 12, 8.5), C(12, 12, 4.5), "M12 12h.01"],
    users: [C(9, 8, 3.5), "M3 20v-.5A6 6 0 0 1 9 13.5a6 6 0 0 1 6 6v.5", C(17, 9, 2.5), "M17.5 14a4.5 4.5 0 0 1 4 4.5v.5"],
  };
  function icon(name, cls) {
    const paths = Array.isArray(name) ? name : ICONS[name] || ICONS.dot;
    const node = s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round",
      "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false", class: cls || null });
    paths.forEach((d) => node.append(s("path", { d })));
    return node;
  }

  // ------------------------------------------------------------------ theme

  const THEME_KEY = "swangz-theme";
  const theme = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
  function applyTheme(t, remember) {
    document.documentElement.dataset.theme = t;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "dark" ? "#0A0A0B" : "#F4F2ED");
    if (remember) { try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* private window: just this visit */ } }
    document.dispatchEvent(new CustomEvent("swangz:theme", { detail: t }));
  }
  (() => { let saved = null; try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* none */ } applyTheme(saved === "light" ? "light" : "dark", false); })();
  function themeButton(cls) {
    const b = el("button", { class: cls || "theme-btn", type: "button" });
    const draw = () => {
      const dark = theme() === "dark";
      b.replaceChildren(icon(dark ? "sun" : "moon"));
      b.setAttribute("aria-label", dark ? "Switch to the light Porcelain theme" : "Switch to the dark Obsidian theme");
      b.title = dark ? "Porcelain (light)" : "Obsidian (dark)";
    };
    b.addEventListener("click", () => { applyTheme(theme() === "dark" ? "light" : "dark", true); draw(); });
    draw();
    return b;
  }

  // ------------------------------------------------------------------ time: one clock for the whole page

  /* Times can be read in the gateway's own time zone (where budgets reset), the viewer's, or UTC.
     The choice is remembered per browser and every date on the page follows it. */
  const TZ_KEY = "swangz-tz";
  const tz = { mode: "gateway", offset: 180 };
  try { const m = localStorage.getItem(TZ_KEY); if (["gateway", "local", "utc"].includes(m)) tz.mode = m; } catch (e) { /* default */ }
  function setGatewayOffset(minutes) { if (Number.isFinite(minutes)) tz.offset = minutes; }
  function setTzMode(mode) {
    tz.mode = mode;
    try { localStorage.setItem(TZ_KEY, mode); } catch (e) { /* this visit only */ }
    document.dispatchEvent(new CustomEvent("swangz:tz", { detail: mode }));
  }
  const shift = () => (tz.mode === "utc" ? 0 : tz.mode === "gateway" ? tz.offset * 60 : null);
  const offText = (min) => {
    const sign = min < 0 ? "−" : "+";
    const a = Math.abs(min);
    return `UTC${sign}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
  };
  function tzLabel(short) {
    if (tz.mode === "utc") return "UTC";
    if (tz.mode === "gateway") return short ? offText(tz.offset) : `Gateway time (${offText(tz.offset)})`;
    const local = -new Date().getTimezoneOffset();
    return short ? offText(local) : `Your time (${offText(local)})`;
  }
  const dtfCache = new Map();
  function format(ts, opts) {
    const sh = shift();
    const key = JSON.stringify(opts) + (sh === null ? "L" : "U");
    if (!dtfCache.has(key)) dtfCache.set(key, new Intl.DateTimeFormat([], sh === null ? opts : { ...opts, timeZone: "UTC" }));
    return dtfCache.get(key).format(new Date((ts + (sh || 0)) * 1000));
  }
  function startOfDay(ts) {
    const sh = shift();
    if (sh === null) { const d = new Date(ts * 1000); d.setHours(0, 0, 0, 0); return d.getTime() / 1000; }
    return Math.floor((ts + sh) / 86400) * 86400 - sh;
  }
  function startOfMonth(ts) {
    const sh = shift();
    if (sh === null) { const d = new Date(ts * 1000); return new Date(d.getFullYear(), d.getMonth(), 1).getTime() / 1000; }
    const d = new Date((ts + sh) * 1000);
    return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000 - sh;
  }
  function dateInput(ts) {  // YYYY-MM-DD in the chosen zone
    const sh = shift();
    const d = new Date((ts + (sh || 0)) * 1000);
    if (sh === null) return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return d.toISOString().slice(0, 10);
  }
  function fromDateInput(text) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text || "");
    if (!m) return null;
    const sh = shift();
    if (sh === null) return new Date(+m[1], +m[2] - 1, +m[3]).getTime() / 1000;
    return Date.UTC(+m[1], +m[2] - 1, +m[3]) / 1000 - sh;
  }

  const fmt = {
    money(v) {
      if (v === null || v === undefined) return "unpriced";
      if (v === 0) return "$0.00";
      if (Math.abs(v) < 0.01) return "$" + v.toFixed(4);
      return "$" + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },
    moneyShort(v) {
      v = v || 0;
      if (Math.abs(v) >= 10000) return "$" + (v / 1000).toFixed(1).replace(/\.0$/, "") + "k";
      if (Math.abs(v) >= 100) return "$" + Math.round(v).toLocaleString();
      return fmt.money(v);
    },
    num(n) { return (n || 0).toLocaleString(); },
    compact(n) {
      n = n || 0;
      if (Math.abs(n) < 1000) return String(Math.round(n));
      if (Math.abs(n) < 1e6) return (n / 1e3).toFixed(n < 1e4 ? 1 : 0).replace(/\.0$/, "") + "K";
      return (n / 1e6).toFixed(n < 1e7 ? 2 : 1).replace(/\.0+$/, "") + "M";
    },
    tokens(n) { return fmt.compact(n).replace("K", "k"); },
    pct(change, digits) {
      if (change === null || change === undefined || !Number.isFinite(change)) return "—";
      const v = change * 100;
      return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(digits === undefined ? (Math.abs(v) < 10 ? 1 : 0) : digits) + "%";
    },
    clock(ts, seconds) { return ts ? format(ts, seconds ? { hour: "2-digit", minute: "2-digit", second: "2-digit" } : { hour: "2-digit", minute: "2-digit" }) : "—"; },
    date(ts) { return ts ? format(ts, { day: "numeric", month: "short", year: "numeric" }) : "—"; },
    dayMonth(ts) { return format(ts, { day: "numeric", month: "short" }); },
    weekday(ts) { return format(ts, { weekday: "short", day: "numeric", month: "short" }); },
    day(ts) {
      const today = startOfDay(Date.now() / 1000);
      const d = startOfDay(ts);
      if (d === today) return "Today";
      if (d === startOfDay(today - 3600)) return "Yesterday";
      return d > today - 6 * 86400 ? format(ts, { weekday: "long", day: "numeric", month: "short" }) : fmt.date(ts);
    },
    when(ts) {
      if (!ts) return "—";
      return startOfDay(ts) === startOfDay(Date.now() / 1000) ? fmt.clock(ts) : fmt.dayMonth(ts);
    },
    stamp(ts) { return ts ? format(ts, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"; },
    ago(ts) {
      if (!ts) return "never";
      const sec = Date.now() / 1000 - ts;
      if (sec < 45) return "just now";
      if (sec < 3600) return Math.round(sec / 60) + " min ago";
      if (sec < 86400) return Math.round(sec / 3600) + " h ago";
      if (sec < 86400 * 30) return Math.round(sec / 86400) + " d ago";
      return fmt.date(ts);
    },
    elapsed(ts) {
      const sec = Math.max(0, Math.round(Date.now() / 1000 - ts));
      if (sec < 60) return sec + "s";
      if (sec < 3600) return Math.floor(sec / 60) + "m " + String(sec % 60).padStart(2, "0") + "s";
      return Math.floor(sec / 3600) + "h " + String(Math.floor(sec % 3600 / 60)).padStart(2, "0") + "m";
    },
    ms(v) { return v === null || v === undefined ? "—" : v < 1000 ? v + " ms" : (v / 1000).toFixed(1) + " s"; },
    dur(sec) {
      sec = Math.round(sec || 0);
      if (sec < 60) return sec + "s";
      if (sec < 3600) return Math.round(sec / 60) + " min";
      const h = Math.floor(sec / 3600);
      const m = Math.round(sec % 3600 / 60);
      return h + "h" + (m ? " " + m + "m" : "");
    },
  };

  // ------------------------------------------------------------------ small things

  const initials = (name) => (name || "?").split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
  const plural = (n, word, many) => `${(n || 0).toLocaleString()} ${n === 1 ? word : many || word + "s"}`;
  function debounce(fn, ms) { let t = null; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
  const gateway = () => (typeof window !== "undefined" && window.SWANGZ_GATEWAY || "").replace(/\/+$/, "");

  function avatar(name, size) { return el("span", { class: "u-avatar" + (size ? " " + size : ""), "aria-hidden": "true" }, initials(name)); }

  function logo(t, size) {
    const cls = "logo" + (size ? " " + size : "");
    const mono = () => {
      const box = el("span", { class: cls + " mono", "aria-hidden": "true" }, initials(t.name || t.tool));
      const c = /^#[0-9a-f]{6}$/i.test(t.color || "") ? t.color : "#3F3F46";
      box.style.background = `linear-gradient(140deg, ${c}, color-mix(in srgb, ${c} 55%, #0A0A0B))`;
      return box;
    };
    if (!t.icon) return mono();
    const img = el("img", { src: gateway() + t.icon, alt: "", loading: "lazy", decoding: "async" });
    const box = el("span", { class: cls, "aria-hidden": "true" }, img);
    img.addEventListener("error", () => box.replaceWith(mono()));
    return box;
  }

  /* A state as a dot and a word. `state` picks the colour; the word is always shown. */
  function status(state, label, opts) {
    opts = opts || {};
    return el("span", { class: `u-status s-${state}` + (opts.breathe ? " breathe" : "") + (opts.plain ? " plain" : ""), title: opts.title || null },
      el("i", { "aria-hidden": "true" }), label);
  }
  function badge(text, tone, iconName) { return el("span", { class: "u-badge" + (tone ? " " + tone : "") }, iconName ? icon(iconName) : null, text); }

  /* Change against a named period. upIsGood decides the tone; the arrow and sign carry the meaning. */
  function delta(change, opts) {
    opts = opts || {};
    if (change === null || change === undefined || !Number.isFinite(change)) {
      return el("span", { class: "u-delta" }, opts.none || "no earlier data");
    }
    const up = change > 0.0005, down = change < -0.0005;
    const good = opts.upIsGood ? up : down;
    const bad = opts.upIsGood ? down : up;
    return el("span", { class: "u-delta" + (good ? " good" : bad ? " bad" : "") },
      up ? icon("trendUp") : down ? icon("trendDown") : null,
      fmt.pct(change), opts.vs ? el("span", { class: "u-sr" }, " " + opts.vs) : null);
  }

  function evidence(text, iconName) { return el("span", { class: "u-evidence" }, icon(iconName || "info"), text); }

  // ------------------------------------------------------------------ loading, empty, error

  function skeleton(kind, n) {
    n = n || 4;
    if (kind === "cards") return el("div", { class: "u-skel-cards", "aria-hidden": "true" }, Array.from({ length: n }, () =>
      el("div", { class: "u-skel-card" }, el("span", { class: "u-skel line" }), el("span", { class: "u-skel big" }), el("span", { class: "u-skel line" }))));
    if (kind === "chart") return skelChart();
    return el("div", { class: "u-skel-rows", "aria-busy": "true", "aria-label": "Loading" }, Array.from({ length: n }, () =>
      el("div", { class: "u-skel-row" }, el("span", { class: "u-skel dot" }), el("span", null, el("span", { class: "u-skel line" }), el("span", { class: "u-skel line" })),
        el("span", { class: "u-skel line" }))));
  }
  function skelChart() {
    const box = el("div", { class: "u-skel", "aria-hidden": "true" });
    box.style.height = "160px";
    return box;
  }

  function stateBox(o) {
    return el("div", { class: "u-state" + (o.tone ? " " + o.tone : "") + (o.compact ? " compact" : ""), role: o.tone === "bad" ? "alert" : null },
      el("div", { class: "ic" }, icon(o.icon || "info")),
      o.title ? el("h3", null, o.title) : null,
      o.text ? el("p", null, o.text) : null,
      o.action ? el("div", { class: "act" }, o.action) : null);
  }
  function errorBox(err, retry, title) {
    return stateBox({ tone: "bad", icon: "alert", title: title || "Temporarily unavailable",
      text: (err && err.message ? err.message + ". " : "") + "The rest of the page is still working.",
      action: retry ? el("button", { class: "btn small", type: "button", onclick: retry }, icon("refresh"), "Retry") : null });
  }

  /* Fill `holder` from an async builder: a skeleton while it loads, an error with Retry if it fails. */
  function load(holder, build, skel) {
    holder.replaceChildren(skel || skeleton("rows", 3));
    return Promise.resolve().then(build).then((n) => { holder.replaceChildren(...[].concat(n).filter(Boolean)); })
      .catch((e) => { if (e && e.status === 401) return; holder.replaceChildren(errorBox(e, () => load(holder, build, skel))); });
  }

  // ------------------------------------------------------------------ toasts and copying

  function toast(message, bad) {
    const t = el("div", { class: "toast" + (bad ? " bad" : ""), role: bad ? "alert" : "status" }, message);
    document.body.append(t);
    setTimeout(() => t.remove(), bad ? 6000 : 3000);
  }
  async function copy(text, what) {
    try { await navigator.clipboard.writeText(text); toast((what || "Copied") + (what ? " copied" : "")); }
    catch (e) { toast("Copy didn't work here — select the text and copy it by hand.", true); }
  }

  // ------------------------------------------------------------------ tooltips

  /* Anything with data-tip gets a tooltip on hover and on keyboard focus. Tooltips explain; they never
     hold the only copy of something important. Charts call tipAt() with their own content. */
  let tipNode = null, tipOwner = null;
  function tipEl() {
    if (!tipNode) { tipNode = el("div", { class: "u-tip", role: "tooltip", id: "u-tip" }); document.body.append(tipNode); }
    return tipNode;
  }
  function place(rect, x, y) {
    const t = tipEl();
    const w = t.offsetWidth, h = t.offsetHeight;
    let left = x !== undefined ? x - w / 2 : rect.left + rect.width / 2 - w / 2;
    let top = (y !== undefined ? y : rect.top) - h - 10;
    if (top < 8) top = (y !== undefined ? y : rect.bottom) + 14;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    t.style.left = left + "px";
    t.style.top = top + "px";
  }
  function showTip(owner, content, x, y) {
    const t = tipEl();
    t.replaceChildren(...[].concat(content));
    tipOwner = owner;
    if (owner && owner.setAttribute && !owner.closest(".u-chart")) owner.setAttribute("aria-describedby", "u-tip");
    place(owner.getBoundingClientRect(), x, y);
    t.classList.add("in");
  }
  function hideTip(owner) {
    if (owner && owner !== tipOwner) return;
    if (tipOwner && tipOwner.removeAttribute) tipOwner.removeAttribute("aria-describedby");
    tipOwner = null;
    if (tipNode) tipNode.classList.remove("in");
  }
  const tipText = (node) => node.dataset.tip;
  document.addEventListener("pointerover", (e) => { const n = e.target.closest && e.target.closest("[data-tip]"); if (n) showTip(n, tipText(n)); });
  document.addEventListener("pointerout", (e) => { const n = e.target.closest && e.target.closest("[data-tip]"); if (n && !n.contains(e.relatedTarget)) hideTip(n); });
  document.addEventListener("focusin", (e) => { const n = e.target.closest && e.target.closest("[data-tip]"); if (n) showTip(n, tipText(n)); });
  document.addEventListener("focusout", (e) => { const n = e.target.closest && e.target.closest("[data-tip]"); if (n) hideTip(n); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
  window.addEventListener("scroll", () => hideTip(), { passive: true, capture: true });
  function infoTip(text) { return el("button", { class: "u-info", type: "button", "data-tip": text, "aria-label": text }, icon("info")); }

  // ------------------------------------------------------------------ charts

  function niceMax(v) {
    if (!(v > 0)) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  }

  /* A chart frame: an SVG redrawn at its real width, one tooltip, keyboard reading with the arrow keys,
     and a table view so no value lives only in a hover. */
  function chartFrame(o, draw) {
    const fig = el("figure", { class: "u-chart" + (o.tone === 2 ? " tone-2" : "") });
    const svgBox = el("div");
    const tableBox = el("div", { class: "u-chart-table", hidden: true });
    const toggle = el("button", { type: "button", "aria-expanded": "false" }, "Show as table");
    toggle.addEventListener("click", () => {
      const open = tableBox.hidden;
      tableBox.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "Hide table" : "Show as table";
      if (open && !tableBox.firstChild) {
        tableBox.append(el("table", null, el("thead", null, el("tr", null, el("th", { scope: "col" }, o.xName || "Day"), el("th", { scope: "col" }, o.yName || "Value"))),
          el("tbody", null, o.data.map((d) => el("tr", null, el("th", { scope: "row" }, d.label), el("td", null, o.format(d.value)))))));
      }
    });
    fig.append(svgBox, el("figcaption", { class: "u-chart-foot" }, el("span", { class: "hint" }, o.caption || ""), toggle), tableBox);
    let width = 0;
    const redraw = () => {
      const w = Math.round(svgBox.clientWidth);
      if (!w || w === width) return;
      width = w;
      svgBox.replaceChildren(draw(w));
    };
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(redraw).observe(svgBox);
    requestAnimationFrame(redraw);
    return fig;
  }

  function chartTipContent(d, o) {
    return [el("b", null, o.format(d.value)), el("span", { class: "k" }, el("i"), d.label), d.note ? el("span", { class: "k" }, d.note) : null].filter(Boolean);
  }

  function axes(g, o, w, h, pad, max) {
    const grid = s("g", { class: "grid" });
    const ax = s("g", { class: "axis" });
    const ticks = [0, max / 2, max];
    ticks.forEach((t) => {
      const y = pad.t + (h - pad.t - pad.b) * (1 - t / max);
      grid.append(s("line", { x1: pad.l, x2: w - pad.r, y1: y, y2: y }));
      const label = s("text", { x: pad.l - 8, y: y + 3.5, "text-anchor": "end" });
      label.textContent = o.tick ? o.tick(t) : o.format(t);
      ax.append(label);
    });
    g.append(grid, ax);
    return ax;
  }

  function xLabels(ax, o, w, h, pad, xs) {
    const n = o.data.length;
    const room = Math.max(1, Math.floor((w - pad.l - pad.r) / 64));
    const step = Math.max(1, Math.ceil(n / room));
    o.data.forEach((d, i) => {
      if (i % step !== 0 && i !== n - 1) return;
      if (i !== n - 1 && n - 1 - i < step) return;  // keep the last label clear of its neighbour
      const t = s("text", { x: xs(i), y: h - 4, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" });
      t.textContent = d.short || d.label;
      ax.append(t);
    });
  }

  function interact(svg, o, xs, n, onActive) {
    let active = -1;
    const show = (i, clientX, clientY) => {
      active = i;
      onActive(i);
      const r = svg.getBoundingClientRect();
      const x = clientX !== undefined ? clientX : r.left + xs(i);
      showTip(svg, chartTipContent(o.data[i], o), x, clientY !== undefined ? clientY : r.top + 12);
    };
    const hide = () => { active = -1; onActive(-1); hideTip(svg); };
    svg.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const x = e.clientX - r.left;
      let best = 0, dist = Infinity;
      for (let i = 0; i < n; i++) { const dd = Math.abs(xs(i) - x); if (dd < dist) { dist = dd; best = i; } }
      show(best, e.clientX, e.clientY);
    });
    svg.addEventListener("pointerleave", hide);
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const next = e.key === "Home" ? 0 : e.key === "End" ? n - 1 : Math.max(0, Math.min(n - 1, (active < 0 ? n - 1 : active) + (e.key === "ArrowLeft" ? -1 : 1)));
      show(next);
    });
    svg.addEventListener("focus", () => show(active < 0 ? n - 1 : active));
  }

  /* Columns over time — one series, so no legend: the title names it. data: [{label, short, value, note}] */
  function columns(o) {
    o = { height: 170, format: fmt.num, ...o };
    return chartFrame(o, (w) => {
      const h = o.height, pad = { t: 10, r: 4, b: 22, l: 44 };
      const max = niceMax(Math.max(...o.data.map((d) => d.value || 0)));
      const svg = s("svg", { width: w, height: h, role: "img", tabindex: "0", "aria-label": o.label + ". Use the left and right arrow keys to read each day." });
      const g = s("g");
      const ax = axes(g, o, w, h, pad, max);
      const n = o.data.length;
      const band = (w - pad.l - pad.r) / n;
      const bw = Math.max(2, Math.min(24, band * 0.64));
      const xs = (i) => pad.l + band * i + band / 2;
      const base = h - pad.b;
      const bars = [];
      o.data.forEach((d, i) => {
        const v = d.value || 0;
        const bh = v > 0 ? Math.max(2, (base - pad.t) * v / max) : 0;
        const x = xs(i) - bw / 2, y = base - bh, r = Math.min(4, bw / 2, bh);
        const path = s("path", { class: "col", d: bh ? `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${base}Z` : "" });
        bars.push(path);
        g.append(path);
      });
      xLabels(ax, o, w, h, pad, xs);
      svg.append(g);
      interact(svg, o, xs, n, (i) => bars.forEach((b, j) => { b.style.opacity = i < 0 || i === j ? "" : ".45"; }));
      return svg;
    });
  }

  /* A line with a soft area under it, a crosshair that finds the day, and the latest value at its end. */
  function line(o) {
    o = { height: 170, format: fmt.num, ...o };
    return chartFrame(o, (w) => {
      const h = o.height, pad = { t: 12, r: o.endLabel === false ? 8 : 52, b: 22, l: 44 };
      const max = niceMax(Math.max(...o.data.map((d) => d.value || 0)));
      const svg = s("svg", { width: w, height: h, role: "img", tabindex: "0", "aria-label": o.label + ". Use the left and right arrow keys to read each day." });
      const g = s("g");
      const ax = axes(g, o, w, h, pad, max);
      const n = o.data.length;
      const xs = (i) => pad.l + (n === 1 ? (w - pad.l - pad.r) / 2 : (w - pad.l - pad.r) * i / (n - 1));
      const base = h - pad.b;
      const ys = (v) => base - (base - pad.t) * (v || 0) / max;
      const pts = o.data.map((d, i) => [xs(i), ys(d.value)]);
      const dLine = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
      g.append(s("path", { class: "area", d: dLine + `L${pts[n - 1][0]},${base}L${pts[0][0]},${base}Z` }), s("path", { class: "line", d: dLine }));
      const cross = s("line", { class: "cross", y1: pad.t, y2: base });
      const dot = s("circle", { class: "end", r: 4.5, cx: pts[n - 1][0], cy: pts[n - 1][1] });
      g.append(cross, dot);
      if (o.endLabel !== false) {
        const t = s("text", { class: "end-label", x: pts[n - 1][0] + 9, y: pts[n - 1][1] + 4 });
        t.textContent = (o.tick || o.format)(o.data[n - 1].value || 0);
        g.append(t);
      }
      xLabels(ax, o, w, h, pad, xs);
      svg.append(g);
      interact(svg, o, xs, n, (i) => {
        cross.classList.toggle("on", i >= 0);
        const at = i < 0 ? n - 1 : i;
        cross.setAttribute("x1", pts[at][0]); cross.setAttribute("x2", pts[at][0]);
        dot.setAttribute("cx", pts[at][0]); dot.setAttribute("cy", pts[at][1]);
      });
      return svg;
    });
  }

  /* A small trend for a stat tile: decorative (the tile states the number), muted, the latest point lit. */
  function sparkline(values, tone) {
    const w = 120, h = 28;
    const max = Math.max(...values, 0) || 1;
    const n = values.length;
    const svg = s("svg", { class: "u-spark" + (tone === 2 ? " tone-2" : ""), viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none", "aria-hidden": "true" });
    if (n < 2) return svg;
    const pts = values.map((v, i) => [(w - 4) * i / (n - 1) + 2, h - 3 - (h - 6) * v / max]);
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
    svg.append(s("path", { class: "area", d: d + `L${pts[n - 1][0]},${h}L${pts[0][0]},${h}Z` }), s("path", { class: "line", d, "vector-effect": "non-scaling-stroke" }));
    return svg;
  }

  /* Ranked bars: name, value and a thin bar, largest first. rows: [{label, href, value, display, note, lead}] */
  function barList(rows, o) {
    o = o || {};
    const top = Math.max(...rows.map((r) => r.value || 0), 0) || 1;
    return el("ul", { class: "u-bars" + (o.tone === 2 ? " tone-2" : "") }, rows.map((r) => {
      const fill = el("i");
      fill.style.width = Math.max(r.value ? 1.5 : 0, (r.value || 0) / top * 100) + "%";
      const name = [r.lead || null, el("span", null, r.label)];
      return el("li", null,
        r.href ? el("a", { href: r.href }, name) : el("div", { class: "nm" }, name),
        el("div", { class: "val" }, r.display !== undefined ? r.display : fmt.num(r.value), r.note ? el("small", null, r.note) : null),
        el("div", { class: "track", "aria-hidden": "true" }, fill));
    }));
  }

  // ------------------------------------------------------------------ tables

  /* columns: [{key, label, num, sort (value fn or false), render(row) → node, lead, hideSm, cls}]
     Sortable headers announce their order; rows open on click or Enter; on phones each row is a card. */
  function table(o) {
    const cols = o.columns;
    let sortKey = o.sort ? o.sort[0] : null, dir = o.sort ? o.sort[1] : "desc";
    const tbody = el("tbody");
    const head = el("tr", null, cols.map((c) => {
      const th = el("th", { scope: "col", class: [c.num ? "num" : "", c.hideSm ? "hide-sm" : ""].join(" ").trim() || null });
      if (c.sort === false || !c.label) th.append(c.label || el("span", { class: "u-sr" }, c.srLabel || ""));
      else th.append(el("button", { type: "button", onclick: () => { dir = sortKey === c.key && dir === "desc" ? "asc" : "desc"; sortKey = c.key; draw(); } },
        c.label, icon("sortUp")));
      return th;
    }));
    const t = el("table", { class: "u-table" + (o.cards === false ? "" : " cards") }, o.caption ? el("caption", { class: "u-sr" }, o.caption) : null,
      el("thead", null, head), tbody);
    const value = (c, r) => (typeof c.sort === "function" ? c.sort(r) : r[c.key]);
    function draw() {
      head.querySelectorAll("th").forEach((th, i) => {
        if (cols[i].key === sortKey && cols[i].sort !== false) th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
        else th.removeAttribute("aria-sort");
      });
      let rows = o.rows.slice();
      const c = cols.find((x) => x.key === sortKey);
      if (c) {
        rows.sort((a, b) => {
          const x = value(c, a), y = value(c, b);
          const cmp = typeof x === "string" || typeof y === "string" ? String(x || "").localeCompare(String(y || "")) : (x || 0) - (y || 0);
          return dir === "asc" ? cmp : -cmp;
        });
      }
      tbody.replaceChildren(...rows.map((r) => {
        const href = o.href ? o.href(r) : null;
        const tr = el("tr", { class: href ? "click" : null, tabindex: href ? "0" : null });
        cols.forEach((col) => tr.append(el("td", { class: [col.num ? "num" : "", col.lead ? "lead" : "", col.hideSm ? "hide-sm" : "", col.cls || ""].join(" ").trim() || null,
          "data-label": col.lead ? null : col.label || null }, col.render ? col.render(r) : (r[col.key] ?? "—"))));
        if (href) {
          tr.addEventListener("click", (e) => { if (!e.target.closest("a, button, input, select")) location.hash = href.replace(/^#/, ""); });
          tr.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === tr) location.hash = href.replace(/^#/, ""); });
        }
        return tr;
      }));
    }
    draw();
    return el("div", { class: "u-table-wrap", tabindex: "0", role: "region", "aria-label": o.caption || "Data table" }, t);
  }

  // ------------------------------------------------------------------ the time machine

  const PRESETS = [["today", "Today"], ["yesterday", "Yesterday"], ["7d", "7 days"], ["30d", "30 days"], ["month", "This month"], ["custom", "Custom"]];
  function presetRange(id, custom) {
    const now = Date.now() / 1000;
    const today = startOfDay(now);
    switch (id) {
      case "yesterday": { const y = startOfDay(today - 3600); return { since: y, until: today }; }
      case "7d": return { since: startOfDay(today - 6 * 86400 + 7200), until: null };
      case "30d": return { since: startOfDay(today - 29 * 86400 + 7200), until: null };
      case "90d": return { since: startOfDay(today - 89 * 86400 + 7200), until: null };
      case "month": return { since: startOfMonth(now), until: null };
      case "custom": {
        const a = fromDateInput(custom && custom.from), b = fromDateInput(custom && custom.to);
        if (a === null) return presetRange("7d");
        return { since: a, until: b !== null && b >= a ? startOfDay(b + 26 * 3600) : null };
      }
      default: return { since: today, until: null };
    }
  }
  /* Presets first, then a custom range, then which clock the page reads in. onChange({preset, since, until, from, to}). */
  function rangeControl(o) {
    const presets = PRESETS.filter(([id]) => !o.presets || o.presets.includes(id));
    let cur = { preset: o.preset || "today", from: o.from || "", to: o.to || "" };
    const from = el("input", { type: "date", value: cur.from, "aria-label": "From" });
    const to = el("input", { type: "date", value: cur.to, "aria-label": "To" });
    const custom = el("span", { class: "custom", hidden: cur.preset !== "custom" }, from, "–", to);
    const seg = el("div", { class: "u-seg", role: "group", "aria-label": "Time range" });
    function fire() {
      const r = presetRange(cur.preset, cur);
      o.onChange({ ...cur, ...r });
    }
    function drawSeg() {
      seg.replaceChildren(...presets.map(([id, label]) => el("button", { type: "button", "aria-pressed": cur.preset === id ? "true" : "false",
        onclick: () => {
          cur.preset = id;
          if (id === "custom" && !from.value) { from.value = dateInput(Date.now() / 1000 - 6 * 86400); to.value = dateInput(Date.now() / 1000); }
          cur.from = from.value; cur.to = to.value;
          custom.hidden = id !== "custom";
          drawSeg(); fire();
        } }, label)));
    }
    [from, to].forEach((i) => i.addEventListener("change", () => { cur.from = from.value; cur.to = to.value; fire(); }));
    drawSeg();
    const zone = el("select", { "aria-label": "Show times in" },
      el("option", { value: "gateway" }, "Gateway time " + offText(tz.offset)),
      el("option", { value: "local" }, "My time " + offText(-new Date().getTimezoneOffset())),
      el("option", { value: "utc" }, "UTC"));
    zone.value = tz.mode;
    zone.addEventListener("change", () => setTzMode(zone.value));
    return el("div", { class: "u-range" }, seg, custom, o.tz === false ? null : el("label", { class: "tz" }, icon("clock"), el("span", { class: "u-sr" }, "Show times in"), zone));
  }

  // ------------------------------------------------------------------ focus

  /* Keep Tab inside a sheet or menu while it is open; hand focus back when it closes. */
  function trapFocus(node) {
    const before = document.activeElement;
    const sel = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    function onKey(e) {
      if (e.key !== "Tab") return;
      const items = [...node.querySelectorAll(sel)].filter((x) => x.offsetParent !== null || x === document.activeElement);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    node.addEventListener("keydown", onKey);
    return () => { node.removeEventListener("keydown", onKey); if (before && before.focus && document.contains(before)) before.focus(); };
  }

  // ------------------------------------------------------------------ the command menu

  /* Ctrl+K anywhere. Static actions filter as you type; search(q) adds live results, grouped.
     actions: [{group, title, sub, icon, href | run, keywords}] */
  function commandMenu(o) {
    let open = false;
    function show() {
      if (open) return;
      open = true;
      const input = el("input", { type: "text", role: "combobox", "aria-expanded": "true", "aria-controls": "u-cmd-list", "aria-autocomplete": "list",
        placeholder: o.placeholder || "Search or jump to…", autocomplete: "off", spellcheck: "false" });
      const list = el("div", { class: "u-cmd-list", id: "u-cmd-list", role: "listbox", "aria-label": "Results" });
      const status = el("div", { class: "u-sr", role: "status", "aria-live": "polite" });
      const box = el("div", { class: "u-cmd", role: "dialog", "aria-modal": "true", "aria-label": "Command menu" },
        el("div", { class: "u-cmd-input" }, icon("search"), input, el("span", { class: "u-kbd" }, "Esc")),
        list, status,
        el("div", { class: "u-cmd-foot" }, el("span", null, el("span", { class: "u-kbd" }, "↑"), el("span", { class: "u-kbd" }, "↓"), "move"),
          el("span", null, el("span", { class: "u-kbd" }, "↵"), "open"), el("span", null, el("span", { class: "u-kbd" }, "Esc"), "close")));
      const scrim = el("div", { class: "u-cmd-scrim" }, box);
      let items = [], sel = 0, seq = 0;
      const release = trapFocus(box);
      function close() {
        if (!open) return;
        open = false;
        scrim.classList.remove("in");
        document.removeEventListener("keydown", onKey, true);
        setTimeout(() => scrim.remove(), 180);
        release();
      }
      function run(item) {
        close();
        if (item.run) item.run();
        else if (item.href) location.hash = item.href.replace(/^#/, "");
      }
      function paint(groups) {
        items = [];
        list.replaceChildren();
        groups.forEach((g) => {
          if (!g.items.length) return;
          list.append(el("div", { class: "u-cmd-group", role: "presentation" }, g.group));
          g.items.forEach((it) => {
            const idx = items.length;
            const node = el("div", { class: "u-cmd-item", role: "option", id: "u-cmd-" + idx, "aria-selected": "false",
              onclick: () => run(it), onpointermove: () => select(idx) },
            el("span", { class: "ic" }, it.lead || icon(it.icon || "chevronRight")),
            el("span", { class: "t" }, el("b", null, it.title), it.sub ? el("span", null, it.sub) : null),
            it.hint ? el("span", { class: "hint" }, it.hint) : null);
            items.push({ ...it, node });
            list.append(node);
          });
        });
        if (!items.length) list.append(el("div", { class: "u-cmd-empty" }, input.value.trim() ? "Nothing matches “" + input.value.trim() + "”." : "Type to search."));
        status.textContent = items.length ? `${items.length} result${items.length === 1 ? "" : "s"}` : "No results";
        select(0);
      }
      function select(i) {
        if (!items.length) { input.removeAttribute("aria-activedescendant"); return; }
        sel = (i + items.length) % items.length;
        items.forEach((it, j) => it.node.setAttribute("aria-selected", j === sel ? "true" : "false"));
        input.setAttribute("aria-activedescendant", items[sel].node.id);
        items[sel].node.scrollIntoView({ block: "nearest" });
      }
      function matchStatic(q) {
        const qq = q.toLowerCase();
        const hits = o.actions.filter((a) => !qq || (a.title + " " + (a.sub || "") + " " + (a.keywords || "")).toLowerCase().includes(qq));
        const groups = [];
        hits.forEach((a) => {
          let g = groups.find((x) => x.group === a.group);
          if (!g) groups.push(g = { group: a.group, items: [] });
          if (g.items.length < (qq ? 6 : 8)) g.items.push(a);
        });
        return groups;
      }
      const searchLive = debounce(async (q, mine) => {
        if (!o.search || q.length < 1) return;
        try {
          const groups = await o.search(q);
          if (mine !== seq || !open) return;
          paint([...matchStatic(q), ...groups]);
        } catch (e) { /* static results stay */ }
      }, 160);
      input.addEventListener("input", () => { const q = input.value.trim(); seq++; paint(matchStatic(q)); searchLive(q, seq); });
      function onKey(e) {
        if (e.key === "Escape") { e.preventDefault(); close(); }
        else if (e.key === "ArrowDown") { e.preventDefault(); select(sel + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); select(sel - 1); }
        else if (e.key === "Enter" && items[sel]) { e.preventDefault(); run(items[sel]); }
      }
      document.addEventListener("keydown", onKey, true);
      scrim.addEventListener("pointerdown", (e) => { if (e.target === scrim) close(); });
      document.body.append(scrim);
      paint(matchStatic(""));
      requestAnimationFrame(() => { scrim.classList.add("in"); input.focus(); });
    }
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); show(); }
    });
    return show;
  }

  window.SUI = {
    el, s, icon, ICONS, theme, applyTheme, themeButton,
    tz, setGatewayOffset, setTzMode, tzLabel, startOfDay, startOfMonth, dateInput, fromDateInput, presetRange, fmt,
    initials, plural, debounce, gateway, avatar, logo, status, badge, delta, evidence,
    skeleton, stateBox, errorBox, load, toast, copy, showTip, hideTip, infoTip,
    columns, line, sparkline, barList, table, rangeControl, trapFocus, commandMenu,
  };
})();
