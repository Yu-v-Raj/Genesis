"""Project-wide Genesis logger."""

import logging

from backend.app.core.core_services.logging.config import configure_logger


logger: logging.Logger = configure_logger()
