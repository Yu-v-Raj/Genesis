"""Typed application settings loaded from the project-root .env file."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from backend.app.core.core_services.config.constants import (
    DEFAULT_APP_DESCRIPTION,
    DEFAULT_APP_NAME,
    DEFAULT_APP_VERSION,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_DATABASE_URL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_EVENT_HISTORY_SIZE,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    ENV_FILE,
    LOCAL_DEVELOPMENT_ORIGIN_REGEX,
    PROJECT_ROOT,
)


class Settings(BaseSettings):
    """Runtime configuration for the Genesis backend service."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = DEFAULT_APP_NAME
    APP_VERSION: str = DEFAULT_APP_VERSION
    APP_DESCRIPTION: str = DEFAULT_APP_DESCRIPTION
    ENVIRONMENT: str = DEFAULT_ENVIRONMENT
    HOST: str = DEFAULT_HOST
    PORT: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    LOG_LEVEL: str = DEFAULT_LOG_LEVEL
    EVENT_HISTORY_SIZE: int = Field(default=DEFAULT_EVENT_HISTORY_SIZE, ge=1)
    HEARTBEAT_INTERVAL_SECONDS: float = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        gt=0,
    )
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    DATABASE_URL: str = DEFAULT_DATABASE_URL
    # Durable work (v0.12): how long a worker's claim on a task lasts without renewal, and
    # how many executions / workflow runs one process works on at once.
    WORKER_LEASE_SECONDS: float = Field(default=30.0, gt=0)
    WORKER_CONCURRENCY: int = Field(default=4, ge=1)
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    ANTHROPIC_API_KEY: SecretStr | None = None

    @field_validator("DATABASE_URL")
    @classmethod
    def _anchor_relative_sqlite_path(cls, value: str) -> str:
        """Resolve relative SQLite paths against the project root, not the working directory.

        ``sqlite+aiosqlite:///./genesis.db`` would otherwise point at a different file for
        uvicorn, Alembic, and scripts started from different directories.
        """
        try:
            url = make_url(value)
        except Exception:
            return value
        database = url.database
        if url.get_backend_name() != "sqlite" or not database or database == ":memory:":
            return value
        if database.startswith("file:") or Path(database).is_absolute():
            return value
        return url.set(database=str((PROJECT_ROOT / database).resolve())).render_as_string(
            hide_password=False
        )

    @property
    def cors_origin_regex(self) -> str | None:
        """Allow any loopback frontend port only while developing locally."""
        return LOCAL_DEVELOPMENT_ORIGIN_REGEX if self.ENVIRONMENT == "development" else None


settings = Settings()
