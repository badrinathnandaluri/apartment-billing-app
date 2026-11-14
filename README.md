# Gnapika Residency: Water & Maintenance Ledger

Monthly water billing and balance sheet for a 12-flat apartment building.
Streamlit front end, Supabase (Postgres) database, PDF output.

## What it does each month

1. **Expenses tab:** enter the Manjeera bill, tankers, and the month's expenses.
2. **Meter readings tab:** type each flat's current reading. Last month's reading is locked
   beside it, and units, water charge and total bill update as you go.
3. **Review & commit tab:** save the bills, print the bills sheet or cut-out slips, then
   close the month. Closing locks it and carries the balance forward.
4. **Dashboard tab:** last closed month at a glance, trends, and every past month's PDFs.

Everything typed is auto-saved as a draft, so a refresh, a sign-out, or the app going to
sleep never loses work.

## Billing rules

| Step | Formula |
|---|---|
| Units used | current reading − previous reading |
| Total water cost | Manjeera bill + tankers × tanker rate |
| Cost per unit | total water cost ÷ total units, rounded **up** to a whole rupee |
| Flat water bill | units × cost per unit |
| Flat total bill | water bill + ₹1,500 maintenance, rounded **up** to the next ₹5 (162 → 165, 166 → 170) |
| Total expenditure | other expenses + total water cost |
| Closing balance | opening balance + total collection − total expenditure |

Maintenance amount, flat numbers, building name and rounding step live in `billing/config.py`.
Closed months keep the numbers they were closed with.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill it in
streamlit run app.py
```

## Secrets

Set these in `.streamlit/secrets.toml` locally, or in Streamlit Cloud → app → Settings → Secrets.

| Key | Value |
|---|---|
| `db_url` | Supabase → Connect → **Session pooler** connection string |
| `app_username` | the login name |
| `app_password_hash` | output of `python scripts/hash_password.py` |

The old plain `app_password` key still works, but the hash is safer: nobody who sees the
secrets can read the password.

Use the **Session pooler** string, not the "direct connection" one. The direct host
(`db.<ref>.supabase.co`) is IPv6-only and cannot be reached from Streamlit Cloud.

## Deploying this version over the old app (one time)

1. If the Supabase project is paused, open supabase.com → the project → **Restore project**.
2. Take a backup: `DB_URL="<connection string>" python scripts/backup.py` (writes `backups/*.json`).
3. Update the app's secrets (table above).
4. Deploy this branch. On first start the app upgrades the database by itself:
   it copies the three original tables to `backup_v1_*`, converts money columns to exact
   decimals, adds the drafts table, and turns on row-level security.
5. Set up the keep-alive (next section).

If a month is currently open in the old app with bills already handed out, close it in the
old app first. This version rounds bills up to the next ₹5, so re-saving that month here
would change some totals by up to ₹4.

## Keeping the database awake

Supabase pauses free projects after about a week without activity, and a paused project
can only be restored by hand. `.github/workflows/keepalive.yml` writes a heartbeat row
twice a week so that never happens.

Setup: GitHub repo → Settings → Secrets and variables → Actions → **New repository secret**
named `DB_URL` with the same connection string as `db_url`. Then Actions → *Keep database
awake* → **Run workflow** once to confirm it is green.

Two things the keep-alive cannot do:

* GitHub pauses scheduled workflows in repos with no activity for 60 days. The workflow
  re-enables itself on every run to avoid this, and GitHub emails you if it ever stops.
* Streamlit Community Cloud puts the *app* to sleep when nobody visits. That is a
  "Yes, get this app back up" button on their side; no data is involved or lost.

## If the database is unreachable

The app retries with exponential backoff for about a minute, showing
"Waking up database… attempt 2 of 7". If it still cannot connect, it shows what is most
likely wrong (paused project, wrong password, timeout) and a Retry button. Whatever was
typed stays in the browser tab and is saved once the database is back.

## Project layout

```
app.py                  entry point: login, database gate, header, four tabs
billing/config.py       building settings (flats, maintenance, rounding)
billing/domain.py       billing math, exact decimals, no I/O
billing/db/engine.py    connection pool, retry policy, error diagnosis
billing/db/schema.py    versioned migrations
billing/db/repo.py      all SQL
billing/services.py     use-cases the UI calls
billing/pdf/render.py   bills sheet, balance sheet, slips
billing/ui/             theme, login, draft state, one module per tab
scripts/                keepalive.py, backup.py, hash_password.py
tests/                  math, PDFs, login, database
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest                                   # math, PDF and login tests
TEST_DATABASE_URL=postgresql://... pytest tests/test_db.py   # needs a throwaway Postgres
```

`tests/test_db.py` drops and recreates the tables. Never point it at the real ledger.

## Ledger safeguards

* Months are billed in order, and only one month can be open at a time.
* Only the latest month can be reopened (password required), so later balances never go stale.
* Every write is a single transaction: a month is saved or closed completely, or not at all.
* Sign-in locks for 5 minutes after 5 wrong attempts, and sessions sign out after 2 idle hours.
