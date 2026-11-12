"""
test_prompt_quality.py — AutoPrompt Phase 5.1: Gemini Prompt Quality Testing

Evaluates Gemini's ability to perform AutoPrompt's two core operations:
1. Generate: From a high-level idea/instruction, create a full structured prompt.
2. Optimize: From a vague prompt, produce a refined, clear, token-efficient prompt.

Tests performed:
- Test A: Generate prompt quality (3 iterations)
- Test B: Optimize prompt quality (3 iterations)
- Test C: Consistency evaluation across iterations
- Test D: Token measurement & token economics analysis
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.gemini_service import (
    count_tokens,
    generate_prompt,
    optimize_prompt,
)

# Test inputs defined in specification
TEST_A_INPUT = (
    "Create a professional prompt for analyzing customer churn in a telecommunications "
    "company using Python and machine learning."
)

TEST_B_INPUT = (
    "Analyze my data and tell me why customers leave. Use Python and give me useful results."
)

# Expected criteria for automated heuristic verification
CRITERIA_A = {
    "role": ["role", "persona", "expert", "specialist", "scientist"],
    "context": ["context", "telecommunication", "telecom", "background", "subscriber"],
    "objective": ["objective", "goal", "predict", "churn", "attrition"],
    "instructions": ["instruction", "step", "directive", "workflow", "1.", "2."],
    "format": ["output format", "expected output", "deliverable", "structure", "format"],
    "constraints": ["constraint", "guardrail", "boundary", "library", "assumption", "limit"],
}

CRITERIA_B = {
    "intent_preserved": ["churn", "leave", "attrition", "customer", "python"],
    "specificity_added": ["model", "feature", "metric", "preprocessing", "analysis", "insight"],
    "no_data_invented": ["your dataset", "provided data", "input data", "data schema", "dataset"],
    "output_format": ["output format", "deliverable", "summary", "structure", "recommendation"],
}


def evaluate_generate_output(text: str) -> dict[str, Any]:
    """Score the generated prompt on key structural criteria."""
    lower = text.lower()
    scores = {}
    for criterion, keywords in CRITERIA_A.items():
        matched = [k for k in keywords if k in lower]
        scores[criterion] = {
            "passed": len(matched) > 0,
            "matched_keywords": matched,
        }
    passed_count = sum(1 for s in scores.values() if s["passed"])
    total_criteria = len(CRITERIA_A)
    return {
        "criteria": scores,
        "score_percent": round((passed_count / total_criteria) * 100, 1),
        "all_passed": passed_count == total_criteria,
    }


def evaluate_optimize_output(text: str) -> dict[str, Any]:
    """Score the optimized prompt on key refinement criteria."""
    lower = text.lower()
    scores = {}
    for criterion, keywords in CRITERIA_B.items():
        matched = [k for k in keywords if k in lower]
        scores[criterion] = {
            "passed": len(matched) > 0,
            "matched_keywords": matched,
        }
    passed_count = sum(1 for s in scores.values() if s["passed"])
    total_criteria = len(CRITERIA_B)
    return {
        "criteria": scores,
        "score_percent": round((passed_count / total_criteria) * 100, 1),
        "all_passed": passed_count == total_criteria,
    }


def run_quality_tests(iterations: int = 3) -> dict[str, Any]:
    """Execute all quality tests and return detailed results."""
    print("=" * 70)
    print("AutoPrompt — Phase 5.1: Gemini Prompt Quality Testing")
    print(f"Model: {settings.GEMINI_MODEL}")
    print(f"Iterations per test: {iterations}")
    print("=" * 70)

    results: dict[str, Any] = {
        "metadata": {
            "model": settings.GEMINI_MODEL,
            "iterations": iterations,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        },
        "test_a_generate": {
            "input": TEST_A_INPUT,
            "input_tokens": count_tokens(TEST_A_INPUT),
            "runs": [],
        },
        "test_b_optimize": {
            "input": TEST_B_INPUT,
            "input_tokens": count_tokens(TEST_B_INPUT),
            "runs": [],
        },
        "summary": {},
    }

    # ── Test A: Generate ──────────────────────────────────────────────────────
    print("\n[TEST A] Executing Generate Prompt...")
    for i in range(1, iterations + 1):
        print(f"  Run {i}/{iterations}...", end="", flush=True)
        res = generate_prompt(TEST_A_INPUT, category="Data Science")
        eval_res = evaluate_generate_output(res.get("generated_prompt", "") or "")
        run_data = {
            "run_index": i,
            "success": res["success"],
            "response_time_ms": res["response_time_ms"],
            "output_tokens": res["output_tokens"],
            "api_usage": res["api_usage"],
            "evaluation": eval_res,
            "output_text": res["generated_prompt"],
        }
        results["test_a_generate"]["runs"].append(run_data)
        status_sym = "[PASS]" if res["success"] and eval_res["all_passed"] else "[WARN]"
        print(f" {status_sym} ({res['response_time_ms']} ms, {res['output_tokens']} tokens, score: {eval_res['score_percent']}%)")
        time.sleep(1)  # small pause between calls

    # ── Test B: Optimize ──────────────────────────────────────────────────────
    print("\n[TEST B] Executing Optimize Prompt...")
    for i in range(1, iterations + 1):
        print(f"  Run {i}/{iterations}...", end="", flush=True)
        res = optimize_prompt(TEST_B_INPUT)
        eval_res = evaluate_optimize_output(res.get("optimized_prompt", "") or "")
        run_data = {
            "run_index": i,
            "success": res["success"],
            "response_time_ms": res["response_time_ms"],
            "output_tokens": res["output_tokens"],
            "api_usage": res["api_usage"],
            "evaluation": eval_res,
            "output_text": res["optimized_prompt"],
        }
        results["test_b_optimize"]["runs"].append(run_data)
        status_sym = "[PASS]" if res["success"] and eval_res["all_passed"] else "[WARN]"
        print(f" {status_sym} ({res['response_time_ms']} ms, {res['output_tokens']} tokens, score: {eval_res['score_percent']}%)")
        time.sleep(1)

    # ── Test C & D Analysis ───────────────────────────────────────────────────
    gen_times = [r["response_time_ms"] for r in results["test_a_generate"]["runs"] if r["success"]]
    opt_times = [r["response_time_ms"] for r in results["test_b_optimize"]["runs"] if r["success"]]
    gen_tokens = [r["output_tokens"] for r in results["test_a_generate"]["runs"] if r["success"]]
    opt_tokens = [r["output_tokens"] for r in results["test_b_optimize"]["runs"] if r["success"]]
    gen_scores = [r["evaluation"]["score_percent"] for r in results["test_a_generate"]["runs"]]
    opt_scores = [r["evaluation"]["score_percent"] for r in results["test_b_optimize"]["runs"]]

    results["summary"] = {
        "test_a_avg_time_ms": round(sum(gen_times) / len(gen_times), 1) if gen_times else 0,
        "test_a_avg_tokens": round(sum(gen_tokens) / len(gen_tokens), 1) if gen_tokens else 0,
        "test_a_avg_score": round(sum(gen_scores) / len(gen_scores), 1) if gen_scores else 0,
        "test_b_avg_time_ms": round(sum(opt_times) / len(opt_times), 1) if opt_times else 0,
        "test_b_avg_tokens": round(sum(opt_tokens) / len(opt_tokens), 1) if opt_tokens else 0,
        "test_b_avg_score": round(sum(opt_scores) / len(opt_scores), 1) if opt_scores else 0,
        "all_runs_succeeded": all(r["success"] for r in results["test_a_generate"]["runs"]) and
                              all(r["success"] for r in results["test_b_optimize"]["runs"]),
    }

    return results


if __name__ == "__main__":
    test_results = run_quality_tests(iterations=3)
    # Dump results as JSON for report generator
    out_path = BACKEND_DIR / "reports" / "test_results.json"
    out_path.write_text(json.dumps(test_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {out_path}")
