import datetime
from fpdf import FPDF

def _format_month(month_year: str) -> str:
    """Convert 'YYYY-MM' to 'Month YYYY' format."""
    dt = datetime.datetime.strptime(month_year, "%Y-%m")
    return dt.strftime("%B %Y")

def _format_currency(value: float) -> str:
    """Format monetary value with commas and Rs. prefix."""
    return f"Rs.{int(round(value)):,}"

def _format_num(value: float) -> str:
    """Format monetary value with commas but without Rs. prefix."""
    return f"{int(round(value)):,}"

def _draw_bills_page(
    pdf: FPDF,
    month_year: str,
    cost_per_unit: int,
    total_collection: float,
    meter_readings: list[dict],
    maintenance_amount: float
):
    """Draw the flat-wise bills landscape page."""
    pdf.add_page(orientation="L")
    pdf.set_font("helvetica", "B", 16)
    month_str = _format_month(month_year)
    pdf.cell(0, 10, f"Apartment Water Billing - {month_str}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Table configuration
    col_widths = [25, 70, 75, 55, 52]
    headers = ["Flat No.", "Water Calculation", "Total Bill", "Paid", "Received"]
    
    # Draw Headers
    pdf.set_font("helvetica", "B", 11)
    pdf.set_fill_color(220, 220, 220)
    for w, h in zip(col_widths, headers):
        # We don't change line here; just draw side-by-side
        pdf.cell(w, 10, h, border=1, align="C", fill=True)
    pdf.ln(10)
    
    # Draw Rows
    pdf.set_font("helvetica", "", 10)
    row_height = 11.5
    line_h = 5
    
    for reading in meter_readings:
        flat_number = reading.get("flat_number", "")
        units_used = int(reading.get("units_used", 0))
        water_bill = reading.get("water_bill", 0.0)
        total_bill = reading.get("total_bill", 0.0)
        
        y_start = pdf.get_y()
        x_start = pdf.get_x()
        
        # Draw cells manually
        
        # Col 1: Flat No
        pdf.rect(x_start, y_start, col_widths[0], row_height)
        pdf.set_xy(x_start, y_start + row_height/2 - line_h/2)
        pdf.cell(col_widths[0], line_h, str(flat_number), align='C')
        
        # Col 2: Water Calc
        x = x_start + col_widths[0]
        pdf.rect(x, y_start, col_widths[1], row_height)
        pdf.set_xy(x, y_start + 1)
        pdf.cell(col_widths[1], line_h, f"{units_used} x {cost_per_unit}", align='C')
        pdf.set_xy(x, y_start + line_h + 1)
        pdf.cell(col_widths[1], line_h, f"= {_format_currency(water_bill)}", align='C')
        
        # Col 3: Total Bill
        x += col_widths[1]
        pdf.rect(x, y_start, col_widths[2], row_height)
        pdf.set_xy(x, y_start + 1)
        pdf.cell(col_widths[2], line_h, f"{_format_num(maintenance_amount)} + {_format_num(water_bill)}", align='C')
        pdf.set_xy(x, y_start + line_h + 1)
        pdf.cell(col_widths[2], line_h, f"= {_format_currency(total_bill)}", align='C')
        
        # Col 4: Paid (empty)
        x += col_widths[2]
        pdf.rect(x, y_start, col_widths[3], row_height)
        
        # Col 5: Received (empty)
        x += col_widths[3]
        pdf.rect(x, y_start, col_widths[4], row_height)
        
        # Move pointer to start of next line
        pdf.set_xy(x_start, y_start + row_height)
        
    # Draw Total row
    pdf.set_font("helvetica", "B", 11)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(sum(col_widths), 10, f"Total Collection: {_format_currency(total_collection)}   ", border=1, align="R", fill=True, new_x="LMARGIN", new_y="NEXT")

def _draw_summary_page(
    pdf: FPDF,
    month_year: str,
    opening_balance: float,
    closing_balance: float,
    expenses: list[dict],
    manjeera_bill: float,
    tanker_count: int,
    tanker_rate: float,
    total_water_bill: float,
    cost_per_unit: int,
    total_apartment_units: int,
    total_collection: float,
    total_expenditure: float,
    net_profit_loss: float,
    maintenance_amount: float
):
    """Draw the financial summary portrait page."""
    pdf.add_page(orientation="P")
    pdf.set_font("helvetica", "B", 16)
    month_str = _format_month(month_year)
    pdf.cell(0, 10, f"Financial Summary - {month_str}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    def section_header(title):
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
    
    def line_item(label, value_str):
        pdf.cell(100, 6, label)
        pdf.cell(0, 6, value_str, align="R", new_x="LMARGIN", new_y="NEXT")

    section_header("--- Opening Balance ---")
    line_item("Opening Balance:", _format_currency(opening_balance))
    pdf.ln(3)
    
    section_header("--- Expenses ---")
    for exp in expenses:
        name = exp.get("expense_name", "Unknown")
        amount = exp.get("amount", 0.0)
        line_item(name, _format_currency(amount))
    pdf.ln(3)
    
    section_header("--- Water Bill Breakdown ---")
    line_item("Manjeera Bill:", _format_currency(manjeera_bill))
    line_item(f"Tankers ({tanker_count} @ {_format_currency(tanker_rate)}):", _format_currency(tanker_count * tanker_rate))
    line_item("Total Water Bill:", _format_currency(total_water_bill))
    pdf.ln(3)
    
    section_header("--- Unit Calculation ---")
    line_item("Total Apartment Units:", f"{total_apartment_units} units")
    line_item("Cost Per Unit:", f"{_format_currency(cost_per_unit)}")
    pdf.ln(3)
    
    section_header("--- Summary ---")
    line_item("Total Collection:", _format_currency(total_collection))
    line_item("Total Expenditure:", _format_currency(total_expenditure))
    line_item("Net Profit/Loss:", _format_currency(net_profit_loss))
    pdf.ln(3)
    
    section_header("--- Closing Balance ---")
    pdf.set_font("helvetica", "B", 11)
    line_item("Closing Balance:", _format_currency(closing_balance))


def generate_bills_pdf(
    month_year: str,
    cost_per_unit: int,
    total_collection: float,
    meter_readings: list[dict],
    maintenance_amount: float = 1500.0
) -> bytes:
    """Generate Page 1 only (flat-wise bills) and return as bytes."""
    pdf = FPDF()
    _draw_bills_page(
        pdf=pdf,
        month_year=month_year,
        cost_per_unit=cost_per_unit,
        total_collection=total_collection,
        meter_readings=meter_readings,
        maintenance_amount=maintenance_amount
    )
    return bytes(pdf.output())

def generate_summary_pdf(
    month_year: str,
    opening_balance: float,
    closing_balance: float,
    expenses: list[dict],
    manjeera_bill: float,
    tanker_count: int,
    tanker_rate: float,
    total_water_bill: float,
    cost_per_unit: int,
    total_apartment_units: int,
    total_collection: float,
    total_expenditure: float,
    net_profit_loss: float,
    maintenance_amount: float = 1500.0
) -> bytes:
    """Generate Page 2 only (financial summary) and return as bytes."""
    pdf = FPDF()
    _draw_summary_page(
        pdf=pdf,
        month_year=month_year,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        expenses=expenses,
        manjeera_bill=manjeera_bill,
        tanker_count=tanker_count,
        tanker_rate=tanker_rate,
        total_water_bill=total_water_bill,
        cost_per_unit=cost_per_unit,
        total_apartment_units=total_apartment_units,
        total_collection=total_collection,
        total_expenditure=total_expenditure,
        net_profit_loss=net_profit_loss,
        maintenance_amount=maintenance_amount
    )
    return bytes(pdf.output())

def generate_full_pdf(
    month_year: str,
    opening_balance: float,
    closing_balance: float,
    expenses: list[dict],
    manjeera_bill: float,
    tanker_count: int,
    tanker_rate: float,
    total_water_bill: float,
    cost_per_unit: int,
    total_apartment_units: int,
    total_collection: float,
    total_expenditure: float,
    net_profit_loss: float,
    meter_readings: list[dict],
    maintenance_amount: float = 1500.0
) -> bytes:
    """Generate both pages (Page 1 + Page 2) in a single PDF."""
    pdf = FPDF()
    
    # Draw Page 1
    _draw_bills_page(
        pdf=pdf,
        month_year=month_year,
        cost_per_unit=cost_per_unit,
        total_collection=total_collection,
        meter_readings=meter_readings,
        maintenance_amount=maintenance_amount
    )
    
    # Draw Page 2
    _draw_summary_page(
        pdf=pdf,
        month_year=month_year,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        expenses=expenses,
        manjeera_bill=manjeera_bill,
        tanker_count=tanker_count,
        tanker_rate=tanker_rate,
        total_water_bill=total_water_bill,
        cost_per_unit=cost_per_unit,
        total_apartment_units=total_apartment_units,
        total_collection=total_collection,
        total_expenditure=total_expenditure,
        net_profit_loss=net_profit_loss,
        maintenance_amount=maintenance_amount
    )
    
    return bytes(pdf.output())

def generate_slips_pdf(
    month_year: str,
    cost_per_unit: int,
    meter_readings: list[dict],
    maintenance_amount: float = 1500.0
) -> bytes:
    """Generate a 3x4 grid of cut-out slips for the 12 flats on a single page."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # A4 Portrait: 210mm x 297mm
    # 3 cols x 4 rows
    margin_x = 10
    margin_y = 15
    col_w = (210 - (margin_x * 2)) / 3.0
    row_h = (297 - (margin_y * 2)) / 4.0
    
    month_str = _format_month(month_year)
    
    for i, reading in enumerate(meter_readings):
        col = i % 3
        row = i // 3
        
        x = margin_x + (col * col_w)
        y = margin_y + (row * row_h)
        
        # Draw box border for cutting
        pdf.set_draw_color(150, 150, 150)
        pdf.rect(x, y, col_w, row_h)
        
        # Reset color
        pdf.set_draw_color(0, 0, 0)
        
        # Apartment Name
        pdf.set_font("helvetica", "B", 12)
        pdf.set_xy(x, y + 8)
        pdf.cell(col_w, 6, "Gnapika Residency", align="C")
        
        # Billing Month
        pdf.set_font("helvetica", "", 9)
        pdf.set_xy(x, y + 14)
        pdf.cell(col_w, 5, f"Billing Month: {month_str}", align="C")
        
        # Flat Number
        pdf.set_font("helvetica", "B", 15)
        pdf.set_xy(x, y + 23)
        pdf.cell(col_w, 6, f"Flat {reading.get('flat_number', '')}", align="C")
        
        # Calculations
        units = int(reading.get("units_used", 0))
        water_bill = float(reading.get("water_bill", 0.0))
        
        pdf.set_font("helvetica", "", 10)
        pdf.set_xy(x + 5, y + 36)
        pdf.cell(col_w - 10, 5, f"Water ({units} \u00d7 Rs.{cost_per_unit}):")
        
        pdf.set_font("helvetica", "B", 10)
        pdf.set_xy(x + 5, y + 41)
        pdf.cell(col_w - 10, 5, f"Rs. {int(water_bill)}", align="R")
        
        pdf.set_font("helvetica", "", 10)
        pdf.set_xy(x + 5, y + 48)
        pdf.cell(col_w - 10, 5, "Maintenance:")
        
        pdf.set_font("helvetica", "B", 10)
        pdf.set_xy(x + 5, y + 48)
        pdf.cell(col_w - 10, 5, f"Rs. {int(maintenance_amount)}", align="R")
        
        pdf.line(x + 10, y + 55, x + col_w - 10, y + 55)
        
        # Total Due
        total = float(reading.get("total_bill", 0.0))
        pdf.set_font("helvetica", "B", 12)
        pdf.set_xy(x + 5, y + 57)
        pdf.cell(col_w - 10, 6, f"Grand Total: Rs. {int(total)}", align="C")

    return bytes(pdf.output())

