"""Tests for app.reminders.service.ReminderService.

Run with: pytest tests/test_reminder_service.py -v
"""

from datetime import datetime, timedelta

import pytest

from app.reminders.exceptions import ReminderNotFoundError
from app.reminders.schemas import ReminderCreate, ReminderUpdate
from app.reminders.service import ReminderService
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService

NOW = datetime(2026, 8, 16, 12, 0, 0)


def test_create_reminder_persists_it(db_session):
    service = ReminderService(db_session)

    reminder = service.create_reminder(
        ReminderCreate(remind_at=NOW + timedelta(hours=1), message="Call the dentist")
    )

    assert reminder.id is not None
    assert reminder.message == "Call the dentist"
    assert reminder.fired_at is None


def test_create_reminder_with_valid_task(db_session):
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="A task"))
    service = ReminderService(db_session)

    reminder = service.create_reminder(
        ReminderCreate(task_id=task.id, remind_at=NOW, message="Reminder")
    )

    assert reminder.task_id == task.id


def test_create_reminder_with_missing_task_raises(db_session):
    service = ReminderService(db_session)

    with pytest.raises(TaskNotFoundError):
        service.create_reminder(ReminderCreate(task_id=999, remind_at=NOW, message="x"))


def test_create_reminder_in_the_past_is_allowed(db_session):
    service = ReminderService(db_session)

    reminder = service.create_reminder(
        ReminderCreate(remind_at=NOW - timedelta(days=1), message="Overdue reminder")
    )

    assert reminder.id is not None


def test_get_reminder_raises_not_found_for_missing_id(db_session):
    service = ReminderService(db_session)

    with pytest.raises(ReminderNotFoundError):
        service.get_reminder(999)


def test_update_reminder_applies_only_provided_fields(db_session):
    service = ReminderService(db_session)
    reminder = service.create_reminder(ReminderCreate(remind_at=NOW, message="Old message"))

    updated = service.update_reminder(reminder.id, ReminderUpdate(message="New message"))

    assert updated.message == "New message"
    assert updated.remind_at == NOW


def test_list_due_reminders_returns_only_past_unfired(db_session):
    service = ReminderService(db_session)
    past = service.create_reminder(
        ReminderCreate(remind_at=NOW - timedelta(hours=1), message="Past")
    )
    service.create_reminder(ReminderCreate(remind_at=NOW + timedelta(hours=1), message="Future"))

    due = service.list_due_reminders(as_of=NOW)

    assert [r.id for r in due] == [past.id]


def test_list_upcoming_reminders_returns_only_future_unfired(db_session):
    service = ReminderService(db_session)
    service.create_reminder(ReminderCreate(remind_at=NOW - timedelta(hours=1), message="Past"))
    future = service.create_reminder(
        ReminderCreate(remind_at=NOW + timedelta(hours=1), message="Future")
    )

    upcoming = service.list_upcoming_reminders(as_of=NOW)

    assert [r.id for r in upcoming] == [future.id]


def test_mark_fired_sets_fired_at(db_session):
    service = ReminderService(db_session)
    reminder = service.create_reminder(ReminderCreate(remind_at=NOW, message="x"))

    fired = service.mark_fired(reminder.id)

    assert fired.fired_at is not None


def test_mark_fired_twice_is_idempotent(db_session):
    service = ReminderService(db_session)
    reminder = service.create_reminder(ReminderCreate(remind_at=NOW, message="x"))
    first = service.mark_fired(reminder.id)

    second = service.mark_fired(reminder.id)  # should not raise

    assert second.fired_at == first.fired_at


def test_fired_reminder_excluded_from_due_list(db_session):
    service = ReminderService(db_session)
    reminder = service.create_reminder(
        ReminderCreate(remind_at=NOW - timedelta(hours=1), message="x")
    )
    service.mark_fired(reminder.id)

    due = service.list_due_reminders(as_of=NOW)

    assert due == []


def test_delete_reminder_removes_it(db_session):
    service = ReminderService(db_session)
    reminder = service.create_reminder(ReminderCreate(remind_at=NOW, message="x"))

    service.delete_reminder(reminder.id)

    with pytest.raises(ReminderNotFoundError):
        service.get_reminder(reminder.id)


def test_delete_reminder_raises_not_found_for_missing_id(db_session):
    service = ReminderService(db_session)

    with pytest.raises(ReminderNotFoundError):
        service.delete_reminder(999)
