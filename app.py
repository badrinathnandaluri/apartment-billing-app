"""
app.py
======
Main Streamlit application for Apartment Water Billing & Management.
Includes Google OAuth protection and Supabase connectivity.
"""

import calendar
from datetime import datetime

import streamlit as st

import database as db
from calculations import (
    FLAT_NUMBERS,
    MAINTENANCE_AMOUNT,
    BillCalculation,
    ExpenseCalculation,
)
from pdf_generator import (
    generate_bills_pdf, 
    generate_summary_pdf, 
    generate_full_pdf, 
    generate_slips_pdf
)

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Apartment Water Billing",
    page_icon="🏢",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Initialize database
# ---------------------------------------------------------------------------
try:
    db.init_db()
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_month(month_year: str) -> str:
    if month_year == "INITIAL":
        return "Initial Setup"
    try:
        dt = datetime.strptime(month_year, "%Y-%m")
        return dt.strftime("%B %Y")
    except ValueError:
        return month_year

def status_badge(status: str) -> str:
    if status == "closed":
        return "✅ Closed"
    return "🔓 Open"


# ===================================================================
# PAGE: Initial Setup
# ===================================================================
def page_initial_setup():
    st.title("🏢 First-Time Setup")
    st.info("Welcome! Enter any existing records you may have. Use 0 if starting fresh.")

    with st.form("initial_setup_form"):
        st.subheader("Opening Balance")
        opening_balance = st.number_input(
            "Latest Closing Balance (₹) — use 0 if starting fresh",
            min_value=0.0, value=0.0, step=100.0, format="%.2f",
        )

        st.subheader("Previous Meter Readings")
        st.caption("Enter last recorded readings for each flat (0 if none).")

        readings: dict[str, float] = {}
        for floor in range(1, 5):
            cols = st.columns(3)
            for unit in range(1, 4):
                flat = f"{floor}0{unit}"
                with cols[unit - 1]:
                    readings[flat] = st.number_input(
                        f"Flat {flat}", min_value=0.0, value=0.0, step=1.0,
                        format="%.1f", key=f"init_{flat}",
                    )

        if st.form_submit_button("✅ Save Initial Setup", type="primary"):
            db.setup_initial_readings(readings, opening_balance)
            st.success("Initial setup saved!")
            st.rerun()

# ===================================================================
# PAGE: Water Bills (Step 1)
# ===================================================================
def page_water_bills():
    st.title("🧾 Water Bills — Meter Readings & Calculation")

    open_month = db.has_open_month()
    today = datetime.today()
    col_m, col_y = st.columns(2)
    with col_m:
        month = st.selectbox("Month", range(1, 13), index=today.month - 1, format_func=lambda m: calendar.month_name[m])
    with col_y:
        year = st.number_input("Year", min_value=2020, max_value=2100, value=today.year)

    month_year = f"{year:04d}-{month:02d}"
    month_status = db.get_month_status(month_year)

    if open_month and open_month != month_year:
        st.error(f"⚠️ **{fmt_month(open_month)}** is still open. Please close it via the **Monthly Expenses** tab before entering bills for a new month.")
        return

    if month_status == "closed":
        st.warning(f"**{fmt_month(month_year)}** is already closed. Go to **View Past Records** to see its data or unlock it.")
        return

    if month_status == "open":
        st.info(f"📋 Bills for **{fmt_month(month_year)}** already saved. You can recalculate and overwrite.")

    st.subheader("🚰 Water Bill")
    c1, c2, c3 = st.columns(3)
    with c1:
        manjeera_bill = st.number_input("Manjeera (Municipal) Bill (₹)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
    with c2:
        tanker_count = st.number_input("Number of Tankers", min_value=0, value=0, step=1)
    with c3:
        tanker_rate = st.number_input("Cost per Tanker (₹)", min_value=0.0, value=0.0, step=50.0, format="%.2f")

    tanker_total = tanker_count * tanker_rate
    total_water = manjeera_bill + tanker_total
    if total_water > 0:
        st.caption(f"Total Water Bill: Rs.{manjeera_bill:,.0f} + ({tanker_count} × Rs.{tanker_rate:,.0f}) = **Rs.{total_water:,.0f}**")

    st.subheader("📊 Meter Readings")
    prev_readings = db.get_previous_readings()
    existing_readings = {}
    if month_status == "open":
        for r in db.get_meter_readings(month_year):
            existing_readings[r["flat_number"]] = r["current_reading"]

    st.caption("Previous readings auto-populated. Enter current readings below.")
    readings_data = {}

    for floor in range(1, 5):
        cols = st.columns(3)
        for unit in range(1, 4):
            flat = f"{floor}0{unit}"
            prev = prev_readings.get(flat, 0.0)
            default_current = existing_readings.get(flat, prev)

            with cols[unit - 1]:
                st.markdown(f"**Flat {flat}** _(prev: {prev:.0f})_")
                current = st.number_input(
                    f"Current — {flat}", min_value=0.0, value=float(default_current),
                    step=1.0, format="%.1f", key=f"reading_{flat}", label_visibility="collapsed",
                )
                readings_data[flat] = (prev, current)

    st.markdown("---")
    if st.button("🔄 Calculate Bills", type="primary", use_container_width=True):
        errors = []
        for flat in FLAT_NUMBERS:
            prev_r, curr_r = readings_data[flat]
            if curr_r < prev_r:
                errors.append(f"Flat {flat}: Current ({curr_r}) < Previous ({prev_r})")
        if total_water <= 0:
            errors.append("Total water bill is zero. Enter Manjeera bill or tanker details.")
        total_units = sum(readings_data[f][1] - readings_data[f][0] for f in FLAT_NUMBERS)
        if total_units <= 0:
            errors.append("Total units is zero. Check meter readings.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            calc = BillCalculation(manjeera_bill=manjeera_bill, tanker_count=tanker_count, tanker_rate=tanker_rate)
            calc.set_readings(readings_data)
            calc.compute()
            st.session_state.bill_calc = calc
            st.session_state.bill_month = month_year

    if "bill_calc" in st.session_state and st.session_state.get("bill_month") == month_year:
        calc: BillCalculation = st.session_state.bill_calc
        st.markdown("### Results")
        m1, m2, m3 = st.columns(3)
        m1.metric("Cost per Unit", f"Rs.{calc.cost_per_unit}")
        m2.metric("Total Units", f"{int(calc.total_apartment_units)}")
        m3.metric("Total Collection", f"Rs.{calc.total_collection:,.0f}")

        table_data = [
            {
                "Flat": fb.flat_number, "Units": f"{fb.units_used:.0f}",
                "Water Calc": f"{fb.units_used:.0f} × {calc.cost_per_unit} = Rs.{fb.water_bill:,.0f}",
                "Total Bill": f"1500 + {fb.water_bill:,.0f} = Rs.{fb.total_bill:,.0f}",
            } for fb in calc.flat_bills
        ]
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        col_save, col_pdf, col_slips = st.columns(3)
        with col_save:
            if st.button("💾 Save Bills", type="primary", use_container_width=True):
                save_data = calc.to_save_dict()
                db.save_bill_data(month_year=month_year, **save_data)
                st.success(f"✅ Bills for {fmt_month(month_year)} saved!")
                st.caption("Now go to **Monthly Expenses** when ready to close the month.")
        with col_pdf:
            pdf_bytes = generate_bills_pdf(
                month_year=month_year, cost_per_unit=calc.cost_per_unit,
                total_collection=calc.total_collection, meter_readings=calc.to_save_dict()["meter_readings"],
                maintenance_amount=MAINTENANCE_AMOUNT,
            )
            st.download_button("📄 Download Bills PDF", data=pdf_bytes, file_name=f"bills_{month_year}.pdf", mime="application/pdf", use_container_width=True)
        with col_slips:
            slips_bytes = generate_slips_pdf(
                month_year=month_year, cost_per_unit=calc.cost_per_unit,
                meter_readings=calc.to_save_dict()["meter_readings"],
                maintenance_amount=MAINTENANCE_AMOUNT,
            )
            st.download_button("✂️ Distribution Slips", data=slips_bytes, file_name=f"slips_{month_year}.pdf", mime="application/pdf", use_container_width=True)

# ===================================================================
# PAGE: Monthly Expenses (Step 2 — Close Month)
# ===================================================================
def page_expenses():
    st.title("💰 Monthly Expenses")

    open_months = db.get_open_months()
    if not open_months:
        st.info("No open months available. Enter water bills first via the **Water Bills** tab.")
        return

    selected_month = st.selectbox("Select month", open_months, format_func=fmt_month)
    if not selected_month:
        return

    record = db.get_monthly_record(selected_month)
    if not record:
        st.error("No bill data found for this month.")
        return

    st.markdown(f"### 📋 {fmt_month(selected_month)} — Bill Summary")
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Water Bill", f"Rs.{record['total_water_bill']:,.0f}")
    mc2.metric("Total Collection", f"Rs.{record['total_collection']:,.0f}")
    mc3.metric("Cost per Unit", f"Rs.{record['cost_per_unit']}")
    st.markdown("---")

    st.subheader("Opening Balance")
    last_closed_balance = db.get_last_closed_balance()
    existing_expenses = db.get_expenses(selected_month)

    if last_closed_balance > 0:
        st.metric("Opening Balance (from last closed month)", f"Rs.{last_closed_balance:,.2f}")
        opening_balance = last_closed_balance
    else:
        opening_balance = st.number_input("Opening Balance (₹)", min_value=0.0, value=0.0, step=100.0, format="%.2f")

    st.subheader("💰 Variable Expenses")
    st.info("💡 You can save expenses as a draft multiple times throughout the month. When ready, finalize the month to lock it.")

    default_expenses = ["Watchman Salary", "Garbage Collection", "Society Security", "Electricity Bill", "Lift Service"]
    if "exp_list" not in st.session_state or st.session_state.get("exp_month") != selected_month:
        if existing_expenses:
            st.session_state.exp_list = [{"expense_name": e["expense_name"], "amount": e["amount"]} for e in existing_expenses]
        else:
            st.session_state.exp_list = [{"expense_name": name, "amount": 0.0} for name in default_expenses]
        st.session_state.exp_month = selected_month

    expenses_to_remove = []
    for i, exp in enumerate(st.session_state.exp_list):
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            st.session_state.exp_list[i]["expense_name"] = st.text_input(
                "Expense Name" if i == 0 else f"Expense {i+1}",
                value=exp["expense_name"], key=f"exp_name_{i}", label_visibility="visible" if i == 0 else "collapsed",
            )
        with c2:
            st.session_state.exp_list[i]["amount"] = st.number_input(
                "Amount (₹)" if i == 0 else f"Amount {i+1}",
                min_value=0.0, value=exp["amount"], step=100.0, format="%.2f",
                key=f"exp_amt_{i}", label_visibility="visible" if i == 0 else "collapsed",
            )
        with c3:
            if i > 0:
                if st.button("❌", key=f"exp_del_{i}"):
                    expenses_to_remove.append(i)

    for idx in sorted(expenses_to_remove, reverse=True):
        st.session_state.exp_list.pop(idx)
        st.rerun()

    if st.button("➕ Add Another Expense"):
        st.session_state.exp_list.append({"expense_name": "", "amount": 0.0})
        st.rerun()

    valid_expenses = [e for e in st.session_state.exp_list if e["expense_name"].strip() and e["amount"] > 0]
    total_var_exp = sum(e["amount"] for e in valid_expenses)
    st.caption(f"Total Variable Expenses so far: **Rs.{total_var_exp:,.0f}**")
    st.markdown("---")

    col_draft, col_calc = st.columns(2)
    with col_draft:
        if st.button("💾 Save Draft (Don't Close Month)", use_container_width=True):
            db.save_expenses_draft(selected_month, valid_expenses)
            st.success("Draft saved successfully! You can come back and edit anytime.")
            
    with col_calc:
        if st.button("🔄 Preview Final Calculation", type="primary", use_container_width=True):
            exp_calc = ExpenseCalculation(
                opening_balance=opening_balance, expenses=valid_expenses,
                total_water_bill=record["total_water_bill"], total_collection=record["total_collection"],
            )
            exp_calc.compute()
            st.session_state.exp_calc = exp_calc
            st.session_state.exp_calc_month = selected_month

    if "exp_calc" in st.session_state and st.session_state.get("exp_calc_month") == selected_month:
        exp_calc = st.session_state.exp_calc
        st.markdown("### Final Summary Preview")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Expenditure", f"Rs.{exp_calc.total_expenditure:,.0f}")
        m2.metric("Total Collection", f"Rs.{exp_calc.total_collection:,.0f}")
        m3.metric("Net", f"Rs.{exp_calc.net_profit_loss:,.0f}")
        m4.metric("Closing Balance", f"Rs.{exp_calc.closing_balance:,.0f}", delta=f"Rs.{exp_calc.net_profit_loss:,.0f}")

        st.warning("⚠️ Finalizing will lock the month and generate the final closing balance.")
        if st.button("🔒 Finalize & Close Month", type="primary"):
            db.close_month(month_year=selected_month, **exp_calc.to_save_dict())
            st.success(f"✅ {fmt_month(selected_month)} is now closed!")
            st.balloons()
            for key in ["exp_calc", "exp_calc_month", "exp_list", "exp_month"]:
                st.session_state.pop(key, None)
            st.rerun()

# ===================================================================
# PAGE: View Past Records
# ===================================================================
def page_view_records():
    st.title("📊 Past Records")

    all_months = db.get_all_months()
    if not all_months:
        st.info("No billing records found yet.")
        return

    selected_month = st.selectbox("Select Month", all_months, format_func=fmt_month)
    if not selected_month:
        return

    record = db.get_monthly_record(selected_month)
    expenses = db.get_expenses(selected_month)
    readings = db.get_meter_readings(selected_month)
    month_status = db.get_month_status(selected_month)

    if not record:
        st.error("Record not found.")
        return

    st.markdown(f"### {fmt_month(selected_month)} — {status_badge(month_status or 'open')}")

    if month_status == "closed":
        with st.expander("🔓 Need to make corrections? Unlock month"):
            st.warning("⚠️ Unlocking will allow you to edit expenses again. Proceed with caution.")
            
            admin_pwd = st.secrets.get("admin_password", "admin")
            unlock_pwd = st.text_input("Enter Admin Password", type="password", key=f"unlock_{selected_month}")
            if st.button("Confirm Unlock"):
                if unlock_pwd == admin_pwd:
                    db.unlock_month(selected_month)
                    st.success(f"{fmt_month(selected_month)} unlocked successfully!")
                    st.rerun()
                elif unlock_pwd:
                    st.error("Incorrect password.")

    st.markdown("#### 🚰 Water Details")
    wc1, wc2, wc3, wc4 = st.columns(4)
    wc1.metric("Manjeera Bill", f"Rs.{record['manjeera_bill']:,.0f}")
    wc2.metric("Tankers", f"{record['tanker_count']} × Rs.{record['tanker_rate']:,.0f}")
    wc3.metric("Total Water Bill", f"Rs.{record['total_water_bill']:,.0f}")
    wc4.metric("Cost per Unit", f"Rs.{record['cost_per_unit']}")

    st.markdown("#### 📊 Flat-wise Bills")
    if readings:
        table_data = [
            {
                "Flat": r["flat_number"], "Previous": f"{r['previous_reading']:.0f}",
                "Current": f"{r['current_reading']:.0f}", "Units": f"{r['units_used']:.0f}",
                "Water Bill": f"Rs.{r['water_bill']:,.0f}", "Total Bill": f"Rs.{r['total_bill']:,.0f}"
            } for r in readings
        ]
        st.dataframe(table_data, use_container_width=True, hide_index=True)

    if month_status == "closed":
        st.markdown("#### 💰 Financial Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Opening Balance", f"Rs.{record['opening_balance']:,.0f}")
        m2.metric("Total Expenditure", f"Rs.{record['total_expenditure']:,.0f}")
        m3.metric("Total Collection", f"Rs.{record['total_collection']:,.0f}")
        m4.metric("Closing Balance", f"Rs.{record['closing_balance']:,.0f}", delta=f"Rs.{record['net_profit_loss']:,.0f}")

        if expenses:
            st.markdown("**Expenses:**")
            exp_data = [{"Expense": e["expense_name"], "Amount": f"Rs.{e['amount']:,.0f}"} for e in expenses]
            st.dataframe(exp_data, use_container_width=True, hide_index=True)

    st.markdown("---")
    pdf_cols = st.columns(4 if month_status == "closed" else 2)

    with pdf_cols[0]:
        pdf1 = generate_bills_pdf(
            month_year=selected_month, cost_per_unit=record["cost_per_unit"],
            total_collection=record["total_collection"], meter_readings=[dict(r) for r in readings],
            maintenance_amount=MAINTENANCE_AMOUNT,
        )
        st.download_button("📄 Bills PDF", data=pdf1, file_name=f"bills_{selected_month}.pdf", mime="application/pdf", use_container_width=True)
        
    with pdf_cols[1]:
        slips_bytes = generate_slips_pdf(
            month_year=selected_month, cost_per_unit=record["cost_per_unit"],
            meter_readings=[dict(r) for r in readings],
            maintenance_amount=MAINTENANCE_AMOUNT,
        )
        st.download_button("✂️ Slips", data=slips_bytes, file_name=f"slips_{selected_month}.pdf", mime="application/pdf", use_container_width=True)

    if month_status == "closed":
        with pdf_cols[2]:
            pdf2 = generate_summary_pdf(
                month_year=selected_month, opening_balance=record["opening_balance"], closing_balance=record["closing_balance"],
                expenses=[dict(e) for e in expenses], manjeera_bill=record["manjeera_bill"], tanker_count=record["tanker_count"],
                tanker_rate=record["tanker_rate"], total_water_bill=record["total_water_bill"], cost_per_unit=record["cost_per_unit"],
                total_apartment_units=record["total_apartment_units"], total_collection=record["total_collection"],
                total_expenditure=record["total_expenditure"], net_profit_loss=record["net_profit_loss"], maintenance_amount=MAINTENANCE_AMOUNT,
            )
            st.download_button("📄 Summary PDF", data=pdf2, file_name=f"summary_{selected_month}.pdf", mime="application/pdf", use_container_width=True)

        with pdf_cols[3]:
            pdf_full = generate_full_pdf(
                month_year=selected_month, opening_balance=record["opening_balance"], closing_balance=record["closing_balance"],
                expenses=[dict(e) for e in expenses], manjeera_bill=record["manjeera_bill"], tanker_count=record["tanker_count"],
                tanker_rate=record["tanker_rate"], total_water_bill=record["total_water_bill"], cost_per_unit=record["cost_per_unit"],
                total_apartment_units=record["total_apartment_units"], total_collection=record["total_collection"],
                total_expenditure=record["total_expenditure"], net_profit_loss=record["net_profit_loss"],
                meter_readings=[dict(r) for r in readings], maintenance_amount=MAINTENANCE_AMOUNT,
            )
            st.download_button("📄 Full PDF", data=pdf_full, file_name=f"full_bill_{selected_month}.pdf", mime="application/pdf", use_container_width=True)


# ===================================================================
# Main App Wrapper with Auth
# ===================================================================
def main_app():
    st.sidebar.title("🏢 Apartment Billing")

    has_setup = db.has_initial_setup()
    all_months = db.get_all_months()

    if not has_setup:
        page = "initial_setup"
        st.sidebar.info("Complete initial setup first.")
    else:
        nav_options = ["🧾 Water Bills", "💰 Monthly Expenses", "📊 View Past Records"]
        nav_choice = st.sidebar.radio("Navigation", nav_options, index=0)
        if nav_choice == nav_options[0]: page = "water_bills"
        elif nav_choice == nav_options[1]: page = "expenses"
        else: page = "view_records"

    st.sidebar.markdown("---")
    if all_months:
        st.sidebar.markdown("**Recent Months:**")
        for m in all_months[:5]:
            s = db.get_month_status(m)
            st.sidebar.markdown(f"- {fmt_month(m)} {status_badge(s or 'open')}")

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Maintenance: Rs.{MAINTENANCE_AMOUNT:,.0f}/flat · {len(FLAT_NUMBERS)} flats")

    if page == "initial_setup": page_initial_setup()
    elif page == "water_bills": page_water_bills()
    elif page == "expenses": page_expenses()
    elif page == "view_records": page_view_records()


# ---------------------------------------------------------------------------
# Simple Authentication
# ---------------------------------------------------------------------------
def check_password():
    """Returns True if the user has entered the correct password."""
    if st.session_state.get("logged_in", False):
        return True

    st.title("🏢 Apartment Billing App")
    st.subheader("Please log in to continue")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log in")

        if submit:
            if username == st.secrets["app_username"] and password == st.secrets["app_password"]:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("😕 Incorrect username or password")
    return False

if not check_password():
    st.stop()

# If authenticated, show logout and run app
st.sidebar.success(f"Logged in as: {st.secrets['app_username']}")
if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.rerun()

main_app()
