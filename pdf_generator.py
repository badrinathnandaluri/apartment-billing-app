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
    row_height = 16
    line_h = 7
    
    for reading in meter_readings:
        flat_number = reading.get("flat_number", "")
        units_used = int(reading.get("units_used", 0))
        water_bill = reading.get("water_bill", 0.0)
        total_bill = reading.get("total_bill", 0.0)
        
        y_start = pdf.get_y()
        x_start = pdf.get_x()
        
        # Check for page break (landscape A4 height is ~210, bottom margin ~10)
        if y_start + row_height > 190:
            pdf.add_page(orientation="L")
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
