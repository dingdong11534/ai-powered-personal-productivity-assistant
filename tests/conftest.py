"""
Shared pytest fixtures.

WHAT THIS DOES
---------------
Every test in this project that touches the database uses one of two
fixtures defined here:

- `db_session`: a raw SQLAlchemy Session bound to a fresh in-memory
  SQLite database, for testing TaskRepository/TaskService directly
  (no HTTP involved).
- `client`: a FastAPI TestClient with `get_db` overridden to use that
  same kind of in-memory database, for testing the actual HTTP API.

Both build their own engine rather than importing `engine` from
app.storage.database — that module's engine is bound to whatever
DATABASE_URL is configured (SQLite file by default, see
app/core/config.py), and tests must never write to that real file.

WHY StaticPool
---------------
An in-memory SQLite database (`sqlite:///:memory:`) normally lives only
as long as the single connection that created it — a second connection
would see an empty, unrelated database. `StaticPool` makes SQLAlchemy
reuse exactly one underlying connection for the whole engine, so every
Session created from that engine sees the same in-memory database. This
is the standard pattern for testing SQLAlchemy + SQLite together (see
SQLAlchemy's own testing docs) and it's why `client` builds a *fresh*
engine per test rather than reusing one across the whole test run —
that's what gives each test a clean, empty database with no leftover
rows from a previous test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.interfaces.main import app
from app.storage.database import Base, get_db


def _make_test_engine():
    from app.storage import models  # noqa: F401
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session():
    """A Session bound to a fresh, empty in-memory database — for
    testing TaskRepository/TaskService directly."""
    engine = _make_test_engine()
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    """A TestClient hitting the real FastAPI app, with get_db overridden
    to use a fresh in-memory database instead of the real one."""
    engine = _make_test_engine()
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
