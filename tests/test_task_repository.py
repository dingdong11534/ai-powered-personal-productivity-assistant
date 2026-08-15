"""Tests for app.tasks.repository.TaskRepository.

Run with: pytest tests/test_task_repository.py -v

Uses the `db_session` fixture (tests/conftest.py) — a real, in-memory
SQLite database — rather than mocking the Session, so these tests also
verify the model's constraints (e.g. defaults, the priority CHECK) do
what's intended.
"""

from app.storage.models import Task, TaskStatus
from app.tasks.repository import TaskRepository


def test_create_assigns_id_and_defaults(db_session):
    repo = TaskRepository(db_session)

    task = repo.create(Task(title="Write report"))

    assert task.id is not None
    assert task.status == TaskStatus.TODO
    assert task.priority == 2
    assert task.created_at is not None
    assert task.updated_at is not None


def test_get_returns_created_task(db_session):
    repo = TaskRepository(db_session)
    created = repo.create(Task(title="Write report"))

    fetched = repo.get(created.id)

    assert fetched is not None
    assert fetched.title == "Write report"


def test_get_returns_none_for_missing_id(db_session):
    repo = TaskRepository(db_session)

    assert repo.get(999) is None


def test_list_returns_all_created_tasks(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="First"))
    repo.create(Task(title="Second"))

    tasks = repo.list()

    assert len(tasks) == 2
    assert {t.title for t in tasks} == {"First", "Second"}


def test_list_respects_skip_and_limit(db_session):
    repo = TaskRepository(db_session)
    for i in range(5):
        repo.create(Task(title=f"Task {i}"))

    page = repo.list(skip=2, limit=2)

    assert len(page) == 2


def test_update_changes_only_given_fields(db_session):
    repo = TaskRepository(db_session)
    task = repo.create(Task(title="Old title", priority=1))

    updated = repo.update(task, {"title": "New title", "status": TaskStatus.DONE})

    assert updated.title == "New title"
    assert updated.status == TaskStatus.DONE
    assert updated.priority == 1  # untouched


def test_delete_removes_task(db_session):
    repo = TaskRepository(db_session)
    task = repo.create(Task(title="Temp"))

    repo.delete(task)

    assert repo.get(task.id) is None
