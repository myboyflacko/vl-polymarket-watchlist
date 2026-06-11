import asyncio
import json
import logging
import sys
from types import ModuleType, SimpleNamespace

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
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_settings.cache_clear()

    class FakeWhaleService:
        async def run(self) -> SimpleNamespace:
            return SimpleNamespace(
                run_id="run-1",
                whales=SimpleNamespace(checked_wallet_count=5, wallet_count=4),
            )

    monkeypatch.setattr(cli, "build_whale_service", lambda: FakeWhaleService())

    exit_code = cli.main(["run", "whales"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Whales completed: run_id=run-1" in stdout

    events = _read_log_events(stdout)
    assert events == ["service.started", "service.completed"]

    completed = _read_log_payloads(stdout)[1]
    assert completed["context"]["service"] == "whales"
    assert completed["context"]["run_id"] == "run-1"
    assert completed["context"]["observed"] == 4
    assert "tracked" not in completed["context"]


def test_run_whales_logs_failed_event_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_settings.cache_clear()

    class FailingWhaleService:
        async def run(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "build_whale_service", lambda: FailingWhaleService())

    exit_code = cli.main(["run", "whales"])

    assert exit_code == 1
    stdout = capsys.readouterr().out
    assert _read_log_events(stdout) == ["service.started", "service.failed"]

    failed = _read_log_payloads(stdout)[1]
    assert failed["levelname"] == "ERROR"
    assert failed["context"]["command"] == "run"
    assert failed["context"]["service"] == "whales"
    assert "RuntimeError: boom" in failed["exc_info"]


def test_api_command_starts_uvicorn_with_local_defaults(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    get_settings.cache_clear()
    calls = []

    fake_uvicorn = ModuleType("uvicorn")

    def fake_run(app: str, *, host: str, port: int, reload: bool) -> None:
        calls.append(
            {
                "app": app,
                "host": host,
                "port": port,
                "reload": reload,
            }
        )

    fake_uvicorn.run = fake_run
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    exit_code = cli.main(["api"])

    assert exit_code == 0
    assert calls == [
        {
            "app": "whale_tracker.api.main:app",
            "host": "127.0.0.1",
            "port": 8000,
            "reload": True,
        }
    ]
    assert "Starting API server at http://127.0.0.1:8000" in capsys.readouterr().out


def test_run_markets_after_whales_waits_for_active_whale_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_markets(*, whales_run_id: str | None) -> str:
        calls.append(str(whales_run_id))
        return "markets-run-1"

    async def run_test() -> None:
        lock = asyncio.Lock()
        await lock.acquire()
        monkeypatch.setattr(cli, "run_markets", fake_run_markets)

        task = asyncio.create_task(
            cli.run_markets_after_whales(
                whales_lock=lock,
                whales_run_id="whales-run-1",
            )
        )
        await asyncio.sleep(0)

        assert calls == []

        lock.release()
        result = await task

        assert result == "markets-run-1"

    asyncio.run(run_test())
    assert calls == ["whales-run-1"]


def test_run_markets_after_whales_runs_immediately_when_whales_are_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_markets(*, whales_run_id: str | None) -> str:
        calls.append(str(whales_run_id))
        return "markets-run-1"

    async def run_test() -> str:
        monkeypatch.setattr(cli, "run_markets", fake_run_markets)
        return await cli.run_markets_after_whales(
            whales_lock=asyncio.Lock(),
            whales_run_id=None,
        )

    assert asyncio.run(run_test()) == "markets-run-1"
    assert calls == ["None"]


def _read_log_payloads(stdout: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in stdout.splitlines()
        if line.startswith("{")
    ]


def _read_log_events(stdout: str) -> list[str]:
    return [str(payload["event"]) for payload in _read_log_payloads(stdout)]
