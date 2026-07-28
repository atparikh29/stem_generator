"""Semantic Clarity check (LLM).

Used *only* to detect missing linguistic qualifiers and to generate pedagogical
feedback -- never to judge mathematical correctness. Returns an ambiguity score
in [0, 1]; the acceptance rule rejects when it exceeds the configured threshold
(FailureCode.SEMANTIC_AMBIGUITY).

With the mock provider this runs a cheap deterministic heuristic so the pipeline
works offline; with a real provider it asks the model to rate ambiguity.
"""
from __future__ import annotations

import json

from ..config import settings
from ..llm.base import LLMProvider
from .result import CheckResult, FailureCode

# Qualifiers whose absence commonly makes a STEM prompt ambiguous.
_EXPECTED_QUALIFIERS = (
    "find", "solve", "evaluate", "determine", "calculate", "compute",
    "expand", "simplify", "factor",
)
_UNIT_HINTS = ("unit", "round", "nearest", "express", "exact")


def _heuristic_score(statement: str) -> float:
    s = statement.lower().strip()
    score = 0.0
    if not s.endswith("?") and "find" not in s and not any(q in s for q in _EXPECTED_QUALIFIERS):
        score += 0.4  # no clear instruction to the student
    if len(s.split()) < 6:
        score += 0.3  # too terse to be unambiguous
    if not any(h in s for h in _UNIT_HINTS):
        score += 0.1  # mild: no rounding/units guidance
    return min(score, 1.0)


def verify(statement: str, provider: LLMProvider, use_llm: bool = True) -> CheckResult:
    threshold = settings.semantic_ambiguity_threshold
    # Heuristic path: always for mock, or when the LLM clarity check is disabled.
    if settings.llm_provider == "mock" or not use_llm:
        amb = _heuristic_score(statement)
        feedback = "looks clear" if amb <= threshold else "missing a clear instruction or qualifier"
        mode = "heuristic"
        if amb <= threshold:
            return CheckResult.ok(feedback, ambiguity_score=amb, mode=mode)
        return CheckResult.fail(FailureCode.SEMANTIC_AMBIGUITY, feedback, ambiguity_score=amb, mode=mode)
    else:
        prompt = (
            "Rate the ambiguity of this math/physics problem statement for a "
            "student on a 0.0-1.0 scale (0 = perfectly clear, 1 = unanswerable as "
            "written). Consider only wording/clarity, NOT correctness. Respond as "
            'JSON: {"ambiguity": <float>, "feedback": "<short note>"}.\n\n'
            f"Statement: {statement}"
        )
        try:
            raw = provider.complete(prompt)
        except Exception as exc:  # noqa: BLE001 - network/timeout on this advisory call:
            # don't hang or force regeneration; skip the clarity check for this candidate.
            return CheckResult.ok(f"semantic check skipped ({type(exc).__name__})",
                                  ambiguity_score=0.0, mode="skipped")
        try:
            parsed = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            amb = float(parsed.get("ambiguity", 1.0))
            feedback = str(parsed.get("feedback", ""))
        except Exception:  # noqa: BLE001 - fail closed: treat unparseable as ambiguous
            amb, feedback = 1.0, "semantic check returned unparseable output"

    if amb <= threshold:
        return CheckResult.ok(feedback, ambiguity_score=amb, mode="llm")
    return CheckResult.fail(
        FailureCode.SEMANTIC_AMBIGUITY,
        feedback,
        ambiguity_score=amb,
        mode="llm",
    )
