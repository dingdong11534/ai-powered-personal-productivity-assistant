"""
Database configuration and session layer.

WHAT THIS DOES
---------------
Sets up the one SQLAlchemy `engine` the whole app uses, the declarative
`Base` every ORM model inherits from, and `get_db()` — a generator that
hands out a `Session` scoped to a single request and always closes it
afterward, regardless of whether the request succeeded or raised.

WHY IT EXISTS AS ITS OWN MODULE
----------------------------------
Every part of the app that needs a database connection (right now just
`app.tasks`, later `app.habits`, `app.scheduling`, ...) needs the *same*
engine and session configuration — same connection string, same pooling
behavior, same commit/rollback discipline. Centralizing that here means:
- a domain module (e.g. app.tasks.repository) only ever imports `get_db`
  or `Base`, never constructs its own engine
- tests can override `get_db` (see tests/conftest.py) to point every
  request at an isolated in-memory database, without touching a single
  line of route or repository code

HOW DATA FLOWS
---------------
Import time: `get_settings()` is read once to build `engine`, bound to
`settings.database_url` (SQLite by default — see app/core/config.py).

Per request: FastAPI calls `get_db()` as a dependency -> a new `Session`
is created from `SessionLocal` -> the route/service/repository code uses
that session for every query in the request -> when the request finishes
(success or exception), the `finally` block closes the session. Nothing
commits automatically — see TaskRepository, which commits explicitly
after each write, so a half-finished multi-step operation can't leave a
partial commit behind.

DESIGN DECISIONS WORTH UNDERSTANDING
----------------------------------------
- `check_same_thread: False` for SQLite: SQLite normally refuses to let a
  connection be used from a different thread than the one that created
  it. FastAPI can run request handlers in different threads, so without
  this flag, a request could crash on "SQLite objects created in a
  thread can only be used in that same thread". This is the standard,
  documented workaround for SQLite + a threaded server; it doesn't apply
  to (and is skipped for) non-SQLite database URLs.
- `sessionmaker(autocommit=False, autoflush=False, ...)`: explicit control
  over when data actually hits the database, rather than SQLAlchemy
  flushing/committing implicitly mid-query. This makes it predictable
  exactly when a write becomes visible to other sessions.
- `create_all_tables()` is a function, not a module-level side effect:
  importing this module must never touch the filesystem or create tables
  as a side effect of `import app.storage.database` (e.g. from a test
  that only wants `Base`). Table creation happens explicitly, once, at
  application startup (see app/interfaces/main.py's lifespan handler).

HOW TO TEST
------------
This module itself has no tests of its own — it has no business logic,
just wiring. It's exercised indirectly by every test that uses the
`db_session` or `client` fixtures in tests/conftest.py, which build a
*separate* engine pointed at an in-memory SQLite database rather than
importing `engine` from here, so tests never touch the real
`data/assistant.db` file.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base. Every ORM model in app.storage.models
    inherits from this, which is what lets Base.metadata.create_all()
    discover and create all of them together."""


def build_engine(database_url: str) -> Engine:
    """Construct a SQLAlchemy engine for `database_url`.

    Pulled out as its own function (rather than inlined below) so tests
    and any future multi-database setup can build an equivalently
    configured engine without duplicating the SQLite-specific connect_args
    logic.
    """
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


_settings = get_settings()
_settings.ensure_data_dir()

engine: Engine = build_engine(_settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a request-scoped Session, always closed after.

    Usage: `db: Session = Depends(get_db)` in a route, or indirectly via
    a service constructed with that session (see app.tasks.service).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables(bind: Engine | None = None) -> None:
    """Create every table registered on Base.metadata (idempotent — safe
    to call on an already-initialized database; existing tables are left
    alone), then apply the narrow additive patch in `_ensure_task_project_id_column`.

    Imports app.storage.models locally, not at module top-level: models
    must be imported *somewhere* before create_all() runs so they've
    registered themselves on Base.metadata, but database.py importing
    models.py (which imports Base from database.py) at module load time
    would be a circular import. Deferring the import to inside this
    function breaks that cycle.
    """
    from app.storage import models  # noqa: F401

    target = bind or engine
    Base.metadata.create_all(bind=target)
    _ensure_task_project_id_column(target)


def _table_exists(conn, table_name: str) -> bool:
    result = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:name",
        {"name": table_name},
    ).fetchone()
    return result is not None


def _ensure_task_project_id_column(target_engine: Engine) -> None:
    """Additive-only patch: add `tasks.project_id` if it's missing.

    WHY THIS EXISTS
    -----------------
    `Base.metadata.create_all()` only creates tables that don't exist yet
    — it never alters an existing table's columns. Phase 1 adds
    `project_id` to the *already-existing* `tasks` table, so a database
    created under Phase 0.2 (before this column existed) would otherwise
    be silently out of sync with the model: SQLAlchemy would generate
    `INSERT`/`SELECT` statements referencing a `project_id` column the
    real table doesn't have, and every query would fail.

    This function detects exactly that situation — `tasks` table exists,
    `project_id` column doesn't — and adds the column via a plain
    `ALTER TABLE ... ADD COLUMN`, which SQLite supports for adding a
    nullable column with no default. Existing rows get `NULL` for the
    new column, which is exactly correct: `project_id` is nullable
    (a task doesn't have to belong to a project), so "we don't know"
    and "not assigned to a project" are the same value.  No data in any
    existing column is touched.

    This patch is intentionally narrow: it fixes precisely one kind of
    change (an added nullable column with no default, no rename, no data
    transform). It does not generalize to a real migration tool.

    SQLite-only: on any other backend this is a no-op, since only SQLite
    is used by this project so far (see app.core.config's DATABASE_URL).

    WHY NOT ALEMBIC, YET
    -----------------------
    See docs/architecture.md's "Migrations" section for the full
    reasoning. Short version: everything this phase's schema needs
    (new tables, one added nullable column) is safely expressible as
    "create what's missing, patch what changed" — which this function
    and `create_all_tables()` already do, and which I can verify
    directly against SQLite semantics. The point to actually adopt
    Alembic is documented there too: the first migration that isn't
    purely additive (a rename, a backfill, a NOT NULL added to a
    populated column, a dropped column) needs real up/down migration
    scripts, because "detect and patch" stops being expressible as a
    simple idempotent check at that point.
    """
    if not str(target_engine.url).startswith("sqlite"):
        return
    with target_engine.begin() as conn:
        if not _table_exists(conn, "tasks"):
            return  # fresh database — create_all() already made it with the column
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()}
        if "project_id" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN project_id INTEGER REFERENCES projects(id)"
            )
