"""
ScheduleItemRepository — direct, ORM-level CRUD against
`schedule_items`, plus `find_overlapping` (the query
ScheduleService.find_conflicts is built on). Same "dumb, no business
rules" role as every other repository in this project.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import ScheduleItem


class ScheduleItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, item: ScheduleItem) -> ScheduleItem:
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def get(self, item_id: int) -> ScheduleItem | None:
        return self.db.get(ScheduleItem, item_id)

    def list(self, *, skip: int = 0, limit: int = 100, user_id: int | None = None) -> list[ScheduleItem]:
        stmt = select(ScheduleItem).order_by(ScheduleItem.starts_at)
        if user_id is not None:
            stmt = stmt.where(ScheduleItem.user_id == user_id)
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt))

    def find_overlapping(
        self,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_id: int | None = None,
        user_id: int | None = None,
    ) -> list[ScheduleItem]:
        """Items that overlap the [starts_at, ends_at) window — two
        ranges overlap when each starts before the other ends. Excludes
        `exclude_id` so re-checking an item against itself during an
        update doesn't flag it as its own conflict."""
        stmt = select(ScheduleItem).where(
            ScheduleItem.starts_at < ends_at, ScheduleItem.ends_at > starts_at
        )
        if exclude_id is not None:
            stmt = stmt.where(ScheduleItem.id != exclude_id)
        if user_id is not None:
            stmt = stmt.where(ScheduleItem.user_id == user_id)
        return list(self.db.scalars(stmt))

    def update(self, item: ScheduleItem, changes: dict) -> ScheduleItem:
        for field, value in changes.items():
            setattr(item, field, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item: ScheduleItem) -> None:
        self.db.delete(item)
        self.db.commit()
