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


def get_provider(override: str | None = None) -> LLMProvider:
    """Return the LLM provider. `override` (mock|openai|anthropic|gemini|deepseek|gemma)
    lets a request pick a model regardless of the .env default.

    Real providers come back wrapped in a rate limiter, because one request can
    fire up to `2 * (max_regenerations + 1)` vendor calls -- the inbound HTTP cap
    doesn't bound that. `mock` is returned bare so the offline pipeline and the
    test suite run at full speed.
    """
    provider = (override or settings.llm_provider).lower()
    if provider == "mock":
        from .mock import MockProvider

        return MockProvider()
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return _throttled(OpenAIProvider())
    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return _throttled(AnthropicProvider())
    if provider == "gemini":
        from .gemini_provider import GeminiProvider

        return _throttled(GeminiProvider())
    if provider == "deepseek":
        from .deepseek_provider import DeepSeekProvider

        return _throttled(DeepSeekProvider())
    if provider == "gemma":
        from .gemma_provider import GemmaProvider

        return _throttled(GemmaProvider())
    if provider == "gpt":
        from .gpt_provider import GptProvider

        return _throttled(GptProvider())
    if provider == "mistral":
        from .mistral_provider import MistralProvider

        return _throttled(MistralProvider())
    if provider == "deepseek_r1":
        from .deepseek_r1_provider import DeepSeekR1Provider

        return _throttled(DeepSeekR1Provider())
    raise ValueError(f"unknown LLM_PROVIDER: {settings.llm_provider}")


def _throttled(provider: LLMProvider) -> LLMProvider:
    from ..ratelimit import ThrottledProvider

    return ThrottledProvider(provider)
