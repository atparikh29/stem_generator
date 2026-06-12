"""Grades a student's submitted answer against a delivered problem's task.

Uses the same deterministic machinery as verification: SymPy equivalence for
math, numeric tolerance for physics. Returns (correct, detail).
"""
from __future__ import annotations

from ..schemas.generator import MathTask, PhysicsTask
from ..translation.registry import parse_math, parse_solution_set
from ..verification.math_verifier import _equivalent, _solution_sets_equal


def grade(task: dict, answer: str) -> tuple[bool, str]:
    domain = task.get("domain")
    try:
        if domain == "math":
            return _grade_math(MathTask.model_validate(task), answer)
        if domain == "physics":
            return _grade_physics(PhysicsTask.model_validate(task), answer)
    except Exception as exc:  # noqa: BLE001
        return False, f"could not grade answer: {exc}"
    return False, "unknown task type"


def _grade_math(task: MathTask, answer: str) -> tuple[bool, str]:
    var = task.variable
    if task.kind == "solve_equation":
        try:
            given = parse_solution_set(answer, var)
            expected = parse_solution_set(task.expected_answer, var)
        except Exception as exc:  # noqa: BLE001
            return False, f"unparseable answer: {exc}"
        ok = _solution_sets_equal(given, expected)
        return ok, "correct" if ok else f"expected {task.expected_answer}"
    given = parse_math(answer, var)
    expected = parse_math(task.expected_answer, var)
    ok = _equivalent(given, expected, var)
    return ok, "correct" if ok else f"expected {task.expected_answer}"


def _grade_physics(task: PhysicsTask, answer: str) -> tuple[bool, str]:
    try:
        val = float(answer)
    except ValueError:
        return False, "physics answers must be numeric (in the requested unit)"
    target = task.expected_answer.value
    tol = max(0.01, 0.01 * abs(target))
    ok = abs(val - target) <= tol
    return ok, "correct" if ok else f"expected {target} {task.expected_answer.unit}"
