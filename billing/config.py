"""Building-level settings. Edit here to change the rules for every future month.

Closed months keep the numbers they were closed with, so changing a value here
never rewrites history.
"""

from __future__ import annotations

from decimal import Decimal

BUILDING_NAME = "Gnapika Residency"

FLAT_NUMBERS: tuple[str, ...] = (
    "101", "102", "103",
    "201", "202", "203",
    "301", "302", "303",
    "401", "402", "403",
)

# Fixed maintenance charged to every flat, every month.
MAINTENANCE_AMOUNT = Decimal("1500")

# A flat's total bill is rounded UP to the next multiple of this (cash handling).
BILL_ROUNDING_STEP = 5

# Expense rows offered when there is no earlier month to copy names from.
DEFAULT_EXPENSES: tuple[str, ...] = (
    "Watchman Salary",
    "Garbage Collection",
    "Society Security",
    "Electricity Bill",
    "Lift Service",
)

# The row that holds the opening balance and starting meter readings.
INITIAL = "INITIAL"

# Log the user out after this many minutes without activity (drafts are kept).
SESSION_IDLE_MINUTES = 120
