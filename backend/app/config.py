"""Application settings, loaded from environment / backend/.env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider: mock | openai | anthropic
    llm_provider: str = "mock"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.2"
    openai_base_url: str = ""  # set for Llama via an OpenAI-compatible server

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    database_url: str = "sqlite:///./stemgen.db"

    # Verifier configuration
    semantic_ambiguity_threshold: float = 0.5
    max_regenerations: int = 5
    # Allowed |observed - target| difficulty-bin gap. 0 = exact match (strict,
    # for the formal experiment); 1 is more forgiving for demos / weaker models.
    difficulty_tolerance: int = 0


settings = Settings()
