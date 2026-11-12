"""Forward-only v26: what the Hub knows about a device's managed workspace (docs/MANAGED-WORKSPACE.md).

Seven columns on `devices`, nothing else. `workspace_state` is the administrator's decision about the one managed
browser workspace on that device; it is separate from the device key, so suspending a workspace and reactivating
it later does not make the person enrol again. `workspace_generation` goes up when a company seat is reassigned,
so a device can tell its saved profile now belongs to someone else's seat. The `policy_*` columns hold what the
app REPORTED about the browser policy on the machine: a tamper signal, never proof and never a secret.
No provider password, cookie, token or session is stored here, and no earlier table is changed."""

MIGRATION = (
    "ALTER TABLE devices ADD COLUMN workspace_state TEXT NOT NULL DEFAULT 'active' CHECK (workspace_state IN ('active','suspended','retired'))",
    "ALTER TABLE devices ADD COLUMN workspace_generation INTEGER NOT NULL DEFAULT 1 CHECK (workspace_generation >= 1)",
    "ALTER TABLE devices ADD COLUMN workspace_changed REAL",
    "ALTER TABLE devices ADD COLUMN workspace_changed_by TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE devices ADD COLUMN policy_ok INTEGER CHECK (policy_ok IN (0,1))",
    "ALTER TABLE devices ADD COLUMN policy_sha TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE devices ADD COLUMN policy_reported REAL",
)
