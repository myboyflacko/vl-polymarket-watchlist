import pytest

from vl_polymarket_watchlist.settings import DatabaseSettings


def test_database_settings_builds_postgres_url() -> None:
    settings = DatabaseSettings(
        name="vl_polymarket_watchlist",
        user="tracker",
        password="secret",
        host="postgres",
        port=5432,
    )

    assert (
        settings.database_url
        == "postgresql+psycopg://tracker:secret@postgres:5432/vl_polymarket_watchlist"
    )


def test_database_settings_reads_watchlist_postgres_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYMARKET_WATCHLIST_POSTGRES_DB", "env_db")
    monkeypatch.setenv("POLYMARKET_WATCHLIST_POSTGRES_USER", "env_user")
    monkeypatch.setenv("POLYMARKET_WATCHLIST_POSTGRES_PASSWORD", "env_secret")
    monkeypatch.setenv("POLYMARKET_WATCHLIST_POSTGRES_HOST", "env_postgres")
    monkeypatch.setenv("POLYMARKET_WATCHLIST_POSTGRES_PORT", "5544")

    settings = DatabaseSettings()

    assert settings.name == "env_db"
    assert settings.user == "env_user"
    assert settings.password == "env_secret"
    assert settings.host == "env_postgres"
    assert settings.port == 5544
