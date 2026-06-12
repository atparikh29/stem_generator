"""engine.explain turns a rejection into per-failure, human-readable reasons."""
from app.llm.mock import MockProvider
from app.schemas.generator import GeneratorOutput, MathTask, PhysicsTask, Quantity
from app.verification import engine


def test_explain_math_invalid_includes_computed_answer():
    cand = GeneratorOutput(
        skill="derivative_rules", difficulty_target=2,
        statement="Find the derivative of f(x) = x^3 with respect to x.",
        solution="...",
        task=MathTask(kind="derivative", expression="x**3", expected_answer="2*x"),  # wrong
    )
    report = engine.verify(cand, MockProvider())
    by_code = {e["code"]: e for e in engine.explain(report)}
    assert "math_invalid" in by_code
    assert by_code["math_invalid"]["label"]            # plain-language label present
    assert "3*x**2" in by_code["math_invalid"]["detail"]  # the verifier's own answer


def test_explain_lists_every_failure_reason():
    cand = GeneratorOutput(
        skill="circular_motion", difficulty_target=1,
        statement="An object moves in a circle. Find acceleration.",
        solution="...",
        task=PhysicsTask(template="circular_motion",
                         givens={"v": Quantity(value=15, unit="m/s"), "r": Quantity(value=2, unit="m")},
                         unknown="ac", expected_answer=Quantity(value=1950, unit="m/s**2")),  # wrong
    )
    report = engine.verify(cand, MockProvider())
    codes = {e["code"] for e in engine.explain(report)}
    assert codes == set(report.failure_reasons)
    assert "math_invalid" in codes
