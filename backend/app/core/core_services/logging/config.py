"""Standard-library logging configuration for the Genesis backend."""

import json
import logging

from backend.app.core.core_services.config.settings import settings


LOGGER_NAME = "genesis"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
_HANDLER_MARKER = "_genesis_console_handler"


class StructuredFormatter(logging.Formatter):
    """Serialize Genesis log records into a stable JSON structure."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "genesis_context", None)
        if context:
            payload["context"] = context
        return json.dumps(payload, default=str)


def _resolve_log_level(log_level: str) -> int:
    """Translate a configured log-level name into its standard-library value."""
    resolved_level = logging.getLevelNamesMapping().get(log_level.upper())
    if not isinstance(resolved_level, int):
        raise ValueError(f"Unsupported LOG_LEVEL: {log_level}")
    return resolved_level


def configure_logger() -> logging.Logger:
    """Return the Genesis logger with exactly one managed console handler."""
    log_level = _resolve_log_level(settings.LOG_LEVEL)
    configured_logger = logging.getLogger(LOGGER_NAME)
    configured_logger.setLevel(log_level)
    configured_logger.propagate = False

    managed_handler = next(
        (
            handler
            for handler in configured_logger.handlers
            if getattr(handler, _HANDLER_MARKER, False)
        ),
        None,
    )
    if managed_handler is None:
        managed_handler = logging.StreamHandler()
        setattr(managed_handler, _HANDLER_MARKER, True)
        configured_logger.addHandler(managed_handler)

    managed_handler.setLevel(log_level)
    managed_handler.setFormatter(StructuredFormatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    return configured_logger
