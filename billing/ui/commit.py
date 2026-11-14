"""Tab 4: review, save bills (step 1), close the month (step 2), download PDFs."""

from __future__ import annotations

import streamlit as st

from billing.db.repo import LedgerError
from billing.domain import (
    D, bill_issues, clean_expenses, compute_bills, compute_close, fmt_money, fmt_units,
)
from billing.pdf.render import bills_pdf, full_pdf, month_label, slips_pdf
from billing.services import Ledger, MonthContext
from billing.ui import state, theme


def _same_as_saved(ctx: MonthContext, bills) -> bool:
    rec = ctx.record
    if not rec:
        return False
    if D(rec["total_collection"]) != bills.total_collection or D(rec["cost_per_unit"]) != bills.cost_per_unit \
            or D(rec["manjeera_bill"]) != bills.manjeera_bill or int(rec["tanker_count"]) != bills.tanker_count \
            or D(rec["tanker_rate"]) != bills.tanker_rate:
        return False
    return all(ctx.saved_readings.get(ln.flat) == ln.current for ln in bills.lines)


@st.dialog("Close the month?")
def _confirm_close(ledger: Ledger, ctx: MonthContext, close) -> None:
    st.markdown(f"This locks **{month_label(ctx.month)}** and carries **{fmt_money(close.closing_balance)}** "
                f"forward as next month's opening balance.")
    st.caption("The latest month can be reopened later with your password if something needs fixing.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", use_container_width=True):
        st.rerun()
    if c2.button("Close month", type="primary", use_container_width=True, icon=":material/lock:"):
        try:
            ledger.close_month(ctx.month, close)
        except LedgerError as e:
            st.error(str(e))
            return
        state.reset(ctx.month)
        st.session_state["flash"] = f"{month_label(ctx.month)} closed. Closing balance {fmt_money(close.closing_balance)}."
        st.session_state["reload"] = True
        st.rerun()


def render(ledger: Ledger, ctx: MonthContext, d: dict) -> None:
    m = ctx.month
    mb, tc, tr = state.water_inputs(d)
    pairs = state.readings_pairs(d, ctx.previous)
    issues = bill_issues(mb, tc, tr, pairs)
    bills = compute_bills(mb, tc, tr, pairs) if not issues else None
    saved_current = bills is not None and _same_as_saved(ctx, bills)
    bills_saved = ctx.status in ("open", "closed")

    left, right = st.columns([1, 1.15], gap="medium")

    # ---- step 1: bills ------------------------------------------------------
    with left, theme.card("step1"):
        theme.step(1, "Save bills & print", "Hand the bills sheet or slips to each flat",
                   "done" if saved_current else "on")
        entered = sum(1 for _, c in pairs.values() if c is not None)
        theme.md(
            theme.check(D(mb) + tc * D(tr) > 0, "Water cost entered (Manjeera / tankers)")
            + theme.check(entered == len(pairs), f"All meter readings entered ({entered}/{len(pairs)})")
            + theme.check(not any("below previous" in i for i in issues), "No reading below last month's")
        )
        if issues:
            for i in issues:
                st.caption(f"• {i}")
        if bills:
            theme.kv_block(
                theme.kv("Total units", fmt_units(bills.total_units)),
                theme.kv("Cost per unit", fmt_money(bills.cost_per_unit),
                         note=f"{fmt_money(bills.total_water_bill)} ÷ {fmt_units(bills.total_units)}, rounded up"),
                theme.kv("Total collection", fmt_money(bills.total_collection), cls="grand"),
            )
            if bills_saved and not saved_current:
                st.warning("Readings or water costs changed since the bills were saved. Save again to update the PDFs.",
                           icon=":material/sync_problem:")
            if saved_current:
                theme.md('<div class="saved-note">✓ Bills saved. Print the sheet or slips below.</div>')
            elif st.button("Save changes to bills" if bills_saved else "Save bills", type="primary",
                           use_container_width=True, icon=":material/save:"):
                try:
                    ledger.save_bills(m, bills)
                    st.session_state["flash"] = f"Bills for {month_label(m)} saved."
                    st.session_state["reload"] = True
                    st.rerun()
                except LedgerError as e:
                    st.error(str(e))
            if saved_current:
                c1, c2 = st.columns(2)
                c1.download_button("Bills sheet", bills_pdf(m, bills), f"bills_{m}.pdf", "application/pdf",
                                   use_container_width=True, icon=":material/description:", on_click="ignore")
                c2.download_button("Cut-out slips", slips_pdf(m, bills), f"slips_{m}.pdf", "application/pdf",
                                   use_container_width=True, icon=":material/content_cut:", on_click="ignore")

    # ---- step 2: close ------------------------------------------------------
    with right, theme.card("step2"):
        theme.step(2, "Close the month", "Locks the ledger and carries the balance forward",
                   "on" if saved_current else "")
        exps = clean_expenses(state.expense_rows(d))
        if bills:
            close = compute_close(ctx.opening_balance, exps, bills.total_water_bill, bills.total_collection)
            net_label = "Surplus this month" if close.net >= 0 else "Deficit this month"
            theme.kv_block(
                theme.kv("Opening balance", fmt_money(close.opening_balance), note="from last month"),
                theme.kv("+ Collection", fmt_money(close.total_collection)),
                theme.kv("− Water cost", fmt_money(close.total_water_bill)),
                theme.kv("− Other expenses", fmt_money(close.total_variable_expenses), note=f"{len(exps)} item(s)"),
                theme.kv(net_label, fmt_money(close.net), cls="total"),
                theme.kv("Closing balance", fmt_money(close.closing_balance), cls="grand"),
            )
            if not exps:
                st.info("No expenses entered yet. Add them in the **Expenses** tab before closing.",
                        icon=":material/info:")
            ready = saved_current
            if not ready:
                st.caption("Save the bills (step 1) first.")
            if st.button("Close month…", type="primary", use_container_width=True, disabled=not ready,
                         icon=":material/lock:"):
                _confirm_close(ledger, ctx, close)
            st.caption("The 2-page report (bills sheet + balance sheet) is available on the Dashboard once closed.")
        else:
            theme.empty("Waiting for step 1", "Finish the water cost and all 12 readings to preview the closing balance.")
