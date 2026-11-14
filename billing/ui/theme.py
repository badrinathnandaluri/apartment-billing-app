"""Visual system: one stylesheet plus small HTML helpers for cards, pills and KPIs."""

from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>

:root {
  --ink: #0f172a; --ink-2: #334155; --muted: #64748b; --faint: #94a3b8;
  --line: #e2e8f0; --line-2: #eef2f7; --bg: #f5f7fb; --card: #ffffff;
  --brand: #0f4c81; --brand-2: #1d6fb8; --brand-soft: #e8f1fa;
  --ok: #047857; --ok-soft: #e7f6ef; --warn: #b45309; --warn-soft: #fdf3e3;
  --bad: #b91c1c; --bad-soft: #fdecec;
  --radius: 14px; --shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.05);
}

.stApp { background: var(--bg); }
.block-container { padding-top: 1.4rem !important; padding-bottom: 3rem !important; max-width: 1320px; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], .stDeployButton { display: none !important; }
header[data-testid="stHeader"] { background: transparent; height: 0; }
h1, h2, h3 { letter-spacing: -0.01em; color: var(--ink); }

/* ---- cards: st.container(border=True) ---- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) ,
div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: var(--radius) !important;
}
[data-testid="stVerticalBlockBorderWrapper"][data-test-border="true"],
.st-key-card, div[class*="st-key-card"] {
  background: var(--card); border: 1px solid var(--line) !important;
  border-radius: var(--radius) !important; box-shadow: var(--shadow);
}
div[class*="st-key-card"] { padding: 1.1rem 1.25rem 1.2rem; }

/* ---- tabs as a segmented navigation bar ---- */
.stTabs [role="tablist"] {
  gap: 4px; background: var(--card); padding: 5px; border-radius: 12px; border: 1px solid var(--line);
  box-shadow: var(--shadow); width: fit-content; max-width: 100%; overflow-x: auto;
}
.stTabs [data-testid="stTab"] {
  height: 38px; padding: 0 18px; border-radius: 9px; color: var(--muted); font-weight: 600;
  display: flex; align-items: center; white-space: nowrap; border: none !important; background: transparent;
}
.stTabs [data-testid="stTab"] p { font-size: .9rem; font-weight: 600; }
.stTabs [data-testid="stTab"]:hover { color: var(--ink); background: var(--line-2); }
.stTabs [data-testid="stTab"][aria-selected="true"] { background: var(--brand); color: #fff; }
.stTabs [data-testid="stTab"][aria-selected="true"] p { color: #fff; }
.stTabs [class*="SelectionIndicator"] { display: none !important; }
.stTabs [role="tabpanel"] { padding-top: 1.1rem; }

/* ---- inputs ---- */
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {
  font-variant-numeric: tabular-nums; font-weight: 500;
}
[data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] { display: none !important; }
[data-baseweb="input"] { border-radius: 9px !important; }
label[data-testid="stWidgetLabel"] p { font-size: .8rem; font-weight: 600; color: var(--ink-2); }

/* ---- buttons ---- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 10px; font-weight: 600; min-height: 42px; transition: all .15s ease;
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: var(--brand); border-color: var(--brand);
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover { background: var(--brand-2); border-color: var(--brand-2); }

/* ---- app header ---- */
.ab-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; margin-bottom: .2rem; }
.ab-brand { display:flex; align-items:center; gap:.8rem; }
.ab-logo { width:42px; height:42px; border-radius:12px; background: linear-gradient(135deg, var(--brand), #2a8fd8);
  display:grid; place-items:center; color:#fff; font-weight:700; font-size:1.05rem; box-shadow: 0 6px 16px rgba(15,76,129,.25); }
.ab-title { font-size:1.2rem; font-weight:700; color:var(--ink); line-height:1.15; }
.ab-sub { font-size:.82rem; color:var(--muted); }

/* ---- pills ---- */
.pill { display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px;
  font-size:.75rem; font-weight:600; border:1px solid transparent; white-space:nowrap; }
.pill::before { content:""; width:6px; height:6px; border-radius:50%; background: currentColor; }
.pill.ok { color: var(--ok); background: var(--ok-soft); }
.pill.warn { color: var(--warn); background: var(--warn-soft); }
.pill.bad { color: var(--bad); background: var(--bad-soft); }
.pill.info { color: var(--brand); background: var(--brand-soft); }
.pill.mute { color: var(--muted); background: var(--line-2); }

/* ---- KPI tiles ---- */
.kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.kpi { background: var(--card); border:1px solid var(--line); border-radius: var(--radius); padding: 14px 16px; box-shadow: var(--shadow); }
.kpi .k { font-size:.74rem; font-weight:600; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.kpi .v { font-size:1.55rem; font-weight:700; color: var(--ink); margin-top: 4px; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.kpi .s { font-size:.78rem; color: var(--muted); margin-top: 2px; }
.kpi .s.up { color: var(--ok); } .kpi .s.down { color: var(--bad); }
.kpi.hero { background: linear-gradient(135deg, #0f4c81, #1d6fb8); border: none; }
.kpi.hero .k, .kpi.hero .s { color: rgba(255,255,255,.78); } .kpi.hero .v { color: #fff; }

/* ---- section titles inside cards ---- */
.sec { display:flex; align-items:baseline; justify-content:space-between; gap: .5rem; margin-bottom: .35rem; }
.sec .t { font-weight:700; font-size: 1rem; color: var(--ink); }
.sec .d { font-size:.8rem; color: var(--muted); }

/* ---- meter grid ---- */
.mhead { font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color: var(--faint); padding: 0 2px; }
.flat { display:inline-grid; place-items:center; min-width: 52px; height: 34px; border-radius: 9px;
  background: var(--brand-soft); color: var(--brand); font-weight: 700; font-variant-numeric: tabular-nums; }
.locked { display:flex; align-items:center; gap:6px; height: 38px; padding: 0 10px; border-radius: 9px;
  background: var(--line-2); color: var(--ink-2); font-variant-numeric: tabular-nums; font-weight: 500; }
.locked svg { flex: none; opacity: .55; }
.num { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ink); line-height: 38px; white-space: nowrap; }
.num.dim { color: var(--faint); font-weight: 500; }
.num.bad { color: var(--bad); }
.num small { color: var(--muted); font-weight: 500; }
.floor { font-size:.72rem; font-weight:700; color: var(--muted); text-transform: uppercase; letter-spacing:.06em; margin: .4rem 0 .1rem; }

/* rows of the meter grid: keep markdown cells the same height as inputs */
div[class*="st-key-card_meters"] [data-testid="stHorizontalBlock"] { align-items: center; }
div[class*="st-key-card_meters"] [data-testid="stMarkdownContainer"],
div[class*="st-key-card_meters"] [data-testid="stMarkdownContainer"] > div,
div[class*="st-key-card_meters"] [data-testid="stMarkdownContainer"] p { margin: 0 !important; }
div[class*="st-key-card_meters"] [data-testid="stHorizontalBlock"] { gap: .5rem; }
div[class*="st-key-card_meters"] [data-testid="stNumberInput"] input { padding-left: 10px; padding-right: 4px; }

/* ---- key/value rows ---- */
.kv { display:flex; justify-content:space-between; gap: 1rem; padding: 7px 0; border-bottom: 1px dashed var(--line); font-size: .92rem; }
.kv:last-child { border-bottom: none; }
.kv .l { color: var(--ink-2); } .kv .l small { color: var(--muted); margin-left: 6px; }
.kv .r { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ink); }
.kv.total { border-top: 1px solid var(--line); border-bottom: none; margin-top: 4px; padding-top: 10px; }
.kv.total .l, .kv.total .r { font-weight: 700; font-size: 1rem; }
.kv.grand { background: var(--brand-soft); border-radius: 10px; padding: 10px 12px; border: none; margin: 8px 0 14px; }
.kv.grand .l, .kv.grand .r { color: var(--brand); font-weight: 700; font-size: 1.05rem; }

.saved-note { display:flex; align-items:center; gap:8px; padding: 10px 12px; border-radius: 10px; background: var(--ok-soft);
  color: var(--ok); font-weight: 600; font-size: .9rem; margin-bottom: 12px; }

/* ---- checklist ---- */
.check { display:flex; gap:10px; align-items:flex-start; padding: 6px 0; font-size: .9rem; color: var(--ink-2); }
.check .i { width:20px; height:20px; border-radius: 50%; display:grid; place-items:center; flex:none; font-size: .7rem; font-weight: 700; margin-top: 1px; }
.check .i.ok { background: var(--ok-soft); color: var(--ok); } .check .i.no { background: var(--bad-soft); color: var(--bad); }

/* ---- step header ---- */
.step { display:flex; gap: 12px; align-items: center; margin-bottom: .5rem; }
.step .n { width: 30px; height: 30px; border-radius: 50%; display:grid; place-items:center; font-weight: 700; font-size: .85rem;
  background: var(--line-2); color: var(--muted); flex: none; }
.step .n.on { background: var(--brand); color: #fff; } .step .n.done { background: var(--ok); color: #fff; }
.step .t { font-weight: 700; color: var(--ink); } .step .d { font-size: .82rem; color: var(--muted); }

/* ---- empty + error states ---- */
.empty { text-align:center; padding: 2.5rem 1rem; color: var(--muted); }
.empty .t { font-weight:700; color: var(--ink); font-size: 1.05rem; margin-bottom: .3rem; }
.err { border-left: 4px solid var(--bad); background: var(--card); border-radius: 12px; padding: 1rem 1.2rem; box-shadow: var(--shadow); }
.err .t { font-weight: 700; color: var(--bad); margin-bottom: .25rem; }

/* ---- login ---- */
.login-hero { text-align:center; margin: 6vh 0 1.2rem; }
.login-hero .ab-logo { margin: 0 auto 14px; width: 54px; height: 54px; font-size: 1.3rem; border-radius: 16px; }
.login-hero h2 { margin: 0; font-size: 1.45rem; }
.login-hero p { color: var(--muted); margin: .25rem 0 0; font-size: .9rem; }

@media (max-width: 640px) {
  .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
  .stTabs [data-baseweb="tab"] { padding: 0 10px; font-size: .82rem; }
  .kpi .v { font-size: 1.3rem; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .kpi.hero { grid-column: 1 / -1; }
  .flat { min-width: 40px; }
  .locked svg { display: none; }
  .locked { padding: 0 6px; }
  /* keep grid rows on one line on phones instead of stacking each cell */
  div[class*="st-key-card_meters"] [data-testid="stHorizontalBlock"],
  div[class*="st-key-card_expenses"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .35rem; }
  div[class*="st-key-card_meters"] [data-testid="stColumn"],
  div[class*="st-key-card_expenses"] [data-testid="stColumn"] { min-width: 0 !important; }
  /* the Water column is derivable (units x rate); drop it on phones to make room */
  div[class*="st-key-card_meters"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(5) { display: none; }
  div[class*="st-key-card"] { padding: .9rem .8rem 1rem; }
  .num { font-size: .9rem; }
}
</style>
"""

LOCK_SVG = ('<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">'
            '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>')


def apply() -> None:
    st.html(CSS)


def esc(s: object) -> str:
    return html.escape(str(s))


def md(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def pill(text: str, tone: str = "info") -> str:
    return f'<span class="pill {tone}">{esc(text)}</span>'


def kpi(label: str, value: str, sub: str = "", tone: str = "", hero: bool = False) -> str:
    sub_html = f'<div class="s {tone}">{esc(sub)}</div>' if sub else ""
    return f'<div class="kpi{" hero" if hero else ""}"><div class="k">{esc(label)}</div><div class="v">{esc(value)}</div>{sub_html}</div>'


def kpi_row(*tiles: str) -> None:
    md(f'<div class="kpis">{"".join(tiles)}</div>')


def section(title: str, desc: str = "") -> None:
    md(f'<div class="sec"><span class="t">{esc(title)}</span><span class="d">{esc(desc)}</span></div>')


def kv(label: str, value: str, note: str = "", cls: str = "") -> str:
    n = f"<small>{esc(note)}</small>" if note else ""
    return f'<div class="kv {cls}"><span class="l">{esc(label)}{n}</span><span class="r">{esc(value)}</span></div>'


def kv_block(*rows: str) -> None:
    md("".join(rows))


def check(ok: bool, text: str) -> str:
    return f'<div class="check"><span class="i {"ok" if ok else "no"}">{"✓" if ok else "!"}</span><span>{esc(text)}</span></div>'


def step(n: int, title: str, desc: str, state: str) -> None:
    label = "✓" if state == "done" else str(n)
    md(f'<div class="step"><span class="n {state}">{label}</span><div><div class="t">{esc(title)}</div>'
       f'<div class="d">{esc(desc)}</div></div></div>')


def empty(title: str, body: str) -> None:
    md(f'<div class="empty"><div class="t">{esc(title)}</div><div>{esc(body)}</div></div>')


def card(key: str):
    """A white card. Keys must start with 'card' (styled via the st-key-card* class)."""
    return st.container(key=f"card_{key}")
