"""SafeRouteNYC backend — PostgreSQL connection setup.

Phase 0: connection wiring ONLY. No tables, no migrations, no queries.
Later phases import `get_connection()` (or the pool directly) to talk to the
PostGIS database.

The connection string comes from the DATABASE_URL environment variable, loaded
from a .env file via python-dotenv. Nothing about the database is hardcoded here,
so the same code runs unchanged locally (Docker Compose) and on AWS.

We use a lazily-initialized psycopg2 connection pool as the reusable "engine".
(psycopg2 is already a pinned dependency; we intentionally avoid adding an ORM
until a phase actually needs one.)
"""

import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from psycopg2 import pool

# Load variables from backend/.env by explicit path, so config loads no matter
# which working directory a script is launched from (uvicorn from backend/, the
# data pipeline from the repo root, etc.). No-op if the file is absent.
load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

# Module-level pool, created on first use so importing this module never forces
# a live database connection (keeps tests / tooling / container builds happy).
_connection_pool: "pool.SimpleConnectionPool | None" = None


def get_pool() -> "pool.SimpleConnectionPool":
    """Return the shared connection pool, creating it on first call.

    Raises RuntimeError if DATABASE_URL is not configured, so misconfiguration
    fails loudly rather than silently connecting to the wrong place.
    """
    global _connection_pool
    if _connection_pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. Copy backend/.env.example to "
                "backend/.env and fill it in."
            )
        _connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _connection_pool


@contextmanager
def get_connection():
    """Borrow a connection from the pool for the duration of a `with` block,
    returning it to the pool afterward.

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)   # later phases
    """
    connection_pool = get_pool()
    conn = connection_pool.getconn()
    try:
        yield conn
    finally:
        connection_pool.putconn(conn)
