"""
test_api_endpoints.py — Comprehensive automated tests for AutoPrompt Phase 5.3A.

Covers:
- Schema validation (Pydantic constraints, min/max lengths, whitespace trimming)
- Valid Generate request (quick & advanced modes)
- Valid Optimize request (including negative token savings calculation)
- Token counting endpoint
- Empty input validation
- Invalid payload & mode validation
- Long input validation
- Gemini API error handling (safe HTTP 503 translation)
- Rate limit handling (HTTP 503, rate_limit)
- Quota exhaustion handling (HTTP 503, quota_exceeded)
- Health and diagnostics endpoints
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError

from app.main import (
    api_count_tokens,
    api_generate_prompt,
    api_optimize_prompt,
    health_check,
    test_gemini as endpoint_test_gemini,
)
from app.schemas.prompt_schemas import (
    GenerateRequest,
    GenerateResponse,
    OptimizeRequest,
    OptimizeResponse,
    TokenCountRequest,
    TokenCountResponse,
)


class TestSchemaValidation(unittest.TestCase):
    """Test Pydantic model validations and constraints."""

    def test_valid_generate_request_quick(self):
        req = GenerateRequest(
            user_idea="Analyze customer churn in telecom using Python",
            mode="quick",
        )
        self.assertEqual(req.user_idea, "Analyze customer churn in telecom using Python")
        self.assertEqual(req.mode, "quick")
        self.assertIsNone(req.category)

    def test_valid_generate_request_advanced(self):
        req = GenerateRequest(
            user_idea="Create a recommendation engine in PyTorch",
            mode="advanced",
            category="Programming",
            role="Deep Learning Engineer",
            objective="Build collaborative filtering model",
            context="Movie ratings dataset with 1M rows",
            constraints="Max latency 50ms",
            output_format="Python module with unit tests",
        )
        self.assertEqual(req.mode, "advanced")
        self.assertEqual(req.role, "Deep Learning Engineer")
        self.assertEqual(req.constraints, "Max latency 50ms")

    def test_empty_user_idea_raises(self):
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="   ")

    def test_short_user_idea_raises(self):
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="hi")

    def test_long_user_idea_raises(self):
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="A" * 10001)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="Build an app", mode="invalid_mode")  # type: ignore

    def test_valid_optimize_request(self):
        req = OptimizeRequest(
            original_prompt="Analyze my data and tell me why customers leave.",
            mode="quick",
            optimization_instructions="Focus on ML pipelines",
        )
        self.assertEqual(req.original_prompt, "Analyze my data and tell me why customers leave.")
        self.assertEqual(req.optimization_instructions, "Focus on ML pipelines")

    def test_empty_optimize_prompt_raises(self):
        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="   ")

    def test_short_optimize_prompt_raises(self):
        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="ab")

    def test_long_optimize_prompt_raises(self):
        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="B" * 15001)

    def test_valid_token_count_request(self):
        req = TokenCountRequest(text="Hello world")
        self.assertEqual(req.text, "Hello world")

    def test_empty_token_count_request_raises(self):
        with self.assertRaises(ValidationError):
            TokenCountRequest(text="   ")

    def test_long_token_count_request_raises(self):
        with self.assertRaises(ValidationError):
            TokenCountRequest(text="C" * 50001)


class TestEndpointHandlers(unittest.TestCase):
    """Test API endpoint route handlers with mocked service layer."""

    def test_health_check_handler(self):
        resp = health_check()
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "ok")
        self.assertIn("gemini_key_configured", body)
        self.assertIn("gemini_model", body)

    @patch("app.main.test_gemini_connection")
    def test_test_gemini_success(self, mock_test):
        mock_test.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "response_time_ms": 150,
            "response_text": "I am working correctly.",
            "error_code": None,
            "error_message": None,
        }
        resp = endpoint_test_gemini()
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertTrue(body["success"])

    @patch("app.main.test_gemini_connection")
    def test_test_gemini_failure(self, mock_test):
        mock_test.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "response_time_ms": 60,
            "response_text": None,
            "error_code": "api_key_invalid",
            "error_message": "Invalid key.",
        }
        resp = endpoint_test_gemini()
        self.assertEqual(resp.status_code, 503)
        body = json.loads(resp.body)
        self.assertFalse(body["success"])
        self.assertEqual(body["error_code"], "api_key_invalid")

    @patch("app.main.generate_prompt")
    def test_generate_endpoint_success(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "generated_prompt": "# Role\nData Scientist\n# Objective\nAnalyze churn",
            "input_tokens": 20,
            "output_tokens": 150,
            "response_time_ms": 1200,
            "error_code": None,
            "error_message": None,
        }
        req = GenerateRequest(
            user_idea="Analyze customer churn in telecom using Python",
            mode="quick",
        )
        resp = api_generate_prompt(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["model"], "gemini-3-flash-preview")
        self.assertIn("# Role", body["generated_prompt"])
        self.assertEqual(body["input_tokens"], 20)
        self.assertEqual(body["output_tokens"], 150)

    @patch("app.main.generate_prompt")
    def test_generate_endpoint_advanced_parameters(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "generated_prompt": "# Advanced Prompt",
            "input_tokens": 50,
            "output_tokens": 300,
            "response_time_ms": 1800,
            "error_code": None,
            "error_message": None,
        }
        req = GenerateRequest(
            user_idea="Build an ML pipeline",
            mode="advanced",
            category="Data Science",
            role="ML Engineer",
            objective="Predict churn",
            context="Telecom subscription data",
            constraints="No data leakage",
            output_format="Clean Python script",
        )
        resp = api_generate_prompt(req)
        self.assertEqual(resp.status_code, 200)
        mock_gen.assert_called_once_with(
            user_idea="Build an ML pipeline",
            mode="advanced",
            category="Data Science",
            role="ML Engineer",
            objective="Predict churn",
            context="Telecom subscription data",
            constraints="No data leakage",
            output_format="Clean Python script",
        )

    @patch("app.main.generate_prompt")
    def test_generate_endpoint_gemini_error(self, mock_gen):
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "generated_prompt": None,
            "input_tokens": 10,
            "output_tokens": 0,
            "response_time_ms": 300,
            "error_code": "network",
            "error_message": "Network connection issue.",
        }
        req = GenerateRequest(user_idea="Test idea")
        resp = api_generate_prompt(req)
        self.assertEqual(resp.status_code, 503)
        body = json.loads(resp.body)
        self.assertFalse(body["success"])
        self.assertEqual(body["error_code"], "network")

    @patch("app.main.generate_prompt")
    def test_generate_endpoint_quota_exhausted(self, mock_gen):
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "generated_prompt": None,
            "input_tokens": 10,
            "output_tokens": 0,
            "response_time_ms": 200,
            "error_code": "quota_exceeded",
            "error_message": "API quota exceeded.",
        }
        req = GenerateRequest(user_idea="Test idea")
        resp = api_generate_prompt(req)
        self.assertEqual(resp.status_code, 503)
        body = json.loads(resp.body)
        self.assertEqual(body["error_code"], "quota_exceeded")

    @patch("app.main.optimize_prompt")
    def test_optimize_endpoint_success(self, mock_opt):
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "original_prompt": "Tell me why customers leave with python.",
            "optimized_prompt": "# Role: Churn Analyst\nIdentify attrition factors using Python.",
            "original_tokens": 15,
            "optimized_tokens": 12,
            "tokens_saved": 3,
            "reduction_percentage": 20.0,
            "response_time_ms": 1100,
            "error_code": None,
            "error_message": None,
        }
        req = OptimizeRequest(original_prompt="Tell me why customers leave with python.")
        resp = api_optimize_prompt(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["tokens_saved"], 3)
        self.assertEqual(body["reduction_percentage"], 20.0)

    @patch("app.main.optimize_prompt")
    def test_optimize_endpoint_negative_token_savings(self, mock_opt):
        # When a vague 10-token prompt is expanded into a 100-token prompt
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "original_prompt": "Analyze my data.",
            "optimized_prompt": "# Role\nData Scientist\n# Tasks\n1. Inspect data...",
            "original_tokens": 5,
            "optimized_tokens": 50,
            "tokens_saved": -45,
            "reduction_percentage": -900.0,
            "response_time_ms": 1400,
            "error_code": None,
            "error_message": None,
        }
        req = OptimizeRequest(original_prompt="Analyze my data.")
        resp = api_optimize_prompt(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertEqual(body["tokens_saved"], -45)
        self.assertEqual(body["reduction_percentage"], -900.0)
        self.assertLess(body["tokens_saved"], 0)

    @patch("app.main.optimize_prompt")
    def test_optimize_endpoint_rate_limit(self, mock_opt):
        mock_opt.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "original_prompt": "Prompt to optimize.",
            "optimized_prompt": None,
            "original_tokens": 6,
            "optimized_tokens": 0,
            "tokens_saved": 0,
            "reduction_percentage": 0.0,
            "response_time_ms": 150,
            "error_code": "rate_limit",
            "error_message": "Rate limit reached.",
        }
        req = OptimizeRequest(original_prompt="Prompt to optimize.")
        resp = api_optimize_prompt(req)
        self.assertEqual(resp.status_code, 503)
        body = json.loads(resp.body)
        self.assertFalse(body["success"])
        self.assertEqual(body["error_code"], "rate_limit")

    @patch("app.main.count_tokens")
    def test_count_tokens_endpoint_success(self, mock_count):
        mock_count.return_value = 42
        req = TokenCountRequest(text="Hello world, measure my tokens.")
        resp = api_count_tokens(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["token_count"], 42)


if __name__ == "__main__":
    unittest.main(verbosity=2)
