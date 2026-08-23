"""Tests for app.scheduling.service.ScheduleService.

Run with: pytest tests/test_schedule_service.py -v
"""

from datetime import datetime

import pytest

from app.scheduling.exceptions import InvalidTimeRangeError, ScheduleItemNotFoundError
from app.scheduling.schemas import ScheduleItemCreate, ScheduleItemUpdate
from app.scheduling.service import ScheduleService
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService


def test_create_schedule_item_persists_it(db_session):
    service = ScheduleService(db_session)

    item = service.create_schedule_item(
        ScheduleItemCreate(
            title="Team meeting",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    assert item.id is not None
    assert item.title == "Team meeting"


def test_create_schedule_item_rejects_invalid_range(db_session):
    service = ScheduleService(db_session)

    with pytest.raises(InvalidTimeRangeError):
        service.create_schedule_item(
            ScheduleItemCreate(
                title="Bad range",
                starts_at=datetime(2026, 8, 16, 10, 0),
                ends_at=datetime(2026, 8, 16, 9, 0),
            )
        )


def test_create_schedule_item_rejects_equal_start_and_end(db_session):
    service = ScheduleService(db_session)

    with pytest.raises(InvalidTimeRangeError):
        service.create_schedule_item(
            ScheduleItemCreate(
                title="Zero-length",
                starts_at=datetime(2026, 8, 16, 9, 0),
                ends_at=datetime(2026, 8, 16, 9, 0),
            )
        )


def test_create_schedule_item_with_missing_task_raises(db_session):
    service = ScheduleService(db_session)

    with pytest.raises(TaskNotFoundError):
        service.create_schedule_item(
            ScheduleItemCreate(
                title="x",
                starts_at=datetime(2026, 8, 16, 9, 0),
                ends_at=datetime(2026, 8, 16, 10, 0),
                task_id=999,
            )
        )


def test_create_schedule_item_with_valid_task(db_session):
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="A task"))
    service = ScheduleService(db_session)

    item = service.create_schedule_item(
        ScheduleItemCreate(
            title="Work on task",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
            task_id=task.id,
        )
    )

    assert item.task_id == task.id


def test_get_schedule_item_raises_not_found_for_missing_id(db_session):
    service = ScheduleService(db_session)

    with pytest.raises(ScheduleItemNotFoundError):
        service.get_schedule_item(999)


def test_update_schedule_item_re_validates_range(db_session):
    service = ScheduleService(db_session)
    item = service.create_schedule_item(
        ScheduleItemCreate(
            title="Item",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    with pytest.raises(InvalidTimeRangeError):
        service.update_schedule_item(
            item.id, ScheduleItemUpdate(ends_at=datetime(2026, 8, 16, 8, 0))
        )


def test_update_schedule_item_changes_only_given_fields(db_session):
    service = ScheduleService(db_session)
    item = service.create_schedule_item(
        ScheduleItemCreate(
            title="Old",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    updated = service.update_schedule_item(item.id, ScheduleItemUpdate(title="New"))

    assert updated.title == "New"
    assert updated.starts_at == datetime(2026, 8, 16, 9, 0)


def test_delete_schedule_item_removes_it(db_session):
    service = ScheduleService(db_session)
    item = service.create_schedule_item(
        ScheduleItemCreate(
            title="x",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    service.delete_schedule_item(item.id)

    with pytest.raises(ScheduleItemNotFoundError):
        service.get_schedule_item(item.id)


def test_creating_overlapping_items_is_allowed(db_session):
    """Conflicts are detected, not blocked — see ScheduleService's docstring."""
    service = ScheduleService(db_session)
    service.create_schedule_item(
        ScheduleItemCreate(
            title="First",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    second = service.create_schedule_item(
        ScheduleItemCreate(
            title="Overlapping",
            starts_at=datetime(2026, 8, 16, 9, 30),
            ends_at=datetime(2026, 8, 16, 10, 30),
        )
    )

    assert second.id is not None  # did not raise


def test_find_conflicts_detects_overlap(db_session):
    service = ScheduleService(db_session)
    first = service.create_schedule_item(
        ScheduleItemCreate(
            title="First",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    conflicts = service.find_conflicts(
        datetime(2026, 8, 16, 9, 30), datetime(2026, 8, 16, 10, 30)
    )

    assert [c.id for c in conflicts] == [first.id]


def test_find_conflicts_ignores_back_to_back_items(db_session):
    service = ScheduleService(db_session)
    service.create_schedule_item(
        ScheduleItemCreate(
            title="First",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    conflicts = service.find_conflicts(
        datetime(2026, 8, 16, 10, 0), datetime(2026, 8, 16, 11, 0)
    )

    assert conflicts == []


def test_find_conflicts_excludes_given_id(db_session):
    service = ScheduleService(db_session)
    item = service.create_schedule_item(
        ScheduleItemCreate(
            title="Item",
            starts_at=datetime(2026, 8, 16, 9, 0),
            ends_at=datetime(2026, 8, 16, 10, 0),
        )
    )

    conflicts = service.find_conflicts(
        datetime(2026, 8, 16, 9, 0), datetime(2026, 8, 16, 10, 0), exclude_id=item.id
    )

    assert conflicts == []
