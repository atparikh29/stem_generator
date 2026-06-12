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

FEWSHOT = """Example (skill=derivative_rules, difficulty_target=2):
{"skill":"derivative_rules","difficulty_target":2,
"statement":"Find the derivative of f(x) = x^3 + 2x with respect to x.",
"solution":"f'(x) = 3x^2 + 2.",
"task":{"domain":"math","kind":"derivative","variable":"x",
"expression":"x**3 + 2*x","expected_answer":"3*x**2 + 2"}}
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
                       'unknown MUST be "ac" or "force". Keep v < 100 m/s and r a few meters.',
}

_MATH_SPEC = {
    "derivative": 'kind="derivative"; expression is a polynomial in x; expected_answer is its exact derivative.',
    "integral": 'kind="integral"; expression in x; interval=[a,b]; expected_answer is the definite integral value.',
    "limit": 'kind="limit"; expression in x; point=a; expected_answer is the limit value.',
    "solve_equation": 'kind="solve_equation"; expression is "lhs = rhs"; for periodic/trig add interval=[a,b] '
                      'so the solution is UNIQUE; expected_answer is that solution.',
    "simplify": 'kind="simplify"; expression and expected_answer are equivalent forms.',
}


def _task_spec(skill: str) -> str:
    if method_of(skill) == "physics":
        return _PHYSICS_SPEC.get(SKILLS[skill].get("template", ""), "")
    return _MATH_SPEC.get(method_of(skill), "")


def build_generation_prompt(spec: GenerationSpec) -> str:
    ctx = json.dumps(spec.context, ensure_ascii=False)
    feedback = ""
    if spec.failure_feedback:
        feedback = (
            "\nThe previous attempt was REJECTED for: "
            + ", ".join(spec.failure_feedback)
            + ". Fix exactly these issues and keep the same skill and difficulty."
        )
    return (
        f"{FEWSHOT}\n"
        f"Generate one problem.\n"
        f"skill = {spec.skill} (verification method: {method_of(spec.skill)})\n"
        f"TASK SPEC: {_task_spec(spec.skill)}\n"
        f"difficulty_target = {spec.difficulty_target}\n"
        f"context (wording/theme only) = {ctx}\n"
        "REQUIRED: the statement must contain EVERY numeric value and unit from "
        "givens (a student must be able to solve it from the statement alone), and "
        "end with a clear 'Find/Determine ...' instruction. expected_answer must be "
        "the correct, verifier-checkable answer."
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
