"""Build the pre-stored validated problem bank -> app/content/problem_bank.json.

Seed (default): generate problems with the deterministic SymPy/pint oracle
(MockProvider) for every skill x difficulty, run each through the full verifier,
and keep only those that pass ALL six checks. Guaranteed valid, offline, no keys.

--augment: additionally ask the configured LLM provider to generate problems
*similar* to a seed example, verify each, and append the passers (the "ask LLM to
generate similar problems" arm). Needs Ollama / an API key.

Run from backend/:
    python -m scripts.build_problem_bank                 # seed only
    python -m scripts.build_problem_bank --augment --per 3
"""
from __future__ import annotations

import argparse
import json

from app.content.problem_bank import _BANK_PATH
from app.content.skills import all_skills
from app.llm.base import GenerationSpec, get_provider
from app.llm.mock import MockProvider
from app.verification import engine

# A few contexts to vary wording/flavor (id + physics noun).
_CONTEXTS = [
    {"id": "generic", "noun": "an object"},
    {"id": "skateboarding", "noun": "a skateboarder"},
    {"id": "space", "noun": "a small satellite"},
]


def _key(p: dict) -> tuple:
    return (p["skill"], p["difficulty"], p["statement"])


def _entry(problem) -> dict:
    return {
        "skill": problem.skill,
        "difficulty": problem.difficulty_target,
        "context_id": getattr(problem, "context_id", "") or "generic",
        "statement": problem.statement,
        "solution": problem.solution,
        "task": problem.task.model_dump(),
    }


def build_seed(per: int) -> list[dict]:
    mock = MockProvider()
    seen: set[tuple] = set()
    bank: list[dict] = []
    for skill in all_skills():
        for difficulty in range(1, 6):
            for ctx in _CONTEXTS:
                for _ in range(per):
                    spec = GenerationSpec(skill, difficulty, ctx)
                    problem = mock.generate_problem(spec)
                    report = engine.verify(problem, mock)
                    if not report.accepted:
                        continue
                    e = _entry(problem)
                    e["context_id"] = ctx["id"]
                    if _key(e) in seen:
                        continue
                    seen.add(_key(e))
                    bank.append(e)
    return bank


def augment(bank: list[dict], per: int) -> list[dict]:
    """Ask the configured LLM for problems similar to seeds; keep verifier passers."""
    provider = get_provider()
    mock = MockProvider()  # for the semantic check path
    seen = {_key(p) for p in bank}
    added = 0
    for skill in all_skills():
        for difficulty in range(1, 6):
            for _ in range(per):
                spec = GenerationSpec(skill, difficulty, _CONTEXTS[0])
                try:
                    problem = provider.generate_problem(spec)
                except Exception:  # noqa: BLE001 - skip bad generations
                    continue
                if problem.skill != skill:
                    continue
                if not engine.verify(problem, mock).accepted:
                    continue
                e = _entry(problem)
                if _key(e) in seen:
                    continue
                seen.add(_key(e))
                bank.append(e)
                added += 1
    print(f"augment: added {added} LLM-verified problems")
    return bank


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=4, help="variants to try per skill/difficulty/context")
    ap.add_argument("--augment", action="store_true", help="also add LLM-generated, verified problems")
    args = ap.parse_args()

    bank = build_seed(args.per)
    if args.augment:
        bank = augment(bank, args.per)

    _BANK_PATH.write_text(json.dumps(bank, indent=1))
    by_skill: dict[str, int] = {}
    for p in bank:
        by_skill[p["skill"]] = by_skill.get(p["skill"], 0) + 1
    print(f"wrote {len(bank)} problems to {_BANK_PATH}")
    for skill, n in sorted(by_skill.items()):
        diffs = sorted({p['difficulty'] for p in bank if p['skill'] == skill})
        print(f"  {skill:<24} {n:>3} problems, difficulties {diffs}")


if __name__ == "__main__":
    main()
