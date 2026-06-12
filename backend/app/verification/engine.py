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
