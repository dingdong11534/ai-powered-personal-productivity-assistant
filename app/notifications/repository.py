"""
NotificationRepository — direct, ORM-level CRUD against `notifications`.
Same "dumb, no business rules" role as every other repository in this
project.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
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
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        unread_only: bool = False,
        search: str | None = None,
        user_id: int | None = None,
    ) -> list[Notification]:
        stmt = select(Notification).order_by(Notification.created_at.desc())
        if user_id is not None:
            stmt = stmt.where((Notification.user_id == user_id) | (Notification.user_id.is_(None)))
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        if search and search.strip():
            q = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    func.coalesce(Notification.title, "").ilike(q),
                    func.coalesce(Notification.body, "").ilike(q),
                    func.coalesce(Notification.source, "").ilike(q),
                )
            )
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt))

    def update(self, notification: Notification, changes: dict) -> Notification:
        for field, value in changes.items():
            setattr(notification, field, value)
        self.db.commit()
        self.db.refresh(notification)
        return notification
