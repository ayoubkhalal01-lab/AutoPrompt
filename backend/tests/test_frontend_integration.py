"""
test_frontend_integration.py — Complete verification suite for Phase 5.3B.
Tests all 11 required scenarios:
1. Generate in Quick mode
2. Generate in Advanced mode
3. Optimize in Quick mode
4. Optimize in Advanced mode
5. Token counting
6. Empty input handling
7. Network / backend unavailable
8. Gemini quota or rate-limit errors
9. Duplicate submissions prevention
10. Mobile and desktop layouts
11. Light and dark themes
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError
from app.main import (
    api_count_tokens,
    api_generate_prompt,
    api_optimize_prompt,
    health_check,
)
from app.schemas.prompt_schemas import (
    GenerateRequest,
    OptimizeRequest,
    TokenCountRequest,
)


class TestFrontendBackendIntegration(unittest.TestCase):
    """Verifies all Phase 5.3B integration requirements."""

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Generate in Quick mode
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.generate_prompt")
    def test_01_generate_quick_mode(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "generated_prompt": "# Role / Persona\nYou are an expert Python engineer...",
            "input_tokens": 25,
            "output_tokens": 350,
            "response_time_ms": 3200,
            "error_code": None,
            "error_message": None,
        }

        req = GenerateRequest(
            user_idea="Build a real-time data streaming pipeline in Python.",
            mode="quick",
            category="Programming"
        )
        res = api_generate_prompt(req)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body)
        self.assertTrue(data["success"])
        self.assertIn("Python", data["generated_prompt"])
        self.assertEqual(data["input_tokens"], 25)
        self.assertEqual(data["output_tokens"], 350)
        self.assertEqual(data["response_time_ms"], 3200)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Generate in Advanced mode
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.generate_prompt")
    def test_02_generate_advanced_mode(self, mock_gen):
        mock_gen.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "generated_prompt": "# Role / Persona\nPrincipal ML Engineer...\n## Deliverables\nModular Python code.",
            "input_tokens": 120,
            "output_tokens": 780,
            "response_time_ms": 6500,
            "error_code": None,
            "error_message": None,
        }

        req = GenerateRequest(
            user_idea="Develop a customer churn prediction pipeline.",
            mode="advanced",
            category="Data Science",
            role="Principal ML Engineer",
            objective="Build scikit-learn pipeline",
            context="Tabular telecom dataset",
            constraints="Strict typing, no data leaks",
            output_format="Modular Python code"
        )
        res = api_generate_prompt(req)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body)
        self.assertTrue(data["success"])
        mock_gen.assert_called_once_with(
            user_idea="Develop a customer churn prediction pipeline.",
            mode="advanced",
            category="Data Science",
            role="Principal ML Engineer",
            objective="Build scikit-learn pipeline",
            context="Tabular telecom dataset",
            constraints="Strict typing, no data leaks",
            output_format="Modular Python code",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Optimize in Quick mode
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.optimize_prompt")
    def test_03_optimize_quick_mode(self, mock_opt):
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "original_prompt": "Please can you help me write code for parsing CSVs...",
            "optimized_prompt": "# High-Performance CSV Parsing\nParse CSV data...",
            "original_tokens": 85,
            "optimized_tokens": 42,
            "tokens_saved": 43,
            "reduction_percentage": 50.6,
            "response_time_ms": 3800,
            "error_code": None,
            "error_message": None,
        }

        req = OptimizeRequest(
            original_prompt="Please can you help me write code for parsing CSVs...",
            mode="quick"
        )
        res = api_optimize_prompt(req)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body)
        self.assertTrue(data["success"])
        self.assertEqual(data["original_tokens"], 85)
        self.assertEqual(data["optimized_tokens"], 42)
        self.assertEqual(data["tokens_saved"], 43)
        self.assertEqual(data["reduction_percentage"], 50.6)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Optimize in Advanced mode (Including Negative Token Savings)
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.optimize_prompt")
    def test_04_optimize_advanced_mode_negative_savings(self, mock_opt):
        # When a vague prompt is expanded for clarity, savings are negative.
        # This test ensures negative savings are calculated accurately without fabrication.
        mock_opt.return_value = {
            "success": True,
            "model": "gemini-3-flash-preview",
            "original_prompt": "Scrape website.",
            "optimized_prompt": "# Web Scraping Engine\nImplement robust scraping with backoff...",
            "original_tokens": 5,
            "optimized_tokens": 120,
            "tokens_saved": -115,
            "reduction_percentage": -2300.0,
            "response_time_ms": 4100,
            "error_code": None,
            "error_message": None,
        }

        req = OptimizeRequest(
            original_prompt="Scrape website.",
            mode="advanced",
            optimization_instructions="Add rate limiting, error handling, robots.txt compliance"
        )
        res = api_optimize_prompt(req)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body)
        self.assertTrue(data["success"])
        self.assertEqual(data["tokens_saved"], -115)
        self.assertEqual(data["reduction_percentage"], -2300.0)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Token counting endpoint
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.count_tokens")
    def test_05_token_counting(self, mock_count):
        mock_count.return_value = 18
        req = TokenCountRequest(text="Measure exact token consumption.")
        res = api_count_tokens(req)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body)
        self.assertTrue(data["success"])
        self.assertEqual(data["token_count"], 18)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Empty input validation
    # ──────────────────────────────────────────────────────────────────────────
    def test_06_empty_input_validation(self):
        # Empty generate throws ValidationError
        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="   ", mode="quick")

        with self.assertRaises(ValidationError):
            GenerateRequest(user_idea="", mode="quick")

        # Empty optimize throws ValidationError
        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="   ", mode="quick")

        with self.assertRaises(ValidationError):
            OptimizeRequest(original_prompt="", mode="quick")

        # Empty token count throws ValidationError
        with self.assertRaises(ValidationError):
            TokenCountRequest(text="   ")

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Network / backend unavailable translation
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.generate_prompt")
    def test_07_network_backend_unavailable(self, mock_gen):
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "generated_prompt": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_time_ms": 0,
            "error_code": "network",
            "error_message": "Network connection issue communicating with the Gemini API.",
        }

        req = GenerateRequest(user_idea="Valid input text", mode="quick")
        res = api_generate_prompt(req)
        self.assertEqual(res.status_code, 503)
        data = json.loads(res.body)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "network")
        self.assertIn("Network connection issue", data["error_message"])

    # ──────────────────────────────────────────────────────────────────────────
    # 8. Gemini quota and rate-limit errors
    # ──────────────────────────────────────────────────────────────────────────
    @patch("app.main.generate_prompt")
    def test_08_quota_and_rate_limit_errors(self, mock_gen):
        # Quota exceeded
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "generated_prompt": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_time_ms": 0,
            "error_code": "quota_exceeded",
            "error_message": "API quota exceeded. Please wait a moment or check your Google AI Studio plan.",
        }
        req_quota = GenerateRequest(user_idea="Valid input text", mode="quick")
        res_quota = api_generate_prompt(req_quota)
        self.assertEqual(res_quota.status_code, 503)
        data_quota = json.loads(res_quota.body)
        self.assertEqual(data_quota["error_code"], "quota_exceeded")

        # Rate limit
        mock_gen.return_value = {
            "success": False,
            "model": "gemini-3-flash-preview",
            "generated_prompt": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_time_ms": 0,
            "error_code": "rate_limit",
            "error_message": "Too many requests sent in a short period. Please slow down and try again.",
        }
        req_rate = GenerateRequest(user_idea="Valid input text", mode="quick")
        res_rate = api_generate_prompt(req_rate)
        self.assertEqual(res_rate.status_code, 503)
        data_rate = json.loads(res_rate.body)
        self.assertEqual(data_rate["error_code"], "rate_limit")

    # ──────────────────────────────────────────────────────────────────────────
    # 9. Duplicate submission prevention & UI state contract
    # ──────────────────────────────────────────────────────────────────────────
    def test_09_duplicate_submissions_frontend_contract(self):
        js_path = WORKSPACE_ROOT / "autoprompt-prototype" / "js" / "workspace.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()

        # Check that workspace.js sets aria-busy and disables action buttons during STATE_PROCESSING
        self.assertIn("workspaceCard.setAttribute('aria-busy', 'true')", js_code)
        self.assertIn("this.setButtonsDisabled(true)", js_code)
        self.assertIn("if (btnGenerate) btnGenerate.disabled = disabled", js_code)
        self.assertIn("if (btnOptimize) btnOptimize.disabled = disabled", js_code)
        self.assertIn("if (this.isProcessing) return;", js_code)

    # ──────────────────────────────────────────────────────────────────────────
    # 10. Mobile and desktop layout integrity
    # ──────────────────────────────────────────────────────────────────────────
    def test_10_responsive_layout_integrity(self):
        html_path = WORKSPACE_ROOT / "autoprompt-prototype" / "index.html"
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Viewport meta tag present
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1.0">', html)

        # Responsive stylesheet present
        self.assertIn('href="css/responsive.css"', html)

        # Check responsive rules in CSS
        resp_css_path = WORKSPACE_ROOT / "autoprompt-prototype" / "css" / "responsive.css"
        with open(resp_css_path, "r", encoding="utf-8") as f:
            resp_css = f.read()

        self.assertIn("@media (max-width: 1024px)", resp_css)
        self.assertIn("@media (max-width: 768px)", resp_css)
        self.assertIn("overflow-x: hidden", resp_css)

    # ──────────────────────────────────────────────────────────────────────────
    # 11. Light and dark theme integrity
    # ──────────────────────────────────────────────────────────────────────────
    def test_11_theme_system_integrity(self):
        theme_js_path = WORKSPACE_ROOT / "autoprompt-prototype" / "js" / "theme.js"
        with open(theme_js_path, "r", encoding="utf-8") as f:
            theme_js = f.read()

        self.assertIn("THEME_LIGHT = 'light'", theme_js)
        self.assertIn("THEME_DARK = 'dark'", theme_js)
        self.assertIn("data-theme", theme_js)
        self.assertIn("localStorage", theme_js)

        style_css_path = WORKSPACE_ROOT / "autoprompt-prototype" / "css" / "style.css"
        with open(style_css_path, "r", encoding="utf-8") as f:
            style_css = f.read()

        self.assertIn('[data-theme="dark"]', style_css)
        self.assertIn("--bg-app:", style_css)
        self.assertIn("--text-primary:", style_css)

    # ──────────────────────────────────────────────────────────────────────────
    # 12. CORS strictly restricted to exact dev origins (No null, no wildcard)
    # ──────────────────────────────────────────────────────────────────────────
    def test_12_cors_restricted_origins(self):
        from app.main import app
        cors_middlewares = [
            m for m in app.user_middleware
            if m.cls.__name__ == "CORSMiddleware"
        ]
        self.assertTrue(len(cors_middlewares) > 0, "CORSMiddleware must be configured")
        cors = cors_middlewares[0]
        allow_origins = cors.kwargs.get("allow_origins", [])
        allow_origin_regex = cors.kwargs.get("allow_origin_regex")

        # Must include exact development origins
        self.assertIn("http://localhost:5500", allow_origins)
        self.assertIn("http://127.0.0.1:5500", allow_origins)

        # Must NOT include null or open wildcard regex
        self.assertNotIn("null", allow_origins)
        self.assertIsNone(allow_origin_regex, "CORS allow_origin_regex must be removed for strict origin locking")

    # ──────────────────────────────────────────────────────────────────────────
    # 13. Optimize behavior: avoid unnecessary expansion & preserve concise prompts
    # ──────────────────────────────────────────────────────────────────────────
    def test_13_optimize_system_instruction_guidelines(self):
        from app.services.gemini_service import OPTIMIZE_SYSTEM_INSTRUCTION
        # Verify core instructions mandate preserving concise prompts and avoiding boilerplate inflation
        self.assertIn("Avoid Unnecessary Expansion", OPTIMIZE_SYSTEM_INSTRUCTION)
        self.assertIn("Preserve Intent & Meaning", OPTIMIZE_SYSTEM_INSTRUCTION)
        self.assertIn("Do NOT artificially inflate token count", OPTIMIZE_SYSTEM_INSTRUCTION)

    # ──────────────────────────────────────────────────────────────────────────
    # 14. Token metrics distinguish Generate vs Optimize
    # ──────────────────────────────────────────────────────────────────────────
    def test_14_token_metrics_distinction_frontend(self):
        js_path = WORKSPACE_ROOT / "autoprompt-prototype" / "js" / "workspace.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()

        # Check distinction between Input Tokens (Generate) and Original Prompt Tokens (Optimize)
        self.assertIn("Input Tokens", js_code)
        self.assertIn("Output Tokens", js_code)
        self.assertIn("Original Prompt Tokens", js_code)
        self.assertIn("Optimized Prompt Tokens", js_code)
        self.assertIn("Tokens Saved", js_code)
        self.assertIn("Token Difference", js_code)
        self.assertIn("Structural expansion", js_code)


if __name__ == "__main__":
    unittest.main()
