# SCCUR Presentation Notes

Speaking script, factual slide corrections, and anticipated Q&A. Pairs with the
review in `SCCUR_Project_Review_and_Action_Plan.pdf`.

## Factual slide corrections (reviewers will probe these)

| Slide | Says | Should say | Why |
|---|---|---|---|
| 6 (Stack) | "Database: PostgreSQL (immutable event log)" | "**SQLite by default** (Postgres supported via `DATABASE_URL`)" | The repo default is SQLite; Postgres is optional. Claiming Postgres invites a "show me" you can't. |
| 6 (Stack) | "LLMs: GPT-5.2 and Llama (ablation)" | "GPT-5.2, Llama, **Claude, and Gemini**" | The provider abstraction now supports all four; the ablation/benchmark harness sweeps any of them. |
| 4 (Contributions) | "A within-subject pilot study **establishing** feasibility… **estimating effect sizes**" | "**Evaluation protocol & pilot-study design** for measuring learning gains" | No human data collected yet — see `docs/evaluation_protocol.md`. Do not claim completed trials. |

## Recommended flow (10–12 min)

1. **Hook (1–2):** a concrete raw-LLM STEM failure — negative time, wrong units,
   an algebra slip — "a 5% hallucination rate is unacceptable in a tutor."
2. **Architecture (3–5):** the flowchart (Slide 5). Key line: *"correctness is
   enforced through deterministic validation, not predicted."*
3. **The 6 failure codes (6–8):** the translation layer (JSON→SymPy/Pint, fails
   closed) and the solver-verifier; structured feedback accelerates convergence.
4. **Empirical results (9–10):** show the generated charts —
   `experiments/results/ablation_validity.svg` (first-pass vs post-loop) and
   `benchmark_failures.svg` (failure taxonomy). State the model used.
5. **Scope & future work (11–12):** proactively give the limitations
   (`docs/limitations_and_scope.md`): 1D-mechanics proof-of-concept, EMA assessor,
   pilot as designed protocol.

## How to generate the results figures (do this before the talk)

```bash
cd backend
ollama serve &                      # or set OPENAI/ANTHROPIC/GEMINI keys in .env

# Causal ablation (single-shot vs closed-loop, planner, context):
LLM_PROVIDER=openai python -m experiments.ablation --students 20 --problems 10

# Cross-model comparison:
python -m experiments.benchmark --providers openai,gemini --students 20 --problems 10
```

Outputs land in `backend/experiments/results/` as `.csv` (tables), `.svg`
(slide-ready charts), and `_report.html` (combined). Mock runs are a pipeline
check only (~100%); use a real model for the numbers you present.

## Anticipated questions & model answers

- **Q: Why not few-shot / Chain-of-Thought?** CoT improves reasoning but stays
  probabilistic; a symbolic verifier gives a *deterministic* correctness guarantee.
- **Q: Does regeneration add unacceptable latency?** No — cold-start onboarding
  serves a pre-verified problem bank (0 ms); live generation streams over SSE and
  the verifier bounds its own LLM call with a timeout.
- **Q: How do you grade equivalent student answers?** SymPy symbolic subtraction +
  simplification (`simplify(a - b) == 0`) with a numeric-sampling fallback.
- **Q: Why separate context from skill/difficulty?** Research-variable hygiene:
  personalization changes only the narrative; the mastery model governs difficulty.
- **Q: Is your student model BKT?** No — a one-parameter EMA mastery tracer, chosen
  deliberately; BKT/IRT is a clean future swap (see limitations doc).
- **Q: Where are the human learning results?** The pilot is a designed protocol
  (`docs/evaluation_protocol.md`); today we present *reliability* results and the
  evaluation plan.
