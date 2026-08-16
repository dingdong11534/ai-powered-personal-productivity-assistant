"""
TagService — the layer app.interfaces routes call for tags.

WHAT THIS DOES
---------------
Owns two kinds of rule TagRepository doesn't:
1. Tag name uniqueness, reported as a domain error (`DuplicateTagError`)
   instead of a raw `IntegrityError` bubbling out of a commit.
2. Idempotent attach/detach: attaching a tag a task already has, or
   detaching one it doesn't, is treated as "already in the desired
   state" and succeeds silently rather than raising. This keeps the tag
   API simple for callers (a client doesn't need to check "is this tag
   already attached?" before attaching — see "Requirements: duplicate
   task/tag associations should not be possible" from the brief, which
   this satisfies at both the DB level, via `task_tags`'s composite
   primary key, and here).

WHY A SEPARATE SERVICE FROM TaskService
--------------------------------------------
Tags are a distinct concern from a task's own fields (title, status,
priority, ...) — folding tag logic into TaskService would grow it into
exactly the kind of do-everything manager class the project brief asks
to avoid. TagService depends on TaskRepository only to fetch the Task a
tag is being attached to/from (via `get_task`, injected at construction)
— it doesn't duplicate task-lookup logic, it reuses TaskRepository's.

HOW TO TEST
------------
See tests/test_tag_service.py.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import Tag, Task
from app.tasks.exceptions import DuplicateTagError, TagNotFoundError, TaskNotFoundError
from app.tasks.repository import TaskRepository
from app.tasks.schemas import TagCreate
from app.tasks.tag_repository import TagRepository


class TagService:
    def __init__(self, db: Session) -> None:
        self.tags = TagRepository(db)
        self.tasks = TaskRepository(db)

    def create_tag(self, data: TagCreate) -> Tag:
        if self.tags.get_by_name(data.name) is not None:
            raise DuplicateTagError(data.name)
        return self.tags.create(Tag(name=data.name))

    def list_tags(self) -> list[Tag]:
        return self.tags.list()

    def get_task_tags(self, task_id: int) -> list[Tag]:
        task = self._get_task(task_id)
        return task.tags

    def attach_tag_to_task(self, task_id: int, tag_id: int) -> Task:
        task = self._get_task(task_id)
        tag = self._get_tag(tag_id)
        self.tags.attach(task, tag)
        return task

    def detach_tag_from_task(self, task_id: int, tag_id: int) -> Task:
        task = self._get_task(task_id)
        tag = self._get_tag(tag_id)
        self.tags.detach(task, tag)
        return task

    def _get_task(self, task_id: int) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def _get_tag(self, tag_id: int) -> Tag:
        tag = self.tags.get(tag_id)
        if tag is None:
            raise TagNotFoundError(tag_id)
        return tag
