# Configuration guide

Everything tunable in this project is configured through **three layers**. Prefer
the earliest layer that fits — don't hardcode.

1. **Runtime settings** — env vars → `backend/app/config.py` (`Settings`).
2. **Content/data files** — JSON in `backend/app/content/`.
3. **Per-request overrides** — API query params / the UI selectors.

---

## Layer 1 — Runtime settings (`.env`)

Copy `.env.example` to `backend/.env` and edit. Every key below is an env var read
by `Settings` in `backend/app/config.py`. **Restart the backend after changing.**
Env vars are UPPER_SNAKE_CASE of the field name (e.g. `MAX_REGENERATIONS`).

### LLM provider
| Env var | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` \| `openai` \| `anthropic` \| `gemini` (default when a request doesn't override) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | – / `gpt-5.2` / – | OpenAI, or Llama via a compatible base URL (e.g. Ollama `http://localhost:11434/v1`) |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | – / `claude-opus-4-8` | Claude |
| `GEMINI_API_KEY` / `GEMINI_MODEL` / `GEMINI_BASE_URL` | – / `gemini-2.5-flash` / Google OpenAI-compat URL | Gemini |

### Database
| `DATABASE_URL` | `sqlite:///./stemgen.db` | SQLite (default) or `postgresql+psycopg://…` |

### Verifier
| `SEMANTIC_AMBIGUITY_THRESHOLD` | `0.5` | reject if the LLM clarity score exceeds this |
| `MAX_REGENERATIONS` | `5` | retry budget for the generate→verify loop |
| `DIFFICULTY_TOLERANCE` | `0` | allowed `|observed − target|` bin gap; 0 = strict (experiment), 1–2 = forgiving |

### Assessor (student model)
| `ASSESSOR_ALPHA` | `0.4` | EMA weight on the newest attempt |
| `INITIAL_MASTERY` | `0.2` | cold-start mastery prior per skill |
| `MISCONCEPTION_THRESHOLD` | `0.25` | mastery below this is flagged as a gap |

### Difficulty anchors (advanced, JSON-valued env)
Difficulty is binned 1..5 relative to a per-skill `(lo, hi)` raw-score range.
Override with a JSON string, e.g.
`DIFFICULTY_MATH_ANCHORS='{"derivative":[3,16]}'`. Fields:
`DIFFICULTY_MATH_ANCHORS`, `DIFFICULTY_PHYS_ANCHORS`, `DIFFICULTY_PHYS_BASE`.

---

## Layer 2 — Content/data files (no code, no restart of logic)

| File | Controls | How |
|---|---|---|
| `backend/app/content/context_library.json` | themes/contexts (id, noun, narrative, interest tags) | edit JSON |
| `backend/app/content/problem_bank.json` | the pre-stored validated problems | regenerate: `python -m scripts.build_problem_bank [--augment]` |

---

## Layer 3 — Per-request overrides (API / UI)

The web UI selectors (and API query params) override the defaults per request:
- **Model** — `?provider=mock|openai|anthropic|gemini`
- **Skill** — `?skill=<id>|random|auto`
- **Difficulty** — `?difficulty=1..5`
- **Context** — chosen at onboarding / settings

Endpoints: `GET /skills`, `GET /contexts`, `POST /sessions`,
`POST /sessions/{id}/settings`, `GET /sessions/{id}/pre-stored`,
`GET /sessions/{id}/next-problem/stream`.

---

## Still defined in code (change the file, add a test)

These are structural, not runtime knobs — edit the source and add a test:

| What | File | Notes |
|---|---|---|
| Skill taxonomy (domain, verification method, physics template) | `content/skills.py` | see "Adding a skill" in `CLAUDE.md` |
| Difficulty op-weights & calculus bonus | `verification/difficulty.py` | keyed by SymPy node types (not env-friendly) |
| Physics templates & field aliases | `verification/physics_verifier.py` | one formula template per skill |
| Prompt text & per-skill examples | `llm/prompt.py` | system instruction, task specs, math rules |
| Mock oracle builders | `llm/mock.py` | offline generator used to seed the bank |

## Quick recipes

- **Run fully offline, instant:** `LLM_PROVIDER=mock` (default).
- **Free local model:** `LLM_PROVIDER=openai`, `OPENAI_BASE_URL=http://localhost:11434/v1`, `OPENAI_MODEL=llama3.1` (with `ollama serve`).
- **Strict research mode:** `DIFFICULTY_TOLERANCE=0`, `SEMANTIC_AMBIGUITY_THRESHOLD=0.5`.
- **Forgiving demo mode:** `DIFFICULTY_TOLERANCE=2`, `MAX_REGENERATIONS=8`.
