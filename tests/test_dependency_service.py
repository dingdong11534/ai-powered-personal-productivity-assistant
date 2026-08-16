"""Tests for app.tasks.dependency_service.TaskDependencyService.

Run with: pytest tests/test_dependency_service.py -v

The cycle-detection algorithm itself (a plain BFS) was additionally
verified standalone against several graph shapes (direct 2-cycles,
3-hop cycles, diamond shapes, unrelated tasks) before being wired into
this service — these tests check it end-to-end through the real
repository/database instead.
"""

import pytest

from app.tasks.exceptions import (
    DependencyCycleError,
    DuplicateDependencyError,
    SelfDependencyError,
    TaskNotFoundError,
)
from app.tasks.dependency_service import TaskDependencyService
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService


def _make_task(task_service, title):
    return task_service.create_task(TaskCreate(title=title))


def test_add_dependency_persists_edge(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")

    dep_service.add_dependency(b.id, a.id)  # B depends on A

    assert dep_service.list_dependencies(b.id) == [a.id]


def test_add_dependency_rejects_self_dependency(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")

    with pytest.raises(SelfDependencyError):
        dep_service.add_dependency(a.id, a.id)


def test_add_dependency_raises_task_not_found_for_missing_task(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")

    with pytest.raises(TaskNotFoundError):
        dep_service.add_dependency(999, a.id)

    with pytest.raises(TaskNotFoundError):
        dep_service.add_dependency(a.id, 999)


def test_add_dependency_rejects_exact_duplicate(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")
    dep_service.add_dependency(b.id, a.id)

    with pytest.raises(DuplicateDependencyError):
        dep_service.add_dependency(b.id, a.id)


def test_add_dependency_rejects_direct_two_cycle(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")
    dep_service.add_dependency(b.id, a.id)  # B depends on A

    with pytest.raises(DependencyCycleError):
        dep_service.add_dependency(a.id, b.id)  # A -> B would close A->B->A


def test_add_dependency_rejects_multi_hop_cycle(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")
    c = _make_task(task_service, "C")
    dep_service.add_dependency(a.id, b.id)  # A depends on B
    dep_service.add_dependency(b.id, c.id)  # B depends on C

    with pytest.raises(DependencyCycleError):
        dep_service.add_dependency(c.id, a.id)  # C -> A would close A->B->C->A


def test_add_dependency_allows_diamond_shape(db_session):
    """A depends on both B and C; B and C both depend on D. Not a cycle."""
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")
    c = _make_task(task_service, "C")
    d = _make_task(task_service, "D")

    dep_service.add_dependency(a.id, b.id)
    dep_service.add_dependency(a.id, c.id)
    dep_service.add_dependency(b.id, d.id)
    dep_service.add_dependency(c.id, d.id)  # should not raise

    assert set(dep_service.list_dependencies(a.id)) == {b.id, c.id}


def test_remove_dependency_deletes_edge(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")
    dep_service.add_dependency(b.id, a.id)

    dep_service.remove_dependency(b.id, a.id)

    assert dep_service.list_dependencies(b.id) == []


def test_remove_dependency_missing_edge_is_a_no_op(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")

    dep_service.remove_dependency(b.id, a.id)  # never existed — should not raise

    assert dep_service.list_dependencies(b.id) == []


def test_get_unresolved_dependencies_reports_incomplete_ones(db_session):
    task_service = TaskService(db_session)
    dep_service = TaskDependencyService(db_session)
    a = _make_task(task_service, "A")
    b = _make_task(task_service, "B")
    dep_service.add_dependency(b.id, a.id)

    unresolved = dep_service.get_unresolved_dependencies(b.id)

    assert [t.id for t in unresolved] == [a.id]
