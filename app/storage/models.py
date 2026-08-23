"""
SQLAlchemy ORM models.

WHAT THIS DOES
---------------
Defines the database tables as Python classes: `Project`, `Task` (with
`TaskStatus`), `Tag`, the `task_tags` association table, `TaskDependency`
(Phase 0.2/1), and `Habit`/`HabitCompletion`, `PomodoroSession`,
`Reminder`, `ScheduleItem`, `Notification` (Phase 2).

WHY THESE TYPES/CONSTRAINTS, SPECIFICALLY
----------------------------------------------
- `status: Mapped[TaskStatus]` mapped to a native SQL `ENUM`, not a plain
  string column: an invalid status is rejected by the column type itself.
  SQLite emulates this with a CHECK constraint under the hood, but the
  Python-level guarantee is the same regardless of backend. The same
  reasoning applies to `HabitFrequency`.
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
  in normal use. `PomodoroSession.task_id` and `Reminder.task_id` and
  `ScheduleItem.task_id` use the same `ondelete="SET NULL"` reasoning:
  each is a historical record that should outlive the task it once
  referenced, not be deleted alongside it.
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
- `HabitCompletion.habit_id` uses `ondelete="CASCADE"` (not `SET NULL`)
  because a completion record is meaningless without its habit — unlike
  a task reference on a Pomodoro session or reminder, there's no
  "orphaned but still useful" reading of a completion whose habit no
  longer exists. `UniqueConstraint("habit_id", "completed_date")` is the
  DB-level backstop behind `HabitService`'s duplicate-completion check —
  see that module's docstring for why `completed_date` is a separate,
  explicitly-set column rather than a derived/expression index.
- `ScheduleItem` has a `CheckConstraint("ends_at > starts_at")` — the
  same defense-in-depth pattern as `priority`'s range check: the service
  layer validates this too (see `app.scheduling.service`), but a bad row
  still can't be written even by code that bypasses the service.

HOW TO TEST
------------
Not tested in isolation — behavior (constraints, defaults, cascades) is
exercised through the repository-level tests in tests/, which are closer
to how these models are actually used.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Table,
    UniqueConstraint,
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


class HabitFrequency(str, enum.Enum):
    """How often a habit is expected to be completed. Drives both
    `target_count`'s meaning ("N times per period") and how
    `app.habits.streak` groups completions into periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Habit(Base):
    """Something the user is tracking recurring completions of.

    No hard-delete is exposed (see app.habits.service) — only archiving,
    the same pattern as Project. `archived_at` blocks *new* completions
    (see HabitService) but never touches existing `HabitCompletion` rows,
    for the same "don't silently destroy history" reasoning as Project's
    tasks.
    """

    __tablename__ = "habits"
    __table_args__ = (
        CheckConstraint("target_count >= 1 AND target_count <= 100", name="ck_habits_target_count_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    frequency: Mapped[HabitFrequency] = mapped_column(
        SAEnum(HabitFrequency, name="habit_frequency"), nullable=False
    )
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    completions: Mapped[list["HabitCompletion"]] = relationship(
        back_populates="habit", order_by="HabitCompletion.completed_at"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Habit(id={self.id!r}, name={self.name!r}, frequency={self.frequency!r})"


class HabitCompletion(Base):
    """One recorded instance of a habit being done.

    This table is the *authoritative* record — streaks and statistics
    are always computed from these rows (see app.habits.streak), never
    from a stored counter, so they can be recomputed and are never at
    risk of drifting out of sync with reality.

    `completed_date` (a plain `Date`, separate from the full-precision
    `completed_at` timestamp) exists solely to support
    `UniqueConstraint("habit_id", "completed_date")` — the DB-level
    backstop for "no duplicate completion on the same calendar day"
    (see HabitService.record_completion for the matching service-level
    check, which runs first). It's set once at creation from
    `completed_at.date()` and never updated, so there's no risk of it
    drifting from `completed_at` — an explicit stored column was chosen
    over a SQL expression index (e.g. `date(completed_at)`) to keep this
    to patterns already used elsewhere in the project (plain columns,
    plain UniqueConstraint) rather than introducing expression indexes
    for one table.
    """

    __tablename__ = "habit_completions"
    __table_args__ = (
        UniqueConstraint("habit_id", "completed_date", name="uq_habit_completion_per_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    completed_date: Mapped[date] = mapped_column(Date, nullable=False)

    habit: Mapped[Habit] = relationship(back_populates="completions")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"HabitCompletion(habit_id={self.habit_id!r}, completed_date={self.completed_date!r})"


class PomodoroSession(Base):
    """A single focus session, optionally associated with a Task.

    `ended_at` is nullable — a session is "in progress" while it's null.
    `duration_seconds` is computed and stored at the moment a session
    ends (see app.pomodoro.service), rather than always computed on read
    from `ended_at - started_at`, so a session's recorded duration is
    fixed at the instant it's known, and reading history doesn't require
    redoing that arithmetic on every row every time.
    """

    __tablename__ = "pomodoro_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"PomodoroSession(id={self.id!r}, task_id={self.task_id!r}, "
            f"ended={self.ended_at is not None})"
        )


class Reminder(Base):
    """A one-time reminder, optionally tied to a Task.

    `created_at` isn't in the brief's suggested field list but is added
    for consistency with every other entity in this project — cheap to
    include, useful for audit/ordering, and it would be an odd asymmetry
    to omit it here alone.
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    fired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Reminder(id={self.id!r}, remind_at={self.remind_at!r}, fired={self.fired_at is not None})"


class ScheduleItem(Base):
    """A block of time on the user's local schedule, optionally tied to
    a Task. `CheckConstraint("ends_at > starts_at")` is the DB-level
    backstop behind ScheduleService's own validation — see that
    module's docstring."""

    __tablename__ = "schedule_items"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_schedule_items_valid_range"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"ScheduleItem(id={self.id!r}, title={self.title!r})"


class Notification(Base):
    """An in-app notification record.

    Deliberately just a data record — see app.notifications's package
    docstring for why any OS-level desktop notification dispatch is kept
    out of the core domain and out of scope for this phase.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Free-form origin label (e.g. 'reminder', 'habit'). Not a "
        "foreign key to anything — Phase 2 does not wire reminders or "
        "habits to automatically create notifications (see "
        "docs/architecture.md); this field just leaves room for a "
        "future integration to say where a notification came from.",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Notification(id={self.id!r}, title={self.title!r}, read={self.read_at is not None})"
