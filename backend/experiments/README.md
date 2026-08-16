# Experiments: reliability, ablation, cross-model benchmark

All runs simulate students requesting problems through the full agent loop and
report the four design-doc metrics: **first-pass validity**, **post-loop
validity**, **mean regenerations**, and the **failure distribution** over the six
codes. Everything runs offline on `mock`; point `LLM_PROVIDER` (or `--providers`)
at a real model for the headline numbers.

> The `mock` provider is a correct-by-construction oracle → ~100% validity, zero
> failures. That validates the *harness*. The single-shot-vs-closed-loop gap only
> shows up with a real model that makes mistakes.

## Commands

```bash
cd backend

# 1. Single condition (thin CLI). Switches: --single-shot, --planner random, --context generic
python -m experiments.run --students 20 --problems 10 --out results.json

# 2. Causal ablation — the three matched comparisons, with CSV + SVG + HTML:
#    single-shot vs closed-loop · adaptive vs random planner · personalized vs generic context
python -m experiments.ablation --students 20 --problems 10 --outdir experiments/results

# 3. Cross-model benchmark — same closed-loop condition across providers:
python -m experiments.benchmark --providers mock,openai,gemini --students 20 --problems 10
```

Use a real model (results land in `experiments/results/`, which is git-ignored):

```bash
ollama serve &                                   # free local Llama
LLM_PROVIDER=openai python -m experiments.ablation --students 20 --problems 10
python -m experiments.benchmark --providers openai,anthropic,gemini
```

## Outputs (`experiments/results/`)

| File | What |
|---|---|
| `ablation.csv` / `.json` | per-condition metrics table |
| `ablation_validity.svg` | grouped bars: first-pass vs post-loop validity per condition |
| `ablation_failures.svg` | stacked bars: the six failure codes per condition |
| `ablation_report.html` | combined report (charts + table) |
| `benchmark_*.svg/.csv/.html` | same, per model |

## Modules

- `harness.py` — `Condition` + `run_condition()`, the shared core.
- `run.py` — single-condition CLI.
- `ablation.py` — the causal-ablation suite.
- `benchmark.py` — cross-model sweep.
- `plots.py` — dependency-free SVG charts (no matplotlib) + HTML report.
