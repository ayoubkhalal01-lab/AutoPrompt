"""
Targeted, Quota-Safe Gemini Live Probe for Phase 7.1 Final Verification.
Constraints:
- At most ONE live Generate request
- At most ONE live Optimize request
- Stop immediately if 429 / quota exceeded occurs
- Never log secrets or API keys
"""

import sys
import json
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.gemini_service import (
    generate_prompt,
    optimize_prompt,
    count_tokens,
    classify_error,
)

results = {
    "live_token_count": None,
    "live_generate": None,
    "live_optimize": None,
    "quota_status": "healthy",
    "halt_reason": None,
}

print("=== Starting Targeted Gemini Live Verification ===")
print(f"Configured Model: {settings.GEMINI_MODEL}")
print(f"API Key Present: {bool(settings.GEMINI_API_KEY)}")

# Step 1: Probe live token counting (lowest quota footprint)
try:
    print("\n[Step 1] Testing live count_tokens...")
    t_start = time.perf_counter()
    tokens = count_tokens("AutoPrompt production validation sentence.")
    elapsed = int((time.perf_counter() - t_start) * 1000)
    print(f"  -> Counted tokens: {tokens} in {elapsed}ms")
    results["live_token_count"] = {"success": True, "tokens": tokens, "elapsed_ms": elapsed}
except Exception as e:
    err_code = classify_error(e)
    print(f"  -> Token count failed: code={err_code}")
    results["live_token_count"] = {"success": False, "error_code": err_code}
    if err_code in ("quota_exceeded", "rate_limit"):
        results["quota_status"] = "exhausted"
        results["halt_reason"] = f"Quota reached during count_tokens ({err_code})"
        print("HALTING: Upstream quota exhausted. Stopping immediately per safety rules.")
        print(json.dumps(results, indent=2))
        sys.exit(0)

# Step 2: Exactly ONE live Generate request
if results["quota_status"] == "healthy":
    print("\n[Step 2] Executing SINGLE live Generate request...")
    t_start = time.perf_counter()
    gen_res = generate_prompt(
        user_idea="Create a prompt for a senior technical writer to document a REST API.",
        mode="quick",
        category="General",
    )
    elapsed = int((time.perf_counter() - t_start) * 1000)
    print(f"  -> Generate success: {gen_res.get('success')} | error_code: {gen_res.get('error_code')} | time: {elapsed}ms")
    results["live_generate"] = {
        "success": gen_res.get("success"),
        "error_code": gen_res.get("error_code"),
        "input_tokens": gen_res.get("input_tokens"),
        "output_tokens": gen_res.get("output_tokens"),
        "elapsed_ms": elapsed,
    }
    if not gen_res.get("success") and gen_res.get("error_code") in ("quota_exceeded", "rate_limit"):
        results["quota_status"] = "exhausted"
        results["halt_reason"] = f"Quota reached during generate ({gen_res.get('error_code')})"
        print("HALTING: Upstream quota reached during generate. Preserving remaining quota.")
        print(json.dumps(results, indent=2))
        sys.exit(0)

# Step 3: Exactly ONE live Optimize request (only if quota healthy)
if results["quota_status"] == "healthy" and results["live_generate"].get("success"):
    print("\n[Step 3] Executing SINGLE live Optimize request...")
    t_start = time.perf_counter()
    opt_res = optimize_prompt(
        original_prompt="Help me write tests for my code so that it works well and has no bugs.",
        mode="quick",
    )
    elapsed = int((time.perf_counter() - t_start) * 1000)
    print(f"  -> Optimize success: {opt_res.get('success')} | error_code: {opt_res.get('error_code')} | time: {elapsed}ms")
    results["live_optimize"] = {
        "success": opt_res.get("success"),
        "error_code": opt_res.get("error_code"),
        "original_tokens": opt_res.get("original_tokens"),
        "optimized_tokens": opt_res.get("optimized_tokens"),
        "tokens_saved": opt_res.get("tokens_saved"),
        "elapsed_ms": elapsed,
    }
    if not opt_res.get("success") and opt_res.get("error_code") in ("quota_exceeded", "rate_limit"):
        results["quota_status"] = "exhausted"
        results["halt_reason"] = f"Quota reached during optimize ({opt_res.get('error_code')})"

print("\n=== Live Verification Complete ===")
print(json.dumps(results, indent=2))
