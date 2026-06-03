import json
import logging
from pathlib import Path

import pytest

from whale_tracker.core.logging import configure_logging
from whale_tracker.settings import get_settings


@pytest.fixture(autouse=True)
def reset_logging() -> None:
    root_logger = logging.getLogger()
    original_level = root_logger.level

    yield

    for handler in list(root_logger.handlers):
        if handler.name and handler.name.startswith("whale_tracker_jsonl_"):
            root_logger.removeHandler(handler)
            handler.close()

    root_logger.setLevel(original_level)
    get_settings.cache_clear()


def test_configure_logging_writes_jsonl_to_stdout_and_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("WHALE_TRACKER_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("WHALE_TRACKER_LOG_LEVEL", "INFO")
    monkeypatch.setenv("WHALE_TRACKER_LOG_RETENTION_DAYS", "7")
    get_settings.cache_clear()

    configure_logging()
    configure_logging()

    root_logger = logging.getLogger()
    handlers = [
        handler
        for handler in root_logger.handlers
        if handler.name and handler.name.startswith("whale_tracker_jsonl_")
    ]

    assert len(handlers) == 2

    logging.getLogger("tests.logging").info(
        "Test event",
        extra={"event": "test.event", "context": {"ok": True}},
    )

    stdout_line = capsys.readouterr().out.strip()
    file_line = (tmp_path / "whale_tracker.jsonl").read_text(
        encoding="utf-8"
    ).strip()

    stdout_payload = json.loads(stdout_line)
    file_payload = json.loads(file_line)

    assert stdout_payload["event"] == "test.event"
    assert stdout_payload["context"] == {"ok": True}
    assert file_payload["event"] == "test.event"

    file_handler = next(
        handler for handler in handlers if hasattr(handler, "baseFilename")
    )
    assert file_handler.backupCount == 7
