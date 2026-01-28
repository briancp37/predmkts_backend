"""Structured logging configuration for CloudWatch compatibility."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from prediction_data.core.config import get_settings


def _get_json_processors() -> list[Processor]:
    """Get processors for JSON output format (production/CloudWatch)."""
    return [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ]


def _get_console_processors() -> list[Processor]:
    """Get processors for console output format (local development)."""
    return [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True),
    ]


def configure_logging(*, json_output: bool | None = None) -> None:
    """Configure structured logging for the application.

    Args:
        json_output: If True, use JSON format (CloudWatch compatible).
            If False, use console format (colored, human-readable).
            If None, auto-detect based on whether stdout is a TTY.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Auto-detect output format if not specified
    if json_output is None:
        json_output = not sys.stdout.isatty()

    # Select processors based on output format
    processors = _get_json_processors() if json_output else _get_console_processors()

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ],
            ),
            *processors,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to match
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A configured structlog BoundLogger instance.
    """
    return structlog.stdlib.get_logger(name)


def bind_context(
    *,
    platform: str | None = None,
    entity: str | None = None,
    run_id: str | None = None,
    dt: str | None = None,
    **kwargs: Any,
) -> None:
    """Bind context variables to all subsequent log messages in the current context.

    This uses structlog's contextvars to add fields that will appear in all
    log messages within the current async context or thread.

    Args:
        platform: The prediction market platform (e.g., "polymarket", "kalshi").
        entity: The entity type being processed (e.g., "markets", "events").
        run_id: Unique identifier for the current ingestion run.
        dt: The data timestamp in ISO format.
        **kwargs: Additional context fields to bind.
    """
    context: dict[str, Any] = {}

    if platform is not None:
        context["platform"] = platform
    if entity is not None:
        context["entity"] = entity
    if run_id is not None:
        context["run_id"] = run_id
    if dt is not None:
        context["dt"] = dt

    context.update(kwargs)

    if context:
        structlog.contextvars.bind_contextvars(**context)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()
