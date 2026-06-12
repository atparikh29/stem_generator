# Regenerate-Until-Valid: Neuro-Symbolic STEM Problem Generator

An agentic research system that generates **verified** Precalculus,
single-variable Calculus, and AP Physics 1 Mechanics problems. An LLM proposes a
problem as structured JSON; a deterministic neuro-symbolic verifier (SymPy +
physics templates + unit checking) independently confirms it before delivery and
**regenerates with an explicit failure reason** when a check fails.

> The LLM proposes. The verifier disposes. Students only ever see problems that
> provably check out.

## Why

Single-shot LLM generation is unreliable for STEM: wrong answers, non-unique
solutions, unit errors, ambiguous wording. This project measures how much a
closed verify-and-regenerate loop improves reliability, and isolates which agent
components matter via ablations.

## Architecture at a glance

```
Next.js UI  ──HTTP──▶  FastAPI backend  ──▶  PostgreSQL (append-only event log)
                              │
        observe → assess → plan → select context → generate (LLM, strict JSON)
              → translate (JSON → SymPy/pint) → verify → accept | regenerate
```

- **Math verifier (SymPy):** symbolic equivalence, solution existence &
  uniqueness, derivative/integral/limit validation, domain-restricted solving.
- **Physics verifier (templates + pint):** unit consistency, parameter realism,
  numeric solution, method validity.
- **Semantic check (LLM):** ambiguity score only — never correctness.
- **Acceptance rule:** deliver only if all deterministic checks pass *and*
  ambiguity < threshold.

Six explicit failure codes drive regeneration and metrics: `json_invalid`,
`math_invalid`, `nonunique_solution`, `unit_mismatch`, `semantic_ambiguity`,
`off_target_difficulty`.

## Quick start (fully offline, no API keys)

```bash
# 1. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env            # defaults: mock LLM + SQLite
uvicorn app.main:app --reload      # API + Swagger UI at http://localhost:8000/docs
pytest                             # run the verifier + pipeline tests

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

Open http://localhost:3000/practice and click **Begin session**.

## Using real LLMs (for the ablation)

Edit `backend/.env`:

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.2
# Llama arm: run a vLLM/Ollama OpenAI-compatible server and set:
# OPENAI_BASE_URL=http://localhost:11434/v1
```

…then `pip install openai` (or `anthropic`) and restart the server.

## Running the reliability experiment

```bash
cd backend && source .venv/bin/activate
python -m experiments.run --students 20 --problems 10 --out results.json
```

Reports first-pass validity, post-loop validity, mean regenerations, and the
failure-code distribution (see `experiments/run.py`).

## Repo layout

See [CLAUDE.md](CLAUDE.md) and [docs/architecture.md](docs/architecture.md).

## Tech stack

FastAPI · SQLModel · SymPy · pint · Pydantic v2 · Next.js (App Router) ·
PostgreSQL / SQLite.
