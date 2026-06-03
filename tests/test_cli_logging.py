import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from whale_tracker import cli
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


def test_run_whales_logs_started_and_completed_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("WHALE_TRACKER_LOG_DIR", str(tmp_path))
    get_settings.cache_clear()

    class FakeWhaleService:
        async def run(self) -> SimpleNamespace:
            return SimpleNamespace(
                run_id="run-1",
                result_whales=SimpleNamespace(wallet_count=3),
                whales=SimpleNamespace(checked_wallet_count=5),
                filtered_whales=SimpleNamespace(wallet_count=4),
                collection_errors=[],
            )

    monkeypatch.setattr(
        cli,
        "build_whale_service",
        lambda *, scoring_enabled: FakeWhaleService(),
    )

    exit_code = cli.main(["run", "whales"])

    assert exit_code == 0
    assert "Whales completed: run_id=run-1" in capsys.readouterr().out

    events = _read_log_events(tmp_path)
    assert events == ["service.started", "service.completed"]

    completed = _read_log_payloads(tmp_path)[1]
    assert completed["context"]["service"] == "whales"
    assert completed["context"]["run_id"] == "run-1"
    assert completed["context"]["selected"] == 3


def test_run_whales_logs_failed_event_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WHALE_TRACKER_LOG_DIR", str(tmp_path))
    get_settings.cache_clear()

    class FailingWhaleService:
        async def run(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        cli,
        "build_whale_service",
        lambda *, scoring_enabled: FailingWhaleService(),
    )

    exit_code = cli.main(["run", "whales"])

    assert exit_code == 1
    assert _read_log_events(tmp_path) == ["service.started", "service.failed"]

    failed = _read_log_payloads(tmp_path)[1]
    assert failed["levelname"] == "ERROR"
    assert failed["context"]["command"] == "run"
    assert failed["context"]["service"] == "whales"
    assert "RuntimeError: boom" in failed["exc_info"]


def _read_log_payloads(log_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (log_dir / "whale_tracker.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]


def _read_log_events(log_dir: Path) -> list[str]:
    return [str(payload["event"]) for payload in _read_log_payloads(log_dir)]
