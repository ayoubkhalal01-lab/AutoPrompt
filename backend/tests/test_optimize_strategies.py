"""
test_optimize_strategies.py

Regression tests for the dual-strategy optimizer:
  - Quality strategy: may expand token count; preservation_note must be set when it does.
  - Token strategy: must REDUCE token count; mandatory constraints must survive.

Does NOT call the live Gemini API — it exercises the pure rule-based path
(_token_optimize) and the service layer with mocked internals.
"""

from __future__ import annotations

import os
import sys

# Allow direct import of app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.services.gemini_service import _token_optimize


# ── Test fixtures ─────────────────────────────────────────────────────────────

# This is the exact prompt reported by the user as having 111 tokens.
SAMPLE_PROMPT_111 = """# Role
You are a senior data scientist specializing in customer behavior analysis.

# Context
We have a telecommunications dataset with approximately 10,000 customer records.
The dataset includes features such as tenure, monthly charges, contract type, and churn label.

# Objective
Build an end-to-end churn classification pipeline that identifies customers at high risk of leaving.

# Instructions
Please make sure to perform the following steps:
1. Ensure that you conduct exploratory data analysis to understand the data distribution.
2. It is important that you preprocess the data (handle missing values, encode categoricals, scale numerics).
3. Train and evaluate at least two classification models.
4. Make sure to compare models using ROC-AUC, precision, recall, and F1 score.
5. Provide recommendations based on the model outputs.

# Constraints
You must use scikit-learn and XGBoost. Do not leak test data into the training set.
The pipeline must not exceed 200 ms latency per prediction in production.""".strip()

CONSTRAINT_PROMPT = """You are a code reviewer.
Please review the Python function below and provide feedback.
Make sure to ensure that all issues are explained clearly.
The review must not exceed 500 words.
You must flag any security vulnerabilities.
Do not omit performance issues.""".strip()


# ── Lightweight token counter that works without network ─────────────────────

def simple_token_count(text: str) -> int:
    """Approximate token count: words + punctuation tokens."""
    import re
    return len(re.findall(r"\S+", text))


# ── Tests for _token_optimize (rule-based, no LLM) ────────────────────────────

class TestTokenOptimizeHelper:
    """Unit tests for the _token_optimize helper."""

    def test_removes_markdown_headings(self):
        text = "# Role\nYou are an expert.\n## Context\nSome background."
        result = _token_optimize(text)
        assert "# Role" not in result
        assert "## Context" not in result
        assert "You are an expert." in result
        assert "Some background." in result

    def test_removes_filler_phrases(self):
        text = "make sure to validate the input. Ensure that the output is JSON."
        result = _token_optimize(text)
        assert "make sure to" not in result.lower()
        assert "Ensure that" not in result
        # Core meaning preserved
        assert "validate" in result
        assert "JSON" in result

    def test_merges_bullet_list(self):
        text = "Do the following:\n- clean the data\n- train the model\n- evaluate results"
        result = _token_optimize(text)
        # Bullets merged — no leading "- "
        assert "- clean" not in result
        assert "clean the data" in result
        assert "train the model" in result
        assert "evaluate results" in result

    def test_preserves_constraint_lines(self):
        """Lines with constraint keywords must survive verbatim."""
        text = (
            "# Instructions\n"
            "Process the input.\n"
            "The pipeline must not exceed 200 ms latency per prediction.\n"
            "You must use scikit-learn and XGBoost.\n"
            "Do not leak test data into the training set.\n"
        )
        result = _token_optimize(text)
        assert "must not exceed 200 ms latency" in result
        assert "must use scikit-learn" in result
        assert "Do not leak test data" in result

    def test_token_reduce_on_sample_prompt(self):
        """Token strategy must reduce token count on the sample prompt."""
        original_tokens = simple_token_count(SAMPLE_PROMPT_111)
        optimized = _token_optimize(SAMPLE_PROMPT_111)
        optimized_tokens = simple_token_count(optimized)

        assert optimized_tokens < original_tokens, (
            f"Token strategy EXPANDED the prompt: {original_tokens} → {optimized_tokens}\n"
            f"Optimized:\n{optimized}"
        )

    def test_constraint_survives_on_sample_prompt(self):
        """The 'must not exceed 200 ms latency' constraint must survive token optimization."""
        optimized = _token_optimize(SAMPLE_PROMPT_111)
        assert "must not exceed 200 ms latency" in optimized, (
            f"Critical latency constraint was removed by token optimizer.\nOutput:\n{optimized}"
        )

    def test_constraint_prompt_all_constraints_survive(self):
        """Every constraint line in CONSTRAINT_PROMPT must appear in the output."""
        result = _token_optimize(CONSTRAINT_PROMPT)
        assert "must not exceed 500 words" in result, f"Constraint missing. Output:\n{result}"
        assert "must flag any security vulnerabilities" in result, f"Constraint missing. Output:\n{result}"
        assert "Do not omit performance issues" in result, f"Constraint missing. Output:\n{result}"

    def test_empty_headings_only_returns_empty(self):
        text = "# Role\n## Context\n### Instructions"
        result = _token_optimize(text)
        # All lines were headings; result should be empty or very short
        assert len(result.strip()) == 0


# ── Tests for optimize_prompt service layer (mocked LLM + token counter) ─────

def _make_settings_with_key(monkeypatch, gemini_service, has_key: bool):
    """Patch settings.has_gemini_key (a property) using its class."""
    monkeypatch.setattr(
        type(gemini_service.settings), "has_gemini_key",
        property(lambda self: has_key)
    )


def _mock_count_tokens(monkeypatch, gemini_service):
    """Replace count_tokens with a word-count approximation (no network needed)."""
    monkeypatch.setattr(gemini_service, "count_tokens", simple_token_count)


class TestOptimizePromptService:
    """
    Tests the full optimize_prompt function.
    For the TOKEN strategy the LLM is not called, so no mocking needed.
    For QUALITY strategy we patch _execute_ai_request.
    """

    def test_token_strategy_no_llm_call(self, monkeypatch):
        """TOKEN strategy must NOT call _execute_ai_request when no custom instructions."""
        from app.services import gemini_service

        called = []

        def fake_execute(*args, **kwargs):
            called.append(True)
            return (True, "fake result", 0, None, None)

        monkeypatch.setattr(gemini_service, "_execute_ai_request", fake_execute)
        _make_settings_with_key(monkeypatch, gemini_service, True)
        _mock_count_tokens(monkeypatch, gemini_service)

        result = gemini_service.optimize_prompt(
            original_prompt=SAMPLE_PROMPT_111,
            strategy="token",
        )

        assert not called, "TOKEN strategy should not call LLM when no custom instructions"
        assert result["success"] is True
        assert result["optimized_tokens"] < result["original_tokens"], (
            f"Token strategy must reduce tokens: {result['original_tokens']} → {result['optimized_tokens']}"
        )
        assert result["preservation_note"] is None, "TOKEN strategy must never set preservation_note"

    def test_quality_strategy_calls_llm(self, monkeypatch):
        """QUALITY strategy must call _execute_ai_request and set preservation_note when tokens rise."""
        from app.services import gemini_service

        # Simulate LLM expanding the prompt (as observed in production)
        expanded = SAMPLE_PROMPT_111 + "\n\nConsider scalability, maintainability, and observability." * 8
        called = []

        def fake_execute(*args, **kwargs):
            called.append(True)
            return (True, expanded, 500, None, None)

        monkeypatch.setattr(gemini_service, "_execute_ai_request", fake_execute)
        _make_settings_with_key(monkeypatch, gemini_service, True)
        _mock_count_tokens(monkeypatch, gemini_service)

        result = gemini_service.optimize_prompt(
            original_prompt=SAMPLE_PROMPT_111,
            strategy="quality",
        )

        assert called, "QUALITY strategy must call LLM"
        assert result["success"] is True
        # When quality strategy expands the prompt, preservation_note must be set
        if result["optimized_tokens"] > result["original_tokens"]:
            assert result["preservation_note"] is not None, (
                "preservation_note must explain token expansion for quality strategy"
            )
            note_lower = result["preservation_note"].lower()
            assert "quality" in note_lower or "token" in note_lower

    def test_no_api_key_returns_error(self, monkeypatch):
        """Service must return structured error when API key is missing."""
        from app.services import gemini_service
        _make_settings_with_key(monkeypatch, gemini_service, False)

        result = gemini_service.optimize_prompt(
            original_prompt="Analyze my data.",
            strategy="quality",
        )

        assert result["success"] is False
        assert result["error_code"] == "api_key_not_found"
        assert result["preservation_note"] is None

    def test_token_strategy_tokens_saved_positive(self, monkeypatch):
        """tokens_saved and reduction_percentage must be positive for TOKEN strategy on sample prompt."""
        from app.services import gemini_service
        _make_settings_with_key(monkeypatch, gemini_service, True)
        _mock_count_tokens(monkeypatch, gemini_service)

        result = gemini_service.optimize_prompt(
            original_prompt=SAMPLE_PROMPT_111,
            strategy="token",
        )

        assert result["tokens_saved"] > 0, (
            f"Expected positive tokens_saved, got {result['tokens_saved']}"
        )
        assert result["reduction_percentage"] > 0, (
            f"Expected positive reduction_percentage, got {result['reduction_percentage']}"
        )

    def test_response_schema_complete(self, monkeypatch):
        """Response must always contain all required fields."""
        from app.services import gemini_service
        _make_settings_with_key(monkeypatch, gemini_service, True)
        _mock_count_tokens(monkeypatch, gemini_service)

        result = gemini_service.optimize_prompt(
            original_prompt="Simple prompt to test.",
            strategy="token",
        )

        required_keys = {
            "success", "model", "original_prompt", "optimized_prompt",
            "original_tokens", "optimized_tokens", "tokens_saved",
            "reduction_percentage", "response_time_ms", "error_code",
            "error_message", "preservation_note",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"Response missing fields: {missing}"
