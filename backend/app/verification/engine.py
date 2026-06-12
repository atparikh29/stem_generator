"""Neuro-Symbolic Verifier orchestration + Acceptance Rule (Section III.C.6).

Runs the deterministic checks (translation, math/physics, difficulty) and the
semantic check, then applies the acceptance rule:

    A problem is delivered only if all deterministic checks pass AND the
    semantic ambiguity is below threshold.
"""
from __future__ import annotations

from ..llm.base import LLMProvider
from ..schemas.generator import GeneratorOutput, MathTask, PhysicsTask
from ..schemas.verifier import VerifierReport
from ..translation.registry import translate
from . import difficulty, math_verifier, physics_verifier, semantic
from .result import CheckResult, FailureCode


def verify(problem: GeneratorOutput, provider: LLMProvider) -> VerifierReport:
    failures: list[FailureCode] = []
    checks: dict[str, dict] = {}

    # 1. Translation Layer: JSON -> executable symbolic form (fail closed).
    trec = translate(problem.task)
    checks["translation"] = trec.model_dump()
    if not trec.ok:
        return VerifierReport(
            accepted=False,
            failure_reasons=[FailureCode.MATH_INVALID.value],
            checks=checks,
        )

    # 2. Deterministic solver/verifier (math or physics).
    if isinstance(problem.task, MathTask):
        core = math_verifier.verify(problem.task)
    elif isinstance(problem.task, PhysicsTask):
        core = physics_verifier.verify(problem.task)
    else:  # pragma: no cover - guarded by schema
        core = CheckResult.fail(FailureCode.MATH_INVALID, "unknown task type")
    checks["core"] = _dump(core)
    failures += core.failures

    # 3. Difficulty hit-rate (deterministic).
    diff = difficulty.verify(problem.task, problem.difficulty_target)
    checks["difficulty"] = _dump(diff)
    failures += diff.failures
    difficulty_observed = diff.data.get("difficulty_observed")

    # 4. Semantic clarity (LLM, advisory).
    sem = semantic.verify(problem.statement, provider)
    checks["semantic"] = _dump(sem)
    failures += sem.failures
    ambiguity = sem.data.get("ambiguity_score")

    # Acceptance rule: every check must pass.
    accepted = not failures
    return VerifierReport(
        accepted=accepted,
        failure_reasons=[f.value for f in failures],
        checks=checks,
        difficulty_observed=difficulty_observed,
        ambiguity_score=ambiguity,
    )


def _dump(r: CheckResult) -> dict:
    return {
        "passed": r.passed,
        "failures": [f.value for f in r.failures],
        "detail": r.detail,
        "data": r.data,
    }


# Plain-language label per failure code (for humans reading the loop).
_LABELS = {
    "json_invalid": "Output didn't match the required JSON schema",
    "math_invalid": "The claimed answer is mathematically wrong",
    "nonunique_solution": "The equation has no single unique solution",
    "unit_mismatch": "The answer's units are inconsistent",
    "semantic_ambiguity": "The wording is unclear/ambiguous for a student",
    "off_target_difficulty": "Difficulty doesn't match the requested level",
}

# Which check carries the detail for each failure code.
_CHECK_FOR = {
    "json_invalid": "translation",
    "math_invalid": "core",
    "nonunique_solution": "core",
    "unit_mismatch": "core",
    "off_target_difficulty": "difficulty",
    "semantic_ambiguity": "semantic",
}


def explain(report: VerifierReport) -> list[dict]:
    """Turn a report into per-failure, human-readable explanations.

    Returns one entry per failure code: {code, label, detail}. The detail is the
    specific reason from the responsible check (e.g. "computed 112.5 != claimed
    1950", or "observed bin 3 != target 2").
    """
    out: list[dict] = []
    for code in report.failure_reasons:
        check = report.checks.get(_CHECK_FOR.get(code, ""), {})
        detail = check.get("detail") or check.get("error") or ""
        # A correctness failure can originate in translation (unparseable task);
        # fall back to its error so the reason is never blank.
        if not detail and code in ("math_invalid", "nonunique_solution", "unit_mismatch"):
            detail = report.checks.get("translation", {}).get("error", "")
        if code == "semantic_ambiguity":
            amb = check.get("data", {}).get("ambiguity_score")
            if amb is not None:
                detail = f"{detail} (ambiguity score {amb})"
        out.append({"code": code, "label": _LABELS.get(code, code), "detail": detail})
    return out
