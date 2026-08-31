import pytest
import sympy as sp

from app.schemas.generator import MathTask
from app.translation.registry import parse_math
from app.verification import math_verifier
from app.verification.result import FailureCode


@pytest.mark.parametrize(
    "student, canonical",
    [
        # A variable fused to a function name — the parser used to read "xsin"
        # as one symbol and split it into x*s*i*n.
        ("2xsin(4x)", "2*x*sin(4*x)"),
        ("4x^2cos(4x)+2xsin(4x)", "4*x**2*cos(4*x) + 2*x*sin(4*x)"),
        ("x^2cos(4x)", "x**2*cos(4*x)"),
        ("sin(2xcos(x))", "sin(2*x*cos(x))"),
    ],
)
def test_variable_glued_to_function_parses(student, canonical):
    assert sp.simplify(parse_math(student) - parse_math(canonical)) == 0


def test_glued_does_not_corrupt_prefixed_functions():
    # "asin(" must stay the arcsine, not become a*sin(.
    assert parse_math("asin(x)") == sp.asin(sp.Symbol("x", real=True))


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
