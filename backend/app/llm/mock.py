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

import math
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
        # k polynomial terms of increasing degree -> difficulty scales with k.
        f = sum(_R.randint(1, 5) * X ** (i + 1) for i in range(1, k + 1))
        d = sp.diff(f, X)
        verb = "Find the slope of the tangent line function" if skill == "tangent_line" else "Find the derivative"
        return _math("derivative", str(f), str(d),
                     f"{verb} of f(x) = {f} with respect to x.", f"f'(x) = {d}")
    if skill == "limits":
        # (x^n - a^n)/(x - a) -> limit n*a^(n-1); higher n scales difficulty.
        a, n = _R.randint(1, 5), k + 1
        f = (X ** n - a ** n) / (X - a)
        val = sp.limit(f, X, a)
        return _math("limit", str(f), str(val),
                     f"Evaluate the limit of ({sp.numer(sp.together(f))})/(x - {a}) as x approaches {a}.",
                     f"Factor and cancel: limit = {val}.", point=float(a))
    if skill == "definite_integrals":
        # Integrand = sum of k monomials (degrees 1..k) -> difficulty scales with k.
        f = sum(_R.randint(1, 5) * X ** i for i in range(1, k + 1))
        b = _R.randint(2, 3)
        val = sp.integrate(f, (X, 0, b))
        return _math("integral", str(f), str(val),
                     f"Evaluate the definite integral of {f} from 0 to {b}.",
                     f"By the FTC, the integral equals {val}.", interval=[0.0, float(b)])
    if skill == "optimization":
        # Critical point of a higher-degree f: f'(x) = a*x^p - a*r^p = 0. An ODD
        # power p keeps the real root unique (x = r); p scales difficulty.
        p = 1 if k == 1 else 3 if k <= 3 else 5
        r, a = _R.randint(1, 4), _R.randint(1, 3)
        lhs = f"{a}*x - {a*r}" if p == 1 else f"{a}*x**{p} - {a * r**p}"
        return _math("solve_equation", f"{lhs} = 0", str(r),
                     f"A function has derivative f'(x) = {lhs}. Find the critical "
                     f"point where f'(x) = 0.",
                     f"Solve {lhs} = 0 to get x = {r}.")
    if skill == "trig_equations":
        # Domain-restricted to [0, pi/2] for a unique solution.
        rhs, sol = _R.choice([("1/2", "pi/6"), ("sqrt(2)/2", "pi/4"), ("sqrt(3)/2", "pi/3")])
        return _math("solve_equation", f"sin(x) = {rhs}", sol,
                     f"Solve sin(x) = {rhs} for x on the interval [0, pi/2].",
                     f"x = {sol}.", interval=[0.0, float(sp.pi / 2)])
    if skill == "exp_log_equations":
        # a*exp(b*x) + d = C  ->  exp(b*x) = m  ->  x = ln(m)/b. The coefficient,
        # inner rate b, and offset d switch on with k so difficulty scales.
        a = 1 if k == 1 else _R.randint(2, 4)
        b = 1 if k <= 2 else 2
        d = 0 if k <= 3 else _R.randint(2, 6)
        m = _R.randint(2, 9)
        C = a * m + d
        expr = f"{a}*exp({b}*x) + {d} = {C}" if d else f"{a}*exp({b}*x) = {a*m}"
        ans = f"log({m})/{b}" if b > 1 else f"log({m})"
        return _math("solve_equation", expr, ans,
                     f"Solve {expr} for x. Express the answer exactly.", f"x = {ans}.")
    if skill == "trig_identities":
        # (sin^2 + cos^2)^k + c  -> simplifies to 1 + c; higher k scales difficulty.
        c = _R.randint(0, 5)
        f = (sp.sin(X) ** 2 + sp.cos(X) ** 2) ** k + c
        simplified = sp.simplify(f)
        return _math("simplify", str(f), str(simplified),
                     f"Simplify {f}.", f"Using sin^2+cos^2=1, the expression equals {simplified}.")
    if skill == "vectors":
        a, b = _R.randint(2, 8), _R.randint(2, 8)
        mag = sp.sqrt(a * a + b * b)
        return _math("simplify", f"sqrt({a}**2 + {b}**2)", str(mag),
                     f"Find the magnitude of the vector <{a}, {b}>.",
                     f"|v| = sqrt({a}^2 + {b}^2) = {mag}.")
    if skill == "function_transformations":
        # Expand (x + c)^(k+1); higher power -> more terms -> higher difficulty.
        c = _R.randint(1, 5)
        expr = sp.expand((X + c) ** (k + 1))
        return _math("simplify", f"(x + {c})**{k+1}", str(expr),
                     f"Expand (x + {c})^{k+1}.", f"(x + {c})^{k+1} = {expr}.")
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
    if skill == "rotational_kinematics":
        w0, al, t = _R.randint(0, 8), _R.randint(1, 5), _R.randint(2, 6)
        w = w0 + al * t
        givens = {"omega0": Quantity(value=w0, unit="rad/s"),
                  "alpha": Quantity(value=al, unit="rad/s**2"), "t": Quantity(value=t, unit="s")}
        task = PhysicsTask(template="rotational_kinematics", givens=givens, unknown="omega",
                           expected_answer=Quantity(value=w, unit="rad/s"))
        st = (f"A wheel spins at {w0} rad/s and angularly accelerates at {al} rad/s^2 for {t} s. "
              "Find its final angular velocity in rad/s.")
        return st, f"omega = omega0 + alpha*t = {w0} + {al}({t}) = {w} rad/s.", task
    if skill == "torque":
        r, f_ = _R.randint(1, 5), _R.randint(10, 50)
        theta = _R.choice([math.pi / 6, math.pi / 4, math.pi / 3])
        tau = r * f_ * math.sin(theta)
        givens = {"r": Quantity(value=r, unit="m"), "F": Quantity(value=f_, unit="N"),
                  "theta": Quantity(value=round(theta, 4), unit="rad")}
        task = PhysicsTask(template="torque", givens=givens, unknown="torque",
                           expected_answer=Quantity(value=r * f_ * math.sin(round(theta, 4)), unit="N*m"))
        st = (f"A {f_} N force acts at the end of a {r} m lever arm, at {round(theta,4)} rad to the arm. "
              "Find the torque in N*m.")
        return st, f"tau = r*F*sin(theta) = {r}*{f_}*sin({round(theta,4)}) = {tau:.2f} N*m.", task
    if skill == "rotational_dynamics":
        inertia, al = _R.randint(2, 10), _R.randint(1, 6)
        tau = inertia * al
        givens = {"I": Quantity(value=inertia, unit="kg*m**2"),
                  "alpha": Quantity(value=al, unit="rad/s**2")}
        task = PhysicsTask(template="rotational_dynamics", givens=givens, unknown="torque",
                           expected_answer=Quantity(value=tau, unit="N*m"))
        st = (f"A rigid body with moment of inertia {inertia} kg*m^2 has angular acceleration "
              f"{al} rad/s^2. Find the net torque in N*m.")
        return st, f"tau = I*alpha = {inertia}({al}) = {tau} N*m.", task
    if skill == "inclined_plane":
        theta = _R.choice([math.pi / 9, math.pi / 6, math.pi / 5])  # 20/30/36 deg
        mu = _R.choice([0.1, 0.2, 0.3])
        theta = round(theta, 4)
        a = 9.8 * (math.sin(theta) - mu * math.cos(theta))
        givens = {"theta": Quantity(value=theta, unit="rad"), "mu": Quantity(value=mu, unit="")}
        task = PhysicsTask(template="inclined_plane", givens=givens, unknown="a",
                           expected_answer=Quantity(value=a, unit="m/s**2"))
        st = (f"A block slides down a {theta} rad incline with friction coefficient {mu}. "
              "Find its acceleration in m/s^2 (g = 9.8 m/s^2).")
        return st, f"a = g(sin(theta) - mu*cos(theta)) = {a:.2f} m/s^2.", task
    if skill == "projectile_motion":
        v0 = _R.randint(10, 40)
        theta = round(_R.choice([math.pi / 6, math.pi / 4, math.pi / 3]), 4)
        rng = v0 ** 2 * math.sin(2 * theta) / 9.8
        givens = {"v0": Quantity(value=v0, unit="m/s"), "theta": Quantity(value=theta, unit="rad")}
        task = PhysicsTask(template="projectile_motion", givens=givens, unknown="range",
                           expected_answer=Quantity(value=rng, unit="m"))
        st = (f"{flavor} is launched at {v0} m/s at {theta} rad above the horizontal. "
              "Find its horizontal range in meters (g = 9.8 m/s^2).")
        return st, f"R = v0^2*sin(2*theta)/g = {rng:.2f} m.", task
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
            # Search the complexity ladder for a candidate that hits the target
            # difficulty (try a few random draws per knob for variety).
            chosen = None
            for k in range(1, 9):
                for _ in range(3):
                    statement, solution, task = _build_math(spec.skill, k)
                    if difficulty.score(task) == spec.difficulty_target:
                        chosen = (statement, solution, task, spec.difficulty_target)
                        break
                if chosen:
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
