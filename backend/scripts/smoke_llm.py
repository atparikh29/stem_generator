"""Smoke-test the configured LLM provider through the full pipeline.

Runs three increasing-scope checks against whatever LLM_PROVIDER is set in
backend/.env (mock | openai | anthropic):

  (a) one raw generation        -> connectivity + schema-valid JSON
  (b) verify that candidate     -> the deterministic verifier's verdict
  (c) one full closed loop       -> regenerate-until-valid in action

Run from the backend/ directory:

    python -m scripts.smoke_llm
    python -m scripts.smoke_llm --skill kinematics --difficulty 2

This is a manual/online check -- it actually calls the provider. The offline
pytest suite always uses the mock, so it never spends money.
"""
from __future__ import annotations

import argparse

from app.agents import orchestrator
from app.config import settings
from app.llm.base import GenerationSpec, get_provider
from app.models import Student
from app.verification import engine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default="derivative_rules")
    ap.add_argument("--difficulty", type=int, default=2)
    ap.add_argument("--max-regen", type=int, default=8)
    ap.add_argument("--hide-prompt", action="store_true", help="don't print the prompt sent to the model")
    args = ap.parse_args()

    provider = get_provider()
    print(f"Provider: {provider.name}  |  model/config from .env (LLM_PROVIDER={settings.llm_provider})")

    spec = GenerationSpec(
        skill=args.skill,
        difficulty_target=args.difficulty,
        context={"id": "generic", "noun": "an object"},
    )

    if not args.hide_prompt:
        from app.llm.prompt import SYSTEM_INSTRUCTION, build_generation_prompt

        print("\n=== PROMPT SENT TO THE MODEL ===")
        print("[system]\n" + SYSTEM_INSTRUCTION)
        print("[user]\n" + build_generation_prompt(spec))
        print("=== END PROMPT ===")

    print("\n--- (a) Provider proposed a candidate ---")
    try:
        candidate = provider.generate_problem(spec)
        print("statement:", candidate.statement)
        print("task     :", candidate.task.model_dump())

        print("\n--- (b) Deterministic verifier verdict ---")
        report = engine.verify(candidate, provider)
        print("accepted:", report.accepted)
        if report.accepted:
            print("all checks passed (math/units, difficulty, clarity)")
        else:
            print("rejected — reason(s):")
            for e in engine.explain(report):
                print(f"  • {e['code']}: {e['label']}")
                if e["detail"]:
                    print(f"      → {e['detail']}")
    except ValueError as exc:
        # A raw single call can legitimately fail schema validation -> json_invalid.
        # The full loop in (c) is what recovers from this; show it, don't crash.
        print("json_invalid on this raw attempt:", str(exc)[:140])
        print("(this is expected for fallible models; the loop below handles it)")

    print("\n--- (c) Full regenerate-until-valid loop (live) ---")
    show_prompt = not args.hide_prompt

    def show(ev: dict) -> None:
        status = ev.get("status")
        a = ev.get("attempt")
        if status == "plan":
            print(f"  plan: skill={ev['skill']} difficulty={ev['difficulty_target']}", flush=True)
        elif status == "generating":
            print(f"\n  attempt {a}: generating… (calling the model)", flush=True)
            # What changed this attempt: the appended failure feedback.
            if ev.get("feedback"):
                print(f"    ↻ prompt now also says: \"previous attempt REJECTED for "
                      f"{', '.join(ev['feedback'])}; fix exactly these\"", flush=True)
            if show_prompt and ev.get("prompt"):
                print("    ---- full prompt for this attempt ----", flush=True)
                for line in ev["prompt"].splitlines():
                    print("    | " + line, flush=True)
                print("    --------------------------------------", flush=True)
        elif status in ("accepted", "rejected"):
            # Show what the model actually proposed, even when it gets rejected.
            if ev.get("statement"):
                print(f"    question: {ev['statement']}", flush=True)
                print(f"    answer  : {ev['answer']}", flush=True)
            if status == "accepted":
                print(f"    -> ✓ ACCEPTED and delivered", flush=True)
            else:
                print(f"    -> ✗ rejected — reason(s):", flush=True)
                for e in ev.get("details", []):
                    line = f"       • {e['code']}: {e['label']}"
                    print(line, flush=True)
                    if e.get("detail"):
                        print(f"           → {e['detail']}", flush=True)
                if not ev.get("details"):  # json_invalid path has no candidate/report
                    print(f"       • json_invalid: {ev.get('detail','')[:100]}", flush=True)
                print("       regenerating…", flush=True)
        elif status == "exhausted":
            print(f"\n  budget exhausted; last failures {ev['failures']}", flush=True)

    # Honor --skill and --difficulty by overriding the Planner (neutral interests
    # keep the context generic).
    student = Student(id="smoke", interests=[])
    result = orchestrator.generate_next_problem(
        student, provider, session=None, max_regenerations=args.max_regen, progress=show,
        skill_override=args.skill, difficulty_override=args.difficulty,
    )
    print(f"\nresult: accepted={result.accepted}  regen_count={result.regen_count}")


if __name__ == "__main__":
    main()
