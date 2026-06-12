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

from app.agents import assessor, orchestrator
from app.config import settings
from app.llm.base import GenerationSpec, get_provider
from app.models import Student
from app.verification import engine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default="derivative_rules")
    ap.add_argument("--difficulty", type=int, default=2)
    ap.add_argument("--max-regen", type=int, default=8)
    args = ap.parse_args()

    provider = get_provider()
    print(f"Provider: {provider.name}  |  model/config from .env (LLM_PROVIDER={settings.llm_provider})")

    spec = GenerationSpec(
        skill=args.skill,
        difficulty_target=args.difficulty,
        context={"id": "generic", "noun": "an object"},
    )

    print("\n--- (a) Provider proposed a candidate ---")
    candidate = provider.generate_problem(spec)
    print("statement:", candidate.statement)
    print("task     :", candidate.task.model_dump())

    print("\n--- (b) Deterministic verifier verdict ---")
    report = engine.verify(candidate, provider)
    print("accepted       :", report.accepted)
    print("failure_reasons:", report.failure_reasons)

    print("\n--- (c) Full regenerate-until-valid loop ---")
    student = Student(id="smoke", interests=["space"], skill_vector=assessor.initial_skill_vector())
    result = orchestrator.generate_next_problem(
        student, provider, session=None, max_regenerations=args.max_regen
    )
    print("accepted   :", result.accepted)
    print("regen_count:", result.regen_count)
    for a in result.attempts:
        print("   rejected attempt:", a["failures"])
    if result.accepted:
        print("delivered  :", result.problem.statement)


if __name__ == "__main__":
    main()
