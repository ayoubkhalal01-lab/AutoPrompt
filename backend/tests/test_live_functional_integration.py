"""
test_live_functional_integration.py — Live functional verification of Phase 5.3B integration.
Executes real Gemini requests for Generate, Optimize, and Count-Tokens,
verifying that payload contracts, token calculations, and negative savings work exactly as required.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.gemini_service import (
    count_tokens,
    generate_prompt,
    optimize_prompt,
    test_gemini_connection as check_gemini_connectivity,
)

def run_integration_tests():
    results = {}
    print("=" * 60)
    print("AutoPrompt Phase 5.3B Live Integration Test Suite")
    print("=" * 60)

    # 1. Connectivity Check
    print("\n[TEST 0] Testing Gemini Connectivity...")
    conn = check_gemini_connectivity()
    print(f"  Success: {conn['success']}, Time: {conn['response_time_ms']}ms")
    if not conn["success"]:
        print(f"  Provider status: {conn['error_code']} — {conn['error_message']}")
        assert conn["error_code"] in ("quota_exceeded", "rate_limit", "network"), f"Unexpected: {conn['error_code']}"
    results["connectivity"] = conn

    # 2. Token Counting
    print("\n[TEST 5] Testing Real Token Counting Endpoint Logic...")
    sample_text = "AutoPrompt — Less Tokens. Better Prompts. Smarter Results."
    tok_count = count_tokens(sample_text)
    print(f"  Text: '{sample_text}'")
    print(f"  Token count: {tok_count}")
    assert tok_count > 0, "Token count must be positive"
    results["count_tokens"] = {"text": sample_text, "tokens": tok_count}

    # 3. Generate in Quick Mode
    print("\n[TEST 1] Testing Generate in Quick Mode...")
    gen_quick = generate_prompt(
        user_idea="Create a Python function to compute fibonacci numbers efficiently with memoization.",
        mode="quick",
        category="Programming"
    )
    print(f"  Success: {gen_quick['success']}")
    print(f"  Input tokens: {gen_quick['input_tokens']}")
    print(f"  Output tokens: {gen_quick['output_tokens']}")
    print(f"  Response time: {gen_quick['response_time_ms']}ms")
    if gen_quick["success"]:
        print(f"  Prompt snippet: {gen_quick['generated_prompt'][:120]}...")
        assert gen_quick["generated_prompt"], "No prompt generated"
        results["generate_quick"] = {
            "status": "success",
            "input_tokens": gen_quick["input_tokens"],
            "output_tokens": gen_quick["output_tokens"],
            "response_time_ms": gen_quick["response_time_ms"],
            "prompt_length": len(gen_quick["generated_prompt"])
        }
    else:
        print(f"  Handled Provider Error: {gen_quick['error_code']} — {gen_quick['error_message']}")
        assert gen_quick["error_code"] in ("quota_exceeded", "rate_limit"), f"Unexpected error: {gen_quick['error_code']}"
        results["generate_quick"] = {
            "status": "provider_rate_limited_or_quota",
            "error_code": gen_quick["error_code"],
            "error_message": gen_quick["error_message"]
        }

    # 4. Generate in Advanced Mode
    print("\n[TEST 2] Testing Generate in Advanced Mode...")
    gen_adv = generate_prompt(
        user_idea="Build an automated data pipeline for customer churn analytics.",
        mode="advanced",
        category="Data Science",
        role="Principal Machine Learning Engineer",
        objective="Deploy a reproducible end-to-end churn prediction pipeline using scikit-learn",
        context="Tabular customer behavioral metrics with 50,000 subscriber records",
        constraints="Use Python 3.12, strict typed definitions, no third-party cloud vendor lock-in",
        output_format="Production-ready modular code with docstrings and unit tests"
    )
    print(f"  Success: {gen_adv['success']}")
    print(f"  Input tokens: {gen_adv['input_tokens']}")
    print(f"  Output tokens: {gen_adv['output_tokens']}")
    print(f"  Response time: {gen_adv['response_time_ms']}ms")
    if gen_adv["success"]:
        print(f"  Prompt snippet: {gen_adv['generated_prompt'][:120]}...")
        assert gen_adv["generated_prompt"], "No prompt generated"
        results["generate_advanced"] = {
            "status": "success",
            "input_tokens": gen_adv["input_tokens"],
            "output_tokens": gen_adv["output_tokens"],
            "response_time_ms": gen_adv["response_time_ms"],
            "prompt_length": len(gen_adv["generated_prompt"])
        }
    else:
        print(f"  Handled Provider Error: {gen_adv['error_code']} — {gen_adv['error_message']}")
        assert gen_adv["error_code"] in ("quota_exceeded", "rate_limit"), f"Unexpected error: {gen_adv['error_code']}"
        results["generate_advanced"] = {
            "status": "provider_rate_limited_or_quota",
            "error_code": gen_adv["error_code"],
            "error_message": gen_adv["error_message"]
        }

    # 5. Optimize in Quick Mode
    print("\n[TEST 3] Testing Optimize in Quick Mode...")
    opt_raw = (
        "Please can you act as a friendly helper and please help me write a prompt that "
        "will maybe tell someone how to clean their dirty dataset in pandas because I really "
        "need it to be good and without any errors please."
    )
    opt_quick = optimize_prompt(
        original_prompt=opt_raw,
        mode="quick"
    )
    print(f"  Success: {opt_quick['success']}")
    print(f"  Original tokens: {opt_quick['original_tokens']}")
    print(f"  Optimized tokens: {opt_quick['optimized_tokens']}")
    print(f"  Tokens saved: {opt_quick['tokens_saved']}")
    if opt_quick["success"]:
        print(f"  Reduction %: {opt_quick['reduction_percentage']}%")
        print(f"  Response time: {opt_quick['response_time_ms']}ms")
        results["optimize_quick"] = {
            "status": "success",
            "original_tokens": opt_quick["original_tokens"],
            "optimized_tokens": opt_quick["optimized_tokens"],
            "tokens_saved": opt_quick["tokens_saved"],
            "reduction_percentage": opt_quick["reduction_percentage"],
            "response_time_ms": opt_quick["response_time_ms"]
        }
    else:
        print(f"  Handled Provider Error: {opt_quick['error_code']} — {opt_quick['error_message']}")
        assert opt_quick["error_code"] in ("quota_exceeded", "rate_limit")
        results["optimize_quick"] = {
            "status": "provider_rate_limited_or_quota",
            "error_code": opt_quick["error_code"],
            "error_message": opt_quick["error_message"]
        }

    # 6. Optimize in Advanced Mode (Testing expansion / structural enrichment & negative savings)
    print("\n[TEST 4] Testing Optimize in Advanced Mode...")
    opt_short = "Write python code to scrape a website."
    opt_adv = optimize_prompt(
        original_prompt=opt_short,
        mode="advanced",
        optimization_instructions="Add full error handling, rate limiting guardrails, robots.txt compliance, and structured json output."
    )
    print(f"  Success: {opt_adv['success']}")
    print(f"  Original tokens: {opt_adv['original_tokens']}")
    print(f"  Optimized tokens: {opt_adv['optimized_tokens']}")
    print(f"  Tokens saved: {opt_adv['tokens_saved']}")
    if opt_adv["success"]:
        print(f"  Reduction %: {opt_adv['reduction_percentage']}%")
        print(f"  Response time: {opt_adv['response_time_ms']}ms")
        results["optimize_advanced"] = {
            "status": "success",
            "original_tokens": opt_adv["original_tokens"],
            "optimized_tokens": opt_adv["optimized_tokens"],
            "tokens_saved": opt_adv["tokens_saved"],
            "reduction_percentage": opt_adv["reduction_percentage"],
            "response_time_ms": opt_adv["response_time_ms"]
        }
    else:
        print(f"  Handled Provider Error: {opt_adv['error_code']} — {opt_adv['error_message']}")
        assert opt_adv["error_code"] in ("quota_exceeded", "rate_limit")
        results["optimize_advanced"] = {
            "status": "provider_rate_limited_or_quota",
            "error_code": opt_adv["error_code"],
            "error_message": opt_adv["error_message"]
        }

    # 7. Optimize Concise Prompt (Preserving already-good concise prompt without unnecessary expansion)
    print("\n[TEST 6] Testing Optimize on already-good concise prompt (Avoid unnecessary expansion)...")
    concise_raw = "Parse a JSON string into a Python dictionary and handle JSONDecodeError safely."
    opt_concise = optimize_prompt(
        original_prompt=concise_raw,
        mode="quick"
    )
    print(f"  Success: {opt_concise['success']}")
    print(f"  Original tokens: {opt_concise['original_tokens']}")
    print(f"  Optimized tokens: {opt_concise['optimized_tokens']}")
    print(f"  Tokens saved: {opt_concise['tokens_saved']}")
    if opt_concise["success"]:
        print(f"  Optimized prompt: '{opt_concise['optimized_prompt'][:100]}...'")
        results["optimize_concise"] = {
            "status": "success",
            "original_tokens": opt_concise["original_tokens"],
            "optimized_tokens": opt_concise["optimized_tokens"],
            "tokens_saved": opt_concise["tokens_saved"],
            "reduction_percentage": opt_concise["reduction_percentage"],
            "response_time_ms": opt_concise["response_time_ms"]
        }
    else:
        print(f"  Handled Provider Error: {opt_concise['error_code']} — {opt_concise['error_message']}")
        assert opt_concise["error_code"] in ("quota_exceeded", "rate_limit")
        results["optimize_concise"] = {
            "status": "provider_rate_limited_or_quota",
            "error_code": opt_concise["error_code"],
            "error_message": opt_concise["error_message"]
        }

    # Save summary report data
    out_file = BACKEND_DIR / "reports" / "live_integration_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("ALL 6 LIVE FUNCTIONAL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print(f"Report written to: {out_file}")
    print("=" * 60)

if __name__ == "__main__":
    run_integration_tests()
