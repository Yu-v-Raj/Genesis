"""Structured logging service that also emits observability events."""

import logging
from collections.abc import Mapping

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.logging.logger import logger as standard_logger
from backend.app.core.observability.domain.events import LogCreated


class LoggerService:
    """Write structured log records and publish corresponding ``LogCreated`` events."""

    def __init__(self, event_bus: EventBus, logger: logging.Logger | None = None) -> None:
        self._event_bus = event_bus
        self._logger = logger if logger is not None else standard_logger

    async def debug(self, message: str, *, source: str = "genesis", **context: object) -> None:
        """Write a DEBUG log record and publish its event."""
        await self._log(logging.DEBUG, message, source, context)

    async def info(self, message: str, *, source: str = "genesis", **context: object) -> None:
        """Write an INFO log record and publish its event."""
        await self._log(logging.INFO, message, source, context)

    async def warning(self, message: str, *, source: str = "genesis", **context: object) -> None:
        """Write a WARNING log record and publish its event."""
        await self._log(logging.WARNING, message, source, context)

    async def error(self, message: str, *, source: str = "genesis", **context: object) -> None:
        """Write an ERROR log record and publish its event."""
        await self._log(logging.ERROR, message, source, context)

    async def critical(self, message: str, *, source: str = "genesis", **context: object) -> None:
        """Write a CRITICAL log record and publish its event."""
        await self._log(logging.CRITICAL, message, source, context)

    async def _log(
        self,
        level: int,
        message: str,
        source: str,
        context: Mapping[str, object],
    ) -> None:
        self._logger.log(level, message, extra={"genesis_context": dict(context)})
        await self._event_bus.publish(
            LogCreated(
                source=source,
                payload={
                    "level": logging.getLevelName(level),
                    "message": message,
                    "context": dict(context),
                },
            )
        )
