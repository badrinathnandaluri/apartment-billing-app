import os
import streamlit as st
import psycopg2
import psycopg2.extras

FLAT_NUMBERS = ['101', '102', '103', '201', '202', '203', '301', '302', '303', '401', '402', '403']

def get_connection():
    """Return a connection using st.secrets with DictCursor."""
    # Note: Streamlit Cloud uses st.secrets. Locally, it reads from .streamlit/secrets.toml
    conn = psycopg2.connect(st.secrets["db_url"])
    return conn

def init_db() -> None:
    """Create tables if they don't exist."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monthly_records (
                    id SERIAL PRIMARY KEY,
                    month_year TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    opening_balance REAL NOT NULL DEFAULT 0,
                    closing_balance REAL NOT NULL DEFAULT 0,
                    manjeera_bill REAL NOT NULL DEFAULT 0,
                    tanker_count INTEGER NOT NULL DEFAULT 0,
                    tanker_rate REAL NOT NULL DEFAULT 0,
                    total_water_bill REAL NOT NULL DEFAULT 0,
                    cost_per_unit INTEGER NOT NULL DEFAULT 0,
                    total_apartment_units INTEGER NOT NULL DEFAULT 0,
                    total_collection REAL NOT NULL DEFAULT 0,
                    total_expenditure REAL NOT NULL DEFAULT 0,
                    net_profit_loss REAL NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    month_year TEXT NOT NULL,
                    expense_name TEXT NOT NULL,
                    amount REAL NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS meter_readings (
                    id SERIAL PRIMARY KEY,
                    month_year TEXT NOT NULL,
                    flat_number TEXT NOT NULL,
                    previous_reading REAL NOT NULL DEFAULT 0,
                    current_reading REAL NOT NULL DEFAULT 0,
                    units_used REAL NOT NULL DEFAULT 0,
                    water_bill REAL NOT NULL DEFAULT 0,
                    total_bill REAL NOT NULL DEFAULT 0,
                    UNIQUE(month_year, flat_number)
                )
            ''')
        conn.commit()

def get_all_months() -> list[str]:
    """Return all month_year values in descending order (exclude 'INITIAL')."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(
                "SELECT month_year FROM monthly_records WHERE month_year != 'INITIAL' ORDER BY month_year DESC"
            )
            return [row['month_year'] for row in cursor.fetchall()]

def get_latest_month() -> str | None:
    """Return the most recent month_year (including INITIAL as fallback)."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(
                """SELECT month_year FROM monthly_records 
                   ORDER BY CASE WHEN month_year = 'INITIAL' THEN 0 ELSE 1 END DESC, 
                            month_year DESC 
                   LIMIT 1"""
            )
            row = cursor.fetchone()
            return row['month_year'] if row else None

def get_monthly_record(month_year: str) -> dict | None:
    """Return the full monthly_record row as a dict."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT * FROM monthly_records WHERE month_year = %s", (month_year,))
            row = cursor.fetchone()
            return dict(row) if row else None

def get_expenses(month_year: str) -> list[dict]:
    """Return expense dicts for the given month."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT * FROM expenses WHERE month_year = %s", (month_year,))
            return [dict(row) for row in cursor.fetchall()]

def get_meter_readings(month_year: str) -> list[dict]:
    """Return meter reading dicts ordered by flat_number."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM meter_readings WHERE month_year = %s ORDER BY flat_number",
                (month_year,)
            )
            return [dict(row) for row in cursor.fetchall()]

def get_previous_readings() -> dict[str, float]:
    """Return {flat_number: current_reading} from the LATEST month."""
    latest_month = get_latest_month()
    if not latest_month:
        return {}
    
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(
                "SELECT flat_number, current_reading FROM meter_readings WHERE month_year = %s",
                (latest_month,)
            )
            return {row['flat_number']: row['current_reading'] for row in cursor.fetchall()}

def get_last_closed_balance() -> float:
    """Return closing_balance from the most recent CLOSED month."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(
                """SELECT closing_balance FROM monthly_records 
                   WHERE status = 'closed' 
                   ORDER BY CASE WHEN month_year = 'INITIAL' THEN 0 ELSE 1 END DESC, 
                            month_year DESC 
                   LIMIT 1"""
            )
            row = cursor.fetchone()
            return row['closing_balance'] if row else 0.0

def get_month_status(month_year: str) -> str | None:
    """Return 'open', 'closed', or None if month doesn't exist."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT status FROM monthly_records WHERE month_year = %s", (month_year,))
            row = cursor.fetchone()
            return row['status'] if row else None

def get_open_months() -> list[str]:
    """Return list of month_year values with status='open'."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(
                "SELECT month_year FROM monthly_records WHERE status = 'open' AND month_year != 'INITIAL' ORDER BY month_year DESC"
            )
            return [row['month_year'] for row in cursor.fetchall()]

def has_open_month() -> str | None:
    """Return the month_year of any open month, or None."""
    open_months = get_open_months()
    return open_months[0] if open_months else None

def save_bill_data(
    month_year: str,
    manjeera_bill: float,
    tanker_count: int,
    tanker_rate: float,
    total_water_bill: float,
    cost_per_unit: int,
    total_apartment_units: int,
    total_collection: float,
    meter_readings: list[dict],
) -> None:
    """Save bill/meter data for a month. Sets status='open'."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM monthly_records WHERE month_year = %s", (month_year,))
            exists = cursor.fetchone() is not None
            
            if exists:
                cursor.execute('''
                    UPDATE monthly_records 
                    SET status = 'open',
                        manjeera_bill = %s,
                        tanker_count = %s,
                        tanker_rate = %s,
                        total_water_bill = %s,
                        cost_per_unit = %s,
                        total_apartment_units = %s,
                        total_collection = %s
                    WHERE month_year = %s
                ''', (manjeera_bill, tanker_count, tanker_rate, total_water_bill, 
                      cost_per_unit, total_apartment_units, total_collection, month_year))
            else:
                cursor.execute('''
                    INSERT INTO monthly_records (
                        month_year, status, manjeera_bill, tanker_count, tanker_rate,
                        total_water_bill, cost_per_unit, total_apartment_units, total_collection,
                        opening_balance, closing_balance, total_expenditure, net_profit_loss
                    ) VALUES (%s, 'open', %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0)
                ''', (month_year, manjeera_bill, tanker_count, tanker_rate, total_water_bill,
                      cost_per_unit, total_apartment_units, total_collection))
                
            cursor.execute("DELETE FROM meter_readings WHERE month_year = %s", (month_year,))
            
            for reading in meter_readings:
                cursor.execute('''
                    INSERT INTO meter_readings (
                        month_year, flat_number, previous_reading, current_reading, 
                        units_used, water_bill, total_bill
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    month_year,
                    reading['flat_number'],
                    reading['previous_reading'],
                    reading['current_reading'],
                    reading['units_used'],
                    reading['water_bill'],
                    reading['total_bill']
                ))
        conn.commit()

def save_expenses_draft(month_year: str, expenses: list[dict]) -> None:
    """Save expenses for the month without finalizing/closing it."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM expenses WHERE month_year = %s", (month_year,))
            for exp in expenses:
                cursor.execute('''
                    INSERT INTO expenses (month_year, expense_name, amount)
                    VALUES (%s, %s, %s)
                ''', (month_year, exp['expense_name'], exp['amount']))
        conn.commit()

def close_month(
    month_year: str,
    opening_balance: float,
    expenses: list[dict],
    total_expenditure: float,
    net_profit_loss: float,
    closing_balance: float,
) -> None:
    """Close a month: save expenses and financial summary, set status='closed'."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE monthly_records
                SET status = 'closed',
                    opening_balance = %s,
                    total_expenditure = %s,
                    net_profit_loss = %s,
                    closing_balance = %s
                WHERE month_year = %s
            ''', (opening_balance, total_expenditure, net_profit_loss, closing_balance, month_year))
            
            cursor.execute("DELETE FROM expenses WHERE month_year = %s", (month_year,))
            
            for exp in expenses:
                cursor.execute('''
                    INSERT INTO expenses (month_year, expense_name, amount)
                    VALUES (%s, %s, %s)
                ''', (month_year, exp['expense_name'], exp['amount']))
        conn.commit()

def unlock_month(month_year: str) -> None:
    """Set status back to 'open'. Keep expenses intact for re-editing."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE monthly_records SET status = 'open' WHERE month_year = %s", (month_year,))
        conn.commit()

def month_exists(month_year: str) -> bool:
    """Check if a monthly record exists."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM monthly_records WHERE month_year = %s", (month_year,))
            return cursor.fetchone() is not None

def setup_initial_readings(readings: dict[str, float], opening_balance: float) -> None:
    """First-time setup. Creates 'INITIAL' record with status='closed'."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Using ON CONFLICT for UPSERT in Postgres
            cursor.execute('''
                INSERT INTO monthly_records (
                    month_year, status, closing_balance, opening_balance, manjeera_bill,
                    tanker_count, tanker_rate, total_water_bill, cost_per_unit,
                    total_apartment_units, total_collection, total_expenditure, net_profit_loss
                ) VALUES ('INITIAL', 'closed', %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                ON CONFLICT (month_year) DO UPDATE SET closing_balance = EXCLUDED.closing_balance
            ''', (opening_balance,))
            
            cursor.execute("DELETE FROM meter_readings WHERE month_year = 'INITIAL'")
            
            for flat, reading in readings.items():
                cursor.execute('''
                    INSERT INTO meter_readings (
                        month_year, flat_number, current_reading,
                        previous_reading, units_used, water_bill, total_bill
                    ) VALUES ('INITIAL', %s, %s, 0, 0, 0, 0)
                ''', (flat, reading))
        conn.commit()

def has_initial_setup() -> bool:
    """Check if any data exists at all."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM monthly_records LIMIT 1")
                return cursor.fetchone() is not None
    except psycopg2.errors.UndefinedTable:
        # Table doesn't exist yet
        return False
