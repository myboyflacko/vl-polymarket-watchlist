from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from void_liquidity.settings import PROJECT_ROOT, get_settings


SQLITE_URL_PREFIX = "sqlite:///"


def resolve_project_path(path: str | Path) -> Path:
    resolved_path = Path(path)

    if resolved_path.is_absolute():
        return resolved_path

    return PROJECT_ROOT / resolved_path


def build_sqlite_url(database_path: str | Path | None = None) -> str:
    if database_path is None:
        return get_settings().database.database_url

    resolved_path = resolve_project_path(database_path)
    return f"{SQLITE_URL_PREFIX}{resolved_path}"


def create_database_engine(database_path: str | Path | None = None) -> Engine:
    database_url = build_sqlite_url(database_path)

    if database_url.startswith(SQLITE_URL_PREFIX):
        Path(database_url.removeprefix(SQLITE_URL_PREFIX)).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    return create_engine(database_url, future=True)


@contextmanager
def database_session(database_path: str | Path | None = None) -> Iterator[Session]:
    engine = create_database_engine(database_path)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        yield session
