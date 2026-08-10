"""Structured JSON logging for quant_stickynote service.

Uses structlog for structured logging with JSON output.
All logs include:
- timestamp (ISO format)
- level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- service name
- message and context variables

Configuration based on LOG_LEVEL environment variable.

Usage:
    from logger import get_logger
    
    log = get_logger(__name__)
    log.info("query_executed", query_id="momentum_001", signals=5, duration_ms=250)
    
    # Output:
    # {"timestamp": "2026-08-10T14:30:45.123Z", "level": "info", "message": "query_executed",
    #  "service": "quant_stickynote", "query_id": "momentum_001", "signals": 5, "duration_ms": 250}
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import settings


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging.
    
    Each log record becomes a JSON object with:
    - timestamp: ISO format timestamp
    - level: Log level (lowercase)
    - service: Service name from config
    - logger: Logger name (module name)
    - message: Log message
    - Additional fields from context
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string.
        
        Args:
            record: LogRecord from logging module
            
        Returns:
            JSON string with all log information
        """
        # Build log dictionary
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname.lower(),
            "service": settings.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from LogRecord.__dict__
        # These are set via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            }:
                log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_data)


class StructuredLogger:
    """Wraps stdlib Logger to accept keyword arguments as structured fields.

    Allows: log.info("msg", query_id="x", duration_ms=50)
    instead of: log.info("msg", extra={"query_id": "x", "duration_ms": 50})
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _emit(self, level: int, msg: str, **kwargs) -> None:
        exc_info = kwargs.pop("exc_info", None)
        stacklevel = kwargs.pop("stacklevel", 2)
        self._logger.log(level, msg, extra=kwargs, exc_info=exc_info, stacklevel=stacklevel)

    def debug(self, msg: str, **kwargs) -> None:
        self._emit(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._emit(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._emit(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._emit(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs) -> None:
        self._emit(logging.CRITICAL, msg, **kwargs)

    def exception(self, msg: str, **kwargs) -> None:
        kwargs.setdefault("exc_info", True)
        self._emit(logging.ERROR, msg, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """Get a configured structured logger instance.

    Args:
        name: Logger name (typically __name__ of calling module)

    Returns:
        StructuredLogger that accepts keyword arguments as fields

    Example:
        log = get_logger(__name__)
        log.info("startup", version="1.0", environment=settings.environment)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
        logger.setLevel(log_level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return StructuredLogger(logger)


# Root logger for service
root_logger = get_logger("quant_stickynote")


def log_startup(version: str = "1.0.0") -> None:
    """Log service startup with configuration details.
    
    Args:
        version: Service version string
    """
    root_logger.info(
        "Service startup",
        version=version,
        environment=settings.environment,
        service=settings.service_name,
        log_level=settings.log_level,
        worker_enabled=settings.worker_enabled,
        api_host=settings.api_host,
        api_port=settings.api_port,
    )


def log_shutdown(reason: str = "Normal shutdown") -> None:
    """Log service shutdown.
    
    Args:
        reason: Reason for shutdown
    """
    root_logger.info("Service shutdown", reason=reason)


def log_query_execution(
    query_id: str,
    status: str,
    signals_extracted: int = 0,
    row_count: int = 0,
    duration_ms: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Log a query execution result.
    
    Args:
        query_id: Query identifier
        status: Execution status (success, error, skipped)
        signals_extracted: Number of signals found
        row_count: Number of rows returned
        duration_ms: Execution duration in milliseconds
        error_message: Error details if status=error
    """
    root_logger.info(
        "Query executed",
        query_id=query_id,
        status=status,
        signals_extracted=signals_extracted,
        row_count=row_count,
        duration_ms=duration_ms,
        error_message=error_message,
    )


def log_signal_created(
    signal_id: int,
    symbol: str,
    position_type: str,
    buy_price: float,
    source_query_id: str,
) -> None:
    """Log a new signal creation.
    
    Args:
        signal_id: StickyNote ID
        symbol: Stock symbol
        position_type: LONG or SHORT
        buy_price: Recommended entry price
        source_query_id: Query that generated signal
    """
    root_logger.info(
        "Signal created",
        signal_id=signal_id,
        symbol=symbol,
        position_type=position_type,
        buy_price=buy_price,
        source_query_id=source_query_id,
    )


def log_signal_status_updated(
    signal_id: int,
    symbol: str,
    old_status: str,
    new_status: str,
) -> None:
    """Log signal status change.
    
    Args:
        signal_id: StickyNote ID
        symbol: Stock symbol
        old_status: Previous status
        new_status: New status
    """
    root_logger.info(
        "Signal status updated",
        signal_id=signal_id,
        symbol=symbol,
        old_status=old_status,
        new_status=new_status,
    )


def log_error(
    error_type: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an error with context.
    
    Args:
        error_type: Type of error
        message: Error message
        context: Additional context variables
    """
    log_data = {
        "error_type": error_type,
    }
    if context:
        log_data.update(context)

    root_logger.error(message, **log_data)
