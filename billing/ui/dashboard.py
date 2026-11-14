"""Tab 1: last closed month at a glance, trends, and the full history with PDFs."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from billing.db.repo import LedgerError
from billing.domain import D, fmt_money, fmt_units
from billing.pdf.render import bills_pdf, full_pdf, month_label, slips_pdf
from billing.services import Ledger
from billing.ui import auth, theme

BRAND = "#0f4c81"
SOFT = "#9cc3e6"


def _delta(cur, prev, money=True, invert=False) -> tuple[str, str]:
    if prev is None:
        return "", ""
    diff = D(cur) - D(prev)
    if diff == 0:
        return "same as last month", ""
    better = (diff < 0) if invert else (diff > 0)
    txt = (fmt_money(abs(diff)) if money else fmt_units(abs(diff))) + (" more" if diff > 0 else " less") + " than last month"
    return txt, "up" if better else "down"


def _units_chart(report) -> alt.Chart:
    df = pd.DataFrame([{"Flat": ln.flat, "Units": float(ln.units), "Bill": float(ln.total_bill)} for ln in report.bills.lines])
    avg = df["Units"].mean()
    base = alt.Chart(df).encode(x=alt.X("Flat:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)))
    bars = base.mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color=BRAND, size=26).encode(
        y=alt.Y("Units:Q", title="Units", axis=alt.Axis(grid=True, gridColor="#eef2f7", domain=False, ticks=False)),
        tooltip=[alt.Tooltip("Flat:N"), alt.Tooltip("Units:Q", format=",.1f"), alt.Tooltip("Bill:Q", format=",.0f", title="Bill ₹")],
    )
    rule = alt.Chart(pd.DataFrame({"avg": [avg]})).mark_rule(color="#94a3b8", strokeDash=[4, 4]).encode(y="avg:Q")
    return (bars + rule).properties(height=230).configure_view(strokeWidth=0).configure(background="#ffffff")


def _trend_chart(months: list[dict]) -> alt.Chart:
    closed = [r for r in months if r["status"] == "closed"][:12][::-1]
    df = pd.DataFrame([{"Month": month_label(r["month_year"])[:3] + " " + r["month_year"][2:4],
                        "Closing balance": float(r["closing_balance"]),
                        "Cost per unit": float(r["cost_per_unit"])} for r in closed])
    x = alt.X("Month:N", sort=None, axis=alt.Axis(labelAngle=0, title=None))
    area = alt.Chart(df).mark_area(line={"color": BRAND, "strokeWidth": 2.5}, color=alt.Gradient(
        gradient="linear", stops=[alt.GradientStop(color="#ffffff", offset=0), alt.GradientStop(color=SOFT, offset=1)],
        x1=1, x2=1, y1=1, y2=0), point=alt.OverlayMarkDef(color=BRAND, size=40)).encode(
        x=x, y=alt.Y("Closing balance:Q", title="Closing balance ₹", axis=alt.Axis(grid=True, gridColor="#eef2f7", domain=False, ticks=False)),
        tooltip=[alt.Tooltip("Month:N"), alt.Tooltip("Closing balance:Q", format=",.0f"), alt.Tooltip("Cost per unit:Q", format=",.0f")],
    )
    return area.properties(height=230).configure_view(strokeWidth=0).configure(background="#ffffff")


@st.dialog("Reopen month")
def _reopen(ledger: Ledger, month: str) -> None:
    st.markdown(f"Reopening **{month_label(month)}** lets you change its readings, water costs and expenses. "
                "You'll need to close it again afterwards.")
    pw = st.text_input("Confirm your password", type="password")
    if st.button("Reopen", type="primary", use_container_width=True, icon=":material/lock_open:"):
        if not auth.verify_current_password(pw):
            st.error("Wrong password.")
            return
        try:
            ledger.reopen_month(month)
        except LedgerError as e:
            st.error(str(e))
            return
        st.session_state["flash"] = f"{month_label(month)} reopened. Edit it in the other tabs."
        st.session_state["reload"] = True
        st.rerun()


def _history(ledger: Ledger, months: list[dict]) -> None:
    with theme.card("history"):
        theme.section("History", f"{len(months)} month(s)")
        closed_ = lambda r: r["status"] == "closed"  # noqa: E731
        rows = [{
            "Month": month_label(r["month_year"]),
            "Status": "✅ Closed" if closed_(r) else "🟡 Open",
            "Units": fmt_units(r["total_apartment_units"]),
            "Cost / unit": fmt_money(r["cost_per_unit"]),
            "Water cost": fmt_money(r["total_water_bill"]),
            "Collection": fmt_money(r["total_collection"]),
            "Expenditure": fmt_money(r["total_expenditure"]) if closed_(r) else "–",
            "Closing balance": fmt_money(r["closing_balance"]) if closed_(r) else "–",
        } for r in months]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     height=min(38 + 35 * len(rows), 400))

        c1, c2 = st.columns([1.2, 2], vertical_alignment="bottom")
        pick = c1.selectbox("Documents for", [r["month_year"] for r in months], format_func=month_label,
                            key="hist_pick")
        report = ledger.report(pick)
        with c2:
            bar = st.container(horizontal=True)
            if report:
                if report.close:
                    bar.download_button("Monthly report (2 pages)", full_pdf(pick, report.bills, report.close),
                                        f"report_{pick}.pdf", "application/pdf", type="primary",
                                        icon=":material/picture_as_pdf:", on_click="ignore")
                bar.download_button("Bills sheet", bills_pdf(pick, report.bills), f"bills_{pick}.pdf",
                                    "application/pdf", icon=":material/description:", on_click="ignore")
                bar.download_button("Slips", slips_pdf(pick, report.bills), f"slips_{pick}.pdf",
                                    "application/pdf", icon=":material/content_cut:", on_click="ignore")
                latest = months[0]["month_year"]
                if report.status == "closed" and pick == latest:
                    if bar.button("Reopen…", icon=":material/lock_open:", type="tertiary"):
                        _reopen(ledger, pick)


def render(ledger: Ledger, months: list[dict]) -> None:
    closed = [r for r in months if r["status"] == "closed"]
    if not closed:
        with theme.card("dash_empty"):
            theme.empty("No closed months yet",
                        "Enter this month's water costs and readings, save the bills, then close the month. "
                        "Its summary will appear here.")
        if months:
            _history(ledger, months)
        return

    last = closed[0]
    prev = closed[1] if len(closed) > 1 else None
    report = ledger.report(last["month_year"])

    theme.md(f'<div class="sec"><span class="t">{theme.esc(month_label(last["month_year"]))} at a glance</span>'
             f'<span class="d">Last closed month</span></div>')
    s_cb, t_cb = _delta(last["closing_balance"], prev and prev["closing_balance"])
    s_cpu, t_cpu = _delta(last["cost_per_unit"], prev and prev["cost_per_unit"], invert=True)
    s_u, t_u = _delta(last["total_apartment_units"], prev and prev["total_apartment_units"], money=False, invert=True)
    net = D(last["net_profit_loss"])
    theme.kpi_row(
        theme.kpi("Closing balance", fmt_money(last["closing_balance"]), s_cb or "carried forward", hero=True),
        theme.kpi("Collected", fmt_money(last["total_collection"]), "12 flats, incl. maintenance"),
        theme.kpi("Spent", fmt_money(last["total_expenditure"]),
                  f"{'surplus' if net >= 0 else 'deficit'} {fmt_money(abs(net))}", "up" if net >= 0 else "down"),
        theme.kpi("Cost per unit", fmt_money(last["cost_per_unit"]), s_cpu, t_cpu),
        theme.kpi("Water used", f"{fmt_units(last['total_apartment_units'])} units", s_u, t_u),
    )
    st.markdown("")

    c1, c2 = st.columns([1.25, 1], gap="medium")
    with c1, theme.card("chart_units"):
        theme.section("Units by flat", "dashed line = building average")
        if report:
            st.altair_chart(_units_chart(report), use_container_width=True)
    with c2, theme.card("chart_trend"):
        theme.section("Balance trend", "closing balance, last 12 months")
        if len(closed) >= 2:
            st.altair_chart(_trend_chart(months), use_container_width=True)
        else:
            theme.empty("Trend appears after two closed months", "")

    if report and report.close:
        c3, c4 = st.columns([1, 1], gap="medium")
        with c3, theme.card("where_money"):
            theme.section("Where the money went", month_label(last["month_year"]))
            rows = [theme.kv("Manjeera", fmt_money(report.bills.manjeera_bill)),
                    theme.kv("Tankers", fmt_money(report.bills.tanker_total),
                             note=f"{report.bills.tanker_count} × {fmt_money(report.bills.tanker_rate)}")]
            rows += [theme.kv(e.name, fmt_money(e.amount)) for e in report.close.expenses]
            rows.append(theme.kv("Total spent", fmt_money(report.close.total_expenditure), cls="total"))
            theme.kv_block(*rows)
        with c4, theme.card("top_users"):
            theme.section("Highest bills", month_label(last["month_year"]))
            top = sorted(report.bills.lines, key=lambda ln: ln.total_bill, reverse=True)[:5]
            theme.kv_block(*[theme.kv(f"Flat {ln.flat}", fmt_money(ln.total_bill), note=f"{fmt_units(ln.units)} units")
                             for ln in top])
    st.markdown("")
    _history(ledger, months)
