"""
SQLAlchemy ORM models.

WHAT THIS DOES
---------------
Defines the database tables as Python classes: `Project`, `Task` (with
`TaskStatus`), `Tag`, the `task_tags` association table, and
`TaskDependency`. The remaining entities in docs/architecture.md's schema
proposal (Habit, PomodoroSession, Reminder, ...) are added as their owning
phase reaches them.

WHY THESE TYPES/CONSTRAINTS, SPECIFICALLY
----------------------------------------------
- `status: Mapped[TaskStatus]` mapped to a native SQL `ENUM`, not a plain
  string column: an invalid status is rejected by the column type itself.
  SQLite emulates this with a CHECK constraint under the hood, but the
  Python-level guarantee is the same regardless of backend.
- `priority` is a plain `Integer` plus an explicit `CheckConstraint`
  (1-4), not a second enum: priority is fundamentally ordered, which an
  integer expresses directly (`priority < 3` sorts and compares
  naturally) where an enum would need extra code for the same ordering.
  Meaning, per Phase 1: **1 = Critical, 2 = High, 3 = Medium, 4 = Low** —
  lower number = more urgent. See `PRIORITY_LABELS` below. The column's
  default of `2` ("High") is left unchanged from Phase 0.2 rather than
  quietly reinterpreted as "Medium" under the new labels — see
  docs/architecture.md's Phase 1 section for the reasoning and how to
  revisit it.
- `created_at`/`updated_at` use `server_default=func.now()` /
  `onupdate=func.now()` — the database sets these, not application code.
- `Task.project_id` is nullable: a task does not have to belong to a
  project. Its foreign key uses `ondelete="SET NULL"` — if a `Project`
  row were ever removed by any means, its tasks become unassigned rather
  than being deleted or left referencing a dead id. In practice the
  Project API never exposes a hard delete (only archive — see
  `app.projects.service`), so this is a defensive default for a
  situation the current API doesn't even allow, not something exercised
  in normal use.
- `task_tags` is a plain `Table` (an association table), not a mapped
  class: it carries no data beyond the two foreign keys, so a full ORM
  class would be unused ceremony. Its composite primary key
  `(task_id, tag_id)` is what makes a duplicate attach a no-op at the DB
  level as a second line of defense behind the service-layer idempotency
  check (see `app.tasks.tag_service`).
- `TaskDependency` similarly uses a composite primary key
  `(task_id, depends_on_task_id)` — the same duplicate-prevention
  reasoning as `task_tags`. Both foreign keys use `ondelete="CASCADE"`:
  deleting a `Task` should take its own dependency edges with it (they're
  meaningless without the task), which is different from the
  `project_id` case above where the *other* side of the relationship
  (the task) must survive.

HOW TO TEST
------------
Not tested in isolation — behavior (constraints, defaults, cascades) is
exercised through the repository-level tests in tests/, which are closer
to how these models are actually used.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Table,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.database import Base

# 1 = Critical, 2 = High, 3 = Medium, 4 = Low — lower number = more urgent.
# Kept as a plain dict rather than a second enum (see module docstring);
# used in tests and available for any future API response that wants to
# surface a human-readable label alongside the raw integer.
PRIORITY_LABELS: dict[int, str] = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}


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


class Project(Base):
    """A container tasks can optionally belong to.

    No hard-delete is exposed anywhere in this project (see
    app.projects.service) — only archiving (`archived_at` set). That's
    what makes `Task.project_id`'s `ondelete="SET NULL"` a defensive
    fallback rather than a path normal use ever exercises: tasks stay
    attached to their (possibly archived) project indefinitely unless a
    task is explicitly reassigned.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Free-form color value (e.g. a hex code or a named color) for "
        "future UI use. Not validated at this layer — a malformed value "
        "can't corrupt data, only display oddly, so validating it would "
        "be complexity a Phase 3 UI is better placed to add once it "
        "knows what format it actually wants.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        doc="Set when the project is archived; NULL means active. A "
        "timestamp rather than a boolean so 'when' is preserved for free.",
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"Project(id={self.id!r}, name={self.name!r}, "
            f"archived={self.archived_at is not None})"
        )


class Task(Base):
    """A single to-do item, optionally belonging to a Project, carrying
    zero or more Tags, and optionally depending on other Tasks."""

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
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project | None] = relationship(back_populates="tasks")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="task_tags", back_populates="tasks", order_by="Tag.name"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Task(id={self.id!r}, title={self.title!r}, status={self.status!r})"


class Tag(Base):
    """A short label that can be attached to any number of tasks."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    tasks: Mapped[list[Task]] = relationship(secondary="task_tags", back_populates="tags")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Tag(id={self.id!r}, name={self.name!r})"


# Association table for the Task <-> Tag many-to-many relationship. A plain
# Table, not a mapped class — see module docstring for why. The composite
# primary key doubles as the "no duplicate attachment" constraint.
task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class TaskDependency(Base):
    """An edge meaning `task` cannot be completed until `depends_on` is.

    `task_id` and `depends_on_task_id` together form the primary key,
    which is what makes attempting to add the same dependency twice a
    no-op at the DB level (a second line of defense behind
    TaskDependencyService's own existence check — see
    app.tasks.dependency_service for why a Python-level check happens
    first rather than relying on catching an IntegrityError).

    Self-dependencies (`task_id == depends_on_task_id`) and cycles
    (A depends on B depends on ... depends on A) are NOT prevented at
    this layer — SQL has no clean way to express "no cycles in this
    edge set" as a constraint. Both are validated in
    app.tasks.dependency_service before a row is ever inserted. See that
    module for the algorithm.
    """

    __tablename__ = "task_dependencies"

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"TaskDependency(task_id={self.task_id!r}, "
            f"depends_on_task_id={self.depends_on_task_id!r})"
        )
