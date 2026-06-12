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

import random

import sympy as sp

from ..schemas.generator import GeneratorOutput, MathTask, PhysicsTask, Quantity
from ..verification import difficulty
from .base import GenerationSpec

X = sp.Symbol("x", real=True)
_R = random.Random()  # unseeded: each generation varies the numbers


def _math(kind, expression, expected, statement, solution, **kw):
    task = MathTask(kind=kind, expression=expression, expected_answer=expected, **kw)
    return statement, solution, task


def _build_math(skill: str, k: int):
    """Return (statement, solution, MathTask) for a math skill at knob k.

    The power/structure is governed by ``k`` (which sets difficulty); the free
    coefficients are randomized so repeated calls for the same skill produce
    different problems with correct, re-derived answers.
    """
    if skill in ("derivative_rules", "tangent_line"):
        c = _R.randint(1, 9)
        f = X ** (k + 1) + c * X
        d = sp.diff(f, X)
        verb = "Find the slope of the tangent line function" if skill == "tangent_line" else "Find the derivative"
        return _math("derivative", f"x**{k+1} + {c}*x", str(d),
                     f"{verb} of f(x) = x^{k+1} + {c}x with respect to x.",
                     f"f'(x) = {d}")
    if skill == "limits":
        a = _R.randint(1, 6)
        expr = f"(x**2 - {a*a})/(x - {a})"
        val = 2 * a
        return _math("limit", expr, str(val),
                     f"Evaluate the limit of (x^2 - {a*a})/(x - {a}) as x approaches {a}.",
                     f"Factor and cancel: limit = {val}.", point=float(a))
    if skill == "definite_integrals":
        b = _R.randint(2, 4)
        val = sp.Rational(b ** (k + 1), k + 1)
        return _math("integral", f"x**{k}", str(val),
                     f"Evaluate the definite integral of x^{k} from 0 to {b}.",
                     f"By the FTC, the integral equals {val}.", interval=[0.0, float(b)])
    if skill == "optimization":
        r = _R.randint(1, 9)  # critical point of f(x)=x^2-2r x  ->  f'(x)=2x-2r=0
        return _math("solve_equation", f"2*x - {2*r} = 0", str(r),
                     f"A function has derivative f'(x) = 2x - {2*r}. Find the critical "
                     f"point where f'(x) = 0.",
                     f"Solve 2x - {2*r} = 0 to get x = {r}.")
    if skill == "trig_equations":
        # Domain-restricted to [0, pi/2] for a unique solution.
        rhs, sol = _R.choice([("1/2", "pi/6"), ("sqrt(2)/2", "pi/4"), ("sqrt(3)/2", "pi/3")])
        return _math("solve_equation", f"sin(x) = {rhs}", sol,
                     f"Solve sin(x) = {rhs} for x on the interval [0, pi/2].",
                     f"x = {sol}.", interval=[0.0, float(sp.pi / 2)])
    if skill == "exp_log_equations":
        c = _R.randint(2, 9)
        return _math("solve_equation", f"exp(x) = {c}", f"log({c})",
                     f"Solve e^x = {c} for x. Express the answer exactly.",
                     f"x = ln({c}).")
    if skill == "trig_identities":
        c = _R.randint(0, 9)
        return _math("simplify", f"sin(x)**2 + cos(x)**2 + {c}", str(1 + c),
                     f"Simplify sin^2(x) + cos^2(x) + {c}.",
                     f"Using the Pythagorean identity, the expression equals {1 + c}.")
    if skill == "vectors":
        a, b = _R.randint(2, 8), _R.randint(2, 8)
        mag = sp.sqrt(a * a + b * b)
        return _math("simplify", f"sqrt({a}**2 + {b}**2)", str(mag),
                     f"Find the magnitude of the vector <{a}, {b}>.",
                     f"|v| = sqrt({a}^2 + {b}^2) = {mag}.")
    if skill == "function_transformations":
        c = _R.randint(1, 9)
        expr = sp.expand((X + c) ** 2)
        return _math("simplify", f"(x + {c})**2", str(expr),
                     f"Expand (x + {c})^2.",
                     f"(x + {c})^2 = {expr}.")
    raise ValueError(f"no math builder for skill {skill}")


def _build_physics(skill: str, context: dict):
    """Return (statement, solution, PhysicsTask) for a physics skill.

    Parameters are randomized within realistic ranges; answers are recomputed so
    they stay correct."""
    flavor = context.get("noun", "an object")
    if skill == "kinematics":
        u, a, t = _R.randint(0, 10), _R.randint(1, 5), _R.randint(2, 6)
        givens = {"u": Quantity(value=u, unit="m/s"), "a": Quantity(value=a, unit="m/s**2"),
                  "t": Quantity(value=t, unit="s")}
        v = u + a * t
        task = PhysicsTask(template="kinematics", givens=givens, unknown="v",
                           expected_answer=Quantity(value=v, unit="m/s"))
        st = (f"{flavor} starts at {u} m/s and accelerates at {a} m/s^2 for {t} s. "
              "Find its final velocity in m/s.")
        return st, f"v = u + at = {u} + {a}({t}) = {v} m/s.", task
    if skill == "newton_friction":
        m, mu = _R.randint(2, 20), _R.choice([0.1, 0.2, 0.3, 0.4])
        f_app = round(mu * m * 9.8 + _R.randint(5, 60))  # keep net force positive
        a = (f_app - mu * m * 9.8) / m
        givens = {"m": Quantity(value=m, unit="kg"), "F_applied": Quantity(value=f_app, unit="N"),
                  "mu": Quantity(value=mu, unit="")}
        task = PhysicsTask(template="newton_friction", givens=givens, unknown="a",
                           expected_answer=Quantity(value=a, unit="m/s**2"))
        st = (f"A {m} kg {flavor} is pushed with {f_app} N across a surface with friction "
              f"coefficient {mu}. Find its acceleration in m/s^2.")
        return st, f"a = (F - mu*m*g)/m = {a:.2f} m/s^2.", task
    if skill == "work_energy":
        f_, d = _R.randint(5, 50), _R.randint(1, 10)
        w = f_ * d
        givens = {"F": Quantity(value=f_, unit="N"), "d": Quantity(value=d, unit="m")}
        task = PhysicsTask(template="work_energy", givens=givens, unknown="work",
                           expected_answer=Quantity(value=w, unit="J"))
        st = f"A constant {f_} N force moves {flavor} {d} m in its direction. Find the work done in joules."
        return st, f"W = Fd = {f_}({d}) = {w} J.", task
    if skill == "impulse_momentum":
        f_, t = _R.randint(5, 40), _R.randint(1, 8)
        j = f_ * t
        givens = {"F": Quantity(value=f_, unit="N"), "t": Quantity(value=t, unit="s")}
        task = PhysicsTask(template="impulse_momentum", givens=givens, unknown="impulse",
                           expected_answer=Quantity(value=j, unit="N*s"))
        st = f"A {f_} N force acts on {flavor} for {t} s. Find the impulse in N*s."
        return st, f"J = Ft = {f_}({t}) = {j} N*s.", task
    if skill == "circular_motion":
        m, v, r = _R.randint(1, 5), _R.randint(2, 10), _R.randint(2, 15)
        fc = m * v ** 2 / r  # exact float; the verifier recomputes the same value
        givens = {"m": Quantity(value=m, unit="kg"), "v": Quantity(value=v, unit="m/s"),
                  "r": Quantity(value=r, unit="m")}
        task = PhysicsTask(template="circular_motion", givens=givens, unknown="force",
                           expected_answer=Quantity(value=fc, unit="N"))
        st = (f"{flavor} of mass {m} kg moves in a circle of radius {r} m at {v} m/s. "
              "Find the centripetal force in newtons.")
        return st, f"F = mv^2/r = {m}({v**2})/{r} = {fc:.2f} N.", task
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
            statement=statement,
            solution=solution,
            task=task,
        )
