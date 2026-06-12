from app.schemas.generator import PhysicsTask, Quantity
from app.verification import physics_verifier
from app.verification.result import FailureCode


def _kinematics(v_unit="m/s", v_val=11.0):
    return PhysicsTask(
        template="kinematics",
        givens={
            "u": Quantity(value=5, unit="m/s"),
            "a": Quantity(value=2, unit="m/s**2"),
            "t": Quantity(value=3, unit="s"),
        },
        unknown="v",
        expected_answer=Quantity(value=v_val, unit=v_unit),
    )


def test_kinematics_correct():
    assert physics_verifier.verify(_kinematics()).passed


def test_kinematics_wrong_value_math_invalid():
    res = physics_verifier.verify(_kinematics(v_val=20.0))
    assert not res.passed
    assert FailureCode.MATH_INVALID in res.failures


def test_unit_mismatch_detected():
    # Claiming the velocity answer is in seconds is a dimensional error.
    res = physics_verifier.verify(_kinematics(v_unit="s"))
    assert not res.passed
    assert FailureCode.UNIT_MISMATCH in res.failures


def test_newton_friction():
    task = PhysicsTask(
        template="newton_friction",
        givens={
            "m": Quantity(value=10, unit="kg"),
            "F_applied": Quantity(value=50, unit="N"),
            "mu": Quantity(value=0.2, unit=""),
        },
        unknown="a",
        expected_answer=Quantity(value=(50 - 0.2 * 10 * 9.8) / 10, unit="m/s**2"),
    )
    assert physics_verifier.verify(task).passed


def test_natural_field_names_are_normalized():
    # LLMs say "velocity"/"radius"/"acceleration"; the template keys are v/r/ac.
    # A correct answer must not be rejected just for vocabulary.
    task = PhysicsTask(
        template="circular_motion",
        givens={"velocity": Quantity(value=500, unit="m/s"), "radius": Quantity(value=2000, unit="m")},
        unknown="acceleration",
        expected_answer=Quantity(value=125, unit="m/s**2"),
    )
    res = physics_verifier.verify(task)
    assert res.passed
    assert res.data.get("computed")


def test_wrong_answer_exposes_computed_value():
    task = PhysicsTask(
        template="circular_motion",
        givens={"velocity": Quantity(value=500, unit="m/s"), "radius": Quantity(value=2000, unit="m")},
        unknown="acceleration",
        expected_answer=Quantity(value=62.5, unit="m/s**2"),  # wrong; real answer 125
    )
    res = physics_verifier.verify(task)
    assert not res.passed
    assert FailureCode.MATH_INVALID in res.failures
    assert res.data.get("computed")  # the verifier's own answer, for display


def test_unrealistic_speed_rejected():
    task = _kinematics()
    task.givens["u"] = Quantity(value=5000, unit="m/s")
    res = physics_verifier.verify(task)
    assert not res.passed
