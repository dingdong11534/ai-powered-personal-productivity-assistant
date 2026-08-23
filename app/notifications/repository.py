"""
NotificationRepository — direct, ORM-level CRUD against `notifications`.
Same "dumb, no business rules" role as every other repository in this
project.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, notification: Notification) -> Notification:
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def get(self, notification_id: int) -> Notification | None:
        return self.db.get(Notification, notification_id)

    def list(
        self, *, skip: int = 0, limit: int = 100, unread_only: bool = False
    ) -> list[Notification]:
        stmt = select(Notification).order_by(Notification.created_at.desc())
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt))

    def update(self, notification: Notification, changes: dict) -> Notification:
        for field, value in changes.items():
            setattr(notification, field, value)
        self.db.commit()
        self.db.refresh(notification)
        return notification
