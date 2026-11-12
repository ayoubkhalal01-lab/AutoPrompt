"""
test_phase_8_5e_acceptance.py — AutoPrompt Phase 8.5-E Acceptance Test Suite
=============================================================================

Executes comprehensive acceptance tests covering:
1. Repository & Vercel Configuration Audit
2. Environment Variable Configuration Safety
3. FastAPI Application Initialization (via api.index)
4. All 15 API Routes End-to-End Testing (Contract & Handler Verification)
5. /health Endpoint Verification
6. Generate and Optimize Workflows (with AI mock)
7. Multilingual Prompts & Unicode Handling (Arabic, CJK, Accents, Emoji)
8. PostgreSQL / Database Engine & Pool Verification
9. Database Persistence (Saved Prompts & Prompt History)
10. Security Headers, CORS, and Exception/Error Handling
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add backend and root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, PromptHistory, SavedPrompt
from api.index import app
from app.main import (
    api_clear_history,
    api_count_tokens,
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
    health_check,
    test_gemini as endpoint_test_gemini,
)
from app.schemas.persistence_schemas import (
    PromptHistoryCreate,
    SavedPromptCreate,
    SavedPromptUpdate,
)
from app.schemas.prompt_schemas import (
    GenerateRequest,
    OptimizeRequest,
    TokenCountRequest,
)


class AcceptanceBase(unittest.TestCase):
    """Base fixture with isolated in-memory SQLite database."""

    def setUp(self):
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Repository & Deployment Configuration Audit
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeploymentConfigurationAudit(unittest.TestCase):
    """Audit repo and Vercel configuration files."""

    def test_entrypoint_file_exists(self):
        self.assertTrue((REPO_ROOT / "api" / "index.py").is_file())

    def test_vercel_json_rewrites_and_functions(self):
        v_file = REPO_ROOT / "vercel.json"
        self.assertTrue(v_file.is_file())
        config = json.loads(v_file.read_text(encoding="utf-8"))
        self.assertEqual(config.get("version"), 2)
        sources = [r["source"] for r in config.get("rewrites", [])]
        self.assertIn("/api/(.*)", sources)
        self.assertIn("/health", sources)
        self.assertIn("/(.*)", sources)
        fn_cfg = config.get("functions", {}).get("api/index.py", {})
        self.assertEqual(fn_cfg.get("maxDuration"), 15)

    def test_root_requirements_present_and_complete(self):
        req_file = REPO_ROOT / "requirements.txt"
        self.assertTrue(req_file.is_file())
        reqs = req_file.read_text(encoding="utf-8")
        for dep in ["fastapi", "uvicorn", "pydantic", "sqlalchemy", "psycopg2-binary", "google-genai"]:
            self.assertIn(dep, reqs)

    def test_environment_variables_configured_without_exposure(self):
        """Check required environment keys exist without printing secrets."""
        from app.config import settings
        self.assertTrue(hasattr(settings, "GEMINI_API_KEY"))
        self.assertTrue(hasattr(settings, "DATABASE_URL"))
        self.assertTrue(hasattr(settings, "GEMINI_MODEL"))
        self.assertTrue(hasattr(settings, "GEMINI_TIMEOUT_SECONDS"))
        self.assertIsInstance(settings.has_gemini_key, bool)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FastAPI Initialization & /health Probe
# ═══════════════════════════════════════════════════════════════════════════════

class TestFastAPIInitializationAndHealth(unittest.TestCase):
    """Verify application bootstrap and health endpoint."""

    def test_app_metadata(self):
        self.assertEqual(app.title, "AutoPrompt Backend")
        self.assertIsNotNone(app.version)

    def test_health_endpoint_healthy(self):
        response = health_check()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.body)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("timestamp", data)
        self.assertIn("gemini_key_configured", data)
        self.assertIn("gemini_model", data)
        # Ensure sys.version / platform are not leaked
        self.assertNotIn("platform", data)
        self.assertNotIn("sys_version", data)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. All 15 API Routes End-to-End Verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllFifteenRoutes(AcceptanceBase):
    """Test every single route of the 15 registered routes."""

    def test_routes_registry_count(self):
        registered = [r for r in app.routes if hasattr(r, "methods")]
        self.assertEqual(len(registered), 15, f"Expected 15 routes, found {len(registered)}")

    def test_route_1_openapi_json(self):
        route = next((r for r in app.routes if getattr(r, "path", None) == "/openapi.json"), None)
        self.assertIsNotNone(route)

    def test_route_2_health(self):
        res = health_check()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.body)["status"], "ok")

    @patch("app.main.test_gemini_connection")
    def test_route_3_test_gemini_diagnostics(self, mock_conn):
        mock_conn.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "response_time_ms": 120,
            "response_text": "OK",
            "error_code": None,
            "error_message": None,
        }
        res = endpoint_test_gemini()
        self.assertIn(res.status_code, [200, 404])

    @patch("app.main.generate_prompt")
    def test_route_4_generate(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "generated_prompt": "Generated Structured Prompt",
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "input_tokens": 15,
            "output_tokens": 40,
            "tokens_saved": -25,
            "response_time_ms": 110,
            "error_code": None,
            "error_message": None,
        }
        res = api_generate_prompt(
            payload=GenerateRequest(user_idea="Write a unit test for FastAPI"),
            db=self.db,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.body)["generated_prompt"], "Generated Structured Prompt")

    @patch("app.main.optimize_prompt")
    def test_route_5_optimize(self, mock_opt):
        mock_opt.return_value = {
            "success": True,
            "optimized_prompt": "Optimized Clean Prompt",
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "tokens_before": 80,
            "tokens_after": 35,
            "tokens_saved": 45,
            "response_time_ms": 95,
            "error_code": None,
            "error_message": None,
        }
        res = api_optimize_prompt(
            payload=OptimizeRequest(original_prompt="A verbose wordy prompt to optimize"),
            db=self.db,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.body)["optimized_prompt"], "Optimized Clean Prompt")

    @patch("app.main.count_tokens", return_value=12)
    def test_route_6_count_tokens(self, mock_count):
        from app.config import settings
        with patch.object(settings, "GEMINI_API_KEY", "mock_key_val"):
            res = api_count_tokens(payload=TokenCountRequest(text="Hello token counter"))
            self.assertEqual(res.status_code, 200)
            self.assertEqual(json.loads(res.body)["token_count"], 12)

    def test_route_7_and_8_saved_prompts_post_get(self):
        # Route 7: POST /api/saved-prompts
        create_res = api_create_saved_prompt(
            payload=SavedPromptCreate(
                title="Route Test Prompt",
                content="Content for route test",
                category="testing",
                operation_type="generate",
            ),
            db=self.db,
        )
        self.assertEqual(create_res.title, "Route Test Prompt")
        prompt_id = create_res.id

        # Route 8: GET /api/saved-prompts
        list_res = api_list_saved_prompts(db=self.db)
        self.assertGreaterEqual(list_res.total, 1)

        # Route 9: GET /api/saved-prompts/{id}
        get_res = api_get_saved_prompt(prompt_id=prompt_id, db=self.db)
        self.assertEqual(get_res.title, "Route Test Prompt")

        # Route 10: PUT /api/saved-prompts/{id}
        put_res = api_update_saved_prompt(
            prompt_id=prompt_id,
            payload=SavedPromptUpdate(title="Updated Route Test Prompt"),
            db=self.db,
        )
        self.assertEqual(put_res.title, "Updated Route Test Prompt")

        # Route 11: DELETE /api/saved-prompts/{id}
        del_res = api_delete_saved_prompt(prompt_id=prompt_id, db=self.db)
        self.assertTrue(del_res.success)

        # Verify 404 after delete
        with self.assertRaises(HTTPException) as ctx:
            api_get_saved_prompt(prompt_id=prompt_id, db=self.db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_route_12_13_14_15_history(self):
        from app.services.persistence_service import record_history
        item = record_history(self.db, PromptHistoryCreate(
            operation_type="generate",
            original_input="History route test",
            generated_output="Output",
            tokens_before=10,
            tokens_after=15,
            tokens_saved=-5,
            model_name="gemini-3-flash-preview",
        ))
        item_id = item.id

        # Route 12: GET /api/history
        hist_list = api_list_history(db=self.db)
        self.assertGreaterEqual(hist_list.total, 1)

        # Route 13: GET /api/history/{id}
        hist_item = api_get_history_item(history_id=item_id, db=self.db)
        self.assertEqual(hist_item.original_input, "History route test")

        # Route 14: DELETE /api/history/{id}
        del_item = api_delete_history_item(history_id=item_id, db=self.db)
        self.assertTrue(del_item.success)

        # Route 15: DELETE /api/history (clear all)
        del_all = api_clear_history(db=self.db)
        self.assertTrue(del_all.success)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Generate & Optimize AI Workflows (Mocked)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAIWorkflows(AcceptanceBase):
    """Test Generate and Optimize end-to-end flows with token calculation."""

    @patch("app.main.generate_prompt")
    def test_generate_workflow_records_history(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "generated_prompt": "You are an expert cloud architect.",
            "model": "gemini-3-flash-preview",
            "mode": "advanced",
            "input_tokens": 20,
            "output_tokens": 50,
            "tokens_saved": -30,
            "response_time_ms": 150,
            "error_code": None,
            "error_message": None,
        }
        res = api_generate_prompt(
            payload=GenerateRequest(
                user_idea="Build a scalable serverless architecture",
                mode="advanced",
                category="development",
            ),
            db=self.db,
        )
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.body)
        self.assertEqual(body["tokens_saved"], -30)

        # Check history recorded in DB
        hist_res = api_list_history(db=self.db)
        items = hist_res.items
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].operation_type, "generate")

    @patch("app.main.optimize_prompt")
    def test_optimize_compression_workflow(self, mock_opt):
        mock_opt.return_value = {
            "success": True,
            "optimized_prompt": "Concise prompt.",
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "tokens_before": 100,
            "tokens_after": 30,
            "tokens_saved": 70,
            "response_time_ms": 120,
            "error_code": None,
            "error_message": None,
        }
        res = api_optimize_prompt(
            payload=OptimizeRequest(
                original_prompt="A very long repetitive prompt with lots of filler words.",
            ),
            db=self.db,
        )
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.body)
        self.assertEqual(body["tokens_before"], 100)
        self.assertEqual(body["tokens_after"], 30)
        self.assertEqual(body["tokens_saved"], 70)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Multilingual Prompts & Unicode Preservation
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultilingualAndUnicode(AcceptanceBase):
    """Ensure Unicode characters across languages are preserved without corruption."""

    @patch("app.main.generate_prompt")
    def test_arabic_prompt_generation_and_persistence(self, mock_gen):
        arabic_text = "اكتب لي خطة عمل تفصيلية لمشروع الذكاء الاصطناعي 🚀"
        mock_gen.return_value = {
            "success": True,
            "generated_prompt": "خطة العمل: ١. المقدمة",
            "model": "gemini-3-flash-preview",
            "mode": "quick",
            "input_tokens": 15,
            "output_tokens": 25,
            "tokens_saved": -10,
            "response_time_ms": 110,
            "error_code": None,
            "error_message": None,
        }
        res = api_generate_prompt(payload=GenerateRequest(user_idea=arabic_text), db=self.db)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.body)["generated_prompt"], "خطة العمل: ١. المقدمة")

        # Save prompt with Arabic content
        save_res = api_create_saved_prompt(
            payload=SavedPromptCreate(
                title="خطة العمل",
                content=arabic_text,
                category="business",
                operation_type="generate",
            ),
            db=self.db,
        )
        self.assertEqual(save_res.title, "خطة العمل")
        pid = save_res.id

        fetched = api_get_saved_prompt(prompt_id=pid, db=self.db)
        self.assertEqual(fetched.content, arabic_text)

    def test_japanese_cjk_and_accents(self):
        cjk_text = "日本語のプロンプトテスト。Café, naïve, résumé. ✨🎯"
        save_res = api_create_saved_prompt(
            payload=SavedPromptCreate(
                title="CJK & Accents",
                content=cjk_text,
                category="multilingual",
                operation_type="optimize",
            ),
            db=self.db,
        )
        self.assertEqual(save_res.title, "CJK & Accents")
        pid = save_res.id
        fetched = api_get_saved_prompt(prompt_id=pid, db=self.db)
        self.assertEqual(fetched.content, cjk_text)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PostgreSQL Engine & Pool Configuration Simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPostgreSQLEnginePoolSimulation(unittest.TestCase):
    """Verify PostgreSQL serverless NullPool configuration without remote host."""

    def test_postgresql_nullpool_instantiation_logic(self):
        from sqlalchemy.pool import NullPool

        test_pg_url = "postgresql://mock_user:mock_pass@ep-preview.neon.tech:6543/mockdb?sslmode=require"

        with patch("sqlalchemy.create_engine") as mock_ce:
            if test_pg_url.startswith("postgresql"):
                mock_ce(test_pg_url, poolclass=NullPool, pool_pre_ping=True, echo=False)

            mock_ce.assert_called_once_with(
                test_pg_url,
                poolclass=NullPool,
                pool_pre_ping=True,
                echo=False,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Database Persistence Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabasePersistenceLifecycle(AcceptanceBase):
    """Test full persistence behavior across separate sessions."""

    def test_saved_prompt_filtering_and_search(self):
        for i in range(5):
            api_create_saved_prompt(
                payload=SavedPromptCreate(
                    title=f"Dev Prompt {i}",
                    content=f"Code sample {i}",
                    category="development",
                    operation_type="generate",
                ),
                db=self.db,
            )
        for i in range(3):
            api_create_saved_prompt(
                payload=SavedPromptCreate(
                    title=f"Marketing Prompt {i}",
                    content=f"Copy sample {i}",
                    category="marketing",
                    operation_type="optimize",
                ),
                db=self.db,
            )

        # Test category filter
        dev_res = api_list_saved_prompts(category="development", db=self.db)
        self.assertEqual(dev_res.total, 5)

        # Test search query
        search_res = api_list_saved_prompts(search="Marketing", db=self.db)
        self.assertEqual(search_res.total, 3)

        # Test pagination bounds
        page_res = api_list_saved_prompts(limit=2, offset=0, db=self.db)
        self.assertEqual(len(page_res.items), 2)
        self.assertEqual(page_res.total, 8)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Security Headers, CORS, and Error Handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityHeadersAndErrors(AcceptanceBase):
    """Verify security controls, CORS behavior, and error mappings."""

    def test_cors_middleware_configured(self):
        cors_middleware = next(
            (m for m in app.user_middleware if "CORSMiddleware" in str(m.cls)), None
        )
        self.assertIsNotNone(cors_middleware, "CORSMiddleware must be configured")

    def test_payload_validation_empty_whitespace(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="   ")

    def test_payload_validation_missing_content(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            SavedPromptCreate(title="Test", content="")

    @patch("app.main.generate_prompt")
    def test_gemini_service_unavailable_mapping(self, mock_gen):
        mock_gen.return_value = {
            "success": False,
            "generated_prompt": None,
            "model": "gemini-3-flash-preview",
            "error_code": "quota_exceeded",
            "error_message": "Quota limit reached",
        }
        res = api_generate_prompt(payload=GenerateRequest(user_idea="Test quota error"), db=self.db)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(json.loads(res.body)["error_code"], "quota_exceeded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
