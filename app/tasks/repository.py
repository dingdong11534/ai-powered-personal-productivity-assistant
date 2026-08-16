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

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.storage.models import Task, TaskStatus, task_tags


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

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        status: TaskStatus | None = None,
        priority: int | None = None,
        project_id: int | None = None,
        tag_id: int | None = None,
        deadline_before: datetime | None = None,
        deadline_after: datetime | None = None,
        completed: bool | None = None,
        search: str | None = None,
    ) -> list[Task]:
        """Return up to `limit` tasks matching every given filter,
        newest first, skipping the first `skip`.

        Every filter argument is optional and independent — omitted ones
        (left as None/default) simply aren't applied, so `list()` with
        no arguments is unfiltered ("give me everything"), matching how
        GET /tasks behaves with no query parameters.

        `completed` is a convenience filter layered on top of `status`:
        `completed=True` means `status == DONE`, `completed=False` means
        `status != DONE`. It's independent of the `status` filter (both
        can be supplied at once, combined with AND) rather than a
        special-cased alias for it — "not done" is a broader question
        ("anything still needing attention") than "status is exactly
        todo/in_progress/cancelled", and a caller may want to ask either.

        `search` matches (case-insensitively, via `ilike`) against
        `title` OR `description` — a simple substring search, not a
        full-text index. See docs/architecture.md's "Search and filter"
        section for why that's the deliberate scope for this phase.

        `tag_id` filters via a join through the `task_tags` association
        table — see app.storage.models for why that's a plain Table
        rather than a mapped class.
        """
        stmt = select(Task).order_by(Task.created_at.desc())

        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        if deadline_before is not None:
            stmt = stmt.where(Task.deadline <= deadline_before)
        if deadline_after is not None:
            stmt = stmt.where(Task.deadline >= deadline_after)
        if completed is True:
            stmt = stmt.where(Task.status == TaskStatus.DONE)
        elif completed is False:
            stmt = stmt.where(Task.status != TaskStatus.DONE)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
        if tag_id is not None:
            stmt = stmt.join(task_tags, task_tags.c.task_id == Task.id).where(
                task_tags.c.tag_id == tag_id
            )

        stmt = stmt.offset(skip).limit(limit)
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
