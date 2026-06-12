"""Anthropic provider (Claude)."""
from __future__ import annotations

from ..config import settings
from ..schemas.generator import GeneratorOutput
from .base import GenerationSpec
from .prompt import SYSTEM_INSTRUCTION, build_generation_prompt, parse_generator_output


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy import

        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def _message(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def complete(self, prompt: str) -> str:
        return self._message(system="", user=prompt)

    def generate_problem(self, spec: GenerationSpec) -> GeneratorOutput:
        raw = self._message(SYSTEM_INSTRUCTION, build_generation_prompt(spec))
        return parse_generator_output(raw)
