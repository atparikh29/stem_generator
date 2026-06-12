"""Translation Record Schema (Appendix B).

Records the deterministic mapping from generator JSON to an executable
verification representation, so each verification is reproducible and auditable
independently of the LLM.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TranslationRecord(BaseModel):
    ok: bool
    method: str = ""            # solve_equation | derivative | ... | physics
    # Canonical, serialized symbolic forms (str(...) of the SymPy/pint objects).
    symbolic: dict[str, Any] = Field(default_factory=dict)
    error: str = ""             # populated when ok is False
