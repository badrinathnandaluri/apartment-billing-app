"""Gnapika Residency: water & maintenance ledger.

    streamlit run app.py

Layout:  billing/domain.py (math)  ·  billing/db/ (pool, retries, schema, SQL)
         billing/services.py (use-cases)  ·  billing/pdf/ (documents)  ·  billing/ui/ (screens)
"""

from __future__ import annotations

from datetime import date

import streamlit as st

st.set_page_config(page_title="Gnapika Ledger", page_icon="💧", layout="wide", initial_sidebar_state="collapsed")

from billing.config import BUILDING_NAME  # noqa: E402
from billing.db.engine import DatabaseUnavailable  # noqa: E402
from billing.pdf.render import month_label  # noqa: E402
from billing.services import Ledger  # noqa: E402
from billing.ui import auth, commit, dashboard, expenses, gate, readings, setup, state, theme  # noqa: E402

TABS = ["Dashboard", "Expenses", "Meter readings", "Review & commit"]


class SessionLedger(Ledger):
    """Caches reads for this browser session; any write (or Refresh) clears the cache.

    Keeps typing snappy: entering a reading re-renders from memory instead of
    re-querying a database that may be a continent away.
    """

    def _cache(self) -> dict:
        if st.session_state.pop("reload", False):
            st.session_state["db_cache"] = {}
        return st.session_state.setdefault("db_cache", {})

    def _memo(self, key: str, fn):
        c = self._cache()
        if key not in c:
            c[key] = fn()
        return c[key]

    def months(self):
        return self._memo("months", super().months)

    def has_initial(self):
        return self._memo("has_initial", super().has_initial)

    def context(self, month):
        return self._memo(f"ctx:{month}", lambda: super(SessionLedger, self).context(month))

    def report(self, month):
        return self._memo(f"report:{month}", lambda: super(SessionLedger, self).report(month))


def next_month(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def working_month(months: list[dict]) -> tuple[str, list[str]]:
    """The open month if there is one; otherwise a choice of new months (in order)."""
    open_ = [r["month_year"] for r in months if r["status"] == "open"]
    if open_:
        return open_[-1], []
    if months:
        start = next_month(months[0]["month_year"])
    else:
        t = date.today()
        start = f"{t.year - (t.month == 1):04d}-{(t.month - 2) % 12 + 1:02d}"   # last month
    options = [start]
    for _ in range(5):
        options.append(next_month(options[-1]))
    return options[0], options


def header(month: str | None, status: str | None, choices: list[str]):
    """Draws the top bar. Returns (chosen month, slot for the draft-sync chip)."""
    sync_slot = None
    c_brand, c_month, c_actions = st.columns([1.3, 2, 0.9], vertical_alignment="center")
    c_brand.markdown(
        f'<div class="ab-brand"><div class="ab-logo">G</div><div><div class="ab-title">{theme.esc(BUILDING_NAME)}</div>'
        f'<div class="ab-sub">Water &amp; maintenance ledger</div></div></div>', unsafe_allow_html=True)

    with c_month:
        if month:
            row = st.container(horizontal=True, vertical_alignment="center", gap="small")
            if choices:
                month = row.selectbox("Billing month", choices, format_func=month_label, key="new_month",
                                      label_visibility="collapsed", width=180,
                                      help="Months are billed in order; pick the month these readings are for.")
            else:
                row.markdown(f'<div class="ab-title" style="font-size:1.05rem">{month_label(month)}</div>',
                             unsafe_allow_html=True)
            badge = theme.pill("Bills saved · open", "warn") if status == "open" else theme.pill("New month", "info")
            row.markdown(badge, unsafe_allow_html=True)
            sync_slot = row.empty()

    with c_actions:
        bar = st.container(horizontal=True, horizontal_alignment="right", gap="small")
        if bar.button("Refresh", icon=":material/refresh:", type="tertiary", help="Reload data from the database"):
            st.session_state["reload"] = True
            st.rerun()
        if bar.button("Sign out", icon=":material/logout:", type="tertiary"):
            auth.logout()
            st.rerun()
    return month, sync_slot


def main(notice: gate.RetryNotice) -> None:
    ledger = gate.ledger(notice, cls=SessionLedger)

    if not ledger.has_initial():
        header(None, None, [])
        setup.render(ledger)
        return

    months = ledger.months()
    month, choices = working_month(months)
    if choices:
        month = st.session_state.get("new_month", month)
        if month not in choices:
            month = choices[0]
    month, sync_slot = header(month, None if choices else "open", choices)
    ctx = ledger.context(month)
    d = state.draft(ctx)
    notice.clear()

    if flash := st.session_state.pop("flash", None):
        st.toast(flash, icon=":material/check_circle:")

    tabs = st.tabs(TABS, key="nav", on_change="rerun", default=TABS[0] if any(
        r["status"] == "closed" for r in months) else TABS[1])
    t_dash, t_exp, t_read, t_commit = tabs
    if t_dash.open:
        with t_dash:
            dashboard.render(ledger, months)
    if t_exp.open:
        with t_exp:
            expenses.render(ctx, d, locked=False)
    if t_read.open:
        with t_read:
            readings.render(ctx, d, locked=False)
    if t_commit.open:
        with t_commit:
            commit.render(ledger, ctx, d)

    if auth.using_plain_password():
        st.caption("🔐 Tip: replace `app_password` with `app_password_hash` in your secrets "
                   "(run `python scripts/hash_password.py`).")

    # Last, so the screen is already drawn while the draft is written.
    state.autosave(ledger, month)
    text, tone = state.sync_status(month)
    sync_slot.markdown(theme.pill(text, tone), unsafe_allow_html=True)


theme.apply()
if auth.require_login():
    _notice = gate.RetryNotice()
    try:
        main(_notice)
    except DatabaseUnavailable as err:
        _notice.clear()
        gate.outage_screen(err)
