"""Downloads every ledger table to a JSON file in backups/.

    DB_URL=postgresql://... python scripts/backup.py

Run it before deploying the new version the first time (the app also keeps an
automatic backup_v1_* copy inside the database when it upgrades the schema).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from billing.db import engine as dbe  # noqa: E402

TABLES = ("monthly_records", "expenses", "meter_readings", "drafts")


def main() -> int:
    url = os.environ.get("DB_URL")
    if not url:
        print("DB_URL is not set", file=sys.stderr)
        return 2

    def work(conn):
        out = {}
        for t in TABLES:
            if conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{t}"}).scalar_one():
                out[t] = [dict(r._mapping) for r in conn.execute(text(f"SELECT * FROM {t} ORDER BY 1"))]
        return out

    data = dbe.run(dbe.create(url), work)
    folder = Path(__file__).resolve().parents[1] / "backups"
    folder.mkdir(exist_ok=True)
    path = folder / f"ledger-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"saved {sum(len(v) for v in data.values())} rows from {len(data)} tables to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
