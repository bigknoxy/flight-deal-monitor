"""Structured logging configuration using structlog.

Provides JSON-formatted logs for log aggregation (ELK, Grafana Loki) with:
- Correlation IDs to track request flow across services
- Request IDs on every log entry within an HTTP request
- Consistent fields: timestamp, level, message, + arbitrary context
- Dev-friendly console output when LOG_FORMAT=console (default in dev)
- Machine-parseable JSON output when LOG_FORMAT=json (for production)

Usage in any module:
    import structlog
    logger = structlog.get_logger()
    logger.info("flight_search_completed", origin="JFK", destination="LHR", results=5)
"""

import contextvars
import logging
import sys
import uuid
from typing import Any, Callable, Optional

import structlog


# Context variables for correlation / request tracking across async boundaries
correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def _add_context_vars(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Inject correlation_id and request_id from context vars into every log entry."""
    cid = correlation_id.get()
    if cid is not None:
        event_dict["correlation_id"] = cid

    rid = request_id.get()
    if rid is not None:
        event_dict["request_id"] = rid

    return event_dict


def _rename_event_to_message(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Rename structlog's 'event' key to 'message' for ELK/Loki compatibility."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _rename_logger_to_name(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Rename the 'logger' key (from stdlib add_logger_name) to 'name' for consistency."""
    if "_record" in event_dict:
        record: logging.LogRecord = event_dict["_record"]
        event_dict["name"] = record.name
    elif "logger" in event_dict:
        event_dict["name"] = event_dict.pop("logger")
    return event_dict


def _drop_colorama(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Drop colorama-related keys that leak into JSON output."""
    event_dict.pop("colorama", None)
    return event_dict


def _timestamp_in_iso8601(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Add an ISO-8601 timestamp field (replaces structlog's default epoch format)."""
    import datetime

    event_dict["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return event_dict


def _filter_stdlib_loggers(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Suppress noisy third-party loggers unless at WARNING+."""
    if "_record" in event_dict:
        record: logging.LogRecord = event_dict["_record"]
        noisy_loggers = {
            "httpx",
            "httpcore",
            "urllib3",
            "asyncio",
            "apscheduler",
            "sqlalchemy",
        }
        if record.name in noisy_loggers and record.levelno < logging.WARNING:
            raise structlog.DropEvent
    return event_dict


class CorrelationIDFilter(logging.Filter):
    """stdlib logging filter that injects correlation_id / request_id into LogRecords."""

    def filter(self, record: logging.LogRecord) -> bool:
        cid = correlation_id.get()
        rid = request_id.get()
        record.correlation_id = cid or ""  # type: ignore[attr-defined]
        record.request_id = rid or ""  # type: ignore[attr-defined]
        return True


def new_correlation_id() -> str:
    """Generate and set a new correlation ID in the context."""
    cid = uuid.uuid4().hex[:16]
    correlation_id.set(cid)
    return cid


def new_request_id() -> str:
    """Generate and set a new request ID in the context."""
    rid = uuid.uuid4().hex[:12]
    request_id.set(rid)
    return rid


def clear_context() -> None:
    """Reset correlation and request IDs (useful at request end)."""
    correlation_id.set(None)
    request_id.set(None)


# ── Shared processor chains ──────────────────────────────────────────────

_shared_processors: list[Callable] = [
    _add_context_vars,
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.stdlib.PositionalArgumentsFormatter(),
    _rename_event_to_message,
    _rename_logger_to_name,
    _filter_stdlib_loggers,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer(),
]


def configure_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """Configure structlog + stdlib logging.

    Args:
        log_level: Python logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: "json" for machine-parseable output, "console" for dev-friendly output.
    """
    is_json = log_format.lower() == "json"

    # 1. Configure structlog to wrap stdlib logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.contextvars.merge_contextvars,
            _add_context_vars,
            _rename_event_to_message,
            _rename_logger_to_name,
            _filter_stdlib_loggers,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.ExceptionRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 2. Configure the stdlib root logger with a ProcessorFormatter
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    handler.addFilter(CorrelationIDFilter())

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _rename_event_to_message,
            _timestamp_in_iso8601 if is_json else (lambda *a, **kw: a[2]),
            structlog.processors.JSONRenderer() if is_json else structlog.dev.ConsoleRenderer(),
        ],
        foreign_pre_chain=[
            _add_context_vars,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            _rename_event_to_message,
            _rename_logger_to_name,
            _filter_stdlib_loggers,
        ],
    )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Quiet down noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "apscheduler", "sqlalchemy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
