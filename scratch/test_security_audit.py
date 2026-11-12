"""
test_security_audit.py — Dedicated security audit verification tests for AutoPrompt Phase 7.3.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base, SavedPrompt
from app.main import (
    app,
    health_check,
    api_list_saved_prompts,
    api_list_history,
)
from app.schemas.persistence_schemas import (
    SavedPromptCreate,
    SavedPromptUpdate,
    PromptHistoryCreate,
)
from app.schemas.prompt_schemas import (
    GenerateRequest,
    OptimizeRequest,
    TokenCountRequest,
)
from app.services.gemini_service import classify_error
from app.services.persistence_service import list_saved_prompts


class TestSecurityHardening(unittest.TestCase):
    """Verify security controls implemented in Phase 7.3."""

    def test_health_check_no_information_disclosure(self):
        """Health check MUST NOT disclose python version or OS platform."""
        resp = health_check()
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertNotIn("python", body, "Python version should not be leaked in /health")
        self.assertNotIn("platform", body, "OS platform should not be leaked in /health")
        self.assertIn("status", body)
        self.assertEqual(body["status"], "ok")
        self.assertIn("gemini_key_configured", body)
        # Verify API key itself is never exposed
        self.assertNotIn("GEMINI_API_KEY", body)
        self.assertNotIn("api_key", body)

    def test_cors_headers_hardened(self):
        """CORS middleware should not allow wildcard headers."""
        # Find CORSMiddleware in app.user_middleware
        cors_middlewares = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
        self.assertTrue(len(cors_middlewares) > 0, "CORSMiddleware should be configured")
        cors_kwargs = cors_middlewares[0].kwargs
        allow_headers = cors_kwargs.get("allow_headers", [])
        self.assertNotIn("*", allow_headers, "allow_headers must not contain wildcard '*'")
        self.assertIn("Content-Type", allow_headers)

    def test_saved_prompt_max_content_length_enforced(self):
        """SavedPromptCreate must reject oversized payloads (> 50,000 characters)."""
        valid_prompt = SavedPromptCreate(
            title="Valid Title",
            content="A" * 50000,
            category="Coding",
            operation_type="generate",
        )
        self.assertEqual(len(valid_prompt.content), 50000)

        with self.assertRaises(ValidationError):
            SavedPromptCreate(
                title="Excessive Title",
                content="A" * 50001,
                category="Coding",
                operation_type="generate",
            )

    def test_saved_prompt_update_max_content_length_enforced(self):
        """SavedPromptUpdate must reject oversized payloads (> 50,000 characters)."""
        with self.assertRaises(ValidationError):
            SavedPromptUpdate(
                content="B" * 50001,
            )

    def test_prompt_history_max_content_length_enforced(self):
        """PromptHistoryCreate must reject oversized original_input (> 50,000 characters)."""
        with self.assertRaises(ValidationError):
            PromptHistoryCreate(
                operation_type="generate",
                original_input="C" * 50001,
            )

    def test_pagination_bounds_saved_prompts(self):
        """Negative limit or huge limit must be clamped to safe boundaries [1, 100]."""
        mock_db = MagicMock()
        mock_db.scalar.return_value = 0
        mock_db.scalars.return_value.all.return_value = []

        resp = api_list_saved_prompts(limit=1000000, offset=-10, db=mock_db)
        self.assertEqual(resp.limit, 100, "Limit exceeding 100 must be clamped to 100")
        self.assertEqual(resp.offset, 0, "Negative offset must be clamped to 0")

        resp_min = api_list_saved_prompts(limit=-5, offset=0, db=mock_db)
        self.assertEqual(resp_min.limit, 1, "Limit < 1 must be clamped to 1")

    def test_pagination_bounds_history(self):
        """History pagination limit must be clamped to safe boundaries [1, 100]."""
        mock_db = MagicMock()
        mock_db.scalar.return_value = 0
        mock_db.scalars.return_value.all.return_value = []

        resp = api_list_history(limit=999999, offset=-5, db=mock_db)
        self.assertEqual(resp.limit, 100, "History limit exceeding 100 must be clamped to 100")
        self.assertEqual(resp.offset, 0, "Negative offset must be clamped to 0")

    def test_sql_injection_resistant_search(self):
        """SQL injection attempts in search queries must be safely handled via ORM parameterization."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Insert dummy records
        prompt = SavedPrompt(
            title="Regular Prompt",
            content="This is safe content",
            category="General",
            operation_type="generate",
        )
        session.add(prompt)
        session.commit()

        # Attempt SQL injection search patterns
        injections = [
            "' OR '1'='1",
            "'; DROP TABLE saved_prompts; --",
            "\" OR 1=1 --",
            "' UNION SELECT * FROM saved_prompts --",
        ]
        for payload in injections:
            total, items = list_saved_prompts(session, search=payload)
            self.assertEqual(total, 0, f"SQL injection payload '{payload}' should match nothing")

        # Confirm table still intact and accessible
        total, items = list_saved_prompts(session)
        self.assertEqual(total, 1)

        session.close()

    def test_xss_payload_in_pydantic_accepted_as_plain_data(self):
        """Pydantic schemas should accept strings containing HTML/JS safely as raw data without execution."""
        xss_payload = '<script>alert("XSS")</script><img src="x" onerror="alert(1)">'
        req = GenerateRequest(user_idea=xss_payload)
        self.assertEqual(req.user_idea, xss_payload)

        prompt_in = SavedPromptCreate(
            title="XSS Test",
            content=xss_payload,
            category="Security",
            operation_type="generate",
        )
        self.assertEqual(prompt_in.content, xss_payload)

    def test_classify_error_sanitization(self):
        """classify_error must categorize all exceptions into safe, standardized error codes without leaking paths/stack traces."""
        test_cases = [
            (Exception("404 models/gemini-2.0-flash is not found"), "model_not_found"),
            (Exception("ResourceExhausted: 429 Quota exceeded"), "quota_exceeded"),
            (Exception("Connection timed out after 30000ms"), "timeout"),
            (Exception("API_KEY_INVALID: The provided key is invalid"), "api_key_invalid"),
            (Exception("Unexpected internal failure with raw path C:\\secret\\path\\file.py"), "unknown"),
        ]
        for exc, expected_code in test_cases:
            code, message = classify_error(exc)
            self.assertEqual(code, expected_code, f"Exception '{exc}' should classify as '{expected_code}', got '{code}'")
            self.assertIsInstance(message, str)
            self.assertNotIn("secret", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
