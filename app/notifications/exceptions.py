"""Notification domain exceptions. Plain Python exceptions — see
app.tasks.exceptions for why."""

from __future__ import annotations


class NotificationNotFoundError(Exception):
    """Raised when a notification lookup by id finds nothing."""

    def __init__(self, notification_id: int) -> None:
        self.notification_id = notification_id
        super().__init__(f"Notification {notification_id} not found")
