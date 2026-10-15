"""Default values and filesystem locations for application configuration."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[5]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_APP_NAME = "Genesis"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_APP_DESCRIPTION = "An extensible Agent Operating System for autonomous AI applications."
DEFAULT_ENVIRONMENT = "development"
# Loopback only: Genesis has no authentication, so it must not listen on the network.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DATABASE_URL = "postgresql+asyncpg://localhost:5432/genesis"
DEFAULT_EVENT_HISTORY_SIZE = 1000
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
# The local frontend's exact origins: Next.js on 3000, or 3001 when 3000 is busy. Only
# these (and the backend's own origin) may make state-changing browser requests.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
)
# Host headers the backend answers. Anything else (e.g. a DNS-rebinding attacker's domain
# that resolves to 127.0.0.1) is refused. Ports are not part of the comparison.
DEFAULT_TRUSTED_HOSTS = ("localhost", "127.0.0.1", "[::1]")
