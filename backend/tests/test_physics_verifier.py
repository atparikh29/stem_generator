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


def test_unrealistic_speed_rejected():
    task = _kinematics()
    task.givens["u"] = Quantity(value=5000, unit="m/s")
    res = physics_verifier.verify(task)
    assert not res.passed
