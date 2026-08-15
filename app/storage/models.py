"""
SQLAlchemy ORM models.

WHAT THIS DOES
---------------
Defines the database tables as Python classes. Currently just `Task`
(and its `TaskStatus` enum) — the schema proposal in docs/architecture.md
lists the rest, added as their owning phase reaches them.

WHY THESE TYPES/CONSTRAINTS, SPECIFICALLY
----------------------------------------------
- `status: Mapped[TaskStatus]` mapped to a native SQL `ENUM`, not a plain
  string column: an invalid status ("donee", empty string, ...) is
  rejected by the column type itself, not caught later by app code that
  might not check every write path. SQLite doesn't have a real ENUM type
  under the hood — SQLAlchemy emulates it with a CHECK constraint — but
  the Python-level guarantee (a `TaskStatus` member, not any string) is
  the same regardless of backend, and the constraint still applies at
  the SQLite layer too.
- `priority` is a plain `Integer` plus an explicit `CheckConstraint`
  (1-4), not a second enum: priority is fundamentally ordered ("more
  urgent than"), which an integer expresses directly (`priority > 2`
  sorts and compares naturally) where an enum would need extra code to
  get the same ordering. The CheckConstraint keeps out-of-range values
  from being written directly at the DB layer, as a second line of
  defense behind the Pydantic schema's `ge=1, le=4` validation.
- `created_at`/`updated_at` use `server_default=func.now()` /
  `onupdate=func.now()` — the *database* sets these timestamps, not
  application code. That means they're correct even for a row inserted
  by something other than this app (a future migration script, a manual
  SQL fix), and there's no risk of a forgotten `datetime.now()` call
  producing a null timestamp.
- `title` is `String(200)` (bounded) while `description` is `Text`
  (unbounded): a title is a short label the UI will want to display
  inline and truncate predictably; a description is free-form content
  with no natural length ceiling. Encoding that distinction in the
  column type documents the intent even before any UI exists.

WHAT'S DELIBERATELY NOT HERE YET
-------------------------------------
`project_id`, `TaskDependency`, `Tag`/`TaskTag` from the schema proposal —
those arrive when app.tasks actually implements projects/dependencies/
tags, not before. Adding foreign keys to tables that don't exist yet
isn't possible anyway, but it's worth being explicit that this is Task
in isolation, matching the Phase 0.2 scope (Task module only).

HOW TO TEST
------------
Not tested in isolation — its behavior (constraints, defaults) is
exercised through tests/test_task_repository.py, which is closer to how
the model is actually used and catches constraint violations the same
way production code would.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.database import Base


class TaskStatus(str, enum.Enum):
    """A task's lifecycle state.

    Inherits from `str` as well as `Enum` so a TaskStatus member compares
    equal to its plain string value (`TaskStatus.TODO == "todo"`) and
    serializes cleanly through Pydantic/JSON without a custom encoder.
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class Task(Base):
    """A single to-do item.

    Matches the `Task` entity from docs/architecture.md's schema
    proposal, minus fields (project_id, dependencies, tags) that belong
    to features not yet built.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("priority >= 1 AND priority <= 4", name="ck_tasks_priority_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
    )
    # 1 = low, 2 = normal, 3 = high, 4 = urgent.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Task(id={self.id!r}, title={self.title!r}, status={self.status!r})"
