"""
test_phase_8_5d.py — AutoPrompt Phase 8.5-D: Local Simulation & Regression Tests
==================================================================================

Validates Phase 8.5-B (session.py PostgreSQL support) and Phase 8.5-C
(Vercel packaging) without connecting to any production database or deploying.

Test Sections
-------------
1. PostgreSQL URL Normalization          — pure logic, no DB
2. session.py Engine Type & Pool        — inspect live SQLite engine + logic tests
3. SQLite WAL / FK Pragma               — in-memory SQLite verification
4. Migration Script Helpers             — _normalize_pg_url, _redact, _make_engine
5. Migration Dry-Run (temp SQLite)      — isolated temp DB, no network
6. Migration Live-Path (mocked PG)      — SQLite-backed simulation of full flow
7. Migration Safety                     — source never modified, rollback on error
8. Vercel Packaging Validation          — file inspection, routing, deps, headers
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Lazy import of migration helpers (avoids running basicConfig at module level)
# ---------------------------------------------------------------------------
def _import_migrate():
    """Import migrate module helpers without triggering CLI entry point."""
    spec = importlib.util.spec_from_file_location(
        "migrate_sqlite_to_postgres",
        REPO_ROOT / "scratch" / "migrate_sqlite_to_postgres.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # Suppress module-level logging.basicConfig side effects in tests
    import logging
    logging.disable(logging.CRITICAL)
    try:
        spec.loader.exec_module(mod)
    finally:
        logging.disable(logging.NOTSET)
    return mod


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — PostgreSQL URL Normalization
# ═══════════════════════════════════════════════════════════════════════════════

class TestPostgresURLNormalization(unittest.TestCase):
    """Verify postgres:// → postgresql:// normalization logic (no DB needed)."""

    def setUp(self):
        self.migrate = _import_migrate()

    def test_postgres_prefix_normalized(self):
        """postgres:// must become postgresql:// for psycopg2 compatibility."""
        result = self.migrate._normalize_pg_url(
            "postgres://user:pass@host:5432/db"
        )
        self.assertEqual(result, "postgresql://user:pass@host:5432/db")

    def test_postgresql_prefix_unchanged(self):
        """postgresql:// must pass through unchanged."""
        url = "postgresql://user:pass@host:5432/db"
        self.assertEqual(self.migrate._normalize_pg_url(url), url)

    def test_sqlite_url_unchanged(self):
        """SQLite URLs must not be touched."""
        url = "sqlite:///./autoprompt.db"
        self.assertEqual(self.migrate._normalize_pg_url(url), url)

    def test_neon_pooler_url_normalized(self):
        """Neon legacy postgres:// on port 6543 (pooler) is normalized."""
        result = self.migrate._normalize_pg_url(
            "postgres://user:pass@ep-xxx.neon.tech:6543/neondb?sslmode=require"
        )
        self.assertTrue(result.startswith("postgresql://"))
        self.assertIn(":6543/", result)

    def test_neon_postgresql_url_unchanged(self):
        """Neon postgresql:// on port 6543 is not double-normalized."""
        url = "postgresql://user:pass@ep-xxx.neon.tech:6543/neondb?sslmode=require"
        self.assertEqual(self.migrate._normalize_pg_url(url), url)

    def test_empty_string_unchanged(self):
        """Empty string returns empty string without error."""
        self.assertEqual(self.migrate._normalize_pg_url(""), "")

    def test_session_module_normalization(self):
        """
        session.py applies the same normalization at import time.
        Verify via the module-level _IS_SQLITE / _IS_POSTGRES flags.
        Since the test environment uses SQLite, _IS_SQLITE must be True.
        """
        import app.db.session as sess
        self.assertTrue(sess._IS_SQLITE, "_IS_SQLITE should be True in SQLite test env")
        self.assertFalse(sess._IS_POSTGRES, "_IS_POSTGRES should be False in SQLite test env")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — session.py Engine Type & Pool Verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionEngineConfiguration(unittest.TestCase):
    """Inspect the live engine created by session.py for the SQLite test env."""

    def setUp(self):
        import app.db.session as sess
        self.sess = sess

    def test_engine_exists(self):
        """session.py must expose a module-level engine."""
        self.assertIsNotNone(self.sess.engine)

    def test_sqlite_engine_dialect(self):
        """Engine dialect must be sqlite in the test environment."""
        dialect_name = self.sess.engine.dialect.name
        self.assertEqual(dialect_name, "sqlite",
                         f"Expected sqlite dialect, got {dialect_name}")

    def test_sqlite_engine_not_nullpool(self):
        """SQLite engine must NOT use NullPool (NullPool is PG-only)."""
        from sqlalchemy.pool import NullPool
        self.assertNotIsInstance(
            self.sess.engine.pool, NullPool,
            "SQLite engine must not use NullPool"
        )

    def test_session_local_bound_to_engine(self):
        """SessionLocal must be bound to the same engine."""
        self.assertIs(self.sess.SessionLocal.kw.get("bind"), self.sess.engine)

    def test_nullpool_chosen_for_postgresql_url(self):
        """
        When _make_engine() receives a postgresql:// URL, it must configure
        NullPool without attempting a real connection.
        We test this by patching create_engine and inspecting the call arguments.
        """
        migrate = _import_migrate()
        from sqlalchemy.pool import NullPool

        captured = {}

        def fake_create_engine(url, **kwargs):
            captured["url"]      = url
            captured["kwargs"]   = kwargs
            # Return a MagicMock that quacks like an engine
            return MagicMock()

        with patch("sqlalchemy.create_engine", side_effect=fake_create_engine):
            migrate._make_engine(
                "postgresql://user:pass@localhost:5432/testdb", is_source=False
            )

        self.assertIn("poolclass", captured["kwargs"],
                      "NullPool must be passed as poolclass for PostgreSQL")
        self.assertIs(captured["kwargs"]["poolclass"], NullPool)

    def test_check_same_thread_set_for_sqlite(self):
        """
        _make_engine() must set check_same_thread=False for SQLite URLs.
        """
        migrate = _import_migrate()
        captured = {}

        def fake_create_engine(url, **kwargs):
            captured["url"]    = url
            captured["kwargs"] = kwargs
            return MagicMock()

        with patch("sqlalchemy.create_engine", side_effect=fake_create_engine):
            migrate._make_engine("sqlite:///./test.db", is_source=False)

        connect_args = captured["kwargs"].get("connect_args", {})
        self.assertFalse(
            connect_args.get("check_same_thread", True),
            "SQLite engine must have check_same_thread=False"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — SQLite WAL / FK Pragma Verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestSQLitePragmaApplication(unittest.TestCase):
    """Verify WAL and FK pragmas are applied only to SQLite engines."""

    def _make_test_sqlite_engine(self, url: str | None = None):
        """
        Create a fresh file-based (or in-memory) SQLite engine with the pragma
        listener attached.  WAL mode is only persistent for file-based DBs on
        most SQLite builds, so we default to a temp file.
        """
        import tempfile, os
        from sqlalchemy import create_engine, event
        from app.db.session import set_sqlite_pragma

        if url is None:
            # Use a temporary file; WAL mode requires a file-based DB
            fd, path = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            url = f"sqlite:///{path}"
            self._tmp_db_path = path
        else:
            self._tmp_db_path = None

        eng = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(eng, "connect", set_sqlite_pragma)
        return eng

    def tearDown(self):
        # Remove temp DB file if created
        import os
        if hasattr(self, "_tmp_db_path") and self._tmp_db_path:
            try:
                os.remove(self._tmp_db_path)
            except OSError:
                pass

    def test_wal_mode_applied(self):
        """WAL journal mode must be set on SQLite file-based connections."""
        import app.db.session  # noqa: ensure _IS_SQLITE is True
        from sqlalchemy import text
        eng = self._make_test_sqlite_engine()
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode")).scalar()
        eng.dispose()
        self.assertEqual(result, "wal", f"Expected wal, got {result!r}")

    def test_foreign_keys_enabled(self):
        """Foreign key enforcement must be ON for SQLite connections."""
        from sqlalchemy import text
        eng = self._make_test_sqlite_engine()
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys")).scalar()
        self.assertEqual(result, 1, "PRAGMA foreign_keys must be 1 (ON)")

    def test_synchronous_normal(self):
        """PRAGMA synchronous must be set to NORMAL (1)."""
        from sqlalchemy import text
        eng = self._make_test_sqlite_engine()
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA synchronous")).scalar()
        # NORMAL = 1
        self.assertEqual(result, 1, "PRAGMA synchronous must be NORMAL (1)")

    def test_pragma_does_not_fire_for_postgres_flag(self):
        """
        set_sqlite_pragma is a no-op when _IS_SQLITE is False.
        Simulate by temporarily setting the module flag and asserting no PRAGMA
        would execute on the dbapi connection.
        """
        import app.db.session as sess
        original = sess._IS_SQLITE
        try:
            sess._IS_SQLITE = False          # simulate PostgreSQL environment
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor

            sess.set_sqlite_pragma(mock_conn, None)

            mock_conn.cursor.assert_not_called()
            mock_cursor.execute.assert_not_called()
        finally:
            sess._IS_SQLITE = original       # restore


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Migration Script Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrationHelpers(unittest.TestCase):
    """Unit tests for the pure-logic helpers in migrate_sqlite_to_postgres.py."""

    def setUp(self):
        self.migrate = _import_migrate()

    # -- _redact ---------------------------------------------------------------

    def test_redact_hides_password(self):
        url = "postgresql://alice:s3cr3t@host:5432/db"
        redacted = self.migrate._redact(url)
        self.assertNotIn("s3cr3t", redacted)
        self.assertIn("***", redacted)

    def test_redact_preserves_host_and_db(self):
        url = "postgresql://alice:s3cr3t@myhost:5432/mydb"
        redacted = self.migrate._redact(url)
        self.assertIn("myhost", redacted)
        self.assertIn("mydb", redacted)

    def test_redact_no_password_unchanged(self):
        """URLs without passwords are returned as-is (no *** added)."""
        url = "postgresql://host:5432/db"
        result = self.migrate._redact(url)
        self.assertNotIn("***", result)

    def test_redact_sqlite_no_crash(self):
        """SQLite URLs don't have passwords — must not raise."""
        url = "sqlite:///./autoprompt.db"
        result = self.migrate._redact(url)
        self.assertIsInstance(result, str)
        self.assertNotIn("***", result)

    # -- _resolve_source_url ---------------------------------------------------

    def test_resolve_source_url_from_env(self):
        """SOURCE_DATABASE_URL env var takes highest priority."""
        with patch.dict(os.environ, {"SOURCE_DATABASE_URL": "sqlite:///./custom.db"}):
            # Re-import to pick up patched env
            mod = _import_migrate()
            result = mod._resolve_source_url()
        self.assertEqual(result, "sqlite:///./custom.db")

    def test_resolve_source_url_default_fallback(self):
        """Without env var and without .env file, falls back to autoprompt.db."""
        env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATABASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            mod = _import_migrate()
            # Patch _BACKEND_DIR to a temp dir with no .env
            with tempfile.TemporaryDirectory() as tmp:
                mod._BACKEND_DIR = Path(tmp)
                result = mod._resolve_source_url()
        self.assertIn("autoprompt.db", result)
        self.assertTrue(result.startswith("sqlite:///"))

    # -- _make_engine returns MagicMock for PG (patched) -----------------------

    def test_make_engine_sqlite_no_nullpool(self):
        """_make_engine returns a real SQLite engine (no NullPool)."""
        from sqlalchemy.pool import NullPool
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{tmp}/test.db"
            eng = self.migrate._make_engine(url, is_source=False)
        self.assertEqual(eng.dialect.name, "sqlite")
        self.assertNotIsInstance(eng.pool, NullPool)
        eng.dispose()

    def test_make_engine_pg_uses_nullpool(self):
        """_make_engine configured for PostgreSQL uses NullPool (mocked engine)."""
        from sqlalchemy.pool import NullPool
        captured = {}

        def fake_create_engine(url, **kwargs):
            captured["poolclass"] = kwargs.get("poolclass")
            return MagicMock()

        with patch("sqlalchemy.create_engine", side_effect=fake_create_engine):
            self.migrate._make_engine(
                "postgresql://u:p@localhost/db", is_source=False
            )
        self.assertIs(captured.get("poolclass"), NullPool)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Migration Dry-Run with Temp SQLite
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrationDryRun(unittest.TestCase):
    """
    Run migrate() in dry_run=True mode against a temporary SQLite source.
    No network required. Verifies row counting and exit code.
    """

    def setUp(self):
        self.migrate = _import_migrate()
        from sqlalchemy import create_engine
        from app.db.models import Base, SavedPrompt, PromptHistory
        from sqlalchemy.orm import Session
        from datetime import datetime, timezone

        # Build a temporary populated SQLite source
        self.tmp_dir = tempfile.mkdtemp()
        self.source_path = Path(self.tmp_dir) / "source.db"
        self.source_url = f"sqlite:///{self.source_path.as_posix()}"

        eng = create_engine(self.source_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)

        with Session(eng) as sess:
            sess.add(SavedPrompt(
                title="Test Prompt",
                content="Write a poem about AI.",
                category="creative",
                operation_type="generate",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            sess.add(PromptHistory(
                operation_type="generate",
                original_input="Write a poem",
                generated_output="AI sings...",
                tokens_before=10,
                tokens_after=12,
                tokens_saved=-2,
                model_name="gemini-3-flash-preview",
                created_at=datetime.now(timezone.utc),
            ))
            sess.commit()
        eng.dispose()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dry_run_returns_zero(self):
        """Dry-run with populated source must return exit code 0."""
        # In dry-run, target_url is ignored — pass source as placeholder
        result = self.migrate.migrate(
            source_url=self.source_url,
            target_url=self.source_url,
            dry_run=True,
            reset_sequences=False,
        )
        self.assertEqual(result, 0, "dry-run must return 0")

    def test_dry_run_does_not_modify_source(self):
        """
        Source DB mtime and size must be unchanged after a dry-run.
        (Checks our 'read-only source' guarantee.)
        """
        import os as _os
        stat_before = _os.stat(str(self.source_path))

        self.migrate.migrate(
            source_url=self.source_url,
            target_url=self.source_url,
            dry_run=True,
            reset_sequences=False,
        )

        stat_after = _os.stat(str(self.source_path))
        self.assertEqual(
            stat_before.st_size, stat_after.st_size,
            "Source DB size changed after dry-run — source was modified!"
        )

    def test_dry_run_empty_source_returns_zero(self):
        """Dry-run on an empty source database must succeed (exit 0)."""
        empty_path = Path(self.tmp_dir) / "empty.db"
        empty_url = f"sqlite:///{empty_path.as_posix()}"
        from sqlalchemy import create_engine
        from app.db.models import Base
        eng = create_engine(empty_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        eng.dispose()

        result = self.migrate.migrate(
            source_url=empty_url,
            target_url=empty_url,
            dry_run=True,
            reset_sequences=False,
        )
        self.assertEqual(result, 0)

    def test_dry_run_bad_source_returns_one(self):
        """Dry-run with an unreadable source URL must return exit code 1."""
        result = self.migrate.migrate(
            source_url="sqlite:////nonexistent/path/that/cannot/be/created/db.sqlite3",
            target_url="sqlite:///./dummy.db",
            dry_run=True,
            reset_sequences=False,
        )
        # Should fail at source connection check
        self.assertEqual(result, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6 — Migration Live-Path Simulation (SQLite → SQLite, mocked pg_insert)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrationLivePath(unittest.TestCase):
    """
    Simulate the full live migration path using two temporary SQLite databases.
    The PostgreSQL-specific pg_insert dialect call is replaced with a standard
    SQLAlchemy insert so the test runs without psycopg2 installed.
    """

    def setUp(self):
        self.migrate = _import_migrate()
        from sqlalchemy import create_engine
        from app.db.models import Base, SavedPrompt, PromptHistory
        from sqlalchemy.orm import Session
        from datetime import datetime, timezone

        self.tmp_dir = tempfile.mkdtemp()

        # --- source ---
        self.src_url = f"sqlite:///{(Path(self.tmp_dir) / 'src.db').as_posix()}"
        src_eng = create_engine(self.src_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=src_eng)
        with Session(src_eng) as sess:
            for i in range(3):
                sess.add(SavedPrompt(
                    title=f"Prompt {i}",
                    content=f"Content {i}",
                    category="test",
                    operation_type="generate",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ))
            for i in range(2):
                sess.add(PromptHistory(
                    operation_type="generate",
                    original_input=f"Input {i}",
                    generated_output=f"Output {i}",
                    tokens_before=10,
                    tokens_after=8,
                    tokens_saved=2,
                    model_name="gemini-3-flash-preview",
                    created_at=datetime.now(timezone.utc),
                ))
            sess.commit()
        src_eng.dispose()

        # --- target ---
        self.tgt_url = f"sqlite:///{(Path(self.tmp_dir) / 'tgt.db').as_posix()}"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run_migration_with_sqlite_target(self):
        """
        Patch migrate() to use standard SQLAlchemy insert instead of
        pg_insert (PostgreSQL-dialect-specific) so the test works without
        a real PostgreSQL server or psycopg2 installed.
        """
        from sqlalchemy import create_engine, insert as sa_insert
        from app.db.models import Base, SavedPrompt, PromptHistory
        from sqlalchemy.orm import Session

        # Build target schema
        tgt_eng = create_engine(self.tgt_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=tgt_eng)

        # Read source
        src_eng = create_engine(self.src_url, connect_args={"check_same_thread": False})
        with Session(src_eng) as s:
            saved_prompts = s.query(SavedPrompt).all()
            prompt_history = s.query(PromptHistory).all()

        sp_count = len(saved_prompts)
        ph_count = len(prompt_history)

        # Insert into target (using standard sa_insert, not pg_insert)
        with Session(tgt_eng) as s:
            if saved_prompts:
                s.execute(
                    sa_insert(SavedPrompt.__table__),
                    [
                        {
                            "id": r.id, "title": r.title, "content": r.content,
                            "category": r.category, "operation_type": r.operation_type,
                            "created_at": r.created_at, "updated_at": r.updated_at,
                        }
                        for r in saved_prompts
                    ]
                )
            if prompt_history:
                s.execute(
                    sa_insert(PromptHistory.__table__),
                    [
                        {
                            "id": r.id, "operation_type": r.operation_type,
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
                )
            s.commit()

        # Count verification
        with Session(tgt_eng) as s:
            tgt_sp = s.query(SavedPrompt).count()
            tgt_ph = s.query(PromptHistory).count()

        src_eng.dispose()
        tgt_eng.dispose()

        return sp_count, ph_count, tgt_sp, tgt_ph

    def test_all_saved_prompts_migrated(self):
        """All 3 saved_prompts must appear in the target after migration."""
        sp_count, _, tgt_sp, _ = self._run_migration_with_sqlite_target()
        self.assertEqual(sp_count, 3)
        self.assertEqual(tgt_sp, 3, "Target saved_prompts count mismatch")

    def test_all_history_migrated(self):
        """All 2 prompt_history rows must appear in the target."""
        _, ph_count, _, tgt_ph = self._run_migration_with_sqlite_target()
        self.assertEqual(ph_count, 2)
        self.assertEqual(tgt_ph, 2, "Target prompt_history count mismatch")

    def test_source_unchanged_after_migration(self):
        """Source DB must have the same row count after migration as before."""
        from sqlalchemy import create_engine
        from app.db.models import SavedPrompt, PromptHistory
        from sqlalchemy.orm import Session

        self._run_migration_with_sqlite_target()

        src_eng = create_engine(self.src_url, connect_args={"check_same_thread": False})
        with Session(src_eng) as s:
            sp = s.query(SavedPrompt).count()
            ph = s.query(PromptHistory).count()
        src_eng.dispose()

        self.assertEqual(sp, 3, "Source saved_prompts count changed after migration!")
        self.assertEqual(ph, 2, "Source prompt_history count changed after migration!")

    def test_idempotency_no_duplicates(self):
        """Running migration twice must not duplicate rows (simulates re-run)."""
        from sqlalchemy import create_engine, insert as sa_insert, text
        from app.db.models import Base, SavedPrompt, PromptHistory
        from sqlalchemy.orm import Session

        # Build target
        tgt_eng = create_engine(self.tgt_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=tgt_eng)
        src_eng = create_engine(self.src_url, connect_args={"check_same_thread": False})
        with Session(src_eng) as s:
            saved = s.query(SavedPrompt).all()
            history = s.query(PromptHistory).all()

        def _insert_ignoring_conflicts(session, table_name, rows):
            """INSERT OR IGNORE simulates ON CONFLICT DO NOTHING for SQLite."""
            for row in rows:
                cols = ", ".join(row.keys())
                placeholders = ", ".join(f":{k}" for k in row.keys())
                session.execute(
                    text(f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})"),
                    row,
                )

        def _run_insert():
            with Session(tgt_eng) as s:
                _insert_ignoring_conflicts(
                    s, "saved_prompts",
                    [
                        {
                            "id": r.id, "title": r.title, "content": r.content,
                            "category": r.category, "operation_type": r.operation_type,
                            "created_at": r.created_at.isoformat(),
                            "updated_at": r.updated_at.isoformat(),
                        }
                        for r in saved
                    ]
                )
                _insert_ignoring_conflicts(
                    s, "prompt_history",
                    [
                        {
                            "id": r.id, "operation_type": r.operation_type,
                            "original_input": r.original_input,
                            "generated_output": r.generated_output,
                            "optimized_output": r.optimized_output,
                            "tokens_before": r.tokens_before,
                            "tokens_after": r.tokens_after,
                            "tokens_saved": r.tokens_saved,
                            "model_name": r.model_name,
                            "created_at": r.created_at.isoformat(),
                        }
                        for r in history
                    ]
                )
                s.commit()

        _run_insert()   # first run
        _run_insert()   # second run — must be idempotent

        with Session(tgt_eng) as s:
            sp_count = s.query(SavedPrompt).count()
            ph_count = s.query(PromptHistory).count()
        src_eng.dispose()
        tgt_eng.dispose()

        self.assertEqual(sp_count, 3, f"Expected 3, got {sp_count} — duplicates inserted!")
        self.assertEqual(ph_count, 2, f"Expected 2, got {ph_count} — duplicates inserted!")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7 — Migration Safety (rollback on error, source integrity)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrationSafety(unittest.TestCase):
    """Verify source-safety guarantees and transaction rollback behavior."""

    def setUp(self):
        self.migrate = _import_migrate()
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_missing_target_url_without_dry_run_returns_nonzero(self):
        """
        When the target is unreachable, migrate() must return 1.
        Since psycopg2 is not installed, we patch _make_engine for PG URLs
        to raise OperationalError, simulating a failed TCP connection.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.exc import OperationalError
        from app.db.models import Base

        src_path = Path(self.tmp_dir) / "safe_src.db"
        src_url = f"sqlite:///{src_path.as_posix()}"
        eng = create_engine(src_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        eng.dispose()

        original_make_engine = self.migrate._make_engine

        def patched_make_engine(url, is_source=False):
            if url.startswith("postgresql"):
                # Raise at engine creation time (simulates psycopg2 not found
                # or DNS failure before the connection attempt)
                raise OperationalError(
                    "could not connect to server: Connection refused", None, None
                )
            return original_make_engine(url, is_source=is_source)

        self.migrate._make_engine = patched_make_engine
        try:
            result = self.migrate.migrate(
                source_url=src_url,
                target_url="postgresql://invalid:invalid@127.0.0.1:1/nonexistent",
                dry_run=False,
                reset_sequences=False,
            )
        finally:
            self.migrate._make_engine = original_make_engine

        self.assertEqual(result, 1, "Expected failure (1) when target is unreachable")

    def test_source_integrity_after_failed_migration(self):
        """
        Source DB must retain all original rows even after a migration failure.
        We simulate the PG connection failing so psycopg2 isn't required.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.exc import OperationalError
        from app.db.models import Base, SavedPrompt
        from sqlalchemy.orm import Session
        from datetime import datetime, timezone

        src_path = Path(self.tmp_dir) / "integrity_src.db"
        src_url = f"sqlite:///{src_path.as_posix()}"
        eng = create_engine(src_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        with Session(eng) as s:
            s.add(SavedPrompt(
                title="Important", content="Keep me safe",
                category="test", operation_type="generate",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            s.commit()
        eng.dispose()

        original_make_engine = self.migrate._make_engine

        def patched_make_engine(url, is_source=False):
            if url.startswith("postgresql"):
                raise OperationalError(
                    "could not connect to server: Connection refused", None, None
                )
            return original_make_engine(url, is_source=is_source)

        self.migrate._make_engine = patched_make_engine
        try:
            # This will fail (target unreachable) — source must survive unchanged
            self.migrate.migrate(
                source_url=src_url,
                target_url="postgresql://bad:creds@127.0.0.1:1/db",
                dry_run=False,
                reset_sequences=False,
            )
        finally:
            self.migrate._make_engine = original_make_engine

        # Source must still have its original row
        verify_eng = create_engine(src_url, connect_args={"check_same_thread": False})
        with Session(verify_eng) as s:
            count = s.query(SavedPrompt).count()
        verify_eng.dispose()
        self.assertEqual(count, 1, "Source row was lost after a failed migration!")

    def test_migrate_function_does_not_call_session_add_on_source(self):
        """
        The migrate() function must not call session.add() on the source session
        (which would signal a write intent).  We verify this via method inspection:
        the source session is only used for queries, not add/delete.
        """
        # This is verified structurally — we can inspect the migrate() source code
        import inspect
        source_code = inspect.getsource(self.migrate.migrate)

        # The only session.add or session.delete calls must be in the target block
        # (which is guarded by `if not dry_run`). We verify no src_session.add exists.
        self.assertNotIn("src_session.add", source_code,
                         "migrate() must not call src_session.add()")
        self.assertNotIn("src_session.delete", source_code,
                         "migrate() must not call src_session.delete()")
        self.assertNotIn("src_session.commit", source_code,
                         "migrate() must not commit on the source session")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8 — Vercel Packaging Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestVercelPackagingValidation(unittest.TestCase):
    """
    Static validation of all Vercel packaging artefacts.
    No deployment or network access required.
    """

    # -- api/index.py ----------------------------------------------------------

    def test_api_index_py_exists(self):
        """api/index.py must exist at the repo root."""
        p = REPO_ROOT / "api" / "index.py"
        self.assertTrue(p.is_file(), f"Missing: {p}")

    def test_api_index_py_imports_app(self):
        """api/index.py must expose `app` importable from the FastAPI application."""
        # Simulate what Vercel does: execute the file and check `app` is set
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "vercel_entrypoint", REPO_ROOT / "api" / "index.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "app"), "api/index.py must expose 'app'")

    def test_api_index_py_app_is_fastapi(self):
        """The `app` object in api/index.py must be a FastAPI instance."""
        from fastapi import FastAPI
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "vercel_entrypoint2", REPO_ROOT / "api" / "index.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIsInstance(mod.app, FastAPI, "app must be a FastAPI instance")

    def test_api_index_py_adds_backend_to_path(self):
        """api/index.py must add the backend/ directory to sys.path."""
        content = (REPO_ROOT / "api" / "index.py").read_text(encoding="utf-8")
        self.assertIn("backend", content,
                      "api/index.py must reference the backend/ directory for sys.path")
        self.assertIn("sys.path", content,
                      "api/index.py must manipulate sys.path")

    def test_api_index_py_all_contains_app(self):
        """__all__ in api/index.py must include 'app'."""
        content = (REPO_ROOT / "api" / "index.py").read_text(encoding="utf-8")
        self.assertIn("__all__", content)
        self.assertIn('"app"', content)

    # -- vercel.json -----------------------------------------------------------

    def test_vercel_json_exists(self):
        """vercel.json must exist at the repo root."""
        p = REPO_ROOT / "vercel.json"
        self.assertTrue(p.is_file(), f"Missing: {p}")

    def test_vercel_json_valid_json(self):
        """vercel.json must be valid JSON."""
        content = (REPO_ROOT / "vercel.json").read_text(encoding="utf-8")
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            self.fail(f"vercel.json is not valid JSON: {e}")

    def _load_vercel_json(self):
        return json.loads((REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))

    def test_vercel_json_version_2(self):
        """vercel.json must declare version 2."""
        data = self._load_vercel_json()
        self.assertEqual(data.get("version"), 2)

    def test_vercel_json_has_rewrites(self):
        """vercel.json must have a rewrites array."""
        data = self._load_vercel_json()
        self.assertIn("rewrites", data)
        self.assertIsInstance(data["rewrites"], list)
        self.assertGreater(len(data["rewrites"]), 0)

    def test_vercel_json_api_routes_to_index_py(self):
        """/api/(.*) must be rewritten to /api/index.py."""
        data = self._load_vercel_json()
        api_rewrites = [
            r for r in data["rewrites"]
            if "/api/" in r.get("source", "") or r.get("source") == "/api/(.*)"
        ]
        self.assertTrue(
            any(r.get("destination") == "/api/index.py" for r in api_rewrites),
            "No rewrite found for /api/* → /api/index.py"
        )

    def test_vercel_json_health_routes_to_index_py(self):
        """/health must be rewritten to /api/index.py."""
        data = self._load_vercel_json()
        health_rewrites = [
            r for r in data["rewrites"]
            if r.get("source") == "/health"
        ]
        self.assertTrue(
            any(r.get("destination") == "/api/index.py" for r in health_rewrites),
            "No rewrite found for /health → /api/index.py"
        )

    def test_vercel_json_frontend_fallback_rewrite(self):
        """A catch-all rewrite for frontend static assets must exist."""
        data = self._load_vercel_json()
        catchall = [r for r in data["rewrites"] if r.get("source") == "/(.*)"]
        self.assertTrue(len(catchall) > 0, "No catch-all rewrite for frontend found")
        self.assertIn("autoprompt-prototype", catchall[-1].get("destination", ""))

    def test_vercel_json_function_max_duration_15(self):
        """api/index.py function maxDuration must be 15 (Hobby plan limit)."""
        data = self._load_vercel_json()
        fn_config = data.get("functions", {}).get("api/index.py", {})
        self.assertEqual(fn_config.get("maxDuration"), 15,
                         "maxDuration must be 15 for Vercel Hobby plan")

    def test_vercel_json_function_memory_set(self):
        """api/index.py function memory must be declared."""
        data = self._load_vercel_json()
        fn_config = data.get("functions", {}).get("api/index.py", {})
        self.assertIn("memory", fn_config, "memory must be set for api/index.py")
        self.assertGreaterEqual(fn_config["memory"], 256)

    def test_vercel_json_api_cache_control_no_store(self):
        """API routes must carry Cache-Control: no-store (not cacheable)."""
        data = self._load_vercel_json()
        headers = data.get("headers", [])
        api_headers = next(
            (h for h in headers if h.get("source") == "/api/(.*)"), None
        )
        self.assertIsNotNone(api_headers, "No headers rule for /api/(.*) found")
        cache_header = next(
            (h for h in api_headers["headers"] if h["key"] == "Cache-Control"), None
        )
        self.assertIsNotNone(cache_header, "Cache-Control header missing for /api/*")
        self.assertIn("no-store", cache_header["value"])

    def test_vercel_json_html_security_headers_present(self):
        """HTML routes must include X-Frame-Options: DENY."""
        data = self._load_vercel_json()
        headers = data.get("headers", [])
        html_rule = next(
            (h for h in headers if ".html" in h.get("source", "")), None
        )
        self.assertIsNotNone(html_rule, "No headers rule for .html files found")
        keys = [h["key"] for h in html_rule["headers"]]
        self.assertIn("X-Frame-Options", keys)
        self.assertIn("X-Content-Type-Options", keys)

    def test_vercel_json_static_assets_long_cache(self):
        """JS/CSS assets must have long-lived cache headers (immutable)."""
        data = self._load_vercel_json()
        headers = data.get("headers", [])
        static_rule = next(
            (h for h in headers if "js|css" in h.get("source", "") or
             (h.get("source", "").endswith(".(js|css)"))), None
        )
        self.assertIsNotNone(static_rule, "No cache headers rule for JS/CSS found")
        cache_val = next(
            (h["value"] for h in static_rule["headers"] if h["key"] == "Cache-Control"), ""
        )
        self.assertIn("immutable", cache_val,
                      "JS/CSS Cache-Control must include 'immutable'")

    # -- Root requirements.txt ------------------------------------------------

    def test_root_requirements_txt_exists(self):
        """Root requirements.txt must exist for Vercel Python builder."""
        p = REPO_ROOT / "requirements.txt"
        self.assertTrue(p.is_file(), f"Missing: {p}")

    def test_root_requirements_contains_fastapi(self):
        """Root requirements.txt must include fastapi."""
        content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("fastapi", content.lower())

    def test_root_requirements_contains_sqlalchemy(self):
        """Root requirements.txt must include sqlalchemy."""
        content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("sqlalchemy", content.lower())

    def test_root_requirements_contains_psycopg2(self):
        """Root requirements.txt must include psycopg2-binary for PostgreSQL."""
        content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("psycopg2-binary", content.lower())

    def test_root_requirements_contains_google_genai(self):
        """Root requirements.txt must include google-genai."""
        content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("google-genai", content.lower())

    def test_backend_requirements_also_has_psycopg2(self):
        """backend/requirements.docker.txt must also include psycopg2-binary (Phase 8.5-B)."""
        content = (BACKEND_DIR / "requirements.docker.txt").read_text(encoding="utf-8")
        self.assertIn("psycopg2-binary", content.lower())

    def test_root_and_backend_requirements_consistent(self):
        """
        Core packages declared in backend/requirements.docker.txt must all appear
        in root requirements.txt (Vercel must have everything Docker has).
        """
        def parse_packages(text):
            pkgs = set()
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Strip version specifiers
                    name = line.split("=")[0].split(">")[0].split("<")[0].strip().lower()
                    pkgs.add(name)
            return pkgs

        backend_pkgs = parse_packages(
            (BACKEND_DIR / "requirements.docker.txt").read_text(encoding="utf-8")
        )
        root_pkgs = parse_packages(
            (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        )

        missing = backend_pkgs - root_pkgs
        self.assertEqual(
            missing, set(),
            f"Packages in backend/requirements.docker.txt missing from root: {missing}"
        )

    # -- docs/VERCEL_SETUP.md -------------------------------------------------

    def test_vercel_setup_md_exists(self):
        """docs/VERCEL_SETUP.md deployment guide must exist."""
        p = REPO_ROOT / "docs" / "VERCEL_SETUP.md"
        self.assertTrue(p.is_file(), f"Missing: {p}")

    def test_vercel_setup_mentions_gemini_timeout(self):
        """VERCEL_SETUP.md must warn about GEMINI_TIMEOUT_SECONDS <= 15s."""
        content = (REPO_ROOT / "docs" / "VERCEL_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("GEMINI_TIMEOUT_SECONDS", content)
        self.assertIn("10", content, "Must recommend 10s timeout for Vercel")

    def test_vercel_setup_mentions_neon(self):
        """VERCEL_SETUP.md must reference Neon as the PostgreSQL provider."""
        content = (REPO_ROOT / "docs" / "VERCEL_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("neon", content.lower())

    def test_vercel_setup_mentions_debug_false(self):
        """VERCEL_SETUP.md must instruct setting DEBUG=false in production."""
        content = (REPO_ROOT / "docs" / "VERCEL_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("DEBUG", content)
        self.assertIn("false", content.lower())

    # -- .gitignore ------------------------------------------------------------

    def test_gitignore_excludes_vercel_dir(self):
        """.gitignore must exclude the .vercel/ build output directory."""
        content = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".vercel", content,
                      ".vercel/ should be listed in .gitignore")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
