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


def test_task_skill_consistency_check():
    from app.agents.orchestrator import _task_matches_skill
    from app.schemas.generator import MathTask, PhysicsTask, Quantity

    # right shapes pass
    assert _task_matches_skill("limits", MathTask(kind="limit", expression="x", point=0.0, expected_answer="0")) is None
    assert _task_matches_skill(
        "kinematics",
        PhysicsTask(template="kinematics", givens={"u": Quantity(value=1, unit="m/s")}, unknown="v",
                    expected_answer=Quantity(value=1, unit="m/s")),
    ) is None
    # wrong shapes are flagged
    assert _task_matches_skill("limits", MathTask(kind="derivative", expression="x", expected_answer="1"))
    assert _task_matches_skill(
        "limits",
        PhysicsTask(template="kinematics", givens={}, unknown="v", expected_answer=Quantity(value=1, unit="m/s")),
    )


def test_progress_callback_receives_live_events():
    events: list[dict] = []
    orchestrator.generate_next_problem(
        _student(), MockProvider(), session=None, progress=events.append
    )
    statuses = [e["status"] for e in events]
    # The mock accepts on the first attempt: plan -> generating -> accepted.
    assert statuses[0] == "plan"
    assert "generating" in statuses
    assert "accepted" in statuses
