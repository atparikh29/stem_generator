"""Single-condition reliability run (thin CLI over experiments.harness).

Reports the four design-doc metrics for ONE configuration:

  - first_pass_validity, post_loop_validity, mean_regenerations, failure_distribution

    python -m experiments.run --students 20 --problems 10 --out results.json
    python -m experiments.run --single-shot            # baseline (no regeneration)
    python -m experiments.run --planner random         # random sequencing
    python -m experiments.run --context generic        # non-personalized

Uses whatever LLM_PROVIDER is configured in .env (default mock, offline). For the
full causal ablation use `experiments.ablation`; for cross-model, `experiments.benchmark`.
"""
from __future__ import annotations

import argparse
import json

from .harness import Condition, run_condition


def run(n_students: int, n_problems: int, max_regen: int) -> dict:
    """Back-compatible entry point: closed-loop, adaptive, personalized."""
    return run_condition(
        Condition("closed-loop", verify=True, planner="adaptive",
                  context="personalized", max_regen=max_regen),
        n_students, n_problems)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=10)
    ap.add_argument("--problems", type=int, default=10)
    ap.add_argument("--max-regen", type=int, default=5)
    ap.add_argument("--single-shot", action="store_true", help="baseline: no regeneration")
    ap.add_argument("--planner", choices=["adaptive", "random"], default="adaptive")
    ap.add_argument("--context", choices=["personalized", "generic"], default="personalized")
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    cond = Condition(
        label="single-shot" if args.single_shot else "closed-loop",
        verify=not args.single_shot, planner=args.planner, context=args.context,
        max_regen=args.max_regen)
    metrics = run_condition(cond, args.students, args.problems)
    print(json.dumps(metrics, indent=2))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
