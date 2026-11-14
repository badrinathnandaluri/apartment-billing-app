"""Versioned, idempotent schema migrations.

Version 1 is the schema the original app created, so an existing Supabase database
is recognised as-is. Version 2 upgrades it in place:

* snapshots the three original tables into backup_v1_* first (inside the same DB)
* money and readings: REAL (4-byte float) -> NUMERIC(12,2) exact decimals
* adds drafts (auto-saved work in progress), app_heartbeat (keep-alive), audit columns
* enables row-level security, so Supabase's public REST API can't read the ledger.
  The app connects as the table owner, which RLS doesn't restrict.

Migrations run under a Postgres advisory lock, so two app instances starting at
once can't run them twice.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

LOCK_ID = 74_101_403  # arbitrary, app-specific

V1 = [
    """
    CREATE TABLE IF NOT EXISTS monthly_records (
        id SERIAL PRIMARY KEY,
        month_year TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        opening_balance REAL NOT NULL DEFAULT 0,
        closing_balance REAL NOT NULL DEFAULT 0,
        manjeera_bill REAL NOT NULL DEFAULT 0,
        tanker_count INTEGER NOT NULL DEFAULT 0,
        tanker_rate REAL NOT NULL DEFAULT 0,
        total_water_bill REAL NOT NULL DEFAULT 0,
        cost_per_unit INTEGER NOT NULL DEFAULT 0,
        total_apartment_units INTEGER NOT NULL DEFAULT 0,
        total_collection REAL NOT NULL DEFAULT 0,
        total_expenditure REAL NOT NULL DEFAULT 0,
        net_profit_loss REAL NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id SERIAL PRIMARY KEY,
        month_year TEXT NOT NULL,
        expense_name TEXT NOT NULL,
        amount REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meter_readings (
        id SERIAL PRIMARY KEY,
        month_year TEXT NOT NULL,
        flat_number TEXT NOT NULL,
        previous_reading REAL NOT NULL DEFAULT 0,
        current_reading REAL NOT NULL DEFAULT 0,
        units_used REAL NOT NULL DEFAULT 0,
        water_bill REAL NOT NULL DEFAULT 0,
        total_bill REAL NOT NULL DEFAULT 0,
        UNIQUE(month_year, flat_number)
    )
    """,
]

_MONEY = {
    "monthly_records": [
        "opening_balance", "closing_balance", "manjeera_bill", "tanker_rate", "total_water_bill",
        "total_apartment_units", "total_collection", "total_expenditure", "net_profit_loss",
    ],
    "expenses": ["amount"],
    "meter_readings": ["previous_reading", "current_reading", "units_used", "water_bill", "total_bill"],
}

V2 = [
    # 1. snapshot before touching anything (no-op if a snapshot already exists)
    "CREATE TABLE IF NOT EXISTS backup_v1_monthly_records AS TABLE monthly_records",
    "CREATE TABLE IF NOT EXISTS backup_v1_expenses AS TABLE expenses",
    "CREATE TABLE IF NOT EXISTS backup_v1_meter_readings AS TABLE meter_readings",
    # 2. exact decimals
    *[
        f"ALTER TABLE {table} ALTER COLUMN {col} TYPE NUMERIC(12,2) USING ROUND({col}::numeric, 2)"
        for table, cols in _MONEY.items()
        for col in cols
    ],
    # 3. integrity + audit
    "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ",
    "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
    """
    DO $$ BEGIN
        ALTER TABLE monthly_records ADD CONSTRAINT monthly_records_status_chk
            CHECK (status IN ('open', 'closed'));
    EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """,
    "CREATE INDEX IF NOT EXISTS expenses_month_idx ON expenses (month_year)",
    # 4. new tables
    """
    CREATE TABLE IF NOT EXISTS drafts (
        month_year TEXT PRIMARY KEY,
        payload JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_heartbeat (
        id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
        source TEXT NOT NULL,
        pinged_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # 5. lock the tables away from Supabase's anon/authenticated REST roles
    *[
        f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY"
        for t in (
            "monthly_records", "expenses", "meter_readings", "drafts", "app_heartbeat",
            "backup_v1_monthly_records", "backup_v1_expenses", "backup_v1_meter_readings",
        )
    ],
]

MIGRATIONS: dict[int, list[str]] = {1: V1, 2: V2}
LATEST = max(MIGRATIONS)


def current_version(conn: Connection) -> int:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    ))
    v = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_version")).scalar_one()
    if v == 0:
        # A database created by the original app has the tables but no version row.
        exists = conn.execute(text("SELECT to_regclass('public.monthly_records') IS NOT NULL")).scalar_one()
        if exists:
            conn.execute(text("INSERT INTO schema_version (version) VALUES (1)"))
            return 1
    return int(v)


def migrate(conn: Connection) -> list[int]:
    """Bring the schema to LATEST. Returns the versions applied (empty if none)."""
    conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": LOCK_ID})
    start = current_version(conn)
    applied = []
    for version in range(start + 1, LATEST + 1):
        for stmt in MIGRATIONS[version]:
            conn.execute(text(stmt))
        conn.execute(text("INSERT INTO schema_version (version) VALUES (:v)"), {"v": version})
        applied.append(version)
    if applied:
        conn.execute(text("ALTER TABLE schema_version ENABLE ROW LEVEL SECURITY"))
    return applied
