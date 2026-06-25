"""OpenAI-compatible providers.

`OpenAICompatProvider` works against any OpenAI-compatible Chat Completions API.
Concrete providers just supply (name, api_key, base_url, model):
  - OpenAIProvider : GPT-5.2, or Llama via a compatible base URL.
  - GeminiProvider : Google Gemini via its OpenAI-compatible endpoint.
"""
from __future__ import annotations

from ..config import settings
from ..schemas.generator import GeneratorOutput
from .base import GenerationSpec
from .prompt import SYSTEM_INSTRUCTION, build_generation_prompt, parse_generator_output


class OpenAICompatProvider:
    """Base provider for any OpenAI-compatible Chat Completions endpoint."""

    name = "openai-compat"

    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        from openai import OpenAI  # lazy import; only needed for these providers

        kwargs = {"api_key": api_key or "unused"}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model

    def complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def generate_problem(self, spec: GenerationSpec) -> GeneratorOutput:
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": build_generation_prompt(spec)},
        ]
        try:
            resp = self._client.chat.completions.create(
                model=self._model, messages=messages, temperature=0.4,
                response_format={"type": "json_object"},
            )
        except Exception:
            # Some OpenAI-compatible servers (Ollama/vLLM/Gemini) reject
            # response_format. Retry without it; parse_generator_output still
            # extracts the JSON object from the reply.
            resp = self._client.chat.completions.create(
                model=self._model, messages=messages, temperature=0.4,
            )
        return parse_generator_output(resp.choices[0].message.content or "")


class OpenAIProvider(OpenAICompatProvider):
    name = "openai"

    def __init__(self) -> None:
        super().__init__(settings.openai_api_key, settings.openai_model, settings.openai_base_url)
