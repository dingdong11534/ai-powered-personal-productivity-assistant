"""
ReminderRepository — direct, ORM-level CRUD against `reminders`, plus
the two read queries ReminderService's "identify due/upcoming reminders"
methods are built from. Same "dumb, no business rules" role as every
other repository in this project.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Reminder


class ReminderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, reminder: Reminder) -> Reminder:
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def get(self, reminder_id: int) -> Reminder | None:
        return self.db.get(Reminder, reminder_id)

    def list(self, *, skip: int = 0, limit: int = 100, user_id: int | None = None) -> list[Reminder]:
        stmt = select(Reminder).order_by(Reminder.remind_at)
        if user_id is not None:
            stmt = stmt.where(Reminder.user_id == user_id)
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt))

    def list_upcoming(self, *, as_of: datetime, user_id: int | None = None) -> list[Reminder]:
        """Not-yet-fired reminders scheduled at or after `as_of`,
        soonest first."""
        stmt = select(Reminder).where(Reminder.fired_at.is_(None), Reminder.remind_at >= as_of)
        if user_id is not None:
            stmt = stmt.where(Reminder.user_id == user_id)
        stmt = stmt.order_by(Reminder.remind_at)
        return list(self.db.scalars(stmt))

    def list_due(self, *, as_of: datetime, user_id: int | None = None) -> list[Reminder]:
        """Not-yet-fired reminders whose time has already come (at or
        before `as_of`) — the set a dispatcher would need to fire."""
        stmt = select(Reminder).where(Reminder.fired_at.is_(None), Reminder.remind_at <= as_of)
        if user_id is not None:
            stmt = stmt.where(Reminder.user_id == user_id)
        stmt = stmt.order_by(Reminder.remind_at)
        return list(self.db.scalars(stmt))

    def update(self, reminder: Reminder, changes: dict) -> Reminder:
        for field, value in changes.items():
            setattr(reminder, field, value)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def delete(self, reminder: Reminder) -> None:
        self.db.delete(reminder)
        self.db.commit()
