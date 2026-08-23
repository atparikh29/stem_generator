"""Application settings, loaded from environment / backend/.env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider: mock | openai | anthropic | gemini | deepseek
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

    # DeepSeek via its OpenAI-compatible endpoint.
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    database_url: str = "sqlite:///./stemgen.db"

    # Per-call LLM network budget. Bounds a stalled/rate-limited provider call
    # (e.g. the semantic clarity check's Gemini request) so it can't hang the
    # generation loop; without this the OpenAI client waits up to ~600s.
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2

    # ----- Rate limiting -----
    # Master switch for both directions (inbound HTTP and outbound provider calls).
    rate_limit_enabled: bool = True

    # Inbound: requests per minute allowed from one client, per route class.
    # `default` covers every /api route; the others additionally apply to their
    # own routes. Buckets are per client IP and per class, so chatty telemetry
    # can't eat the budget for an expensive generation.
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10      # login/register/forgot/reset (brute force)
    rate_limit_generate_per_minute: int = 12  # the LLM generate->verify loop

    # Identify clients by X-Forwarded-For instead of the socket peer. Only enable
    # behind a proxy you control: the header is client-supplied and otherwise
    # lets anyone mint a fresh bucket per request.
    rate_limit_trust_forwarded_for: bool = False

    # Outbound: how fast we may call a real LLM vendor, per provider. Keeps the
    # regeneration loop inside provider quotas. The mock provider is never paced.
    llm_rate_limit_per_minute: int = 30
    llm_max_concurrent_calls: int = 4
    # How long an outbound call may wait for a slot before giving up.
    llm_rate_limit_wait_seconds: float = 10.0

    # Verifier configuration
    semantic_ambiguity_threshold: float = 0.5
    max_regenerations: int = 5
    # Whether the semantic clarity check calls the LLM (a second request per
    # candidate) or uses the offline heuristic. Off avoids doubling provider
    # calls / rate-limit stalls, at the cost of the LLM-graded ambiguity signal.
    # The GUI "advanced" toggle can override this per generation.
    semantic_llm_check: bool = True
    # Allowed |observed - target| difficulty-bin gap. 0 = exact match (strict,
    # for the formal experiment); 1 is more forgiving for demos / weaker models.
    difficulty_tolerance: int = 0

    # Progress dashboard: "time spent" sums the gaps between consecutive events
    # in a session, but caps each gap so idle time (a tab left open) doesn't
    # inflate the total. A gap longer than this counts as this many seconds.
    active_gap_cap_seconds: int = 300  # 5 minutes

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
        # 2D / rotational templates, tuned to fill the previously-empty bins 4 & 5.
        "rotational_kinematics": (1.7, 5.7), "torque": (1.2, 5.2),
        "rotational_dynamics": (1.3, 5.3), "inclined_plane": (1.3, 5.3),
        "projectile_motion": (1.8, 5.8),
    }
    difficulty_phys_base: dict[str, float] = {
        "kinematics": 1.0, "impulse_momentum": 1.5, "work_energy": 2.0,
        "newton_friction": 2.5, "circular_motion": 3.0,
        "rotational_kinematics": 1.0, "torque": 1.5, "rotational_dynamics": 3.0,
        "inclined_plane": 3.0, "projectile_motion": 4.5,
    }


settings = Settings()
