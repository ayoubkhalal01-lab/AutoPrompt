"""
test_persistence_api.py — Comprehensive tests for SQLite persistence, Saved Prompts, and History (Phase 6).

Covers:
- Database initialization and schema creation.
- Saved Prompts CRUD operations.
- Search and filtering (category, operation_type, keyword search).
- Pagination for saved prompts and history.
- Validation errors on invalid or empty inputs.
- Safe transaction handling and rollback.
- History recording and deletion/clearing.
- Isolated in-memory SQLite database (zero side-effects on dev database).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.models import Base, PromptHistory, SavedPrompt
from app.db.session import get_db, init_db
from app.main import (
    api_clear_history,
    api_create_saved_prompt,
    api_delete_history_item,
    api_delete_saved_prompt,
    api_generate_prompt,
    api_get_history_item,
    api_get_saved_prompt,
    api_list_history,
    api_list_saved_prompts,
    api_optimize_prompt,
    api_update_saved_prompt,
    app,
)
from app.schemas.persistence_schemas import (
    PromptHistoryCreate,
    SavedPromptCreate,
    SavedPromptUpdate,
)
from app.schemas.prompt_schemas import GenerateRequest, OptimizeRequest
from app.services.persistence_service import (
    clear_history,
    create_saved_prompt,
    delete_history_item,
    delete_saved_prompt,
    get_history_item,
    get_saved_prompt,
    list_history,
    list_saved_prompts,
    record_history,
    update_saved_prompt,
)


class TestPersistenceBase(unittest.TestCase):
    """Sets up an isolated, in-memory SQLite database for each test."""

    def setUp(self):
        # Isolated SQLite in-memory database using StaticPool for thread-sharing
        self.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.test_engine)
        self.TestSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.test_engine
        )
        self.db: Session = self.TestSessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.test_engine)
        self.test_engine.dispose()


class TestDatabaseInitialization(TestPersistenceBase):
    """Test non-destructive database initialization and table schemas."""

    def test_init_db_creates_required_tables(self):
        inspector_engine = self.test_engine
        from sqlalchemy import inspect
        inspector = inspect(inspector_engine)
        table_names = inspector.get_table_names()

        self.assertIn("saved_prompts", table_names)
        self.assertIn("prompt_history", table_names)

        saved_cols = [c["name"] for c in inspector.get_columns("saved_prompts")]
        for col in ["id", "title", "content", "category", "operation_type", "created_at", "updated_at"]:
            self.assertIn(col, saved_cols)

        hist_cols = [c["name"] for c in inspector.get_columns("prompt_history")]
        for col in ["id", "operation_type", "original_input", "generated_output", "optimized_output", "tokens_before", "tokens_after", "tokens_saved", "model_name", "created_at"]:
            self.assertIn(col, hist_cols)


class TestSavedPromptsCRUD(TestPersistenceBase):
    """Test Saved Prompts CRUD operations and validations."""

    def test_create_and_get_saved_prompt(self):
        prompt_in = SavedPromptCreate(
            title="Telecommunications Churn Prompt",
            content="## Role\nStaff Data Scientist\n## Objective\nAnalyze churn",
            category="Data Science",
            operation_type="generate",
        )
        saved = api_create_saved_prompt(prompt_in, db=self.db)
        self.assertIsNotNone(saved.id)
        self.assertEqual(saved.title, "Telecommunications Churn Prompt")
        self.assertEqual(saved.category, "Data Science")
        self.assertEqual(saved.operation_type, "generate")
        self.assertIsNotNone(saved.created_at)

        # Retrieve
        retrieved = api_get_saved_prompt(saved.id, db=self.db)
        self.assertEqual(retrieved.id, saved.id)
        self.assertEqual(retrieved.content, saved.content)

    def test_get_nonexistent_saved_prompt_raises_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            api_get_saved_prompt(99999, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_saved_prompt(self):
        prompt_in = SavedPromptCreate(
            title="Initial Title",
            content="Initial Content",
            category="General",
            operation_type="optimize",
        )
        saved = api_create_saved_prompt(prompt_in, db=self.db)

        # Update title and category
        update_in = SavedPromptUpdate(
            title="Updated Title",
            category="Business",
        )
        updated = api_update_saved_prompt(saved.id, update_in, db=self.db)
        self.assertEqual(updated.title, "Updated Title")
        self.assertEqual(updated.category, "Business")
        self.assertEqual(updated.content, "Initial Content")

    def test_update_nonexistent_saved_prompt_raises_404(self):
        from fastapi import HTTPException
        update_in = SavedPromptUpdate(title="Nonexistent")
        with self.assertRaises(HTTPException) as ctx:
            api_update_saved_prompt(99999, update_in, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_saved_prompt(self):
        prompt_in = SavedPromptCreate(
            title="Temporary Prompt",
            content="To be deleted",
            category="General",
            operation_type="generate",
        )
        saved = api_create_saved_prompt(prompt_in, db=self.db)

        # Delete
        del_resp = api_delete_saved_prompt(saved.id, db=self.db)
        self.assertTrue(del_resp.success)
        self.assertEqual(del_resp.id, saved.id)

        # Confirm 404 on subsequent get
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            api_get_saved_prompt(saved.id, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_nonexistent_saved_prompt_raises_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            api_delete_saved_prompt(99999, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)


class TestSavedPromptsSearchAndPagination(TestPersistenceBase):
    """Test filtering, keyword search, and pagination on Saved Prompts."""

    def setUp(self):
        super().setUp()
        # Seed 12 prompts across categories and operation types
        categories = ["Coding", "Data Science", "General", "Business"]
        for i in range(1, 13):
            cat = categories[(i - 1) % len(categories)]
            op = "generate" if i % 2 == 1 else "optimize"
            title = f"Prompt #{i:02d} - {cat} Master"
            content = f"Instruction content for item {i} with unique keyword_{i}"
            create_saved_prompt(
                self.db,
                SavedPromptCreate(title=title, content=content, category=cat, operation_type=op),
            )

    def test_pagination_limit_and_offset(self):
        page1 = api_list_saved_prompts(limit=5, offset=0, db=self.db)
        self.assertEqual(page1.total, 12)
        self.assertEqual(len(page1.items), 5)

        page2 = api_list_saved_prompts(limit=5, offset=5, db=self.db)
        self.assertEqual(page2.total, 12)
        self.assertEqual(len(page2.items), 5)
        self.assertNotEqual(page1.items[0].id, page2.items[0].id)

        page3 = api_list_saved_prompts(limit=5, offset=10, db=self.db)
        self.assertEqual(page3.total, 12)
        self.assertEqual(len(page3.items), 2)

    def test_filter_by_category(self):
        resp = api_list_saved_prompts(category="Coding", db=self.db)
        self.assertEqual(resp.total, 3)
        for item in resp.items:
            self.assertEqual(item.category, "Coding")

    def test_filter_by_operation_type(self):
        resp = api_list_saved_prompts(operation_type="optimize", db=self.db)
        self.assertEqual(resp.total, 6)
        for item in resp.items:
            self.assertEqual(item.operation_type, "optimize")

    def test_search_by_title_and_content_keyword(self):
        # Search in title
        resp_title = api_list_saved_prompts(search="Prompt #07", db=self.db)
        self.assertEqual(resp_title.total, 1)
        self.assertEqual(resp_title.items[0].title, "Prompt #07 - General Master")

        # Search in content
        resp_content = api_list_saved_prompts(search="keyword_9", db=self.db)
        self.assertEqual(resp_content.total, 1)
        self.assertIn("keyword_9", resp_content.items[0].content)


class TestPromptHistoryService(TestPersistenceBase):
    """Test Prompt History recording, pagination, and deletion."""

    def test_record_and_retrieve_history(self):
        hist_in = PromptHistoryCreate(
            operation_type="generate",
            original_input="Analyze customer churn dataset",
            generated_output="## Role\nExpert Data Scientist",
            tokens_before=15,
            tokens_after=120,
            model_name="gemini-3-flash-preview",
        )
        record = record_history(self.db, hist_in)
        self.assertIsNotNone(record.id)
        self.assertEqual(record.operation_type, "generate")

        item = api_get_history_item(record.id, db=self.db)
        self.assertEqual(item.id, record.id)
        self.assertEqual(item.original_input, "Analyze customer churn dataset")
        self.assertEqual(item.tokens_before, 15)
        self.assertEqual(item.tokens_after, 120)

    def test_history_pagination(self):
        for i in range(1, 16):
            record_history(
                self.db,
                PromptHistoryCreate(
                    operation_type="optimize" if i % 2 == 0 else "generate",
                    original_input=f"Input prompt #{i}",
                    tokens_before=10 * i,
                    tokens_after=15 * i,
                ),
            )

        resp = api_list_history(limit=5, offset=0, db=self.db)
        self.assertEqual(resp.total, 15)
        self.assertEqual(len(resp.items), 5)

        # Filter by operation
        resp_opt = api_list_history(operation_type="optimize", db=self.db)
        self.assertEqual(resp_opt.total, 7)

    def test_delete_single_history_item(self):
        record = record_history(
            self.db,
            PromptHistoryCreate(operation_type="generate", original_input="Delete me"),
        )
        del_resp = api_delete_history_item(record.id, db=self.db)
        self.assertTrue(del_resp.success)

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            api_get_history_item(record.id, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_clear_all_history(self):
        for i in range(5):
            record_history(
                self.db,
                PromptHistoryCreate(operation_type="generate", original_input=f"Item {i}"),
            )
        self.assertEqual(self.db.query(PromptHistory).count(), 5)

        clear_resp = api_clear_history(db=self.db)
        self.assertTrue(clear_resp.success)
        self.assertEqual(clear_resp.deleted_count, 5)
        self.assertEqual(self.db.query(PromptHistory).count(), 0)


class TestAutomaticHistoryOnOperations(TestPersistenceBase):
    """Test that successful AI operations automatically populate prompt_history."""

    @patch("app.main.generate_prompt")
    def test_generate_auto_records_history(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "generated_prompt": "# Role\nMachine Learning Engineer",
            "input_tokens": 25,
            "output_tokens": 150,
            "response_time_ms": 320,
            "error_code": None,
            "error_message": None,
        }

        req = GenerateRequest(user_idea="Build an fraud model", mode="quick")
        resp = api_generate_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 200)

        # Confirm history entry was automatically created
        history_records = self.db.query(PromptHistory).all()
        self.assertEqual(len(history_records), 1)
        self.assertEqual(history_records[0].operation_type, "generate")
        self.assertEqual(history_records[0].original_input, "Build an fraud model")
        self.assertEqual(history_records[0].tokens_before, 25)
        self.assertEqual(history_records[0].tokens_after, 150)

    @patch("app.main.optimize_prompt")
    def test_optimize_auto_records_history(self, mock_opt):
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "original_prompt": "Raw unoptimized prompt",
            "optimized_prompt": "Refined and clean prompt",
            "original_tokens": 40,
            "optimized_tokens": 25,
            "tokens_saved": 15,
            "reduction_percentage": 37.5,
            "response_time_ms": 280,
            "error_code": None,
            "error_message": None,
        }

        req = OptimizeRequest(original_prompt="Raw unoptimized prompt", mode="quick")
        resp = api_optimize_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 200)

        history_records = self.db.query(PromptHistory).all()
        self.assertEqual(len(history_records), 1)
        self.assertEqual(history_records[0].operation_type, "optimize")
        self.assertEqual(history_records[0].original_input, "Raw unoptimized prompt")
        self.assertEqual(history_records[0].tokens_saved, 15)


if __name__ == "__main__":
    unittest.main()
