"""Context Selector, Section III.C.3.

Retrieves a thematic wrapper from the curated context library that matches the
student's interests. Personalization changes CONTEXT ONLY -- not skill or
difficulty. Physics skills use the context noun; math skills are theme-agnostic
but still record which context was selected.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "content" / "context_library.json"


@lru_cache(maxsize=1)
def _library() -> list[dict]:
    return json.loads(_LIBRARY_PATH.read_text())["contexts"]


def select(interests: list[str], skill: str) -> dict:
    contexts = _library()
    interest_set = {i.lower() for i in (interests or [])}
    # Best match: most overlapping interest tags; ties fall back to "generic".
    best = None
    best_overlap = 0
    for ctx in contexts:
        overlap = len(interest_set & {t.lower() for t in ctx.get("interest_tags", [])})
        if overlap > best_overlap:
            best, best_overlap = ctx, overlap
    if best is None:
        best = next((c for c in contexts if c["id"] == "generic"), contexts[0])
    return best
