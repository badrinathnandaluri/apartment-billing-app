"""Use-cases the UI calls. Each method is one retried unit of work."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, TypeVar

from sqlalchemy.engine import Connection, Engine

from billing.config import FLAT_NUMBERS, INITIAL, MAINTENANCE_AMOUNT
from billing.db import engine as dbe
from billing.db import repo, schema
from billing.domain import (
    D, BillResult, CloseResult, ExpenseLine, FlatLine,
)

T = TypeVar("T")


@dataclass(frozen=True)
class MonthContext:
    """Everything the screens need about the month being worked on."""
    month: str
    status: str | None                 # None = not saved yet, "open", "closed"
    previous: dict[str, Decimal]       # previous meter readings (locked)
    previous_usage: dict[str, Decimal]
    opening_balance: Decimal
    record: dict | None
    saved_readings: dict[str, Decimal]
    saved_expenses: list[dict]
    suggested_expense_names: list[str]
    draft: dict | None


@dataclass(frozen=True)
class MonthReport:
    """A saved month, rebuilt into domain objects for display and PDFs."""
    month: str
    status: str
    bills: BillResult
    close: CloseResult | None


class Ledger:
    def __init__(self, engine: Engine, on_retry: dbe.OnRetry | None = None):
        self.engine = engine
        self.on_retry = on_retry

    def _run(self, work: Callable[[Connection], T], write: bool = False) -> T:
        return dbe.run(self.engine, work, write=write, on_retry=self.on_retry)

    # -- startup -------------------------------------------------------------
    def connect_and_migrate(self) -> list[int]:
        return self._run(schema.migrate, write=True)

    def ping(self, source: str = "app") -> None:
        self._run(lambda c: repo.heartbeat(c, source), write=True)

    def has_initial(self) -> bool:
        return self._run(repo.has_initial)

    def save_initial(self, readings: dict[str, Decimal], opening: Decimal) -> None:
        self._run(lambda c: repo.save_initial(c, readings, opening), write=True)

    # -- reads ---------------------------------------------------------------
    def months(self) -> list[dict]:
        return self._run(repo.list_months)

    def context(self, month: str) -> MonthContext:
        def work(c: Connection) -> MonthContext:
            rec = repo.get_month(c, month)
            readings = repo.get_readings(c, month) if rec else []
            return MonthContext(
                month=month,
                status=rec["status"] if rec else None,
                previous=repo.previous_readings(c, month),
                previous_usage=repo.previous_usage(c, month),
                opening_balance=repo.opening_balance_for(c, month),
                record=rec,
                saved_readings={r["flat_number"]: D(r["current_reading"]) for r in readings},
                saved_expenses=repo.get_expenses(c, month) if rec else [],
                suggested_expense_names=repo.latest_expense_names(c),
                draft=repo.get_draft(c, month),
            )
        return self._run(work)

    def report(self, month: str) -> MonthReport | None:
        def work(c: Connection):
            rec = repo.get_month(c, month)
            if not rec or month == INITIAL:
                return None
            return rec, repo.get_readings(c, month), repo.get_expenses(c, month)
        got = self._run(work)
        if not got:
            return None
        return build_report(*got)

    # -- writes --------------------------------------------------------------
    def save_draft(self, month: str, payload: dict) -> None:
        self._run(lambda c: repo.save_draft(c, month, payload), write=True)

    def save_bills(self, month: str, bills: BillResult) -> None:
        self._run(lambda c: repo.save_bills(c, month, bills), write=True)

    def close_month(self, month: str, close: CloseResult) -> None:
        self._run(lambda c: repo.close_month(c, month, close), write=True)

    def reopen_month(self, month: str) -> None:
        self._run(lambda c: repo.reopen_month(c, month), write=True)


def build_report(rec: dict, readings: list[dict], expenses: list[dict]) -> MonthReport:
    by_flat = {r["flat_number"]: r for r in readings}
    lines = tuple(
        FlatLine(
            flat=f,
            previous=D(by_flat[f]["previous_reading"]),
            current=D(by_flat[f]["current_reading"]),
            units=D(by_flat[f]["units_used"]),
            water_bill=D(by_flat[f]["water_bill"]),
            total_bill=D(by_flat[f]["total_bill"]),
        )
        for f in FLAT_NUMBERS if f in by_flat
    )
    bills = BillResult(
        manjeera_bill=D(rec["manjeera_bill"]),
        tanker_count=int(rec["tanker_count"]),
        tanker_rate=D(rec["tanker_rate"]),
        total_water_bill=D(rec["total_water_bill"]),
        total_units=D(rec["total_apartment_units"]),
        cost_per_unit=D(rec["cost_per_unit"]),
        lines=lines,
        total_collection=D(rec["total_collection"]),
        maintenance=MAINTENANCE_AMOUNT,
    )
    close = None
    if rec["status"] == "closed":
        # Use the stored totals, so history shows exactly what was closed.
        lines_e = tuple(ExpenseLine(e["expense_name"], D(e["amount"])) for e in expenses)
        close = CloseResult(
            opening_balance=D(rec["opening_balance"]),
            expenses=lines_e,
            total_variable_expenses=sum((e.amount for e in lines_e), D(0)),
            total_water_bill=D(rec["total_water_bill"]),
            total_expenditure=D(rec["total_expenditure"]),
            total_collection=D(rec["total_collection"]),
            net=D(rec["net_profit_loss"]),
            closing_balance=D(rec["closing_balance"]),
        )
    return MonthReport(rec["month_year"], rec["status"], bills, close)
