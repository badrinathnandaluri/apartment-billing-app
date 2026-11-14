"""Shown once, on an empty database: opening balance + starting meter readings."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from billing.config import FLAT_NUMBERS
from billing.domain import D
from billing.services import Ledger
from billing.ui import theme


def render(ledger: Ledger) -> None:
    _, mid, _ = st.columns([1, 2.4, 1])
    with mid, theme.card("setup"):
        theme.section("Welcome. Let's set the starting point", "One-time setup")
        st.caption("Enter the balance in hand and each flat's latest meter reading. "
                   "The first month you bill will use these as its opening balance and previous readings.")
        with st.form("setup", border=False):
            opening = st.number_input("Balance in hand today  ₹ (negative if the society owes money)",
                                      value=0.0, step=100.0, format="%.2f")
            st.markdown('<div class="mhead" style="margin-top:.6rem">Latest meter readings</div>',
                        unsafe_allow_html=True)
            readings: dict[str, float] = {}
            for floor in "1234":
                cols = st.columns(3)
                for col, flat in zip(cols, [f for f in FLAT_NUMBERS if f.startswith(floor)]):
                    readings[flat] = col.number_input(f"Flat {flat}", min_value=0.0, value=0.0, step=1.0,
                                                      format="%.2f", key=f"setup_{flat}")
            if st.form_submit_button("Save starting point", type="primary", use_container_width=True):
                ledger.save_initial({f: D(v) for f, v in readings.items()}, D(opening) or Decimal(0))
                st.session_state["flash"] = "Starting point saved. You can bill your first month now."
                st.rerun()
