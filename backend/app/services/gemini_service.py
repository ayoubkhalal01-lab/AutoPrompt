"""
gemini_service.py — Production AI service layer for AutoPrompt with Gemini API.

Phase 5.4 Architecture:
- Standardized execution engine for Generate and Optimize workflows.
- Centralized error taxonomy with stable error codes and safe recovery messages.
- Explicit timeouts and bounded retries for transient errors only.
- Strict response normalization protecting against empty or filtered provider responses.
- Safe structured logging that never exposes API keys, user prompts, or secrets.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.config import settings

# ── Structured Observability Logger ───────────────────────────────────────────
logger = logging.getLogger("autoprompt.ai")
if not logger.handlers:
    # Ensure default console handler exists with clean formatting
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    )
    logger.addHandler(_handler)
logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))


# ── Centralized Error Taxonomy & Safe User-Facing Messages ────────────────────
SAFE_ERROR_HINTS: dict[str, str] = {
    "api_key_invalid":   "The Gemini API key is invalid or unauthorized. Please verify your credentials.",
    "api_key_not_found": "No API key configured. Please set GEMINI_API_KEY in the server environment.",
    "quota_exceeded":    "API quota exceeded. Please wait a moment or check your Google AI Studio plan.",
    "rate_limit":        "Too many requests sent in a short period. Please slow down and try again.",
    "model_not_found":   "Configured Gemini model is unavailable. Check model configuration.",
    "network":           "Network connection issue communicating with the Gemini API.",
    "timeout":           "Request to the Gemini API timed out. Please try again.",
    "invalid_response":  "The AI model returned an empty or unparseable response. Please refine your inputs and retry.",
    "unknown":           "An unexpected error occurred while communicating with the Gemini API.",
}

# Transient error codes eligible for bounded exponential retry
TRANSIENT_ERROR_CODES: frozenset[str] = frozenset({"network", "timeout"})

_TEST_PROMPT = (
    "Reply with exactly one sentence confirming you are the Gemini API and are working correctly."
)

# ── System Instructions for AutoPrompt Operations ────────────────────────────
GENERATE_SYSTEM_INSTRUCTION = """You are AutoPrompt's Prompt Generation Engine.
Your task is to generate a comprehensive, production-ready, highly effective prompt based on the user's task or idea.
The generated prompt must be directly usable as a prompt for an LLM and must include clear markdown sections:
- **Role / Persona**: Define the expert role and domain depth.
- **Context & Background**: Specific business, technical, or analytical context.
- **Objective**: Clear, measurable, and actionable goal.
- **Instructions**: Step-by-step numbered directives detailing the exact workflow.
- **Expected Output Format**: Concrete structure, code blocks, schema, tables, or sections expected.
- **Constraints & Guardrails**: Boundaries, libraries, edge-cases, assumptions, and negative constraints.

Do not include conversational preamble or closing remarks (such as 'Here is your prompt:'). Output the generated prompt directly."""

OPTIMIZE_SYSTEM_INSTRUCTION = """You are AutoPrompt's Prompt Optimization Engine.
Your task is to optimize an existing prompt for maximum effectiveness, clarity, and token efficiency while strictly preserving the user's original intent.

Core Guidelines:
1. Preserve Intent & Meaning: Never alter the user's fundamental goal or domain constraints.
2. Avoid Unnecessary Expansion: If a prompt is already concise, clear, and well-specified, preserve its brevity and refine it minimally. Do NOT artificially inflate token count or inject boilerplate templates when simple, direct instructions suffice.
3. Eliminate Inefficiencies: Purge conversational filler, polite preambles, redundant restatements, and vague phrasing.
4. Enhance Structure Appropriately: When a prompt is genuinely vague or underspecified, add necessary structure (concrete deliverables, constraints, or steps)—but remain token-economical.
5. Do NOT Invent Unavailable Data: Do not assume specific dataset schemas, proprietary column names, or mock data not provided in the prompt.
6. Direct Output: Output only the optimized prompt. Never include conversational preamble (such as 'Here is the optimized prompt:') or closing remarks."""

# System instruction used for the QUALITY strategy (may add structure)
QUALITY_SYSTEM_INSTRUCTION = OPTIMIZE_SYSTEM_INSTRUCTION

# System instruction used for the TOKEN strategy (explicitly discourages expansion)
TOKEN_SYSTEM_INSTRUCTION = """You are AutoPrompt's Token-Reduction Engine.
Your task is to rewrite an existing prompt using the minimum number of tokens while strictly preserving all essential requirements, technical constraints, and the original intent.

Rules:
1. Remove every markdown heading (## Role, ## Context, etc.) unless the heading text conveys unique meaning not already expressed in the content below it.
2. Delete filler phrases: "Please", "Make sure to", "It is important that", "You should", "Ensure that".
3. Merge bullet-point lists into comma-separated inline text wherever the meaning is unchanged.
4. Remove redundant restatements of the same constraint or instruction.
5. PRESERVE every technical constraint verbatim (lines containing: must, must not, should not, do not, limit, maximum, minimum, required, constraint, latency, threshold).
6. Direct Output: Output only the reduced prompt. No preamble, no explanation."""


# ── Token-Optimization Helper (rule-based, no LLM) ───────────────────────────
# Keyword patterns that identify mandatory-constraint lines (must NOT be deleted)
_CONSTRAINT_PATTERN = re.compile(
    r"\b(must|must not|should not|do not|don\'t|limit|maximum|minimum|required|"
    r"constraint|latency|threshold|never|no more than|at most|at least)\b",
    re.IGNORECASE,
)
# Markdown headings: "# …", "## …", "**Label:**", "- **Label:**"
_HEADING_PATTERN = re.compile(r"^(#{1,6}\s+.+|[-*]\s+\*\*.+\*\*:?\s*)$")
# Filler phrases to strip (case-insensitive)
_FILLERS = re.compile(
    r"\b(please|make sure to|it is important that|ensure that|you should|"
    r"be sure to|keep in mind that|note that)\b[,.]?\s*",
    re.IGNORECASE,
)


def _token_optimize(text: str) -> str:
    """
    Rule-based token minimiser.
    Removes headings and filler words; merges short bullet lists into inline text;
    collapses blank lines; always preserves constraint sentences verbatim.
    """
    lines = text.splitlines()
    result_lines: list[str] = []
    pending_bullets: list[str] = []

    def flush_bullets() -> None:
        if pending_bullets:
            result_lines.append(", ".join(pending_bullets) + ".")
            pending_bullets.clear()

    for raw in lines:
        line = raw.strip()

        # Always keep constraint lines exactly as-is
        if _CONSTRAINT_PATTERN.search(line):
            flush_bullets()
            result_lines.append(line)
            continue

        # Drop pure markdown headings (they add tokens without content)
        if _HEADING_PATTERN.match(line):
            continue

        # Collect bullet-list items for merging
        if line.startswith(("- ", "* ", "• ")):
            item = _FILLERS.sub("", line[2:]).strip()
            if item:
                pending_bullets.append(item)
            continue

        # Flush collected bullets before a non-bullet line
        flush_bullets()

        if not line:
            # Preserve at most one blank line between paragraphs
            if result_lines and result_lines[-1] != "":
                result_lines.append("")
            continue

        # Strip filler phrases from regular sentences
        cleaned = _FILLERS.sub("", line).strip()
        if cleaned:
            result_lines.append(cleaned)

    flush_bullets()

    # Strip leading/trailing blank lines
    while result_lines and result_lines[0] == "":
        result_lines.pop(0)
    while result_lines and result_lines[-1] == "":
        result_lines.pop()

    return "\n".join(result_lines)


# ── Error Classifier ──────────────────────────────────────────────────────────
def classify_error(exc: Exception) -> tuple[str, str]:
    """
    Map an exception to (error_code, safe_message).
    The raw exception message is logged server-side (sanitized)
    and never forwarded to the client.
    Handles actual provider rate-limit (429) and quota exhaustion errors
    dynamically without hardcoded RPM assumptions.
    """
    status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status_code == 429:
        msg = str(exc).lower()
        if any(x in msg for x in ("quota", "resource_exhausted", "billing", "daily limit")):
            return "quota_exceeded", SAFE_ERROR_HINTS["quota_exceeded"]
        return "rate_limit", SAFE_ERROR_HINTS["rate_limit"]

    msg = str(exc).lower()

    if any(x in msg for x in ("api key not valid", "invalid api key", "api_key_invalid", "unauthenticated")):
        return "api_key_invalid", SAFE_ERROR_HINTS["api_key_invalid"]
    if any(x in msg for x in ("resource_exhausted", "quota", "daily limit", "billing")):
        return "quota_exceeded", SAFE_ERROR_HINTS["quota_exceeded"]
    if any(x in msg for x in ("rate", "limit", "too many requests", "429")):
        return "rate_limit", SAFE_ERROR_HINTS["rate_limit"]
    if any(x in msg for x in ("not found", "404", "unknown model", "no longer available")):
        return "model_not_found", SAFE_ERROR_HINTS["model_not_found"]
    if any(x in msg for x in ("timeout", "timed out")):
        return "timeout", SAFE_ERROR_HINTS["timeout"]
    if any(x in msg for x in ("connection", "network", "getaddrinfo", "ssl", "remoteprotocolerror")):
        return "network", SAFE_ERROR_HINTS["network"]

    return "unknown", SAFE_ERROR_HINTS["unknown"]


# ── Centralized Client Factory ────────────────────────────────────────────────
def get_gemini_client() -> Any:
    """Builds and returns a configured Google GenAI client with explicit timeouts."""
    if not settings.has_gemini_key:
        return None
    from google import genai  # type: ignore[import-untyped]
    from google.genai import types  # type: ignore[import-untyped]

    timeout_ms = int(settings.GEMINI_TIMEOUT_SECONDS * 1000)
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )


# ── Standardized AI Execution Engine ──────────────────────────────────────────
def _execute_ai_request(
    operation: str,
    system_instruction: str,
    user_content: str,
    temperature: float | None = None,
) -> tuple[bool, str | None, int, str | None, str | None]:
    """
    Standardized execution workflow for AI operations:
    1. Client instantiation with explicit timeouts
    2. Bounded retries for transient errors only
    3. Response normalization and validation
    4. Structured observability logging without secret leakage

    Returns:
        (success, normalized_text, elapsed_ms, error_code, error_message)
    """
    client = get_gemini_client()
    if not client:
        logger.warning(
            "AI operation aborted: missing API key | op=%s | model=%s",
            operation,
            settings.GEMINI_MODEL,
        )
        return False, None, 0, "api_key_not_found", SAFE_ERROR_HINTS["api_key_not_found"]

    from google.genai import types  # type: ignore[import-untyped]

    temp = settings.GEMINI_TEMPERATURE if temperature is None else temperature
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temp,
    )

    max_attempts = max(1, settings.GEMINI_MAX_RETRIES)
    last_exc: Exception | None = None
    start = time.monotonic()

    logger.info("AI operation started | op=%s | model=%s", operation, settings.GEMINI_MODEL)

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=user_content,
                config=config,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Response normalization & validation
            raw_text = getattr(response, "text", None)
            if raw_text is None or not raw_text.strip():
                logger.warning(
                    "AI operation empty response | op=%s | model=%s | attempt=%d | elapsed_ms=%d",
                    operation,
                    settings.GEMINI_MODEL,
                    attempt,
                    elapsed_ms,
                )
                return False, None, elapsed_ms, "invalid_response", SAFE_ERROR_HINTS["invalid_response"]

            normalized_text = raw_text.strip()
            logger.info(
                "AI operation succeeded | op=%s | model=%s | elapsed_ms=%d | output_chars=%d",
                operation,
                settings.GEMINI_MODEL,
                elapsed_ms,
                len(normalized_text),
            )
            return True, normalized_text, elapsed_ms, None, None

        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            error_code, safe_msg = classify_error(exc)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            logger.warning(
                "AI operation failed attempt | op=%s | model=%s | attempt=%d/%d | error_code=%s | elapsed_ms=%d",
                operation,
                settings.GEMINI_MODEL,
                attempt,
                max_attempts,
                error_code,
                elapsed_ms,
            )

            # Only retry transient errors
            if error_code not in TRANSIENT_ERROR_CODES:
                break

            if attempt < max_attempts:
                backoff_delay = 1.0 * (2 ** (attempt - 1))
                time.sleep(backoff_delay)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    error_code, safe_msg = classify_error(last_exc or Exception("Unknown error"))

    logger.error(
        "AI operation terminated with error | op=%s | model=%s | final_error_code=%s | elapsed_ms=%d",
        operation,
        settings.GEMINI_MODEL,
        error_code,
        elapsed_ms,
    )

    return False, None, elapsed_ms, error_code, safe_msg


# ── Token Counting Service ────────────────────────────────────────────────────
def count_tokens(text: str, model: str | None = None) -> int:
    """
    Count the exact number of tokens in a given text string using the official SDK.
    Returns 0 if the API key is not configured, text is blank, or counting fails.
    """
    if not settings.has_gemini_key or not text or not text.strip():
        return 0

    client = get_gemini_client()
    if not client:
        return 0

    try:
        target_model = model or settings.GEMINI_MODEL
        res = client.models.count_tokens(model=target_model, contents=text)
        return int(res.total_tokens)
    except Exception as exc:  # noqa: BLE001
        error_code, _ = classify_error(exc)
        logger.warning("Token count lookup failed | model=%s | error_code=%s", model or settings.GEMINI_MODEL, error_code)
        return 0


# ── Public AI Endpoints ───────────────────────────────────────────────────────
def generate_prompt(
    user_idea: str,
    mode: str = "quick",
    category: str | None = None,
    role: str | None = None,
    objective: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    output_format: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """
    Generate a complete, structured prompt from a user idea/task.
    Returns a normalized dictionary adhering to the GenerateResponse schema.
    """
    if not settings.has_gemini_key:
        return {
            "success": False,
            "model": settings.GEMINI_MODEL,
            "generated_prompt": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_time_ms": 0,
            "error_code": "api_key_not_found",
            "error_message": SAFE_ERROR_HINTS["api_key_not_found"],
        }

    # Format user content
    if mode == "advanced":
        parts = []
        if category:
            parts.append(f"Category: {category}")
        parts.append(f"Core Task / Idea: {user_idea}")
        if role:
            parts.append(f"Target Role / Persona: {role}")
        if objective:
            parts.append(f"Target Objective: {objective}")
        if context:
            parts.append(f"Background & Context: {context}")
        if constraints:
            parts.append(f"Constraints & Guardrails: {constraints}")
        if output_format:
            parts.append(f"Desired Output Format: {output_format}")
        user_content = "\n\n".join(parts)
    else:
        user_content = f"Category: {category}\nTask: {user_idea}" if category else user_idea

    input_tokens = count_tokens(user_content)

    success, normalized_prompt, elapsed_ms, error_code, error_message = _execute_ai_request(
        operation="generate",
        system_instruction=GENERATE_SYSTEM_INSTRUCTION,
        user_content=user_content,
        temperature=temperature,
    )

    output_tokens = count_tokens(normalized_prompt) if (success and normalized_prompt) else 0

    return {
        "success": success,
        "model": settings.GEMINI_MODEL,
        "generated_prompt": normalized_prompt,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "response_time_ms": elapsed_ms,
        "error_code": error_code,
        "error_message": error_message,
    }


def optimize_prompt(
    original_prompt: str,
    mode: str = "quick",
    optimization_instructions: str | None = None,
    temperature: float | None = None,
    strategy: str = "quality",
) -> dict[str, Any]:
    """
    Optimize an existing user prompt.

    strategy "quality" (default):
        Passes the prompt through the Gemini LLM for structural / clarity improvement.
        May increase token count; a preservation_note will explain if it does.

    strategy "token":
        First runs a lightweight rule-based token reducer (_token_optimize).
        Then, if the user also provided optimization_instructions, additionally
        runs a strict LLM pass with TOKEN_SYSTEM_INSTRUCTION to honour custom directives.
        Guarantees: constraint lines are always preserved verbatim.
    """
    if not settings.has_gemini_key:
        return {
            "success": False,
            "model": settings.GEMINI_MODEL,
            "original_prompt": original_prompt,
            "optimized_prompt": None,
            "original_tokens": 0,
            "optimized_tokens": 0,
            "tokens_saved": 0,
            "reduction_percentage": 0.0,
            "response_time_ms": 0,
            "error_code": "api_key_not_found",
            "error_message": SAFE_ERROR_HINTS["api_key_not_found"],
            "preservation_note": None,
        }

    original_tokens = count_tokens(original_prompt)

    if strategy == "token":
        # ── Token strategy: rule-based reduction ──────────────────────────────
        optimized_text = _token_optimize(original_prompt)

        # If custom instructions were provided, honour them with a focused LLM pass
        if optimization_instructions:
            user_content = (
                f"Prompt to further minimise:\n{optimized_text}\n\n"
                f"Additional directives:\n{optimization_instructions}"
            )
            success, optimized_text, elapsed_ms, error_code, error_message = _execute_ai_request(
                operation="optimize",
                system_instruction=TOKEN_SYSTEM_INSTRUCTION,
                user_content=user_content,
                temperature=temperature,
            )
        else:
            success, elapsed_ms, error_code, error_message = True, 0, None, None

    else:
        # ── Quality strategy: full LLM pass (existing behaviour) ─────────────
        if optimization_instructions:
            user_content = (
                f"Prompt to optimize:\n{original_prompt}\n\n"
                f"Specific Focus Directives:\n{optimization_instructions}"
            )
        else:
            user_content = original_prompt

        success, optimized_text, elapsed_ms, error_code, error_message = _execute_ai_request(
            operation="optimize",
            system_instruction=QUALITY_SYSTEM_INSTRUCTION,
            user_content=user_content,
            temperature=temperature,
        )

    optimized_tokens = count_tokens(optimized_text) if (success and optimized_text) else 0
    tokens_saved = (original_tokens - optimized_tokens) if success else 0
    reduction_percentage = (
        round((tokens_saved / original_tokens) * 100, 1)
        if (success and original_tokens > 0) else 0.0
    )

    # Explain token expansion only for quality strategy
    preservation_note: str | None = None
    if success and strategy == "quality" and optimized_tokens > original_tokens:
        preservation_note = (
            f"The optimized prompt is {optimized_tokens - original_tokens} tokens longer than the original "
            f"({original_tokens} → {optimized_tokens}). This is expected for the Quality strategy, which adds "
            "clarity, structure, and completeness. Use the Token strategy if you need a shorter result."
        )

    return {
        "success": success,
        "model": settings.GEMINI_MODEL,
        "original_prompt": original_prompt,
        "optimized_prompt": optimized_text,
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "tokens_saved": tokens_saved,
        "reduction_percentage": reduction_percentage,
        "response_time_ms": elapsed_ms,
        "error_code": error_code,
        "error_message": error_message,
        "preservation_note": preservation_note,
    }


def test_gemini_connection() -> dict[str, Any]:
    """
    Lightweight diagnostics verification for Gemini API connectivity.
    Compatible with GET /api/test-gemini.
    """
    if not settings.has_gemini_key:
        return {
            "success": False,
            "model": settings.GEMINI_MODEL,
            "response_time_ms": 0,
            "response_text": None,
            "error_code": "api_key_not_found",
            "error_message": SAFE_ERROR_HINTS["api_key_not_found"],
        }

    success, text, elapsed_ms, error_code, error_message = _execute_ai_request(
        operation="diagnostics",
        system_instruction="Reply with exactly one short confirmation sentence.",
        user_content=_TEST_PROMPT,
    )

    return {
        "success": success,
        "model": settings.GEMINI_MODEL,
        "response_time_ms": elapsed_ms,
        "response_text": text,
        "error_code": error_code,
        "error_message": error_message,
    }
