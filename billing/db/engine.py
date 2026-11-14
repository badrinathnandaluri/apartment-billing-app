"""Connection pool + retry policy. No Streamlit imports, so scripts and tests can use it.

Why the old app crashed
-----------------------
* Every query opened a brand-new psycopg2 connection and never closed it.
* One failed connect at startup hit st.stop() with no retry.
* A paused Supabase project (free tier pauses after ~a week idle) makes its host stop
  resolving, which is the "could not translate host name" / ENOTFOUND error.

What this module does instead
-----------------------------
* One small SQLAlchemy pool per process, with pre-ping (dead connections are replaced
  transparently) and recycling (connections never outlive Supabase's idle cut-off).
* Every unit of work runs through `run()`, which retries transient failures with
  exponential backoff and reports each attempt to an optional callback (the UI shows it).
* Failures are classified so the UI can say *why* in plain words instead of a traceback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
)

log = logging.getLogger(__name__)
T = TypeVar("T")

# ~75 s of patience in total: 1, 2, 4, 8, 16, 16 ... seconds between attempts.
MAX_ATTEMPTS = 7
MAX_SECONDS = 75


def normalise_url(url: str) -> str:
    """Accept postgres:// or postgresql:// URLs; force the psycopg2 driver and TLS."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    host = parts.hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1") and "sslmode" not in query:
        query["sslmode"] = "require"
    return urlunsplit(parts._replace(query=urlencode(query)))


def create(url: str) -> Engine:
    return sa.create_engine(
        normalise_url(url),
        pool_size=2,
        max_overflow=3,
        pool_timeout=20,
        pool_pre_ping=True,      # test each connection before use; replace if dead
        pool_recycle=240,        # never reuse a connection older than 4 minutes
        pool_use_lifo=True,      # reuse the warmest connection; idle ones age out
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "application_name": "gnapika-ledger",
        },
    )


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Diagnosis:
    kind: str        # "paused" | "dns" | "auth" | "timeout" | "network" | "unknown"
    title: str
    advice: str
    transient: bool  # worth retrying automatically


def diagnose(exc: BaseException) -> Diagnosis:
    text = str(exc).lower()
    if "could not translate host name" in text or "name or service not known" in text \
            or "nodename nor servname" in text or "enotfound" in text or "getaddrinfo" in text:
        return Diagnosis(
            "paused",
            "The database server can't be found",
            "This almost always means the Supabase project is **paused** (free projects pause "
            "after about a week without use). Open supabase.com → your project → **Restore "
            "project**, wait about a minute, then press Retry. The keep-alive job in this repo "
            "stops this from happening again once it is set up. If the project is not paused, "
            "your db_url may use the direct `db.<ref>.supabase.co` host, which is IPv6-only; "
            "use the **Session pooler** connection string instead.",
            transient=True,
        )
    if "password authentication failed" in text or "no pg_hba.conf entry" in text \
            or "tenant or user not found" in text:
        return Diagnosis(
            "auth",
            "The database rejected the login",
            "The password or user in `db_url` is wrong (or was reset in Supabase). "
            "Copy the connection string again from Supabase → Connect, then update the app's secrets.",
            transient=False,
        )
    if "timeout" in text or "timed out" in text:
        return Diagnosis(
            "timeout",
            "The database is taking too long to answer",
            "It is probably still waking up. Wait a few seconds and press Retry.",
            transient=True,
        )
    if isinstance(exc, (OperationalError, InterfaceError)) or "connection" in text or "server closed" in text \
            or "ssl" in text or "eof" in text:
        return Diagnosis(
            "network",
            "Lost the connection to the database",
            "The database dropped the connection. This usually fixes itself; press Retry.",
            transient=True,
        )
    return Diagnosis("unknown", "Unexpected database error", str(exc)[:300], transient=False)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return True
    if isinstance(exc, (OperationalError, InterfaceError)):
        return diagnose(exc).transient
    return False


class DatabaseUnavailable(RuntimeError):
    def __init__(self, diagnosis: Diagnosis, attempts: int, cause: BaseException):
        super().__init__(f"{diagnosis.title} after {attempts} attempt(s): {cause}")
        self.diagnosis = diagnosis
        self.attempts = attempts
        self.cause = cause


# ---------------------------------------------------------------------------
# Running work with retries
# ---------------------------------------------------------------------------
OnRetry = Callable[[int, int, float, Diagnosis], None]   # attempt, max_attempts, wait_s, diagnosis


def run(
    engine: Engine,
    work: Callable[[Connection], T],
    *,
    write: bool = False,
    on_retry: OnRetry | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    max_seconds: float = MAX_SECONDS,
) -> T:
    """Run `work(conn)` in one transaction, retrying connection-level failures.

    The whole unit of work is retried, never half of it: writes commit atomically
    or not at all, so a retry can't double-apply anything.
    """

    def before_sleep(state: RetryCallState) -> None:
        exc = state.outcome.exception() if state.outcome else None
        wait = state.next_action.sleep if state.next_action else 0.0
        diag = diagnose(exc) if exc else Diagnosis("unknown", "", "", True)
        log.warning("DB attempt %s failed (%s); retrying in %.1fs", state.attempt_number, diag.kind, wait)
        if on_retry:
            on_retry(state.attempt_number, max_attempts, wait, diag)

    retrying = Retrying(
        retry=retry_if_exception(_is_transient),
        wait=wait_exponential_jitter(initial=1, max=16, jitter=0.5),
        stop=stop_after_attempt(max_attempts) | stop_after_delay(max_seconds),
        before_sleep=before_sleep,
        reraise=True,
    )
    attempts = 0
    try:
        for attempt in retrying:
            with attempt:
                attempts = attempt.retry_state.attempt_number
                with (engine.begin() if write else engine.connect()) as conn:
                    return work(conn)
    except (OperationalError, InterfaceError, DBAPIError) as exc:
        diag = diagnose(exc)
        if isinstance(exc, DBAPIError) and not isinstance(exc, (OperationalError, InterfaceError)) \
                and not exc.connection_invalidated:
            raise  # a real SQL error (bug or constraint), not an availability problem
        raise DatabaseUnavailable(diag, attempts, exc) from exc
    raise AssertionError("unreachable")  # pragma: no cover
