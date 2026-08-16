"""Reusable experiment core: run ONE condition and return reliability metrics.

A *condition* is a fully specified configuration of the three research variables
the project claims to isolate (Slide 4 "causal ablation"):

  - verify   : closed-loop (regenerate-until-valid) vs single-shot baseline
  - planner  : adaptive mastery policy vs random skill/difficulty sequencing
  - context  : personalized (interest-matched) vs generic thematic wrapper

Every condition simulates N students each requesting M problems through the full
agent loop and reports the four design-doc metrics:

  - first_pass_validity : fraction accepted on the very first attempt
  - post_loop_validity  : fraction eventually delivered within the regen budget
  - mean_regenerations  : average regenerations per delivered problem
  - failure_distribution: count per failure code across all rejected attempts

Runs offline on the mock provider; pass a real provider for the headline numbers.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

from app.agents import assessor, orchestrator
from app.content.skills import all_skills
from app.llm.base import LLMProvider, get_provider
from app.models import Student
from app.verification.result import FailureCode

# Canonical order of the six failure codes (stable columns for tables/charts).
FAILURE_CODES: list[str] = [c.value for c in FailureCode]


@dataclass(frozen=True)
class Condition:
    """One fully specified experimental configuration."""

    label: str
    verify: bool = True                 # closed-loop vs single-shot
    planner: str = "adaptive"           # "adaptive" | "random"
    context: str = "personalized"       # "personalized" | "generic"
    max_regen: int = 5

    def as_dict(self) -> dict:
        return {"label": self.label, "verify": self.verify,
                "planner": self.planner, "context": self.context}


def run_condition(cond: Condition, n_students: int, n_problems: int,
                  provider: LLMProvider | None = None, seed: int = 0) -> dict:
    provider = provider or get_provider()
    skills = all_skills()
    rng = random.Random(seed)
    # Single-shot baseline = no regeneration budget; closed-loop = full budget.
    max_regen = cond.max_regen if cond.verify else 0

    delivered = first_pass = total = regen_total = 0
    failures: Counter[str] = Counter()

    for s in range(n_students):
        interests = [] if cond.context == "generic" else ["sports", "space"]
        student = Student(id=f"sim-{s}", interests=interests,
                          skill_vector=assessor.initial_skill_vector())
        for p in range(n_problems):
            # Adaptive: make one skill low-mastery so the planner targets it.
            target = skills[(s + p) % len(skills)]
            student.skill_vector = {k: (0.0 if k == target else 0.85) for k in skills}

            skill_override = difficulty_override = None
            if cond.planner == "random":
                skill_override = rng.choice(skills)
                difficulty_override = rng.randint(1, 5)

            total += 1
            result = orchestrator.generate_next_problem(
                student, provider, session=None, max_regenerations=max_regen,
                skill_override=skill_override, difficulty_override=difficulty_override,
            )
            for attempt in result.attempts:
                for code in attempt["failures"]:
                    failures[code] += 1
            if result.accepted:
                delivered += 1
                regen_total += result.regen_count
                if result.regen_count == 0:
                    first_pass += 1

    return {
        **cond.as_dict(),
        "provider": provider.name,
        "n_students": n_students,
        "n_problems": n_problems,
        "max_regenerations": max_regen,
        "total_requests": total,
        "first_pass_validity": round(first_pass / total, 4) if total else 0.0,
        "post_loop_validity": round(delivered / total, 4) if total else 0.0,
        "mean_regenerations": round(regen_total / delivered, 4) if delivered else 0.0,
        "failure_distribution": {c: failures.get(c, 0) for c in FAILURE_CODES},
    }
