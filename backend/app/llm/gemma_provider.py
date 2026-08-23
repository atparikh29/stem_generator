"""Gemma served locally by Ollama (OpenAI-compatible endpoint).

Reuses the OpenAI Chat Completions machinery, pointed at Ollama's OpenAI-compatible
API (default http://localhost:11434/v1). This is a separate provider slot from the
`openai`/Llama arm, so Llama and Gemma can both be selected while Ollama serves
both. Set GEMMA_MODEL to the exact tag from `ollama list`. No API key needed.
"""
from __future__ import annotations

from ..config import settings
from .openai_provider import OpenAICompatProvider


class GemmaProvider(OpenAICompatProvider):
    name = "gemma"

    def __init__(self) -> None:
        super().__init__(settings.gemma_api_key or "ollama",
                         settings.gemma_model, settings.gemma_base_url)
