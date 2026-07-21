"""Typed application settings loaded from the project-root .env file."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core.core_services.config.constants import (
    DEFAULT_APP_DESCRIPTION,
    DEFAULT_APP_NAME,
    DEFAULT_APP_VERSION,
    DEFAULT_DATABASE_URL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    ENV_FILE,
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
    DATABASE_URL: str = DEFAULT_DATABASE_URL
    OPENAI_API_KEY: SecretStr | None = None
    ANTHROPIC_API_KEY: SecretStr | None = None


settings = Settings()
