"""
test_prompt_regression.py — Regression Test Suite for AutoPrompt Operations (Phase 5.5).

Covers 7 required regression scenarios:
1. Very short prompts ("help", "python loop")
2. Already optimized prompts (concise & precise)
3. Long prompts (>150 words with multiple detailed constraints)
4. Ambiguous prompts ("make it better", "fix code")
5. Multilingual prompts (French, Spanish, German, Arabic)
6. Prompts containing strict negative constraints ("Do not use regex", "Must be O(1) space")
7. Prompts where optimization increases token count (verifying honest negative token metrics)

Patching strategy: patch `get_gemini_client` (not the Settings property) to avoid
the Python 3.14 `@property` no-setter AttributeError discovered in Phase 5.4.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.gemini_service import generate_prompt, optimize_prompt
from tests.evaluation.evaluator import (
    deterministic_token_count,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_client(text: str) -> MagicMock:
    """Build a minimal Gemini client mock returning the given text."""
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp
    return mock_client


def _mock_generate(mock_output: str):
    """Context-manager wrapper: patches get_gemini_client + count_tokens."""
    return patch("app.services.gemini_service.get_gemini_client",
                 return_value=_make_mock_client(mock_output))


# ── Test Suite ────────────────────────────────────────────────────────────────

class TestPromptRegressionSuite:

    # ── 1. Very Short Prompts ─────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "short_input",
        [
            "help",
            "python loop",
            "write an email to my manager",
            "regex for email",
        ],
    )
    def test_regression_very_short_prompts(self, short_input: str):
        """Very short inputs must produce a non-empty structured generate response."""
        mock_output = (
            "## Role / Persona\nYou are an expert assistant.\n\n"
            "## Objective\nProvide a comprehensive solution for: " + short_input + ".\n\n"
            "## Instructions\n1. Clarify scope.\n2. Execute solution.\n\n"
            "## Expected Output Format\nStructured response with examples.\n\n"
            "## Constraints & Guardrails\nBe precise and direct."
        )

        with _mock_generate(mock_output), \
             patch("app.services.gemini_service.count_tokens", return_value=10):
            res = generate_prompt(short_input)

        assert res["success"] is True
        assert res["generated_prompt"] is not None
        assert len(res["generated_prompt"]) > 50, "Output too brief for a very short input"

    @pytest.mark.parametrize(
        "short_input",
        [
            "help",
            "python loop",
        ],
    )
    def test_regression_very_short_prompts_optimize(self, short_input: str):
        """Very short optimize inputs must succeed without raising exceptions."""
        mock_output = "Provide expert-level guidance for: " + short_input + ". Include clear steps and constraints."

        with _mock_generate(mock_output), \
             patch("app.services.gemini_service.count_tokens", return_value=10):
            res = optimize_prompt(short_input)

        assert res["success"] is True
        assert res["optimized_prompt"] is not None

    # ── 2. Already Optimized Prompts ──────────────────────────────────────────
    def test_regression_already_optimized_prompt_discipline(self):
        """
        An already concise, well-specified prompt should not be massively expanded.
        We mock token counts directly to control the calculation.
        """
        concise_prompt = (
            "Given array nums, return all unique triplets summing to 0. "
            "Time: O(N^2). Space: O(1). Output valid Python 3 code only."
        )
        mock_optimized = (
            "Given an array `nums`, return all unique triplets `[a, b, c]` such that `a + b + c == 0`.\n\n"
            "Constraints:\n- Time complexity: O(N^2) or better\n- Space complexity: O(1) auxiliary\n"
            "- Output valid Python 3 code only."
        )

        with _mock_generate(mock_optimized), \
             patch("app.services.gemini_service.count_tokens", side_effect=lambda t, model=None: (
                 30 if t == concise_prompt else 48
             )):
            res = optimize_prompt(concise_prompt)

        assert res["success"] is True
        assert res["original_tokens"] == 30
        assert res["optimized_tokens"] == 48
        # Token delta should be negative but within a modest range (< 50 expansion)
        assert abs(res["tokens_saved"]) < 50
        assert "Python 3" in res["optimized_prompt"]
        assert "O(N^2)" in res["optimized_prompt"]

    # ── 3. Long Prompts with Complex Constraints ───────────────────────────────
    def test_regression_long_prompt_preservation(self):
        """Long, detailed prompts must retain core directives after optimize."""
        long_prompt = (
            "You are a Senior Security Architect evaluating a Kubernetes cluster. "
            "Inspect for: 1. CIS Kubernetes Benchmark compliance. "
            "2. NetworkPolicies enforcing default-deny ingress/egress across all namespaces. "
            "3. Pod Security Standards set to Restricted mode. No privilege escalation. "
            "4. mTLS with Istio service mesh and cert-manager certificate rotation. "
            "5. Secret encryption at rest via AWS KMS envelope encryption. "
            "Deliverable: Audit checklist with severity (Critical/High/Medium/Low), "
            "remediation kubectl commands, and verification steps. "
            "Do not use legacy PodSecurityPolicies."
        )
        mock_optimized = (
            "As a Senior Security Architect, audit the Kubernetes cluster against:\n"
            "1. CIS Kubernetes Benchmark compliance.\n"
            "2. Default-deny NetworkPolicies for all namespaces (ingress + egress).\n"
            "3. Pod Security Standards in Restricted mode, no privilege escalation.\n"
            "4. mTLS via Istio + cert-manager auto-rotation.\n"
            "5. AWS KMS envelope encryption for Secrets at rest.\n\n"
            "Deliverable: Severity-ranked checklist (Critical/High/Medium/Low) with kubectl "
            "remediation commands and verification steps. Do not use PodSecurityPolicies."
        )

        with _mock_generate(mock_optimized), \
             patch("app.services.gemini_service.count_tokens", return_value=50):
            res = optimize_prompt(long_prompt)

        assert res["success"] is True
        assert "CIS Kubernetes Benchmark" in res["optimized_prompt"]
        assert "PodSecurityPolicies" in res["optimized_prompt"]
        assert "privilege escalation" in res["optimized_prompt"]

    # ── 4. Ambiguous & Underspecified Prompts ─────────────────────────────────
    @pytest.mark.parametrize("ambiguous_input", ["make it better", "fix code", "improve SEO"])
    def test_regression_ambiguous_prompts_generate(self, ambiguous_input: str):
        """Ambiguous prompts should produce structured diagnostic template responses."""
        mock_output = (
            "## Role / Persona\nYou are an expert diagnostic consultant.\n\n"
            "## Objective\nProvide a systematic framework to address: " + ambiguous_input + ".\n\n"
            "## Instructions\n1. Request input context.\n2. Apply diagnostic rubric.\n\n"
            "## Expected Output Format\nStep-by-step remediation guide.\n\n"
            "## Constraints & Guardrails\nDo not invent unstated assumptions."
        )

        with _mock_generate(mock_output), \
             patch("app.services.gemini_service.count_tokens", return_value=10):
            res = generate_prompt(ambiguous_input)

        assert res["success"] is True
        assert "Role / Persona" in res["generated_prompt"]
        assert "Objective" in res["generated_prompt"]

    # ── 5. Multilingual Prompts ────────────────────────────────────────────────
    @pytest.mark.parametrize(
        "lang, prompt_text",
        [
            ("French", "Rédigez un prompt pour analyser la fidélité des clients dans une entreprise SaaS."),
            ("Spanish", "Cree un prompt para optimizar consultas SQL lentas en una base de datos PostgreSQL."),
            ("German", "Erstellen Sie einen Prompt zur Analyse von Kundendaten mit Python und Pandas."),
            ("Arabic", "اكتب موجه احترافي لتحليل مشاعر العملاء باستخدام بايثون."),
        ],
    )
    def test_regression_multilingual_prompts(self, lang: str, prompt_text: str):
        """Multilingual prompt inputs must process without UTF-8 encoding errors."""
        mock_output = f"## Role / Persona\nExpert prompt engineer ({lang} context).\n\n## Objective\nAddress the request systematically."

        with _mock_generate(mock_output), \
             patch("app.services.gemini_service.count_tokens", return_value=20):
            res = generate_prompt(prompt_text)

        assert res["success"] is True, f"Multilingual prompt failed for {lang}"
        assert res["generated_prompt"] is not None
        assert len(res["generated_prompt"]) > 20

    # ── 6. Strict Constraints & Guardrails ────────────────────────────────────
    def test_regression_strict_constraints_preservation(self):
        """Strict negative constraints injected into input must appear in generated output."""
        task_with_constraints = (
            "Write a Python function to validate email addresses. "
            "DO NOT USE REGEX. Must execute under 10 microseconds. "
            "No third-party packages allowed."
        )
        mock_output = (
            "## Role / Persona\nPython Algorithm Engineer.\n\n"
            "## Objective\nImplement an email validation function.\n\n"
            "## Instructions\n1. Parse the email string character-by-character.\n2. Validate '@' and domain components.\n\n"
            "## Constraints & Guardrails\n"
            "- STRICT: DO NOT USE REGEX.\n"
            "- Execution latency under 10 microseconds.\n"
            "- Python standard library only. No third-party packages allowed."
        )

        with _mock_generate(mock_output), \
             patch("app.services.gemini_service.count_tokens", return_value=35):
            res = generate_prompt(task_with_constraints)

        assert res["success"] is True
        assert "DO NOT USE REGEX" in res["generated_prompt"]
        assert "third-party" in res["generated_prompt"] or "third_party" in res["generated_prompt"] or "third party" in res["generated_prompt"]

    # ── 7. Honest Negative Token Savings ─────────────────────────────────────
    def test_regression_honest_token_expansion_metrics(self):
        """
        When optimization expands a prompt for structure, tokens_saved must be
        negative and mathematically exact: tokens_saved = original_tokens - optimized_tokens.
        reduction_percentage = (tokens_saved / original_tokens) * 100
        """
        short_prompt = "audit my cloud security"
        expanded_output = (
            "Act as a Cloud Security Auditor.\n\n"
            "Requirements:\n"
            "1. Audit IAM policies for least-privilege access.\n"
            "2. Verify S3 bucket public access blocks.\n"
            "3. Ensure CloudTrail multi-region logging is active.\n"
            "Deliverable: Prioritized finding table with remediation steps."
        )

        # Simulate exact token counts via mock:
        # original = 8, optimized = 56, saved = -48, pct = -600.0%
        def _count(text, model=None):
            return 8 if text == short_prompt else 56

        with _mock_generate(expanded_output), \
             patch("app.services.gemini_service.count_tokens", side_effect=_count):
            res = optimize_prompt(short_prompt)

        assert res["success"] is True
        assert res["original_tokens"] == 8
        assert res["optimized_tokens"] == 56
        assert res["tokens_saved"] == -48              # 8 - 56 = -48
        assert res["reduction_percentage"] == -600.0   # (-48 / 8) * 100 = -600.0
        # Must be negative: no fabricated compression
        assert res["tokens_saved"] < 0
        assert res["reduction_percentage"] < 0.0
