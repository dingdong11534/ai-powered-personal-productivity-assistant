"""Tests for app.tasks.tag_service.TagService.

Run with: pytest tests/test_tag_service.py -v
"""

import pytest

from app.tasks.exceptions import DuplicateTagError, TagNotFoundError, TaskNotFoundError
from app.tasks.schemas import TagCreate, TaskCreate
from app.tasks.service import TaskService
from app.tasks.tag_service import TagService


def test_create_tag_persists_and_returns_it(db_session):
    service = TagService(db_session)

    tag = service.create_tag(TagCreate(name="urgent"))

    assert tag.id is not None
    assert tag.name == "urgent"


def test_create_tag_rejects_duplicate_name(db_session):
    service = TagService(db_session)
    service.create_tag(TagCreate(name="urgent"))

    with pytest.raises(DuplicateTagError):
        service.create_tag(TagCreate(name="urgent"))


def test_list_tags_returns_created_tags(db_session):
    service = TagService(db_session)
    service.create_tag(TagCreate(name="urgent"))
    service.create_tag(TagCreate(name="home"))

    tags = service.list_tags()

    assert {t.name for t in tags} == {"urgent", "home"}


def test_attach_tag_to_task_adds_it(db_session):
    tag_service = TagService(db_session)
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Pay bills"))
    tag = tag_service.create_tag(TagCreate(name="finance"))

    updated_task = tag_service.attach_tag_to_task(task.id, tag.id)

    assert [t.name for t in updated_task.tags] == ["finance"]


def test_attach_tag_twice_is_idempotent(db_session):
    tag_service = TagService(db_session)
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Pay bills"))
    tag = tag_service.create_tag(TagCreate(name="finance"))

    tag_service.attach_tag_to_task(task.id, tag.id)
    updated_task = tag_service.attach_tag_to_task(task.id, tag.id)

    assert [t.name for t in updated_task.tags] == ["finance"]  # still just one


def test_attach_tag_raises_task_not_found(db_session):
    tag_service = TagService(db_session)
    tag = tag_service.create_tag(TagCreate(name="finance"))

    with pytest.raises(TaskNotFoundError):
        tag_service.attach_tag_to_task(999, tag.id)


def test_attach_tag_raises_tag_not_found(db_session):
    task_service = TaskService(db_session)
    tag_service = TagService(db_session)
    task = task_service.create_task(TaskCreate(title="Pay bills"))

    with pytest.raises(TagNotFoundError):
        tag_service.attach_tag_to_task(task.id, 999)


def test_detach_tag_removes_it(db_session):
    tag_service = TagService(db_session)
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Pay bills"))
    tag = tag_service.create_tag(TagCreate(name="finance"))
    tag_service.attach_tag_to_task(task.id, tag.id)

    updated_task = tag_service.detach_tag_from_task(task.id, tag.id)

    assert updated_task.tags == []


def test_detach_tag_not_attached_is_idempotent(db_session):
    tag_service = TagService(db_session)
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Pay bills"))
    tag = tag_service.create_tag(TagCreate(name="finance"))

    updated_task = tag_service.detach_tag_from_task(task.id, tag.id)  # never attached

    assert updated_task.tags == []


def test_get_task_tags_returns_attached_tags(db_session):
    tag_service = TagService(db_session)
    task_service = TaskService(db_session)
    task = task_service.create_task(TaskCreate(title="Pay bills"))
    finance = tag_service.create_tag(TagCreate(name="finance"))
    home = tag_service.create_tag(TagCreate(name="home"))
    tag_service.attach_tag_to_task(task.id, finance.id)
    tag_service.attach_tag_to_task(task.id, home.id)

    tags = tag_service.get_task_tags(task.id)

    assert {t.name for t in tags} == {"finance", "home"}
