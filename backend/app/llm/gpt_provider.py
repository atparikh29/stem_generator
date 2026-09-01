"""GPT on OpenAI's own API.

A distinct provider slot from `openai` — this project points the `openai` slot at
a local Llama server (via OPENAI_BASE_URL), so GPT needs its own slot that talks to
api.openai.com. Reuses the OpenAI Chat Completions machinery with no base_url
override (defaulting to OpenAI). Needs a real OpenAI API key (GPT_API_KEY).
"""
from __future__ import annotations

from ..config import settings
from .openai_provider import OpenAICompatProvider


class GptProvider(OpenAICompatProvider):
    name = "gpt"

    def __init__(self) -> None:
        super().__init__(settings.gpt_api_key, settings.gpt_model, settings.gpt_base_url)
