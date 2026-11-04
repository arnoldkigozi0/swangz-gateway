"""Device credential lifecycle shared by the routes that need it (D-002).

A device is one `devices` row with a stable `device_id`; over its life it holds several gateway keys
(`keys.device_id`), because the Swangz app rotates its key. Everything that ends a device must end ALL its
keys, and everything that asks "is this device still in use" must look across all of them."""

import time

DAY = 86400
IDLE_DAYS_DEFAULT = 60
IDLE_DAYS_MIN, IDLE_DAYS_MAX = 7, 365
ROTATE_AFTER_DAYS = 30
GRACE_SECONDS = 600
ROTATIONS_PER_HOUR = 3
ROTATED = ("system: rotated", "system: reissued")  # a key replaced by a newer one: never a reason to wipe the device
KEY_STORAGE = ("keychain", "file")
KEY_BACKENDS = ("credential-manager", "keychain", "secret-service")


def idle_days(db):
    try:
        days = int(db.get_setting("device_idle_days", str(IDLE_DAYS_DEFAULT)) or IDLE_DAYS_DEFAULT)
    except ValueError:
        days = IDLE_DAYS_DEFAULT
    return min(max(days, IDLE_DAYS_MIN), IDLE_DAYS_MAX)


def revoke_device_keys(db, live, key_id, by, reason="this device was disconnected.", now=None):
    """Revoke a key and, when it belongs to a device, every other unrevoked key of that device, in one statement,
    then cut what is in flight on each (`live` is None on the command line). -> (ids revoked, requests cut)."""
    now = time.time() if now is None else now
    with db.tx():
        row = db.one("SELECT id, device_id FROM keys WHERE id = ?", (key_id,))
        if not row:
            return [], 0
        ids = [r["id"] for r in db.q("SELECT id FROM keys WHERE revoked IS NULL AND (id = ? OR (device_id IS NOT NULL AND device_id = ?))",
                                     (key_id, row["device_id"]))]
        for kid in ids:
            db.x("UPDATE keys SET revoked = ?, revoked_by = ? WHERE id = ? AND revoked IS NULL", (now, by, kid))
    cut = sum(live.cut(reason, key_id=kid) for kid in ids) if live else 0
    return ids, cut


def active_device_count(db, person_id):
    """Devices with an active key, plus hand-made keys: the number the ten-device limit counts. A device that is
    mid-rotation holds two keys but is one device."""
    return db.scalar(
        "SELECT COUNT(*) FROM (SELECT id FROM keys WHERE person_id = ? AND revoked IS NULL AND device_id IS NULL"
        " UNION SELECT device_id FROM keys WHERE person_id = ? AND revoked IS NULL AND device_id IS NOT NULL)",
        (person_id, person_id)) or 0


def expire_idle(gw, now=None):
    """Hourly: revoke every device with no activity for `device_idle_days`. Activity is the newest of the app's
    last check-in, enrolment, and any of its keys being used (proxy use counts). A refused attempt on a key that was
    already revoked is not activity (the proxy stamps last_used before it checks), so only use made while the key was
    valid counts. -> number revoked."""
    db = gw.db
    now = time.time() if now is None else now
    days = idle_days(db)
    cutoff = now - days * DAY
    # the 10-minute grace is enforced when a key is used; make it true in the records too
    db.x("UPDATE keys SET revoked = retire_at, revoked_by = 'system: rotated' WHERE revoked IS NULL AND retire_at IS NOT NULL AND retire_at <= ?", (now,))
    n = 0
    for d in db.q("SELECT d.device_id, d.person_id, d.name, d.enrolled, d.last_seen, MAX(CASE WHEN k.revoked IS NULL OR k.last_used <= k.revoked THEN k.last_used END) AS used, p.name AS person"
                  " FROM devices d JOIN keys k ON k.device_id = d.device_id JOIN people p ON p.id = d.person_id"
                  " WHERE d.device_id IS NOT NULL GROUP BY d.device_id HAVING SUM(k.revoked IS NULL) > 0"):
        last = max(d["enrolled"] or 0, d["last_seen"] or 0, d["used"] or 0)
        if last >= cutoff:
            continue
        ids = [r["id"] for r in db.q("SELECT id FROM keys WHERE device_id = ? AND revoked IS NULL", (d["device_id"],))]
        if not ids:
            continue
        db.x("UPDATE keys SET revoked = ?, revoked_by = 'system: idle' WHERE device_id = ? AND revoked IS NULL", (now, d["device_id"]))
        for kid in ids:
            gw.live.cut("this device was disconnected after being idle.", key_id=kid)
        gw.audit("system", "revoked an idle device", d["person"], f"{d['name']}: no activity for {days} days",
                 before={"keys": ids, "last_active": last}, after={"revoked_by": "system: idle", "idle_days": days},
                 correlation=f"device:{d['device_id']}", area="trust")
        n += 1
    return n
