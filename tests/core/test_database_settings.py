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
