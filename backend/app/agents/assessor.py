"""Assessor (Student Model), Section III.C.1.

Produces a skill vector (mastery in [0, 1] per skill) and misconception tags from
a short diagnostic and from observed attempt outcomes. Mastery is updated with a
simple exponential moving average so recent performance dominates.
"""
from __future__ import annotations

from ..config import settings
from ..content.skills import all_skills


def initial_skill_vector() -> dict[str, float]:
    """Cold-start prior: everyone is assumed low-mastery until assessed."""
    return {skill: settings.initial_mastery for skill in all_skills()}


def update_from_diagnostic(responses: dict[str, bool]) -> dict[str, float]:
    """responses: skill -> was the diagnostic item answered correctly."""
    vec = initial_skill_vector()
    for skill, correct in responses.items():
        if skill in vec:
            vec[skill] = 0.7 if correct else 0.15
    return vec


def update_mastery(skill_vector: dict[str, float], skill: str, correct: bool) -> dict[str, float]:
    """EMA update after observing one graded attempt."""
    vec = dict(skill_vector)
    prior = vec.get(skill, settings.initial_mastery)
    obs = 1.0 if correct else 0.0
    alpha = settings.assessor_alpha
    vec[skill] = round((1 - alpha) * prior + alpha * obs, 4)
    return vec


def infer_misconceptions(skill_vector: dict[str, float], threshold: float | None = None) -> list[str]:
    """Tag persistently low-mastery skills as misconception areas."""
    thr = settings.misconception_threshold if threshold is None else threshold
    return [skill for skill, m in skill_vector.items() if m < thr]
