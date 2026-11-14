"""Database tests. Run against a throwaway Postgres:

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres pytest

Skipped when TEST_DATABASE_URL is not set. Never point it at the real ledger:
every test drops and recreates the tables.
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from billing.config import FLAT_NUMBERS
from billing.db import engine as dbe
from billing.db.repo import LedgerError
from billing.domain import clean_expenses, compute_bills, compute_close
from billing.services import Ledger

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

TABLES = ("monthly_records", "expenses", "meter_readings", "drafts", "app_heartbeat", "schema_version",
          "backup_v1_monthly_records", "backup_v1_expenses", "backup_v1_meter_readings")


@pytest.fixture
def engine():
    eng = dbe.create(URL)
    with eng.begin() as c:
        for t in TABLES:
            c.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
    yield eng
    eng.dispose()


@pytest.fixture
def ledger(engine):
    lg = Ledger(engine)
    lg.connect_and_migrate()
    return lg


def start(ledger, base=1000):
    ledger.save_initial({f: Decimal(base) for f in FLAT_NUMBERS}, Decimal("-250"))


def bills_for(ledger, month, units=10, water=11_530):
    ctx = ledger.context(month)
    rd = {f: (ctx.previous[f], ctx.previous[f] + units) for f in FLAT_NUMBERS}
    return compute_bills(water, 0, 0, rd)


def close(ledger, month, bills, expenses=({"name": "Watchman", "amount": 8000},)):
    ctx = ledger.context(month)
    c = compute_close(ctx.opening_balance, clean_expenses(expenses), bills.total_water_bill, bills.total_collection)
    ledger.close_month(month, c)
    return c


def test_migrates_an_original_v1_database_in_place(engine):
    from billing.db.schema import V1
    with engine.begin() as c:
        for s in V1:
            c.execute(text(s))
        c.execute(text("INSERT INTO monthly_records (month_year, status, closing_balance) VALUES ('INITIAL','closed', 1234.5)"))
        c.execute(text("INSERT INTO meter_readings (month_year, flat_number, current_reading) VALUES ('INITIAL','101', 987.3)"))
    applied = Ledger(engine).connect_and_migrate()
    assert applied == [2]
    with engine.connect() as c:
        assert c.execute(text("SELECT closing_balance FROM monthly_records")).scalar_one() == Decimal("1234.50")
        assert c.execute(text("SELECT current_reading FROM meter_readings")).scalar_one() == Decimal("987.30")
        assert c.execute(text("SELECT COUNT(*) FROM backup_v1_monthly_records")).scalar_one() == 1
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE relname='expenses'")).scalar_one()
    assert Ledger(engine).connect_and_migrate() == []   # idempotent


def test_full_month_cycle_and_carry_forward(ledger):
    start(ledger)
    b1 = bills_for(ledger, "2026-09")
    ledger.save_bills("2026-09", b1)
    c1 = close(ledger, "2026-09", b1)
    assert c1.opening_balance == Decimal("-250")          # negative balances carry over

    ctx = ledger.context("2026-10")
    assert ctx.opening_balance == c1.closing_balance
    assert ctx.previous["101"] == 1010                     # September's current reading

    report = ledger.report("2026-09")
    assert report.status == "closed"
    assert report.close.closing_balance == c1.closing_balance
    assert report.bills.lines[0].total_bill == b1.lines[0].total_bill


def test_resaving_an_open_month_keeps_correct_previous_readings(ledger):
    """The original app's bug: re-editing a saved month showed 0 units for every flat."""
    start(ledger)
    ledger.save_bills("2026-09", bills_for(ledger, "2026-09", units=10))
    ctx = ledger.context("2026-09")
    assert ctx.previous["101"] == 1000 and ctx.saved_readings["101"] == 1010
    ledger.save_bills("2026-09", bills_for(ledger, "2026-09", units=12))
    assert ledger.context("2026-09").saved_readings["101"] == 1012


def test_ledger_rules(ledger):
    start(ledger)
    b = bills_for(ledger, "2026-09")
    ledger.save_bills("2026-09", b)
    with pytest.raises(LedgerError, match="still open"):
        ledger.save_bills("2026-10", bills_for(ledger, "2026-10"))
    close(ledger, "2026-09", b)
    with pytest.raises(LedgerError, match="closed"):
        ledger.save_bills("2026-09", b)
    with pytest.raises(LedgerError, match="in order"):
        ledger.save_bills("2026-08", bills_for(ledger, "2026-08"))
    ledger.save_bills("2026-10", bills_for(ledger, "2026-10"))
    close(ledger, "2026-10", bills_for(ledger, "2026-10"))
    with pytest.raises(LedgerError, match="Only the latest"):
        ledger.reopen_month("2026-09")
    ledger.reopen_month("2026-10")
    assert ledger.context("2026-10").status == "open"


def test_drafts_round_trip_and_clear_on_close(ledger):
    start(ledger)
    ledger.save_draft("2026-09", {"manjeera": "10000", "readings": {"101": "1010"}, "_ui": "x"})
    d = ledger.context("2026-09").draft
    assert d["manjeera"] == "10000" and "_ui" not in d and d["_saved_at"]
    b = bills_for(ledger, "2026-09")
    ledger.save_bills("2026-09", b)
    close(ledger, "2026-09", b)
    assert ledger.context("2026-09").draft is None


def test_retry_reports_attempts_then_gives_a_diagnosis():
    seen = []
    eng = dbe.create("postgresql://u:p@no-such-host.invalid:5432/db")
    with pytest.raises(dbe.DatabaseUnavailable) as err:
        dbe.run(eng, lambda c: c.execute(text("SELECT 1")), max_attempts=3, max_seconds=30,
                on_retry=lambda a, m, w, d: seen.append((a, d.kind)))
    assert [a for a, _ in seen] == [1, 2]
    assert err.value.diagnosis.kind == "paused"
    assert isinstance(err.value.cause, OperationalError)


def test_retry_recovers_when_the_database_wakes_up(ledger):
    calls = {"n": 0}

    def flaky(conn):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))
        return conn.execute(text("SELECT 42")).scalar_one()

    assert dbe.run(ledger.engine, flaky, max_attempts=5) == 42
    assert calls["n"] == 3


def test_sql_errors_are_not_retried(ledger):
    calls = {"n": 0}

    def bad(conn):
        calls["n"] += 1
        conn.execute(text("SELECT * FROM no_such_table"))

    with pytest.raises(Exception) as err:
        dbe.run(ledger.engine, bad)
    assert calls["n"] == 1 and not isinstance(err.value, dbe.DatabaseUnavailable)
