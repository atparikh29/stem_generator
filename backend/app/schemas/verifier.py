"""Verifier Schema (Appendix B): the structured report the verifier returns."""
from __future__ import annotations

from pydantic import BaseModel, Field


class VerifierReport(BaseModel):
    accepted: bool
    failure_reasons: list[str] = Field(default_factory=list)
    # Per-check detail keyed by check name (math, physics, difficulty, semantic).
    checks: dict[str, dict] = Field(default_factory=dict)
    difficulty_observed: int | None = None
    ambiguity_score: float | None = None
