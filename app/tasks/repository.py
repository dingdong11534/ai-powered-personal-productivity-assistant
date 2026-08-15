"""
TaskRepository — direct, ORM-level CRUD against the `tasks` table.

WHAT THIS DOES
---------------
The only place in the project that runs SQLAlchemy queries against Task.
Every method takes and returns SQLAlchemy `Task` objects (or `None`) —
it knows nothing about HTTP, Pydantic schemas, or what "not found" should
mean to a caller.

WHY IT'S SEPARATE FROM TaskService
--------------------------------------
This split (repository vs. service) is the same "domain packages depend
on app.storage, not the other way around" boundary from
docs/architecture.md, one level more specific:

- TaskRepository is deliberately dumb: no business rules, no exceptions
  beyond what SQLAlchemy itself raises. That's what makes it trivial to
  test against a real (in-memory) database with no mocking, and what
  would make it swappable for a different persistence approach later
  without touching business logic.
- TaskService (service.py) is where "task_id doesn't exist -> raise
  TaskNotFoundError" and any future business rule lives. Keeping that out
  of the repository means the repository's `get()` can stay a plain
  "give me the row or None" — the same primitive both
  "does this exist?" checks and "fetch or 404" logic can be built from.

HOW TO TEST
------------
See tests/test_task_repository.py. These tests use a real in-memory
SQLite database (see tests/conftest.py's `db_session` fixture) rather
than mocking the Session — a mock would only prove the repository calls
`.add()`/`.commit()` in some order, not that the resulting SQL actually
does what's intended (e.g. that the CHECK constraint on `priority` is
real).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Task


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, task: Task) -> Task:
        """Persist a new (not-yet-added) Task and return it with its
        server-assigned fields (id, created_at, updated_at) populated."""
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get(self, task_id: int) -> Task | None:
        """Return the Task with this id, or None if it doesn't exist."""
        return self.db.get(Task, task_id)

    def list(self, *, skip: int = 0, limit: int = 100) -> list[Task]:
        """Return up to `limit` tasks, newest first, skipping the first
        `skip` — a simple offset/limit page. Ordering by created_at,
        rather than leaving order database-default/unspecified, is what
        makes repeated calls to GET /tasks return a stable order."""
        stmt = select(Task).order_by(Task.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt))

    def update(self, task: Task, changes: dict) -> Task:
        """Apply `changes` (attribute name -> new value) to an existing,
        already-fetched Task, persist, and return the refreshed row."""
        for field, value in changes.items():
            setattr(task, field, value)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, task: Task) -> None:
        """Delete an existing, already-fetched Task."""
        self.db.delete(task)
        self.db.commit()
