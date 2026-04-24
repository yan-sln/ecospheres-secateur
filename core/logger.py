# -*- coding: utf-8 -*-
"""QGIS-native logging configuration for the ecosphères‑secateur package.

This module configures a Python logger that forwards all messages to the
QGIS message log panel via QgsMessageLog. It is designed for QGIS plugins
and avoids console/file handlers in favor of native integration.

The logger is initialized once and can be imported safely across modules
without duplicating handlers.
"""

from __future__ import annotations

import logging
from typing import Final

from qgis.core import Qgis, QgsMessageLog  # type: ignore

# Public logger name (used across the plugin)
LOGGER_NAME: Final[str] = "secateur"

# Tag displayed in QGIS log panel (should match plugin name)
QGIS_TAG: Final[str] = "Secateur"


class QgisLogHandler(logging.Handler):
    """Logging handler that forwards records to QGIS."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the QGIS message log."""
        try:
            message: str = self.format(record)
            level: Qgis.MessageLevel = self._map_level(record.levelno)

            QgsMessageLog.logMessage(message, QGIS_TAG, level)
        except Exception:  # pragma: no cover
            # Avoid crashing QGIS logging on unexpected errors
            self.handleError(record)

    @staticmethod
    def _map_level(levelno: int) -> Qgis.MessageLevel:
        """Map Python logging levels to QGIS levels."""
        if levelno >= logging.ERROR:
            return Qgis.MessageLevel.Critical
        if levelno >= logging.WARNING:
            return Qgis.MessageLevel.Warning
        return Qgis.MessageLevel.Info


def setup_logger() -> logging.Logger:
    """Configure and return the package logger.

    The logger is configured only once. Subsequent calls return the same
    instance without adding duplicate handlers.
    """
    logger: logging.Logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler: logging.Handler = QgisLogHandler()
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.propagate = False

    return logger


# Module‑level logger
logger: logging.Logger = setup_logger()
