"""
test_ai_architecture_reliability.py — Phase 5.4 Architecture & Reliability Unit Tests.

Covers:
- Configuration validation (API key presence, placeholders, timeouts, retries)
- Centralized error taxonomy and status mapping
- Retry behavior (transient vs non-transient errors)
- Timeout behavior handling
- Response normalization (empty, null, or whitespace-only provider responses)
- Logging security (asserting API keys and user prompts are never logged)
- Generate & Optimize regression contracts
"""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings
from app.main import ERROR_HTTP_STATUS, _resolve_status_code
from app.schemas.prompt_schemas import GenerateResponse, OptimizeResponse
from app.services.gemini_service import (
    SAFE_ERROR_HINTS,
    TRANSIENT_ERROR_CODES,
    classify_error,
    generate_prompt,
    optimize_prompt,
)


class TestAIConfiguration(unittest.TestCase):
    """Test AI configuration isolation, key validation, and defaults."""

    def test_has_gemini_key_logic(self):
        s = Settings()
        s.GEMINI_API_KEY = ""
        self.assertFalse(s.has_gemini_key)

        s.GEMINI_API_KEY = "your_gemini_api_key_here"
        self.assertFalse(s.has_gemini_key)

        s.GEMINI_API_KEY = "AIzaSyFakeValidKey12345"
        self.assertTrue(s.has_gemini_key)

    def test_configurable_model_and_timeouts(self):
        s = Settings()
        self.assertIsInstance(s.GEMINI_MODEL, str)
        self.assertTrue(len(s.GEMINI_MODEL) > 0)
        self.assertGreater(s.GEMINI_TIMEOUT_SECONDS, 0)
        self.assertGreaterEqual(s.GEMINI_MAX_RETRIES, 1)


class TestErrorClassification(unittest.TestCase):
    """Test centralized error taxonomy mapping."""

    def test_classify_quota_exceeded_429(self):
        exc = Exception("429 RESOURCE_EXHAUSTED: You exceeded your current quota")
        code, msg = classify_error(exc)
        self.assertEqual(code, "quota_exceeded")
        self.assertEqual(msg, SAFE_ERROR_HINTS["quota_exceeded"])

    def test_classify_rate_limit(self):
        exc = Exception("429 Too Many Requests: Rate limit exceeded")
        code, msg = classify_error(exc)
        self.assertEqual(code, "rate_limit")
        self.assertEqual(msg, SAFE_ERROR_HINTS["rate_limit"])

    def test_classify_invalid_api_key(self):
        exc = Exception("API key not valid. Please pass a valid API key.")
        code, msg = classify_error(exc)
        self.assertEqual(code, "api_key_invalid")
        self.assertEqual(msg, SAFE_ERROR_HINTS["api_key_invalid"])

    def test_classify_timeout(self):
        exc = Exception("Request timed out after 30000ms")
        code, msg = classify_error(exc)
        self.assertEqual(code, "timeout")
        self.assertEqual(msg, SAFE_ERROR_HINTS["timeout"])

    def test_classify_network(self):
        exc = Exception("getaddrinfo failed: Connection reset by peer")
        code, msg = classify_error(exc)
        self.assertEqual(code, "network")
        self.assertEqual(msg, SAFE_ERROR_HINTS["network"])

    def test_classify_model_not_found(self):
        exc = Exception("Model not found: models/gemini-unknown 404")
        code, msg = classify_error(exc)
        self.assertEqual(code, "model_not_found")
        self.assertEqual(msg, SAFE_ERROR_HINTS["model_not_found"])

    def test_classify_unknown(self):
        exc = Exception("Some completely unexpected exception string")
        code, msg = classify_error(exc)
        self.assertEqual(code, "unknown")
        self.assertEqual(msg, SAFE_ERROR_HINTS["unknown"])

    def test_http_status_resolution(self):
        self.assertEqual(_resolve_status_code({"success": True}), 200)
        self.assertEqual(_resolve_status_code({"success": False, "error_code": "quota_exceeded"}), 503)
        self.assertEqual(_resolve_status_code({"success": False, "error_code": "invalid_response"}), 502)
        self.assertEqual(_resolve_status_code({"success": False, "error_code": "unknown"}), 500)


class TestRetryAndTimeoutPolicy(unittest.TestCase):
    """Test that only transient errors are retried and bounded retries are enforced."""

    @patch("app.services.gemini_service.time.sleep")
    @patch("app.services.gemini_service.get_gemini_client")
    def test_transient_error_retries_bounded(self, mock_client_factory, mock_sleep):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("connection reset")
        mock_client_factory.return_value = mock_client

        with patch("app.config.settings.GEMINI_MAX_RETRIES", 2):
            result = generate_prompt(user_idea="Test retry logic", mode="quick")

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "network")
        # Should have attempted exactly 2 times (initial + 1 retry)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("app.services.gemini_service.time.sleep")
    @patch("app.services.gemini_service.get_gemini_client")
    def test_non_transient_quota_error_never_retried(self, mock_client_factory, mock_sleep):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED quota")
        mock_client_factory.return_value = mock_client

        with patch("app.config.settings.GEMINI_MAX_RETRIES", 2):
            result = generate_prompt(user_idea="Test quota exhaustion", mode="quick")

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "quota_exceeded")
        # Quota exhaustion must terminate immediately on attempt 1
        self.assertEqual(mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()


class TestResponseNormalization(unittest.TestCase):
    """Test handling of empty, null, or malformed provider responses."""

    @patch("app.services.gemini_service.get_gemini_client")
    def test_empty_string_response_normalized_to_error(self, mock_client_factory):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "   "  # whitespace-only response
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_factory.return_value = mock_client

        result = generate_prompt(user_idea="Testing empty response", mode="quick")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "invalid_response")
        self.assertIn("empty or unparseable response", result["error_message"])

    @patch("app.services.gemini_service.get_gemini_client")
    def test_null_text_response_normalized_to_error(self, mock_client_factory):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = None  # Blocked candidate / null text
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_factory.return_value = mock_client

        result = optimize_prompt(original_prompt="Testing null response", mode="quick")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "invalid_response")
        self.assertIsNone(result["optimized_prompt"])

    @patch("app.services.gemini_service.count_tokens")
    @patch("app.services.gemini_service.get_gemini_client")
    def test_valid_response_properly_stripped(self, mock_client_factory, mock_count):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "  # Valid Generated Output  \n\n"
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_factory.return_value = mock_client
        mock_count.return_value = 10

        result = generate_prompt(user_idea="Testing valid prompt", mode="quick")
        self.assertTrue(result["success"])
        self.assertEqual(result["generated_prompt"], "# Valid Generated Output")


class TestLoggingSecurity(unittest.TestCase):
    """Test that logging captures operational metadata without leaking sensitive data."""

    @patch("app.services.gemini_service.get_gemini_client")
    def test_never_logs_user_prompt_or_api_key(self, mock_client_factory):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Optimized output content."
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_factory.return_value = mock_client

        sensitive_prompt = "TOP_SECRET_USER_PASSWORD_12345"
        sensitive_key = "AIzaSySuperSecretKeyNotForLogs"

        with patch("app.config.settings.GEMINI_API_KEY", sensitive_key):
            with self.assertLogs("autoprompt.ai", level="INFO") as cm:
                optimize_prompt(original_prompt=sensitive_prompt, mode="quick")

            all_logs = " ".join(cm.output)
            # Must log operational telemetry
            self.assertIn("op=optimize", all_logs)
            self.assertIn("model=", all_logs)
            self.assertIn("AI operation", all_logs)

            # Must NEVER log the prompt text or API key
            self.assertNotIn(sensitive_prompt, all_logs)
            self.assertNotIn(sensitive_key, all_logs)


class TestResponseContractRegression(unittest.TestCase):
    """Ensure response dictionaries strictly conform to Pydantic schemas."""

    @patch("app.services.gemini_service.get_gemini_client")
    def test_generate_response_schema_conformity(self, mock_client_factory):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "# Structured Persona Prompt"
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_factory.return_value = mock_client

        result = generate_prompt(user_idea="Build an ML pipeline", mode="quick")
        # Throws ValidationError if dictionary does not match schema contract
        validated = GenerateResponse(**result)
        self.assertTrue(validated.success)
        self.assertEqual(validated.generated_prompt, "# Structured Persona Prompt")

    @patch("app.services.gemini_service.get_gemini_client")
    def test_optimize_response_schema_conformity(self, mock_client_factory):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Refined prompt directives"
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_factory.return_value = mock_client

        result = optimize_prompt(original_prompt="Raw vague text", mode="quick")
        validated = OptimizeResponse(**result)
        self.assertTrue(validated.success)
        self.assertEqual(validated.original_prompt, "Raw vague text")
        self.assertEqual(validated.optimized_prompt, "Refined prompt directives")


if __name__ == "__main__":
    unittest.main()
