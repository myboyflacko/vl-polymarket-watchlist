import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Protocol

from pythonjsonlogger.json import JsonFormatter

from whale_tracker.settings import PROJECT_ROOT, Settings, get_settings

DEFAULT_LOG_FILE_NAME = "whale_tracker.jsonl"

_FILE_HANDLER_NAME = "whale_tracker_jsonl_file"
_STDOUT_HANDLER_NAME = "whale_tracker_jsonl_stdout"

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_SENSITIVE_PAYLOAD_KEYS = {
    "proxy_wallet",
    "ranked_wallets",
    "removed_wallets",
    "token_id",
    "token_ids",
    "wallets",
}


class _DomainEventLike(Protocol):
    event_type: str
    source: str
    occurred_at: datetime
    correlation_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any]


def _log_path(settings: Settings) -> Path:
    log_dir = settings.logging.log_dir

    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir

    return log_dir / DEFAULT_LOG_FILE_NAME


def configure_logging(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    root_logger = logging.getLogger()
    log_path = _log_path(settings)
    log_level = _log_level(settings.logging.level)

    configured_handlers = {
        handler.name: handler
        for handler in root_logger.handlers
        if handler.name in {_FILE_HANDLER_NAME, _STDOUT_HANDLER_NAME}
    }
    file_handler = configured_handlers.get(_FILE_HANDLER_NAME)
    stdout_handler = configured_handlers.get(_STDOUT_HANDLER_NAME)

    if (
        file_handler is not None
        and stdout_handler is not None
        and Path(getattr(file_handler, "baseFilename", "")) == log_path
        and getattr(file_handler, "backupCount", None)
        == settings.logging.retention_days
        and root_logger.level == log_level
    ):
        return

    for handler in list(root_logger.handlers):
        if handler.name not in {_FILE_HANDLER_NAME, _STDOUT_HANDLER_NAME}:
            continue

        root_logger.removeHandler(handler)
        handler.close()

    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter(
        "{asctime}{levelname}{name}{message}{event}{error_type}{error}"
        "{traceback}{context}{exc_info}",
        style="{",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.name = _STDOUT_HANDLER_NAME
    stdout_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=settings.logging.retention_days,
        encoding="utf-8",
    )
    file_handler.name = _FILE_HANDLER_NAME
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(log_level)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class VoidLogger:
    def __init__(self, name):
        self._logger = logging.getLogger(name)

    def log_event(
        self,
        event: str,
        level: str = "INFO",
        **context: Any,
    ) -> None:
        configure_logging()
        normalized_level = level.upper()

        if normalized_level not in _LEVEL_MAP:
            raise ValueError(f"Provide one of this log levels {_LEVEL_MAP.keys()}")

        self._logger.log(
            _LEVEL_MAP[normalized_level],
            event,
            extra={
                "event": event,
                "context": context,
            },
        )

    def log_domain_event(self, event: _DomainEventLike) -> None:
        level = "ERROR" if event.event_type.endswith(".failed") else "INFO"
        self.log_event(
            event.event_type,
            level=level,
            source=event.source,
            occurred_at=event.occurred_at.isoformat(),
            correlation_id=event.correlation_id,
            payload=_sanitize_log_payload(event.payload),
            metadata=event.metadata,
        )

    def log_error(
        self,
        event: str,
        exc: Exception,
        level: str = "ERROR",
        **context: Any,
    ) -> None:
        configure_logging()
        normalized_level = level.upper()

        if normalized_level not in _LEVEL_MAP:
            raise ValueError(f"Provide one of this log levels {_LEVEL_MAP.keys()}")

        self._logger.log(
            _LEVEL_MAP[normalized_level],
            event,
            extra={
                "event": event,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ).strip(),
                "context": context,
            },
            stacklevel=2,
        )


def _sanitize_log_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_log_payload(item)
            for key, item in value.items()
            if key not in _SENSITIVE_PAYLOAD_KEYS
        }

    if isinstance(value, list):
        return [_sanitize_log_payload(item) for item in value]

    return value


def _log_level(value: str) -> int:
    normalized_level = value.upper()

    if normalized_level not in _LEVEL_MAP:
        raise ValueError(f"Provide one of this log levels {_LEVEL_MAP.keys()}")

    return _LEVEL_MAP[normalized_level]
