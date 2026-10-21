"""Connecting to the database.

* The **engine** knows how to reach the database (one per application).
* A **session** is one unit of work: you read and change rows through it, then
  `commit()` saves everything together or nothing at all (a *transaction*).
"""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from incident_intel.config import get_settings
from incident_intel.storage.tables import Base


def make_engine(url: str) -> Engine:
    """Create an engine for `url`, with SQLite-friendly settings when needed."""
    parsed = make_url(url)
    is_sqlite = parsed.get_backend_name() == "sqlite"
    in_memory = is_sqlite and parsed.database in (None, "", ":memory:")
    if is_sqlite and not in_memory:
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)

    options: dict[str, Any] = {}
    if is_sqlite:
        # FastAPI may run a request on a different thread than the one that
        # opened the SQLite connection; this flag allows that.
        options["connect_args"] = {"check_same_thread": False}
    if in_memory:
        # An in-memory database lives inside one connection, so every session
        # must share that connection (used by the tests).
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _use_write_ahead_log(dbapi_connection: Any, _record: Any) -> None:
            # WAL mode lets the API keep reading while the loader script writes.
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

    return engine


def create_tables(engine: Engine) -> None:
    """Create any missing tables. (Real projects use migrations; see the learning notes.)"""
    Base.metadata.create_all(engine)


def reset_tables(engine: Engine) -> None:
    """Delete all tables and create them again, empty."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@lru_cache
def get_engine() -> Engine:
    """The application's shared engine, built from `DATABASE_URL`."""
    return make_engine(get_settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    with _session_factory()() as session:
        yield session
