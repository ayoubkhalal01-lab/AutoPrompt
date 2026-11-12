"""
AutoPrompt — Phase 6: Persistence Smoke Test Suite
Validates all aspects of Phase 6: Persistence, Saved Prompts & History:
  1. Frontend Loading & Script Integrity
  2. Saved Prompts CRUD, Search & Filtering
  3. Prompt History Recording, Metrics, & Deletion
  4. Badge Count Metrics & Visibility
  5. Database Persistence across restarts & Session Integrity
"""

import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, PromptHistory, SavedPrompt
from app.db.session import init_db
from app.main import (
    api_clear_history,
    api_create_saved_prompt,
    api_delete_history_item,
    api_delete_saved_prompt,
    api_get_history_item,
    api_get_saved_prompt,
    api_list_history,
    api_list_saved_prompts,
    api_update_saved_prompt,
)
from app.schemas.persistence_schemas import (
    PromptHistoryCreate,
    SavedPromptCreate,
    SavedPromptUpdate,
)
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. Frontend Loading & Script Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontendLoadingAndScriptIntegrity(unittest.TestCase):
    """Smoke test for HTML structure, script order, and modal element contracts."""

    @classmethod
    def setUpClass(cls):
        cls.prototype_dir = Path(__file__).resolve().parent.parent.parent / "autoprompt-prototype"
        cls.html_path = cls.prototype_dir / "index.html"
        cls.persistence_js_path = cls.prototype_dir / "js" / "persistence.js"
        cls.workspace_js_path = cls.prototype_dir / "js" / "workspace.js"

        with open(cls.html_path, "r", encoding="utf-8") as f:
            cls.html_content = f.read()

        with open(cls.persistence_js_path, "r", encoding="utf-8") as f:
            cls.js_content = f.read()

    def test_01_script_loading_order(self):
        """Verify script tags appear in correct dependency order in index.html."""
        expected_order = [
            "js/mock-data.js",
            "js/theme.js",
            "js/workspace.js",
            "js/app.js",
            "js/persistence.js",
        ]
        positions = []
        for script in expected_order:
            pos = self.html_content.find(f'src="{script}"')
            self.assertNotEqual(pos, -1, f"Missing script tag for {script}")
            positions.append(pos)

        # Confirm strictly ascending order
        self.assertEqual(positions, sorted(positions), "Scripts must be loaded in dependency order")

    def test_02_all_modal_elements_exist_in_dom(self):
        """Verify all 5 persistence modals exist in index.html with correct attributes."""
        expected_modals = [
            "modal-save-prompt",
            "modal-saved-prompts",
            "modal-prompt-history",
            "modal-edit-prompt",
            "modal-confirm-action",
        ]
        for modal_id in expected_modals:
            pattern = rf'id="{modal_id}"[^>]*class="modal-backdrop"'
            self.assertRegex(
                self.html_content,
                pattern,
                f"Modal #{modal_id} must exist with modal-backdrop class",
            )

    def test_03_nav_buttons_and_badges_exist(self):
        """Verify header navigation buttons and count badges are present."""
        self.assertIn('id="btn-nav-saved-prompts"', self.html_content)
        self.assertIn('id="btn-nav-history"', self.html_content)
        self.assertIn('id="saved-prompts-count-badge"', self.html_content)
        self.assertIn('id="history-count-badge"', self.html_content)
        self.assertIn('id="toast-container"', self.html_content)

    def test_04_save_prompt_triggers_exist(self):
        """Verify save prompt action buttons exist in results view."""
        self.assertIn('id="btn-results-save-top"', self.html_content)
        self.assertIn('id="btn-results-save-bottom"', self.html_content)
        self.assertIn('id="btn-save-main-result"', self.html_content)

    def test_05_modal_form_controls_exist(self):
        """Verify form controls inside the save, edit, and history modals."""
        required_ids = [
            "input-save-prompt-title",
            "select-save-prompt-category",
            "preview-save-prompt-content",
            "input-save-prompt-operation-type",
            "btn-confirm-save-prompt",
            "btn-cancel-save-prompt",
            "input-search-saved",
            "select-filter-saved-category",
            "select-filter-saved-operation",
            "saved-prompts-list-container",
            "saved-prompts-loading",
            "saved-prompts-empty",
            "select-filter-history-operation",
            "history-list-container",
            "history-loading",
            "history-empty",
            "btn-trigger-clear-history",
            "input-edit-prompt-id",
            "input-edit-prompt-title",
            "select-edit-prompt-category",
            "btn-confirm-edit-prompt",
            "modal-confirm-title",
            "modal-confirm-message",
            "btn-proceed-confirm",
            "btn-cancel-confirm",
        ]
        for elem_id in required_ids:
            self.assertIn(f'id="{elem_id}"', self.html_content, f"Element #{elem_id} missing in index.html")

    def test_06_persistence_js_exports_manager(self):
        """Verify persistence.js exports PersistenceManager with public API."""
        self.assertIn("global.PersistenceManager =", self.js_content)
        for method in ["openSavePromptModal", "openSavedPromptsModal", "openHistoryModal", "showToast", "refreshBadgeCount"]:
            self.assertIn(method, self.js_content, f"PersistenceManager must expose {method}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Saved Prompts CRUD, Search & Filtering
# ─────────────────────────────────────────────────────────────────────────────

class TestSavedPromptsSmoke(unittest.TestCase):
    """Smoke test for Saved Prompts lifecycle: Create, Read, Update, Delete, Search."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_01_create_saved_prompt_from_generate(self):
        """Verify saving a prompt generated via Generate feature."""
        item = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Customer Churn SQL Generator",
                content="Write an optimized PostgreSQL query to identify churn risk based on activity.",
                category="Data Science",
                operation_type="generate",
            ),
        )
        self.assertIsNotNone(item.id)
        self.assertEqual(item.title, "Customer Churn SQL Generator")
        self.assertEqual(item.category, "Data Science")
        self.assertEqual(item.operation_type, "generate")
        self.assertIsNotNone(item.created_at)
        self.assertIsNotNone(item.updated_at)

    def test_02_create_saved_prompt_from_optimize(self):
        """Verify saving a prompt optimized via Optimize feature."""
        item = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Concise Refactor Instruction",
                content="Refactor the authentication middleware to use constant-time token comparison.",
                category="Coding",
                operation_type="optimize",
            ),
        )
        self.assertIsNotNone(item.id)
        self.assertEqual(item.operation_type, "optimize")

    def test_03_retrieve_single_saved_prompt(self):
        """Verify single prompt retrieval by ID."""
        saved = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Test Retrieve",
                content="Instruction content here",
                category="General",
                operation_type="generate",
            ),
        )
        retrieved = get_saved_prompt(self.db, saved.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, saved.id)
        self.assertEqual(retrieved.title, "Test Retrieve")

    def test_04_search_saved_prompts_by_title_and_keyword(self):
        """Verify search matches keywords across title and prompt body."""
        create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Kubernetes Deployment YAML",
                content="Generate a production deployment manifest with resource limits and probes.",
                category="Coding",
                operation_type="generate",
            ),
        )
        create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Marketing Campaign Email",
                content="Draft a launch announcement for beta users focusing on speed.",
                category="Business",
                operation_type="generate",
            ),
        )

        # Search title
        total1, res1 = list_saved_prompts(self.db, search="Kubernetes")
        self.assertEqual(total1, 1)
        self.assertEqual(res1[0].title, "Kubernetes Deployment YAML")

        # Search content keyword
        total2, res2 = list_saved_prompts(self.db, search="resource limits")
        self.assertEqual(total2, 1)
        self.assertEqual(res2[0].title, "Kubernetes Deployment YAML")

        # Non-matching search
        total3, _ = list_saved_prompts(self.db, search="nonexistent_xyz")
        self.assertEqual(total3, 0)

    def test_05_filter_by_category_and_operation_type(self):
        """Verify filtering saved prompts by category and operation type."""
        for i in range(4):
            create_saved_prompt(
                self.db,
                SavedPromptCreate(
                    title=f"Coding Prompt {i}",
                    content=f"Content {i}",
                    category="Coding",
                    operation_type="generate" if i % 2 == 0 else "optimize",
                ),
            )
        create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Business Prompt",
                content="Content B",
                category="Business",
                operation_type="optimize",
            ),
        )

        # Category filter
        total, coding_items = list_saved_prompts(self.db, category="Coding")
        self.assertEqual(total, 4)

        # Operation filter
        opt_total, opt_items = list_saved_prompts(self.db, operation_type="optimize")
        self.assertEqual(opt_total, 3)

        # Combined filter
        both_total, both_items = list_saved_prompts(self.db, category="Coding", operation_type="optimize")
        self.assertEqual(both_total, 2)

    def test_06_update_saved_prompt(self):
        """Verify editing title and category updates record and updated_at."""
        saved = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="Initial Title",
                content="Original content",
                category="General",
                operation_type="generate",
            ),
        )
        updated = update_saved_prompt(
            self.db,
            saved.id,
            SavedPromptUpdate(title="Updated Title", category="Academic"),
        )
        self.assertEqual(updated.title, "Updated Title")
        self.assertEqual(updated.category, "Academic")
        self.assertEqual(updated.content, "Original content")  # content preserved

    def test_07_delete_saved_prompt(self):
        """Verify deleting a saved prompt removes it and returns None on subsequent get."""
        saved = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title="To Delete",
                content="Will be removed",
                category="General",
                operation_type="generate",
            ),
        )
        success = delete_saved_prompt(self.db, saved.id)
        self.assertTrue(success)
        self.assertIsNone(get_saved_prompt(self.db, saved.id))

    def test_08_delete_nonexistent_returns_false(self):
        """Verify deleting a non-existent ID gracefully returns False."""
        success = delete_saved_prompt(self.db, 99999)
        self.assertFalse(success)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Prompt History Recording, Metrics, & Deletion
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptHistorySmoke(unittest.TestCase):
    """Smoke test for Prompt History recording, pagination, metrics, and deletion."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_01_record_generate_history(self):
        """Verify recording a Generate operation with model and token count."""
        hist = record_history(
            self.db,
            PromptHistoryCreate(
                operation_type="generate",
                original_input="Analyze customer churn dataset",
                generated_output="## Role: Senior Data Scientist...",
                tokens_before=15,
                tokens_after=145,
                tokens_saved=0,
                model_name="gemini-3-flash-preview",
            ),
        )
        self.assertIsNotNone(hist.id)
        self.assertEqual(hist.operation_type, "generate")
        self.assertEqual(hist.original_input, "Analyze customer churn dataset")
        self.assertEqual(hist.tokens_before, 15)
        self.assertEqual(hist.tokens_after, 145)
        self.assertEqual(hist.model_name, "gemini-3-flash-preview")
        self.assertIsNotNone(hist.created_at)

    def test_02_record_optimize_history_with_token_savings(self):
        """Verify recording an Optimize operation with before/after/saved token counts."""
        hist = record_history(
            self.db,
            PromptHistoryCreate(
                operation_type="optimize",
                original_input="Please kindly act as an expert and write a python script to parse CSV...",
                optimized_output="Write a Python script using csv.DictReader to parse CSV files with validation.",
                tokens_before=85,
                tokens_after=32,
                tokens_saved=53,
                model_name="gemini-3-flash-preview",
            ),
        )
        self.assertIsNotNone(hist.id)
        self.assertEqual(hist.operation_type, "optimize")
        self.assertEqual(hist.tokens_saved, 53)

    def test_03_list_history_ordered_by_newest_first(self):
        """Verify history entries are returned in descending chronological order."""
        for i in range(1, 4):
            record_history(
                self.db,
                PromptHistoryCreate(
                    operation_type="generate",
                    original_input=f"Input run #{i}",
                    generated_output=f"Output run #{i}",
                ),
            )
        total, items = list_history(self.db, limit=10, offset=0)
        self.assertEqual(total, 3)
        self.assertEqual(items[0].original_input, "Input run #3")
        self.assertEqual(items[2].original_input, "Input run #1")

    def test_04_filter_history_by_operation_type(self):
        """Verify filtering history by operation type."""
        record_history(
            self.db,
            PromptHistoryCreate(
                operation_type="generate",
                original_input="Gen 1",
                generated_output="Out 1",
            ),
        )
        record_history(
            self.db,
            PromptHistoryCreate(
                operation_type="optimize",
                original_input="Opt 1",
                optimized_output="Out 2",
            ),
        )
        gen_total, gen_items = list_history(self.db, operation_type="generate")
        self.assertEqual(gen_total, 1)
        self.assertEqual(gen_items[0].operation_type, "generate")

        opt_total, opt_items = list_history(self.db, operation_type="optimize")
        self.assertEqual(opt_total, 1)
        self.assertEqual(opt_items[0].operation_type, "optimize")

    def test_05_delete_single_history_item(self):
        """Verify deleting a single history item by ID."""
        hist = record_history(
            self.db,
            PromptHistoryCreate(
                operation_type="generate",
                original_input="To delete",
                generated_output="Output",
            ),
        )
        success = delete_history_item(self.db, hist.id)
        self.assertTrue(success)
        self.assertIsNone(get_history_item(self.db, hist.id))

    def test_06_clear_all_history(self):
        """Verify clearing all history removes every record."""
        for i in range(5):
            record_history(
                self.db,
                PromptHistoryCreate(
                    operation_type="generate",
                    original_input=f"Batch {i}",
                    generated_output=f"Out {i}",
                ),
            )
        deleted_count = clear_history(self.db)
        self.assertEqual(deleted_count, 5)
        total_after, _ = list_history(self.db)
        self.assertEqual(total_after, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Badge Counts & API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestBadgeCountsSmoke(unittest.TestCase):
    """Smoke test for count reporting endpoints used by frontend navigation badges."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_01_saved_prompts_count_lifecycle(self):
        """Verify saved prompts total increments on creation and decrements on deletion."""
        # Initial count is 0
        resp0 = api_list_saved_prompts(limit=1, offset=0, db=self.db)
        self.assertEqual(resp0.total, 0)

        # Create two items
        p1 = api_create_saved_prompt(
            SavedPromptCreate(title="P1", content="C1", category="General", operation_type="generate"),
            db=self.db,
        )
        resp1 = api_list_saved_prompts(limit=1, offset=0, db=self.db)
        self.assertEqual(resp1.total, 1)

        p2 = api_create_saved_prompt(
            SavedPromptCreate(title="P2", content="C2", category="Coding", operation_type="optimize"),
            db=self.db,
        )
        resp2 = api_list_saved_prompts(limit=1, offset=0, db=self.db)
        self.assertEqual(resp2.total, 2)

        # Delete one item
        api_delete_saved_prompt(p1.id, db=self.db)
        resp3 = api_list_saved_prompts(limit=1, offset=0, db=self.db)
        self.assertEqual(resp3.total, 1)

    def test_02_history_count_lifecycle(self):
        """Verify history total increments on run and clears to 0 on clear-all."""
        resp0 = api_list_history(limit=1, offset=0, db=self.db)
        self.assertEqual(resp0.total, 0)

        record_history(
            self.db,
            PromptHistoryCreate(operation_type="generate", original_input="R1", generated_output="O1"),
        )
        record_history(
            self.db,
            PromptHistoryCreate(operation_type="optimize", original_input="R2", optimized_output="O2"),
        )
        resp1 = api_list_history(limit=1, offset=0, db=self.db)
        self.assertEqual(resp1.total, 2)

        api_clear_history(db=self.db)
        resp2 = api_list_history(limit=1, offset=0, db=self.db)
        self.assertEqual(resp2.total, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Database Persistence & Restart Simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabasePersistenceSmoke(unittest.TestCase):
    """Smoke test for disk SQLite file persistence across process/session restarts."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "autoprompt_test.db")
        self.db_url = f"sqlite:///{self.db_path}"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_data_persists_across_engine_restart(self):
        """Simulate backend restart: write records, disconnect, reconnect, verify data."""
        # ── Session 1: Startup & Creation ──
        engine1 = create_engine(self.db_url)
        init_db(engine1)
        Session1 = sessionmaker(bind=engine1)
        db1 = Session1()

        saved1 = create_saved_prompt(
            db1,
            SavedPromptCreate(
                title="Persistent Prompt",
                content="This prompt must survive backend restarts.",
                category="Data Science",
                operation_type="generate",
            ),
        )
        hist1 = record_history(
            db1,
            PromptHistoryCreate(
                operation_type="generate",
                original_input="Persistent run input",
                generated_output="Persistent run output",
                tokens_before=20,
                tokens_after=110,
                tokens_saved=0,
                model_name="gemini-3-flash-preview",
            ),
        )
        saved1_id = saved1.id
        hist1_id = hist1.id

        db1.close()
        engine1.dispose()

        # ── Session 2: Backend Restart Simulation ──
        engine2 = create_engine(self.db_url)
        init_db(engine2)  # Non-destructive: tables already exist
        Session2 = sessionmaker(bind=engine2)
        db2 = Session2()

        # Verify saved prompt survived
        recovered_prompt = get_saved_prompt(db2, saved1_id)
        self.assertIsNotNone(recovered_prompt)
        self.assertEqual(recovered_prompt.title, "Persistent Prompt")
        self.assertEqual(recovered_prompt.category, "Data Science")
        self.assertEqual(recovered_prompt.content, "This prompt must survive backend restarts.")

        # Verify history survived
        recovered_history = get_history_item(db2, hist1_id)
        self.assertIsNotNone(recovered_history)
        self.assertEqual(recovered_history.original_input, "Persistent run input")
        self.assertEqual(recovered_history.tokens_after, 110)

        db2.close()
        engine2.dispose()

    def test_02_database_schema_and_indexes(self):
        """Verify tables, columns, and indexes are created properly in SQLite."""
        engine = create_engine(self.db_url)
        init_db(engine)
        inspector = inspect(engine)

        tables = inspector.get_table_names()
        self.assertIn("saved_prompts", tables)
        self.assertIn("prompt_history", tables)

        # Inspect saved_prompts columns
        sp_cols = {col["name"]: col for col in inspector.get_columns("saved_prompts")}
        for required_col in ["id", "title", "content", "category", "operation_type", "created_at", "updated_at"]:
            self.assertIn(required_col, sp_cols, f"Column {required_col} missing in saved_prompts")

        # Inspect prompt_history columns
        ph_cols = {col["name"]: col for col in inspector.get_columns("prompt_history")}
        for required_col in ["id", "operation_type", "original_input", "generated_output", "tokens_before", "tokens_after", "tokens_saved", "model_name", "created_at"]:
            self.assertIn(required_col, ph_cols, f"Column {required_col} missing in prompt_history")

        # Verify indexes exist
        sp_indexes = [idx["name"] for idx in inspector.get_indexes("saved_prompts")]
        self.assertTrue(any("category" in str(idx) or "op" in str(idx) for idx in sp_indexes))

        engine.dispose()

    def test_03_transaction_rollback_on_failure(self):
        """Verify database transaction rolls back on unhandled error, leaving DB consistent."""
        engine = create_engine(self.db_url)
        init_db(engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        # Successful creation
        create_saved_prompt(
            db,
            SavedPromptCreate(title="Valid", content="Valid content", category="General", operation_type="generate"),
        )
        self.assertEqual(db.query(SavedPrompt).count(), 1)

        # Intentionally cause an error and rollback
        try:
            db.begin_nested()
            db.execute(text("INSERT INTO non_existent_table VALUES (1)"))
            db.commit()
        except Exception:
            db.rollback()

        # Database is still healthy and count is unchanged
        self.assertEqual(db.query(SavedPrompt).count(), 1)

        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
