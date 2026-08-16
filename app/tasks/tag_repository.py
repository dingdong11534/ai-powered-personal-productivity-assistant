"""
TagRepository — direct, ORM-level access to `tags` and the `task_tags`
association table.

Same "dumb, no business rules" role as TaskRepository/ProjectRepository —
see those modules' docstrings for the layering rationale. TagService owns
the rules (uniqueness messaging, idempotent attach/detach).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Tag, Task


class TagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, tag: Tag) -> Tag:
        self.db.add(tag)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def get(self, tag_id: int) -> Tag | None:
        return self.db.get(Tag, tag_id)

    def get_by_name(self, name: str) -> Tag | None:
        stmt = select(Tag).where(Tag.name == name)
        return self.db.scalars(stmt).first()

    def list(self) -> list[Tag]:
        stmt = select(Tag).order_by(Tag.name)
        return list(self.db.scalars(stmt))

    def attach(self, task: Task, tag: Tag) -> None:
        """Add `tag` to `task.tags` if it isn't already there, then
        commit. Uses the ORM relationship (rather than inserting into
        `task_tags` directly) so SQLAlchemy's own duplicate-avoidance
        for relationship collections applies, on top of the caller
        (TagService) already checking first."""
        if tag not in task.tags:
            task.tags.append(tag)
            self.db.commit()

    def detach(self, task: Task, tag: Tag) -> None:
        """Remove `tag` from `task.tags` if present, then commit. A no-op
        (not an error) if the tag wasn't attached — see TagService for
        why detach is idempotent."""
        if tag in task.tags:
            task.tags.remove(tag)
            self.db.commit()
