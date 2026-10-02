"""
calculations.py
================
Pure calculation/business-logic layer for apartment water billing.

Rounding rules:
  • Cost per unit  → rounded UP to next integer  (math.ceil)
  • Individual flat total bill → rounded to nearest Rs.5
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Configuration — edit these to change defaults
# ---------------------------------------------------------------------------
MAINTENANCE_AMOUNT: float = 1500.0
FLAT_NUMBERS: list[str] = [
    "101", "102", "103",
    "201", "202", "203",
    "301", "302", "303",
    "401", "402", "403",
]


# ---------------------------------------------------------------------------
# Rounding helpers
# ---------------------------------------------------------------------------

def round_up_to_int(value: float) -> int:
    """Round a value UP to the nearest integer (ceiling).

    >>> round_up_to_int(96.755)
    97
    >>> round_up_to_int(100.0)
    100
    """
    return math.ceil(value)


def round_to_nearest_5(value: float) -> float:
    """Round a value to the nearest Rs.5.

    >>> round_to_nearest_5(3222)
    3220.0
    >>> round_to_nearest_5(3228)
    3230.0
    >>> round_to_nearest_5(3213)
    3215.0
    """
    return round(value / 5) * 5.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FlatBill:
    """Computed billing data for a single flat."""
    flat_number: str
    previous_reading: float
    current_reading: float
    units_used: float = 0.0
    water_bill: float = 0.0
    total_bill: float = 0.0  # rounded to nearest 5

    def compute(self, cost_per_unit: int) -> None:
        """Calculate units, water bill, and rounded total bill."""
        self.units_used = self.current_reading - self.previous_reading
        self.water_bill = self.units_used * cost_per_unit
        raw_total = MAINTENANCE_AMOUNT + self.water_bill
        self.total_bill = round_to_nearest_5(raw_total)


@dataclass
class BillCalculation:
    """Calculates water bills for all flats (Step 1 — no expenses)."""
    manjeera_bill: float = 0.0
    tanker_count: int = 0
    tanker_rate: float = 0.0

    flat_bills: list[FlatBill] = field(default_factory=list)

    # Computed
    total_water_bill: float = 0.0
    total_apartment_units: float = 0.0
    cost_per_unit: int = 0
    total_collection: float = 0.0

    def set_readings(self, readings: dict[str, tuple[float, float]]) -> None:
        """Populate flat_bills from {flat_number: (previous, current)}."""
        self.flat_bills = [
            FlatBill(
                flat_number=flat,
                previous_reading=readings[flat][0],
                current_reading=readings[flat][1],
            )
            for flat in FLAT_NUMBERS
            if flat in readings
        ]

    def compute(self) -> None:
        """Run bill calculations."""
        # Total water bill
        self.total_water_bill = self.manjeera_bill + (self.tanker_count * self.tanker_rate)

        # Total apartment units
        self.total_apartment_units = sum(
            fb.current_reading - fb.previous_reading for fb in self.flat_bills
        )

        # Cost per unit (rounded UP)
        if self.total_apartment_units > 0:
            self.cost_per_unit = round_up_to_int(
                self.total_water_bill / self.total_apartment_units
            )
        else:
            self.cost_per_unit = 0

        # Per-flat bills
        for fb in self.flat_bills:
            fb.compute(self.cost_per_unit)

        # Total collection
        self.total_collection = sum(fb.total_bill for fb in self.flat_bills)

    def to_save_dict(self) -> dict:
        """Return dict for database.save_bill_data()."""
        return {
            "manjeera_bill": self.manjeera_bill,
            "tanker_count": self.tanker_count,
            "tanker_rate": self.tanker_rate,
            "total_water_bill": self.total_water_bill,
            "cost_per_unit": self.cost_per_unit,
            "total_apartment_units": int(self.total_apartment_units),
            "total_collection": self.total_collection,
            "meter_readings": [
                {
                    "flat_number": fb.flat_number,
                    "previous_reading": fb.previous_reading,
                    "current_reading": fb.current_reading,
                    "units_used": fb.units_used,
                    "water_bill": fb.water_bill,
                    "total_bill": fb.total_bill,
                }
                for fb in self.flat_bills
            ],
        }


@dataclass
class ExpenseCalculation:
    """Calculates the financial summary when closing a month (Step 2)."""
    opening_balance: float = 0.0
    expenses: list[dict] = field(default_factory=list)
    # expenses: [{"expense_name": str, "amount": float}, ...]

    # From saved bill data
    total_water_bill: float = 0.0
    total_collection: float = 0.0

    # Computed
    total_variable_expenses: float = 0.0
    total_expenditure: float = 0.0
    net_profit_loss: float = 0.0
    closing_balance: float = 0.0

    def compute(self) -> None:
        """Run expense/closing calculations."""
        self.total_variable_expenses = sum(e["amount"] for e in self.expenses)
        self.total_expenditure = self.total_variable_expenses + self.total_water_bill
        self.net_profit_loss = self.total_collection - self.total_expenditure
        self.closing_balance = self.opening_balance + self.net_profit_loss

    def to_save_dict(self) -> dict:
        """Return dict for database.close_month()."""
        return {
            "opening_balance": self.opening_balance,
            "expenses": [
                {"expense_name": e["expense_name"], "amount": e["amount"]}
                for e in self.expenses
            ],
            "total_expenditure": self.total_expenditure,
            "net_profit_loss": self.net_profit_loss,
            "closing_balance": self.closing_balance,
        }
