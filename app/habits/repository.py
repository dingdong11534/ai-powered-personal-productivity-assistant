"""
HabitRepository and HabitCompletionRepository — direct, ORM-level CRUD.

Two small classes in one file rather than two files: they're both facets
of a single aggregate (a Habit and its own completion log), always used
together by HabitService, unlike Tag (app.tasks.tag_repository), which
is an independently addressable resource with its own top-level API and
so earned its own file.

Same "dumb, no business rules" role as every other repository in this
project — see app.tasks.repository's docstring for the layering
rationale. HabitService owns duplicate-completion checking and the
archived-habit rule.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Habit, HabitCompletion


class HabitRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, habit: Habit) -> Habit:
        self.db.add(habit)
        self.db.commit()
        self.db.refresh(habit)
        return habit

    def get(self, habit_id: int) -> Habit | None:
        return self.db.get(Habit, habit_id)

    def list(
        self, *, skip: int = 0, limit: int = 100, include_archived: bool = True
    ) -> list[Habit]:
        stmt = select(Habit).order_by(Habit.created_at.desc()).offset(skip).limit(limit)
        if not include_archived:
            stmt = stmt.where(Habit.archived_at.is_(None))
        return list(self.db.scalars(stmt))

    def update(self, habit: Habit, changes: dict) -> Habit:
        for field, value in changes.items():
            setattr(habit, field, value)
        self.db.commit()
        self.db.refresh(habit)
        return habit

    def delete(self, habit: Habit) -> None:
        self.db.delete(habit)
        self.db.commit()


class HabitCompletionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def exists_on_date(self, habit_id: int, completed_date: date) -> bool:
        stmt = select(HabitCompletion).where(
            HabitCompletion.habit_id == habit_id,
            HabitCompletion.completed_date == completed_date,
        )
        return self.db.scalars(stmt).first() is not None

    def create(self, completion: HabitCompletion) -> HabitCompletion:
        self.db.add(completion)
        self.db.commit()
        self.db.refresh(completion)
        return completion

    def list_for_habit(self, habit_id: int) -> list[HabitCompletion]:
        stmt = (
            select(HabitCompletion)
            .where(HabitCompletion.habit_id == habit_id)
            .order_by(HabitCompletion.completed_date)
        )
        return list(self.db.scalars(stmt))
