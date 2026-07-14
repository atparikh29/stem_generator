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

    # Google Gemini via its OpenAI-compatible endpoint.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    database_url: str = "sqlite:///./stemgen.db"

    # Verifier configuration
    semantic_ambiguity_threshold: float = 0.5
    max_regenerations: int = 5
    # Allowed |observed - target| difficulty-bin gap. 0 = exact match (strict,
    # for the formal experiment); 1 is more forgiving for demos / weaker models.
    difficulty_tolerance: int = 0

    # Assessor (student model) tuning.
    assessor_alpha: float = 0.4           # EMA weight on the newest observation
    initial_mastery: float = 0.2          # cold-start mastery prior per skill
    misconception_threshold: float = 0.25  # below this mastery -> flagged as a gap

    # Difficulty scoring anchors. Each (lo, hi) is the raw-score range for a skill;
    # difficulty is binned 1..5 relative to it. Override via env as JSON, e.g.
    # DIFFICULTY_MATH_ANCHORS='{"derivative":[3,16]}'.
    difficulty_math_anchors: dict[str, tuple[float, float]] = {
        "derivative": (3.0, 14.0), "integral": (3.0, 9.0), "limit": (6.5, 11.0),
        "solve_equation": (2.5, 6.0), "simplify": (1.0, 13.5),
    }
    difficulty_phys_anchors: dict[str, tuple[float, float]] = {
        "kinematics": (2.0, 4.5), "newton_friction": (3.5, 6.0), "work_energy": (2.5, 5.0),
        "impulse_momentum": (2.0, 4.5), "circular_motion": (3.5, 6.5),
    }
    difficulty_phys_base: dict[str, float] = {
        "kinematics": 1.0, "impulse_momentum": 1.5, "work_energy": 2.0,
        "newton_friction": 2.5, "circular_motion": 3.0,
    }


settings = Settings()
