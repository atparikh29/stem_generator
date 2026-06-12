"""Deterministic, offline reference generator.

Stands in for the LLM generator so the full agentic pipeline (and the test
suite) runs with no API key. Unlike a real LLM, it uses SymPy / pint to compute
*correct* answers, so it behaves like an oracle generator: every candidate it
emits is mathematically valid. It self-tunes a complexity knob to hit the
planner's target difficulty bin; if it cannot, it reports its honest difficulty.

Real providers (OpenAI/GPT-5.2, Anthropic, Llama) replace this class for the
cross-model reliability ablation, where genuine generation errors exercise the
regenerate-until-valid loop and the six failure codes.
"""
from __future__ import annotations

import sympy as sp

from ..schemas.generator import GeneratorOutput, MathTask, PhysicsTask, Quantity
from ..verification import difficulty
from .base import GenerationSpec

X = sp.Symbol("x", real=True)


def _math(kind, expression, expected, statement, solution, **kw):
    task = MathTask(kind=kind, expression=expression, expected_answer=expected, **kw)
    return statement, solution, task


def _build_math(skill: str, k: int):
    """Return (statement, solution, MathTask) for a math skill at knob k."""
    if skill in ("derivative_rules", "tangent_line"):
        f = X ** (k + 1) + k * X
        d = sp.diff(f, X)
        verb = "Find the slope of the tangent line function" if skill == "tangent_line" else "Find the derivative"
        return _math("derivative", f"x**{k+1} + {k}*x", str(d),
                     f"{verb} of f(x) = x^{k+1} + {k}x with respect to x.",
                     f"f'(x) = {d}")
    if skill == "limits":
        a = k
        expr = f"(x**2 - {a*a})/(x - {a})"
        val = 2 * a
        return _math("limit", expr, str(val),
                     f"Evaluate the limit of (x^2 - {a*a})/(x - {a}) as x approaches {a}.",
                     f"Factor and cancel: limit = {val}.", point=float(a))
    if skill == "definite_integrals":
        b = 2
        val = sp.Rational(b ** (k + 1), k + 1)
        return _math("integral", f"x**{k}", str(val),
                     f"Evaluate the definite integral of x^{k} from 0 to {b}.",
                     f"By the FTC, the integral equals {val}.", interval=[0.0, float(b)])
    if skill == "optimization":
        # Critical point of f(x) = x^2 - 2k x  ->  f'(x) = 2x - 2k = 0  ->  x = k.
        return _math("solve_equation", f"2*x - {2*k} = 0", str(k),
                     f"A function has derivative f'(x) = 2x - {2*k}. Find the critical "
                     f"point where f'(x) = 0.",
                     f"Solve 2x - {2*k} = 0 to get x = {k}.")
    if skill == "trig_equations":
        # Domain-restricted to [0, pi/2] for a unique solution.
        return _math("solve_equation", "sin(x) = 1/2", "pi/6",
                     "Solve sin(x) = 1/2 for x on the interval [0, pi/2].",
                     "x = pi/6.", interval=[0.0, float(sp.pi / 2)])
    if skill == "exp_log_equations":
        c = k + 1
        return _math("solve_equation", f"exp(x) = {c}", f"log({c})",
                     f"Solve e^x = {c} for x. Express the answer exactly.",
                     f"x = ln({c}).")
    if skill == "trig_identities":
        return _math("simplify", f"sin(x)**2 + cos(x)**2 + {k}", str(1 + k),
                     f"Simplify sin^2(x) + cos^2(x) + {k}.",
                     f"Using the Pythagorean identity, the expression equals {1 + k}.")
    if skill == "vectors":
        a, b = 3, 4 * k
        mag = sp.sqrt(a * a + b * b)
        return _math("simplify", f"sqrt({a}**2 + {b}**2)", str(mag),
                     f"Find the magnitude of the vector <{a}, {b}>.",
                     f"|v| = sqrt({a}^2 + {b}^2) = {mag}.")
    if skill == "function_transformations":
        expr = sp.expand((X + k) ** 2)
        return _math("simplify", f"(x + {k})**2", str(expr),
                     f"Expand (x + {k})^2.",
                     f"(x + {k})^2 = {expr}.")
    raise ValueError(f"no math builder for skill {skill}")


def _build_physics(skill: str, context: dict):
    """Return (statement, solution, PhysicsTask) for a physics skill."""
    flavor = context.get("noun", "an object")
    if skill == "kinematics":
        givens = {"u": Quantity(value=5, unit="m/s"), "a": Quantity(value=2, unit="m/s**2"),
                  "t": Quantity(value=3, unit="s")}
        v = 5 + 2 * 3
        task = PhysicsTask(template="kinematics", givens=givens, unknown="v",
                           expected_answer=Quantity(value=v, unit="m/s"))
        st = (f"{flavor} starts at 5 m/s and accelerates at 2 m/s^2 for 3 s. "
              "Find its final velocity in m/s.")
        return st, f"v = u + at = 5 + 2(3) = {v} m/s.", task
    if skill == "newton_friction":
        givens = {"m": Quantity(value=10, unit="kg"), "F_applied": Quantity(value=50, unit="N"),
                  "mu": Quantity(value=0.2, unit="")}
        a = (50 - 0.2 * 10 * 9.8) / 10
        task = PhysicsTask(template="newton_friction", givens=givens, unknown="a",
                           expected_answer=Quantity(value=a, unit="m/s**2"))
        st = (f"A 10 kg {flavor} is pushed with 50 N across a surface with friction "
              "coefficient 0.2. Find its acceleration in m/s^2.")
        return st, f"a = (F - mu*m*g)/m = {a:.2f} m/s^2.", task
    if skill == "work_energy":
        givens = {"F": Quantity(value=20, unit="N"), "d": Quantity(value=4, unit="m")}
        w = 20 * 4
        task = PhysicsTask(template="work_energy", givens=givens, unknown="work",
                           expected_answer=Quantity(value=w, unit="J"))
        st = f"A constant 20 N force moves {flavor} 4 m in its direction. Find the work done in joules."
        return st, f"W = Fd = 20(4) = {w} J.", task
    if skill == "impulse_momentum":
        givens = {"F": Quantity(value=15, unit="N"), "t": Quantity(value=2, unit="s")}
        j = 15 * 2
        task = PhysicsTask(template="impulse_momentum", givens=givens, unknown="impulse",
                           expected_answer=Quantity(value=j, unit="N*s"))
        st = f"A 15 N force acts on {flavor} for 2 s. Find the impulse in N*s."
        return st, f"J = Ft = 15(2) = {j} N*s.", task
    if skill == "circular_motion":
        givens = {"m": Quantity(value=2, unit="kg"), "v": Quantity(value=4, unit="m/s"),
                  "r": Quantity(value=8, unit="m")}
        fc = 2 * 4 ** 2 / 8
        task = PhysicsTask(template="circular_motion", givens=givens, unknown="force",
                           expected_answer=Quantity(value=fc, unit="N"))
        st = (f"{flavor} of mass 2 kg moves in a circle of radius 8 m at 4 m/s. "
              "Find the centripetal force in newtons.")
        return st, f"F = mv^2/r = 2(16)/8 = {fc} N.", task
    raise ValueError(f"no physics builder for skill {skill}")


class MockProvider:
    name = "mock"

    def complete(self, prompt: str) -> str:
        # Only the semantic check uses complete(); the mock path of the semantic
        # check is heuristic and never calls this. Return a clear-rating default.
        return '{"ambiguity": 0.0, "feedback": "ok"}'

    def generate_problem(self, spec: GenerationSpec) -> GeneratorOutput:
        from ..content.skills import domain_of, Domain

        # Vary the knob with the number of prior failures so regeneration changes output.
        nudge = len(spec.failure_feedback)

        if domain_of(spec.skill) == Domain.PHYSICS:
            statement, solution, task = _build_physics(spec.skill, spec.context)
            target = difficulty.score(task)
        else:
            # Search a small family for a candidate that hits the target difficulty.
            chosen = None
            for k in range(1, 7):
                statement, solution, task = _build_math(spec.skill, k)
                if difficulty.score(task) == spec.difficulty_target:
                    chosen = (statement, solution, task, spec.difficulty_target)
                    break
            if chosen is None:
                k = 1 + (nudge % 5)
                statement, solution, task = _build_math(spec.skill, k)
                target = difficulty.score(task)
            else:
                statement, solution, task, target = chosen

        return GeneratorOutput(
            skill=spec.skill,
            difficulty_target=target,
            context_id=spec.context.get("id", ""),
            statement=statement,
            solution=solution,
            task=task,
        )
