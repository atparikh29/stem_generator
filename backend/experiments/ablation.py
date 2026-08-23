"""Causal ablation suite (Slide 4).

Isolates the three research variables by running matched conditions and writing a
comparison table + charts:

  1. Verification  : single-shot baseline   vs closed-loop (regenerate-until-valid)
  2. Planning      : random sequencing      vs adaptive mastery policy
  3. Personalization: generic context       vs personalized context

Each pair changes exactly ONE variable; everything else is held fixed, so the
delta is attributable to that variable.

    python -m experiments.ablation --students 20 --problems 10 --outdir experiments/results

Runs on whatever LLM_PROVIDER is set (default mock, offline). The single-shot vs
closed-loop *gap* only appears with a real model that makes mistakes -- point
LLM_PROVIDER at openai/anthropic/gemini for the headline numbers.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.llm.base import get_provider

from .harness import FAILURE_CODES, Condition, run_condition
from .plots import grouped_bar_svg, html_report, stacked_bar_svg, table_html

# Baseline holds the "full system" config; each variant flips one variable.
CONDITIONS = [
    Condition("single-shot", verify=False, planner="adaptive", context="personalized"),
    Condition("closed-loop", verify=True, planner="adaptive", context="personalized"),
    Condition("random-planner", verify=True, planner="random", context="personalized"),
    Condition("generic-context", verify=True, planner="adaptive", context="generic"),
]

_METRIC_COLS = ["first_pass_validity", "post_loop_validity", "mean_regenerations"]


def run(n_students: int, n_problems: int, outdir: Path) -> list[dict]:
    provider = get_provider()
    rows = []
    for i, c in enumerate(CONDITIONS, 1):
        print(f"\n=== condition {i}/{len(CONDITIONS)}: {c.label} "
              f"(verify={c.verify}, planner={c.planner}, context={c.context}) ===", flush=True)
        rows.append(run_condition(c, n_students, n_problems, provider=provider))
    outdir.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, outdir / "ablation.csv")
    _write_charts(rows, provider.name, outdir)
    (outdir / "ablation.json").write_text(json.dumps(rows, indent=2))
    return rows


def _write_csv(rows: list[dict], path: Path) -> None:
    cols = ["label", "provider", "verify", "planner", "context", "total_requests",
            *_METRIC_COLS, *[f"fail_{c}" for c in FAILURE_CODES]]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r["label"], r["provider"], r["verify"], r["planner"], r["context"],
                        r["total_requests"], *[r[m] for m in _METRIC_COLS],
                        *[r["failure_distribution"][c] for c in FAILURE_CODES]])


def _write_charts(rows: list[dict], provider: str, outdir: Path) -> None:
    labels = [r["label"] for r in rows]
    validity = grouped_bar_svg(
        f"Validity by condition ({provider})", labels,
        {"first-pass": [r["first_pass_validity"] for r in rows],
         "post-loop": [r["post_loop_validity"] for r in rows]},
        ymax=1.0, y_label="validity")
    failures = stacked_bar_svg(
        f"Failure taxonomy by condition ({provider})", labels,
        {c: [r["failure_distribution"][c] for r in rows] for c in FAILURE_CODES})
    (outdir / "ablation_validity.svg").write_text(validity)
    (outdir / "ablation_failures.svg").write_text(failures)

    tbl = table_html(
        ["condition", "first-pass", "post-loop", "mean regens"],
        [[r["label"], f'{r["first_pass_validity"]:.0%}', f'{r["post_loop_validity"]:.0%}',
          r["mean_regenerations"]] for r in rows])
    report = html_report(
        f"Causal Ablation — {provider}",
        "Each variant flips exactly one variable vs the closed-loop baseline. "
        "Note: on the mock oracle validity is ~100%; the single-shot vs closed-loop "
        "gap appears with a real model.",
        [validity, failures], tbl)
    (outdir / "ablation_report.html").write_text(report)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=20)
    ap.add_argument("--problems", type=int, default=10)
    ap.add_argument("--outdir", type=str, default="experiments/results")
    args = ap.parse_args()
    rows = run(args.students, args.problems, Path(args.outdir))
    print(json.dumps(rows, indent=2))
    print(f"\nwrote CSV + SVG + HTML to {args.outdir}/")


if __name__ == "__main__":
    main()
