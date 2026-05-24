from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def resolve_project_path(path: str | Path) -> Path:
    resolved_path = Path(path)

    if resolved_path.is_absolute():
        return resolved_path

    return PROJECT_ROOT / resolved_path


def build_sqlite_url(database_path: str | Path) -> str:
    resolved_path = resolve_project_path(database_path)
    return f"sqlite:///{resolved_path}"


def create_database_engine(database_path: str | Path) -> Engine:
    resolved_path = resolve_project_path(database_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{resolved_path}", future=True)


@contextmanager
def database_session(database_path: str | Path) -> Iterator[Session]:
    engine = create_database_engine(database_path)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        yield session
