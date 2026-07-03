from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vl_polymarket_watchlist.settings import get_settings


def get_database_url(database_url: str | None = None) -> str:
    return database_url or get_settings().database.database_url


def create_database_engine(database_url: str | None = None) -> Engine:
    database_url = get_database_url(database_url)
    return create_engine(database_url, future=True)


@contextmanager
def database_session(database_url: str | None = None) -> Iterator[Session]:
    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        yield session
