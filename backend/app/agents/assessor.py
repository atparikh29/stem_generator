"""Assessor (Student Model), Section III.C.1.

Produces a skill vector (mastery in [0, 1] per skill) and misconception tags from
a short diagnostic and from observed attempt outcomes. Mastery is updated with a
simple exponential moving average so recent performance dominates.
"""
from __future__ import annotations

from ..content.skills import all_skills

ALPHA = 0.4  # EMA weight on the newest observation


def initial_skill_vector() -> dict[str, float]:
    """Cold-start prior: everyone is assumed low-mastery until assessed."""
    return {skill: 0.2 for skill in all_skills()}


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
    prior = vec.get(skill, 0.2)
    obs = 1.0 if correct else 0.0
    vec[skill] = round((1 - ALPHA) * prior + ALPHA * obs, 4)
    return vec


def infer_misconceptions(skill_vector: dict[str, float], threshold: float = 0.25) -> list[str]:
    """Tag persistently low-mastery skills as misconception areas."""
    return [skill for skill, m in skill_vector.items() if m < threshold]
