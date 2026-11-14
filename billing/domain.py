"""Billing math. Pure functions over Decimal: no database, no Streamlit.

Rules
-----
units used         = current reading - previous reading
total water cost   = Manjeera bill + tankers x tanker rate
cost per unit      = total water cost / total units, rounded UP to a whole rupee
flat water bill    = units used x cost per unit
flat total bill    = water bill + maintenance, rounded UP to the next multiple of 5
total expenditure  = variable expenses + total water cost
net                = total collection - total expenditure
closing balance    = opening balance + net
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Iterable, Mapping

from billing.config import BILL_ROUNDING_STEP, FLAT_NUMBERS, MAINTENANCE_AMOUNT

ZERO = Decimal("0")


def D(value: object) -> Decimal:
    """Convert anything numeric (including None and floats from the DB) to Decimal."""
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        # str() first so 0.1 (float) becomes Decimal("0.1"), not 0.1000000000000000055...
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Not a number: {value!r}") from exc


def ceil_to_int(value: Decimal) -> Decimal:
    """96.1 -> 97, 100 -> 100."""
    return D(value).to_integral_value(rounding=ROUND_CEILING)


def round_up_to_step(value: Decimal, step: int = BILL_ROUNDING_STEP) -> Decimal:
    """162 -> 165, 163 -> 165, 165 -> 165, 166 -> 170."""
    step_d = Decimal(step)
    return (D(value) / step_d).to_integral_value(rounding=ROUND_CEILING) * step_d


# ---------------------------------------------------------------------------
# Water bills
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FlatLine:
    flat: str
    previous: Decimal
    current: Decimal
    units: Decimal
    water_bill: Decimal
    total_bill: Decimal


@dataclass(frozen=True)
class BillResult:
    manjeera_bill: Decimal
    tanker_count: int
    tanker_rate: Decimal
    total_water_bill: Decimal
    total_units: Decimal
    cost_per_unit: Decimal
    lines: tuple[FlatLine, ...]
    total_collection: Decimal
    maintenance: Decimal = MAINTENANCE_AMOUNT

    @property
    def tanker_total(self) -> Decimal:
        return self.tanker_rate * self.tanker_count


def water_total(manjeera_bill: object, tanker_count: object, tanker_rate: object) -> Decimal:
    return D(manjeera_bill) + D(tanker_count) * D(tanker_rate)


def bill_issues(
    manjeera_bill: object,
    tanker_count: object,
    tanker_rate: object,
    readings: Mapping[str, tuple[object, object | None]],
) -> list[str]:
    """Everything that stops a month's bills from being calculated. Empty list = OK."""
    issues: list[str] = []
    if D(manjeera_bill) < 0 or D(tanker_rate) < 0 or D(tanker_count) < 0:
        issues.append("Water amounts can't be negative.")
    if water_total(manjeera_bill, tanker_count, tanker_rate) <= 0:
        issues.append("Enter the Manjeera bill or tanker details. Total water cost is ₹0.")
    missing = [f for f in FLAT_NUMBERS if readings.get(f, (0, None))[1] is None]
    if missing:
        issues.append(f"Current reading missing for flat {', '.join(missing)}.")
    for flat in FLAT_NUMBERS:
        prev, curr = readings.get(flat, (0, None))
        if curr is not None and D(curr) < D(prev):
            issues.append(f"Flat {flat}: current reading {fmt_units(D(curr))} is below previous {fmt_units(D(prev))}.")
    if not missing:
        total_units = sum((D(c) - D(p) for p, c in (readings[f] for f in FLAT_NUMBERS)), ZERO)
        if total_units <= 0:
            issues.append("Total units used is 0. Check the meter readings.")
    return issues


def compute_bills(
    manjeera_bill: object,
    tanker_count: object,
    tanker_rate: object,
    readings: Mapping[str, tuple[object, object]],
    maintenance: Decimal = MAINTENANCE_AMOUNT,
) -> BillResult:
    """readings = {flat: (previous, current)}. Call bill_issues() first; this raises on bad input."""
    issues = bill_issues(manjeera_bill, tanker_count, tanker_rate, readings)
    if issues:
        raise ValueError(" ".join(issues))

    total_water = water_total(manjeera_bill, tanker_count, tanker_rate)
    pairs = {f: (D(readings[f][0]), D(readings[f][1])) for f in FLAT_NUMBERS}
    total_units = sum((c - p for p, c in pairs.values()), ZERO)
    cpu = ceil_to_int(total_water / total_units)

    lines = []
    for flat in FLAT_NUMBERS:
        prev, curr = pairs[flat]
        units = curr - prev
        water = units * cpu
        lines.append(FlatLine(flat, prev, curr, units, water, round_up_to_step(water + maintenance)))

    return BillResult(
        manjeera_bill=D(manjeera_bill),
        tanker_count=int(D(tanker_count)),
        tanker_rate=D(tanker_rate),
        total_water_bill=total_water,
        total_units=total_units,
        cost_per_unit=cpu,
        lines=tuple(lines),
        total_collection=sum((ln.total_bill for ln in lines), ZERO),
        maintenance=maintenance,
    )


@dataclass(frozen=True)
class Estimate:
    """Live preview while readings are still being typed."""
    cost_per_unit: Decimal | None
    exact: bool
    entered: int
    lines: dict[str, FlatLine] = field(default_factory=dict)


def estimate_bills(
    manjeera_bill: object,
    tanker_count: object,
    tanker_rate: object,
    readings: Mapping[str, tuple[object, object | None]],
    fallback_units: Mapping[str, object] | None = None,
    maintenance: Decimal = MAINTENANCE_AMOUNT,
) -> Estimate:
    """Estimated per-flat bills from whatever has been typed so far.

    Flats without a reading yet count with last month's usage (fallback_units),
    so the cost per unit stays realistic instead of spiking while only a few flats are in.
    Becomes exact once all 12 readings are entered.
    """
    total_water = water_total(manjeera_bill, tanker_count, tanker_rate)
    fallback_units = fallback_units or {}
    entered = 0
    units_by_flat: dict[str, Decimal] = {}
    pool = ZERO
    for flat in FLAT_NUMBERS:
        prev, curr = readings.get(flat, (0, None))
        if curr is not None and D(curr) >= D(prev):
            entered += 1
            units_by_flat[flat] = D(curr) - D(prev)
            pool += units_by_flat[flat]
        else:
            pool += max(D(fallback_units.get(flat)), ZERO)

    exact = entered == len(FLAT_NUMBERS)
    if total_water <= 0 or pool <= 0:
        return Estimate(None, exact, entered)

    cpu = ceil_to_int(total_water / pool)
    lines = {}
    for flat, units in units_by_flat.items():
        prev, curr = readings[flat]
        water = units * cpu
        lines[flat] = FlatLine(flat, D(prev), D(curr), units, water, round_up_to_step(water + maintenance))
    return Estimate(cpu, exact, entered, lines)


# ---------------------------------------------------------------------------
# Closing the month
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExpenseLine:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class CloseResult:
    opening_balance: Decimal
    expenses: tuple[ExpenseLine, ...]
    total_variable_expenses: Decimal
    total_water_bill: Decimal
    total_expenditure: Decimal
    total_collection: Decimal
    net: Decimal
    closing_balance: Decimal


def clean_expenses(rows: Iterable[Mapping[str, object]]) -> tuple[ExpenseLine, ...]:
    """Drop blank rows; keep named rows with a positive amount."""
    out = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        amount = D(r.get("amount"))
        if name and amount > 0:
            out.append(ExpenseLine(name, amount))
    return tuple(out)


def compute_close(
    opening_balance: object,
    expenses: Iterable[ExpenseLine],
    total_water_bill: object,
    total_collection: object,
) -> CloseResult:
    expenses = tuple(expenses)
    variable = sum((e.amount for e in expenses), ZERO)
    expenditure = variable + D(total_water_bill)
    net = D(total_collection) - expenditure
    return CloseResult(
        opening_balance=D(opening_balance),
        expenses=expenses,
        total_variable_expenses=variable,
        total_water_bill=D(total_water_bill),
        total_expenditure=expenditure,
        total_collection=D(total_collection),
        net=net,
        closing_balance=D(opening_balance) + net,
    )


# ---------------------------------------------------------------------------
# Formatting (shared by UI and PDF)
# ---------------------------------------------------------------------------
def fmt_units(value: object) -> str:
    """12 -> '12', 12.5 -> '12.5'."""
    v = D(value).normalize()
    if v == v.to_integral_value():
        return f"{int(v):,}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def group_indian(n: int) -> str:
    """1234567 -> '12,34,567'."""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + s


def fmt_money(value: object, symbol: str = "₹") -> str:
    """Indian-grouped rupees; paise shown only when present."""
    v = D(value).quantize(Decimal("0.01"))
    whole = int(v)
    paise = abs(v - whole)
    sign = "-" if v < 0 else ""
    base = group_indian(abs(whole))
    if paise:
        base += f"{paise:.2f}"[1:]
    return f"{sign}{symbol}{base}"
