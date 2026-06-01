import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pythonjsonlogger.json import JsonFormatter

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_FILE_NAME = "polymarket_services.jsonl"
LOG_DIR_ENV = "VOID_LIQUIDITY_LOG_DIR"

_HANDLER_NAME = "void_liquidity_jsonl"

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


def _log_path() -> Path:
    configured_log_dir = os.getenv(LOG_DIR_ENV)
    log_dir = Path(configured_log_dir) if configured_log_dir else PROJECT_ROOT / "logs"

    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir

    return log_dir / DEFAULT_LOG_FILE_NAME


def configure_logging() -> None:
    root_logger = logging.getLogger()
    log_path = _log_path()

    for handler in root_logger.handlers:
        if handler.name != _HANDLER_NAME:
            continue

        if Path(getattr(handler, "baseFilename", "")) == log_path:
            return

        root_logger.removeHandler(handler)
        handler.close()

    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.name = _HANDLER_NAME

    formatter = JsonFormatter(
        "{asctime}{levelname}{name}{event}{error_type}{error}"
        "{traceback}{context}",
        style="{",
    )

    handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)
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
