"""Tab 3: meter readings. Previous readings are locked; bills update as each reading is entered."""

from __future__ import annotations

import streamlit as st

from billing.config import FLAT_NUMBERS
from billing.domain import D, estimate_bills, fmt_money, fmt_units, water_total
from billing.services import MonthContext
from billing.ui import state, theme

WIDTHS = [0.62, 1.05, 1.25, 0.72, 0.95, 0.95]


def _setter(flat: str):
    def set_(d: dict, v: object) -> None:
        d["readings"][flat] = v
    return set_


def _flat_row(m: str, d: dict, ctx: MonthContext, flat: str, est, locked: bool) -> None:
    prev = ctx.previous[flat]
    key = state.wkey(m, "reading", flat)
    state.seed(key, d["readings"].get(flat))
    c_flat, c_prev, c_cur, c_units, c_water, c_total = st.columns(WIDTHS, vertical_alignment="center", gap="small")
    c_flat.markdown(f'<span class="flat">{flat}</span>', unsafe_allow_html=True)
    c_prev.markdown(f'<div class="locked" title="Last month\'s reading (locked)">{theme.LOCK_SVG}{fmt_units(prev)}</div>',
                    unsafe_allow_html=True)
    with c_cur:
        st.number_input(f"Current reading, flat {flat}", key=key, label_visibility="collapsed",
                        min_value=0.0, step=1.0, format="%g", value=None, placeholder=f"≥ {fmt_units(prev)}",
                        disabled=locked, on_change=state.bind, args=(m, d, key, _setter(flat)))

    cur = d["readings"].get(flat)
    if cur is None:
        last = ctx.previous_usage.get(flat)
        hint = f"<small>last {fmt_units(last)}</small>" if last is not None else "–"
        c_units.markdown(f'<div class="num dim">{hint}</div>', unsafe_allow_html=True)
        c_water.markdown('<div class="num dim">–</div>', unsafe_allow_html=True)
        c_total.markdown('<div class="num dim">–</div>', unsafe_allow_html=True)
        return
    units = D(cur) - prev
    if units < 0:
        c_units.markdown(f'<div class="num bad">{fmt_units(units)}</div>', unsafe_allow_html=True)
        c_water.markdown('<div class="num bad">below</div>', unsafe_allow_html=True)
        c_total.markdown('<div class="num bad">previous</div>', unsafe_allow_html=True)
        return
    line = est.lines.get(flat)
    c_units.markdown(f'<div class="num">{fmt_units(units)}</div>', unsafe_allow_html=True)
    if line:
        c_water.markdown(f'<div class="num">{fmt_money(line.water_bill)}</div>', unsafe_allow_html=True)
        c_total.markdown(f'<div class="num">{fmt_money(line.total_bill)}</div>', unsafe_allow_html=True)
    else:
        c_water.markdown('<div class="num dim"><small>needs water cost</small></div>', unsafe_allow_html=True)


def _header() -> None:
    cols = st.columns(WIDTHS, gap="small")
    for c, label in zip(cols, ["Flat", "Previous", "Current", "Units", "Water", "Total bill"]):
        c.markdown(f'<div class="mhead">{label}</div>', unsafe_allow_html=True)


def render(ctx: MonthContext, d: dict, locked: bool) -> None:
    m = ctx.month
    mb, tc, tr = state.water_inputs(d)
    pairs = state.readings_pairs(d, ctx.previous)
    est = estimate_bills(mb, tc, tr, pairs, fallback_units=ctx.previous_usage)
    total_water = water_total(mb, tc, tr)
    entered_units = sum((ln.units for ln in est.lines.values()), D(0))

    cpu_label = "Cost per unit" if est.exact else "Cost per unit (estimate)"
    cpu_sub = "final" if est.exact else ("uses last month's usage for flats not entered yet" if est.cost_per_unit else
                                         "enter the water cost in Expenses")
    theme.kpi_row(
        theme.kpi("Readings entered", f"{est.entered} / {len(FLAT_NUMBERS)}",
                  "all in" if est.exact else f"{len(FLAT_NUMBERS) - est.entered} to go", "up" if est.exact else ""),
        theme.kpi("Total water cost", fmt_money(total_water), "Manjeera + tankers"),
        theme.kpi(cpu_label, fmt_money(est.cost_per_unit) if est.cost_per_unit else "–", cpu_sub),
        theme.kpi("Total units" if est.exact else "Units so far", fmt_units(entered_units),
                  "all 12 flats" if est.exact else f"{len(est.lines)} flat(s) entered"),
        theme.kpi("Total collection" if est.exact else "Collection so far",
                  fmt_money(sum((ln.total_bill for ln in est.lines.values()), D(0))), "incl. maintenance", hero=True),
    )
    st.markdown("")

    left, right = st.columns(2, gap="medium")
    floors = {1: left, 2: left, 3: right, 4: right}
    for side, name in ((left, "a"), (right, "b")):
        with side, theme.card(f"meters_{name}"):
            _header()
            for floor in [f for f, s in floors.items() if s is side]:
                theme.md(f'<div class="floor">Floor {floor}</div>')
                for flat in [x for x in FLAT_NUMBERS if x.startswith(str(floor))]:
                    _flat_row(m, d, ctx, flat, est, locked)
    st.caption("Press **Enter** or **Tab** after each reading; the bill updates instantly and the draft saves itself. "
               "Totals are rounded up to the next ₹5.")
