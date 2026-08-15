"""Tests for app.tasks.service.TaskService.

Run with: pytest tests/test_task_service.py -v

These are the tests for the *business rule* layer specifically — no
FastAPI, no HTTP — which is what makes them the fastest and most direct
check that e.g. "missing id raises TaskNotFoundError" instead of, say,
returning None (which the repository does, correctly, one layer down).
"""

import pytest

from app.storage.models import TaskStatus
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.schemas import TaskCreate, TaskUpdate
from app.tasks.service import TaskService


def test_create_task_persists_and_returns_it(db_session):
    service = TaskService(db_session)

    task = service.create_task(TaskCreate(title="Write tests"))

    assert task.id is not None
    assert task.title == "Write tests"
    assert task.status == TaskStatus.TODO
    assert task.priority == 2


def test_create_task_honors_provided_fields(db_session):
    service = TaskService(db_session)

    task = service.create_task(
        TaskCreate(title="Ship it", priority=4, status=TaskStatus.IN_PROGRESS)
    )

    assert task.priority == 4
    assert task.status == TaskStatus.IN_PROGRESS


def test_get_task_raises_not_found_for_missing_id(db_session):
    service = TaskService(db_session)

    with pytest.raises(TaskNotFoundError):
        service.get_task(999)


def test_update_task_applies_only_provided_fields(db_session):
    service = TaskService(db_session)
    task = service.create_task(TaskCreate(title="Draft", priority=1))

    updated = service.update_task(task.id, TaskUpdate(status=TaskStatus.DONE))

    assert updated.status == TaskStatus.DONE
    assert updated.title == "Draft"  # untouched
    assert updated.priority == 1  # untouched


def test_update_task_raises_not_found_for_missing_id(db_session):
    service = TaskService(db_session)

    with pytest.raises(TaskNotFoundError):
        service.update_task(999, TaskUpdate(title="x"))


def test_delete_task_removes_it(db_session):
    service = TaskService(db_session)
    task = service.create_task(TaskCreate(title="Temp"))

    service.delete_task(task.id)

    with pytest.raises(TaskNotFoundError):
        service.get_task(task.id)


def test_delete_task_raises_not_found_for_missing_id(db_session):
    service = TaskService(db_session)

    with pytest.raises(TaskNotFoundError):
        service.delete_task(999)
