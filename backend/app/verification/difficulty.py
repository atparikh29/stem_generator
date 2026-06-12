"""Difficulty Hit-Rate (deterministic), Section V.

Mathematics: difficulty = weighted operation count from the SymPy expression
tree, binned to 1..5.
Physics: difficulty = equation chain length + concept transitions + algebraic
rearrangement cost, binned to 1..5.

A "hit" occurs when the observed bin equals the target bin; otherwise the check
emits FailureCode.OFF_TARGET_DIFFICULTY.
"""
from __future__ import annotations

import sympy as sp

from ..schemas.generator import MathTask, PhysicsTask
from ..translation.registry import parse_equation, parse_math
from .result import CheckResult, FailureCode

# Per-node weights for the math operation-count heuristic.
_OP_WEIGHTS = {
    sp.Add: 1.0,
    sp.Mul: 1.0,
    sp.Pow: 1.5,
    sp.sin: 2.0, sp.cos: 2.0, sp.tan: 2.0,
    sp.asin: 2.5, sp.acos: 2.5, sp.atan: 2.5,
    sp.exp: 2.0, sp.log: 2.0,
}

# Physics templates ordered by intrinsic conceptual difficulty.
_PHYS_BASE = {
    "kinematics": 1.0,
    "impulse_momentum": 1.5,
    "work_energy": 2.0,
    "newton_friction": 2.5,
    "circular_motion": 3.0,
}


def _bin(score: float, thresholds: list[float]) -> int:
    """Map a raw score to a 1..5 bin via ascending thresholds."""
    for i, t in enumerate(thresholds, start=1):
        if score <= t:
            return i
    return 5


def _math_score(task: MathTask) -> float:
    try:
        if task.kind == "solve_equation":
            expr = parse_equation(task.expression, task.variable)
        else:
            expr = parse_math(task.expression, task.variable)
    except Exception:  # noqa: BLE001
        return 0.0
    score = 0.0
    for node in sp.preorder_traversal(expr):
        score += _OP_WEIGHTS.get(type(node), 0.2 if node.is_number else 0.0)
    # Calculus operations are intrinsically harder than algebra.
    score += {"derivative": 1.5, "integral": 3.0, "limit": 2.0}.get(task.kind, 0.0)
    return score


def _physics_score(task: PhysicsTask) -> float:
    base = _PHYS_BASE.get(task.template, 1.0)
    chain_len = len(task.givens)          # proxy for equation chain length
    rearrangement = 0.5 if task.unknown not in ("v", "ac", "impulse", "work") else 0.0
    return base + 0.4 * chain_len + rearrangement


def score(task: MathTask | PhysicsTask) -> int:
    if isinstance(task, MathTask):
        return _bin(_math_score(task), [2.5, 5.0, 8.0, 12.0])
    return _bin(_physics_score(task), [2.0, 3.0, 4.0, 5.0])


def verify(task: MathTask | PhysicsTask, target: int) -> CheckResult:
    observed = score(task)
    if observed == target:
        return CheckResult.ok("difficulty on target", difficulty_observed=observed)
    return CheckResult.fail(
        FailureCode.OFF_TARGET_DIFFICULTY,
        f"observed difficulty bin {observed} != target {target}",
        difficulty_observed=observed,
    )
