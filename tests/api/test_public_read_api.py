from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from whale_tracker.api import main as api_main


def test_whales_returns_latest_whale_observations(monkeypatch):
    generated_at = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(api_main, "get_latest_discovery_run_id", lambda: "whales-run-1")
    monkeypatch.setattr(
        api_main,
        "list_whale_observations",
        lambda *, run_id: SimpleNamespace(
            profile_version="whale_discovery_trade_first",
            generated_at=generated_at,
            whales=[{"proxy_wallet": "0xabc"}],
        ),
    )

    response = api_main.get_latest_whales()

    assert response.model_dump(mode="json") == {
        "whales": [{"proxy_wallet": "0xabc"}],
        "run_id": "whales-run-1",
        "profile_version": "whale_discovery_trade_first",
        "generated_at": "2026-06-11T12:00:00Z",
        "whales_count": 1,
    }


def test_whales_uses_requested_run_id(monkeypatch):
    calls = []

    monkeypatch.setattr(api_main, "get_latest_discovery_run_id", lambda: "latest-run")
    monkeypatch.setattr(
        api_main,
        "list_whale_observations",
        lambda *, run_id: calls.append(run_id)
        or SimpleNamespace(
            profile_version="profile",
            generated_at=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
            whales=[],
        ),
    )

    response = api_main.get_latest_whales(run_id="requested-run")

    assert calls == ["requested-run"]
    assert response.run_id == "requested-run"


def test_whales_returns_404_without_available_run(monkeypatch):
    monkeypatch.setattr(api_main, "get_latest_discovery_run_id", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        api_main.get_latest_whales()

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No whale run found"


def test_markets_returns_latest_tracked_markets(monkeypatch):
    generated_at = datetime(2026, 6, 11, 12, 5, tzinfo=UTC)

    monkeypatch.setattr(api_main, "get_latest_market_run_id", lambda: "markets-run-1")
    monkeypatch.setattr(
        api_main,
        "list_tracked_markets",
        lambda *, run_id: SimpleNamespace(
            run_id=run_id,
            filter_profile="dominant_side_5_whales_80_percent_latest_run",
            generated_at=generated_at,
            markets=[{"condition_id": "condition-1", "token_id": "token-1"}],
        ),
    )

    response = api_main.get_latest_markets()

    assert response.model_dump(mode="json") == {
        "markets": [{"condition_id": "condition-1", "token_id": "token-1"}],
        "run_id": "markets-run-1",
        "filter_profile": "dominant_side_5_whales_80_percent_latest_run",
        "generated_at": "2026-06-11T12:05:00Z",
        "markets_count": 1,
    }


def test_orderbooks_endpoint_is_not_public():
    paths = {route.path for route in api_main.app.routes}

    assert "/orderbooks" not in paths
