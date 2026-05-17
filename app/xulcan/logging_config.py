"""Logging configuration for the Xulcan framework.

Implement a declarative configuration pattern that strictly separates
configuration generation from execution. This module provides:

    - `get_logging_config`: Generate a standard Python logging configuration
      dictionary based on application settings.
    - `configure_structlog_wrapper`: Configure structlog's logger factory and
      processor chain.
    - Context management utilities via `structlog.contextvars` for structured
      metadata injection (e.g., correlation IDs).
"""

from typing import Any

import structlog
from structlog.types import Processor

from xulcan.config import Settings


# =============================================================================
# CONFIGURATION GENERATORS
# =============================================================================


def get_common_processors() -> list[Processor]:
    """Return the processor chain common to both JSON and console outputs.

    Execute before the final rendering step, handling context merging,
    log level injection, timestamp formatting, and exception serialization.

    Returns:
        list[Processor]: Ordered list of structlog processors.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def get_logging_config(settings: Settings) -> dict[str, Any]:
    """Generate a logging configuration dictionary for `logging.config.dictConfig`.

    Return a configuration that varies by environment: production/staging uses
    JSON output for log aggregation systems (Splunk, Datadog, ELK), while
    development uses colored console output for human readability.

    Note:
        This is a pure function that does not modify global state.

    Args:
        settings: Application settings containing LOG_LEVEL and ENVIRONMENT.

    Returns:
        dict[str, Any]: Configuration dictionary compatible with dictConfig.
    """
    log_level = settings.LOG_LEVEL.upper()
    is_production = settings.ENVIRONMENT.lower() in ("production", "staging")

    # Select renderer based on environment.
    # - Production: JSON for machine parsing.
    # - Development: Colored console for readability.
    if is_production:
        renderer = structlog.processors.JSONRenderer()
        formatter_class = "structlog.stdlib.ProcessorFormatter"
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        formatter_class = "structlog.stdlib.ProcessorFormatter"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": formatter_class,
                "processor": renderer,
                "foreign_pre_chain": get_common_processors(),
            },
        },
        "handlers": {
            "console": {
                "level": log_level,
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": True,
            },
            **{
                lib: {"level": "WARNING", "propagate": False}
                for lib in settings.LOGGING_NOISY_MODULES
            },
        },
    }


def configure_structlog_wrapper(settings: Settings) -> None:
    """Configure the structlog wrapper and processor chain.

    Build the processor pipeline by combining level filtering, common processors,
    and the formatter wrapper. Cache the logger on first use for performance.

    Args:
        settings: Application settings (reserved for future configuration).
    """
    structlog_processors = [
        structlog.stdlib.filter_by_level,
        *get_common_processors(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=structlog_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# =============================================================================
# LOGGER RETRIEVAL
# =============================================================================


def get_logger(name: str | None = None) -> Any:
    """Retrieve a configured structlog logger instance.

    Args:
        name: Optional logger name. If omitted, return the root logger.

    Returns:
        A bound structlog logger instance.
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()


# =============================================================================
# CONTEXT VARIABLE EXPORTS
# =============================================================================
# Expose structlog's context variable utilities for correlation ID management.

bind_contextvars = structlog.contextvars.bind_contextvars
unbind_contextvars = structlog.contextvars.unbind_contextvars
clear_contextvars = structlog.contextvars.clear_contextvars