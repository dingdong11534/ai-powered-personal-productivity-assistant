"""
ScheduleService — the layer app.interfaces calls for schedule items.

WHAT THIS DOES
---------------
- `create_schedule_item` / `update_schedule_item`: validate that the
  resulting time range has `ends_at > starts_at` (raises
  `InvalidTimeRangeError`, HTTP 400 — the DB's own CheckConstraint on
  `schedule_items` is the backstop behind this, same defense-in-depth
  pattern as `priority`). Also validates `task_id` if given, same
  cross-domain read pattern as PomodoroSessionService/ReminderService.
- `find_conflicts`: returns any existing items that overlap a given
  time range.

WHY CONFLICTS ARE DETECTED, NOT BLOCKED
--------------------------------------------
`create_schedule_item` does **not** call `find_conflicts` and does
**not** reject an overlapping item. This mirrors how real calendar
tools behave (Google Calendar, Outlook, etc. all allow double-booking
and just show it, rather than refusing the second event) — overlap is
often intentional (a task block inside a longer meeting, a tentative
placeholder) and a hard block would need an escape hatch ("create
anyway") that adds complexity nothing in this phase's brief asked for.
`find_conflicts` is exposed as its own method — testable directly (see
tests/test_schedule_service.py) and reachable via
`GET /schedule/conflicts?starts_at=&ends_at=` — as a *query* a caller
(a future UI, or the person using the API directly) can run before or
after creating something, without the server silently enforcing it. If
a stricter "reject overlapping items" policy turns out to be wanted,
that's a small, deliberate change to `create_schedule_item` later, not
a default assumed now.

HOW TO TEST
------------
See tests/test_schedule_service.py.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.scheduling.exceptions import InvalidTimeRangeError, ScheduleItemNotFoundError
from app.scheduling.repository import ScheduleItemRepository
from app.scheduling.schemas import ScheduleItemCreate, ScheduleItemUpdate
from app.storage.models import ScheduleItem
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.repository import TaskRepository


class ScheduleService:
    def __init__(self, db: Session) -> None:
        self.repository = ScheduleItemRepository(db)
        self.tasks = TaskRepository(db)

    def create_schedule_item(self, data: ScheduleItemCreate, user_id: int | None = None) -> ScheduleItem:
        fields = data.model_dump()
        self._validate_range(fields["starts_at"], fields["ends_at"])
        if fields.get("task_id") is not None and self.tasks.get(fields["task_id"]) is None:
            raise TaskNotFoundError(fields["task_id"])
        if user_id is not None:
            fields["user_id"] = user_id
        item = ScheduleItem(**fields)
        return self.repository.create(item)

    def get_schedule_item(self, item_id: int) -> ScheduleItem:
        item = self.repository.get(item_id)
        if item is None:
            raise ScheduleItemNotFoundError(item_id)
        return item

    def list_schedule_items(
        self, *, skip: int = 0, limit: int = 100, user_id: int | None = None
    ) -> list[ScheduleItem]:
        return self.repository.list(skip=skip, limit=limit, user_id=user_id)

    def update_schedule_item(self, item_id: int, data: ScheduleItemUpdate) -> ScheduleItem:
        item = self.get_schedule_item(item_id)
        changes = data.model_dump(exclude_unset=True)

        resulting_starts_at = changes.get("starts_at", item.starts_at)
        resulting_ends_at = changes.get("ends_at", item.ends_at)
        if "starts_at" in changes or "ends_at" in changes:
            self._validate_range(resulting_starts_at, resulting_ends_at)

        if "task_id" in changes and changes["task_id"] is not None:
            if self.tasks.get(changes["task_id"]) is None:
                raise TaskNotFoundError(changes["task_id"])

        return self.repository.update(item, changes)

    def delete_schedule_item(self, item_id: int) -> None:
        item = self.get_schedule_item(item_id)
        self.repository.delete(item)

    def find_conflicts(
        self,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_id: int | None = None,
        user_id: int | None = None,
    ) -> list[ScheduleItem]:
        """Existing items that overlap [starts_at, ends_at). See module
        docstring for why this is a query, not an enforced block."""
        return self.repository.find_overlapping(
            starts_at, ends_at, exclude_id=exclude_id, user_id=user_id
        )

    def find_all_conflicts(self, user_id: int | None = None) -> list[ScheduleItem]:
        """Find all schedule items that overlap with at least one other item."""
        items = self.repository.list(limit=500, user_id=user_id)
        conflicting_ids: set[int] = set()
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a.starts_at < b.ends_at and a.ends_at > b.starts_at:
                    conflicting_ids.add(a.id)
                    conflicting_ids.add(b.id)
        return [item for item in items if item.id in conflicting_ids]

    def _validate_range(self, starts_at: datetime, ends_at: datetime) -> None:
        if ends_at <= starts_at:
            raise InvalidTimeRangeError()
