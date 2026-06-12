"""Reliability experiment harness.

Simulates N students each requesting M problems through the full agent loop and
reports the metrics from the design doc:

  - first_pass_validity:  fraction of problems accepted on the very first attempt
  - post_loop_validity:   fraction eventually delivered within the regen budget
  - mean_regenerations:   average regenerations per delivered problem
  - failure_distribution: count per failure code across all rejected attempts

Run:  python -m experiments.run --students 20 --problems 10 --out results.json

Uses whatever LLM_PROVIDER is configured in .env (default: mock, offline). Swap
to openai/anthropic to compare models for the ablation.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from app.agents import assessor, orchestrator
from app.content.skills import all_skills
from app.llm.base import get_provider
from app.models import Student


def run(n_students: int, n_problems: int, max_regen: int) -> dict:
    provider = get_provider()
    skills = all_skills()

    delivered = 0
    first_pass = 0
    total_requests = 0
    regen_total = 0
    failures: Counter[str] = Counter()

    for s in range(n_students):
        student = Student(
            id=f"sim-{s}",
            interests=["sports", "space"],
            skill_vector=assessor.initial_skill_vector(),
        )
        for p in range(n_problems):
            # Rotate the targeted skill so we cover the taxonomy evenly.
            target = skills[(s + p) % len(skills)]
            student.skill_vector = {k: (0.0 if k == target else 0.85) for k in skills}

            total_requests += 1
            result = orchestrator.generate_next_problem(
                student, provider, session=None, max_regenerations=max_regen
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
        "provider": provider.name,
        "n_students": n_students,
        "n_problems": n_problems,
        "max_regenerations": max_regen,
        "total_requests": total_requests,
        "first_pass_validity": round(first_pass / total_requests, 4) if total_requests else 0,
        "post_loop_validity": round(delivered / total_requests, 4) if total_requests else 0,
        "mean_regenerations": round(regen_total / delivered, 4) if delivered else 0,
        "failure_distribution": dict(failures),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=10)
    ap.add_argument("--problems", type=int, default=10)
    ap.add_argument("--max-regen", type=int, default=5)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    metrics = run(args.students, args.problems, args.max_regen)
    print(json.dumps(metrics, indent=2))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
