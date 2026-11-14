"""Keeps the free Supabase project from pausing.

Run by .github/workflows/keepalive.yml twice a week. It connects, writes one row
to app_heartbeat (real database activity), and exits non-zero on failure, so
GitHub emails you if the project ever does go down.

    DB_URL=postgresql://... python scripts/keepalive.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from billing.db import engine as dbe  # noqa: E402
from billing.db import repo, schema  # noqa: E402


def main() -> int:
    url = os.environ.get("DB_URL")
    if not url:
        print("DB_URL is not set", file=sys.stderr)
        return 2
    eng = dbe.create(url)

    def log(attempt, max_attempts, wait, diag):
        print(f"attempt {attempt}/{max_attempts} failed ({diag.kind}); retrying in {wait:.0f}s")

    def work(conn):
        schema.migrate(conn)          # no-op once up to date; creates app_heartbeat if needed
        repo.heartbeat(conn, "github-actions")
        return conn.exec_driver_sql("SELECT pinged_at FROM app_heartbeat").scalar_one()

    try:
        at = dbe.run(eng, work, write=True, on_retry=log, max_attempts=8, max_seconds=180)
    except dbe.DatabaseUnavailable as err:
        print(f"FAILED: {err.diagnosis.title}\n{err.diagnosis.advice}", file=sys.stderr)
        return 1
    print(f"ok: heartbeat written at {at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
