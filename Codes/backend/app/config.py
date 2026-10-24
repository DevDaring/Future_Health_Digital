"""Application settings, read from environment variables (and `.env` if present).

Every tunable that a judge or clinician might want to see lives here or in a YAML
fixture, never as a magic number inside business logic.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class Settings(BaseSettings):
    """Typed settings. Unknown keys in `.env` are ignored on purpose, so one env file can
    serve several tools."""

    model_config = SettingsConfigDict(
        # Later files win: repo `.env` (from .env.example), then a private backend/.env.local.
        env_file=(
            os.environ.get("WASL_ENV_FILE", str(REPO_DIR / ".env")),
            str(BACKEND_DIR / ".env.local"),
        ),
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+psycopg://wasl:wasl@localhost:5441/wasl"
    jwt_secret: str = "change-me"
    jwt_expiry_minutes: int = 12 * 60
    demo_mode: bool = True
    seed: int = 42
    population_size: int = 5000
    daily_outreach_budget: int = 200
    public_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    artifacts_dir: str = str(BACKEND_DIR / "artifacts")
    docs_dir: str = str(REPO_DIR / "docs")
    scheduler_enabled: bool = True

    # LLM -------------------------------------------------------------------------
    llm_provider: str = "mock"  # mock | anthropic | nanogpt | linkapi | relay | azure_openai
    llm_model: str = "claude-opus-5-5"
    anthropic_api_key: str = ""
    # OpenAI-compatible relays (NanoGPT, LinkAPI). Tried in order by the `relay` provider.
    nanogpt_api_key: str = ""
    nanogpt_base_url: str = "https://nano-gpt.com/api/v1"
    nanogpt_model: str = "anthropic/claude-haiku-5.5"
    linkapi_api_key: str = ""
    linkapi_base_url: str = "https://api.linkapi.ai/v1"
    linkapi_model: str = "gemini-3-flash-preview"
    llm_timeout_s: float = 40.0
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""

    translation_pass_threshold: float = 0.85
    sla_days_urgent: int = 7
    sla_days_high: int = 21
    sla_days_routine: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def sla_days(self, severity: str) -> int:
        return {"urgent": self.sla_days_urgent, "high": self.sla_days_high}.get(
            severity, self.sla_days_routine
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
