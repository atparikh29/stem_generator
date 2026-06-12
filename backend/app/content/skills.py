"""Domain scope and skill taxonomy (Section IV of the design doc).

Each skill belongs to a domain and maps to a verification *method* the
Translation Layer knows how to build. Physics skills additionally name a
deterministic formula template.
"""
from __future__ import annotations

from enum import Enum


class Domain(str, Enum):
    PRECALCULUS = "precalculus"
    CALCULUS = "calculus"
    PHYSICS = "physics"


# skill_id -> metadata. `method` is consumed by the translation layer / verifier.
SKILLS: dict[str, dict] = {
    # ----- Precalculus -----
    "trig_equations": {"domain": Domain.PRECALCULUS, "method": "solve_equation"},
    "trig_identities": {"domain": Domain.PRECALCULUS, "method": "simplify"},
    "exp_log_equations": {"domain": Domain.PRECALCULUS, "method": "solve_equation"},
    "vectors": {"domain": Domain.PRECALCULUS, "method": "simplify"},
    "function_transformations": {"domain": Domain.PRECALCULUS, "method": "simplify"},
    # ----- Single-variable Calculus -----
    "limits": {"domain": Domain.CALCULUS, "method": "limit"},
    "derivative_rules": {"domain": Domain.CALCULUS, "method": "derivative"},
    "tangent_line": {"domain": Domain.CALCULUS, "method": "derivative"},
    "optimization": {"domain": Domain.CALCULUS, "method": "solve_equation"},
    "definite_integrals": {"domain": Domain.CALCULUS, "method": "integral"},
    # ----- AP Physics 1 Mechanics -----
    "kinematics": {"domain": Domain.PHYSICS, "method": "physics", "template": "kinematics"},
    "newton_friction": {"domain": Domain.PHYSICS, "method": "physics", "template": "newton_friction"},
    "work_energy": {"domain": Domain.PHYSICS, "method": "physics", "template": "work_energy"},
    "impulse_momentum": {"domain": Domain.PHYSICS, "method": "physics", "template": "impulse_momentum"},
    "circular_motion": {"domain": Domain.PHYSICS, "method": "physics", "template": "circular_motion"},
}


def all_skills() -> list[str]:
    return list(SKILLS.keys())


def domain_of(skill: str) -> Domain:
    return SKILLS[skill]["domain"]


def method_of(skill: str) -> str:
    return SKILLS[skill]["method"]
