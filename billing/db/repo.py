"""All SQL lives here. Every function takes an open Connection and does one job.

Month keys are 'YYYY-MM' strings plus the special 'INITIAL' row (opening balance and
starting meter readings). Because 'INITIAL' sorts *after* digits as text, every
"latest month" query excludes it explicitly and falls back to it.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from billing.config import FLAT_NUMBERS, INITIAL
from billing.domain import BillResult, CloseResult


def _rows(conn: Connection, sql: str, **params: Any) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def _row(conn: Connection, sql: str, **params: Any) -> dict | None:
    r = conn.execute(text(sql), params).first()
    return dict(r._mapping) if r else None


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def has_initial(conn: Connection) -> bool:
    return conn.execute(text("SELECT EXISTS (SELECT 1 FROM monthly_records)")).scalar_one()


def list_months(conn: Connection) -> list[dict]:
    """All real months, newest first, with headline numbers."""
    return _rows(conn, """
        SELECT month_year, status, opening_balance, closing_balance, total_water_bill,
               cost_per_unit, total_apartment_units, total_collection, total_expenditure,
               net_profit_loss, manjeera_bill, tanker_count, tanker_rate, closed_at
        FROM monthly_records WHERE month_year <> :initial
        ORDER BY month_year DESC
    """, initial=INITIAL)


def get_month(conn: Connection, month: str) -> dict | None:
    return _row(conn, "SELECT * FROM monthly_records WHERE month_year = :m", m=month)


def get_readings(conn: Connection, month: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM meter_readings WHERE month_year = :m ORDER BY flat_number", m=month)


def get_expenses(conn: Connection, month: str) -> list[dict]:
    return _rows(conn, "SELECT expense_name, amount FROM expenses WHERE month_year = :m ORDER BY position, id", m=month)


def month_before(conn: Connection, month: str) -> str | None:
    """The latest real month strictly before `month`, else INITIAL if it exists."""
    m = conn.execute(text(
        "SELECT MAX(month_year) FROM monthly_records WHERE month_year <> :i AND month_year < :m"
    ), {"i": INITIAL, "m": month}).scalar_one()
    if m:
        return m
    return INITIAL if get_month(conn, INITIAL) else None


def previous_readings(conn: Connection, month: str) -> dict[str, Decimal]:
    """Last month's closing meter readings: the 'previous' column for `month`.

    The original app read these from the *latest saved* month, so re-opening a saved
    month made previous == current and every flat showed 0 units. This reads from
    the month *before* the one being billed.
    """
    prior = month_before(conn, month)
    if not prior:
        return {f: Decimal(0) for f in FLAT_NUMBERS}
    got = {r["flat_number"]: Decimal(r["current_reading"]) for r in _rows(
        conn, "SELECT flat_number, current_reading FROM meter_readings WHERE month_year = :m", m=prior)}
    return {f: got.get(f, Decimal(0)) for f in FLAT_NUMBERS}


def previous_usage(conn: Connection, month: str) -> dict[str, Decimal]:
    """Units each flat used in the month before `month` (for live estimates)."""
    prior = month_before(conn, month)
    if not prior or prior == INITIAL:
        return {}
    return {r["flat_number"]: Decimal(r["units_used"]) for r in _rows(
        conn, "SELECT flat_number, units_used FROM meter_readings WHERE month_year = :m", m=prior)}


def opening_balance_for(conn: Connection, month: str) -> Decimal:
    """Closing balance of the month before `month` (INITIAL's balance for the first month)."""
    prior = month_before(conn, month)
    if not prior:
        return Decimal(0)
    rec = get_month(conn, prior)
    return Decimal(rec["closing_balance"]) if rec else Decimal(0)


def latest_expense_names(conn: Connection) -> list[str]:
    """Expense names from the most recent month that has any, to pre-fill a new month."""
    m = conn.execute(text("SELECT MAX(month_year) FROM expenses WHERE month_year <> :i"), {"i": INITIAL}).scalar_one()
    if not m:
        return []
    return [r["expense_name"] for r in get_expenses(conn, m)]


def get_draft(conn: Connection, month: str) -> dict | None:
    r = _row(conn, "SELECT payload, updated_at FROM drafts WHERE month_year = :m", m=month)
    if not r:
        return None
    payload = r["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload["_saved_at"] = r["updated_at"]
    return payload


# ---------------------------------------------------------------------------
# Writes (callers run these inside engine.begin(): all-or-nothing)
# ---------------------------------------------------------------------------
class LedgerError(ValueError):
    """A business rule stopped the write. The message is safe to show to the user."""


def _lock_ledger(conn: Connection) -> None:
    # Serialise ledger writes so two browser tabs can't close the same month twice.
    conn.execute(text("SELECT pg_advisory_xact_lock(74101404)"))


def save_initial(conn: Connection, readings: dict[str, Decimal], opening_balance: Decimal) -> None:
    _lock_ledger(conn)
    if conn.execute(text("SELECT EXISTS (SELECT 1 FROM monthly_records WHERE month_year <> :i)"), {"i": INITIAL}).scalar_one():
        raise LedgerError("Months have already been billed; the starting point can't be changed now.")
    conn.execute(text("""
        INSERT INTO monthly_records (month_year, status, opening_balance, closing_balance)
        VALUES (:i, 'closed', :b, :b)
        ON CONFLICT (month_year) DO UPDATE SET opening_balance = EXCLUDED.opening_balance,
            closing_balance = EXCLUDED.closing_balance, updated_at = now()
    """), {"i": INITIAL, "b": opening_balance})
    conn.execute(text("DELETE FROM meter_readings WHERE month_year = :i"), {"i": INITIAL})
    for flat in FLAT_NUMBERS:
        conn.execute(text("""
            INSERT INTO meter_readings (month_year, flat_number, previous_reading, current_reading,
                                        units_used, water_bill, total_bill)
            VALUES (:i, :f, 0, :r, 0, 0, 0)
        """), {"i": INITIAL, "f": flat, "r": readings.get(flat, Decimal(0))})


def check_can_bill(conn: Connection, month: str) -> None:
    """Raise LedgerError unless bills may be saved for `month`."""
    rec = get_month(conn, month)
    if rec and rec["status"] == "closed":
        raise LedgerError(f"{month} is closed. Reopen it first.")
    other_open = conn.execute(text(
        "SELECT month_year FROM monthly_records WHERE status = 'open' AND month_year <> :m AND month_year <> :i"
    ), {"m": month, "i": INITIAL}).scalar()
    if other_open:
        raise LedgerError(f"{other_open} is still open. Close it before starting another month.")
    later = conn.execute(text(
        "SELECT MAX(month_year) FROM monthly_records WHERE month_year > :m AND month_year <> :i"
    ), {"m": month, "i": INITIAL}).scalar()
    if later:
        raise LedgerError(f"{later} already exists. Months must be billed in order.")


def save_bills(conn: Connection, month: str, bills: BillResult) -> None:
    _lock_ledger(conn)
    check_can_bill(conn, month)
    opening = opening_balance_for(conn, month)
    conn.execute(text("""
        INSERT INTO monthly_records (month_year, status, opening_balance, closing_balance, manjeera_bill,
            tanker_count, tanker_rate, total_water_bill, cost_per_unit, total_apartment_units, total_collection)
        VALUES (:m, 'open', :ob, :ob, :mb, :tc, :tr, :tw, :cpu, :tu, :col)
        ON CONFLICT (month_year) DO UPDATE SET status = 'open', opening_balance = EXCLUDED.opening_balance,
            manjeera_bill = EXCLUDED.manjeera_bill, tanker_count = EXCLUDED.tanker_count,
            tanker_rate = EXCLUDED.tanker_rate, total_water_bill = EXCLUDED.total_water_bill,
            cost_per_unit = EXCLUDED.cost_per_unit, total_apartment_units = EXCLUDED.total_apartment_units,
            total_collection = EXCLUDED.total_collection, updated_at = now()
    """), {
        "m": month, "ob": opening, "mb": bills.manjeera_bill, "tc": bills.tanker_count, "tr": bills.tanker_rate,
        "tw": bills.total_water_bill, "cpu": int(bills.cost_per_unit), "tu": bills.total_units,
        "col": bills.total_collection,
    })
    conn.execute(text("DELETE FROM meter_readings WHERE month_year = :m"), {"m": month})
    conn.execute(text("""
        INSERT INTO meter_readings (month_year, flat_number, previous_reading, current_reading,
                                    units_used, water_bill, total_bill)
        VALUES (:m, :f, :p, :c, :u, :w, :t)
    """), [
        {"m": month, "f": ln.flat, "p": ln.previous, "c": ln.current, "u": ln.units,
         "w": ln.water_bill, "t": ln.total_bill}
        for ln in bills.lines
    ])


def save_expenses(conn: Connection, month: str, close: CloseResult) -> None:
    conn.execute(text("DELETE FROM expenses WHERE month_year = :m"), {"m": month})
    if close.expenses:
        conn.execute(text(
            "INSERT INTO expenses (month_year, expense_name, amount, position) VALUES (:m, :n, :a, :p)"
        ), [{"m": month, "n": e.name, "a": e.amount, "p": i} for i, e in enumerate(close.expenses)])


def close_month(conn: Connection, month: str, close: CloseResult) -> None:
    _lock_ledger(conn)
    rec = get_month(conn, month)
    if not rec:
        raise LedgerError(f"Save the bills for {month} before closing it.")
    if rec["status"] == "closed":
        raise LedgerError(f"{month} is already closed.")
    if opening_balance_for(conn, month) != close.opening_balance:
        # The opening balance is always the previous month's closing balance.
        raise LedgerError("The previous month's closing balance changed. Refresh and try again.")
    save_expenses(conn, month, close)
    conn.execute(text("""
        UPDATE monthly_records SET status = 'closed', opening_balance = :ob, total_expenditure = :te,
            net_profit_loss = :net, closing_balance = :cb, closed_at = now(), updated_at = now()
        WHERE month_year = :m
    """), {"m": month, "ob": close.opening_balance, "te": close.total_expenditure,
           "net": close.net, "cb": close.closing_balance})
    conn.execute(text("DELETE FROM drafts WHERE month_year = :m"), {"m": month})


def reopen_month(conn: Connection, month: str) -> None:
    """Only the most recent month can be reopened, so later balances never go stale."""
    _lock_ledger(conn)
    latest = conn.execute(text(
        "SELECT MAX(month_year) FROM monthly_records WHERE month_year <> :i"), {"i": INITIAL}).scalar()
    if month != latest:
        raise LedgerError(f"Only the latest month ({latest}) can be reopened; later months depend on {month}'s closing balance.")
    rec = get_month(conn, month)
    if not rec or rec["status"] != "closed":
        raise LedgerError(f"{month} is not closed.")
    conn.execute(text("UPDATE monthly_records SET status = 'open', closed_at = NULL, updated_at = now() WHERE month_year = :m"),
                 {"m": month})


def save_draft(conn: Connection, month: str, payload: dict) -> None:
    clean = {k: v for k, v in payload.items() if not k.startswith("_")}
    conn.execute(text("""
        INSERT INTO drafts (month_year, payload, updated_at) VALUES (:m, CAST(:p AS JSONB), now())
        ON CONFLICT (month_year) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
    """), {"m": month, "p": json.dumps(clean, default=str)})


def heartbeat(conn: Connection, source: str) -> None:
    conn.execute(text("""
        INSERT INTO app_heartbeat (id, source, pinged_at) VALUES (1, :s, now())
        ON CONFLICT (id) DO UPDATE SET source = EXCLUDED.source, pinged_at = now()
    """), {"s": source})
