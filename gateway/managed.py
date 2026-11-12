"""The managed workspace, server side (docs/MANAGED-WORKSPACE.md, W2, W4 and W5).

One administrator-managed browser workspace per enrolled device. The server never sees inside it: it says whether
the workspace may be open (`active`, `suspended`, `retired`), which generation of it the device should hold, and
which browser-policy baseline the company expects. The app reports what policy it found on the machine; that
report is a tamper signal from software on the person's own computer, never proof and never an input that
GRANTS anything. Everything here can only take access away.

Hard limits: no provider password, cookie, token or session is read, stored or sent here. State lives on the
`devices` row, apart from the device key, so suspending a workspace does not disconnect the device, and neither
does it touch a gateway API key or an automation (W7).
"""

import re
import time

from .admin import ApiError
from .admin import route as admin_route

STATES = ("active", "suspended", "retired")
MODES = ("warn", "enforce")
DEFAULT_MODE = "warn"  # until docs/RELEASE-ACCEPTANCE-GATE.md has the evidence for enforce (MANAGED-WORKSPACE section 7)
POLICY_STALE_SECONDS = 600  # ten missed heartbeats: the report is old, not current
SHA256 = re.compile(r"[0-9a-f]{64}")
ACTIONS = ("suspend", "reactivate", "retire", "reset")
DEVICE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
PLAIN = {"suspended": "Your Swangz workspace on this device is paused by an administrator. Talk to your admin to have it restored.",
         "retired": "Your Swangz workspace on this device was closed by an administrator. Talk to your admin."}


def mode(db):
    value = (db.get_setting("managed_policy_mode", DEFAULT_MODE) or DEFAULT_MODE).strip().lower()
    return value if value in MODES else DEFAULT_MODE


def expected_sha(db):
    value = (db.get_setting("managed_policy_sha256", "") or "").strip().lower()
    return value if SHA256.fullmatch(value) else None


def effective_state(gw, person, device):
    """What the device is told. A person the account rule no longer allows has no workspace, whatever the row says."""
    if not gw.settings.email_allowed(person["email"]):
        return "retired"
    return device["workspace_state"] if device.get("workspace_state") in STATES else "retired"  # unreadable fails closed


def block(gw, person, device, base):
    """Contract 2: contract 1's block plus the workspace state and the policy baseline. Built only from the
    authenticated person and device rows and from settings, never from the request."""
    state = effective_state(gw, person, device)
    out = dict(base, contract=2)
    out["workspace"] = {"state": state, "generation": int(device.get("workspace_generation") or 1)}
    out["policy"] = {"sha256": expected_sha(gw.db), "mode": mode(gw.db)}
    return out


def heartbeat_answer(gw, person, device):
    """Added to the heartbeat answer of an app that asks for contract 2. Small by design: far under 2 KB."""
    return {"workspace": {"state": effective_state(gw, person, device), "generation": int(device.get("workspace_generation") or 1)},
            "policy": {"sha256": expected_sha(gw.db), "mode": mode(gw.db)}}


def record_policy_report(ctx, person, device, now):
    """`policy: {"ok": bool, "sha256": "<64 hex>"}` in a heartbeat. Absent or malformed: nothing recorded and nothing
    changes. Only the app's own claim; the console shows it as "reported by the app"."""
    report = ctx.body.get("policy")
    if not isinstance(report, dict) or not isinstance(report.get("ok"), bool):
        return
    sha = str(report.get("sha256") or "").lower()
    sha = sha if SHA256.fullmatch(sha) else ""
    ok = 1 if report["ok"] else 0
    ctx.db.x("UPDATE devices SET policy_ok = ?, policy_sha = ?, policy_reported = ? WHERE device_id = ?", (ok, sha, now, device["device_id"]))
    if not ok and device.get("policy_ok") != 0:  # only the move to failing is worth a line in the audit log
        ctx.gw.audit(person["name"], "device reported its browser policy is not in force", person["name"], device["name"], ctx.ip,
                     before={"policy_ok": device.get("policy_ok")}, after={"policy_ok": 0, "reported_by": "the app"},
                     correlation=f"device:{device['device_id']}")


def policy_problem(db, device, now):
    """Why `enforce` would refuse this device, or None. Missing, stale, failing, or not the baseline the company expects."""
    if device.get("policy_ok") is None or not device.get("policy_reported"):
        return "has not reported its browser policy"
    if now - device["policy_reported"] > POLICY_STALE_SECONDS:
        return "has not reported its browser policy recently"
    if not device["policy_ok"]:
        return "reports that its browser policy is not in force"
    want = expected_sha(db)
    if want and device.get("policy_sha") != want:
        return "is not running the browser policy the company expects"
    return None


def launch_refusal(gw, person, query):
    """For /go: the device the Open came from may say who it is with `d=<device id>`. The claim is only ever used to
    REFUSE: a device that is not this person's is ignored, and leaving it out opens nothing that was closed (the
    app and the machine policy are what hold the line on the device; this is a second check on the way in).
    -> (plain reason, rule) or None."""
    ids = query.get("d") or []
    if len(ids) != 1 or not DEVICE_ID.fullmatch(ids[0]):
        return None
    device = gw.db.one("SELECT * FROM devices WHERE device_id = ? AND person_id = ?", (ids[0], person["id"]))
    if not device:
        return None
    state = effective_state(gw, person, device)
    if state != "active":
        return PLAIN[state], f"workspace_{state}"
    if mode(gw.db) == "enforce":
        problem = policy_problem(gw.db, device, time.time())
        if problem:
            return (f"This device {problem}, so your Swangz workspace cannot open a provider. Check that the company browser "
                    "settings are installed, or talk to your admin."), "workspace_policy"
    return None


@admin_route("POST", r"/devices/(?P<device_id>[A-Za-z0-9_-]{1,64})/workspace", area=("govern", "emergency"))
def set_workspace(ctx, device_id):
    """suspend | reactivate | retire | reset. The app closes the workspace within one heartbeat of `suspended`,
    deletes the profile folder on `retired` or a higher generation, and keeps the sign-in on `reactivate` from
    `suspended`. Nothing here touches the device key or any API key."""
    action = str(ctx.body.get("action") or "")
    if action not in ACTIONS:
        raise ApiError(400, "action must be one of: " + ", ".join(ACTIONS))
    row = ctx.db.one("SELECT d.*, p.name AS person FROM devices d JOIN people p ON p.id = d.person_id WHERE d.device_id = ?", (device_id,))
    if not row:
        raise ApiError(404, "no such device")
    before = {"state": row["workspace_state"], "generation": row["workspace_generation"]}
    state, generation = row["workspace_state"], row["workspace_generation"]
    if action == "suspend":
        if state == "retired":
            raise ApiError(409, "This workspace was already closed for good. Reactivate it first to start a new one.", "workspace_retired")
        state = "suspended"
    elif action == "reactivate":
        if state == "retired":
            generation += 1  # a new workspace: the device must not trust any folder it still has
        state = "active"
    elif action == "retire":
        state = "retired"
    else:  # reset: a company seat changed hands, so a folder signed in by the last holder is not this person's
        if state == "retired":
            raise ApiError(409, "This workspace was already closed for good.", "workspace_retired")
        generation += 1
    after = {"state": state, "generation": generation}
    if after != before:
        ctx.db.x("UPDATE devices SET workspace_state = ?, workspace_generation = ?, workspace_changed = ?, workspace_changed_by = ?"
                 " WHERE device_id = ?", (state, generation, time.time(), ctx.admin["username"], device_id))
        ctx.audit(f"{action} the workspace on a device", row["person"], row["name"], before=before, after=after, correlation=f"device:{device_id}")
    return {"ok": True, "workspace": after, "changed": after != before}
