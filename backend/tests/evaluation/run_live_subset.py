"""
run_live_subset.py — Quota-Safe Live Validation Script for Phase 5.5.

Executes a maximum of 4 targeted live calls against Gemini API:
1. Generate: Data Science (gen_datascience_01)
2. Generate: Coding (gen_coding_01)
3. Optimize: Already Concise (opt_already_concise_01)
4. Optimize: Long prompt with strict constraints

Halts immediately if quota exhaustion (429) is encountered.
Saves results to backend/reports/live_validation_results.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.gemini_service import (
    count_tokens,
    generate_prompt,
    optimize_prompt,
    test_gemini_connection,
)
from tests.evaluation.dataset import get_prompt_by_id
from tests.evaluation.evaluator import evaluate_generate, evaluate_optimize

LONG_STRICT_PROMPT = (
    "You are a Senior Security Architect evaluating an enterprise Kubernetes deployment. "
    "Inspect the cluster configuration for: 1. CIS Kubernetes Benchmark compliance. "
    "2. NetworkPolicies enforcing default-deny ingress and egress across all tenant namespaces. "
    "3. Pod Security Standards set strictly to Restricted mode with privilege escalation disallowed. "
    "4. Mutual TLS (mTLS) with Istio service mesh and automated certificate rotation via cert-manager. "
    "5. Secret encryption at rest using AWS KMS envelope encryption. "
    "Format the deliverable as a comprehensive audit checklist with severity rankings (Critical, High, Medium, Low), "
    "remediation commands (kubectl), and verification steps. Do not use legacy PodSecurityPolicies."
)


def run_targeted_validation() -> dict:
    print("=" * 70)
    print("AutoPrompt Phase 5.5 — Targeted Live Validation (Max 4 Calls)")
    print(f"Model: {settings.GEMINI_MODEL}")
    print("=" * 70)

    # 0. Test initial connectivity
    conn = test_gemini_connection()
    print(f"\n[Probe] API Ping: success={conn['success']}, error_code={conn.get('error_code')}")
    if not conn["success"]:
        print(f"Aborting live validation: API unavailable ({conn.get('error_code')}: {conn.get('error_message')})")
        return {
            "status": "aborted",
            "reason": conn.get("error_code"),
            "message": conn.get("error_message"),
            "requests_made": 1,
            "results": [],
        }

    results = []
    requests_made = 1

    # Case 1: Generate Data Science
    print("\n[Case 1/4] Generate: Data Science (gen_datascience_01)...", end="", flush=True)
    bench_ds = get_prompt_by_id("gen_datascience_01")
    t0 = time.monotonic()
    resp_ds = generate_prompt(user_idea=bench_ds.input_text, mode=bench_ds.mode, category=bench_ds.category)
    requests_made += 1
    eval_ds = evaluate_generate(
        output_text=resp_ds.get("generated_prompt") or "",
        benchmark=bench_ds,
        input_tokens=resp_ds.get("input_tokens"),
        output_tokens=resp_ds.get("output_tokens"),
    )
    status_sym = "[PASS]" if resp_ds["success"] and eval_ds.passed else "[FAIL]"
    print(f" {status_sym} score={eval_ds.composite_score}% ({resp_ds.get('response_time_ms', 0)}ms)")
    results.append({
        "case": "generate_data_science",
        "id": "gen_datascience_01",
        "success": resp_ds["success"],
        "error_code": resp_ds.get("error_code"),
        "response_time_ms": resp_ds.get("response_time_ms"),
        "input_tokens": resp_ds.get("input_tokens"),
        "output_tokens": resp_ds.get("output_tokens"),
        "composite_score": eval_ds.composite_score,
        "passed": eval_ds.passed,
        "diagnostics": eval_ds.diagnostics,
    })

    if resp_ds.get("error_code") == "quota_exceeded":
        print("Quota exceeded; halting remaining live calls.")
        return {"status": "quota_exceeded", "requests_made": requests_made, "results": results}

    time.sleep(1.5)

    # Case 2: Generate Coding
    print("[Case 2/4] Generate: Coding (gen_coding_01)...", end="", flush=True)
    bench_code = get_prompt_by_id("gen_coding_01")
    resp_code = generate_prompt(
        user_idea=bench_code.input_text,
        mode=bench_code.mode,
        category=bench_code.category,
        role=bench_code.advanced_params.get("role"),
        objective=bench_code.advanced_params.get("objective"),
        context=bench_code.advanced_params.get("context"),
        constraints=bench_code.advanced_params.get("constraints"),
        output_format=bench_code.advanced_params.get("output_format"),
    )
    requests_made += 1
    eval_code = evaluate_generate(
        output_text=resp_code.get("generated_prompt") or "",
        benchmark=bench_code,
        input_tokens=resp_code.get("input_tokens"),
        output_tokens=resp_code.get("output_tokens"),
    )
    status_sym = "[PASS]" if resp_code["success"] and eval_code.passed else "[FAIL]"
    print(f" {status_sym} score={eval_code.composite_score}% ({resp_code.get('response_time_ms', 0)}ms)")
    results.append({
        "case": "generate_coding",
        "id": "gen_coding_01",
        "success": resp_code["success"],
        "error_code": resp_code.get("error_code"),
        "response_time_ms": resp_code.get("response_time_ms"),
        "input_tokens": resp_code.get("input_tokens"),
        "output_tokens": resp_code.get("output_tokens"),
        "composite_score": eval_code.composite_score,
        "passed": eval_code.passed,
        "diagnostics": eval_code.diagnostics,
    })

    if resp_code.get("error_code") == "quota_exceeded":
        print("Quota exceeded; halting remaining live calls.")
        return {"status": "quota_exceeded", "requests_made": requests_made, "results": results}

    time.sleep(1.5)

    # Case 3: Optimize Already Concise
    print("[Case 3/4] Optimize: Already Concise (opt_already_concise_01)...", end="", flush=True)
    bench_concise = get_prompt_by_id("opt_already_concise_01")
    resp_concise = optimize_prompt(original_prompt=bench_concise.input_text, mode="quick")
    requests_made += 1
    eval_concise = evaluate_optimize(
        original_text=bench_concise.input_text,
        optimized_text=resp_concise.get("optimized_prompt") or "",
        benchmark=bench_concise,
        original_tokens=resp_concise.get("original_tokens"),
        optimized_tokens=resp_concise.get("optimized_tokens"),
    )
    status_sym = "[PASS]" if resp_concise["success"] and eval_concise.passed else "[FAIL]"
    print(f" {status_sym} score={eval_concise.composite_score}% (tokens: {resp_concise.get('original_tokens')}->{resp_concise.get('optimized_tokens')})")
    results.append({
        "case": "optimize_already_concise",
        "id": "opt_already_concise_01",
        "success": resp_concise["success"],
        "error_code": resp_concise.get("error_code"),
        "response_time_ms": resp_concise.get("response_time_ms"),
        "original_tokens": resp_concise.get("original_tokens"),
        "optimized_tokens": resp_concise.get("optimized_tokens"),
        "tokens_saved": resp_concise.get("tokens_saved"),
        "reduction_percentage": resp_concise.get("reduction_percentage"),
        "composite_score": eval_concise.composite_score,
        "passed": eval_concise.passed,
        "diagnostics": eval_concise.diagnostics,
    })

    if resp_concise.get("error_code") == "quota_exceeded":
        print("Quota exceeded; halting remaining live calls.")
        return {"status": "quota_exceeded", "requests_made": requests_made, "results": results}

    time.sleep(1.5)

    # Case 4: Optimize Long Prompt with Strict Constraints
    print("[Case 4/4] Optimize: Long with Strict Constraints...", end="", flush=True)
    from tests.evaluation.dataset import BenchmarkPrompt
    bench_long = BenchmarkPrompt(
        id="opt_long_strict_01",
        category="Coding",
        operation="optimize",
        mode="quick",
        input_text=LONG_STRICT_PROMPT,
        expected_intent="Streamline comprehensive Kubernetes security audit prompt while preserving strict constraints.",
        key_concepts=[["kubernetes", "k8s"], ["cis", "benchmark"], ["networkpolicies", "network policy"], ["mtls", "istio"], ["kms", "encryption"], ["podsecuritypolicies", "pod security"]],
        expected_constraints=["Enforce default-deny ingress/egress", "Do not use legacy PodSecurityPolicies", "Severity rankings"],
        negative_constraints=["Do not drop strict constraints"],
        conciseness_expectation="preserve_conciseness",
    )
    resp_long = optimize_prompt(original_prompt=LONG_STRICT_PROMPT, mode="quick")
    requests_made += 1
    eval_long = evaluate_optimize(
        original_text=LONG_STRICT_PROMPT,
        optimized_text=resp_long.get("optimized_prompt") or "",
        benchmark=bench_long,
        original_tokens=resp_long.get("original_tokens"),
        optimized_tokens=resp_long.get("optimized_tokens"),
    )
    status_sym = "[PASS]" if resp_long["success"] and eval_long.passed else "[FAIL]"
    print(f" {status_sym} score={eval_long.composite_score}% (tokens: {resp_long.get('original_tokens')}->{resp_long.get('optimized_tokens')})")
    results.append({
        "case": "optimize_long_strict",
        "id": "opt_long_strict_01",
        "success": resp_long["success"],
        "error_code": resp_long.get("error_code"),
        "response_time_ms": resp_long.get("response_time_ms"),
        "original_tokens": resp_long.get("original_tokens"),
        "optimized_tokens": resp_long.get("optimized_tokens"),
        "tokens_saved": resp_long.get("tokens_saved"),
        "reduction_percentage": resp_long.get("reduction_percentage"),
        "composite_score": eval_long.composite_score,
        "passed": eval_long.passed,
        "diagnostics": eval_long.diagnostics,
    })

    summary = {
        "status": "completed",
        "model": settings.GEMINI_MODEL,
        "requests_made": requests_made,
        "results": results,
    }

    out_path = BACKEND_DIR / "reports" / "live_validation_results.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nLive validation results saved to {out_path}")
    return summary


if __name__ == "__main__":
    run_targeted_validation()
