"""
HabitService — the layer app.interfaces calls for habits.

WHAT THIS DOES
---------------
Wraps HabitRepository/HabitCompletionRepository with the rules a caller
actually wants:
- fetch-or-raise (`HabitNotFoundError`) for a missing habit;
- block recording a completion for an archived habit
  (`ArchivedHabitError`);
- block a second completion on the same calendar date
  (`DuplicateCompletionError`), checked before insert — same
  "clear domain error over a raw DB error" pattern as TagService and
  TaskDependencyService;
- compute streaks/statistics by fetching completion history and handing
  it to the pure functions in `app.habits.streak`, never by reading a
  stored counter (there isn't one — see that module's docstring for why).

`archived_at` on a habit blocks new completions but nothing else: an
archived habit can still be fetched, updated, and its history/statistics
read — the same "archiving blocks new activity, never erases history"
rule as ProjectService (see that module and docs/architecture.md).

HOW TO TEST
------------
See tests/test_habit_service.py for CRUD/archiving/duplicate-completion
rules, and tests/test_habit_streak.py for the pure streak/statistics
math in isolation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.habits.exceptions import ArchivedHabitError, DuplicateCompletionError, HabitNotFoundError
from app.habits.repository import HabitCompletionRepository, HabitRepository
from app.habits.schemas import HabitCreate, HabitUpdate
from app.habits.streak import HabitStatistics, calculate_statistics
from app.storage.models import Habit, HabitCompletion


class HabitService:
    def __init__(self, db: Session) -> None:
        self.repository = HabitRepository(db)
        self.completions = HabitCompletionRepository(db)

    def create_habit(self, data: HabitCreate) -> Habit:
        habit = Habit(**data.model_dump())
        return self.repository.create(habit)

    def get_habit(self, habit_id: int) -> Habit:
        habit = self.repository.get(habit_id)
        if habit is None:
            raise HabitNotFoundError(habit_id)
        return habit

    def list_habits(
        self, *, skip: int = 0, limit: int = 100, include_archived: bool = True
    ) -> list[Habit]:
        return self.repository.list(skip=skip, limit=limit, include_archived=include_archived)

    def update_habit(self, habit_id: int, data: HabitUpdate) -> Habit:
        habit = self.get_habit(habit_id)
        changes = data.model_dump(exclude_unset=True)
        return self.repository.update(habit, changes)

    def archive_habit(self, habit_id: int) -> Habit:
        habit = self.get_habit(habit_id)
        archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.update(habit, {"archived_at": archived_at})

    def unarchive_habit(self, habit_id: int) -> Habit:
        """Restore an archived habit to active status."""
        habit = self.get_habit(habit_id)
        return self.repository.update(habit, {"archived_at": None})

    def delete_habit(self, habit_id: int) -> None:
        """Delete a habit and its completions (cascade)."""
        habit = self.get_habit(habit_id)
        self.repository.delete(habit)

    def record_completion(
        self, habit_id: int, completed_at: datetime | None = None
    ) -> HabitCompletion:
        habit = self.get_habit(habit_id)
        if habit.archived_at is not None:
            raise ArchivedHabitError(habit_id)

        if completed_at is None:
            completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        completed_date = completed_at.date()

        if self.completions.exists_on_date(habit_id, completed_date):
            raise DuplicateCompletionError(habit_id, completed_date)

        completion = HabitCompletion(
            habit_id=habit_id, completed_at=completed_at, completed_date=completed_date
        )
        return self.completions.create(completion)

    def get_completion_history(self, habit_id: int) -> list[HabitCompletion]:
        self.get_habit(habit_id)  # raises HabitNotFoundError if missing
        return self.completions.list_for_habit(habit_id)

    def get_statistics(self, habit_id: int, *, today: date | None = None) -> HabitStatistics:
        habit = self.get_habit(habit_id)
        if today is None:
            today = datetime.now(timezone.utc).date()
        completion_dates = [c.completed_date for c in self.completions.list_for_habit(habit_id)]
        return calculate_statistics(
            frequency=habit.frequency,
            target_count=habit.target_count,
            completion_dates=completion_dates,
            created_date=habit.created_at.date(),
            today=today,
        )
