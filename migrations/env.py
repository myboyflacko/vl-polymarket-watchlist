from __future__ import annotations

from logging.config import fileConfig
from os import environ
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from void_liquidity.adapters.polymarket.market_discovery.sources.track_whales.db import (
    Base,
    build_sqlite_url,
)
from void_liquidity.adapters.polymarket.market_discovery.sources.track_whales.schemas import (
    WhaleTrackingProfile,
)


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured_url = environ.get("VOID_LIQUIDITY_WHALE_TRACKER_DATABASE_URL")

    if configured_url:
        return configured_url

    return build_sqlite_url(WhaleTrackingProfile().database_path)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
