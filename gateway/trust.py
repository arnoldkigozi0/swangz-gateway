"""The Trust area's API: where requests come from (known networks, the location table), incidents, and
the notifications the control room raises.

Reading is open to every console user; changing networks and incidents needs the trust area
(gateway/authz.py). Every change is audited with what it was before and after.
"""

import ipaddress
import time

from . import geo
from .admin import ApiError, route

NETWORK_KINDS = ("office", "vpn", "home", "cloud", "other")


# ---------------------------------------------------------------- where: known networks and the location table


@route("GET", r"/geo")
def geo_status(ctx):
    networks = ctx.db.q("SELECT id, cidr, label, place, kind, created, created_by FROM networks ORDER BY label COLLATE NOCASE")
    return {"table": geo.status(ctx.db), "networks": networks}


@route("GET", r"/geo/lookup")
def geo_lookup(ctx):
    """What the gateway can say about one address, and how it knows."""
    ip = ctx.arg("ip", "")
    if not ip:
        raise ApiError(400, "give an address: ?ip=")
    return geo.describe(ip, ctx.db)


def _network_values(body, partial=False):
    out = {}
    if "cidr" in body or not partial:
        try:
            net = ipaddress.ip_network(str(body.get("cidr") or "").strip(), strict=False)
        except ValueError:
            raise ApiError(400, "cidr must be a network such as 41.210.145.0/24 or a single address")
        if net.prefixlen == 0:
            raise ApiError(400, "that network covers every address; name something smaller")
        out["cidr"] = str(net)
    if "label" in body or not partial:
        label = str(body.get("label") or "").strip()[:80]
        if not label:
            raise ApiError(400, "give the network a name, e.g. Swangz office")
        out["label"] = label
    if "place" in body:
        out["place"] = str(body.get("place") or "").strip()[:80]
    if "kind" in body:
        if body["kind"] not in NETWORK_KINDS:
            raise ApiError(400, "kind must be one of: " + ", ".join(NETWORK_KINDS))
        out["kind"] = body["kind"]
    return out


@route("POST", r"/networks", area="trust")
def add_network(ctx):
    values = _network_values(ctx.body)
    if ctx.db.one("SELECT 1 FROM networks WHERE cidr = ?", (values["cidr"],)):
        raise ApiError(400, "that network is already named")
    rid = ctx.db.x("INSERT INTO networks(cidr, label, place, kind, created, created_by) VALUES(?,?,?,?,?,?)",
                   (values["cidr"], values["label"], values.get("place", ""), values.get("kind", "office"), time.time(),
                    ctx.admin["username"])).lastrowid
    geo.invalidate()
    ctx.audit("named a network", values["label"], values["cidr"], after=values, correlation=f"network:{rid}")
    return {"ok": True, "id": rid}


@route("PATCH", r"/networks/(?P<nid>\d+)", area="trust")
def edit_network(ctx, nid):
    row = ctx.db.one("SELECT * FROM networks WHERE id = ?", (int(nid),))
    if not row:
        raise ApiError(404, "no such network")
    values = _network_values(ctx.body, partial=True)
    if values:
        ctx.db.x(f"UPDATE networks SET {', '.join(f'{k} = ?' for k in values)} WHERE id = ?", [*values.values(), row["id"]])
        geo.invalidate()
        ctx.audit("changed a network", row["label"], ", ".join(sorted(values)), before={k: row[k] for k in values},
                  after=values, correlation=f"network:{nid}")
    return {"ok": True}


@route("DELETE", r"/networks/(?P<nid>\d+)", area="trust")
def remove_network(ctx, nid):
    row = ctx.db.one("SELECT * FROM networks WHERE id = ?", (int(nid),))
    if not row:
        raise ApiError(404, "no such network")
    ctx.db.x("DELETE FROM networks WHERE id = ?", (row["id"],))
    geo.invalidate()
    ctx.audit("removed a network name", row["label"], row["cidr"], before=row, correlation=f"network:{nid}")
    return {"ok": True}


# ---------------------------------------------------------------- incidents

SEVERITIES = ("low", "medium", "high", "critical")
STATUSES = ("open", "investigating", "contained", "resolved", "dismissed")
CLOSED = ("resolved", "dismissed")
TRANSITIONS = {
    "open": ("investigating", "contained", "resolved", "dismissed"),
    "investigating": ("contained", "resolved", "dismissed"),
    "contained": ("investigating", "resolved"),
    "resolved": ("open",),
    "dismissed": ("open",),
}
LINK_KINDS = ("person", "device", "request", "tool", "session", "event")


def _link_label(db, kind, ref):
    """What a link points at, checked: (label, error)."""
    if kind == "person":
        row = db.one("SELECT name FROM people WHERE id = ?", (int(ref) if str(ref).isdigit() else -1,))
        return (row["name"], None) if row else (None, "no such person")
    if kind == "device":
        row = db.one("SELECT k.label, p.name FROM keys k JOIN people p ON p.id = k.person_id WHERE k.id = ?", (ref,))
        return (f"{row['label']} ({row['name']})", None) if row else (None, "no such device")
    if kind == "request":
        row = db.one("SELECT r.id, r.model, p.name FROM requests r LEFT JOIN people p ON p.id = r.person_id WHERE r.id = ?",
                     (int(ref) if str(ref).isdigit() else -1,))
        return (f"Request #{row['id']}" + (f" · {row['name']}" if row["name"] else ""), None) if row else (None, "no such request")
    if kind == "tool":
        row = db.one("SELECT name FROM tools WHERE id = ?", (ref,))
        return (row["name"], None) if row else (None, "no such tool")
    if kind == "session":
        return (("Session " + str(ref)[:24]), None) if db.one("SELECT 1 FROM requests WHERE session = ? LIMIT 1", (ref,)) \
            else (None, "no such session")
    return (str(ref)[:120], None)  # a security event: its own description


def _note(db, iid, author, text, kind="note"):
    db.x("INSERT INTO incident_notes(incident_id, ts, author, kind, text) VALUES(?,?,?,?,?)", (iid, time.time(), author, kind, text[:4000]))
    db.x("UPDATE incidents SET updated = ? WHERE id = ?", (time.time(), iid))


def _incident(ctx, iid):
    row = ctx.db.one("SELECT * FROM incidents WHERE id = ?", (int(iid),))
    if not row:
        raise ApiError(404, "no such incident")
    return row


@route("GET", r"/incidents")
def list_incidents(ctx):
    state = ctx.arg("status", "active")
    where = {"active": "status NOT IN ('resolved', 'dismissed')", "closed": "status IN ('resolved', 'dismissed')", "all": "1"}.get(state)
    if where is None:
        raise ApiError(400, "status must be active, closed or all")
    rows = ctx.db.q(f"SELECT i.*, (SELECT COUNT(*) FROM incident_links l WHERE l.incident_id = i.id) AS links,"
                    f" (SELECT COUNT(*) FROM incident_notes n WHERE n.incident_id = i.id AND n.kind = 'note') AS notes"
                    f" FROM incidents i WHERE {where} ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
                    " WHEN 'medium' THEN 2 ELSE 3 END, updated DESC LIMIT 500")
    counts = {r["status"]: r["n"] for r in ctx.db.q("SELECT status, COUNT(*) AS n FROM incidents GROUP BY status")}
    return {"items": rows, "counts": counts, "statuses": STATUSES, "severities": SEVERITIES}


@route("GET", r"/incidents/(?P<iid>\d+)")
def get_incident(ctx, iid):
    row = _incident(ctx, iid)
    links = ctx.db.q("SELECT * FROM incident_links WHERE incident_id = ? ORDER BY added, id", (row["id"],))
    notes = ctx.db.q("SELECT * FROM incident_notes WHERE incident_id = ? ORDER BY ts, id", (row["id"],))
    trail = ctx.db.q("SELECT ts, actor, action, detail, outcome FROM audit WHERE correlation = ? ORDER BY id", (f"incident:{row['id']}",))
    return {**row, "links_list": links, "notes_list": notes, "trail": trail, "next": TRANSITIONS[row["status"]]}


@route("POST", r"/incidents", area="trust")
def open_incident(ctx):
    b = ctx.body
    title = str(b.get("title") or "").strip()[:200]
    if not title:
        raise ApiError(400, "give the incident a title")
    severity = b.get("severity") or "medium"
    if severity not in SEVERITIES:
        raise ApiError(400, "severity must be low, medium, high or critical")
    links = []
    for link in b.get("links") or []:
        kind, ref = (link or {}).get("kind"), str((link or {}).get("ref") or "").strip()[:200]
        if kind not in LINK_KINDS or not ref:
            raise ApiError(400, "each link needs a kind (" + ", ".join(LINK_KINDS) + ") and a ref")
        label, err = _link_label(ctx.db, kind, ref)
        if err:
            raise ApiError(400, err)
        links.append((kind, ref, str(link.get("label") or label)[:200]))
    now, who = time.time(), ctx.admin["username"]
    with ctx.db.tx():
        iid = ctx.db.x("INSERT INTO incidents(title, severity, owner, summary, source, created, created_by, updated)"
                       " VALUES(?,?,?,?,?,?,?,?)", (title, severity, str(b.get("owner") or who)[:80], str(b.get("summary") or "")[:4000],
                                                     str(b.get("source") or "")[:120], now, who, now)).lastrowid
        for kind, ref, label in links:
            ctx.db.x("INSERT OR IGNORE INTO incident_links(incident_id, kind, ref, label, added, added_by) VALUES(?,?,?,?,?,?)",
                     (iid, kind, ref, label, now, who))
        _note(ctx.db, iid, who, f"Opened with {severity} severity" + (f" from {b['source']}" if b.get("source") else "") + ".", "status")
    ctx.audit("opened an incident", title, severity, after={"severity": severity, "links": len(links)}, correlation=f"incident:{iid}")
    return {"ok": True, "id": iid}


@route("PATCH", r"/incidents/(?P<iid>\d+)", area="trust")
def update_incident(ctx, iid):
    row = _incident(ctx, iid)
    b, who = ctx.body, ctx.admin["username"]
    changes = {}
    for key, limit in (("title", 200), ("owner", 80), ("summary", 4000), ("resolution", 4000)):
        if key in b:
            changes[key] = str(b[key] or "").strip()[:limit]
    if "title" in changes and not changes["title"]:
        raise ApiError(400, "an incident needs a title")
    if "severity" in b:
        if b["severity"] not in SEVERITIES:
            raise ApiError(400, "severity must be low, medium, high or critical")
        changes["severity"] = b["severity"]
    if "status" in b and b["status"] != row["status"]:
        status = b["status"]
        if status not in TRANSITIONS[row["status"]]:
            raise ApiError(400, f"an incident that is {row['status']} can go to: " + ", ".join(TRANSITIONS[row["status"]]))
        if status in CLOSED and not (changes.get("resolution") or row["resolution"]):
            raise ApiError(400, "say how it ended: a resolution is needed to close an incident")
        changes["status"] = status
        if status in CLOSED:
            changes["closed"], changes["closed_by"] = time.time(), who
        else:
            changes["closed"], changes["closed_by"] = None, ""
    changes = {k: v for k, v in changes.items() if row.get(k) != v}
    if not changes:
        return {"ok": True}
    with ctx.db.tx():
        ctx.db.x(f"UPDATE incidents SET {', '.join(f'{k} = ?' for k in changes)}, updated = ? WHERE id = ?",
                 [*changes.values(), time.time(), row["id"]])
        if "status" in changes:
            _note(ctx.db, row["id"], who, f"{row['status'].capitalize()} → {changes['status']}"
                  + (f": {changes.get('resolution') or row['resolution']}" if changes["status"] in CLOSED else "."), "status")
        if "severity" in changes:
            _note(ctx.db, row["id"], who, f"Severity {row['severity']} → {changes['severity']}.", "status")
    shown = {k: v for k, v in changes.items() if k not in ("closed", "closed_by")}
    ctx.audit("changed an incident", row["title"], ", ".join(sorted(shown)), before={k: row[k] for k in shown}, after=shown,
              correlation=f"incident:{row['id']}")
    return {"ok": True}


@route("POST", r"/incidents/(?P<iid>\d+)/notes", area="trust")
def add_incident_note(ctx, iid):
    row = _incident(ctx, iid)
    text = str(ctx.body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "write the note first")
    _note(ctx.db, row["id"], ctx.admin["username"], text)
    ctx.audit("added a note to an incident", row["title"], text[:120], correlation=f"incident:{row['id']}")
    return {"ok": True}


@route("POST", r"/incidents/(?P<iid>\d+)/links", area="trust")
def add_incident_link(ctx, iid):
    row = _incident(ctx, iid)
    kind, ref = ctx.body.get("kind"), str(ctx.body.get("ref") or "").strip()[:200]
    if kind not in LINK_KINDS or not ref:
        raise ApiError(400, "a link needs a kind (" + ", ".join(LINK_KINDS) + ") and a ref")
    label, err = _link_label(ctx.db, kind, ref)
    if err:
        raise ApiError(400, err)
    label = str(ctx.body.get("label") or label)[:200]
    added = ctx.db.x("INSERT OR IGNORE INTO incident_links(incident_id, kind, ref, label, added, added_by) VALUES(?,?,?,?,?,?)",
                     (row["id"], kind, ref, label, time.time(), ctx.admin["username"])).rowcount
    if added:
        ctx.db.x("UPDATE incidents SET updated = ? WHERE id = ?", (time.time(), row["id"]))
        ctx.audit("linked evidence to an incident", row["title"], f"{kind}: {label}", correlation=f"incident:{row['id']}")
    return {"ok": True, "added": bool(added)}


@route("DELETE", r"/incidents/(?P<iid>\d+)/links/(?P<lid>\d+)", area="trust")
def remove_incident_link(ctx, iid, lid):
    row = _incident(ctx, iid)
    link = ctx.db.one("SELECT * FROM incident_links WHERE id = ? AND incident_id = ?", (int(lid), row["id"]))
    if not link:
        raise ApiError(404, "no such link")
    ctx.db.x("DELETE FROM incident_links WHERE id = ?", (link["id"],))
    ctx.audit("unlinked evidence from an incident", row["title"], f"{link['kind']}: {link['label']}", before=link,
              correlation=f"incident:{row['id']}")
    return {"ok": True}


# ---------------------------------------------------------------- notifications


@route("GET", r"/notifications")
def list_notifications(ctx):
    from . import notify

    notify.refresh_if_stale(ctx.gw)
    everything = ctx.arg("all") == "1"
    rows = ctx.db.q("SELECT n.*, r.read FROM notifications n LEFT JOIN notification_reads r ON r.notification_id = n.id AND r.admin_id = ?"
                    + ("" if everything else " WHERE n.resolved IS NULL")
                    + " ORDER BY n.resolved IS NOT NULL, CASE n.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'warning' THEN 2"
                      " WHEN 'notice' THEN 3 ELSE 4 END, n.last_seen DESC LIMIT 300", (ctx.admin["id"],))
    unread = sum(1 for r in rows if not r["read"] and not r["resolved"])
    return {"items": rows, "unread": unread, "email": bool(notify.smtp_settings())}


@route("POST", r"/notifications/read")
def read_notifications(ctx):
    """Mark notifications read for this console user only. `ids`, or `all: true`."""
    if ctx.body.get("all"):
        ids = [r["id"] for r in ctx.db.q("SELECT id FROM notifications WHERE resolved IS NULL")]
    else:
        try:
            ids = [int(i) for i in ctx.body.get("ids") or []][:500]
        except (TypeError, ValueError):
            raise ApiError(400, "ids must be numbers")
    now = time.time()
    for nid in ids:
        ctx.db.x("INSERT OR IGNORE INTO notification_reads(notification_id, admin_id, read)"
                 " SELECT id, ?, ? FROM notifications WHERE id = ?", (ctx.admin["id"], now, nid))
    return {"ok": True, "read": len(ids)}
