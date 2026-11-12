"""
session.py — Database engine and session factory for AutoPrompt.

Configures:
- SQLite connection with WAL journal mode and foreign key enforcement (local dev).
- PostgreSQL connection with NullPool for serverless/Vercel compatibility.
- Safe session lifecycle management with automatic rollback on error.
- Non-destructive database initialization.

Phase 8.5-B: Added PostgreSQL/NullPool support and postgres:// → postgresql:// URL
normalization to support Neon Serverless Postgres on Vercel.
"""

from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import Base

logger = logging.getLogger("autoprompt.db")

# ---------------------------------------------------------------------------
# URL normalization — some providers (Heroku, Neon legacy URLs) emit
# "postgres://" which psycopg2 does not accept; normalize to "postgresql://".
# ---------------------------------------------------------------------------
_raw_url: str = settings.DATABASE_URL
if _raw_url.startswith("postgres://"):
    _raw_url = "postgresql://" + _raw_url[len("postgres://"):]
    logger.debug("Normalized DATABASE_URL prefix: postgres:// → postgresql://")

_IS_SQLITE = _raw_url.startswith("sqlite")
_IS_POSTGRES = _raw_url.startswith("postgresql")

# ---------------------------------------------------------------------------
# Engine construction
#
# SQLite  → standard thread-safe pool with check_same_thread=False.
# PostgreSQL serverless (Vercel) → NullPool so every request gets a fresh
#   connection and no long-lived connections are held open between invocations.
#   pool_pre_ping stays True for TCP keepalive verification.
# ---------------------------------------------------------------------------
if _IS_POSTGRES:
    from sqlalchemy.pool import NullPool
    engine = create_engine(
        _raw_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        echo=False,
    )
    logger.debug("PostgreSQL engine created with NullPool (serverless mode).")
else:
    # SQLite (default for local dev and Docker)
    engine = create_engine(
        _raw_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False,
    )
    logger.debug("SQLite engine created.")


# ---------------------------------------------------------------------------
# SQLite-only: set WAL journal mode and foreign key enforcement on connect.
# This listener is a no-op for PostgreSQL engines.
# ---------------------------------------------------------------------------
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and foreign key constraints on SQLite connections."""
    if _IS_SQLITE:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception as exc:
            logger.debug("Failed to set SQLite PRAGMA: %s", exc)
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(bind_engine=None) -> None:
    """
    Initialize database schema non-destructively.
    Only creates tables that do not already exist.
    """
    target = bind_engine or engine

    # Ensure SQLite parent directory exists for file-based database paths (e.g. /app/data)
    if settings.DATABASE_URL.startswith("sqlite") and not settings.DATABASE_URL.startswith("sqlite:///:memory:"):
        from pathlib import Path
        db_raw_path = settings.DATABASE_URL.replace("sqlite:///", "")
        if db_raw_path:
            parent_dir = Path(db_raw_path).parent
            if parent_dir and not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    logger.info("Created SQLite parent directory: %s", parent_dir)
                except Exception as exc:
                    logger.debug("Failed to auto-create SQLite directory %s: %s", parent_dir, exc)

    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=target)
    logger.info("Database schema initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    Automatically rolls back on exceptions and closes the session on completion.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        db.rollback()
        logger.error("Database transaction rolled back due to error: %s", exc)
        raise
    finally:
        db.close()
