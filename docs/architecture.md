# Architecture

This document explains how the codebase is structured and how a request flows
through it. It mirrors the design PDFs and the flowchart.

## 1. The big picture

Three processes:

1. **Frontend** (`frontend/`) — Next.js practice UI. Talks only to the backend
   HTTP API.
2. **Backend** (`backend/app/`) — FastAPI app hosting the agent loop and the
   verifier. This is where the research lives.
3. **Database** — SQLite by default (zero setup), PostgreSQL for real runs. Holds
   an **append-only event log** plus convenience projections.

## 2. The closed loop, step by step

Everything below happens inside `agents/orchestrator.py::generate_next_problem`.
Each numbered step maps to a flowchart box.

| # | Step | Module | Output |
|---|------|--------|--------|
| 1 | Observe telemetry | orchestrator + `models.Event` | recent attempts |
| 2 | Assessor: skill vector | `agents/assessor.py` | mastery per skill, misconceptions |
| 3 | Planner: skill & difficulty | `agents/planner.py` | `(skill, difficulty_target)` |
| 4 | Context selector | `agents/context_selector.py` | a context (theme only) |
| 5 | LLM generator: strict JSON | `llm/*` + `schemas/generator.py` | `GeneratorOutput` |
| 6 | Translation: JSON → symbolic | `translation/registry.py` | `TranslationRecord` |
| 7 | Neuro-symbolic verify | `verification/engine.py` | `VerifierReport` |
| 8 | Accept or regenerate | orchestrator | delivered problem **or** retry |

If JSON fails validation → `json_invalid`, regenerate. If a deterministic check
fails → its failure code is fed back into the next generation prompt. After
`MAX_REGENERATIONS`, the attempt is recorded as `failed`.

## 3. Why the translation layer exists

The LLM emits natural-language-adjacent JSON. We never parse mathematics out of
prose. The `task` field carries a **machine-checkable spec** (e.g. a SymPy
expression string + claimed answer). `translation/registry.py` is the single,
auditable bridge from that spec to executable SymPy/pint objects, and it **fails
closed**: anything outside a known function/symbol allow-list raises rather than
executing. This makes every verification reproducible and safe.

## 4. The verifier (the oracle)

`verification/engine.py` runs four checks and applies the acceptance rule
("deliver only if all deterministic checks pass and ambiguity < threshold"):

- **`math_verifier.py` (SymPy)** — `solve_equation` (with optional domain
  restriction), `derivative`, `integral`, `limit`, `simplify`. Equivalence uses
  `simplify` with a numeric-sampling fallback. Detects non-unique/infinite
  solution sets.
- **`physics_verifier.py` (templates + pint)** — one formula template per AP
  Physics 1 skill. pint enforces unit consistency; a realism envelope rejects
  absurd magnitudes; the numeric answer is checked against the claim.
- **`difficulty.py`** — operation-count heuristic (math) / chain-length heuristic
  (physics) binned to 1–5; emits `off_target_difficulty` on a miss.
- **`semantic.py` (LLM)** — ambiguity score only. Heuristic under the mock
  provider so the pipeline stays offline.

Each check returns a `CheckResult` carrying zero or more `FailureCode`s. The six
codes are the complete, closed vocabulary of rejection reasons.

## 5. Data model

- **`Event`** — immutable, append-only. One row per observe/plan/generate/verify/
  fail/deliver/attempt. This is the research record; never mutate it.
- **`Student`** — id, interests, `skill_vector`, misconceptions.
- **`ProblemRecord`** — a delivered (or failed) problem, with `regen_count` and
  `failure_reasons`.

## 6. LLM provider abstraction

`llm/base.py` defines a tiny `LLMProvider` protocol with `complete()` and
`generate_problem()`. Implementations:

- **`mock.py`** — offline oracle; uses SymPy/pint to emit *correct* problems so
  the pipeline and tests run with no keys. Self-tunes difficulty.
- **`openai_provider.py`** — GPT-5.2, or Llama via an OpenAI-compatible base URL.
- **`anthropic_provider.py`** — Claude.

Swapping providers is the core ablation knob.

## 7. Where to change things

- New skill → `content/skills.py` (+ verifier method + mock builder + test).
- New context/theme → `content/context_library.json`.
- New failure reason → don't. The closed set is intentional; discuss first.
- Verifier thresholds → `backend/.env` (`SEMANTIC_AMBIGUITY_THRESHOLD`,
  `MAX_REGENERATIONS`).
