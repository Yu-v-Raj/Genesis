"""Default values and filesystem locations for application configuration."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[5]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_APP_NAME = "Genesis"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_APP_DESCRIPTION = "An extensible Agent Operating System for autonomous AI applications."
DEFAULT_ENVIRONMENT = "development"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DATABASE_URL = "postgresql+asyncpg://localhost:5432/genesis"
