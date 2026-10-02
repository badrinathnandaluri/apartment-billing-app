# 🏢 Apartment Water Billing & Management

Automated monthly billing application for a 12-flat apartment complex.

## Features

- **Monthly bill calculation** with automatic rounding rules
- **Persistent database** (SQLite) — remembers previous meter readings & closing balance
- **Dynamic expense entry** — add/remove variable expenses each month
- **PDF generation** — 2-page bill matching manual ledger format
- **History browser** — view past months and re-download PDFs

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

## First-Time Setup

On first launch, the app asks for:
1. **Opening Balance** — your latest closing balance (or 0 if starting fresh)
2. **Previous Meter Readings** — last recorded readings for each flat (or 0)

## Monthly Workflow

1. Select the month/year
2. Enter variable expenses (Watchman, Garbage, etc.)
3. Enter water bill details (Manjeera + tankers)
4. Enter current meter readings (previous readings auto-populated)
5. Click **Calculate Bills** to preview
6. Click **Save to Database** to persist
7. Click **Download PDF** for the printable bill

## Project Structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — main entry point |
| `database.py` | SQLite data layer |
| `calculations.py` | Business logic & rounding |
| `pdf_generator.py` | 2-page PDF bill generation |
| `requirements.txt` | Python dependencies |

## Calculation Rules

| Calculation | Formula |
|------------|---------|
| Units Used | Current Reading − Previous Reading |
| Total Water Bill | Manjeera + (Tankers × Rate) |
| Cost per Unit | ⌈ Total Water Bill ÷ Total Units ⌉ (rounded UP) |
| Flat Water Bill | Units × Cost per Unit |
| Flat Total Bill | round₅(1500 + Flat Water Bill) |
| Total Collection | Σ Flat Total Bills (rounded) |
| Total Expenditure | Σ Expenses + Total Water Bill |
| Closing Balance | Opening Balance + (Collection − Expenditure) |

## Configuration

Edit `calculations.py` to change:
- `MAINTENANCE_AMOUNT` — currently ₹1,500 per flat
- `FLAT_NUMBERS` — list of flat identifiers
