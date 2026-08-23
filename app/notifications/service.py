"""
NotificationService — the layer app.interfaces calls for notifications.

Deliberately the thinnest service in this project: creation and
read/unread state have no business rules beyond "does it exist" — see
app.notifications's package docstring for why any real dispatch/delivery
logic is out of scope here.

`mark_read`/`mark_unread` are idempotent (setting `read_at` when it's
already set, or clearing it when it's already null, both just succeed)
— same reasoning as ReminderService.mark_fired: a client shouldn't have
to check current state before flipping it.

HOW TO TEST
------------
See tests/test_notification_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.notifications.exceptions import NotificationNotFoundError
from app.notifications.repository import NotificationRepository
from app.notifications.schemas import NotificationCreate
from app.storage.models import Notification


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.repository = NotificationRepository(db)

    def create_notification(self, data: NotificationCreate) -> Notification:
        notification = Notification(**data.model_dump())
        return self.repository.create(notification)

    def get_notification(self, notification_id: int) -> Notification:
        notification = self.repository.get(notification_id)
        if notification is None:
            raise NotificationNotFoundError(notification_id)
        return notification

    def list_notifications(
        self, *, skip: int = 0, limit: int = 100, unread_only: bool = False
    ) -> list[Notification]:
        return self.repository.list(skip=skip, limit=limit, unread_only=unread_only)

    def mark_read(self, notification_id: int) -> Notification:
        notification = self.get_notification(notification_id)
        if notification.read_at is not None:
            return notification  # idempotent
        read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.update(notification, {"read_at": read_at})

    def mark_unread(self, notification_id: int) -> Notification:
        notification = self.get_notification(notification_id)
        if notification.read_at is None:
            return notification  # idempotent
        return self.repository.update(notification, {"read_at": None})
