"""Reminder domain exceptions. Plain Python exceptions — see
app.tasks.exceptions for why."""

from __future__ import annotations


class ReminderNotFoundError(Exception):
    """Raised when a reminder lookup by id finds nothing."""

    def __init__(self, reminder_id: int) -> None:
        self.reminder_id = reminder_id
        super().__init__(f"Reminder {reminder_id} not found")
