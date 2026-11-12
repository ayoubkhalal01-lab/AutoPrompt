"""
run_benchmark.py — Benchmark Runner for AutoPrompt Phase 5.5.

Executes systematic evaluation across the 16 curated benchmark prompts in
tests/evaluation/dataset.py.

Modes:
- Reference Mode (default / deterministic): Evaluates verified reference outputs
  without invoking external APIs, establishing ground-truth baselines.
- Live Mode (`--live`): Executes live requests through AutoPrompt's Gemini service,
  evaluating real model responses while strictly reporting response times and token counts.

Outputs:
- Generates `backend/reports/evaluation_results.json`
- Prints formatted console summary
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.gemini_service import (
    count_tokens,
    generate_prompt,
    optimize_prompt,
)
from tests.evaluation.dataset import EVALUATION_DATASET, BenchmarkPrompt
from tests.evaluation.evaluator import (
    EvaluationReport,
    deterministic_token_count,
    evaluate_generate,
    evaluate_optimize,
)


def run_benchmark(
    use_live_api: bool = False,
    category_filter: str | None = None,
) -> dict[str, Any]:
    """
    Run evaluation suite across all benchmark items.
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())
    mode_label = "Live Gemini API" if use_live_api else "Deterministic Baseline Reference"

    print("=" * 78)
    print(f"AutoPrompt — Phase 5.5 Evaluation & Benchmark Runner")
    print(f"Execution Mode: {mode_label}")
    print(f"Active Model  : {settings.GEMINI_MODEL if use_live_api else 'Reference Output (Ground Truth)'}")
    print(f"Timestamp     : {timestamp}")
    print("=" * 78)

    items = EVALUATION_DATASET
    if category_filter:
        items = [p for p in items if p.category.lower() == category_filter.lower()]
        print(f"Filtered by category: {category_filter} ({len(items)} prompts)")

    reports: list[dict[str, Any]] = []
    category_scores: dict[str, list[float]] = {}
    token_stats: list[dict[str, Any]] = []

    live_call_count = 0

    for idx, bench in enumerate(items, 1):
        print(f"[{idx:02d}/{len(items):02d}] {bench.id:<22} | {bench.category:<15} | {bench.operation:<8}...", end="", flush=True)

        resp_time_ms = 0
        error_info: dict[str, Any] | None = None

        if use_live_api:
            # Live invocation through AutoPrompt Gemini Service
            live_call_count += 1
            if bench.operation == "generate":
                api_resp = generate_prompt(
                    user_idea=bench.input_text,
                    mode=bench.mode,
                    category=bench.category,
                    role=bench.advanced_params.get("role"),
                    objective=bench.advanced_params.get("objective"),
                    context=bench.advanced_params.get("context"),
                    constraints=bench.advanced_params.get("constraints"),
                    output_format=bench.advanced_params.get("output_format"),
                )
                output_text = api_resp.get("generated_prompt") or ""
                resp_time_ms = api_resp.get("response_time_ms", 0)
                in_tok = api_resp.get("input_tokens", 0)
                out_tok = api_resp.get("output_tokens", 0)
                if not api_resp["success"]:
                    error_info = {
                        "error_code": api_resp.get("error_code"),
                        "error_message": api_resp.get("error_message"),
                    }
                eval_rep = evaluate_generate(
                    output_text=output_text,
                    benchmark=bench,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                )
            else:
                api_resp = optimize_prompt(
                    original_prompt=bench.input_text,
                    mode=bench.mode,
                    optimization_instructions=bench.advanced_params.get("optimization_instructions"),
                )
                output_text = api_resp.get("optimized_prompt") or ""
                resp_time_ms = api_resp.get("response_time_ms", 0)
                orig_tok = api_resp.get("original_tokens", 0)
                opt_tok = api_resp.get("optimized_tokens", 0)
                if not api_resp["success"]:
                    error_info = {
                        "error_code": api_resp.get("error_code"),
                        "error_message": api_resp.get("error_message"),
                    }
                eval_rep = evaluate_optimize(
                    original_text=bench.input_text,
                    optimized_text=output_text,
                    benchmark=bench,
                    original_tokens=orig_tok,
                    optimized_tokens=opt_tok,
                )
            # Sleep 1.5s between live calls to be conservative with quota
            time.sleep(1.5)
        else:
            # Deterministic reference output evaluation
            output_text = bench.reference_output
            if bench.operation == "generate":
                in_tok = deterministic_token_count(bench.input_text)
                out_tok = deterministic_token_count(output_text)
                eval_rep = evaluate_generate(
                    output_text=output_text,
                    benchmark=bench,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                )
            else:
                orig_tok = deterministic_token_count(bench.input_text)
                opt_tok = deterministic_token_count(output_text)
                eval_rep = evaluate_optimize(
                    original_text=bench.input_text,
                    optimized_text=output_text,
                    benchmark=bench,
                    original_tokens=orig_tok,
                    optimized_tokens=opt_tok,
                )

        rep_dict = eval_rep.to_dict()
        rep_dict["response_time_ms"] = resp_time_ms
        rep_dict["evaluated_text"] = output_text
        if error_info:
            rep_dict["error_info"] = error_info

        reports.append(rep_dict)

        # Track category statistics
        category_scores.setdefault(bench.category, []).append(eval_rep.composite_score)
        token_stats.append(eval_rep.token_metrics)

        status_flag = "[PASS]" if eval_rep.passed else "[FAIL]"
        print(f" {status_flag} Score: {eval_rep.composite_score:>5.1f}% | Time: {resp_time_ms:>4}ms")

    # ── Summary Calculations ──────────────────────────────────────────────────
    all_scores = [r["composite_score"] for r in reports]
    passed_count = sum(1 for r in reports if r["passed"])
    pass_rate = round((passed_count / max(1, len(reports))) * 100.0, 1)
    avg_score = round(sum(all_scores) / max(1, len(all_scores)), 1)

    category_summary = {}
    for cat, scores in category_scores.items():
        category_summary[cat] = {
            "prompt_count": len(scores),
            "average_score": round(sum(scores) / len(scores), 1),
            "min_score": min(scores),
            "max_score": max(scores),
        }

    # Token efficiency statistics
    optimize_reports = [r for r in reports if r["operation"] == "optimize"]
    expansion_cases = [r for r in optimize_reports if r["token_metrics"].get("tokens_saved", 0) < 0]
    compression_cases = [r for r in optimize_reports if r["token_metrics"].get("tokens_saved", 0) > 0]
    neutral_cases = [r for r in optimize_reports if r["token_metrics"].get("tokens_saved", 0) == 0]

    benchmark_summary: dict[str, Any] = {
        "metadata": {
            "timestamp": timestamp,
            "mode": "live" if use_live_api else "reference",
            "model": settings.GEMINI_MODEL if use_live_api else "reference_gold_standard",
            "total_prompts": len(reports),
            "live_api_calls_made": live_call_count,
        },
        "aggregate_metrics": {
            "overall_pass_rate_pct": pass_rate,
            "overall_average_score": avg_score,
            "passed_prompts": passed_count,
            "failed_prompts": len(reports) - passed_count,
        },
        "category_performance": category_summary,
        "token_efficiency_analysis": {
            "total_optimize_prompts": len(optimize_reports),
            "compression_prompts_count": len(compression_cases),
            "expansion_prompts_count": len(expansion_cases),
            "neutral_prompts_count": len(neutral_cases),
            "explanation": (
                "Token expansion is expected and honest when prompts lack crucial guardrails, "
                "context, or deliverables. Concise prompts are preserved without unnecessary inflation."
            ),
        },
        "detailed_results": reports,
    }

    # Save results to JSON
    reports_dir = BACKEND_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "evaluation_results.json"
    json_path.write_text(json.dumps(benchmark_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary table
    print("\n" + "=" * 78)
    print("BENCHMARK EXECUTION SUMMARY")
    print("=" * 78)
    print(f"Total Prompts Evaluated: {len(reports)}")
    print(f"Overall Pass Rate      : {pass_rate}% ({passed_count}/{len(reports)} passed)")
    print(f"Overall Average Score  : {avg_score}%")
    print(f"Live API Calls Used    : {live_call_count}")
    print("-" * 78)
    print(f"{'Category':<22} | {'Prompts':<8} | {'Avg Score':<10} | {'Min/Max':<12}")
    print("-" * 78)
    for cat, data in category_summary.items():
        print(f"{cat:<22} | {data['prompt_count']:<8} | {data['average_score']:>8.1f}% | {data['min_score']:>4.1f}% / {data['max_score']:>4.1f}%")
    print("-" * 78)
    print(f"Token Economics (Optimize):")
    print(f"  • Compressed (Saved Tokens): {len(compression_cases)} cases")
    print(f"  • Expanded for Structure   : {len(expansion_cases)} cases")
    print(f"  • Neutral / Preserved      : {len(neutral_cases)} cases")
    print("=" * 78)
    print(f"Full benchmark data written to: {json_path}")
    print("=" * 78)

    return benchmark_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoPrompt Phase 5.5 Benchmark Runner")
    parser.add_argument("--live", action="store_true", help="Execute live requests via Gemini API")
    parser.add_argument("--category", type=str, default=None, help="Filter by specific category")
    args = parser.parse_args()

    run_benchmark(use_live_api=args.live, category_filter=args.category)
