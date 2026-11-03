"""Application settings, loaded from environment / `.env` (TRD §8)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunables live here; nothing else in the codebase hard-codes limits, models or URLs."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"
    api_keys_sha256: str = ""

    gemini_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    llm_primary: str = "gemini"
    llm_fallback: str = "groq"
    llm_model_primary: str = ""
    llm_model_fallback: str = ""
    llm_budget_per_doc: int = Field(default=10, ge=0)
    llm_enabled: bool = True
    pii_redaction: bool = True

    max_upload_mb: int = Field(default=10, ge=1)
    max_batch_files: int = Field(default=20, ge=1)
    target_grade: int = Field(default=9, ge=1, le=18)
    rate_limit: str = "20/minute"
    cors_origins: str = ""
    mcp_allowed_dir: str = ""
    langsmith_tracing: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
