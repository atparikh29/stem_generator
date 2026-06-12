"""Neuro-Symbolic Solver-Verifier: Mathematics (SymPy).

Implements the deterministic math checks from the design doc:
  - symbolic equivalence checking
  - solution existence and uniqueness
  - derivative and integral validation
  - domain-restricted solving

Every check is a pure function of the parsed task; no LLM is involved, so the
result is reproducible. Failures map to FailureCode.MATH_INVALID or
FailureCode.NONUNIQUE_SOLUTION.
"""
from __future__ import annotations

import random

import sympy as sp

from ..schemas.generator import MathTask
from ..translation.registry import (
    TranslationError,
    parse_equation,
    parse_math,
    parse_solution_set,
)
from .result import CheckResult, FailureCode


def _equivalent(a: sp.Expr, b: sp.Expr, variable: str = "x") -> bool:
    """Symbolic equivalence with a numeric sampling fallback."""
    try:
        diff = sp.simplify(a - b)
        if diff == 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    # Numeric fallback: agree at several random points in the domain.
    x = sp.Symbol(variable, real=True)
    rng = random.Random(1234)
    agree = 0
    trials = 0
    for _ in range(12):
        pt = rng.uniform(-3, 3)
        try:
            va = complex(a.subs(x, pt))
            vb = complex(b.subs(x, pt))
        except Exception:  # noqa: BLE001
            continue
        trials += 1
        if abs(va - vb) < 1e-6:
            agree += 1
    return trials >= 4 and agree == trials


def verify(task: MathTask) -> CheckResult:
    var = task.variable
    try:
        if task.kind == "solve_equation":
            return _verify_solve(task, var)
        if task.kind == "derivative":
            return _verify_derivative(task, var)
        if task.kind == "integral":
            return _verify_integral(task, var)
        if task.kind == "limit":
            return _verify_limit(task, var)
        if task.kind == "simplify":
            return _verify_simplify(task, var)
        return CheckResult.fail(FailureCode.MATH_INVALID, f"unknown kind {task.kind}")
    except TranslationError as exc:
        return CheckResult.fail(FailureCode.MATH_INVALID, str(exc))
    except Exception as exc:  # noqa: BLE001 - fail closed on solver errors
        return CheckResult.fail(FailureCode.MATH_INVALID, f"solver error: {exc}")


def _verify_solve(task: MathTask, var: str) -> CheckResult:
    eq = parse_equation(task.expression, var)
    expected = parse_solution_set(task.expected_answer, var)
    x = sp.Symbol(var, real=True)

    # Domain-restricted solving: if an interval [a, b] is supplied, solve there
    # instead of over all reals (needed for periodic trig equations).
    if task.interval and len(task.interval) == 2:
        domain = sp.Interval(task.interval[0], task.interval[1])
    else:
        domain = sp.S.Reals
    solset = sp.solveset(eq, x, domain=domain)
    finite = getattr(solset, "is_finite_set", None)
    # Infinite solution set (e.g. an identity or periodic family) -> not unique.
    if solset is sp.S.Reals or finite is False:
        return CheckResult.fail(
            FailureCode.NONUNIQUE_SOLUTION,
            "equation does not have a finite, unique solution set",
        )
    if finite is True:
        actual = list(solset)
    else:
        # solveset could not prove finiteness (e.g. a ConditionSet). NEVER iterate
        # a possibly-unbounded set -- fall back to solve(), which returns a finite
        # list of principal solutions.
        actual = sp.solve(eq, x)
        if not actual:
            return CheckResult.fail(FailureCode.MATH_INVALID, "could not determine a solution set")

    if not actual:
        return CheckResult.fail(FailureCode.MATH_INVALID, "no real solution exists")

    # Claimed a unique answer but the equation has several real roots.
    if len(actual) > 1 and len(expected) == 1:
        return CheckResult.fail(
            FailureCode.NONUNIQUE_SOLUTION,
            f"claimed 1 solution but found {len(actual)}: {actual}",
        )

    # Set equality between claimed and actual solutions.
    matched = _solution_sets_equal(actual, expected)
    if not matched:
        return CheckResult.fail(
            FailureCode.MATH_INVALID,
            f"claimed solutions {expected} != actual {actual}",
        )
    return CheckResult.ok("solution set verified", solutions=[str(s) for s in actual])


def _solution_sets_equal(a: list[sp.Expr], b: list[sp.Expr]) -> bool:
    if len(a) != len(b):
        return False
    remaining = list(b)
    for elem in a:
        hit = next((r for r in remaining if sp.simplify(elem - r) == 0), None)
        if hit is None:
            return False
        remaining.remove(hit)
    return True


def _verify_derivative(task: MathTask, var: str) -> CheckResult:
    x = sp.Symbol(var, real=True)
    f = parse_math(task.expression, var)
    claimed = parse_math(task.expected_answer, var)
    actual = sp.diff(f, x)
    if _equivalent(actual, claimed, var):
        return CheckResult.ok("derivative verified", derivative=str(sp.simplify(actual)))
    return CheckResult.fail(
        FailureCode.MATH_INVALID,
        f"d/d{var}[{f}] = {sp.simplify(actual)} != claimed {claimed}",
    )


def _verify_integral(task: MathTask, var: str) -> CheckResult:
    x = sp.Symbol(var, real=True)
    f = parse_math(task.expression, var)
    claimed = parse_math(task.expected_answer, var)
    if not task.interval or len(task.interval) != 2:
        return CheckResult.fail(FailureCode.MATH_INVALID, "definite integral needs interval [a, b]")
    a, b = task.interval
    actual = sp.integrate(f, (x, a, b))
    if actual.has(sp.Integral) or actual in (sp.nan, sp.zoo, sp.oo, -sp.oo):
        return CheckResult.fail(FailureCode.MATH_INVALID, "integral does not converge / no closed form")
    if _equivalent(actual, claimed, var):
        return CheckResult.ok("integral verified", value=str(sp.simplify(actual)))
    return CheckResult.fail(
        FailureCode.MATH_INVALID,
        f"integral = {sp.simplify(actual)} != claimed {claimed}",
    )


def _verify_limit(task: MathTask, var: str) -> CheckResult:
    x = sp.Symbol(var, real=True)
    f = parse_math(task.expression, var)
    claimed = parse_math(task.expected_answer, var)
    if task.point is None:
        return CheckResult.fail(FailureCode.MATH_INVALID, "limit needs a point")
    actual = sp.limit(f, x, task.point)
    if actual in (sp.nan, sp.zoo):
        return CheckResult.fail(FailureCode.MATH_INVALID, "limit does not exist")
    if _equivalent(actual, claimed, var):
        return CheckResult.ok("limit verified", value=str(actual))
    return CheckResult.fail(FailureCode.MATH_INVALID, f"limit = {actual} != claimed {claimed}")


def _verify_simplify(task: MathTask, var: str) -> CheckResult:
    """Identity / equivalence verification: expression == expected_answer."""
    lhs = parse_math(task.expression, var)
    rhs = parse_math(task.expected_answer, var)
    if _equivalent(lhs, rhs, var):
        return CheckResult.ok("expressions are equivalent")
    return CheckResult.fail(FailureCode.MATH_INVALID, f"{lhs} is not equivalent to {rhs}")
