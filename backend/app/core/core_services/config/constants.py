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
DEFAULT_EVENT_HISTORY_SIZE = 1000
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
# Next.js moves to the next free port (3001, 3002, ...) when 3000 is busy, so local
# development accepts any loopback port instead of failing with a CORS error.
LOCAL_DEVELOPMENT_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"
