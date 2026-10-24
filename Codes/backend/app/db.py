"""Database engine, session factory and portable column types.

Production runs on PostgreSQL 16. The test-suite runs on SQLite so `make test` needs no
Docker; the custom types below map to native Postgres types (JSONB, TEXT[]) and to JSON
on SQLite.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import JSON, Text, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings

JSONType = JSON().with_variant(JSONB(), "postgresql")


class StrList(TypeDecorator[list[str]]):
    """`text[]` on Postgres, a JSON list elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[str] | None, dialect: Any) -> list[str] | None:
        return list(value) if value is not None else None

    def process_result_value(self, value: Any, dialect: Any) -> list[str] | None:
        return list(value) if value is not None else None


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn: Any, _: Any) -> None:  # pragma: no cover - trivial
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return eng
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


def configure(url: str | None = None) -> Engine:
    """(Re)configure the global engine. Tests call this with a SQLite URL."""
    global _engine, _SessionLocal
    _engine = make_engine(url or get_settings().database_url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def engine() -> Engine:
    if _engine is None:
        configure()
    assert _engine is not None
    return _engine


def SessionLocal() -> Session:  # noqa: N802 - reads like a class on purpose
    if _SessionLocal is None:
        configure()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
