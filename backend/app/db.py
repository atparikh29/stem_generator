"""Database engine and session helpers (SQLModel over SQLite/Postgres)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# check_same_thread is a SQLite-only argument; ignore it for Postgres.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Create tables. Import models first so they register on SQLModel.metadata."""
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    # expire_on_commit=False so ORM objects keep their loaded attributes after a
    # commit. The agent loop commits several times per request (append-only event
    # log); without this the delivered ProblemRecord would be expired and
    # serialize to {} in the API response.
    with Session(engine, expire_on_commit=False) as session:
        yield session
