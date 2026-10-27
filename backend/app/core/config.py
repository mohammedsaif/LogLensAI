"""Runtime configuration loaded from environment variables (12-factor)."""

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LogLens AI"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "sqlite:///./loglens.db"
    # NoDecode: accept plain comma-separated env values instead of requiring JSON lists.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:8080", "http://127.0.0.1:5173"]
    )

    # Upload limits
    max_upload_mb: float = 10.0
    max_lines: int = 200_000
    allowed_extensions: Annotated[list[str], NoDecode] = Field(default_factory=lambda: [".log", ".txt", ".jsonl"])

    # Detection tuning
    rare_max_count: int = 3
    threshold_percent: int = 80
    burst_min_count: int = 10

    # Evidence / AI
    ai_provider: Literal["mock", "anthropic", "openai", "gemini", "ollama", "disabled"] = "mock"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    anthropic_server_fallbacks: bool = True
    # OpenAI or any OpenAI-compatible server (set OPENAI_BASE_URL for Groq, OpenRouter, LM Studio, vLLM, ...).
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    openai_response_format: Literal["json_schema", "json_object"] = "json_schema"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    # Local models: nothing leaves your machine/network.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_num_ctx: int = 16384
    ai_timeout_seconds: float = 45.0
    ai_max_retries: int = 2
    ai_backoff_seconds: float = 0.5
    ai_max_output_tokens: int = 4000
    evidence_token_budget: int = 6000
    evidence_max_items: int = 25
    redact_ip_addresses: bool = True

    retention_days: int = 30

    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()
