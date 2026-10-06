"""PostgreSQL RunStore adapter (ADR 0003): the durable owner of the action ledger."""

from psycopg.conninfo import conninfo_to_dict

from .migrate import apply_migrations
from .store import PostgresRunStore


def database_name(dsn: str) -> str:
    """The database a DSN points at (used to keep the ledger out of provider DBs)."""
    return str(conninfo_to_dict(dsn).get("dbname") or "")


__all__ = ["PostgresRunStore", "apply_migrations", "database_name"]
