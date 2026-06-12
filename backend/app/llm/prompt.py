"""Prompt construction + strict-JSON parsing for real LLM providers.

The generator is instructed to emit ONLY JSON validating against
`GeneratorOutput`. We never trust the model's math: the JSON `task` carries a
machine-checkable spec that the deterministic verifier re-derives independently.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from ..content.skills import SKILLS, method_of
from ..schemas.generator import GeneratorOutput
from .base import GenerationSpec

SYSTEM_INSTRUCTION = """You are a STEM problem generator for Precalculus, \
single-variable Calculus, and AP Physics 1 Mechanics. You output ONLY a single \
JSON object, no prose, no markdown fences. The JSON must validate against this \
schema:

{
  "skill": str,
  "difficulty_target": int (1-5),
  "statement": str,            # the problem shown to the student
  "solution": str,             # worked solution shown after answering
  "task": {                    # machine-checkable spec
    # MATH task:
    "domain": "math",
    "kind": "solve_equation"|"derivative"|"integral"|"limit"|"simplify",
    "variable": "x",
    "expression": str,         # use "lhs = rhs" for solve_equation
    "interval": [a, b] | null, # required for integral; domain for solve_equation
    "point": number | null,    # required for limit
    "expected_answer": str     # SymPy-parseable; comma-separated set for solve_equation
    # --- OR PHYSICS task: ---
    "domain": "physics",
    "template": "kinematics"|"newton_friction"|"work_energy"|"impulse_momentum"|"circular_motion",
    "givens": {name: {"value": number, "unit": str}},
    "unknown": str,
    "expected_answer": {"value": number, "unit": str}
  }
}

Rules:
- expected_answer MUST be the correct answer; it will be verified symbolically.
- Keep numbers physically realistic. Use SI units.
- Personalization affects ONLY the statement's wording/context, never the skill or difficulty.
"""

# Exact, verifier-aligned spec per physics template. Using these field names
# avoids needless rejection; computable unknowns avoid off-template questions.
_PHYSICS_SPEC = {
    "kinematics": 'givens keys MUST be from {"u","a","t","v","s"} (SI units m/s, m/s^2, s, m). '
                  'unknown MUST be one of "v","s","t","a". Typical: give u,a,t and ask for v.',
    "newton_friction": 'givens keys MUST be {"m","F_applied","mu"} (kg, N, dimensionless). '
                       'unknown MUST be "a" or "friction".',
    "work_energy": 'givens keys MUST be {"F","d"} (N, m) to find work, OR {"m","v"} (kg, m/s) to find ke. '
                   'unknown MUST be "work","ke", or "v".',
    "impulse_momentum": 'givens keys MUST be {"F","t"} (N, s) to find impulse, OR {"m","v"} (kg, m/s) to find momentum. '
                        'unknown MUST be "impulse","momentum", or "dv".',
    "circular_motion": 'givens keys MUST be {"v","r"} (m/s, m) to find ac, OR {"m","v","r"} to find force. '
                       'unknown MUST be "ac" or "force". Keep v < 100 m/s and r a few meters, and use an '
                       'everyday scenario that is realistic at those magnitudes (a ball on a string, a car '
                       'on a curved road, a stone in a sling) — NOT a satellite or planetary orbit.',
}

_MATH_SPEC = {
    "derivative": 'kind="derivative"; expression is a polynomial in x; expected_answer is its exact derivative.',
    "integral": 'kind="integral"; expression in x; interval=[a,b]; expected_answer is the definite integral value.',
    "limit": 'kind="limit"; expression in x; point=a; expected_answer is the limit value.',
    "solve_equation": 'kind="solve_equation"; expression is "lhs = rhs"; for periodic/trig add interval=[a,b] '
                      'so the solution is UNIQUE; expected_answer is that solution.',
    "simplify": 'kind="simplify"; expression and expected_answer are equivalent forms.',
}


# A concrete, valid example per verification method/template, so the model has a
# correct anchor for the exact skill (not just a generic one).
_MATH_EXAMPLE = {
    "derivative": '{"skill":"derivative_rules","difficulty_target":2,"statement":"Find the derivative of '
                  'f(x) = x^3 + 2x with respect to x.","solution":"3x^2 + 2.","task":{"domain":"math",'
                  '"kind":"derivative","variable":"x","expression":"x**3 + 2*x","expected_answer":"3*x**2 + 2"}}',
    "limit": '{"skill":"limits","difficulty_target":2,"statement":"Evaluate the limit of (x^2 - 9)/(x - 3) as x '
             'approaches 3.","solution":"Factor and cancel: 6.","task":{"domain":"math","kind":"limit",'
             '"variable":"x","expression":"(x**2 - 9)/(x - 3)","point":3,"expected_answer":"6"}}',
    "integral": '{"skill":"definite_integrals","difficulty_target":2,"statement":"Evaluate the definite integral '
                'of x^2 from 0 to 2.","solution":"8/3.","task":{"domain":"math","kind":"integral","variable":"x",'
                '"expression":"x**2","interval":[0,2],"expected_answer":"8/3"}}',
    "solve_equation": '{"skill":"trig_equations","difficulty_target":2,"statement":"Solve sin(x) = 1/2 for x on '
                      '[0, pi/2].","solution":"pi/6.","task":{"domain":"math","kind":"solve_equation","variable":"x",'
                      '"expression":"sin(x) = 1/2","interval":[0,1.5708],"expected_answer":"pi/6"}}',
    "simplify": '{"skill":"trig_identities","difficulty_target":2,"statement":"Simplify sin^2(x) + cos^2(x).",'
                '"solution":"1.","task":{"domain":"math","kind":"simplify","variable":"x",'
                '"expression":"sin(x)**2 + cos(x)**2","expected_answer":"1"}}',
}

_PHYSICS_EXAMPLE = {
    "kinematics": '{"skill":"kinematics","difficulty_target":2,"statement":"A cart starts at 5 m/s and accelerates '
                  'at 2 m/s^2 for 3 s. Find its final velocity.","solution":"11 m/s.","task":{"domain":"physics",'
                  '"template":"kinematics","givens":{"u":{"value":5,"unit":"m/s"},"a":{"value":2,"unit":"m/s**2"},'
                  '"t":{"value":3,"unit":"s"}},"unknown":"v","expected_answer":{"value":11,"unit":"m/s"}}}',
    "circular_motion": '{"skill":"circular_motion","difficulty_target":3,"statement":"A 2 kg ball on a string moves '
                       'in a circle of radius 4 m at 6 m/s. Find the centripetal force.","solution":"18 N.","task":'
                       '{"domain":"physics","template":"circular_motion","givens":{"m":{"value":2,"unit":"kg"},'
                       '"v":{"value":6,"unit":"m/s"},"r":{"value":4,"unit":"m"}},"unknown":"force",'
                       '"expected_answer":{"value":18,"unit":"N"}}}',
}

# Hard constraints for math expressions (the common failure mode for weak models).
_MATH_RULES = (
    "MATH RULES: the expression must be a CONCRETE elementary function of the single "
    "variable ONLY (e.g. polynomials, sin/cos/exp/log). Do NOT use undefined functions "
    "like v(x) or f(x), do NOT introduce other letters (no h, s, t unless it is the "
    "variable), and do NOT put '=' in a non-equation expression. This is a pure-math "
    "problem — do NOT turn it into a physics word problem about motion/forces."
)


def _task_spec(skill: str) -> str:
    if method_of(skill) == "physics":
        return _PHYSICS_SPEC.get(SKILLS[skill].get("template", ""), "")
    return _MATH_SPEC.get(method_of(skill), "")


def _example(skill: str) -> str:
    if method_of(skill) == "physics":
        tmpl = SKILLS[skill].get("template", "")
        return _PHYSICS_EXAMPLE.get(tmpl, _PHYSICS_EXAMPLE["kinematics"])
    return _MATH_EXAMPLE.get(method_of(skill), _MATH_EXAMPLE["derivative"])


def build_generation_prompt(spec: GenerationSpec) -> str:
    ctx = json.dumps(spec.context, ensure_ascii=False)
    feedback = ""
    if spec.failure_feedback:
        feedback = (
            "\nThe previous attempt was REJECTED for: "
            + ", ".join(spec.failure_feedback)
            + ". Fix exactly these issues and keep the same skill and difficulty."
        )
    is_math = method_of(spec.skill) != "physics"
    domain_rule = (
        _MATH_RULES if is_math
        else "PHYSICS RULE: task.domain MUST be \"physics\" with the template below."
    )
    return (
        f"Example for this exact skill:\n{_example(spec.skill)}\n\n"
        f"Generate one problem.\n"
        f"skill = {spec.skill} (verification method: {method_of(spec.skill)})\n"
        f"The task MUST match this skill: "
        f"{'kind=' + method_of(spec.skill) if is_math else 'domain=physics, template=' + SKILLS[spec.skill].get('template','')}.\n"
        f"TASK SPEC: {_task_spec(spec.skill)}\n"
        f"{domain_rule}\n"
        f"difficulty_target = {spec.difficulty_target}\n"
        f"context (wording/theme only) = {ctx}\n"
        "REQUIRED: the statement must contain EVERY numeric value and unit from "
        "givens (a student must be able to solve it from the statement alone), and "
        "end with a clear 'Find/Determine ...' instruction. expected_answer must be "
        "the correct, verifier-checkable answer. Choose a physically PLAUSIBLE "
        "real-world scenario for the given magnitudes; if the context theme would be "
        "unrealistic for these numbers, ignore the theme and pick a sensible one."
        f"{feedback}\n"
        "Return ONLY the JSON object."
    )


def parse_generator_output(raw: str) -> GeneratorOutput:
    """Extract and validate JSON. Raises ValueError on invalid -> json_invalid."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    try:
        data = json.loads(raw[start : end + 1])
        return GeneratorOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid generator JSON: {exc}") from exc
