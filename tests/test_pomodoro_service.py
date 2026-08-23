"""Tests for app.pomodoro.service.PomodoroSessionService.

Run with: pytest tests/test_pomodoro_service.py -v
"""

import pytest

from app.pomodoro.exceptions import PomodoroSessionNotFoundError, SessionAlreadyEndedError
from app.pomodoro.service import PomodoroSessionService
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService


def test_start_session_without_task(db_session):
    service = PomodoroSessionService(db_session)

    session = service.start_session()

    assert session.id is not None
    assert session.task_id is None
    assert session.ended_at is None
    assert session.interrupted is False


def test_start_session_with_valid_task(db_session):
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Write report"))
    service = PomodoroSessionService(db_session)

    session = service.start_session(task_id=task.id)

    assert session.task_id == task.id


def test_start_session_with_missing_task_raises(db_session):
    service = PomodoroSessionService(db_session)

    with pytest.raises(TaskNotFoundError):
        service.start_session(task_id=999)


def test_get_session_raises_not_found_for_missing_id(db_session):
    service = PomodoroSessionService(db_session)

    with pytest.raises(PomodoroSessionNotFoundError):
        service.get_session(999)


def test_end_session_sets_ended_at_and_duration(db_session):
    service = PomodoroSessionService(db_session)
    session = service.start_session()

    ended = service.end_session(session.id)

    assert ended.ended_at is not None
    assert ended.duration_seconds is not None
    assert ended.duration_seconds >= 0
    assert ended.interrupted is False


def test_end_session_with_interrupted_flag(db_session):
    service = PomodoroSessionService(db_session)
    session = service.start_session()

    ended = service.end_session(session.id, interrupted=True)

    assert ended.interrupted is True
    assert ended.ended_at is not None


def test_end_session_twice_raises(db_session):
    service = PomodoroSessionService(db_session)
    session = service.start_session()
    service.end_session(session.id)

    with pytest.raises(SessionAlreadyEndedError):
        service.end_session(session.id)


def test_end_session_raises_not_found_for_missing_id(db_session):
    service = PomodoroSessionService(db_session)

    with pytest.raises(PomodoroSessionNotFoundError):
        service.end_session(999)


def test_list_sessions_filters_by_task(db_session):
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Task A"))
    service = PomodoroSessionService(db_session)
    service.start_session(task_id=task.id)
    service.start_session()  # no task

    sessions = service.list_sessions(task_id=task.id)

    assert len(sessions) == 1
    assert sessions[0].task_id == task.id


def test_list_sessions_returns_all_without_filter(db_session):
    service = PomodoroSessionService(db_session)
    service.start_session()
    service.start_session()

    sessions = service.list_sessions()

    assert len(sessions) == 2
