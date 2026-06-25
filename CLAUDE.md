# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this project is

**Regenerate-Until-Valid** is an agentic research system that generates
**verified** STEM problems for Precalculus, single-variable Calculus, and AP
Physics 1 Mechanics. The research claim: a closed-loop agent that *generates,
then deterministically verifies, then regenerates on failure* produces
materially more reliable problems than single-shot LLM generation.

The LLM never decides correctness. It proposes a problem as structured JSON; a
**neuro-symbolic verifier** (SymPy for math, deterministic templates + unit
checking for physics, plus an LLM clarity check) independently re-derives the
answer and accepts or rejects with an explicit failure code.

## The closed loop (this is the whole system)

```
observe → assess → plan → select context → generate(JSON)
        → translate(JSON→symbolic) → verify → accept | regenerate(with reason)
```

Wrapped around that core is a **session flow**: a new session onboards (pick
context/skill/difficulty) and is served an **instant, pre-verified problem from a
bank** (`content/problem_bank.py`); a returning session restores saved state.
Onboarding and any settings change serve a pre-stored problem (no LLM wait);
"continue" runs the Planner → LLM loop above. See `docs/architecture.md`.

Read `docs/architecture.md` for the long version. Source-of-truth design lives in
the three PDFs the project was specced from (kept out of git; ask Anay).

## Repository layout

```
backend/app/
  agents/         the loop: assessor, planner, context_selector, orchestrator, grader
  llm/            provider abstraction: mock (offline oracle), openai (GPT-5.2/Llama), anthropic
  translation/    JSON → SymPy/pint (the ONLY math-parsing bridge; fails closed)
  verification/   math_verifier (SymPy), physics_verifier (templates+pint),
                  difficulty, semantic, engine (acceptance rule), result (failure codes)
  schemas/        Pydantic: generator / verifier / translation-record (Appendix B)
  content/        skills taxonomy, context library, problem_bank (pre-verified bank)
  api/            FastAPI routes (sessions, pre-stored, SSE stream, attempts)
  scripts/        build_problem_bank.py (seed + --augment), smoke_llm, list_skills
  models.py       immutable Event log + Student (=session, holds saved state) + ProblemRecord
backend/tests/    pytest; runs fully offline on the mock provider
frontend/         Next.js (App Router) practice UI
docs/             architecture + experiment notes
```

## How to run

Backend (defaults to offline mock LLM + SQLite — no keys needed):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000  (docs at /docs)
pytest                                  # full suite, offline
```

Frontend:

```bash
cd frontend
npm install
npm run dev                             # http://localhost:3000
```

Switch the LLM for the ablation by editing `backend/.env` (copy from
`.env.example`): set `LLM_PROVIDER=openai|anthropic`, add the key. Point
`OPENAI_BASE_URL` at a vLLM/Ollama server to run the Llama arm.

## The six failure codes (never invent new ones)

`json_invalid`, `math_invalid`, `nonunique_solution`, `unit_mismatch`,
`semantic_ambiguity`, `off_target_difficulty`. They are defined once in
`verification/result.py::FailureCode`. Every rejection maps to exactly one of
these; metrics and the event log depend on this closed set.

## Conventions and invariants (please preserve)

- **The verifier is the oracle, not the LLM.** Never let model output decide
  mathematical correctness. If you add a domain, add a deterministic verifier
  for it.
- **The translation layer fails closed.** Unparseable / out-of-allow-list
  expressions raise, never `eval`. Don't widen `_ALLOWED_FUNCS` casually.
- **The event log is append-only.** Write new `Event` rows; never update or
  delete them. `Student`/`ProblemRecord` are projections.
- **Personalization changes context only** — never skill or difficulty. That
  separation is a research variable; keep it clean.
- **Offline-first.** The `mock` provider must keep the whole pipeline and test
  suite green with no network/keys. New features need a mock path.
- **Schemas are the contract.** Generator output that fails Pydantic validation
  is `json_invalid` by definition — don't "rescue" malformed JSON in the loop.

## Adding a skill (typical change)

1. Register it in `content/skills.py::SKILLS` (domain + verification method,
   plus `template` for physics).
2. Ensure the verification method exists in `math_verifier` / `physics_verifier`.
3. Add a mock builder branch in `llm/mock.py` so it works offline.
4. Add a test in `backend/tests/`.

## For Claude Code specifically

- Run `pytest` from `backend/` after backend changes; it's fast and offline.
- Prefer editing existing modules over adding parallel ones.
- When unsure about intended behavior, the design PDFs and `docs/architecture.md`
  are authoritative over guesses.
- Default to the latest Claude models if wiring the Anthropic provider for demos;
  use GPT-5.2 / Llama for the formal cross-model ablation per the research plan.
