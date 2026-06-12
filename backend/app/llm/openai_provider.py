"""OpenAI-compatible provider (GPT-5.2, or Llama via a compatible base URL)."""
from __future__ import annotations

from ..config import settings
from ..schemas.generator import GeneratorOutput
from .base import GenerationSpec
from .prompt import SYSTEM_INSTRUCTION, build_generation_prompt, parse_generator_output


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI  # lazy import; only needed for this provider

        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self._client = OpenAI(**kwargs)
        self._model = settings.openai_model

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
                model=self._model,
                messages=messages,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
        except Exception:
            # Some OpenAI-compatible servers (e.g. some Ollama/vLLM builds) reject
            # response_format. Retry without it; parse_generator_output still
            # extracts the JSON object from the reply.
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.4,
            )
        return parse_generator_output(resp.choices[0].message.content or "")
