"""Failure codes and the verification result type shared by all checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FailureCode(str, Enum):
    """The six explicit failure reasons from the design doc (Section VII)."""

    JSON_INVALID = "json_invalid"
    MATH_INVALID = "math_invalid"
    NONUNIQUE_SOLUTION = "nonunique_solution"
    UNIT_MISMATCH = "unit_mismatch"
    SEMANTIC_AMBIGUITY = "semantic_ambiguity"
    OFF_TARGET_DIFFICULTY = "off_target_difficulty"


@dataclass
class CheckResult:
    """Outcome of a single verification check."""

    passed: bool
    failures: list[FailureCode] = field(default_factory=list)
    detail: str = ""
    # Extra structured info, e.g. computed answer, difficulty bin, ambiguity score.
    data: dict = field(default_factory=dict)

    @classmethod
    def ok(cls, detail: str = "", **data) -> "CheckResult":
        return cls(passed=True, detail=detail, data=data)

    @classmethod
    def fail(cls, code: FailureCode, detail: str = "", **data) -> "CheckResult":
        return cls(passed=False, failures=[code], detail=detail, data=data)
