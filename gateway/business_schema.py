"""Forward-only v20: business declarations and reversible archival; v19 stays immutable."""
from .hub_schema import DECLARATIONS
MIGRATION = """
ALTER TABLE hub_reports ADD COLUMN adoption_stage TEXT NOT NULL DEFAULT '';
ALTER TABLE hub_reports ADD COLUMN frequency_period TEXT NOT NULL DEFAULT 'month';
ALTER TABLE hub_reports ADD COLUMN manual_unit TEXT NOT NULL DEFAULT 'h';
ALTER TABLE hub_reports ADD COLUMN ai_unit TEXT NOT NULL DEFAULT 'h';
ALTER TABLE hub_reports ADD COLUMN archived_at REAL;
ALTER TABLE hub_reports ADD COLUMN archived_by TEXT;
ALTER TABLE hub_reports ADD COLUMN financial_basis TEXT NOT NULL DEFAULT 'staff-reported estimate';
ALTER TABLE hub_reports ADD COLUMN financial_actor TEXT NOT NULL DEFAULT '';
ALTER TABLE procurement_requests ADD COLUMN proposal_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE procurement_requests ADD COLUMN financial_basis TEXT NOT NULL DEFAULT 'staff-reported estimate';
CREATE TABLE procurement_versions (
 request_id INTEGER NOT NULL REFERENCES procurement_requests(id), version INTEGER NOT NULL,
 actor TEXT NOT NULL, ts REAL NOT NULL, reason TEXT NOT NULL, snapshot_json TEXT NOT NULL,
 PRIMARY KEY(request_id,version)
);
CREATE INDEX hub_business_scope ON hub_reports(kind,archived_at,created,department);
CREATE TABLE hub_attribution_changes (
 id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES hub_reports(id),
 actor TEXT NOT NULL, ts REAL NOT NULL, reason TEXT NOT NULL,
 previous_person_id INTEGER REFERENCES people(id), person_id INTEGER REFERENCES people(id),
 previous_tool_id TEXT REFERENCES tools(id), tool_id TEXT REFERENCES tools(id)
);
CREATE TABLE procurement_business (
 request_id INTEGER PRIMARY KEY REFERENCES procurement_requests(id),
 frequency_period TEXT NOT NULL DEFAULT 'month', manual_unit TEXT NOT NULL DEFAULT 'h',
 ai_unit TEXT NOT NULL DEFAULT 'h', adoption_stage TEXT NOT NULL DEFAULT '',
""" + DECLARATIONS + """
);
CREATE TABLE procurement_projects (
 request_id INTEGER NOT NULL REFERENCES procurement_requests(id), position INTEGER NOT NULL,
 name TEXT NOT NULL, link TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
 traditional TEXT NOT NULL DEFAULT '', ai_way TEXT NOT NULL DEFAULT '', benefit TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(request_id,position)
);
CREATE TABLE hub_tool_plans (
 id INTEGER PRIMARY KEY, tool_id TEXT NOT NULL REFERENCES tools(id), name TEXT NOT NULL,
 monthly_usd REAL NOT NULL CHECK(monthly_usd>=0), included REAL CHECK(included>=0),
 unit_rate_usd REAL CHECK(unit_rate_usd>=0), usage_unit TEXT NOT NULL DEFAULT '',
 flat_rate INTEGER NOT NULL DEFAULT 0 CHECK(flat_rate IN (0,1)), pricing_url TEXT NOT NULL,
 checked REAL NOT NULL, actor TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
 UNIQUE(tool_id,name)
);
CREATE TABLE procurement_drafts (
 person_id INTEGER PRIMARY KEY REFERENCES people(id), version INTEGER NOT NULL DEFAULT 0,
 updated REAL NOT NULL, submitted_request_id INTEGER REFERENCES procurement_requests(id),
 tool_id TEXT REFERENCES tools(id), tool_name TEXT NOT NULL DEFAULT '',
 official_url TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
 purchase_type TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
 business_impact TEXT NOT NULL DEFAULT '', requested_plan TEXT NOT NULL DEFAULT '',
 estimated_monthly_cost REAL CHECK(estimated_monthly_cost>=0),
 estimated_one_time_cost REAL CHECK(estimated_one_time_cost>=0), currency TEXT NOT NULL DEFAULT 'USD'
);
CREATE TABLE procurement_draft_business (
 person_id INTEGER PRIMARY KEY REFERENCES procurement_drafts(person_id),
 frequency_period TEXT NOT NULL DEFAULT 'month', manual_unit TEXT NOT NULL DEFAULT 'h',
 ai_unit TEXT NOT NULL DEFAULT 'h', adoption_stage TEXT NOT NULL DEFAULT '',
""" + DECLARATIONS + """
);
CREATE TABLE procurement_draft_projects (
 person_id INTEGER NOT NULL REFERENCES procurement_drafts(person_id), position INTEGER NOT NULL,
 name TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
 traditional TEXT NOT NULL DEFAULT '', ai_way TEXT NOT NULL DEFAULT '', benefit TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(person_id,position)
);
CREATE TABLE hub_department_grants (
 person_id INTEGER NOT NULL REFERENCES people(id), department TEXT NOT NULL,
 actor TEXT NOT NULL, granted REAL NOT NULL, revoked REAL,
 PRIMARY KEY(person_id,department)
);
CREATE TABLE hub_department_requests (
 id INTEGER PRIMARY KEY, person_id INTEGER REFERENCES people(id),
 submitter_name TEXT NOT NULL, submitter_email TEXT NOT NULL,
 reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'submitted'
 CHECK(state IN ('submitted','reviewed','approved','rejected')),
 created REAL NOT NULL, updated REAL NOT NULL, reviewer_id INTEGER REFERENCES admins(id),
 admin_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE hub_department_request_scopes (
 request_id INTEGER NOT NULL REFERENCES hub_department_requests(id),department TEXT NOT NULL,
 PRIMARY KEY(request_id,department)
);
CREATE TABLE hub_department_decisions (
 id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES hub_department_requests(id),
 actor TEXT NOT NULL, ts REAL NOT NULL, state TEXT NOT NULL, note TEXT NOT NULL
);
"""
