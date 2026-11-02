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

    Supports both SQLite (local/dev) and PostgreSQL (Render / production).
    PostgreSQL URLs starting with "postgres://" are normalised to
    "postgresql://" for SQLAlchemy 2.x compatibility.
    """
    # Render's DATABASE_URL uses the older "postgres://" scheme;
    # SQLAlchemy 2.x only accepts "postgresql://".
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


_settings = get_settings()
# Only create the data directory for local SQLite usage; Postgres has its own host.
if _settings.database_url.startswith("sqlite"):
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
    alone), then apply additive schema patches and seed data.

    Imports app.storage.models locally, not at module top-level: models
    must be imported *somewhere* before create_all() runs so they've
    registered themselves on Base.metadata, but database.py importing
    models.py (which imports Base from database.py) at module load time
    would be a circular import. Deferring the import to inside this
    function breaks that cycle.

    Both SQLite and PostgreSQL are supported:
    - SQLite: additive PRAGMA-based column patches keep backwards compat.
    - PostgreSQL: `create_all` is idempotent; the helper skips PRAGMA
      calls and uses information_schema instead.
    """
    from app.storage import models  # noqa: F401

    target = bind or engine
    Base.metadata.create_all(bind=target)
    url_str = str(target.url)
    if url_str.startswith("sqlite"):
        _ensure_task_project_id_column(target)
        _ensure_pomodoro_session_name_column(target)
    _ensure_user_schema_and_admin(target)


def _table_exists(conn, table_name: str, dialect: str = "sqlite") -> bool:
    """Check whether a table exists in the connected database."""
    if dialect == "sqlite":
        result = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:name",
            {"name": table_name},
        ).fetchone()
    else:
        # PostgreSQL / information_schema
        result = conn.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:name",
            {"name": table_name},
        ).fetchone()
    return result is not None


def _column_exists(conn, table_name: str, column_name: str, dialect: str = "sqlite") -> bool:
    """Check whether a column exists in a table."""
    if dialect == "sqlite":
        cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}
        return column_name in cols
    else:
        result = conn.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:tbl AND column_name=:col",
            {"tbl": table_name, "col": column_name},
        ).fetchone()
        return result is not None


def _ensure_task_project_id_column(target_engine: Engine) -> None:
    """Additive-only patch: add `tasks.project_id` if it's missing."""
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


def _ensure_pomodoro_session_name_column(target_engine: Engine) -> None:
    """Additive-only patch: add `pomodoro_sessions.session_name` if missing."""
    if not str(target_engine.url).startswith("sqlite"):
        return
    with target_engine.begin() as conn:
        if not _table_exists(conn, "pomodoro_sessions"):
            return
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(pomodoro_sessions)").fetchall()}
        if "session_name" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE pomodoro_sessions ADD COLUMN session_name TEXT"
            )


def _ensure_user_schema_and_admin(target_engine: Engine) -> None:
    """Additive-only patch: add `user_id` to entity tables, create kunal admin,
    seed test users (alice/bob/charlie/diana/edward), and backfill existing data.

    Works for both SQLite (PRAGMA column inspection) and PostgreSQL
    (information_schema column inspection). On PostgreSQL, `create_all` already
    handles column creation, so only the missing-column additions and seed data
    are applied here.
    """
    from app.users.security import hash_password

    url_str = str(target_engine.url)
    dialect = "sqlite" if url_str.startswith("sqlite") else "postgresql"
    now_sql = "datetime('now')" if dialect == "sqlite" else "NOW()"

    tables_with_user_id = [
        "tasks",
        "projects",
        "habits",
        "reminders",
        "schedule_items",
        "pomodoro_sessions",
        "notifications",
        "conversations",
        "memories",
    ]

    with target_engine.begin() as conn:
        # 1. Add user_id column if missing (SQLite only — PG gets this from create_all)
        if dialect == "sqlite":
            for table in tables_with_user_id:
                if not _table_exists(conn, table, dialect):
                    continue
                if not _column_exists(conn, table, "user_id", dialect):
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)")

        # 2. Ensure kunal admin and extra user columns exist
        if _table_exists(conn, "users", dialect):
            if dialect == "sqlite":
                # SQLite: additive ALTER TABLE patches for legacy DBs
                if not _column_exists(conn, "users", "custom_api_keys", dialect):
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN custom_api_keys TEXT")
                if not _column_exists(conn, "users", "last_active_at", dialect):
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_active_at DATETIME")
                if not _column_exists(conn, "users", "token_usage", dialect):
                    conn.exec_driver_sql("ALTER TABLE users ADD COLUMN token_usage INTEGER NOT NULL DEFAULT 0")

            # 3. Seed kunal admin
            admin_row = conn.exec_driver_sql(
                "SELECT id, role FROM users WHERE username = 'kunal'"
            ).fetchone()
            if not admin_row:
                kunal_hash = hash_password("kunalreward34")
                conn.exec_driver_sql(
                    f"INSERT INTO users (username, password_hash, role, token_usage, created_at) "
                    f"VALUES ('kunal', :phash, 'admin', 0, {now_sql})",
                    {"phash": kunal_hash},
                )
                admin_row = conn.exec_driver_sql(
                    "SELECT id, role FROM users WHERE username = 'kunal'"
                ).fetchone()

            if admin_row:
                admin_id = admin_row[0]
                # 4. Backfill unassigned rows to admin
                for table in tables_with_user_id:
                    if _table_exists(conn, table, dialect):
                        conn.exec_driver_sql(
                            f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL",
                            {"uid": admin_id},
                        )

            # 5. Seed test users (alice, bob, charlie, diana, edward) with password 123
            test_users = [("alice", "123"), ("bob", "123"), ("charlie", "123"),
                          ("diana", "123"), ("edward", "123")]
            for uname, upwd in test_users:
                exists = conn.exec_driver_sql(
                    "SELECT id FROM users WHERE username = :u", {"u": uname}
                ).fetchone()
                if not exists:
                    phash = hash_password(upwd)
                    conn.exec_driver_sql(
                        f"INSERT INTO users (username, password_hash, role, token_usage, created_at) "
                        f"VALUES (:u, :ph, 'user', 0, {now_sql})",
                        {"u": uname, "ph": phash},
                    )

        # 6. Ensure tasks has assigned_user_id (SQLite only for legacy DBs)
        if dialect == "sqlite" and _table_exists(conn, "tasks", dialect):
            if not _column_exists(conn, "tasks", "assigned_user_id", dialect):
                conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN assigned_user_id INTEGER REFERENCES users(id)")

        # 7. Populate owner memberships for projects if missing
        if _table_exists(conn, "projects", dialect) and _table_exists(conn, "project_members", dialect):
            projects = conn.exec_driver_sql(
                "SELECT id, user_id FROM projects WHERE user_id IS NOT NULL"
            ).fetchall()
            for pid, uid in projects:
                existing = conn.exec_driver_sql(
                    "SELECT id FROM project_members WHERE project_id = :pid AND user_id = :uid",
                    {"pid": pid, "uid": uid},
                ).fetchone()
                if not existing:
                    conn.exec_driver_sql(
                        f"INSERT INTO project_members (project_id, user_id, role, status, created_at, updated_at) "
                        f"VALUES (:pid, :uid, 'owner', 'accepted', {now_sql}, {now_sql})",
                        {"pid": pid, "uid": uid},
                    )


