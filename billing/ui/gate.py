"""Connects to the database with visible progress, and turns outages into a calm screen."""

from __future__ import annotations

import streamlit as st
from sqlalchemy.engine import Engine

from billing.db import engine as dbe
from billing.services import Ledger
from billing.ui import theme


@st.cache_resource(show_spinner=False)
def _engine(url: str) -> Engine:
    return dbe.create(url)


@st.cache_resource(show_spinner=False)
def _migrated(url: str) -> dict:
    # Filled once per server process after migrations succeed.
    return {"done": False}


def db_url() -> str | None:
    try:
        return st.secrets.get("db_url")
    except Exception:
        return None


class RetryNotice:
    """Shows 'Waking up database…' only when a call actually has to retry."""

    def __init__(self) -> None:
        self.slot = st.empty()
        self.shown = False

    def __call__(self, attempt: int, max_attempts: int, wait: float, diag: dbe.Diagnosis) -> None:
        self.shown = True
        hint = "The database is waking up" if diag.kind in ("timeout", "network") else diag.title
        self.slot.info(
            f"**Waking up database…** {hint}. Attempt {attempt + 1} of {max_attempts}, "
            f"retrying in {wait:.0f}s. Nothing you typed is lost.",
            icon=":material/hourglass_top:",
        )

    def clear(self) -> None:
        if self.shown:
            self.slot.empty()


def ledger(notice: RetryNotice, cls: type[Ledger] = Ledger) -> Ledger:
    url = db_url()
    if not url:
        st.error("No database configured. Add `db_url` to the app's secrets (see README → Secrets).")
        st.stop()
    lg = cls(_engine(url), on_retry=notice)
    flag = _migrated(url)
    if not flag["done"]:
        with st.spinner("Connecting to the database…"):
            lg.connect_and_migrate()
        flag["done"] = True
    return lg


def outage_screen(err: dbe.DatabaseUnavailable) -> None:
    d = err.diagnosis
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        theme.md(
            f'<div class="err"><div class="t">{theme.esc(d.title)}</div>'
            f'<div style="color:var(--ink-2);font-size:.92rem">Tried {err.attempts} time(s) over about a minute. '
            f'Your unsaved work is kept in this browser tab, so retrying is safe.</div></div>'
        )
        st.markdown("")
        st.markdown(d.advice)
        if st.button("Retry now", type="primary", icon=":material/refresh:"):
            st.rerun()
        with st.expander("Technical details"):
            st.code(str(err.cause)[:1500])
