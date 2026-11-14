"""Tab 2: water costs and the month's expenses."""

from __future__ import annotations

import streamlit as st

from billing.domain import clean_expenses, fmt_money, water_total
from billing.services import MonthContext
from billing.ui import state, theme


def _setter(field: str):
    def set_(d: dict, v: object) -> None:
        d[field] = v
    return set_


def _row_setter(row_id: str, field: str):
    def set_(d: dict, v: object) -> None:
        for r in d["expenses"]:
            if r["id"] == row_id:
                r[field] = v
    return set_


def _add_row(month: str, d: dict) -> None:
    d["expenses"].append(state.new_expense_row())
    state.mark_dirty(month)


def _remove_row(month: str, d: dict, row_id: str) -> None:
    d["expenses"] = [r for r in d["expenses"] if r["id"] != row_id]
    state.mark_dirty(month)


def render(ctx: MonthContext, d: dict, locked: bool) -> None:
    m = ctx.month
    left, right = st.columns([1, 1.25], gap="medium")

    # ---- water --------------------------------------------------------------
    with left, theme.card("water"):
        theme.section("Water supply", "Decides the cost per unit")
        k_mb, k_tc, k_tr = state.wkey(m, "manjeera"), state.wkey(m, "tanker_count"), state.wkey(m, "tanker_rate")
        state.seed(k_mb, d.get("manjeera"))
        state.seed(k_tc, int(d.get("tanker_count") or 0))
        state.seed(k_tr, d.get("tanker_rate"))

        st.number_input("Manjeera (municipal) bill  ₹", key=k_mb, min_value=0.0, step=100.0, format="%.2f",
                        value=None, placeholder="e.g. 8,450", disabled=locked,
                        on_change=state.bind, args=(m, d, k_mb, _setter("manjeera")))
        c1, c2 = st.columns(2)
        with c1:
            st.number_input("Tankers used", key=k_tc, min_value=0, step=1, disabled=locked,
                            on_change=state.bind, args=(m, d, k_tc, _setter("tanker_count")))
        with c2:
            st.number_input("Cost per tanker  ₹", key=k_tr, min_value=0.0, step=50.0, format="%.2f",
                            value=None, placeholder="e.g. 900", disabled=locked,
                            on_change=state.bind, args=(m, d, k_tr, _setter("tanker_rate")))

        mb, tc, tr = state.water_inputs(d)
        theme.kv_block(
            theme.kv("Manjeera", fmt_money(mb)),
            theme.kv("Tankers", fmt_money(tc * tr), note=f"{tc} × {fmt_money(tr)}"),
            theme.kv("Total water cost", fmt_money(water_total(mb, tc, tr)), cls="total"),
        )

    # ---- expenses -----------------------------------------------------------
    with right, theme.card("expenses"):
        theme.section("Monthly expenses", "Names carry over from last month")
        h1, h2, _ = st.columns([2.2, 1.4, 0.45])
        h1.markdown('<div class="mhead">Expense</div>', unsafe_allow_html=True)
        h2.markdown('<div class="mhead">Amount ₹</div>', unsafe_allow_html=True)

        for row in list(d["expenses"]):
            rid = row["id"]
            kn, ka = state.wkey(m, "exp", rid, "name"), state.wkey(m, "exp", rid, "amount")
            state.seed(kn, row.get("name") or "")
            state.seed(ka, row.get("amount"))
            c1, c2, c3 = st.columns([2.2, 1.4, 0.45], vertical_alignment="center")
            with c1:
                st.text_input("Expense", key=kn, label_visibility="collapsed", placeholder="Expense name",
                              disabled=locked, on_change=state.bind, args=(m, d, kn, _row_setter(rid, "name")))
            with c2:
                st.number_input("Amount", key=ka, label_visibility="collapsed", min_value=0.0, step=100.0,
                                format="%.2f", value=None, placeholder="0", disabled=locked,
                                on_change=state.bind, args=(m, d, ka, _row_setter(rid, "amount")))
            with c3:
                st.button("", key=state.wkey(m, "exp", rid, "del"), icon=":material/close:", type="tertiary",
                          help="Remove this expense", disabled=locked, on_click=_remove_row, args=(m, d, rid))

        st.button("Add expense", icon=":material/add:", disabled=locked, on_click=_add_row, args=(m, d),
                  key=state.wkey(m, "exp_add"))
        exps = clean_expenses(state.expense_rows(d))
        total = sum((e.amount for e in exps), 0)
        theme.kv_block(theme.kv("Total other expenses", fmt_money(total), note=f"{len(exps)} item(s)", cls="total"))
        st.caption("Rows without a name or amount are ignored. Expenses can be filled in any time before closing the month.")
