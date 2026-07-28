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
    _ensure_columns()


def _ensure_columns() -> None:
    """Add columns introduced after a table was first created.

    SQLModel.create_all() creates missing *tables* but never ALTERs existing
    ones, so a pre-existing stemgen.db would be missing newer Student columns.
    For the SQLite dev DB we add them in place (SQLite supports ADD COLUMN),
    preserving existing rows. Postgres deployments should use real migrations.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text

    wanted = {"reset_token_hash": "TEXT", "reset_expires_at": "DATETIME"}
    existing = {c["name"] for c in inspect(engine).get_columns("students")}
    with engine.begin() as conn:
        for col, coltype in wanted.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE students ADD COLUMN {col} {coltype}"))


def get_session() -> Iterator[Session]:
    # expire_on_commit=False so ORM objects keep their loaded attributes after a
    # commit. The agent loop commits several times per request (append-only event
    # log); without this the delivered ProblemRecord would be expired and
    # serialize to {} in the API response.
    with Session(engine, expire_on_commit=False) as session:
        yield session
