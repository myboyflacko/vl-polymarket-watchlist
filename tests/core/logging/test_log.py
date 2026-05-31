import json
from pathlib import Path

import pytest

from void_liquidity.core.events import DomainEvent
from void_liquidity.core.logging.log import (
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


def test_log_domain_event_writes_event_context(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv(LOG_DIR_ENV, str(log_dir))
    logger = VoidLogger("void_liquidity.test")
    event = DomainEvent.create(
        event_type="pipeline.discovery.whales.started",
        source="polymarket.whale_tracker",
        payload={"run_id": "run-1"},
        correlation_id="correlation-1",
        metadata={"profile": "quality"},
    )

    logger.log_domain_event(event)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    [payload] = _read_log_lines(log_dir)
    assert payload["levelname"] == "INFO"
    assert payload["name"] == "void_liquidity.test"
    assert payload["event"] == "pipeline.discovery.whales.started"
    assert payload["context"] == {
        "source": "polymarket.whale_tracker",
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": "correlation-1",
        "payload": {"run_id": "run-1"},
        "metadata": {"profile": "quality"},
    }


def test_log_domain_event_uses_error_level_for_failed_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv(LOG_DIR_ENV, str(log_dir))
    logger = VoidLogger("void_liquidity.test")
    event = DomainEvent.create(
        event_type="pipeline.discovery.whales.failed",
        source="polymarket.whale_tracker",
    )

    logger.log_domain_event(event)

    [payload] = _read_log_lines(log_dir)
    assert payload["levelname"] == "ERROR"
    assert payload["event"] == "pipeline.discovery.whales.failed"
