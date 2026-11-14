"""Printable documents.

Page 1  Bills sheet (portrait): one row per flat, with Paid/Received columns for
        signatures. Geometry matches the tuned original so all 12 rows plus the
        total fit on one A4 page.
Page 2  Balance sheet (portrait): opening balance, collections, expenses, water-unit
        math and the closing balance that carries forward.
Slips   12 cut-out slips (3 x 4) for handing to each flat.

Core PDF fonts are Latin-1 only, so amounts use "Rs." rather than the rupee sign.
"""

from __future__ import annotations

from datetime import datetime

from fpdf import FPDF

from billing.config import BUILDING_NAME
from billing.domain import BillResult, CloseResult, fmt_money, fmt_units

INK = (31, 41, 55)
MUTED = (107, 114, 128)
RULE = (209, 213, 219)
BAND = (238, 242, 247)
ACCENT = (15, 76, 129)


def month_label(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def rs(value) -> str:
    return fmt_money(value, "Rs.")


def _new_pdf(title: str) -> FPDF:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(False)
    pdf.set_title(title)
    pdf.set_author(BUILDING_NAME)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*INK)
    return pdf


def _heading(pdf: FPDF, title: str, subtitle: str) -> None:
    pdf.set_font("helvetica", "B", 15)
    pdf.cell(0, 8, title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)
    pdf.ln(3)


# ---------------------------------------------------------------------------
# Page 1: bills sheet
# ---------------------------------------------------------------------------
def draw_bills_page(pdf: FPDF, month: str, bills: BillResult) -> None:
    pdf.add_page(orientation="P")
    _heading(
        pdf,
        f"{BUILDING_NAME}  |  Water & Maintenance Bill  |  {month_label(month)}",
        f"Cost per unit {rs(bills.cost_per_unit)}   |   Maintenance {rs(bills.maintenance)} per flat   |   "
        f"Total units {fmt_units(bills.total_units)}   |   Bills rounded up to the next Rs.5",
    )

    widths = [18, 55, 55, 31, 31]
    headers = ["Flat No.", "Water Calculation", "Total Bill", "Paid", "Received"]
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(*BAND)
    for w, h in zip(widths, headers):
        pdf.cell(w, 10, h, border=1, align="C", fill=True)
    pdf.ln(10)

    row_h, line_h = 18.5, 7
    for ln in bills.lines:
        x0, y0 = pdf.get_x(), pdf.get_y()
        x = x0
        for w in widths:
            pdf.rect(x, y0, w, row_h)
            x += w

        pdf.set_font("helvetica", "B", 12)
        pdf.set_xy(x0, y0 + row_h / 2 - line_h / 2)
        pdf.cell(widths[0], line_h, ln.flat, align="C")

        x = x0 + widths[0]
        pdf.set_font("helvetica", "", 10)
        pdf.set_xy(x, y0 + 1.5)
        pdf.cell(widths[1], line_h, f"{fmt_units(ln.units)} units x {rs(bills.cost_per_unit)}", align="C")
        pdf.set_xy(x, y0 + line_h + 2)
        pdf.cell(widths[1], line_h, f"= {rs(ln.water_bill)}", align="C")

        x += widths[1]
        pdf.set_xy(x, y0 + 1.5)
        pdf.cell(widths[2], line_h, f"{rs(bills.maintenance)} + {rs(ln.water_bill)}", align="C")
        pdf.set_font("helvetica", "B", 11)
        pdf.set_xy(x, y0 + line_h + 2)
        pdf.cell(widths[2], line_h, f"= {rs(ln.total_bill)}", align="C")

        pdf.set_xy(x0, y0 + row_h)

    pdf.set_font("helvetica", "B", 11)
    pdf.set_fill_color(*BAND)
    pdf.cell(sum(widths), 10, f"Total Collection: {rs(bills.total_collection)}   ",
             border=1, align="R", fill=True, new_x="LMARGIN", new_y="NEXT")


# ---------------------------------------------------------------------------
# Page 2: balance sheet
# ---------------------------------------------------------------------------
def draw_summary_page(pdf: FPDF, month: str, bills: BillResult, close: CloseResult) -> None:
    pdf.add_page(orientation="P")
    _heading(pdf, f"Balance Sheet  |  {month_label(month)}", BUILDING_NAME)

    full_w = pdf.w - pdf.l_margin - pdf.r_margin

    def section(title: str) -> None:
        pdf.ln(2)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(*ACCENT)
        pdf.cell(0, 6, title.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*INK)
        pdf.set_draw_color(*RULE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + full_w, pdf.get_y())
        pdf.set_draw_color(*INK)
        pdf.ln(1)

    def row(label: str, value: str, bold: bool = False, note: str = "") -> None:
        pdf.set_font("helvetica", "B" if bold else "", 10.5)
        pdf.cell(full_w * 0.45, 7, label)
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(full_w * 0.30, 7, note)
        pdf.set_text_color(*INK)
        pdf.set_font("helvetica", "B" if bold else "", 10.5)
        pdf.cell(0, 7, value, align="R", new_x="LMARGIN", new_y="NEXT")

    def total_band(label: str, value: str) -> None:
        pdf.set_fill_color(*BAND)
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(full_w * 0.6, 9, f"  {label}", fill=True)
        pdf.cell(0, 9, f"{value}  ", align="R", fill=True, new_x="LMARGIN", new_y="NEXT")

    section("Opening balance")
    row("Brought forward from last month", rs(close.opening_balance), bold=True)

    section("Collections")
    row("Water bills + maintenance (12 flats)", rs(close.total_collection), bold=True,
        note=f"maintenance {rs(bills.maintenance)} x {len(bills.lines)}")

    section("Water cost")
    row("Manjeera (municipal) bill", rs(bills.manjeera_bill))
    row("Tankers", rs(bills.tanker_total), note=f"{bills.tanker_count} x {rs(bills.tanker_rate)}")
    row("Total water cost", rs(bills.total_water_bill), bold=True)

    section("Water unit calculation")
    row("Total units used (all flats)", f"{fmt_units(bills.total_units)} units")
    row("Total water cost / total units", rs(bills.cost_per_unit), bold=True,
        note=f"{rs(bills.total_water_bill)} / {fmt_units(bills.total_units)}, rounded up")

    section("Other expenses")
    if close.expenses:
        for e in close.expenses:
            row(e.name, rs(e.amount))
    else:
        row("None", rs(0))
    row("Total other expenses", rs(close.total_variable_expenses), bold=True)

    section("Summary")
    row("Total collection", rs(close.total_collection))
    row("Total expenditure (water + other)", rs(close.total_expenditure))
    row("Surplus" if close.net >= 0 else "Deficit", rs(close.net), bold=True)
    pdf.ln(3)
    total_band("Closing balance (carried to next month)", rs(close.closing_balance))

    pdf.set_y(-18)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, f"Closing balance = opening {rs(close.opening_balance)} + collection {rs(close.total_collection)}"
                   f" - expenditure {rs(close.total_expenditure)}", align="C")
    pdf.set_text_color(*INK)


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------
def _bytes(pdf: FPDF) -> bytes:
    return bytes(pdf.output())


def bills_pdf(month: str, bills: BillResult) -> bytes:
    pdf = _new_pdf(f"Bills {month}")
    draw_bills_page(pdf, month, bills)
    return _bytes(pdf)


def full_pdf(month: str, bills: BillResult, close: CloseResult) -> bytes:
    """The 2-page monthly report: bills sheet + balance sheet."""
    pdf = _new_pdf(f"Monthly report {month}")
    draw_bills_page(pdf, month, bills)
    draw_summary_page(pdf, month, bills, close)
    return _bytes(pdf)


def slips_pdf(month: str, bills: BillResult) -> bytes:
    pdf = _new_pdf(f"Slips {month}")
    pdf.add_page()
    margin_x, margin_y = 10, 15
    col_w = (210 - 2 * margin_x) / 3
    row_h = (297 - 2 * margin_y) / 4

    for i, ln in enumerate(bills.lines):
        x = margin_x + (i % 3) * col_w
        y = margin_y + (i // 3) * row_h

        pdf.set_draw_color(*RULE)
        pdf.set_dash_pattern(dash=1.5, gap=1.5)
        pdf.rect(x, y, col_w, row_h)
        pdf.set_dash_pattern()
        pdf.set_draw_color(*INK)

        pdf.set_font("helvetica", "B", 12)
        pdf.set_xy(x, y + 8)
        pdf.cell(col_w, 6, BUILDING_NAME, align="C")
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x, y + 14)
        pdf.cell(col_w, 5, f"Billing month: {month_label(month)}", align="C")
        pdf.set_text_color(*INK)

        pdf.set_font("helvetica", "B", 16)
        pdf.set_xy(x, y + 22)
        pdf.cell(col_w, 7, f"Flat {ln.flat}", align="C")

        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x + 5, y + 31)
        pdf.cell(col_w - 10, 4, f"Meter {fmt_units(ln.previous)} -> {fmt_units(ln.current)}", align="C")
        pdf.set_text_color(*INK)

        def pair(label: str, value: str, top: float) -> None:
            pdf.set_font("helvetica", "", 10)
            pdf.set_xy(x + 5, y + top)
            pdf.cell(col_w - 10, 5, label)
            pdf.set_font("helvetica", "B", 10)
            pdf.set_xy(x + 5, y + top)
            pdf.cell(col_w - 10, 5, value, align="R")

        pair(f"Water ({fmt_units(ln.units)} x {rs(bills.cost_per_unit)})", rs(ln.water_bill), 38)
        pair("Maintenance", rs(bills.maintenance), 45)
        pdf.line(x + 8, y + 53, x + col_w - 8, y + 53)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_xy(x + 5, y + 56)
        pdf.cell(col_w - 10, 7, f"Total: {rs(ln.total_bill)}", align="C")
    return _bytes(pdf)
