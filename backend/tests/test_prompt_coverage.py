"""Guard: every skill's generation prompt must actually describe its own task.

The physics templates rotational_*/torque/inclined_plane/projectile_motion were
added with a mock builder + verifier but no prompt spec/example, so the model was
handed a blank TASK SPEC and a *kinematics* example while being asked for a
different template — and failed ~every generation. These tests make that class of
omission fail loudly instead of silently tanking a skill's validity.
"""
from app.content.skills import SKILLS, all_skills, method_of
from app.llm.prompt import _PROMPTS, _example, _task_spec, parse_generator_output
from app.llm.mock import MockProvider
from app.verification import engine

_KINEMATICS_FALLBACK = _PROMPTS["physics_example"]["kinematics"]
_DERIVATIVE_FALLBACK = _PROMPTS["math_example"]["derivative"]


def test_every_skill_has_a_nonempty_task_spec():
    missing = [s for s in all_skills() if not _task_spec(s).strip()]
    assert not missing, f"skills with a blank TASK SPEC in the prompt: {missing}"


def test_every_physics_template_has_its_own_example():
    # A physics skill must not fall back to the kinematics example (kinematics aside).
    bad = [s for s in all_skills()
           if method_of(s) == "physics" and s != "kinematics"
           and _example(s) == _KINEMATICS_FALLBACK]
    assert not bad, f"physics skills falling back to the kinematics example: {bad}"


def test_every_math_method_has_its_own_example():
    bad = [s for s in all_skills()
           if method_of(s) != "physics" and method_of(s) != "derivative"
           and _example(s) == _DERIVATIVE_FALLBACK]
    assert not bad, f"math skills falling back to the derivative example: {bad}"


def test_prompt_examples_are_self_consistent_and_verify():
    # Each shipped example must itself pass the verifier — a broken example would
    # teach the model to produce rejected problems.
    mp = MockProvider()
    for tmpl, ex in _PROMPTS["physics_example"].items():
        cand = parse_generator_output(ex)
        assert cand.task.template == tmpl, f"{tmpl} example declares template {cand.task.template}"
        rep = engine.verify(cand, mp, use_llm_semantic=False)
        assert rep.accepted, f"physics example for {tmpl} fails verification: {rep.failure_reasons}"


def test_math_examples_verify():
    # Every math example (per-method and per-skill) must itself verify.
    mp = MockProvider()
    for key, ex in _PROMPTS["math_example"].items():
        cand = parse_generator_output(ex)
        rep = engine.verify(cand, mp, use_llm_semantic=False)
        assert rep.accepted, f"math example '{key}' fails verification: {rep.failure_reasons}"


def test_skills_needing_their_own_example_have_one():
    # These skills' word-problem framing differs from a bare method, so they must
    # not fall back to a sibling skill's example (regression guard for the audit).
    import json
    for sk in ("optimization", "exp_log_equations", "function_transformations"):
        ex = json.loads(_example(sk))
        assert ex["skill"] == sk, f"{sk} is being taught with the {ex['skill']} example"
