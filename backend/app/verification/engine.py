"""Neuro-Symbolic Verifier orchestration + Acceptance Rule (Section III.C.6).

Runs the deterministic checks (translation, math/physics, difficulty) and the
semantic check, then applies the acceptance rule:

    A problem is delivered only if all deterministic checks pass AND the
    semantic ambiguity is below threshold.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from ..llm.base import LLMProvider
from ..schemas.generator import GeneratorOutput, MathTask, PhysicsTask
from ..schemas.verifier import VerifierReport
from ..translation.registry import translate
from . import difficulty, math_verifier, physics_verifier, semantic
from .result import CheckResult, FailureCode


def verify(problem: GeneratorOutput, provider: LLMProvider,
           use_llm_semantic: bool = True,
           on_step: Optional[Callable[[str, dict], None]] = None) -> VerifierReport:
    """Run the four verification sub-checks in order.

    `on_step(name, data)` is called after each sub-check (translation, core,
    difficulty, semantic) with its outcome + `ms` timing, so the caller can log
    exactly where verification spends time (the semantic step makes an LLM call).
    """
    failures: list[FailureCode] = []
    checks: dict[str, dict] = {}

    def step(name: str, data: dict, t0: float) -> None:
        if on_step is not None:
            on_step(name, {**data, "ms": int((time.monotonic() - t0) * 1000)})

    # 1. Translation Layer: JSON -> executable symbolic form (fail closed).
    t0 = time.monotonic()
    trec = translate(problem.task)
    checks["translation"] = trec.model_dump()
    step("translation", {"ok": trec.ok, "detail": getattr(trec, "error", "") or ""}, t0)
    if not trec.ok:
        return VerifierReport(
            accepted=False,
            failure_reasons=[FailureCode.MATH_INVALID.value],
            checks=checks,
        )

    # 2. Deterministic solver/verifier (math or physics).
    t0 = time.monotonic()
    if isinstance(problem.task, MathTask):
        core = math_verifier.verify(problem.task)
    elif isinstance(problem.task, PhysicsTask):
        core = physics_verifier.verify(problem.task)
    else:  # pragma: no cover - guarded by schema
        core = CheckResult.fail(FailureCode.MATH_INVALID, "unknown task type")
    checks["core"] = _dump(core)
    failures += core.failures
    step("core", {"passed": core.passed,
                  "failures": [f.value for f in core.failures], "detail": core.detail}, t0)

    # 3. Difficulty hit-rate (deterministic).
    t0 = time.monotonic()
    diff = difficulty.verify(problem.task, problem.difficulty_target)
    checks["difficulty"] = _dump(diff)
    failures += diff.failures
    difficulty_observed = diff.data.get("difficulty_observed")
    step("difficulty", {"passed": diff.passed, "difficulty_observed": difficulty_observed}, t0)

    # 4. Semantic clarity (advisory) -- LLM call unless disabled/mock.
    t0 = time.monotonic()
    sem = semantic.verify(problem.statement, provider, use_llm=use_llm_semantic)
    checks["semantic"] = _dump(sem)
    failures += sem.failures
    ambiguity = sem.data.get("ambiguity_score")
    step("semantic", {"passed": sem.passed, "mode": sem.data.get("mode"),
                      "ambiguity_score": ambiguity}, t0)

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
