import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

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


def _log_level(value: str) -> int:
    normalized_level = value.upper()

    if normalized_level not in _LEVEL_MAP:
        raise ValueError(f"Provide one of this log levels {_LEVEL_MAP.keys()}")

    return _LEVEL_MAP[normalized_level]
