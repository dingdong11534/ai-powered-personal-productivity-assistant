"""Tests for the Phase 1 additions to app.tasks.service.TaskService:
project validation and dependency-blocked completion.

Run with: pytest tests/test_task_service_phase1.py -v

Pre-existing CRUD/not-found behavior from Phase 0.2 stays in
tests/test_task_service.py — this file only covers what's new.
"""

import pytest

from app.projects.exceptions import ArchivedProjectError, ProjectNotFoundError
from app.projects.schemas import ProjectCreate
from app.projects.service import ProjectService
from app.storage.models import TaskStatus
from app.tasks.dependency_service import TaskDependencyService
from app.tasks.exceptions import UnresolvedDependencyError
from app.tasks.schemas import TaskCreate, TaskUpdate
from app.tasks.service import TaskService


def test_create_task_with_valid_project_id_succeeds(db_session):
    project_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    project = project_service.create_project(ProjectCreate(name="Home Renovation"))

    task = task_service.create_task(TaskCreate(title="Buy paint", project_id=project.id))

    assert task.project_id == project.id


def test_create_task_with_missing_project_id_raises(db_session):
    task_service = TaskService(db_session)

    with pytest.raises(ProjectNotFoundError):
        task_service.create_task(TaskCreate(title="Buy paint", project_id=999))


def test_create_task_with_archived_project_id_raises(db_session):
    project_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    project = project_service.create_project(ProjectCreate(name="Old project"))
    project_service.archive_project(project.id)

    with pytest.raises(ArchivedProjectError):
        task_service.create_task(TaskCreate(title="Buy paint", project_id=project.id))


def test_create_task_without_project_id_succeeds(db_session):
    task_service = TaskService(db_session)

    task = task_service.create_task(TaskCreate(title="Standalone task"))

    assert task.project_id is None


def test_update_task_to_archived_project_raises(db_session):
    project_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    project = project_service.create_project(ProjectCreate(name="Active for now"))
    task = task_service.create_task(TaskCreate(title="A task"))
    project_service.archive_project(project.id)

    with pytest.raises(ArchivedProjectError):
        task_service.update_task(task.id, TaskUpdate(project_id=project.id))


def test_archiving_project_does_not_affect_existing_task_assignment(db_session):
    """Tasks already assigned to a project keep their project_id, and stay
    fully readable, once that project is archived — no cascading change."""
    project_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    project = project_service.create_project(ProjectCreate(name="Wrapping up"))
    task = task_service.create_task(TaskCreate(title="Last task", project_id=project.id))

    project_service.archive_project(project.id)
    fetched = task_service.get_task(task.id)

    assert fetched.project_id == project.id


def test_marking_task_done_with_unresolved_dependency_raises(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = task_service.create_task(TaskCreate(title="A"))
    b = task_service.create_task(TaskCreate(title="B"))
    dep_service.add_dependency(b.id, a.id)  # B depends on A, A still todo

    with pytest.raises(UnresolvedDependencyError):
        task_service.update_task(b.id, TaskUpdate(status=TaskStatus.DONE))


def test_marking_task_done_after_dependency_resolved_succeeds(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = task_service.create_task(TaskCreate(title="A"))
    b = task_service.create_task(TaskCreate(title="B"))
    dep_service.add_dependency(b.id, a.id)

    task_service.update_task(a.id, TaskUpdate(status=TaskStatus.DONE))
    updated_b = task_service.update_task(b.id, TaskUpdate(status=TaskStatus.DONE))

    assert updated_b.status == TaskStatus.DONE


def test_marking_task_done_with_no_dependencies_succeeds(db_session):
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Standalone"))

    updated = task_service.update_task(task.id, TaskUpdate(status=TaskStatus.DONE))

    assert updated.status == TaskStatus.DONE


def test_non_status_update_does_not_trigger_dependency_check(db_session):
    """Updating an unrelated field on a task with unresolved dependencies
    must not be blocked — only actually moving to `done` is."""
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = task_service.create_task(TaskCreate(title="A"))
    b = task_service.create_task(TaskCreate(title="B"))
    dep_service.add_dependency(b.id, a.id)

    updated = task_service.update_task(b.id, TaskUpdate(title="B renamed"))

    assert updated.title == "B renamed"
