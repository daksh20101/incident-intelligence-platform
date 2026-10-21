"""Shared test fixtures. pytest finds this file automatically.

Every test that asks for `client` or `session` gets its own brand-new, empty
in-memory database, so tests can't affect each other or your real data file.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from incident_intel.api.main import app
from incident_intel.storage.db import create_tables, get_session, make_engine


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = make_engine("sqlite://")  # "sqlite://" with no file = in memory
    create_tables(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    """An API client whose requests use the test database."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    yield TestClient(app)
    app.dependency_overrides.clear()
