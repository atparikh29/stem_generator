"""DeepSeek-R1 (reasoning model) served locally by Ollama.

Reuses the OpenAI Chat Completions machinery, pointed at Ollama's OpenAI-compatible
API. R1 emits a <think>...</think> reasoning preamble before its answer;
`parse_generator_output` strips that block before extracting the JSON object, so
the reasoning tokens don't poison JSON parsing. Set DEEPSEEK_R1_MODEL to the exact
tag from `ollama list` (e.g. deepseek-r1:14b). No API key needed.

Distinct from the cloud `deepseek` provider (DeepSeek-V3 via api.deepseek.com).
"""
from __future__ import annotations

from ..config import settings
from .openai_provider import OpenAICompatProvider


class DeepSeekR1Provider(OpenAICompatProvider):
    name = "deepseek_r1"

    def __init__(self) -> None:
        super().__init__(settings.deepseek_r1_api_key or "ollama",
                         settings.deepseek_r1_model, settings.deepseek_r1_base_url)
