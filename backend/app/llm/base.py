"""LLM provider abstraction.

A `LLMProvider` exposes two methods:
  - `complete(prompt)`            -> free-form text (used by the semantic check)
  - `generate_problem(spec)`      -> a GeneratorOutput (strict JSON) candidate

The provider is selected by `settings.llm_provider`. The default `mock` provider
is fully deterministic and offline, so the whole pipeline (and the test suite)
runs without any API key. Real providers (OpenAI/GPT-5.2, Anthropic, or Llama via
an OpenAI-compatible endpoint) are used for the cross-model ablation.
"""
from __future__ import annotations

from typing import Protocol

from ..config import settings
from ..schemas.generator import GeneratorOutput


class GenerationSpec:
    """Everything the generator needs to draft one candidate problem."""

    def __init__(
        self,
        skill: str,
        difficulty_target: int,
        context: dict,
        failure_feedback: list[str] | None = None,
    ) -> None:
        self.skill = skill
        self.difficulty_target = difficulty_target
        self.context = context
        self.failure_feedback = failure_feedback or []


class LLMProvider(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...

    def generate_problem(self, spec: GenerationSpec) -> GeneratorOutput: ...


def get_provider() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "mock":
        from .mock import MockProvider

        return MockProvider()
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"unknown LLM_PROVIDER: {settings.llm_provider}")
