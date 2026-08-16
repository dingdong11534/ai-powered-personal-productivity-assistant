"""Tests for app.projects.service.ProjectService.

Run with: pytest tests/test_project_service.py -v
"""

import pytest

from app.projects.exceptions import ProjectNotFoundError
from app.projects.schemas import ProjectCreate, ProjectUpdate
from app.projects.service import ProjectService


def test_create_project_persists_and_returns_it(db_session):
    service = ProjectService(db_session)

    project = service.create_project(ProjectCreate(name="Home Renovation", color="teal"))

    assert project.id is not None
    assert project.name == "Home Renovation"
    assert project.color == "teal"
    assert project.archived_at is None


def test_get_project_raises_not_found_for_missing_id(db_session):
    service = ProjectService(db_session)

    with pytest.raises(ProjectNotFoundError):
        service.get_project(999)


def test_update_project_applies_only_provided_fields(db_session):
    service = ProjectService(db_session)
    project = service.create_project(ProjectCreate(name="Old", color="red"))

    updated = service.update_project(project.id, ProjectUpdate(name="New"))

    assert updated.name == "New"
    assert updated.color == "red"  # untouched


def test_update_project_raises_not_found_for_missing_id(db_session):
    service = ProjectService(db_session)

    with pytest.raises(ProjectNotFoundError):
        service.update_project(999, ProjectUpdate(name="x"))


def test_archive_project_sets_archived_at(db_session):
    service = ProjectService(db_session)
    project = service.create_project(ProjectCreate(name="Done project"))
    assert project.archived_at is None

    archived = service.archive_project(project.id)

    assert archived.archived_at is not None


def test_archive_project_raises_not_found_for_missing_id(db_session):
    service = ProjectService(db_session)

    with pytest.raises(ProjectNotFoundError):
        service.archive_project(999)


def test_archiving_twice_just_re_stamps_archived_at(db_session):
    service = ProjectService(db_session)
    project = service.create_project(ProjectCreate(name="Done project"))

    first = service.archive_project(project.id)
    second = service.archive_project(project.id)

    assert first.archived_at is not None
    assert second.archived_at is not None


def test_list_projects_excludes_archived_when_requested(db_session):
    service = ProjectService(db_session)
    active = service.create_project(ProjectCreate(name="Active"))
    archived = service.create_project(ProjectCreate(name="Will archive"))
    service.archive_project(archived.id)

    projects = service.list_projects(include_archived=False)

    assert [p.id for p in projects] == [active.id]
