"""Domain scope and skill taxonomy (Section IV of the design doc).

The taxonomy is **editable as data** in `skills.json` (skill_id -> domain,
verification method, and physics template). `method` is consumed by the
translation layer / verifier; physics skills additionally name a deterministic
formula template.

Editing skills.json can re-point an existing skill's domain/method/template. A
genuinely NEW skill still needs a verifier method + a mock builder (see
"Adding a skill" in CLAUDE.md) -- the taxonomy alone doesn't implement it.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

_SKILLS_PATH = Path(__file__).resolve().parent / "skills.json"


class Domain(str, Enum):
    PRECALCULUS = "precalculus"
    CALCULUS = "calculus"
    PHYSICS = "physics"


def _load() -> dict[str, dict]:
    raw = json.loads(_SKILLS_PATH.read_text())
    return {sid: {**meta, "domain": Domain(meta["domain"])} for sid, meta in raw.items()}


# skill_id -> metadata (domain as a Domain enum, matching the rest of the code).
SKILLS: dict[str, dict] = _load()


def all_skills() -> list[str]:
    return list(SKILLS.keys())


def domain_of(skill: str) -> Domain:
    return SKILLS[skill]["domain"]


def method_of(skill: str) -> str:
    return SKILLS[skill]["method"]
