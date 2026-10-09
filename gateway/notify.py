"""Notifications: the conditions the control room raises, kept so each admin can see what is new.

Each condition has a stable key (`budget-7-monthly`, `provider-off:openai`, …). A refresh upserts the ones
that hold now and marks the rest resolved, so a condition is one notification however long it lasts, and it
comes back as new if it returns after being resolved. Read state is per console user.

Sources: everything on *Needs attention* (insight.attention), the emergency switches, providers failing,
and open high or critical incidents. Severity runs info < notice < warning < high < critical.

Email is optional and off by default. With `GATEWAY_SMTP_HOST` and `GATEWAY_NOTIFY_TO` set, new high and
critical notifications are emailed once (stdlib smtplib, STARTTLS when `GATEWAY_SMTP_PORT` is 587). The
message carries the title, the text and a link, never request content.
"""

import os
import smtplib
import threading
import time
import types
from email.message import EmailMessage

SEVERITIES = ("info", "notice", "warning", "high", "critical")
RANK = {s: i for i, s in enumerate(SEVERITIES)}
FROM_ATTENTION = {"info": "info", "low": "notice", "medium": "warning", "high": "high"}
REFRESH_SECONDS = 60
_lock = threading.Lock()
_last = {}


def conditions(gw):
    """[{key, severity, area, title, text, href}] that hold right now."""
    from . import insight

    db, now = gw.db, time.time()
    ctx = types.SimpleNamespace(db=db, gw=gw, arg=lambda name, default=None, cast=str: default)
    out = []
    for item in insight.attention(ctx)["items"]:
        out.append({"key": "att:" + item["key"], "severity": FROM_ATTENTION.get(item["severity"], "notice"),
                    "area": item["area"], "title": item["title"], "text": item["text"], "href": item["href"]})
    for name in [n for n in (db.get_setting("disabled_providers", "") or "").split(",") if n]:
        p = gw.settings.providers.get(name)
        out.append({"key": f"provider-off:{name}", "severity": "warning", "area": "Emergency",
                    "title": f"{p.label if p else name} is switched off", "text": "Requests to it are refused until it is switched back on.",
                    "href": "#/settings?tab=emergency"})
    if db.get_setting("workspace_paused", "0") == "1":
        out.append({"key": "workspace-paused", "severity": "notice", "area": "Emergency", "title": "Company browsers are paused",
                    "text": "Shared tools can't be opened in a company browser until they are resumed.", "href": "#/settings?tab=emergency"})
    for r in db.q("SELECT provider, COUNT(*) AS n, SUM(outcome = 'error') AS errors FROM requests WHERE ts >= ?"
                  " AND kind NOT IN ('other') AND outcome IN ('ok', 'error') GROUP BY provider", (now - 3600,)):
        if r["n"] >= 5 and (r["errors"] or 0) / r["n"] >= 0.25:
            p = gw.settings.providers.get(r["provider"])
            out.append({"key": f"provider-errors:{r['provider']}", "severity": "warning", "area": "Reliability",
                        "title": f"{p.label if p else r['provider']} is failing",
                        "text": f"{r['errors']} of {r['n']} requests in the last hour failed at the provider.",
                        "href": f"#/activity?tab=ai&outcome=error"})
    for r in db.q("SELECT id, title, severity, status FROM incidents WHERE status IN ('open', 'investigating', 'contained')"
                  " AND severity IN ('high', 'critical')"):
        out.append({"key": f"incident:{r['id']}", "severity": "critical" if r["severity"] == "critical" else "high", "area": "Trust",
                    "title": f"Incident: {r['title']}", "text": f"{r['severity'].capitalize()} severity, {r['status']}.",
                    "href": f"#/incidents/{r['id']}"})
    return out


def refresh(gw, now=None):
    """Bring the stored notifications in line with what holds now. -> the ids that are new or came back."""
    now = now or time.time()
    db = gw.db
    with _lock:
        current = {c["key"]: c for c in conditions(gw)}
        fresh = []
        with db.tx():
            stored = {r["key"]: r for r in db.q("SELECT * FROM notifications")}
            for key, c in current.items():
                row = stored.get(key)
                if row is None:
                    nid = db.x("INSERT INTO notifications(key, severity, area, title, text, href, first_seen, last_seen)"
                               " VALUES(?,?,?,?,?,?,?,?)", (key, c["severity"], c["area"], c["title"][:200], c["text"][:500],
                                                            c["href"][:200], now, now)).lastrowid
                    fresh.append(nid)
                elif row["resolved"]:
                    # it came back: new again for everyone
                    db.x("UPDATE notifications SET severity = ?, area = ?, title = ?, text = ?, href = ?, first_seen = ?, last_seen = ?,"
                         " resolved = NULL, emailed = NULL WHERE id = ?", (c["severity"], c["area"], c["title"][:200], c["text"][:500],
                                                                          c["href"][:200], now, now, row["id"]))
                    db.x("DELETE FROM notification_reads WHERE notification_id = ?", (row["id"],))
                    fresh.append(row["id"])
                else:
                    db.x("UPDATE notifications SET severity = ?, title = ?, text = ?, href = ?, last_seen = ? WHERE id = ?",
                         (c["severity"], c["title"][:200], c["text"][:500], c["href"][:200], now, row["id"]))
            for key, row in stored.items():
                if key not in current and not row["resolved"]:
                    db.x("UPDATE notifications SET resolved = ? WHERE id = ?", (now, row["id"]))
            # resolved notifications are kept 30 days for the record, then dropped
            db.x("DELETE FROM notifications WHERE resolved IS NOT NULL AND resolved < ?", (now - 30 * 86400,))
        _last[id(db)] = now
    if fresh:
        email_new(gw)
    return fresh


def refresh_if_stale(gw):
    if time.time() - _last.get(id(gw.db), 0) >= REFRESH_SECONDS:
        refresh(gw)


def smtp_settings():
    host, to = os.environ.get("GATEWAY_SMTP_HOST", ""), os.environ.get("GATEWAY_NOTIFY_TO", "")
    if not host or not to:
        return None
    return {"host": host, "port": int(os.environ.get("GATEWAY_SMTP_PORT", "587") or 587),
            "user": os.environ.get("GATEWAY_SMTP_USER", ""), "password": os.environ.get("GATEWAY_SMTP_PASSWORD", ""),
            "sender": os.environ.get("GATEWAY_SMTP_FROM", "") or os.environ.get("GATEWAY_SMTP_USER", "") or "swangz-ai@localhost",
            "to": [a.strip() for a in to.split(",") if a.strip()]}


def email_new(gw, send=None):
    """Email unresolved high and critical notifications that haven't been emailed. -> how many were sent."""
    cfg = smtp_settings()
    if not cfg and send is None:
        return 0
    rows = gw.db.q("SELECT * FROM notifications WHERE resolved IS NULL AND emailed IS NULL AND severity IN ('high', 'critical')"
                   " ORDER BY id")
    if not rows:
        return 0
    base = gw.public_url().rstrip("/") + "/admin"
    msg = EmailMessage()
    msg["Subject"] = f"Swangz AI: {rows[0]['title']}" + (f" (+{len(rows) - 1} more)" if len(rows) > 1 else "")
    msg["From"] = (cfg or {}).get("sender", "swangz-ai@localhost")
    msg["To"] = ", ".join((cfg or {}).get("to", []))
    msg.set_content("\n\n".join(f"[{r['severity'].upper()}] {r['title']}\n{r['text']}\n{base}{r['href']}" for r in rows)
                    + "\n\n— Swangz AI control room. Manage notifications in the console.")
    try:
        (send or _smtp_send)(cfg, msg)
    except (OSError, smtplib.SMTPException) as exc:
        gw.log(f"notifications: email failed: {exc!r}")
        return 0
    now = time.time()
    gw.db.x(f"UPDATE notifications SET emailed = ? WHERE id IN ({','.join('?' * len(rows))})", [now, *[r["id"] for r in rows]])
    return len(rows)


def _smtp_send(cfg, msg):
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
        if cfg["port"] == 587:
            s.starttls()
        if cfg["user"]:
            s.login(cfg["user"], cfg["password"])
        s.send_message(msg)
