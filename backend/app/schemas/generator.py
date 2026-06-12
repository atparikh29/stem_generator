"""Generator Schema (Appendix B).

The Generator (LLM) must emit JSON that validates against `GeneratorOutput`.
Anything that fails validation is logged as `json_invalid` and regenerated.
The `task` is a discriminated union: math skills emit a `MathTask`, physics
skills emit a `PhysicsTask`. The task carries the *machine-checkable* spec; the
Translation Layer never parses free-form natural language.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class Quantity(BaseModel):
    """A physical quantity: numeric value plus a unit string (pint-parseable)."""

    value: float
    unit: str  # e.g. "m", "m/s", "kg*m/s", "N", "" for dimensionless


class MathTask(BaseModel):
    domain: Literal["math"] = "math"
    # Maps to a SymPy verification recipe.
    kind: Literal["solve_equation", "derivative", "integral", "limit", "simplify"]
    variable: str = "x"
    # Main expression. For solve_equation, use "lhs = rhs". Otherwise a single expr.
    expression: str
    interval: Optional[list[float]] = None  # [a, b] for definite integral
    point: Optional[float] = None           # x -> point, for limit
    # The candidate answer the problem claims is correct (string SymPy expr, or a
    # comma-separated set for solve_equation).
    expected_answer: str


class PhysicsTask(BaseModel):
    domain: Literal["physics"] = "physics"
    template: Literal[
        "kinematics",
        "newton_friction",
        "work_energy",
        "impulse_momentum",
        "circular_motion",
    ]
    givens: dict[str, Quantity]
    unknown: str
    expected_answer: Quantity


Task = Annotated[Union[MathTask, PhysicsTask], Field(discriminator="domain")]


class GeneratorOutput(BaseModel):
    """Top-level structured object the LLM must produce."""

    skill: str
    difficulty_target: int = Field(ge=1, le=5)
    context_id: str = ""
    # Natural-language problem statement shown to the student.
    statement: str
    # Worked / final solution shown after the student answers.
    solution: str
    task: Task
