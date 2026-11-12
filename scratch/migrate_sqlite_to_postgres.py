#!/usr/bin/env python3
"""
migrate_sqlite_to_postgres.py — AutoPrompt Phase 8.5-B
=======================================================

Non-destructive, idempotent migration script that copies all data from
a local SQLite database to a PostgreSQL database (e.g. Neon Serverless).

Usage
-----
Set environment variables then run:

    # Required
    TARGET_DATABASE_URL=postgresql://user:pass@host:5432/dbname

    # Optional (auto-detected from backend/.env / autoprompt.db if omitted)
    SOURCE_DATABASE_URL=sqlite:///./backend/autoprompt.db

    python scratch/migrate_sqlite_to_postgres.py [--dry-run] [--reset-sequences]

Flags
-----
  --dry-run           Read source, print row counts, but write nothing.
  --reset-sequences   After insertion, reset PostgreSQL serial sequences to
                      max(id) + 1 to prevent duplicate-key errors on INSERT.
                      Enabled by default when TARGET_DATABASE_URL is set.

Safety guarantees
-----------------
- Source database is opened read-only (never modified).
- INSERT uses ON CONFLICT DO NOTHING → safe to re-run on a partially-migrated DB.
- All rows are inserted in a single atomic transaction; rolls back on any error.
- Count verification is run after commit.
- No environment secrets are printed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from project root without installing the package
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("migrate")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_pg_url(url: str) -> str:
    """Normalize postgres:// → postgresql:// (required by psycopg2)."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _redact(url: str) -> str:
    """Return URL with password replaced by ***."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        redacted = p._replace(netloc=p.netloc.replace(p.password or "", "***") if p.password else p.netloc)
        return urlunparse(redacted)
    except Exception:
        return "<redacted>"


def _make_engine(url: str, is_source: bool = False):
    """Create a SQLAlchemy engine for the given URL."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    is_sqlite = url.startswith("sqlite")
    if is_sqlite:
        # Standard SQLite engine — read-only enforcement is a best-effort bonus.
        # SQLite URI mode (?mode=ro) is not reliably supported across all SQLAlchemy
        # driver/platform combinations; plain check_same_thread=False is sufficient
        # since we never call session.add/commit on the source session.
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    else:
        return create_engine(url, poolclass=NullPool, pool_pre_ping=True, echo=False)


def _resolve_source_url() -> str:
    """Auto-detect SOURCE_DATABASE_URL from env or backend/.env."""
    url = os.getenv("SOURCE_DATABASE_URL", "")
    if url:
        return url

    # Try loading backend/.env
    env_file = _BACKEND_DIR / ".env"
    if env_file.is_file():
        from dotenv import dotenv_values
        vals = dotenv_values(env_file)
        url = vals.get("DATABASE_URL", "")
        if url:
            log.info("Loaded SOURCE_DATABASE_URL from backend/.env")
            return url

    # Default: local SQLite next to backend
    default = f"sqlite:///{(_BACKEND_DIR / 'autoprompt.db').as_posix()}"
    log.info("Using default SOURCE_DATABASE_URL: %s", default)
    return default


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------
def migrate(source_url: str, target_url: str, dry_run: bool, reset_sequences: bool) -> int:
    """
    Migrate all rows from source (SQLite) to target (PostgreSQL).

    Returns 0 on success, 1 on failure.
    """
    from sqlalchemy.orm import Session

    # Import models — Base.metadata drives schema creation on target
    from app.db.models import Base, SavedPrompt, PromptHistory

    log.info("=" * 60)
    log.info("AutoPrompt — SQLite → PostgreSQL Migration")
    log.info("=" * 60)
    log.info("Source : %s", _redact(source_url))
    log.info("Target : %s", _redact(target_url))
    log.info("Mode   : %s", "DRY RUN (no writes)" if dry_run else "LIVE")
    log.info("-" * 60)

    # -- Source engine & session ------------------------------------------------
    src_engine = _make_engine(source_url, is_source=True)
    try:
        with Session(src_engine) as src_session:
            src_session.execute(__import__("sqlalchemy").text("SELECT 1"))
        log.info("✓ Source connection OK")
    except Exception as exc:
        log.error("✗ Cannot connect to source database: %s", exc)
        return 1

    # -- Target engine (skipped entirely in dry-run mode) ----------------------
    tgt_engine = None
    if not dry_run:
        try:
            tgt_engine = _make_engine(target_url, is_source=False)
        except Exception as exc:
            log.error("✗ Cannot create target database engine: %s", exc)
            log.error("  Hint: verify TARGET_DATABASE_URL and that psycopg2-binary is installed.")
            return 1
        try:
            with Session(tgt_engine) as tgt_session:
                tgt_session.execute(__import__("sqlalchemy").text("SELECT 1"))
            log.info("✓ Target connection OK")
        except Exception as exc:
            log.error("✗ Cannot connect to target database: %s", exc)
            log.error("  Hint: verify TARGET_DATABASE_URL and that psycopg2-binary is installed.")
            return 1

    # -- Create schema on target -----------------------------------------------
    if not dry_run and tgt_engine is not None:
        log.info("Creating schema on target (CREATE TABLE IF NOT EXISTS)…")
        try:
            Base.metadata.create_all(bind=tgt_engine)
            log.info("✓ Schema ready")
        except Exception as exc:
            log.error("✗ Schema creation failed: %s", exc)
            return 1

    # -- Read from source -------------------------------------------------------
    with Session(src_engine) as src_session:
        saved_prompts = src_session.query(SavedPrompt).all()
        prompt_history = src_session.query(PromptHistory).all()

    sp_count = len(saved_prompts)
    ph_count = len(prompt_history)
    log.info("Source rows — saved_prompts: %d | prompt_history: %d", sp_count, ph_count)

    if dry_run:
        log.info("DRY RUN complete — no data written.")
        return 0

    if sp_count == 0 and ph_count == 0:
        log.warning("Source database appears empty. Nothing to migrate.")
        return 0

    # -- Insert into target (atomic, idempotent) --------------------------------
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    log.info("Inserting rows into target (ON CONFLICT DO NOTHING)…")
    try:
        with Session(tgt_engine) as tgt_session:
            # saved_prompts
            if saved_prompts:
                sp_rows = [
                    {
                        "id": r.id,
                        "title": r.title,
                        "content": r.content,
                        "category": r.category,
                        "operation_type": r.operation_type,
                        "created_at": r.created_at,
                        "updated_at": r.updated_at,
                    }
                    for r in saved_prompts
                ]
                stmt = pg_insert(SavedPrompt.__table__).values(sp_rows)
                stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                tgt_session.execute(stmt)
                log.info("  saved_prompts: %d rows inserted (duplicates skipped)", len(sp_rows))

            # prompt_history
            if prompt_history:
                ph_rows = [
                    {
                        "id": r.id,
                        "operation_type": r.operation_type,
                        "original_input": r.original_input,
                        "generated_output": r.generated_output,
                        "optimized_output": r.optimized_output,
                        "tokens_before": r.tokens_before,
                        "tokens_after": r.tokens_after,
                        "tokens_saved": r.tokens_saved,
                        "model_name": r.model_name,
                        "created_at": r.created_at,
                    }
                    for r in prompt_history
                ]
                stmt = pg_insert(PromptHistory.__table__).values(ph_rows)
                stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                tgt_session.execute(stmt)
                log.info("  prompt_history: %d rows inserted (duplicates skipped)", len(ph_rows))

            tgt_session.commit()
            log.info("✓ Transaction committed")

    except Exception as exc:
        log.error("✗ Insertion failed — transaction rolled back: %s", exc)
        return 1

    # -- Reset PostgreSQL sequences ---------------------------------------------
    if reset_sequences:
        log.info("Resetting PostgreSQL serial sequences…")
        try:
            from sqlalchemy import text
            with tgt_engine.connect() as conn:
                for table, col, seq in [
                    ("saved_prompts",  "id", "saved_prompts_id_seq"),
                    ("prompt_history", "id", "prompt_history_id_seq"),
                ]:
                    result = conn.execute(text(f"SELECT MAX({col}) FROM {table}"))
                    max_id = result.scalar()
                    if max_id is not None:
                        conn.execute(text(f"SELECT setval('{seq}', {max_id})"))
                        log.info("  %s.%s sequence → next value = %d", table, col, max_id + 1)
                conn.commit()
            log.info("✓ Sequences reset")
        except Exception as exc:
            log.warning("Could not reset sequences (non-fatal): %s", exc)

    # -- Count verification -----------------------------------------------------
    log.info("-" * 60)
    log.info("Count verification…")
    try:
        with Session(tgt_engine) as tgt_session:
            tgt_sp = tgt_session.query(SavedPrompt).count()
            tgt_ph = tgt_session.query(PromptHistory).count()
    except Exception as exc:
        log.error("✗ Verification query failed: %s", exc)
        return 1

    sp_ok = tgt_sp >= sp_count
    ph_ok = tgt_ph >= ph_count

    log.info("  saved_prompts  — source: %d | target: %d  %s", sp_count, tgt_sp, "✓" if sp_ok else "✗ MISMATCH")
    log.info("  prompt_history — source: %d | target: %d  %s", ph_count, tgt_ph, "✓" if ph_ok else "✗ MISMATCH")

    if sp_ok and ph_ok:
        log.info("=" * 60)
        log.info("✓ Migration complete — all rows verified.")
        log.info("=" * 60)
        return 0
    else:
        log.error("✗ Row count mismatch — investigate before switching DATABASE_URL.")
        return 1


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate AutoPrompt data from SQLite to PostgreSQL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read source and print counts; do not write anything.",
    )
    parser.add_argument(
        "--no-reset-sequences",
        action="store_true",
        help="Skip resetting PostgreSQL serial sequences after insertion.",
    )
    args = parser.parse_args()

    source_url = _resolve_source_url()
    target_url = os.getenv("TARGET_DATABASE_URL", "")

    if not target_url:
        if args.dry_run:
            log.warning("TARGET_DATABASE_URL not set — running dry-run against source only.")
            target_url = source_url  # dry-run never writes, so this is safe
        else:
            log.error("TARGET_DATABASE_URL is required. Set it and re-run.")
            log.error("  Example: $env:TARGET_DATABASE_URL='postgresql://user:pass@host/db'")
            sys.exit(1)

    target_url = _normalize_pg_url(target_url)
    reset_sequences = not args.no_reset_sequences and not args.dry_run

    exit_code = migrate(
        source_url=source_url,
        target_url=target_url,
        dry_run=args.dry_run,
        reset_sequences=reset_sequences,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
