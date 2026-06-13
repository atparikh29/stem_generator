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

from ..config import settings
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


# Per-skill (lo, hi) raw-score anchors: lo = the simplest *realistic* problem for
# this kind/template (bin 1), hi = its hardest (bin 5). Difficulty is binned
# RELATIVE to the skill's own achievable range, so every skill can span 1..5 and
# the planner's targets are reachable (a global scale made e.g. any limit >= bin 4
# and any polynomial derivative <= bin 3).
_MATH_ANCHORS = {
    "derivative": (3.0, 14.0),
    "integral": (3.0, 9.0),
    "limit": (6.5, 11.0),
    "solve_equation": (2.5, 6.0),
    "simplify": (1.0, 13.5),
}
_PHYS_ANCHORS = {
    "kinematics": (2.0, 4.5),
    "newton_friction": (3.5, 6.0),
    "work_energy": (2.5, 5.0),
    "impulse_momentum": (2.0, 4.5),
    "circular_motion": (3.5, 6.5),
}


def _norm_bin(raw: float, lo: float, hi: float) -> int:
    """Map a raw score into 1..5 relative to [lo, hi]."""
    if hi <= lo:
        return 3
    frac = (raw - lo) / (hi - lo)
    return max(1, min(5, 1 + round(frac * 4)))


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
        lo, hi = _MATH_ANCHORS.get(task.kind, (2.5, 12.0))
        return _norm_bin(_math_score(task), lo, hi)
    lo, hi = _PHYS_ANCHORS.get(task.template, (2.0, 5.0))
    return _norm_bin(_physics_score(task), lo, hi)


def verify(task: MathTask | PhysicsTask, target: int) -> CheckResult:
    observed = score(task)
    tolerance = settings.difficulty_tolerance
    if abs(observed - target) <= tolerance:
        return CheckResult.ok("difficulty on target", difficulty_observed=observed)
    return CheckResult.fail(
        FailureCode.OFF_TARGET_DIFFICULTY,
        f"observed difficulty bin {observed} != target {target} (tolerance {tolerance})",
        difficulty_observed=observed,
    )
