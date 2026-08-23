"""DeepSeek via its OpenAI-compatible endpoint.

Reuses the OpenAI Chat Completions machinery (and the same prompt/parse path) by
pointing the OpenAI client at DeepSeek's API. Needs a DeepSeek API key
(DEEPSEEK_API_KEY). Default model `deepseek-chat` (DeepSeek-V3).
"""
from __future__ import annotations

from ..config import settings
from .openai_provider import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"

    def __init__(self) -> None:
        super().__init__(settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_base_url)
