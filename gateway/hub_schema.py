"""Schema v19: native adoption, accountability and procurement. Existing tables are preserved."""
DECLARATIONS = """
    usage_confirmation TEXT CHECK(usage_confirmation IN ('used','opened_not_used','accidental')),
    reason TEXT NOT NULL DEFAULT '',
    impact TEXT NOT NULL DEFAULT '',
    deliverables TEXT NOT NULL DEFAULT '',
    quality TEXT NOT NULL DEFAULT '',
    challenges TEXT NOT NULL DEFAULT '',
    issues TEXT NOT NULL DEFAULT '',
    next_steps TEXT NOT NULL DEFAULT '',
    manual_hours REAL CHECK(manual_hours >= 0),
    ai_hours REAL CHECK(ai_hours >= 0),
    manual_cost REAL CHECK(manual_cost >= 0),
    ai_cost REAL CHECK(ai_cost >= 0),
    subscription_cost REAL CHECK(subscription_cost >= 0),
    extra_credits REAL CHECK(extra_credits >= 0),
    other_expenses REAL CHECK(other_expenses >= 0),
    revenue REAL CHECK(revenue >= 0),
    revenue_description TEXT NOT NULL DEFAULT '',
    frequency REAL CHECK(frequency >= 0),
    usage_amount REAL CHECK(usage_amount >= 0),
    usage_unit TEXT NOT NULL DEFAULT '',
    pricing_source TEXT NOT NULL DEFAULT '',
    selected_plan TEXT NOT NULL DEFAULT '',
    usage_included REAL CHECK(usage_included >= 0),
    usage_unit_cost_usd REAL CHECK(usage_unit_cost_usd >= 0),
    usage_cost_usd REAL CHECK(usage_cost_usd >= 0),
    usage_flat_rate INTEGER CHECK(usage_flat_rate IN (0,1)),
    currency TEXT NOT NULL DEFAULT 'USD',
    claimed_requests INTEGER CHECK(claimed_requests >= 0),
    claimed_access_events INTEGER CHECK(claimed_access_events >= 0),
    claimed_days INTEGER CHECK(claimed_days BETWEEN 0 AND 7)
"""
MIGRATION = """
ALTER TABLE keys ADD COLUMN hub_tool_id TEXT REFERENCES tools(id);
ALTER TABLE requests ADD COLUMN hub_tool_id TEXT REFERENCES tools(id) ON DELETE SET NULL;
CREATE TABLE weekly_evidence (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    tool_id TEXT NOT NULL REFERENCES tools(id),
    week_start TEXT NOT NULL,
    timezone TEXT NOT NULL,
    starts REAL NOT NULL,
    ends REAL NOT NULL,
    compiled REAL NOT NULL,
    department TEXT NOT NULL DEFAULT '',
    api_requests INTEGER NOT NULL DEFAULT 0,
    api_success INTEGER NOT NULL DEFAULT 0,
    api_failed INTEGER NOT NULL DEFAULT 0,
    launches INTEGER NOT NULL DEFAULT 0,
    access_events INTEGER NOT NULL DEFAULT 0,
    tab_open_seconds INTEGER NOT NULL DEFAULT 0,
    shared_turns INTEGER NOT NULL DEFAULT 0,
    shared_occupancy_seconds INTEGER NOT NULL DEFAULT 0,
    media_requests INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_api_cost REAL,
    unpriced_requests INTEGER NOT NULL DEFAULT 0,
    active_days INTEGER NOT NULL DEFAULT 0,
    last_activity REAL,
    completeness TEXT NOT NULL,
    limitations TEXT NOT NULL,
    UNIQUE(person_id, tool_id, week_start)
);
CREATE TABLE weekly_evidence_events (
    evidence_id INTEGER NOT NULL REFERENCES weekly_evidence(id),
    source TEXT NOT NULL CHECK(source IN ('requests','launches','site_usage','tool_turns')),
    source_id INTEGER NOT NULL,
    ts REAL NOT NULL,
    outcome TEXT NOT NULL,
    model TEXT,
    cost_source TEXT,
    PRIMARY KEY(evidence_id, source, source_id)
);
CREATE TABLE hub_reports (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('weekly','adoption')),
    person_id INTEGER REFERENCES people(id),
    tool_id TEXT REFERENCES tools(id),
    evidence_id INTEGER UNIQUE REFERENCES weekly_evidence(id),
    week_start TEXT,
    department TEXT NOT NULL DEFAULT '',
    submitter_name TEXT NOT NULL DEFAULT '',
    submitter_email TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL DEFAULT '',
    official_url TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','submitted','reviewed','confirmed','returned','resubmitted')),
    created REAL NOT NULL,
    updated REAL NOT NULL,
    submitted REAL,
    version INTEGER NOT NULL DEFAULT 0,
    reviewer_id INTEGER REFERENCES admins(id),
    reviewed REAL,
    reviewer_note TEXT NOT NULL DEFAULT '',
    reconciliation TEXT NOT NULL DEFAULT 'insufficient_telemetry',
    reconciliation_reason TEXT NOT NULL DEFAULT '',
    reconciliation_tolerance REAL NOT NULL DEFAULT 0.1,
""" + DECLARATIONS + """,
    CHECK((kind = 'weekly' AND person_id IS NOT NULL AND tool_id IS NOT NULL AND evidence_id IS NOT NULL AND week_start IS NOT NULL) OR kind = 'adoption')
);
CREATE UNIQUE INDEX hub_report_week ON hub_reports(person_id,tool_id,week_start) WHERE kind = 'weekly';
CREATE INDEX hub_reports_filters ON hub_reports(kind,week_start,state,person_id,tool_id);
CREATE TABLE hub_report_projects (
    report_id INTEGER NOT NULL REFERENCES hub_reports(id),
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    traditional TEXT NOT NULL DEFAULT '',
    ai_way TEXT NOT NULL DEFAULT '',
    benefit TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(report_id,position)
);
CREATE TABLE hub_report_versions (
    report_id INTEGER NOT NULL REFERENCES hub_reports(id),
    version INTEGER NOT NULL,
    submitted REAL NOT NULL,
    actor TEXT NOT NULL,
    declaration_json TEXT NOT NULL,
    reconciliation TEXT NOT NULL,
    reconciliation_reason TEXT NOT NULL,
    PRIMARY KEY(report_id,version)
);
CREATE TABLE hub_report_reviews (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES hub_reports(id),
    version INTEGER NOT NULL,
    admin_id INTEGER REFERENCES admins(id),
    actor TEXT NOT NULL,
    ts REAL NOT NULL,
    action TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE weekly_overrides (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    tool_id TEXT NOT NULL REFERENCES tools(id),
    starts REAL NOT NULL,
    expires REAL NOT NULL,
    admin_id INTEGER NOT NULL REFERENCES admins(id),
    reason TEXT NOT NULL,
    CHECK(expires > starts)
);
CREATE TABLE procurement_requests (
    id INTEGER PRIMARY KEY,
    person_id INTEGER REFERENCES people(id),
    tool_id TEXT REFERENCES tools(id),
    submitter_name TEXT NOT NULL DEFAULT '',
    submitter_email TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL,
    official_url TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    purchase_type TEXT NOT NULL CHECK(purchase_type IN ('new_tool','subscription','licence','credits','other')),
    reason TEXT NOT NULL,
    business_impact TEXT NOT NULL DEFAULT '',
    requested_plan TEXT NOT NULL DEFAULT '',
    estimated_monthly_cost REAL CHECK(estimated_monthly_cost >= 0),
    estimated_one_time_cost REAL CHECK(estimated_one_time_cost >= 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    state TEXT NOT NULL DEFAULT 'submitted' CHECK(state IN ('submitted','reviewed','approved','rejected','purchased')),
    created REAL NOT NULL,
    updated REAL NOT NULL,
    reviewer_id INTEGER REFERENCES admins(id),
    admin_note TEXT NOT NULL DEFAULT '',
    security_checked INTEGER NOT NULL DEFAULT 0,
    subscription_checked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE procurement_reviews (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES procurement_requests(id),
    actor TEXT NOT NULL,
    ts REAL NOT NULL,
    previous_state TEXT NOT NULL,
    state TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE tracker_imports (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    imported REAL NOT NULL,
    original_json TEXT NOT NULL,
    PRIMARY KEY(source,source_id)
);
CREATE TABLE hub_notifications (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    dedupe_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    href TEXT NOT NULL,
    created REAL NOT NULL,
    read REAL,
    email_state TEXT NOT NULL DEFAULT 'not_configured' CHECK(email_state IN ('not_configured','pending','sent','failed')),
    emailed REAL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE weekly_management_snapshots (
    id INTEGER PRIMARY KEY,
    week_start TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created REAL NOT NULL,
    actor TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    UNIQUE(week_start,revision)
);
"""
