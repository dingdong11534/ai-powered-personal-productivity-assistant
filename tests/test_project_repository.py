"""Tests for app.projects.repository.ProjectRepository.

Run with: pytest tests/test_project_repository.py -v
"""

from datetime import datetime

from app.projects.repository import ProjectRepository
from app.storage.models import Project


def test_create_assigns_id_and_defaults(db_session):
    repo = ProjectRepository(db_session)

    project = repo.create(Project(name="Home Renovation"))

    assert project.id is not None
    assert project.created_at is not None
    assert project.archived_at is None


def test_get_returns_created_project(db_session):
    repo = ProjectRepository(db_session)
    created = repo.create(Project(name="Home Renovation"))

    fetched = repo.get(created.id)

    assert fetched is not None
    assert fetched.name == "Home Renovation"


def test_get_returns_none_for_missing_id(db_session):
    repo = ProjectRepository(db_session)

    assert repo.get(999) is None


def test_list_returns_all_created_projects(db_session):
    repo = ProjectRepository(db_session)
    repo.create(Project(name="A"))
    repo.create(Project(name="B"))

    projects = repo.list()

    assert len(projects) == 2


def test_list_include_archived_false_excludes_archived(db_session):
    repo = ProjectRepository(db_session)
    active = repo.create(Project(name="Active"))
    archived = repo.create(Project(name="Archived"))
    repo.update(archived, {"archived_at": datetime(2026, 1, 1)})

    projects = repo.list(include_archived=False)

    assert [p.id for p in projects] == [active.id]


def test_update_changes_only_given_fields(db_session):
    repo = ProjectRepository(db_session)
    project = repo.create(Project(name="Old name", color="blue"))

    updated = repo.update(project, {"name": "New name"})

    assert updated.name == "New name"
    assert updated.color == "blue"  # untouched
