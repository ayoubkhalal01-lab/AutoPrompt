"""
evaluator.py — Multi-Dimensional Evaluation Engine for AutoPrompt (Phase 5.5).

Evaluates Generate and Optimize outputs across five objective dimensions:
1. Structure & Organization (0-100%)
2. Intent & Semantic Preservation (0-100%)
3. Constraint Adherence & Guardrails (0-100%)
4. Token Discipline & Efficiency (0-100%)
5. Clarity, Usability & Preamble Freedom (0-100%)

Calculates an overall Composite Quality Score and generates structured diagnostic metrics.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from tests.evaluation.dataset import BenchmarkPrompt

# Standard AutoPrompt structural sections
EXPECTED_GENERATE_SECTIONS = [
    ("role", ["role", "persona", "expert", "specialist", "engineer", "lead", "staff", "educator", "consultant", "scientist"]),
    ("context", ["context", "background", "setting", "environment", "scenario"]),
    ("objective", ["objective", "goal", "task", "purpose", "deliverable"]),
    ("instructions", ["instructions", "step", "workflow", "directives", "guidelines", "tasks", "1.", "2."]),
    ("output_format", ["output format", "expected output", "deliverables", "structure", "format", "schema"]),
    ("constraints", ["constraints", "guardrails", "boundaries", "rules", "limitations", "requirements"]),
]

CONVERSATIONAL_PREAMBLE_PATTERNS = [
    r"^here is (the|your|a) (generated|optimized|improved|complete|new)?\s*prompt",
    r"^sure[,!]? here is",
    r"^certainly[,!]?",
    r"^i have (generated|optimized|created|refined)",
    r"^below is (the|your|an)?\s*prompt",
    r"hope this helps",
    r"let me know if you need any(thing)? else",
]


@dataclass
class DimensionScore:
    name: str
    weight: float
    score: float
    max_score: float
    passed: bool
    details: dict[str, Any]


@dataclass
class EvaluationReport:
    prompt_id: str
    category: str
    operation: str
    composite_score: float
    passed: bool
    token_metrics: dict[str, Any]
    dimensions: dict[str, DimensionScore]
    diagnostics: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def deterministic_token_count(text: str, live: bool = False) -> int:
    """
    Count tokens deterministically. When live=True, attempts to use the official
    SDK count_tokens. By default, uses standard offline subword estimation (~3.8 chars/token)
    to prevent network hangs or quota consumption during routine evaluation.
    """
    if not text or not text.strip():
        return 0

    if live:
        try:
            from app.services.gemini_service import count_tokens
            live_count = count_tokens(text)
            if live_count > 0:
                return live_count
        except Exception:
            pass

    # Standard deterministic estimation: ~3.8 characters per token for English & code
    return max(1, round(len(text.strip()) / 3.8))


def check_preamble_freedom(text: str) -> tuple[bool, list[str]]:
    """Verify text starts and ends directly without conversational filler."""
    text_lower = text.strip().lower()
    first_paragraph = text_lower.split("\n\n")[0]
    detected_patterns = []

    for pattern in CONVERSATIONAL_PREAMBLE_PATTERNS:
        if re.search(pattern, first_paragraph) or re.search(pattern, text_lower[-120:]):
            detected_patterns.append(pattern)

    return len(detected_patterns) == 0, detected_patterns


def _match_concept(concept_def: str | list[str], text_lower: str) -> bool:
    """Check if concept or any of its aliases match in text."""
    if isinstance(concept_def, list):
        return any(alias.lower() in text_lower for alias in concept_def)
    return concept_def.lower() in text_lower


def evaluate_generate(
    output_text: str,
    benchmark: BenchmarkPrompt,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> EvaluationReport:
    """
    Evaluate a generated prompt against the 5-dimension rubric.
    """
    diagnostics: list[str] = []
    text = (output_text or "").strip()
    text_lower = text.lower()

    in_tok = input_tokens if input_tokens is not None else deterministic_token_count(benchmark.input_text)
    out_tok = output_tokens if output_tokens is not None else deterministic_token_count(text)

    # ── Dimension 1: Structure & Organization (Weight: 0.25) ──────────────────
    found_sections = []
    missing_sections = []
    for section_name, keywords in EXPECTED_GENERATE_SECTIONS:
        if any(kw in text_lower for kw in keywords):
            found_sections.append(section_name)
        else:
            missing_sections.append(section_name)

    struct_ratio = len(found_sections) / len(EXPECTED_GENERATE_SECTIONS)
    structure_score = round(struct_ratio * 100.0, 1)
    if missing_sections:
        diagnostics.append(f"Structure: Missing sections: {', '.join(missing_sections)}")

    dim_structure = DimensionScore(
        name="Structure & Organization",
        weight=0.25,
        score=structure_score,
        max_score=100.0,
        passed=structure_score >= 70.0,
        details={"found": found_sections, "missing": missing_sections},
    )

    # ── Dimension 2: Intent & Concept Preservation (Weight: 0.25) ──────────────
    matched_concepts = []
    missing_concepts = []
    for concept in benchmark.key_concepts:
        if _match_concept(concept, text_lower):
            label = concept if isinstance(concept, str) else concept[0]
            matched_concepts.append(label)
        else:
            label = concept if isinstance(concept, str) else concept[0]
            missing_concepts.append(label)

    concept_ratio = (
        len(matched_concepts) / len(benchmark.key_concepts)
        if benchmark.key_concepts else 1.0
    )
    intent_score = round(concept_ratio * 100.0, 1)
    if missing_concepts:
        diagnostics.append(f"Intent: Missing key concepts: {', '.join(missing_concepts)}")

    dim_intent = DimensionScore(
        name="Intent & Concept Preservation",
        weight=0.25,
        score=intent_score,
        max_score=100.0,
        passed=intent_score >= 65.0,
        details={"matched": matched_concepts, "missing": missing_concepts},
    )

    # ── Dimension 3: Constraint Adherence & Guardrails (Weight: 0.20) ──────────
    constraint_checks = []
    for constraint in benchmark.expected_constraints:
        cw = [w for w in re.findall(r"\w+", constraint.lower()) if len(w) > 3]
        matched_w = [w for w in cw if w in text_lower]
        adhered = (len(matched_w) / max(1, len(cw))) >= 0.4
        constraint_checks.append({"constraint": constraint, "adhered": adhered})

    # Check negative constraints (must NOT appear)
    negative_violations = []
    for neg in benchmark.negative_constraints:
        if "preamble" in neg.lower():
            is_clean, patterns = check_preamble_freedom(text)
            if not is_clean:
                negative_violations.append(f"Preamble detected: {patterns}")

    adhered_count = sum(1 for c in constraint_checks if c["adhered"])
    total_constraints = max(1, len(constraint_checks))
    constraint_ratio = adhered_count / total_constraints
    if negative_violations:
        constraint_ratio = max(0.0, constraint_ratio - 0.2 * len(negative_violations))

    constraint_score = round(constraint_ratio * 100.0, 1)
    if negative_violations:
        diagnostics.extend(negative_violations)

    dim_constraints = DimensionScore(
        name="Constraint Adherence & Guardrails",
        weight=0.20,
        score=constraint_score,
        max_score=100.0,
        passed=constraint_score >= 60.0,
        details={"checks": constraint_checks, "violations": negative_violations},
    )

    # ── Dimension 4: Token Discipline & Efficiency (Weight: 0.15) ─────────────
    # For generate: healthy prompts are between 120 and 800 tokens.
    if out_tok < 60:
        token_score = 40.0
        diagnostics.append(f"Tokens: Output too brief ({out_tok} tokens)")
    elif out_tok > 1200:
        token_score = 60.0
        diagnostics.append(f"Tokens: Output excessively bloated ({out_tok} tokens)")
    else:
        token_score = 100.0

    dim_tokens = DimensionScore(
        name="Token Discipline & Efficiency",
        weight=0.15,
        score=token_score,
        max_score=100.0,
        passed=token_score >= 70.0,
        details={"input_tokens": in_tok, "output_tokens": out_tok},
    )

    # ── Dimension 5: Clarity, Usability & Directness (Weight: 0.15) ────────────
    clarity_score = 100.0
    preamble_clean, patterns = check_preamble_freedom(text)
    if not preamble_clean:
        clarity_score -= 30.0
        diagnostics.append(f"Clarity: Conversational preamble found: {patterns}")

    # Check for markdown headers or numbered steps
    has_markdown_headings = bool(re.search(r"^(#|##|###|\*\*)\s*", text, re.MULTILINE))
    if not has_markdown_headings:
        clarity_score -= 25.0
        diagnostics.append("Clarity: Lacks markdown section headers")

    has_numbered_steps = bool(re.search(r"^\d+\.\s+", text, re.MULTILINE))
    if not has_numbered_steps:
        clarity_score -= 15.0

    clarity_score = max(0.0, round(clarity_score, 1))
    dim_clarity = DimensionScore(
        name="Clarity, Usability & Directness",
        weight=0.15,
        score=clarity_score,
        max_score=100.0,
        passed=clarity_score >= 60.0,
        details={"has_headings": has_markdown_headings, "has_steps": has_numbered_steps},
    )

    # ── Composite Score Calculation ───────────────────────────────────────────
    composite = round(
        (dim_structure.score * dim_structure.weight)
        + (dim_intent.score * dim_intent.weight)
        + (dim_constraints.score * dim_constraints.weight)
        + (dim_tokens.score * dim_tokens.weight)
        + (dim_clarity.score * dim_clarity.weight),
        1,
    )

    passed_overall = composite >= 70.0 and dim_structure.passed and dim_intent.passed

    return EvaluationReport(
        prompt_id=benchmark.id,
        category=benchmark.category,
        operation=benchmark.operation,
        composite_score=composite,
        passed=passed_overall,
        token_metrics={
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "expansion_ratio": round(out_tok / max(1, in_tok), 2),
        },
        dimensions={
            "structure": dim_structure,
            "intent": dim_intent,
            "constraints": dim_constraints,
            "tokens": dim_tokens,
            "clarity": dim_clarity,
        },
        diagnostics=diagnostics,
    )


def evaluate_optimize(
    original_text: str,
    optimized_text: str,
    benchmark: BenchmarkPrompt,
    original_tokens: int | None = None,
    optimized_tokens: int | None = None,
) -> EvaluationReport:
    """
    Evaluate an optimized prompt against the 5-dimension rubric with strict
    checks against unnecessary expansion on already concise prompts.
    """
    diagnostics: list[str] = []
    orig = (original_text or "").strip()
    opt = (optimized_text or "").strip()
    opt_lower = opt.lower()

    orig_tok = original_tokens if original_tokens is not None else deterministic_token_count(orig)
    opt_tok = optimized_tokens if optimized_tokens is not None else deterministic_token_count(opt)
    tokens_saved = orig_tok - opt_tok
    reduction_pct = round((tokens_saved / max(1, orig_tok)) * 100.0, 1)

    # ── Dimension 1: Semantic & Intent Preservation (Weight: 0.30) ─────────────
    matched_concepts = []
    missing_concepts = []
    for concept in benchmark.key_concepts:
        if _match_concept(concept, opt_lower):
            label = concept if isinstance(concept, str) else concept[0]
            matched_concepts.append(label)
        else:
            label = concept if isinstance(concept, str) else concept[0]
            missing_concepts.append(label)

    concept_ratio = (
        len(matched_concepts) / len(benchmark.key_concepts)
        if benchmark.key_concepts else 1.0
    )
    intent_score = round(concept_ratio * 100.0, 1)
    if missing_concepts:
        diagnostics.append(f"Intent: Missing core concepts: {', '.join(missing_concepts)}")

    dim_intent = DimensionScore(
        name="Semantic & Intent Preservation",
        weight=0.30,
        score=intent_score,
        max_score=100.0,
        passed=intent_score >= 65.0,
        details={"matched": matched_concepts, "missing": missing_concepts},
    )

    # ── Dimension 2: Constraint Preservation & Guardrails (Weight: 0.25) ───────
    constraint_checks = []
    for constraint in benchmark.expected_constraints:
        cw = [w for w in re.findall(r"\w+", constraint.lower()) if len(w) > 3]
        matched_w = [w for w in cw if w in opt_lower]
        adhered = (len(matched_w) / max(1, len(cw))) >= 0.4
        constraint_checks.append({"constraint": constraint, "adhered": adhered})

    adhered_count = sum(1 for c in constraint_checks if c["adhered"])
    total_constraints = max(1, len(constraint_checks))
    constraint_ratio = adhered_count / total_constraints
    constraint_score = round(constraint_ratio * 100.0, 1)

    dim_constraints = DimensionScore(
        name="Constraint Preservation & Guardrails",
        weight=0.25,
        score=constraint_score,
        max_score=100.0,
        passed=constraint_score >= 60.0,
        details={"checks": constraint_checks},
    )

    # ── Dimension 3: Token Discipline & Expansion Policy (Weight: 0.20) ────────
    token_score = 100.0
    expectation = benchmark.conciseness_expectation

    if expectation == "preserve_conciseness":
        # Concise prompt must NOT blow up (> 1.7x expansion AND > 45 tokens delta is penalized)
        delta = opt_tok - orig_tok
        if opt_tok > (orig_tok * 1.7) and delta > 45:
            excess_pct = round((delta / orig_tok) * 100, 1)
            token_score = max(40.0, 100.0 - (excess_pct * 0.6))
            diagnostics.append(
                f"Token Policy: Concise prompt was excessively expanded (+{excess_pct}%, from {orig_tok} to {opt_tok} tokens)"
            )
        else:
            token_score = 100.0
    elif expectation == "compress":
        # Verbose prompt should compress tokens
        if tokens_saved >= 0:
            token_score = 100.0
        else:
            token_score = max(50.0, 100.0 - abs(reduction_pct))
            diagnostics.append(f"Token Policy: Expected compression but expanded by {-tokens_saved} tokens")
    elif expectation == "expand_for_structure":
        # Under-specified prompt properly expands for necessary guardrails/steps
        if opt_tok > 800:
            token_score = 65.0
            diagnostics.append(f"Token Policy: Structural expansion bloated beyond 800 tokens ({opt_tok})")
        else:
            token_score = 100.0

    token_score = round(token_score, 1)
    dim_tokens = DimensionScore(
        name="Token Discipline & Expansion Policy",
        weight=0.20,
        score=token_score,
        max_score=100.0,
        passed=token_score >= 65.0,
        details={
            "expectation": expectation,
            "original_tokens": orig_tok,
            "optimized_tokens": opt_tok,
            "tokens_saved": tokens_saved,
            "reduction_percentage": reduction_pct,
        },
    )

    # ── Dimension 4: Clarity Improvement (Weight: 0.15) ────────────────────────
    clarity_score = 100.0
    has_numbered_or_bullets = bool(re.search(r"^(\d+\.|\-|\*)\s+", opt, re.MULTILINE))
    if not has_numbered_or_bullets and len(opt.splitlines()) <= 1:
        clarity_score -= 30.0
        diagnostics.append("Clarity: Lacks structural list or formatting")

    clarity_score = max(40.0, round(clarity_score, 1))
    dim_clarity = DimensionScore(
        name="Clarity & Readability",
        weight=0.15,
        score=clarity_score,
        max_score=100.0,
        passed=clarity_score >= 60.0,
        details={"has_structured_points": has_numbered_or_bullets},
    )

    # ── Dimension 5: Preamble & Filler Removal (Weight: 0.10) ──────────────────
    filler_score = 100.0
    preamble_clean, patterns = check_preamble_freedom(opt)
    if not preamble_clean:
        filler_score -= 40.0
        diagnostics.append(f"Preamble: Conversational filler found: {patterns}")

    # Check for informal greetings like 'hey', 'please', 'thanks'
    for filler_word in ["hey", "can you please", "thanks", "i want to", "i need a"]:
        if filler_word in opt_lower.split():
            filler_score -= 15.0
            diagnostics.append(f"Filler: Retained informal phrase '{filler_word}'")

    filler_score = max(0.0, round(filler_score, 1))
    dim_filler = DimensionScore(
        name="Preamble & Filler Elimination",
        weight=0.10,
        score=filler_score,
        max_score=100.0,
        passed=filler_score >= 70.0,
        details={"clean_preamble": preamble_clean},
    )

    # ── Composite Score Calculation ───────────────────────────────────────────
    composite = round(
        (dim_intent.score * dim_intent.weight)
        + (dim_constraints.score * dim_constraints.weight)
        + (dim_tokens.score * dim_tokens.weight)
        + (dim_clarity.score * dim_clarity.weight)
        + (dim_filler.score * dim_filler.weight),
        1,
    )

    passed_overall = composite >= 70.0 and dim_intent.passed and dim_tokens.passed

    return EvaluationReport(
        prompt_id=benchmark.id,
        category=benchmark.category,
        operation=benchmark.operation,
        composite_score=composite,
        passed=passed_overall,
        token_metrics={
            "original_tokens": orig_tok,
            "optimized_tokens": opt_tok,
            "tokens_saved": tokens_saved,
            "reduction_percentage": reduction_pct,
            "conciseness_expectation": expectation,
        },
        dimensions={
            "intent": dim_intent,
            "constraints": dim_constraints,
            "tokens": dim_tokens,
            "clarity": dim_clarity,
            "filler": dim_filler,
        },
        diagnostics=diagnostics,
    )
