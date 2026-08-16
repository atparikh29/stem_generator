"""Cross-model empirical benchmark (Slide 6).

Runs the SAME closed-loop condition against several providers and writes a
comparison table + charts of the four reliability metrics, so "architecture-level
reliability gains" can be shown as hard numbers rather than asserted.

    python -m experiments.benchmark --providers mock,openai,gemini \
        --students 20 --problems 10 --outdir experiments/results

Each provider must be configured (keys / base URL) in .env exactly as for normal
runs; `get_provider(name)` builds it. `mock` always works offline. Providers that
error (missing key, server down) are skipped with a note rather than aborting.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.llm.base import get_provider

from .harness import FAILURE_CODES, Condition, run_condition
from .plots import grouped_bar_svg, html_report, stacked_bar_svg, table_html

# The full-system configuration, held fixed across models.
BENCH_CONDITION = Condition("closed-loop", verify=True, planner="adaptive", context="personalized")


def run(providers: list[str], n_students: int, n_problems: int, outdir: Path) -> list[dict]:
    rows: list[dict] = []
    for name in providers:
        try:
            provider = get_provider(name)
        except Exception as exc:  # noqa: BLE001 - skip unconfigured providers
            print(f"[skip] provider '{name}': {exc}")
            continue
        print(f"[run ] {name} …")
        try:
            r = run_condition(BENCH_CONDITION, n_students, n_problems, provider=provider)
            r["provider"] = name
            rows.append(r)
        except Exception as exc:  # noqa: BLE001 - a failing model shouldn't abort the sweep
            print(f"[fail] provider '{name}': {exc}")
    outdir.mkdir(parents=True, exist_ok=True)
    if rows:
        _write_csv(rows, outdir / "benchmark.csv")
        _write_charts(rows, outdir)
        (outdir / "benchmark.json").write_text(json.dumps(rows, indent=2))
    return rows


def _write_csv(rows: list[dict], path: Path) -> None:
    cols = ["provider", "total_requests", "first_pass_validity", "post_loop_validity",
            "mean_regenerations", *[f"fail_{c}" for c in FAILURE_CODES]]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r["provider"], r["total_requests"], r["first_pass_validity"],
                        r["post_loop_validity"], r["mean_regenerations"],
                        *[r["failure_distribution"][c] for c in FAILURE_CODES]])


def _write_charts(rows: list[dict], outdir: Path) -> None:
    models = [r["provider"] for r in rows]
    validity = grouped_bar_svg(
        "Validity by model (closed-loop)", models,
        {"first-pass": [r["first_pass_validity"] for r in rows],
         "post-loop": [r["post_loop_validity"] for r in rows]},
        ymax=1.0, y_label="validity")
    regen_max = max([r["mean_regenerations"] for r in rows] + [1.0])
    regens = grouped_bar_svg(
        "Mean regenerations by model", models,
        {"mean regens": [r["mean_regenerations"] for r in rows]},
        ymax=regen_max, y_label="regenerations")
    failures = stacked_bar_svg(
        "Failure taxonomy by model", models,
        {c: [r["failure_distribution"][c] for r in rows] for c in FAILURE_CODES})
    for fname, svg in [("benchmark_validity.svg", validity),
                       ("benchmark_regens.svg", regens),
                       ("benchmark_failures.svg", failures)]:
        (outdir / fname).write_text(svg)

    tbl = table_html(
        ["model", "first-pass", "post-loop", "mean regens"],
        [[r["provider"], f'{r["first_pass_validity"]:.0%}', f'{r["post_loop_validity"]:.0%}',
          r["mean_regenerations"]] for r in rows])
    report = html_report(
        "Cross-Model Benchmark",
        "Same closed-loop condition across providers. The verifier makes every "
        "model converge to high post-loop validity; first-pass validity and mean "
        "regenerations expose how much each model leans on the loop.",
        [validity, regens, failures], tbl)
    (outdir / "benchmark_report.html").write_text(report)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", type=str, default="mock",
                    help="comma-separated: mock,openai,anthropic,gemini")
    ap.add_argument("--students", type=int, default=20)
    ap.add_argument("--problems", type=int, default=10)
    ap.add_argument("--outdir", type=str, default="experiments/results")
    args = ap.parse_args()
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    rows = run(providers, args.students, args.problems, Path(args.outdir))
    print(json.dumps(rows, indent=2))
    print(f"\nwrote CSV + SVG + HTML to {args.outdir}/ ({len(rows)} model(s))")


if __name__ == "__main__":
    main()
