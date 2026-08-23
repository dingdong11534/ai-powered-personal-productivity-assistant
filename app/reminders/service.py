"""
ReminderService — the layer app.interfaces calls for reminders.

WHAT THIS DOES
---------------
- `create_reminder`: validates `task_id` if given (same cross-domain
  read pattern as PomodoroSessionService — see that module). Accepts
  `remind_at` in the past without complaint: a reminder is just a
  timestamp + message the caller wants surfaced; rejecting a past time
  would only get in the way of legitimate uses (backfilling, testing,
  clock skew) and the "is this overdue" question is already answered by
  `list_due_reminders` regardless of when it was created.
- `mark_fired`: **idempotent** — marking an already-fired reminder as
  fired again is a no-op that returns the reminder's existing state,
  not an error. This mirrors TagService's attach/detach idempotency:
  the caller here will typically be an automated dispatch/polling loop
  (not built yet — see docs/architecture.md's "known limitations"),
  and such a loop needs to be safe to call twice on the same reminder
  (e.g. after a retry) without crashing. There is deliberately no
  `ReminderAlreadyFiredError` for this reason.
- `list_due_reminders` / `list_upcoming_reminders`: read-only queries
  built on `ReminderRepository.list_due`/`list_upcoming` — no business
  logic beyond "not yet fired, and remind_at is <=/>= now".

HOW TO TEST
------------
See tests/test_reminder_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.reminders.exceptions import ReminderNotFoundError
from app.reminders.repository import ReminderRepository
from app.reminders.schemas import ReminderCreate, ReminderUpdate
from app.storage.models import Reminder
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.repository import TaskRepository


class ReminderService:
    def __init__(self, db: Session) -> None:
        self.repository = ReminderRepository(db)
        self.tasks = TaskRepository(db)

    def create_reminder(self, data: ReminderCreate) -> Reminder:
        fields = data.model_dump()
        if fields.get("task_id") is not None and self.tasks.get(fields["task_id"]) is None:
            raise TaskNotFoundError(fields["task_id"])
        reminder = Reminder(**fields)
        return self.repository.create(reminder)

    def get_reminder(self, reminder_id: int) -> Reminder:
        reminder = self.repository.get(reminder_id)
        if reminder is None:
            raise ReminderNotFoundError(reminder_id)
        return reminder

    def list_reminders(self, *, skip: int = 0, limit: int = 100) -> list[Reminder]:
        return self.repository.list(skip=skip, limit=limit)

    def list_upcoming_reminders(self, *, as_of: datetime | None = None) -> list[Reminder]:
        as_of = as_of or datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.list_upcoming(as_of=as_of)

    def list_due_reminders(self, *, as_of: datetime | None = None) -> list[Reminder]:
        as_of = as_of or datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.list_due(as_of=as_of)

    def update_reminder(self, reminder_id: int, data: ReminderUpdate) -> Reminder:
        reminder = self.get_reminder(reminder_id)
        changes = data.model_dump(exclude_unset=True)
        if "task_id" in changes and changes["task_id"] is not None:
            if self.tasks.get(changes["task_id"]) is None:
                raise TaskNotFoundError(changes["task_id"])
        return self.repository.update(reminder, changes)

    def mark_fired(self, reminder_id: int) -> Reminder:
        reminder = self.get_reminder(reminder_id)
        if reminder.fired_at is not None:
            return reminder  # idempotent — see module docstring
        fired_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.update(reminder, {"fired_at": fired_at})

    def delete_reminder(self, reminder_id: int) -> None:
        reminder = self.get_reminder(reminder_id)
        self.repository.delete(reminder)
