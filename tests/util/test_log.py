import json
from pathlib import Path

import pytest

from void_liquidity.util.log import (
    DEFAULT_LOG_FILE_NAME,
    LOG_DIR_ENV,
    VoidLogger,
)


def _read_log_lines(log_dir: Path) -> list[dict[str, object]]:
    log_path = log_dir / DEFAULT_LOG_FILE_NAME

    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]


def test_log_event_writes_jsonl_without_console_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv(LOG_DIR_ENV, str(log_dir))
    logger = VoidLogger("void_liquidity.test")

    logger.log_event("test.event", wallet="0xabc", count=2)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    [payload] = _read_log_lines(log_dir)
    assert payload["levelname"] == "INFO"
    assert payload["name"] == "void_liquidity.test"
    assert payload["event"] == "test.event"
    assert payload["context"] == {"wallet": "0xabc", "count": 2}
    assert isinstance(payload["asctime"], str)


def test_log_error_writes_agent_readable_error_payload(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv(LOG_DIR_ENV, str(log_dir))
    logger = VoidLogger("void_liquidity.test")

    try:
        raise ValueError("bad payload")
    except ValueError as exc:
        logger.log_error("test.failed", exc, endpoint="/activity")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    [payload] = _read_log_lines(log_dir)
    assert payload["levelname"] == "ERROR"
    assert payload["name"] == "void_liquidity.test"
    assert payload["event"] == "test.failed"
    assert payload["error_type"] == "ValueError"
    assert payload["error"] == "bad payload"
    assert payload["context"] == {"endpoint": "/activity"}
    assert "ValueError: bad payload" in payload["traceback"]
