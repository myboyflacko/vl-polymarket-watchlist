import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from whale_tracker.settings import Settings, get_settings


_STDOUT_HANDLER_NAME = "whale_tracker_jsonl_stdout"

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    root_logger = logging.getLogger()
    log_level = _log_level(settings.logging.level)

    configured_handlers = {
        handler.name: handler
        for handler in root_logger.handlers
        if handler.name in {_STDOUT_HANDLER_NAME}
    }
    stdout_handler = configured_handlers.get(_STDOUT_HANDLER_NAME)

    if stdout_handler is not None and root_logger.level == log_level:
        return

    for handler in list(root_logger.handlers):
        if handler.name not in {_STDOUT_HANDLER_NAME}:
            continue

        root_logger.removeHandler(handler)
        handler.close()

    formatter = JsonFormatter(
        "{asctime}{levelname}{name}{message}{event}{error_type}{error}"
        "{traceback}{context}{exc_info}",
        style="{",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.name = _STDOUT_HANDLER_NAME
    stdout_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.setLevel(log_level)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _log_level(value: str) -> int:
    normalized_level = value.upper()

    if normalized_level not in _LEVEL_MAP:
        raise ValueError(f"Provide one of this log levels {_LEVEL_MAP.keys()}")

    return _LEVEL_MAP[normalized_level]
