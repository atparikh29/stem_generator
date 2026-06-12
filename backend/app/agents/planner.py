"""Planner, Section III.C.2.

Mastery policy: prioritize the lowest-mastery skill and set a difficulty that is
challenging but attainable (controlled progression). Difficulty and skill are
NOT influenced by personalization -- only by the student model.
"""
from __future__ import annotations

from ..content.skills import all_skills


def plan(skill_vector: dict[str, float], recent: list[str] | None = None) -> tuple[str, int]:
    """Return (next_skill, difficulty_target in 1..5).

    Prioritizes the lowest-mastery skill, but skips skills served in the last few
    problems (``recent``) so a wrong answer -- which lowers that skill's mastery
    -- doesn't pin the student to the same skill forever. Falls back to the full
    ranking if every skill is recent.
    """
    if not skill_vector:
        skill_vector = {s: 0.2 for s in all_skills()}
    recent = recent or []

    ranked = sorted(skill_vector, key=lambda s: (skill_vector[s], s))
    candidates = [s for s in ranked if s not in recent] or ranked
    skill = candidates[0]
    # Controlled progression: target just above current ability.
    difficulty = _difficulty_from_mastery(skill_vector[skill])
    return skill, difficulty


def _difficulty_from_mastery(mastery: float) -> int:
    # mastery 0.0 -> bin 1, 1.0 -> bin 5, with a +1 "stretch" nudge, clamped.
    base = round(mastery * 4) + 1
    stretch = base + (1 if mastery < 0.8 else 0)
    return max(1, min(5, stretch))
