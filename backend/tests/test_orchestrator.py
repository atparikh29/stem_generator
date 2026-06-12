"""End-to-end: the mock provider should drive the loop to an accepted problem
for every skill, fully offline."""
from app.agents import orchestrator
from app.content.skills import all_skills
from app.llm.mock import MockProvider
from app.models import Student


def _student():
    from app.agents import assessor

    return Student(id="t1", name="Test", interests=["sports", "skateboarding"],
                   skill_vector=assessor.initial_skill_vector())


def test_every_skill_produces_accepted_problem():
    provider = MockProvider()
    student = _student()
    for skill in all_skills():
        # Force the planner's choice by zeroing one skill's mastery.
        student.skill_vector = {s: (0.0 if s == skill else 0.9) for s in all_skills()}
        result = orchestrator.generate_next_problem(student, provider, session=None, max_regenerations=5)
        assert result.accepted, f"{skill} failed: {result.report.failure_reasons}"
        assert result.problem.skill == skill
        assert result.report.accepted


def test_loop_runs_without_session():
    provider = MockProvider()
    result = orchestrator.generate_next_problem(_student(), provider, session=None)
    assert result.report is not None
