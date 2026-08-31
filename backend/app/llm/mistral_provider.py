"""Mistral-Nemo served locally by Ollama (OpenAI-compatible endpoint).

Reuses the OpenAI Chat Completions machinery, pointed at Ollama's OpenAI-compatible
API (default http://localhost:11434/v1). A separate provider slot so Mistral can be
selected alongside the other local models. Set MISTRAL_MODEL to the exact tag from
`ollama list`. No API key needed.
"""
from __future__ import annotations

from ..config import settings
from .openai_provider import OpenAICompatProvider


class MistralProvider(OpenAICompatProvider):
    name = "mistral"

    def __init__(self) -> None:
        super().__init__(settings.mistral_api_key or "ollama",
                         settings.mistral_model, settings.mistral_base_url)
