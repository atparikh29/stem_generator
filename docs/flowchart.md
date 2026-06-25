# System flowchart (as implemented)

This reflects the actual codebase: session lifecycle, the pre-stored validated
bank, model-driven generation, and the keep-settings vs. adaptive (Planner)
split. See `docs/architecture.md` for the prose version.

```mermaid
---
config:
  layout: fixed
---
flowchart TB
 subgraph Verifier["Neuro-Symbolic Verifier (the oracle)"]
        SymPy["SymPy Math<br>Equivalence, Solvability,<br>Difficulty (per-skill bins)"]
        PhysicsTemplates["Physics Templates<br>Units, Realism, Numeric"]
        LLMSemantic["LLM Semantic<br>Clarity Check"]
  end
 subgraph Bank["Pre-stored Validated Bank"]
        BuildBank["build_problem_bank.py<br>seed (SymPy/pint oracle)<br>+ --augment (LLM)<br>every entry passes the verifier"]
        BankJSON[("problem_bank.json")]
        BuildBank --> BankJSON
  end
    Start(["START Session"]) --> SessionCheck{"Returning Session?<br>(browser sessionId)"}
    SessionCheck -- No --> Onboarding["Initial Onboarding<br>Select Context, Skill,<br>Difficulty &amp; Model"]
    Onboarding --> FetchPreStored["Fetch Pre-stored<br>Validated Problem"]
    SessionCheck -- Yes --> LoadState["Load Saved State<br>Context, Skill, Difficulty,<br>Model &amp; Skill Vector"]
    LoadState --> StartupChange{"Change Settings<br>on Startup?"}
    StartupChange -- Yes --> AdjustSettings["Adjust Settings<br>Context, Skill,<br>Difficulty &amp; Model"]
    AdjustSettings --> FetchPreStored
    StartupChange -- "No (continue)" --> KeepSettings{"Model = Mock?"}
    BankJSON -. served instantly .-> FetchPreStored
    FetchPreStored -- "skill not banked<br>(fallback)" --> ContextSelector
    FetchPreStored --> StudentInteraction(["Student Interaction<br>(answer the problem)"])
    StudentInteraction --> ObserveTelemetry["Observe Telemetry"]
    ObserveTelemetry --> Assessor["Assessor<br>Update Skill Vector"]
    Assessor --> SaveState["Save State to DB<br>Progress &amp; Skill Vector<br>(append-only event log)"]
    SaveState --> NextChoice{"Next action?"}
    NextChoice -- "Change settings" --> AdjustSettings
    NextChoice -- "Next problem<br>(keep skill &amp; difficulty)" --> KeepSettings
    NextChoice -- "Adaptive next" --> Planner["Planner<br>pick Skill &amp; Difficulty<br>from mastery"]
    KeepSettings -- Yes --> FetchPreStored
    KeepSettings -- "No (Llama/Claude)" --> ContextSelector["Context Selector<br>Personalized Context"]
    Planner --> ContextSelector
    ContextSelector --> LLMGenerator["LLM Generator<br>(selected model)<br>Structured JSON"]
    LLMGenerator --> JSONValid{"JSON valid &amp;<br>matches skill?"}
    JSONValid -- No --> FailReason["Fail Reason<br>json_invalid / math_invalid /<br>nonunique_solution / unit_mismatch /<br>semantic_ambiguity / off_target_difficulty"]
    JSONValid -- Yes --> TranslationLayer["Translation Layer<br>JSON → Symbolic<br>(fails closed)"]
    TranslationLayer --> SymPy
    SymPy --> PhysicsTemplates
    PhysicsTemplates --> LLMSemantic
    LLMSemantic --> Accept{"ACCEPT?<br>Deterministic ✓<br>Semantic ✓<br>(difficulty tolerance)"}
    Accept -- Yes --> DeliverProblem["Deliver Problem<br>Update Event Log<br>(source = pre_stored | llm)"]
    Accept -- No --> FailReason
    FailReason -- "regenerate with<br>specific failure detail" --> LLMGenerator
    DeliverProblem --> StudentInteraction
```

## What changed vs. the original flowchart

- **Model** is chosen at onboarding / settings, and it routes the "keep settings"
  path: **Mock → instant pre-stored**, **Llama/Claude → live LLM generation** at
  the chosen skill & difficulty.
- **Pre-stored bank** is an explicit source (`problem_bank.json`), built by
  `scripts/build_problem_bank.py` (deterministic seed + optional `--augment`);
  every entry is verifier-valid. Fetch falls back to the LLM loop if a skill
  isn't banked.
- **Two "next" paths**: *Next problem* keeps the user's skill/difficulty;
  *Adaptive next* hands skill & difficulty to the Planner.
- **JSON check** also enforces task↔skill consistency; **regeneration** feeds the
  *specific* failure detail (e.g. the verifier's computed answer) back to the model.
- **Difficulty** is binned per-skill with a configurable tolerance.
- Delivery records the **source** (`pre_stored` | `llm`) in the append-only log.
