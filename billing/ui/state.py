"""Work-in-progress state for the month being billed.

Three layers, so nothing typed is ever lost:

1. Widget values: Streamlit forgets these when a widget isn't on screen
   (e.g. another tab is open, or the DB error screen is showing).
2. The *draft* dict in st.session_state: the source of truth. Every widget
   copies its value here on change and is re-seeded from it when it reappears.
3. The drafts table in Postgres: the draft is auto-saved after each change, so
   a browser refresh, a new device, or the app going to sleep restores it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import streamlit as st

from billing.config import DEFAULT_EXPENSES, FLAT_NUMBERS
from billing.db.engine import DatabaseUnavailable
from billing.domain import D
from billing.services import Ledger, MonthContext

_DRAFTS = "drafts"            # {month: draft}
_DIRTY = "draft_dirty"        # set of months with unsaved changes
_SYNC = "draft_sync"          # {month: (ok: bool, at: datetime)}


def _num(v: object) -> float | None:
    return None if v is None or v == "" else float(v)


def _new_row(name: str = "", amount: float | None = None) -> dict:
    return {"id": uuid.uuid4().hex[:8], "name": name, "amount": amount}


def build_draft(ctx: MonthContext) -> dict:
    """Starting point for a month: DB draft > saved month > sensible defaults."""
    if ctx.draft:
        d = {k: v for k, v in ctx.draft.items() if not k.startswith("_")}
        d.setdefault("readings", {})
        d.setdefault("expenses", [])
        for row in d["expenses"]:
            row.setdefault("id", uuid.uuid4().hex[:8])
        return d

    rec = ctx.record
    if rec:
        expenses = [_new_row(e["expense_name"], _num(e["amount"])) for e in ctx.saved_expenses]
        if not expenses:
            expenses = [_new_row(n) for n in (ctx.suggested_expense_names or DEFAULT_EXPENSES)]
        return {
            "manjeera": _num(rec["manjeera_bill"]),
            "tanker_count": int(rec["tanker_count"] or 0),
            "tanker_rate": _num(rec["tanker_rate"]),
            "readings": {f: _num(ctx.saved_readings.get(f)) for f in FLAT_NUMBERS},
            "expenses": expenses,
        }

    return {
        "manjeera": None,
        "tanker_count": 0,
        "tanker_rate": None,
        "readings": {f: None for f in FLAT_NUMBERS},
        "expenses": [_new_row(n) for n in (ctx.suggested_expense_names or DEFAULT_EXPENSES)],
    }


def draft(ctx: MonthContext) -> dict:
    drafts = st.session_state.setdefault(_DRAFTS, {})
    if ctx.month not in drafts:
        drafts[ctx.month] = build_draft(ctx)
    return drafts[ctx.month]


def reset(month: str) -> None:
    st.session_state.get(_DRAFTS, {}).pop(month, None)
    st.session_state.get(_DIRTY, set()).discard(month)
    for k in [k for k in st.session_state.keys() if isinstance(k, str) and k.startswith(f"w:{month}:")]:
        del st.session_state[k]


def mark_dirty(month: str) -> None:
    st.session_state.setdefault(_DIRTY, set()).add(month)


# ---------------------------------------------------------------------------
# Widget binding
# ---------------------------------------------------------------------------
def wkey(month: str, *path: str) -> str:
    return "w:" + month + ":" + ":".join(path)


def seed(key: str, value: object) -> None:
    """Give a widget its value from the draft the first time it appears."""
    if key not in st.session_state:
        st.session_state[key] = value


def bind(month: str, d: dict, key: str, setter) -> None:
    """on_change: copy widget value into the draft and schedule an autosave."""
    setter(d, st.session_state.get(key))
    mark_dirty(month)


# ---------------------------------------------------------------------------
# Autosave
# ---------------------------------------------------------------------------
def autosave(ledger: Ledger, month: str) -> None:
    dirty = st.session_state.setdefault(_DIRTY, set())
    if month not in dirty:
        return
    d = st.session_state.get(_DRAFTS, {}).get(month)
    if d is None:
        return
    try:
        ledger.save_draft(month, d)
        dirty.discard(month)
        st.session_state.setdefault(_SYNC, {})[month] = (True, datetime.now(timezone.utc))
    except DatabaseUnavailable:
        # Keep the draft in memory and try again on the next change.
        st.session_state.setdefault(_SYNC, {})[month] = (False, datetime.now(timezone.utc))


def sync_status(month: str) -> tuple[str, str]:
    """(text, tone) for the header chip."""
    if month in st.session_state.get(_DIRTY, set()):
        ok_at = st.session_state.get(_SYNC, {}).get(month)
        if ok_at and not ok_at[0]:
            return "Draft not synced: kept in this tab", "warn"
        return "Saving draft…", "mute"
    ok_at = st.session_state.get(_SYNC, {}).get(month)
    if ok_at and ok_at[0]:
        return f"Draft saved {ok_at[1].astimezone().strftime('%H:%M')}", "ok"
    return "Draft auto-saves", "mute"


# ---------------------------------------------------------------------------
# Typed accessors used by the screens
# ---------------------------------------------------------------------------
def readings_pairs(d: dict, previous: dict[str, Decimal]) -> dict[str, tuple[Decimal, Decimal | None]]:
    out = {}
    for f in FLAT_NUMBERS:
        cur = d["readings"].get(f)
        out[f] = (previous[f], None if cur is None else D(cur))
    return out


def water_inputs(d: dict) -> tuple[Decimal, int, Decimal]:
    return D(d.get("manjeera")), int(d.get("tanker_count") or 0), D(d.get("tanker_rate"))


def expense_rows(d: dict) -> list[dict]:
    return [{"name": r.get("name"), "amount": r.get("amount")} for r in d["expenses"]]


def new_expense_row() -> dict:
    return _new_row()
