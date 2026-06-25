"""Google Gemini via its OpenAI-compatible endpoint.

Reuses the OpenAI Chat Completions machinery (and the same prompt/parse path) by
pointing the OpenAI client at Google's compatibility base URL. Needs a Google AI
Studio API key (GEMINI_API_KEY).
"""
from __future__ import annotations

from ..config import settings
from .openai_provider import OpenAICompatProvider


class GeminiProvider(OpenAICompatProvider):
    name = "gemini"

    def __init__(self) -> None:
        super().__init__(settings.gemini_api_key, settings.gemini_model, settings.gemini_base_url)
