"""Who may change what in the control room — decided here and nowhere else.

Every console user can see everything: that is what the control room is for, and seeing is audited
where it matters (opening a full record, exporting). Changing things is split into areas, and a role is
a set of areas. Routes name the area they need (`admin.route(..., area=...)`); the dispatcher asks
`can()` before the handler runs, so no handler re-implements the check and nothing is enforced only in
the browser.

Storage stays compatible with the original owner/viewer model: an owner is `role = 'owner'`; every other
role is `role = 'viewer'` plus the areas it may change (`admins.areas`, v13).
"""

AREAS = {
    "govern": "People, devices, tools, access, policies, models, purposes and the company browsers",
    "money": "Prices, media rates, subscriptions and budgets",
    "trust": "Incidents, known networks and security settings",
    "emergency": "Stop all AI, cut a request, suspend a person, revoke a device or tool, end a turn, switch a provider off",
    "admin": "Console users and roles, privacy and retention settings",
}

# name -> (label, areas it may change, one line for the console)
ROLES = {
    "owner": ("Owner", frozenset(AREAS), "Can change everything, including console users and privacy settings."),
    "operations": ("Operations admin", frozenset({"govern", "emergency"}),
                   "Runs people, tools, access, policies and the company browsers; can use the emergency controls."),
    "security": ("Security admin", frozenset({"trust", "emergency"}),
                 "Investigates: incidents, known networks, security settings; can use the emergency controls."),
    "billing": ("Billing admin", frozenset({"money"}), "Prices, media rates, subscriptions and budgets."),
    "viewer": ("Viewer", frozenset(), "Can see everything, change nothing."),
}


def _split(areas):
    return frozenset(a.strip() for a in (areas or "").split(",") if a.strip() in AREAS)


def areas_of(admin):
    """The areas this console user may change."""
    if not admin:
        return frozenset()
    if admin.get("role") == "owner":
        return frozenset(AREAS)
    return _split(admin.get("areas"))


def role_of(admin):
    """The named role that matches this user's areas; 'custom' when none does."""
    if not admin:
        return "viewer"
    if admin.get("role") == "owner":
        return "owner"
    mine = areas_of(admin)
    for name, (_label, areas, _about) in ROLES.items():
        if name != "owner" and areas == mine:
            return name
    return "custom"


def label_of(admin):
    role = role_of(admin)
    return ROLES[role][0] if role in ROLES else "Custom"


def can(admin, area):
    """True when this console user may change things in `area` (a name, or a tuple meaning any of)."""
    if area is None:
        return True
    wanted = (area,) if isinstance(area, str) else tuple(area)
    mine = areas_of(admin)
    return any(a in mine for a in wanted)


def stored(role, areas=None):
    """A role name (or custom areas) -> the (role, areas) columns to store."""
    if role == "owner":
        return "owner", ""
    if role in ROLES:
        return "viewer", ",".join(sorted(ROLES[role][1]))
    if role == "custom":
        chosen = _split(",".join(areas or []))
        return "viewer", ",".join(sorted(chosen))
    raise ValueError(f"unknown role {role!r}")


def describe(admin):
    """What the console tells the signed-in user about their own authority."""
    return {"role": role_of(admin), "role_label": label_of(admin), "can": sorted(areas_of(admin)),
            "owner": bool(admin and admin.get("role") == "owner")}
