from decimal import Decimal

import pytest

from billing.config import FLAT_NUMBERS
from billing.domain import (
    D, ExpenseLine, bill_issues, ceil_to_int, clean_expenses, compute_bills, compute_close,
    estimate_bills, fmt_money, fmt_units, round_up_to_step,
)


@pytest.mark.parametrize("raw, expected", [
    (160, 160), (161, 165), (162, 165), (163, 165), (165, 165), (166, 170), (3222, 3225), ("2664.5", 2665),
])
def test_bill_rounds_up_to_next_5(raw, expected):
    assert round_up_to_step(D(raw)) == expected


@pytest.mark.parametrize("raw, expected", [("96.1", 97), ("96.001", 97), ("100", 100), ("0.2", 1)])
def test_cost_per_unit_rounds_up(raw, expected):
    assert ceil_to_int(D(raw)) == expected


def readings(units_each, prev=1000):
    return {f: (prev, prev + units_each) for f in FLAT_NUMBERS}


def test_compute_bills_end_to_end():
    # 12 flats x 10 units = 120 units; water 11,530 -> 96.08/unit -> 97
    r = compute_bills(10_000, 3, "510", readings(10))
    assert r.total_water_bill == Decimal("11530")
    assert r.total_units == 120
    assert r.cost_per_unit == 97
    line = r.lines[0]
    assert line.water_bill == 970
    assert line.total_bill == 2470            # 1500 + 970 = 2470 (already a multiple of 5)
    assert r.total_collection == 2470 * 12


def test_fractional_units_and_rounding():
    rd = readings(10)
    rd["101"] = (1000, "1012.5")             # 12.5 units
    r = compute_bills(12_000, 0, 0, rd)
    # total units 122.5 -> 97.96 -> 98/unit; flat 101: 12.5 x 98 = 1225 + 1500 = 2725
    assert r.cost_per_unit == 98
    assert r.lines[0].water_bill == Decimal("1225.0")
    assert r.lines[0].total_bill == 2725
    assert r.lines[1].total_bill == 2480     # 980 + 1500


def test_issues_block_bad_input():
    rd = readings(10)
    rd["203"] = (500, 400)
    rd["303"] = (500, None)
    issues = bill_issues(0, 0, 0, rd)
    assert any("Total water cost" in i for i in issues)
    assert any("303" in i and "missing" in i for i in issues)
    assert any("Flat 203" in i for i in issues)
    with pytest.raises(ValueError):
        compute_bills(0, 0, 0, rd)


def test_zero_total_units_is_an_issue():
    assert any("Total units" in i for i in bill_issues(5000, 0, 0, readings(0)))


def test_estimate_uses_last_month_for_missing_flats():
    rd = {f: (1000, None) for f in FLAT_NUMBERS}
    rd["101"] = (1000, 1010)
    est = estimate_bills(11_530, 0, 0, rd, fallback_units={f: 10 for f in FLAT_NUMBERS})
    assert not est.exact and est.entered == 1
    assert est.cost_per_unit == 97            # same as if everyone used 10
    assert est.lines["101"].total_bill == 2470
    full = estimate_bills(11_530, 0, 0, readings(10))
    assert full.exact and full.cost_per_unit == compute_bills(11_530, 0, 0, readings(10)).cost_per_unit


def test_close_month_math_and_negative_balance():
    exp = clean_expenses([{"name": "Watchman", "amount": 8000}, {"name": "", "amount": 50}, {"name": "Lift", "amount": 0}])
    assert exp == (ExpenseLine("Watchman", Decimal("8000")),)
    c = compute_close(-500, exp, 11_530, 29_640)
    assert c.total_expenditure == 19_530
    assert c.net == 10_110
    assert c.closing_balance == 9_610


def test_formatting():
    assert fmt_money(1234567) == "₹12,34,567"
    assert fmt_money(-1500) == "-₹1,500"
    assert fmt_money("99.5", "Rs.") == "Rs.99.50"
    assert fmt_units(12) == "12" and fmt_units("12.50") == "12.5"
