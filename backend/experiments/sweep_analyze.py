"""Analyze detailed sweep logs into every derived result + charts + headline JSON.

Reads <root>/<provider>/attempts.jsonl (written by experiments.sweeps) and, from
that single per-provider dataset, reconstructs:

  1. regeneration-budget curve   validity@b, b = 0..max_regen
  2. cross-model comparison      first-pass vs post-loop per provider (+ Wilson CI)
  3. per-domain validity
  4. failure-code trajectory across regeneration rounds
  5. per-difficulty validity
  6. (frontier anchor if present among providers)
  7. seed variance               from <root>/_var_s*/openai

Writes charts (SVG), an HTML report, and headline.json (the numbers the slides
and abstract quote). Providers with zero usable requests (bad key / no balance /
quota) are reported as unavailable rather than plotted as 0%.

    python -m experiments.sweep_analyze --root experiments/results/sweeps_YYYYMMDD
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .harness import FAILURE_CODES
from .plots import grouped_bar_svg, html_report, stacked_bar_svg, table_html

PROVIDER_ORDER = ["openai", "gemma", "mistral", "deepseek_r1", "gemini", "deepseek", "anthropic"]
PROVIDER_LABEL = {"openai": "Llama 3.1 8B", "gemma": "Gemma 4",
                  "mistral": "Mistral-Nemo", "deepseek_r1": "DeepSeek-R1 14B",
                  "gemini": "Gemini 3.6 Flash", "deepseek": "DeepSeek-V3",
                  "anthropic": "Claude Opus 4.8"}

# Static deployment metadata. Local footprints are the Ollama GGUF sizes (a good
# proxy for RAM/VRAM to load; runtime needs that plus KV-cache + overhead).
# Cloud models are proprietary — weights/size undisclosed.
PROVIDER_META = {
    "openai":      {"params": "8B",    "footprint": "4.9 GB", "deploy": "Local (Ollama)"},
    "gemma":       {"params": "8B",    "footprint": "9.6 GB", "deploy": "Local (Ollama)"},
    "mistral":     {"params": "12B",   "footprint": "7.1 GB", "deploy": "Local (Ollama)"},
    "deepseek_r1": {"params": "14.8B", "footprint": "9.0 GB", "deploy": "Local (Ollama)"},
    "gemini":      {"params": "—",     "footprint": "cloud",  "deploy": "API key"},
    "deepseek":    {"params": "—",     "footprint": "cloud",  "deploy": "API key"},
    "anthropic":   {"params": "—",     "footprint": "cloud",  "deploy": "API key"},
}


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open() if l.strip()]


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def analyze_provider(rows: list[dict], max_regen: int) -> dict:
    usable = [r for r in rows if "error" not in r]
    errors = len(rows) - len(usable)
    n = len(usable)
    delivered = [r for r in usable if r.get("accepted")]
    first_pass = sum(1 for r in delivered if r.get("regen_count", 0) == 0)

    # Budget curve: validity@b = fraction of usable accepted within b regenerations.
    budget = {}
    for b in range(0, max_regen + 1):
        k = sum(1 for r in delivered if r.get("regen_count", 0) <= b)
        budget[b] = round(k / n, 4) if n else 0.0

    # Failure trajectory across rounds + total distinct errors intercepted.
    round_codes: dict[int, Counter] = defaultdict(Counter)
    total_failures: Counter = Counter()
    for r in usable:
        for rd in r.get("rounds", []):
            for code in rd.get("failures", []):
                round_codes[rd.get("round", 0)][code] += 1
                total_failures[code] += 1

    def _bucket_by(keyfn):
        out = {}
        for r in usable:
            g = keyfn(r)
            d = out.setdefault(g, {"n": 0, "fp": 0, "post": 0})
            d["n"] += 1
            if r.get("accepted"):
                d["post"] += 1
                if r.get("regen_count", 0) == 0:
                    d["fp"] += 1
        return {g: {"n": v["n"],
                    "first_pass": round(v["fp"] / v["n"], 4),
                    "post_loop": round(v["post"] / v["n"], 4)}
                for g, v in out.items()}

    def _bucket(key: str):
        return _bucket_by(lambda r: r.get(key))

    # math = precalculus + calculus (SymPy-checked); physics = template + units.
    def _track(r):
        return "physics" if r.get("domain") == "physics" else "math"

    fp_ci = _wilson(first_pass, n)
    post_ci = _wilson(len(delivered), n)
    walls = sorted(r["wall_ms"] for r in usable if "wall_ms" in r)
    median_ms = walls[len(walls) // 2] if walls else 0
    mean_ms = (sum(walls) / len(walls)) if walls else 0
    # Per-attempt (per generate->verify cycle) time. wall_ms covers the whole loop;
    # attempts per problem = rejected rounds + (1 accepted round if delivered). This
    # gives the average cost of one regeneration cycle without per-round timestamps.
    total_wall = sum(r["wall_ms"] for r in usable if "wall_ms" in r)
    total_attempts = sum(len(r.get("rounds", [])) + (1 if r.get("accepted") else 0)
                         for r in usable if "wall_ms" in r)
    regens = [r.get("regen_count", 0) for r in delivered]
    return {
        "usable": n, "errors": errors,
        "median_seconds": round(median_ms / 1000, 1),
        "mean_seconds": round(mean_ms / 1000, 1),
        "seconds_per_attempt": round(total_wall / total_attempts / 1000, 1) if total_attempts else 0.0,
        "mean_regenerations": round(sum(regens) / len(regens), 2) if regens else 0.0,
        "total_minutes": round(sum(walls) / 60000, 1),
        "first_pass_validity": round(first_pass / n, 4) if n else 0.0,
        "post_loop_validity": round(len(delivered) / n, 4) if n else 0.0,
        "first_pass_ci95": [round(x, 4) for x in fp_ci],
        "post_loop_ci95": [round(x, 4) for x in post_ci],
        "budget_curve": budget,
        "errors_intercepted": sum(total_failures.values()),
        "failure_distribution": {c: total_failures.get(c, 0) for c in FAILURE_CODES},
        "failure_trajectory": {str(rd): dict(cnt) for rd, cnt in sorted(round_codes.items())},
        "by_track": _bucket_by(_track),   # math vs physics
        "by_domain": _bucket("domain"),
        "by_difficulty": {str(k): v for k, v in sorted(_bucket("difficulty").items())},
        "by_skill": {r: {"n": d["n"], "post_loop": d["post_loop"]}
                     for r, d in _bucket("skill").items()},
    }


def _line_svg(title: str, xs: list[int], series: dict[str, list[float]]) -> str:
    """Minimal multi-series line chart (validity vs regeneration budget), 0..1 y."""
    W, H, ml, mr, mt, mb = 640, 380, 60, 140, 50, 50
    pw, ph = W - ml - mr, H - mt - mb
    colors = ["#2F6DB5", "#C77D1A", "#2E8B57", "#8B2E5E", "#555"]
    def px(i): return ml + (pw * i / (len(xs) - 1) if len(xs) > 1 else 0)
    def py(v): return mt + ph * (1 - v)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">']
    out.append(f'<text x="{W/2}" y="26" text-anchor="middle" font-size="16" font-weight="700">{title}</text>')
    for g in range(0, 6):
        v = g / 5
        y = py(v)
        out.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+pw}" y2="{y:.1f}" stroke="#eee"/>')
        out.append(f'<text x="{ml-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#666">{v:.0%}</text>')
    for i, x in enumerate(xs):
        out.append(f'<text x="{px(i):.1f}" y="{mt+ph+20:.1f}" text-anchor="middle" font-size="11" fill="#666">{x}</text>')
    out.append(f'<text x="{ml+pw/2:.0f}" y="{H-10}" text-anchor="middle" font-size="12" fill="#444">regeneration budget</text>')
    for idx, (name, ys) in enumerate(series.items()):
        c = colors[idx % len(colors)]
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(ys))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2.5"/>')
        for i, v in enumerate(ys):
            out.append(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="3" fill="{c}"/>')
        ly = mt + 6 + idx * 20
        out.append(f'<line x1="{ml+pw+14}" y1="{ly}" x2="{ml+pw+34}" y2="{ly}" stroke="{c}" stroke-width="3"/>')
        out.append(f'<text x="{ml+pw+38}" y="{ly+4}" font-size="12" fill="#333">{name}</text>')
    out.append("</svg>")
    return "\n".join(out)


def run(root: Path) -> dict:
    # Discover providers with data directly under root.
    provs = [p for p in PROVIDER_ORDER if (root / p / "attempts.jsonl").exists()]
    summaries = {p: json.loads((root / p / "summary.json").read_text())
                 for p in provs if (root / p / "summary.json").exists()}
    max_regen = max((s.get("max_regen", 6) for s in summaries.values()), default=6)

    results, available, unavailable = {}, [], []
    for p in provs:
        a = analyze_provider(_load(root / p / "attempts.jsonl"),
                             summaries.get(p, {}).get("max_regen", max_regen))
        results[p] = a
        (available if a["usable"] > 0 else unavailable).append(p)

    # Seed variance for openai (Llama): seed0 (root) + _var_s* dirs.
    variance = {}
    seed_dirs = [root / p for p in ("openai",)] + sorted(root.glob("_var_s*/openai"))
    fps, posts = [], []
    for d in seed_dirs:
        rows = _load(d / "attempts.jsonl")
        u = [r for r in rows if "error" not in r]
        if u:
            fps.append(sum(1 for r in u if r.get("accepted") and r.get("regen_count", 0) == 0) / len(u))
            posts.append(sum(1 for r in u if r.get("accepted")) / len(u))
    if len(fps) >= 2:
        variance = {"seeds": len(fps),
                    "first_pass_mean": round(sum(fps) / len(fps), 4),
                    "first_pass_std": round((sum((x - sum(fps)/len(fps))**2 for x in fps)/len(fps))**0.5, 4),
                    "post_loop_mean": round(sum(posts) / len(posts), 4),
                    "post_loop_std": round((sum((x - sum(posts)/len(posts))**2 for x in posts)/len(posts))**0.5, 4)}

    outdir = root / "analysis"
    outdir.mkdir(exist_ok=True)

    # ---- charts ----
    # Budget curve (available providers).
    xs = list(range(0, max_regen + 1))

    def _curve_at(p: str, b: int) -> float:
        # A provider run at a smaller max_regen plateaus at its own final value.
        bc = results[p]["budget_curve"]
        return bc[b] if b in bc else bc[max(bc)]

    curve_series = {PROVIDER_LABEL[p]: [_curve_at(p, b) for b in xs] for p in available}
    (outdir / "budget_curve.svg").write_text(_line_svg("Validity vs regeneration budget", xs, curve_series))

    # Cross-model validity bars.
    if available:
        models = [PROVIDER_LABEL[p] for p in available]
        grouped = grouped_bar_svg("Validity by model", models,
            {"single-shot": [results[p]["first_pass_validity"] for p in available],
             "closed-loop": [results[p]["post_loop_validity"] for p in available]},
            ymax=1.0, y_label="validity")
        (outdir / "cross_model_validity.svg").write_text(grouped)

    # Per-difficulty validity for the headline model (openai if available else first).
    head = "openai" if "openai" in available else (available[0] if available else None)
    if head:
        diffs = sorted(results[head]["by_difficulty"].keys(), key=int)
        perdiff = grouped_bar_svg(f"Validity by difficulty ({PROVIDER_LABEL[head]})", diffs,
            {"single-shot": [results[head]["by_difficulty"][d]["first_pass"] for d in diffs],
             "closed-loop": [results[head]["by_difficulty"][d]["post_loop"] for d in diffs]},
            ymax=1.0, y_label="validity")
        (outdir / "by_difficulty.svg").write_text(perdiff)

        doms = sorted(results[head]["by_domain"].keys())
        perdom = grouped_bar_svg(f"Validity by domain ({PROVIDER_LABEL[head]})", doms,
            {"single-shot": [results[head]["by_domain"][d]["first_pass"] for d in doms],
             "closed-loop": [results[head]["by_domain"][d]["post_loop"] for d in doms]},
            ymax=1.0, y_label="validity")
        (outdir / "by_domain.svg").write_text(perdom)

        traj = results[head]["failure_trajectory"]
        rounds = sorted(traj.keys(), key=int)
        if rounds:
            stacked = stacked_bar_svg(f"Failure codes by regeneration round ({PROVIDER_LABEL[head]})",
                [f"round {r}" for r in rounds],
                {c: [traj[r].get(c, 0) for r in rounds] for c in FAILURE_CODES})
            (outdir / "failure_trajectory.svg").write_text(stacked)

    # ---- headline JSON ----
    headline = {
        "root": str(root), "max_regen": max_regen,
        "available_providers": available, "unavailable_providers": unavailable,
        "providers": {p: {
            "label": PROVIDER_LABEL[p], **PROVIDER_META.get(p, {}),
            "usable": results[p]["usable"],
            "errors": results[p]["errors"],
            "single_shot": results[p]["first_pass_validity"],
            "closed_loop": results[p]["post_loop_validity"],
            "single_shot_ci95": results[p]["first_pass_ci95"],
            "closed_loop_ci95": results[p]["post_loop_ci95"],
            "errors_intercepted": results[p]["errors_intercepted"],
            "median_seconds": results[p]["median_seconds"],
            "mean_seconds": results[p]["mean_seconds"],
            "seconds_per_attempt": results[p]["seconds_per_attempt"],
            "mean_regenerations": results[p]["mean_regenerations"],
            "by_track": results[p]["by_track"],   # math vs physics single-shot/closed-loop
            "budget_curve": results[p]["budget_curve"],
        } for p in provs},
        "variance_openai": variance,
        "full": results,
    }
    (outdir / "headline.json").write_text(json.dumps(headline, indent=2))

    # ---- HTML report ----
    svgs = [str((outdir / f).read_text()) for f in
            ["budget_curve.svg", "cross_model_validity.svg", "by_difficulty.svg",
             "by_domain.svg", "failure_trajectory.svg"] if (outdir / f).exists()]
    def _trk(p, track, field):
        t = results[p]["by_track"].get(track)
        return f'{t[field]:.0%}' if t else "—"

    tbl = table_html(
        ["model", "deploy", "footprint", "n", "overall", "math (s→c)", "physics (s→c)",
         "errors caught", "median s/prob"],
        [[PROVIDER_LABEL[p], PROVIDER_META.get(p, {}).get("deploy", "—"),
          PROVIDER_META.get(p, {}).get("footprint", "—"), results[p]["usable"],
          f'{results[p]["first_pass_validity"]:.0%}→{results[p]["post_loop_validity"]:.0%}',
          f'{_trk(p, "math", "first_pass")}→{_trk(p, "math", "post_loop")}',
          f'{_trk(p, "physics", "first_pass")}→{_trk(p, "physics", "post_loop")}',
          results[p]["errors_intercepted"], f'{results[p]["median_seconds"]:.0f}s'] for p in available])
    intro = ("Every number below is reconstructed from per-attempt logs of the closed loop "
             f"run at max_regen={max_regen}. Single-shot = validity at budget 0; closed-loop = "
             "validity at full budget. Providers with no usable requests were unavailable "
             f"(key/balance/quota): {', '.join(unavailable) or 'none'}.")
    (outdir / "sweep_report.html").write_text(html_report("Regenerate-Until-Valid — Sweep Results", intro, svgs, tbl))

    print(json.dumps({"available": available, "unavailable": unavailable,
                      "headline": {p: (results[p]["first_pass_validity"], results[p]["post_loop_validity"],
                                       results[p]["usable"]) for p in available},
                      "variance": variance}, indent=2))
    print(f"\nwrote analysis -> {outdir}")
    return headline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    run(Path(args.root))


if __name__ == "__main__":
    main()
