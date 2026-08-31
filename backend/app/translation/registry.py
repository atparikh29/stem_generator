"""Translation Layer (Section III.C.5).

Deterministically converts validated generator JSON into executable symbolic /
numeric representations. The LLM never parses mathematics: this registry is the
single, auditable bridge between natural-language-adjacent JSON and the solver.

Parsing is restricted to a known function/symbol allow-list so a malformed or
adversarial expression fails closed (raises) rather than executing anything.
"""
from __future__ import annotations

import re

import sympy as sp
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from ..schemas.generator import MathTask, PhysicsTask
from ..schemas.translation import TranslationRecord

_TRANSFORMS = standard_transformations + (implicit_multiplication_application,)

# Allow-list of names the parser may resolve. Everything else is rejected.
_ALLOWED_FUNCS: dict[str, object] = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "sec": sp.sec, "csc": sp.csc, "cot": sp.cot,
    "exp": sp.exp, "log": sp.log, "ln": sp.log, "sqrt": sp.sqrt,
    "Abs": sp.Abs, "abs": sp.Abs,
    "pi": sp.pi, "E": sp.E, "e": sp.E,
}


class TranslationError(ValueError):
    """Raised when JSON cannot be mapped to a verifiable symbolic form."""


# Function names the parser knows, longest first so we peel the longest match
# (e.g. prefer "asin" over its "sin" suffix).
_FUNC_NAMES = sorted(
    (k for k, v in _ALLOWED_FUNCS.items() if callable(v)),
    key=len,
    reverse=True,
)


def _disambiguate_funcs(expr: str) -> str:
    """Insert an explicit ``*`` where a variable is glued to a function call.

    SymPy's implicit-multiplication parser handles ``2*x*sin(4*x)`` and even
    ``2sin(x)``, but a bare variable fused to a function name — ``2xsin(4x)`` —
    is read as one symbol ``xsin`` and split into ``x*s*i*n``. Students write
    the fused form constantly (``2xsin(4x)``, ``x^2cos(x)``), so before parsing
    we split any maximal letter-run sitting directly before ``(`` into its
    variable prefix and trailing known function: ``xsin(`` -> ``x*sin(``. A run
    that is itself a known name (``sin``, ``asin``, ``log``) is left untouched.
    """

    def repl(match: re.Match[str]) -> str:
        run = match.group(0)
        if run in _ALLOWED_FUNCS:  # whole run is a function/const — leave it
            return run
        for fn in _FUNC_NAMES:
            if len(fn) < len(run) and run.endswith(fn):
                return f"{run[:-len(fn)]}*{fn}"
        return run

    return re.sub(r"[A-Za-z]+(?=\()", repl, expr)


def parse_math(expr: str, variable: str = "x") -> sp.Expr:
    """Parse a single expression using the restricted allow-list."""
    local = dict(_ALLOWED_FUNCS)
    local[variable] = sp.Symbol(variable, real=True)
    # Models often write "^" for exponentiation; in Python/SymPy that's XOR. No
    # STEM expression here means bitwise XOR, so normalize it to "**".
    expr = expr.replace("^", "**")
    expr = _disambiguate_funcs(expr)
    try:
        parsed = parse_expr(
            expr,
            local_dict=local,
            transformations=_TRANSFORMS,
            evaluate=True,
        )
    except (SyntaxError, TypeError, ValueError, AttributeError) as exc:
        raise TranslationError(f"cannot parse expression {expr!r}: {exc}") from exc

    # Reject anything that introduced a symbol outside {variable}.
    allowed_symbols = {sp.Symbol(variable, real=True), sp.Symbol(variable)}
    stray = set(parsed.free_symbols) - allowed_symbols
    if stray:
        raise TranslationError(f"unexpected free symbols {stray} in {expr!r}")
    return parsed


def parse_equation(expr: str, variable: str = "x") -> sp.Eq:
    if "=" not in expr:
        raise TranslationError(f"equation must contain '=': {expr!r}")
    lhs, rhs = expr.split("=", 1)
    return sp.Eq(parse_math(lhs, variable), parse_math(rhs, variable))


def parse_solution_set(expr: str, variable: str = "x") -> list[sp.Expr]:
    """Parse a comma-separated candidate solution set."""
    parts = [p.strip() for p in expr.split(",") if p.strip()]
    return [parse_math(p, variable) for p in parts]


def translate(task: MathTask | PhysicsTask) -> TranslationRecord:
    """Build a TranslationRecord, failing closed on any parse error."""
    try:
        if isinstance(task, MathTask):
            symbolic: dict = {"kind": task.kind, "variable": task.variable}
            if task.kind == "solve_equation":
                eq = parse_equation(task.expression, task.variable)
                symbolic["equation"] = str(eq)
                symbolic["expected"] = [str(s) for s in parse_solution_set(task.expected_answer, task.variable)]
            else:
                symbolic["expression"] = str(parse_math(task.expression, task.variable))
                symbolic["expected"] = str(parse_math(task.expected_answer, task.variable))
            return TranslationRecord(ok=True, method=task.kind, symbolic=symbolic)

        # PhysicsTask: validate units are parseable here; numeric solve happens
        # in the physics verifier.
        from .units import ureg  # local import to keep pint optional at import time

        symbolic = {"template": task.template, "unknown": task.unknown, "givens": {}}
        for name, q in task.givens.items():
            symbolic["givens"][name] = str((q.value * ureg(q.unit)) if q.unit else q.value)
        symbolic["expected"] = str(
            (task.expected_answer.value * ureg(task.expected_answer.unit))
            if task.expected_answer.unit
            else task.expected_answer.value
        )
        return TranslationRecord(ok=True, method="physics", symbolic=symbolic)

    except (TranslationError, Exception) as exc:  # noqa: BLE001 - fail closed
        return TranslationRecord(ok=False, error=str(exc))
