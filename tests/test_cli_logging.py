import json
import logging
from types import SimpleNamespace

import pytest

from vl_polymarket_watchlist import cli
from vl_polymarket_watchlist.settings import get_settings


@pytest.fixture(autouse=True)
def reset_logging() -> None:
    root_logger = logging.getLogger()
    original_level = root_logger.level

    yield

    for handler in list(root_logger.handlers):
        if handler.name and handler.name.startswith("vl_polymarket_watchlist_jsonl_"):
            root_logger.removeHandler(handler)
            handler.close()

    root_logger.setLevel(original_level)
    get_settings.cache_clear()


def test_run_discovery_logs_started_and_completed_events(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_settings.cache_clear()

    class FakeDiscoveryService:
        async def run(self) -> SimpleNamespace:
            return SimpleNamespace(
                run_id="run-1",
                source="whale_discovery",
                checked_count=3,
                observed_count=2,
                errors=[],
            )

    monkeypatch.setattr(
        cli,
        "build_discovery_service",
        lambda *, source_name: FakeDiscoveryService(),
    )

    exit_code = cli.main(["run", "discovery"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Discovery completed: run_id=run-1" in stdout

    payloads = _read_log_payloads(stdout)
    assert [payload["event"] for payload in payloads] == [
        "service.started",
        "service.completed",
    ]
    assert payloads[1]["context"] == {
        "service": "discovery",
        "run_id": "run-1",
        "source": "whale_discovery",
        "checked": 3,
        "observed": 2,
        "errors": 0,
    }


def test_run_discovery_logs_failed_event_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_settings.cache_clear()

    class FailingDiscoveryService:
        async def run(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        cli,
        "build_discovery_service",
        lambda *, source_name: FailingDiscoveryService(),
    )

    exit_code = cli.main(["run", "discovery"])

    assert exit_code == 1
    payloads = _read_log_payloads(capsys.readouterr().out)
    assert [payload["event"] for payload in payloads] == [
        "service.started",
        "service.failed",
    ]
    assert payloads[1]["levelname"] == "ERROR"
    assert payloads[1]["context"]["command"] == "run"
    assert payloads[1]["context"]["service"] == "discovery"
    assert "RuntimeError: boom" in payloads[1]["exc_info"]


def test_run_orderbooks_logs_skipped_event(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_settings.cache_clear()

    class SkippedOrderbookService:
        async def run(self) -> SimpleNamespace:
            return SimpleNamespace(
                run_id=None,
                status="skipped",
                skip_reason="no_completed_discovery_run",
            )

    monkeypatch.setattr(
        cli,
        "build_orderbook_service",
        lambda *, batch_size: SkippedOrderbookService(),
    )

    exit_code = cli.main(["run", "orderbooks"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Orderbooks skipped: reason=no_completed_discovery_run" in stdout

    payloads = _read_log_payloads(stdout)
    assert [payload["event"] for payload in payloads] == [
        "service.started",
        "service.skipped",
    ]
    assert payloads[1]["context"] == {
        "service": "orderbooks",
        "reason": "no_completed_discovery_run",
    }


def test_removed_services_are_not_cli_choices() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "whales"])

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "trades"])

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "markets"])

    with pytest.raises(SystemExit):
        parser.parse_args(["api"])


def _read_log_payloads(stdout: str) -> list[dict]:
    return [
        json.loads(line)
        for line in stdout.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]
