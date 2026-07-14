"""Prompt construction + strict-JSON parsing for real LLM providers.

The generator is instructed to emit ONLY JSON validating against
`GeneratorOutput`. We never trust the model's math: the JSON `task` carries a
machine-checkable spec that the deterministic verifier re-derives independently.

All prompt TEXT (system instruction, per-skill specs/examples, rules) is editable
as data in `content/prompts.json`; only the assembly logic lives here.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ..content.skills import SKILLS, method_of
from ..schemas.generator import GeneratorOutput
from .base import GenerationSpec

_PROMPTS = json.loads((Path(__file__).resolve().parent.parent / "content" / "prompts.json").read_text())

SYSTEM_INSTRUCTION = _PROMPTS["system_instruction"]


def _task_spec(skill: str) -> str:
    if method_of(skill) == "physics":
        return _PROMPTS["physics_spec"].get(SKILLS[skill].get("template", ""), "")
    return _PROMPTS["math_spec"].get(method_of(skill), "")


def _example(skill: str) -> str:
    if method_of(skill) == "physics":
        tmpl = SKILLS[skill].get("template", "")
        return _PROMPTS["physics_example"].get(tmpl, _PROMPTS["physics_example"]["kinematics"])
    return _PROMPTS["math_example"].get(method_of(skill), _PROMPTS["math_example"]["derivative"])


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
    domain_rule = _PROMPTS["math_rules"] if is_math else _PROMPTS["physics_rule"]
    match_line = (
        "kind=" + method_of(spec.skill) if is_math
        else "domain=physics, template=" + SKILLS[spec.skill].get("template", "")
    )
    return (
        f"{_PROMPTS['example_intro']}\n{_example(spec.skill)}\n\n"
        f"Generate one problem.\n"
        f"skill = {spec.skill} (verification method: {method_of(spec.skill)})\n"
        f"The task MUST match this skill: {match_line}.\n"
        f"TASK SPEC: {_task_spec(spec.skill)}\n"
        f"{domain_rule}\n"
        f"difficulty_target = {spec.difficulty_target}\n"
        f"context (wording/theme only) = {ctx}\n"
        f"{_PROMPTS['required']}"
        f"{feedback}\n"
        f"{_PROMPTS['footer']}"
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
