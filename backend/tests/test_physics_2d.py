"""2D / rotational physics templates: correctness, unit checks, difficulty spread."""
import pytest

from app.llm.mock import MockProvider, _build_physics
from app.schemas.generator import GeneratorOutput, PhysicsTask, Quantity
from app.verification import difficulty, engine, physics_verifier

NEW = ["rotational_kinematics", "torque", "rotational_dynamics",
       "inclined_plane", "projectile_motion"]


def _candidate(skill):
    st, sol, task = _build_physics(skill, {"noun": "a ball"})
    return GeneratorOutput(skill=skill, difficulty_target=difficulty.score(task),
                           statement=st, solution=sol, task=task)


@pytest.mark.parametrize("skill", NEW)
def test_new_template_generates_and_verifies(skill):
    assert engine.verify(_candidate(skill), MockProvider()).accepted


@pytest.mark.parametrize("skill", NEW)
def test_wrong_answer_is_rejected_math_invalid(skill):
    st, sol, task = _build_physics(skill, {"noun": "a ball"})
    task.expected_answer = Quantity(value=task.expected_answer.value + 42.0,
                                    unit=task.expected_answer.unit)
    cand = GeneratorOutput(skill=skill, difficulty_target=3, statement=st, solution=sol, task=task)
    assert not engine.verify(cand, MockProvider()).accepted


def test_projectile_range_formula():
    # R = v0^2 sin(2*theta)/g ; at 45 deg (~0.7854 rad) R = v0^2/g.
    task = PhysicsTask(template="projectile_motion",
                       givens={"v0": Quantity(value=20, unit="m/s"),
                               "theta": Quantity(value=0.7854, unit="rad")},
                       unknown="range",
                       expected_answer=Quantity(value=20 ** 2 / 9.8, unit="m"))
    assert physics_verifier.verify(task).passed


def test_torque_unit_mismatch_is_caught():
    # Claiming the torque is in newtons (not N*m) must fail on dimensionality.
    task = PhysicsTask(template="torque",
                       givens={"r": Quantity(value=2, unit="m"), "F": Quantity(value=10, unit="N"),
                               "theta": Quantity(value=1.5708, unit="rad")},
                       unknown="torque",
                       expected_answer=Quantity(value=20, unit="N"))  # wrong unit
    res = physics_verifier.verify(task)
    assert not res.passed


def test_new_physics_spans_bins_4_and_5():
    # The whole point: rotational/2D fill the difficulty bins plain templates couldn't.
    bins = {difficulty.score(_build_physics(s, {"noun": "x"})[2]) for s in NEW}
    assert {4, 5} <= bins, f"expected bins 4 and 5 to be covered, got {sorted(bins)}"
