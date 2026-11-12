"""
test_evaluation_framework.py — Unit Tests for AutoPrompt Evaluation Framework (Phase 5.5).

Verifies:
1. Benchmark dataset integrity and complete 8-category coverage.
2. Token counting consistency and deterministic estimation.
3. Conversational preamble detector accuracy.
4. Generate evaluation rubric scoring, dimension weights, and thresholds.
5. Optimize evaluation rubric scoring and expansion policy enforcement.
6. Error detection on malformed or bloated inputs.
"""

from __future__ import annotations

import pytest

from tests.evaluation.dataset import (
    EVALUATION_DATASET,
    BenchmarkPrompt,
    get_dataset,
    get_prompt_by_id,
    get_prompts_by_category,
)
from tests.evaluation.evaluator import (
    check_preamble_freedom,
    deterministic_token_count,
    evaluate_generate,
    evaluate_optimize,
)

REQUIRED_CATEGORIES = [
    "General",
    "Coding",
    "Data Science",
    "Academic",
    "Business",
    "Creative",
    "Ambiguous",
    "Already Concise",
]


class TestEvaluationDataset:
    def test_dataset_coverage(self):
        """Dataset must cover all 8 required task categories."""
        categories = {p.category for p in EVALUATION_DATASET}
        for req in REQUIRED_CATEGORIES:
            assert req in categories, f"Missing category: {req}"

    def test_dataset_prompts_have_required_fields(self):
        """Every benchmark prompt must provide complete specification."""
        for p in EVALUATION_DATASET:
            assert p.id.strip(), "Prompt must have unique ID"
            assert p.category in REQUIRED_CATEGORIES
            assert p.operation in ("generate", "optimize")
            assert p.mode in ("quick", "advanced")
            assert len(p.input_text) > 0
            assert len(p.expected_intent) > 0
            assert len(p.key_concepts) > 0
            assert len(p.expected_constraints) > 0
            assert p.conciseness_expectation in ("expand_for_structure", "preserve_conciseness", "compress")
            assert len(p.reference_output.strip()) > 0

    def test_dataset_retrieval_helpers(self):
        """Test dataset query helpers."""
        assert len(get_dataset()) == len(EVALUATION_DATASET)
        coding_prompts = get_prompts_by_category("Coding")
        assert len(coding_prompts) >= 2
        p = get_prompt_by_id("gen_coding_01")
        assert p is not None
        assert p.id == "gen_coding_01"
        assert get_prompt_by_id("non_existent_id") is None


class TestEvaluatorTokenizerAndPreamble:
    def test_deterministic_token_count_empty(self):
        assert deterministic_token_count("") == 0
        assert deterministic_token_count("   ") == 0

    def test_deterministic_token_count_proportional(self):
        short_count = deterministic_token_count("Hello world")
        long_count = deterministic_token_count("Hello world " * 20)
        assert short_count > 0
        assert long_count > short_count

    def test_check_preamble_freedom_clean(self):
        clean_text = "## Role / Persona\nYou are an expert Python developer."
        is_clean, patterns = check_preamble_freedom(clean_text)
        assert is_clean is True
        assert len(patterns) == 0

    def test_check_preamble_freedom_detects_filler(self):
        filler_texts = [
            "Here is the generated prompt you requested:\n\nDo this task...",
            "Sure, here is your prompt:\n\nTask details...",
            "Certainly! Below is the prompt:\n\nDo something...",
            "Task instructions...\n\nHope this helps! Let me know if you need anything else.",
        ]
        for ft in filler_texts:
            is_clean, patterns = check_preamble_freedom(ft)
            assert is_clean is False, f"Failed to detect preamble in: {ft}"
            assert len(patterns) > 0


class TestGenerateEvaluationRubric:
    @pytest.fixture
    def generate_fixture(self) -> BenchmarkPrompt:
        p = get_prompt_by_id("gen_general_01")
        assert p is not None
        return p

    def test_reference_output_passes(self, generate_fixture):
        report = evaluate_generate(generate_fixture.reference_output, generate_fixture)
        assert report.passed is True
        assert report.composite_score >= 80.0
        assert report.dimensions["structure"].passed is True
        assert report.dimensions["intent"].passed is True

    def test_missing_sections_penalized(self, generate_fixture):
        # Text without standard sections
        bad_output = "Just summarize the meeting into a table and give me action items."
        report = evaluate_generate(bad_output, generate_fixture)
        assert report.dimensions["structure"].score < 50.0
        assert report.passed is False

    def test_rubric_weights_sum_to_one(self, generate_fixture):
        report = evaluate_generate(generate_fixture.reference_output, generate_fixture)
        total_weight = sum(dim.weight for dim in report.dimensions.values())
        assert abs(total_weight - 1.0) < 1e-4


class TestOptimizeEvaluationRubric:
    @pytest.fixture
    def concise_fixture(self) -> BenchmarkPrompt:
        p = get_prompt_by_id("opt_already_concise_01")
        assert p is not None
        return p

    @pytest.fixture
    def compress_fixture(self) -> BenchmarkPrompt:
        p = get_prompt_by_id("opt_general_02")
        assert p is not None
        return p

    def test_concise_reference_passes(self, concise_fixture):
        report = evaluate_optimize(
            original_text=concise_fixture.input_text,
            optimized_text=concise_fixture.reference_output,
            benchmark=concise_fixture,
        )
        assert report.passed is True
        assert report.dimensions["tokens"].score == 100.0

    def test_excessive_expansion_on_concise_penalized(self, concise_fixture):
        # Artificially expand concise prompt to 1200 chars
        bloated_output = (
            concise_fixture.reference_output
            + "\n\nAdditional unnecessary explanations:\n"
            + ("Explain everything in extreme detail with ten background paragraphs. " * 15)
        )
        report = evaluate_optimize(
            original_text=concise_fixture.input_text,
            optimized_text=bloated_output,
            benchmark=concise_fixture,
        )
        assert report.dimensions["tokens"].score < 70.0

    def test_compress_verbose_input_rewards_savings(self, compress_fixture):
        report = evaluate_optimize(
            original_text=compress_fixture.input_text,
            optimized_text=compress_fixture.reference_output,
            benchmark=compress_fixture,
        )
        assert report.passed is True
        assert report.token_metrics["tokens_saved"] > 0
        assert report.dimensions["tokens"].score == 100.0

    def test_serialization(self, concise_fixture):
        report = evaluate_optimize(
            original_text=concise_fixture.input_text,
            optimized_text=concise_fixture.reference_output,
            benchmark=concise_fixture,
        )
        d = report.to_dict()
        assert d["prompt_id"] == concise_fixture.id
        assert "composite_score" in d
        assert "token_metrics" in d
        assert "dimensions" in d
