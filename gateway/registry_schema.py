"""Forward-only v24: the manual provider-account registry (Amendment 01, task 1).

A person tells Swangz which AI subscription they hold and may add what they know about it. Nothing here is
fetched from a provider and nothing here is confirmed: every row is a declaration by the holder. Nothing in this
migration touches an earlier table, and nothing reads these tables to decide access, spend or licences.

- `provider_accounts` is retained forever: a row is only ever ended (active -> ended), never edited or deleted.
- `provider_account_values` is append-only: a correction is a new row, and the latest row for a kind is current.
- Foreign keys to people and tools are RESTRICT, so a tool or person with a registry row cannot be deleted away.
- INSERT OR REPLACE and REPLACE INTO delete the row they replace without firing DELETE triggers (recursive_triggers is
  off, and stays off). So BEFORE INSERT guards abort any insert whose id already exists, and an account insert that would
  take the place of an active (holder, tool, route) row under a new id. `CHECK (id > 0)` keeps the guards exact: a
  BEFORE INSERT trigger sees an auto-assigned id as -1, which therefore can never be a stored id.

A tuple migration runs each element as one statement (a trigger body holds semicolons, so it cannot be split on them).
"""

MIGRATION = (
    """CREATE TABLE provider_accounts (
 id INTEGER PRIMARY KEY CHECK (id > 0),
 account_holder_kind TEXT NOT NULL DEFAULT 'person' CHECK (account_holder_kind IN ('person','company')),
 holder_person_id INTEGER REFERENCES people(id) ON DELETE RESTRICT,
 tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE RESTRICT,
 route TEXT NOT NULL CHECK (route IN ('individual','seat','api','enterprise')),
 payer TEXT NOT NULL CHECK (payer IN ('person','company','none')),
 assertion TEXT NOT NULL DEFAULT 'holder_declared' CHECK (assertion IN ('holder_declared','admin_declared')),
 label TEXT NOT NULL DEFAULT '' CHECK (length(label) <= 80),
 status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')),
 created REAL NOT NULL,
 created_by INTEGER REFERENCES people(id) ON DELETE RESTRICT,
 ended REAL,
 CHECK ((account_holder_kind = 'person') = (holder_person_id IS NOT NULL)),
 CHECK (route NOT IN ('individual','seat') OR account_holder_kind = 'person'),
 CHECK (route != 'individual' OR payer IN ('person','none')),
 CHECK (route != 'seat' OR payer = 'company'),
 CHECK ((status = 'active' AND ended IS NULL) OR (status = 'ended' AND ended IS NOT NULL))
)""",
    "CREATE INDEX provider_accounts_holder ON provider_accounts(holder_person_id, status)",
    "CREATE INDEX provider_accounts_tool ON provider_accounts(tool_id)",
    "CREATE UNIQUE INDEX provider_accounts_one_active ON provider_accounts(holder_person_id, tool_id, route) WHERE status = 'active'",
    """CREATE TABLE provider_account_values (
 id INTEGER PRIMARY KEY CHECK (id > 0),
 account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE RESTRICT,
 kind TEXT NOT NULL CHECK (kind IN ('plan','quota_limit','quota_used','period_end','credit_balance','monthly_price')),
 value TEXT NOT NULL CHECK (length(value) BETWEEN 1 AND 60),
 currency TEXT NOT NULL DEFAULT '' CHECK (length(currency) IN (0, 3)),
 as_of TEXT NOT NULL CHECK (length(as_of) = 10),
 recorded REAL NOT NULL,
 recorded_by INTEGER NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
 CHECK ((kind IN ('credit_balance','monthly_price')) = (currency != ''))
)""",
    "CREATE INDEX provider_account_values_account ON provider_account_values(account_id, kind, id)",
    """CREATE TRIGGER provider_account_values_no_update BEFORE UPDATE ON provider_account_values
BEGIN SELECT RAISE(ABORT, 'provider account values are never changed'); END""",
    """CREATE TRIGGER provider_account_values_no_delete BEFORE DELETE ON provider_account_values
BEGIN SELECT RAISE(ABORT, 'provider account values are never deleted'); END""",
    """CREATE TRIGGER provider_account_values_no_replace BEFORE INSERT ON provider_account_values
WHEN EXISTS (SELECT 1 FROM provider_account_values WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'provider account values are never replaced'); END""",
    """CREATE TRIGGER provider_account_values_not_after_end BEFORE INSERT ON provider_account_values
WHEN (SELECT status FROM provider_accounts WHERE id = NEW.account_id) != 'active'
BEGIN SELECT RAISE(ABORT, 'an ended provider account takes no more values'); END""",
    """CREATE TRIGGER provider_accounts_no_delete BEFORE DELETE ON provider_accounts
BEGIN SELECT RAISE(ABORT, 'provider accounts are retained, never deleted'); END""",
    """CREATE TRIGGER provider_accounts_no_replace BEFORE INSERT ON provider_accounts
WHEN EXISTS (SELECT 1 FROM provider_accounts WHERE id = NEW.id)
 OR (NEW.status = 'active' AND EXISTS (SELECT 1 FROM provider_accounts WHERE status = 'active'
  AND holder_person_id = NEW.holder_person_id AND tool_id = NEW.tool_id AND route = NEW.route))
BEGIN SELECT RAISE(ABORT, 'provider accounts are never replaced'); END""",
    """CREATE TRIGGER provider_accounts_only_end BEFORE UPDATE ON provider_accounts
WHEN NOT (OLD.status = 'active' AND NEW.status = 'ended' AND NEW.ended IS NOT NULL
 AND NEW.id = OLD.id AND NEW.account_holder_kind = OLD.account_holder_kind AND NEW.holder_person_id IS OLD.holder_person_id
 AND NEW.tool_id = OLD.tool_id AND NEW.route = OLD.route AND NEW.payer = OLD.payer AND NEW.assertion = OLD.assertion
 AND NEW.label = OLD.label AND NEW.created = OLD.created AND NEW.created_by IS OLD.created_by)
BEGIN SELECT RAISE(ABORT, 'a provider account can only be ended'); END""",
)
