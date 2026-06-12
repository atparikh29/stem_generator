from app.schemas.generator import MathTask
from app.verification import math_verifier
from app.verification.result import FailureCode


def test_correct_derivative_passes():
    task = MathTask(kind="derivative", expression="x**3 + 2*x", expected_answer="3*x**2 + 2")
    assert math_verifier.verify(task).passed


def test_wrong_derivative_fails_math_invalid():
    task = MathTask(kind="derivative", expression="x**3", expected_answer="2*x**2")
    res = math_verifier.verify(task)
    assert not res.passed
    assert FailureCode.MATH_INVALID in res.failures


def test_definite_integral():
    task = MathTask(kind="integral", expression="x**2", interval=[0, 2], expected_answer="8/3")
    assert math_verifier.verify(task).passed


def test_limit():
    task = MathTask(kind="limit", expression="(x**2 - 1)/(x - 1)", point=1, expected_answer="2")
    assert math_verifier.verify(task).passed


def test_trig_identity_simplify():
    task = MathTask(kind="simplify", expression="sin(x)**2 + cos(x)**2", expected_answer="1")
    assert math_verifier.verify(task).passed


def test_domain_restricted_trig_solution_unique():
    task = MathTask(kind="solve_equation", expression="sin(x) = 1/2",
                    interval=[0, 1.5708], expected_answer="pi/6")
    assert math_verifier.verify(task).passed


def test_periodic_equation_over_reals_is_nonunique():
    task = MathTask(kind="solve_equation", expression="sin(x) = 0", expected_answer="0")
    res = math_verifier.verify(task)
    assert not res.passed
    assert FailureCode.NONUNIQUE_SOLUTION in res.failures
