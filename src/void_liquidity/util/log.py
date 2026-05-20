import json
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_FILE_NAME = "polymarket_services.jsonl"
LOG_DIR_ENV = "VOID_LIQUIDITY_LOG_DIR"


def _log_path() -> Path:
    configured_log_dir = os.getenv(LOG_DIR_ENV)
    log_dir = Path(configured_log_dir) if configured_log_dir else PROJECT_ROOT / "logs"

    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir

    return log_dir / DEFAULT_LOG_FILE_NAME


def log_event(level: str, event: str, **context: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
        "context": context,
    }
    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, ensure_ascii=False, default=str))
        log_file.write("\n")


def log_error(event: str, exc: Exception, **context: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": "error",
        "event": event,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "context": context,
        "traceback": traceback.format_exc(),
    }
    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, ensure_ascii=False, default=str))
        log_file.write("\n")
