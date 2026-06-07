import json
import logging

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


def test_configure_logging_writes_jsonl_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("WHALE_TRACKER_LOG_LEVEL", "INFO")
    get_settings.cache_clear()

    configure_logging()
    configure_logging()

    root_logger = logging.getLogger()
    handlers = [
        handler
        for handler in root_logger.handlers
        if handler.name and handler.name.startswith("whale_tracker_jsonl_")
    ]

    assert len(handlers) == 1

    logging.getLogger("tests.logging").info(
        "Test event",
        extra={"event": "test.event", "context": {"ok": True}},
    )

    stdout_line = capsys.readouterr().out.strip()
    stdout_payload = json.loads(stdout_line)

    assert stdout_payload["event"] == "test.event"
    assert stdout_payload["context"] == {"ok": True}
