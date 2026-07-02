from polymarket_storage.settings import DatabaseSettings


def test_database_settings_builds_postgres_url() -> None:
    settings = DatabaseSettings(
        name="polymarket_storage",
        user="tracker",
        password="secret",
        host="postgres",
        port=5432,
    )

    assert (
        settings.database_url
        == "postgresql+psycopg://tracker:secret@postgres:5432/polymarket_storage"
    )
