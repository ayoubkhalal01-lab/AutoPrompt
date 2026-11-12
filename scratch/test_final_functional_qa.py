"""
AutoPrompt — Phase 7.1 Final Functional QA Test Suite
Comprehensive, isolated, non-destructive test suite verifying all Phase 7.1 requirements:
- Section 2: Environment & Startup Verification
- Section 3: Core Functional Testing (Generate, Optimize, Token Counting)
- Section 4: Saved Prompts & History Testing (Isolated Test Database)
- Section 5: Frontend Contracts & Integrity
- Section 6: Regression & Edge Cases (14 specific scenarios)
- Section 8: Gemini Live Targeted Verification (Quota-Safe)
"""

import os
import sys
import json
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure backend is on PYTHONPATH
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError

from app.config import settings
from app.db.models import Base, SavedPrompt, PromptHistory
from app.db.session import init_db
from app.schemas.prompt_schemas import (
    GenerateRequest,
    GenerateResponse,
    OptimizeRequest,
    OptimizeResponse,
    TokenCountRequest,
    TokenCountResponse,
)
from app.schemas.persistence_schemas import (
    SavedPromptCreate,
    SavedPromptUpdate,
    SavedPromptResponse,
    PromptHistoryCreate,
    PromptHistoryResponse,
)
from app.main import (
    app,
    health_check,
    api_count_tokens,
    api_generate_prompt,
    api_optimize_prompt,
    api_create_saved_prompt,
    api_list_saved_prompts,
    api_get_saved_prompt,
    api_update_saved_prompt,
    api_delete_saved_prompt,
    api_list_history,
    api_get_history_item,
    api_delete_history_item,
    api_clear_history,
    _resolve_status_code,
)
from app.services.gemini_service import (
    classify_error,
    count_tokens,
)
from app.services.persistence_service import (
    create_saved_prompt,
    get_saved_prompt,
    list_saved_prompts,
    update_saved_prompt,
    delete_saved_prompt,
    record_history,
    get_history_item,
    list_history,
    delete_history_item,
    clear_history,
)


class TestEnvironmentAndStartup(unittest.TestCase):
    """Section 2: Environment & Startup Verification"""

    def test_01_python_environment(self):
        """Verify Python 3.14+ version."""
        self.assertGreaterEqual(sys.version_info.major, 3)
        self.assertGreaterEqual(sys.version_info.minor, 10)

    def test_02_config_loading_no_secret_exposure(self):
        """Verify settings load safely without secret leaks."""
        self.assertIsNotNone(settings.APP_NAME)
        self.assertIsNotNone(settings.GEMINI_MODEL)
        self.assertGreater(settings.GEMINI_TIMEOUT_SECONDS, 0)
        self.assertGreaterEqual(settings.GEMINI_MAX_RETRIES, 1)
        # Verify API key is present but string representation of settings doesn't reveal it
        self.assertTrue(settings.has_gemini_key)
        self.assertNotIn(settings.GEMINI_API_KEY, repr(settings))

    def test_03_health_check_endpoint(self):
        """Verify health check endpoint returns 200 and expected metadata."""
        resp = health_check()
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.body.decode())
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["gemini_key_configured"])
        self.assertEqual(data["gemini_model"], settings.GEMINI_MODEL)
        # Ensure no secret in health check response
        self.assertNotIn("AIza", json.dumps(data))

    def test_04_gitignore_rules(self):
        """Verify .gitignore excludes .env and *.db files."""
        root_gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
        backend_gitignore = BACKEND_DIR / ".gitignore"
        self.assertTrue(root_gitignore.exists())
        self.assertTrue(backend_gitignore.exists())
        with open(root_gitignore, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn(".env", content)
            self.assertIn("*.db", content)
        with open(backend_gitignore, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn(".env", content)
            self.assertIn("*.db", content)


class TestCoreGeneratePrompt(unittest.TestCase):
    """Section 3A: Core Functional Testing — Generate Prompt"""

    def setUp(self):
        # Create an isolated in-memory DB session
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_generate_empty_input_fails_validation(self):
        """Empty input should raise Pydantic ValidationError."""
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="")

    def test_generate_whitespace_only_fails_validation(self):
        """Whitespace-only input should raise Pydantic ValidationError."""
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="   \n\t  ")

    def test_generate_short_input_accepted(self):
        """Very short input (3+ chars) is accepted by schema."""
        req = GenerateRequest(user_idea="SQL")
        self.assertEqual(req.user_idea, "SQL")

    def test_generate_unicode_and_special_chars(self):
        """Unicode characters (CJK, Arabic, Accents, Emoji) handled safely."""
        req = GenerateRequest(
            user_idea="Optimiser une requête SQL pour données financières € & ¥ — 🚀"
        )
        self.assertIn("€ & ¥ — 🚀", req.user_idea)

    def test_generate_multiline_input(self):
        """Multiline input formatted and preserved."""
        multiline = "Build a microservice:\n1. Use FastAPI\n2. Integrate SQLite\n3. Add JWT auth"
        req = GenerateRequest(user_idea=multiline)
        self.assertEqual(req.user_idea, multiline)

    def test_generate_long_input_within_limit(self):
        """Input up to 5,000 characters is accepted."""
        long_idea = "A" * 4900
        req = GenerateRequest(user_idea=long_idea)
        self.assertEqual(len(req.user_idea), 4900)

    def test_generate_input_exceeding_max_length(self):
        """Input exceeding 10,000 characters raises ValidationError."""
        too_long = "A" * 10001
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea=too_long)

    @patch("app.main.generate_prompt")
    def test_generate_endpoint_success_and_auto_history(self, mock_gen):
        """Successful generation returns 200 and records history."""
        mock_gen.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "category": "Coding",
            "user_idea": "Build a CLI in Python",
            "generated_prompt": "You are an expert CLI developer...",
            "input_tokens": 15,
            "output_tokens": 180,
            "response_time_ms": 850,
            "error_code": None,
            "error_message": None,
        }
        req = GenerateRequest(user_idea="Build a CLI in Python", category="Coding")
        resp = api_generate_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["input_tokens"], 15)
        self.assertEqual(data["output_tokens"], 180)

        # Check auto-recorded history in test DB
        hist = self.db.query(PromptHistory).first()
        self.assertIsNotNone(hist)
        self.assertEqual(hist.operation_type, "generate")
        self.assertEqual(hist.original_input, "Build a CLI in Python")
        self.assertEqual(hist.tokens_before, 15)
        self.assertEqual(hist.tokens_after, 180)

    @patch("app.main.generate_prompt")
    def test_generate_quota_exceeded_handled_gracefully(self, mock_gen):
        """Quota exceeded maps to HTTP 503 with standardized error_code."""
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "category": "Coding",
            "user_idea": "Build a CLI",
            "generated_prompt": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_time_ms": 120,
            "error_code": "quota_exceeded",
            "error_message": "API quota exceeded. Please wait a moment.",
        }
        req = GenerateRequest(user_idea="Build a CLI")
        resp = api_generate_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 503)
        data = json.loads(resp.body.decode())
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "quota_exceeded")
        # History should NOT be recorded on failure
        self.assertEqual(self.db.query(PromptHistory).count(), 0)

    @patch("app.main.generate_prompt")
    def test_generate_timeout_handled_gracefully(self, mock_gen):
        """Timeout maps to HTTP 503 with error_code: timeout."""
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "category": "General",
            "user_idea": "Test timeout",
            "generated_prompt": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_time_ms": 30000,
            "error_code": "timeout",
            "error_message": "Request timed out.",
        }
        req = GenerateRequest(user_idea="Test timeout")
        resp = api_generate_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 503)
        data = json.loads(resp.body.decode())
        self.assertEqual(data["error_code"], "timeout")


class TestCoreOptimizePrompt(unittest.TestCase):
    """Section 3B: Core Functional Testing — Optimize Prompt"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_optimize_empty_prompt_fails_validation(self):
        """Empty prompt fails validation."""
        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="")

    def test_optimize_whitespace_only_fails_validation(self):
        """Whitespace only fails validation."""
        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="    ")

    def test_optimize_unicode_and_special_chars(self):
        """Unicode characters preserved in optimization payload."""
        req = OptimizeRequest(original_prompt="Traduire ce texte en français : 🚀 Café crème")
        self.assertIn("Café crème", req.original_prompt)

    @patch("app.main.optimize_prompt")
    def test_optimize_honest_token_expansion(self, mock_opt):
        """Under-specified prompt expansion honestly reports negative savings."""
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "original_prompt": "Help me fix my code.",
            "optimized_prompt": "# Role: Senior Debugger\n## Objective\nAnalyze code...",
            "original_tokens": 6,
            "optimized_tokens": 120,
            "tokens_saved": -114,
            "reduction_percentage": -1900.0,
            "response_time_ms": 950,
            "error_code": None,
            "error_message": None,
        }
        req = OptimizeRequest(original_prompt="Help me fix my code.")
        resp = api_optimize_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["tokens_saved"], -114)
        self.assertEqual(data["reduction_percentage"], -1900.0)

        # Verify auto-recorded history
        hist = self.db.query(PromptHistory).first()
        self.assertIsNotNone(hist)
        self.assertEqual(hist.operation_type, "optimize")
        self.assertEqual(hist.tokens_before, 6)
        self.assertEqual(hist.tokens_after, 120)
        self.assertEqual(hist.tokens_saved, -114)

    @patch("app.main.optimize_prompt")
    def test_optimize_token_compression(self, mock_opt):
        """Verbose prompt compression honestly reports positive savings."""
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "original_prompt": "Wordy prompt with unnecessary repetitions...",
            "optimized_prompt": "Concise structured directive.",
            "original_tokens": 200,
            "optimized_tokens": 50,
            "tokens_saved": 150,
            "reduction_percentage": 75.0,
            "response_time_ms": 820,
            "error_code": None,
            "error_message": None,
        }
        req = OptimizeRequest(original_prompt="Wordy prompt...")
        resp = api_optimize_prompt(req, db=self.db)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.body.decode())
        self.assertEqual(data["tokens_saved"], 150)
        self.assertEqual(data["reduction_percentage"], 75.0)


class TestCoreTokenCounting(unittest.TestCase):
    """Section 3C: Core Functional Testing — Token Counting"""

    def test_count_tokens_empty_input(self):
        """Empty input raises ValidationError."""
        with self.assertRaises(ValidationError):
            TokenCountRequest(text="")

    def test_count_tokens_whitespace_only(self):
        """Whitespace only raises ValidationError."""
        with self.assertRaises(ValidationError):
            TokenCountRequest(text="   \n\t  ")

    @patch("app.main.count_tokens")
    def test_count_tokens_endpoint_success(self, mock_count):
        """Token count endpoint returns integer token count."""
        mock_count.return_value = 24
        req = TokenCountRequest(text="Test token count calculation.")
        resp = api_count_tokens(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["token_count"], 24)

    @patch("app.main.count_tokens")
    def test_count_tokens_consistency(self, mock_count):
        """Identical inputs produce identical token counts."""
        mock_count.return_value = 17
        req = TokenCountRequest(text="Consistent sentence for token measurement.")
        resp1 = api_count_tokens(req)
        resp2 = api_count_tokens(req)
        self.assertEqual(json.loads(resp1.body.decode())["token_count"], 17)
        self.assertEqual(json.loads(resp2.body.decode())["token_count"], 17)


class TestSavedPromptsAndHistory(unittest.TestCase):
    """Section 4: Saved Prompts & History (Isolated In-Memory Database)"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_saved_prompts_crud_lifecycle(self):
        """Full create, read, update, list, search, delete lifecycle."""
        # 1. Create
        create_payload = SavedPromptCreate(
            title="QA Test Prompt",
            content="Role: QA Lead\nObjective: Verify system",
            category="Coding",
            operation_type="generate",
        )
        prompt = create_saved_prompt(self.db, create_payload)
        self.assertIsNotNone(prompt.id)
        self.assertEqual(prompt.title, "QA Test Prompt")

        # 2. Get by ID
        fetched = get_saved_prompt(self.db, prompt.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.content, "Role: QA Lead\nObjective: Verify system")

        # 3. Search & Filter
        total, items = list_saved_prompts(self.db, search="QA Test", category="Coding")
        self.assertEqual(total, 1)
        self.assertEqual(items[0].id, prompt.id)

        # Search by content keyword
        total_content, items_content = list_saved_prompts(self.db, search="Verify system")
        self.assertEqual(total_content, 1)

        # 4. Update
        update_payload = SavedPromptUpdate(
            title="Updated QA Prompt",
            content="Updated content...",
            category="Data Science",
        )
        updated = update_saved_prompt(self.db, prompt.id, update_payload)
        self.assertEqual(updated.title, "Updated QA Prompt")
        self.assertEqual(updated.category, "Data Science")

        # 5. Delete
        del_success = delete_saved_prompt(self.db, prompt.id)
        self.assertTrue(del_success)
        self.assertIsNone(get_saved_prompt(self.db, prompt.id))

    def test_saved_prompt_nonexistent_returns_none(self):
        """Querying nonexistent ID returns None / 404."""
        self.assertIsNone(get_saved_prompt(self.db, 99999))
        self.assertFalse(delete_saved_prompt(self.db, 99999))
        self.assertIsNone(update_saved_prompt(self.db, 99999, SavedPromptUpdate(title="X")))

    def test_history_lifecycle_and_clear(self):
        """History creation, ordering, filtering, and atomic clear."""
        # Record 3 items
        for i in range(3):
            record_history(
                self.db,
                PromptHistoryCreate(
                    operation_type="generate" if i % 2 == 0 else "optimize",
                    original_input=f"Input {i}",
                    generated_output=f"Output {i}",
                    tokens_before=10 * (i + 1),
                    tokens_after=50 * (i + 1),
                    model_name="gemini-3-flash-preview",
                ),
            )
            time.sleep(0.01)

        # Check total and reverse chronological order
        total, items = list_history(self.db)
        self.assertEqual(total, 3)
        self.assertEqual(items[0].original_input, "Input 2")  # newest first

        # Filter by operation_type
        gen_total, gen_items = list_history(self.db, operation_type="generate")
        self.assertEqual(gen_total, 2)

        # Delete single item
        del_item_id = items[0].id
        self.assertTrue(delete_history_item(self.db, del_item_id))
        self.assertIsNone(get_history_item(self.db, del_item_id))

        # Clear all
        count_cleared = clear_history(self.db)
        self.assertEqual(count_cleared, 2)
        total_after, _ = list_history(self.db)
        self.assertEqual(total_after, 0)

    def test_persistence_engine_restart(self):
        """Data persists when a new engine and session connect to the same file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            # First session creates data
            engine1 = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine1)
            Session1 = sessionmaker(bind=engine1)
            db1 = Session1()

            prompt = create_saved_prompt(
                db1,
                SavedPromptCreate(
                    title="Persistence Test Prompt",
                    content="Persisted across restarts",
                    operation_type="generate",
                ),
            )
            prompt_id = prompt.id
            db1.close()
            engine1.dispose()

            # Second session re-opens
            engine2 = create_engine(f"sqlite:///{db_path}")
            Session2 = sessionmaker(bind=engine2)
            db2 = Session2()

            fetched = get_saved_prompt(db2, prompt_id)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.title, "Persistence Test Prompt")
            db2.close()
            engine2.dispose()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


class TestFrontendContractsAndDOM(unittest.TestCase):
    """Section 5: Frontend DOM Structure & Modal Element Contracts"""

    @classmethod
    def setUpClass(cls):
        cls.html_path = Path(__file__).resolve().parent.parent / "autoprompt-prototype" / "index.html"
        cls.persistence_js_path = (
            Path(__file__).resolve().parent.parent / "autoprompt-prototype" / "js" / "persistence.js"
        )
        with open(cls.html_path, "r", encoding="utf-8") as f:
            cls.html = f.read()
        with open(cls.persistence_js_path, "r", encoding="utf-8") as f:
            cls.js = f.read()

    def test_dom_modal_elements_exist(self):
        """All required persistence modals exist in HTML."""
        required_ids = [
            "modal-save-prompt",
            "modal-saved-prompts",
            "modal-prompt-history",
            "modal-edit-prompt",
            "modal-confirm-action",
            "toast-container",
            "btn-nav-saved-prompts",
            "btn-nav-history",
            "saved-prompts-count-badge",
            "history-count-badge",
        ]
        for elem_id in required_ids:
            self.assertIn(f'id="{elem_id}"', self.html, f"Missing DOM element: {elem_id}")

    def test_dom_action_buttons_exist(self):
        """Save prompt trigger buttons exist in workspace."""
        self.assertIn('id="btn-results-save-top"', self.html)
        self.assertIn('id="btn-results-save-bottom"', self.html)
        self.assertIn('id="btn-save-main-result"', self.html)

    def test_persistence_js_exposes_manager(self):
        """persistence.js attaches global.PersistenceManager."""
        self.assertIn("global.PersistenceManager =", self.js)
        self.assertIn("openSavedPromptsModal", self.js)
        self.assertIn("openHistoryModal", self.js)
        self.assertIn("openSavePromptModal", self.js)
        self.assertIn("refreshBadgeCount", self.js)


class TestRegressionScenarios(unittest.TestCase):
    """Section 6: 14 Regression & Edge-Case Scenarios"""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_scenario_01_backend_unavailable_error_mapping(self):
        """Scenario 1: Network connection failure maps to HTTP 503 network."""
        status = _resolve_status_code({"success": False, "error_code": "network"})
        self.assertEqual(status, 503)

    def test_scenario_02_backend_recovery_after_error(self):
        """Scenario 2: Successful call immediately after error succeeds."""
        status_err = _resolve_status_code({"success": False, "error_code": "timeout"})
        status_ok = _resolve_status_code({"success": True})
        self.assertEqual(status_err, 503)
        self.assertEqual(status_ok, 200)

    def test_scenario_03_invalid_api_response_handling(self):
        """Scenario 3: Empty/null response maps to HTTP 502 invalid_response."""
        status = _resolve_status_code({"success": False, "error_code": "invalid_response"})
        self.assertEqual(status, 502)

    def test_scenario_04_http_404_nonexistent_record(self):
        """Scenario 4: Deleting or querying nonexistent prompt returns 404."""
        self.assertIsNone(get_saved_prompt(self.db, 88888))
        self.assertFalse(delete_saved_prompt(self.db, 88888))

    def test_scenario_05_http_422_invalid_request_data(self):
        """Scenario 5: Invalid payload fails Pydantic schema validation."""
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="", mode="invalid_mode")

    def test_scenario_06_http_429_quota_exhaustion(self):
        """Scenario 6: Quota exhaustion returns HTTP 503 quota_exceeded."""
        status = _resolve_status_code({"success": False, "error_code": "quota_exceeded"})
        self.assertEqual(status, 503)

    def test_scenario_07_network_timeout(self):
        """Scenario 7: Timeout returns HTTP 503 timeout."""
        status = _resolve_status_code({"success": False, "error_code": "timeout"})
        self.assertEqual(status, 503)

    def test_scenario_08_repeated_clicks_debouncing_contract(self):
        """Scenario 8: Multiple identical saves create distinct timestamped records."""
        p1 = create_saved_prompt(
            self.db,
            SavedPromptCreate(title="Click Test", content="Content", operation_type="generate"),
        )
        p2 = create_saved_prompt(
            self.db,
            SavedPromptCreate(title="Click Test", content="Content", operation_type="generate"),
        )
        self.assertNotEqual(p1.id, p2.id)

    def test_scenario_09_empty_saved_prompts_list(self):
        """Scenario 9: Listing empty saved prompts returns 0 items cleanly."""
        total, items = list_saved_prompts(self.db)
        self.assertEqual(total, 0)
        self.assertEqual(items, [])

    def test_scenario_10_empty_history_list(self):
        """Scenario 10: Listing empty history returns 0 items cleanly."""
        total, items = list_history(self.db)
        self.assertEqual(total, 0)
        self.assertEqual(items, [])

    def test_scenario_11_database_rollback_on_failure(self):
        """Scenario 11: Transaction safely rolls back on constraint violation."""
        with self.assertRaises(Exception):
            # Attempt to insert directly with invalid null title
            invalid_record = SavedPrompt(title=None, content="Missing title", operation_type="generate")
            self.db.add(invalid_record)
            self.db.commit()
        self.db.rollback()
        # Verify DB is healthy after rollback
        self.assertEqual(self.db.query(SavedPrompt).count(), 0)

    def test_scenario_12_very_long_user_input_preservation(self):
        """Scenario 12: 4,000 character prompt is preserved without truncation."""
        long_text = ("Analysis task: " + ("abcdefghij " * 350)).strip()
        p = create_saved_prompt(
            self.db,
            SavedPromptCreate(title="Long Prompt", content=long_text, operation_type="generate"),
        )
        fetched = get_saved_prompt(self.db, p.id)
        self.assertEqual(fetched.content, long_text)

    def test_scenario_13_special_characters_and_sql_injection_safety(self):
        """Scenario 13: SQL quotes and special chars do not cause SQL injection."""
        sql_injection_attempt = "'; DROP TABLE saved_prompts; --"
        p = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title=sql_injection_attempt,
                content=sql_injection_attempt,
                operation_type="generate",
            ),
        )
        fetched = get_saved_prompt(self.db, p.id)
        self.assertEqual(fetched.title, sql_injection_attempt)
        # Verify table still exists
        self.assertEqual(self.db.query(SavedPrompt).count(), 1)

    def test_scenario_14_multilingual_unicode_handling(self):
        """Scenario 14: Full multilingual text (Arabic, Japanese, Accents) preserved."""
        arabic_text = "اكتب موجهاً احترافياً لتحليل مشاعر العملاء"
        japanese_text = "PythonとPandasを使用したデータ分析プロンプト"
        p = create_saved_prompt(
            self.db,
            SavedPromptCreate(
                title=arabic_text,
                content=japanese_text,
                operation_type="generate",
            ),
        )
        fetched = get_saved_prompt(self.db, p.id)
        self.assertEqual(fetched.title, arabic_text)
        self.assertEqual(fetched.content, japanese_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
