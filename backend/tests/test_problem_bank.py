"""The pre-stored bank must cover every skill and only contain verifier-valid problems."""
import pytest

from app.content import problem_bank
from app.content.skills import all_skills
from app.llm.mock import MockProvider
from app.schemas.generator import GeneratorOutput
from app.verification import engine


def test_bank_is_built_and_covers_every_skill():
    bank = problem_bank.load()
    assert bank, "problem_bank.json is empty -- run `python -m scripts.build_problem_bank`"
    covered = problem_bank.skills_covered()
    assert set(all_skills()) <= covered, f"missing skills: {set(all_skills()) - covered}"


@pytest.mark.parametrize("skill", all_skills())
def test_fetched_problem_passes_the_verifier(skill):
    entry = problem_bank.fetch(skill, difficulty=3)  # falls back to nearest difficulty
    assert entry is not None
    candidate = GeneratorOutput(
        skill=entry["skill"], difficulty_target=entry["difficulty"],
        statement=entry["statement"], solution=entry["solution"], task=entry["task"],
    )
    assert engine.verify(candidate, MockProvider()).accepted


def test_fetch_unknown_skill_returns_none():
    assert problem_bank.fetch("not_a_skill", 1) is None
