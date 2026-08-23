"""Tests for app.habits.service.HabitService.

Run with: pytest tests/test_habit_service.py -v
"""

from datetime import datetime

import pytest

from app.habits.exceptions import ArchivedHabitError, DuplicateCompletionError, HabitNotFoundError
from app.habits.schemas import HabitCreate, HabitUpdate
from app.habits.service import HabitService
from app.storage.models import HabitFrequency


def test_create_habit_persists_and_returns_it(db_session):
    service = HabitService(db_session)

    habit = service.create_habit(
        HabitCreate(name="Drink water", frequency=HabitFrequency.DAILY, target_count=3)
    )

    assert habit.id is not None
    assert habit.name == "Drink water"
    assert habit.frequency == HabitFrequency.DAILY
    assert habit.target_count == 3
    assert habit.archived_at is None


def test_create_habit_defaults_target_count_to_one(db_session):
    service = HabitService(db_session)

    habit = service.create_habit(HabitCreate(name="Meditate", frequency=HabitFrequency.DAILY))

    assert habit.target_count == 1


def test_get_habit_raises_not_found_for_missing_id(db_session):
    service = HabitService(db_session)

    with pytest.raises(HabitNotFoundError):
        service.get_habit(999)


def test_update_habit_applies_only_provided_fields(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Old", frequency=HabitFrequency.DAILY))

    updated = service.update_habit(habit.id, HabitUpdate(name="New"))

    assert updated.name == "New"
    assert updated.frequency == HabitFrequency.DAILY  # untouched


def test_update_habit_raises_not_found_for_missing_id(db_session):
    service = HabitService(db_session)

    with pytest.raises(HabitNotFoundError):
        service.update_habit(999, HabitUpdate(name="x"))


def test_archive_habit_sets_archived_at(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))

    archived = service.archive_habit(habit.id)

    assert archived.archived_at is not None


def test_archive_habit_raises_not_found_for_missing_id(db_session):
    service = HabitService(db_session)

    with pytest.raises(HabitNotFoundError):
        service.archive_habit(999)


def test_list_habits_excludes_archived_when_requested(db_session):
    service = HabitService(db_session)
    active = service.create_habit(HabitCreate(name="Active", frequency=HabitFrequency.DAILY))
    archived = service.create_habit(
        HabitCreate(name="Will archive", frequency=HabitFrequency.DAILY)
    )
    service.archive_habit(archived.id)

    habits = service.list_habits(include_archived=False)

    assert [h.id for h in habits] == [active.id]


def test_record_completion_persists_it(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))

    completion = service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 9, 0))

    assert completion.id is not None
    assert completion.habit_id == habit.id
    assert completion.completed_date == datetime(2026, 8, 16, 9, 0).date()


def test_record_completion_defaults_to_now(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))

    completion = service.record_completion(habit.id)

    assert completion.completed_at is not None
    assert completion.completed_date is not None


def test_record_completion_raises_not_found_for_missing_habit(db_session):
    service = HabitService(db_session)

    with pytest.raises(HabitNotFoundError):
        service.record_completion(999)


def test_record_completion_rejects_duplicate_same_day(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 9, 0))

    with pytest.raises(DuplicateCompletionError):
        service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 21, 0))  # same day


def test_record_completion_allows_different_days(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 9, 0))

    second = service.record_completion(habit.id, completed_at=datetime(2026, 8, 17, 9, 0))

    assert second.id is not None


def test_record_completion_rejects_for_archived_habit(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))
    service.archive_habit(habit.id)

    with pytest.raises(ArchivedHabitError):
        service.record_completion(habit.id)


def test_get_completion_history_returns_recorded_completions(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 15, 9, 0))
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 9, 0))

    history = service.get_completion_history(habit.id)

    assert len(history) == 2


def test_get_completion_history_raises_not_found_for_missing_habit(db_session):
    service = HabitService(db_session)

    with pytest.raises(HabitNotFoundError):
        service.get_completion_history(999)


def test_archived_habit_history_remains_readable(db_session):
    """Archiving blocks new completions but never hides existing history."""
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 9, 0))
    service.archive_habit(habit.id)

    history = service.get_completion_history(habit.id)

    assert len(history) == 1


def test_get_statistics_computed_from_history(db_session):
    service = HabitService(db_session)
    habit = service.create_habit(HabitCreate(name="Habit", frequency=HabitFrequency.DAILY))
    habit.created_at = datetime(2026, 8, 15, 9, 0)
    db_session.commit()
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 15, 9, 0))
    service.record_completion(habit.id, completed_at=datetime(2026, 8, 16, 9, 0))

    stats = service.get_statistics(habit.id, today=datetime(2026, 8, 16).date())

    assert stats.total_completions == 2
    assert stats.current_streak == 2


def test_get_statistics_raises_not_found_for_missing_habit(db_session):
    service = HabitService(db_session)

    with pytest.raises(HabitNotFoundError):
        service.get_statistics(999)
